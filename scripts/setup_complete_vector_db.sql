-- Complete Vector Database Setup for Supabase
-- Run this in Supabase SQL Editor

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Drop existing table if you want to start fresh (CAREFUL!)
-- DROP TABLE IF EXISTS products CASCADE;

-- 3. Create products table with vector support
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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Create indexes for faster search
CREATE INDEX IF NOT EXISTS idx_products_target_pest ON products(target_pest);
CREATE INDEX IF NOT EXISTS idx_products_name ON products(product_name);
CREATE INDEX IF NOT EXISTS idx_products_group ON products(product_group);

-- 5. Create vector index for similarity search
CREATE INDEX IF NOT EXISTS idx_products_embedding ON products 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- 6. Create RPC function for vector similarity search
CREATE OR REPLACE FUNCTION match_products(
  query_embedding vector(1536),
  match_threshold float DEFAULT 0.5,
  match_count int DEFAULT 10
)
RETURNS TABLE (
  id bigint,
  product_name text,
  active_ingredient text,
  target_pest text,
  applicable_crops text,
  how_to_use text,
  product_group text,
  formulation text,
  usage_rate text,
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
    products.product_group,
    products.formulation,
    products.usage_rate,
    1 - (products.embedding <=> query_embedding) AS similarity
  FROM products
  WHERE products.embedding IS NOT NULL
    AND 1 - (products.embedding <=> query_embedding) > match_threshold
  ORDER BY products.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- 7. Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 8. Create trigger to auto-update updated_at
DROP TRIGGER IF EXISTS update_products_updated_at ON products;
CREATE TRIGGER update_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 9. Verify setup
SELECT 
    'Table created' as status,
    COUNT(*) as total_products,
    COUNT(embedding) as products_with_embeddings
FROM products;

-- 10. Test vector search function (will return empty until data is inserted)
-- SELECT * FROM match_products(
--     array_fill(0, ARRAY[1536])::vector,
--     0.5,
--     5
-- );
