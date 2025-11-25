import os
import csv
import asyncio
from typing import List, Dict
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import AsyncOpenAI

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY or not OPENAI_API_KEY:
    print("Error: Missing environment variables. Please check .env file.")
    exit(1)

# Initialize clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

CSV_FILE = "Data ICPL product for iDA.csv"

async def get_embedding(text: str) -> List[float]:
    """Generate embedding using OpenAI"""
    try:
        response = await openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
            encoding_format="float"
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return []

def read_csv(file_path: str) -> List[Dict]:
    """Read CSV file and return list of dicts"""
    products = []
    try:
        with open(file_path, mode='r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Clean keys (remove BOM or whitespace)
                clean_row = {k.strip(): v.strip() for k, v in row.items() if k}
                if not products:
                    print(f"Debug - First row keys: {list(clean_row.keys())}")
                    print(f"Debug - First row sample values:")
                    for key in list(clean_row.keys())[:10]:
                        print(f"  '{key}': '{clean_row[key][:50] if clean_row[key] else 'EMPTY'}'")
                products.append(clean_row)
    except Exception as e:
        print(f"Error reading CSV: {e}")
    return products

async def process_product(product: Dict):
    """Process a single product and upload to Supabase"""
    try:
        # Create text for embedding
        # Combine important fields to create a rich semantic representation
        text_to_embed = f"""
        Product: {product.get('ชื่อสินค้า (ชื่อการค้า)', '')}
        Active Ingredient: {product.get('สารสําคัญ', '')}
        Common Name: {product.get('ชื่อสาร', '')}
        Target Pest: {product.get('ศัตรูพืชที่กำจัดได้', '')}
        Applicable Crops: {product.get('ใช้ได้กับพืช', '')}
        Usage: {product.get('วิธีใช้', '')}
        """
        
        # Generate embedding
        embedding = await get_embedding(text_to_embed)
        
        if not embedding:
            print(f"Skipping {product.get('ชื่อสินค้า (ชื่อการค้า)')}: No embedding generated")
            return

        # Prepare data for Supabase
        # Map Thai CSV headers to Supabase columns
        data = {
            "product_name": product.get('ชื่อสินค้า (ชื่อการค้า)', ''),
            "active_ingredient": product.get('สารสําคัญ', ''),
            "target_pest": product.get('ศัตรูพืชที่กำจัดได้', ''),
            "applicable_crops": product.get('ใช้ได้กับพืช', ''),
            "how_to_use": product.get('วิธีใช้', ''),
            "usage_period": product.get('ช่วงการใช้', ''),
            "usage_rate": product.get('อัตราการใช้', ''),
            "embedding": embedding
        }

        # Insert into Supabase
        supabase.table("products").insert(data).execute()
        print(f"✅ Imported: {product.get('ชื่อสินค้า (ชื่อการค้า)')}")

    except Exception as e:
        print(f"❌ Error processing {product.get('ชื่อสินค้า (ชื่อการค้า)')}: {e}")

async def main():
    print(f"Starting import from {CSV_FILE}...")
    
    products = read_csv(CSV_FILE)
    print(f"Found {len(products)} products in CSV.")
    
    # Process in batches to avoid rate limits
    batch_size = 5
    for i in range(0, len(products), batch_size):
        batch = products[i:i+batch_size]
        await asyncio.gather(*[process_product(p) for p in batch])
        print(f"Processed batch {i//batch_size + 1}/{(len(products)-1)//batch_size + 1}")
        await asyncio.sleep(1)  # Small delay to be nice to API

    print("\nImport completed! 🎉")

if __name__ == "__main__":
    asyncio.run(main())
