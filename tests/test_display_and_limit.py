"""
Tests — Display formatting (Thai name + %) and product list limit (10 from 7)

Scenarios:
1. _combine_thai_name_with_percent helper pairs Thai tokens with % from
   active_ingredient correctly (single, multi-compound, edge cases).
2. docs_to_use limit changed 7 → 10 so broad queries like
   "เพลี้ยไฟในทุเรียน" return up to 10 matching products.
3. Prompt text instructs LLM to output Thai name + % format.
"""

from __future__ import annotations

import inspect
import os

import pytest
from dotenv import load_dotenv

load_dotenv(override=True)


# =============================================================================
# 1. _combine_thai_name_with_percent helper (pure function, no DB)
# =============================================================================

class TestThaiNamePercentCombine:
    """Pair common_name_th tokens with % from active_ingredient"""

    @pytest.mark.parametrize("thai,ai,expected", [
        # Single active ingredient with %
        (
            "ไบเฟนทริน",
            "BIFENTHRIN 5% SC",
            "ไบเฟนทริน 5%",
        ),
        # Two active ingredients (common in insecticides)
        (
            "ไบเฟนทริน + อิมิดาคลอพริด",
            "BIFENTHRIN 5% + IMIDACLOPRID 25% SC",
            "ไบเฟนทริน 5% + อิมิดาคลอพริด 25%",
        ),
        # Weed killer — single
        (
            "กลูโฟซิเนต-แอมโมเนียม",
            "GLUFOSINATE-AMMONIUM 15% W/V SL",
            "กลูโฟซิเนต-แอมโมเนียม 15%",
        ),
        # Fungicide
        (
            "เฮกซาโคนาโซล",
            "HEXACONAZOLE 5% SC",
            "เฮกซาโคนาโซล 5%",
        ),
        # Fractional %
        (
            "อะเซทามิพริด",
            "ACETAMIPRID 2.85% EC",
            "อะเซทามิพริด 2.85%",
        ),
        # Triple active ingredients
        (
            "a + b + c",
            "A 10% + B 20% + C 30% EC",
            "a 10% + b 20% + c 30%",
        ),
    ])
    def test_pair_thai_with_percent(self, thai, ai, expected):
        from app.services.rag.response_generator_agent import _combine_thai_name_with_percent

        result = _combine_thai_name_with_percent(thai, ai)
        assert result == expected, (
            f"thai={thai!r}, ai={ai!r}\n  expected={expected!r}\n  got={result!r}"
        )

    def test_empty_thai_returns_empty(self):
        from app.services.rag.response_generator_agent import _combine_thai_name_with_percent
        assert _combine_thai_name_with_percent("", "BIFENTHRIN 5%") == ""

    def test_empty_ai_returns_thai_only(self):
        from app.services.rag.response_generator_agent import _combine_thai_name_with_percent
        assert _combine_thai_name_with_percent("ไบเฟนทริน", "") == "ไบเฟนทริน"

    def test_missing_percent_returns_thai_only(self):
        """ถ้า active_ingredient ไม่มี % → ไม่ต้องเติม % (ห้ามคิดค่าเอง)"""
        from app.services.rag.response_generator_agent import _combine_thai_name_with_percent
        result = _combine_thai_name_with_percent("ไบเฟนทริน", "BIFENTHRIN")
        assert result == "ไบเฟนทริน"

    def test_mismatched_token_count_returns_thai_only(self):
        """Thai 2 tokens, AI 3 tokens → cannot align → return Thai only"""
        from app.services.rag.response_generator_agent import _combine_thai_name_with_percent
        result = _combine_thai_name_with_percent(
            "a + b",
            "A 10% + B 20% + C 30%",
        )
        assert result == "a + b"


# =============================================================================
# 2. docs_to_use limit 10 (source-level check)
# =============================================================================

class TestDocsLimit:
    """Regression guard: limit is 10, referenced via _DOCS_LIMIT constant"""

    def test_docs_to_use_limit_is_ten(self):
        from app.services.rag import response_generator_agent
        src = inspect.getsource(response_generator_agent.ResponseGeneratorAgent._generate_llm_response)
        assert "_DOCS_LIMIT = 10" in src, (
            "docs_to_use limit should be defined as _DOCS_LIMIT = 10"
        )
        # Must NOT use hard-coded [:7] anymore in docs_to_use init
        assert "documents[:7]" not in src, (
            "_generate_llm_response() should no longer slice to 7 (use _DOCS_LIMIT)"
        )

    def test_docs_limit_constant_used_consistently(self):
        """Rescue branch must also use _DOCS_LIMIT (not hardcoded 7)"""
        from app.services.rag import response_generator_agent
        src = inspect.getsource(response_generator_agent.ResponseGeneratorAgent._generate_llm_response)
        # Count hardcoded 7s — should be 0 for docs_to_use comparisons
        import re
        bad_patterns = [
            r"len\(docs_to_use\)\s*>=\s*7\b",
            r"docs_to_use\[:7\]",
        ]
        for pat in bad_patterns:
            matches = re.findall(pat, src)
            assert not matches, f"Found hardcoded '7' reference: {pat} → {matches}"


# =============================================================================
# 3. Prompt instructs LLM to include %
# =============================================================================

class TestPromptIncludesPercent:
    """Prompts must tell LLM to include % when showing ingredient name"""

    def test_prompt_mentions_percent_format(self):
        from app import prompts as prompts_mod
        src = inspect.getsource(prompts_mod)
        # Must mention the % rule and an example
        assert "ภาษาไทย + %" in src or "ไทย + %" in src, (
            "prompts.py missing 'ชื่อไทย + %' format instruction"
        )

    def test_prompt_no_longer_forbids_percent(self):
        """Old rule 'ไม่ต้องแสดง % ในวงเล็บ' must be removed"""
        from app import prompts as prompts_mod
        src = inspect.getsource(prompts_mod)
        assert "ไม่ต้องแสดง %" not in src, (
            "Legacy rule 'ไม่ต้องแสดง %' still present — must be removed"
        )

    def test_prompt_has_concrete_example_with_percent(self):
        """Prompt should contain an example like '(ไบเฟนทริน 5% + อิมิดาคลอพริด 25%)'"""
        from app import prompts as prompts_mod
        src = inspect.getsource(prompts_mod)
        # At least one example with % in parens showing the target format
        import re
        # Accept either 'ไบเฟนทริน 5%' or any 'ชื่อไทย N%' pattern
        has_pct_example = bool(re.search(r'[\u0E00-\u0E7F]+\s*\d+(\.\d+)?%', src))
        assert has_pct_example, "Prompt missing concrete example of 'ชื่อไทย N%'"


# =============================================================================
# 4. Context builder includes "แสดงในวงเล็บ" hint for LLM
# =============================================================================

class TestContextBuilderHint:
    """When both common_name_th + active_ingredient exist, context must provide
    a pre-merged 'แสดงในวงเล็บ' hint so the LLM doesn't drop %"""

    def test_context_builder_emits_combined_hint(self):
        from app.services.rag import response_generator_agent
        src = inspect.getsource(response_generator_agent.ResponseGeneratorAgent._generate_llm_response)
        assert "แสดงในวงเล็บ" in src, (
            "_generate_llm_response() should emit a pre-merged 'แสดงในวงเล็บ' hint per product"
        )
        assert "_combine_thai_name_with_percent" in src, (
            "_generate_llm_response() should call the combining helper"
        )
