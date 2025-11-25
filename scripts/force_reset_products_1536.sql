-- FORCE RESET SCRIPT
-- This script will DELETE the existing products table and recreate it correctly.
-- Use this if you are having trouble with "expected 768 dimensions" errors.

-- 1. Drop the existing table (and all dependent objects)
DROP TABLE IF EXISTS products CASCADE;

-- 2. Re-create the table with vector(1536)
CREATE TABLE products (
  id BIGSERIAL PRIMARY KEY,
  product_name TEXT,
  active_ingredient TEXT,
  target_pest TEXT,
  applicable_crops TEXT,
  how_to_use TEXT,
  usage_period TEXT,
  usage_rate TEXT,
  embedding vector(1536) -- Correct dimension for OpenAI
);

-- 3. Create the index
CREATE INDEX idx_products_embedding ON products 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- 4. Re-create the search function
CREATE OR REPLACE FUNCTION match_products (
  query_embedding vector(1536),
  match_threshold float,
  match_count int
)
RETURNS TABLE (
  id bigint,
  product_name text,
  active_ingredient text,
  target_pest text,
  applicable_crops text,
  how_to_use text,
  usage_period text,
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
    products.usage_period,
    products.usage_rate,
    1 - (products.embedding <=> query_embedding) AS similarity
  FROM products
  WHERE 1 - (products.embedding <=> query_embedding) > match_threshold
  ORDER BY products.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- 5. Grant permissions
GRANT ALL ON TABLE products TO anon, authenticated;
GRANT ALL ON SEQUENCE products_id_seq TO anon, authenticated;
