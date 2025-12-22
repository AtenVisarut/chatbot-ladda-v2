"""
Rich Menu Service
สร้างและจัดการ Rich Menu ผ่าน LINE Messaging API
"""

import logging
import httpx
from typing import Optional, Dict, Any

from app.config import LINE_CHANNEL_ACCESS_TOKEN, LIFF_URL

logger = logging.getLogger(__name__)

# LINE API Base URL
LINE_API_BASE = "https://api.line.me/v2/bot"

# Rich Menu Configuration
RICH_MENU_CONFIG = {
    "size": {
        "width": 2500,
        "height": 1686
    },
    "selected": True,
    "name": "Ladda Bot Menu",
    "chatBarText": "เมนู",
    "areas": [
        {
            # A: ลงทะเบียน (บนซ้าย)
            "bounds": {"x": 0, "y": 0, "width": 1250, "height": 843},
            "action": {
                "type": "uri",
                "label": "ลงทะเบียน",
                "uri": LIFF_URL
            }
        },
        {
            # B: กรุณาแนบรูปใบพืชจากแกลเลอรี 📷 (บนขวา) - เปิดแกลเลอรี่
            "bounds": {"x": 1250, "y": 0, "width": 1250, "height": 843},
            "action": {
                "type": "cameraRoll",
                "label": "กรุณาแนบรูปใบพืชจากแกลเลอรี 📷"
            }
        },
        {
            # C: ดูสภาพอากาศ (ล่างซ้าย) - เปิด Location picker
            "bounds": {"x": 0, "y": 843, "width": 1250, "height": 843},
            "action": {
                "type": "location",
                "label": "ดูสภาพอากาศ"
            }
        },
        {
            # D: ช่วยเหลือ (ล่างขวา)
            "bounds": {"x": 1250, "y": 843, "width": 1250, "height": 843},
            "action": {
                "type": "message",
                "label": "ช่วยเหลือ",
                "text": "ช่วยเหลือ"
            }
        }
    ]
}


def get_headers() -> Dict[str, str]:
    """Get authorization headers for LINE API"""
    return {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }


async def create_rich_menu() -> Optional[str]:
    """
    สร้าง Rich Menu และ return rich menu ID
    """
    try:
        url = f"{LINE_API_BASE}/richmenu"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers=get_headers(),
                json=RICH_MENU_CONFIG
            )

            if response.status_code == 200:
                data = response.json()
                rich_menu_id = data.get("richMenuId")
                logger.info(f"Created Rich Menu: {rich_menu_id}")
                return rich_menu_id
            else:
                logger.error(f"Failed to create Rich Menu: {response.status_code} - {response.text}")
                return None

    except Exception as e:
        logger.error(f"Error creating Rich Menu: {e}")
        return None


async def upload_rich_menu_image(rich_menu_id: str, image_path: str) -> bool:
    """
    อัปโหลดรูปภาพสำหรับ Rich Menu

    Args:
        rich_menu_id: ID ของ Rich Menu
        image_path: path ไปยังไฟล์รูปภาพ (PNG หรือ JPEG)
    """
    try:
        url = f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content"

        # Read image file
        with open(image_path, "rb") as f:
            image_data = f.read()

        # Determine content type
        content_type = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"

        headers = {
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": content_type
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, content=image_data)

            if response.status_code == 200:
                logger.info(f"Uploaded image for Rich Menu: {rich_menu_id}")
                return True
            else:
                logger.error(f"Failed to upload image: {response.status_code} - {response.text}")
                return False

    except Exception as e:
        logger.error(f"Error uploading Rich Menu image: {e}")
        return False


async def set_default_rich_menu(rich_menu_id: str) -> bool:
    """
    ตั้ง Rich Menu เป็น default สำหรับทุก user
    """
    try:
        url = f"{LINE_API_BASE}/user/all/richmenu/{rich_menu_id}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers=get_headers()
            )

            if response.status_code == 200:
                logger.info(f"Set default Rich Menu: {rich_menu_id}")
                return True
            else:
                logger.error(f"Failed to set default: {response.status_code} - {response.text}")
                return False

    except Exception as e:
        logger.error(f"Error setting default Rich Menu: {e}")
        return False


async def delete_rich_menu(rich_menu_id: str) -> bool:
    """ลบ Rich Menu"""
    try:
        url = f"{LINE_API_BASE}/richmenu/{rich_menu_id}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(url, headers=get_headers())

            if response.status_code == 200:
                logger.info(f"Deleted Rich Menu: {rich_menu_id}")
                return True
            else:
                logger.error(f"Failed to delete: {response.status_code} - {response.text}")
                return False

    except Exception as e:
        logger.error(f"Error deleting Rich Menu: {e}")
        return False


async def get_rich_menu_list() -> list:
    """ดึงรายการ Rich Menu ทั้งหมด"""
    try:
        url = f"{LINE_API_BASE}/richmenu/list"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=get_headers())

            if response.status_code == 200:
                data = response.json()
                return data.get("richmenus", [])
            else:
                logger.error(f"Failed to get list: {response.status_code} - {response.text}")
                return []

    except Exception as e:
        logger.error(f"Error getting Rich Menu list: {e}")
        return []


async def get_default_rich_menu() -> Optional[str]:
    """ดึง default Rich Menu ID"""
    try:
        url = f"{LINE_API_BASE}/user/all/richmenu"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=get_headers())

            if response.status_code == 200:
                data = response.json()
                return data.get("richMenuId")
            else:
                return None

    except Exception as e:
        logger.error(f"Error getting default Rich Menu: {e}")
        return None


async def delete_default_rich_menu() -> bool:
    """ยกเลิก default Rich Menu"""
    try:
        url = f"{LINE_API_BASE}/user/all/richmenu"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(url, headers=get_headers())

            if response.status_code == 200:
                logger.info("Deleted default Rich Menu")
                return True
            else:
                logger.error(f"Failed to delete default: {response.status_code} - {response.text}")
                return False

    except Exception as e:
        logger.error(f"Error deleting default Rich Menu: {e}")
        return False


async def setup_rich_menu(image_path: str, delete_old: bool = True) -> Optional[str]:
    """
    Setup Rich Menu ครบวงจร:
    1. ลบ Rich Menu เก่า (ถ้าต้องการ)
    2. สร้าง Rich Menu ใหม่
    3. อัปโหลดรูปภาพ
    4. ตั้งเป็น default

    Args:
        image_path: path ไปยังไฟล์รูปภาพเมนู
        delete_old: ลบ Rich Menu เก่าหรือไม่

    Returns:
        Rich Menu ID ถ้าสำเร็จ, None ถ้าล้มเหลว
    """
    try:
        # 1. ลบ Rich Menu เก่า
        if delete_old:
            # ยกเลิก default ก่อน
            await delete_default_rich_menu()

            # ลบ Rich Menu ทั้งหมด
            menus = await get_rich_menu_list()
            for menu in menus:
                await delete_rich_menu(menu["richMenuId"])
                logger.info(f"Deleted old menu: {menu['richMenuId']}")

        # 2. สร้าง Rich Menu ใหม่
        rich_menu_id = await create_rich_menu()
        if not rich_menu_id:
            logger.error("Failed to create Rich Menu")
            return None

        # 3. อัปโหลดรูปภาพ
        if not await upload_rich_menu_image(rich_menu_id, image_path):
            logger.error("Failed to upload image, deleting menu")
            await delete_rich_menu(rich_menu_id)
            return None

        # 4. ตั้งเป็น default
        if not await set_default_rich_menu(rich_menu_id):
            logger.error("Failed to set default, but menu created")
            # ไม่ลบเพราะ menu สร้างสำเร็จแล้ว

        logger.info(f"Rich Menu setup complete: {rich_menu_id}")
        return rich_menu_id

    except Exception as e:
        logger.error(f"Error in setup_rich_menu: {e}")
        return None
