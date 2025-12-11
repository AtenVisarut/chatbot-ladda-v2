"""
Import Knowledge CSV to Supabase with OpenAI Embeddings
สำหรับ import ข้อมูลความรู้จาก CSV ไปยัง Supabase พร้อมสร้าง embedding

Usage:
    python scripts/import_knowledge_to_supabase.py [--file FILE] [--all]

Options:
    --file FILE  Import specific CSV file
    --all        Import all CSV files in data/knowledge_templates/
"""

import os
import sys
import csv
import asyncio
import argparse
import uuid
from pathlib import Path

# Fix Windows console encoding for Thai and emoji
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from typing import List, Dict, Optional
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import AsyncOpenAI

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Validate environment variables
if not all([SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY]):
    print("❌ Error: Missing environment variables")
    print("   Required: SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY")
    sys.exit(1)

# Initialize clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Knowledge templates directory
KNOWLEDGE_DIR = Path(__file__).parent.parent / "data" / "knowledge_templates"
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
        print(f"   ⚠️ Error generating embedding: {e}")
        return []


def read_csv(file_path: Path) -> List[Dict]:
    """Read CSV file and return list of dicts"""
    records = []
    try:
        with open(file_path, mode='r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Clean keys (remove BOM or whitespace)
                clean_row = {k.strip(): v.strip() if v else '' for k, v in row.items() if k}
                records.append(clean_row)
    except Exception as e:
        print(f"❌ Error reading {file_path}: {e}")
    return records


async def check_duplicate(title: str) -> bool:
    """Check if title already exists in database"""
    try:
        result = supabase.table(TABLE_NAME).select("id").eq("title", title).execute()
        return len(result.data) > 0
    except Exception as e:
        print(f"   ⚠️ Error checking duplicate: {e}")
        return False


async def process_record(record: Dict, source_file: str) -> bool:
    """Process a single knowledge record and upload to Supabase"""
    title = record.get('title', '').strip()
    content = record.get('content', '').strip()

    if not title or not content:
        print(f"   ⏭️ Skipping empty record")
        return False

    # Check for duplicates
    if await check_duplicate(title):
        print(f"   ⏭️ Skipping duplicate: {title[:50]}...")
        return False

    try:
        # Create text for embedding (combine title + content for better search)
        text_to_embed = f"{title}\n\n{content}"

        # Generate embedding
        embedding = await get_embedding(text_to_embed)

        if not embedding:
            print(f"   ❌ No embedding for: {title[:50]}...")
            return False

        # Prepare data for Supabase
        now = datetime.utcnow().isoformat()
        data = {
            "id": str(uuid.uuid4()),
            "title": title,
            "content": content,
            "category": record.get('category', '').strip() or None,
            "plant_type": record.get('plant_type', '').strip() or None,
            "source": record.get('source', '').strip() or source_file,
            "metadata": {
                "imported_from": source_file,
                "original_source": record.get('source', '')
            },
            "embedding": embedding,
            "created_at": now,
            "updated_at": now
        }

        # Insert into Supabase
        supabase.table(TABLE_NAME).insert(data).execute()
        print(f"   ✅ {title[:60]}...")
        return True

    except Exception as e:
        print(f"   ❌ Error: {title[:40]}... - {e}")
        return False


async def import_csv_file(file_path: Path) -> tuple[int, int]:
    """Import a single CSV file, returns (success_count, total_count)"""
    print(f"\n📂 Processing: {file_path.name}")
    print("-" * 50)

    records = read_csv(file_path)
    if not records:
        print("   No records found")
        return 0, 0

    print(f"   Found {len(records)} records")

    success_count = 0
    batch_size = 5  # Process in batches to avoid rate limits

    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        results = await asyncio.gather(
            *[process_record(r, file_path.name) for r in batch]
        )
        success_count += sum(results)

        # Small delay between batches
        if i + batch_size < len(records):
            await asyncio.sleep(0.5)

    return success_count, len(records)


async def import_all_csv_files():
    """Import all CSV files from knowledge_templates directory"""
    if not KNOWLEDGE_DIR.exists():
        print(f"❌ Directory not found: {KNOWLEDGE_DIR}")
        return

    csv_files = list(KNOWLEDGE_DIR.glob("*.csv"))
    if not csv_files:
        print(f"❌ No CSV files found in {KNOWLEDGE_DIR}")
        return

    print(f"🚀 Found {len(csv_files)} CSV files to import")
    print("=" * 60)

    total_success = 0
    total_records = 0

    for csv_file in csv_files:
        success, total = await import_csv_file(csv_file)
        total_success += success
        total_records += total

    print("\n" + "=" * 60)
    print(f"🎉 Import completed!")
    print(f"   Total imported: {total_success}/{total_records} records")
    print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(description="Import knowledge CSV to Supabase")
    parser.add_argument("--file", type=str, help="Import specific CSV file")
    parser.add_argument("--all", action="store_true", help="Import all CSV files")
    args = parser.parse_args()

    print("=" * 60)
    print("📚 Knowledge Import to Supabase")
    print("=" * 60)
    print(f"   Supabase URL: {SUPABASE_URL[:40]}...")
    print(f"   Table: {TABLE_NAME}")
    print(f"   Embedding model: text-embedding-3-small (1536 dims)")

    if args.file:
        # Import specific file
        file_path = Path(args.file)
        if not file_path.exists():
            # Try in knowledge_templates directory
            file_path = KNOWLEDGE_DIR / args.file

        if not file_path.exists():
            print(f"❌ File not found: {args.file}")
            return

        await import_csv_file(file_path)
        print("\n🎉 Import completed!")

    elif args.all:
        # Import all files
        await import_all_csv_files()

    else:
        # No arguments - show available files and ask
        print(f"\n📁 Available CSV files in {KNOWLEDGE_DIR}:")
        csv_files = list(KNOWLEDGE_DIR.glob("*.csv"))
        for i, f in enumerate(csv_files, 1):
            records = read_csv(f)
            print(f"   {i}. {f.name} ({len(records)} records)")

        print("\nUsage:")
        print("   python scripts/import_knowledge_to_supabase.py --all")
        print("   python scripts/import_knowledge_to_supabase.py --file diseases_template.csv")


if __name__ == "__main__":
    asyncio.run(main())
