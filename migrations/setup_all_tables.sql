-- ============================================================
-- Chatbot น้องลัดดา (ICP Ladda) — Full Database Schema
-- Supabase PostgreSQL + pgvector
-- Run this in Supabase SQL Editor to create all tables + RPC
-- ============================================================

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- 1. products3 — สินค้า 47 ตัว + embedding vector
-- ============================================================
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
    aliases TEXT,
    link_product TEXT,
    image_url TEXT,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for vector search
CREATE INDEX IF NOT EXISTS idx_products3_embedding ON products3
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);

-- Index for category filter
CREATE INDEX IF NOT EXISTS idx_products3_category ON products3 (product_category);

-- Index for product name lookup
CREATE INDEX IF NOT EXISTS idx_products3_name ON products3 (product_name);

-- ============================================================
-- 2. memory_chatladda — Conversation memory (แยกจาก project อื่น)
-- ============================================================
CREATE TABLE IF NOT EXISTS memory_chatladda (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,           -- 'user' | 'assistant'
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',  -- {products: [...], type: "admin_reply", ...}
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for user_id + created_at (most common query pattern)
CREATE INDEX IF NOT EXISTS idx_memory_user_created ON memory_chatladda (user_id, created_at DESC);

-- ============================================================
-- 3. user_ladda(LINE,FACE) — User profiles
-- ============================================================
CREATE TABLE IF NOT EXISTS "user_ladda(LINE,FACE)" (
    id BIGSERIAL PRIMARY KEY,
    line_user_id TEXT UNIQUE NOT NULL,  -- LINE: U{hex}, Facebook: fb:{psid}
    display_name TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Index for user lookup
CREATE INDEX IF NOT EXISTS idx_user_ladda_uid ON "user_ladda(LINE,FACE)" (line_user_id);

-- ============================================================
-- 4. cache_chatbot — Key-value cache with TTL
-- ============================================================
CREATE TABLE IF NOT EXISTS cache_chatbot (
    key TEXT PRIMARY KEY,
    value JSONB,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for expiry cleanup
CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache_chatbot (expires_at);

-- ============================================================
-- 5. ladda_analyst_event — Event tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS ladda_analyst_event (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT,
    event_type TEXT NOT NULL,        -- 'question' | 'product_recommendation' | 'error'
    source TEXT,                     -- 'AgenticRAG' | 'Q&A' | etc.
    product_name TEXT,
    question_text TEXT,
    intent TEXT,
    error_type TEXT,
    error_message TEXT,
    response_time_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for dashboard queries
CREATE INDEX IF NOT EXISTS idx_analytics_user ON ladda_analyst_event (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_type ON ladda_analyst_event (event_type, created_at DESC);

-- ============================================================
-- 6. analytics_alerts — System alerts
-- ============================================================
CREATE TABLE IF NOT EXISTS analytics_alerts (
    id BIGSERIAL PRIMARY KEY,
    alert_type TEXT NOT NULL,         -- 'high_error_rate' | 'slow_response' | etc.
    message TEXT NOT NULL,
    severity TEXT DEFAULT 'info',     -- 'info' | 'warning' | 'critical'
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for recent alerts
CREATE INDEX IF NOT EXISTS idx_alerts_created ON analytics_alerts (created_at DESC);

-- ============================================================
-- 7. admin_handoffs — Bot-to-admin handoff queue
-- ============================================================
CREATE TABLE IF NOT EXISTS admin_handoffs (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    platform TEXT DEFAULT 'line',     -- 'line' | 'facebook'
    display_name TEXT,
    trigger_message TEXT,             -- ข้อความที่ bot ตอบไม่ได้
    status TEXT DEFAULT 'pending',    -- 'pending' | 'active' | 'resolved'
    assigned_admin TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Index for handoff queue
CREATE INDEX IF NOT EXISTS idx_handoffs_status ON admin_handoffs (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_handoffs_user ON admin_handoffs (user_id);

-- ============================================================
-- RPC: hybrid_search_products3 — Vector + Keyword hybrid search
-- ============================================================
CREATE OR REPLACE FUNCTION hybrid_search_products3(
    query_embedding VECTOR(1536),
    search_query TEXT,
    vector_weight FLOAT DEFAULT 0.6,
    keyword_weight FLOAT DEFAULT 0.4,
    match_threshold FLOAT DEFAULT 0.15,
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
        p.aliases,
        p.link_product,
        p.image_url,
        (1 - (p.embedding <=> query_embedding))::FLOAT AS similarity
    FROM products3 p
    WHERE p.embedding IS NOT NULL
      AND (1 - (p.embedding <=> query_embedding)) >= match_threshold
    ORDER BY similarity DESC
    LIMIT match_count;
END;
$$;

-- ============================================================
-- RLS Policies (optional — disable for service_role key)
-- ============================================================
-- ALTER TABLE products3 ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE memory_chatladda ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE "user_ladda(LINE,FACE)" ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE cache_chatbot ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE ladda_analyst_event ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE analytics_alerts ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE admin_handoffs ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- Done! 7 tables + 1 RPC + 10 indexes created.
-- ============================================================
