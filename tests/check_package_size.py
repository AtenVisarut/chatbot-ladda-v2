"""Check package_size for all products — especially นาแดน 6 จี and อาร์เทมิส"""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client

sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

res = sb.table('products').select('id, product_name, package_size').execute()

print(f"Total products: {len(res.data)}\n")
print(f"{'ID':>4} | {'Product':<28} | {'package_size'}")
print("-" * 90)

null_count = 0
for r in sorted(res.data, key=lambda x: x['id']):
    pkg = r.get('package_size')
    if not pkg:
        null_count += 1
        pkg_display = "*** NULL ***"
    else:
        pkg_display = pkg[:60]
    print(f"{r['id']:>4} | {r['product_name']:<28} | {pkg_display}")

print(f"\nNull package_size: {null_count}/{len(res.data)}")
