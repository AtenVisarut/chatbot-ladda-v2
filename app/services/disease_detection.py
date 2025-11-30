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
    """Detect plant disease/pest from an image, optionally using extra user description.

    The function:
    1. Checks cache (if no extra info).
    2. Builds a detailed prompt with examples.
    3. Calls GPT‑4o (vision) and expects a JSON response.
    4. Parses the response, applies simple post‑processing based on extra_user_info
       to disambiguate common confusions (e.g., leaf spot vs. Anthracnose).
    5. Returns a ``DiseaseDetectionResult`` model.
    """

    logger.info("Starting pest/disease detection with GPT‑4o")

    # ---------------------------------------------------------------------
    # Cache lookup (only when we don't have extra user info – otherwise the
    # user is providing disambiguating context, so we always run a fresh query)
    # ---------------------------------------------------------------------
    if not extra_user_info:
        image_hash = get_image_hash(image_bytes)
        cached = await get_from_cache("detection", image_hash)
        if cached:
            logger.info("✓ Using cached detection result")
            return DiseaseDetectionResult(**cached)

    try:
        # Encode image for the OpenAI API
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        # -----------------------------------------------------------------
        # Prompt – includes mission, step‑by‑step analysis, categories, warnings
        # and concrete examples to help the model differentiate similar diseases.
        # -----------------------------------------------------------------
        prompt_text = """คุณคือผู้เชี่ยวชาญโรคพืชและศัตรูพืชไทย ประสบการณ์ 20 ปี

🎯 **ภารกิจ**:  วิเคราะห์ภาพพืชเพื่อตรวจจับโรค, ศัตรูพืช, วัชพืช ให้แม่นยำที่สุดโดยอ้างอิงจากลักษณะอาการ สี ขนาด และตำแหน่ง

ห้ามเดา — หากไม่มีหลักฐานชัดเจนในภาพ ต้องลดความเชื่อมั่น (confidence ต่ำ)

──────────────────────────────────────────────
📌 สิ่งที่ต้องตรวจสอบอย่างละเอียด (Critical Checkpoints)
1) **ลักษณะแผล (Lesion Characteristics)**:
   - **รูปร่าง**: กลม/รี (Oval), รูปตา (Eye-shaped), หรือรูปร่างไม่แน่นอน (Irregular)
   - **สี**: สีน้ำตาลเข้ม, สีเทากลางแผล, สีดำ, หรือมีวงสีเหลืองล้อมรอบ (Halo)
   - **พื้นผิว**: ยุบตัวลง (Sunken), นูนขึ้น, หรือเป็นผง
2) **การกระจายตัว**: กระจายทั่วใบ, เป็นกลุ่ม, หรือเริ่มจากขอบใบ

──────────────────────────────────────────────
⚠️ กฎการแยกแยะโรคที่สำคัญ (Differentiation Rules)

1. **โรคใบจุดสีน้ำตาล (Brown Spot) vs แอนแทรคโนส (Anthracnose)**
   - **Brown Spot (ใบจุดสีน้ำตาล)**:
     - แผลมักเป็นรูป **"ไข่" หรือ "เมล็ดงา" (Oval/Sesame seed shape)**
     - สีน้ำตาลเข้ม **มักมีจุดสีเทาหรือขาวตรงกลาง (Grey/White center)**
     - **มีวงสีเหลืองล้อมรอบ (Yellow halo)** ชัดเจน
     - ขนาดแผลสม่ำเสมอ กระจายทั่วใบ
   - **Anthracnose (แอนแทรคโนส)**:
     - แผลมักมี **รูปร่างไม่แน่นอน (Irregular)** หรือกลมซ้อนกัน
     - ลักษณะ **ยุบตัวลง (Sunken)** ชัดเจน
     - สีน้ำตาลดำ หรือมี **วงซ้อนกันเป็นชั้นๆ (Concentric rings)**
     - อาจพบ **เมือกเยิ้มสีส้ม/ชมพู (Spore masses)** ในสภาพชื้น

2. **กฎอื่นๆ**:
   - ห้ามสรุปว่าเป็น “เพลี้ยไฟ” หากแมลง **มีสีเขียว**
   - ถ้าลักษณะเหมือนอาการขาดธาตุ (ใบเหลืองเป็นขอบ) → ให้ระบุว่า “อาจเป็นอาการขาดธาตุ”

──────────────────────────────────────────────
📚 ตัวอย่าง pattern ที่ใช้ตัดสิน
- **Brown Spot**: จุดสีน้ำตาล รูปไข่ มีสีเทากลางแผล มีวงเหลืองล้อม
- **Anthracnose**: แผลยุบตัว สีคล้ำ ขอบชัด อาจมีวงซ้อน
- **Downy Mildew**: คราบเทา/ขาวใต้ใบ ใบเหลืองเป็นปื้น
- **Powdery Mildew**: ผงขาวบนใบ/ยอด
- **เพลี้ยอ่อน**: ตัวอวบ สีเขียว/เหลือง อยู่เป็นกลุ่ม
- **เพลี้ยจักจั่น**: ตัวลิ่ม สีเขียวสด เคลื่อนที่เร็ว

──────────────────────────────────────────────
📤 ให้ตอบเป็น JSON เท่านั้น (ต้องเป็น JSON ที่ถูกต้อง)

{
  "disease_name": "ชื่อเฉพาะ เช่น โรคใบจุดสีน้ำตาล, แอนแทรคโนส, เพลี้ยอ่อน, อื่นๆ",
  "pest_type": "เชื้อรา/แมลง/ไวรัส/วัชพืช/ขาดธาตุ/unknown",
  "confidence_level_percent": 0-100,
  "confidence": "สูง/ปานกลาง/ต่ำ",
  "symptoms_in_image": "สรุปอาการที่เห็นชัดในภาพ",
  "symptoms": "รายละเอียดอาการ สี ขนาด ตำแหน่ง รูปร่าง",
  "possible_cause": "สาเหตุที่เป็นไปได้จากสิ่งที่เห็น",
  "severity_level": "รุนแรง/ปานกลาง/เล็กน้อย",
  "severity": "เหตุผลประกอบระดับความรุนแรง",
  "description": "คำอธิบายเพิ่มเติมและคำแนะนำ",
  "affected_area": "ส่วนของต้นที่ได้รับผลกระทบ เช่น ใบอ่อน, ใต้ใบ, ลำต้น",
  "spread_risk": "สูง/ปานกลาง/ต่ำ"
}

หากไม่พบปัญหาใดๆ:
{
  "disease_name": "ไม่พบปัญหา",
  "confidence": "สูง"
}

"""

        # Append extra user info if provided
        if extra_user_info:
            prompt_text += f"\n\nเพิ่มเติมจากผู้ใช้: {extra_user_info}"

        # -----------------------------------------------------------------
        # Call OpenAI vision model
        # -----------------------------------------------------------------
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                        },
                    ],
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=1000,
        )

        raw_text = response.choices[0].message.content
        logger.info(f"OpenAI raw response: {raw_text}")

        # -----------------------------------------------------------------
        # Parse JSON (fallback to raw text if parsing fails)
        # -----------------------------------------------------------------
        try:
            data = json.loads(raw_text)
        except Exception as e:
            logger.warning(f"Failed to parse JSON from response: {e}", exc_info=True)
            data = {
                "disease_name": "ไม่ทราบชื่อโรค",
                "confidence": "ปานกลาง",
                "symptoms": "",
                "severity": "ปานกลาง",
                "description": raw_text,
            }

        # Normalise fields
        disease_name = data.get("disease_name") or data.get("disease") or data.get("โรค") or "ไม่ทราบชื่อโรค"
        confidence = (
            str(data.get("confidence_level_percent"))
            if "confidence_level_percent" in data
            else str(data.get("confidence", "ปานกลาง"))
        )
        symptoms = data.get("symptoms_in_image") or data.get("symptoms") or data.get("อาการ") or ""
        severity = data.get("severity_level") or data.get("severity") or data.get("ความรุนแรง") or "ปานกลาง"
        description = data.get("description") or data.get("possible_cause") or raw_text
        pest_type = data.get("pest_type") or "ศัตรูพืช"
        affected_area = data.get("affected_area") or ""
        spread_risk = data.get("spread_risk") or ""

        # -----------------------------------------------------------------
        # Simple post‑processing using extra_user_info to correct common confusions
        # -----------------------------------------------------------------
        if extra_user_info:
            lowered = extra_user_info.lower()
            if "จุด" in lowered and "สี" in lowered and "สีน้ำตาล" in lowered:
                if "anthracnose" in disease_name.lower() or "แอนแทรคโนส" in disease_name:
                    logger.info("🔧 Adjusting disease_name based on user description to Leaf Spot")
                    disease_name = "Leaf Spot"
            if "แอนแทรคโนส" in lowered and "แผล" in lowered:
                if "leaf spot" in disease_name.lower() or "ใบจุด" in disease_name:
                    logger.info("🔧 Adjusting disease_name based on user description to Anthracnose")
                    disease_name = "Anthracnose"

        # Build raw_analysis for downstream use
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
            raw_analysis=" | ".join(raw_parts),
        )

        # Warn if confidence is low
        try:
            confidence_num = int(confidence.replace("%", "").replace("สูง", "90").replace("ปานกลาง", "60").replace("ต่ำ", "30"))
        except Exception:
            confidence_num = 0
        if confidence_num < 50 or "ต่ำ" in confidence:
            logger.warning(f"Low confidence detection: {result.disease_name} ({confidence})")

        logger.info(f"Pest/Disease detected: {result.disease_name} (Type: {pest_type}, Confidence: {confidence})")

        # Cache the result when we didn't have extra user info
        if not extra_user_info:
            image_hash = get_image_hash(image_bytes)
            await set_to_cache("detection", image_hash, result.dict())

        # Optional logging for analytics
        try:
            log_entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "disease_name": result.disease_name,
                "pest_type": pest_type,
                "confidence": confidence,
                "severity": result.severity,
                "has_user_input": bool(extra_user_info),
            }
            logger.debug(f"Detection log: {log_entry}")
        except Exception as e:
            logger.warning(f"Failed to log detection: {e}")

        return result

    except Exception as e:
        logger.error(f"Error in pest/disease detection: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Detection failed: {str(e)}")
