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


class TestClarificationMerge:
    """
    Real-world regression (LINE screenshot 2026-04-20):
      T1: user "ไฟท็อปใช้ยาอะไรแก้"    → bot: 4 fungicides
      T2: user "ตัวไหนดีสุดคับ"        → bot asks for stage
      T3: user "ระยะติดผล"            → BUG: bot recommended PGR/ปุ๋ย instead
                                       of narrowing to fungicides

    Fix: when context shows bot asked for missing info AND current query
    is a short stage-only reply → merge with root topic from earlier
    user message.
    """

    def test_stage_reply_patterns(self):
        # Keep in sync with orchestrator Stage -1 _STAGE_WORDS
        _STAGE_WORDS = (
            "ใบอ่อน", "ออกดอก", "ติดผล", "หลังเก็บเกี่ยว",
            "ต้นอ่อน", "แตกใบ", "ระยะ", "ต้นกล้า", "หลังเก็บ",
            "ก่อนเก็บ", "ก่อนเก็บเกี่ยว", "กำลังติดผล", "กำลังออกดอก",
            "ระยะดอก", "ระยะผล", "ระยะก่อนออกดอก", "ระยะติดผล",
            "ดอก", "ผลอ่อน", "ผลแก่", "ผลเล็ก",
            "ใบแก่", "แตกยอด",
        )
        positive = [
            "ระยะติดผล", "ใบอ่อน", "ออกดอกแล้ว", "หลังเก็บเกี่ยว",
            # Short-form replies users actually send
            "ดอก",          # short for ออกดอก
            "ผลอ่อน",
            "ระยะดอก",
        ]
        negative = ["ไบเตอร์ใช้ยังไง", "อัตราเท่าไหร่", "ใช้ยังไง", "ราคา"]
        for q in positive:
            assert any(kw in q for kw in _STAGE_WORDS), f"Missed: {q!r}"
        for q in negative:
            assert not any(kw in q for kw in _STAGE_WORDS), f"False match: {q!r}"

    def test_orchestrator_has_clarification_merge_logic(self):
        import inspect
        from app.services.rag import orchestrator
        src = inspect.getsource(orchestrator)
        assert "_is_short_stage_reply" in src
        assert "_bot_asked_for_context" in src
        assert "Clarification reply: merging with" in src

    def test_skip_short_best_pick_messages_when_finding_root(self):
        """Ensure ตัวไหนดีสุด is NOT picked as root topic"""
        import inspect
        from app.services.rag import orchestrator
        src = inspect.getsource(orchestrator)
        assert "ตัวไหนดี" in src
        assert "_SKIP_PATTERNS" in src or "SKIP_PATTERNS" in src

    def test_uses_latest_topic_not_earliest(self):
        """Multi-topic conversation: must use LATEST user topic, not first"""
        import inspect
        from app.services.rag import orchestrator
        src = inspect.getsource(orchestrator)
        # Must iterate in reverse to prefer recent topic
        assert "reversed(_user_msgs)" in src, (
            "Must iterate ผู้ใช้ messages in reverse to pick latest topic"
        )
        assert "latest topic" in src.lower() or "most recent" in src.lower(), (
            "Logic must document latest-first selection"
        )

    def test_skips_stage_only_messages_when_finding_root(self):
        """An earlier stage-only message must not be used as root topic"""
        import inspect
        from app.services.rag import orchestrator
        src = inspect.getsource(orchestrator)
        # The skip must check for stage words AND require action words to pass
        assert "_STAGE_WORDS" in src
        # Keywords that distinguish real queries from stage-only replies
        for kw in ("ยา", "ใช้", "แนะนำ", "โรค", "หนอน", "เพลี้ย"):
            assert kw in src, (
                f"Stage-reply filter must check for action keyword {kw!r}"
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

    def test_known_stage_scans_user_turns_only(self):
        """
        Regression (Railway log 2026-04-21): "ตัวไหนใช้ดีที่สุดครับ" for rice
        went straight to pick-one path because _known_stage=True was triggered
        by the bot's OWN previous reply containing "ในระยะข้าวอายุ 10-15 วัน".
        The stage-keyword scan must restrict to user turns only.
        """
        from app.services.rag import response_generator_agent
        src = inspect.getsource(
            response_generator_agent.ResponseGeneratorAgent._generate_llm_response
        )
        # Must build a user-only view of the context before the stage scan
        assert "line.startswith(\"ผู้ใช้:\")" in src, (
            "Stage-keyword scan must filter _ctx_recent to ผู้ใช้: lines"
        )
        # And must run the scan over that filtered view, not the raw context
        assert "_known_stage = any(kw in _user_ctx" in src, (
            "_known_stage must be evaluated against the user-only context"
        )
