"""
Diagnostic-intent detection (deterministic, no LLM).

When a user asks a query like "ยางพาราเป็นจุดสีน้ำตาลที่ใบเกิดจากอะไร"
they want a diagnosis, not just a product lookup. We want to:
  1. Widen the disease candidate set via curated crop priors.
  2. Switch the response template to hedge language ("อาจเกิดจาก X หรือ Y").

This module is keyword-based on purpose — zero LLM calls, zero
hallucination risk. Gated by DIAGNOSTIC_INTENT_ENABLED feature flag.
"""
from __future__ import annotations

_DIAGNOSTIC_KEYWORDS = (
    "เกิดจากอะไร",
    "เกิดจาก",
    "สาเหตุ",
    "เพราะอะไร",
    "โรคอะไร",
    "เป็นโรคอะไร",
    "คืออะไร",
    "อาการแบบนี้",
    "ทำไมถึง",
    "ทำไม",
)


def is_diagnostic_query(query: str) -> bool:
    """Return True if query reads as a diagnosis request (causal/what-is)."""
    if not query:
        return False
    q = query.strip()
    return any(kw in q for kw in _DIAGNOSTIC_KEYWORDS)
