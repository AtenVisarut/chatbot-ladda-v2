"""
Text Message Templates
สำหรับ Chatbot Ladda - Plant Disease Detection
ใช้แทน Flex Messages ทั้งหมด - return string เท่านั้น
"""

from typing import Dict, List, Optional

from app.prompts import WELCOME_MESSAGE


# =============================================================================
# Welcome & Registration Messages
# =============================================================================

def get_welcome_text() -> str:
    """ข้อความต้อนรับ user ใหม่"""
    return WELCOME_MESSAGE








# =============================================================================
# Help & Guide Messages
# =============================================================================

def get_help_menu_text() -> str:
    """เมนูช่วยเหลือ"""
    return (
        "📋 เมนูช่วยเหลือ\n"
        "━━━━━━━━━━━━━━━\n\n"
        "น้องลัดดาช่วยอะไรได้บ้าง:\n\n"
        "🌱 ถามเรื่องสินค้า ICP\n"
        "- ใช้สารตัวไหนดีกับพืช/โรค/แมลง\n"
        "- สารสำคัญ กลุ่มสาร (IRAC, FRAC)\n"
        "- ใช้กับพืชอะไรได้บ้าง ช่วงไหนควรใช้\n\n"
        "คำสั่งอื่นๆ:\n"
        "- พิมพ์ \"ดูผลิตภัณฑ์\" เพื่อดูสินค้า\n"
        "- พิมพ์ \"วิธีใช้งาน\" เพื่อดูคู่มือ\n"
        "- พิมพ์ \"ล้างความจำ\" เพื่อเริ่มใหม่\n\n"
        "💬 หรือพิมพ์ถามมาได้เลยนะคะ"
    )


def get_usage_guide_text() -> str:
    """คู่มือการใช้งานแบบละเอียด"""
    return (
        "💬 ถามข้อมูลสินค้า ICP กับน้องลัดดาได้นะคะ:\n"
        "- \"เพลี้ยไฟใช้สารตัวไหนดี\"\n"
        "- \"ระยะแตกใบอ่อนทุเรียน มีสารไหนช่วยได้\"\n"
        "- \"อาร์ดอน ใช้กับพืชอะไรได้บ้าง\"\n"
        "- \"หนอนกระทู้ข้าวโพด ใช้อะไรกำจัด\"\n\n"
        "ลองพิมพ์ถามมาได้เลยค่ะ น้องลัดดาพร้อมช่วยเลยนะคะ 😊"
    )


def get_product_catalog_text() -> str:
    """รายการผลิตภัณฑ์"""
    return (
        "📦 ผลิตภัณฑ์ ICP Ladda\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "หมวดหมู่ผลิตภัณฑ์:\n"
        "🐛 ยาฆ่าแมลง\n"
        "🍄 ยาฆ่าเชื้อรา\n"
        "🌿 ยาฆ่าหญ้า\n"
        "💧 ปุ๋ยและสารเสริม\n\n"
        "ดูรายละเอียดเพิ่มเติม:\n"
        "🔗 https://www.icpladda.com/about/\n\n"
        "💬 หรือพิมพ์ถามชื่อผลิตภัณฑ์ได้เลยค่ะ"
    )


# =============================================================================
# Disease Detection Flow Messages
# =============================================================================

def get_initial_questions_text() -> str:
    """ข้อความถามชนิดพืช (Step 1/2)"""
    return (
        "🌱 ขั้นตอนที่ 1/2: เลือกชนิดพืช\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "กรุณาพิมพ์ชนิดพืชที่ต้องการวิเคราะห์:\n\n"
        "- ข้าว\n"
        "- ทุเรียน\n"
        "- ข้าวโพด\n"
        "- มันสำปะหลัง\n"
        "- อ้อย\n"
        "- อื่นๆ (พิมพ์ชื่อพืช)\n\n"
        "พิมพ์ \"ยกเลิก\" เพื่อยกเลิก"
    )


def get_other_plant_prompt_text() -> str:
    """ข้อความให้พิมพ์ชื่อพืชอื่น"""
    return (
        "🌿 กรุณาพิมพ์ชื่อพืชที่ต้องการวิเคราะห์ค่ะ\n\n"
        "ตัวอย่าง: มะม่วง, ลำไย, ส้ม, พริก, มะเขือเทศ, ยางพารา, ปาล์ม\n\n"
        "พิมพ์ \"ยกเลิก\" เพื่อยกเลิก"
    )


def get_plant_type_retry_text() -> str:
    """ข้อความแจ้งเตือนเมื่อพิมพ์ชนิดพืชไม่ถูกต้อง"""
    return (
        "❌ ไม่พบชนิดพืชที่ระบุ\n\n"
        "กรุณาพิมพ์ชนิดพืชใหม่:\n"
        "- ข้าว\n"
        "- ทุเรียน\n"
        "- ข้าวโพด\n"
        "- มันสำปะหลัง\n"
        "- อ้อย\n"
        "- อื่นๆ (พิมพ์ชื่อพืช)\n\n"
        "พิมพ์ \"ยกเลิก\" เพื่อยกเลิก"
    )


def get_growth_stage_question_text(plant_type: str) -> str:
    """ข้อความถามระยะการเติบโต (Step 2/2) ตามชนิดพืช"""
    stages = _get_growth_stages_for_plant(plant_type)
    stages_text = "\n".join(f"- {s}" for s in stages)

    return (
        f"🌱 ขั้นตอนที่ 2/2: ระยะการเติบโตของ{plant_type}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"กรุณาพิมพ์ระยะการเติบโต:\n\n"
        f"{stages_text}\n\n"
        "หรือพิมพ์ \"ไม่ทราบ\" ถ้าไม่แน่ใจ\n"
        "พิมพ์ \"ยกเลิก\" เพื่อยกเลิก"
    )


def _get_growth_stages_for_plant(plant_type: str) -> list:
    """ดึงรายการระยะการเติบโตตามชนิดพืช"""
    plant_lower = plant_type.lower() if plant_type else ""

    if "ข้าวโพด" in plant_lower:
        return ["งอก/ต้นอ่อน", "เจริญเติบโต", "ออกดอก", "ติดฝัก"]
    elif "ข้าว" in plant_lower:
        return ["กล้า/ปักดำ", "แตกกอ", "ตั้งท้อง", "ออกรวง"]
    elif "มันสำปะหลัง" in plant_lower or "มัน" in plant_lower:
        return ["ปลูกใหม่", "เจริญเติบโต", "สะสมแป้ง", "เก็บเกี่ยว"]
    elif "อ้อย" in plant_lower:
        return ["งอก/แตกกอ", "ย่างปล้อง", "สะสมน้ำตาล", "เก็บเกี่ยว"]
    elif "ทุเรียน" in plant_lower:
        return ["ก่อนออกดอก", "ออกดอก", "ติดผล", "เก็บเกี่ยว"]
    elif "มะม่วง" in plant_lower:
        return ["ก่อนออกดอก", "ออกดอก", "ติดผล", "เก็บเกี่ยว"]
    elif "ลำไย" in plant_lower:
        return ["ก่อนออกดอก", "ออกดอก", "ติดผล", "เก็บเกี่ยว"]
    elif "ส้ม" in plant_lower or "มะนาว" in plant_lower:
        return ["ก่อนออกดอก", "ออกดอก", "ติดผล", "เก็บเกี่ยว"]
    elif "ยางพารา" in plant_lower or "ยาง" in plant_lower:
        return ["ต้นอ่อน", "ก่อนเปิดกรีด", "เปิดกรีด", "บำรุงต้น"]
    elif "ปาล์ม" in plant_lower:
        return ["ต้นอ่อน", "ก่อนออกทลาย", "ออกทลาย", "บำรุงต้น"]
    elif "พริก" in plant_lower:
        return ["ต้นอ่อน", "เจริญเติบโต", "ออกดอก", "เก็บเกี่ยว"]
    elif "มะเขือเทศ" in plant_lower:
        return ["ต้นอ่อน", "เจริญเติบโต", "ออกดอก", "เก็บเกี่ยว"]
    elif any(v in plant_lower for v in ["ผัก", "มะเขือ", "แตง", "กะหล่ำ", "คะน้า", "ผักกาด"]):
        return ["ต้นอ่อน", "เจริญเติบโต", "ก่อนเก็บเกี่ยว"]
    else:
        return ["ต้นอ่อน", "เจริญเติบโต", "ออกดอก/ผล", "เก็บเกี่ยว"]


def get_analyzing_text(with_info: bool = False) -> str:
    """ข้อความแจ้งกำลังวิเคราะห์"""
    if with_info:
        return "🔬 กำลังวิเคราะห์รูปภาพพร้อมข้อมูลเพิ่มเติม... กรุณารอสักครู่ค่ะ"
    return "🔬 กำลังวิเคราะห์รูปภาพ... กรุณารอสักครู่ค่ะ"


# =============================================================================
# Disease Result & Product Messages
# =============================================================================

def format_disease_result_text(
    disease_name: str,
    confidence: str,
    symptoms: str,
    severity: str,
    raw_analysis: str = "",
    pest_type: str = "",
    pest_vector: str = None,
    category: str = "",
    show_product_hint: bool = True
) -> str:
    """Format ผลวิเคราะห์โรคพืชเป็น text"""
    # Severity label
    severity_label = _get_severity_label(severity)

    lines = [
        "🔍 ผลการวิเคราะห์โรคพืช",
        "━━━━━━━━━━━━━━━━━━━",
        "",
        f"🦠 โรค: {disease_name}",
        f"⚠️ ความรุนแรง: {severity_label}",
    ]

    if category:
        lines.append(f"📋 ประเภท: {category}")

    if pest_type:
        lines.append(f"🏷️ ชนิด: {pest_type}")

    lines.append("")

    # Symptoms
    if symptoms:
        formatted_symptoms = _format_symptoms_text(symptoms)
        lines.append(f"🌿 อาการ: {formatted_symptoms}")
        lines.append("")

    # Pest vector warning
    if pest_vector:
        lines.append(f"🐛 แมลงพาหะ: {pest_vector}")
        lines.append("⚠️ ควรกำจัดแมลงพาหะร่วมด้วย")
        lines.append("")

    # Recommendations from raw_analysis
    if raw_analysis:
        recommendation = _format_recommendation_text(raw_analysis)
        if recommendation:
            lines.append(f"💡 คำแนะนำ: {recommendation}")
            lines.append("")

    if show_product_hint:
        lines.append("💊 ดูผลิตภัณฑ์แนะนำด้านล่าง")

    lines.append("")
    lines.append("⚠️ หมายเหตุ: นี่เป็นการวินิจฉัยเบื้องต้น ควรปรึกษาผู้เชี่ยวชาญก่อนใช้")

    return "\n".join(lines)


def format_product_list_text(products: List[Dict]) -> str:
    """Format รายการผลิตภัณฑ์เป็น text"""
    if not products:
        return "ไม่พบผลิตภัณฑ์ที่เหมาะสม"

    lines = [
        "💊 ผลิตภัณฑ์แนะนำ",
        "━━━━━━━━━━━━━━━",
    ]

    for idx, p in enumerate(products[:5], 1):
        from app.utils.pest_columns import get_pest_display
        name = p.get("product_name", "ไม่ระบุ")
        active = p.get("active_ingredient", "-")
        _pest_disp = get_pest_display(p, max_len=100) or "-"
        crops = p.get("applicable_crops", "-")
        period = p.get("usage_period", "-")
        how = p.get("how_to_use", "-")
        rate = p.get("usage_rate", "-")
        link = p.get("link_product", "")

        lines.append("")
        lines.append(f"{'─'*20}")
        lines.append(f"{idx}. {name}")
        lines.append(f"   สารสำคัญ: {active}")
        for _line in _pest_disp.split('\n'):
            lines.append(f"   {_line}")
        lines.append(f"   พืชที่ใช้ได้: {crops}")
        lines.append(f"   ช่วงการใช้: {period}")
        lines.append(f"   วิธีใช้: {how}")
        lines.append(f"   อัตราใช้: {rate}")
        if link and link.startswith("http"):
            lines.append(f"   🔗 {link}")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append("📚 ดูรายละเอียดเพิ่มเติม: https://www.icpladda.com/about/")
    lines.append("⚠️ ปรับอัตรา/ปริมาณตามฉลากจริงก่อนใช้ทุกครั้ง")

    return "\n".join(lines)


# =============================================================================
# Context Handler Messages
# =============================================================================

def get_continue_or_cancel_text(current_task: str) -> str:
    """ข้อความถามว่าจะทำต่อหรือยกเลิก"""
    return (
        f"⚠️ มีงานค้างอยู่\n\n"
        f"คุณกำลัง{current_task}อยู่ค่ะ\n\n"
        "พิมพ์ \"ทำต่อ\" เพื่อทำต่อ\n"
        "พิมพ์ \"ยกเลิก\" เพื่อยกเลิก"
    )


def get_image_choice_text() -> str:
    """ข้อความถามว่าจะใช้รูปใหม่หรือรูปเดิม"""
    return (
        "📷 คุณส่งรูปใหม่มา\n\n"
        "คุณกำลังวิเคราะห์รูปอยู่ แต่ส่งรูปใหม่มา\n"
        "ต้องการวิเคราะห์รูปไหนคะ?\n\n"
        "พิมพ์ \"รูปใหม่\" เพื่อใช้รูปใหม่\n"
        "พิมพ์ \"รูปเดิม\" เพื่อใช้รูปเดิม"
    )


# =============================================================================
# Helper Functions
# =============================================================================

def _format_symptoms_text(symptoms: str) -> str:
    """Format อาการให้กระชับ"""
    if not symptoms:
        return "ไม่พบข้อมูลอาการ"
    symptoms = symptoms.strip()
    if len(symptoms) <= 200:
        return symptoms
    cut_point = 200
    for sep in ['. ', ' | ', ', ', ' ']:
        idx = symptoms.rfind(sep, 0, 250)
        if idx > 100:
            cut_point = idx + len(sep)
            break
    return symptoms[:cut_point].strip()


def _get_severity_label(severity: str) -> str:
    """แปลง severity เป็น label"""
    if not severity:
        return "ปานกลาง"
    severity_lower = severity.lower()
    if any(x in severity_lower for x in ['รุนแรง', 'สูง', 'มาก', 'severe', 'high']):
        return "รุนแรง"
    elif any(x in severity_lower for x in ['เล็กน้อย', 'ต่ำ', 'น้อย', 'mild', 'low', 'light']):
        return "เล็กน้อย"
    return "ปานกลาง"


def _format_recommendation_text(raw_analysis: str) -> str:
    """Format คำแนะนำจาก raw_analysis"""
    if not raw_analysis:
        return ""
    parts = raw_analysis.split(' | ')
    main_part = parts[0] if parts else raw_analysis
    result = main_part.strip()
    if len(result) > 300:
        cut_point = 300
        for sep in ['. ', '। ', ' - ']:
            idx = result.rfind(sep, 0, 350)
            if idx > 150:
                cut_point = idx + len(sep)
                break
        result = result[:cut_point].strip()
    return result
