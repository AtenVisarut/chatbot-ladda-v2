"""Check package_size, absorption_method, mechanism_of_action in DB"""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client

sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# Check all products
res = sb.table('products').select('id, product_name, package_size, absorption_method, mechanism_of_action').execute()

print(f"Total products: {len(res.data)}\n")
print(f"{'ID':>4} {'Product':<20} {'package_size':<30} {'absorption':<25} {'mechanism':<30}")
print("-" * 120)
for r in res.data:
    name = (r.get('product_name') or '')[:18]
    pkg = (r.get('package_size') or '-')[:28]
    absorb = (r.get('absorption_method') or '-')[:23]
    mech = (r.get('mechanism_of_action') or '-')[:28]
    print(f"{r['id']:>4} {name:<20} {pkg:<30} {absorb:<25} {mech:<30}")

# Count non-null
pkg_count = sum(1 for r in res.data if r.get('package_size'))
abs_count = sum(1 for r in res.data if r.get('absorption_method'))
mech_count = sum(1 for r in res.data if r.get('mechanism_of_action'))
print(f"\nNon-null counts: package_size={pkg_count}, absorption={abs_count}, mechanism={mech_count}")
