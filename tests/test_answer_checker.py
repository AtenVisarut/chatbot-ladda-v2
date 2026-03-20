"""
Tests for Conditional Answer Checker (Agent 5)

Tests _should_check_answer() risk detection logic
and _check_answer_relevance() integration.
"""
import pytest
from unittest.mock import MagicMock
from app.services.rag import IntentType, QueryAnalysis
from app.services.rag.response_generator_agent import ResponseGeneratorAgent


def _make_query_analysis(intent, entities=None, query="test"):
    return QueryAnalysis(
        original_query=query,
        intent=intent,
        confidence=0.8,
        entities=entities or {},
        expanded_queries=[],
        required_sources=["products"],
    )


def _make_retrieval_result(docs=None, avg_sim=0.6):
    result = MagicMock()
    result.documents = docs or []
    result.avg_similarity = avg_sim
    return result


def _make_doc(category="Fungicide", product_name="TestProduct"):
    doc = MagicMock()
    doc.metadata = {
        "category": category,
        "product_category": category,
        "product_name": product_name,
    }
    return doc


@pytest.fixture
def agent():
    """Shared fixture: creates ResponseGeneratorAgent without __init__."""
    return ResponseGeneratorAgent.__new__(ResponseGeneratorAgent)


class TestShouldCheckAnswer:
    """Test risk detection: when should the checker be triggered?"""

    @pytest.fixture(autouse=True)
    def _setup(self, agent):
        self.agent = agent

    def test_skip_greeting(self):
        """Greeting should never trigger checker."""
        qa = _make_query_analysis(IntentType.GREETING)
        ret = _make_retrieval_result([_make_doc()])
        assert self.agent._should_check_answer(qa, ret) is False

    def test_skip_product_inquiry(self):
        """Specific product inquiry should skip checker."""
        qa = _make_query_analysis(IntentType.PRODUCT_INQUIRY)
        ret = _make_retrieval_result([_make_doc()])
        assert self.agent._should_check_answer(qa, ret) is False

    def test_skip_usage_instruction(self):
        """Usage instruction should skip checker."""
        qa = _make_query_analysis(IntentType.USAGE_INSTRUCTION)
        ret = _make_retrieval_result([_make_doc()])
        assert self.agent._should_check_answer(qa, ret) is False

    def test_skip_no_docs(self):
        """No documents = no check needed."""
        qa = _make_query_analysis(IntentType.DISEASE_TREATMENT)
        ret = _make_retrieval_result(docs=[])
        assert self.agent._should_check_answer(qa, ret) is False

    def test_trigger_category_mismatch(self):
        """Nutrient intent + Fungicide top doc → must trigger."""
        qa = _make_query_analysis(IntentType.NUTRIENT_SUPPLEMENT, query="บำรุงใบทุเรียน")
        ret = _make_retrieval_result([_make_doc("Fungicide")])
        assert self.agent._should_check_answer(qa, ret) is True

    def test_trigger_low_similarity(self):
        """Low avg similarity → must trigger."""
        qa = _make_query_analysis(IntentType.DISEASE_TREATMENT, query="โรคแปลกๆ")
        ret = _make_retrieval_result([_make_doc("Fungicide")], avg_sim=0.25)
        assert self.agent._should_check_answer(qa, ret) is True

    def test_trigger_problem_type_conflict(self):
        """Stage 0 says nutrient but Agent 1 says product_recommendation → must trigger."""
        qa = _make_query_analysis(
            IntentType.PRODUCT_RECOMMENDATION,
            entities={"problem_type": "nutrient"},
            query="บำรุงใบทุเรียน"
        )
        ret = _make_retrieval_result([_make_doc("Fungicide")])
        assert self.agent._should_check_answer(qa, ret) is True

    def test_pass_matching_category(self):
        """Disease intent + Fungicide top doc → no trigger needed."""
        qa = _make_query_analysis(IntentType.DISEASE_TREATMENT, query="โรคใบไหม้ข้าว")
        ret = _make_retrieval_result([_make_doc("Fungicide")])
        assert self.agent._should_check_answer(qa, ret) is False

    def test_pass_pest_with_insecticide(self):
        """Pest intent + Insecticide doc → no trigger."""
        qa = _make_query_analysis(IntentType.PEST_CONTROL, query="เพลี้ยในข้าว")
        ret = _make_retrieval_result([_make_doc("Insecticide")])
        assert self.agent._should_check_answer(qa, ret) is False

    def test_pass_weed_with_herbicide(self):
        """Weed intent + Herbicide doc → no trigger."""
        qa = _make_query_analysis(IntentType.WEED_CONTROL, query="หญ้าในสวน")
        ret = _make_retrieval_result([_make_doc("Herbicide")])
        assert self.agent._should_check_answer(qa, ret) is False

    def test_trigger_disease_intent_but_herbicide_doc(self):
        """Disease intent + Herbicide top doc → trigger."""
        qa = _make_query_analysis(IntentType.DISEASE_TREATMENT, query="ข้าวเป็นโรค")
        ret = _make_retrieval_result([_make_doc("Herbicide")])
        assert self.agent._should_check_answer(qa, ret) is True

    def test_trigger_pest_intent_but_fungicide_doc(self):
        """Pest intent + Fungicide top doc → trigger."""
        qa = _make_query_analysis(IntentType.PEST_CONTROL, query="เพลี้ยในมัน")
        ret = _make_retrieval_result([_make_doc("Fungicide")])
        assert self.agent._should_check_answer(qa, ret) is True


class TestHardQueries:
    """Test with realistic difficult query scenarios."""

    @pytest.fixture(autouse=True)
    def _setup(self, agent):
        self.agent = agent

    def test_nutrient_query_fungicide_answer(self):
        """บำรุงใบทุเรียน + Fungicide doc → MUST trigger checker."""
        qa = _make_query_analysis(
            IntentType.NUTRIENT_SUPPLEMENT,
            entities={"problem_type": "nutrient", "plant_type": "ทุเรียน"},
            query="บำรุงใบทุเรียน"
        )
        ret = _make_retrieval_result([_make_doc("Fungicide", "รีโนเวท")])
        assert self.agent._should_check_answer(qa, ret) is True

    def test_nutrient_query_biostimulant_answer(self):
        """บำรุงใบทุเรียน + Biostimulants doc → should NOT trigger."""
        qa = _make_query_analysis(
            IntentType.NUTRIENT_SUPPLEMENT,
            entities={"problem_type": "nutrient", "plant_type": "ทุเรียน"},
            query="บำรุงใบทุเรียน"
        )
        ret = _make_retrieval_result([_make_doc("Biostimulants", "ไบโอเฟอร์ทิล")])
        assert self.agent._should_check_answer(qa, ret) is False

    def test_misclassified_nutrient_as_recommendation(self):
        """LLM classified บำรุง as product_recommendation → trigger via problem_type conflict."""
        qa = _make_query_analysis(
            IntentType.PRODUCT_RECOMMENDATION,
            entities={"problem_type": "nutrient"},
            query="เร่งดอกมะม่วง"
        )
        ret = _make_retrieval_result([_make_doc("Insecticide", "แจ๊ส")])
        assert self.agent._should_check_answer(qa, ret) is True

    def test_compound_disease_pest_query(self):
        """ข้าวเป็นโรค มีเพลี้ยด้วย — disease intent + Fungicide = OK."""
        qa = _make_query_analysis(
            IntentType.DISEASE_TREATMENT,
            entities={"problem_type": "disease", "disease_name": "ใบไหม้"},
            query="ข้าวเป็นโรคใบไหม้ มีเพลี้ยด้วย"
        )
        ret = _make_retrieval_result([_make_doc("Fungicide", "โมเดิน")])
        assert self.agent._should_check_answer(qa, ret) is False


class TestVeryHardQueries:
    """คำถามยากมากที่เกษตรกรจริงถาม — edge cases, ambiguity, slang."""

    @pytest.fixture(autouse=True)
    def _setup(self, agent):
        self.agent = agent

    # =====================================================================
    # กลุ่ม 1: Ambiguous — คำถามกำกวม ตีความได้หลายทาง
    # =====================================================================
    def test_ambiguous_leaf_yellow_as_nutrient(self):
        """ใบเหลือง → อาจเป็น nutrient (ขาดธาตุ) หรือ disease
        ถ้า Stage 0 บอก nutrient แต่ LLM classify disease → trigger."""
        qa = _make_query_analysis(
            IntentType.DISEASE_TREATMENT,
            entities={"problem_type": "nutrient", "plant_type": "ทุเรียน"},
            query="ทุเรียนใบเหลือง ใช้อะไรดี"
        )
        ret = _make_retrieval_result([_make_doc("Fungicide", "รีโนเวท")])
        assert self.agent._should_check_answer(qa, ret) is True  # conflict: nutrient vs disease

    def test_ambiguous_leaf_yellow_correct_nutrient(self):
        """ใบเหลือง + nutrient intent + Biostimulant doc → OK, ไม่ trigger."""
        qa = _make_query_analysis(
            IntentType.NUTRIENT_SUPPLEMENT,
            entities={"problem_type": "nutrient", "plant_type": "ทุเรียน"},
            query="ทุเรียนใบเหลือง ใช้อะไรดี"
        )
        ret = _make_retrieval_result([_make_doc("Biostimulants", "ไบโอเฟอร์ทิล")])
        assert self.agent._should_check_answer(qa, ret) is False

    def test_ambiguous_flower_drop(self):
        """ดอกร่วง — อาจเป็น disease (anthracnose) หรือ nutrient (ขาด boron)
        ถ้า Stage 0=nutrient แต่ Agent 1=disease → trigger."""
        qa = _make_query_analysis(
            IntentType.DISEASE_TREATMENT,
            entities={"problem_type": "nutrient"},
            query="ทุเรียนดอกร่วง ใช้ยาอะไร"
        )
        ret = _make_retrieval_result([_make_doc("Fungicide", "โมเดิน")])
        assert self.agent._should_check_answer(qa, ret) is True

    # =====================================================================
    # กลุ่ม 2: Cross-category — ถามผิดประเภทโดยสิ้นเชิง
    # =====================================================================
    def test_pest_query_gets_herbicide(self):
        """ถามเรื่องเพลี้ย แต่ได้ยาหญ้า → trigger."""
        qa = _make_query_analysis(
            IntentType.PEST_CONTROL,
            entities={"problem_type": "insect", "pest_name": "เพลี้ยแป้ง"},
            query="เพลี้ยแป้งในมันสำปะหลัง ใช้ยาอะไร"
        )
        ret = _make_retrieval_result([_make_doc("Herbicide", "ไกลโฟเสท")])
        assert self.agent._should_check_answer(qa, ret) is True

    def test_weed_query_gets_insecticide(self):
        """ถามเรื่องหญ้า แต่ได้ยาแมลง → trigger."""
        qa = _make_query_analysis(
            IntentType.WEED_CONTROL,
            entities={"problem_type": "weed"},
            query="กำจัดหญ้าในสวนปาล์ม"
        )
        ret = _make_retrieval_result([_make_doc("Insecticide", "ไฮซีส")])
        assert self.agent._should_check_answer(qa, ret) is True

    def test_disease_query_gets_insecticide(self):
        """ถามเรื่องโรค แต่ได้ยาแมลง → trigger."""
        qa = _make_query_analysis(
            IntentType.DISEASE_TREATMENT,
            entities={"problem_type": "disease", "disease_name": "แอนแทรคโนส"},
            query="โรคแอนแทรคโนสในมะม่วง รักษายังไง"
        )
        ret = _make_retrieval_result([_make_doc("Insecticide", "แจ๊ส")])
        assert self.agent._should_check_answer(qa, ret) is True

    # =====================================================================
    # กลุ่ม 3: Slang + ภาษาชาวบ้าน
    # =====================================================================
    def test_slang_ya_dood_nutrient_conflict(self):
        """'ต้นโทรม' = nutrient slang, ถ้า LLM classify เป็น general → trigger."""
        qa = _make_query_analysis(
            IntentType.GENERAL_AGRICULTURE,
            entities={"problem_type": "nutrient"},
            query="ต้นทุเรียนโทรม ใช้อะไรดี"
        )
        ret = _make_retrieval_result([_make_doc("Fungicide", "รีโนเวท")])
        assert self.agent._should_check_answer(qa, ret) is True

    def test_slang_ra_khuen(self):
        """'ราขึ้น' = disease slang, disease intent + Fungicide = OK."""
        qa = _make_query_analysis(
            IntentType.DISEASE_TREATMENT,
            entities={"problem_type": "disease"},
            query="ทุเรียนราขึ้น ฉีดอะไร"
        )
        ret = _make_retrieval_result([_make_doc("Fungicide", "โมเดิน")])
        assert self.agent._should_check_answer(qa, ret) is False

    # =====================================================================
    # กลุ่ม 4: Low confidence / borderline retrieval
    # =====================================================================
    def test_very_low_similarity(self):
        """Similarity 0.20 = docs แทบไม่เกี่ยว → trigger."""
        qa = _make_query_analysis(
            IntentType.DISEASE_TREATMENT,
            entities={"problem_type": "disease"},
            query="โรคที่ไม่เคยได้ยินชื่อ"
        )
        ret = _make_retrieval_result([_make_doc("Fungicide")], avg_sim=0.20)
        assert self.agent._should_check_answer(qa, ret) is True

    def test_borderline_similarity(self):
        """Similarity 0.35 = พอดีขอบ → trigger (< 0.35 threshold)."""
        qa = _make_query_analysis(
            IntentType.DISEASE_TREATMENT,
            entities={"problem_type": "disease"},
            query="โรคพืชแปลกๆ"
        )
        ret = _make_retrieval_result([_make_doc("Fungicide")], avg_sim=0.34)
        assert self.agent._should_check_answer(qa, ret) is True

    def test_above_threshold_similarity(self):
        """Similarity 0.36 = เกินขอบ → ไม่ trigger (category ตรง)."""
        qa = _make_query_analysis(
            IntentType.DISEASE_TREATMENT,
            entities={"problem_type": "disease"},
            query="โรคใบจุดในข้าว"
        )
        ret = _make_retrieval_result([_make_doc("Fungicide")], avg_sim=0.36)
        assert self.agent._should_check_answer(qa, ret) is False

    # =====================================================================
    # กลุ่ม 5: Multiple risk factors ซ้อนกัน
    # =====================================================================
    def test_double_risk_low_sim_plus_category_mismatch(self):
        """Low similarity + category mismatch = ยิ่งต้อง trigger."""
        qa = _make_query_analysis(
            IntentType.NUTRIENT_SUPPLEMENT,
            entities={"problem_type": "nutrient"},
            query="บำรุงต้นลำไย"
        )
        ret = _make_retrieval_result([_make_doc("Insecticide", "แจ๊ส")], avg_sim=0.25)
        assert self.agent._should_check_answer(qa, ret) is True

    def test_triple_risk_all_conflicts(self):
        """Low sim + category mismatch + problem_type conflict = absolute trigger."""
        qa = _make_query_analysis(
            IntentType.PRODUCT_RECOMMENDATION,
            entities={"problem_type": "nutrient"},
            query="เร่งผลมังคุด"
        )
        ret = _make_retrieval_result([_make_doc("Herbicide", "พาราควอท")], avg_sim=0.22)
        assert self.agent._should_check_answer(qa, ret) is True

    # =====================================================================
    # กลุ่ม 6: ถูกต้อง ไม่ควร trigger (false positive check)
    # =====================================================================
    def test_correct_disease_rice_blast(self):
        """ข้าวโรคไหม้ + Fungicide = ถูกต้อง, ไม่ trigger."""
        qa = _make_query_analysis(
            IntentType.DISEASE_TREATMENT,
            entities={"problem_type": "disease", "disease_name": "ใบไหม้", "plant_type": "ข้าว"},
            query="ข้าวเป็นโรคใบไหม้ ใช้ยาอะไร"
        )
        ret = _make_retrieval_result([_make_doc("Fungicide", "โมเดิน")], avg_sim=0.75)
        assert self.agent._should_check_answer(qa, ret) is False

    def test_correct_pest_aphid_cassava(self):
        """เพลี้ยแป้งมันสำปะหลัง + Insecticide = ถูกต้อง."""
        qa = _make_query_analysis(
            IntentType.PEST_CONTROL,
            entities={"problem_type": "insect", "pest_name": "เพลี้ยแป้ง", "plant_type": "มันสำปะหลัง"},
            query="เพลี้ยแป้งในมันสำปะหลัง ใช้อะไร"
        )
        ret = _make_retrieval_result([_make_doc("Insecticide", "แมสฟอร์ด")], avg_sim=0.70)
        assert self.agent._should_check_answer(qa, ret) is False

    def test_correct_weed_rice_paddy(self):
        """หญ้าในนาข้าว + Herbicide = ถูกต้อง."""
        qa = _make_query_analysis(
            IntentType.WEED_CONTROL,
            entities={"problem_type": "weed", "plant_type": "ข้าว"},
            query="หญ้าขึ้นในนาข้าว ใช้ยาอะไร"
        )
        ret = _make_retrieval_result([_make_doc("Herbicide", "ออนดิวตี้")], avg_sim=0.65)
        assert self.agent._should_check_answer(qa, ret) is False

    def test_correct_nutrient_durian_fertilize(self):
        """บำรุงทุเรียน + Biostimulants = ถูกต้อง."""
        qa = _make_query_analysis(
            IntentType.NUTRIENT_SUPPLEMENT,
            entities={"problem_type": "nutrient", "plant_type": "ทุเรียน"},
            query="บำรุงทุเรียนให้ออกดอก"
        )
        ret = _make_retrieval_result([_make_doc("Biostimulants", "ไบโอเฟอร์ทิล")], avg_sim=0.60)
        assert self.agent._should_check_answer(qa, ret) is False

    def test_correct_high_confidence_general_ag(self):
        """General agriculture + high sim + no problem_type = ไม่ trigger."""
        qa = _make_query_analysis(
            IntentType.GENERAL_AGRICULTURE,
            entities={},
            query="ปลูกข้าวโพดช่วงไหนดี"
        )
        ret = _make_retrieval_result([_make_doc("Fertilizer", "ปุ๋ย")], avg_sim=0.55)
        assert self.agent._should_check_answer(qa, ret) is False

    # =====================================================================
    # กลุ่ม 7: Real-world bug scenarios (จาก bugs ที่เจอจริง)
    # =====================================================================
    def test_real_bug_bamrung_bai_durian(self):
        """BUG CASE: "บำรุงใบทุเรียน" → ได้รีโนเวท (Fungicide)
        ทุก risk signal ต้อง trigger."""
        # Scenario A: LLM classify ถูก (nutrient_supplement) แต่ doc ผิด
        qa = _make_query_analysis(
            IntentType.NUTRIENT_SUPPLEMENT,
            entities={"problem_type": "nutrient", "plant_type": "ทุเรียน"},
            query="บำรุงใบทุเรียน"
        )
        ret = _make_retrieval_result([_make_doc("Fungicide", "รีโนเวท")], avg_sim=0.45)
        assert self.agent._should_check_answer(qa, ret) is True

    def test_real_bug_bamrung_misclassified(self):
        """BUG CASE: "บำรุงใบทุเรียน" LLM classify เป็น product_recommendation
        problem_type conflict ต้อง trigger."""
        qa = _make_query_analysis(
            IntentType.PRODUCT_RECOMMENDATION,
            entities={"problem_type": "nutrient", "plant_type": "ทุเรียน"},
            query="บำรุงใบทุเรียน"
        )
        ret = _make_retrieval_result([_make_doc("Fungicide", "รีโนเวท")], avg_sim=0.50)
        assert self.agent._should_check_answer(qa, ret) is True

    def test_real_scenario_rer_dok_mango(self):
        """เร่งดอกมะม่วง → ต้องได้ PGR/Biostimulant ไม่ใช่ Insecticide."""
        qa = _make_query_analysis(
            IntentType.NUTRIENT_SUPPLEMENT,
            entities={"problem_type": "nutrient", "plant_type": "มะม่วง"},
            query="เร่งดอกมะม่วง"
        )
        ret = _make_retrieval_result([_make_doc("Insecticide", "แจ๊ส")])
        assert self.agent._should_check_answer(qa, ret) is True

    def test_real_scenario_tid_pol_longan(self):
        """ลำไยไม่ติดผล → nutrient/PGR ไม่ใช่ Fungicide."""
        qa = _make_query_analysis(
            IntentType.NUTRIENT_SUPPLEMENT,
            entities={"problem_type": "nutrient", "plant_type": "ลำไย"},
            query="ลำไยไม่ติดผล ใช้อะไรดี"
        )
        ret = _make_retrieval_result([_make_doc("Fungicide", "พรีดิก")])
        assert self.agent._should_check_answer(qa, ret) is True
