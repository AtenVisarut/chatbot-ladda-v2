"""
Agro-Risk Service
บริการตรวจสอบสภาพอากาศและความเสี่ยงทางการเกษตร
"""

import logging
import httpx
from typing import Dict, Optional, Any

from app.config import AGRO_RISK_API_URL

logger = logging.getLogger(__name__)

# Timeout configuration
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


async def check_weather(lat: float, lng: float) -> Dict[str, Any]:
    """
    ตรวจสอบสภาพอากาศจากพิกัด GPS

    Args:
        lat: ละติจูด
        lng: ลองจิจูด

    Returns:
        Dict containing:
        - success: bool
        - flexMessage: LINE Flex Message พร้อมใช้งาน (ถ้าสำเร็จ)
        - error: error message (ถ้าล้มเหลว)
    """
    try:
        url = f"{AGRO_RISK_API_URL}/api/v1/weather/check"

        payload = {
            "latitude": lat,
            "longitude": lng
        }

        logger.info(f"Checking weather for location: ({lat}, {lng})")

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


async def analyze_crop_risk(lat: float, lng: float, crop_type: str) -> Dict[str, Any]:
    """
    วิเคราะห์ความเสี่ยงสำหรับพืชเฉพาะชนิด

    Args:
        lat: ละติจูด
        lng: ลองจิจูด
        crop_type: ประเภทพืช (เช่น "ข้าว", "ข้าวโพด", "มันสำปะหลัง")

    Returns:
        Dict containing:
        - success: bool
        - flexMessage: LINE Flex Message พร้อมใช้งาน (ถ้าสำเร็จ)
        - error: error message (ถ้าล้มเหลว)
    """
    try:
        url = f"{AGRO_RISK_API_URL}/api/v1/risk/analyze"

        payload = {
            "latitude": lat,
            "longitude": lng,
            "cropType": crop_type
        }

        logger.info(f"Analyzing crop risk for {crop_type} at ({lat}, {lng})")

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


def create_weather_error_flex(error_message: str) -> Dict:
    """
    สร้าง Flex Message สำหรับแสดง error
    หมายเหตุ: ใช้ message action แทน location action เพราะ location ใช้ใน Flex button ไม่ได้
    """
    return {
        "type": "flex",
        "altText": "ไม่สามารถดูสภาพอากาศได้",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "❌ เกิดข้อผิดพลาด",
                        "color": "#ffffff",
                        "size": "lg",
                        "weight": "bold",
                        "align": "center"
                    }
                ],
                "backgroundColor": "#E74C3C",
                "paddingAll": "15px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": error_message,
                        "size": "sm",
                        "color": "#666666",
                        "wrap": True,
                        "align": "center"
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "action": {
                            "type": "message",
                            "label": "🔄 ลองใหม่อีกครั้ง",
                            "text": "ดูสภาพอากาศ"
                        },
                        "color": "#27AE60"
                    }
                ]
            }
        }
    }


def create_weather_request_quick_reply() -> Dict:
    """
    สร้าง Quick Reply สำหรับขอ location
    ใช้ action type: location เพื่อให้ LINE ขอพิกัดจาก user
    """
    return {
        "items": [
            {
                "type": "action",
                "action": {
                    "type": "location",
                    "label": "🌤️ ดูสภาพอากาศในพื้นที่"
                }
            }
        ]
    }


def create_crop_selection_flex(lat: float, lng: float) -> Dict:
    """
    สร้าง Flex Message สำหรับเลือกประเภทพืชเพื่อวิเคราะห์ความเสี่ยง
    """
    crops = [
        {"name": "ข้าว", "icon": "🌾"},
        {"name": "ข้าวโพด", "icon": "🌽"},
        {"name": "มันสำปะหลัง", "icon": "🥔"},
        {"name": "อ้อย", "icon": "🎋"},
    ]

    buttons = []
    for crop in crops:
        buttons.append({
            "type": "button",
            "style": "secondary",
            "height": "sm",
            "action": {
                "type": "postback",
                "label": f"{crop['icon']} {crop['name']}",
                "data": f"action=analyze_crop_risk&lat={lat}&lng={lng}&crop={crop['name']}"
            }
        })

    return {
        "type": "flex",
        "altText": "เลือกประเภทพืชเพื่อวิเคราะห์ความเสี่ยง",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "🌱 วิเคราะห์ความเสี่ยงพืช",
                        "color": "#ffffff",
                        "size": "lg",
                        "weight": "bold",
                        "align": "center"
                    }
                ],
                "backgroundColor": "#27AE60",
                "paddingAll": "15px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "เลือกประเภทพืชที่ต้องการวิเคราะห์",
                        "size": "sm",
                        "color": "#666666",
                        "align": "center",
                        "wrap": True
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": buttons
            }
        }
    }
