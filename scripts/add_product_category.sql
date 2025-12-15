-- ============================================================================
-- เพิ่ม column product_category ใน table products
-- ============================================================================

-- 1. เพิ่ม column
ALTER TABLE products
ADD COLUMN IF NOT EXISTS product_category text;

-- 2. สร้าง index เพื่อ query เร็วขึ้น
CREATE INDEX IF NOT EXISTS idx_products_category ON products(product_category);

-- 3. อัปเดต match_products function ให้ return product_category ด้วย
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
  link_product text,
  product_category text,
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
    products.link_product,
    products.product_category,
    1 - (products.embedding <=> query_embedding) AS similarity
  FROM products
  WHERE 1 - (products.embedding <=> query_embedding) > match_threshold
  ORDER BY products.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- 4. Grant permissions
GRANT ALL ON products TO authenticated;
GRANT ALL ON products TO anon;
