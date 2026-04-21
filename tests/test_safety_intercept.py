"""Tests for _check_unsupported_question safety intercept."""
import pytest
from app.services.chat.handler import _check_unsupported_question


class TestTankMix:
    def test_tank_mix_blocked(self):
        cases = [
            "ผสมร่วมกันได้ไหม",
            "ใช้ร่วมกันกับไบเตอร์ได้ไหม",
            "ฉีดพร้อมกันกับโมเดินได้ไหม",
            "ผสมกันได้ไหมครับ",
            "tank mix ได้ไหม",
            "รวมยาได้ไหมคะ",
        ]
        for q in cases:
            result = _check_unsupported_question(q)
            assert result is not None, f"Should block tank mix: {q!r}"
            assert "tank mix" in result.lower() or "ผสมยา" in result or "ผสม" in result

    def test_dosage_not_blocked(self):
        """อัตราการผสม (dosage) ต้องไม่ถูก block"""
        cases = [
            "ผสมกี่ซีซีต่อน้ำ 20 ลิตร",
            "ผสมน้ำกี่ลิตร",
            "อัตราผสมคือเท่าไหร่",
            "ผสมยาอัตราเท่าไหร่ครับ",
        ]
        for q in cases:
            result = _check_unsupported_question(q)
            assert result is None, f"Should NOT block dosage question: {q!r}"


class TestPHI:
    def test_phi_blocked(self):
        cases = [
            "หยุดยากี่วันก่อนเก็บเกี่ยว",
            "ระยะหยุดยาคือกี่วัน",
            "หยุดพ่นกี่วัน",
            "ก่อนเก็บเกี่ยวกี่วันถึงหยุดยา",
            "pre-harvest interval คือเท่าไหร่",
        ]
        for q in cases:
            result = _check_unsupported_question(q)
            assert result is not None, f"Should block PHI: {q!r}"
            assert "PHI" in result or "หยุดยา" in result

    def test_harvest_stage_not_blocked(self):
        """ระยะก่อนเก็บเกี่ยว (growth stage) ต้องไม่ถูก block"""
        cases = [
            "ยาอะไรใช้ได้ก่อนเก็บเกี่ยว",
            "ระยะก่อนเก็บเกี่ยวใช้ยาอะไรได้บ้าง",
        ]
        for q in cases:
            result = _check_unsupported_question(q)
            assert result is None, f"Should NOT block harvest stage: {q!r}"


class TestResistance:
    def test_resistance_blocked(self):
        cases = [
            "แมลงดื้อยาแล้วทำยังไง",
            "ต้านทานยาแล้วควรเปลี่ยนเป็นอะไร",
            "ยาไม่ได้ผลแล้วครับ",
            "เชื้อดื้อยา",
        ]
        for q in cases:
            result = _check_unsupported_question(q)
            assert result is not None, f"Should block resistance: {q!r}"

    def test_normal_efficacy_not_blocked(self):
        """คำถามปกติว่า 'ยาได้ผลไหม' ต้องไม่ถูก block"""
        cases = [
            "ไบเตอร์ใช้กับทุเรียนได้ผลไหม",
            "ยาตัวนี้ได้ผลดีไหม",
            "ต้านทานโรคใบไหม้ได้ไหม",
        ]
        for q in cases:
            result = _check_unsupported_question(q)
            assert result is None, f"Should NOT block efficacy question: {q!r}"


class TestNormalQuestionsPassThrough:
    def test_normal_questions_not_blocked(self):
        cases = [
            "ยาอะไรฆ่าเพลี้ยในทุเรียน",
            "โมเดินใช้กับข้าวโพดได้ไหม",
            "ไบเตอร์กับดอยเลอร์ต่างกันยังไง",
            "อัตราการใช้ไบเตอร์คือเท่าไหร่",
            "สวัสดีครับ",
        ]
        for q in cases:
            result = _check_unsupported_question(q)
            assert result is None, f"Should NOT block normal question: {q!r}"
