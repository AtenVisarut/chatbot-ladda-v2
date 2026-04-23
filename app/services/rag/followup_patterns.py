"""
Single source of truth for follow-up detection patterns.

Imported by orchestrator, query_understanding_agent, and response_generator
so the three agents can't drift out of sync (drift caused the 2026-04-23
cross-category bug: orchestrator matched "ตัวไหนดี" but response generator's
private list didn't, so Mode ก fired instead of Mode ข).
"""
from __future__ import annotations

import re

from app.utils.text_processing import strip_thai_diacritics


# Comparison / selection follow-up — user is choosing among products the bot
# already listed in a prior turn. Must be precise enough to not fire on
# brand-new queries. Matched as substrings after normalization.
COMPARISON_FOLLOWUP_PATTERNS: tuple[str, ...] = (
    # "ตัวไหน…" family
    'ตัวไหนดี', 'ตัวไหนเหมาะ', 'ตัวไหนเด็ด', 'ตัวไหนเจ๋ง',
    'ตัวไหนเวิร์ค', 'ตัวไหนเวิร์ก', 'ตัวไหนได้ผล', 'ตัวไหนน่าใช้',
    'ตัวไหนเด่น', 'ตัวไหนคุ้ม',
    # "อันไหน…" family
    'อันไหนดี', 'อันไหนเหมาะ', 'อันไหนได้ผล', 'อันไหนเด็ด',
    # "แบบไหน…" / "รุ่นไหน…" family
    'แบบไหนดี', 'แบบไหนเหมาะ',
    'รุ่นไหนดี', 'รุ่นไหนเหมาะ',
    # Explicit compare verbs
    'ต่างกัน', 'แตกต่าง', 'เปรียบเทียบ', 'ใช้ต่าง', 'เทียบกัน',
    # English
    'which is good', 'which is best', 'which one',
    'best one', 'compare', 'comparison',
)


_WHITESPACE_RE = re.compile(r'\s+')
# Sara-a short (ั, U+0E31) — commonly omitted typo in "ตัว" → "ตว".
# Strip for matching only; never mutate the user's original text.
_DROPPABLE_VOWELS_RE = re.compile(r'[ั]')


def _normalize(text: str) -> str:
    """Normalize text for tolerant pattern matching.

    Applies, in order:
      1. lowercase (English)
      2. strip all whitespace (Thai has no word spaces — "ตัว ไหน ดี" ≡ "ตัวไหนดี")
      3. strip tone marks + thanthakhat + mai taikhu (shared with diacritics_match)
      4. strip ั (commonly omitted typo: "ตวไหนดี" ≡ "ตัวไหนดี")
    """
    text = text.lower()
    text = _WHITESPACE_RE.sub('', text)
    text = strip_thai_diacritics(text)
    text = _DROPPABLE_VOWELS_RE.sub('', text)
    return text


# Pre-compute normalized patterns at import time — matching is in the hot path
# (every message) and the pattern list is constant.
_NORMALIZED_PATTERNS: tuple[str, ...] = tuple(_normalize(p) for p in COMPARISON_FOLLOWUP_PATTERNS)


def is_comparison_followup(query: str) -> bool:
    """True if the query is asking to choose/compare among prior products.

    Tolerant to honorifics (ครับ/คับ/ค่ะ/…), internal whitespace ("ตัว ไหน ดี"),
    missing short vowels ("ตวไหนดี"), and common tone-mark omissions.

    Example matches: "ตัวไหนดีครับ", "อันไหนเหมาะสุด", "ใช้ต่างกันยังไง",
    "compare them", "which one is best".
    Example non-matches: "แนะนำยาฆ่าหญ้า", "ใช้ยังไง", "ขายดี" (sales-popularity,
    handled separately).
    """
    if not query:
        return False
    norm = _normalize(query)
    return any(p in norm for p in _NORMALIZED_PATTERNS)
