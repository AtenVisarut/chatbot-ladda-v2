-- ============================================================
-- products_icp — สินค้า ICP Ladda (sync จาก Google Sheets)
-- มี row_hash สำหรับตรวจจับ row ที่เปลี่ยน
-- ============================================================

CREATE TABLE IF NOT EXISTS products_icp (
    id BIGSERIAL PRIMARY KEY,
    product_name TEXT NOT NULL UNIQUE,
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
    row_hash TEXT,                    -- MD5 hash สำหรับตรวจจับ row ที่เปลี่ยน
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_products_icp_embedding ON products_icp
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);
CREATE INDEX IF NOT EXISTS idx_products_icp_category ON products_icp (product_category);
CREATE INDEX IF NOT EXISTS idx_products_icp_name ON products_icp (product_name);

-- RPC: hybrid search สำหรับ products_icp
CREATE OR REPLACE FUNCTION hybrid_search_products_icp(
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
        p.id, p.product_name, p.common_name_th, p.active_ingredient,
        p.fungicides, p.insecticides, p.herbicides, p.biostimulant, p.pgr_hormones,
        p.applicable_crops, p.how_to_use, p.usage_period, p.usage_rate,
        p.product_category, p.package_size, p.physical_form, p.selling_point,
        p.absorption_method, p.mechanism_of_action, p.action_characteristics,
        p.phytotoxicity, p.strategy, p.chemical_group_rac, p.caution_notes,
        p.aliases, p.link_product, p.image_url,
        (1 - (p.embedding <=> query_embedding))::FLOAT AS similarity
    FROM products_icp p
    WHERE p.embedding IS NOT NULL
      AND (1 - (p.embedding <=> query_embedding)) >= match_threshold
    ORDER BY similarity DESC
    LIMIT match_count;
END;
$$;
