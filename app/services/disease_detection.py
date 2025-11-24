import logging
import json
import io
import datetime
from typing import Optional
import base64
from PIL import Image
from fastapi import HTTPException

from app.models import DiseaseDetectionResult
from app.services.services import openai_client
from app.services.cache import get_image_hash, get_from_cache, set_to_cache

logger = logging.getLogger(__name__)

async def detect_disease(image_bytes: bytes, extra_user_info: Optional[str] = None) -> DiseaseDetectionResult:
    logger.info("Starting pest/disease detection with GPT")
    
    # Check cache first (only if no extra user info)
    if not extra_user_info:
        image_hash = get_image_hash(image_bytes)
        # Use "detection" as cache type
        cached_result = await get_from_cache("detection", image_hash)
        if cached_result:
            logger.info("✓ Using cached detection result")
            return DiseaseDetectionResult(**cached_result)
    
    try:
        # Encode image to base64
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        prompt_text = """คุณคือผู้เชี่ยวชาญด้านโรคพืชและศัตรูพืชของกรมวิชาการเกษตรไทย มีประสบการณ์ 20 ปี

🎯 **ภารกิจ**: วิเคราะห์ภาพพืชเพื่อระบุปัญหาอย่างแม่นยำ

📋 **ขั้นตอนการวิเคราะห์**:
1. สังเกตอาการบนใบ/ลำต้น/ผล อย่างละเอียด
2. ระบุสี รูปร่าง และลักษณะของความเสียหาย
3. มองหาแมลง ไข่ หรือร่องรอยของศัตรูพืช
4. ประเมินความรุนแรงจากพื้นที่ที่เสียหาย

🔍 **จำแนกประเภท** (เลือก 1 ประเภทเท่านั้น):
- **เชื้อรา**: จุดสีน้ำตาล/ดำ, แผลเปียก, ราขาว, ใบไหม้, ราน้ำค้าง, แอนแทรคโนส
- **แมลง**: เห็นแมลง, รอยกัด, ใบม้วน, มีเยื่อใย, เพลี้ย, หนอน, ด้วง
- **ไวรัส**: ใบด่าง, ใบหงิก, เส้นใบเหลือง, แคระแกร็น
- **วัชพืช**: พืชแปลกปลอมในแปลง, หญ้า

⚠️ **ข้อควรระวัง**:
- ห้ามเดาโดยไม่มีหลักฐานในภาพ
- ถ้าไม่แน่ใจ ให้ระบุ confidence ต่ำ
- ถ้าภาพไม่ชัด ให้ระบุว่า "ต้องการภาพเพิ่มเติม"

📤 **ตอบเป็น JSON เท่านั้น** (ไม่ต้องมี markdown):

{
  "disease_name": "ชื่อเฉพาะเจาะจง เช่น เพลี้ยไฟ, แอนแทรคโนส, ราน้ำค้าง",
  "pest_type": "เชื้อรา/แมลง/ไวรัส/วัชพืช",
  "confidence_level_percent": 0-100,
  "confidence": "สูง/ปานกลาง/ต่ำ",
  "symptoms_in_image": "อาการที่เห็นชัดในภาพ (สั้นๆ)",
  "symptoms": "รายละเอียดอาการทั้งหมด รวมสี ตำแหน่ง ขนาด",
  "possible_cause": "สาเหตุที่เป็นไปได้ และปัจจัยเสี่ยง",
  "severity_level": "รุนแรง/ปานกลาง/เล็กน้อย",
  "severity": "ระดับความรุนแรง พร้อมเหตุผล",
  "description": "คำอธิบายเพิ่มเติม และข้อแนะนำเบื้องต้น",
  "affected_area": "ส่วนของพืชที่ได้รับผลกระทบ",
  "spread_risk": "ความเสี่ยงการแพร่กระจาย (สูง/ปานกลาง/ต่ำ)"
}

✅ หากไม่พบปัญหา: disease_name = "ไม่พบปัญหา", confidence = "สูง" """

        # If user provided extra observation text, include it as additional context
        if extra_user_info:
            prompt_text += f"\n\nเพิ่มเติมจากผู้ใช้: {extra_user_info}"

        # Call OpenAI with image
        response = await openai_client.chat.completions.create(
            model="gpt-4o",  # Use GPT-4o for better vision analysis
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=1000,
        )
        
        raw_text = response.choices[0].message.content
        logger.info(f"OpenAI raw response: {raw_text}")

        # Extract JSON flexibly
        try:
            data = json.loads(raw_text)
        except Exception as e:
            logger.warning(f"Failed to parse JSON from Gemini response: {e}", exc_info=True)
            data = {"disease_name": "ไม่ทราบชื่อโรค", "confidence": "ปานกลาง", "symptoms": "", "severity": "ปานกลาง", "description": raw_text}

        # Map many possible keys to canonical fields
        disease_name = data.get("disease_name") or data.get("disease") or data.get("โรค") or "ไม่ทราบชื่อโรค"
        # confidence prefer numeric percent if provided
        confidence = ""
        if "confidence_level_percent" in data:
            confidence = str(data.get("confidence_level_percent"))
        elif "confidence" in data:
            confidence = str(data.get("confidence"))
        elif "confidence_percent" in data:
            confidence = str(data.get("confidence_percent"))
        else:
            confidence = "ปานกลาง"
        # symptoms
        symptoms = data.get("symptoms_in_image") or data.get("symptoms") or data.get("อาการ") or ""
        # severity
        severity = data.get("severity_level") or data.get("severity") or data.get("ความรุนแรง") or "ปานกลาง"
        # description / raw
        description = data.get("description") or data.get("possible_cause") or raw_text
        
        # Extract pest_type
        pest_type = data.get("pest_type") or "ศัตรูพืช"
        
        # Extract additional fields for better analysis
        affected_area = data.get("affected_area") or ""
        spread_risk = data.get("spread_risk") or ""
        
        # Build comprehensive raw_analysis
        raw_parts = [f"{pest_type}: {description}"]
        if affected_area:
            raw_parts.append(f"ส่วนที่ได้รับผลกระทบ: {affected_area}")
        if spread_risk:
            raw_parts.append(f"ความเสี่ยงการแพร่: {spread_risk}")
        
        result = DiseaseDetectionResult(
            disease_name=str(disease_name),
            confidence=str(confidence),
            symptoms=str(symptoms),
            severity=str(severity),
            raw_analysis=" | ".join(raw_parts)
        )
        
        # Check confidence level and warn if low
        confidence_num = 0
        try:
            if confidence.replace("%", "").replace("สูง", "90").replace("ปานกลาง", "60").replace("ต่ำ", "30").isdigit():
                confidence_num = int(confidence.replace("%", "").replace("สูง", "90").replace("ปานกลาง", "60").replace("ต่ำ", "30"))
        except:
            pass
        
        if confidence_num < 50 or "ต่ำ" in confidence:
            logger.warning(f"Low confidence detection: {result.disease_name} ({confidence})")
        
        logger.info(f"Pest/Disease detected: {result.disease_name} (Type: {pest_type}, Confidence: {confidence})")
        
        # Cache the result (only if no extra user info)
        if not extra_user_info:
            image_hash = get_image_hash(image_bytes)
            # Use "detection" as cache type
            await set_to_cache("detection", image_hash, result.dict())
        
        # Log detection for analysis (optional - can be used to improve accuracy)
        try:
            log_entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "disease_name": result.disease_name,
                "pest_type": pest_type,
                "confidence": confidence,
                "severity": result.severity,
                "has_user_input": bool(extra_user_info)
            }
            # Could save to file or database for later analysis
            logger.debug(f"Detection log: {log_entry}")
        except Exception as e:
            logger.warning(f"Failed to log detection: {e}")
        
        return result

    except Exception as e:
        logger.error(f"Error in pest/disease detection: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Detection failed: {str(e)}")
