"""
Script: อัปเดต target_pest + regenerate embedding สำหรับ คาริสมา
"""
import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

os.chdir("C:\\clone_chatbot_ick\\Chatbot-ladda")
sys.path.insert(0, "C:\\clone_chatbot_ick\\Chatbot-ladda")

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
from app.config import OPENAI_API_KEY
from app.services.services import supabase_client

openai_client = OpenAI(api_key=OPENAI_API_KEY)

# ============================================================
# แก้ไขตรงนี้
# ============================================================

PRODUCT_ID = 264  # คาริสมา

# target_pest ใหม่ (เพิ่ม ไฟท็อปธอร่า ให้ชัดเจน)
NEW_TARGET_PEST = """
(ทุเรียน) ไฟท็อปธอร่า รากเน่า โคนเน่า Phytophthora palmivora
(มันฝรั่ง) ไฟท็อปธอร่า รากเน่า โคนเน่า
(พืชผัก) รากเน่าโคนเน่า Pythium spp.
(ทั่วไป) โรครากเน่าโคนเน่าจากเชื้อราชั้นต่ำในดิน
""".strip()

# embedding text — รวมข้อมูลสำคัญทั้งหมด
EMBEDDING_TEXT = """
ชื่อสินค้า: คาริสมา Charisma |
ประเภท: ยาป้องกันกำจัดเชื้อรา Fungicide |
สารสำคัญ: โพรพาโมคาร์บ ไฮโดรคลอไรด์ PROPAMOCARB HYDROCHLORIDE 72.2% |
โรค: ไฟท็อปธอร่า ไฟท็อป Phytophthora รากเน่า โคนเน่า root rot Pythium |
พืช: ทุเรียน มันฝรั่ง พืชผัก พืชไร่ ไม้ผล |
จุดเด่น: สูตร SL น้ำใส ปลอดภัย ออกฤทธิ์ไว ต้นฟื้นเร็ว ใช้ได้ทั้งพ่นทางใบหรือราดดิน
""".strip()

# ============================================================
# ไม่ต้องแก้ไขด้านล่างนี้
# ============================================================

def generate_embedding(text: str) -> list:
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding


def main():
    print("=" * 60)
    print("อัปเดต คาริสมา — target_pest + embedding")
    print("=" * 60)

    # 1. ดึงข้อมูลปัจจุบัน
    result = supabase_client.table('products').select('product_name, target_pest').eq('id', PRODUCT_ID).execute()
    if not result.data:
        print(f"ERROR: ไม่เจอสินค้า ID={PRODUCT_ID}!")
        return

    current = result.data[0]
    print(f"\nProduct: {current['product_name']}")
    print(f"\n[BEFORE] target_pest:\n{current['target_pest']}")
    print(f"\n[AFTER] target_pest:\n{NEW_TARGET_PEST}")

    # 2. สร้าง embedding ใหม่
    print("\n" + "-" * 40)
    print("Generating embedding...")
    embedding = generate_embedding(EMBEDDING_TEXT)
    if not embedding:
        print("ERROR: Failed to generate embedding!")
        return
    print(f"Embedding generated: {len(embedding)} dimensions")

    # 3. อัปเดต Supabase
    print("\nUpdating Supabase...")
    update_data = {
        "target_pest": NEW_TARGET_PEST,
        "embedding": embedding,
    }

    supabase_client.table('products').update(update_data).eq('id', PRODUCT_ID).execute()
    print("Updated successfully!")

    # 4. Verify
    print("\n" + "-" * 40)
    print("Verifying...")
    verify = supabase_client.table('products').select('product_name, target_pest').eq('id', PRODUCT_ID).execute()
    if verify.data:
        print(f"target_pest:\n{verify.data[0]['target_pest']}")

        # Check keywords
        keywords = ['ไฟท็อปธอร่า', 'Phytophthora', 'รากเน่า', 'โคนเน่า']
        print(f"\nKeyword check:")
        for kw in keywords:
            found = kw in verify.data[0]['target_pest']
            status = "✓" if found else "✗"
            print(f"  {status} {kw}")

    print("\n" + "=" * 60)
    print("DONE!")
    print("=" * 60)


if __name__ == "__main__":
    main()
