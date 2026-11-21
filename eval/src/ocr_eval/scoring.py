"""필드 채점: 정규화 후 정확 일치. 부분 점수 없음.

백엔드 비유: 필드 1개 = assert 1개. 정규화는 "표기 차이"(콤마, 하이픈, 날짜 구분자)만 없애고
"값 차이"(자릿수, 숫자, 글자)는 그대로 남긴다. 그래서 정규화가 오독을 숨기지 않는다.

필드 타입(`x-ocr-type`, schema.json):
- amount: 정수(원). "1,234,000", "1234000원", 1234000 → 1234000
- date:   YYYY-MM-DD. "2026. 7. 25.", "2026년 07월 25일", "2026/07/25" → "2026-07-25"
- id:     숫자·영문만 남김. "000-12-34567" == "000 12 34567" == "0001234567"
- text:   앞뒤 공백 제거, 연속 공백 1개로, NFC 정규화. 괄호·(주) 등은 그대로 비교
- 공통 null: None, "", "null", "None", "-", "없음", "해당 없음", "N/A" → None
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

NULL_STRINGS = {"", "null", "none", "-", "—", "없음", "해당없음", "해당 없음", "n/a", "na"}

_DATE_RE = re.compile(r"^\s*(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*[.일]?\s*$")


class Unparseable(str):
    """정규화 실패 표시. 원문을 그대로 들고 다니며 어떤 정답과도 같지 않다."""

    def __eq__(self, other: object) -> bool:  # noqa: D105
        return False

    __hash__ = str.__hash__


def is_null(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and v.strip().lower() in NULL_STRINGS:
        return True
    return False


def norm_amount(v: Any) -> int | None | Unparseable:
    if is_null(v):
        return None
    if isinstance(v, bool):
        return Unparseable(str(v))
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if v.is_integer() else Unparseable(str(v))
    s = str(v).strip().replace(",", "").replace(" ", "").removesuffix("원").removeprefix("₩")
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return Unparseable(str(v))


def norm_date(v: Any) -> str | None | Unparseable:
    if is_null(v):
        return None
    m = _DATE_RE.match(str(v))
    if not m:
        return Unparseable(str(v))
    y, mo, d = (int(x) for x in m.groups())
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return Unparseable(str(v))
    return f"{y:04d}-{mo:02d}-{d:02d}"


def norm_id(v: Any) -> str | None:
    if is_null(v):
        return None
    s = unicodedata.normalize("NFKC", str(v))
    return re.sub(r"[^0-9A-Za-z]", "", s).upper() or None


def norm_text(v: Any) -> str | None:
    if is_null(v):
        return None
    s = unicodedata.normalize("NFC", str(v))
    return re.sub(r"\s+", " ", s).strip()


NORMALIZERS = {"amount": norm_amount, "date": norm_date, "id": norm_id, "text": norm_text}


def field_types(schema: dict) -> dict[str, str]:
    return {k: p.get("x-ocr-type", "text") for k, p in schema["properties"].items()}


@dataclass
class FieldResult:
    field: str
    ftype: str
    gold: Any
    pred: Any
    gold_norm: Any
    pred_norm: Any
    correct: bool
    error: str | None  # None | missing | hallucination | misread | unparseable | no_json


def classify(gold_norm: Any, pred_norm: Any) -> str | None:
    if isinstance(pred_norm, Unparseable):
        return "unparseable"
    if gold_norm == pred_norm:
        return None
    if gold_norm is not None and pred_norm is None:
        return "missing"
    if gold_norm is None and pred_norm is not None:
        return "hallucination"
    return "misread"


def score_document(gold: dict, pred: dict | None, ftypes: dict[str, str]) -> list[FieldResult]:
    """pred=None(JSON 파싱 실패)이면 모든 필드를 no_json 오답으로 센다."""
    out: list[FieldResult] = []
    for f, t in ftypes.items():
        norm = NORMALIZERS[t]
        g = gold.get(f)
        gn = norm(g)
        if pred is None:
            out.append(FieldResult(f, t, g, None, gn, None, False, "no_json"))
            continue
        p = pred.get(f)
        pn = norm(p)
        err = classify(gn, pn)
        out.append(FieldResult(f, t, g, p, gn, pn, err is None, err))
    return out


def strip_meta(schema: dict, drop_keywords: list[str] | tuple[str, ...] = ()) -> dict:
    """서버에 보낼 스키마: `x-*` 메타와 `$schema`, 그리고 지정한 키워드(예: pattern)를 재귀적으로 뺀다."""
    drop = set(drop_keywords) | {"$schema"}

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items() if not k.startswith("x-") and k not in drop}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)
