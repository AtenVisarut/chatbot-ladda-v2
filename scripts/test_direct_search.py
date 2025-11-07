"""
Test direct search without RPC function
"""
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

def test_search():
    print("Testing direct search...")
    
    # Test 1: Get all products
    print("\n1. Getting all products...")
    response = supabase.table('products').select('product_name, target_pest').limit(5).execute()
    print(f"Found {len(response.data)} products:")
    for p in response.data:
        print(f"  - {p['product_name']}: {p['target_pest'][:50]}...")
    
    # Test 2: Search by keyword
    print("\n2. Keyword search for 'เพลี้ยไฟ'...")
    response = supabase.table('products').select('*').ilike('target_pest', '%เพลี้ยไฟ%').execute()
    print(f"Found {len(response.data)} products")
    for p in response.data:
        print(f"  - {p['product_name']}")
    
    # Test 3: Generate embedding and search
    print("\n3. Vector search for 'เพลี้ยไฟ ทุเรียน'...")
    query = "เพลี้ยไฟ ทุเรียน ศัตรูพืช แมลง"
    
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=query
    )
    embedding = response.data[0].embedding
    
    print(f"Generated embedding with {len(embedding)} dimensions")
    
    # Try RPC with very low threshold
    try:
        result = supabase.rpc(
            'match_products',
            {
                'query_embedding': embedding,
                'match_threshold': 0.0,  # Very low threshold
                'match_count': 5
            }
        ).execute()
        
        print(f"RPC returned {len(result.data) if result.data else 0} results")
        if result.data:
            for item in result.data[:3]:
                print(f"  - {item.get('product_name')}: similarity={item.get('similarity', 0):.3f}")
        else:
            print("  No results!")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Test 4: Check if embeddings exist
    print("\n4. Checking embeddings...")
    response = supabase.table('products').select('product_name, embedding').limit(3).execute()
    for p in response.data:
        has_embedding = p.get('embedding') is not None
        print(f"  - {p['product_name']}: embedding={'✓' if has_embedding else '✗'}")

if __name__ == "__main__":
    test_search()
