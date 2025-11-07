#!/usr/bin/env python
"""
ดูเนื้อหาและโครงสร้างของไฟล์ PDF
"""

import os
import pdfplumber

def preview_pdf(pdf_path):
    """แสดงตัวอย่างเนื้อหาจาก PDF"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            print("="*60)
            print("📄 ข้อมูล PDF")
            print("="*60)
            print(f"จำนวนหน้า: {len(pdf.pages)}")
            print(f"ไฟล์: {pdf_path}")
            
            # แสดงเนื้อหา 2 หน้าแรก
            print("\n" + "="*60)
            print("📝 เนื้อหา (2 หน้าแรก)")
            print("="*60)
            
            for i, page in enumerate(pdf.pages[:2], 1):
                print(f"\n--- หน้า {i} ---")
                text = page.extract_text()
                if text:
                    print(text[:500])
                    if len(text) > 500:
                        print("...")
                else:
                    print("(ไม่มีข้อความ)")
            
            # แสดงตาราง
            print("\n" + "="*60)
            print("📊 ตาราง")
            print("="*60)
            
            total_tables = 0
            for i, page in enumerate(pdf.pages, 1):
                tables = page.extract_tables()
                if tables:
                    print(f"\nหน้า {i}: พบ {len(tables)} ตาราง")
                    total_tables += len(tables)
                    
                    # แสดงตารางแรก
                    if tables and i == 1:
                        print("\nตัวอย่างตารางแรก:")
                        table = tables[0]
                        for row_idx, row in enumerate(table[:5]):  # แสดง 5 แถวแรก
                            print(f"  แถว {row_idx + 1}: {row}")
            
            print(f"\nรวมตารางทั้งหมด: {total_tables} ตาราง")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    """Main function"""
    print("="*60)
    print("🔍 ดูเนื้อหาไฟล์ PDF")
    print("="*60)
    
    print("\n📁 ระบุ path ไฟล์ PDF:")
    pdf_path = input("Path: ").strip().strip('"')
    
    if not os.path.exists(pdf_path):
        print(f"❌ ไม่พบไฟล์: {pdf_path}")
        return
    
    print(f"\n📖 กำลังอ่านไฟล์: {pdf_path}\n")
    preview_pdf(pdf_path)
    
    print("\n" + "="*60)
    print("💡 ขั้นตอนต่อไป:")
    print("1. ถ้ามีตาราง: python scripts/import_pdf_to_pinecone.py")
    print("2. เลือกวิธี 1 (แยกจากตาราง)")
    print("="*60)

if __name__ == "__main__":
    main()
