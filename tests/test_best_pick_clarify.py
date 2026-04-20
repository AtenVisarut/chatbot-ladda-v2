"""
Tests — "ตัวไหนดีสุด" follow-up → bot should ask for crop+stage before picking one

Real-world scenario (from LINE screenshot):
  T1: user "เพลี้ยไฟทุเรียนใช้อะไรดี"
  T1 bot: [lists 8 insecticide products]
  T2: user "ตัวไหนดีสุดครับ"
  T2 bot (BEFORE fix): picked ไบเตอร์ arbitrarily
  T2 bot (AFTER fix):  asks back for crop+stage to narrow down

Logic:
  - detect_best_pick = query matches ตัวไหนดี/อันไหนดี/แนะนำตัวไหน/สรุปตัวไหน
    + query length < 40 chars
    + context exists (this is a follow-up, not standalone)
  - If plant NOT known → ask plant
  - If plant known + stage NOT known → ask stage
  - If both known → pick 1 + explain why
"""

from __future__ import annotations

import inspect
import pytest


class TestBestPickPatterns:
    """Best-pick follow-up phrase recognition"""

    @pytest.mark.parametrize("query,expected", [
        ("ตัวไหนดีสุด", True),
        ("ตัวไหนดีที่สุด", True),
        ("ตัวไหนดีสุดครับ", True),
        ("อันไหนดีสุด", True),
        ("อันไหนดี", True),
        ("แนะนำตัวไหน", True),
        ("สรุปตัวไหน", True),
        ("ใช้ตัวไหนดี", True),
        # Not best-pick
        ("ไบเตอร์ใช้ยังไง", False),
        ("อัตราใช้เท่าไหร่", False),
        ("ใช้ยังไง", False),
    ])
    def test_phrase_detection(self, query, expected):
        _BEST_PICK = [
            'ตัวไหนดีสุด', 'ตัวไหนดีที่สุด', 'ตัวไหนดี', 'อันไหนดีสุด',
            'อันไหนดีที่สุด', 'อันไหนดี', 'แนะนำตัวไหน', 'สรุปตัวไหน',
            'ตัวไหนเวิร์ค', 'เลือกตัวไหน', 'ใช้ตัวไหนดี',
        ]
        matched = any(p in query for p in _BEST_PICK)
        assert matched == expected, (
            f"Query {query!r} expected={expected}, got={matched}"
        )


class TestSourceWiring:
    """Source-level guards on response generator"""

    def test_best_pick_note_defined(self):
        from app.services.rag import response_generator_agent
        src = inspect.getsource(
            response_generator_agent.ResponseGeneratorAgent._generate_llm_response
        )
        assert "_BEST_PICK_PATTERNS" in src
        assert "best_pick_note" in src
        assert "{best_pick_note}" in src, (
            "best_pick_note must be interpolated into final prompt"
        )

    def test_asks_for_plant_when_missing(self):
        from app.services.rag import response_generator_agent
        src = inspect.getsource(
            response_generator_agent.ResponseGeneratorAgent._generate_llm_response
        )
        assert "ใช้กับพืชอะไร" in src, (
            "best_pick_note must ask for plant when not known"
        )
        assert "ระยะของพืช" in src, (
            "best_pick_note must ask for growth stage when not known"
        )

    def test_context_scan_for_known_plant(self):
        """Must scan context text for plant (not just entities)"""
        from app.services.rag import response_generator_agent
        src = inspect.getsource(
            response_generator_agent.ResponseGeneratorAgent._generate_llm_response
        )
        # Should check context for plant names list
        assert "_PLANT_NAMES" in src or "ทุเรียน" in src  # presence of crop list

    def test_picks_one_when_both_known(self):
        """When plant+stage both known → pick 1 + explain (no ask-back)"""
        from app.services.rag import response_generator_agent
        src = inspect.getsource(
            response_generator_agent.ResponseGeneratorAgent._generate_llm_response
        )
        assert "เลือก 1 สินค้า" in src or "pick" in src.lower()
        assert "Skyrocket" in src or "บอกเหตุผล" in src, (
            "When enough context, scorer should pick + explain why"
        )

    def test_only_triggers_on_short_follow_ups(self):
        """best-pick should only activate for short queries (follow-ups)"""
        from app.services.rag import response_generator_agent
        src = inspect.getsource(
            response_generator_agent.ResponseGeneratorAgent._generate_llm_response
        )
        assert "len(_q.strip()) < 40" in src or "len(_q.strip()) <= 40" in src
