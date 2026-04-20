"""
Unit tests for capability_scorer — heuristic scoring of bot answers
No API calls; tests only the rule-based scorer logic.
"""

from __future__ import annotations

import pytest

from tests.capability_scorer import (
    score_product_info, score_pest_crop, score_usage_rate,
    score_moa, score_selling_point, score_comparison,
    build_questions,
    _extract_percents, _extract_formulation,
)


# =============================================================================
# Helpers
# =============================================================================

class TestHelpers:
    @pytest.mark.parametrize("text,expected", [
        ("BIFENTHRIN 5% + IMIDACLOPRID 25%", ["5%", "25%"]),
        ("HEXACONAZOLE 5% SC", ["5%"]),
        ("ACETAMIPRID 2.85% EC", ["2.85%"]),
        ("no percent", []),
    ])
    def test_extract_percents(self, text, expected):
        assert _extract_percents(text) == expected

    @pytest.mark.parametrize("ai,expected", [
        ("BIFENTHRIN 5% + IMIDACLOPRID 25% SC", "SC"),
        ("HEXACONAZOLE 5% SC", "SC"),
        ("OXADIAZON 25% EC", "EC"),
        ("ACETAMIPRID 2.85% EC", "EC"),
        ("ไดยูรอน 80% WP", "WP"),
        ("ไดยูแมกซ์ 80 ดับเบิลยู.พี.", "ดับเบิลยู.พี."),
        ("no formulation here", None),
    ])
    def test_extract_formulation(self, ai, expected):
        assert _extract_formulation(ai) == expected


# =============================================================================
# Capability 1: Product info
# =============================================================================

class TestProductInfo:
    PRODUCT = {
        "product_name": "ไบเตอร์",
        "active_ingredient": "BIFENTHRIN 5% + IMIDACLOPRID 25% SC",
        "common_name_th": "ไบเฟนทริน + อิมิดาคลอพริด",
    }

    def test_perfect_answer(self):
        answer = "ไบเตอร์ (ไบเฟนทริน 5% + อิมิดาคลอพริด 25% SC) — สารสำคัญสองตัว"
        r = score_product_info(answer, self.PRODUCT)
        assert r.score == 100, f"Expected 100, got {r.score} ({r.reason})"

    def test_missing_formulation(self):
        answer = "ไบเตอร์ (ไบเฟนทริน 5% + อิมิดาคลอพริด 25%)"
        r = score_product_info(answer, self.PRODUCT)
        assert r.score == 75, f"Should lose 25 for formulation: {r.score} ({r.reason})"

    def test_missing_percent(self):
        answer = "ไบเตอร์ (ไบเฟนทริน + อิมิดาคลอพริด SC)"
        r = score_product_info(answer, self.PRODUCT)
        assert r.score == 75, f"Should lose 25 for percent: {r.score} ({r.reason})"

    def test_missing_all_ingredient_info(self):
        answer = "ไบเตอร์ ใช้ทั่วไป"
        r = score_product_info(answer, self.PRODUCT)
        # has name (25), missing thai, missing %, missing formulation
        assert r.score == 25, f"Only product name: {r.score} ({r.reason})"

    def test_empty_answer(self):
        r = score_product_info("", self.PRODUCT)
        assert r.score == 0

    def test_no_db_data_gives_full(self):
        """DB lacks some fields → those checks get full credit"""
        p = {"product_name": "ชุดกล่องม่วง"}  # no AI, no thai, no %, no formulation
        answer = "ชุดกล่องม่วง"
        r = score_product_info(answer, p)
        # Only name check runs (25) + others default to 25 each = 100
        assert r.score == 100


# =============================================================================
# Capability 2: Pest / crop
# =============================================================================

class TestPestCrop:
    PRODUCT = {
        "insecticides": "ทุเรียน - เพลี้ยไฟ เพลี้ยจั๊กจั่น หนอนเจาะผล",
        "applicable_crops": "ทุเรียน, ข้าว, มะม่วง",
        "fungicides": None,
        "herbicides": None,
        "biostimulant": None,
        "pgr_hormones": None,
        "fertilizer": None,
    }

    def test_perfect_answer(self):
        answer = "ไบเตอร์ใช้กำจัดเพลี้ยไฟและเพลี้ยจั๊กจั่นในทุเรียนได้ดี"
        r = score_pest_crop(answer, self.PRODUCT)
        assert r.score == 100

    def test_only_crop_mentioned(self):
        answer = "ใช้กับทุเรียนและข้าวได้"
        r = score_pest_crop(answer, self.PRODUCT)
        # no pest mentioned → 0 for target, 50 for crop
        assert r.score == 50

    def test_only_pest_mentioned(self):
        answer = "กำจัดเพลี้ยไฟและเพลี้ยจั๊กจั่น"
        r = score_pest_crop(answer, self.PRODUCT)
        assert r.score == 50


# =============================================================================
# Capability 3: Usage rate + verb
# =============================================================================

class TestUsageRate:
    PRODUCT = {
        "usage_rate": "15-20 มล. ต่อน้ำ 20 ลิตร",
        "how_to_use": "ผสมน้ำแล้วฉีดพ่นทั่วทรงพุ่ม",
    }

    def test_perfect_answer(self):
        answer = "อัตราใช้ 15-20 มล./น้ำ 20 ลิตร ผสมน้ำแล้วฉีดพ่น"
        r = score_usage_rate(answer, self.PRODUCT)
        assert r.score == 100

    def test_missing_verb(self):
        answer = "อัตราใช้ 15-20 มล./น้ำ 20 ลิตร"
        r = score_usage_rate(answer, self.PRODUCT)
        assert r.score == 50  # has rate, missing verb

    def test_missing_rate(self):
        answer = "ผสมน้ำแล้วฉีดพ่นตามฉลาก"
        r = score_usage_rate(answer, self.PRODUCT)
        # has verb (50), missing specific number (0 or 25)
        assert 50 <= r.score <= 75


# =============================================================================
# Capability 4: MoA
# =============================================================================

class TestMoA:
    PRODUCT_WITH_RAC = {
        "chemical_group_rac": "กลุ่ม 3A + 4A",
    }
    PRODUCT_SINGLE_CODE = {
        "chemical_group_rac": "กลุ่ม E",
    }
    PRODUCT_NO_RAC = {
        "chemical_group_rac": None,
    }

    def test_perfect_match_compound(self):
        answer = "ไบเตอร์อยู่ในกลุ่ม 3A + 4A"
        r = score_moa(answer, self.PRODUCT_WITH_RAC)
        assert r.score == 100

    def test_partial_match(self):
        answer = "อยู่ในกลุ่ม 3A"
        r = score_moa(answer, self.PRODUCT_WITH_RAC)
        assert r.score == 60

    def test_single_code(self):
        answer = "ออล์สตาร์อยู่ในกลุ่มสาร E"
        r = score_moa(answer, self.PRODUCT_SINGLE_CODE)
        assert r.score == 100

    def test_no_match_penalizes(self):
        answer = "ไบเตอร์ใช้กำจัดเพลี้ย"
        r = score_moa(answer, self.PRODUCT_WITH_RAC)
        assert r.score == 0

    def test_no_data_penalizes_when_rac_context(self):
        """LLM says 'ไม่มีข้อมูลกลุ่ม IRAC' → 0 points even if codes not mentioned"""
        answer = "ขออภัย ไม่มีข้อมูลเรื่องกลุ่ม IRAC ของสินค้านี้"
        r = score_moa(answer, self.PRODUCT_WITH_RAC)
        assert r.score == 0

    def test_no_rac_in_db_full_credit(self):
        answer = "ชุดกล่องม่วงเป็นชุดบำรุง"
        r = score_moa(answer, self.PRODUCT_NO_RAC)
        assert r.score == 100


# =============================================================================
# Capability 5: Selling point
# =============================================================================

class TestSellingPoint:
    PRODUCT = {
        "selling_point": "ออกฤทธิ์เร็ว ป้องกันการต้านทาน ใช้ได้ทุกระยะ",
    }

    def test_half_match(self):
        answer = "ออกฤทธิ์เร็วและใช้ได้ทุกระยะ"
        r = score_selling_point(answer, self.PRODUCT)
        assert r.score == 100  # 2/3 tokens ≥ 50%

    def test_one_token(self):
        answer = "ออกฤทธิ์เร็ว"
        r = score_selling_point(answer, self.PRODUCT)
        # 1/3 = 33% → between 25-50% threshold → 70
        assert r.score in (70, 40)

    def test_no_match(self):
        answer = "ใช้ได้ดี"
        r = score_selling_point(answer, self.PRODUCT)
        assert r.score in (0, 40)


# =============================================================================
# Capability 6: Comparison
# =============================================================================

class TestComparison:
    PRODUCT_A = {
        "product_name": "ไบเตอร์",
        "product_category": "Insecticide",
        "active_ingredient": "BIFENTHRIN 5% + IMIDACLOPRID 25% SC",
        "common_name_th": "ไบเฟนทริน + อิมิดาคลอพริด",
        "mechanism_of_action": "",
    }
    PRODUCT_B = {
        "product_name": "คอนทาฟ",
        "product_category": "Fungicide",
        "active_ingredient": "HEXACONAZOLE 5% SC",
        "common_name_th": "เฮกซาโคนาโซล",
        "mechanism_of_action": "",
    }

    def test_perfect_comparison(self):
        answer = "ไบเตอร์เป็น Insecticide ส่วนคอนทาฟเป็น Fungicide"
        r = score_comparison(answer, self.PRODUCT_A, self.PRODUCT_B)
        assert r.score == 100

    def test_only_names_no_diff(self):
        answer = "ไบเตอร์และคอนทาฟ"
        r = score_comparison(answer, self.PRODUCT_A, self.PRODUCT_B)
        assert r.score == 50  # both names but no differentiator

    def test_only_one_name(self):
        answer = "ไบเตอร์เป็น Insecticide"
        r = score_comparison(answer, self.PRODUCT_A, self.PRODUCT_B)
        # one name (25) + category differentiator (50) = 75
        assert r.score == 75


# =============================================================================
# Question builder
# =============================================================================

class TestTokenizeTargets:
    """Cover DB's 'pestในcrop' compact format (no ' - ' separator)"""

    def test_compact_pest_in_crop_format(self):
        from tests.capability_scorer import _tokenize_targets
        text = "เพลี้ยไฟในส้ม,หนอนชอนใบในถั่วฝักยาว,เพลี้ยไฟในมะเขือ"
        toks = _tokenize_targets(text, min_len=3)
        # Should produce both "เพลี้ยไฟในส้ม" AND "เพลี้ยไฟ" (crop-less aliases)
        assert "เพลี้ยไฟ" in toks
        assert "หนอนชอนใบ" in toks

    def test_dash_separator_format(self):
        from tests.capability_scorer import _tokenize_targets
        text = "ทุเรียน - เพลี้ยไฟ เพลี้ยจักจั่น"
        toks = _tokenize_targets(text, min_len=3)
        assert "เพลี้ยไฟ" in toks
        assert "เพลี้ยจักจั่น" in toks
        # crop name should not be a token
        assert "ทุเรียน" not in toks

    def test_newline_separator(self):
        from tests.capability_scorer import _tokenize_targets
        text = "เพลี้ยไฟในทุเรียน\nเพลี้ยแป้งในลำไย"
        toks = _tokenize_targets(text, min_len=3)
        assert "เพลี้ยไฟ" in toks
        assert "เพลี้ยแป้ง" in toks


class TestMoANarrative:
    """PGR products have narrative rac (not numeric codes)"""

    PRODUCT = {
        "chemical_group_rac": "ควบคุมการเจริญเติบโตของพืช",
    }

    def test_narrative_with_keywords(self):
        from tests.capability_scorer import score_moa
        answer = "พรีดิคท์ 10% เป็นสารควบคุมการเจริญเติบโตของพืช (PGR) ยับยั้งการแตกใบอ่อน"
        r = score_moa(answer, self.PRODUCT)
        assert r.score == 100

    def test_narrative_partial(self):
        from tests.capability_scorer import score_moa
        answer = "เป็นสารควบคุม"
        r = score_moa(answer, self.PRODUCT)
        assert r.score == 60

    def test_narrative_no_match(self):
        from tests.capability_scorer import score_moa
        answer = "ใช้กับทุเรียนได้"
        r = score_moa(answer, self.PRODUCT)
        assert r.score == 0


class TestComparisonBothIngredients:
    """New: if answer mentions both Thai ingredient names → differentiator found"""

    def test_both_thai_ingredients_differentiates(self):
        from tests.capability_scorer import score_comparison
        a = {
            "product_name": "แจ๊ส 50 อีซี", "product_category": "Insecticide",
            "common_name_th": "ฟีโนบูคาร์บ", "active_ingredient": "FENOBUCARB 50% EC",
            "mechanism_of_action": "", "usage_rate": "10-20 มล.",
        }
        b = {
            "product_name": "โบรีส", "product_category": "Insecticide",
            "common_name_th": "ไพริดาเบน", "active_ingredient": "PYRIDABEN 20% WP",
            "mechanism_of_action": "", "usage_rate": "30 กรัม",
        }
        answer = "แจ๊ส 50 อีซี (ฟีโนบูคาร์บ 50%) และ โบรีส (ไพริดาเบน 20%) ต่างกัน"
        r = score_comparison(answer, a, b)
        assert r.score == 100


class TestQuestionBuilder:
    def test_builds_5_questions_without_partner(self):
        q = build_questions({"product_name": "ไบเตอร์"})
        assert len(q) == 5
        assert "ไบเตอร์" in q[1]

    def test_builds_6_with_partner(self):
        q = build_questions(
            {"product_name": "ไบเตอร์"},
            comparison_partner={"product_name": "คอนทาฟ"},
        )
        assert len(q) == 6
        assert "คอนทาฟ" in q[6]
        assert "ไบเตอร์" in q[6]
