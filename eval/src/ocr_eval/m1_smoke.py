"""M1 스모크 실행기: 문서 이미지 → /v1/chat/completions(구조화 출력) → 필드 채점.

    # 서버 없이 요청 본문만 만들어 확인 (네트워크 호출 없음)
    uv run python -m ocr_eval.m1_smoke --config eval/configs/m1-smoke-vat-slip.yaml --model qwen3vl-8b --dry-run
    # 첫 1장만 호출하고 멈춤 (워밍업 없음) → results/{model}/limit-1/
    uv run python -m ocr_eval.m1_smoke --config eval/configs/m1-smoke-vat-slip.yaml --model qwen3vl-8b --limit 1
    # 본 측정 (워밍업 1건 + 8장) → results/{model}/
    uv run python -m ocr_eval.m1_smoke --config eval/configs/m1-smoke-vat-slip.yaml --model qwen3vl-8b

접속 정보는 `.env`의 LLM_BASE_URL, LLM_API_KEY에서 읽고, 화면·로그·결과 파일에 쓰지 않는다.
모델 이름은 --model(없으면 LLM_MODEL)로 받는다.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import re
import statistics
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from PIL import Image

from ocr_core.settings import LLMSettings, find_repo_root, llm_settings
from ocr_eval.scoring import field_types, score_document, strip_meta

PATCH_PX = 32  # Qwen3-VL / Qwen3.5: patch 16 × spatial merge 2 → 32×32 px당 토큰 1개


# ---------------------------------------------------------------- 준비
def model_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9.\-]+", "-", name.lower()).strip("-")


def est_image_tokens(w: int, h: int, patch: int = PATCH_PX) -> int:
    """Qwen smart_resize 근사: 각 변을 patch 배수로 반올림. 픽셀 상한 안쪽일 때만 맞다."""
    return max(1, round(w / patch)) * max(1, round(h / patch))


def load_docs(dataset: Path) -> list[dict]:
    docs = []
    for label_path in sorted((dataset / "labels").glob("*.json")):
        doc_id = label_path.stem
        img = dataset / "images" / f"{doc_id}.png"
        if not img.exists():
            raise FileNotFoundError(f"정답만 있고 이미지가 없음: {img}")
        docs.append({"doc_id": doc_id, "image": img, "gold": json.loads(label_path.read_text(encoding="utf-8"))})
    if not docs:
        raise FileNotFoundError(f"정답 JSON이 없는 데이터셋: {dataset}/labels")
    return docs


def data_url(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def build_body(model: str, image_url: str, cfg: dict, server_schema: dict) -> dict:
    req, prompt = cfg["request"], cfg["prompt"]
    messages: list[dict] = []
    if prompt.get("system"):
        messages.append({"role": "system", "content": prompt["system"]})
    messages.append(
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_url}},  # 이미지 먼저, 지시문 다음 (Qwen 권장 순서)
                {"type": "text", "text": prompt["user"].strip()},
            ],
        }
    )
    return {
        "model": model,
        "messages": messages,
        "temperature": req["temperature"],
        "max_tokens": req["max_tokens"],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": req.get("response_format_name", "extraction"),
                "schema": server_schema,
                "strict": bool(req.get("strict", True)),
            },
        },
    }


def git_sha(root: Path) -> str | None:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True, check=True)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout.strip()
        return sha.stdout.strip() + ("-dirty" if dirty else "")
    except Exception:
        return None


# ---------------------------------------------------------------- 호출
def call_once(client, body: dict, extra_body: dict, settings: LLMSettings) -> dict:
    """요청 1건. 예외도 결과로 돌려준다(에러 문자열은 URL·키를 가린 뒤 저장)."""
    t0 = time.perf_counter()
    try:
        resp = client.chat.completions.create(**body, extra_body=extra_body or None)
        latency = time.perf_counter() - t0
        choice = resp.choices[0]
        usage = resp.usage
        return {
            "ok": True,
            "latency_s": round(latency, 4),
            "raw_text": choice.message.content,
            "finish_reason": choice.finish_reason,
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "error": None,
        }
    except Exception as e:  # noqa: BLE001
        latency = time.perf_counter() - t0
        status = getattr(e, "status_code", None)
        return {
            "ok": False,
            "latency_s": round(latency, 4),
            "raw_text": None,
            "finish_reason": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "error": settings.redact(f"{type(e).__name__}(status={status}): {e}")[:2000],
        }


def parse_and_validate(raw: str | None, validator: Draft202012Validator) -> tuple[dict | None, bool, bool, list[str]]:
    """(pred, json_parsed, schema_valid, schema_errors)"""
    if raw is None:
        return None, False, False, ["no response"]
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, False, False, [f"json: {e.msg} at {e.pos}"]
    if not isinstance(obj, dict):
        return None, True, False, ["top-level is not an object"]
    errs = [f"{'/'.join(map(str, er.path)) or '<root>'}: {er.message}" for er in validator.iter_errors(obj)]
    return obj, True, not errs, errs


# ---------------------------------------------------------------- 요약
def summarize(rows: list[dict], fields: list[dict], ftypes: dict[str, str]) -> dict:
    n = len(rows)
    lat = [r["latency_s"] for r in rows if r["ok"]]
    pt = [r["prompt_tokens"] for r in rows if r["prompt_tokens"] is not None]
    ct = [r["completion_tokens"] for r in rows if r["completion_tokens"] is not None]

    def acc(sel: list[dict]) -> dict:
        k = sum(f["correct"] for f in sel)
        return {"correct": k, "total": len(sel), "rate": round(k / len(sel), 4) if sel else None}

    per_field = {f: acc([x for x in fields if x["field"] == f]) for f in ftypes}
    per_type = {t: acc([x for x in fields if x["ftype"] == t]) for t in sorted(set(ftypes.values()))}
    errors: dict[str, int] = {}
    for x in fields:
        if x["error"]:
            errors[x["error"]] = errors.get(x["error"], 0) + 1
    doc_exact = sum(all(x["correct"] for x in fields if x["doc_id"] == r["doc_id"]) for r in rows)
    return {
        "n_docs": n,
        "http_ok": sum(r["ok"] for r in rows),
        "json_parse_rate": round(sum(r["json_parsed"] for r in rows) / n, 4) if n else None,
        "json_valid_rate": round(sum(r["schema_valid"] for r in rows) / n, 4) if n else None,
        "json_valid": f"{sum(r['schema_valid'] for r in rows)}/{n}",
        "field_accuracy": acc(fields),
        "amount_field_accuracy": per_type.get("amount"),
        "doc_exact_match": {"correct": doc_exact, "total": n, "rate": round(doc_exact / n, 4) if n else None},
        "per_type": per_type,
        "per_field": per_field,
        "error_types": errors,
        "latency_s": {
            "mean": round(statistics.mean(lat), 3) if lat else None,
            "p50": round(statistics.median(lat), 3) if lat else None,
            "max": round(max(lat), 3) if lat else None,
            "n": len(lat),
        },
        "prompt_tokens": {"mean": round(statistics.mean(pt), 1) if pt else None, "min": min(pt) if pt else None, "max": max(pt) if pt else None},
        "completion_tokens": {"mean": round(statistics.mean(ct), 1) if ct else None, "max": max(ct) if ct else None},
        "finish_reasons": {fr: sum(r["finish_reason"] == fr for r in rows) for fr in {r["finish_reason"] for r in rows}},
    }


def print_summary(s: dict, model: str) -> None:
    fa, am, de = s["field_accuracy"], s["amount_field_accuracy"] or {}, s["doc_exact_match"]
    print(f"\n== {model} ==")
    print(f"HTTP OK          {s['http_ok']}/{s['n_docs']}")
    print(f"JSON 유효율      {s['json_valid']}  (parse {s['json_parse_rate']})")
    print(f"필드 정답률      {fa['correct']}/{fa['total']} = {fa['rate']}")
    print(f"금액 필드 정답률 {am.get('correct')}/{am.get('total')} = {am.get('rate')}")
    print(f"문서 완전 일치   {de['correct']}/{de['total']}")
    print(f"지연(s)          mean {s['latency_s']['mean']}  p50 {s['latency_s']['p50']}  max {s['latency_s']['max']}")
    print(f"prompt_tokens    mean {s['prompt_tokens']['mean']}  min {s['prompt_tokens']['min']}  max {s['prompt_tokens']['max']}")
    print(f"completion_tok   mean {s['completion_tokens']['mean']}  max {s['completion_tokens']['max']}")
    print(f"실패 유형        {s['error_types'] or '-'}")
    for f, a in s["per_field"].items():
        print(f"  {f:<22} {a['correct']}/{a['total']}")


# ---------------------------------------------------------------- 메인
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="M1 스모크: 문서 이미지 → JSON 추출 → 필드 채점")
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--model", help="served-model-name (없으면 .env LLM_MODEL)")
    ap.add_argument("--limit", type=int, help="앞에서 N장만. 주면 워밍업 기본 0, 결과는 results/{model}/limit-N/")
    ap.add_argument("--warmup", type=int, help="측정 제외 워밍업 요청 수 (config 값 덮어쓰기)")
    ap.add_argument("--dry-run", action="store_true", help="서버 호출 없이 요청 본문만 만들어 크기를 확인")
    ap.add_argument("--overwrite", action="store_true", help="기존 결과 폴더 덮어쓰기 허용")
    args = ap.parse_args(argv)

    root = find_repo_root()
    cfg = yaml.safe_load((root / args.config if not args.config.is_absolute() else args.config).read_text(encoding="utf-8"))
    dataset = root / cfg["dataset"]
    schema = json.loads((dataset / "schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    ftypes = field_types(schema)
    server_schema = strip_meta(schema, cfg["request"].get("schema_drop_keywords") or [])

    settings = None if args.dry_run else llm_settings(require=True)
    model = args.model or (settings.model if settings else None) or llm_settings(require=False).model
    if not model:
        ap.error("--model 또는 .env LLM_MODEL이 필요합니다")
    mcfg = (cfg.get("models") or {}).get(model)
    if mcfg is None:
        print(f"[warn] config.models에 '{model}'이 없어 extra_body 없이 보냅니다", file=sys.stderr)
    extra_body = (mcfg or {}).get("extra_body") or {}

    docs = load_docs(dataset)
    if args.limit:
        docs = docs[: args.limit]
    warmup = args.warmup if args.warmup is not None else (0 if args.limit else int(cfg.get("run", {}).get("warmup", 0)))

    out = root / cfg["results_root"] / model_slug(model)
    if args.dry_run:
        out = out / "dry-run"
    elif args.limit:
        out = out / f"limit-{args.limit}"
    if not args.dry_run and (out / "predictions.jsonl").exists() and not args.overwrite:
        print(f"[stop] 결과가 이미 있음: {out.relative_to(root)} (--overwrite로 덮어쓰기)", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    mime = cfg["request"].get("image_mime", "image/png")

    # ---- dry-run: 본문만 만든다
    if args.dry_run:
        previews = []
        for d in docs:
            with Image.open(d["image"]) as im:
                w, h = im.size
            url = data_url(d["image"], mime)
            body = build_body(model, url, cfg, server_schema)
            if extra_body:
                body = {**body, **extra_body}  # SDK extra_body는 최상위 키로 합쳐진다
            size = len(json.dumps(body, ensure_ascii=False).encode("utf-8"))
            preview = json.loads(json.dumps(body, ensure_ascii=False))
            preview["messages"][-1]["content"][0]["image_url"]["url"] = url[:48] + f"...<{len(url)} chars>"
            previews.append(
                {
                    "doc_id": d["doc_id"],
                    "image_wh": [w, h],
                    "png_bytes": d["image"].stat().st_size,
                    "data_url_chars": len(url),
                    "body_bytes": size,
                    "est_image_tokens": est_image_tokens(w, h),
                    "body_preview": preview,
                }
            )
            print(f"{d['doc_id']}  {w}x{h}  png {d['image'].stat().st_size/1024:.0f}KB  body {size/1024:.0f}KB  est_img_tokens {est_image_tokens(w, h)}")
        with (out / "requests-preview.jsonl").open("w", encoding="utf-8") as fh:
            for p in previews:
                fh.write(json.dumps(p, ensure_ascii=False) + "\n")
        sizes = [p["body_bytes"] for p in previews]
        print(f"\n[dry-run] {len(previews)}건 본문 생성, 평균 {statistics.mean(sizes)/1024:.1f}KB, 최대 {max(sizes)/1024:.1f}KB")
        print(f"[dry-run] extra_body={json.dumps(extra_body, ensure_ascii=False)}  warmup={warmup}")
        print(f"[dry-run] 미리보기: {(out / 'requests-preview.jsonl').relative_to(root)}")
        return 0

    # ---- 실제 호출
    from ocr_core.llm import make_client

    assert settings is not None
    client = make_client(settings, timeout_s=float(cfg["request"].get("timeout_s", 120)))
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")

    t0 = time.perf_counter()
    try:
        listed = [m.id for m in client.models.list().data]
        models_check = {"http_ok": True, "latency_s": round(time.perf_counter() - t0, 4), "ids": listed, "model_listed": model in listed}
    except Exception as e:  # noqa: BLE001
        models_check = {"http_ok": False, "error": settings.redact(f"{type(e).__name__}: {e}")[:1000]}
    (out / "models.json").write_text(json.dumps(models_check, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"GET /v1/models -> {models_check}")
    if not models_check.get("http_ok"):
        print("[stop] /v1/models 실패. 엔드포인트 미기동 또는 키 불일치", file=sys.stderr)
        return 3
    if not models_check["model_listed"]:
        print(f"[stop] 서버 모델 목록에 '{model}' 없음", file=sys.stderr)
        return 3

    warm_rows = []
    for i in range(warmup):
        body = build_body(model, data_url(docs[0]["image"], mime), cfg, server_schema)
        r = call_once(client, body, extra_body, settings)
        warm_rows.append({"warmup_index": i, "doc_id": docs[0]["doc_id"], **{k: r[k] for k in ("ok", "latency_s", "prompt_tokens", "completion_tokens", "finish_reason", "error")}})
        print(f"[warmup {i}] ok={r['ok']} {r['latency_s']}s")

    rows, fields = [], []
    for d in docs:
        body = build_body(model, data_url(d["image"], mime), cfg, server_schema)
        r = call_once(client, body, extra_body, settings)
        pred, parsed, valid, errs = parse_and_validate(r["raw_text"], validator)
        frs = score_document(d["gold"], pred, ftypes)
        n_ok = sum(f.correct for f in frs)
        rows.append(
            {
                "doc_id": d["doc_id"],
                **r,
                "json_parsed": parsed,
                "schema_valid": valid,
                "schema_errors": errs,
                "pred": pred,
                "fields_correct": n_ok,
                "fields_total": len(frs),
            }
        )
        for f in frs:
            fd = asdict(f)
            fields.append({"doc_id": d["doc_id"], **{k: (str(v) if k.endswith("_norm") and v is not None else v) for k, v in fd.items()}})
        print(f"{d['doc_id']}  ok={r['ok']}  {r['latency_s']}s  prompt={r['prompt_tokens']}  compl={r['completion_tokens']}  json={valid}  fields {n_ok}/{len(frs)}" + (f"  ERR {r['error'][:120]}" if r["error"] else ""))

    with (out / "predictions.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    if warm_rows:
        with (out / "warmup.jsonl").open("w", encoding="utf-8") as fh:
            for row in warm_rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (out / "fields.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["doc_id", "field", "ftype", "gold", "pred", "gold_norm", "pred_norm", "correct", "error"])
        w.writeheader()
        w.writerows(fields)

    summary = summarize(rows, fields, ftypes)
    manifest = dataset / "manifest.json"
    summary["meta"] = {
        "experiment_id": cfg["experiment_id"],
        "model": model,
        "extra_body": extra_body,
        "dataset": cfg["dataset"],
        "schema_sha256": json.loads(manifest.read_text(encoding="utf-8")).get("schema_sha256") if manifest.exists() else None,
        "endpoint": "env:LLM_BASE_URL",
        "request": {k: v for k, v in cfg["request"].items()},
        "warmup": warmup,
        "limit": args.limit,
        "started_utc": started,
        "git": git_sha(root),
        "est_image_tokens_per_doc": est_image_tokens(*Image.open(docs[0]["image"]).size),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print_summary(summary, model)
    print(f"\n결과: {out.relative_to(root)}/ (predictions.jsonl, fields.csv, summary.json, models.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
