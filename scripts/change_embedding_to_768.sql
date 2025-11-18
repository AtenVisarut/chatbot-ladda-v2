-- Change embedding column from vector(1536) to vector(768) for E5 model
-- Run this in Supabase SQL Editor

-- Step 1: Drop the old vector index (required before changing column type)
DROP INDEX IF EXISTS idx_products_embedding;

-- Step 2: Change the column type to vector(768)
ALTER TABLE products 
ALTER COLUMN embedding TYPE vector(768);

-- Step 3: Create new vector index for 768 dimensions
CREATE INDEX idx_products_embedding ON products 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Step 4: Verify the change
SELECT 
    column_name, 
    data_type,
    udt_name
FROM information_schema.columns
WHERE table_name = 'products' AND column_name = 'embedding';

-- Step 5: Check products
SELECT 
    COUNT(*) as total_products,
    COUNT(embedding) as products_with_embeddings
FROM products;

-- Success message
SELECT '✅ Column changed to vector(768) successfully!' as status;
