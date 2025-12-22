"""
Script สำหรับ Setup Rich Menu

วิธีใช้:
1. เตรียมรูปภาพเมนู ขนาด 2500x1686 px (PNG หรือ JPG)
2. รัน: python setup_rich_menu.py <path_to_image>

ตัวอย่าง:
    python setup_rich_menu.py rich_menu.png
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.rich_menu import setup_rich_menu, get_rich_menu_list, get_default_rich_menu


async def main():
    print("=" * 50)
    print("  Ladda Bot - Rich Menu Setup")
    print("=" * 50)

    # Check arguments
    if len(sys.argv) < 2:
        print("\n[ERROR] กรุณาระบุ path รูปภาพเมนู")
        print("\nวิธีใช้:")
        print("  python setup_rich_menu.py <path_to_image>")
        print("\nตัวอย่าง:")
        print("  python setup_rich_menu.py rich_menu.png")
        print("\nข้อกำหนดรูปภาพ:")
        print("  - ขนาด: 2500 x 1686 pixels")
        print("  - รูปแบบ: PNG หรือ JPEG")
        print("  - ขนาดไฟล์: ไม่เกิน 1 MB")
        return

    image_path = sys.argv[1]

    # Check if image exists
    if not os.path.exists(image_path):
        print(f"\n[ERROR] ไม่พบไฟล์: {image_path}")
        return

    # Check file size (max 1MB)
    file_size = os.path.getsize(image_path)
    if file_size > 1024 * 1024:
        print(f"\n[ERROR] ไฟล์ใหญ่เกินไป: {file_size / 1024 / 1024:.2f} MB (max 1 MB)")
        return

    print(f"\nรูปภาพ: {image_path}")
    print(f"ขนาดไฟล์: {file_size / 1024:.1f} KB")

    # Show current Rich Menu status
    print("\n--- Rich Menu ปัจจุบัน ---")
    current_menus = await get_rich_menu_list()
    if current_menus:
        for menu in current_menus:
            print(f"  - {menu['name']} ({menu['richMenuId'][:20]}...)")
    else:
        print("  (ไม่มี Rich Menu)")

    default_menu = await get_default_rich_menu()
    if default_menu:
        print(f"  Default: {default_menu[:20]}...")
    else:
        print("  Default: (ไม่ได้ตั้งค่า)")

    # Confirm
    print("\n" + "-" * 50)
    confirm = input("ต้องการสร้าง Rich Menu ใหม่? (y/n): ").strip().lower()
    if confirm != 'y':
        print("ยกเลิก")
        return

    # Setup Rich Menu
    print("\n--- กำลังสร้าง Rich Menu ---")
    print("1. ลบ Rich Menu เก่า...")
    print("2. สร้าง Rich Menu ใหม่...")
    print("3. อัปโหลดรูปภาพ...")
    print("4. ตั้งเป็น Default...")

    rich_menu_id = await setup_rich_menu(image_path, delete_old=True)

    if rich_menu_id:
        print("\n" + "=" * 50)
        print("  สำเร็จ!")
        print("=" * 50)
        print(f"\nRich Menu ID: {rich_menu_id}")
        print("\nการตั้งค่า:")
        print("  - ลงทะเบียน: เปิด LIFF")
        print("  - วิเคราะห์โรค: เปิดแกลเลอรี่")
        print("  - ดูสภาพอากาศ: เปิด Location picker")
        print("  - ช่วยเหลือ: ส่งข้อความ 'ช่วยเหลือ'")
        print("\nทดสอบ: เปิด LINE แชทกับ Bot แล้วดู Rich Menu")
    else:
        print("\n[ERROR] ไม่สามารถสร้าง Rich Menu ได้")
        print("กรุณาตรวจสอบ:")
        print("  - LINE_CHANNEL_ACCESS_TOKEN ถูกต้อง")
        print("  - รูปภาพมีขนาด 2500x1686 px")


if __name__ == "__main__":
    asyncio.run(main())
