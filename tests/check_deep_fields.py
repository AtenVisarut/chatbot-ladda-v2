"""Check action_characteristics for ทูโฟฟอส and target_pest for อาร์เทมีส"""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client

sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# Check ทูโฟฟอส
print("=" * 70)
print("ทูโฟฟอส — action_characteristics")
print("=" * 70)
res = sb.table('products').select('id, product_name, action_characteristics, how_to_use, target_pest, applicable_crops').ilike('product_name', '%ทูโฟฟอส%').execute()
for r in res.data:
    print(f"ID: {r['id']}")
    print(f"Name: {r['product_name']}")
    print(f"action_characteristics:\n  {r.get('action_characteristics', '-')}")
    print(f"how_to_use:\n  {r.get('how_to_use', '-')}")
    print(f"target_pest:\n  {r.get('target_pest', '-')}")
    print(f"applicable_crops:\n  {r.get('applicable_crops', '-')}")

# Check อาร์เทมีส
print("\n" + "=" * 70)
print("อาร์เทมีส — target_pest (ฟิวซาเรียม)")
print("=" * 70)
res2 = sb.table('products').select('id, product_name, target_pest').ilike('product_name', '%อาร์เทมีส%').execute()
for r in res2.data:
    print(f"ID: {r['id']}")
    print(f"Name: {r['product_name']}")
    print(f"target_pest:\n  {r.get('target_pest', '-')}")
    has_fusarium = 'ฟิวซาเรียม' in (r.get('target_pest') or '')
    print(f"Contains ฟิวซาเรียม: {has_fusarium}")
