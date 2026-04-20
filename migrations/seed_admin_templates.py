"""
Seed admin_templates table with default templates.
รัน: python migrations/seed_admin_templates.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()
os.environ.setdefault("ADMIN_PASSWORD", "seedpass-only-for-script")
os.environ.setdefault("SECRET_KEY", "seed-key-for-script-1234567890")

from app.dependencies import supabase_client


SEEDS = [
    {
        "title": "ขอบคุณที่รอ + ส่งข้อมูลที่ถูกต้อง",
        "category": "handoff",
        "content": (
            "ขออภัยในความล่าช้าค่ะ ขอตอบคำถาม {product_name} ให้คุณลูกค้าดังนี้ค่ะ\n\n"
            "{custom_answer}\n\n"
            "หากต้องการข้อมูลเพิ่มเติม สอบถามได้เลยนะคะ 😊"
        ),
        "placeholders": ["product_name", "custom_answer"],
    },
    {
        "title": "ไม่มีข้อมูลสินค้านี้ในระบบ",
        "category": "handoff",
        "content": (
            'ขออภัยค่ะ น้องลัดดายังไม่มีข้อมูลของ "{product_name}" ในระบบ '
            "กรุณาติดต่อเจ้าหน้าที่ ไอ ซี พี ลัดดา โดยตรงค่ะ 🙏"
        ),
        "placeholders": ["product_name"],
    },
    {
        "title": "ปรึกษาเจ้าหน้าที่โดยตรง",
        "category": "handoff",
        "content": (
            "สำหรับคำถามนี้ แนะนำให้ปรึกษาเจ้าหน้าที่ ไอ ซี พี ลัดดา "
            "โดยตรงเพื่อคำแนะนำที่เหมาะสมกับสภาพพืชของคุณลูกค้านะคะ 🙏"
        ),
        "placeholders": [],
    },
    {
        "title": "อัตราการใช้ทั่วไป (กรอกเอง)",
        "category": "usage",
        "content": (
            "สำหรับ {product_name} ใช้กับ{plant}:\n"
            "• อัตราใช้: {rate}\n"
            "• วิธีใช้: {how_to_use}\n"
            "• ช่วงใช้: {when}\n\n"
            "กรุณาอ่านฉลากก่อนใช้ทุกครั้งนะคะ 😊"
        ),
        "placeholders": ["product_name", "plant", "rate", "how_to_use", "when"],
    },
    {
        "title": "ขอบคุณที่สอบถาม",
        "category": "general",
        "content": (
            "ขอบคุณที่สอบถาม น้องลัดดายินดีให้บริการค่ะ "
            "ถ้ามีคำถามเพิ่มเติมสามารถสอบถามได้ตลอดนะคะ 😊"
        ),
        "placeholders": [],
    },
    {
        "title": "คำนวณอัตราการใช้ (Handoff)",
        "category": "handoff",
        "content": (
            "สำหรับการคำนวณอัตราการใช้ให้ตรงกับพื้นที่ของคุณลูกค้า "
            "แนะนำให้ปรึกษาเจ้าหน้าที่ ไอ ซี พี ลัดดา โดยตรงค่ะ 🙏"
        ),
        "placeholders": [],
    },
    {
        "title": "สอบถามราคาสินค้า",
        "category": "handoff",
        "content": (
            "สำหรับข้อมูลราคา กรุณาติดต่อสอบถามจากเจ้าหน้าที่ ไอ ซี พี ลัดดา "
            "หรือตัวแทนจำหน่ายในพื้นที่โดยตรงค่ะ 🙏"
        ),
        "placeholders": [],
    },
]


async def seed():
    if supabase_client is None:
        print("ERROR: supabase_client not available — check env vars")
        return

    # Only insert if title doesn't already exist (idempotent)
    existing = supabase_client.table("admin_templates").select("title").execute()
    existing_titles = {row["title"] for row in (existing.data or [])}

    new_seeds = [s for s in SEEDS if s["title"] not in existing_titles]
    if not new_seeds:
        print(f"All {len(SEEDS)} seeds already present — no insert needed.")
        return

    result = (
        supabase_client.table("admin_templates").insert(new_seeds).execute()
    )
    inserted = len(result.data or [])
    print(f"Inserted {inserted} templates (skipped {len(SEEDS) - inserted} duplicates)")
    for row in result.data or []:
        print(f"  [{row['id']}] {row['category']:<8} | {row['title']}")


if __name__ == "__main__":
    asyncio.run(seed())
