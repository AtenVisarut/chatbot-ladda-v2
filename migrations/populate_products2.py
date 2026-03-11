"""
Populate products2 table from CSV + generate fresh embeddings.

Usage:
    python migrations/populate_products2.py

Reads: ICP_product - products_rows (2).csv
Target: Supabase products2 table
Embedding: OpenAI text-embedding-3-small (1536 dims)
"""
import os
import sys
import csv
import time
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "ICP_product - products_rows (2).csv")

# CSV header → DB column mapping
COLUMN_MAP = {
    "product_name": "product_name",
    "common_name_th": "common_name_th",
    "active_ingredient": "active_ingredient",
    "Herbicides": "herbicides",
    "Insecticides": "insecticides",
    "Plant Biostimulant": "biostimulant",
    "applicable_crops": "applicable_crops",
    "how_to_use": "how_to_use",
    "usage_period": "usage_period",
    "usage_rate": "usage_rate",
    "product_category": "product_category",
    "package_size": "package_size",
    "physical_form": "physical_form",
    "selling_point": "selling_point",
    "absorption_method": "absorption_method",
    "mechanism_of_action": "mechanism_of_action",
    "action_characteristics": "action_characteristics",
    "phytotoxicity": "phytotoxicity",
    "strategy": "strategy",
}

# These CSV headers have leading/trailing spaces or special chars — match by substring
FUZZY_COLUMNS = {
    "กลุ่มสารเคมี": "chemical_group_rac",
    "Fungicides": "fungicides",
    "PGR": "pgr_hormones",
}


def _resolve_column(csv_header: str) -> str | None:
    """Map a CSV header to a DB column name."""
    h = csv_header.strip()
    # Exact match
    if h in COLUMN_MAP:
        return COLUMN_MAP[h]
    # Fuzzy match (for headers with extra whitespace/Thai)
    for key, col in FUZZY_COLUMNS.items():
        if key in h:
            return col
    return None


def generate_embedding(text: str, client: OpenAI) -> list | None:
    """Generate embedding using text-embedding-3-small."""
    try:
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
            encoding_format="float",
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"  ✗ Embedding error: {e}")
        return None


def build_embedding_text(row: dict) -> str:
    """Build rich text for embedding from product fields."""
    parts = [
        f"ชื่อสินค้า: {row.get('product_name', '')}",
        f"ชื่อสามัญ: {row.get('common_name_th', '')}",
        f"สารสำคัญ: {row.get('active_ingredient', '')}",
        f"ประเภท: {row.get('product_category', '')}",
        f"กำจัดแมลง: {row.get('insecticides', '')}" if row.get('insecticides') else "",
        f"กำจัดโรค: {row.get('fungicides', '')}" if row.get('fungicides') else "",
        f"กำจัดวัชพืช: {row.get('herbicides', '')}" if row.get('herbicides') else "",
        f"สารชีวภัณฑ์: {row.get('biostimulant', '')}" if row.get('biostimulant') else "",
        f"ฮอร์โมน: {row.get('pgr_hormones', '')}" if row.get('pgr_hormones') else "",
        f"พืชที่ใช้ได้: {row.get('applicable_crops', '')}",
        f"วิธีใช้: {row.get('how_to_use', '')}",
        f"ช่วงเวลาใช้: {row.get('usage_period', '')}",
        f"อัตราใช้: {row.get('usage_rate', '')}",
        f"จุดเด่น: {row.get('selling_point', '')}",
        f"การดูดซึม: {row.get('absorption_method', '')}",
        f"กลไกการออกฤทธิ์: {row.get('mechanism_of_action', '')}",
        f"ลักษณะการออกฤทธิ์: {row.get('action_characteristics', '')}",
        f"ความเป็นพิษต่อพืช: {row.get('phytotoxicity', '')}",
        f"กลยุทธ์: {row.get('strategy', '')}",
    ]
    return " | ".join(p for p in parts if p)


def read_csv() -> list[dict]:
    """Read CSV and map to DB columns."""
    rows = []
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        # Build header → column mapping
        header_map = {}
        for h in headers:
            col = _resolve_column(h)
            if col:
                header_map[h] = col

        print(f"Mapped {len(header_map)}/{len(headers)} CSV columns:")
        for h, c in header_map.items():
            print(f"  {h.strip()[:40]:40s} → {c}")

        for csv_row in reader:
            db_row = {}
            for csv_h, db_col in header_map.items():
                val = csv_row.get(csv_h, "").strip()
                if val:
                    db_row[db_col] = val
            # Skip rows without product_name
            if db_row.get("product_name"):
                rows.append(db_row)

    return rows


def main():
    print("=" * 60)
    print("Populate products2 — CSV → Embedding → Supabase")
    print("=" * 60)

    # Init clients
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Read CSV
    print("\n1. Reading CSV...")
    rows = read_csv()
    print(f"   ✓ {len(rows)} products found\n")

    # Process each row
    print("2. Generating embeddings & inserting...")
    success = 0
    errors = 0

    for idx, row in enumerate(rows, 1):
        name = row.get("product_name", "?")
        print(f"[{idx:2d}/{len(rows)}] {name}")

        # Generate embedding
        embed_text = build_embedding_text(row)
        embedding = generate_embedding(embed_text, openai_client)

        if embedding:
            row["embedding"] = embedding
            print(f"        ✓ embedding ({len(embedding)} dims)")
        else:
            print(f"        ✗ embedding failed — inserting without")

        # Insert into Supabase
        try:
            supabase.table("products2").insert(row).execute()
            success += 1
            print(f"        ✓ inserted")
        except Exception as e:
            errors += 1
            print(f"        ✗ insert error: {e}")

        # Rate limit (OpenAI tier-1: 500 RPM)
        time.sleep(0.3)

    print("\n" + "=" * 60)
    print(f"Done! Success: {success} | Errors: {errors}")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
