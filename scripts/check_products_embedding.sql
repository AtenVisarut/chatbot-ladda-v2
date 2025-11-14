-- Check if products table has embedding column
SELECT 
    column_name, 
    data_type, 
    character_maximum_length
FROM information_schema.columns
WHERE table_name = 'products'
ORDER BY ordinal_position;

-- Check if there are any embeddings in products table
SELECT 
    COUNT(*) as total_products,
    COUNT(embedding) as products_with_embedding,
    COUNT(*) - COUNT(embedding) as products_without_embedding
FROM products;

-- Sample products to see structure
SELECT 
    id,
    product_name,
    target_pest,
    CASE 
        WHEN embedding IS NULL THEN 'No embedding'
        ELSE 'Has embedding'
    END as embedding_status
FROM products
LIMIT 5;
