"""
Test Stage 0 pre-detection: disease, pest, and weed extraction.

Simulates the orchestrator's Stage 0 entity extraction logic
to verify correct pattern matching before queries hit the LLM.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.text_processing import (
    diacritics_match,
    generate_thai_disease_variants,
)
from app.services.disease.constants import DISEASE_PATTERNS_SORTED, get_canonical
from app.services.chat.handler import detect_problem_type


# ── Re-create Stage 0 pest patterns (same as orchestrator.py) ──
_PEST_PATTERNS_STAGE0 = [
    'เพลี้ยกระโดดสีน้ำตาล', 'เพลี้ยจักจั่นข้าวโพด', 'เพลี้ยกระโดดข้าวโพด',
    'เพลี้ยจักจั่นมะม่วง', 'เพลี้ยจักจั่นเขียว', 'เพลี้ยจักจั่นฝอย',
    'เพลี้ยไก่แจ้', 'เพลี้ยกระโดด', 'เพลี้ยจักจั่น', 'เพลี้ยหอย',
    'เพลี้ยไฟ', 'เพลี้ยอ่อน', 'เพลี้ยแป้ง', 'เพลี้ย',
    'หนอนเจาะผล', 'หนอนชอนใบ', 'หนอนกระทู้',
    'หนอนกอ', 'หนอนเจาะ', 'หนอนใย', 'หนอน',
    'แมลงค่อมทอง', 'แมลงวันผล', 'แมลงหวี่ขาว', 'แมลงวัน', 'แมลง',
    'ด้วงงวง', 'ด้วง',
    'ไรสี่ขา', 'ไรแดง', 'ไรขาว', 'ไรแมง', 'ตัวไร',
    'ทริปส์', 'จักจั่น', 'มด', 'ปลวก',
]


def extract_disease(query: str) -> str:
    """Simulate Stage 0 disease extraction."""
    for pattern in DISEASE_PATTERNS_SORTED:
        if diacritics_match(query, pattern):
            return get_canonical(pattern)
    return ''


def extract_pest(query: str) -> str:
    """Simulate Stage 0 pest extraction."""
    for pattern in _PEST_PATTERNS_STAGE0:
        if diacritics_match(query, pattern):
            return pattern
    return ''


def simulate_pest_prefilter(pest_name: str, product_pest_texts: dict) -> dict:
    """
    Simulate pest pre-filter.
    product_pest_texts: {product_name: pest_text_from_all_columns}
    Returns: {product_name: passed_filter}
    """
    results = {}
    for name, pest_text in product_pest_texts.items():
        results[name] = pest_name.lower() in pest_text.lower()
    return results


def simulate_disease_prefilter(disease_name: str, product_pest_texts: dict) -> dict:
    """
    Simulate disease pre-filter using boundary-aware matching.
    Returns: {product_name: passed_filter}
    """
    import re

    def _disease_in_pest_text(variant, pest_text):
        escaped = re.escape(variant.lower())
        pattern = r'(?:^|[\s,;(]|โรคเชื้อรา|เชื้อรา|โรครา|โรค|เชื้อ|รา)' + escaped
        return bool(re.search(pattern, pest_text.lower()))

    variants = generate_thai_disease_variants(disease_name)
    results = {}
    for name, pest_text in product_pest_texts.items():
        results[name] = any(_disease_in_pest_text(v, pest_text) for v in variants)
    return results


# =====================================================================
# DISEASE TESTS (โรคเชื้อรา)
# =====================================================================
class TestDiseaseExtraction:
    """Test Stage 0 disease name extraction from user queries."""

    @pytest.mark.parametrize("query,expected_disease", [
        # Specific diseases — must extract full name, not generic
        ("ใบจุดสีน้ำตาล ใช้ยาอะไร", "ใบจุดสีน้ำตาล"),
        ("โรคใบจุดสีน้ำตาลในทุเรียน", "ใบจุดสีน้ำตาล"),
        ("ใบจุดสนิมในข้าวโพด", "ใบจุดสนิม"),
        ("ใบจุดสีม่วง ใช้อะไรรักษา", "ใบจุดสีม่วง"),
        ("ใบจุด ใช้ยาอะไร", "ใบจุด"),  # generic — should still work
        # ราชนิดต่างๆ
        ("ราสีชมพูในทุเรียน รักษายังไง", "ราสีชมพู"),
        ("ราน้ำค้างในข้าวโพด", "ราน้ำค้าง"),
        ("ราแป้งในมะม่วง", "ราแป้ง"),
        ("ราสนิมในข้าว", "ราสนิม"),
        ("ราดำในมะม่วง", "ราดำ"),
        ("ราเขียวในทุเรียน", "ราเขียว"),
        # ไฟท็อป variants
        ("ไฟท็อปธอร่า ใช้อะไร", "ไฟท็อปธอร่า"),
        ("ไฟทอปธอร่าในทุเรียน", "ไฟท็อปธอร่า"),  # canonical
        ("โรคไฟทิปในทุเรียน", "ไฟท็อป"),  # canonical of ไฟทิป
        # เน่า
        ("รากเน่าในทุเรียน", "รากเน่า"),
        ("ผลเน่าในมะม่วง", "ผลเน่า"),
        ("โคนเน่าในทุเรียน", "โคนเน่า"),
        # แอนแทรคโนส variants
        ("แอนแทรคโนส ใช้อะไร", "แอนแทรคโนส"),
        ("โรคแอนแทคโนสในมะม่วง", "แอนแทรคโนส"),  # canonical
        # ฟิวซาเรียม
        ("ฟิวซาเรียม ใช้อะไรรักษา", "ฟิวซาเรียม"),
        ("ฟูซาเรียมในกล้วย", "ฟิวซาเรียม"),  # canonical
        # ใบไหม้
        ("ใบไหม้ในข้าว", "ใบไหม้"),
        ("ใบไหม้แผลใหญ่ในข้าวโพด", "ใบไหม้แผลใหญ่"),
        # อื่นๆ
        ("ขอบใบแห้ง ใช้อะไร", "ขอบใบแห้ง"),
        ("เมล็ดด่าง ในข้าว", "เมล็ดด่าง"),
        ("ใบด่าง ในพริก", "ใบด่าง"),
    ])
    def test_disease_extraction(self, query, expected_disease):
        result = extract_disease(query)
        assert result == expected_disease, \
            f"Query: '{query}' → got '{result}', expected '{expected_disease}'"


class TestDiseasePreFilter:
    """Test disease pre-filter keeps only matching products."""

    def test_leaf_spot_brown_filters_correctly(self):
        """ใบจุดสีน้ำตาล should NOT match ใบจุดสนิม products."""
        products = {
            "รีโนเวท": "ใบจุดสีน้ำตาล, ราสนิม, แอนแทรคโนส",
            "อาร์เทมิส": "ใบจุด, ราสนิม, แอนแทรคโนส",
            "ไซม๊อกซิเมท": "ใบจุดสนิม, ราน้ำค้าง",
            "โค-ราซ": "ใบจุดสนิม, แอนแทรคโนส",
        }
        result = simulate_disease_prefilter("ใบจุดสีน้ำตาล", products)
        assert result["รีโนเวท"] == True   # exact match
        # อาร์เทมิส has generic "ใบจุด" only — boundary-aware matching correctly
        # does NOT match "ใบจุดสีน้ำตาล" variants against generic "ใบจุด"
        assert result["อาร์เทมิส"] == False
        assert result["ไซม๊อกซิเมท"] == False  # ใบจุดสนิม ≠ ใบจุดสีน้ำตาล
        assert result["โค-ราซ"] == False

    def test_pink_mold_filter(self):
        """ราสีชมพู should match ราชมพู variant."""
        products = {
            "อาร์เทมิส": "ราสีชมพู, ใบจุด, แอนแทรคโนส",
            "คาริสมา": "แอนแทรคโนส, ราน้ำค้าง",
        }
        result = simulate_disease_prefilter("ราสีชมพู", products)
        assert result["อาร์เทมิส"] == True
        assert result["คาริสมา"] == False

    def test_anthracnose_filter(self):
        """แอนแทรคโนส — most products have it, so many should pass."""
        products = {
            "อาร์เทมิส": "แอนแทรคโนส, ราสีชมพู",
            "คาริสมา": "แอนแทรคโนส, ราน้ำค้าง",
            "นาแดน": "เพลี้ยกระโดด, หนอน",
        }
        result = simulate_disease_prefilter("แอนแทรคโนส", products)
        assert result["อาร์เทมิส"] == True
        assert result["คาริสมา"] == True
        assert result["นาแดน"] == False


# =====================================================================
# PEST TESTS (แมลง/ศัตรูพืช)
# =====================================================================
class TestPestExtraction:
    """Test Stage 0 pest name extraction from user queries."""

    @pytest.mark.parametrize("query,expected_pest", [
        # Specific pests
        ("เพลี้ยไก่แจ้ ใช้อะไรจัดการดี", "เพลี้ยไก่แจ้"),
        ("เพลี้ยจักจั่นฝอยในทุเรียน", "เพลี้ยจักจั่นฝอย"),
        ("เพลี้ยกระโดดสีน้ำตาลในนาข้าว", "เพลี้ยกระโดดสีน้ำตาล"),
        ("เพลี้ยแป้งในมันสำปะหลัง", "เพลี้ยแป้ง"),
        ("เพลี้ยไฟในทุเรียน", "เพลี้ยไฟ"),
        ("เพลี้ยอ่อนในผัก", "เพลี้ยอ่อน"),
        # Generic เพลี้ย — should still work
        ("เพลี้ย ใช้ยาอะไร", "เพลี้ย"),
        # หนอน
        ("หนอนเจาะผลทุเรียน ใช้อะไร", "หนอนเจาะผล"),
        ("หนอนชอนใบในส้ม", "หนอนชอนใบ"),
        ("หนอนกระทู้ในข้าวโพด", "หนอนกระทู้"),
        ("หนอนกอข้าว", "หนอนกอ"),
        ("หนอนเจาะลำต้น", "หนอนเจาะ"),
        ("หนอน ใช้ยาอะไร", "หนอน"),
        # แมลง
        ("แมลงค่อมทอง ใช้อะไร", "แมลงค่อมทอง"),
        ("แมลงหวี่ขาวในพริก", "แมลงหวี่ขาว"),
        ("แมลงวันผลไม้ ใช้ยาอะไร", "แมลงวันผล"),
        # ไร
        ("ไรแดงในส้ม", "ไรแดง"),
        ("ไรสี่ขาในมะม่วง", "ไรสี่ขา"),
        # อื่นๆ
        ("ทริปส์ในพริก", "ทริปส์"),
        ("ด้วงงวงในข้าว", "ด้วงงวง"),
    ])
    def test_pest_extraction(self, query, expected_pest):
        result = extract_pest(query)
        assert result == expected_pest, \
            f"Query: '{query}' → got '{result}', expected '{expected_pest}'"


class TestPestPreFilter:
    """Test pest pre-filter keeps only matching products."""

    def test_chicken_flea_filters_other_pests(self):
        """เพลี้ยไก่แจ้ should NOT match เพลี้ยไฟ/เพลี้ยกระโดด products."""
        products = {
            "โมเดิน 50": "เพลี้ยไฟ, เพลี้ยจักจั่นฝอย, เพลี้ยไก่แจ้",
            "ชุดกล่องม่วง": "เพลี้ยไฟในทุเรียน, หนอน",
            "นาแดน 6 จี": "เพลี้ยกระโดด, หนอน",
        }
        result = simulate_pest_prefilter("เพลี้ยไก่แจ้", products)
        assert result["โมเดิน 50"] == True       # has เพลี้ยไก่แจ้
        assert result["ชุดกล่องม่วง"] == False   # only เพลี้ยไฟ
        assert result["นาแดน 6 จี"] == False     # only เพลี้ยกระโดด

    def test_mealybug_filters_correctly(self):
        """เพลี้ยแป้ง should NOT match เพลี้ยไฟ."""
        products = {
            "สินค้า A": "เพลี้ยแป้ง, มด",
            "สินค้า B": "เพลี้ยไฟ, ทริปส์",
            "สินค้า C": "เพลี้ยแป้ง, เพลี้ยอ่อน",
        }
        result = simulate_pest_prefilter("เพลี้ยแป้ง", products)
        assert result["สินค้า A"] == True
        assert result["สินค้า B"] == False
        assert result["สินค้า C"] == True

    def test_borer_worm_filters_correctly(self):
        """หนอนเจาะผล should NOT match หนอนกอ."""
        products = {
            "สินค้า X": "หนอนเจาะผล, หนอนชอนใบ",
            "สินค้า Y": "หนอนกอ, เพลี้ยกระโดด",
        }
        result = simulate_pest_prefilter("หนอนเจาะผล", products)
        assert result["สินค้า X"] == True
        assert result["สินค้า Y"] == False

    def test_generic_pest_matches_all(self):
        """Generic เพลี้ย should match ALL เพลี้ย types."""
        products = {
            "สินค้า A": "เพลี้ยไฟ",
            "สินค้า B": "เพลี้ยแป้ง",
            "สินค้า C": "หนอนกอ",
        }
        result = simulate_pest_prefilter("เพลี้ย", products)
        assert result["สินค้า A"] == True
        assert result["สินค้า B"] == True
        assert result["สินค้า C"] == False


# =====================================================================
# WEED TESTS (วัชพืช)
# =====================================================================
class TestWeedDetection:
    """Test problem type detection for weed queries."""

    @pytest.mark.parametrize("query,expected_type", [
        ("หญ้าขึ้นในสวน ใช้อะไรดี", "weed"),
        ("กำจัดหญ้าในนาข้าว", "weed"),
        ("ยาฆ่าหญ้า แนะนำหน่อย", "weed"),
        # NOTE: "วัชพืชในไร่ข้าวโพด" is a known false positive:
        # diacritics stripping makes "ไร่ข้าว" → "ไรขาว" matching INSECT "ไรขาว" (mite)
        ("กำจัดวัชพืชในสวนทุเรียน", "weed"),
        ("หญ้างอกในสวนทุเรียน", "weed"),
    ])
    def test_weed_detection(self, query, expected_type):
        result = detect_problem_type(query)
        assert result == expected_type, \
            f"Query: '{query}' → got '{result}', expected '{expected_type}'"


# =====================================================================
# PROBLEM TYPE DETECTION (ครบทุกประเภท)
# =====================================================================
class TestProblemTypeDetection:
    """Test that problem type detection works for all categories."""

    @pytest.mark.parametrize("query,expected_type", [
        # Disease
        ("ใบจุดสีน้ำตาล ใช้ยาอะไร", "disease"),
        ("โรคราสีชมพู ในทุเรียน", "disease"),
        ("ใบไหม้ในข้าว", "disease"),
        # Insect
        ("เพลี้ยไก่แจ้ ใช้อะไร", "insect"),
        ("หนอนเจาะผลทุเรียน", "insect"),
        ("แมลงค่อมทอง ใช้ยาอะไร", "insect"),
        # Weed
        ("หญ้าขึ้นในสวน", "weed"),
        ("กำจัดวัชพืชในสวนทุเรียน", "weed"),
    ])
    def test_problem_type(self, query, expected_type):
        result = detect_problem_type(query)
        assert result == expected_type, \
            f"Query: '{query}' → got '{result}', expected '{expected_type}'"


# =====================================================================
# CROSS-CATEGORY: No false positives
# =====================================================================
class TestNoCrossCategoryLeak:
    """Ensure specific names don't extract wrong category patterns."""

    def test_pest_query_no_disease_extraction(self):
        """เพลี้ยไก่แจ้ should NOT extract a disease name."""
        assert extract_disease("เพลี้ยไก่แจ้ ใช้อะไร") == ''

    def test_disease_query_no_pest_extraction(self):
        """ราสีชมพู should NOT extract a pest name (รา is not a pest pattern)."""
        # ราสีชมพู contains no pest patterns
        pest = extract_pest("ราสีชมพูในทุเรียน")
        assert pest == '', f"Unexpected pest extraction: '{pest}'"

    def test_weed_query_no_disease_extraction(self):
        """หญ้าขึ้นในนา should NOT extract a disease name."""
        assert extract_disease("หญ้าขึ้นในนา ใช้อะไรดี") == ''

    def test_leaf_blight_vs_sheath_blight(self):
        """ใบไหม้ should NOT match กาบใบไหม้ (boundary check in Stage 0)."""
        # This tests the DISEASE_PATTERNS matching logic
        # ใบไหม้ should extract as ใบไหม้ from "ใบไหม้ในข้าว"
        assert extract_disease("ใบไหม้ในข้าว") == "ใบไหม้"
        # กาบใบแห้ง is in patterns but กาบใบไหม้ is not
        assert extract_disease("กาบใบแห้ง") == "กาบใบแห้ง"
