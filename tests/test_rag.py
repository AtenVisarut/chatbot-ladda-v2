#!/usr/bin/env python
"""
ทดสอบระบบ RAG (Retrieval-Augmented Generation)
ตรวจสอบว่า Pinecone ค้นหาผลิตภัณฑ์ได้ถูกต้อง
"""

import os
from dotenv import load_dotenv
from pinecone import Pinecone
from openai import OpenAI

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "plant-products")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def test_rag():
    """ทดสอบ RAG system"""
    
    print("="*60)
    print("🧪 ทดสอบระบบ RAG")
    print("="*60)
    
    # เชื่อมต่อ Pinecone
    print("\n1️⃣ เชื่อมต่อ Pinecone...")
    try:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        index = pc.Index(PINECONE_INDEX_NAME)
        
        stats = index.describe_index_stats()
        print(f"   ✅ เชื่อมต่อสำเร็จ")
        print(f"   📊 จำนวนข้อมูล: {stats.total_vector_count} รายการ")
        print(f"   📐 Dimension: {stats.dimension}")
        
        if stats.total_vector_count == 0:
            print("\n   ⚠️  ไม่มีข้อมูลใน Pinecone!")
            print("   รัน: python scripts/import_csv_to_pinecone.py")
            return
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return
    
    # เชื่อมต่อ OpenAI
    print("\n2️⃣ เชื่อมต่อ OpenAI...")
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        print("   ✅ เชื่อมต่อสำเร็จ")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return
    
    # ทดสอบ queries
    test_queries = [
        "โรคใบจุด อาการใบมีจุดสีน้ำตาล",
        "โรคราน้ำค้าง ใบเหลือง",
        "เพลี้ยอ่อน แมลงศัตรูพืช",
        "ปุ๋ยอินทรีย์ เสริมสร้างภูมิคุ้มกัน",
        "ยาฆ่าแมลง ปลอดภัย",
    ]
    
    print("\n3️⃣ ทดสอบการค้นหา...")
    print("="*60)
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n🔍 Query {i}: {query}")
        print("-"*60)
        
        try:
            # สร้าง embedding
            embedding_response = client.embeddings.create(
                model="text-embedding-3-small",
                input=query
            )
            query_vector = embedding_response.data[0].embedding
            
            # ค้นหาใน Pinecone
            results = index.query(
                vector=query_vector,
                top_k=3,
                include_metadata=True
            )
            
            if not results.matches:
                print("   ❌ ไม่พบผลลัพธ์")
                continue
            
            # แสดงผลลัพธ์
            for j, match in enumerate(results.matches, 1):
                metadata = match.metadata
                
                product_name = (
                    metadata.get("ชื่อผลิตภัณฑ์") or 
                    metadata.get("product_name") or 
                    "ไม่ระบุชื่อ"
                )
                
                description = (
                    metadata.get("คำอธิบาย") or 
                    metadata.get("description") or 
                    ""
                )
                
                print(f"\n   {j}. {product_name}")
                print(f"      Score: {match.score:.3f}")
                if description:
                    print(f"      {description[:100]}...")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print("\n" + "="*60)
    print("✅ ทดสอบเสร็จสิ้น!")
    print("="*60)
    
    print("\n💡 ถ้าผลลัพธ์ไม่ตรง:")
    print("1. ตรวจสอบข้อมูลใน CSV")
    print("2. รัน import_csv_to_pinecone.py ใหม่")
    print("3. ตรวจสอบว่า columns ในไฟล์ถูกต้อง")

if __name__ == "__main__":
    test_rag()
