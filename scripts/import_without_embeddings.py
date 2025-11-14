"""
Import CSV to Supabase WITHOUT embeddings (faster, no OpenAI needed)
Use this if you have network issues
"""
import os
import csv
import json
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def import_csv_simple(csv_path: str):
    """Import CSV data to Supabase WITHOUT embeddings"""
    
    print(f"Reading CSV file: {csv_path}")
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    print(f"Found {len(rows)} products")
    
    success_count = 0
    error_count = 0
    
    # Prepare batch insert
    batch_data = []
    
    for idx, row in enumerate(rows, 1):
        try:
            # Extract key fields
            product_name = row.get('ชื่อสินค้า (ชื่อการค้า)', '').strip()
            if not product_name:
                print(f"Row {idx}: Skipping - no product name")
                continue
            
            active_ingredient = row.get('สารสําคัญ', '').strip()
            target_pest = row.get('ศัตรูพืชที่กำจัดได้', '').strip()
            applicable_crops = row.get('ใช้ได้กับพืช', '').strip()
            how_to_use = row.get('วิธีใช้', '').strip()
            product_group = row.get('กลุ่มสาร', '').strip()
            formulation = row.get('Formulation', '').strip()
            usage_rate = row.get('อัตราการใช้', '').strip()
            
            # Prepare data (NO embedding)
            data = {
                'product_name': product_name,
                'active_ingredient': active_ingredient,
                'target_pest': target_pest,
                'applicable_crops': applicable_crops,
                'how_to_use': how_to_use,
                'product_group': product_group,
                'formulation': formulation,
                'usage_rate': usage_rate,
                'metadata': json.dumps(row, ensure_ascii=False)
            }
            
            batch_data.append(data)
            print(f"[{idx}/{len(rows)}] Prepared: {product_name}")
            
        except Exception as e:
            print(f"  ✗ Error preparing row {idx}: {e}")
            error_count += 1
            continue
    
    # Insert all at once
    if batch_data:
        try:
            print(f"\nInserting {len(batch_data)} products to Supabase...")
            result = supabase.table('products').insert(batch_data).execute()
            success_count = len(batch_data)
            print(f"✓ Successfully inserted {success_count} products")
        except Exception as e:
            print(f"✗ Batch insert failed: {e}")
            print("\nTrying one-by-one insert...")
            
            # Fallback: insert one by one
            for idx, data in enumerate(batch_data, 1):
                try:
                    supabase.table('products').insert(data).execute()
                    print(f"  [{idx}/{len(batch_data)}] ✓ {data['product_name']}")
                    success_count += 1
                except Exception as e2:
                    print(f"  [{idx}/{len(batch_data)}] ✗ {data['product_name']}: {e2}")
                    error_count += 1
    
    print("\n" + "="*60)
    print(f"Import completed!")
    print(f"Success: {success_count}")
    print(f"Errors: {error_count}")
    print("="*60)
    print("\nNote: Embeddings not generated. System will use keyword search.")

if __name__ == "__main__":
    # Check if CSV path provided as argument
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    else:
        csv_file = "Data ICPL product for iDA.csv"
    
    if not os.path.exists(csv_file):
        print(f"Error: CSV file not found: {csv_file}")
        print(f"Usage: python {sys.argv[0]} <path_to_csv>")
        exit(1)
    
    print("Starting CSV import to Supabase (WITHOUT embeddings)...")
    print("="*60)
    
    import_csv_simple(csv_file)
