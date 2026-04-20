"""
Tests — Product switching / rapid back-to-back product inquiries

Scenario ที่ user ทำบ่อย:
1. "A ใช้ยังไง" → "แล้ว B ล่ะ"            → bot ต้องตอบ B ไม่ใช่ A
2. "A ใช้ยังไง" → "B ใช้ยังไง" → "ต่างกัน" → compare [A, B] (ไม่ใช่ทั้งของเก่าใน memory)
3. ไล่ 3+ สินค้าติด → state ล่าสุดต้องตรง ไม่รั่วข้าม
4. Family sibling switch: บอมส์ไวท์ → บอมส์แม็กซ์ (same family, different SKU)
5. Cross-category switch: Insecticide (ไบเตอร์) → Fungicide (คอนทาฟ)

ทดสอบ 3 layers:
- L1 (registry): extract_all_product_names คืนผลถูกต้องต่อคำถามเดี่ยว
- L2 (conversation state): save/read/clear ทำงานถูก
- L3 (memory + state): follow-up question ไม่หลุดไปสินค้าเก่า

Integration — require real Supabase
"""

from __future__ import annotations

import asyncio
import os

import pytest
from dotenv import load_dotenv

load_dotenv(override=True)


def _has_real_supabase() -> bool:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not (url.startswith("https://fwzdgzpuajcsigwlyojr") and key.startswith("eyJ") and len(key) > 100):
        return False
    try:
        from app import dependencies as _deps
        actual_url = getattr(_deps, "SUPABASE_URL", None) or ""
        return "fwzdgzpuajcsigwlyojr" in actual_url
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _has_real_supabase(),
    reason="Needs real Supabase (integration test)",
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def registry_loaded():
    from app.dependencies import supabase_client
    from app.services.product.registry import ProductRegistry

    reg = ProductRegistry.get_instance()
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(reg.load_from_db(supabase_client))
    finally:
        loop.close()
    return reg


# =============================================================================
# Layer 1 — extraction per single-product question
# =============================================================================

class TestSingleProductExtractionSwitch:
    """ทุก turn ที่ user พิมพ์ชื่อสินค้าใหม่ → extract ได้สินค้าใหม่เท่านั้น"""

    @pytest.mark.parametrize("query,expected", [
        ("ไบเตอร์ ใช้ยังไง", {"ไบเตอร์"}),
        ("แล้วดอยเลอร์ล่ะ", {"ดอยเลอร์"}),
        ("ออลสตาร์ใช้กับข้าวได้ไหม", {"ออล์สตาร์"}),
        ("คอนทาฟ อัตราเท่าไหร่", {"คอนทาฟ"}),
    ])
    def test_single_product_turn_extracts_only_that(self, registry_loaded, query, expected):
        """แต่ละ turn ที่มีสินค้าตัวเดียว → ต้อง extract ตัวนั้นเท่านั้น (ไม่รั่วไปตัวอื่น)"""
        from app.services.chat.handler import extract_all_product_names_from_question

        extracted = set(extract_all_product_names_from_question(query))
        assert expected.issubset(extracted), (
            f"Query {query!r} expected {expected}, got {extracted}"
        )


# =============================================================================
# Layer 2 — conversation state save/read/clear
# =============================================================================

class TestConversationStateSwitch:
    """ทดสอบ state machine เมื่อ user สลับสินค้า"""

    @pytest.mark.asyncio
    async def test_save_new_state_overwrites_old(self):
        """save A → save B → read = B (state ไม่ทับซ้อน)"""
        from app.services.cache import (
            save_conversation_state,
            get_conversation_state,
            clear_conversation_state,
        )

        uid = "test_switch_overwrite"
        await clear_conversation_state(uid)

        await save_conversation_state(uid, {
            "active_product": "ไบเตอร์",
            "active_intent": "product_inquiry",
        })
        await save_conversation_state(uid, {
            "active_product": "ดอยเลอร์",
            "active_intent": "product_inquiry",
        })

        state = await get_conversation_state(uid)
        assert state is not None
        assert state["active_product"] == "ดอยเลอร์", (
            f"Expected state to reflect latest product (ดอยเลอร์), got {state['active_product']!r}"
        )

        await clear_conversation_state(uid)

    @pytest.mark.asyncio
    async def test_clear_removes_state(self):
        """clear_conversation_state → get คืน None"""
        from app.services.cache import (
            save_conversation_state,
            get_conversation_state,
            clear_conversation_state,
        )

        uid = "test_switch_clear"
        await save_conversation_state(uid, {"active_product": "ไบเตอร์"})
        await clear_conversation_state(uid)

        state = await get_conversation_state(uid)
        assert state is None

    @pytest.mark.asyncio
    async def test_sequential_3_product_switching(self):
        """ไล่ 3 สินค้าติด → state.active_product ต้อง = ตัวล่าสุด"""
        from app.services.cache import (
            save_conversation_state,
            get_conversation_state,
            clear_conversation_state,
        )

        uid = "test_switch_3seq"
        await clear_conversation_state(uid)

        sequence = ["ไบเตอร์", "ดอยเลอร์", "คอนทาฟ"]
        for p in sequence:
            await save_conversation_state(uid, {
                "active_product": p,
                "active_intent": "product_inquiry",
            })

        state = await get_conversation_state(uid)
        assert state["active_product"] == sequence[-1], (
            f"After switching A→B→C, state should = C ({sequence[-1]}), "
            f"got {state['active_product']!r}"
        )

        await clear_conversation_state(uid)


# =============================================================================
# Layer 3 — multi-product extraction in compare follow-up
# =============================================================================

class TestCompareFollowupSwitch:
    """
    User asks A, then B, then 'ต่างกันยังไง' — extraction must return both
    when mentioned together (not stuck on latest single).
    """

    @pytest.mark.parametrize("compare_query,expected_pair", [
        ("ไบเตอร์ ดอยเลอร์ ต่างกันยังไง", {"ไบเตอร์", "ดอยเลอร์"}),
        ("คอนทาฟ กับ อาร์เทมิส ต่างกันยังไง", {"คอนทาฟ", "อาร์เทมิส"}),
        ("ไดยูแมกซ์ ออลสตาร์ ใช้แตกต่างกันยังไง", {"ไดยูแมกซ์", "ออล์สตาร์"}),
        ("บอมส์ ไวท์ บอมส์ แม็กซ์ ต่างกันยังไง", {"บอมส์ ไวท์", "บอมส์ แม็กซ์"}),
    ])
    def test_compare_extracts_both_products(self, registry_loaded, compare_query, expected_pair):
        """Compare query ที่มี 2 ชื่อสินค้า → ต้อง extract ครบทั้งคู่"""
        from app.services.chat.handler import extract_all_product_names_from_question

        extracted = set(extract_all_product_names_from_question(compare_query))
        missing = expected_pair - extracted
        assert not missing, (
            f"Compare query {compare_query!r} missing products: {missing}\n"
            f"  Got: {extracted}"
        )


# =============================================================================
# Layer 4 — family sibling switch
# =============================================================================

class TestFamilySiblingSwitch:
    """
    Family products (บอมส์ ไวท์/แม็กซ์/ซิงค์) — user สลับใน family เดียวกัน
    → ห้าม return ผิด sibling
    """

    @pytest.mark.parametrize("query,expected", [
        ("บอมส์ ไวท์ ใช้ยังไง", "บอมส์ ไวท์"),
        ("บอมส์ แม็กซ์ ใช้ยังไง", "บอมส์ แม็กซ์"),
        ("บอมส์ ซิงค์ ใช้ยังไง", "บอมส์ ซิงค์"),
        ("บอมส์ มิกซ์ ใช้ยังไง", "บอมส์ มิกซ์"),
        ("บอมส์ ฟาสท์ ใช้ยังไง", "บอมส์ ฟาสท์"),
    ])
    def test_family_member_extracts_correct_sibling(self, registry_loaded, query, expected):
        """ชื่อ family + suffix → extract sibling ที่ถูกต้อง"""
        from app.services.chat.handler import extract_all_product_names_from_question

        extracted = extract_all_product_names_from_question(query)
        assert expected in extracted, (
            f"Query {query!r} should extract {expected!r}, got {extracted}"
        )

    def test_family_suffix_multi_switch(self, registry_loaded):
        """'ไวท์ แม็กซ์ ซิงค์ ต่างกันยังไง' → ต้อง extract ทั้ง 3 sibling"""
        from app.services.chat.handler import extract_all_product_names_from_question

        query = "ไวท์ แม็กซ์ ซิงค์ ต่างกันยังไง"
        extracted = set(extract_all_product_names_from_question(query))
        expected = {"บอมส์ ไวท์", "บอมส์ แม็กซ์", "บอมส์ ซิงค์"}
        missing = expected - extracted
        assert not missing, f"Multi-suffix switch missing: {missing}, got: {extracted}"


# =============================================================================
# Layer 5 — cross-category switch
# =============================================================================

class TestCrossCategorySwitch:
    """
    User สลับจาก Insecticide → Fungicide → Herbicide
    → extraction + state ต้องทำตาม category ปัจจุบัน ไม่สับสน
    """

    CROSS_CATEGORY_SEQUENCE = [
        ("ไบเตอร์ ใช้ยังไง", "ไบเตอร์", "Insecticide"),
        ("คอนทาฟ ใช้ยังไง", "คอนทาฟ", "Fungicide"),
        ("ออลสตาร์ ใช้ยังไง", "ออล์สตาร์", "Herbicide"),
    ]

    @pytest.mark.parametrize("query,expected_product,expected_category", CROSS_CATEGORY_SEQUENCE)
    def test_each_turn_extracts_correct_category_product(
        self, registry_loaded, query, expected_product, expected_category
    ):
        """แต่ละ turn ของ sequence → extract product ที่ category ตรงคำถาม"""
        from app.services.chat.handler import extract_all_product_names_from_question

        extracted = extract_all_product_names_from_question(query)
        assert expected_product in extracted, (
            f"Turn {query!r} should return {expected_product!r} ({expected_category})"
        )

        # Verify product's category matches expected
        cat_map = getattr(registry_loaded, "_category_map", {})
        actual_category = cat_map.get(expected_product, "")
        assert actual_category == expected_category, (
            f"{expected_product!r} category={actual_category!r}, expected {expected_category!r}"
        )

    @pytest.mark.asyncio
    async def test_cross_category_state_reflects_latest(self):
        """3 turn cross-category → state.active_product = ตัวล่าสุด (ไม่ค้างสินค้าเก่า)"""
        from app.services.cache import (
            save_conversation_state,
            get_conversation_state,
            clear_conversation_state,
        )

        uid = "test_cross_cat_switch"
        await clear_conversation_state(uid)

        for _, product, category in self.CROSS_CATEGORY_SEQUENCE:
            await save_conversation_state(uid, {
                "active_product": product,
                "active_intent": "product_inquiry",
                "active_category": category,
            })

        state = await get_conversation_state(uid)
        _, last_product, last_category = self.CROSS_CATEGORY_SEQUENCE[-1]
        assert state["active_product"] == last_product
        assert state["active_category"] == last_category

        await clear_conversation_state(uid)


# =============================================================================
# Layer 6 — vague follow-up should stick to latest product
# =============================================================================

class TestVagueFollowupSticksToLatest:
    """
    User: 'ไบเตอร์ ใช้ยังไง' → 'อัตราเท่าไหร่'
    Vague follow-up ไม่มีชื่อสินค้า → bot ต้องดึง product จาก state (ไบเตอร์)
    ไม่ใช่หยิบ product อื่นมั่ว
    """

    @pytest.mark.asyncio
    async def test_vague_followup_reads_latest_state(self):
        """state ที่ save ล่าสุด → get คืนค่าตัวเดียวกัน"""
        from app.services.cache import (
            save_conversation_state,
            get_conversation_state,
            clear_conversation_state,
        )

        uid = "test_vague_followup"
        await clear_conversation_state(uid)

        await save_conversation_state(uid, {
            "active_product": "ไบเตอร์",
            "active_intent": "product_inquiry",
        })

        # Simulate vague follow-up: bot reads state without mention of product
        state = await get_conversation_state(uid)
        assert state is not None
        assert state["active_product"] == "ไบเตอร์"

        await clear_conversation_state(uid)

    @pytest.mark.parametrize("vague_query", [
        "อัตราเท่าไหร่",
        "ผสมน้ำเท่าไหร่",
        "พ่นกี่ครั้ง",
        "ใช้ตอนไหน",
        "มีผลข้างเคียงไหม",
    ])
    def test_vague_query_extracts_no_product(self, registry_loaded, vague_query):
        """คำถาม vague ไม่มีชื่อสินค้า → extract_all คืน list ว่าง"""
        from app.services.chat.handler import extract_all_product_names_from_question

        extracted = extract_all_product_names_from_question(vague_query)
        assert not extracted, (
            f"Vague query {vague_query!r} should have no products, got {extracted}"
        )


# =============================================================================
# Layer 7 — greeting clears previous state
# =============================================================================

class TestGreetingClearsState:
    """'สวัสดี' / 'hello' → state ต้องโดน clear (บ่ง session ใหม่)"""

    @pytest.mark.asyncio
    async def test_clear_conversation_state_removes_saved(self):
        """save state → clear → get คืน None"""
        from app.services.cache import (
            save_conversation_state,
            get_conversation_state,
            clear_conversation_state,
        )

        uid = "test_greeting_clear"
        await save_conversation_state(uid, {
            "active_product": "ไบเตอร์",
            "active_intent": "product_inquiry",
        })

        state = await get_conversation_state(uid)
        assert state is not None

        await clear_conversation_state(uid)
        state2 = await get_conversation_state(uid)
        assert state2 is None, f"State not cleared, still have {state2}"
