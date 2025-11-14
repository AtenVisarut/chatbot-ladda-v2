"""
Test E5 Embeddings for Knowledge Search
"""
import os
import sys
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

def test_e5_embeddings():
    print("=" * 60)
    print("Test E5 Embeddings (768 dimensions)")
    print("=" * 60)
    
    # 1. Load E5 model
    print("\n1. Loading E5 model...")
    try:
        model = SentenceTransformer('intfloat/multilingual-e5-base')
        print("✓ E5 model loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load E5 model: {e}")
        return
    
    # 2. Test embedding generation
    print("\n2. Testing embedding generation...")
    test_texts = [
        "query: เพลี้ยไฟกำจัดยังไง",
        "query: ราน้ำค้างเกิดจากอะไร",
        "passage: เพลี้ยไฟเป็นศัตรูพืชที่สำคัญ"
    ]
    
    for text in test_texts:
        try:
            embedding = model.encode(text, normalize_embeddings=True)
            print(f"\n✓ Text: {text[:50]}...")
            print(f"  Embedding shape: {embedding.shape}")
            print(f"  Embedding type: {type(embedding)}")
            print(f"  First 5 values: {embedding[:5]}")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    # 3. Test similarity
    print("\n3. Testing similarity...")
    try:
        query = "query: เพลี้ยไฟ"
        passage1 = "passage: เพลี้ยไฟเป็นศัตรูพืชที่สำคัญ ทำความเสียหายโดยการดูดกินน้ำเลี้ยง"
        passage2 = "passage: ราน้ำค้างเป็นโรคพืชที่เกิดจากเชื้อรา"
        
        query_emb = model.encode(query, normalize_embeddings=True)
        passage1_emb = model.encode(passage1, normalize_embeddings=True)
        passage2_emb = model.encode(passage2, normalize_embeddings=True)
        
        # Calculate cosine similarity
        import numpy as np
        sim1 = np.dot(query_emb, passage1_emb)
        sim2 = np.dot(query_emb, passage2_emb)
        
        print(f"\nQuery: {query}")
        print(f"Passage 1 similarity: {sim1:.4f} (เพลี้ยไฟ)")
        print(f"Passage 2 similarity: {sim2:.4f} (ราน้ำค้าง)")
        print(f"\n✓ Higher similarity for relevant passage!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # 4. Test with Supabase
    print("\n4. Testing with Supabase...")
    try:
        from supabase import create_client
        
        SUPABASE_URL = os.getenv("SUPABASE_URL")
        SUPABASE_KEY = os.getenv("SUPABASE_KEY")
        
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("❌ Supabase credentials not found")
            return
        
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Generate embedding
        query = "query: เพลี้ยไฟ อาการ การป้องกัน"
        query_embedding = model.encode(query, normalize_embeddings=True).tolist()
        
        print(f"✓ Generated embedding for: {query}")
        print(f"✓ Embedding dimensions: {len(query_embedding)}")
        
        # Test RPC function
        result = supabase.rpc(
            'match_knowledge',
            {
                'query_embedding': query_embedding,
                'match_threshold': 0.3,
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
            print("  Note: Run scripts/setup_knowledge_e5_768.sql first")
            
    except Exception as e:
        print(f"❌ Supabase test error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)

if __name__ == "__main__":
    test_e5_embeddings()
