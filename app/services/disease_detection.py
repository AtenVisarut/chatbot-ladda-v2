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
from app.services.disease_database import (
    generate_disease_prompt_section,
    get_disease_info,
    get_severity_description,
    FUNGAL_DISEASES,
    BACTERIAL_DISEASES,
    VIRAL_DISEASES,
    INSECT_PESTS,
    NUTRIENT_DEFICIENCIES,
)

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
        # and comprehensive disease/pest database for accurate identification.
        # -----------------------------------------------------------------

        # สร้าง prompt section จากฐานข้อมูล
        disease_database_section = generate_disease_prompt_section()

        prompt_text = f"""คุณคือผู้เชี่ยวชาญโรคพืชและศัตรูพืชไทย ประสบการณ์ 20 ปี

🎯 **ภารกิจ**: วิเคราะห์ภาพพืชเพื่อตรวจจับโรค, ศัตรูพืช, วัชพืช, หรืออาการขาดธาตุ ให้แม่นยำที่สุด
โดยอ้างอิงจากลักษณะอาการ สี ขนาด ตำแหน่ง และเปรียบเทียบกับฐานข้อมูลด้านล่าง

⚠️ **ห้ามเดา** — หากไม่มีหลักฐานชัดเจนในภาพ ต้องลดความเชื่อมั่น (confidence ต่ำ)

══════════════════════════════════════════════════════════════════
📌 **ขั้นตอนการวิเคราะห์** (ทำตามลำดับ)

**ขั้นที่ 1: สำรวจภาพรวม**
- ระบุชนิดพืช (ถ้าเป็นไปได้)
- สังเกตส่วนที่มีปัญหา: ใบอ่อน/ใบแก่/ใต้ใบ/ก้าน/ลำต้น/ผล/ราก/ดอก

**ขั้นที่ 2: วิเคราะห์ลักษณะแผล (Lesion Characteristics)**
- **รูปร่าง**: กลม/รี (Oval), รูปตา (Eye-shaped), หรือรูปร่างไม่แน่นอน (Irregular)
- **สี**: สีน้ำตาลเข้ม, สีเทากลางแผล, สีดำ, หรือมีวงสีเหลืองล้อมรอบ (Halo)
- **พื้นผิว**: ยุบตัวลง (Sunken), นูนขึ้น, หรือเป็นผง
- **ขอบแผล**: คม/ไม่ชัด/มี halo
- **ตำแหน่ง**: กระจาย/เป็นกลุ่ม/ตามเส้นใบ/ขอบใบ/ปลายใบ
- **ลักษณะพิเศษ**: ผงขาว/ราเทา/ใยรา/จุดดำ/ตุ่ม/รู/รอยขูด/เปียกน้ำ

**ขั้นที่ 3: ตรวจหาแมลง** (ถ้ามี)
- สี: เขียว/เหลือง/ดำ/ขาว/ส้ม/แดง
- ขนาด: เล็กมาก(<1มม.)/เล็ก(1-3มม.)/กลาง(3-10มม.)/ใหญ่(>10มม.)
- รูปร่าง: อวบกลม/เรียวยาว/ลิ่ม/แบน/มีปีก
- พฤติกรรม: อยู่นิ่ง/เคลื่อนที่เร็ว/กระโดด/บิน
- ร่องรอย: มูล/ไข่/ใย/รอยกัด/เส้นทางในใบ

**ขั้นที่ 4: เปรียบเทียบกับฐานข้อมูล**
ดูรายการโรค/แมลง/อาการขาดธาตุด้านล่าง และเลือกที่ตรงที่สุด

══════════════════════════════════════════════════════════════════
📚 **ฐานข้อมูลโรค/แมลง/อาการขาดธาตุ**

{disease_database_section}

══════════════════════════════════════════════════════════════════
⚠️ **กฎการแยกแยะโรคที่สำคัญ** (Differentiation Rules)

**1. โรคใบจุดสีน้ำตาล (Brown Spot) vs แอนแทรคโนส (Anthracnose)**
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

**2. กฎแมลง:**
- ❌ ห้ามสรุปว่าเป็น "เพลี้ยไฟ (Thrips)" หากแมลง **มีสีเขียว**
- ✅ แมลงสีเขียว → ตรวจสอบ: เพลี้ยอ่อน (ตัวอวบ) หรือ เพลี้ยจักจั่น (ตัวเรียว กระโดด)
- ✅ แมลงสีขาวบินเป็นกลุ่ม → แมลงหวี่ขาว
- ✅ ตัวขาวมีผงแป้ง → เพลี้ยแป้ง
- ✅ ตุ่ม/เกล็ดไม่เคลื่อนที่ → เพลี้ยหอย

**3. โรคเชื้อรา:**
- จุดกลมมีวงซ้อน + สีเทากลาง + halo เหลือง → Brown Spot / Leaf Spot
- แผลขอบคมตามขอบใบ ยุบตัว → Anthracnose
- ผงขาวบนใบ → Powdery Mildew
- ขนราใต้ใบ → Downy Mildew
- ตุ่มส้ม/สนิม → Rust

**4. อาการขาดธาตุ:**
- ใบล่างเหลืองทั้งแผ่น → ขาด N
- ใบเหลืองระหว่างเส้น เส้นใบเขียว + ใบล่าง → ขาด Mg
- ใบเหลืองระหว่างเส้น เส้นใบเขียว + ใบอ่อน → ขาด Fe
- ขอบใบไหม้ → ขาด K
- ใบม่วง/แดง → ขาด P
- ยอดตาย ใบอ่อนบิดงอ → ขาด Ca หรือ B

**5. กรณีไม่แน่ใจ:**
- ภาพเบลอ/ไม่ชัด → "ต้องการภาพที่ชัดเจนกว่านี้"
- อาการคล้ายหลายโรค → ระบุความเป็นไปได้หลายอย่าง + ลด confidence
- อาจเป็นขาดธาตุ → "อาจเป็นอาการขาดธาตุ ต้องการข้อมูลเพิ่มเติม"

══════════════════════════════════════════════════════════════════
📤 **รูปแบบคำตอบ** (JSON เท่านั้น)

{{
  "disease_name": "ชื่อโรค/แมลง/อาการ ภาษาไทย (ภาษาอังกฤษ)",
  "pest_type": "เชื้อรา/แบคทีเรีย/ไวรัส/แมลง/ไร/วัชพืช/ขาดธาตุ/unknown",
  "confidence_level_percent": 0-100,
  "confidence": "สูง/ปานกลาง/ต่ำ",
  "symptoms_in_image": "อาการที่เห็นในภาพ (สี, รูปร่าง, ตำแหน่ง, ขนาด)",
  "symptoms": "รายละเอียดอาการครบถ้วน",
  "possible_cause": "สาเหตุที่เป็นไปได้ + เหตุผลที่วินิจฉัยเช่นนี้",
  "differential_diagnosis": "โรค/แมลงอื่นที่คล้ายกัน และเหตุผลที่ตัดออก",
  "severity_level": "รุนแรง/ปานกลาง/เล็กน้อย",
  "severity": "เหตุผลที่ประเมินระดับความรุนแรงนี้",
  "description": "คำอธิบายโดยละเอียดและคำแนะนำเบื้องต้น",
  "affected_area": "ส่วนของต้นที่ได้รับผลกระทบ",
  "spread_risk": "สูง/ปานกลาง/ต่ำ",
  "additional_info_needed": "ข้อมูลเพิ่มเติมที่ต้องการ (ถ้ามี)"
}}

หากไม่พบปัญหาใดๆ:
{{
  "disease_name": "ไม่พบปัญหา",
  "pest_type": "healthy",
  "confidence_level_percent": 90,
  "confidence": "สูง",
  "symptoms_in_image": "พืชดูแข็งแรง ไม่พบอาการผิดปกติ",
  "symptoms": "ไม่มี",
  "description": "พืชดูแข็งแรงปกติ"
}}
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
        # Enhanced post‑processing using disease database and user info
        # -----------------------------------------------------------------

        # ดึงข้อมูลเพิ่มเติมจากฐานข้อมูล
        disease_info = get_disease_info(disease_name)
        if disease_info:
            logger.info(f"📚 Found disease in database: {disease_info.get('name_th')} ({disease_info.get('category')})")
            # เพิ่มข้อมูล differential diagnosis จากฐานข้อมูล
            if disease_info.get("distinguish_from"):
                description += f" | ⚠️ แยกจาก: {disease_info['distinguish_from']}"

        # Post-processing based on extra_user_info
        if extra_user_info:
            lowered = extra_user_info.lower()

            # แก้ไขการสับสน Leaf Spot vs Anthracnose
            if "จุด" in lowered and "กลม" in lowered:
                if "anthracnose" in disease_name.lower() or "แอนแทรคโนส" in disease_name:
                    logger.info("🔧 Adjusting: User described round spots → Leaf Spot")
                    disease_name = "โรคใบจุด (Leaf Spot)"
            if ("ขอบใบ" in lowered or "ปลายใบ" in lowered) and "แผล" in lowered:
                if "leaf spot" in disease_name.lower() or "ใบจุด" in disease_name:
                    logger.info("🔧 Adjusting: User described edge lesions → Anthracnose")
                    disease_name = "โรคแอนแทรคโนส (Anthracnose)"

            # แก้ไขการสับสนเพลี้ย
            if "สีเขียว" in lowered and "เพลี้ยไฟ" in disease_name.lower():
                logger.info("🔧 Adjusting: Green insect cannot be Thrips")
                if "อวบ" in lowered or "กลม" in lowered:
                    disease_name = "เพลี้ยอ่อน (Aphid)"
                else:
                    disease_name = "เพลี้ยจักจั่น (Leafhopper)"

            # แก้ไขการสับสนอาการขาดธาตุ
            if "เส้นใบเขียว" in lowered and "เหลือง" in lowered:
                if "ใบล่าง" in lowered or "ใบแก่" in lowered:
                    logger.info("🔧 Adjusting: Lower leaf chlorosis → Mg deficiency")
                    disease_name = "ขาดแมกนีเซียม (Mg Deficiency)"
                    pest_type = "ขาดธาตุ"
                elif "ใบอ่อน" in lowered or "ยอด" in lowered:
                    logger.info("🔧 Adjusting: Young leaf chlorosis → Fe deficiency")
                    disease_name = "ขาดเหล็ก (Fe Deficiency)"
                    pest_type = "ขาดธาตุ"

            # ตรวจสอบอาการขอบใบไหม้
            if "ขอบใบไหม้" in lowered or "ขอบใบแห้ง" in lowered:
                if "ขาด" not in disease_name.lower() and "blight" not in disease_name.lower():
                    logger.info("🔧 User mentioned leaf edge burn → checking K deficiency")
                    description += " | ⚠️ หมายเหตุ: อาจเป็นอาการขาดโพแทสเซียม (K) ด้วย"

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
