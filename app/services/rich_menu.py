"""
Rich Menu Service
สร้างและจัดการ Rich Menu ผ่าน LINE Messaging API
"""

import logging
import httpx
from typing import Optional, Dict, Any

from app.config import LINE_CHANNEL_ACCESS_TOKEN, LIFF_URL, LIFF_DISEASES_URL

logger = logging.getLogger(__name__)

# LINE API Base URL
LINE_API_BASE = "https://api.line.me/v2/bot"

# Rich Menu Configuration (5 ปุ่ม - 3 บน + 2 ล่าง)
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
            "bounds": {"x": 0, "y": 0, "width": 833, "height": 843},
            "action": {
                "type": "uri",
                "label": "ลงทะเบียน",
                "uri": LIFF_URL
            }
        },
        {
            # B: กล้อง (บนกลาง) - เปิดกล้อง
            "bounds": {"x": 833, "y": 0, "width": 834, "height": 843},
            "action": {
                "type": "camera",
                "label": "กล้อง"
            }
        },
        {
            # C: Gallery (บนขวา) - เปิดแกลเลอรี่
            "bounds": {"x": 1667, "y": 0, "width": 833, "height": 843},
            "action": {
                "type": "cameraRoll",
                "label": "Gallery"
            }
        },
        {
            # D: ดูสภาพอากาศ (ล่างซ้าย) - เปิด Location picker
            "bounds": {"x": 0, "y": 843, "width": 1250, "height": 843},
            "action": {
                "type": "location",
                "label": "ดูสภาพอากาศ"
            }
        },
        {
            # E: คู่มือโรคพืช (ล่างขวา) - เปิด LIFF หน้าคู่มือโรคพืช
            "bounds": {"x": 1250, "y": 843, "width": 1250, "height": 843},
            "action": {
                "type": "uri",
                "label": "คู่มือโรคพืช",
                "uri": LIFF_DISEASES_URL
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
    - รองรับ PNG และ JPEG
    - บีบอัดอัตโนมัติถ้าเกิน 1MB

    Args:
        rich_menu_id: ID ของ Rich Menu
        image_path: path ไปยังไฟล์รูปภาพ (PNG หรือ JPEG)
    """
    try:
        from PIL import Image
        import io

        url = f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content"

        # Read and compress image if needed (LINE limit is 1MB)
        max_size = 1024 * 1024  # 1MB

        with open(image_path, "rb") as f:
            image_data = f.read()

        original_size = len(image_data)
        logger.info(f"Original image size: {original_size} bytes")

        # If image is too large, compress it
        if original_size > max_size:
            logger.info("Image too large, compressing...")
            img = Image.open(image_path)

            # Convert to RGB if necessary (for PNG with transparency)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')

            # Compress as JPEG with decreasing quality until under 1MB
            quality = 85
            while quality > 20:
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=quality, optimize=True)
                image_data = buffer.getvalue()

                if len(image_data) <= max_size:
                    logger.info(f"Compressed to {len(image_data)} bytes (quality={quality})")
                    break
                quality -= 10

            content_type = "image/jpeg"
        else:
            # Use original format
            content_type = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"

        headers = {
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": content_type
        }

        logger.info(f"Uploading image: {len(image_data)} bytes, type: {content_type}")

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


async def setup_rich_menu_debug(test_upload: bool = False) -> dict:
    """Debug function to test Rich Menu creation step by step"""
    from PIL import Image
    import io

    result = {"steps": [], "config": None, "token_preview": None}

    # Show config
    result["config"] = RICH_MENU_CONFIG
    result["token_preview"] = f"{LINE_CHANNEL_ACCESS_TOKEN[:20]}..." if LINE_CHANNEL_ACCESS_TOKEN else "None"

    rich_menu_id = None

    # Step 1: Try to create rich menu
    try:
        url = f"{LINE_API_BASE}/richmenu"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=get_headers(), json=RICH_MENU_CONFIG)
            result["steps"].append({
                "step": "create_rich_menu",
                "status_code": response.status_code,
                "response": response.text[:500] if response.text else "empty"
            })
            if response.status_code == 200:
                rich_menu_id = response.json().get("richMenuId")
    except Exception as e:
        result["steps"].append({"step": "create_rich_menu", "error": str(e)})

    # Step 2: Try to upload image (if test_upload=True and rich_menu_id exists)
    if test_upload and rich_menu_id:
        image_path = "rich_menu_5.png"
        try:
            import os
            if os.path.exists(image_path):
                # Compress image
                with open(image_path, "rb") as f:
                    original_data = f.read()

                result["steps"].append({
                    "step": "read_image",
                    "original_size": len(original_data)
                })

                # Compress
                img = Image.open(image_path)
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')

                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=75, optimize=True)
                image_data = buffer.getvalue()

                result["steps"].append({
                    "step": "compress_image",
                    "compressed_size": len(image_data),
                    "format": "JPEG",
                    "quality": 75
                })

                # Upload
                upload_url = f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content"
                headers = {
                    "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                    "Content-Type": "image/jpeg"
                }

                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(upload_url, headers=headers, content=image_data)
                    result["steps"].append({
                        "step": "upload_image",
                        "status_code": response.status_code,
                        "response": response.text[:500] if response.text else "empty"
                    })

                    # Step 3: Set as default if upload succeeded
                    if response.status_code == 200:
                        default_url = f"{LINE_API_BASE}/user/all/richmenu/{rich_menu_id}"
                        response = await client.post(default_url, headers=get_headers())
                        result["steps"].append({
                            "step": "set_default",
                            "status_code": response.status_code,
                            "response": response.text[:200] if response.text else "empty"
                        })
                        result["rich_menu_id"] = rich_menu_id
            else:
                result["steps"].append({"step": "read_image", "error": "File not found"})
        except Exception as e:
            result["steps"].append({"step": "upload_image", "error": str(e)})

    return result


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
