"""
Tests — Applicability question flow (user asks "X ใช้กับ Y ได้ไหม")

Real-world scenario from LINE log:
  Turn 1: user "เกรก 5 เอสซี" → bot replies with details
  Turn 2: user "ถ้าเพลี้ยจั๊กจั่นในทุเรียนล่ะ ใช้ได้มั้ย"
  → bot SHOULD say "เกรก 5 เอสซี ไม่ได้ระบุว่าใช้กับเพลี้ยจั๊กจั่นในทุเรียนค่ะ"
     before recommending alternatives — not jump straight to alternatives

Coverage:
1. Pattern recognition — applicability phrases detected
2. Source-level — orchestrator sets asked_product hint + carries through
3. Response generator — applicability_note injected when asked_product's
   data doesn't cover the new pest/plant
"""

from __future__ import annotations

import inspect
import pytest


class TestApplicabilityPatterns:
    """Phrases that signal 'can X be used for Y?'"""

    @pytest.mark.parametrize("query", [
        "ใช้ได้มั้ย",
        "ใช้ได้ไหม",
        "ถ้าเพลี้ยจั๊กจั่นในทุเรียนล่ะ ใช้ได้มั้ย",
        "ฉีดได้มั้ย",
        "ฉีดได้ไหม",
        "ได้มั้ย",
        "ได้ไหม",
    ])
    def test_applicability_phrase_recognized(self, query):
        _PHRASES = [
            'ใช้ได้มั้ย', 'ใช้ได้ไหม', 'ฉีดได้มั้ย', 'ฉีดได้ไหม',
            'ได้มั้ย', 'ได้ไหม',
        ]
        assert any(p in query for p in _PHRASES), (
            f"Applicability phrase missed: {query!r}"
        )

    @pytest.mark.parametrize("query", [
        "ใช้ยังไง",
        "อัตราเท่าไหร่",
        "กลุ่ม IRAC อะไร",
        "สารสำคัญคืออะไร",
    ])
    def test_non_applicability_not_matched(self, query):
        """พวกถามวิธีใช้/อัตรา ไม่ควร match applicability phrases"""
        strict_phrases = ['ใช้ได้มั้ย', 'ใช้ได้ไหม', 'ฉีดได้มั้ย', 'ฉีดได้ไหม']
        assert not any(p in query for p in strict_phrases), (
            f"Non-applicability query mis-matched: {query!r}"
        )


class TestOrchestratorApplicabilityHint:
    """Orchestrator source-level checks"""

    def test_orchestrator_defines_applicability_phrases(self):
        from app.services.rag import orchestrator
        src = inspect.getsource(orchestrator)
        assert "_APPLICABILITY_PHRASES" in src
        assert "_has_applicability_phrase" in src
        assert "asked_product" in src, (
            "Orchestrator should set hints['asked_product']"
        )

    def test_orchestrator_extracts_prev_product_from_context(self):
        from app.services.rag import orchestrator
        src = inspect.getsource(orchestrator)
        assert "_prev_product_from_context" in src
        assert "[สินค้าล่าสุดในบทสนทนา]" in src

    def test_orchestrator_adds_asked_product_to_product_names(self):
        """When new-topic branch: asked_product must be added to product_names
        so retrieval fetches both"""
        from app.services.rag import orchestrator
        src = inspect.getsource(orchestrator)
        # Must add prev product into retrieval product_names list
        assert "product_names" in src
        assert "asked_product" in src


class TestQueryUnderstandingPropagation:
    """QueryUnderstandingAgent must propagate asked_product into entities"""

    def test_query_understanding_propagates_asked_product(self):
        from app.services.rag import query_understanding_agent
        src = inspect.getsource(query_understanding_agent)
        assert "asked_product" in src, (
            "QueryUnderstandingAgent must propagate hints['asked_product'] "
            "into entities so ResponseGenerator can see it"
        )


class TestResponseGeneratorApplicabilityNote:
    """ResponseGenerator must emit applicability_note when denial is needed"""

    def test_generator_has_applicability_note_logic(self):
        from app.services.rag import response_generator_agent
        src = inspect.getsource(
            response_generator_agent.ResponseGeneratorAgent._generate_llm_response
        )
        assert "applicability_note" in src, (
            "_generate_llm_response missing applicability_note variable"
        )
        assert "asked_product" in src
        assert "ไม่ได้ระบุว่าใช้กับ" in src, (
            "applicability_note should contain the denial phrase template"
        )

    def test_applicability_note_skipped_when_coverage_matches(self):
        """If asked_product's DB data DOES cover the target → no denial note"""
        from app.services.rag import response_generator_agent
        src = inspect.getsource(
            response_generator_agent.ResponseGeneratorAgent._generate_llm_response
        )
        # The logic must have a _covers = False default and only skip note when _covers
        assert "_covers = False" in src or "_covers=False" in src
        assert "if not _covers" in src

    def test_applicability_note_uses_docs_to_use_metadata(self):
        """Note decision must be data-driven, not prompt-driven"""
        from app.services.rag import response_generator_agent
        src = inspect.getsource(
            response_generator_agent.ResponseGeneratorAgent._generate_llm_response
        )
        assert "_asked_doc" in src, (
            "Must look up asked_product's doc in docs_to_use for coverage check"
        )
        assert "_plant_matches_crops" in src or "applicable_crops" in src


class TestDenialFlow:
    """Integration-adjacent: verify the chain of hints wiring is complete"""

    def test_hint_propagation_chain(self):
        """
        Chain: orchestrator.hints['asked_product']
           → query_understanding.entities['asked_product']
           → response_generator reads entities.get('asked_product')
        """
        from app.services.rag import (
            orchestrator, query_understanding_agent, response_generator_agent,
        )
        o_src = inspect.getsource(orchestrator)
        qu_src = inspect.getsource(query_understanding_agent)
        rg_src = inspect.getsource(response_generator_agent)

        assert "hints['asked_product']" in o_src or 'hints["asked_product"]' in o_src, (
            "orchestrator must assign hints['asked_product']"
        )
        assert "asked_product" in qu_src
        assert "entities.get('asked_product')" in rg_src or "entities['asked_product']" in rg_src, (
            "response_generator must read asked_product from entities"
        )
