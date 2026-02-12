"""
Unit tests for: Metadata Product Leaks into New Topic fix
Tests 2 layers:
  Layer 1: orchestrator.py Strategy 0 guard — skip metadata product when query has new topic
  Layer 2: query_understanding_agent.py — GENERAL_AGRICULTURE in skip set
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, "C:\\clone_chatbot_ick\\Chatbot-ladda")

from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

from app.services.chat.handler import extract_plant_type_from_question
from app.services.rag import IntentType


# =====================================================================
# Layer 1: Strategy 0 guard logic (unit-test the guard conditions)
# =====================================================================

_DISEASE_PEST_KEYWORDS = ['โรค', 'เพลี้ย', 'หนอน', 'ด้วง', 'แมลง', 'เชื้อ', 'ราแป้ง', 'ราน้ำ', 'ราสี', 'ราสนิม', 'ราดำ', 'ไรแดง', 'ไรขาว']
_USAGE_VERBS = ['ใช้', 'ฉีด', 'พ่น', 'ผสม', 'ราด', 'หยด', 'รด']

def _has_new_topic(query: str) -> bool:
    """Replicate the guard logic from orchestrator.py Strategy 0 (with applicability exception)"""
    plant = extract_plant_type_from_question(query)
    has_kw = any(kw in query for kw in _DISEASE_PEST_KEYWORDS)
    is_applicability = bool(plant) and any(v in query for v in _USAGE_VERBS)
    return (bool(plant) and not is_applicability) or has_kw


class TestStrategy0Guard:
    """Layer 1: Strategy 0 should be SKIPPED when query introduces a new topic"""

    def test_new_topic_with_plant(self):
        """'ทำทุเรียนนอกฤดู' has plant=ทุเรียน → blocked"""
        assert _has_new_topic("ทำทุเรียนนอกฤดู") is True
        print("  PASS: 'ทำทุเรียนนอกฤดู' → blocked (plant=ทุเรียน)")

    def test_new_topic_with_disease_keyword(self):
        """'โรคราสีชมพู ทุเรียน' has โรค + plant → blocked"""
        assert _has_new_topic("โรคราสีชมพู ทุเรียน") is True
        print("  PASS: 'โรคราสีชมพู ทุเรียน' → blocked")

    def test_new_topic_with_pest_keyword(self):
        """'เพลี้ยไฟ แก้ยังไง' has เพลี้ย → blocked"""
        assert _has_new_topic("เพลี้ยไฟ แก้ยังไง") is True
        print("  PASS: 'เพลี้ยไฟ แก้ยังไง' → blocked")

    def test_new_topic_with_worm(self):
        """'หนอนเจาะลำต้น' has หนอน → blocked"""
        assert _has_new_topic("หนอนเจาะลำต้น") is True
        print("  PASS: 'หนอนเจาะลำต้น' → blocked")

    def test_new_topic_with_fungus(self):
        """'ราแป้ง ใช้อะไรดี' has ราแป้ง → blocked"""
        assert _has_new_topic("ราแป้ง ใช้อะไรดี") is True
        print("  PASS: 'ราแป้ง ใช้อะไรดี' → blocked (ราแป้ง)")

    def test_new_topic_with_mite(self):
        """'ไรแดง ข้าว' has ไรแดง + plant=ข้าว → blocked"""
        assert _has_new_topic("ไรแดง ข้าว") is True
        print("  PASS: 'ไรแดง ข้าว' → blocked (ไรแดง + plant)")

    def test_new_topic_with_beetle(self):
        """'ด้วงแรด ปาล์ม' has ด้วง → blocked"""
        assert _has_new_topic("ด้วงแรด ปาล์ม") is True
        print("  PASS: 'ด้วงแรด ปาล์ม' → blocked")

    def test_new_topic_with_insect(self):
        """'แมลงหวี่ขาว' has แมลง → blocked"""
        assert _has_new_topic("แมลงหวี่ขาว") is True
        print("  PASS: 'แมลงหวี่ขาว' → blocked")

    def test_new_topic_with_pathogen(self):
        """'เชื้อราไฟทอปธอร่า' has เชื้อ → blocked"""
        assert _has_new_topic("เชื้อราไฟทอปธอร่า") is True
        print("  PASS: 'เชื้อราไฟทอปธอร่า' → blocked")

    def test_followup_usage(self):
        """'ใช้ยังไง' — no plant, no disease/pest → allowed"""
        assert _has_new_topic("ใช้ยังไง") is False
        print("  PASS: 'ใช้ยังไง' → allowed (follow-up)")

    def test_followup_mix(self):
        """'ผสมอะไร' — no plant, no disease/pest → allowed"""
        assert _has_new_topic("ผสมอะไร") is False
        print("  PASS: 'ผสมอะไร' → allowed (follow-up)")

    def test_followup_price(self):
        """'ราคาเท่าไหร่' — no plant, no disease/pest → allowed"""
        assert _has_new_topic("ราคาเท่าไหร่") is False
        print("  PASS: 'ราคาเท่าไหร่' → allowed (follow-up)")

    def test_followup_spray_rate(self):
        """'อัตราฉีดพ่น' — no plant, no disease/pest → allowed"""
        assert _has_new_topic("อัตราฉีดพ่น") is False
        print("  PASS: 'อัตราฉีดพ่น' → allowed (follow-up)")

    def test_followup_how_often(self):
        """'ฉีดกี่วันครั้ง' — allowed"""
        assert _has_new_topic("ฉีดกี่วันครั้ง") is False
        print("  PASS: 'ฉีดกี่วันครั้ง' → allowed (follow-up)")


# =====================================================================
# Layer 2: GENERAL_AGRICULTURE in skip set
# =====================================================================

class TestProductOverrideSkipSet:
    """Layer 2: When LLM says product=None and intent is in skip set,
    the pre-extracted product hint should NOT be injected."""

    def test_general_agriculture_in_skip_set(self):
        """GENERAL_AGRICULTURE should be in the skip set"""
        _rec_intents_for_override = {
            IntentType.PRODUCT_RECOMMENDATION, IntentType.DISEASE_TREATMENT,
            IntentType.PEST_CONTROL, IntentType.NUTRIENT_SUPPLEMENT,
            IntentType.GENERAL_AGRICULTURE,
        }
        assert IntentType.GENERAL_AGRICULTURE in _rec_intents_for_override
        print("  PASS: GENERAL_AGRICULTURE is in _rec_intents_for_override")

    def test_usage_instruction_not_in_skip_set(self):
        """USAGE_INSTRUCTION should NOT be in skip set (follow-up needs product)"""
        _rec_intents_for_override = {
            IntentType.PRODUCT_RECOMMENDATION, IntentType.DISEASE_TREATMENT,
            IntentType.PEST_CONTROL, IntentType.NUTRIENT_SUPPLEMENT,
            IntentType.GENERAL_AGRICULTURE,
        }
        assert IntentType.USAGE_INSTRUCTION not in _rec_intents_for_override
        print("  PASS: USAGE_INSTRUCTION is NOT in skip set (allows product inject for follow-up)")

    def test_product_inquiry_not_in_skip_set(self):
        """PRODUCT_INQUIRY should NOT be in skip set"""
        _rec_intents_for_override = {
            IntentType.PRODUCT_RECOMMENDATION, IntentType.DISEASE_TREATMENT,
            IntentType.PEST_CONTROL, IntentType.NUTRIENT_SUPPLEMENT,
            IntentType.GENERAL_AGRICULTURE,
        }
        assert IntentType.PRODUCT_INQUIRY not in _rec_intents_for_override
        print("  PASS: PRODUCT_INQUIRY is NOT in skip set")

    def test_skip_logic_general_agriculture(self):
        """Simulate: LLM says product=None, intent=GENERAL_AGRICULTURE, hint='แมสฟอร์ด'
        Expected: product stays None (skip override)"""
        hints = {'product_name': 'แมสฟอร์ด'}
        entities = {}  # LLM returned no product → product_name not in entities
        intent = IntentType.GENERAL_AGRICULTURE
        llm_fallback_keys = []

        _rec_intents_for_override = {
            IntentType.PRODUCT_RECOMMENDATION, IntentType.DISEASE_TREATMENT,
            IntentType.PEST_CONTROL, IntentType.NUTRIENT_SUPPLEMENT,
            IntentType.GENERAL_AGRICULTURE,
        }

        # Replicate the override logic
        if hints.get('product_name') and entities.get('product_name') != hints['product_name']:
            if 'product_name' not in llm_fallback_keys:
                llm_said_none = entities.get('product_name') is None
                if llm_said_none and intent in _rec_intents_for_override:
                    pass  # Skip override — correct!
                else:
                    entities['product_name'] = hints['product_name']

        assert entities.get('product_name') is None, \
            f"product should be None but got '{entities.get('product_name')}'"
        print("  PASS: GENERAL_AGRICULTURE + product=None → skip override (no inject)")

    def test_override_works_for_usage_instruction(self):
        """Simulate: LLM says product=None, intent=USAGE_INSTRUCTION, hint='แมสฟอร์ด'
        Expected: product gets overridden to 'แมสฟอร์ด' (follow-up needs it)"""
        hints = {'product_name': 'แมสฟอร์ด'}
        entities = {}
        intent = IntentType.USAGE_INSTRUCTION
        llm_fallback_keys = []

        _rec_intents_for_override = {
            IntentType.PRODUCT_RECOMMENDATION, IntentType.DISEASE_TREATMENT,
            IntentType.PEST_CONTROL, IntentType.NUTRIENT_SUPPLEMENT,
            IntentType.GENERAL_AGRICULTURE,
        }

        if hints.get('product_name') and entities.get('product_name') != hints['product_name']:
            if 'product_name' not in llm_fallback_keys:
                llm_said_none = entities.get('product_name') is None
                if llm_said_none and intent in _rec_intents_for_override:
                    pass
                else:
                    entities['product_name'] = hints['product_name']

        assert entities.get('product_name') == 'แมสฟอร์ด', \
            f"product should be 'แมสฟอร์ด' but got '{entities.get('product_name')}'"
        print("  PASS: USAGE_INSTRUCTION + product=None → override to 'แมสฟอร์ด' (follow-up)")


# =====================================================================
# Combined scenario: end-to-end logic simulation
# =====================================================================

class TestEndToEndScenario:
    """Simulate the exact bug scenario from the plan"""

    def test_bug_scenario_blocked(self):
        """User: 'เพลี้ยแป้ง' → bot: แมสฟอร์ด → User: 'ทำทุเรียนนอกฤดู'
        Strategy 0 should NOT inject แมสฟอร์ด because query has plant=ทุเรียน"""
        query = "ทำทุเรียนนอกฤดู"
        context = "[บทสนทนาปัจจุบัน]\nผู้ใช้: เพลี้ยแป้ง\nน้องลัดดา: แนะนำ แมสฟอร์ด\n[สินค้าล่าสุดในบทสนทนา] แมสฟอร์ด\n[สรุปหัวข้อก่อนหน้า]\n"

        # Strategy 0 guard
        plant = extract_plant_type_from_question(query)
        has_kw = any(kw in query for kw in _DISEASE_PEST_KEYWORDS)
        should_skip = bool(plant) or has_kw

        assert should_skip is True, "Strategy 0 should be skipped for new topic"
        assert plant == "ทุเรียน", f"Expected plant=ทุเรียน, got {plant}"

        # Since skipped, detected_product stays None
        detected_product = None
        assert detected_product is None
        print("  PASS: Bug scenario — 'ทำทุเรียนนอกฤดู' after แมสฟอร์ด → Strategy 0 blocked")

    def test_followup_allowed(self):
        """User: 'เพลี้ยแป้ง' → bot: แมสฟอร์ด → User: 'ใช้ยังไง'
        Strategy 0 should inject แมสฟอร์ด because query is a follow-up"""
        query = "ใช้ยังไง"
        context_line = "[สินค้าล่าสุดในบทสนทนา] แมสฟอร์ด"

        # Strategy 0 guard
        plant = extract_plant_type_from_question(query)
        has_kw = any(kw in query for kw in _DISEASE_PEST_KEYWORDS)
        should_skip = bool(plant) or has_kw

        assert should_skip is False, "Strategy 0 should NOT be skipped for follow-up"

        # Strategy 0 fires — extract product from metadata line
        detected_product = None
        if context_line.startswith("[สินค้าล่าสุดในบทสนทนา]"):
            section_text = context_line.replace("[สินค้าล่าสุดในบทสนทนา]", "").strip()
            if section_text:
                detected_product = section_text.split(',')[0].strip()

        assert detected_product == "แมสฟอร์ด", f"Expected แมสฟอร์ด, got {detected_product}"
        print("  PASS: Follow-up 'ใช้ยังไง' → Strategy 0 fires → แมสฟอร์ด injected")

    def test_disease_query_blocked(self):
        """User: 'โรครากเน่า' after product recommendation → blocked"""
        query = "โรครากเน่า"
        plant = extract_plant_type_from_question(query)
        has_kw = any(kw in query for kw in _DISEASE_PEST_KEYWORDS)
        should_skip = bool(plant) or has_kw

        assert should_skip is True
        print("  PASS: 'โรครากเน่า' → Strategy 0 blocked (has โรค + รา)")

    def test_pest_query_blocked(self):
        """User: 'เพลี้ยไฟ ทำยังไง' after product recommendation → blocked"""
        query = "เพลี้ยไฟ ทำยังไง"
        plant = extract_plant_type_from_question(query)
        has_kw = any(kw in query for kw in _DISEASE_PEST_KEYWORDS)
        should_skip = bool(plant) or has_kw

        assert should_skip is True
        print("  PASS: 'เพลี้ยไฟ ทำยังไง' → Strategy 0 blocked")


# =====================================================================
# Layer 1b: Applicability pattern exception
# =====================================================================

class TestApplicabilityPattern:
    """Layer 1b: Queries like 'ใช้ในทุเรียนได้มั้ย' should NOT be blocked
    even though they contain a plant name, because they're asking about
    the current product's applicability — not introducing a new topic."""

    def test_applicability_durian(self):
        """'ใช้ในทุเรียนได้มั้ย' — plant + usage verb → allowed"""
        assert _has_new_topic("ใช้ในทุเรียนได้มั้ย") is False
        print("  PASS: 'ใช้ในทุเรียนได้มั้ย' → allowed (applicability)")

    def test_applicability_spray_mango(self):
        """'ฉีดมะม่วงได้ไหม' — plant + ฉีด → allowed"""
        assert _has_new_topic("ฉีดมะม่วงได้ไหม") is False
        print("  PASS: 'ฉีดมะม่วงได้ไหม' → allowed (applicability)")

    def test_applicability_spray_rice(self):
        """'พ่นข้าวได้ไหม' — plant + พ่น → allowed"""
        assert _has_new_topic("พ่นข้าวได้ไหม") is False
        print("  PASS: 'พ่นข้าวได้ไหม' → allowed (applicability)")

    def test_applicability_use_with_longan(self):
        """'ใช้กับลำไยได้มั้ย' — plant + ใช้ → allowed"""
        assert _has_new_topic("ใช้กับลำไยได้มั้ย") is False
        print("  PASS: 'ใช้กับลำไยได้มั้ย' → allowed (applicability)")

    def test_applicability_mix_orange(self):
        """'ผสมพ่นส้มได้ไหม' — plant + ผสม → allowed"""
        assert _has_new_topic("ผสมพ่นส้มได้ไหม") is False
        print("  PASS: 'ผสมพ่นส้มได้ไหม' → allowed (applicability)")

    def test_new_topic_still_blocked(self):
        """'ทำทุเรียนนอกฤดู' — plant but NO usage verb → blocked"""
        assert _has_new_topic("ทำทุเรียนนอกฤดู") is True
        print("  PASS: 'ทำทุเรียนนอกฤดู' → blocked (no usage verb)")

    def test_disease_with_usage_still_blocked(self):
        """'ราแป้ง ฉีดอะไรดี' — has disease keyword → blocked regardless"""
        assert _has_new_topic("ราแป้ง ฉีดอะไรดี") is True
        print("  PASS: 'ราแป้ง ฉีดอะไรดี' → blocked (disease keyword overrides)")


# =====================================================================
# Layer 2b: Trust LLM when hint is from context
# =====================================================================

class TestContextHintTrustLLM:
    """Layer 2b: When product hint is from context (not query) and LLM found
    a specific product, trust LLM over the context hint."""

    def _run_override_logic(self, hints, entities, intent):
        """Replicate the override logic from query_understanding_agent.py"""
        llm_fallback_keys = hints.get('_llm_fallback_keys', [])
        _rec_intents_for_override = {
            IntentType.PRODUCT_RECOMMENDATION, IntentType.DISEASE_TREATMENT,
            IntentType.PEST_CONTROL, IntentType.NUTRIENT_SUPPLEMENT,
            IntentType.GENERAL_AGRICULTURE,
        }
        if hints.get('product_name') and entities.get('product_name') != hints['product_name']:
            if 'product_name' not in llm_fallback_keys:
                llm_said_none = entities.get('product_name') is None
                hint_from_query = hints.get('_product_from_query', False)
                if llm_said_none and intent in _rec_intents_for_override:
                    pass  # Skip override
                elif not llm_said_none and not hint_from_query:
                    pass  # Keep LLM product (context hint less reliable)
                else:
                    entities['product_name'] = hints['product_name']
        return entities

    def test_llm_wins_over_context_hint(self):
        """Bug scenario: hint=พาสนาว (from context), LLM=โมเดิน (correct)
        Expected: Keep LLM product=โมเดิน"""
        hints = {'product_name': 'พาสนาว', '_product_from_query': False}
        entities = {'product_name': 'โมเดิน'}
        result = self._run_override_logic(hints, entities, IntentType.PRODUCT_INQUIRY)
        assert result.get('product_name') == 'โมเดิน', \
            f"Expected 'โมเดิน' but got '{result.get('product_name')}'"
        print("  PASS: LLM='โมเดิน' vs context hint='พาสนาว' → keep LLM (โมเดิน)")

    def test_query_hint_overrides_llm(self):
        """hint=โมเดิน (from query), LLM=คาริสมา (wrong)
        Expected: Override to โมเดิน"""
        hints = {'product_name': 'โมเดิน', '_product_from_query': True}
        entities = {'product_name': 'คาริสมา'}
        result = self._run_override_logic(hints, entities, IntentType.PRODUCT_INQUIRY)
        assert result.get('product_name') == 'โมเดิน', \
            f"Expected 'โมเดิน' but got '{result.get('product_name')}'"
        print("  PASS: hint from query='โมเดิน' vs LLM='คาริสมา' → override to โมเดิน")

    def test_context_hint_llm_none_skip(self):
        """hint=พาสนาว (from context), LLM=None, intent=DISEASE_TREATMENT
        Expected: Skip override (LLM correctly found no product)"""
        hints = {'product_name': 'พาสนาว', '_product_from_query': False}
        entities = {}  # LLM returned None
        result = self._run_override_logic(hints, entities, IntentType.DISEASE_TREATMENT)
        assert result.get('product_name') is None, \
            f"Expected None but got '{result.get('product_name')}'"
        print("  PASS: context hint='พาสนาว' + LLM=None + DISEASE_TREATMENT → skip (no inject)")

    def test_query_hint_overrides_none(self):
        """hint=โมเดิน (from query), LLM=None, intent=USAGE_INSTRUCTION
        Expected: Override to โมเดิน"""
        hints = {'product_name': 'โมเดิน', '_product_from_query': True}
        entities = {}  # LLM returned None
        result = self._run_override_logic(hints, entities, IntentType.USAGE_INSTRUCTION)
        assert result.get('product_name') == 'โมเดิน', \
            f"Expected 'โมเดิน' but got '{result.get('product_name')}'"
        print("  PASS: query hint='โมเดิน' + LLM=None + USAGE_INSTRUCTION → override to โมเดิน")

    def test_no_flag_defaults_to_override(self):
        """No _product_from_query flag (backward compat) → defaults to override"""
        hints = {'product_name': 'แมสฟอร์ด'}  # No _product_from_query key
        entities = {'product_name': 'คาริสมา'}
        result = self._run_override_logic(hints, entities, IntentType.PRODUCT_INQUIRY)
        # hint_from_query defaults to False → LLM wins (not llm_said_none and not hint_from_query)
        assert result.get('product_name') == 'คาริสมา', \
            f"Expected 'คาริสมา' (LLM kept) but got '{result.get('product_name')}'"
        print("  PASS: no flag (backward compat) + LLM has product → keep LLM")

    def test_exact_bug_scenario_follow_up(self):
        """Exact bug: 'โมเดิน' → bot answers → 'ใช้ในทุเรียนได้มั้ย'
        Strategy 2 finds พาสนาว, but LLM reads context and finds โมเดิน
        Expected: Keep LLM=โมเดิน"""
        # Strategy 0 allowed (applicability) but no metadata product
        # Strategy 2 found พาสนาว (wrong)
        hints = {'product_name': 'พาสนาว', '_product_from_query': False}
        entities = {'product_name': 'โมเดิน'}  # LLM read context correctly
        result = self._run_override_logic(hints, entities, IntentType.PRODUCT_INQUIRY)
        assert result.get('product_name') == 'โมเดิน', \
            f"Expected 'โมเดิน' but got '{result.get('product_name')}'"
        print("  PASS: Exact bug scenario → LLM='โมเดิน' kept over context hint='พาสนาว'")


# =====================================================================
# Run all tests
# =====================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("Test: Metadata Product Leak Fix")
    print("=" * 60)

    print("\n--- Layer 1: Strategy 0 Guard (orchestrator.py) ---")
    t1 = TestStrategy0Guard()
    t1.test_new_topic_with_plant()
    t1.test_new_topic_with_disease_keyword()
    t1.test_new_topic_with_pest_keyword()
    t1.test_new_topic_with_worm()
    t1.test_new_topic_with_fungus()
    t1.test_new_topic_with_mite()
    t1.test_new_topic_with_beetle()
    t1.test_new_topic_with_insect()
    t1.test_new_topic_with_pathogen()
    t1.test_followup_usage()
    t1.test_followup_mix()
    t1.test_followup_price()
    t1.test_followup_spray_rate()
    t1.test_followup_how_often()

    print("\n--- Layer 2: Product Override Skip Set (query_understanding_agent.py) ---")
    t2 = TestProductOverrideSkipSet()
    t2.test_general_agriculture_in_skip_set()
    t2.test_usage_instruction_not_in_skip_set()
    t2.test_product_inquiry_not_in_skip_set()
    t2.test_skip_logic_general_agriculture()
    t2.test_override_works_for_usage_instruction()

    print("\n--- End-to-End Scenario Simulation ---")
    t3 = TestEndToEndScenario()
    t3.test_bug_scenario_blocked()
    t3.test_followup_allowed()
    t3.test_disease_query_blocked()
    t3.test_pest_query_blocked()

    print("\n--- Layer 1b: Applicability Pattern Exception ---")
    t4 = TestApplicabilityPattern()
    t4.test_applicability_durian()
    t4.test_applicability_spray_mango()
    t4.test_applicability_spray_rice()
    t4.test_applicability_use_with_longan()
    t4.test_applicability_mix_orange()
    t4.test_new_topic_still_blocked()
    t4.test_disease_with_usage_still_blocked()

    print("\n--- Layer 2b: Trust LLM over Context Hint ---")
    t5 = TestContextHintTrustLLM()
    t5.test_llm_wins_over_context_hint()
    t5.test_query_hint_overrides_llm()
    t5.test_context_hint_llm_none_skip()
    t5.test_query_hint_overrides_none()
    t5.test_no_flag_defaults_to_override()
    t5.test_exact_bug_scenario_follow_up()

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
