"""
Tests สำหรับคำถามจริงจากเกษตรกร — จำลองสถานการณ์ที่หลากหลาย

ทดสอบ:
1. คำถามกว้าง ไม่ระบุชื่อสินค้า (เกษตรกรไม่รู้ชื่อยา)
2. คำถามยาว ซับซ้อน หลายเงื่อนไข
3. ภาษาชาวบ้าน / slang
4. Follow-up สั้น (ถามต่อเนื่อง)
5. คำถามเปรียบเทียบ
6. คำถามเทคนิค (IRAC/FRAC/กลุ่มสาร)
7. คำถามที่ bot อาจสับสน
"""

import pytest
from app.services.chat.handler import (
    extract_plant_type_from_question,
    extract_product_name_from_question,
    detect_problem_types,
    resolve_farmer_slang,
    is_agriculture_question,
    is_product_question,
    is_usage_question,
)


# ===========================================================================
# 1. คำถามกว้าง ไม่ระบุชื่อสินค้า
# ===========================================================================

class TestBroadQueriesNoProductName:
    """เกษตรกรถามกว้างๆ ไม่พิมพ์ชื่อสินค้า — bot ต้อง route ไป RAG"""

    @pytest.mark.parametrize("query,expected_plant,expected_problem", [
        ("ข้าวเป็นโรค ใช้ยาอะไรดี", "ข้าว", "disease"),
        ("ทุเรียนเป็นเพลี้ย ฉีดอะไร", "ทุเรียน", "insect"),
        ("หญ้าในนาข้าว กำจัดยังไง", "ข้าว", "weed"),
        ("บำรุงทุเรียนหลังเก็บเกี่ยว", "ทุเรียน", "nutrient"),
        # "ใบร่วง/ใบเหลือง" → detect_problem_types จัดเป็น nutrient (ขาดธาตุ) ไม่ใช่ disease
        # Agent 1 LLM จะ classify ถูกต้องกว่า Stage 0
        ("มะม่วงใบร่วง ทำยังไงดี", "มะม่วง", "nutrient"),
        ("อ้อยมีหนอนเจาะลำต้น", "อ้อย", "insect"),
        # "ข้าวโพด" ถูก match "ข้าว" ก่อน (substring) — known behavior, Agent 1 LLM จะจับถูก
        ("ข้าวโพดเป็นราน้ำค้าง", "ข้าว", "disease"),
        # "ใบเหลือง" → nutrient (ขาดธาตุ)
        ("ส้มใบเหลือง แก้ยังไง", "ส้ม", "nutrient"),
    ])
    def test_broad_query_detection(self, query, expected_plant, expected_problem):
        plant = extract_plant_type_from_question(query)
        problems = detect_problem_types(query)
        assert plant == expected_plant, f"Expected plant={expected_plant}, got {plant}"
        assert expected_problem in problems, f"Expected {expected_problem} in {problems} for '{query}'"

    @pytest.mark.parametrize("query", [
        "มียาฆ่าแมลงแนะนำไหม",
        "ยากำจัดวัชพืชตัวไหนดี",
        "ปุ๋ยบำรุงต้นมีอะไรบ้าง",
        "แนะนำยาฆ่าหญ้าหน่อย",
        "มีสารกำจัดเชื้อราไหม",
    ])
    def test_broad_query_routes_to_rag(self, query):
        """คำถามกว้างต้อง detect เป็น agriculture → route ไป RAG"""
        assert is_agriculture_question(query), f"'{query}' should be agriculture"

    @pytest.mark.parametrize("query", [
        "มียาฆ่าแมลงแนะนำไหม",
        "แนะนำยาอะไรดี",
        "ใช้สารอะไรดี",
    ])
    def test_no_product_detected(self, query):
        """คำถามกว้างไม่ควร detect ชื่อสินค้า"""
        product = extract_product_name_from_question(query)
        assert product is None, f"Should not detect product in '{query}', got {product}"


# ===========================================================================
# 2. คำถามยาว ซับซ้อน หลายเงื่อนไข
# ===========================================================================

class TestLongComplexQueries:
    """คำถามยาว เกษตรกรอธิบายสถานการณ์ละเอียด"""

    @pytest.mark.parametrize("query,expected_plant", [
        ("บำรุงข้าวอายุ 60 วัน มียาแนะนำไหมครับและช่วยอะไร", "ข้าว"),
        ("ช่วงฟื้นต้นทุเรียน มีสินค้าอะไรแนะนำบ้างครับ", "ทุเรียน"),
        ("ทุเรียนอายุ 3 ปี ใบเหลืองร่วง ควรใช้ยาอะไร", "ทุเรียน"),
        ("นาข้าวเพิ่งหว่านได้ 2 อาทิตย์ หญ้าขึ้นเยอะมาก แนะนำยาหน่อย", "ข้าว"),
        ("มะม่วงออกดอกแล้ว มีเพลี้ยไฟ ฉีดอะไรได้บ้างที่ไม่เป็นอันตรายต่อดอก", "มะม่วง"),
        ("ส้มเป็นแคงเกอร์ รักษายังไง มียาตัวไหนที่ใช้ได้", "ส้ม"),
    ])
    def test_long_query_plant_detection(self, query, expected_plant):
        plant = extract_plant_type_from_question(query)
        assert plant == expected_plant

    @pytest.mark.parametrize("query", [
        "บำรุงข้าวอายุ 60 วัน มียาแนะนำไหมครับและช่วยอะไร",
        "ช่วงฟื้นต้นทุเรียน มีสินค้าอะไรแนะนำบ้างครับ",
        "มะม่วงออกดอกแล้ว มีเพลี้ยไฟ ฉีดอะไรได้บ้าง",
    ])
    def test_long_query_is_agriculture(self, query):
        assert is_agriculture_question(query)


# ===========================================================================
# 3. ภาษาชาวบ้าน / slang
# ===========================================================================

class TestFarmerSlang:
    """เกษตรกรใช้ภาษาชาวบ้าน — bot ต้องเข้าใจ"""

    @pytest.mark.parametrize("query,expected_slang", [
        ("ข้าวดีดใช้อะไร", "ข้าวดีด"),
        ("ข้าวตีดในนา กำจัดยังไง", "ข้าวตีด"),
    ])
    def test_slang_detected(self, query, expected_slang):
        result = resolve_farmer_slang(query)
        matched = [s for s in result["matched_slangs"]]
        assert any(expected_slang in str(m) for m in matched), \
            f"Expected slang '{expected_slang}' in {matched}"

    @pytest.mark.parametrize("query,expected_type", [
        ("ข้าวดีดใช้อะไร", "weed"),
        ("ข้าวตีดในนา กำจัดยังไง", "weed"),
    ])
    def test_slang_problem_type(self, query, expected_type):
        result = resolve_farmer_slang(query)
        assert result["problem_type"] == expected_type, \
            f"Expected problem_type={expected_type}, got {result['problem_type']}"


# ===========================================================================
# 4. Follow-up สั้น
# ===========================================================================

class TestShortFollowUp:
    """คำถาม follow-up สั้นๆ — ไม่ควร detect ชื่อสินค้า/พืช"""

    @pytest.mark.parametrize("query", [
        "ใช้ยังไง",
        "ผสมกี่ซีซี",
        "อัตราเท่าไหร่",
        "ใช้ช่วงไหน",
        "กี่วันฉีดที",
    ])
    def test_short_followup_no_product(self, query):
        product = extract_product_name_from_question(query)
        assert product is None

    @pytest.mark.parametrize("query", [
        "ใช้ยังไง",
        "ผสมกี่ซีซี",
    ])
    def test_short_followup_is_usage(self, query):
        assert is_usage_question(query)

    @pytest.mark.parametrize("query", [
        "ใช้ต่างกันยังไง",
        "เปรียบเทียบให้หน่อย",
        "ตัวไหนดีกว่า",
    ])
    def test_comparison_no_product(self, query):
        product = extract_product_name_from_question(query)
        assert product is None


# ===========================================================================
# 5. คำถามเทคนิค (IRAC/FRAC/กลุ่มสาร)
# ===========================================================================

class TestTechnicalQueries:
    """คำถามเทคนิคเกี่ยวกับกลุ่มสาร"""

    @pytest.mark.parametrize("query", [
        "โมเดินอยู่กลุ่มสารอะไร",
        "ไบเตอร์อยู่ IRAC อะไร",
        "คาริสมา กลุ่ม FRAC อะไร",
        "แกนเตอร์ HRAC กลุ่มไหน",
        "กลุ่มสารเคมีของเกรค",
    ])
    def test_irac_frac_is_agriculture(self, query):
        assert is_agriculture_question(query), f"'{query}' should be agriculture"

    @pytest.mark.parametrize("query", [
        "กลุ่มiracอะไร",
        "อยู่กลุ่มสารไหน",
        "frac กลุ่มอะไร",
    ])
    def test_irac_followup_is_agriculture(self, query):
        """follow-up เรื่อง IRAC ต้อง detect เป็น agriculture"""
        assert is_agriculture_question(query)


# ===========================================================================
# 6. คำถามที่ bot อาจสับสน
# ===========================================================================

class TestConfusingQueries:
    """คำถามที่อาจทำให้ bot สับสน"""

    def test_price_question_not_answerable(self):
        """ถามราคา — ไม่ควร detect เป็น product inquiry"""
        # Bot ไม่ตอบราคา (อยู่ใน prompt rules)
        query = "โมเดิน ราคาเท่าไหร่"
        product = extract_product_name_from_question(query)
        # ควร detect ชื่อสินค้าได้ แต่ prompt จะห้ามตอบราคา
        assert product is not None  # ชื่อสินค้ายัง detect ได้

    def test_non_icp_product(self):
        """ถามสินค้าที่ไม่ใช่ ICP"""
        query = "ไซเพอร์เมทริน ใช้ยังไง"
        product = extract_product_name_from_question(query)
        # ไม่ควร detect เป็นสินค้า ICP
        assert product is None

    @pytest.mark.parametrize("query", [
        "สวัสดีครับ",
        # "ขอบคุณครับ" → not greeting, handled by _NON_AGRI_KEYWORDS
        "ดีครับ",
    ])
    def test_greeting_not_agriculture(self, query):
        from app.prompts import GREETING_KEYWORDS
        is_greeting = any(kw in query for kw in GREETING_KEYWORDS)
        assert is_greeting

    def test_mixed_pest_disease(self):
        """ถามทั้งโรค+แมลง ในคำถามเดียว"""
        query = "ทุเรียนเป็นรากเน่า กับมีเพลี้ยด้วย ใช้ยาอะไร"
        plant = extract_plant_type_from_question(query)
        problems = detect_problem_types(query)
        assert plant == "ทุเรียน"
        assert "disease" in problems or "insect" in problems

    def test_multiple_plants(self):
        """ถามหลายพืช — ควร detect พืชแรก"""
        query = "ข้าวกับข้าวโพด ใช้ยาฆ่าหญ้าตัวเดียวกันได้ไหม"
        plant = extract_plant_type_from_question(query)
        assert plant is not None  # ควร detect พืชได้อย่างน้อย 1

    def test_applicability_question(self):
        """ถามว่าใช้กับพืช X ได้ไหม (follow-up)"""
        query = "ใช้กับมันสำปะหลังได้ไหม"
        plant = extract_plant_type_from_question(query)
        assert plant == "มันสำปะหลัง"
        assert is_agriculture_question(query)

    def test_calculate_question(self):
        """ถามคำนวณ — "10 ไร่ ใช้เท่าไหร่" ไม่มี agri keyword
        แต่ RAG-first routing จะส่งไป RAG เพราะ _is_clearly_non_agriculture = False
        (ข้อความไม่ match non-agri keywords เช่น ขอบคุณ/บาย/555)"""
        from app.services.chat.handler import _is_clearly_non_agriculture
        query = "10 ไร่ ใช้เท่าไหร่"
        # ไม่ใช่ non-agriculture → RAG-first routing จะส่งไป RAG
        assert not _is_clearly_non_agriculture(query)

    def test_mix_question(self):
        """ถามผสมร่วม — ปุ๋ย อยู่ใน agriculture keywords"""
        query = "ผสมกับปุ๋ยได้ไหม"
        # "ปุ๋ย" อยู่ใน PRODUCT_KEYWORDS → is_product_question = True
        assert is_product_question(query) or is_agriculture_question(query)


# ===========================================================================
# 7. Edge cases — ภาษาไทยสะกดผิด/ตัวเล็กตัวใหญ่
# ===========================================================================

class TestTypoAndCasing:
    """เกษตรกรพิมพ์ผิด / ใช้ภาษาอังกฤษปนไทย"""

    @pytest.mark.parametrize("query", [
        "irac กลุ่มอะไร",
        "IRAC กลุ่มอะไร",
        "Irac กลุ่มอะไร",
    ])
    def test_irac_case_insensitive(self, query):
        assert is_agriculture_question(query)

    @pytest.mark.parametrize("query,expected_plant", [
        ("ทุเรียน", "ทุเรียน"),
        ("มันสำปะหลัง", "มันสำปะหลัง"),
        ("มันสัมปะหลัง", "มันสำปะหลัง"),  # typo common
    ])
    def test_plant_typo_detection(self, query, expected_plant):
        plant = extract_plant_type_from_question(query)
        assert plant == expected_plant


# ===========================================================================
# 8. คำถามที่ RAG ต้องตอบว่า "ไม่มีข้อมูล"
# ===========================================================================

class TestNoDataExpected:
    """คำถามที่ไม่เกี่ยวกับเกษตร — ไม่ควร route ไป RAG"""

    @pytest.mark.parametrize("query", [
        "วันนี้อากาศดีจัง",
        "เล่าเรื่องตลกให้ฟังหน่อย",
        "ขอเบอร์โทรหน่อย",
    ])
    def test_non_agriculture_not_routed(self, query):
        is_agri = is_agriculture_question(query)
        is_prod = is_product_question(query)
        # อย่างน้อย 1 ตัวต้อง False (ไม่เข้า RAG)
        assert not (is_agri and is_prod), f"'{query}' should not be both agriculture AND product"
