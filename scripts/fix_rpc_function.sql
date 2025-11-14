-- Fix RPC function - Remove product_description column
-- Run this in Supabase SQL Editor

-- Drop old function
DROP FUNCTION IF EXISTS match_products CASCADE;

-- Create correct RPC function (without product_description)
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
    p.id,
    p.product_name,
    p.active_ingredient,
    p.target_pest,
    p.applicable_crops,
    p.how_to_use,
    p.product_group,
    p.formulation,
    p.usage_rate,
    1 - (p.embedding <=> query_embedding) AS similarity
  FROM products p
  WHERE p.embedding IS NOT NULL
    AND 1 - (p.embedding <=> query_embedding) > match_threshold
  ORDER BY p.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Test function
SELECT * FROM match_products(
    array_fill(0, ARRAY[1536])::vector,
    0.0,
    3
);
