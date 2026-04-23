"""
End-to-end regression for the 2026-04-23 comparison follow-up bug
(LINE dealer test session):

Turn 1: "ยาบำรุงและให้สารอาหารข้าวใช้ตัวไหน"  (ask for rice nutrient)
Turn 2: "ตัวไหนดี"                            (which is good?)

Before the fix:
  - Turn 2 was interpreted with hallucinated expanded_queries
    ("ยากำจัดวัชพืชในอ้อย") → retrieval pulled cross-category products
  - Response generator entered Mode ก (clarify) and asked about
    weed stage + durian age → completely off-topic.

After the fix: Turn 2 must stay on rice-nutrient products and must
NOT ask about วัชพืช/ทุเรียน clarifications.
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


class TestRiceNutrientComparisonFollowup:
    """Real dealer scenario: rice-nutrient list → 'ตัวไหนดี' follow-up."""

    @pytest.mark.asyncio
    async def test_two_turn_flow_stays_on_category(self, registry_loaded):
        """Full 2-turn flow: ensure turn 2 preserves nutrient/rice context."""
        from app.services.cache import clear_conversation_state, get_conversation_state
        from app.services.chat.handler import handle_natural_conversation

        uid = "test_rice_nutrient_compare_e2e"
        await clear_conversation_state(uid)

        # ---- Turn 1 ---------------------------------------------------------
        turn1 = await handle_natural_conversation(
            uid, "ยาบำรุงและให้สารอาหารข้าวใช้ตัวไหน"
        )
        assert turn1, "Turn 1 must return a non-empty answer"

        # Turn 1 should populate active_products from the listed items.
        state = await get_conversation_state(uid)
        assert state is not None, "Turn 1 must save conversation state"
        active_products = state.get("active_products") or []
        assert len(active_products) >= 2, (
            f"Turn 1 should list ≥2 products in active_products, got {active_products}"
        )

        # ---- Turn 2 — the bug under test ------------------------------------
        turn2 = await handle_natural_conversation(uid, "ตัวไหนดี")
        assert turn2, "Turn 2 must return a non-empty answer"

        # Cross-category leakage guard: turn 2 must NOT ask about
        # unrelated categories (weed stage / durian age). These were the
        # exact hallucinated clarifications from the bug screenshot.
        _FORBIDDEN = [
            "ระยะของวัชพืช", "วัชพืชงอก", "ยาคุม", "ยาฆ่า",
            "อายุของทุเรียน", "หลังปลูก",
        ]
        leaks = [kw for kw in _FORBIDDEN if kw in turn2]
        assert not leaks, (
            f"Turn 2 leaked unrelated categories {leaks}:\n{turn2[:800]}"
        )

        # Must still be on-topic: answer should at least reference one of
        # the products from turn 1 OR the rice/nutrient topic.
        # (Internal strategy names like Skyrocket/Expand must NEVER reach
        # user-facing copy — they're confidential business classification.)
        _on_topic_signals = active_products + [
            "ข้าว", "บำรุง", "ธาตุอาหาร",
        ]
        on_topic_hits = [s for s in _on_topic_signals if s in turn2]
        assert on_topic_hits, (
            f"Turn 2 lost topic context — no product/category mention.\n"
            f"Turn 1 products: {active_products}\nTurn 2:\n{turn2[:800]}"
        )

        await clear_conversation_state(uid)

    @pytest.mark.asyncio
    async def test_pre_seeded_state_direct_turn2(self, registry_loaded):
        """Bypass turn 1: seed state manually with rice nutrients (mirrors
        the log from the bug report), then call turn 2 directly."""
        from app.services.cache import clear_conversation_state, save_conversation_state
        from app.services.rag.orchestrator import process_with_agentic_rag

        uid = "test_rice_nutrient_compare_seeded"
        await clear_conversation_state(uid)

        # Exact active_products from the dealer log (2026-04-23 02:02)
        seeded = [
            "บอมส์ ซิงค์", "บอมส์ ซูริค", "ชุดเขียวพุ่งไว",
            "รวงใหญ่ชุดทอง", "บอมส์ แม็กซ์",
        ]
        await save_conversation_state(uid, {
            "active_product": seeded[0],
            "active_products": seeded,
            "active_intent": "nutrient_supplement",
            "active_plant": "ข้าว",
        })

        result = await process_with_agentic_rag(
            "ตัวไหนดี", context="", user_id=uid,
        )

        assert result.answer, "Expected non-empty answer"

        # Cross-category clarifying-question leakage (the actual bug signature —
        # bare word 'ทุเรียน'/'วัชพืช' can legitimately appear in product descriptions
        # listing applicable crops, e.g. "ใช้ได้กับข้าว, ทุเรียน, มะม่วง")
        _FORBIDDEN_CLARIFY = [
            "ระยะของวัชพืช", "วัชพืชงอก", "หลังวัชพืช",
            "อายุของทุเรียน", "หลังปลูก",
        ]
        leaks = [kw for kw in _FORBIDDEN_CLARIFY if kw in result.answer]
        assert not leaks, (
            f"Rice-nutrient follow-up leaked clarifying questions {leaks}:\n"
            f"{result.answer[:600]}"
        )

        # Must stay on the 5 seeded products (at least one must be named)
        mentioned = [p for p in seeded if p in result.answer]
        assert mentioned, (
            f"Answer must reference at least one seeded product.\n"
            f"Seeded: {seeded}\nAnswer:\n{result.answer[:800]}"
        )

        await clear_conversation_state(uid)


# =============================================================================
# Cross-plant × cross-category × phrasing-variation matrix
# =============================================================================
#
# The bug class (cross-category leakage on follow-up) is pipeline-wide, not
# plant-specific — but users word follow-ups differently and the bot ships
# across 90 products × 25+ crops. These tests pin the fix across the common
# axes so phrasing drift or category-specific retrieval quirks can't regress
# the behavior silently.
# =============================================================================


# Seeded scenarios — (plant, intent, active_products, topic_signals, forbidden_clarify)
# topic_signals: words that should plausibly appear in an on-topic answer
# forbidden_clarify: exact clarifying-question substrings the bot must NOT emit
_SCENARIOS = {
    "rice_herbicide": {
        "plant": "ข้าว",
        "intent": "weed_control",
        "products": ["แกนเตอร์", "อะนิลการ์ด", "ทูโฟฟอส"],
        "on_topic": ["ข้าว", "หญ้า", "วัชพืช"],
        "forbidden_clarify": ["อายุของทุเรียน", "หลังปลูก"],
    },
    "durian_fungicide": {
        "plant": "ทุเรียน",
        "intent": "disease_treatment",
        "products": ["คาริสมา", "อาร์เทมิส", "คอนทาฟ"],
        "on_topic": ["ทุเรียน", "โรค", "รา", "เชื้อ"],
        "forbidden_clarify": ["ระยะของวัชพืช", "วัชพืชงอก"],
    },
    "mango_pgr": {
        "plant": "มะม่วง",
        "intent": "nutrient_supplement",
        "products": ["แจ๊ส 50 อีซี", "แอสไปร์", "ซิมเมอร์"],
        "on_topic": ["มะม่วง", "ดอก", "ใบ", "ฮอร์โมน", "กระตุ้น"],
        "forbidden_clarify": ["ระยะของวัชพืช", "วัชพืชงอก"],
    },
    "rice_insecticide": {
        "plant": "ข้าว",
        "intent": "pest_control",
        "products": ["ไบเตอร์", "อิมิดาโกลด์ 70", "โบว์แลน"],
        "on_topic": ["ข้าว", "แมลง", "เพลี้ย", "หนอน"],
        "forbidden_clarify": ["ระยะของวัชพืช", "อายุของทุเรียน"],
    },
}


# Variation phrasings that must all route to comparison follow-up
_PHRASING_VARIATIONS = [
    "ตัวไหนดี",
    "ตัวไหนเหมาะ",
    "ตัวไหนได้ผล",
    "อันไหนดี",
    "แบบไหนดี",
    "ใช้ต่างกันยังไง",
    "เปรียบเทียบให้หน่อย",
]


class TestCrossPlantComparisonFollowup:
    """Seed state for each (plant × category), ask a compare follow-up,
    assert answer stays on category and mentions at least one seeded product."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_key", list(_SCENARIOS.keys()))
    async def test_scenario_stays_on_category(self, scenario_key, registry_loaded):
        from app.services.cache import clear_conversation_state, save_conversation_state
        from app.services.rag.orchestrator import process_with_agentic_rag

        s = _SCENARIOS[scenario_key]
        uid = f"test_compare_e2e_{scenario_key}"
        await clear_conversation_state(uid)
        await save_conversation_state(uid, {
            "active_product": s["products"][0],
            "active_products": s["products"],
            "active_intent": s["intent"],
            "active_plant": s["plant"],
        })

        result = await process_with_agentic_rag(
            "ตัวไหนดี", context="", user_id=uid,
        )

        assert result.answer, f"{scenario_key}: empty answer"
        for forbidden in s["forbidden_clarify"]:
            assert forbidden not in result.answer, (
                f"{scenario_key}: leaked clarifying question {forbidden!r}:\n"
                f"{result.answer[:600]}"
            )
        # At least one seeded product should be named
        mentioned = [p for p in s["products"] if p in result.answer]
        assert mentioned, (
            f"{scenario_key}: answer names no seeded product.\n"
            f"Seeded: {s['products']}\nAnswer:\n{result.answer[:800]}"
        )

        await clear_conversation_state(uid)


class TestPhrasingVariations:
    """Every supported phrasing must route to the same short-circuit path.
    Sharing-of-truth test: if one phrase doesn't route, retrieval will spin
    up and the answer will diverge — we check this via a cheap pipeline
    signal (state-guided direct-lookup of seeded products)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("phrase", _PHRASING_VARIATIONS)
    async def test_phrase_stays_on_seeded_products(self, phrase, registry_loaded):
        from app.services.cache import clear_conversation_state, save_conversation_state
        from app.services.rag.orchestrator import process_with_agentic_rag

        uid = f"test_compare_phrase_{abs(hash(phrase)) % 10_000}"
        # Use rice-nutrient seed (the original bug context)
        seeded = ["บอมส์ ซิงค์", "บอมส์ ซูริค", "บอมส์ แม็กซ์"]
        await clear_conversation_state(uid)
        await save_conversation_state(uid, {
            "active_product": seeded[0],
            "active_products": seeded,
            "active_intent": "nutrient_supplement",
            "active_plant": "ข้าว",
        })

        result = await process_with_agentic_rag(phrase, context="", user_id=uid)
        assert result.answer, f"Phrasing {phrase!r}: empty answer"
        mentioned = [p for p in seeded if p in result.answer]
        assert mentioned, (
            f"Phrasing {phrase!r} did not route as comparison follow-up — "
            f"seeded products not mentioned.\nAnswer:\n{result.answer[:600]}"
        )

        await clear_conversation_state(uid)


class TestPlantRestatedSameTopic:
    """'ตัวไหนดีสำหรับข้าว' with state.plant='ข้าว' must stay in follow-up mode,
    not be reclassified as a new topic."""

    @pytest.mark.asyncio
    async def test_same_plant_restated_keeps_context(self, registry_loaded):
        from app.services.cache import clear_conversation_state, save_conversation_state
        from app.services.rag.orchestrator import process_with_agentic_rag

        uid = "test_compare_plant_restated"
        seeded = ["บอมส์ ซิงค์", "บอมส์ ซูริค", "บอมส์ แม็กซ์"]
        await clear_conversation_state(uid)
        await save_conversation_state(uid, {
            "active_product": seeded[0],
            "active_products": seeded,
            "active_intent": "nutrient_supplement",
            "active_plant": "ข้าว",
        })

        result = await process_with_agentic_rag(
            "ตัวไหนดีสำหรับข้าว", context="", user_id=uid,
        )
        assert result.answer
        mentioned = [p for p in seeded if p in result.answer]
        assert mentioned, (
            "Same-plant re-statement must keep the comparison follow-up path.\n"
            f"Answer:\n{result.answer[:600]}"
        )

        await clear_conversation_state(uid)

    @pytest.mark.asyncio
    async def test_different_plant_IS_new_topic(self, registry_loaded):
        """Negative case: different plant → must NOT stay in compare follow-up.
        Guards against over-generalizing the plant-restated fix."""
        from app.services.cache import clear_conversation_state, save_conversation_state
        from app.services.rag.orchestrator import process_with_agentic_rag

        uid = "test_compare_plant_switched"
        seeded = ["บอมส์ ซิงค์", "บอมส์ ซูริค", "บอมส์ แม็กซ์"]
        await clear_conversation_state(uid)
        await save_conversation_state(uid, {
            "active_product": seeded[0],
            "active_products": seeded,
            "active_intent": "nutrient_supplement",
            "active_plant": "ข้าว",
        })

        # User explicitly switches plant → this is a new question about durian
        result = await process_with_agentic_rag(
            "ตัวไหนดีสำหรับทุเรียน", context="", user_id=uid,
        )
        assert result.answer
        # Answer shouldn't be locked to the rice-nutrient list — at least one
        # durian-relevant term should appear (product or crop name).
        assert "ทุเรียน" in result.answer, (
            "Plant switch must override compare follow-up — answer should "
            "address the new plant, not the prior list.\n"
            f"Answer:\n{result.answer[:600]}"
        )

        await clear_conversation_state(uid)
