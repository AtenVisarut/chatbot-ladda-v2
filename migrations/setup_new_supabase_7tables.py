"""
Setup 7 tables + RPC for Chatbot Ladda in NEW Supabase project.
Then migrate products3 data from OLD project.

Tables: products3, memory_chatladda, admin_handoffs,
        user_ladda(LINE,FACE), cache, analytics_events, analytics_alerts

Usage:
    python migrations/setup_new_supabase_7tables.py
"""
import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
load_dotenv()

# OLD Supabase (source — current .env)
OLD_URL = os.getenv("SUPABASE_URL")
OLD_KEY = os.getenv("SUPABASE_KEY")

# NEW Supabase (target)
NEW_URL = "https://nvtdtyrwvfuvldccpprc.supabase.co"
NEW_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im52dGR0eXJ3dmZ1dmxkY2NwcHJjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDIzMzM3MSwiZXhwIjoyMDg5ODA5MzcxfQ.BlHfKevI41NFv-cgGdTsMvfq4VfCQIkx23opJorEZOc"

SQL_TABLES = """
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. products3
CREATE TABLE IF NOT EXISTS products3 (
    id BIGSERIAL PRIMARY KEY,
    product_name TEXT NOT NULL,
    common_name_th TEXT,
    active_ingredient TEXT,
    fungicides TEXT,
    insecticides TEXT,
    herbicides TEXT,
    biostimulant TEXT,
    pgr_hormones TEXT,
    applicable_crops TEXT,
    how_to_use TEXT,
    usage_period TEXT,
    usage_rate TEXT,
    product_category TEXT,
    package_size TEXT,
    physical_form TEXT,
    selling_point TEXT,
    absorption_method TEXT,
    mechanism_of_action TEXT,
    action_characteristics TEXT,
    phytotoxicity TEXT,
    strategy TEXT,
    chemical_group_rac TEXT,
    caution_notes TEXT,
    product_group TEXT,
    aliases TEXT,
    link_product TEXT,
    image_url TEXT,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_products3_name ON products3 (product_name);
CREATE INDEX IF NOT EXISTS idx_products3_category ON products3 (product_category);

-- 2. memory_chatladda
CREATE TABLE IF NOT EXISTS memory_chatladda (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_memory_chatladda_user_created ON memory_chatladda (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_chatladda_created ON memory_chatladda (created_at DESC);

-- 3. admin_handoffs
CREATE TABLE IF NOT EXISTS admin_handoffs (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'line',
    display_name TEXT,
    trigger_message TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'resolved')),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_admin_handoffs_user ON admin_handoffs (user_id);
CREATE INDEX IF NOT EXISTS idx_admin_handoffs_status ON admin_handoffs (status);

-- 4. user_ladda(LINE,FACE)
CREATE TABLE IF NOT EXISTS "user_ladda(LINE,FACE)" (
    id BIGSERIAL PRIMARY KEY,
    line_user_id TEXT UNIQUE NOT NULL,
    display_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_user_ladda_line_user_id ON "user_ladda(LINE,FACE)" (line_user_id);

-- 5. cache
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value JSONB,
    expires_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache (expires_at);

-- 6. analytics_events
CREATE TABLE IF NOT EXISTS analytics_events (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT,
    event_type TEXT NOT NULL,
    disease_name TEXT,
    pest_type TEXT,
    confidence TEXT,
    severity TEXT,
    product_name TEXT,
    question_text TEXT,
    intent TEXT,
    error_type TEXT,
    error_message TEXT,
    stack_trace TEXT,
    response_time_ms FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_analytics_events_type ON analytics_events (event_type);
CREATE INDEX IF NOT EXISTS idx_analytics_events_created ON analytics_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_events_user ON analytics_events (user_id);

-- 7. analytics_alerts
CREATE TABLE IF NOT EXISTS analytics_alerts (
    id BIGSERIAL PRIMARY KEY,
    alert_type TEXT NOT NULL,
    message TEXT,
    severity TEXT DEFAULT 'warning',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_analytics_alerts_created ON analytics_alerts (created_at DESC);

-- RLS + Policies
ALTER TABLE products3 ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_chatladda ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_handoffs ENABLE ROW LEVEL SECURITY;
ALTER TABLE "user_ladda(LINE,FACE)" ENABLE ROW LEVEL SECURITY;
ALTER TABLE cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_alerts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all" ON products3 FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON memory_chatladda FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON admin_handoffs FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON "user_ladda(LINE,FACE)" FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON cache FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON analytics_events FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON analytics_alerts FOR ALL USING (true) WITH CHECK (true);
"""

SQL_RPC = """
CREATE OR REPLACE FUNCTION hybrid_search_products3(
    query_embedding vector(1536),
    query_text TEXT DEFAULT '',
    match_threshold FLOAT DEFAULT 0.3,
    match_count INT DEFAULT 10
)
RETURNS TABLE (
    id BIGINT, product_name TEXT, common_name_th TEXT, active_ingredient TEXT,
    fungicides TEXT, insecticides TEXT, herbicides TEXT, biostimulant TEXT,
    pgr_hormones TEXT, applicable_crops TEXT, how_to_use TEXT, usage_period TEXT,
    usage_rate TEXT, product_category TEXT, package_size TEXT, physical_form TEXT,
    selling_point TEXT, absorption_method TEXT, mechanism_of_action TEXT,
    action_characteristics TEXT, phytotoxicity TEXT, strategy TEXT,
    chemical_group_rac TEXT, caution_notes TEXT, product_group TEXT,
    aliases TEXT, link_product TEXT, image_url TEXT, similarity FLOAT
)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT p.id, p.product_name, p.common_name_th, p.active_ingredient,
        p.fungicides, p.insecticides, p.herbicides, p.biostimulant,
        p.pgr_hormones, p.applicable_crops, p.how_to_use, p.usage_period,
        p.usage_rate, p.product_category, p.package_size, p.physical_form,
        p.selling_point, p.absorption_method, p.mechanism_of_action,
        p.action_characteristics, p.phytotoxicity, p.strategy,
        p.chemical_group_rac, p.caution_notes, p.product_group,
        p.aliases, p.link_product, p.image_url,
        1 - (p.embedding <=> query_embedding) AS similarity
    FROM products3 p
    WHERE p.embedding IS NOT NULL
      AND 1 - (p.embedding <=> query_embedding) > match_threshold
    ORDER BY similarity DESC
    LIMIT match_count;
END; $$;
"""


def migrate_products(old_sb: Client, new_sb: Client):
    """โอน products3 จาก project เก่า → ใหม่"""
    print("\nMigrating products3...")
    result = old_sb.table("products3").select("*").execute()
    products = result.data
    if not products:
        print("  No products in old project!")
        return

    print(f"  Found {len(products)} products in old project")

    existing = new_sb.table("products3").select("id").limit(1).execute()
    if existing.data:
        print("  WARNING: New project already has data — skipping to prevent duplicates")
        return

    success = 0
    for i, p in enumerate(products, 1):
        try:
            data = {k: v for k, v in p.items() if k != 'id'}
            new_sb.table("products3").insert(data).execute()
            print(f"  [{i}/{len(products)}] {p['product_name']}")
            success += 1
        except Exception as e:
            print(f"  [{i}/{len(products)}] ERROR: {p.get('product_name','?')} — {e}")

    print(f"  Done: {success}/{len(products)} migrated")


def main():
    print("=" * 60)
    print("Setup NEW Supabase — 7 Tables for Chatbot Ladda")
    print("=" * 60)

    if not OLD_URL or not OLD_KEY:
        print("ERROR: SUPABASE_URL / SUPABASE_KEY not set in .env")
        sys.exit(1)

    print(f"\nOLD: {OLD_URL}")
    print(f"NEW: {NEW_URL}")

    print("\n" + "=" * 60)
    print("STEP 1: Run this SQL in NEW Supabase > SQL Editor (Tables):")
    print("=" * 60)
    print(SQL_TABLES)

    print("\n" + "=" * 60)
    print("STEP 2: Run this SQL in NEW Supabase > SQL Editor (RPC):")
    print("=" * 60)
    print(SQL_RPC)

    input("\nPress Enter AFTER running both SQL scripts...")

    old_sb = create_client(OLD_URL, OLD_KEY)
    new_sb = create_client(NEW_URL, NEW_KEY)

    # Verify tables
    print("\nVerifying tables...")
    tables = [
        "products3", "memory_chatladda", "admin_handoffs",
        "user_ladda(LINE,FACE)", "cache", "analytics_events", "analytics_alerts"
    ]
    all_ok = True
    for t in tables:
        try:
            new_sb.table(t).select("id").limit(1).execute()
            print(f"  [OK] {t}")
        except Exception as e:
            print(f"  [FAIL] {t}")
            all_ok = False

    if not all_ok:
        print("\nSome tables missing! Run SQL first.")
        sys.exit(1)

    # Migrate products
    migrate_products(old_sb, new_sb)

    print("\n" + "=" * 60)
    print("DONE! Update env vars:")
    print("=" * 60)
    print(f"SUPABASE_URL={NEW_URL}")
    print(f"SUPABASE_KEY={NEW_KEY}")
    print(f"MEMORY_TABLE=memory_chatladda")


if __name__ == "__main__":
    main()
