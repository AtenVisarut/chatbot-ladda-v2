-- =============================================
-- Alter products2 — add backward-compatible columns
-- Run in Supabase SQL Editor
-- =============================================

-- 1. Add missing columns
ALTER TABLE products2 ADD COLUMN IF NOT EXISTS aliases TEXT;
ALTER TABLE products2 ADD COLUMN IF NOT EXISTS link_product TEXT;
ALTER TABLE products2 ADD COLUMN IF NOT EXISTS image_url TEXT;
ALTER TABLE products2 ADD COLUMN IF NOT EXISTS pathogen_type TEXT;

-- 2. (target_pest removed — code now reads 5 separate columns directly:
--     fungicides, insecticides, herbicides, biostimulant, pgr_hormones)

-- 3. Copy aliases, link_product and image_url from old products table
UPDATE products2 p2
SET aliases = p1.aliases,
    link_product = p1.link_product,
    image_url = p1.image_url
FROM products p1
WHERE p2.product_name = p1.product_name;

-- 4. Drop old function first (return type changed — cannot CREATE OR REPLACE)
DROP FUNCTION IF EXISTS hybrid_search_products2(vector, text, double precision, double precision, integer);

-- 5. Recreate hybrid_search_products2 RPC with updated columns
CREATE OR REPLACE FUNCTION hybrid_search_products2(
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
        p.strategy,
        p.aliases,
        p.link_product,
        p.image_url,
        p.pathogen_type,
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
