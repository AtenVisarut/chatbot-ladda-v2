#!/usr/bin/env python
"""
ตัวช่วยดูเนื้อหาและโครงสร้างของไฟล์ต่างๆ (CSV, PDF)
"""

import csv
import os
import sys
from typing import Optional
try:
    import pdfplumber
except ImportError:
    print("⚠️ pdfplumber not installed. PDF preview will be disabled.")
    print("   Install with: pip install pdfplumber")

def preview_csv(csv_path: str, num_rows: int = 5) -> None:
    """
    แสดงตัวอย่างข้อมูลจาก CSV
    
    Args:
        csv_path: path ไปยังไฟล์ CSV
        num_rows: จำนวนแถวที่ต้องการแสดง
    """
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as file:
            # ตรวจสอบ delimiter
            dialect = csv.Sniffer().sniff(file.read(4096))
            file.seek(0)
            
            reader = csv.reader(file, dialect)
            headers = next(reader)
            
            print("="*60)
            print("📊 ข้อมูล CSV")
            print("="*60)
            print(f"ไฟล์: {csv_path}")
            print(f"Columns ({len(headers)}):")
            for i, header in enumerate(headers, 1):
                print(f"{i:2d}. {header}")
            
            print("\nตัวอย่างข้อมูล:")
            for i, row in enumerate(reader):
                if i >= num_rows:
                    break
                print(f"\nแถวที่ {i+1}:")
                for header, value in zip(headers, row):
                    print(f"  {header}: {value}")
                    
    except FileNotFoundError:
        print(f"❌ ไม่พบไฟล์ {csv_path}")
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาด: {str(e)}")

def preview_pdf(pdf_path: str, max_pages: int = 2) -> None:
    """
    แสดงตัวอย่างเนื้อหาจาก PDF
    
    Args:
        pdf_path: path ไปยังไฟล์ PDF
        max_pages: จำนวนหน้าที่ต้องการแสดง
    """
    if 'pdfplumber' not in sys.modules:
        print("❌ ไม่สามารถแสดงตัวอย่าง PDF ได้ (pdfplumber not installed)")
        return
        
    try:
        with pdfplumber.open(pdf_path) as pdf:
            print("="*60)
            print("📄 ข้อมูล PDF")
            print("="*60)
            print(f"จำนวนหน้า: {len(pdf.pages)}")
            print(f"ไฟล์: {pdf_path}")
            
            # แสดงเนื้อหาตามจำนวนหน้าที่กำหนด
            for i, page in enumerate(pdf.pages[:max_pages]):
                print(f"\n{'='*60}")
                print(f"หน้า {i+1}")
                print(f"{'='*60}")
                print(page.extract_text())
                
    except FileNotFoundError:
        print(f"❌ ไม่พบไฟล์ {pdf_path}")
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาด: {str(e)}")

def preview_file(file_path: str, num_rows: Optional[int] = 5, max_pages: Optional[int] = 2) -> None:
    """
    แสดงตัวอย่างเนื้อหาจากไฟล์ตามประเภท
    
    Args:
        file_path: path ไปยังไฟล์
        num_rows: จำนวนแถวที่ต้องการแสดงสำหรับ CSV
        max_pages: จำนวนหน้าที่ต้องการแสดงสำหรับ PDF
    """
    if not os.path.exists(file_path):
        print(f"❌ ไม่พบไฟล์ {file_path}")
        return
        
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.csv':
        preview_csv(file_path, num_rows)
    elif ext == '.pdf':
        preview_pdf(file_path, max_pages)
    else:
        print(f"❌ ไม่รองรับไฟล์นามสกุล {ext}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python preview_files.py <file_path> [num_rows/max_pages]")
        sys.exit(1)
        
    file_path = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    
    if limit:
        preview_file(file_path, num_rows=limit, max_pages=limit)
    else:
        preview_file(file_path)