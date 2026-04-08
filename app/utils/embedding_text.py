"""
Shared function สร้าง embedding text จาก product data
ใช้ร่วมกันระหว่าง generate_embeddings.py และ sync_sheets_to_supabase.py
*** ห้ามเขียนซ้ำที่อื่น — ต้อง import จากที่นี่เท่านั้น ***
"""


def build_embedding_text(product: dict) -> str:
    """สร้าง text สำหรับ embedding จากข้อมูลสินค้า"""
    text_parts = [
        f"ชื่อสินค้า: {product.get('product_name', '')}",
        f"สารสำคัญ: {product.get('active_ingredient', '')}",
        f"สารกำจัดเชื้อรา: {product.get('fungicides', '')}",
        f"สารกำจัดแมลง: {product.get('insecticides', '')}",
        f"สารกำจัดวัชพืช: {product.get('herbicides', '')}",
        f"สารกระตุ้นชีวภาพ: {product.get('biostimulant', '')}",
        f"ปุ๋ยธาตุอาหาร: {product.get('fertilizer', '')}",
        f"ฮอร์โมนพืช: {product.get('pgr_hormones', '')}",
        f"จุดเด่น: {product.get('selling_point', '')}",
        f"ใช้ได้กับพืช: {product.get('applicable_crops', '')}",
        f"กลุ่มสาร: {product.get('product_group', '') or product.get('chemical_group_rac', '')}",
        f"ข้อควรระวัง: {product.get('caution_notes', '')}",
    ]
    return " | ".join([p for p in text_parts if p])
