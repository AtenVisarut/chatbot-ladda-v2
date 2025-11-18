-- Add "usage_period" column to products table
-- Run this in Supabase SQL Editor

-- 1. Add new column
ALTER TABLE products 
ADD COLUMN IF NOT EXISTS usage_period TEXT;

-- 2. Create index for faster search
CREATE INDEX IF NOT EXISTS idx_products_usage_period ON products(usage_period);

-- 3. Verify the column was added
SELECT 
    column_name, 
    data_type, 
    is_nullable
FROM information_schema.columns
WHERE table_name = 'products'
ORDER BY ordinal_position;

-- 4. Check current data
SELECT 
    COUNT(*) as total_products,
    COUNT(usage_period) as products_with_usage_period,
    COUNT(usage_period) * 100.0 / COUNT(*) as percentage
FROM products;

-- Note: After running this script, you need to re-import the CSV data
-- to populate the usage_period column with data from "ช่วงการใช้"
