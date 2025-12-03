import logging
from typing import List, Optional, Union, Dict
from app.models import DiseaseDetectionResult, ProductRecommendation
from app.services.services import openai_client
from app.utils.response_template import build_simple_response
from app.utils.flex_messages import (
    create_disease_result_flex,
    create_product_carousel_flex
)

logger = logging.getLogger(__name__)

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
            from app.utils.response_template import build_detailed_response
            return build_detailed_response(disease_info, knowledge_text or "", products, extra_user_info)

        # Call GPT
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
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


async def generate_flex_response(
    disease_info: DiseaseDetectionResult,
    products: List[ProductRecommendation],
    extra_user_info: Optional[str] = None
) -> List[Dict]:
    """
    Generate Flex Message response for disease detection
    Returns list of Flex Messages: [disease_result, product_carousel]
    """
    try:
        logger.info("Generating Flex Message response")
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

        # 1. Disease Result Flex
        try:
            # Sanitize inputs
            safe_disease_name = (disease_info.disease_name or "ไม่ทราบ")[:100]
            safe_confidence = str(disease_info.confidence or "75")[:20]
            safe_symptoms = (disease_info.symptoms or "ไม่ระบุอาการ")[:500]
            safe_severity = (disease_info.severity or "ปานกลาง")[:100]
            safe_raw = (disease_info.raw_analysis or "")[:500]

            disease_flex = create_disease_result_flex(
                disease_name=safe_disease_name,
                confidence=safe_confidence,
                symptoms=safe_symptoms,
                severity=safe_severity,
                raw_analysis=safe_raw,
                pest_type=pest_type
            )
            messages.append(disease_flex)
            logger.info("  ✓ Disease flex created")
        except Exception as e:
            logger.error(f"Error creating disease flex: {e}", exc_info=True)
            # Add simple text fallback
            messages.append({
                "type": "text",
                "text": f"🔍 ผลวิเคราะห์: {disease_info.disease_name}\nความมั่นใจ: {disease_info.confidence}\nอาการ: {disease_info.symptoms[:200] if disease_info.symptoms else 'ไม่ระบุ'}"
            })

        # 2. Product Carousel Flex (if products available)
        if products:
            try:
                product_list = []
                for p in products[:5]:  # Limit to 5 products
                    # Sanitize all product fields
                    product_list.append({
                        "product_name": (p.product_name or "ไม่ระบุ")[:100],
                        "active_ingredient": (p.active_ingredient or "-")[:100],
                        "target_pest": (p.target_pest or "-")[:200],
                        "applicable_crops": (p.applicable_crops or "-")[:150],
                        "usage_period": (p.usage_period or "-")[:100],
                        "how_to_use": (p.how_to_use or "-")[:200],
                        "usage_rate": (p.usage_rate or "-")[:100],
                        "link_product": (p.link_product or "")[:500] if p.link_product and str(p.link_product).startswith("http") else "",
                        "similarity": p.score if hasattr(p, 'score') else 0.8
                    })

                product_flex = create_product_carousel_flex(product_list)
                messages.append(product_flex)
                logger.info(f"  ✓ Product carousel created with {len(product_list)} products")
            except Exception as e:
                logger.error(f"Error creating product carousel: {e}", exc_info=True)
                # Add simple text fallback for products
                product_names = [p.product_name for p in products[:3]]
                messages.append({
                    "type": "text",
                    "text": f"💊 ผลิตภัณฑ์แนะนำ:\n" + "\n".join(f"• {name}" for name in product_names)
                })

        # 3. Add footer text message
        footer_msg = {
            "type": "text",
            "text": "⚠️ หมายเหตุ: นี่เป็นการวินิจฉัยเบื้องต้น ควรปรึกษาผู้เชี่ยวชาญก่อนใช้\n\n📚 ดูรายละเอียดเพิ่มเติม: icpladda.com\n💬 ส่งรูปเพิ่มหรือถามได้เลยค่ะ"
        }
        messages.append(footer_msg)

        logger.info(f"✓ Flex response generated: {len(messages)} messages")
        return messages

    except Exception as e:
        logger.error(f"Error generating flex response: {e}", exc_info=True)
        # Fallback to simple text
        return [{"type": "text", "text": build_simple_response(disease_info)}]
