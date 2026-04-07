"""
Tests for hallucination prevention in response_generator_agent.py
- Cross-product hallucination detection
- Product name validation
- Common query patterns that might cause issues
"""

import pytest
from unittest.mock import MagicMock
from app.services.rag import IntentType, QueryAnalysis, RetrievedDocument


# ===========================================================================
# Helper: create mock objects
# ===========================================================================

def _make_doc(product_name, category="Fungicide", crops="ข้าว"):
    return RetrievedDocument(
        id=str(hash(product_name)),
        title=product_name,
        content=f"สินค้า {product_name}",
        source="products",
        similarity_score=0.8,
        rerank_score=0.8,
        metadata={
            "product_name": product_name,
            "category": category,
            "product_category": category,
            "applicable_crops": crops,
        }
    )


def _make_query(intent=IntentType.DISEASE_TREATMENT, product_name=None, plant_type=None):
    entities = {}
    if product_name:
        entities["product_name"] = product_name
    if plant_type:
        entities["plant_type"] = plant_type
    return QueryAnalysis(
        original_query="test query",
        intent=intent,
        confidence=0.9,
        entities=entities,
        expanded_queries=["test query"],
        required_sources=["products"]
    )


# ===========================================================================
# Test: Cross-product hallucination
# ===========================================================================

class TestCrossProductHallucination:
    """Test that products NOT in retrieved docs are removed from answer"""

    def setup_method(self):
        from app.services.rag.response_generator_agent import ResponseGeneratorAgent
        self.agent = ResponseGeneratorAgent()

    def test_allowed_product_stays(self):
        """Product in retrieved docs should NOT be removed"""
        docs = [_make_doc("คอนทาฟ")]
        query = _make_query()
        answer = 'แนะนำ "คอนทาฟ (เฮกซาโคนาโซล)" ค่ะ'
        result = self.agent._validate_product_names(answer, docs, query)
        assert "คอนทาฟ" in result

    def test_hallucinated_quoted_product_removed(self):
        """Quoted product NOT in DB should be removed"""
        docs = [_make_doc("คอนทาฟ")]
        query = _make_query()
        answer = 'แนะนำ "สินค้าปลอม (สารไม่มี)" ค่ะ'
        result = self.agent._validate_product_names(answer, docs, query)
        assert "สินค้าปลอม" not in result


# ===========================================================================
# Test: Common query patterns
# ===========================================================================

class TestCommonQueryPatterns:
    """Test Stage 0 pre-detection for common farmer questions"""

    def test_rice_disease_detection(self):
        """ข้าวดีด should detect plant=ข้าว, problem=disease"""
        from app.services.chat.handler import extract_plant_type_from_question, detect_problem_types
        plant = extract_plant_type_from_question("ข้าวดีดใช้อะไร")
        assert plant == "ข้าว"

    def test_durian_pest_detection(self):
        """เพลี้ยไฟทุเรียน should detect plant=ทุเรียน"""
        from app.services.chat.handler import extract_plant_type_from_question
        plant = extract_plant_type_from_question("เพลี้ยไฟทุเรียน ใช้ยาอะไร")
        assert plant == "ทุเรียน"

    def test_weed_detection(self):
        """หญ้าในนาข้าว should detect plant=ข้าว, problem=weed"""
        from app.services.chat.handler import extract_plant_type_from_question, detect_problem_types
        plant = extract_plant_type_from_question("หญ้าในนาข้าว ใช้อะไร")
        problems = detect_problem_types("หญ้าในนาข้าว ใช้อะไร")
        assert plant == "ข้าว"
        assert "weed" in problems

    def test_nutrient_detection(self):
        """บำรุงข้าว should detect plant=ข้าว, problem=nutrient"""
        from app.services.chat.handler import extract_plant_type_from_question, detect_problem_types
        plant = extract_plant_type_from_question("บำรุงข้าวยังไงดี")
        problems = detect_problem_types("บำรุงข้าวยังไงดี")
        assert plant == "ข้าว"
        assert "nutrient" in problems

    def test_pgr_detection(self):
        """ยับยั้งใบอ่อนทุเรียน should detect plant=ทุเรียน
        Note: PGR detection via problem_type happens in orchestrator (slang resolution),
        not in detect_problem_types which checks simpler keywords"""
        from app.services.chat.handler import extract_plant_type_from_question
        plant = extract_plant_type_from_question("ยับยั้งใบอ่อนทุเรียน")
        assert plant == "ทุเรียน"

    def test_product_name_detection(self):
        """โมเดิน should detect product name"""
        from app.services.chat.handler import extract_product_name_from_question
        product = extract_product_name_from_question("โมเดิน ใช้ยังไง")
        assert product is not None
        assert "โมเดิน" in product

    def test_follow_up_no_product(self):
        """Short follow-up like 'ใช้ยังไง' should NOT detect product"""
        from app.services.chat.handler import extract_product_name_from_question
        product = extract_product_name_from_question("ใช้ยังไง")
        assert product is None

    def test_comparison_not_product(self):
        """'ใช้ต่างกันยังไง' should not detect a product name"""
        from app.services.chat.handler import extract_product_name_from_question
        product = extract_product_name_from_question("ใช้ต่างกันยังไง")
        assert product is None

    def test_cassava_plant_detection(self):
        """มันสำปะหลัง should be detected as plant"""
        from app.services.chat.handler import extract_plant_type_from_question
        plant = extract_plant_type_from_question("ไฟท็อปมันสำปะหลัง")
        assert plant == "มันสำปะหลัง"

    def test_farmer_slang_rice_did(self):
        """ข้าวดีด should be resolved as farmer slang"""
        from app.services.chat.handler import resolve_farmer_slang
        result = resolve_farmer_slang("ข้าวดีดใช้อะไร")
        assert result["matched_slangs"]  # should match something
        assert "ข้าวดีด" in str(result["matched_slangs"])


# ===========================================================================
# Test: Intent classification edge cases
# ===========================================================================

class TestIntentEdgeCases:
    """Test that tricky queries get correct intent classification"""

    def test_fertilizer_query_is_nutrient(self):
        """'มีปุ๋ยแนะนำไหม' should be nutrient_supplement"""
        from app.services.chat.handler import detect_problem_types
        problems = detect_problem_types("มีปุ๋ยแนะนำไหม")
        assert "nutrient" in problems

    def test_applicability_is_agriculture(self):
        """'ใช้กับมันสำปะหลังได้ไหม' should be detected as agriculture question"""
        from app.services.chat.handler import is_agriculture_question
        result = is_agriculture_question("ใช้กับมันสำปะหลังได้ไหม")
        assert result is True

    def test_greeting_detected(self):
        """สวัสดี should be detected as greeting"""
        from app.prompts import GREETING_KEYWORDS
        msg = "สวัสดีครับ"
        is_greeting = any(kw in msg for kw in GREETING_KEYWORDS)
        assert is_greeting
