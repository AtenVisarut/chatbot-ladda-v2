"""
Test Document Knowledge Base Search
"""
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def test_document_search():
    print("=" * 60)
    print("Test Document Knowledge Base Search")
    print("=" * 60)
    
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # 1. Check documents
    print("\n1. Checking documents table...")
    try:
        result = supabase.table('documents').select('*').limit(5).execute()
        print(f"✓ Total documents: {len(result.data)}")
        
        if result.data:
            first_doc = result.data[0]
            print(f"✓ First document ID: {first_doc.get('id')}")
            content = first_doc.get('content', '')
            print(f"✓ Content preview: {content[:100]}...")
            print(f"✓ Has embedding: {first_doc.get('embedding') is not None}")
    except Exception as e:
        print(f"✗ Error checking documents: {e}")
        return
    
    # 2. Test keyword search
    print("\n2. Testing keyword search...")
    test_queries = ["เพลี้ยไฟ", "ราน้ำค้าง", "หนอน", "โรคพืช"]
    
    for query in test_queries:
        try:
            result = supabase.table('documents')\
                .select('content')\
                .ilike('content', f'%{query}%')\
                .limit(3)\
                .execute()
            
            print(f"\nQuery: '{query}'")
            print(f"  Results: {len(result.data)} documents")
            
            if result.data:
                for i, doc in enumerate(result.data[:2], 1):
                    content = doc.get('content', '')
                    preview = content[:80] + "..." if len(content) > 80 else content
                    print(f"  {i}. {preview}")
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    # 3. Test vector search (if RPC function exists)
    print("\n3. Testing vector search...")
    try:
        query = "เพลี้ยไฟ อาการ การป้องกัน"
        
        response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=query
        )
        query_embedding = response.data[0].embedding
        print(f"✓ Generated embedding for: {query}")
        
        result = supabase.rpc(
            'match_documents',
            {
                'query_embedding': query_embedding,
                'match_threshold': 0.5,
                'match_count': 3
            }
        ).execute()
        
        print(f"✓ Vector search results: {len(result.data)} documents")
        
        if result.data:
            for i, doc in enumerate(result.data, 1):
                content = doc.get('content', '')
                similarity = doc.get('similarity', 0)
                preview = content[:80] + "..." if len(content) > 80 else content
                print(f"  {i}. [{similarity:.2%}] {preview}")
        else:
            print("  ⚠️  No results found")
            
    except Exception as e:
        print(f"✗ Vector search error: {e}")
        print("  Note: Run scripts/setup_document_search.sql first")
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_document_search()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
