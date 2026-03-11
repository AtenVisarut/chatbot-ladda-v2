"""
Populate products3 table from ICP_product3.csv + generate fresh embeddings.

Usage:
    python migrations/populate_products3.py

Reads: ICP_product3.csv (CSV)
Target: Supabase products3 table
Embedding: OpenAI text-embedding-3-small (1536 dims)

After running:
  - 47 products inserted with embeddings
  - aliases/link_product/image_url copied from products2
"""
import csv
import os
import sys
import time
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI

# Fix Windows console encoding for Thai text
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# CSV is at chatbot_ladda-ick/ICP_product3.csv (2 levels up from migrations/)
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ICP_product3.csv")
TARGET_TABLE = "products3"

# CSV header -> DB column mapping (exact match)
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

# Headers with leading/trailing spaces or Thai -- match by substring
FUZZY_COLUMNS = {
    "กลุ่มสารเคมี": "chemical_group_rac",
    "Fungicides": "fungicides",
    "PGR": "pgr_hormones",
    "ข้อควรระวังเพิ่มเติม": "caution_notes",
}

# Skip these CSV columns (not DB fields)
SKIP_COLUMNS = {"embedding"}


def _resolve_column(header: str) -> str | None:
    """Map a CSV header to a DB column name."""
    h = header.strip()
    if h in SKIP_COLUMNS:
        return None
    if h in COLUMN_MAP:
        return COLUMN_MAP[h]
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
        print(f"  [FAIL] Embedding error: {e}")
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
        f"ข้อควรระวัง: {row.get('caution_notes', '')}" if row.get('caution_notes') else "",
        f"กลยุทธ์: {row.get('strategy', '')}",
    ]
    return " | ".join(p for p in parts if p)


def read_csv() -> list[dict]:
    """Read CSV and map to DB columns."""
    if not os.path.exists(CSV_PATH):
        print(f"ERROR: CSV not found at {CSV_PATH}")
        sys.exit(1)

    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)

    # Build header -> column mapping
    header_map = {}
    for i, h in enumerate(headers):
        if h:
            col = _resolve_column(str(h))
            if col:
                header_map[i] = col

    print(f"Mapped {len(header_map)}/{len(headers)} CSV columns:")
    for i, col in header_map.items():
        h_str = str(headers[i]).strip()[:40]
        print(f"  [{i:2d}] {h_str:40s} -> {col}")

    # Re-read with DictReader-style parsing (handle multi-line fields)
    rows = []
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for csv_row in reader:
            db_row = {}
            for col_idx, db_col in header_map.items():
                if col_idx < len(csv_row) and csv_row[col_idx] is not None:
                    val = str(csv_row[col_idx]).strip()
                    if val:
                        db_row[db_col] = val
            if db_row.get("product_name"):
                rows.append(db_row)

    return rows


def copy_compat_columns(supabase: Client):
    """Copy aliases, link_product, image_url from products2 to products3."""
    print("\n3. Copying aliases/link_product/image_url from products2...")

    result = supabase.table("products2").select(
        "product_name, aliases, link_product, image_url"
    ).execute()

    if not result.data:
        print("   [WARN] No data in products2 -- skipping compat copy")
        return

    copied = 0
    for p2 in result.data:
        name = p2.get("product_name")
        if not name:
            continue

        update = {}
        if p2.get("aliases"):
            update["aliases"] = p2["aliases"]
        if p2.get("link_product"):
            update["link_product"] = p2["link_product"]
        if p2.get("image_url"):
            update["image_url"] = p2["image_url"]

        if update:
            try:
                supabase.table(TARGET_TABLE).update(update).eq(
                    "product_name", name
                ).execute()
                copied += 1
            except Exception:
                pass

    print(f"   [OK] Copied compat columns for {copied} products")


def main():
    print("=" * 60)
    print(f"Populate {TARGET_TABLE} -- CSV -> Embedding -> Supabase")
    print("=" * 60)

    # Init clients
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Read CSV
    print("\n1. Reading CSV...")
    rows = read_csv()
    print(f"   [OK] {len(rows)} products found\n")

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
            print(f"        [OK] embedding ({len(embedding)} dims)")
        else:
            print(f"        [FAIL] embedding failed -- inserting without")

        # Insert into Supabase
        try:
            supabase.table(TARGET_TABLE).insert(row).execute()
            success += 1
            print(f"        [OK] inserted")
        except Exception as e:
            errors += 1
            print(f"        [FAIL] insert error: {e}")

        # Rate limit (OpenAI tier-1: 500 RPM)
        time.sleep(0.3)

    print(f"\n   Insert done! Success: {success} | Errors: {errors}")

    # Copy compat columns from products2
    copy_compat_columns(supabase)

    print("\n" + "=" * 60)
    print(f"Done! {TARGET_TABLE} populated with {success} products")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
