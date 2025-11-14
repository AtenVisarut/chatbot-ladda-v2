"""
Test Knowledge Table Vector Search
"""
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def test_knowledge_search():
    print("=" * 60)
    print("Test Knowledge Table Vector Search")
    print("=" * 60)
    
    if not OPENAI_API_KEY:
        print("❌ OPENAI_API_KEY not found (needed for embeddings)")
        return
    
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # 1. Check knowledge table
    print("\n1. Checking knowledge table...")
    try:
        result = supabase.table('knowledge').select('*').limit(5).execute()
        print(f"✓ Total knowledge entries: {len(result.data)}")
        
        if result.data:
            first_item = result.data[0]
            print(f"✓ First entry ID: {first_item.get('id')}")
            content = first_item.get('content', '')
            print(f"✓ Content preview: {content[:100]}...")
            print(f"✓ Has embedding: {first_item.get('embedding') is not None}")
            
            # Check embedding type
            if first_item.get('embedding'):
                emb = first_item.get('embedding')
                if isinstance(emb, list):
                    print(f"✓ Embedding type: list")
                    print(f"✓ Embedding dimensions: {len(emb)}")
                elif isinstance(emb, str):
                    print(f"⚠️  Embedding type: string (needs conversion)")
                else:
                    print(f"⚠️  Embedding type: {type(emb)}")
    except Exception as e:
        print(f"✗ Error checking knowledge table: {e}")
        return
    
    # 2. Test keyword search
    print("\n2. Testing keyword search...")
    test_queries = ["เพลี้ยไฟ", "ราน้ำค้าง", "หนอน", "โรคพืช"]
    
    for query in test_queries:
        try:
            result = supabase.table('knowledge')\
                .select('content')\
                .ilike('content', f'%{query}%')\
                .limit(2)\
                .execute()
            
            print(f"\nQuery: '{query}'")
            print(f"  Results: {len(result.data)} entries")
            
            if result.data:
                for i, item in enumerate(result.data, 1):
                    content = item.get('content', '')
                    preview = content[:80] + "..." if len(content) > 80 else content
                    print(f"  {i}. {preview}")
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    # 3. Test vector search
    print("\n3. Testing vector search...")
    try:
        query = "เพลี้ยไฟ อาการ การป้องกัน วิธีกำจัด"
        
        # Generate embedding
        response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=query
        )
        query_embedding = response.data[0].embedding
        print(f"✓ Generated embedding for: {query}")
        print(f"✓ Embedding dimensions: {len(query_embedding)}")
        
        # Test RPC function
        result = supabase.rpc(
            'match_knowledge',
            {
                'query_embedding': query_embedding,
                'match_threshold': 0.5,
                'match_count': 3
            }
        ).execute()
        
        print(f"✓ Vector search results: {len(result.data)} entries")
        
        if result.data:
            for i, item in enumerate(result.data, 1):
                content = item.get('content', '')
                similarity = item.get('similarity', 0)
                preview = content[:100] + "..." if len(content) > 100 else content
                print(f"  {i}. [{similarity:.2%}] {preview}")
        else:
            print("  ⚠️  No results found")
            print("  Possible reasons:")
            print("  - Embeddings are NULL")
            print("  - Embeddings are wrong type (string instead of vector)")
            print("  - Threshold too high")
            print("  - RPC function not created")
            
    except Exception as e:
        print(f"✗ Vector search error: {e}")
        print("  Note: Run scripts/setup_knowledge_search.sql first")
    
    # 4. Test different thresholds
    print("\n4. Testing different similarity thresholds...")
    try:
        query = "โรคพืช"
        response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=query
        )
        query_embedding = response.data[0].embedding
        
        thresholds = [0.0, 0.3, 0.5, 0.7]
        for threshold in thresholds:
            result = supabase.rpc(
                'match_knowledge',
                {
                    'query_embedding': query_embedding,
                    'match_threshold': threshold,
                    'match_count': 5
                }
            ).execute()
            
            print(f"  Threshold {threshold}: {len(result.data)} results")
            
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_knowledge_search()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
