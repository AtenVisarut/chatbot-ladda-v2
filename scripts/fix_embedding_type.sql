-- Fix embedding column type from text to vector
-- Run this in Supabase SQL Editor

-- Step 1: Add a new column with correct vector type
ALTER TABLE products ADD COLUMN IF NOT EXISTS embedding_vector vector(1536);

-- Step 2: Convert string embeddings to proper vector type
-- This converts '[0.1,0.2,0.3,...]' string format to actual vector
UPDATE products 
SET embedding_vector = embedding::vector
WHERE embedding IS NOT NULL;

-- Step 3: Drop old embedding column
ALTER TABLE products DROP COLUMN IF EXISTS embedding;

-- Step 4: Rename new column to 'embedding'
ALTER TABLE products RENAME COLUMN embedding_vector TO embedding;

-- Step 5: Recreate the vector index
DROP INDEX IF EXISTS idx_products_embedding;
CREATE INDEX idx_products_embedding ON products 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Step 6: Verify the fix
SELECT 
    'Fixed!' as status,
    COUNT(*) as total_products,
    COUNT(embedding) as products_with_embeddings,
    pg_typeof(embedding) as embedding_type
FROM products
WHERE embedding IS NOT NULL
LIMIT 1;

-- Step 7: Test the RPC function
SELECT * FROM match_products(
    array_fill(0, ARRAY[1536])::vector,
    0.0,
    5
);
