"""
Import Fertilizer Data (ข้อมูลปุ๋ย) to Supabase Knowledge Base
แปลงข้อมูลปุ๋ย/สารเคมีจาก CSV เข้าสู่ Knowledge table พร้อม embedding

Usage:
    python scripts/import_fertilizer_knowledge.py
"""

import os
import sys
import csv
import asyncio
import uuid
import argparse
from pathlib import Path
from typing import List, Dict
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import AsyncOpenAI

# Fix Windows console encoding for Thai
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Validate environment variables
if not all([SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY]):
    print("Error: Missing environment variables")
    print("   Required: SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY")
    sys.exit(1)

# Initialize clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# File paths
CSV_FILE = Path(__file__).parent.parent / "ข้อมูลปุ๋ยicp.csv"
TABLE_NAME = "knowledge"


async def get_embedding(text: str) -> List[float]:
    """Generate embedding using OpenAI text-embedding-3-small (1536 dimensions)"""
    try:
        response = await openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
            encoding_format="float"
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"   Warning: Error generating embedding: {e}")
        return []


def read_fertilizer_csv(file_path: Path) -> List[Dict]:
    """Read fertilizer CSV file"""
    records = []
    try:
        with open(file_path, mode='r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Clean keys
                clean_row = {k.strip(): v.strip() if v else '' for k, v in row.items() if k}
                records.append(clean_row)
        print(f"Read {len(records)} records from CSV")
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    return records


def transform_to_knowledge(record: Dict) -> Dict:
    """Transform fertilizer record to knowledge format"""
    plant = record.get('พืช', '').strip()
    product_type = record.get('ประเภท', '').strip()
    product_name = record.get('ชื่อสินค้า', '').strip()
    common_name = record.get('ชื่อสามัญ', '').strip()
    properties = record.get('คุณสมบัติ', '').strip()
    benefits = record.get('ประโยชน์', '').strip()
    usage_rate = record.get('อัตราใช้', '').strip()

    if not product_name:
        return None

    # Create readable title
    title = f"{product_name} - {product_type} สำหรับ{plant}"

    # Build comprehensive content
    content_parts = []

    # Product info header
    content_parts.append(f"ชื่อสินค้า: {product_name}")
    content_parts.append(f"ประเภท: {product_type}")
    content_parts.append(f"พืชที่ใช้ได้: {plant}")

    if common_name:
        content_parts.append(f"ชื่อสามัญ/สารสำคัญ: {common_name}")

    if properties:
        content_parts.append(f"คุณสมบัติ: {properties}")

    if benefits:
        content_parts.append(f"ประโยชน์/การใช้งาน: {benefits}")

    if usage_rate:
        content_parts.append(f"อัตราการใช้: {usage_rate}")

    content = "\n".join(content_parts)

    # Map product type to category
    category_map = {
        'กำจัดแมลง': 'สารกำจัดแมลง',
        'ป้องกันโรค': 'สารป้องกันโรค',
        'ปุ๋ยและสารบำรุง': 'ปุ๋ยและธาตุอาหาร',
        'กำจัดวัชพืช': 'สารกำจัดวัชพืช'
    }
    category = category_map.get(product_type, product_type)

    return {
        'title': title,
        'content': content,
        'category': category,
        'plant_type': plant,
        'product_name': product_name,
        'product_type': product_type
    }


async def check_duplicate(title: str) -> bool:
    """Check if title already exists in database"""
    try:
        result = supabase.table(TABLE_NAME).select("id").eq("title", title).execute()
        return len(result.data) > 0
    except Exception as e:
        print(f"   Warning: Error checking duplicate: {e}")
        return False


async def process_record(knowledge: Dict) -> bool:
    """Process a single knowledge record and upload to Supabase"""
    title = knowledge['title']
    content = knowledge['content']

    # Check for duplicates
    if await check_duplicate(title):
        print(f"   Skip (dup): {title[:50]}...")
        return False

    try:
        # Create text for embedding
        text_to_embed = f"{title}\n\n{content}"

        # Generate embedding
        embedding = await get_embedding(text_to_embed)

        if not embedding:
            print(f"   No embedding: {title[:50]}...")
            return False

        # Prepare data for Supabase
        now = datetime.utcnow().isoformat()
        data = {
            "id": str(uuid.uuid4()),
            "title": title,
            "content": content,
            "category": knowledge['category'],
            "plant_type": knowledge['plant_type'],
            "source": "ข้อมูลปุ๋ยicp.csv",
            "metadata": {
                "product_name": knowledge['product_name'],
                "product_type": knowledge['product_type'],
                "imported_from": "fertilizer_csv",
                "data_type": "fertilizer_product"
            },
            "embedding": embedding,
            "created_at": now,
            "updated_at": now
        }

        # Insert into Supabase
        supabase.table(TABLE_NAME).insert(data).execute()
        print(f"   OK: {title[:60]}...")
        return True

    except Exception as e:
        print(f"   Error: {title[:40]}... - {e}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="Import fertilizer CSV to Supabase")
    parser.add_argument("--yes", "-y", action="store_true", help="Auto confirm import")
    args = parser.parse_args()

    print("=" * 60)
    print("Import Fertilizer Data to Knowledge Base")
    print("=" * 60)
    print(f"   CSV File: {CSV_FILE}")
    print(f"   Supabase URL: {SUPABASE_URL[:40]}...")
    print(f"   Table: {TABLE_NAME}")
    print(f"   Embedding: text-embedding-3-small (1536 dims)")
    print("=" * 60)

    if not CSV_FILE.exists():
        print(f"Error: File not found: {CSV_FILE}")
        return

    # Read CSV
    records = read_fertilizer_csv(CSV_FILE)
    if not records:
        print("No records found")
        return

    # Transform to knowledge format
    knowledge_records = []
    for r in records:
        k = transform_to_knowledge(r)
        if k:
            knowledge_records.append(k)

    print(f"Transformed {len(knowledge_records)} records")

    # Show sample
    if knowledge_records:
        print("\nSample record:")
        print("-" * 40)
        sample = knowledge_records[0]
        print(f"Title: {sample['title']}")
        print(f"Category: {sample['category']}")
        print(f"Plant: {sample['plant_type']}")
        print(f"Content preview: {sample['content'][:200]}...")
        print("-" * 40)

    # Confirm import
    print(f"\nReady to import {len(knowledge_records)} records")
    if not args.yes:
        confirm = input("Continue? (y/n): ").strip().lower()
        if confirm != 'y':
            print("Cancelled")
            return

    print("\nImporting...")

    # Process records in batches
    success_count = 0
    batch_size = 5

    for i in range(0, len(knowledge_records), batch_size):
        batch = knowledge_records[i:i+batch_size]
        results = await asyncio.gather(
            *[process_record(k) for k in batch]
        )
        success_count += sum(results)

        # Progress
        progress = min(i + batch_size, len(knowledge_records))
        print(f"   Progress: {progress}/{len(knowledge_records)}")

        # Rate limit delay
        if i + batch_size < len(knowledge_records):
            await asyncio.sleep(0.5)

    print("\n" + "=" * 60)
    print(f"Import completed!")
    print(f"   Imported: {success_count}/{len(knowledge_records)} records")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
