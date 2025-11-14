"""
Import CSV to Supabase using direct connection
Try to bypass DNS issues
"""
import os
import csv
import json
import sys
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def import_csv_direct(csv_path: str):
    """Import CSV using direct HTTP requests"""
    
    print(f"Reading CSV file: {csv_path}")
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    print(f"Found {len(rows)} products")
    
    # Prepare data
    batch_data = []
    for idx, row in enumerate(rows, 1):
        product_name = row.get('ชื่อสินค้า (ชื่อการค้า)', '').strip()
        if not product_name:
            continue
        
        data = {
            'product_name': product_name,
            'active_ingredient': row.get('สารสําคัญ', '').strip(),
            'target_pest': row.get('ศัตรูพืชที่กำจัดได้', '').strip(),
            'applicable_crops': row.get('ใช้ได้กับพืช', '').strip(),
            'how_to_use': row.get('วิธีใช้', '').strip(),
            'product_group': row.get('กลุ่มสาร', '').strip(),
            'formulation': row.get('Formulation', '').strip(),
            'usage_rate': row.get('อัตราการใช้', '').strip(),
            'metadata': json.dumps(row, ensure_ascii=False)
        }
        batch_data.append(data)
        print(f"[{idx}/{len(rows)}] Prepared: {product_name}")
    
    print(f"\nPrepared {len(batch_data)} products")
    print(f"Attempting direct HTTP connection to: {SUPABASE_URL}")
    
    # Try direct HTTP request
    url = f"{SUPABASE_URL}/rest/v1/products"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    
    try:
        # Try with longer timeout and no SSL verification
        with httpx.Client(timeout=30.0, verify=False) as client:
            print("Sending batch insert request...")
            response = client.post(url, json=batch_data, headers=headers)
            
            if response.status_code in [200, 201]:
                print(f"✓ Successfully inserted {len(batch_data)} products!")
                return True
            else:
                print(f"✗ Failed: HTTP {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        print(f"Error type: {type(e).__name__}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    else:
        csv_file = "Data ICPL product for iDA.csv"
    
    if not os.path.exists(csv_file):
        print(f"Error: CSV file not found: {csv_file}")
        exit(1)
    
    print("Starting direct HTTP import to Supabase...")
    print("="*60)
    
    success = import_csv_direct(csv_file)
    
    if success:
        print("\n✓ Import completed successfully!")
    else:
        print("\n✗ Import failed. Please use Supabase Dashboard instead.")
