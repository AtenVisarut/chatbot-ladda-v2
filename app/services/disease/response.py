import logging
from typing import List, Optional, Union, Dict
from app.models import DiseaseDetectionResult, ProductRecommendation
from app.dependencies import openai_client
from app.utils.line.response_template import build_simple_response
from app.utils.line.text_messages import (
    format_disease_result_text,
    format_product_list_text,
    get_growth_stage_question_text
)
from app.services.product.recommendation import get_search_query_for_disease
from app.prompts import DISEASE_DETECTION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# =============================================================================
# Growth Stage Quick Reply - ตามชนิดพืช
# =============================================================================
GROWTH_STAGES = {
    # ===== พืชไร่ =====
    "ข้าว": [
        {"label": "🌱 กล้า/ปักดำ", "text": "ระยะกล้า ปักดำ 0-20 วัน"},
        {"label": "🌿 แตกกอ", "text": "ระยะแตกกอ 20-50 วัน"},
        {"label": "🌾 ตั้งท้อง", "text": "ระยะตั้งท้อง 50-80 วัน"},
        {"label": "🌻 ออกรวง", "text": "ระยะออกรวง 80+ วัน"},
    ],
    "ข้าวโพด": [
        {"label": "🌱 งอก/ต้นอ่อน", "text": "ระยะงอก ต้นอ่อน 0-20 วัน"},
        {"label": "🌿 เจริญเติบโต", "text": "ระยะเจริญเติบโต 20-50 วัน"},
        {"label": "🌸 ออกดอก", "text": "ระยะออกดอก ผสมเกสร 50-70 วัน"},
        {"label": "🌽 ติดฝัก", "text": "ระยะติดฝัก เก็บเกี่ยว 70+ วัน"},
    ],
    "มันสำปะหลัง": [
        {"label": "🌱 ปลูกใหม่", "text": "ระยะปลูกใหม่ 0-2 เดือน"},
        {"label": "🌿 เจริญเติบโต", "text": "ระยะเจริญเติบโต 2-6 เดือน"},
        {"label": "🥔 สะสมแป้ง", "text": "ระยะสะสมแป้ง 6-10 เดือน"},
        {"label": "📦 เก็บเกี่ยว", "text": "ระยะเก็บเกี่ยว 10-12 เดือน"},
    ],
    "อ้อย": [
        {"label": "🌱 งอก/แตกกอ", "text": "ระยะงอก แตกกอ 0-3 เดือน"},
        {"label": "🌿 ย่างปล้อง", "text": "ระยะย่างปล้อง 3-6 เดือน"},
        {"label": "🎋 สะสมน้ำตาล", "text": "ระยะสะสมน้ำตาล 6-10 เดือน"},
        {"label": "📦 เก็บเกี่ยว", "text": "ระยะเก็บเกี่ยว 10-12 เดือน"},
    ],

    # ===== ไม้ผล =====
    "มะม่วง": [
        {"label": "🌿 ก่อนออกดอก", "text": "ระยะก่อนออกดอก"},
        {"label": "🌸 ออกดอก", "text": "ระยะออกดอก"},
        {"label": "🥭 ติดผล", "text": "ระยะติดผล ผลโต"},
        {"label": "📦 เก็บเกี่ยว", "text": "ระยะเก็บเกี่ยว"},
    ],
    "ทุเรียน": [
        {"label": "🌿 ก่อนออกดอก", "text": "ระยะก่อนออกดอก บำรุงต้น"},
        {"label": "🌸 ออกดอก", "text": "ระยะออกดอก"},
        {"label": "🍈 ติดผล", "text": "ระยะติดผล ผลโต"},
        {"label": "📦 เก็บเกี่ยว", "text": "ระยะเก็บเกี่ยว"},
    ],
    "ลำไย": [
        {"label": "🌿 ก่อนออกดอก", "text": "ระยะก่อนออกดอก ราดสาร"},
        {"label": "🌸 ออกดอก", "text": "ระยะออกดอก"},
        {"label": "🫐 ติดผล", "text": "ระยะติดผล ผลโต"},
        {"label": "📦 เก็บเกี่ยว", "text": "ระยะเก็บเกี่ยว"},
    ],
    "ส้ม": [
        {"label": "🌿 ก่อนออกดอก", "text": "ระยะก่อนออกดอก"},
        {"label": "🌸 ออกดอก", "text": "ระยะออกดอก"},
        {"label": "🍊 ติดผล", "text": "ระยะติดผล ผลโต"},
        {"label": "📦 เก็บเกี่ยว", "text": "ระยะเก็บเกี่ยว"},
    ],

    # ===== พืชยืนต้น/อุตสาหกรรม =====
    "ยางพารา": [
        {"label": "🌱 ต้นอ่อน", "text": "ระยะต้นอ่อน 0-3 ปี"},
        {"label": "🌿 ก่อนเปิดกรีด", "text": "ระยะก่อนเปิดกรีด 3-6 ปี"},
        {"label": "🪵 เปิดกรีด", "text": "ระยะเปิดกรีด กรีดยาง"},
        {"label": "🔄 บำรุงต้น", "text": "ระยะบำรุงต้น พักต้น"},
    ],
    "ปาล์มน้ำมัน": [
        {"label": "🌱 ต้นอ่อน", "text": "ระยะต้นอ่อน 0-3 ปี"},
        {"label": "🌿 ก่อนออกทลาย", "text": "ระยะก่อนออกทลาย"},
        {"label": "🌴 ออกทลาย", "text": "ระยะออกทลาย ให้ผลผลิต"},
        {"label": "🔄 บำรุงต้น", "text": "ระยะบำรุงต้น"},
    ],

    # ===== พืชผัก =====
    "ผัก": [
        {"label": "🌱 ต้นอ่อน", "text": "ระยะต้นอ่อน 0-15 วัน"},
        {"label": "🌿 เจริญเติบโต", "text": "ระยะเจริญเติบโต 15-30 วัน"},
        {"label": "📦 ก่อนเก็บเกี่ยว", "text": "ระยะก่อนเก็บเกี่ยว"},
    ],
    "พริก": [
        {"label": "🌱 ต้นอ่อน", "text": "ระยะต้นอ่อน กล้า 0-30 วัน"},
        {"label": "🌿 เจริญเติบโต", "text": "ระยะเจริญเติบโต 30-60 วัน"},
        {"label": "🌸 ออกดอก", "text": "ระยะออกดอก ติดผล"},
        {"label": "🌶️ เก็บเกี่ยว", "text": "ระยะเก็บเกี่ยว"},
    ],
    "มะเขือเทศ": [
        {"label": "🌱 ต้นอ่อน", "text": "ระยะต้นอ่อน กล้า 0-30 วัน"},
        {"label": "🌿 เจริญเติบโต", "text": "ระยะเจริญเติบโต 30-50 วัน"},
        {"label": "🌸 ออกดอก", "text": "ระยะออกดอก ติดผล"},
        {"label": "🍅 เก็บเกี่ยว", "text": "ระยะเก็บเกี่ยว"},
    ],

    # ===== Default =====
    "default": [
        {"label": "🌱 ต้นอ่อน", "text": "ระยะต้นอ่อน"},
        {"label": "🌿 เจริญเติบโต", "text": "ระยะเจริญเติบโต"},
        {"label": "🌸 ออกดอก/ผล", "text": "ระยะออกดอก ติดผล"},
        {"label": "📦 เก็บเกี่ยว", "text": "ระยะเก็บเกี่ยว"},
    ],
}

def get_growth_stage_options(plant_type: str) -> list:
    """Get growth stage options based on plant type"""
    plant_lower = plant_type.lower() if plant_type else ""

    # ===== พืชไร่ =====
    if "ข้าว" in plant_lower or "rice" in plant_lower:
        return GROWTH_STAGES["ข้าว"]
    elif "ข้าวโพด" in plant_lower or "corn" in plant_lower or "maize" in plant_lower:
        return GROWTH_STAGES["ข้าวโพด"]
    elif "มันสำปะหลัง" in plant_lower or "มัน" in plant_lower or "cassava" in plant_lower:
        return GROWTH_STAGES["มันสำปะหลัง"]
    elif "อ้อย" in plant_lower or "sugarcane" in plant_lower:
        return GROWTH_STAGES["อ้อย"]

    # ===== ไม้ผล =====
    elif "มะม่วง" in plant_lower or "mango" in plant_lower:
        return GROWTH_STAGES["มะม่วง"]
    elif "ทุเรียน" in plant_lower or "durian" in plant_lower:
        return GROWTH_STAGES["ทุเรียน"]
    elif "ลำไย" in plant_lower or "longan" in plant_lower:
        return GROWTH_STAGES["ลำไย"]
    elif "ส้ม" in plant_lower or "มะนาว" in plant_lower or "citrus" in plant_lower or "ส้มโอ" in plant_lower:
        return GROWTH_STAGES["ส้ม"]

    # ===== พืชยืนต้น/อุตสาหกรรม =====
    elif "ยางพารา" in plant_lower or "ยาง" in plant_lower or "rubber" in plant_lower:
        return GROWTH_STAGES["ยางพารา"]
    elif "ปาล์ม" in plant_lower or "palm" in plant_lower:
        return GROWTH_STAGES["ปาล์มน้ำมัน"]

    # ===== พืชผัก =====
    elif "พริก" in plant_lower or "chili" in plant_lower or "pepper" in plant_lower:
        return GROWTH_STAGES["พริก"]
    elif "มะเขือเทศ" in plant_lower or "tomato" in plant_lower:
        return GROWTH_STAGES["มะเขือเทศ"]
    elif any(v in plant_lower for v in ["ผัก", "มะเขือ", "แตง", "กะหล่ำ", "คะน้า", "ผักกาด", "บวบ", "ฟัก"]):
        return GROWTH_STAGES["ผัก"]

    # ===== Default =====
    else:
        return GROWTH_STAGES["default"]


async def generate_final_response(
    disease_info: DiseaseDetectionResult,
    products: List[ProductRecommendation],
    extra_user_info: Optional[str] = None
) -> str:
    """
    Generate final response using GPT-4o- (AI-powered)

    Includes:
    - Symptoms (อาการที่เกิด)
    - Additional Disease Info (ข้อมูลกำกับโรค)
    - Product Recommendations (คำแนะนำผลิตภัณฑ์)
    """
    try:
        logger.info("Generating response using GPT-4o")

        # Knowledge base table removed - using GPT knowledge instead
        knowledge_text = None

        # Prepare product list text
        products_text = ""
        if products:
            for idx, p in enumerate(products[:5], 1):
                products_text += f"\n{idx}. {p.product_name}"
                products_text += f"\n   - สารสำคัญ: {p.active_ingredient}"
                products_text += f"\n   - ศัตรูพืช: {p.target_pest}"
                products_text += f"\n   - พืชที่ใช้ได้: {p.applicable_crops}"
                products_text += f"\n   - ช่วงการใช้: {p.usage_period}"
                products_text += f"\n   - วิธีใช้: {p.how_to_use}"
                products_text += f"\n   - อัตราใช้: {p.usage_rate}"
                products_text += "\n"
        else:
            products_text = "ไม่พบผลิตภัณฑ์ที่เหมาะสมในระบบ"

        # Construct Prompt
        if products:
            product_section_prompt = f"""
5. 💊 **สินค้าแนะนำ**:
   (เลือกแนะนำ 1-3 รายการที่เหมาะสมที่สุด เรียงเป็นข้อ 1, 2, 3)
   ⚠️ สำคัญ: ต้องแสดงข้อมูลครบทุกหัวข้อดังนี้
   - **ชื่อสินค้า**: (ระบุชื่อผลิตภัณฑ์)
   - **สารสำคัญ**: (คัดลอกจากรายการ)
   - **ศัตรูพืชที่กำจัดได้**: (คัดลอกจากรายการ - ห้ามข้าม)
   - **พืชที่ใช้ได้**: (คัดลอกจากรายการ)
   - **ช่วงการใช้**: (คัดลอกจากรายการ)
   - **อัตราการใช้**: (คัดลอกจากรายการ)
   - **ประโยชน์**: (อธิบายสั้นๆ)
"""
            products_list_prompt = f"""
ผลิตภัณฑ์ที่แนะนำ (เลือกจากรายการนี้เท่านั้น):
{products_text}
"""
        else:
            product_section_prompt = ""
            products_list_prompt = ""

        prompt = f"""คุณคือผู้เชี่ยวชาญด้านโรคพืชและศัตรูพืชประสบการณ์20ปี ของ ICP LADDA
หน้าที่ของคุณคือแจ้งผลการตรวจโรคพืชและแนะนำวิธีรักษาให้กับเกษตรกร

ข้อมูลการตรวจ:
- โรคที่พบ: {disease_info.disease_name}
- ความมั่นใจ: {disease_info.confidence}
- อาการเบื้องต้นจากระบบ: {disease_info.symptoms}
- ข้อมูลเพิ่มเติมจากผู้ใช้: {extra_user_info if extra_user_info else '-'}

ข้อมูลอ้างอิง (Knowledge Base):
{knowledge_text if knowledge_text else 'ไม่มีข้อมูลเพิ่มเติม'}
{products_list_prompt}
โครงสร้างคำตอบที่ต้องการ (ห้ามเปลี่ยนหัวข้อ):
1. 🔍 **ผลการตรวจจับ**: (ชื่อโรคภาษาไทย และภาษาอังกฤษ)
2. 📊 **ระดับความมั่นใจ**: (ระบุ % หรือระดับความมั่นใจ)
3. 🌿 **อาการที่เห็น**: (อธิบายลักษณะอาการที่พบในภาพ + ข้อมูลวิชาการเล็กน้อย)
4. 📝 **ข้อมูลกำกับโรค**: (สรุปสาเหตุ การแพร่ระบาด และสภาพแวดล้อมที่เหมาะสม แบบกระชับ){product_section_prompt}
โทนเสียง: เป็นกันเอง สุภาพ กระชับ เข้าใจง่าย
ภาษา: ไทย
ไม่ใช้ Markdown หัวข้อใหญ่ (เช่น #) ใช้แค่ตัวหนา

ตอบกลับ:"""

        if not openai_client:
            logger.warning("OpenAI client not available, falling back to template")
            from app.utils.line.response_template import build_detailed_response
            return build_detailed_response(disease_info, knowledge_text or "", products, extra_user_info)

        # Call GPT
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": DISEASE_DETECTION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )

        final_response = response.choices[0].message.content.strip()

        # Post-process (remove markdown code blocks if any)
        final_response = final_response.replace("```", "").replace("**", "")

        # Append Static Footer (Important Notes & Links)
        final_response += "\n\n" + "━"*15
        final_response += "\n*หมายเหตุสำคัญ*"
        final_response += "\n• เป็นแค่การวินิจฉัยเบื้องต้น ควรปรึกษาผู้เชี่ยวชาญก่อนใช้"
        final_response += "\n• ปรับอัตรา/ปริมาณตามฉลากจริงก่อนใช้ทุกครั้ง"
        final_response += "\n• ควรสอบถามร้านค้าตัวแทนจำหน่ายเพื่อแนะนำเพิ่มเติม"
        final_response += "\n• ทดสอบในพื้นที่เล็กก่อนพ่นทั้งแปลง"

        final_response += "\n\n📚 ดูรายละเอียดผลิตภัณฑ์ทั้งหมด:"
        final_response += "\n🔗 https://www.icpladda.com/about/"
        final_response += "\n\n💬 ส่งรูปเพิ่มหรือถามข้อมูลเพิ่มเติมได้เลยค่ะ 😊"

        logger.info("✓ Response generated successfully with GPT")
        return final_response

    except Exception as e:
        logger.error(f"Error generating response: {e}", exc_info=True)
        return build_simple_response(disease_info)


async def generate_text_response(
    disease_info: DiseaseDetectionResult,
    products: List[ProductRecommendation],
    extra_user_info: Optional[str] = None
) -> List[str]:
    """
    Generate text message response for disease detection
    Returns list of text strings: [disease_result_text, product_list_text, footer_text]
    """
    try:
        logger.info("Generating text message response")
        logger.info(f"  Disease: {disease_info.disease_name}")
        logger.info(f"  Products count: {len(products) if products else 0}")

        messages = []

        # Extract pest type from raw_analysis (with safety)
        pest_type = "โรคพืช"
        try:
            if disease_info.raw_analysis:
                parts = disease_info.raw_analysis.split(":")
                if len(parts) > 0 and parts[0].strip():
                    pest_type = parts[0].strip()[:50]  # Limit length
        except Exception as e:
            logger.warning(f"Error extracting pest_type: {e}")

        # 1. Disease Result Text
        try:
            # Sanitize inputs
            safe_disease_name = (disease_info.disease_name or "ไม่ทราบ")[:100]
            safe_confidence = str(disease_info.confidence or "75")[:20]
            safe_symptoms = (disease_info.symptoms or "ไม่ระบุอาการ")[:500]
            safe_severity = (disease_info.severity or "ปานกลาง")[:100]
            safe_raw = (disease_info.raw_analysis or "")[:500]

            # ตรวจสอบว่าโรคนี้มีแมลงพาหะหรือไม่
            pest_vector_info = None
            try:
                _, pest_name, _ = get_search_query_for_disease(safe_disease_name)
                if pest_name:
                    pest_vector_info = pest_name
                    logger.info(f"🐛 โรค {safe_disease_name} มีแมลงพาหะ: {pest_name}")
            except Exception as e:
                logger.warning(f"Error checking pest vector: {e}")

            disease_text = format_disease_result_text(
                disease_name=safe_disease_name,
                confidence=safe_confidence,
                symptoms=safe_symptoms,
                severity=safe_severity,
                raw_analysis=safe_raw,
                pest_type=pest_type,
                pest_vector=pest_vector_info,
                category=disease_info.category or ""
            )
            messages.append(disease_text)
            logger.info("  ✓ Disease text created")
        except Exception as e:
            logger.error(f"Error creating disease text: {e}", exc_info=True)
            messages.append(f"🔍 ผลวิเคราะห์: {disease_info.disease_name}\nความมั่นใจ: {disease_info.confidence}\nอาการ: {disease_info.symptoms[:200] if disease_info.symptoms else 'ไม่ระบุ'}")

        # 2. Product list text (if products available)
        if products:
            try:
                product_list = []
                for p in products[:5]:  # Limit to 5 products
                    product_list.append({
                        "product_name": (p.product_name or "ไม่ระบุ")[:100],
                        "active_ingredient": (p.active_ingredient or "-")[:100],
                        "target_pest": (p.target_pest or "-")[:200],
                        "applicable_crops": (p.applicable_crops or "-")[:150],
                        "usage_period": (p.usage_period or "-")[:100],
                        "how_to_use": (p.how_to_use or "-")[:200],
                        "usage_rate": (p.usage_rate or "-")[:100],
                        "link_product": (p.link_product or "")[:500] if p.link_product and str(p.link_product).startswith("http") else "",
                        "image_url": (p.image_url or "") if hasattr(p, 'image_url') else "",
                        "similarity": p.score if hasattr(p, 'score') else 0.8
                    })

                product_text = format_product_list_text(product_list)
                messages.append(product_text)
                logger.info(f"  ✓ Product list created with {len(product_list)} products")
            except Exception as e:
                logger.error(f"Error creating product list: {e}", exc_info=True)
                product_names = [p.product_name for p in products[:3]]
                messages.append("💊 ผลิตภัณฑ์แนะนำ:\n" + "\n".join(f"• {name}" for name in product_names))


        logger.info(f"✓ Text response generated: {len(messages)} messages")
        return messages

    except Exception as e:
        logger.error(f"Error generating text response: {e}", exc_info=True)
        return [build_simple_response(disease_info)]


async def generate_diagnosis_with_stage_question(
    disease_info: DiseaseDetectionResult
) -> list:
    """
    Generate text message for disease diagnosis + ask for growth stage
    NO product recommendations yet - wait for user to select growth stage first
    """
    try:
        logger.info("Generating diagnosis response with growth stage question")

        messages = []

        # Extract pest type from raw_analysis
        pest_type = "โรคพืช"
        try:
            if disease_info.raw_analysis:
                parts = disease_info.raw_analysis.split(":")
                if len(parts) > 0 and parts[0].strip():
                    pest_type = parts[0].strip()[:50]
        except Exception:
            pass

        # 1. Disease Result Text
        try:
            safe_disease_name = (disease_info.disease_name or "ไม่ทราบ")[:100]
            safe_confidence = str(disease_info.confidence or "75")[:20]
            safe_symptoms = (disease_info.symptoms or "ไม่ระบุอาการ")[:500]
            safe_severity = (disease_info.severity or "ปานกลาง")[:100]
            safe_raw = (disease_info.raw_analysis or "")[:500]

            # ตรวจสอบว่าโรคนี้มีแมลงพาหะหรือไม่
            pest_vector_info = None
            try:
                _, pest_name, _ = get_search_query_for_disease(safe_disease_name)
                if pest_name:
                    pest_vector_info = pest_name
            except Exception:
                pass

            disease_text = format_disease_result_text(
                disease_name=safe_disease_name,
                confidence=safe_confidence,
                symptoms=safe_symptoms,
                severity=safe_severity,
                raw_analysis=safe_raw,
                pest_type=pest_type,
                pest_vector=pest_vector_info,
                category=disease_info.category or "",
                show_product_hint=False
            )
            messages.append(disease_text)
        except Exception as e:
            logger.error(f"Error creating disease text: {e}", exc_info=True)
            messages.append(f"🔍 ผลวิเคราะห์: {disease_info.disease_name}")

        # 2. Ask for growth stage
        plant_type = disease_info.plant_type or ""
        plant_display = plant_type if plant_type else "พืช"

        question_text = get_growth_stage_question_text(plant_display)
        messages.append(question_text)

        logger.info(f"✓ Diagnosis with stage question generated for plant: {plant_type}")
        return messages

    except Exception as e:
        logger.error(f"Error generating diagnosis with stage question: {e}", exc_info=True)
        return [f"🔍 ผลวิเคราะห์: {disease_info.disease_name}\n\nพืชอยู่ในระยะไหนคะ? กรุณาพิมพ์ระยะการเติบโต"]
