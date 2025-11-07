-- ============================================================================
-- Supabase Setup Script for Plant Products Database
-- ============================================================================

-- Enable pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Create products table
CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    product_name TEXT NOT NULL,
    active_ingredient TEXT,
    target_pest TEXT,
    applicable_crops TEXT,
    how_to_use TEXT,
    product_group TEXT,
    formulation TEXT,
    usage_rate TEXT,
    metadata JSONB,
    embedding vector(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index for vector similarity search
CREATE INDEX IF NOT EXISTS products_embedding_idx 
ON products USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Create index for product name search
CREATE INDEX IF NOT EXISTS products_name_idx ON products(product_name);

-- Create index for target pest search
CREATE INDEX IF NOT EXISTS products_pest_idx ON products(target_pest);

-- Create RPC function for vector similarity search
CREATE OR REPLACE FUNCTION match_products(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.3,
    match_count int DEFAULT 10
)
RETURNS TABLE (
    id bigint,
    product_name text,
    active_ingredient text,
    target_pest text,
    applicable_crops text,
    how_to_use text,
    metadata jsonb,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        products.id,
        products.product_name,
        products.active_ingredient,
        products.target_pest,
        products.applicable_crops,
        products.how_to_use,
        products.metadata,
        1 - (products.embedding <=> query_embedding) as similarity
    FROM products
    WHERE 1 - (products.embedding <=> query_embedding) > match_threshold
    ORDER BY products.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Grant permissions (adjust as needed)
-- ALTER TABLE products ENABLE ROW LEVEL SECURITY;
