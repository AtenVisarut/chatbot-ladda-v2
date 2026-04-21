"""
Regression tests for open-category clarify flow.

Scenario:
  User asks an open-ended category query with no crop:
    "แนะนำยาฆ่าหญ้าหน่อย" / "อยากได้กำจัดแมลง" / "มีปุ๋ยไหม"
  Bot should ask ONE follow-up ("ใช้กับพืชอะไร...") instead of trying
  to rank products category-wide (which returns irrelevant picks).

  On the next turn, the user's free-form reply ("ข้าว", "ข้าวใช้กับหนอน",
  "ทุเรียนกำจัดไฟทอป") is rewritten into a proper RAG query that carries
  the category context.

These tests run the detector + resume pure functions — no async handler /
Redis / OpenAI needed.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.category_clarify import (  # noqa: E402
    CATEGORY_CLARIFY_MESSAGES,
    CategoryType,
    detect_open_category_query,
    get_clarify_message,
    resume_query_from_clarify,
)
from app.services.plant.registry import PlantRegistry  # noqa: E402


@pytest.fixture(autouse=True, scope="module")
def _bootstrap_plant_registry():
    # The registry is normally loaded at app startup; unit tests bypass that.
    # PlantRegistry is a process-wide singleton, so save+restore around this
    # module to avoid polluting other tests that load their own plant set.
    reg = PlantRegistry.get_instance()
    _saved = (
        dict(reg._canonical_to_aliases),
        list(reg._sorted_names),
        dict(reg._lookup),
        reg._loaded,
        reg._load_time,
    )
    reg._build_index({
        "ข้าว", "ข้าวโพด", "ข้าวเหนียว",
        "ทุเรียน", "อ้อย", "มันสำปะหลัง",
        "ยางพารา", "ปาล์ม", "มะม่วง", "ลำไย",
    })
    reg._loaded = True
    yield
    (
        reg._canonical_to_aliases,
        reg._sorted_names,
        reg._lookup,
        reg._loaded,
        reg._load_time,
    ) = _saved


# ---------------------------------------------------------------------------
# Detection: open category → Category
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "query,expected",
    [
        ("แนะนำยาฆ่าหญ้าหน่อยครับ", CategoryType.HERBICIDE),
        ("มียาฆ่าหญ้าไหม", CategoryType.HERBICIDE),
        ("อยากได้ยาคุมหญ้า", CategoryType.HERBICIDE),
        ("อยากได้กำจัดแมลง", CategoryType.INSECTICIDE),
        ("มียาฆ่าแมลงไหม", CategoryType.INSECTICIDE),
        ("แนะนำยาเชื้อราหน่อย", CategoryType.FUNGICIDE),
        ("มียากันราไหม", CategoryType.FUNGICIDE),
        ("มีปุ๋ยไหม", CategoryType.FERTILIZER),
        ("อยากได้อาหารพืช", CategoryType.FERTILIZER),
        ("แนะนำสารอาหารพืชหน่อย", CategoryType.FERTILIZER),
    ],
)
def test_open_category_detected(query, expected):
    assert detect_open_category_query(query) is expected, (
        f"'{query}' should trigger clarify → {expected.value}"
    )


# ---------------------------------------------------------------------------
# Detection: query already has crop → DO NOT clarify
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "query",
    [
        "แนะนำยาฆ่าหญ้าในข้าว",
        "ยาฆ่าแมลงสำหรับทุเรียน",
        "ปุ๋ยข้าวระยะแตกกอ",
        "ยาเชื้อราทุเรียน",
        "อ้อยใช้ยาฆ่าหญ้าอะไรดี",
    ],
)
def test_query_with_crop_skips_clarify(query):
    assert detect_open_category_query(query) is None, (
        f"'{query}' contains a crop — skip clarify, go straight to RAG"
    )


# ---------------------------------------------------------------------------
# Detection: escape words
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "query",
    [
        "ยาฆ่าหญ้าทั่วไป",
        "ปุ๋ยทุกชนิด",
        "ยาฆ่าแมลงทุกพืช",
    ],
)
def test_escape_word_skips_clarify(query):
    assert detect_open_category_query(query) is None


# ---------------------------------------------------------------------------
# Detection: unrelated queries → None
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "query",
    [
        "สวัสดีครับ",
        "ราคาเท่าไร",
        "ใช้ยังไง",
        "ไบเตอร์กำจัดอะไรได้บ้าง",  # product-specific, not open
        "",
    ],
)
def test_unrelated_query_no_clarify(query):
    assert detect_open_category_query(query) is None


# ---------------------------------------------------------------------------
# Detection: long queries are assumed to have enough context
# ---------------------------------------------------------------------------
def test_long_query_skipped():
    # ≥40 chars → skip clarify (user typed a full sentence, RAG will handle)
    long_q = "แนะนำยาฆ่าหญ้าที่ใช้กำจัดหญ้าในพื้นที่ต่างๆ"
    assert detect_open_category_query(long_q) is None


# ---------------------------------------------------------------------------
# Messages: all four categories have a clarify message
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cat", list(CategoryType))
def test_clarify_message_exists(cat):
    msg = get_clarify_message(cat)
    assert msg, f"{cat.value} must have a clarify message"
    assert "น้องลัดดา" in msg or "รบกวน" in msg, (
        "clarify prompt should sound like น้องลัดดา asking politely"
    )
    # Must mention 'พืช' (crop) since that's the whole point of the follow-up
    assert "พืช" in msg


def test_all_categories_have_messages():
    # Structural guard: if a new CategoryType is added, its message must be too
    for cat in CategoryType:
        assert cat in CATEGORY_CLARIFY_MESSAGES


# ---------------------------------------------------------------------------
# Resume: herbicide (crop-only reply)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "reply,expected_substr",
    [
        ("ข้าว", "ยาฆ่าหญ้าในข้าว"),
        ("อ้อย", "ยาฆ่าหญ้าในอ้อย"),
        ("ข้าวโพด", "ยาฆ่าหญ้าในข้าวโพด"),
        ("มันสำปะหลัง", "ยาฆ่าหญ้าในมันสำปะหลัง"),
    ],
)
def test_herbicide_resume_with_crop(reply, expected_substr):
    out = resume_query_from_clarify(CategoryType.HERBICIDE, reply)
    assert expected_substr in out, (
        f"Reply '{reply}' should rewrite into query containing '{expected_substr}', got '{out}'"
    )


def test_herbicide_resume_escape_word():
    out = resume_query_from_clarify(CategoryType.HERBICIDE, "ทั่วไป")
    assert "ยาฆ่าหญ้า" in out and "ทั่วไป" in out


# ---------------------------------------------------------------------------
# Resume: free-form replies user gave as examples
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "category,reply,expected_substrs",
    [
        (CategoryType.INSECTICIDE, "ข้าวใช้กับหนอน", ["ยาฆ่าแมลง", "ข้าว", "หนอน"]),
        (CategoryType.FUNGICIDE, "ทุเรียนกำจัดไฟทอป", ["ยากำจัดเชื้อรา", "ทุเรียน"]),
        (CategoryType.FERTILIZER, "ข้าวแตกกอไม่ดี", ["ปุ๋ย", "ข้าว"]),
        (CategoryType.FERTILIZER, "บำรุงต้นเพิ่มสารอาหารทุเรียน", ["ปุ๋ย", "ทุเรียน"]),
    ],
)
def test_resume_preserves_category_and_reply(category, reply, expected_substrs):
    out = resume_query_from_clarify(category, reply)
    for sub in expected_substrs:
        assert sub in out, (
            f"Category {category.value} + reply '{reply}' → '{out}' "
            f"must include substring '{sub}'"
        )


def test_resume_skips_prepend_when_reply_has_label():
    # Reply already mentions "ปุ๋ย" — don't double-prepend
    out = resume_query_from_clarify(CategoryType.FERTILIZER, "ปุ๋ยข้าวระยะแตกกอ")
    assert out.count("ปุ๋ย") == 1


def test_resume_empty_reply_falls_back_to_category():
    out = resume_query_from_clarify(CategoryType.HERBICIDE, "")
    assert "ยาฆ่าหญ้า" in out

    out2 = resume_query_from_clarify(CategoryType.INSECTICIDE, "   ")
    assert "ยาฆ่าแมลง" in out2
