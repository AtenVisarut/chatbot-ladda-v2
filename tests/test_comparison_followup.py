"""
Comparison follow-up — cross-category leakage guard (2026-04-23):

Regression for dealer test: bot listed 9 nutrient products in turn 1.
User replied "ตัวไหนดี" in turn 2. Bot asked clarifying question about
"weed stage + durian age" — cross-category hallucination.

Root cause: orchestrator correctly detected comparison follow-up, but
  - QueryUnderstanding LLM generated hallucinated expanded_queries
    ("ยากำจัดวัชพืชในอ้อย" etc.) which polluted retrieval
  - Response generator's _COMPARISON_KEYWORDS didn't include "ตัวไหนดี"
    → Mode ก (clarify) fired instead of Mode ข (compare)

Fix pins:
  1. shared followup_patterns module (single source of truth)
  2. orchestrator propagates _comparison_followup hint + plant re-state guard
  3. query_understanding_agent clamps expanded_queries to product_names
  4. retrieval_agent short-circuits multi-source + fallbacks
  5. response_generator honors flag + imports shared patterns
"""
from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 0. Shared pattern module — single source of truth
# =============================================================================

class TestSharedPatterns:
    """followup_patterns must cover all phrasings used in tests below."""

    @pytest.mark.parametrize("query", [
        # "ตัวไหน…" family
        "ตัวไหนดี", "ตัวไหนดีครับ", "ตัวไหนเหมาะ", "ตัวไหนเหมาะสุด",
        "ตัวไหนเด็ด", "ตัวไหนเวิร์ค", "ตัวไหนได้ผล", "ตัวไหนน่าใช้",
        "ตัวไหนเจ๋ง", "ตัวไหนเด่น", "ตัวไหนคุ้ม",
        # "อันไหน…" family
        "อันไหนดี", "อันไหนเหมาะ", "อันไหนได้ผล",
        # "แบบไหน…" / "รุ่นไหน…" family
        "แบบไหนดี", "รุ่นไหนเหมาะ",
        # Explicit compare
        "ใช้ต่างกันยังไง", "เปรียบเทียบให้หน่อย", "แตกต่างกันยังไง",
        "สองตัวนี้ต่างกัน", "เทียบกัน",
        # English
        "which is good", "which one", "compare them", "best one please",
    ])
    def test_matches(self, query):
        from app.services.rag.followup_patterns import is_comparison_followup
        assert is_comparison_followup(query), f"Should match: {query!r}"

    @pytest.mark.parametrize("query", [
        # Brand-new queries (not follow-ups)
        "แนะนำยาฆ่าหญ้า", "มีปุ๋ยแนะนำไหม", "ใช้ยังไง", "อัตราเท่าไหร่",
        "ราคาเท่าไหร่", "ซื้อที่ไหน",
        # Sales-popularity (handled by separate handler)
        "ขายดีไหม", "ยอดนิยม",
        # Empty / trivial
        "", "ดี", "ok",
    ])
    def test_non_matches(self, query):
        from app.services.rag.followup_patterns import is_comparison_followup
        assert not is_comparison_followup(query), f"Should not match: {query!r}"

    @pytest.mark.parametrize("query", [
        # Honorifics — honorific suffix variants
        "ตัวไหนดีครับ", "ตัวไหนดีคับ", "ตัวไหนดีค่ะ", "ตัวไหนดีคะ",
        "ตัวไหนดีนะครับ", "ตัวไหนดีนะคะ", "ตัวไหนดีจ้า", "ตัวไหนดีฮับ",
        "ตัวไหนดีสุดครับ", "ตัวไหนดีสุดๆ", "ตัวไหนดีมากๆครับ",
        "ตัวไหนดีหน่อยครับ",
        # Typo: missing ั (sara-a short) — common fast-typing omission
        "ตวไหนดี", "ตวไหนดีครับ", "อนไหนดี",
        # Whitespace in core pattern (Thai shouldn't have internal spaces but users do)
        "ตัวไหน ดี", "ตัว ไหน ดี", "ตัวไหน ดี ครับ",
        # Tone marks added/stripped
        "ตัวไหนดีสุด", "อันไหน ดี", "แบบไหน ดี",
    ])
    def test_tolerant_matches(self, query):
        """Normalizer must handle honorifics + typos + internal spaces."""
        from app.services.rag.followup_patterns import is_comparison_followup
        assert is_comparison_followup(query), f"Should tolerate: {query!r}"

    @pytest.mark.parametrize("query", [
        # Normalizer must not false-positive on unrelated Thai/English text
        "ข้าวขาวไหม", "ซื้อที่ไหนดี", "ขายดีครับ", "ใช้ยังไงครับ",
        "ราคาเท่าไหร่ครับ", "มีอะไรบ้าง",
    ])
    def test_normalizer_no_false_positive(self, query):
        """Aggressive normalization (strip ั, whitespace, tone) must not
        false-match brand-new queries or other-handler queries."""
        from app.services.rag.followup_patterns import is_comparison_followup
        assert not is_comparison_followup(query), f"False positive: {query!r}"


# =============================================================================
# 1. Source-level guards — wire-up across files must not regress
# =============================================================================

class TestOrchestratorPropagatesFlag:
    def test_comparison_followup_sets_hint(self):
        from app.services.rag import orchestrator
        src = inspect.getsource(orchestrator.AgenticRAG.process)
        assert "_comparison_followup" in src, (
            "orchestrator doesn't propagate _comparison_followup hint"
        )

    def test_uses_shared_pattern_module(self):
        """Orchestrator must use shared is_comparison_followup — not a local list."""
        from app.services.rag import orchestrator
        src = inspect.getsource(orchestrator.AgenticRAG.process)
        assert "is_comparison_followup" in src, (
            "orchestrator should delegate pattern matching to "
            "app.services.rag.followup_patterns.is_comparison_followup"
        )

    def test_plant_restated_not_new_topic_on_compare(self):
        """'ตัวไหนดีสำหรับข้าว' with state.plant=ข้าว must NOT be marked new topic."""
        from app.services.rag import orchestrator
        src = inspect.getsource(orchestrator.AgenticRAG.process)
        # Guard must factor compare into the plant-new-topic decision
        assert "_plant_would_be_new" in src or "_is_compare and not _different_plant" in src, (
            "orchestrator's new-topic guard must exempt compare follow-ups "
            "that re-state the same plant"
        )


class TestQueryUnderstandingClampsExpansion:
    def test_clamp_expanded_queries_on_comparison(self):
        from app.services.rag import query_understanding_agent
        src = inspect.getsource(query_understanding_agent.QueryUnderstandingAgent._llm_analyze)
        assert "_comparison_followup" in src, (
            "query_understanding_agent doesn't check _comparison_followup"
        )
        assert "expanded_queries = list(hints['product_names'])" in src, (
            "query_understanding_agent doesn't clamp expanded_queries to "
            "product_names on comparison follow-up — LLM hallucination will "
            "pollute retrieval"
        )


class TestRetrievalShortCircuits:
    def test_retrieval_skips_multi_source_on_comparison(self):
        from app.services.rag import retrieval_agent
        src = inspect.getsource(retrieval_agent.RetrievalAgent.retrieve)
        assert "_comparison_followup" in src
        assert "direct_lookup_ids" in src


class TestResponseGeneratorHonorsFlag:
    def test_uses_shared_pattern_module(self):
        from app.services.rag import response_generator_agent
        src = inspect.getsource(response_generator_agent.ResponseGeneratorAgent)
        assert "is_comparison_followup" in src, (
            "response_generator should import shared is_comparison_followup — "
            "private keyword list causes drift from orchestrator"
        )

    def test_comparison_mode_honors_entity_flag(self):
        from app.services.rag import response_generator_agent
        src = inspect.getsource(response_generator_agent.ResponseGeneratorAgent)
        assert "_comparison_followup" in src, (
            "response_generator must check entities['_comparison_followup'] — "
            "Mode decision should honor orchestrator's follow-up detection"
        )
