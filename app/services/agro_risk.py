"""
Agro-Risk Service
บริการตรวจสอบสภาพอากาศและความเสี่ยงทางการเกษตร
"""

import logging
import httpx
from typing import Dict, Optional, Any, List

from app.config import AGRO_RISK_API_URL

logger = logging.getLogger(__name__)

# Timeout configuration
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Crop type mapping - แปลงชื่อพืชภาษาไทยเป็น API crop type
CROP_TYPE_MAP = {
    "ข้าว": "rice",
    "นาข้าว": "rice",
    "ข้าวโพด": "corn",
    "มันสำปะหลัง": "cassava",
    "อ้อย": "sugarcane",
    "ยางพารา": "rubber",
    "ปาล์ม": "palm",
    "ปาล์มน้ำมัน": "palm",
    # พืชใหม่ 4 ชนิดที่ API รองรับ
    "ทุเรียน": "durian",
    "มะม่วง": "mango",
    "ลำไย": "longan",
    "องุ่น": "grape",
    # พืชอื่นๆ
    "มังคุด": "fruit",
    "ลิ้นจี่": "fruit",
    "เงาะ": "fruit",
    "ส้ม": "fruit",
    "มะนาว": "fruit",
    "ผัก": "vegetable",
    "พืชผัก": "vegetable",
}


def get_crop_type(thai_crop_name: str) -> Optional[str]:
    """แปลงชื่อพืชภาษาไทยเป็น API crop type"""
    if not thai_crop_name:
        return None
    return CROP_TYPE_MAP.get(thai_crop_name, thai_crop_name.lower())


async def check_weather(
    lat: float,
    lng: float,
    address: Optional[str] = None,
    crops: Optional[List[str]] = None,
    growth_stage: str = "vegetative"
) -> Dict[str, Any]:
    """
    ตรวจสอบสภาพอากาศจากพิกัด GPS

    Args:
        lat: ละติจูด
        lng: ลองจิจูด
        address: ที่อยู่จาก LINE location message (optional)
        crops: รายการพืชที่ปลูก (ภาษาไทย) จาก user data (optional)
        growth_stage: ระยะการเจริญเติบโต (default: vegetative)

    Returns:
        Dict containing:
        - success: bool
        - flexMessage: LINE Flex Message พร้อมใช้งาน (ถ้าสำเร็จ)
        - error: error message (ถ้าล้มเหลว)
    """
    try:
        url = f"{AGRO_RISK_API_URL}/api/v1/weather/check"

        # Build payload
        payload = {
            "location": {
                "latitude": lat,
                "longitude": lng
            },
            "address": address
        }

        # Add crops info if available (support multiple crops)
        if crops and len(crops) > 0:
            crops_list = []
            for crop in crops:
                api_crop_type = get_crop_type(crop)
                if api_crop_type:
                    crops_list.append({
                        "type": api_crop_type,
                        "name": crop,  # ส่งชื่อภาษาไทยด้วย
                        "growthStage": growth_stage
                    })
            if crops_list:
                payload["crops"] = crops_list
                logger.info(f"Including crops info: {crops} -> {[c['type'] for c in crops_list]}")

        logger.info(f"Checking weather for location: ({lat}, {lng}), address: {address}, crops: {crops}")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(url, json=payload)

            if response.status_code == 200:
                data = response.json()
                logger.info(f"Weather check successful for ({lat}, {lng})")
                return {
                    "success": True,
                    "flexMessage": data.get("flexMessage"),
                    "data": data
                }
            else:
                logger.error(f"Weather API error: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "error": f"API Error: {response.status_code}"
                }

    except httpx.TimeoutException:
        logger.error(f"Weather API timeout for ({lat}, {lng})")
        return {
            "success": False,
            "error": "การเชื่อมต่อหมดเวลา กรุณาลองใหม่อีกครั้ง"
        }
    except Exception as e:
        logger.error(f"Weather check error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def analyze_crop_risk(lat: float, lng: float, crop_type: str, growth_stage: str = "vegetative") -> Dict[str, Any]:
    """
    วิเคราะห์ความเสี่ยงสำหรับพืชเฉพาะชนิด

    Args:
        lat: ละติจูด
        lng: ลองจิจูด
        crop_type: ประเภทพืช (เช่น "ข้าว", "ข้าวโพด", "มันสำปะหลัง")
        growth_stage: ระยะการเจริญเติบโต (default: "vegetative")

    Returns:
        Dict containing:
        - success: bool
        - flexMessage: LINE Flex Message พร้อมใช้งาน (ถ้าสำเร็จ)
        - error: error message (ถ้าล้มเหลว)
    """
    try:
        url = f"{AGRO_RISK_API_URL}/api/v1/risk/analyze"

        # Map Thai crop names to API crop types
        crop_type_map = {
            "ข้าว": "rice",
            "ข้าวโพด": "corn",
            "มันสำปะหลัง": "cassava",
            "อ้อย": "sugarcane",
            "ทุเรียน": "durian",
            "มะม่วง": "mango",
            "ลำไย": "longan",
            "องุ่น": "grape",
        }

        api_crop_type = crop_type_map.get(crop_type, crop_type.lower())

        payload = {
            "location": {
                "latitude": lat,
                "longitude": lng
            },
            "crop": {
                "type": api_crop_type,
                "growthStage": growth_stage
            }
        }

        logger.info(f"Analyzing crop risk for {crop_type} ({api_crop_type}) at ({lat}, {lng})")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(url, json=payload)

            if response.status_code == 200:
                data = response.json()
                logger.info(f"Crop risk analysis successful for {crop_type}")
                return {
                    "success": True,
                    "flexMessage": data.get("flexMessage"),
                    "data": data
                }
            else:
                logger.error(f"Risk API error: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "error": f"API Error: {response.status_code}"
                }

    except httpx.TimeoutException:
        logger.error(f"Risk API timeout for {crop_type} at ({lat}, {lng})")
        return {
            "success": False,
            "error": "การเชื่อมต่อหมดเวลา กรุณาลองใหม่อีกครั้ง"
        }
    except Exception as e:
        logger.error(f"Risk analysis error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def get_weather_forecast(lat: float, lng: float, days: int = 7, address: Optional[str] = None) -> Dict[str, Any]:
    """
    ดึงพยากรณ์อากาศ 7 วัน

    Args:
        lat: ละติจูด
        lng: ลองจิจูด
        days: จำนวนวันที่ต้องการพยากรณ์ (default: 7)
        address: ชื่อจังหวัด/ที่อยู่ (optional)

    Returns:
        Dict containing:
        - success: bool
        - flexMessage: LINE Flex Message พร้อมใช้งาน (ถ้าสำเร็จ)
        - error: error message (ถ้าล้มเหลว)
    """
    try:
        url = f"{AGRO_RISK_API_URL}/api/v1/weather/forecast"

        payload = {
            "location": {
                "latitude": lat,
                "longitude": lng
            },
            "days": days
        }

        # Add address if provided
        if address:
            payload["address"] = address

        logger.info(f"Getting weather forecast for ({lat}, {lng}), days: {days}, address: {address}")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(url, json=payload)

            if response.status_code == 200:
                data = response.json()
                logger.info(f"Weather forecast successful for ({lat}, {lng})")
                return {
                    "success": True,
                    "flexMessage": data.get("flexMessage"),
                    "data": data
                }
            else:
                logger.error(f"Forecast API error: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "error": f"API Error: {response.status_code}"
                }

    except httpx.TimeoutException:
        logger.error(f"Forecast API timeout for ({lat}, {lng})")
        return {
            "success": False,
            "error": "การเชื่อมต่อหมดเวลา กรุณาลองใหม่อีกครั้ง"
        }
    except Exception as e:
        logger.error(f"Forecast error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def create_weather_error_text(error_message: str) -> str:
    """
    สร้างข้อความ error สภาพอากาศ
    """
    return (
        f"❌ เกิดข้อผิดพลาด\n\n"
        f"{error_message}\n\n"
        "พิมพ์ \"ดูสภาพอากาศ\" เพื่อลองใหม่อีกครั้งค่ะ"
    )


def create_crop_selection_text() -> str:
    """
    สร้างข้อความให้เลือกประเภทพืชเพื่อวิเคราะห์ความเสี่ยง
    """
    return (
        "🌱 วิเคราะห์ความเสี่ยงพืช\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "กรุณาพิมพ์ชื่อพืชที่ต้องการวิเคราะห์:\n\n"
        "🌾 ข้าว\n"
        "🌽 ข้าวโพด\n"
        "🥔 มันสำปะหลัง\n"
        "🎋 อ้อย\n"
        "🥝 ทุเรียน\n"
        "🫐 ลำไย\n"
        "🥭 มะม่วง\n"
        "🍇 องุ่น"
    )
