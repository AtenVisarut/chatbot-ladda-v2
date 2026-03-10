"""
Reformat insecticides column: Format A (flat) → Format B (crop-tagged)

8 products need reformatting. Each mapping is sourced from:
- selling_point (SP)
- usage_period (UP)
- applicable_crops (AC)
- pest name implies crop (e.g. หนอนกอ = rice pest, หนอนกออ้อย = sugarcane)

Run: python migrations/reformat_insecticides.py
"""

import os
import sys
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.dependencies import supabase_client, openai_client


# ============================================================================
# MAPPING: product_id → new insecticides text
# Each line documents the SOURCE of the pest→crop association
# ============================================================================

UPDATES = {
    # [1] โมเดิน 50
    # SP: "โดยเฉพาะทุเรียน เด่นที่สุดในการกำจัดเพลี้ยไฟ เพลี้ยจักจั่นฝอย เพลี้ยไก่แจ้"
    # UP: "มันสำปะหลัง:กำจัดแมลงหวี่ขาว เพลี้ยแป้งลาย เพลี้ยแป้งมันสำปะหลังสีเทา และไรแดงหม่อน"
    1: "เพลี้ยไฟในทุเรียน, เพลี้ยจักจั่นฝอยในทุเรียน, เพลี้ยไก่แจ้ในทุเรียน, "
       "แมลงหวี่ขาวในมันสำปะหลัง, เพลี้ยแป้งลายในมันสำปะหลัง, ไรแดงหม่อนในมันสำปะหลัง",

    # [8] นาแดน - จี
    # AC: "นาข้าว นาหว่านน้ำตม นาดำ" (rice-only)
    # SP: "หนอนกอข้าว เช่น หนอนกอแถบลาย หนอนกอสีครีม หนอนกอสีชมพู หนอนกอลายม่วง"
    8: "หนอนกอแถบลายในนาข้าว, หนอนกอสีครีมในนาข้าว, "
       "หนอนกอสีชมพูในนาข้าว, หนอนกอลายม่วงในนาข้าว",

    # [14] กะรัต 35
    # AC: "ทุเรียน, มะม่วง, ข้าวโพด, อ้อย, ถั่วฝักยาว, พริก, ผัก (ห้ามใช้ในนาข้าว)"
    # "หนอนเจาะต้นออย" = หนอนเจาะต้นอ้อย (typo in original)
    # เพลี้ยอ่อน = common on ไม้ผล + พืชผัก (AC lists both)
    # แมลงและหนอนกัดกินใบดอกผล = ไม้ผล (target is ใบ ดอก ผล)
    14: "เพลี้ยอ่อนในไม้ผล, เพลี้ยอ่อนในพืชผัก, หนอนเจาะต้นอ้อย, "
        "แมลงและหนอนกัดกินใบดอกและผลในไม้ผล",

    # [25] แจ๊ส 50 อีซี
    # UP: "นาข้าว : ใช้กำจัดเพลี้ยกระโดดสีน้ำตาล ... ไม้ผล : ป้องกันแมลงได้ในทุกระยะ"
    # เพลี้ยกระโดดสีน้ำตาล/หลังขาว = rice-specific pests (BPH/WBPH)
    # เพลี้ยจักจั่นเขียว = rice leafhopper
    # เพลี้ยจักจั่น = ไม้ผล (from UP context)
    25: "เพลี้ยกระโดดสีน้ำตาลในนาข้าว, เพลี้ยกระโดดหลังขาวในนาข้าว, "
        "เพลี้ยจักจั่นเขียวในนาข้าว, เพลี้ยจักจั่นในไม้ผล",

    # [27] ซีเอ็มจี
    # AC: "ใช้ได้ทุกพืช ยกเว้นห้ามใช้ในนาข้าว"
    # SP: "กำจัดแมลงได้ดีหลากหลายชนิด" (broadspectrum)
    # No crop-specific pest data → tag with main crop groups from AC
    27: "เพลี้ยไฟในไม้ผล, เพลี้ยไฟในพืชผัก, หนอนในไม้ผล, "
        "หนอนในพืชผัก, แมลงปากกัดและปากดูดต่างๆ",

    # [34] แมสฟอร์ด
    # AC: "ทุเรียน, ข้าว, ลำไย, ส้ม, ข้าวโพด, หอมแดง, ผักคะน้า..."
    # SP: "กำจัดเพลี้ยแป้งได้ดี" (specialty)
    # เพลี้ยไฟ = common on ทุเรียน + ลำไย (AC has both)
    # เพลี้ยแป้ง = common on ทุเรียน + ลำไย (AC has both)
    # เพลี้ยหอย = common on ส้ม + ทุเรียน (AC has both)
    34: "เพลี้ยไฟในทุเรียน, เพลี้ยไฟในลำไย, "
        "เพลี้ยแป้งในทุเรียน, เพลี้ยแป้งในลำไย, "
        "เพลี้ยหอยในทุเรียน, เพลี้ยหอยในส้ม",

    # [36] ไพรซีน
    # AC: "นาข้าว, ทุเรียน" (only 2 crops)
    # SP: "เพลี้ยจั่กจั่น เพลี้ยกระโดดสีน้ำตาล เพลี้ยจักจั่นฝอย"
    # เพลี้ยกระโดดสีน้ำตาล/หลังขาว = rice-specific (BPH/WBPH)
    # เพลี้ยจักจั่นฝอย = durian pest (remaining crop after rice)
    # เพลี้ยจักจั่น = ทุเรียน (SP context + AC)
    36: "เพลี้ยกระโดดสีน้ำตาลในนาข้าว, เพลี้ยกระโดดหลังขาวในนาข้าว, "
        "เพลี้ยจักจั่นฝอยในทุเรียน, เพลี้ยจักจั่นในทุเรียน",

    # [38] บลูไวท์
    # AC: "ทุเรียน, มะม่วง, ลำไย, ผัก, อ้อย"
    # หนอนกออ้อย → อ้อย (clear from pest name)
    # หนอนผีเสื้อ = common on ไม้ผล + ผัก (AC has both)
    # เพลี้ยไฟ = common on ทุเรียน + มะม่วง (AC has both)
    # ไร = common on ทุเรียน + ลำไย (AC has both)
    38: "หนอนผีเสื้อในไม้ผล, หนอนผีเสื้อในพืชผัก, หนอนกออ้อย, "
        "เพลี้ยไฟในทุเรียน, เพลี้ยไฟในมะม่วง, ไรในทุเรียน, ไรในลำไย",

    # [40] เมลสัน
    # AC: "ปลอดภัย ในทุกพืช"
    # SP: "คุมไข่ไร ควบคุมไรแดงได้นานกว่า 30 วัน"
    # UP: "ใช้ป้องกันกำจัดตระกูลไร ในทุกระยะ"
    # ไรแดง = common on ทุเรียน, ลำไย, พืชผัก
    40: "ไรแดงในทุเรียน, ไรแดงในไม้ผล, ไรแดงในพืชผัก",
}


def show_changes():
    """Show proposed changes before applying."""
    print("=" * 70)
    print("PROPOSED INSECTICIDES COLUMN CHANGES")
    print("=" * 70)

    for pid, new_text in UPDATES.items():
        result = supabase_client.table('products2') \
            .select('product_name, insecticides') \
            .eq('id', pid) \
            .execute()

        if not result.data:
            print(f"\n[{pid}] NOT FOUND!")
            continue

        p = result.data[0]
        old_text = (p.get('insecticides') or '').strip()
        print(f"\n[{pid}] {p['product_name']}")
        print(f"  OLD: {old_text[:120]}")
        print(f"  NEW: {new_text[:120]}")

    print("\n" + "=" * 70)


def update_insecticides():
    """Update insecticides column in database."""
    print("\nUpdating insecticides column...")

    for pid, new_text in UPDATES.items():
        result = supabase_client.table('products2') \
            .update({'insecticides': new_text}) \
            .eq('id', pid) \
            .execute()

        name = result.data[0]['product_name'] if result.data else f"ID={pid}"
        print(f"  Updated [{pid}] {name}")

    print(f"\nDone! Updated {len(UPDATES)} products.")


async def regenerate_embeddings():
    """Regenerate embeddings for updated products using text-embedding-3-small."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = "text-embedding-3-small"

    print(f"\nRegenerating embeddings with {model}...")

    for pid in UPDATES.keys():
        # Fetch full product data
        result = supabase_client.table('products2') \
            .select('*') \
            .eq('id', pid) \
            .execute()

        if not result.data:
            print(f"  [{pid}] NOT FOUND — skipping")
            continue

        p = result.data[0]

        # Build embedding text (same template as generate_embeddings.py)
        embed_text = (
            f"ชื่อสินค้า: {p.get('product_name', '')} | "
            f"ชื่อสามัญ: {p.get('common_name_th', '')} | "
            f"สารสำคัญ: {p.get('active_ingredient', '')} | "
            f"ประเภท: {p.get('product_category', '')} | "
            f"กำจัดเชื้อรา: {(p.get('fungicides') or '')[:200]} | "
            f"กำจัดแมลง: {(p.get('insecticides') or '')[:200]} | "
            f"กำจัดวัชพืช: {(p.get('herbicides') or '')[:200]} | "
            f"สารชีวภัณฑ์: {(p.get('biostimulant') or '')[:200]} | "
            f"ฮอร์โมนพืช: {(p.get('pgr_hormones') or '')[:200]} | "
            f"พืชที่ใช้ได้: {(p.get('applicable_crops') or '')[:200]} | "
            f"วิธีใช้: {(p.get('how_to_use') or '')[:200]} | "
            f"ช่วงเวลาใช้: {(p.get('usage_period') or '')[:200]} | "
            f"อัตราใช้: {(p.get('usage_rate') or '')[:100]} | "
            f"จุดเด่น: {(p.get('selling_point') or '')[:200]}"
        )

        # Generate embedding
        response = await client.embeddings.create(
            input=embed_text,
            model=model,
        )
        embedding = response.data[0].embedding

        # Update in DB
        supabase_client.table('products2') \
            .update({'embedding': embedding}) \
            .eq('id', pid) \
            .execute()

        print(f"  [{pid}] {p['product_name']} — embedding regenerated ({len(embedding)} dims)")

    print(f"\nDone! Regenerated embeddings for {len(UPDATES)} products.")


if __name__ == "__main__":
    # Step 1: Show proposed changes
    show_changes()

    # Step 2: Confirm
    confirm = input("\nApply changes? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Aborted.")
        sys.exit(0)

    # Step 3: Update DB
    update_insecticides()

    # Step 4: Regenerate embeddings
    asyncio.run(regenerate_embeddings())

    print("\n✓ All done! Insecticides reformatted + embeddings regenerated.")
