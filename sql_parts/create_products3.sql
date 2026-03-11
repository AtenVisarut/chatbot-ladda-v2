-- =============================================
-- products3 table — from ICP_product.xlsx
-- Run this in Supabase SQL Editor
-- =============================================

-- Enable pgvector extension (if not already)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS products3 (
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
    caution_notes   TEXT,          -- ข้อควรระวังเพิ่มเติม (NEW)
    strategy        TEXT,          -- Expand / Natural / Skyrocket / Standard
    embedding       vector(1536),  -- text-embedding-3-small
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Index for vector similarity search
CREATE INDEX IF NOT EXISTS idx_products3_embedding ON products3
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);

-- Index for full-text search
ALTER TABLE products3 ADD COLUMN IF NOT EXISTS search_vector tsvector
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
            COALESCE(strategy, '') || ' ' ||
            COALESCE(caution_notes, '')
        )
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_products3_search ON products3 USING GIN (search_vector);

-- Unique constraint on product name
CREATE UNIQUE INDEX IF NOT EXISTS idx_products3_name ON products3 (product_name);

-- RPC function for hybrid search on products3
CREATE OR REPLACE FUNCTION hybrid_search_products3(
    query_embedding vector(1536),
    search_query    TEXT,
    vector_weight   FLOAT DEFAULT 0.6,
    keyword_weight  FLOAT DEFAULT 0.4,
    match_count     INT DEFAULT 20
)
RETURNS TABLE (
    id                      BIGINT,
    product_name            TEXT,
    common_name_th          TEXT,
    active_ingredient       TEXT,
    chemical_group_rac      TEXT,
    herbicides              TEXT,
    fungicides              TEXT,
    insecticides            TEXT,
    biostimulant            TEXT,
    pgr_hormones            TEXT,
    applicable_crops        TEXT,
    how_to_use              TEXT,
    usage_period            TEXT,
    usage_rate              TEXT,
    product_category        TEXT,
    package_size            TEXT,
    physical_form           TEXT,
    selling_point           TEXT,
    absorption_method       TEXT,
    mechanism_of_action     TEXT,
    action_characteristics  TEXT,
    phytotoxicity           TEXT,
    caution_notes           TEXT,
    strategy                TEXT,
    aliases                 TEXT,
    link_product            TEXT,
    image_url               TEXT,
    pathogen_type           TEXT,
    similarity              FLOAT
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
        p.caution_notes,
        p.strategy,
        p.aliases,
        p.link_product,
        p.image_url,
        p.pathogen_type,
        (
            vector_weight * (1 - (p.embedding <=> query_embedding)) +
            keyword_weight * COALESCE(ts_rank(p.search_vector, plainto_tsquery('simple', search_query)), 0)
        )::FLOAT AS similarity
    FROM products3 p
    WHERE p.embedding IS NOT NULL
    ORDER BY similarity DESC
    LIMIT match_count;
END;
$$;

-- Compat columns (aliases, link_product, image_url from products2)
ALTER TABLE products3 ADD COLUMN IF NOT EXISTS aliases TEXT;
ALTER TABLE products3 ADD COLUMN IF NOT EXISTS link_product TEXT;
ALTER TABLE products3 ADD COLUMN IF NOT EXISTS image_url TEXT;
ALTER TABLE products3 ADD COLUMN IF NOT EXISTS pathogen_type TEXT;
