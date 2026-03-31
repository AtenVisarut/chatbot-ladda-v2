"""
Sync Google Sheets → Supabase products_icp + re-generate embedding
ใช้สำหรับทีม PD อัปเดตข้อมูลสินค้าผ่าน Google Sheets

Usage:
    python scripts/sync_sheets_to_supabase.py

Env vars:
    GOOGLE_SERVICE_ACCOUNT  - JSON string ของ Google service account
    GOOGLE_SHEET_ID         - Google Sheets ID
    SUPABASE_URL            - Supabase project URL
    SUPABASE_SERVICE_KEY    - Supabase service_role key (ไม่ใช่ anon key)
    OPENAI_API_KEY          - OpenAI API key
    CHATBOT_URL             - (optional) URL ของ chatbot สำหรับ reload registry
"""
import os
import sys
import json
import hashlib
import time
import glob
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

load_dotenv()

import gspread
from google.oauth2.service_account import Credentials
from supabase import create_client, Client
from openai import OpenAI
from app.utils.embedding_text import build_embedding_text

# ============================================================
# Config
# ============================================================
PRODUCT_TABLE = "products_icp"
BACKUP_DIR = os.path.join(os.path.dirname(__file__), "backups")
MAX_BACKUPS = 5

# Column mapping: Google Sheets header → Supabase column
SHEET_TO_DB = {
    "product_name": "product_name",
    "common_name_th": "common_name_th",
    "active_ingredient": "active_ingredient",
    "(กลุ่มสารเคมี)กลุ่ม 1-29 ตาม RAC": "chemical_group_rac",
    "Herbicides": "herbicides",
    "Fungicides": "fungicides",
    "Insecticides": "insecticides",
    "Plant Biostimulant": "biostimulant",
    "PGR/Hormones": "pgr_hormones",
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
    "ข้อควรระวังเพิ่มเติม": "caution_notes",
    "strategy": "strategy",
}


# ============================================================
# Functions
# ============================================================

def connect_google_sheets():
    """เชื่อมต่อ Google Sheets ด้วย service account"""
    creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT")
    sheet_id = os.getenv("GOOGLE_SHEET_ID")

    if not creds_json:
        print("ERROR: GOOGLE_SERVICE_ACCOUNT env var not set")
        sys.exit(1)
    if not sheet_id:
        print("ERROR: GOOGLE_SHEET_ID env var not set")
        sys.exit(1)

    creds_dict = json.loads(creds_json)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)

    spreadsheet = gc.open_by_key(sheet_id)
    worksheet = spreadsheet.worksheet("Products")
    print(f"✓ เชื่อมต่อ Google Sheets สำเร็จ: {spreadsheet.title}")
    return worksheet


def read_sheets_data(worksheet) -> list:
    """อ่านข้อมูลจาก Google Sheets → list of dicts"""
    records = worksheet.get_all_records()
    print(f"✓ อ่านข้อมูลจาก Sheets: {len(records)} rows")
    return records


def compute_row_hash(row: dict) -> str:
    """คำนวณ MD5 hash ของ row เพื่อตรวจจับการเปลี่ยนแปลง"""
    # เอาเฉพาะ columns ที่ sync (ไม่รวม id, embedding, hash, timestamps)
    content = ""
    for sheet_col, db_col in SHEET_TO_DB.items():
        val = str(row.get(sheet_col, "") or "").strip()
        content += val
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def map_row_to_db(row: dict) -> dict:
    """แปลง Sheets row → Supabase record"""
    record = {}
    for sheet_col, db_col in SHEET_TO_DB.items():
        val = row.get(sheet_col, "")
        if isinstance(val, str):
            val = val.strip()
        record[db_col] = val if val else None
    return record


def validate_row(row: dict, idx: int) -> bool:
    """ตรวจสอบว่า row มีข้อมูลครบ"""
    name = str(row.get("product_name", "") or "").strip()
    category = str(row.get("product_category", "") or "").strip()

    if not name:
        print(f"  ⚠ Row {idx}: product_name ว่าง → skip")
        return False
    if not category:
        print(f"  ⚠ Row {idx}: product_category ว่าง ({name}) → skip")
        return False
    return True


def backup_products(supabase: Client):
    """Backup products ก่อน sync"""
    os.makedirs(BACKUP_DIR, exist_ok=True)

    try:
        result = supabase.table(PRODUCT_TABLE).select(
            "id, product_name, common_name_th, active_ingredient, "
            "fungicides, insecticides, herbicides, biostimulant, pgr_hormones, "
            "applicable_crops, how_to_use, usage_period, usage_rate, "
            "product_category, strategy, caution_notes, row_hash"
        ).execute()

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(BACKUP_DIR, f"products_icp_backup_{ts}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.data, f, ensure_ascii=False, indent=2)
        print(f"✓ Backup saved: {path} ({len(result.data)} rows)")

        # ลบ backup เก่า เก็บแค่ 5 ไฟล์
        backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "products_icp_backup_*.json")))
        while len(backups) > MAX_BACKUPS:
            old = backups.pop(0)
            os.remove(old)
            print(f"  ลบ backup เก่า: {os.path.basename(old)}")

    except Exception as e:
        print(f"⚠ Backup failed (continue anyway): {e}")


def sync():
    """Main sync function"""
    print("=" * 60)
    print("Sync Google Sheets → Supabase products_icp")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # --- Init clients ---
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if not supabase_url or not supabase_key:
        print("ERROR: SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
        sys.exit(1)
    if not openai_key:
        print("ERROR: OPENAI_API_KEY not set")
        sys.exit(1)

    supabase = create_client(supabase_url, supabase_key)
    openai_client = OpenAI(api_key=openai_key)

    # --- 1. อ่าน Google Sheets ---
    print("\n1. อ่าน Google Sheets...")
    worksheet = connect_google_sheets()
    sheets_rows = read_sheets_data(worksheet)

    # --- 2. อ่าน hash ปัจจุบันจาก Supabase ---
    print("\n2. อ่าน row_hash จาก Supabase...")
    try:
        db_result = supabase.table(PRODUCT_TABLE).select("product_name, row_hash").execute()
        db_hashes = {r["product_name"]: r.get("row_hash") for r in db_result.data}
        print(f"   DB มี {len(db_hashes)} products")
    except Exception as e:
        print(f"   ⚠ อ่าน DB failed (treat all as new): {e}")
        db_hashes = {}

    # --- 3. เปรียบเทียบ hash → หา rows ที่เปลี่ยน ---
    print("\n3. ตรวจหา rows ที่เปลี่ยน...")
    changed_rows = []
    skipped_validation = 0
    unchanged = 0

    for idx, row in enumerate(sheets_rows, 1):
        name = str(row.get("product_name", "") or "").strip()
        if not name or name.lower() == "example":
            continue

        if not validate_row(row, idx):
            skipped_validation += 1
            continue

        new_hash = compute_row_hash(row)
        old_hash = db_hashes.get(name)

        if new_hash == old_hash:
            unchanged += 1
        else:
            reason = "NEW" if old_hash is None else "CHANGED"
            changed_rows.append((row, new_hash, reason))
            print(f"   [{reason}] {name}")

    print(f"\n   Unchanged: {unchanged}")
    print(f"   Changed: {len(changed_rows)}")
    print(f"   Skipped (validation): {skipped_validation}")

    if not changed_rows:
        print("\n✓ ไม่มี row ที่เปลี่ยน — ไม่ต้อง sync")
        print_summary(len(sheets_rows), 0, skipped_validation, 0, 0)
        return

    # --- 4. Backup ก่อน sync ---
    print("\n4. Backup ก่อน sync...")
    backup_products(supabase)

    # --- 5. Upsert + generate embedding ---
    print(f"\n5. Syncing {len(changed_rows)} rows...")
    success = 0
    errors = 0

    for i, (row, row_hash, reason) in enumerate(changed_rows, 1):
        name = row.get("product_name", "?")
        try:
            record = map_row_to_db(row)
            record["row_hash"] = row_hash
            record["updated_at"] = datetime.now().isoformat()

            # Generate embedding
            emb_text = build_embedding_text(record)
            emb_response = openai_client.embeddings.create(
                model="text-embedding-3-small", input=emb_text
            )
            record["embedding"] = emb_response.data[0].embedding

            # Upsert (on conflict product_name)
            supabase.table(PRODUCT_TABLE).upsert(
                record, on_conflict="product_name"
            ).execute()

            print(f"   [{i}/{len(changed_rows)}] ✓ {name} ({reason})")
            success += 1
            time.sleep(0.3)  # Rate limiting

        except Exception as e:
            print(f"   [{i}/{len(changed_rows)}] ✗ {name}: {e}")
            errors += 1

    # --- 6. Post-sync: reload registry ---
    print("\n6. Post-sync...")
    chatbot_url = os.getenv("CHATBOT_URL")
    if chatbot_url:
        try:
            import httpx
            r = httpx.post(f"{chatbot_url}/admin/reload-registry", timeout=10)
            print(f"   ✓ Reload registry: {r.status_code}")
        except Exception as e:
            print(f"   ⚠ Reload failed: {e}")
    else:
        print("   TODO: ตั้ง CHATBOT_URL env var เพื่อ reload registry อัตโนมัติ")

    # --- 7. Summary ---
    print_summary(len(sheets_rows), len(changed_rows), skipped_validation, success, errors)

    if errors > 0:
        sys.exit(1)


def print_summary(total, changed, skipped, success, errors):
    """พิมพ์สรุปผล"""
    print("\n" + "=" * 60)
    print("สรุปผล Sync")
    print("=" * 60)
    print(f"  Total rows in Sheets:  {total}")
    print(f"  Changed rows:          {changed}")
    print(f"  Skipped (validation):  {skipped}")
    print(f"  Successfully synced:   {success}")
    print(f"  Errors:                {errors}")
    print("=" * 60)


if __name__ == "__main__":
    try:
        sync()
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
