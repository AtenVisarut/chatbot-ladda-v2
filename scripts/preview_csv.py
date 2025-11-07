#!/usr/bin/env python
"""
ดูโครงสร้างและข้อมูลในไฟล์ CSV
ใช้ก่อนนำเข้าข้อมูลเพื่อตรวจสอบ columns
"""

import csv
import os

def preview_csv(csv_path, num_rows=5):
    """
    แสดงตัวอย่างข้อมูลจาก CSV
    
    Args:
        csv_path: path ไปยังไฟล์ CSV
        num_rows: จำนวนแถวที่ต้องการแสดง
    """
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as file:
            # ตรวจสอบ delimiter
            sample = file.read(1024)
            file.seek(0)
            delimiter = ',' if sample.count(',') > sample.count(';') else ';'
            
            reader = csv.DictReader(file, delimiter=delimiter)
            
            # อ่านข้อมูล
            rows = []
            for i, row in enumerate(reader):
                if i >= num_rows:
                    break
                rows.append(row)
            
            if not rows:
                print("❌ ไม่มีข้อมูลในไฟล์")
                return
            
            # แสดง columns
            print("="*60)
            print("📋 Columns ในไฟล์ CSV")
            print("="*60)
            columns = list(rows[0].keys())
            for i, col in enumerate(columns, 1):
                print(f"{i}. {col}")
            
            # แสดงตัวอย่างข้อมูล
            print("\n" + "="*60)
            print(f"📊 ตัวอย่างข้อมูล ({len(rows)} แถวแรก)")
            print("="*60)
            
            for i, row in enumerate(rows, 1):
                print(f"\n--- แถวที่ {i} ---")
                for key, value in row.items():
                    if value:  # แสดงเฉพาะที่มีค่า
                        display_value = str(value)[:100]
                        if len(str(value)) > 100:
                            display_value += "..."
                        print(f"{key}: {display_value}")
            
            # นับจำนวนแถวทั้งหมด
            file.seek(0)
            total_rows = sum(1 for _ in reader)
            print(f"\n📊 จำนวนแถวทั้งหมด: {total_rows}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    """Main function"""
    print("="*60)
    print("🔍 ดูโครงสร้างไฟล์ CSV")
    print("="*60)
    
    print("\n📁 ระบุ path ไฟล์ CSV:")
    csv_path = input("Path: ").strip().strip('"')
    
    if not os.path.exists(csv_path):
        print(f"❌ ไม่พบไฟล์: {csv_path}")
        return
    
    print(f"\n📖 กำลังอ่านไฟล์: {csv_path}\n")
    preview_csv(csv_path)
    
    print("\n" + "="*60)
    print("💡 ขั้นตอนต่อไป:")
    print("1. ตรวจสอบว่า columns ถูกต้อง")
    print("2. รัน: python scripts/import_csv_to_pinecone.py")
    print("3. ระบุ path ไฟล์ CSV เดียวกัน")
    print("="*60)

if __name__ == "__main__":
    main()
