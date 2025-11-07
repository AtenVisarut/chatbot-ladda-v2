"""
Test Supabase connection and vector search
"""
import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def test_connection():
    """Test Supabase connection"""
    print("Testing Supabase connection...")
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Try to query products table
        response = supabase.table('products').select('id').limit(1).execute()
        
        print("✓ Connection successful!")
        print(f"  Database is accessible")
        return True
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False

def test_product_count():
    """Test product count"""
    print("\nChecking product count...")
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        response = supabase.table('products').select('id', count='exact').execute()
        count = response.count
        
        print(f"✓ Found {count} products in database")
        return True
    except Exception as e:
        print(f"✗ Failed to count products: {e}")
        return False

def test_vector_search():
    """Test vector similarity search"""
    print("\nTesting vector search...")
    
    test_queries = [
        "เพลี้ยไฟ ทุเรียน",
        "หนอนกอข้าว",
        "โรคแอนแทรคโนส",
        "เชื้อรา ใบไหม้"
    ]
    
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        
        for query in test_queries:
            print(f"\n  Query: '{query}'")
            
            # Generate embedding
            response = openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=query
            )
            embedding = response.data[0].embedding
            
            # Search
            results = supabase.rpc(
                'match_products',
                {
                    'query_embedding': embedding,
                    'match_threshold': 0.3,
                    'match_count': 3
                }
            ).execute()
            
            if results.data:
                print(f"  ✓ Found {len(results.data)} matches:")
                for i, product in enumerate(results.data[:3], 1):
                    similarity = product.get('similarity', 0)
                    name = product.get('product_name', 'Unknown')
                    pest = product.get('target_pest', 'N/A')
                    print(f"    {i}. {name}")
                    print(f"       ศัตรูพืช: {pest[:50]}...")
                    print(f"       Similarity: {similarity:.3f}")
            else:
                print(f"  ⚠️  No matches found")
        
        return True
    except Exception as e:
        print(f"✗ Vector search failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_product_details():
    """Test retrieving product details"""
    print("\nTesting product details retrieval...")
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        response = supabase.table('products').select('*').limit(3).execute()
        
        if response.data:
            print(f"✓ Retrieved {len(response.data)} products")
            for product in response.data:
                print(f"\n  Product: {product.get('product_name')}")
                print(f"  - สารสำคัญ: {product.get('active_ingredient', 'N/A')}")
                print(f"  - ศัตรูพืช: {product.get('target_pest', 'N/A')[:50]}...")
                print(f"  - ใช้ได้กับพืช: {product.get('applicable_crops', 'N/A')[:50]}...")
        else:
            print("⚠️  No products found")
        
        return True
    except Exception as e:
        print(f"✗ Failed to retrieve products: {e}")
        return False

def main():
    print("="*60)
    print("Supabase Integration Test")
    print("="*60)
    
    # Check environment variables
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("✗ Missing Supabase credentials in .env file")
        print("  Please set SUPABASE_URL and SUPABASE_KEY")
        return
    
    if not OPENAI_API_KEY:
        print("✗ Missing OpenAI API key in .env file")
        return
    
    # Run tests
    tests = [
        test_connection,
        test_product_count,
        test_product_details,
        test_vector_search
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
            results.append(False)
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("✓ All tests passed!")
    else:
        print("⚠️  Some tests failed. Check the output above.")
    print("="*60)

if __name__ == "__main__":
    main()
