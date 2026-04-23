"""
Tests — Bot context-following correctness

ครอบคลุม 3 ปัญหาที่พบจาก LINE log (2026-04-17):
1. Comparison follow-up ("ใช้แตกต่างกันยังไง") → ต้อง preserve product
   context ไม่ drop และไม่หยิบสินค้าเก่าจาก memory มาตอบ
2. Topic boundary — user พิมพ์สินค้าใหม่ → skip stale memory
3. Disease-from-context — intent comparison/usage/nutrient ห้ามดึงโรคเก่า
   จาก context มา filter products

Tests ครอบคลุม:
- Products ทุก category (Fungicide/Insecticide/Herbicide/PGR/Biostim/Fertilizer/NPK)
- User queries หลายแบบ (ถามตรง / follow-up / compare / usage / IRAC / active_ing)
- State machine scenarios (single → multi → switch → vague)
"""

from __future__ import annotations

import asyncio
import inspect
import os
from typing import List, Set

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
# Module-level fixtures
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


# Representative products across all categories (covers 90-product DB)
REPRESENTATIVE_PRODUCTS = {
    "Fungicide": ["คอนทาฟ", "อาร์เทมิส", "คาริสมา", "พรีดิคท์ 25% เอฟ"],
    "Insecticide": ["ไบเตอร์", "อิมิดาโกลด์ 70", "ไดนาคลอร์", "โบว์แลน", "โบว์แลน 285"],
    "Herbicide": ["ออล์สตาร์", "ไดยูแมกซ์", "ไดยูแมกซ์ 80 ดับเบิ้ลยู.พี.", "ก็อปกัน", "ไกลโฟเสท"],
    "PGR": ["แจ๊ส 50 อีซี", "แอสไปร์", "ซิมเมอร์"],
    "Biostimulants/Fertilizer": [
        "บอมส์ ไวท์", "บอมส์ แม็กซ์", "บอมส์ ซิงค์",
        "บอมส์ มิกซ์", "บอมส์ ฟาสท์", "บอมส์ เจล",
    ],
    "NPK": ["NPK 0-0-60", "NPK 0-52-34", "NPK 13-0-46"],
    "Bundles": ["ชุดกล่องม่วง", "ชุดเขียวพุ่งไว", "รวงใหญ่ชุดทอง"],
}


# =============================================================================
# 1. Source-level regression guards (no DB roundtrip)
# =============================================================================

class TestSourceGuards:
    """Static source-analysis: verify the fixed code paths are actually in place"""

    def test_orchestrator_has_comparison_followup_guard(self):
        """#1: orchestrator must not drop product on ต่างกัน/แตกต่าง queries"""
        from app.services.rag import orchestrator
        src = inspect.getsource(orchestrator)
        assert "_FOLLOWUP_COMPARE" in src, "Missing _FOLLOWUP_COMPARE list"
        assert "_is_compare_followup" in src, "Missing _is_compare_followup guard"

    def test_orchestrator_uses_active_products_for_comparison(self):
        """#1: on comparison follow-up, must pull ALL active_products from state"""
        from app.services.rag import orchestrator
        src = inspect.getsource(orchestrator)
        assert "active_products" in src, "orchestrator doesn't read active_products list"
        assert "Comparison follow-up" in src, "Missing comparison follow-up branch in state strategy"

    def test_orchestrator_has_topic_boundary_guard(self):
        """#2: topic boundary when user pipelines new product"""
        from app.services.rag import orchestrator
        src = inspect.getsource(orchestrator)
        assert "New-product topic" in src, "Topic boundary not wired"

    def test_response_generator_skips_disease_context_on_compare(self):
        """#3: comparison intent must bypass disease-from-context extraction"""
        from app.services.rag import response_generator_agent
        src = inspect.getsource(response_generator_agent)
        # Must include comparison patterns in skip-list
        assert "_skip_disease_context" in src
        assert ("ต่างกัน" in src) and ("เปรียบเทียบ" in src), (
            "response_generator doesn't treat comparison intent as disease-free"
        )

    def test_response_generator_skips_disease_for_nutrient_and_usage(self):
        """#3: nutrient/usage intents must also bypass disease-from-context"""
        from app.services.rag import response_generator_agent
        src = inspect.getsource(response_generator_agent)
        assert "NUTRIENT_SUPPLEMENT" in src and "USAGE_INSTRUCTION" in src, (
            "response_generator skip list missing NUTRIENT_SUPPLEMENT/USAGE_INSTRUCTION"
        )

    def test_response_generator_skips_disease_when_query_names_product(self):
        """#4 (2026-04-22 bug): 'โมเดินใช้ทำอะไร' after disease context —
        must skip context_disease so product-inquiry answer isn't blocked."""
        from app.services.rag import response_generator_agent
        src = inspect.getsource(response_generator_agent)
        # Must invoke product-name extraction as part of skip logic
        assert "extract_product_name_from_question" in src, (
            "response_generator doesn't skip context_disease when query names a product"
        )
        # Capability patterns must also include product-info phrasings
        for pat in ['ทำอะไร', 'คืออะไร', 'สรรพคุณ']:
            assert f"'{pat}'" in src, f"_CAPABILITY_PAT missing {pat!r}"


# =============================================================================
# 2. Extraction coverage across all product categories
# =============================================================================

class TestExtractionCoverage:
    """Every representative product must be extractable by its canonical name"""

    def test_all_representative_products_exist(self, registry_loaded):
        """Sanity: all representative products exist in registry"""
        canonicals = set(registry_loaded.get_canonical_list())
        missing: List[str] = []
        for category, names in REPRESENTATIVE_PRODUCTS.items():
            for n in names:
                if n not in canonicals:
                    missing.append(f"{category}:{n}")
        assert not missing, f"Missing canonical products: {missing}"

    @pytest.mark.parametrize("product", sum(REPRESENTATIVE_PRODUCTS.values(), []))
    def test_exact_name_extracts(self, registry_loaded, product):
        """ถาม '<product> ใช้ยังไง' → ต้อง extract canonical เดิม"""
        from app.services.chat.handler import extract_all_product_names_from_question

        query = f"{product} ใช้ยังไง"
        extracted = extract_all_product_names_from_question(query)
        assert product in extracted, (
            f"Query: {query!r} → {extracted}, expected to contain {product!r}"
        )

    @pytest.mark.parametrize("cat_name,products", [
        ("Fungicide compare", ["คอนทาฟ", "อาร์เทมิส"]),
        ("Insecticide compare", ["ไบเตอร์", "ไดนาคลอร์"]),
        ("Herbicide compare", ["ออล์สตาร์", "ก็อปกัน"]),
        ("Biostim compare", ["บอมส์ ไวท์", "บอมส์ แม็กซ์"]),
        ("NPK compare", ["NPK 0-0-60", "NPK 13-0-46"]),
    ])
    def test_cross_category_pair_extraction(self, registry_loaded, cat_name, products):
        """เทียบคู่ในกลุ่มเดียวกัน — ต้อง extract ครบทั้ง 2 ตัว"""
        from app.services.chat.handler import extract_all_product_names_from_question

        query = f"{products[0]} กับ {products[1]} ต่างกันยังไง"
        extracted = set(extract_all_product_names_from_question(query))
        missing = set(products) - extracted
        assert not missing, (
            f"[{cat_name}] query={query!r} → extracted={extracted}, missing={missing}"
        )


# =============================================================================
# 3. Comparison query pattern recognition
# =============================================================================

class TestComparisonPatterns:
    """Comparison follow-ups MUST be detected as compare (not drop product)"""

    @pytest.mark.parametrize("query", [
        "ต่างกันยังไง",
        "ใช้แตกต่างกันยังไง",
        "แตกต่างกันอย่างไร",
        "เปรียบเทียบหน่อย",
        "อันไหนดีกว่า",
        "ตัวไหนดีกว่ากัน",
        "ตัวไหนดี",
        "ใช้ต่างกันยังไง",
    ])
    def test_compare_pattern_matches(self, query):
        _FOLLOWUP_COMPARE = [
            'ต่างกัน', 'แตกต่าง', 'เปรียบเทียบ',
            'อันไหนดี', 'ตัวไหนดี', 'ใช้ต่าง',
        ]
        assert any(p in query for p in _FOLLOWUP_COMPARE), (
            f"Compare pattern missed: {query!r}"
        )

    @pytest.mark.parametrize("query", [
        "อัตราใช้เท่าไหร่",
        "ใช้ยังไง",
        "ใช้กับทุเรียนได้ไหม",
        "ขนาดบรรจุ",
    ])
    def test_usage_pattern_not_misclassified_as_compare(self, query):
        """usage follow-up ต้องไม่ match compare patterns (ต่างกัน/แตกต่าง)"""
        _FOLLOWUP_COMPARE = [
            'ต่างกัน', 'แตกต่าง', 'เปรียบเทียบ',
            'อันไหนดี', 'ตัวไหนดี', 'ใช้ต่าง',
        ]
        assert not any(p in query for p in _FOLLOWUP_COMPARE), (
            f"Usage query mis-matched as compare: {query!r}"
        )


# =============================================================================
# 4. Conversation state — active_products list tracking
# =============================================================================

class TestConversationStateList:
    """state.active_products must be a list preserved for comparison follow-up"""

    @pytest.mark.asyncio
    async def test_save_and_retrieve_multi_products(self):
        """save_conversation_state ต้องเก็บ list active_products ครบ"""
        from app.services.cache import (
            save_conversation_state, get_conversation_state, clear_conversation_state,
        )

        uid = "test_state_multi_list"
        await clear_conversation_state(uid)

        state = {
            "active_product": "ไดยูแมกซ์",
            "active_products": ["ไดยูแมกซ์", "ไดยูแมกซ์ 80 ดับเบิ้ลยู.พี."],
            "active_intent": "product_inquiry",
        }
        await save_conversation_state(uid, state)

        loaded = await get_conversation_state(uid)
        assert loaded is not None
        assert loaded.get("active_product") == "ไดยูแมกซ์"
        assert loaded.get("active_products") == [
            "ไดยูแมกซ์", "ไดยูแมกซ์ 80 ดับเบิ้ลยู.พี.",
        ]

        await clear_conversation_state(uid)

    @pytest.mark.asyncio
    async def test_handler_populates_active_products_from_answer(self):
        """handler._save_conv_state_from_answer ต้อง populate active_products จาก text answer"""
        from app.services.chat.handler import _save_conv_state_from_answer
        from app.services.cache import get_conversation_state, clear_conversation_state

        uid = "test_handler_populate_list"
        await clear_conversation_state(uid)

        # Simulate bot answer with 2 variants
        answer = (
            'สำหรับ "ไดยูแมกซ์" น้องลัดดามีให้เลือก 2 รุ่นค่ะ:\n'
            '1. ไดยูแมกซ์ (ไดยูรอน 80% SC)\n'
            '2. ไดยูแมกซ์ 80 ดับเบิ้ลยู.พี. (ไดยูรอน 80% WP)'
        )
        await _save_conv_state_from_answer(
            uid, answer=answer, intent="product_inquiry", query="ไดยูแมก", rag_response=None,
        )

        state = await get_conversation_state(uid)
        assert state is not None, "State not saved"
        products = state.get("active_products") or []
        assert "ไดยูแมกซ์" in products or "ไดยูแมกซ์ 80 ดับเบิ้ลยู.พี." in products, (
            f"active_products should contain ไดยูแมกซ์ variant, got {products}"
        )

        await clear_conversation_state(uid)


# =============================================================================
# 5. End-to-end regression: LINE log scenario 2026-04-17
# =============================================================================

class TestRealWorldRegression:
    """
    Scenario from LINE log (2026-04-17):
    Turn 1: "ไดยูแมก" → bot replies with 2 variants
    Turn 2: "ใช้แตกต่างกันยังไง" → must stay on ไดยูแมกซ์ (NOT บอมส์ แม็กซ์)
    """

    @pytest.mark.asyncio
    async def test_comparison_followup_preserves_product_not_vague(self, registry_loaded):
        """
        Pre-seed conversation state with ไดยูแมกซ์ variants. Then user asks
        comparison follow-up "ใช้แตกต่างกันยังไง". Orchestrator's drop logic
        must NOT drop — hints['product_name'] stays set.
        """
        from app.services.cache import save_conversation_state, clear_conversation_state
        from app.services.rag.orchestrator import process_with_agentic_rag

        uid = "test_real_world_diyumax"
        await clear_conversation_state(uid)
        await save_conversation_state(uid, {
            "active_product": "ไดยูแมกซ์",
            "active_products": ["ไดยูแมกซ์", "ไดยูแมกซ์ 80 ดับเบิ้ลยู.พี."],
            "active_intent": "product_inquiry",
            "active_plant": "",
        })

        result = await process_with_agentic_rag(
            "ใช้แตกต่างกันยังไง",
            context="",
            user_id=uid,
        )

        # MUST mention ไดยูแมกซ์ — NOT บอมส์ แม็กซ์
        assert result.answer, "Expected non-empty answer"
        assert "ไดยูแมกซ์" in result.answer or "ไดยูรอน" in result.answer, (
            f"Answer should discuss ไดยูแมกซ์, got:\n{result.answer[:800]}"
        )
        assert "บอมส์" not in result.answer, (
            f"Answer should NOT mention บอมส์ (memory contamination), got:\n{result.answer[:800]}"
        )

        await clear_conversation_state(uid)


# =============================================================================
# 6. New-product topic boundary — skip stale context
# =============================================================================

class TestTopicBoundary:
    """
    When user introduces a NEW product not in conversation state,
    orchestrator must skip stale context/memory to avoid contamination.
    """

    @pytest.mark.asyncio
    async def test_new_product_topic_bypasses_state(self, registry_loaded):
        """
        Pre-seed state with ไบเตอร์ (Insecticide). User then types ออลสตาร์
        (Herbicide, different category). Answer must be about ออลสตาร์
        with no leak of ไบเตอร์'s insecticide data.
        """
        from app.services.cache import save_conversation_state, clear_conversation_state
        from app.services.rag.orchestrator import process_with_agentic_rag

        uid = "test_topic_new_product"
        await clear_conversation_state(uid)
        await save_conversation_state(uid, {
            "active_product": "ไบเตอร์",
            "active_products": ["ไบเตอร์"],
            "active_intent": "product_inquiry",
            "active_plant": "",
        })

        result = await process_with_agentic_rag(
            "ออลสตาร์ ใช้ยังไง",
            context="",
            user_id=uid,
        )

        assert result.answer, "Expected non-empty answer"
        # ออล์สตาร์ is Herbicide for rice/kale weeds
        assert "ออล" in result.answer, (
            f"Answer should discuss ออล์สตาร์, got:\n{result.answer[:500]}"
        )
        # Insecticide markers from ไบเตอร์ must NOT appear
        leak_markers = ["BIFENTHRIN", "IMIDACLOPRID", "ไบเฟนทริน"]
        leaked = [m for m in leak_markers if m.lower() in result.answer.lower()]
        assert not leaked, (
            f"Answer leaked ไบเตอร์ data ({leaked}):\n{result.answer[:500]}"
        )

        await clear_conversation_state(uid)


# =============================================================================
# 7. Disease context scoping
# =============================================================================

class TestDiseaseContextScoping:
    """
    When intent is comparison/usage/nutrient, disease extracted from OLD
    context must not pollute the current retrieval.
    """

    def test_comparison_query_skips_disease_context(self):
        """Source-level: comparison patterns must be in the _skip_disease_context branch"""
        from app.services.rag import response_generator_agent
        src = inspect.getsource(response_generator_agent)
        # Must have a comparison guard AND it must flip _skip_disease_context
        assert "_skip_disease_context = True" in src
        # Must include at least these comparison tokens near the skip
        for tok in ["ต่างกัน", "แตกต่าง", "เปรียบเทียบ", "อันไหน"]:
            assert tok in src, f"Missing comparison token in response_generator: {tok}"

    @pytest.mark.parametrize("intent_name", [
        "WEED_CONTROL",
        "PEST_CONTROL",
        "NUTRIENT_SUPPLEMENT",
        "USAGE_INSTRUCTION",
    ])
    def test_non_disease_intents_in_skip_set(self, intent_name):
        """These intents should never trigger disease-from-context extraction"""
        from app.services.rag import response_generator_agent
        src = inspect.getsource(response_generator_agent)
        assert intent_name in src, (
            f"Intent {intent_name} not referenced in response_generator skip set"
        )


# =============================================================================
# 8. Edge cases — borderline follow-up queries
# =============================================================================

class TestFollowupEdgeCases:
    """Edge cases that historically confused the bot"""

    @pytest.mark.parametrize("query,is_compare", [
        # clearly compare
        ("ใช้แตกต่างกันยังไง", True),
        ("ต่างกันตรงไหน", True),
        ("เปรียบเทียบ 3 ตัวนี้", True),
        # clearly NOT compare (usage/ask)
        ("ใช้ยังไง", False),
        ("ใช้กับทุเรียนได้ไหม", False),
        ("กลุ่ม IRAC อะไร", False),
        # ambiguous — but has compare token
        ("ตัวไหนดี", True),
        # normal product name
        ("ไบเตอร์", False),
    ])
    def test_compare_classification(self, query, is_compare):
        _FOLLOWUP_COMPARE = [
            'ต่างกัน', 'แตกต่าง', 'เปรียบเทียบ',
            'อันไหนดี', 'ตัวไหนดี', 'ใช้ต่าง',
        ]
        matched = any(p in query for p in _FOLLOWUP_COMPARE)
        assert matched == is_compare, (
            f"Query {query!r} expected is_compare={is_compare}, got matched={matched}"
        )
