"""
Setup all tables + RPC functions for Chatbot Ladda in NEW Supabase project.
Migrates products3 data from OLD project.

Usage:
    python migrations/setup_new_supabase.py

Tables created:
  1. products3          — สินค้า + embedding (vector 1536)
  2. memory_chatladda   — conversation memory (แยกจากหมอพืช)
  3. user_ladda(LINE,FACE) — user profiles
  4. analytics_events   — analytics tracking
  5. analytics_alerts   — alert notifications
  6. admin_handoffs     — handoff to admin
  7. cache              — L2 cache (Supabase)
  8. knowledge          — knowledge base + embedding
  9. diseases           — disease database + embedding

RPC functions created:
  1. hybrid_search_products3  — vector + keyword search
  2. hybrid_search_diseases   — vector search diseases
  3. match_knowledge          — vector search knowledge
"""
import os
import sys
import time
import json
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

load_dotenv()

# --- OLD Supabase (source) ---
OLD_SUPABASE_URL = os.getenv("SUPABASE_URL")
OLD_SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# --- NEW Supabase (target) ---
NEW_SUPABASE_URL = "https://nvtdtyrwvfuvldccpprc.supabase.co"
NEW_SUPABASE_KEY = os.getenv("NEW_SUPABASE_KEY", "")  # service_role key — set via env var

# ============================================================================
# SQL: Create all tables
# ============================================================================

SQL_TABLES = """
-- ============================================================
-- 1. products3 — สินค้า ICP Ladda + vector embedding
-- ============================================================
CREATE EXTENSION IF NOT EXISTS vector;

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

-- ============================================================
-- 2. memory_chatladda — conversation memory
-- ============================================================
CREATE TABLE IF NOT EXISTS memory_chatladda (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memory_chatladda_user_created
    ON memory_chatladda (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_chatladda_created
    ON memory_chatladda (created_at DESC);

-- ============================================================
-- 3. user_ladda(LINE,FACE) — user profiles
-- ============================================================
CREATE TABLE IF NOT EXISTS "user_ladda(LINE,FACE)" (
    id BIGSERIAL PRIMARY KEY,
    line_user_id TEXT UNIQUE NOT NULL,
    display_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_ladda_line_user_id
    ON "user_ladda(LINE,FACE)" (line_user_id);

-- ============================================================
-- 4. analytics_events — event tracking
-- ============================================================
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

CREATE INDEX IF NOT EXISTS idx_analytics_events_type
    ON analytics_events (event_type);
CREATE INDEX IF NOT EXISTS idx_analytics_events_created
    ON analytics_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_events_user
    ON analytics_events (user_id);

-- ============================================================
-- 5. analytics_alerts — alert notifications
-- ============================================================
CREATE TABLE IF NOT EXISTS analytics_alerts (
    id BIGSERIAL PRIMARY KEY,
    alert_type TEXT NOT NULL,
    message TEXT,
    severity TEXT DEFAULT 'warning',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analytics_alerts_created
    ON analytics_alerts (created_at DESC);

-- ============================================================
-- 6. admin_handoffs — handoff to admin
-- ============================================================
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

CREATE INDEX IF NOT EXISTS idx_admin_handoffs_user
    ON admin_handoffs (user_id);
CREATE INDEX IF NOT EXISTS idx_admin_handoffs_status
    ON admin_handoffs (status);

-- ============================================================
-- 7. cache — L2 cache (Supabase)
-- ============================================================
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value JSONB,
    expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_cache_expires
    ON cache (expires_at);

-- ============================================================
-- 8. knowledge — knowledge base + embedding
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge (
    id BIGSERIAL PRIMARY KEY,
    title TEXT,
    content TEXT NOT NULL,
    category TEXT,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 9. diseases — disease database + embedding
-- ============================================================
CREATE TABLE IF NOT EXISTS diseases (
    id BIGSERIAL PRIMARY KEY,
    disease_name TEXT NOT NULL,
    disease_name_en TEXT,
    plant_type TEXT,
    symptoms TEXT,
    cause TEXT,
    prevention TEXT,
    treatment TEXT,
    severity TEXT,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_diseases_name ON diseases (disease_name);
CREATE INDEX IF NOT EXISTS idx_diseases_plant ON diseases (plant_type);

-- ============================================================
-- Enable RLS on all tables (allow all via service_role)
-- ============================================================
ALTER TABLE products3 ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_chatladda ENABLE ROW LEVEL SECURITY;
ALTER TABLE "user_ladda(LINE,FACE)" ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_handoffs ENABLE ROW LEVEL SECURITY;
ALTER TABLE cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge ENABLE ROW LEVEL SECURITY;
ALTER TABLE diseases ENABLE ROW LEVEL SECURITY;

-- Policies (allow all for service_role key)
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOR tbl IN
        SELECT unnest(ARRAY[
            'products3', 'memory_chatladda', 'user_ladda(LINE,FACE)',
            'analytics_events', 'analytics_alerts', 'admin_handoffs',
            'cache', 'knowledge', 'diseases'
        ])
    LOOP
        EXECUTE format(
            'CREATE POLICY IF NOT EXISTS "service_role_all" ON %I FOR ALL USING (true) WITH CHECK (true)',
            tbl
        );
    END LOOP;
END $$;
"""

# ============================================================================
# SQL: Create RPC functions
# ============================================================================

SQL_RPC = """
-- ============================================================
-- RPC 1: hybrid_search_products3
-- ============================================================
CREATE OR REPLACE FUNCTION hybrid_search_products3(
    query_embedding vector(1536),
    query_text TEXT DEFAULT '',
    match_threshold FLOAT DEFAULT 0.3,
    match_count INT DEFAULT 10
)
RETURNS TABLE (
    id BIGINT,
    product_name TEXT,
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
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        p.id,
        p.product_name,
        p.common_name_th,
        p.active_ingredient,
        p.fungicides,
        p.insecticides,
        p.herbicides,
        p.biostimulant,
        p.pgr_hormones,
        p.applicable_crops,
        p.how_to_use,
        p.usage_period,
        p.usage_rate,
        p.product_category,
        p.package_size,
        p.physical_form,
        p.selling_point,
        p.absorption_method,
        p.mechanism_of_action,
        p.action_characteristics,
        p.phytotoxicity,
        p.strategy,
        p.chemical_group_rac,
        p.caution_notes,
        p.product_group,
        p.aliases,
        p.link_product,
        p.image_url,
        1 - (p.embedding <=> query_embedding) AS similarity
    FROM products3 p
    WHERE p.embedding IS NOT NULL
      AND 1 - (p.embedding <=> query_embedding) > match_threshold
    ORDER BY similarity DESC
    LIMIT match_count;
END;
$$;

-- ============================================================
-- RPC 2: hybrid_search_diseases
-- ============================================================
CREATE OR REPLACE FUNCTION hybrid_search_diseases(
    query_embedding vector(1536),
    match_threshold FLOAT DEFAULT 0.3,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    id BIGINT,
    disease_name TEXT,
    disease_name_en TEXT,
    plant_type TEXT,
    symptoms TEXT,
    cause TEXT,
    prevention TEXT,
    treatment TEXT,
    severity TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id,
        d.disease_name,
        d.disease_name_en,
        d.plant_type,
        d.symptoms,
        d.cause,
        d.prevention,
        d.treatment,
        d.severity,
        1 - (d.embedding <=> query_embedding) AS similarity
    FROM diseases d
    WHERE d.embedding IS NOT NULL
      AND 1 - (d.embedding <=> query_embedding) > match_threshold
    ORDER BY similarity DESC
    LIMIT match_count;
END;
$$;

-- ============================================================
-- RPC 3: match_knowledge
-- ============================================================
CREATE OR REPLACE FUNCTION match_knowledge(
    query_embedding vector(1536),
    match_threshold FLOAT DEFAULT 0.35,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    id BIGINT,
    title TEXT,
    content TEXT,
    category TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        k.id,
        k.title,
        k.content,
        k.category,
        1 - (k.embedding <=> query_embedding) AS similarity
    FROM knowledge k
    WHERE k.embedding IS NOT NULL
      AND 1 - (k.embedding <=> query_embedding) > match_threshold
    ORDER BY similarity DESC
    LIMIT match_count;
END;
$$;
"""


def migrate_products(old_sb: Client, new_sb: Client):
    """โอนข้อมูล products3 จาก project เก่ามาใหม่"""
    print("\n3. Migrating products3 data from OLD project...")

    # Fetch all products from old project
    result = old_sb.table("products3").select("*").execute()
    products = result.data

    if not products:
        print("   No products found in old project!")
        return

    print(f"   Found {len(products)} products in old project")

    # Check if new project already has data
    existing = new_sb.table("products3").select("id").limit(1).execute()
    if existing.data:
        print(f"   WARNING: New project already has products3 data!")
        print(f"   Skipping migration to prevent duplicates.")
        print(f"   To re-migrate, delete all rows from products3 first.")
        return

    # Insert in batches
    success = 0
    errors = 0
    for i, product in enumerate(products, 1):
        try:
            # Remove 'id' to let Supabase auto-generate
            data = {k: v for k, v in product.items() if k != 'id'}
            new_sb.table("products3").insert(data).execute()
            print(f"   [{i}/{len(products)}] {product['product_name']}")
            success += 1
        except Exception as e:
            print(f"   [{i}/{len(products)}] ERROR: {product.get('product_name', '?')} — {e}")
            errors += 1

    print(f"   Done: {success} success, {errors} errors")


def main():
    print("=" * 60)
    print("Setup NEW Supabase Project for Chatbot Ladda")
    print("=" * 60)

    if not OLD_SUPABASE_URL or not OLD_SUPABASE_KEY:
        print("ERROR: Set SUPABASE_URL and SUPABASE_KEY in .env (old project)")
        sys.exit(1)

    old_sb = create_client(OLD_SUPABASE_URL, OLD_SUPABASE_KEY)
    new_sb = create_client(NEW_SUPABASE_URL, NEW_SUPABASE_KEY)

    # Step 1: Print SQL for manual execution
    print("\n1. CREATE TABLES — Run this SQL in NEW Supabase Dashboard > SQL Editor:")
    print("-" * 60)
    print(SQL_TABLES)
    print("-" * 60)

    print("\n2. CREATE RPC FUNCTIONS — Run this SQL in NEW Supabase Dashboard > SQL Editor:")
    print("-" * 60)
    print(SQL_RPC)
    print("-" * 60)

    # Step 2: Check if tables exist in new project
    input("\nPress Enter AFTER running both SQL scripts in Supabase Dashboard...")

    # Step 3: Verify tables
    print("\nVerifying tables in new project...")
    tables_to_check = [
        "products3", "memory_chatladda", "user_ladda(LINE,FACE)",
        "analytics_events", "analytics_alerts", "admin_handoffs",
        "cache", "knowledge", "diseases"
    ]

    all_ok = True
    for table in tables_to_check:
        try:
            new_sb.table(table).select("id").limit(1).execute()
            print(f"   [OK] {table}")
        except Exception as e:
            print(f"   [FAIL] {table} — {e}")
            all_ok = False

    if not all_ok:
        print("\nSome tables are missing! Please run the SQL scripts first.")
        sys.exit(1)

    # Step 4: Migrate products3 data
    migrate_products(old_sb, new_sb)

    # Step 5: Print env vars to update
    print("\n" + "=" * 60)
    print("DONE! Update these env vars in Railway / .env:")
    print("=" * 60)
    print(f"SUPABASE_URL={NEW_SUPABASE_URL}")
    print(f"SUPABASE_KEY={NEW_SUPABASE_KEY}")
    print(f"MEMORY_TABLE=memory_chatladda")
    print(f"PRODUCT_TABLE=products3")
    print(f"PRODUCT_RPC=hybrid_search_products3")
    print("=" * 60)


if __name__ == "__main__":
    main()
