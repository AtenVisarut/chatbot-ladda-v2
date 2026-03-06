-- =============================================
-- products2 table — structured from ICP_product CSV
-- Run this in Supabase SQL Editor
-- =============================================

-- Enable pgvector extension (if not already)
CREATE EXTENSION IF NOT EXISTS vector;

-- Drop and recreate (CAUTION: destroys existing data)
DROP TABLE IF EXISTS products2;

CREATE TABLE products2 (
    id              BIGSERIAL PRIMARY KEY,
    product_name    TEXT NOT NULL,
    common_name_th  TEXT,
    active_ingredient TEXT,
    chemical_group_rac TEXT,       -- กลุ่มสารเคมี กลุ่ม 1-29 ตาม RAC
    herbicides      TEXT,          -- วัชพืชที่กำจัดได้
    fungicides      TEXT,          -- โรคที่กำจัดได้
    insecticides    TEXT,          -- แมลงที่กำจัดได้
    biostimulant    TEXT,          -- Plant Biostimulant
    pgr_hormones    TEXT,          -- PGR/Hormones
    applicable_crops TEXT,
    how_to_use      TEXT,
    usage_period    TEXT,
    usage_rate      TEXT,
    product_category TEXT,         -- Insecticide / Herbicide / Fungicide / PGR / Biostimulants
    package_size    TEXT,
    physical_form   TEXT,
    selling_point   TEXT,
    absorption_method TEXT,
    mechanism_of_action TEXT,
    action_characteristics TEXT,
    phytotoxicity   TEXT,
    strategy        TEXT,          -- Expand / Natural / Skyrocket / Standard
    embedding       vector(1536),  -- text-embedding-3-small
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Index for vector similarity search
CREATE INDEX idx_products2_embedding ON products2
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);

-- Index for full-text search
ALTER TABLE products2 ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        to_tsvector('simple',
            COALESCE(product_name, '') || ' ' ||
            COALESCE(common_name_th, '') || ' ' ||
            COALESCE(active_ingredient, '') || ' ' ||
            COALESCE(herbicides, '') || ' ' ||
            COALESCE(fungicides, '') || ' ' ||
            COALESCE(insecticides, '') || ' ' ||
            COALESCE(applicable_crops, '') || ' ' ||
            COALESCE(selling_point, '') || ' ' ||
            COALESCE(product_category, '') || ' ' ||
            COALESCE(strategy, '')
        )
    ) STORED;

CREATE INDEX idx_products2_search ON products2 USING GIN (search_vector);

-- Unique constraint on product name
CREATE UNIQUE INDEX idx_products2_name ON products2 (product_name);

-- RPC function for hybrid search on products2
CREATE OR REPLACE FUNCTION hybrid_search_products2(
    query_embedding vector(1536),
    search_query    TEXT,
    vector_weight   FLOAT DEFAULT 0.6,
    keyword_weight  FLOAT DEFAULT 0.4,
    match_count     INT DEFAULT 20
)
RETURNS TABLE (
    id                  BIGINT,
    product_name        TEXT,
    common_name_th      TEXT,
    active_ingredient   TEXT,
    chemical_group_rac  TEXT,
    herbicides          TEXT,
    fungicides          TEXT,
    insecticides        TEXT,
    biostimulant        TEXT,
    pgr_hormones        TEXT,
    applicable_crops    TEXT,
    how_to_use          TEXT,
    usage_period        TEXT,
    usage_rate          TEXT,
    product_category    TEXT,
    package_size        TEXT,
    physical_form       TEXT,
    selling_point       TEXT,
    absorption_method   TEXT,
    mechanism_of_action TEXT,
    action_characteristics TEXT,
    phytotoxicity       TEXT,
    strategy            TEXT,
    similarity          FLOAT
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
        p.chemical_group_rac,
        p.herbicides,
        p.fungicides,
        p.insecticides,
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
        (
            vector_weight * (1 - (p.embedding <=> query_embedding)) +
            keyword_weight * COALESCE(ts_rank(p.search_vector, plainto_tsquery('simple', search_query)), 0)
        )::FLOAT AS similarity
    FROM products2 p
    WHERE p.embedding IS NOT NULL
    ORDER BY similarity DESC
    LIMIT match_count;
END;
$$;
