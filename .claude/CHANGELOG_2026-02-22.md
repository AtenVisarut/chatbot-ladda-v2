# Changelog 2026-02-22

## Anti-Hallucination: Number Validation + Product Name Check

ปรับปรุงระบบ anti-hallucination 2 จุด + แก้ broken imports + migrate `max_tokens` → `max_completion_tokens`

---

### WI-1: Enforce Number Validation

**ไฟล์**: `app/services/rag/response_generator_agent.py:167-174`

**ปัญหา**: ระบบ validate ตัวเลขอัตราใช้ได้แล้ว แต่แค่ log ไม่เตือนเกษตรกร → LLM อาจแต่งตัวเลขขึ้นมา (เช่น 50 ซีซี แทนที่จริงคือ 20 ซีซี) เกษตรกรไม่รู้

**แก้ไข**:
- เปลี่ยนจาก `logger.warning` (log-only) → `logger.error` + append warning ท้ายคำตอบ
- เกษตรกรจะเห็น: `(หมายเหตุ: กรุณาตรวจสอบอัตราการใช้จากฉลากสินค้าอีกครั้งค่ะ)`
- ไม่ block คำตอบทั้งหมด เพราะอาจเป็น false positive (LLM คำนวณ 200÷10=20 → "20" ไม่อยู่ใน source)

---

### WI-2: Validate Product Names ทั้ง Quoted และ Unquoted

**ไฟล์**: `app/services/rag/response_generator_agent.py:565-578`

**ปัญหา**: ระบบตรวจเฉพาะชื่อสินค้าในเครื่องหมายคำพูด `"..."` → ถ้า LLM เขียนชื่อสินค้าโดยไม่ใส่เครื่องหมายคำพูดจะหลุดรอด

**แก้ไข**: เพิ่ม Pass 2 ใน `_validate_product_names()`:
- Scan ชื่อสินค้าจาก `ICP_PRODUCT_NAMES` (DB-driven) ทั้งหมดที่ปรากฏใน answer
- ถ้าชื่อสินค้าอยู่ใน DB แต่ไม่อยู่ใน retrieved docs → cross-product hallucination
- แทนที่ด้วย: `(กรุณาสอบถามข้อมูล {ชื่อสินค้า} แยกต่างหากค่ะ)`
- ข้ามชื่อสั้นกว่า 3 ตัวอักษร เพื่อป้องกัน false positive

---

### Fix: Restore Disease Constants Module

**ปัญหา**: `app/services/disease/` ถูกลบทั้ง directory ใน commit `48fa74b` แต่ RAG pipeline ยัง import `DISEASE_PATTERNS_SORTED` และ `get_canonical` จาก 4 ไฟล์ → crash ทุกครั้งที่ถามคำถามเกี่ยวกับโรค

**แก้ไข**:
- Restore `app/services/disease/__init__.py` (minimal)
- Restore `app/services/disease/constants.py` จาก git history (40 lines: patterns + canonical mapping)
- ลบ dead code: `database.py`, `detection.py`, `response.py`, `search.py` (ถูกลบจาก disk อยู่แล้ว)
- Safe import ใน `handler.py:9`: `try/except ImportError` สำหรับ `disease.search` (ยังไม่มี module)

---

### Fix: Migrate `max_tokens` → `max_completion_tokens`

**ปัญหา**: gpt-5 ไม่รองรับ `max_tokens` parameter → ต้องใช้ `max_completion_tokens`

**ไฟล์ที่แก้** (10 จุด):

| ไฟล์ | จุดที่แก้ |
|------|-----------|
| `app/services/rag/response_generator_agent.py` | `max_completion_tokens=700` |
| `app/services/rag/grounding_agent.py` | `max_completion_tokens=500` |
| `app/services/rag/retrieval_agent.py` | `max_completion_tokens=100` |
| `app/services/chat/handler.py` | 4 จุด: 600, 800, 600, 150 |
| `app/services/chat/quick_classifier.py` | 2 จุด: 300, 300 |
| `app/services/knowledge_base.py` | `max_completion_tokens=400` |
| `app/services/product/recommendation.py` | 2 จุด: 800, 800 |
| `app/services/reranker.py` | `max_completion_tokens=100` |

---

## Test Results (test_farmer_questions.py)

```
7 PASS / 2 WARN / 0 FAIL / 0 ERROR
Avg: 6.8s per question
```

| Conv | Status | หมายเหตุ |
|------|--------|----------|
| A1 โมเดิน ใช้ยังไง | PASS | WI-1 warning appended |
| A2 ใช้กับทุเรียนได้ไหม | PASS | Follow-up ถูก + WI-1 |
| B1 ใบทุเรียนเป็นจุด | PASS | แนะนำ fungicide |
| C1 เพลี้ยกระโดดนาข้าว | PASS | แนะนำ insecticide |
| C2 ผสมกี่ซีซี | PASS | ตอบเป็น มล. |
| D1 อาเทมิส ราคา | WARN | test expect "อาร์เทมีส" แต่ DB ชื่อ "อาร์เทมิส" |
| E1 หนอนเจาะลำต้น | PASS | แนะนำชุดกล่องม่วง |
| F1 15 ไร่ กี่ขวด | WARN | คำนวณถูก — WARN เพราะชื่อ DB |
| G1 ราแป้งข้าวโพด | PASS | Anti-hallucination block ทำงาน |

WARN ทั้ง 2 ตัว = test expectation เก่า (expect สระอี "อาร์เทมีส" แต่ DB ไม่มีสระอี) ไม่ใช่ bug
