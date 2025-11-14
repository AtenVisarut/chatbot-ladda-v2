-- Fix embeddings - Drop and recreate table with correct vector type
-- Run this in Supabase SQL Editor

-- 1. Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Drop old table (CAREFUL - this deletes all data!)
DROP TABLE IF EXISTS products CASCADE;

-- 3. Create new table with CORRECT vector type
CREATE TABLE products (
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
    embedding vector(1536),  -- IMPORTANT: vector type, not text!
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Create indexes
CREATE INDEX idx_products_target_pest ON products(target_pest);
CREATE INDEX idx_products_name ON products(product_name);
CREATE INDEX idx_products_group ON products(product_group);

-- 5. Create vector index
CREATE INDEX idx_products_embedding ON products 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- 6. Create RPC function
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

-- 7. Verify
SELECT 'Table recreated successfully' as status;
