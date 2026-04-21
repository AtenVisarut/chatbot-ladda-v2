"""
Regression tests for greeting-keyword false positives.

Background:
    GREETING_KEYWORDS contains short forms like "ดีครับ" / "ดีคับ" that
    legitimately appear at the end of follow-up questions such as
    "ใช้ตัวไหนดีคับ". A substring match would misroute these to the
    greeting fast path and skip RAG entirely. handler.py adds a
    question-marker guard ("ไหน", "อะไร", ...) to prevent that.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.prompts import GREETING_KEYWORDS


# Mirror of the guard block in handler.py:5a. Kept as a pure function so
# we can test routing without spinning up the full async handler.
_QUESTION_MARKERS = (
    "ไหน", "อะไร", "ยังไง", "เท่าไร", "เท่าไหร่",
    "ไหม", "มั้ย", "กี่", "ทำไม",
)


def _is_greeting_fastpath(message: str, has_agri_keyword: bool = False) -> bool:
    msg_stripped = message.strip().lower()
    has_question_marker = any(qm in msg_stripped for qm in _QUESTION_MARKERS)
    if has_agri_keyword or has_question_marker or len(msg_stripped) >= 30:
        return False
    for gkw in GREETING_KEYWORDS:
        if gkw in msg_stripped:
            if len(gkw) <= 2 and len(msg_stripped) > 8:
                continue
            return True
    return False


# ---------------------------------------------------------------------------
# False-positive regressions (the bug being fixed)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "query",
    [
        "ใช้ตัวไหนดีคับ",
        "ใช้ตัวไหนดีครับ",
        "ใช้อะไรดีครับ",
        "ใช้อะไรดีคับ",
        "ใช้ยังไงดีครับ",
        "ตัวไหนดีครับ",
        "แนะนำตัวไหนดีคับ",
        "ราคาเท่าไรครับ",
        "ใช้ได้ไหมครับ",
        "ทำไมถึงเป็นแบบนี้",
    ],
)
def test_follow_up_questions_not_greeting(query):
    assert _is_greeting_fastpath(query) is False, (
        f"'{query}' should NOT be routed to greeting flow"
    )


# ---------------------------------------------------------------------------
# True positives must still work
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "query",
    [
        "สวัสดีครับ",
        "สวัสดีค่ะ",
        "หวัดดีครับ",
        "hello",
        "hi",
        "ดีครับ",
        "ดีคับ",
        "ดีค่ะ",
    ],
)
def test_plain_greeting_still_detected(query):
    assert _is_greeting_fastpath(query) is True, (
        f"'{query}' should be routed to greeting flow"
    )


# ---------------------------------------------------------------------------
# Agri question guard still wins
# ---------------------------------------------------------------------------
def test_agri_keyword_wins_over_greeting():
    # Even without a question marker, an agri keyword should skip greeting.
    assert _is_greeting_fastpath("ปลูกข้าว20วันใช้ยาดีครับ", has_agri_keyword=True) is False


# ---------------------------------------------------------------------------
# Long-message guard
# ---------------------------------------------------------------------------
def test_long_message_not_greeting():
    # ≥30 chars → skip greeting fast path regardless of match.
    assert _is_greeting_fastpath("สวัสดีครับ อยากสอบถามเรื่องยาสักหน่อย ไม่แน่ใจ") is False
