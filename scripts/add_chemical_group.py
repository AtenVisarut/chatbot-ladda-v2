"""
Script to add chemical_group (กลุ่มสาร) to products table in Supabase
Data source: C:\clone_chatbot_ick\Data ICPL product for iDA - สำหรับ view.csv
"""
import sys
import os
import io
import csv

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Setup path
os.chdir("C:\\clone_chatbot_ick\\Chatbot-ladda")
sys.path.insert(0, "C:\\clone_chatbot_ick\\Chatbot-ladda")

from dotenv import load_dotenv
load_dotenv()

from app.services.services import supabase_client

# CSV file path
CSV_PATH = r"C:\clone_chatbot_ick\Data ICPL product for iDA - สำหรับ view.csv"

def parse_csv():
    """Parse CSV and extract product_name -> chemical_group mapping"""
    mapping = {}

    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)  # Skip header

        # Find column indices
        # Column 3 = ชื่อสินค้า (ชื่อการค้า)
        # Column 6 = กลุ่มสาร
        product_col = 3
        chemical_group_col = 6

        for row in reader:
            if len(row) > chemical_group_col:
                product_name = row[product_col].strip() if row[product_col] else ""
                chemical_group = row[chemical_group_col].strip() if row[chemical_group_col] else ""

                if product_name and chemical_group:
                    # Clean up product name (remove special chars at end)
                    product_name = product_name.rstrip(' ,.')
                    mapping[product_name] = chemical_group

    return mapping

def update_products(mapping):
    """Update products in Supabase with chemical_group"""

    # Get all products
    result = supabase_client.table('products').select('id, product_name').execute()
    products = result.data

    print(f"Found {len(products)} products in database")
    print(f"Found {len(mapping)} products in CSV with กลุ่มสาร")
    print()

    updated = 0
    not_found = []

    for product in products:
        db_name = product['product_name']
        product_id = product['id']

        # Try exact match first
        chemical_group = mapping.get(db_name)

        # Try partial match if not found
        if not chemical_group:
            for csv_name, group in mapping.items():
                # Check if CSV name is contained in DB name or vice versa
                if csv_name in db_name or db_name in csv_name:
                    chemical_group = group
                    break
                # Check without spaces
                if csv_name.replace(" ", "") == db_name.replace(" ", ""):
                    chemical_group = group
                    break

        if chemical_group:
            # Update product
            try:
                supabase_client.table('products').update({
                    'chemical_group': chemical_group
                }).eq('id', product_id).execute()

                print(f"✓ Updated: {db_name} → {chemical_group}")
                updated += 1
            except Exception as e:
                print(f"✗ Error updating {db_name}: {e}")
        else:
            not_found.append(db_name)

    print()
    print(f"=== Summary ===")
    print(f"Updated: {updated} products")
    print(f"Not found in CSV: {len(not_found)} products")

    if not_found:
        print()
        print("Products not found in CSV:")
        for name in not_found[:20]:  # Show first 20
            print(f"  - {name}")
        if len(not_found) > 20:
            print(f"  ... and {len(not_found) - 20} more")

def main():
    print("=== Add Chemical Group to Products ===")
    print()

    # Parse CSV
    print("1. Parsing CSV...")
    mapping = parse_csv()

    print(f"   Extracted {len(mapping)} product-chemical_group mappings")
    print()

    # Show sample
    print("   Sample mappings:")
    for i, (name, group) in enumerate(list(mapping.items())[:5]):
        print(f"     {name}: {group}")
    print()

    # Update products
    print("2. Updating products in Supabase...")
    print()
    update_products(mapping)

if __name__ == "__main__":
    main()
