import logging
import json
import re
import io
import datetime
import asyncio
from typing import Optional
import base64
from PIL import Image
from fastapi import HTTPException
from openai import AsyncOpenAI
import httpx

from app.models import DiseaseDetectionResult
from app.config import OPENROUTER_API_KEY, USE_RAG_DETECTION
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

# Timeout configuration for API calls
API_TIMEOUT = 60  # seconds - ต้องตอบภายใน 60 วินาที

API_CONNECT_TIMEOUT = 15
  # seconds - timeout สำหรับ connection

# Initialize OpenRouter client for Gemini 3 Flash (disease detection)
gemini_client = None
if OPENROUTER_API_KEY:
    # สร้าง httpx client พร้อม timeout
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=API_CONNECT_TIMEOUT,
            read=API_TIMEOUT,
            write=API_TIMEOUT,
            pool=API_TIMEOUT
        )
    )
    gemini_client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
        http_client=http_client,
    )
    logger.info(f"OpenRouter (Gemini 3 Flash) initialized with {API_TIMEOUT}s timeout")


async def detect_disease(image_bytes: bytes, extra_user_info: Optional[str] = None) -> DiseaseDetectionResult:
    """Detect plant disease/pest from an image using Gemini 3 Flash via OpenRouter.

    The function:
    1. Checks cache (if no extra info).
    2. Builds a detailed prompt with examples.
    3. Calls Gemini 3 Flash (vision) via OpenRouter and expects a JSON response.
    4. Parses the response, applies simple post‑processing based on extra_user_info
       to disambiguate common confusions (e.g., leaf spot vs. Anthracnose).
    5. Returns a ``DiseaseDetectionResult`` model.
    """

    logger.info("Starting pest/disease detection with Gemini 3 Flash (via OpenRouter)")

    # Check if Gemini client is initialized
    if not gemini_client:
        logger.error("OpenRouter API key not configured for Gemini")
        raise HTTPException(status_code=500, detail="Disease detection service not configured")

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

**ขั้นที่ 3: ตรวจหาแมลง** (สำคัญมาก! ต้องสังเกตละเอียด)
- สี: เขียว/เหลือง/ดำ/ขาว/ส้ม/แดง/**น้ำตาล**
- ขนาด: เล็กมาก(<1มม.)/เล็ก(1-3มม.)/กลาง(3-10มม.)/ใหญ่(>10มม.)
- รูปร่าง: อวบกลม/เรียวยาว/**รูปลิ่ม**/แบน/มีปีก
- พฤติกรรม: อยู่นิ่ง/เคลื่อนที่เร็ว/**กระโดด**/บิน
- ร่องรอย: มูล/ไข่/ใย/รอยกัด/เส้นทางในใบ
- **⚠️ ตำแหน่งที่พบ**: บนใบ / ใต้ใบ / **โคนต้น** / กาบใบ

**🔴 สำคัญ: ถ้าเห็นแมลงในภาพ ต้องระบุว่าพบแมลง ห้ามบอกว่า "ไม่พบปัญหา"!**

**ขั้นที่ 4: เปรียบเทียบกับฐานข้อมูล**
ดูรายการโรค/แมลง/อาการขาดธาตุด้านล่าง และเลือกที่ตรงที่สุด

**ขั้นที่ 5: วิเคราะห์สาเหตุเชิงลึก (Root Cause Analysis)** ⭐ สำคัญมาก!
- ระบุสาเหตุที่เป็นไปได้ทั้งหมด พร้อมความน่าจะเป็น (%)
- วิเคราะห์ว่าอาการนี้อาจเกิดจากหลายปัจจัยร่วมกันหรือไม่
- หาความเชื่อมโยงระหว่าง สาเหตุ → อาการ → ผลกระทบ

**ตัวอย่าง Cause Chain ที่ต้องวิเคราะห์:**
- ใบมีรอยกัด + จุดน้ำตาล → หนอนกัดก่อน → เชื้อราเข้าทางแผล (2 ปัญหาซ้อนกัน)
- ใบเหลือง + ต้นแคระ → ขาดไนโตรเจน / หรือ รากเน่าจากน้ำขัง / หรือ เพลี้ยดูดน้ำเลี้ยง
- ใบไหม้จากขอบ → โรค BLB / หรือ ขาดโพแทสเซียม / หรือ เกลือในดินสูง / หรือ แดดเผา
- ใบด่าง + บิดงอ → ไวรัส / หรือ สารเคมีเข้มข้นเกินไป / หรือ 2,4-D ลอย

**ขั้นที่ 6: ระบุปัจจัยเสี่ยงและการป้องกัน**
- ปัจจัยสิ่งแวดล้อมที่อาจทำให้เกิดปัญหานี้ (ฤดูกาล, ความชื้น, การจัดการ)
- ปัจจัยที่อาจทำให้อาการรุนแรงขึ้น
- วิธีป้องกันไม่ให้เกิดซ้ำในอนาคต
- ระดับความเร่งด่วนในการรักษา

══════════════════════════════════════════════════════════════════
📚 **ฐานข้อมูลโรค/แมลง/อาการขาดธาตุ**

{disease_database_section}

══════════════════════════════════════════════════════════════════
🚨 **กฎการแยกแยะโรคที่สำคัญมาก** (CRITICAL Differentiation Rules)

**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
**🔴 1. วิธีแยก 3 โรคที่มักสับสน: Brown Spot vs Leaf Spot vs Anthracnose**
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**

| ลักษณะ | Brown Spot (จุดสีน้ำตาล) | Leaf Spot (ใบจุด) | Anthracnose (แอนแทรคโนส) |
|--------|-------------------------|-------------------|--------------------------|
| **พืชที่พบบ่อย** | ข้าว | พืชทั่วไป ผัก | มะม่วง พริก ไม้ผล |
| **รูปร่างจุด** | รูปไข่/เมล็ดงา (oval) | กลม/รี | ไม่แน่นอน (irregular) |
| **ตรงกลางจุด** | ✅ สีเทา/ขาว ชัดเจน | ❌ สีเดียวกัน | ❌ สีเข้มทั้งหมด |
| **Halo สีเหลือง** | ✅ ชัดมาก | ⚠️ อาจมีบ้าง | ❌ ไม่มี |
| **แผลยุบตัว** | ❌ ไม่ยุบ | ❌ ไม่ยุบ | ✅ ยุบตัวชัด (SUNKEN) |
| **ตำแหน่งแผล** | กระจายทั่วใบ | กระจายทั่วใบ | ขอบใบ/ปลายใบ → ลามเข้า |
| **สปอร์สีส้ม/ชมพู** | ❌ ไม่มี | ❌ ไม่มี | ✅ มี (สภาพชื้น) |

**🎯 วิธีจำง่าย:**
- **ข้าว + จุดรูปไข่ + ตรงกลางสีเทา + halo เหลือง** = **Brown Spot** ✅
- **พืชทั่วไป + จุดกลม + สีสม่ำเสมอ + กระจายทั่วใบ** = **Leaf Spot**
- **มะม่วง/พริก + แผลยุบตัว + เริ่มจากขอบใบ + อาจมีสปอร์ส้ม** = **Anthracnose** ✅

**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
**🟠 2. Anthracnose ในมะม่วง (Mango Anthracnose) - ลักษณะเฉพาะ**
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
- ใบ: แผลสีน้ำตาลดำ **ยุบตัว** เริ่มจาก **ขอบใบ/ปลายใบ** ลามเข้าเป็นรูป V
- ผล: แผล **บุ๋มสีดำ** ขยายวงกว้าง เนื้อเน่า
- ดอก: ดำ แห้ง ร่วง
- สภาพชื้น: มีสปอร์สีส้ม/ชมพู (salmon-pink)
- ❌ **ไม่มี halo สีเหลืองรอบแผล**
- ❌ **ไม่มีตรงกลางสีเทา/ขาว**

**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
**🥭 2.5 วิธีแยก Anthracnose vs Leaf Spot ในทุเรียน (CRITICAL!)**
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**

⚠️ **ทุเรียนเป็นพืชที่พบทั้ง 2 โรคนี้บ่อยมาก ต้องดูลักษณะให้ดี!**

| ลักษณะ | Anthracnose (แอนแทรคโนส) | Leaf Spot (ใบจุด) |
|--------|--------------------------|-------------------|
| **⭐ พื้นผิวแผล** | 🔻 **ยุบตัว/บุ๋ม (SUNKEN)** | ➖ **ราบเรียบ** |
| **⭐ ตำแหน่งเริ่มต้น** | **ขอบใบ/ปลายใบ** → ลามเข้า | **กระจายทั่วใบ** ไม่เริ่มจากขอบ |
| **รูปแบบการลาม** | เป็นรูป **V** จากปลายใบ | จุดแยกกัน ไม่รวมตัว |
| **สีแผล** | น้ำตาลเข้ม/ดำ | น้ำตาลอ่อน-กลาง สม่ำเสมอ |
| **ขอบแผล** | ไม่ชัด เนื้อเยื่อตาย | ขอบชัดเจน |
| **สปอร์สีส้ม/ชมพู** | ✅ มี (สภาพชื้น) | ❌ ไม่มี |
| **Halo สีเหลือง** | ❌ ไม่มี | ⚠️ อาจมีบ้าง |
| **เชื้อสาเหตุ** | Colletotrichum | Pestalotiopsis, Cercospora |

**🎯 วิธีจำง่ายสำหรับทุเรียน:**
- **แผลยุบตัว 🔻 + เริ่มจากขอบ/ปลายใบ + ลามเป็น V + สีดำ** = **Anthracnose** ✅
- **จุดราบเรียบ ➖ + กระจายทั่วใบ + ขอบชัด + สีน้ำตาลสม่ำเสมอ** = **Leaf Spot** ✅

**🔴 ข้อผิดพลาดที่ห้ามทำ (ทุเรียน):**
- ❌ เห็นจุดบนใบทุเรียน → ตอบว่า Anthracnose ทันที (ผิด! ต้องดูว่ายุบตัวไหม เริ่มจากขอบไหม)
- ❌ เห็นจุดกระจายทั่วใบทุเรียน → ตอบว่า Anthracnose (ผิด! Anthracnose เริ่มจากขอบ/ปลายใบ)
- ✅ จุดกระจายทั่วใบ + ไม่ยุบตัว = **Leaf Spot**
- ✅ แผลจากขอบใบ + ยุบตัว + สีดำ = **Anthracnose**

**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
**🟤 2.6 วิธีแยก 4 โรคที่สับสนบ่อยมาก: ใบจุดสาหร่าย vs ราสนิม vs ใบจุด vs แอนแทรคโนส**
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**

⚠️ **กฎสำคัญที่สุด: ดูที่ "พื้นผิวแผล" และ "สี" เป็นอันดับแรก!**

| ลักษณะ | ใบจุดสาหร่าย (Algal) | ราสนิม (Rust) | ใบจุด (Leaf Spot) | แอนแทรคโนส (Anthracnose) |
|--------|---------------------|---------------|-------------------|--------------------------|
| **⭐ พื้นผิวแผล** | 🔺 **นูน กำมะหยี่** | 🔺 **นูน เป็นผง** | ➖ **ราบเรียบ** | 🔻 **ยุบตัว** |
| **สาเหตุ** | สาหร่าย Cephaleuros | เชื้อรา Puccinia | เชื้อรา Cercospora | เชื้อรา Colletotrichum |
| **สีแผล** | ส้ม/แดงอิฐ/เขียวเทา | ⭐ **ส้มสด/สนิม** | น้ำตาล สม่ำเสมอ | น้ำตาลเข้ม/ดำ |
| **⭐ ผิวสัมผัส** | **ขรุขระ มีขนฟู** | **ผงสปอร์ติดมือ!** | เรียบ แห้ง | เรียบ หรือแห้งแตก |
| **ตำแหน่ง** | ผิวบนใบ | ⭐ **ใต้ใบ** เป็นหลัก | กระจายทั่วใบ | ขอบใบ/ปลายใบ |
| **รูปร่าง** | กลม ขอบชัด | ตุ่มเล็กกระจาย | กลม/รี ขอบชัด | ไม่แน่นอน (irregular) |
| **ขอบแผล** | ขอบนูนชัด | ไม่มีขอบชัด (ฟุ้ง) | ขอบราบ | ขอบคม เนื้อเยื่อตาย |
| **พืชที่พบบ่อย** | ทุเรียน มังคุด กาแฟ | ถั่ว อ้อย ข้าวโพด | พืชทั่วไป ผัก | มะม่วง พริก ทุเรียน |

**🎯 วิธีแยกง่ายๆ 4 โรค:**
- **จุดนูน 🔺 + สีส้ม/แดงอิฐ + ผิวกำมะหยี่ขรุขระ (ไม่ติดมือ)** = **ใบจุดสาหร่าย** 🟠
- **จุดนูน 🔺 + สีส้มสด + ผงสปอร์ติดมือ! + ใต้ใบ** = **ราสนิม (Rust)** 🟧
- **จุดราบเรียบ ➖ + สีน้ำตาลสม่ำเสมอ + กระจายทั่วใบ** = **ใบจุด (Leaf Spot)** 🟤
- **แผลยุบตัว 🔻 + สีน้ำตาลดำ + เริ่มจากขอบใบ/ปลายใบ** = **แอนแทรคโนส** ⚫

**⚠️ วิธีแยก "ใบจุดสาหร่าย" vs "ราสนิม" (ทั้งคู่สีส้ม!):**
- **ใบจุดสาหร่าย**: ผิว **ขรุขระเหมือนกำมะหยี่/ตะไคร่** มีขนฟู **ไม่มีผงติดมือ** พบ **ผิวบนใบ**
- **ราสนิม (Rust)**: ผิว **เป็นผงสปอร์ สัมผัสแล้วติดมือเป็นสีส้ม!** พบ **ใต้ใบ** เป็นหลัก

**🔴 ข้อผิดพลาดที่ห้ามทำ:**
- ❌ เห็นจุดสีส้ม/แดง → ตอบว่า Anthracnose (ผิด! Anthracnose สีน้ำตาลดำ ไม่ใช่ส้ม)
- ❌ เห็นจุดนูน → ตอบว่า Leaf Spot (ผิด! Leaf Spot จุดราบเรียบ ไม่นูน)
- ❌ เห็นจุดกลางใบ → ตอบว่า Anthracnose (ผิด! Anthracnose เริ่มจากขอบใบ/ปลายใบ)
- ❌ เห็นจุดสีส้มนูน → ตอบว่า Rust ทันที (ผิด! ต้องดูว่าผงติดมือไหม ถ้าไม่ติดมืออาจเป็น Algal)

**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
**🟡 3. โรคข้าว 3 โรคที่สับสนบ่อย: Rice Blast vs Brown Spot vs Bacterial Leaf Blight**
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**

| ลักษณะ | Rice Blast (โรคไหม้) | Brown Spot (จุดสีน้ำตาล) | Bacterial Leaf Blight (ขอบใบแห้ง) |
|--------|---------------------|-------------------------|----------------------------------|
| **รูปร่างแผล** | 💎 รูปเพชร/รูปตา หัวท้ายแหลม (SPINDLE/DIAMOND) | 🥚 รูปไข่/เมล็ดงา (OVAL) | 📏 เป็นทางยาวตามขอบใบ (LESION from EDGE) |
| **ตำแหน่งเริ่มต้น** | กระจายบนใบ | กระจายบนใบ | ⚠️ เริ่มจากขอบใบ/ปลายใบ เสมอ! |
| **ตรงกลางแผล** | ✅ สีเทา/ขาว | ✅ สีเทา/ขาว | ❌ ไม่มีจุดกลาง (แห้งทั้งแผล) |
| **Halo สีเหลือง** | ⚠️ อาจมีบ้าง | ✅ ชัดมาก | ❌ ไม่มี (ขอบหยักคลื่น) |
| **ขอบแผล** | เรียบ ชัด | เรียบ ชัด | 🌊 หยักคล้ายคลื่น (WAVY) |
| **อาการเพิ่มเติม** | คอรวงเน่า รวงหัก | เมล็ดด่าง | ใบม้วนตามยาว แห้งสีฟาง |
| **หยดน้ำยาง** | ❌ ไม่มี | ❌ ไม่มี | ✅ มี bacterial ooze สีเหลือง |

**🎯 วิธีจำง่ายสำหรับโรคข้าว:**
- **แผลรูปเพชร/ตา หัวท้ายแหลม** = **Rice Blast (โรคไหม้)** 💎
- **จุดรูปไข่ + ตรงกลางสีเทา + halo เหลืองชัด** = **Brown Spot** 🥚
- **แห้งจากขอบใบ/ปลายใบ + ขอบหยักคลื่น + ใบม้วน** = **Bacterial Leaf Blight (ขอบใบแห้ง)** 📏

**⚠️ ข้อควรระวัง:**
- Rice Blast: แผลขยายตามแนวยาวของใบ (ไม่กลม) เหมือนรูปเรือ
- Brown Spot: จุดกระจายทั่วใบ ไม่รวมกัน แต่ละจุดมีขอบชัด
- Bacterial Leaf Blight: แผลจะลามจากขอบ/ปลายเข้าสู่กลางใบ ไม่ใช่เป็นจุดแยก

**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
**🌾 3.5 โรคกาบใบข้าว 3 โรคที่สับสนบ่อยมาก: กาบใบแห้ง vs กาบใบเน่า vs ใบไหม้ (CRITICAL!)**
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**

⚠️ **ดูตำแหน่งของแผลก่อน! นี่คือ KEY สำคัญที่สุด!**

| ลักษณะ | กาบใบแห้ง (Sheath Blight) | กาบใบเน่า (Sheath Rot) | ใบไหม้ (Rice Blast) |
|--------|--------------------------|----------------------|---------------------|
| **⭐ ตำแหน่ง** | **กาบใบ** (ใกล้ระดับน้ำ) | **กาบใบธง** (ใกล้รวง) | **แผ่นใบ** (ไม่ใช่กาบ) |
| **เชื้อสาเหตุ** | Rhizoctonia solani | Sarocladium oryzae | Pyricularia oryzae |
| **รูปร่างแผล** | วงรี/รูปไข่ ใหญ่ (2-3 ซม.) | ไม่แน่นอน เป็นแถบ | 💎 รูปเพชร/ตา หัวท้ายแหลม |
| **สีแผล** | ขอบน้ำตาล ตรงกลางเทา/ขาว | น้ำตาลเข้ม/ดำ | ขอบน้ำตาล ตรงกลางเทา |
| **ลักษณะพิเศษ** | ⭐ มี **sclerotia** (เม็ดกลมสีน้ำตาลคล้ายเมล็ดผักกาด) | ⭐ ผงสปอร์สีขาว/ชมพู **รวงไม่ออก** | อาจลามไปคอรวง |
| **การลุกลาม** | จากกาบใบขึ้นไปใบ | กาบใบธงเน่า → รวงเสีย | จุดแยกกัน หรือลามคอรวง |
| **ระยะที่พบ** | แตกกอ-ตั้งท้อง | ออกรวง-เก็บเกี่ยว | ทุกระยะ |

**🎯 วิธีจำง่ายสำหรับโรคกาบใบข้าว:**
- **แผลที่กาบใบ (ไม่ใช่แผ่นใบ) + ใกล้ระดับน้ำ + มีเม็ด sclerotia สีน้ำตาล** = **กาบใบแห้ง (Sheath Blight)** 🟤
- **แผลที่กาบใบธง + สีน้ำตาลดำ + รวงข้าวไม่ออก/ลีบ** = **กาบใบเน่า (Sheath Rot)** ⚫
- **แผลรูปเพชร/ตาบนแผ่นใบ + ไม่ใช่ที่กาบใบ** = **ใบไหม้ (Rice Blast)** 💎

**🔴 ข้อผิดพลาดที่ห้ามทำ:**
- ❌ เห็นแผลที่กาบใบ → ตอบว่า Rice Blast (ผิด! Rice Blast อยู่บนแผ่นใบ)
- ❌ เห็นแผลรูปวงรีที่กาบใบ → ตอบว่า Leaf Blight (ผิด! ต้องเป็น Sheath Blight)
- ❌ เห็นรวงข้าวไม่ออก + กาบใบเปลี่ยนสี → ตอบว่า Rice Blast (ผิด! น่าจะเป็น Sheath Rot)
- ✅ แผลบน **กาบใบ** = Sheath Blight หรือ Sheath Rot
- ✅ แผลบน **แผ่นใบ** = Rice Blast หรือ Brown Spot หรือ Leaf Blight

**⚠️ กาบใบ vs แผ่นใบ คืออะไร?**
- **กาบใบ (Sheath)**: ส่วนที่หุ้มรอบลำต้น อยู่ใกล้โคน/ระดับน้ำ
- **แผ่นใบ (Leaf Blade)**: ส่วนใบที่แผ่ออก อยู่เหนือกาบใบขึ้นไป

**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
**🟢 4. กฎการแยกแยะเพลี้ย/แมลงปากดูด (CRITICAL - มักสับสนบ่อย!):**
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**

| **ลักษณะ**|**เพลี้ยไก่แจ้**|**เพลี้ยหอย**| **เพลี้ยอ่อน**| **เพลี้ยแป้ง**|
| --------- | ---------- | --------- | ----------- | ---------- |
| **ขนาด**  | 2–4 มม. | 1–5 มม.| 1–3 มม.  | 2–5 มม.|
| **สี**     | น้ำตาลอ่อน/เทา/เขียว | ขาว/น้ำตาล/ดำ (มีเปลือก) | เขียว/เหลือง/ดำ  | ขาวคล้ายปุยนุ่น   |
| **รูปร่าง**  | ตัวเรียว คล้ายจักจั่นจิ๋ว | กลม/รี มีเปลือกแข็ง      | อวบกลม นิ่ม      | รูปรี มีเส้นใยแป้ง |


| **มีเกราะ/เปลือก**| ไม่มี   | มีเกราะแข็ง | ไม่มี| ไม่มี (แต่มีผงแป้ง/เส้นใย)          |
| **พืชที่พบ** | ทุเรียน, ลำไย, มะม่วง, ส้ม, มะนาว | เกือบทุกพืช | เกือบทุกพืช | เกือบทุกพืช โดยเฉพาะไม้ผล–ไม้ประดับ |


**🎯 วิธีจำง่ายสำหรับเพลี้ย:**
- **เกาะทำมุม 45° ก้นชี้ขึ้น + ส้ม/มะนาว** = **เพลี้ยไก่แจ้** ⭐ (สำคัญ: พาหะโรคกรีนนิ่ง!)
- **อยู่นิ่งไม่ขยับ + มีเกราะ/เปลือกแข็ง** = **เพลี้ยหอย**
- **ตัวอวบกลม + สีเขียว/เหลือง** = **เพลี้ยอ่อน**
- **มีผงแป้งขาว + เส้นใยขาว** = **เพลี้ยแป้ง**

**⚠️ ข้อควรระวัง:**
- ❌ ห้ามสรุปว่าเป็น "เพลี้ยไฟ (Thrips)" หากแมลง **มีสีเขียว**
- ❌ ห้ามสับสน "เพลี้ยไก่แจ้" กับ "เพลี้ยหอย" - ดูการเคลื่อนที่และท่าเกาะ!
- ✅ แมลงสีเขียว → ตรวจสอบ: เพลี้ยอ่อน (ตัวอวบ) หรือ เพลี้ยจักจั่น (ตัวเรียว กระโดด)
- ✅ แมลงสีขาวบินเป็นกลุ่ม → แมลงหวี่ขาว
- ✅ ตัวขาวมีผงแป้ง → เพลี้ยแป้ง
- ✅ ตุ่ม/เกล็ดไม่เคลื่อนที่ → เพลี้ยหอย
- ✅ เกาะทำมุม 45° + พืชส้ม → เพลี้ยไก่แจ้

**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
**🌾 4.5 แมลงศัตรูข้าว (Rice Pests) - สำคัญมาก!:**
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**

| ลักษณะ | เพลี้ยกระโดดสีน้ำตาล (BPH) | เพลี้ยจักจั่นเขียว (GLH) | เพลี้ยกระโดดหลังขาว (WBPH) |
|--------|--------------------------|------------------------|---------------------------|
| **สี** | ⭐ น้ำตาลอ่อน-เข้ม | ⭐ เขียวสด | น้ำตาลอ่อน + แถบขาวที่หลัง |
| **ขนาด** | 2-3 มม. | 3-5 มม. | 2-3 มม. |
| **รูปร่าง** | ลิ่ม | เรียวยาว ลิ่ม | ลิ่ม |
| **ตำแหน่ง** | ⭐ โคนต้น/ระดับน้ำ | ⭐ บนใบ/ใต้ใบ | โคนต้น |
| **พฤติกรรม** | กระโดด | กระโดด/บิน | กระโดด |

**🎯 วิธีแยกเพลี้ยในข้าว:**
- **แมลงสีน้ำตาล + พบที่โคนต้นข้าว** = **เพลี้ยกระโดดสีน้ำตาล (BPH)** ⭐
- **แมลงสีเขียว + พบบนใบข้าว** = **เพลี้ยจักจั่นเขียว (GLH)** ⭐
- **แมลงสีน้ำตาล + มีแถบขาวที่หลัง** = **เพลี้ยกระโดดหลังขาว (WBPH)**

**🔴 ข้อผิดพลาดที่ห้ามทำ:**
- ❌ เห็นแมลงในข้าว → บอกว่า "ไม่พบปัญหา" (ผิด!)
- ❌ เห็นแมลงสีน้ำตาลในข้าว → บอกว่าเป็น "เพลี้ยจักจั่น" ทั่วไป (ต้องระบุว่าเป็น BPH!)
- ✅ ถ้าเห็นแมลงเล็กๆ สีน้ำตาลในข้าว → ต้องสรุปว่า "เพลี้ยกระโดดสีน้ำตาล"

**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
**🥭 4.6 แมลงศัตรูทุเรียนที่ทำลายใบ (Durian Leaf Pests) - สำคัญมาก!:**
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**

⚠️ **ทุเรียนมีอาการใบผิดปกติ 2 แบบหลักจากแมลง:**

| ลักษณะ | เพลี้ยจักจั่นฝอย (Durian Jassid) | เพลี้ยไฟ (Thrips) |
|--------|--------------------------------|-------------------|
| **⭐ อาการใบ** | ใบหงิก งอ โค้ง **ม้วนขึ้น** | ใบมีรอยขีดสีเงิน/น้ำตาล **ผิดรูป** |
| **อาการรุนแรง** | ใบแห้ง ร่วง เหลือแต่กิ่ง = **"ก้านธูป"** | ใบไหม้ เปลี่ยนสี ร่วง |
| **ขนาดแมลง** | 2-3 มม. | 1-2 มม. (เล็กมาก) |
| **สีแมลง** | เขียวอ่อน/เหลืองอ่อน | เหลือง/น้ำตาลอ่อน |
| **ตำแหน่งทำลาย** | ใบอ่อน ยอดอ่อน | ใบอ่อน ยอดอ่อน ดอก |
| **ลักษณะเฉพาะ** | กระโดดเมื่อถูกรบกวน | ตัวเรียวยาว มีปีก |
| **ร่องรอย** | ใบหงิกงอ ไม่มีรอยขีด | **รอยขีดสีเงิน/ขาว** บนใบ |

**🎯 วิธีแยก 2 แมลงนี้:**
- **ใบหงิก + งอ + ไม่มีรอยขีด + กิ่งเหลือแต่ก้าน (ก้านธูป)** = **เพลี้ยจักจั่นฝอย** ⭐
- **ใบมีรอยขีดสีเงิน/น้ำตาล + ใบผิดรูป + ไหม้** = **เพลี้ยไฟ** ⭐

**🔴 ข้อผิดพลาดที่ห้ามทำ (ทุเรียน):**
- ❌ เห็นใบทุเรียนหงิก/ก้านธูป → บอกว่าเป็นโรค (ผิด! น่าจะเป็นเพลี้ยจักจั่นฝอย)
- ❌ เห็นรอยขีดสีเงินบนใบทุเรียน → บอกว่าเป็นโรค (ผิด! น่าจะเป็นเพลี้ยไฟ)
- ✅ ใบหงิก + ก้านธูป = **ต้องสรุปว่า "เพลี้ยจักจั่นฝอย (Durian Jassid)"**
- ✅ รอยขีดสีเงิน + ใบผิดรูป = **ต้องสรุปว่า "เพลี้ยไฟ (Thrips)"**

**⚠️ หมายเหตุ: ทั้งเพลี้ยจักจั่นฝอยและเพลี้ยไฟ อาจเป็นพาหะของโรคอื่นได้ด้วย!**

**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
**🔵 5. อาการขาดธาตุ vs โรค (CRITICAL - มักสับสนบ่อยมาก!):**
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**

**⚠️ กฎสำคัญ: ใบเหลืองไม่จำเป็นต้องเป็นโรค!**

| ลักษณะ | ขาดธาตุอาหาร | โรคพืช (เชื้อรา/แบคทีเรีย) |
|--------|-------------|--------------------------|
| **สีใบ** | เหลืองสม่ำเสมอทั้งใบ/เป็นบริเวณกว้าง | มีจุด/แผล/ขีดสีต่างจากรอบๆ |
| **มีจุด/แผล** | ❌ ไม่มีจุดหรือแผล | ✅ มีจุด/แผลชัดเจน |
| **ขอบแผล** | ❌ ไม่มีขอบ | ✅ มีขอบชัด อาจมี halo |
| **ตำแหน่งเริ่ม** | ใบล่าง (N,Mg,K) หรือ ใบอ่อน (Fe,Ca) | กระจาย หรือ จุดใดจุดหนึ่ง |
| **การลาม** | ค่อยๆ ลามทั้งต้น | ลามจากจุดแผลออกไป |

**🎯 วิธีแยก "ใบเหลือง" (ขาดธาตุ) vs "โรค":**
- **ใบเหลืองทั้งใบ + ไม่มีจุด/แผล** = **ขาดธาตุอาหาร** ✅
- **ใบเหลือง + มีจุดหรือแผลเห็นชัด** = **โรค** (ตรวจสอบเพิ่ม)
- **ใบเหลืองเฉพาะระหว่างเส้นใบ + เส้นใบยังเขียว** = **ขาด Fe หรือ Mg** ✅

**รายละเอียดอาการขาดธาตุ:**
| ธาตุ | อาการ | ตำแหน่ง |
|-----|-------|--------|
| **N (ไนโตรเจน)** | ใบเหลืองซีดทั้งใบ ต้นแคระ | ใบล่างก่อน → ลามขึ้น |
| **Mg (แมกนีเซียม)** | เหลืองระหว่างเส้น เส้นใบเขียว | ใบล่าง/ใบแก่ |
| **Fe (เหล็ก)** | เหลืองระหว่างเส้น เส้นใบเขียว | ใบอ่อน/ยอด |
| **K (โพแทสเซียม)** | ขอบใบไหม้ ใบม้วน | ใบล่าง |
| **P (ฟอสฟอรัส)** | ใบม่วง/แดง | ใบล่าง |
| **Ca (แคลเซียม)** | ยอดตาย ใบอ่อนบิดงอ | ยอด/ใบอ่อน |

**❌ ข้อผิดพลาดที่พบบ่อย:**
- เห็นใบเหลือง → สรุปว่าเป็นโรค (ผิด! ต้องดูว่ามีจุด/แผลไหม)
- เห็นใบเหลืองในข้าว → สรุปว่าเป็น Brown Spot (ผิด! Brown Spot ต้องมีจุดสีน้ำตาลชัดเจน)

**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
**⚠️ 6. กรณีไม่แน่ใจ:**
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**
- ภาพเบลอ/ไม่ชัด → "ต้องการภาพที่ชัดเจนกว่านี้"
- อาการคล้ายหลายโรค → ระบุความเป็นไปได้หลายอย่าง + ลด confidence
- ใบเหลืองไม่มีจุด/แผล → **ต้องสรุปว่า "ขาดธาตุอาหาร"** ไม่ใช่โรค!

══════════════════════════════════════════════════════════════════
📤 **รูปแบบคำตอบ** (JSON เท่านั้น)

{{
  "plant_type": "ชนิดพืชที่เห็นในภาพ เช่น ข้าว, มะม่วง, พริก, ผักทั่วไป",
  "disease_name": "ชื่อโรค/แมลง/อาการ ภาษาไทย (ภาษาอังกฤษ) - ต้องระบุให้ถูกต้องตามชนิดพืช",
  "pest_type": "เชื้อรา/แบคทีเรีย/ไวรัส/แมลง/ไร/วัชพืช/ขาดธาตุ/unknown",
  "confidence_level_percent": 0-100,
  "confidence": "สูง/ปานกลาง/ต่ำ",
  "symptoms_in_image": "อาการที่เห็นในภาพ (สี, รูปร่าง, ตำแหน่ง, ขนาด, ยุบตัวหรือไม่, มี halo หรือไม่)",
  "key_diagnostic_features": "ลักษณะสำคัญที่ใช้วินิจฉัย เช่น ตรงกลางสีเทา, แผลยุบตัว, halo เหลือง",
  "symptoms": "รายละเอียดอาการครบถ้วน",
  "possible_cause": "สาเหตุที่เป็นไปได้ + เหตุผลที่วินิจฉัยเช่นนี้",
  "differential_diagnosis": "โรค/แมลงอื่นที่คล้ายกัน และเหตุผลที่ตัดออก (เช่น ไม่ใช่ Leaf Spot เพราะ...)",
  "severity_level": "รุนแรง/ปานกลาง/เล็กน้อย",
  "severity": "เหตุผลที่ประเมินระดับความรุนแรงนี้",
  "description": "คำอธิบายโดยละเอียดและคำแนะนำเบื้องต้น",
  "affected_area": "ส่วนของต้นที่ได้รับผลกระทบ",
  "spread_risk": "สูง/ปานกลาง/ต่ำ",
  "additional_info_needed": "ข้อมูลเพิ่มเติมที่ต้องการ (ถ้ามี)",

  "possible_causes": [
    {{"cause": "สาเหตุหลัก", "probability": 70, "reason": "เหตุผลที่คิดว่าเป็นสาเหตุนี้", "evidence": "หลักฐานที่เห็นในภาพ"}},
    {{"cause": "สาเหตุรอง (ถ้ามี)", "probability": 20, "reason": "เหตุผล", "evidence": "หลักฐาน"}}
  ],
  "cause_chain": "อธิบายลำดับความเชื่อมโยง: สาเหตุ → อาการ → ผลกระทบ (เช่น ใส่ปุ๋ย N มาก → ต้นอ่อนแอ → เชื้อราเข้าง่าย → ใบไหม้)",
  "contributing_factors": ["ปัจจัยที่อาจทำให้อาการรุนแรงขึ้น เช่น ความชื้นสูง, ปลูกถี่"],
  "risk_factors": ["ปัจจัยเสี่ยงที่ควรระวัง เช่น หน้าฝน, เคยเป็นโรคนี้มาก่อน"],
  "prevention": ["วิธีป้องกันระยะยาว เช่น ปลูกให้โปร่ง, ลดปุ๋ย N, เลือกพันธุ์ต้านทาน"],
  "treatment_priority": "เร่งด่วน/ปานกลาง/ไม่เร่งด่วน - พร้อมเหตุผล"
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
        # Call Gemini 3 Flash via OpenRouter (vision model)
        # -----------------------------------------------------------------

        system_instruction = """คุณคือผู้เชี่ยวชาญโรคพืช ตอบเป็น JSON เท่านั้น (ไม่ต้องใส่ ```json)
ตอบกระชับ แต่ละ field ไม่เกิน 100 ตัวอักษร
ห้ามมี field ซ้ำกัน

"""

        # เรียก API พร้อม timeout handling
        try:
            response = await asyncio.wait_for(
                gemini_client.chat.completions.create(
                    model="google/gemini-3-flash-preview",  # Upgraded from 2.5 Pro
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": system_instruction + prompt_text},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                                },
                            ],
                        }
                    ],
                    max_tokens=8192,
                    extra_headers={
                        "HTTP-Referer": "https://ladda-chatbot.railway.app",
                        "X-Title": "Ladda Plant Disease Detection",
                    },
                ),
                timeout=API_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.error(f"Gemini API timeout after {API_TIMEOUT} seconds")
            # Return fallback result instead of raising exception
            return DiseaseDetectionResult(
                disease_name="ไม่สามารถวิเคราะห์ได้ (Timeout)",
                confidence="ต่ำ",
                symptoms="ระบบไม่สามารถวิเคราะห์ภาพได้ในเวลาที่กำหนด",
                severity="ไม่ทราบ",
                raw_analysis="API Timeout - กรุณาลองใหม่อีกครั้ง หรือส่งภาพที่ชัดเจนกว่านี้",
                plant_type="",
            )
        except httpx.TimeoutException as e:
            logger.error(f"HTTP timeout error: {e}")
            return DiseaseDetectionResult(
                disease_name="ไม่สามารถวิเคราะห์ได้ (Connection Timeout)",
                confidence="ต่ำ",
                symptoms="ไม่สามารถเชื่อมต่อกับระบบวิเคราะห์ได้",
                severity="ไม่ทราบ",
                raw_analysis="Connection Timeout - กรุณาลองใหม่อีกครั้ง",
                plant_type="",
            )
        except httpx.ConnectError as e:
            logger.error(f"HTTP connection error: {e}")
            return DiseaseDetectionResult(
                disease_name="ไม่สามารถวิเคราะห์ได้ (Connection Error)",
                confidence="ต่ำ",
                symptoms="ไม่สามารถเชื่อมต่อกับระบบวิเคราะห์ได้",
                severity="ไม่ทราบ",
                raw_analysis="Connection Error - กรุณาลองใหม่อีกครั้ง",
                plant_type="",
            )

        raw_text = response.choices[0].message.content
        logger.info(f"Gemini raw response: {raw_text[:500]}...")

        # -----------------------------------------------------------------
        # Parse JSON (Gemini may wrap JSON in markdown code blocks)
        # -----------------------------------------------------------------
        try:
            # Clean up raw_text - remove markdown code blocks
            json_str = raw_text.strip()

            # Remove ```json or ``` at the beginning
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            elif json_str.startswith("```"):
                json_str = json_str[3:]

            # Remove ``` at the end
            if json_str.endswith("```"):
                json_str = json_str[:-3]

            json_str = json_str.strip()

            # Try to find JSON object if there's extra text
            if not json_str.startswith("{"):
                # Find the first { and last }
                start_idx = json_str.find("{")
                end_idx = json_str.rfind("}")
                if start_idx != -1 and end_idx != -1:
                    json_str = json_str[start_idx:end_idx + 1]

            logger.info(f"Cleaned JSON string (first 200 chars): {json_str[:200]}...")
            data = json.loads(json_str)
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

        # Parse new Root Cause Analysis fields
        possible_causes = data.get("possible_causes") or []
        cause_chain = data.get("cause_chain") or ""
        contributing_factors = data.get("contributing_factors") or []
        risk_factors = data.get("risk_factors") or []
        prevention = data.get("prevention") or []
        treatment_priority = data.get("treatment_priority") or "ปานกลาง"
        plant_type = data.get("plant_type") or ""
        key_diagnostic_features = data.get("key_diagnostic_features") or ""
        differential_diagnosis = data.get("differential_diagnosis") or ""

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

            # =================================================================
            # แก้ไขการสับสน Leaf Spot vs Anthracnose (โดยเฉพาะทุเรียน!)
            # =================================================================
            is_durian = any(x in lowered for x in ["ทุเรียน", "durian"])

            # ลักษณะของ Leaf Spot: จุดกลม กระจายทั่วใบ ราบเรียบ
            leafspot_signs = ["จุดกลม", "กระจาย", "ราบเรียบ", "ไม่ยุบ", "กลางใบ", "ทั่วใบ"]
            has_leafspot_signs = any(kw in lowered for kw in leafspot_signs)

            # ลักษณะของ Anthracnose: ยุบตัว เริ่มจากขอบ/ปลายใบ ลามเป็น V สีดำ
            anthracnose_signs = ["ยุบ", "บุ๋ม", "sunken", "ขอบใบ", "ปลายใบ", "ลาม", "รูป v", "สีดำ"]
            has_anthracnose_signs = any(kw in lowered for kw in anthracnose_signs)

            # ถ้าเป็นทุเรียน ให้ใช้กฎเฉพาะ
            if is_durian:
                if has_leafspot_signs and not has_anthracnose_signs:
                    if "anthracnose" in disease_name.lower() or "แอนแทรคโนส" in disease_name:
                        logger.info("🔧 Durian: Round scattered flat spots → Leaf Spot, not Anthracnose")
                        disease_name = "โรคใบจุดทุเรียน (Durian Leaf Spot)"
                        description += " | ⚠️ เป็นโรคใบจุด ไม่ใช่แอนแทรคโนส เพราะจุดกระจายทั่วใบและไม่ยุบตัว"

                if has_anthracnose_signs and not has_leafspot_signs:
                    if "leaf spot" in disease_name.lower() or "ใบจุด" in disease_name:
                        logger.info("🔧 Durian: Sunken edge lesions → Anthracnose, not Leaf Spot")
                        disease_name = "โรคแอนแทรคโนสทุเรียน (Durian Anthracnose)"
                        description += " | ⚠️ เป็นแอนแทรคโนส ไม่ใช่ใบจุด เพราะแผลยุบตัวและเริ่มจากขอบใบ"
            else:
                # กฎทั่วไปสำหรับพืชอื่น
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

            # =================================================================
            # แก้ไขการสับสนเพลี้ยไก่แจ้ vs เพลี้ยหอย (CRITICAL!)
            # =================================================================
            is_citrus = any(x in lowered for x in ["ส้ม", "มะนาว", "มะกรูด", "ส้มโอ", "citrus", "lime", "orange"])

            # เพลี้ยไก่แจ้ detection (ท่าเกาะ 45° + ส้ม/มะนาว + เคลื่อนที่ได้)
            psyllid_keywords = ["45", "มุม", "ก้นชี้", "เอียง", "กระโดด", "บิน", "เคลื่อนที่", "ไก่แจ้", "psyllid"]
            if any(kw in lowered for kw in psyllid_keywords) or is_citrus:
                if "เพลี้ยหอย" in disease_name or "scale" in disease_name.lower():
                    # ถ้าพบ keyword ของเพลี้ยไก่แจ้ แต่ GPT ตอบเพลี้ยหอย → แก้ไข
                    if any(kw in lowered for kw in ["45", "มุม", "ก้นชี้", "เอียง", "กระโดด", "บิน", "ไก่แจ้", "psyllid"]):
                        logger.info("🔧 Adjusting: 45° posture / movement / citrus → Citrus Psyllid, not Scale")
                        disease_name = "เพลี้ยไก่แจ้ (Asian Citrus Psyllid)"
                        pest_type = "แมลง"
                        description += " | ⚠️ สำคัญ: เพลี้ยไก่แจ้เป็นพาหะโรคกรีนนิ่ง (HLB) ในพืชตระกูลส้ม!"

            # เพลี้ยหอย detection (อยู่นิ่ง + มีเกราะ)
            scale_keywords = ["อยู่นิ่ง", "ไม่ขยับ", "เกราะ", "เปลือก", "เกล็ด", "ตุ่ม"]
            if any(kw in lowered for kw in scale_keywords):
                if "เพลี้ยไก่แจ้" in disease_name or "psyllid" in disease_name.lower():
                    logger.info("🔧 Adjusting: Stationary + shell → Scale Insect, not Psyllid")
                    disease_name = "เพลี้ยหอย (Scale Insect)"
                    pest_type = "แมลง"

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

            # =================================================================
            # แก้ไขการสับสนโรคข้าว 3 โรค: Rice Blast vs Brown Spot vs BLB
            # =================================================================
            is_rice = "ข้าว" in lowered or "rice" in lowered

            # Rice Blast detection
            if is_rice and ("รูปเพชร" in lowered or "รูปตา" in lowered or "หัวแหลม" in lowered or "ท้ายแหลม" in lowered or "spindle" in lowered or "diamond" in lowered or "คอรวง" in lowered or "รวงหัก" in lowered):
                if "brown spot" in disease_name.lower() or "จุดสีน้ำตาล" in disease_name:
                    logger.info("🔧 Adjusting: Rice + spindle/diamond shape → Rice Blast, not Brown Spot")
                    disease_name = "โรคไหม้ข้าว (Rice Blast)"
                    pest_type = "เชื้อรา"

            # Brown Spot detection (รูปไข่ + ตรงกลางสีเทา + halo เหลือง)
            if is_rice and ("รูปไข่" in lowered or "oval" in lowered) and ("กลางสีเทา" in lowered or "กลางขาว" in lowered or "halo" in lowered):
                if "blast" in disease_name.lower() or "ไหม้" in disease_name or "blight" in disease_name.lower() or "ขอบใบแห้ง" in disease_name:
                    logger.info("🔧 Adjusting: Rice + oval + grey center + halo → Brown Spot")
                    disease_name = "โรคจุดสีน้ำตาลข้าว (Rice Brown Spot)"
                    pest_type = "เชื้อรา"

            # Bacterial Leaf Blight detection (เริ่มจากขอบใบ + ขอบหยัก/คลื่น + ใบม้วน)
            if is_rice and ("ขอบใบ" in lowered or "ปลายใบ" in lowered) and ("แห้ง" in lowered or "หยัก" in lowered or "คลื่น" in lowered or "ม้วน" in lowered or "wavy" in lowered):
                if "brown spot" in disease_name.lower() or "จุดสีน้ำตาล" in disease_name or "blast" in disease_name.lower() or "ไหม้" in disease_name:
                    logger.info("🔧 Adjusting: Rice + edge lesion + wavy margin → Bacterial Leaf Blight")
                    disease_name = "โรคขอบใบแห้งข้าว (Bacterial Leaf Blight)"
                    pest_type = "แบคทีเรีย"

            # =================================================================
            # แก้ไขการสับสน 4 โรค: ใบจุดสาหร่าย vs ราสนิม vs ใบจุด vs แอนแทรคโนส (CRITICAL!)
            # =================================================================

            # Keywords สำหรับแต่ละโรค
            algal_keywords = ["กำมะหยี่", "ขรุขระ", "ตะไคร่", "สาหร่าย", "algal", "velvet", "เขียวเทา", "cephaleuros"]
            rust_keywords = ["ผง", "สปอร์", "ติดมือ", "rust", "ราสนิม", "สนิม", "pustule", "ใต้ใบ", "puccinia"]
            leafspot_keywords = ["ราบ", "เรียบ", "flat", "สม่ำเสมอ", "กลางใบ", "กระจาย"]
            anthracnose_keywords = ["ยุบ", "บุ๋ม", "sunken", "ขอบใบ", "ปลายใบ", "ลาม", "เน่า", "ดำ", "irregular"]
            orange_keywords = ["ส้ม", "แดงอิฐ", "orange", "สนิม", "rust"]

            has_algal = any(kw in lowered for kw in algal_keywords)
            has_rust = any(kw in lowered for kw in rust_keywords)
            has_leafspot = any(kw in lowered for kw in leafspot_keywords)
            has_anthracnose = any(kw in lowered for kw in anthracnose_keywords)
            has_orange = any(kw in lowered for kw in orange_keywords)
            has_raised = "นูน" in lowered or "raised" in lowered

            # 1. ใบจุดสาหร่าย: จุดนูน + สีส้ม/แดงอิฐ + ผิวขรุขระกำมะหยี่ (ไม่ใช่ผง)
            if has_algal and has_raised and has_orange and not has_anthracnose:
                if "rust" in disease_name.lower() or "ราสนิม" in disease_name or "leaf spot" in disease_name.lower() or "ใบจุด" in disease_name:
                    logger.info("🔧 Adjusting: Raised/velvety/orange spots → Algal Leaf Spot")
                    disease_name = "โรคใบจุดสาหร่าย (Algal Leaf Spot)"
                    pest_type = "สาหร่าย"
                    description += " | ⚠️ สาเหตุจากสาหร่าย Cephaleuros (ไม่ใช่เชื้อรา) พบมากในสวนชื้น ร่มเงา"

            # 2. ราสนิม (Rust): จุดนูน + สีส้ม + ผงสปอร์ติดมือ + ใต้ใบ
            if has_rust and has_orange and not has_algal:
                if "algal" in disease_name.lower() or "สาหร่าย" in disease_name:
                    logger.info("🔧 Adjusting: Powdery orange pustules → Rust, not Algal")
                    disease_name = "โรคราสนิม (Rust)"
                    pest_type = "เชื้อรา"
                    description += " | ⚠️ เชื้อรา Puccinia - สปอร์ติดมือเป็นสีส้ม พบใต้ใบเป็นหลัก"

            # 3. แอนแทรคโนส: แผลยุบตัว + สีน้ำตาลดำ + เริ่มจากขอบใบ
            if has_anthracnose and not has_algal and not has_rust:
                if "สาหร่าย" in disease_name or "algal" in disease_name.lower():
                    logger.info("🔧 Adjusting: Sunken/black/edge lesion → Anthracnose")
                    disease_name = "โรคแอนแทรคโนส (Anthracnose)"
                    pest_type = "เชื้อรา"
                elif "leaf spot" in disease_name.lower() or "ใบจุด" in disease_name:
                    if "ขอบใบ" in lowered or "ปลายใบ" in lowered or "ยุบ" in lowered or "บุ๋ม" in lowered:
                        logger.info("🔧 Adjusting: Edge lesion + sunken → Anthracnose, not Leaf Spot")
                        disease_name = "โรคแอนแทรคโนส (Anthracnose)"
                        pest_type = "เชื้อรา"
                elif "rust" in disease_name.lower() or "ราสนิม" in disease_name:
                    logger.info("🔧 Adjusting: Sunken/black → Anthracnose, not Rust")
                    disease_name = "โรคแอนแทรคโนส (Anthracnose)"
                    pest_type = "เชื้อรา"

            # 4. ใบจุด (Leaf Spot): จุดราบเรียบ + สีน้ำตาลสม่ำเสมอ + กระจายทั่วใบ
            if has_leafspot and not has_algal and not has_anthracnose and not has_rust:
                if "anthracnose" in disease_name.lower() or "แอนแทรคโนส" in disease_name:
                    logger.info("🔧 Adjusting: Flat/even spots scattered → Leaf Spot, not Anthracnose")
                    disease_name = "โรคใบจุด (Leaf Spot)"
                    pest_type = "เชื้อรา"
                elif "สาหร่าย" in disease_name or "algal" in disease_name.lower():
                    logger.info("🔧 Adjusting: Flat brown spots → Leaf Spot, not Algal")
                    disease_name = "โรคใบจุด (Leaf Spot)"
                    pest_type = "เชื้อรา"

        # Build raw_analysis for downstream use (include Root Cause Analysis)
        raw_parts = [f"{pest_type}: {description}"]
        if affected_area:
            raw_parts.append(f"ส่วนที่ได้รับผลกระทบ: {affected_area}")
        if spread_risk:
            raw_parts.append(f"ความเสี่ยงการแพร่: {spread_risk}")

        # Add Root Cause Analysis to raw_analysis
        if plant_type:
            raw_parts.append(f"ชนิดพืช: {plant_type}")
        if key_diagnostic_features:
            raw_parts.append(f"ลักษณะสำคัญ: {key_diagnostic_features}")
        if possible_causes:
            causes_str = "; ".join([f"{c.get('cause', '')} ({c.get('probability', 0)}%)" for c in possible_causes if isinstance(c, dict)])
            if causes_str:
                raw_parts.append(f"สาเหตุที่เป็นไปได้: {causes_str}")
        if cause_chain:
            raw_parts.append(f"ลำดับสาเหตุ: {cause_chain}")
        if contributing_factors:
            raw_parts.append(f"ปัจจัยเสริม: {', '.join(contributing_factors) if isinstance(contributing_factors, list) else contributing_factors}")
        if risk_factors:
            raw_parts.append(f"ปัจจัยเสี่ยง: {', '.join(risk_factors) if isinstance(risk_factors, list) else risk_factors}")
        if prevention:
            raw_parts.append(f"การป้องกัน: {', '.join(prevention) if isinstance(prevention, list) else prevention}")
        if treatment_priority and treatment_priority != "ปานกลาง":
            raw_parts.append(f"ความเร่งด่วน: {treatment_priority}")

        result = DiseaseDetectionResult(
            disease_name=str(disease_name),
            confidence=str(confidence),
            symptoms=str(symptoms),
            severity=str(severity),
            raw_analysis=" | ".join(raw_parts),
            plant_type=str(plant_type) if plant_type else "",
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
                "model": "gemini-2.5-pro-preview",
            }
            logger.debug(f"Detection log: {log_entry}")
        except Exception as e:
            logger.warning(f"Failed to log detection: {e}")

        return result

    except Exception as e:
        logger.error(f"Error in pest/disease detection: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Detection failed: {str(e)}")


# ============================================================================
# Disease Detection v2: Vector Search First (No Hardcode Prompt)
# ============================================================================

async def detect_disease_v2(image_bytes: bytes, extra_user_info: Optional[str] = None) -> DiseaseDetectionResult:
    """
    Disease Detection v2 - Vector Search เป็นหลัก (ไม่ใช้ hardcode prompt)

    Architecture:
    1. Gemini Vision (Quick) → ระบุชื่อโรค/keywords จากภาพ (~3-5s) - prompt สั้น
    2. Vector Search (Supabase) → ดึงข้อมูลโรคจาก DB (~0.5s)
    3. Gemini Analysis → สรุปผลจากข้อมูล DB (~3-5s)

    ข้อดี:
    - Prompt size ลด 70-80%
    - Token cost ลดลงมาก
    - อัพเดทโรคได้ผ่าน Database โดยไม่ต้อง deploy
    """
    from app.services.disease_search import search_diseases, build_context_from_diseases, get_disease_by_key
    from app.services.quick_classifier import ClassificationResult, ProblemCategory

    logger.info("🚀 Starting Disease Detection v2 (Vector Search First)")

    # Check if Gemini client is initialized
    if not gemini_client:
        logger.error("OpenRouter API key not configured")
        raise HTTPException(status_code=500, detail="Disease detection service not configured")

    # ---------------------------------------------------------------------
    # Cache lookup
    # ---------------------------------------------------------------------
    cache_key = None
    if not extra_user_info:
        cache_key = get_image_hash(image_bytes)
        cached = await get_from_cache("detection_v2", cache_key)
        if cached:
            logger.info("✓ Using cached v2 detection result")
            return DiseaseDetectionResult(**cached)

    try:
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        # -----------------------------------------------------------------
        # Step 1: Quick Vision - ระบุโรค/แมลง/ปัญหาจากภาพ (prompt สั้น)
        # -----------------------------------------------------------------
        logger.info("👁️ Step 1: Quick Vision (Identify Problem)")

        quick_prompt = """คุณคือผู้เชี่ยวชาญโรคพืชไทย ดูภาพและระบุปัญหาที่เห็น

ตอบเป็น JSON (ไม่ต้องใส่ ```json):
{
  "plant_type": "ชนิดพืช (ข้าว/ทุเรียน/มะม่วง/อ้อย/ข้าวโพด/มันสำปะหลัง/ยางพารา/ไม่ทราบ)",
  "problem_type": "fungal/bacterial/viral/insect/nutrient/weed/healthy/unknown",
  "problem_name_th": "ชื่อโรค/แมลง/ปัญหา ภาษาไทย",
  "problem_name_en": "English name",
  "keywords": ["คำสำคัญ", "สำหรับค้นหา", "3-5 คำ"],
  "visual_symptoms": "อาการที่เห็นในภาพ",
  "confidence": 0-100,
  "severity": "รุนแรง/ปานกลาง/เล็กน้อย"
}

หมายเหตุ:
- fungal = เชื้อรา (จุด, ไหม้, ราขาว, ราดำ, ราสนิม)
- bacterial = แบคทีเรีย (เน่าเละ, เหี่ยว, แผลฉ่ำน้ำ)
- viral = ไวรัส (ด่าง, หงิก, แคระ)
- insect = แมลง (เพลี้ย, หนอน, ด้วง, ไร)
- nutrient = ขาดธาตุ (ใบเหลืองสม่ำเสมอ)
- healthy = ไม่พบปัญหา"""

        if extra_user_info:
            quick_prompt += f"\n\nข้อมูลจากผู้ใช้: {extra_user_info}"

        try:
            response1 = await asyncio.wait_for(
                gemini_client.chat.completions.create(
                    model="google/gemini-3-flash-preview",  # ใช้ 3 Flash สำหรับ vision (เร็ว + แม่นยำ)
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": quick_prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                                },
                            ],
                        }
                    ],
                    max_tokens=1000,
                    temperature=0.1,
                    extra_headers={
                        "HTTP-Referer": "https://ladda-chatbot.railway.app",
                        "X-Title": "Ladda v2 Vision",
                    },
                ),
                timeout=60
            )
        except asyncio.TimeoutError:
            logger.error("Quick Vision timeout - Fallback to v1")
            return await detect_disease(image_bytes, extra_user_info)
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.error(f"HTTP error in quick vision - Fallback to v1: {e}")
            return await detect_disease(image_bytes, extra_user_info)

        raw_text1 = response1.choices[0].message.content
        logger.info(f"Quick Vision response: {raw_text1[:200]}...")

        # Parse quick vision result with robust JSON handling
        import re
        quick_data = None

        try:
            json_str = raw_text1.strip()

            # Extract JSON from markdown code block
            if "```" in json_str:
                match = re.search(r'```(?:json)?\s*([\s\S]*?)```', json_str)
                if match:
                    json_str = match.group(1)

            # Find JSON object
            start_idx = json_str.find("{")
            end_idx = json_str.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = json_str[start_idx:end_idx + 1]

            # Clean JSON - fix common Gemini issues
            json_str = json_str.strip()
            json_str = re.sub(r',\s*}', '}', json_str)  # trailing comma before }
            json_str = re.sub(r',\s*]', ']', json_str)  # trailing comma before ]
            json_str = re.sub(r'//.*$', '', json_str, flags=re.MULTILINE)  # comments
            json_str = re.sub(r'/\*[\s\S]*?\*/', '', json_str)  # block comments

            quick_data = json.loads(json_str)
            logger.info("✓ JSON parsed successfully")

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed: {e}, trying regex extraction...")

            # Fallback: Extract fields using regex
            quick_data = {}

            # Extract plant_type
            match = re.search(r'"plant_type"\s*:\s*"([^"]*)"', raw_text1)
            if match:
                quick_data["plant_type"] = match.group(1)

            # Extract problem_type
            match = re.search(r'"problem_type"\s*:\s*"([^"]*)"', raw_text1)
            if match:
                quick_data["problem_type"] = match.group(1)

            # Extract problem_name_th
            match = re.search(r'"problem_name_th"\s*:\s*"([^"]*)"', raw_text1)
            if match:
                quick_data["problem_name_th"] = match.group(1)

            # Extract problem_name_en
            match = re.search(r'"problem_name_en"\s*:\s*"([^"]*)"', raw_text1)
            if match:
                quick_data["problem_name_en"] = match.group(1)

            # Extract keywords array
            match = re.search(r'"keywords"\s*:\s*\[(.*?)\]', raw_text1, re.DOTALL)
            if match:
                keywords_str = match.group(1)
                quick_data["keywords"] = re.findall(r'"([^"]*)"', keywords_str)

            # Extract visual_symptoms
            match = re.search(r'"visual_symptoms"\s*:\s*"([^"]*)"', raw_text1)
            if match:
                quick_data["visual_symptoms"] = match.group(1)

            # Extract confidence
            match = re.search(r'"confidence"\s*:\s*(\d+)', raw_text1)
            if match:
                quick_data["confidence"] = int(match.group(1))

            # Extract severity
            match = re.search(r'"severity"\s*:\s*"([^"]*)"', raw_text1)
            if match:
                quick_data["severity"] = match.group(1)

            if quick_data.get("plant_type") or quick_data.get("problem_name_th"):
                logger.info(f"✓ Regex extraction successful: {quick_data}")
            else:
                logger.warning("✗ Regex extraction failed")

        # Set defaults for missing fields
        if not quick_data:
            quick_data = {}

        quick_data.setdefault("plant_type", "")
        quick_data.setdefault("problem_type", "unknown")
        quick_data.setdefault("problem_name_th", "ไม่ทราบ")
        quick_data.setdefault("problem_name_en", "Unknown")
        quick_data.setdefault("keywords", [])
        quick_data.setdefault("visual_symptoms", raw_text1[:200] if raw_text1 else "")
        quick_data.setdefault("confidence", 50)
        quick_data.setdefault("severity", "ปานกลาง")

        plant_type = quick_data.get("plant_type", "")
        problem_type = quick_data.get("problem_type", "unknown")
        problem_name_th = quick_data.get("problem_name_th", "ไม่ทราบ")
        problem_name_en = quick_data.get("problem_name_en", "")
        keywords = quick_data.get("keywords", [])
        visual_symptoms = quick_data.get("visual_symptoms", "")
        quick_confidence = quick_data.get("confidence", 50)
        severity = quick_data.get("severity", "ปานกลาง")

        logger.info(f"   → Plant: {plant_type}")
        logger.info(f"   → Problem: {problem_name_th} ({problem_type})")
        logger.info(f"   → Keywords: {keywords}")

        # ถ้า Quick Vision ล้มเหลว (ไม่มี plant_type และ problem เป็น unknown) → ใช้ v1 แทน
        if not plant_type and problem_type == "unknown" and problem_name_th == "ไม่ทราบ":
            logger.warning("⚠️ Quick Vision failed - Fallback to v1")
            return await detect_disease(image_bytes, extra_user_info)

        # Handle healthy plants early
        if problem_type == "healthy":
            result = DiseaseDetectionResult(
                disease_name="ไม่พบปัญหา",
                confidence="90",
                symptoms="พืชดูแข็งแรง ไม่พบอาการผิดปกติ",
                severity="ไม่มี",
                raw_analysis="พืชแข็งแรงปกติ ไม่พบโรค/แมลง/อาการขาดธาตุ",
                plant_type=plant_type,
            )
            if cache_key:
                await set_to_cache("detection_v2", cache_key, result.dict())
            return result

        # -----------------------------------------------------------------
        # Step 2: Vector Search - ดึงข้อมูลจาก Database
        # -----------------------------------------------------------------
        logger.info("🔍 Step 2: Vector Search (Fetch from Database)")

        # สร้าง classification สำหรับ vector search
        classification = ClassificationResult(
            category=ProblemCategory(problem_type) if problem_type in [e.value for e in ProblemCategory] else ProblemCategory.UNKNOWN,
            plant_type=plant_type,
            confidence=float(quick_confidence) / 100,
            keywords=keywords + [problem_name_th, problem_name_en],
            summary=f"{problem_name_th} ({problem_name_en})"
        )

        matched_diseases = await search_diseases(classification, top_k=5)

        if matched_diseases:
            logger.info(f"   → Found {len(matched_diseases)} diseases in DB:")
            for i, d in enumerate(matched_diseases[:3], 1):
                logger.info(f"      {i}. {d.name_th} ({d.name_en}) - {d.similarity:.2f}")
        else:
            logger.warning("   → No diseases found in database")

        # Build RAG context from matched diseases
        rag_context = build_context_from_diseases(matched_diseases) if matched_diseases else ""

        # -----------------------------------------------------------------
        # Step 3: Final Analysis - สรุปผลด้วยข้อมูลจาก DB
        # -----------------------------------------------------------------
        logger.info("🎯 Step 3: Final Analysis (Using DB Context)")

        if rag_context:
            final_prompt = f"""คุณคือผู้เชี่ยวชาญโรคพืช วิเคราะห์ภาพและให้คำแนะนำ

📋 **ข้อมูลเบื้องต้นจากระบบ:**
- พืช: {plant_type}
- ปัญหาเบื้องต้น: {problem_name_th} ({problem_name_en})
- อาการที่เห็น: {visual_symptoms}

📚 **ข้อมูลโรคจากฐานข้อมูล:**
{rag_context}

══════════════════════════════════════════════════════════════════
🎯 **ภารกิจ**: ดูภาพและเปรียบเทียบกับข้อมูลข้างต้น แล้วสรุปว่าเป็นโรคใด

ตอบเป็น JSON (ไม่ต้องใส่ ```json):
{{
  "disease_name": "ชื่อโรค/แมลง ไทย (English)",
  "confidence": 0-100,
  "matched_disease_from_db": "ชื่อโรคที่ match จาก DB (ถ้ามี)",
  "symptoms": "อาการที่เห็นในภาพ",
  "severity": "รุนแรง/ปานกลาง/เล็กน้อย",
  "cause": "สาเหตุ",
  "treatment": "วิธีรักษา/แก้ไข",
  "prevention": "การป้องกัน"
}}"""
        else:
            # ไม่มีข้อมูลใน DB - ให้วิเคราะห์ตามความรู้ทั่วไป
            final_prompt = f"""คุณคือผู้เชี่ยวชาญโรคพืช วิเคราะห์ภาพและให้คำแนะนำ

📋 **ข้อมูลเบื้องต้น:**
- พืช: {plant_type}
- ปัญหาเบื้องต้น: {problem_name_th}
- อาการที่เห็น: {visual_symptoms}

⚠️ ไม่พบข้อมูลในฐานข้อมูล กรุณาวิเคราะห์ตามความรู้ทั่วไป

ตอบเป็น JSON (ไม่ต้องใส่ ```json):
{{
  "disease_name": "ชื่อโรค/แมลง ไทย (English)",
  "confidence": 0-100,
  "matched_disease_from_db": null,
  "symptoms": "อาการที่เห็นในภาพ",
  "severity": "รุนแรง/ปานกลาง/เล็กน้อย",
  "cause": "สาเหตุ",
  "treatment": "วิธีรักษา/แก้ไข",
  "prevention": "การป้องกัน"
}}"""

        try:
            response2 = await asyncio.wait_for(
                gemini_client.chat.completions.create(
                    model="google/gemini-2.0-flash-001",  # ใช้ Flash สำหรับสรุปผล (เร็ว)
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": final_prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                                },
                            ],
                        }
                    ],
                    max_tokens=1500,
                    temperature=0.2,
                    extra_headers={
                        "HTTP-Referer": "https://ladda-chatbot.railway.app",
                        "X-Title": "Ladda v2 Summary",
                    },
                ),
                timeout=30
            )
        except asyncio.TimeoutError:
            logger.error("Final Analysis timeout - using quick result")
            # Fallback to quick vision result
            result = DiseaseDetectionResult(
                disease_name=problem_name_th,
                confidence=str(quick_confidence),
                symptoms=visual_symptoms,
                severity=severity,
                raw_analysis=f"Quick analysis: {problem_name_th}",
                plant_type=plant_type,
            )
            if cache_key:
                await set_to_cache("detection_v2", cache_key, result.dict())
            return result

        raw_text2 = response2.choices[0].message.content
        logger.info(f"Final Analysis response: {raw_text2[:200]}...")

        # Parse final analysis result
        try:
            json_str = raw_text2.strip()
            if json_str.startswith("```"):
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]

            if not json_str.strip().startswith("{"):
                start_idx = json_str.find("{")
                end_idx = json_str.rfind("}")
                if start_idx != -1 and end_idx != -1:
                    json_str = json_str[start_idx:end_idx + 1]

            final_data = json.loads(json_str.strip())
        except Exception as e:
            logger.warning(f"Failed to parse final analysis JSON: {e}")
            final_data = {
                "disease_name": problem_name_th,
                "confidence": quick_confidence,
                "symptoms": visual_symptoms,
                "severity": severity,
            }

        # Extract final result
        disease_name = final_data.get("disease_name") or problem_name_th
        confidence = str(final_data.get("confidence", quick_confidence))
        symptoms = final_data.get("symptoms") or visual_symptoms
        final_severity = final_data.get("severity") or severity
        cause = final_data.get("cause", "")
        treatment = final_data.get("treatment", "")
        prevention = final_data.get("prevention", "")
        matched_db = final_data.get("matched_disease_from_db", "")

        # Build raw analysis
        raw_parts = [f"โรค/ปัญหา: {disease_name}"]
        if matched_db:
            raw_parts.append(f"🔍 DB Match: {matched_db}")
        if cause:
            raw_parts.append(f"สาเหตุ: {cause}")
        if treatment:
            raw_parts.append(f"การรักษา: {treatment}")
        if prevention:
            raw_parts.append(f"การป้องกัน: {prevention}")

        result = DiseaseDetectionResult(
            disease_name=str(disease_name),
            confidence=str(confidence),
            symptoms=str(symptoms),
            severity=str(final_severity),
            raw_analysis=" | ".join(raw_parts),
            plant_type=str(plant_type),
        )

        # Cache result
        if cache_key:
            await set_to_cache("detection_v2", cache_key, result.dict())

        logger.info(f"✅ v2 Detection complete: {result.disease_name} (Confidence: {confidence}%)")

        return result

    except Exception as e:
        logger.error(f"Error in v2 detection: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Detection v2 failed: {str(e)}")


# ============================================================================
# Smart Detect: Auto-select v1 or v2 based on feature flag
# ============================================================================

async def smart_detect_disease(image_bytes: bytes, extra_user_info: Optional[str] = None) -> DiseaseDetectionResult:
    """
    Smart disease detection that chooses v1 or v2 based on USE_RAG_DETECTION flag.

    - USE_RAG_DETECTION=1: Use v2 (RAG + Vector Search) - faster, cheaper
    - USE_RAG_DETECTION=0: Use v1 (hardcoded database) - original behavior
    """
    if USE_RAG_DETECTION:
        logger.info("Using Disease Detection v2 (RAG + Vector Search)")
        return await detect_disease_v2(image_bytes, extra_user_info)
    else:
        logger.info("Using Disease Detection v1 (Hardcoded Database)")
        return await detect_disease(image_bytes, extra_user_info)
