"""
Tests for RAG-first routing logic
Verifies: greeting → instant, non-agri → general chat, everything else → RAG (default)
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.chat.handler import (
    is_agriculture_question,
    is_product_question,
    _is_clearly_non_agriculture,
    extract_product_name_from_question,
)
from app.prompts import GREETING_KEYWORDS, GENERAL_CHAT_PROMPT


# =============================================================================
# Helper: simulate routing decision (same logic as handle_natural_conversation)
# =============================================================================
def simulate_route(message: str) -> str:
    """Simulate routing decision, returns: 'greeting', 'rag', or 'general_chat'"""
    # 5a. Greeting fast path (with short-keyword guard)
    msg_stripped = message.strip().lower()
    _is_greeting = False
    if len(msg_stripped) < 30:
        for _gkw in GREETING_KEYWORDS:
            if _gkw in msg_stripped:
                if len(_gkw) <= 2 and len(msg_stripped) > 8:
                    continue
                _is_greeting = True
                break
    if _is_greeting:
        return "greeting"

    # 5b. Classify intent (simplified — no extract_keywords_from_question)
    is_agri_q = is_agriculture_question(message)
    is_prod_q = is_product_question(message)
    has_product_name = extract_product_name_from_question(message) is not None

    # 5c. RAG-first routing
    explicit_match = is_agri_q or is_prod_q or has_product_name
    is_non_agri = _is_clearly_non_agriculture(message)
    route_to_rag = explicit_match or not is_non_agri

    if route_to_rag:
        return "rag"
    else:
        return "general_chat"


# =============================================================================
# Test 1: Greetings → instant reply
# =============================================================================
class TestGreetingRouting:
    @pytest.mark.parametrize("msg", [
        "สวัสดีครับ",
        "หวัดดี",
        "ดีครับ",
        "ดีค่ะ",
        "hello",
        "hi",
    ])
    def test_greetings_route_to_instant(self, msg):
        assert simulate_route(msg) == "greeting", f"'{msg}' should route to greeting"


# =============================================================================
# Test 2: Clearly non-agriculture → general chat (neutered)
# =============================================================================
class TestNonAgriRouting:
    @pytest.mark.parametrize("msg", [
        "ขอบคุณค่ะ",
        "ขอบคุณครับ",
        "ขอบใจ",
        "บาย",
        "ลาก่อนค่ะ",
        "555",
        "ฮ่าๆ",
        "ชื่ออะไรคะ",
        "เป็นใคร",
        "โอเค",
        "เข้าใจแล้ว",
        "ได้เลยค่ะ",
        "เก่งมากเลย",
        "ok",
    ])
    def test_non_agri_short_messages_route_to_general_chat(self, msg):
        assert simulate_route(msg) == "general_chat", f"'{msg}' should route to general_chat"


# =============================================================================
# Test 3: Disease names (including transliterated) → RAG
# =============================================================================
class TestDiseaseRoutingToRAG:
    @pytest.mark.parametrize("msg", [
        # ชื่อโรคทับศัพท์ที่เคยหลุด (ปัญหาหลัก)
        "ฟิวซาเรี่ยม",
        "ฟิวซาเรียม",
        "ฟอซาเรียม",
        "ไฟท็อปธอร่า",
        "ไฟทอปธอร่า",
        "คอลเลทโทริคัม",
        # ชื่อโรคที่อยู่ใน AGRICULTURE_KEYWORDS อยู่แล้ว
        "แอนแทรคโนส",
        "ราน้ำค้าง",
        "เชื้อรา",
        # ชื่อโรค + พืช
        "ฟิวซาเรี่ยมในทุเรียน",
        "โรคราสีชมพูในทุเรียน",
    ])
    def test_disease_names_route_to_rag(self, msg):
        result = simulate_route(msg)
        assert result == "rag", f"'{msg}' should route to RAG, got '{result}'"


# =============================================================================
# Test 4: Product names → RAG
# =============================================================================
class TestProductRoutingToRAG:
    @pytest.mark.parametrize("msg", [
        "โทมาฮอค",
        "โมเดิน",
        "คาริสมา",
        "แจ๊ส",
        "โทมาฮอคมีกี่ขนาด",
        "โมเดินใช้ยังไง",
    ])
    def test_product_names_route_to_rag(self, msg):
        result = simulate_route(msg)
        assert result == "rag", f"'{msg}' should route to RAG, got '{result}'"


# =============================================================================
# Test 5: Ambiguous / unknown messages → RAG (default, NOT general chat)
# =============================================================================
class TestAmbiguousRoutingToRAG:
    @pytest.mark.parametrize("msg", [
        # ข้อความที่ไม่ชัดเจน → ควรไป RAG (ปลอดภัยกว่า)
        "ฟิวซาเรี่ยม",                    # ชื่อโรคทับศัพท์ ← ปัญหาหลัก!
        "มีวิธีแก้ไหม",                   # follow-up ไม่มี keyword ชัด
        "ช่วยแนะนำหน่อย",                 # ambiguous
        "ใช้ตัวไหนดี",                     # ambiguous product
        "ยาดูด",                          # farmer slang
        "ต้นเป็นอะไรไม่รู้",               # symptom description
        "ใบมันเหลืองๆ",                   # symptom
        "อัตราผสมเท่าไหร่",               # dosage question
        "ไซมอกซิเมทใช้กับอะไร",            # chemical name
    ])
    def test_ambiguous_messages_route_to_rag_not_general_chat(self, msg):
        result = simulate_route(msg)
        assert result == "rag", f"'{msg}' should route to RAG (default), got '{result}'"


# =============================================================================
# Test 6: Long non-agri messages → RAG (safety: len > 30 → not non-agri → RAG)
# =============================================================================
class TestLongNonAgriGoesToRAG:
    @pytest.mark.parametrize("msg", [
        "ขอบคุณค่ะ แล้วใช้กับทุเรียนได้มั้ย",   # ขอบคุณ + follow-up
        "ขอบคุณมากค่ะ แล้วใช้ตอนไหนดี",          # ขอบคุณ + follow-up
        "เข้าใจแล้วค่ะ แล้วยานี้ใช้กี่ซีซี",       # acknowledgement + follow-up
    ])
    def test_long_messages_with_non_agri_keyword_still_go_to_rag(self, msg):
        result = simulate_route(msg)
        assert result == "rag", f"'{msg}' (len={len(msg)}) should route to RAG, got '{result}'"


# =============================================================================
# Test 7: GENERAL_CHAT_PROMPT safety — no agriculture expertise
# =============================================================================
class TestGeneralChatPromptSafety:
    def test_no_agriculture_expertise(self):
        assert "ความเชี่ยวชาญ" not in GENERAL_CHAT_PROMPT

    def test_no_product_knowledge(self):
        assert "ผลิตภัณฑ์ ICP Ladda" not in GENERAL_CHAT_PROMPT

    def test_no_calculation_ability(self):
        assert "คำนวณอัตราผสม" not in GENERAL_CHAT_PROMPT

    def test_has_product_constraint(self):
        assert "ห้ามแนะนำชื่อสินค้า" in GENERAL_CHAT_PROMPT

    def test_has_disease_constraint(self):
        assert "ห้ามตอบเรื่องโรคพืช" in GENERAL_CHAT_PROMPT

    def test_has_redirect_message(self):
        assert "กรุณาพิมพ์ชื่อสินค้า" in GENERAL_CHAT_PROMPT

    def test_no_hallucination_constraint(self):
        assert "ห้ามเดา" in GENERAL_CHAT_PROMPT


# =============================================================================
# Test 8: _is_clearly_non_agriculture edge cases
# =============================================================================
class TestNonAgriFunction:
    def test_short_non_agri_true(self):
        assert _is_clearly_non_agriculture("ขอบคุณ") == True

    def test_long_message_always_false(self):
        # Even with non-agri keyword, messages > 20 chars → False (might have follow-up)
        assert _is_clearly_non_agriculture("ขอบคุณค่ะ แล้วสินค้านี้ใช้กับทุเรียนได้ไหมคะ") == False
        assert _is_clearly_non_agriculture("ขอบคุณมากค่ะ แล้วใช้ตอนไหนดี") == False

    def test_empty_message(self):
        assert _is_clearly_non_agriculture("") == False

    def test_random_short_message_not_non_agri(self):
        # Short but no non-agri keyword → False → routes to RAG (safe!)
        assert _is_clearly_non_agriculture("ใบเหลือง") == False
        assert _is_clearly_non_agriculture("ฟิวซาเรี่ยม") == False

    def test_agriculture_keyword_not_matched(self):
        # "ข้าว" is agriculture, not in _NON_AGRI_KEYWORDS
        assert _is_clearly_non_agriculture("ข้าว") == False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
