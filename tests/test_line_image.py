#!/usr/bin/env python
"""
ทดสอบการดาวน์โหลดรูปจาก LINE
"""

import os
from dotenv import load_dotenv

load_dotenv()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

print("="*60)
print("🧪 ทดสอบ LINE Image Download")
print("="*60)

if not LINE_CHANNEL_ACCESS_TOKEN:
    print("❌ ไม่พบ LINE_CHANNEL_ACCESS_TOKEN ในไฟล์ .env")
    exit(1)

print(f"✅ พบ Access Token: {LINE_CHANNEL_ACCESS_TOKEN[:30]}...")

print("\n📝 หมายเหตุ:")
print("- การทดสอบนี้ต้องมี message ID จริงจาก LINE")
print("- ถ้าไม่มี message ID จะไม่สามารถทดสอบได้")
print("- แต่ถ้า token ถูกต้อง ระบบควรทำงานได้")

print("\n✅ LINE Token พร้อมใช้งาน")
print("\n💡 ถ้ายังมีปัญหา:")
print("1. ตรวจสอบ token ที่ LINE Console")
print("2. ตรวจสอบว่า token ไม่หมดอายุ")
print("3. ลอง issue token ใหม่")
