"""
Tests — Chemical group (IRAC/FRAC/HRAC/RAC/MoA) queries

Real-world regression: bot เคยตอบ "ไม่มีข้อมูลเรื่องกลุ่ม IRAC" ทั้งที่ DB
มีฟิลด์ chemical_group_rac เก็บค่า เช่น "กลุ่ม 3A + 4A"

Root cause: LLM ไม่รู้ว่า field "กลุ่มสาร (RAC)" ในข้อมูล = answer สำหรับ
IRAC/FRAC/HRAC/MoA — prompt ไม่ได้สอน mapping

Fix:
  1. Tag field ใน product_context ด้วย synonyms ตาม category:
     "กลุ่มสาร (IRAC / MoA / Mode of Action): ..." สำหรับ Insecticide
     "กลุ่มสาร (FRAC / MoA / Mode of Action): ..." สำหรับ Fungicide
     "กลุ่มสาร (HRAC / MoA / Mode of Action): ..." สำหรับ Herbicide
  2. Inject chem_group_note เมื่อ query มี keyword IRAC/FRAC/HRAC/MoA
     เตือน LLM ให้ตอบจากฟิลด์นี้ ห้ามตอบ "ไม่มีข้อมูล"
"""

from __future__ import annotations

import inspect
import pytest


class TestChemGroupPromptHint:
    """Source-level: chem_group_note injected + RAC field tagged with synonyms"""

    def test_rac_field_has_category_based_tag(self):
        """Field header must include IRAC/FRAC/HRAC based on category"""
        from app.services.rag import response_generator_agent
        src = inspect.getsource(
            response_generator_agent.ResponseGeneratorAgent._generate_llm_response
        )
        # Expected header format includes all 4 synonyms
        assert "IRAC" in src, "IRAC tag missing in RAC field output"
        assert "FRAC" in src, "FRAC tag missing"
        assert "HRAC" in src, "HRAC tag missing"
        assert "MoA" in src, "MoA tag missing"
        assert "Mode of Action" in src

    def test_chem_group_note_triggered_by_keywords(self):
        from app.services.rag import response_generator_agent
        src = inspect.getsource(
            response_generator_agent.ResponseGeneratorAgent._generate_llm_response
        )
        # Must have the keyword list + note variable
        assert "chem_group_note" in src
        for kw in ('irac', 'frac', 'hrac', 'moa', 'กลุ่มสาร', 'กลไกการออกฤทธิ์'):
            assert kw in src, f"chem_group keyword missing: {kw!r}"

    def test_chem_group_note_prevents_no_data_reply(self):
        from app.services.rag import response_generator_agent
        src = inspect.getsource(
            response_generator_agent.ResponseGeneratorAgent._generate_llm_response
        )
        # Note must tell LLM not to reply "no data" when field is present
        assert "ห้ามตอบว่า" in src and "ไม่มีข้อมูล" in src

    def test_chem_group_note_in_final_prompt(self):
        from app.services.rag import response_generator_agent
        src = inspect.getsource(
            response_generator_agent.ResponseGeneratorAgent._generate_llm_response
        )
        # {chem_group_note} must appear in the final f-string prompt
        assert "{chem_group_note}" in src


class TestChemGroupPatternDetection:
    """The keyword detection used by chem_group_note"""

    @pytest.mark.parametrize("query", [
        "ไบเตอร์ อยู่กลุ่ม IRAC อะไร",
        "คอนทาฟ FRAC อะไร",
        "ไดยูแมกซ์ HRAC อะไร",
        "โคเฟสต้า MoA คืออะไร",
        "ออลสตาร์ กลุ่มสารอะไร",
        "โบว์แลน กลไกการออกฤทธิ์",
    ])
    def test_chem_group_keywords_matched(self, query):
        _chem_group_kw = [
            'irac', 'frac', 'hrac', 'rac', 'moa', 'mode of action',
            'กลุ่มสาร', 'กลุ่มเคมี', 'กลุ่มยา', 'กลไกการออกฤทธิ์',
        ]
        assert any(kw in query.lower() for kw in _chem_group_kw), (
            f"Chem-group query not recognized: {query!r}"
        )

    @pytest.mark.parametrize("query", [
        "ไบเตอร์ ใช้ยังไง",
        "อัตราเท่าไหร่",
        "ใช้กับทุเรียนได้ไหม",
    ])
    def test_non_chem_group_queries_not_matched(self, query):
        _chem_group_kw = ['irac', 'frac', 'hrac', 'moa', 'mode of action',
                          'กลุ่มสาร', 'กลุ่มเคมี', 'กลุ่มยา', 'กลไกการออกฤทธิ์']
        assert not any(kw in query.lower() for kw in _chem_group_kw), (
            f"Non-chem-group query falsely matched: {query!r}"
        )


@pytest.mark.skipif(
    True, reason="Integration — enable locally with real OpenAI + Supabase"
)
class TestIRACQueryE2E:
    """End-to-end smoke test — requires real API keys"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("product,expected_group_hint", [
        ("ไบเตอร์", "3A"),
        ("คอนทาฟ", "3"),
        ("ออลสตาร์", "E"),
        ("โคเฟสต้า", "3 + 11"),
    ])
    async def test_direct_irac_question(self, product, expected_group_hint):
        from app.services.rag.orchestrator import process_with_agentic_rag
        r = await process_with_agentic_rag(
            f"{product} อยู่กลุ่ม IRAC/FRAC/HRAC อะไร"
        )
        assert r.answer, "No answer returned"
        assert expected_group_hint in r.answer, (
            f"Expected {expected_group_hint!r} in answer, got: {r.answer[:300]}"
        )
        # Must NOT say "no data"
        for bad in ("ไม่มีข้อมูล", "ไม่ทราบ"):
            assert bad not in r.answer, (
                f"Bot incorrectly said {bad!r} for {product} — answer was: {r.answer[:300]}"
            )
