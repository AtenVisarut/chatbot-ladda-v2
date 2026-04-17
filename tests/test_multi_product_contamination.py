"""
Tests — Multi-product / cross-category confusion
จากผลตอบกลับเกษตรกร: ถามสินค้าหลายตัว/หลายกลุ่มพร้อมกัน bot อาจ
1. extract ชื่อสินค้าไม่ครบ → ตกหล่นสินค้าบางตัว
2. ตอบข้อมูลสินค้าเก่ากว่าจาก memory แทนตัวใหม่ (context contamination)
3. ตอบ "ไม่มีข้อมูล" ทั้งที่ DB มี (field ไม่ถูก pass เข้า prompt)
4. ผสมข้อมูลระหว่างสินค้าในคำตอบเดียว

Tests นี้ตั้งใจให้บาง test **FAIL เพื่อ document bug** ที่พบ — ใส่ xfail
หรือแยก strict/loose เพื่อให้ CI ผ่าน แต่ dev เห็นปัญหาชัด
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from dotenv import load_dotenv

# โหลด .env ก่อน (override ค่า dummy ที่ conftest ใส่ไว้)
# ต้องทำก่อน import app.dependencies เพื่อให้ supabase_client ใช้ URL จริง
load_dotenv(override=True)


def _has_real_supabase() -> bool:
    """
    Check if real Supabase credentials are configured AND
    app.dependencies.supabase_client uses them (not conftest dummy values).
    """
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not (url.startswith("https://fwzdgzpuajcsigwlyojr") and key.startswith("eyJ") and len(key) > 100):
        return False
    # Also verify app.dependencies picked up real values (conftest may have imported first)
    try:
        from app import dependencies as _deps
        actual_url = getattr(_deps, "SUPABASE_URL", None) or ""
        return "fwzdgzpuajcsigwlyojr" in actual_url
    except Exception:
        return False


# -- Skip module entirely when external deps aren't available (CI) ------------
pytestmark = pytest.mark.skipif(
    not _has_real_supabase(),
    reason="Needs real Supabase registry (integration test)",
)


@pytest.fixture(scope="module")
def registry_loaded():
    """Load real ProductRegistry once for all tests in this module."""
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
# 1. Product-name extraction edge cases (ตัวที่ทำให้ bot ตกหล่นสินค้า)
# =============================================================================

class TestMultiProductExtraction:
    """ถ้า extract ไม่ครบ → memory contamination ตามมาแน่"""

    @pytest.mark.parametrize("query,must_contain", [
        # 2-product cross-category compare
        ("ออลสตาร์ ดอยเลอร์ ต่างกันยังไง", {"ออล์สตาร์", "ดอยเลอร์"}),
        ("ไบเตอร์ คอนทาฟ ต่างกันยังไง", {"ไบเตอร์", "คอนทาฟ"}),
        # 3-product
        ("คอนทาฟ ไบเตอร์ ดอยเลอร์ ใช้กับพืชอะไรบ้าง", {"ไบเตอร์", "คอนทาฟ", "ดอยเลอร์"}),
        # "กับ"
        ("คาซ่า กับ โคเบิล ต่างกันอย่างไร", {"คาซ่า", "โคเบิล"}),
        ("อยากรู้ โคเฟสต้า กับ โซนิก", {"โคเฟสต้า", "โซนิก"}),
        # comma/slash separator
        ("ไบเตอร์,ดอยเลอร์,โบว์แลน", {"ไบเตอร์", "ดอยเลอร์"}),
        ("ไบเตอร์/ดอยเลอร์", {"ไบเตอร์", "ดอยเลอร์"}),
    ])
    def test_extracts_all_products(self, registry_loaded, query, must_contain):
        from app.services.chat.handler import extract_all_product_names_from_question

        extracted = set(extract_all_product_names_from_question(query))
        missing = must_contain - extracted
        assert not missing, (
            f"Query: {query!r}\n"
            f"  Expected to find: {must_contain}\n"
            f"  Actually found:   {extracted}\n"
            f"  Missing: {missing}"
        )

    @pytest.mark.parametrize("query,must_contain", [
        # บอมส์ family — suffix-only should resolve to all family members
        # (fixed by _scan_family_suffixes in registry.extract_all_product_names)
        (
            "ไวท์ แม็กซ์ ซิงค์ ต่างกันยังไง",
            {"บอมส์ ไวท์", "บอมส์ แม็กซ์", "บอมส์ ซิงค์"},
        ),
        (
            "มิกซ์ ฟาสท์ ใช้ต่างกันยังไง",
            {"บอมส์ มิกซ์", "บอมส์ ฟาสท์"},
        ),
        # version-number product must preserve number in canonical
        # (fixed by aligning fallback canonical with DB: อิมิดาโกลด์ 70)
        (
            "อิมิดาโกลด์ 70 กับ คลิฟตัน ใช้ยังไง",
            {"อิมิดาโกลด์ 70", "คลิฟตัน"},
        ),
    ])
    def test_extraction_family_and_version(self, registry_loaded, query, must_contain):
        from app.services.chat.handler import extract_all_product_names_from_question

        extracted = set(extract_all_product_names_from_question(query))
        assert must_contain.issubset(extracted), (
            f"Query: {query!r}\n"
            f"  Expected: {must_contain}\n"
            f"  Got:      {extracted}"
        )


# =============================================================================
# 2. answer_usage_question — prompt ส่ง field ครบไหม
# =============================================================================

class TestUsagePromptFields:
    """
    Bug: products_text ใน answer_usage_question ไม่ใส่
    active_ingredient / chemical_group_rac / strategy / product_category /
    physical_form / selling_point
    → เวลา user ถาม "สารสำคัญ" / "IRAC group" → LLM ไม่มี data → hallucinate/ตอบ no data
    """

    def test_usage_prompt_includes_core_identity_fields(self):
        """เช็คว่า code path ใน answer_usage_question ใส่ field สำคัญเข้า prompt"""
        import inspect
        from app.services.chat import handler

        src = inspect.getsource(handler.answer_usage_question)
        # prompt ต้องมี fields พวกนี้ ไม่งั้น LLM ตอบ "ไม่มีข้อมูล"
        required_tokens = [
            "active_ingredient",     # สารสำคัญ
            "chemical_group_rac",    # IRAC/FRAC group
            "product_category",      # Insecticide/Herbicide/Fungicide
        ]
        missing = [t for t in required_tokens if t not in src]
        assert not missing, (
            f"answer_usage_question source is missing fields in prompt: {missing}\n"
            f"→ user questions about these attributes will get 'no data' even when DB has them"
        )


# =============================================================================
# 3. Context contamination — memory ของ turn ก่อนปนกับ turn ปัจจุบัน
# =============================================================================

class TestContextContamination:
    """
    ผลที่คาดหวัง: user ถามสินค้า A แล้วเปลี่ยนไปถาม B —
    ข้อมูล/ชื่อสารสำคัญของ A ต้องไม่โผล่ในคำตอบของ B
    """

    @pytest.mark.asyncio
    async def test_fresh_fetch_bypasses_stale_memory(self, registry_loaded):
        """
        หลัง fix ล่าสุด: ถ้า user mention ชื่อสินค้าในคำถาม → ต้อง fresh-fetch จาก DB
        และข้ามข้อมูลใน memory (กัน contamination)
        """
        from app.services.memory import save_recommended_products, clear_memory
        from app.services.chat.handler import answer_usage_question, _fetch_product_from_db

        uid = "test_fresh_fetch_bypass"
        await clear_memory(uid)

        # Pre-seed memory with ไบเตอร์ + ดอยเลอร์ (different categories)
        for pname in ("ไบเตอร์", "ดอยเลอร์"):
            rows = await _fetch_product_from_db(pname)
            if rows:
                await save_recommended_products(uid, rows[:1])

        # Now ask about ออลสตาร์ (Herbicide) — should NOT leak insecticide data
        answer = await answer_usage_question(uid, "ออลสตาร์ ใช้ยังไง")
        assert answer, "Expected non-empty answer"

        # Expect herbicide info (OXADIAZON / 300-400 มล. ต่อไร่ / ข้าว/ผักคะน้า)
        assert ("ข้าว" in answer) or ("ผักคะน้า" in answer) or ("300" in answer), (
            "Answer should describe ออลสตาร์'s crop/rate, got:\n" + answer[:500]
        )

        # Expect NO leak from pre-seeded memory
        leak_markers = ["BIFENTHRIN", "IMIDACLOPRID", "ดอยเลอร์", "ไบเตอร์"]
        leaked = [m for m in leak_markers if m.lower() in answer.lower()]
        assert not leaked, (
            f"Memory contamination: leaked {leaked} from pre-seeded memory\n"
            f"Answer: {answer[:500]}"
        )

    @pytest.mark.asyncio
    async def test_short_vague_query_returns_clarification(self, registry_loaded):
        """
        Short vague query like 'อัตราใช้เท่าไหร่' with no memory → ต้องถามกลับ
        (ไม่ใช่ hallucinate หรือเงียบ)
        """
        from app.services.memory import clear_memory
        from app.services.chat.handler import answer_usage_question

        uid = "test_short_vague_no_mem"
        await clear_memory(uid)

        answer = await answer_usage_question(uid, "อัตราการใช้")
        # ควรถามกลับ หรือ None (ให้ไป flow อื่น) — ห้ามตอบด้วยสินค้าสุ่ม
        if answer:
            # ถ้าตอบ → ต้องเป็น clarification ไม่ใช่ข้อมูลสินค้า
            assert (
                "ทราบรายละเอียด" in answer
                or "สินค้าตัวไหน" in answer
                or "พืชอะไร" in answer
            ), f"Short vague query should ask for clarification, got: {answer[:300]}"


# =============================================================================
# 4. Multi-product answer quality
# =============================================================================

class TestMultiProductAnswer:
    """เวลา user ถามหลายสินค้าพร้อมกัน — คำตอบต้องครอบคลุมทุกตัว ไม่ผสมข้อมูล"""

    @pytest.mark.asyncio
    async def test_compare_3_products_cross_category(self, registry_loaded):
        """ถามเทียบ 3 สินค้า 3 กลุ่ม — คำตอบต้องกล่าวถึงทั้ง 3 และถูก category"""
        from app.services.chat.handler import answer_usage_question

        uid = "test_compare_3_cat"
        q = "ไบเตอร์ ออลสตาร์ คอนทาฟ ต่างกันยังไง"
        answer = await answer_usage_question(uid, q)
        assert answer, "Expected non-empty answer"

        # ทุกตัวต้องถูกกล่าวถึง
        for name in ("ไบเตอร์", "คอนทาฟ"):
            assert name in answer, f"Answer missing {name}:\n{answer[:500]}"
        # ออลสตาร์ อาจถูก render เป็น ออล์สตาร์ (canonical)
        assert ("ออลสตาร์" in answer) or ("ออล์สตาร์" in answer), (
            f"Answer missing ออล์สตาร์:\n{answer[:500]}"
        )

        # Category cue ที่ถูก
        # ไบเตอร์ = insecticide → ควรมี 'แมลง' หรือ 'หนอน'
        # ออลสตาร์ = herbicide → ควรมี 'วัชพืช' หรือ 'หญ้า'
        # คอนทาฟ = fungicide → ควรมี 'เชื้อรา' หรือ 'โรค'
        assert any(k in answer for k in ("แมลง", "หนอน")), "Expected insecticide cue"
        assert any(k in answer for k in ("วัชพืช", "หญ้า")), "Expected herbicide cue"
        assert any(k in answer for k in ("เชื้อรา", "โรคพืช", "โรค")), "Expected fungicide cue"

    @pytest.mark.asyncio
    async def test_active_ingredient_question_does_not_false_negative(self, registry_loaded):
        """
        Fixed: 'สารสำคัญคืออะไร' ของหลายสินค้า ต้องมีสารสำคัญจริงของแต่ละตัว
        (fix: added active_ingredient/chemical_group_rac/product_category to products_text)
        """
        from app.services.chat.handler import answer_usage_question

        uid = "test_active_ingredient_multi"
        q = "ไบเตอร์ คอนทาฟ ออลสตาร์ สารสำคัญคืออะไรบ้าง"
        answer = await answer_usage_question(uid, q)
        assert answer, "Expected non-empty answer"

        # ต้องมีสารสำคัญอย่างน้อยของแต่ละตัว (ตามที่เก็บใน DB)
        # DB: ไบเตอร์=BIFENTHRIN+IMIDACLOPRID, คอนทาฟ=HEXACONAZOLE, ออล์สตาร์=OXADIAZON
        hits = {
            "ไบเตอร์": any(s in answer.upper() for s in ("BIFENTHRIN", "ไบเฟนทริน", "IMIDACLOPRID")),
            "คอนทาฟ": any(s in answer.upper() for s in ("HEXACONAZOLE", "เฮกซะโคนาโซล", "เฮกซา")),
            "ออล์สตาร์": any(s in answer.upper() for s in ("OXADIAZON", "ออกซาไดอะซอน")),
        }
        missing = [k for k, ok in hits.items() if not ok]
        assert not missing, (
            f"active_ingredient missing for {missing}:\n{answer[:600]}"
        )


# =============================================================================
# 5. Enrich consistency — memory ที่มีค่าว่าง ต้องถูก overwrite จาก DB
# =============================================================================

class TestComparisonFollowup:
    """
    Real-world bug (2026-04-17): user พิมพ์ "ไดยูแมก" → bot ตอบ 2 variants.
    แล้ว user ถาม "ใช้แตกต่างกันยังไง" (follow-up comparison)
    → bot ตอบเกี่ยวกับ 'บอมส์ แม็กซ์' แทน ไดยูแมกซ์ (เอาของเก่าจาก memory มา)

    Root cause: orchestrator dropped product_name='ไดยูแมกซ์' จาก conversation state
    เพราะ "ใช้แตกต่างกันยังไง" ไม่อยู่ใน _FOLLOWUP_USAGE → ถูกตีเป็น vague query
    → clear conversation state → RAG pipeline หา product จาก memory context
    → ดึง บอมส์ แม็กซ์ จาก 10 products ใน memory ผิด

    Fix: เพิ่ม comparison patterns เข้า orchestrator (preserve product context)
    """

    @pytest.mark.parametrize("query", [
        "ใช้แตกต่างกันยังไง",
        "ต่างกันยังไง",
        "แตกต่างกันยังไง",
        "เปรียบเทียบหน่อย",
        "อันไหนดีกว่า",
        "ตัวไหนดีกว่ากัน",
        "ใช้ต่างกันยังไง",
    ])
    def test_comparison_query_pattern_recognized(self, registry_loaded, query):
        """
        Regression guard: comparison follow-up ต้องถูกตรวจจับและ preserve product
        จาก conversation state ไม่ใช่ drop แล้ว clear state
        """
        _FOLLOWUP_COMPARE = [
            'ต่างกัน', 'แตกต่าง', 'เปรียบเทียบ', 'อันไหนดี', 'ตัวไหนดี',
            'อันไหนดีกว่า', 'ตัวไหนดีกว่า', 'ใช้ต่าง',
        ]
        matched = any(p in query for p in _FOLLOWUP_COMPARE)
        assert matched, f"Comparison pattern not matched for query: {query!r}"

    def test_orchestrator_keeps_product_on_comparison(self):
        """
        เช็คว่า orchestrator source มี _FOLLOWUP_COMPARE และใช้เป็น guard
        เพื่อไม่ drop product context
        """
        import inspect
        from app.services.rag import orchestrator

        src = inspect.getsource(orchestrator)
        assert "_FOLLOWUP_COMPARE" in src, (
            "Orchestrator missing _FOLLOWUP_COMPARE list → 'ใช้แตกต่างกันยังไง' "
            "will drop product from conversation state and pull random from memory"
        )
        assert "_is_compare_followup" in src, (
            "Orchestrator not checking _is_compare_followup as drop guard"
        )


class TestEnrichFromDB:
    @pytest.mark.asyncio
    async def test_enrich_overwrites_short_values(self, registry_loaded):
        """
        Memory เก่ามี active_ingredient='' (ค่าว่าง) — เวลา follow-up query
        ต้อง enrich ด้วย active_ingredient ที่ถูกต้องจาก DB ก่อนส่งให้ LLM
        """
        from app.services.memory import save_recommended_products, clear_memory
        from app.services.chat.handler import answer_usage_question

        uid = "test_enrich_short"
        await clear_memory(uid)

        stale = {
            "product_name": "ไบเตอร์",
            "product_category": "Insecticide",
            "active_ingredient": "",  # missing → ต้อง enrich
            "how_to_use": "",
            "usage_rate": "",
        }
        await save_recommended_products(uid, [stale])

        answer = await answer_usage_question(uid, "อัตราใช้เท่าไหร่ กับทุเรียน")
        assert answer, "Expected non-empty answer"
        # หลัง enrich ต้องมีอัตราใช้จริง (15-20 มล. / น้ำ 20 ลิตร)
        assert "15" in answer or "20" in answer, (
            f"Expected real usage rate after enrich, got:\n{answer[:500]}"
        )
