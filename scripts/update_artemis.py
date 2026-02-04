"""
Update/Upsert อาร์เทมีส (Artemis) product in Supabase
"""
import os
import json
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)


def generate_embedding(text: str) -> list:
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding


def update_artemis():
    product_data = {
        "product_name": "อาร์เทมีส",
        "active_ingredient": "ไดฟีโนโคนาโซล + อะซ๊อคซีสโตรบิน (DIFENOCONAZOLE + AZOXYSTROBIN 12.5%+20% W/V SC)",
        "product_category": "ป้องกันโรค",
        "target_pest": "โรคใบจุดสีน้ำตาล โรคใบขีดสีน้ำตาล โรคเมล็ดด่าง ในนาข้าว",
        "applicable_crops": "นาข้าว ไม้ผล",
        "how_to_use": "ผสมน้ำตามอัตราที่แนะนำ แล้วทำการฉีดพ่นที่ต้น ให้ทั่วบริเวณทรงพุ่ม",
        "usage_rate": "ในไม้ผล(ทุเรียน) ใช้ 200 ซีซีต่อ 200 ลิตร ในนาข้าว ใช้ 50 ซีซีต่อไร่",
        "usage_period": "",
        "link_product": "http://system.icpladda.com/CDN//difeno_azoxystrobin_%E0%B8%AD%E0%B8%B2%E0%B8%A3%E0%B9%8C%E0%B9%80%E0%B8%97%E0%B8%A1%E0%B8%B4%E0%B8%AA_07042025_213519.pdf",
        "pathogen_type": "เชื้อรา",
    }

    # Generate embedding
    embedding_text = (
        f"ชื่อสินค้า: อาร์เทมีส | "
        f"ประเภท: ยากำจัดเชื้อรา โรคพืช | "
        f"สารสำคัญ: ไดฟีโนโคนาโซล + อะซ๊อคซีสโตรบิน | "
        f"ศัตรูพืชที่กำจัดได้: โรคใบจุดสีน้ำตาล โรคใบขีดสีน้ำตาล โรคเมล็ดด่าง ในนาข้าว | "
        f"ใช้ได้กับพืช: นาข้าว ไม้ผล ทุเรียน | "
        f"กลุ่มสาร: Fungicide"
    )

    print("Generating embedding...")
    embedding = generate_embedding(embedding_text)
    if not embedding:
        print("Failed to generate embedding!")
        return

    product_data["embedding"] = embedding

    # Check if อาร์เทมีส already exists
    print("Checking existing data...")
    existing = supabase.table("products").select("id").eq("product_name", "อาร์เทมีส").execute()

    if existing.data:
        # Update existing
        row_id = existing.data[0]["id"]
        print(f"Found existing record id={row_id}, updating...")
        result = supabase.table("products").update(product_data).eq("id", row_id).execute()
        print(f"Updated successfully! id={row_id}")
    else:
        # Insert new
        print("No existing record, inserting new...")
        result = supabase.table("products").insert(product_data).execute()
        print(f"Inserted successfully! id={result.data[0]['id']}")

    # Verify
    verify = supabase.table("products").select("id, product_name, active_ingredient, target_pest, usage_rate").eq("product_name", "อาร์เทมีส").execute()
    if verify.data:
        row = verify.data[0]
        print(f"\nVerification:")
        print(f"  id: {row['id']}")
        print(f"  product_name: {row['product_name']}")
        print(f"  active_ingredient: {row['active_ingredient']}")
        print(f"  target_pest: {row['target_pest']}")
        print(f"  usage_rate: {row['usage_rate']}")


if __name__ == "__main__":
    print("=" * 60)
    print("Updating อาร์เทมีส (Artemis) in Supabase")
    print("=" * 60)
    update_artemis()
    print("\nDone!")
