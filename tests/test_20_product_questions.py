"""
Test 20 คำถามเกี่ยวกับสินค้าจาก products table
ทดสอบว่า answer_qa_with_vector_search() ใช้ products table ได้ถูกต้อง

ครอบคลุม:
- คำถามเฉพาะสินค้า (ชื่อ/วิธีใช้/อัตรา)
- คำถามตามปัญหา (โรค/แมลง/วัชพืช)
- คำถามตามพืช
- คำถามแนะนำสินค้า
- คำถามทั่วไปเกี่ยวกับสินค้า
"""
import os
import sys
import asyncio
import io

# Force UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# 20 test questions - ใช้ชื่อสินค้าจริงจาก products table
TEST_QUESTIONS = [
    # --- กลุ่ม 1: ถามเฉพาะสินค้า (product-specific) ---
    {
        "id": 1,
        "question": "โมเดิน 50 ใช้กำจัดอะไรได้บ้าง",
        "expected_product": "โมเดิน 50",
        "category": "กำจัดแมลง",
        "type": "product_info"
    },
    {
        "id": 2,
        "question": "อัตราการใช้ แอนดาแม็กซ์ ในทุเรียน",
        "expected_product": "แอนดาแม็กซ์",
        "category": "ป้องกันโรค",
        "type": "usage_rate"
    },
    {
        "id": 3,
        "question": "เกรค 5 เอสซี วิธีใช้อย่างไร",
        "expected_product": "เกรค 5 เอสซี",
        "category": "กำจัดแมลง",
        "type": "how_to_use"
    },
    {
        "id": 4,
        "question": "ก็อปกัน คืออะไร ใช้ทำอะไร",
        "expected_product": "ก็อปกัน",
        "category": "ป้องกันโรค",
        "type": "what_is"
    },

    # --- กลุ่ม 2: ถามตามปัญหา (problem-based) ---
    {
        "id": 5,
        "question": "เพลี้ยไฟในทุเรียน ใช้ยาอะไรดี",
        "expected_product": "โมเดิน 50",
        "category": "กำจัดแมลง",
        "type": "recommend_insect"
    },
    {
        "id": 6,
        "question": "โรคแอนแทรคโนสในทุเรียน ป้องกันยังไง",
        "expected_product": "โค-ราซ",
        "category": "ป้องกันโรค",
        "type": "recommend_disease"
    },
    {
        "id": 7,
        "question": "หนอนกอข้าว กำจัดด้วยอะไร",
        "expected_product": "นาแดน",
        "category": "กำจัดแมลง",
        "type": "recommend_insect"
    },
    {
        "id": 8,
        "question": "วัชพืชในนาข้าว ใช้ยาอะไร",
        "expected_product": "แกนเตอร์",
        "category": "กำจัดวัชพืช",
        "type": "recommend_weed"
    },

    # --- กลุ่ม 3: ถามตามพืช (crop-based) ---
    {
        "id": 9,
        "question": "ยาฆ่าแมลงสำหรับข้าว มีตัวไหนบ้าง",
        "expected_product": "เกรค",
        "category": "กำจัดแมลง",
        "type": "crop_products"
    },
    {
        "id": 10,
        "question": "สินค้า ICP สำหรับทุเรียน มีอะไรบ้าง",
        "expected_product": "โมเดิน",
        "category": "กำจัดแมลง",
        "type": "crop_products"
    },
    {
        "id": 11,
        "question": "ยากำจัดวัชพืชในอ้อย แนะนำหน่อย",
        "expected_product": "ราเซอร์",
        "category": "กำจัดวัชพืช",
        "type": "recommend_weed"
    },

    # --- กลุ่ม 4: ถามเฉพาะเจาะจง (specific detail) ---
    {
        "id": 12,
        "question": "พรีดิคท์ ใช้กับทุเรียนช่วงไหน",
        "expected_product": "พรีดิคท์",
        "category": "ปุ๋ยและสารบำรุง",
        "type": "usage_period"
    },
    {
        "id": 13,
        "question": "ไฮซีส ใช้กำจัดหนอนอะไรได้บ้าง",
        "expected_product": "ไฮซีส",
        "category": "กำจัดแมลง",
        "type": "product_info"
    },
    {
        "id": 14,
        "question": "อิมิดาโกลด์ 70 ผสมน้ำกี่ซีซีต่อน้ำ 20 ลิตร",
        "expected_product": "อิมิดาโกลด์ 70",
        "category": "กำจัดแมลง",
        "type": "usage_rate"
    },

    # --- กลุ่ม 5: โรคเฉพาะ (disease-specific) ---
    {
        "id": 15,
        "question": "โรครากเน่าโคนเน่าทุเรียน ใช้ยาอะไร",
        "expected_product": "คาริสมา",
        "category": "ป้องกันโรค",
        "type": "recommend_disease"
    },
    {
        "id": 16,
        "question": "ราน้ำค้างในข้าวโพด ป้องกันด้วยอะไร",
        "expected_product": "โทมาฮอค",
        "category": "ป้องกันโรค",
        "type": "recommend_disease"
    },
    {
        "id": 17,
        "question": "โรคใบจุดสีน้ำตาลในข้าว ใช้สารอะไร",
        "expected_product": "เทอราโน่",
        "category": "ป้องกันโรค",
        "type": "recommend_disease"
    },

    # --- กลุ่ม 6: คำถามแบบผสม ---
    {
        "id": 18,
        "question": "เพลี้ยกระโดดสีน้ำตาลในนาข้าว แนะนำยาหน่อย",
        "expected_product": "แจ๊ส",
        "category": "กำจัดแมลง",
        "type": "recommend_insect"
    },
    {
        "id": 19,
        "question": "เบนซาน่า เอฟ ใช้กับพืชอะไรได้บ้าง",
        "expected_product": "เบนซาน่า เอฟ",
        "category": "ป้องกันโรค",
        "type": "product_info"
    },
    {
        "id": 20,
        "question": "ชุดกล่องม่วง คืออะไร มีอะไรบ้าง",
        "expected_product": "ชุด กล่องม่วง",
        "category": "กำจัดแมลง",
        "type": "what_is"
    },
]


async def run_single_test(question_data: dict) -> dict:
    """Run a single test question and return result"""
    from app.services.agentic_rag import get_agentic_rag

    q_id = question_data["id"]
    question = question_data["question"]
    expected = question_data["expected_product"]
    category = question_data["category"]

    print(f"\n{'='*60}")
    print(f"Q{q_id}: {question}")
    print(f"  Expected product: {expected} ({category})")
    print(f"  Type: {question_data['type']}")
    print(f"{'─'*60}")

    try:
        rag = get_agentic_rag()
        response = await rag.process(question, context="", user_id="test-20q")
        answer = response.answer or ""

        # Check results
        has_expected = expected.lower() in answer.lower() if expected else True
        has_emoji = any(e in answer for e in ['🦠', '🌿', '💊', '📋', '⚖️', '📅', '⚠️', '💡', '🔍', '🔢'])
        has_divider = '━' in answer
        has_no_brackets = '[' not in answer or 'ข้อมูล' not in answer  # [หัวข้อ] format removed
        is_not_error = 'ขออภัย' not in answer[:20] and 'เกิดข้อผิดพลาด' not in answer

        # Print answer (truncated)
        print(f"\n  Answer ({len(answer)} chars):")
        for line in answer[:500].split('\n'):
            print(f"    {line}")
        if len(answer) > 500:
            print(f"    ... (truncated)")

        # Print checks
        print(f"\n  Checks:")
        print(f"    {'✓' if has_expected else '✗'} Contains expected product: {expected}")
        print(f"    {'✓' if has_emoji else '✗'} Has emoji headers")
        print(f"    {'✓' if has_divider else '○'} Has ━ dividers")
        print(f"    {'✓' if is_not_error else '✗'} Not an error response")

        return {
            "id": q_id,
            "question": question,
            "expected": expected,
            "has_expected": has_expected,
            "has_emoji": has_emoji,
            "has_divider": has_divider,
            "is_not_error": is_not_error,
            "answer_length": len(answer),
            "passed": has_expected and is_not_error,
        }

    except Exception as e:
        print(f"\n  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {
            "id": q_id,
            "question": question,
            "expected": expected,
            "has_expected": False,
            "has_emoji": False,
            "has_divider": False,
            "is_not_error": False,
            "answer_length": 0,
            "passed": False,
            "error": str(e),
        }


async def main():
    print("=" * 60)
    print("TEST: 20 Product Questions via products table")
    print("=" * 60)

    # Verify environment
    from app.config import SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY
    if not all([SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY]):
        print("ERROR: Missing environment variables (SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY)")
        return

    # Verify products table connectivity
    from app.services.services import supabase_client
    if not supabase_client:
        print("ERROR: Supabase client not initialized")
        return

    try:
        count_result = supabase_client.table('products').select('id', count='exact').execute()
        print(f"\nProducts in DB: {count_result.count}")
    except Exception as e:
        print(f"ERROR checking products table: {e}")
        return

    # Run all 20 tests
    results = []
    for q_data in TEST_QUESTIONS:
        result = await run_single_test(q_data)
        results.append(result)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    has_emoji_count = sum(1 for r in results if r["has_emoji"])
    has_divider_count = sum(1 for r in results if r["has_divider"])
    has_expected_count = sum(1 for r in results if r["has_expected"])
    not_error_count = sum(1 for r in results if r["is_not_error"])

    print(f"\nOverall: {passed}/{total} passed")
    print(f"  - Found expected product: {has_expected_count}/{total}")
    print(f"  - Has emoji headers:      {has_emoji_count}/{total}")
    print(f"  - Has ━ dividers:         {has_divider_count}/{total}")
    print(f"  - Not error response:     {not_error_count}/{total}")

    # Detail table
    print(f"\n{'ID':>3} {'Pass':>5} {'Product':>5} {'Emoji':>5} {'Divider':>7} {'Len':>5}  Question")
    print(f"{'─'*3} {'─'*5} {'─'*5} {'─'*5} {'─'*7} {'─'*5}  {'─'*30}")
    for r in results:
        p = '✓' if r['passed'] else '✗'
        prod = '✓' if r['has_expected'] else '✗'
        emo = '✓' if r['has_emoji'] else '✗'
        div = '✓' if r['has_divider'] else '○'
        print(f"{r['id']:>3} {p:>5} {prod:>5} {emo:>5} {div:>7} {r['answer_length']:>5}  {r['question'][:40]}")

    if passed == total:
        print(f"\n✓ ALL {total} TESTS PASSED!")
    else:
        print(f"\n⚠ {total - passed} tests failed out of {total}")
        failed = [r for r in results if not r["passed"]]
        print("\nFailed questions:")
        for r in failed:
            print(f"  Q{r['id']}: {r['question']}")
            if r.get('error'):
                print(f"       Error: {r['error']}")
            elif not r['has_expected']:
                print(f"       Missing expected product: {r['expected']}")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
