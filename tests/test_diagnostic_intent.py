"""
Diagnostic-intent path tests: keyword detection, crop priors, whitelist
guards, orchestrator wiring, and adversarial LLM output.

Scope added 2026-04-22 (test-dev branch).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.disease.constants import DISEASE_CANONICAL, DISEASE_PATTERNS
from app.services.disease.crop_disease_priors import (
    CROP_DISEASE_PRIORS,
    resolve_crop_symptom_to_diseases,
)
from app.services.disease.diagnostic_intent import is_diagnostic_query
from app.utils.text_processing import SYMPTOM_PATHOGEN_MAP


# ---------------------------------------------------------------------------
# §2 — is_diagnostic_query
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "query",
    [
        "ยางพาราเป็นจุดสีน้ำตาลที่ใบเกิดจากอะไร",
        "ใบเหลืองเกิดจากอะไร",
        "สาเหตุที่ใบจุด",
        "รากเน่าเพราะอะไร",
        "ทุเรียนเป็นโรคอะไร",
        "อาการแบบนี้เป็นโรคอะไร",
        "ทำไมถึงเป็นใบไหม้",
        "ใบจุดคืออะไร",
    ],
)
def test_diagnostic_query_detected(query):
    assert is_diagnostic_query(query) is True


@pytest.mark.parametrize(
    "query",
    [
        "แนะนำยาฆ่าเพลี้ย",
        "มีไบเตอร์มั้ย",
        "อัตราใช้ราคาเท่าไร",
        "สวัสดีครับ",
        "",
    ],
)
def test_non_diagnostic_query_ignored(query):
    assert is_diagnostic_query(query) is False


# ---------------------------------------------------------------------------
# §3 — crop priors whitelist + resolver
# ---------------------------------------------------------------------------
# Every pathogen name that already appears in SYMPTOM_PATHOGEN_MAP.values().
# The priors table is allowed to reference either a DISEASE_PATTERNS entry
# or a known pathogen name — both resolve to strings present in products3.
_KNOWN_PATHOGENS = {p for lst in SYMPTOM_PATHOGEN_MAP.values() for p in lst}
_VALID_CANONICALS = (
    set(DISEASE_PATTERNS) | set(DISEASE_CANONICAL.values()) | _KNOWN_PATHOGENS
)


def test_priors_cover_top_8_crops():
    expected = {
        "ยางพารา", "ทุเรียน", "ข้าว", "ข้าวโพด",
        "มันสำปะหลัง", "อ้อย", "มะม่วง", "ปาล์ม",
    }
    assert set(CROP_DISEASE_PRIORS) == expected


def test_all_priors_reference_known_diseases():
    """Whitelist guard: every disease in priors must already exist."""
    for crop, symptom_map in CROP_DISEASE_PRIORS.items():
        for symptom, pairs in symptom_map.items():
            for disease, weight in pairs:
                assert disease in _VALID_CANONICALS, (
                    f"{crop} / {symptom} → unknown disease '{disease}' "
                    "(must be in DISEASE_PATTERNS or a known pathogen)"
                )
                assert 0 < weight <= 1, (
                    f"{crop} / {symptom} → invalid weight {weight} for '{disease}'"
                )


def test_priors_weights_descending_per_symptom():
    for crop, symptom_map in CROP_DISEASE_PRIORS.items():
        for symptom, pairs in symptom_map.items():
            weights = [w for _, w in pairs]
            assert weights == sorted(weights, reverse=True), (
                f"{crop} / {symptom}: weights not sorted desc"
            )


@pytest.mark.parametrize(
    "crop,query,first_disease",
    [
        ("ยางพารา", "ยางพาราเป็นจุดสีน้ำตาลที่ใบเกิดจากอะไร", "เซอโคสปอร่า"),
        ("ยางพารา", "เปลือกแตกเกิดจากอะไร", "ไฟทอปธอร่า"),
        ("ทุเรียน", "ทุเรียนรากเน่าเกิดจากอะไร", "ไฟทอปธอร่า"),
        ("ทุเรียน", "โคนเน่าในทุเรียน", "ไฟทอปธอร่า"),
        ("ข้าว", "ข้าวใบไหม้สาเหตุคืออะไร", "ใบไหม้"),
        ("ข้าว", "ขอบใบแห้งในข้าวเกิดจากอะไร", "แบคทีเรีย"),
        ("ข้าวโพด", "ข้าวโพดใบไหม้เพราะอะไร", "ใบไหม้แผลใหญ่"),
        ("ข้าวโพด", "ราน้ำค้างในข้าวโพด", "ราน้ำค้าง"),
        ("มันสำปะหลัง", "มันสำปะหลังรากเน่า", "พิเทียม"),
        ("อ้อย", "อ้อยเป็นราสนิม", "ราสนิม"),
        ("มะม่วง", "มะม่วงเป็นแอนแทรคโนส", "แอนแทรคโนส"),
        ("ปาล์ม", "ปาล์มทะลายเน่า", "แอนแทรคโนส"),
    ],
)
def test_resolver_returns_expected_top_disease(crop, query, first_disease):
    result = resolve_crop_symptom_to_diseases(crop, query)
    assert result, f"expected non-empty for {crop}/{query}"
    assert result[0] == first_disease, (
        f"{crop}/{query}: expected first='{first_disease}', got {result}"
    )


def test_resolver_dedupes_across_symptom_keys():
    # "ทุเรียนโคนเน่าและรากเน่า" matches both "โคนเน่า" and "รากเน่า"
    # — both list ไฟทอปธอร่า; must not appear twice.
    result = resolve_crop_symptom_to_diseases("ทุเรียน", "ทุเรียนโคนเน่าและรากเน่า")
    assert result.count("ไฟทอปธอร่า") == 1


@pytest.mark.parametrize(
    "crop,query",
    [
        ("ยางพารา", "สวัสดี"),                # no symptom
        ("ถั่วเขียว", "ถั่วเขียวใบจุด"),        # crop not in priors
        ("", "ใบจุด"),                         # empty crop
        ("ยางพารา", ""),                       # empty query
    ],
)
def test_resolver_returns_empty_for_miss(crop, query):
    assert resolve_crop_symptom_to_diseases(crop, query) == []


# ---------------------------------------------------------------------------
# §4 — orchestrator integration (flag gated)
# ---------------------------------------------------------------------------
# We only test the deterministic building blocks that the orchestrator
# invokes; the full orchestrator call involves async OpenAI + Supabase.
def test_flag_default_disabled_in_non_test_env(monkeypatch):
    monkeypatch.delenv("DIAGNOSTIC_INTENT_ENABLED", raising=False)
    # Re-import to pick up default
    import importlib

    from app import config as _cfg

    importlib.reload(_cfg)
    assert _cfg.DIAGNOSTIC_INTENT_ENABLED is False


def test_flag_honors_env_true(monkeypatch):
    monkeypatch.setenv("DIAGNOSTIC_INTENT_ENABLED", "true")
    import importlib

    from app import config as _cfg

    importlib.reload(_cfg)
    assert _cfg.DIAGNOSTIC_INTENT_ENABLED is True


# ---------------------------------------------------------------------------
# §7 — Agent 1 defense-in-depth: disease_name validation
# ---------------------------------------------------------------------------
# Re-implement the validator as a pure function so we can test without
# spinning up the full QueryUnderstandingAgent (which needs OpenAI + async).
# This mirror must stay in sync with query_understanding_agent.py.
def _validate_llm_disease_name(name: str | None) -> str | None:
    if not name:
        return None
    is_thai = any('฀' <= c <= '๿' for c in name)
    db_match = any(p in name or name in p for p in DISEASE_PATTERNS)
    return name if (is_thai and db_match) else None


@pytest.mark.parametrize(
    "llm_output",
    [
        "Phytophthora root rot",
        "Cercospora leaf spot",
        "Anthracnose",
        "root rot disease",
        "rice blast",
    ],
)
def test_english_disease_names_rejected(llm_output):
    assert _validate_llm_disease_name(llm_output) is None


@pytest.mark.parametrize(
    "llm_output",
    [
        "โรคประหลาดที่ไม่มีในระบบ",
        "เชื้อไม่รู้จัก",
    ],
)
def test_non_db_thai_disease_rejected(llm_output):
    assert _validate_llm_disease_name(llm_output) is None


@pytest.mark.parametrize(
    "llm_output",
    [
        "รากเน่า",
        "แอนแทรคโนส",
        "ไฟทอปธอร่า",
        "ใบจุดสีน้ำตาล",
        "ราน้ำค้าง",
    ],
)
def test_canonical_thai_disease_accepted(llm_output):
    assert _validate_llm_disease_name(llm_output) == llm_output


def test_empty_or_none_passes_through():
    assert _validate_llm_disease_name(None) is None
    assert _validate_llm_disease_name("") is None
