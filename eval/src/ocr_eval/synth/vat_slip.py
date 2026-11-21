"""가상 부가가치세 납부서 합성기 (vat-slip-v1).

실행:
    uv run python -m ocr_eval.synth.vat_slip --out eval/datasets/vat-slip-v1

- seed 고정(기본 20261120). 같은 seed면 정답 JSON은 항상 같다. PNG 바이트는 Pillow 버전과
  macOS 폰트 파일이 같을 때 같다(manifest.json의 sha256으로 확인).
- 모든 상호·사업자번호·전자납부번호·계좌번호·세무서명은 가짜다.
  - 사업자등록번호: 앞 3자리 `000`(존재하지 않는 세무서 코드) + 체크섬을 일부러 틀리게 만든다.
  - 전자납부번호·가상계좌: `0000`/`000`으로 시작. 은행·세무서·상호는 가나다 순 음절로 만든 가상 이름.
- 모델이 읽어야 할 값은 문서에 인쇄된 값뿐이다. 합계(납부할 세액)도 인쇄해 두며, 모델이 계산하지 않게 한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DATASET = "vat-slip-v1"
DEFAULT_SEED = 20261120
WIDTH, HEIGHT = 1240, 1754  # A4 @150dpi
FONT_CANDIDATES = [
    ("/System/Library/Fonts/AppleSDGothicNeo.ttc", {"regular": 0, "medium": 2, "bold": 6}),
    ("/System/Library/Fonts/Supplemental/AppleGothic.ttf", {"regular": 0, "medium": 0, "bold": 0}),
]

# 추출 스키마. 필드명은 앱(ocr-agent) ocr 모듈과 맞출 이름(snake_case, 영문).
# `x-ocr-type`은 채점기 전용 메타데이터이며 서버로 보낼 때 제거한다.
DATE_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "vat_slip",
    "description": "부가가치세 납부서에서 읽은 값. 문서에 없는 값은 null. 계산하지 않는다.",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "taxpayer_name",
        "business_reg_no",
        "tax_item",
        "tax_period_start",
        "tax_period_end",
        "due_date",
        "total_amount",
        "electronic_payment_no",
        "virtual_account_no",
        "tax_office",
    ],
    "properties": {
        "taxpayer_name": {"type": ["string", "null"], "description": "납부자 상호", "x-ocr-type": "text"},
        "business_reg_no": {"type": ["string", "null"], "description": "사업자등록번호(문서 표기 그대로)", "x-ocr-type": "id"},
        "tax_item": {"type": ["string", "null"], "description": "세목", "x-ocr-type": "text"},
        "tax_period_start": {"type": ["string", "null"], "pattern": DATE_PATTERN, "description": "과세기간 시작일 YYYY-MM-DD", "x-ocr-type": "date"},
        "tax_period_end": {"type": ["string", "null"], "pattern": DATE_PATTERN, "description": "과세기간 종료일 YYYY-MM-DD", "x-ocr-type": "date"},
        "due_date": {"type": ["string", "null"], "pattern": DATE_PATTERN, "description": "납부기한 YYYY-MM-DD", "x-ocr-type": "date"},
        "total_amount": {"type": ["integer", "null"], "description": "납부할 세액 합계(원, 정수)", "x-ocr-type": "amount"},
        "electronic_payment_no": {"type": ["string", "null"], "description": "전자납부번호(문서 표기 그대로)", "x-ocr-type": "id"},
        "virtual_account_no": {"type": ["string", "null"], "description": "납부 가상계좌 번호(문서 표기 그대로)", "x-ocr-type": "id"},
        "tax_office": {"type": ["string", "null"], "description": "관할 세무서명", "x-ocr-type": "text"},
    },
}

# 문서별 변주 계획: 금액 자릿수 6~10, 날짜·번호 표기, 가상계좌 유무를 고르게 섞는다.
# va: "show" = 계좌 인쇄, "omit" = 계좌 행 자체가 없음, "blank" = 행은 있고 값 칸이 비어 있음 → 정답 null
PLAN = [
    {"digits": 6, "date_style": "dot_space", "brn_style": "hyphen", "epn_style": "hyphen", "va": "show", "period": ("2026", 1, "확정")},
    {"digits": 7, "date_style": "korean", "brn_style": "hyphen", "epn_style": "space", "va": "show", "period": ("2025", 2, "확정")},
    {"digits": 8, "date_style": "iso", "brn_style": "plain", "epn_style": "hyphen", "va": "omit", "period": ("2026", 1, "예정")},
    {"digits": 9, "date_style": "dot", "brn_style": "hyphen", "epn_style": "plain", "va": "show", "period": ("2025", 2, "예정")},
    {"digits": 10, "date_style": "korean_pad", "brn_style": "hyphen", "epn_style": "hyphen", "va": "show", "period": ("2024", 2, "확정")},
    {"digits": 6, "date_style": "slash", "brn_style": "space", "epn_style": "hyphen", "va": "show", "period": ("2025", 1, "확정")},
    {"digits": 8, "date_style": "dot_space", "brn_style": "hyphen", "epn_style": "space", "va": "blank", "period": ("2024", 1, "예정")},
    {"digits": 10, "date_style": "iso", "brn_style": "hyphen", "epn_style": "hyphen", "va": "show", "period": ("2026", 2, "예정")},
]
NAMES = [
    "가나다상사",
    "(주)라마바테크",
    "주식회사 사아자물산",
    "차카타푸드",
    "파하솔루션(주)",
    "거너더상회",
    "러머버에너지(주)",
    "서어저유통",
]
TAX_OFFICES = ["가람세무서", "나래세무서", "다온세무서", "라온세무서"]
BANKS = ["가나은행", "다라은행", "마바은행"]


@dataclass
class Slip:
    doc_id: str
    label: dict
    render: dict  # 인쇄용 문자열


def fmt_date(d: date, style: str) -> str:
    return {
        "iso": f"{d:%Y-%m-%d}",
        "dot": f"{d:%Y.%m.%d}",
        "dot_space": f"{d.year}. {d.month:02d}. {d.day:02d}.",
        "korean": f"{d.year}년 {d.month}월 {d.day}일",
        "korean_pad": f"{d.year}년 {d.month:02d}월 {d.day:02d}일",
        "slash": f"{d:%Y/%m/%d}",
    }[style]


def fake_brn(rng: random.Random) -> str:
    """사업자등록번호 형식(3-2-5) + 앞자리 000 + 체크섬 불일치."""
    weights = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    while True:
        digits = [0, 0, 0] + [rng.randint(0, 9) for _ in range(7)]
        s = sum(d * w for d, w in zip(digits[:9], weights)) + (digits[8] * 5) // 10
        valid_check = (10 - s % 10) % 10
        if digits[9] != valid_check:  # 일부러 틀린 체크섬만 채택
            return "".join(map(str, digits))


def style_brn(raw: str, style: str) -> str:
    a, b, c = raw[:3], raw[3:5], raw[5:]
    return {"hyphen": f"{a}-{b}-{c}", "plain": raw, "space": f"{a} {b} {c}"}[style]


def style_epn(raw: str, style: str) -> str:
    """전자납부번호 19자리 = 4-4-1-10 구분 표기(가짜, 0000으로 시작)."""
    parts = [raw[:4], raw[4:8], raw[8:9], raw[9:]]
    return {"hyphen": "-".join(parts), "space": " ".join(parts), "plain": raw}[style]


def period_dates(year: str, half: int, kind: str) -> tuple[date, date, date]:
    y = int(year)
    if half == 1:
        start = date(y, 1, 1)
        end = date(y, 3, 31) if kind == "예정" else date(y, 6, 30)
    else:
        start = date(y, 7, 1)
        end = date(y, 9, 30) if kind == "예정" else date(y, 12, 31)
    nxt = end + timedelta(days=1)  # 과세기간 종료 다음 달 25일
    due = date(nxt.year, nxt.month, 25)
    return start, end, due


def amount_with_digits(rng: random.Random, digits: int) -> int:
    lo, hi = 10 ** (digits - 1), 10**digits - 1
    return rng.randint(lo // 10, hi // 10) * 10  # 원 단위 끝자리 0 (실무 표기처럼 10원 단위)


def build_slips(seed: int) -> list[Slip]:
    rng = random.Random(seed)
    slips: list[Slip] = []
    for i, plan in enumerate(PLAN, start=1):
        doc_id = f"vat-slip-{i:03d}"
        total = amount_with_digits(rng, plan["digits"])
        # 가산세는 0 또는 합계의 일부. 본세 = 합계 - 가산세. 합계를 인쇄하므로 모델은 계산할 필요가 없다.
        penalty = 0 if i % 3 else (total // 100) // 10 * 10
        base = total - penalty
        brn_raw = fake_brn(rng)
        epn_raw = "0000" + "".join(str(rng.randint(0, 9)) for _ in range(15))
        va_raw = "000-" + "".join(str(rng.randint(0, 9)) for _ in range(4)) + "-" + "".join(
            str(rng.randint(0, 9)) for _ in range(4)
        ) + "-" + "".join(str(rng.randint(0, 9)) for _ in range(2))
        start, end, due = period_dates(*plan["period"])
        issued = due - timedelta(days=rng.randint(5, 20))  # 발행일: 정답 필드가 아닌 방해 날짜
        office = TAX_OFFICES[rng.randrange(len(TAX_OFFICES))]
        bank = BANKS[rng.randrange(len(BANKS))]
        brn_printed = style_brn(brn_raw, plan["brn_style"])
        epn_printed = style_epn(epn_raw, plan["epn_style"])
        va_printed = va_raw if plan["va"] == "show" else None
        ds = plan["date_style"]
        year, half, kind = plan["period"]
        label = {
            "taxpayer_name": NAMES[i - 1],
            "business_reg_no": brn_printed,
            "tax_item": "부가가치세",
            "tax_period_start": start.isoformat(),
            "tax_period_end": end.isoformat(),
            "due_date": due.isoformat(),
            "total_amount": total,
            "electronic_payment_no": epn_printed,
            "virtual_account_no": va_printed,
            "tax_office": office,
        }
        render = {
            "name": NAMES[i - 1],
            "brn": brn_printed,
            "period_title": f"{year}년 {half}기 {kind}",
            "period": f"{fmt_date(start, ds)} ~ {fmt_date(end, ds)}",
            "due": fmt_date(due, ds),
            "issued": fmt_date(issued, ds),
            "office": office,
            "epn": epn_printed,
            "va_mode": plan["va"],
            "bank": bank,
            "va": va_raw,
            "base": f"{base:,}",
            "penalty": f"{penalty:,}",
            "total": f"{total:,}",
        }
        slips.append(Slip(doc_id, label, render))
    return slips


# ---------------------------------------------------------------- 렌더링
def load_fonts() -> tuple[str, dict]:
    for path, idx in FONT_CANDIDATES:
        if Path(path).exists():
            return path, idx
    raise FileNotFoundError("한국어 폰트를 찾지 못했습니다 (AppleSDGothicNeo/AppleGothic).")


def render(slip: Slip) -> Image.Image:
    font_path, idx = load_fonts()

    def F(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(font_path, size, index=idx[weight])

    r = slip.render
    img = Image.new("RGB", (WIDTH, HEIGHT), "white")
    d = ImageDraw.Draw(img)
    black, gray = (0, 0, 0), (110, 110, 110)
    L, R = 90, WIDTH - 90

    # 머리말
    d.text((L, 70), "합성 견본 · 평가용 (실제 서류 아님)", font=F(20), fill=gray)
    d.text((WIDTH // 2, 150), "부가가치세 납부서", font=F(56, "bold"), fill=black, anchor="mm")
    d.text((WIDTH // 2, 215), f"({r['period_title']} · 납부자용)", font=F(28, "medium"), fill=black, anchor="mm")
    d.line([(L, 260), (R, 260)], fill=black, width=3)

    # 기본 정보 표
    rows: list[tuple[str, str]] = [
        ("납부자 상호", r["name"]),
        ("사업자등록번호", r["brn"]),
        ("세목", "부가가치세"),
        ("과세기간", r["period"]),
        ("납부기한", r["due"]),
        ("관할세무서", r["office"]),
        ("전자납부번호", r["epn"]),
    ]
    if r["va_mode"] == "show":
        rows.append(("납부계좌(가상계좌)", f"{r['bank']}  {r['va']}"))
    elif r["va_mode"] == "blank":
        rows.append(("납부계좌(가상계좌)", ""))
    y, row_h, key_w = 290, 74, 300
    for key, val in rows:
        d.rectangle([L, y, R, y + row_h], outline=black, width=2)
        d.rectangle([L, y, L + key_w, y + row_h], fill=(238, 238, 238), outline=black, width=2)
        d.text((L + 20, y + row_h // 2), key, font=F(28, "medium"), fill=black, anchor="lm")
        d.text((L + key_w + 24, y + row_h // 2), val, font=F(30), fill=black, anchor="lm")
        y += row_h

    # 세액 표 (합계는 인쇄됨)
    y += 50
    d.text((L, y), "납부할 세액", font=F(32, "bold"), fill=black)
    y += 56
    col = [L, L + 420, R]
    d.rectangle([L, y, R, y + row_h], fill=(238, 238, 238), outline=black, width=2)
    d.line([(col[1], y), (col[1], y + row_h)], fill=black, width=2)
    d.text((L + 20, y + row_h // 2), "구분", font=F(28, "medium"), fill=black, anchor="lm")
    d.text((R - 24, y + row_h // 2), "금액(원)", font=F(28, "medium"), fill=black, anchor="rm")
    y += row_h
    for key, val, bold in [("본세", r["base"], False), ("가산세", r["penalty"], False), ("합계", r["total"], True)]:
        d.rectangle([L, y, R, y + row_h], outline=black, width=3 if bold else 2)
        d.line([(col[1], y), (col[1], y + row_h)], fill=black, width=2)
        w = "bold" if bold else "regular"
        d.text((L + 20, y + row_h // 2), key, font=F(30, "bold" if bold else "medium"), fill=black, anchor="lm")
        d.text((R - 24, y + row_h // 2), val, font=F(34 if bold else 30, w), fill=black, anchor="rm")
        y += row_h

    # 꼬리말 (방해 정보: 발행일, 안내문)
    y += 50
    for line in [
        "위 금액을 납부기한까지 납부하시기 바랍니다.",
        "납부기한이 지나면 납부지연가산세가 추가될 수 있습니다.",
        "전자납부번호로 인터넷뱅킹·가상계좌 납부가 가능합니다.",
    ]:
        d.text((L, y), line, font=F(24), fill=black)
        y += 42
    y += 30
    d.text((L, y), f"발행일  {r['issued']}", font=F(26), fill=black)
    d.text((R, y), f"{r['office']}장", font=F(30, "bold"), fill=black, anchor="ra")
    # 수납인 칸
    d.rectangle([R - 220, y + 60, R, y + 200], outline=black, width=2)
    assert y + 200 < HEIGHT - 20, "레이아웃이 페이지를 넘음"
    d.text((R - 110, y + 82), "수납인", font=F(22), fill=gray, anchor="mm")
    d.text((L, HEIGHT - 70), f"{slip.doc_id}  ·  {DATASET}  ·  synthetic", font=F(18), fill=gray)
    return img


def write_dataset(out: Path, seed: int) -> list[dict]:
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    schema_text = json.dumps(SCHEMA, ensure_ascii=False, indent=2) + "\n"
    (out / "schema.json").write_text(schema_text, encoding="utf-8")
    manifest = []
    for slip in build_slips(seed):
        img_path = out / "images" / f"{slip.doc_id}.png"
        render(slip).save(img_path, format="PNG", dpi=(150, 150), optimize=False)
        label_path = out / "labels" / f"{slip.doc_id}.json"
        label_path.write_text(json.dumps(slip.label, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest.append(
            {
                "doc_id": slip.doc_id,
                "image": f"images/{img_path.name}",
                "label": f"labels/{label_path.name}",
                "image_sha256": hashlib.sha256(img_path.read_bytes()).hexdigest(),
                "label_sha256": hashlib.sha256(label_path.read_bytes()).hexdigest(),
                "amount_digits": len(str(slip.label["total_amount"])),
                "date_style": PLAN[int(slip.doc_id[-3:]) - 1]["date_style"],
                "virtual_account": slip.render["va_mode"],
            }
        )
    font_path, _ = load_fonts()
    import PIL

    meta = {
        "dataset": DATASET,
        "seed": seed,
        "size": [WIDTH, HEIGHT],
        "dpi": 150,
        "font": Path(font_path).name,
        "pillow": PIL.__version__,
        "schema_sha256": hashlib.sha256(schema_text.encode()).hexdigest(),
        "docs": manifest,
    }
    (out / "manifest.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("eval/datasets") / DATASET)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = ap.parse_args()
    manifest = write_dataset(args.out, args.seed)
    for m in manifest:
        print(f"{m['doc_id']}  digits={m['amount_digits']:>2}  date={m['date_style']:<10}  va={m['virtual_account']}")
    print(f"wrote {len(manifest)} docs -> {args.out}")


if __name__ == "__main__":
    main()
