# 📋 คู่มือเพิ่ม Column "ช่วงการใช้" (usage_period)

## ✅ สิ่งที่ทำเสร็จแล้ว

### 1. อัปเดต SQL Scripts
- ✅ `scripts/setup_complete_vector_db.sql` - เพิ่ม column usage_period
- ✅ `scripts/create_match_products_function.sql` - อัปเดต RPC function
- ✅ `scripts/add_usage_period_column.sql` - สร้าง script สำหรับเพิ่ม column

### 2. อัปเดต Python Code
- ✅ `app/main.py` - เพิ่ม usage_period ใน ProductRecommendation model
- ✅ อัปเดตทุกส่วนที่แสดงข้อมูลผลิตภัณฑ์ให้รวม usage_period
- ✅ สร้าง `scripts/update_import_script_usage_period.py` - script สำหรับ import ข้อมูลใหม่

---

## 🚀 ขั้นตอนการใช้งาน

### ขั้นตอนที่ 1: เพิ่ม Column ใน Supabase

รัน SQL script นี้ใน Supabase SQL Editor:

```sql
-- เพิ่ม column usage_period
ALTER TABLE products 
ADD COLUMN IF NOT EXISTS usage_period TEXT;

-- สร้าง index
CREATE INDEX IF NOT EXISTS idx_products_usage_period ON products(usage_period);

-- ตรวจสอบ
SELECT column_name, data_type 
FROM information_schema.columns
WHERE table_name = 'products'
ORDER BY ordinal_position;
```

หรือรัน script ที่เตรียมไว้:
```bash
# รันไฟล์ scripts/add_usage_period_column.sql ใน Supabase SQL Editor
```

### ขั้นตอนที่ 2: อัปเดต RPC Function

รัน SQL script นี้ใน Supabase SQL Editor:

```sql
-- อัปเดต match_products function
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
  usage_period text,  -- เพิ่มบรรทัดนี้
  usage_rate text,
  similarity float
)
LANGUAGE plpgsql
AS $
BEGIN
  RETURN QUERY
  SELECT
    products.id,
    products.product_name,
    products.active_ingredient,
    products.target_pest,
    products.applicable_crops,
    products.how_to_use,
    products.usage_period,  -- เพิ่มบรรทัดนี้
    products.usage_rate,
    1 - (products.embedding <=> query_embedding) AS similarity
  FROM products
  WHERE 1 - (products.embedding <=> query_embedding) > match_threshold
  ORDER BY products.embedding <=> query_embedding
  LIMIT match_count;
END;
$;
```

หรือรัน script ที่เตรียมไว้:
```bash
# รันไฟล์ scripts/create_match_products_function.sql ใน Supabase SQL Editor
```

### ขั้นตอนที่ 3: Import ข้อมูลใหม่

**ตัวเลือก A: ลบข้อมูลเก่าและ Import ใหม่ทั้งหมด**

```bash
# 1. ลบข้อมูลเก่า (ระวัง!)
python scripts/clear_products.py

# 2. Import ข้อมูลใหม่พร้อม usage_period
python scripts/update_import_script_usage_period.py
```

**ตัวเลือก B: อัปเดตข้อมูลที่มีอยู่**

```sql
-- อัปเดตข้อมูล usage_period จาก metadata (ถ้ามี)
UPDATE products
SET usage_period = metadata->>'ช่วงการใช้'
WHERE metadata->>'ช่วงการใช้' IS NOT NULL;

-- ตรวจสอบผลลัพธ์
SELECT 
    COUNT(*) as total,
    COUNT(usage_period) as with_usage_period,
    COUNT(usage_period) * 100.0 / COUNT(*) as percentage
FROM products;
```

### ขั้นตอนที่ 4: ทดสอบ

```bash
# ทดสอบว่า API ทำงานถูกต้อง
python tests/test_supabase.py

# ตรวจสอบว่า usage_period แสดงผลใน response
# ส่งรูปภาพโรคพืชผ่าน LINE Bot และดูว่าคำแนะนำมี "ช่วงการใช้" หรือไม่
```

---

## 📊 ตรวจสอบข้อมูล

### ตรวจสอบว่า Column ถูกเพิ่มแล้ว

```sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'products'
ORDER BY ordinal_position;
```

### ตรวจสอบข้อมูล usage_period

```sql
-- ดูข้อมูล usage_period
SELECT 
    product_name,
    usage_period,
    usage_rate
FROM products
WHERE usage_period IS NOT NULL
LIMIT 10;

-- สถิติ
SELECT 
    COUNT(*) as total_products,
    COUNT(usage_period) as products_with_usage_period,
    COUNT(usage_period) * 100.0 / COUNT(*) as percentage
FROM products;
```

### ทดสอบ Vector Search

```sql
-- ทดสอบ match_products function
SELECT 
    product_name,
    usage_period,
    usage_rate,
    similarity
FROM match_products(
    array_fill(0, ARRAY[768])::vector,
    0.3,
    5
);
```

---

## 🔍 ตัวอย่างข้อมูล usage_period จาก CSV

จากไฟล์ `Data ICPL product for iDA.csv`:

| ชื่อสินค้า | ช่วงการใช้ |
|-----------|-----------|
| โมเดิน 50 | ป้องกันแมลงในระยะแตกใบอ่อน |
| พรีดิคท์ 25 | ทุเรียน : ใช้พ่นที่ใบ ในระยะใบเพสลาด |
| ราเซอร์ | ใช้หลังปลูกพืชประธาน 0-3 วัน |
| พาสนาว | ก่อนปลูกพืช และหลังปลูกพืช 2-3 เดือน |

---

## 📝 การแสดงผลใน LINE Bot

หลังจากอัปเดตแล้ว ผลิตภัณฑ์จะแสดงข้อมูลเพิ่มเติม:

```
💊 ผลิตภัณฑ์แนะนำ:

1. โมเดิน 50
   สารสำคัญ: OMETHOATE 50% W/V SL
   ศัตรูพืช: เพลี้ยไฟ เพลี้ยจักจั่นฝอย เพลี้ยไก่แจ้
   ใช้กับพืช: ปลอดภัยใช้ได้ทุกพืช โดยเฉพาะทุเรียน
   ช่วงการใช้: ป้องกันแมลงในระยะแตกใบอ่อน  ⬅️ ใหม่!
   อัตราใช้: 300 ซีซีต่อ 200 ลิตร
```

---

## ⚠️ ข้อควรระวัง

1. **Backup ข้อมูลก่อน** - ก่อนลบหรืออัปเดตข้อมูล
2. **ทดสอบใน Development ก่อน** - อย่ารันใน Production ทันที
3. **ตรวจสอบ RPC Function** - ให้แน่ใจว่า function return ข้อมูลครบ
4. **Re-generate Embeddings** - ถ้าต้องการให้ usage_period อยู่ใน embeddings

---

## 🎯 สรุป

การเพิ่ม column "ช่วงการใช้" (usage_period) จะช่วยให้:

1. ✅ เกษตรกรรู้ว่าควรใช้ผลิตภัณฑ์เมื่อไหร่
2. ✅ เพิ่มความแม่นยำของคำแนะนำ
3. ✅ ข้อมูลครบถ้วนมากขึ้น
4. ✅ ใช้งานง่ายขึ้น

---

**Version:** 1.0  
**Last Updated:** 2024-11-18  
**Status:** Ready to Deploy ✅
