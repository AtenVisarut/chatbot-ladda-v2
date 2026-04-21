"""
Test word-order variants + surface forms for symptom → pathogen / disease
resolution. Added 2026-04-21 to cover diagnostic queries like
"ยางพาราเป็นจุดสีน้ำตาลที่ใบเกิดจากอะไร".

Purely additive: every variant must resolve to a pathogen / canonical that
already exists in the codebase (no fabricated entries).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.disease.constants import (
    DISEASE_CANONICAL,
    DISEASE_PATTERNS,
    DISEASE_PATTERNS_SORTED,
    get_canonical,
)
from app.utils.text_processing import (
    SYMPTOM_PATHOGEN_MAP,
    diacritics_match,
    resolve_symptom_to_pathogens,
)


# ---------------------------------------------------------------------------
# SYMPTOM_PATHOGEN_MAP — word-order variants
# ---------------------------------------------------------------------------
# All pathogens referenced in the map must belong to this set (i.e. we never
# invent a new pathogen — only route new surface forms to existing ones).
_EXISTING_PATHOGENS = {
    "เซอโคสปอร่า",
    "แอนแทรคโนส",
    "ไฟทอปธอร่า",
    "ฟิวซาเรียม",
    "ราสีชมพู",
    "ราแป้ง",
    "โอดิอัม",
    "ราดำ",
    "พิเทียม",
    "ราน้ำค้าง",
}


def test_symptom_map_uses_only_known_pathogens():
    for symptom, pathogens in SYMPTOM_PATHOGEN_MAP.items():
        for p in pathogens:
            assert p in _EXISTING_PATHOGENS, (
                f"symptom '{symptom}' maps to unknown pathogen '{p}' — "
                "additive fix must route to existing pathogens only"
            )


@pytest.mark.parametrize(
    "variant,expected",
    [
        ("จุดที่ใบ", ["เซอโคสปอร่า", "แอนแทรคโนส"]),
        ("จุดบนใบ", ["เซอโคสปอร่า", "แอนแทรคโนส"]),
        ("ใบมีจุด", ["เซอโคสปอร่า", "แอนแทรคโนส"]),
        ("ใบเป็นจุด", ["เซอโคสปอร่า", "แอนแทรคโนส"]),
        ("จุดสีน้ำตาล", ["เซอโคสปอร่า", "แอนแทรคโนส"]),
        ("จุดน้ำตาล", ["เซอโคสปอร่า", "แอนแทรคโนส"]),
        ("ใบเป็นแผลไหม้", ["ไฟทอปธอร่า", "แอนแทรคโนส"]),
        ("ใบหลุดร่วง", ["แอนแทรคโนส", "ไฟทอปธอร่า"]),
        ("น้ำยางไหล", ["ไฟทอปธอร่า"]),
    ],
)
def test_symptom_variants_present_with_expected_pathogens(variant, expected):
    assert variant in SYMPTOM_PATHOGEN_MAP, (
        f"missing word-order variant '{variant}' in SYMPTOM_PATHOGEN_MAP"
    )
    assert SYMPTOM_PATHOGEN_MAP[variant] == expected


# End-to-end: the public resolver picks up the variants from a realistic query
@pytest.mark.parametrize(
    "query,expected_contains",
    [
        # Railway-style rubber diagnostic query
        (
            "ยางพาราเป็นจุดสีน้ำตาลที่ใบเกิดจากอะไร",
            ["เซอโคสปอร่า", "แอนแทรคโนส"],
        ),
        ("ทุเรียนใบมีจุดเยอะมาก", ["เซอโคสปอร่า", "แอนแทรคโนส"]),
        ("ใบเป็นจุดทั้งใบเลย", ["เซอโคสปอร่า", "แอนแทรคโนส"]),
        ("มีจุดที่ใบเยอะ", ["เซอโคสปอร่า", "แอนแทรคโนส"]),
        ("มีจุดบนใบเต็มไปหมด", ["เซอโคสปอร่า", "แอนแทรคโนส"]),
        ("ใบหลุดร่วงเร็วมาก", ["แอนแทรคโนส", "ไฟทอปธอร่า"]),
        ("ยางพาราน้ำยางไหลผิดปกติ", ["ไฟทอปธอร่า"]),
        ("ใบเป็นแผลไหม้ช่วงฝนตก", ["ไฟทอปธอร่า", "แอนแทรคโนส"]),
    ],
)
def test_resolve_symptom_to_pathogens_covers_variants(query, expected_contains):
    result = resolve_symptom_to_pathogens(query)
    for pathogen in expected_contains:
        assert pathogen in result, (
            f"query '{query}' failed to resolve '{pathogen}' (got {result})"
        )


# ---------------------------------------------------------------------------
# DISEASE_PATTERNS / DISEASE_CANONICAL — surface forms
# ---------------------------------------------------------------------------
# Every canonical target must already exist as a DISEASE_PATTERNS entry or
# as a known canonical — we do not create new canonical diseases here.
_VALID_CANONICALS = set(DISEASE_PATTERNS) | set(DISEASE_CANONICAL.values())


def test_disease_canonical_targets_are_known():
    for surface, canonical in DISEASE_CANONICAL.items():
        assert canonical in _VALID_CANONICALS, (
            f"surface '{surface}' → unknown canonical '{canonical}'"
        )


@pytest.mark.parametrize(
    "surface,canonical",
    [
        ("จุดสีน้ำตาล", "ใบจุดสีน้ำตาล"),
        ("จุดน้ำตาล", "ใบจุดสีน้ำตาล"),
        ("จุดที่ใบ", "ใบจุด"),
        ("จุดบนใบ", "ใบจุด"),
        ("ใบมีจุด", "ใบจุด"),
        ("ใบเป็นจุด", "ใบจุด"),
    ],
)
def test_surface_forms_canonicalize_correctly(surface, canonical):
    assert surface in DISEASE_PATTERNS, (
        f"missing surface form '{surface}' in DISEASE_PATTERNS"
    )
    assert get_canonical(surface) == canonical


# Regression: Stage 0 disease extraction finds the right canonical for
# diagnostic queries, not just canonical-spelled queries.
def _extract_disease(query: str) -> str:
    """Mirror orchestrator's Stage 0 disease extraction."""
    for pattern in DISEASE_PATTERNS_SORTED:
        if diacritics_match(query, pattern):
            return get_canonical(pattern)
    return ""


@pytest.mark.parametrize(
    "query,expected_canonical",
    [
        ("ยางพาราเป็นจุดสีน้ำตาลที่ใบเกิดจากอะไร", "ใบจุดสีน้ำตาล"),
        ("ทุเรียนมีจุดสีน้ำตาลที่ใบ", "ใบจุดสีน้ำตาล"),
        ("พริกใบมีจุดทำอย่างไร", "ใบจุด"),
    ],
)
def test_stage0_extraction_picks_canonical_for_variants(query, expected_canonical):
    assert _extract_disease(query) == expected_canonical


# Guard: when query contains the longer canonical ("ใบจุดสีน้ำตาล") verbatim,
# Stage 0 must pick that over the shorter "ใบจุด" substring.
def test_longest_match_precedence_preserved():
    q = "ทุเรียนมีใบจุดสีน้ำตาลกระจายทั่ว"
    assert _extract_disease(q) == "ใบจุดสีน้ำตาล"


# Guard: when a query matches multiple symptom variants that share pathogens,
# resolve_symptom_to_pathogens must dedupe the result.
def test_resolver_dedupes_overlapping_variants():
    # "ใบมีจุดสีน้ำตาล" matches both "ใบมีจุด" and "จุดสีน้ำตาล",
    # each mapping to ["เซอโคสปอร่า", "แอนแทรคโนส"]
    result = resolve_symptom_to_pathogens("ใบมีจุดสีน้ำตาลเยอะ")
    assert result == ["เซอโคสปอร่า", "แอนแทรคโนส"]


# Guard: queries with no known symptoms must return empty (no over-matching).
@pytest.mark.parametrize(
    "query",
    [
        "ปุ๋ยเร่งดอกทุเรียนยี่ห้อไหนดี",
        "สวัสดีครับ",
        "ข้าวราคาเท่าไร",
    ],
)
def test_resolver_returns_empty_for_unrelated_queries(query):
    assert resolve_symptom_to_pathogens(query) == []
