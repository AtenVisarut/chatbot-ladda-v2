-- Verify that products table has correct vector type
-- Run this to check if table is set up correctly

-- 1. Check if vector extension is enabled
SELECT * FROM pg_extension WHERE extname = 'vector';

-- 2. Check table structure
SELECT 
    column_name, 
    data_type,
    udt_name
FROM information_schema.columns 
WHERE table_name = 'products'
ORDER BY ordinal_position;

-- 3. Check if embedding column is vector type
SELECT 
    column_name,
    data_type,
    udt_name
FROM information_schema.columns 
WHERE table_name = 'products' 
  AND column_name = 'embedding';

-- Expected result for embedding:
-- column_name: embedding
-- data_type: USER-DEFINED
-- udt_name: vector

-- 4. Check if RPC function exists
SELECT 
    routine_name,
    routine_type
FROM information_schema.routines
WHERE routine_name = 'match_products';

-- 5. Count products
SELECT COUNT(*) as total_products FROM products;

-- 6. Count products with embeddings
SELECT COUNT(*) as products_with_embeddings 
FROM products 
WHERE embedding IS NOT NULL;
