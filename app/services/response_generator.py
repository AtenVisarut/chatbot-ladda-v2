import logging
from typing import List, Optional
from app.models import DiseaseDetectionResult, ProductRecommendation
from app.services.knowledge_base import retrieve_knowledge_from_knowledge_table
from app.services.services import openai_client
from app.utils.response_template import build_simple_response

logger = logging.getLogger(__name__)

async def generate_final_response(
    disease_info: DiseaseDetectionResult, 
    products: List[ProductRecommendation],
    extra_user_info: Optional[str] = None
) -> str:
    """
    Generate final response using GPT-4o-mini (AI-powered)
    
    Includes:
    - Symptoms (อาการที่เกิด)
    - Additional Disease Info (ข้อมูลกำกับโรค)
    - Product Recommendations (คำแนะนำผลิตภัณฑ์)
    """
    try:
        logger.info("Generating response using GPT-4o-mini")
        
        # Get knowledge from database
        knowledge_text = await retrieve_knowledge_from_knowledge_table(disease_info.disease_name)
        
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

        prompt = f"""คุณคือผู้เชี่ยวชาญด้านโรคพืชของ ICP Ladda
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
            from app.utils.response_template import build_detailed_response
            return build_detailed_response(disease_info, knowledge_text or "", products, extra_user_info)

        # Call GPT
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful agricultural expert assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        final_response = response.choices[0].message.content.strip()
        
        # Post-process (remove markdown code blocks if any)
        final_response = final_response.replace("```", "").replace("**", "")
        
        # Append Static Footer (Important Notes & Links)
        final_response += "\n\n" + "="*30
        final_response += "\n**หมายเหตุสำคัญ**:"
        final_response += "\n• ✅ ปรับอัตรา/ปริมาณตามฉลากจริงก่อนใช้ทุกครั้ง"
        final_response += "\n• ✅ ควรปรึกษาผู้เชี่ยวชาญก่อนใช้"
        final_response += "\n• ✅ ทดสอบในพื้นที่เล็กก่อนพ่นทั้งแปลง"
        
        final_response += "\n\n📚 ดูรายละเอียดผลิตภัณฑ์ทั้งหมด:"
        final_response += "\n🔗 https://www.icpladda.com/about/"
        final_response += "\n\n💬 ส่งรูปเพิ่มหรือถามข้อมูลเพิ่มเติมได้เลยค่ะ 😊"
        
        logger.info("✓ Response generated successfully with GPT")
        return final_response

    except Exception as e:
        logger.error(f"Error generating response: {e}", exc_info=True)
        return build_simple_response(disease_info)
