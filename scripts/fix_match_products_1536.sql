-- Update match_products function for 1536-dimensional vectors (OpenAI embeddings)
-- AND add usage_period field
-- Run this in Supabase SQL Editor

DROP FUNCTION IF EXISTS match_products(vector, float, int);

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
  WHERE products.embedding IS NOT NULL
    AND 1 - (products.embedding <=> query_embedding) > match_threshold
  ORDER BY products.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Grant permissions
GRANT EXECUTE ON FUNCTION match_products TO authenticated;
GRANT EXECUTE ON FUNCTION match_products TO anon;

-- Test the function
SELECT 
    product_name,
    usage_period,
    usage_rate,
    similarity
FROM match_products(
    array_fill(0, ARRAY[1536])::vector,
    0.0,
    3
);
