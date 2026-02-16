"""
Script: Import fertilizer recommendations CSV into Supabase
Reads CSV, generates embeddings, inserts into mahbin_npk table

Prerequisites:
    1. Run setup_mahbin_npk.sql in Supabase SQL Editor first
    2. Place CSV at: C:\\clone_chatbot_ick\\ICP_Fer_utf8.csv

Usage:
    python scripts/import_mahbin_npk.py
"""
import sys
import os
import io
import csv
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

os.chdir("C:\\clone_chatbot_ick\\Chatbot-ladda")
sys.path.insert(0, "C:\\clone_chatbot_ick\\Chatbot-ladda")

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
from app.config import OPENAI_API_KEY, EMBEDDING_MODEL
from app.dependencies import supabase_client

openai_client = OpenAI(api_key=OPENAI_API_KEY)

CSV_PATH = "C:\\clone_chatbot_ick\\ICP_Fer_utf8.csv"


def generate_embedding(text: str) -> list:
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding


def build_embedding_text(row: dict) -> str:
    """Build embedding text for fertilizer recommendation"""
    parts = [
        f"สูตรปุ๋ยแนะนำ {row['fertilizer_formula']}",
        f"สำหรับ{row['crop']}",
        f"ระยะ{row['growth_stage']}",
    ]
    if row.get('primary_nutrients'):
        parts.append(f"ธาตุ: {row['primary_nutrients']}")
    if row.get('benefits'):
        parts.append(f"ประโยชน์: {row['benefits']}")
    if row.get('usage_rate'):
        parts.append(f"อัตรา: {row['usage_rate']}")
    return " | ".join(parts)


def main():
    print("=" * 70)
    print("IMPORT FERTILIZER RECOMMENDATIONS")
    print(f"CSV: {CSV_PATH}")
    print(f"Embedding Model: {EMBEDDING_MODEL}")
    print("=" * 70)

    # Read CSV
    if not os.path.exists(CSV_PATH):
        print(f"ERROR: CSV file not found at {CSV_PATH}")
        return

    rows = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    print(f"\nTotal rows in CSV: {len(rows)}")

    # Show preview
    print(f"\n{'ID':<5} {'Crop':<15} {'Stage':<30} {'Formula':<30}")
    print("-" * 80)
    for row in rows:
        pid = row.get('Product ID', '?')
        crop = row.get('พืช', '?')
        stage = row.get('ระยะพืช', '?')[:28]
        formula = row.get('สูตรปุ๋ย', '?')[:28]
        print(f"{pid:<5} {crop:<15} {stage:<30} {formula:<30}")

    # Clear existing data
    print(f"\nClearing existing mahbin_npk data...")
    try:
        supabase_client.table('mahbin_npk').delete().neq('id', 0).execute()
        print("  Cleared.")
    except Exception as e:
        print(f"  Warning (may be empty): {e}")

    # Import rows
    print(f"\nImporting {len(rows)} rows...")
    success_count = 0
    errors = []
    t0 = time.time()

    for i, row in enumerate(rows, 1):
        try:
            # Map CSV columns to DB columns
            data = {
                'crop': row.get('พืช', '').strip(),
                'growth_stage': row.get('ระยะพืช', '').strip(),
                'fertilizer_formula': row.get('สูตรปุ๋ย', '').strip(),
                'usage_rate': row.get('อัตราการใช้', '').strip(),
                'primary_nutrients': row.get('ธาตุหลัก/ธาตุรอง', '').strip(),
                'benefits': row.get('ประโยชน์', '').strip(),
            }

            # Clean trailing dots from formula (e.g. "46-0-0." → "46-0-0")
            data['fertilizer_formula'] = data['fertilizer_formula'].rstrip('.')

            # Generate embedding
            emb_text = build_embedding_text(data)
            print(f"[{i}/{len(rows)}] {data['crop']} | {data['growth_stage'][:25]}")
            print(f"  Formula: {data['fertilizer_formula']}")
            print(f"  Embedding text: {emb_text[:80]}...")

            embedding = generate_embedding(emb_text)
            data['embedding'] = embedding

            # Insert
            supabase_client.table('mahbin_npk').insert(data).execute()
            print(f"  Inserted!")
            success_count += 1

        except Exception as e:
            error_msg = f"Row {i} ({row.get('พืช', '?')}): {str(e)}"
            errors.append(error_msg)
            print(f"  ERROR: {e}")

    elapsed = time.time() - t0

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"Total rows: {len(rows)}")
    print(f"Success: {success_count}")
    print(f"Errors: {len(errors)}")
    print(f"Time: {elapsed:.1f}s")

    if errors:
        print(f"\nErrors:")
        for e in errors:
            print(f"  - {e}")

    # Verify
    print(f"\nVerifying...")
    result = supabase_client.table('mahbin_npk').select('id, crop, growth_stage, fertilizer_formula').execute()
    print(f"Rows in DB: {len(result.data)}")
    for r in result.data:
        print(f"  [{r['id']}] {r['crop']} | {r['growth_stage'][:25]} | {r['fertilizer_formula'][:25]}")

    print(f"\n{'=' * 70}")
    print("DONE")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
