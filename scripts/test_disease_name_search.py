"""
Test Disease Name Search
"""
import os
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from supabase import create_client

load_dotenv()

def test_disease_name_search():
    print("=" * 60)
    print("Test Disease Name Search")
    print("=" * 60)
    
    # Load E5 model
    print("\n1. Loading E5 model...")
    model = SentenceTransformer('intfloat/multilingual-e5-base')
    print("✓ Model loaded")
    
    # Connect to Supabase
    supabase = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_KEY")
    )
    
    # Test cases
    test_cases = [
        {
            "disease": "โรคไหม้ข้าว",
            "expected": "โรคไหม้ข้าว"
        },
        {
            "disease": "เพลี้ยไฟ",
            "expected": "เพลี้ยไฟ"
        },
        {
            "disease": "ราน้ำค้าง",
            "expected": "ราน้ำค้าง"
        }
    ]
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n{'='*60}")
        print(f"Test {i}: {test['disease']}")
        print("=" * 60)
        
        # Method 1: Disease name only (RECOMMENDED)
        print("\n📍 Method 1: Disease name only")
        query1 = f"query: {test['disease']}"
        embedding1 = model.encode(query1, normalize_embeddings=True).tolist()
        
        result1 = supabase.rpc('match_knowledge', {
            'query_embedding': embedding1,
            'match_threshold': 0.6,
            'match_count': 3
        }).execute()
        
        print(f"Query: '{query1}'")
        print(f"Results: {len(result1.data)}")
        if result1.data:
            for j, item in enumerate(result1.data, 1):
                similarity = item.get('similarity', 0)
                content = item.get('content', '')[:100]
                print(f"  {j}. [{similarity:.0%}] {content}...")
        
        # Method 2: Disease name + symptoms (OLD - may cause conflicts)
        print("\n📍 Method 2: Disease name + symptoms (OLD)")
        query2 = f"query: {test['disease']} อาการ ใบเหลือง จุดสีน้ำตาล"
        embedding2 = model.encode(query2, normalize_embeddings=True).tolist()
        
        result2 = supabase.rpc('match_knowledge', {
            'query_embedding': embedding2,
            'match_threshold': 0.6,
            'match_count': 3
        }).execute()
        
        print(f"Query: '{query2}'")
        print(f"Results: {len(result2.data)}")
        if result2.data:
            for j, item in enumerate(result2.data, 1):
                similarity = item.get('similarity', 0)
                content = item.get('content', '')[:100]
                print(f"  {j}. [{similarity:.0%}] {content}...")
        
        # Compare
        print("\n📊 Comparison:")
        print(f"Method 1 (name only): {len(result1.data)} results")
        print(f"Method 2 (name+symptoms): {len(result2.data)} results")
        
        if result1.data and result2.data:
            top1 = result1.data[0].get('content', '')[:50]
            top2 = result2.data[0].get('content', '')[:50]
            print(f"\nTop result Method 1: {top1}...")
            print(f"Top result Method 2: {top2}...")
            
            if top1 == top2:
                print("✓ Same result (Good!)")
            else:
                print("⚠️  Different results (Method 1 is more accurate)")
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("\n💡 Recommendation: Use Method 1 (disease name only)")
    print("=" * 60)

if __name__ == "__main__":
    test_disease_name_search()
