"""
Debug Vector Search - Check what's wrong
"""
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def debug_vector_search():
    print("=" * 60)
    print("Debug Vector Search")
    print("=" * 60)
    
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # 1. Check products
    print("\n1. Checking products...")
    result = supabase.table('products').select('*').execute()
    print(f"✓ Total products: {len(result.data)}")
    
    if result.data:
        first_product = result.data[0]
        print(f"✓ First product: {first_product.get('product_name')}")
        print(f"✓ Has embedding: {first_product.get('embedding') is not None}")
        if first_product.get('embedding'):
            emb = first_product.get('embedding')
            if isinstance(emb, list):
                print(f"✓ Embedding type: list")
                print(f"✓ Embedding length: {len(emb)} dimensions")
            else:
                print(f"✗ Embedding type: {type(emb)} (should be list)")
                print(f"✗ Embedding length: {len(str(emb))} chars (should be 1536 dimensions)")
    
    # 2. Check RPC function exists
    print("\n2. Testing RPC function...")
    try:
        # Create a dummy embedding
        dummy_embedding = [0.0] * 1536
        
        result = supabase.rpc(
            'match_products',
            {
                'query_embedding': dummy_embedding,
                'match_threshold': 0.0,  # Very low threshold
                'match_count': 5
            }
        ).execute()
        
        print(f"✓ RPC function exists")
        print(f"✓ Results: {len(result.data)} products")
        
        if result.data:
            for p in result.data[:3]:
                print(f"  - {p.get('product_name')} (similarity: {p.get('similarity', 0):.4f})")
        else:
            print("  ⚠️  No results even with threshold=0.0")
            print("  This means embeddings might be NULL or wrong type")
            
    except Exception as e:
        print(f"✗ RPC function error: {e}")
        print("\n⚠️  RPC function 'match_products' not found or has error!")
        print("   Please run the SQL from: scripts/clean_start.sql")
        return
    
    # 3. Test with real query
    print("\n3. Testing with real query...")
    query = "เพลี้ยไฟ ศัตรูพืช แมลง"
    
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=query
    )
    query_embedding = response.data[0].embedding
    
    # Try different thresholds
    thresholds = [0.0, 0.3, 0.5, 0.7]
    
    for threshold in thresholds:
        result = supabase.rpc(
            'match_products',
            {
                'query_embedding': query_embedding,
                'match_threshold': threshold,
                'match_count': 5
            }
        ).execute()
        
        print(f"\nThreshold {threshold}: {len(result.data)} results")
        if result.data:
            for p in result.data[:2]:
                print(f"  - {p.get('product_name')} ({p.get('similarity', 0):.2%})")
    
    print("\n" + "=" * 60)
    print("Debug completed!")
    print("=" * 60)

if __name__ == "__main__":
    try:
        debug_vector_search()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
