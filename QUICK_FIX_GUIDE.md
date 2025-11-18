# 🚀 Quick Fix Guide - เพิ่ม usage_period และแก้ไข embeddings

## ปัญหาที่พบ
1. ❌ Embeddings ใน database เป็น vector(1536) แต่โค้ดใช้ E5 (768 มิติ)
2. ❌ Embeddings ถูกเก็บเป็น text (19,000+ มิติ) แทนที่จะเป็น vector
3. ✅ Column usage_period มีอยู่แล้ว แต่ไม่แสดงผลเพราะ vector search ไม่ทำงาน

## 🔧 วิธีแก้ไข (ทำตามลำดับ)

### ขั้นตอนที่ 1: เปลี่ยน embedding column เป็น 768 มิติ

รัน SQL นี้ใน **Supabase SQL Editor**:

```sql
-- Drop old index
DROP INDEX IF EXISTS idx_products_embedding;

-- Change column type
ALTER TABLE products 
ALTER COLUMN embedding TYPE vector(768);

-- Create new index
CREATE INDEX idx_products_embedding ON products 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

หรือรันไฟล์: `scripts/change_embedding_to_768.sql`

### ขั้นตอนที่ 2: Re-import ข้อมูลพร้อม E5 embeddings

```bash
python scripts/reimport_with_e5.py
```

จะใช้เวลาประมาณ 1-2 นาที

### ขั้นตอนที่ 3: อัปเดต RPC function

รัน SQL นี้ใน **Supabase SQL Editor**:

```sql
DROP FUNCTION IF EXISTS match_products(vector, float, int);

CREATE OR REPLACE FUNCTION match_products(
  query_embedding vector(768),
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

GRANT EXECUTE ON FUNCTION match_products TO authenticated;
GRANT EXECUTE ON FUNCTION match_products TO anon;
```

หรือรันไฟล์: `scripts/create_match_products_function.sql`

### ขั้นตอนที่ 4: ทดสอบ

```bash
# ทดสอบ vector search
python scripts/test_match_products_function.py

# ทดสอบว่า usage_period แสดงผล
python scripts/check_usage_period.py
```

### ขั้นตอนที่ 5: เริ่ม server

```bash
python app/main.py
```

## ✅ ผลลัพธ์ที่คาดหวัง

หลังจากทำตามขั้นตอนแล้ว:

1. ✅ Vector search ทำงานได้ (E5 model, 768 มิติ)
2. ✅ usage_period แสดงผลใน LINE Bot
3. ✅ ระบบแนะนำผลิตภัณฑ์ได้แม่นยำขึ้น

ตัวอย่างผลลัพธ์:
```
💊 ผลิตภัณฑ์แนะนำ:

1. โมเดิน 50
   สารสำคัญ: OMETHOATE 50% W/V SL
   ศัตรูพืช: เพลี้ยไฟ เพลี้ยจักจั่นฝอย
   ใช้กับพืช: ปลอดภัยใช้ได้ทุกพืช
   ช่วงการใช้: ป้องกันแมลงในระยะแตกใบอ่อน ⬅️ ใหม่!
   อัตราใช้: 300 ซีซีต่อ 200 ลิตร
```

## 🔍 การตรวจสอบ

### ตรวจสอบ embedding dimension
```sql
SELECT 
    product_name,
    array_length(embedding, 1) as embedding_dimension
FROM products
LIMIT 5;
```

ควรได้ 768 มิติ

### ตรวจสอบ usage_period
```sql
SELECT 
    product_name,
    usage_period,
    usage_rate
FROM products
WHERE usage_period IS NOT NULL
LIMIT 5;
```

### ทดสอบ vector search
```sql
SELECT 
    product_name,
    usage_period,
    similarity
FROM match_products(
    array_fill(0, ARRAY[768])::vector,
    0.0,
    5
);
```

## ⚠️ หมายเหตุ

- การเปลี่ยน column type จะลบ embeddings เก่าทั้งหมด (ปกติ)
- ต้อง re-import ข้อมูลใหม่พร้อม embeddings ที่ถูกต้อง
- E5 model ฟรี ไม่เสีย API cost
- ใช้เวลารวมประมาณ 5-10 นาที

---

**Status:** Ready to Execute ✅  
**Last Updated:** 2024-11-18
