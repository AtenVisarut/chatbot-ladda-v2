-- Fix embedding dimension mismatch (768 -> 1536)

-- 1. Drop the existing index (must be done before altering column)
DROP INDEX IF EXISTS idx_products_embedding;

-- 2. Alter the column type to vector(1536)
-- Note: This will delete existing data in the column because dimensions don't match.
-- Since we are re-importing anyway, this is fine.
ALTER TABLE products 
ALTER COLUMN embedding TYPE vector(1536) 
USING null::vector(1536); -- Reset data to null to avoid conversion errors

-- 3. Re-create the index for 1536 dimensions
CREATE INDEX idx_products_embedding ON products 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- 4. Update the match_products function to accept 1536 dimensions
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

-- 5. Verify the change
SELECT 
    column_name, 
    data_type, 
    udt_name 
FROM information_schema.columns 
WHERE table_name = 'products' AND column_name = 'embedding';
