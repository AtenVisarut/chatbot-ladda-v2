"""
Regression tests for "ยิ่งคุยยิ่งแย่" bug:
product context being dropped or over-filtered on product-capability / MoA
follow-ups like "ไบเตอร์กำจัดอะไรได้บ้าง และ อยู่กลุ่ม moa อะไร".

Two layers caused the failure:
  1. orchestrator._FOLLOWUP_USAGE did not include capability/MoA keywords, so
     the product from conversation state was dropped as "topic change".
  2. response_generator._skip_disease_context did not cover capability queries,
     so a stale context_disease (e.g. แอนแทรคโนส) narrowed docs 23 → 1.

These tests mirror the minimal keyword checks so we can assert routing logic
without spinning up the full async orchestrator (which needs OpenAI+Supabase).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Orchestrator follow-up keyword mirror
# ---------------------------------------------------------------------------
_FOLLOWUP_USAGE = [
    'ใช้ยังไง', 'ใช้เท่าไหร่', 'ผสมกี่', 'ฉีดกี่', 'พ่นกี่',
    'ผสมเท่าไหร่', 'อัตราเท่าไหร่', 'ใช้กี่', 'ราดกี่',
    'ใช้ช่วงไหน', 'ใช้ตอนไหน', 'ใช้ได้กี่', 'ได้ผลไหม',
    'ได้ช่วงไหน', 'ช่วงไหนได้', 'ใช้ได้ไหม', 'ใช้กับ',
    'กลุ่มสาร', 'กลุ่มเคมี', 'irac', 'frac', 'hrac', 'rac', 'moa',
    'ขนาดบรรจุ', 'กี่ลิตร', 'กี่กรัม', 'ขนาดไหน',
    'กำจัดอะไร', 'ฆ่าอะไร', 'กำจัดได้', 'ฆ่าได้',
    'ออกฤทธิ์', 'สารออกฤทธิ์', 'สารสำคัญ', 'active ingredient',
]


def _is_followup_usage(query: str) -> bool:
    return len(query.strip()) < 60 and any(p in query.lower() for p in _FOLLOWUP_USAGE)


@pytest.mark.parametrize(
    "query",
    [
        "กำจัดอะไรได้บ้าง และ อยู่กลุ่ม moaอะไรคับ",
        "ไบเตอร์กำจัดอะไรได้บ้าง",
        "ตัวนี้ฆ่าอะไรได้",
        "สารออกฤทธิ์คืออะไร",
        "อยู่กลุ่ม moa อะไร",
        "กลุ่มสารอะไร",
        "ออกฤทธิ์ยังไง",
        "ใช้ยังไง",
        "ผสมกี่ซีซี",
        "ราคาเท่าไร",  # short, uses "เท่าไร" but not in FOLLOWUP_USAGE → False
    ],
)
def test_capability_or_usage_queries_keep_product(query):
    # 9/10 queries should be recognized as follow-ups (→ product context kept).
    # "ราคาเท่าไร" is a non-followup counter-case included to sanity-check.
    recognized = _is_followup_usage(query)
    if "ราคา" in query:
        assert recognized is False, f"'{query}' is not a capability/usage follow-up"
    else:
        assert recognized is True, (
            f"'{query}' MUST be recognized as follow-up or orchestrator "
            f"will drop the product from conversation state"
        )


# ---------------------------------------------------------------------------
# Response generator capability-skip mirror
# ---------------------------------------------------------------------------
_CAPABILITY_PAT = [
    'กำจัดอะไร', 'ฆ่าอะไร', 'กำจัดได้', 'ฆ่าได้',
    'ออกฤทธิ์', 'สารออกฤทธิ์', 'สารสำคัญ',
    'กลุ่มสาร', 'กลุ่มเคมี', 'moa', 'irac', 'frac', 'hrac',
]


def _should_skip_context_disease(query: str) -> bool:
    return any(p in query.lower() for p in _CAPABILITY_PAT)


@pytest.mark.parametrize(
    "query",
    [
        "กำจัดอะไรได้บ้าง และ อยู่กลุ่ม moaอะไรคับ",
        "สารออกฤทธิ์คืออะไร",
        "ไบเตอร์ moa อะไร",
        "อยู่กลุ่ม irac ไหน",
        "ฆ่าอะไรได้บ้าง",
    ],
)
def test_capability_query_skips_context_disease_filter(query):
    assert _should_skip_context_disease(query) is True, (
        f"'{query}' — response generator must skip stale context disease filter"
    )


@pytest.mark.parametrize(
    "query",
    [
        "มีสินค้าอื่นไหม",          # generic follow-up — keep context disease
        "ตัวไหนดีสุด",               # comparison — handled by separate skip
        "ใช้ยังไง",                   # usage — not capability
    ],
)
def test_non_capability_query_preserves_context_disease(query):
    # These should NOT skip the context disease filter.
    # (ตัวไหนดีสุด is handled via _COMPARE_PAT in real code, not tested here.)
    assert _should_skip_context_disease(query) is False
