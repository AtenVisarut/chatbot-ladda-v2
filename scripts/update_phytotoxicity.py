"""
Script: Update phytotoxicity column in Supabase products table from CSV

Usage:
    python scripts/update_phytotoxicity.py
"""
import os, sys, csv, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
os.chdir("C:\\clone_chatbot_ick\\Chatbot-ladda")
sys.path.insert(0, "C:\\clone_chatbot_ick\\Chatbot-ladda")

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

CSV_FILE = "C:\\clone_chatbot_ick\\Data ICPL product for iDA - สำหรับ view.csv"

# Name aliases: CSV name → DB name
NAME_ALIASES = {
    "อาร์เทมีส": "อาร์เทมิส",
    "ก๊อปกัน": "ก็อปกัน",
}

# 1. Load CSV
csv_data = {}
with open(CSV_FILE, encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        name = row.get('ชื่อสินค้า (ชื่อการค้า)', '').strip()
        phyto = row.get('ความเป็นพิษต่อพืชประธาน', '').strip()
        if name and phyto:
            # Apply alias
            db_name = NAME_ALIASES.get(name, name)
            csv_data[db_name] = phyto

print(f"CSV: {len(csv_data)} products with phytotoxicity data\n")

# 2. Fetch DB products
res = sb.table('products').select('id, product_name, phytotoxicity').execute()
products = res.data
print(f"DB: {len(products)} products\n")

# 3. Match and update
updated = 0
skipped = 0
not_found = []

print(f"{'ID':>4} | {'Product':<30} | {'Status':<10} | Phytotoxicity")
print("-" * 100)

for p in sorted(products, key=lambda x: x['id']):
    pid = p['id']
    pname = p['product_name']
    existing = p.get('phytotoxicity') or ''

    # Try exact match
    phyto = csv_data.get(pname)

    # Try partial match if exact fails
    if not phyto:
        for csv_name, csv_phyto in csv_data.items():
            if csv_name in pname or pname in csv_name:
                phyto = csv_phyto
                break

    if not phyto:
        not_found.append(pname)
        print(f"{pid:>4} | {pname:<30} | NOT FOUND  |")
        continue

    if existing:
        print(f"{pid:>4} | {pname:<30} | EXISTS     | {existing[:50]}")
        skipped += 1
        continue

    # Update
    sb.table('products').update({'phytotoxicity': phyto}).eq('id', pid).execute()
    print(f"{pid:>4} | {pname:<30} | UPDATED    | {phyto[:50]}")
    updated += 1

print(f"\n{'='*60}")
print(f"Updated: {updated}")
print(f"Already had data: {skipped}")
print(f"Not found in CSV: {len(not_found)}")
if not_found:
    for n in not_found:
        print(f"  - {n}")
print(f"{'='*60}")
