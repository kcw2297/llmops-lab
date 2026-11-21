import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from ocr_core.settings import LLMSettings
from ocr_eval.m1_smoke import build_body, est_image_tokens, parse_and_validate
from ocr_eval.scoring import (
    Unparseable,
    classify,
    field_types,
    norm_amount,
    norm_date,
    norm_id,
    norm_text,
    score_document,
    strip_meta,
)

DATASET = Path(__file__).resolve().parents[1] / "datasets" / "vat-slip-v1"


# ---- 금액
@pytest.mark.parametrize(
    "raw,expected",
    [
        (1234000, 1234000),
        ("1,234,000", 1234000),
        ("1234000원", 1234000),
        ("1,250,083,400 원", 1250083400),
        ("₩681,210", 681210),
        (681210.0, 681210),
        (None, None),
        ("", None),
        ("null", None),
    ],
)
def test_norm_amount(raw, expected):
    assert norm_amount(raw) == expected


@pytest.mark.parametrize("raw", ["약 68만원", "681,21O", 681210.5, True])
def test_norm_amount_unparseable(raw):
    v = norm_amount(raw)
    assert isinstance(v, Unparseable)
    assert v != 681210


def test_amount_digit_misread_is_not_hidden():
    # 자릿수 하나 빠진 값은 정규화 후에도 달라야 한다
    assert norm_amount("68,121") != norm_amount("681,210")


# ---- 날짜
@pytest.mark.parametrize(
    "raw",
    ["2026-07-25", "2026.07.25", "2026. 07. 25.", "2026. 7. 25.", "2026년 7월 25일", "2026년 07월 25일", "2026/07/25"],
)
def test_norm_date_variants(raw):
    assert norm_date(raw) == "2026-07-25"


@pytest.mark.parametrize("raw", ["26.07.25", "2026-13-01", "7월 25일", "2026-07"])
def test_norm_date_unparseable(raw):
    assert isinstance(norm_date(raw), Unparseable)


def test_norm_date_null():
    assert norm_date(None) is None
    assert norm_date("  ") is None


# ---- 번호·텍스트·null
def test_norm_id_ignores_separators_only():
    assert norm_id("000-98-64326") == norm_id("000 98 64326") == norm_id("0009864326")
    assert norm_id("000-98-64326") != norm_id("000-98-64328")  # 숫자 오독은 그대로 오답


def test_norm_text():
    assert norm_text("  주식회사  사아자물산 ") == "주식회사 사아자물산"
    assert norm_text("(주)라마바테크") != norm_text("라마바테크")
    assert norm_text("해당 없음") is None
    assert norm_text("-") is None


# ---- 실패 분류
def test_classify():
    assert classify("a", "a") is None
    assert classify("a", None) == "missing"
    assert classify(None, "000-1") == "hallucination"
    assert classify(None, None) is None
    assert classify(100, 1000) == "misread"
    assert classify("2026-07-25", Unparseable("7/25")) == "unparseable"


# ---- 문서 단위 채점 (데이터셋 정답 사용)
def _schema():
    return json.loads((DATASET / "schema.json").read_text(encoding="utf-8"))


def _gold(i):
    return json.loads((DATASET / "labels" / f"vat-slip-{i:03d}.json").read_text(encoding="utf-8"))


def test_gold_scores_perfect_on_itself():
    ft = field_types(_schema())
    for i in range(1, 9):
        g = _gold(i)
        assert all(r.correct for r in score_document(g, g, ft)), i


def test_formatting_differences_still_correct():
    ft = field_types(_schema())
    g = _gold(1)
    pred = dict(g)
    pred["total_amount"] = f"{g['total_amount']:,}원"
    pred["due_date"] = "2026. 07. 25."
    pred["business_reg_no"] = g["business_reg_no"].replace("-", "")
    res = {r.field: r for r in score_document(g, pred, ft)}
    assert all(r.correct for r in res.values())


def test_null_gold_hallucination_and_no_json():
    ft = field_types(_schema())
    g = _gold(3)  # virtual_account_no = null (계좌 행 없음)
    assert g["virtual_account_no"] is None
    pred = dict(g, virtual_account_no="000-1234-5678-90")
    res = {r.field: r for r in score_document(g, pred, ft)}
    assert res["virtual_account_no"].error == "hallucination"
    res2 = score_document(g, None, ft)
    assert all(r.error == "no_json" and not r.correct for r in res2)


def test_labels_valid_against_schema():
    v = Draft202012Validator(_schema())
    for i in range(1, 9):
        assert not list(v.iter_errors(_gold(i))), i


def test_amount_digits_cover_6_to_10():
    digits = {len(str(_gold(i)["total_amount"])) for i in range(1, 9)}
    assert digits == {6, 7, 8, 9, 10}


def test_fake_business_numbers_start_with_000():
    for i in range(1, 9):
        assert norm_id(_gold(i)["business_reg_no"]).startswith("000")


# ---- 요청 본문·스키마
def test_strip_meta_removes_x_keys_and_selected_keywords():
    s = strip_meta(_schema(), ["pattern"])
    txt = json.dumps(s)
    assert "x-ocr-type" not in txt and "$schema" not in txt and '"pattern"' not in txt
    assert s["required"] == _schema()["required"]


def test_build_body_shape():
    cfg = {
        "request": {"temperature": 0, "max_tokens": 1024, "response_format_name": "vat_slip", "strict": True},
        "prompt": {"system": None, "user": "읽어라"},
    }
    b = build_body("m", "data:image/png;base64,AAAA", cfg, {"type": "object"})
    assert b["temperature"] == 0
    assert b["response_format"]["type"] == "json_schema"
    content = b["messages"][0]["content"]
    assert content[0]["type"] == "image_url" and content[1]["type"] == "text"


def test_parse_and_validate():
    v = Draft202012Validator(_schema())
    pred, parsed, valid, errs = parse_and_validate(json.dumps(_gold(1), ensure_ascii=False), v)
    assert parsed and valid and not errs
    _, parsed, valid, _ = parse_and_validate("```json\n{}\n```", v)
    assert not parsed and not valid
    _, parsed, valid, errs = parse_and_validate('{"total_amount": "1,000"}', v)
    assert parsed and not valid and errs


def test_est_image_tokens_a4_150dpi():
    assert est_image_tokens(1240, 1754) == 39 * 55 == 2145


def test_settings_repr_and_redact_hide_secrets():
    s = LLMSettings(base_url="https://abc123-8000.proxy.example.net/v1", api_key="sk-secret-xyz", model="m")
    assert "abc123" not in repr(s) and "sk-secret" not in repr(s)
    msg = s.redact("Connection error to https://abc123-8000.proxy.example.net/v1/chat key=sk-secret-xyz")
    assert "abc123" not in msg and "sk-secret" not in msg
