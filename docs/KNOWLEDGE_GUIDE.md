# คู่มือการเพิ่ม Knowledge Base

## ภาพรวม

ระบบ Knowledge Base ใช้เทคนิค **RAG (Retrieval-Augmented Generation)** ทำให้บอทตอบคำถามได้แม่นยำขึ้น โดยดึงข้อมูลจากฐานความรู้มาประกอบการตอบ

## 1. โครงสร้างข้อมูล

### Knowledge Table

| Column | Type | Description |
|--------|------|-------------|
| title | TEXT | หัวข้อ/ชื่อโรค/ชื่อศัตรูพืช |
| content | TEXT | เนื้อหารายละเอียด |
| category | TEXT | หมวดหมู่ |
| plant_type | TEXT | ชนิดพืช (optional) |
| source | TEXT | แหล่งที่มา |
| embedding | vector(1536) | Vector สำหรับค้นหา |

### หมวดหมู่ที่แนะนำ

- `disease` - โรคพืช (เชื้อรา, ไวรัส, แบคทีเรีย)
- `pest` - ศัตรูพืช (แมลง, ไร, หนอน)
- `crop_care` - การดูแลพืช (ปุ๋ย, น้ำ, ตัดแต่ง)
- `product_usage` - วิธีใช้ผลิตภัณฑ์
- `prevention` - การป้องกัน
- `harvest` - การเก็บเกี่ยว
- `general` - ความรู้ทั่วไป

---

## 2. Setup Supabase

### 2.1 รัน SQL สร้าง Table

```bash
# ไปที่ Supabase Dashboard > SQL Editor
# รัน scripts/setup_knowledge_table.sql
```

### 2.2 ตรวจสอบ

```sql
SELECT COUNT(*) FROM knowledge;
```

---

## 3. วิธีเพิ่ม Knowledge

### 3.1 จาก CSV File

**รูปแบบ CSV:**
```csv
title,content,category,plant_type,source
โรคผลเน่าทุเรียน,"รายละเอียด...",disease,ทุเรียน,กรมวิชาการเกษตร
เพลี้ยกระโดดสีน้ำตาล,"รายละเอียด...",pest,ข้าว,กรมการข้าว
```

**Import:**
```bash
cd scripts
python knowledge_ingestion.py --csv "../data/knowledge_templates/diseases_template.csv"
```

**Preview ก่อน Import:**
```bash
python knowledge_ingestion.py --csv "../data/diseases.csv" --dry-run
```

### 3.2 จาก Excel File

```bash
# ต้องติดตั้ง: pip install pandas openpyxl
python knowledge_ingestion.py --excel "../data/knowledge.xlsx"
```

### 3.3 จาก Website

```bash
# ดึงจาก URL
python knowledge_ingestion.py --url "https://www.doa.go.th/โรคพืช"

# ระบุ CSS selector
python knowledge_ingestion.py --url "https://example.com" --selector ".article-content"
```

### 3.4 จาก PDF

```bash
# ต้องติดตั้ง: pip install pymupdf
python knowledge_ingestion.py --pdf "../data/manual.pdf"

# แบ่งเป็น chunks
python knowledge_ingestion.py --pdf "../data/manual.pdf" --chunk
```

### 3.5 Import ทั้งโฟลเดอร์

```bash
# Import ไฟล์ CSV ทั้งหมด
python knowledge_ingestion.py --folder "../data/knowledge" --type csv

# Import ทุกประเภท
python knowledge_ingestion.py --folder "../data/knowledge"
```

---

## 4. ตัวอย่างเนื้อหาที่ดี

### โรคพืช (Disease)

```
โรคผลเน่าทุเรียน (Phytophthora Fruit Rot)

สาเหตุ: เชื้อรา Phytophthora palmivora

อาการ:
- ผลมีจุดสีน้ำตาลดำ เริ่มจากขั้วผล
- แผลขยายเป็นวงกลม เนื้อผลเน่าเละ
- มีกลิ่นเหม็น ผลร่วงก่อนสุก

สภาพที่เหมาะกับการระบาด:
- ความชื้นสูง ฝนตกต่อเนื่อง
- ดินน้ำท่วมขัง

การป้องกันกำจัด:
1. ตัดแต่งกิ่งให้โปร่ง
2. หลีกเลี่ยงน้ำท่วมโคน
3. พ่นสารป้องกันเชื้อรา
```

### ศัตรูพืช (Pest)

```
เพลี้ยกระโดดสีน้ำตาล (Brown Planthopper)

ลักษณะ:
- ตัวสีน้ำตาล ยาว 4-5 มม.
- ดูดกินน้ำเลี้ยงที่โคนต้นข้าว

อาการเสียหาย:
- ต้นข้าวเหลืองซีด
- อาการไหม้เป็นหย่อม (hopper burn)

ช่วงระบาด:
- ระยะแตกกอ-ตั้งท้อง

การป้องกันกำจัด:
1. ใช้พันธุ์ต้านทาน
2. ลดปุ๋ยไนโตรเจน
3. ใช้สารเคมีเมื่อพบ 10-20 ตัว/กอ
```

---

## 5. แหล่งข้อมูลแนะนำ

### เว็บไซต์ภาษาไทย

- กรมวิชาการเกษตร: https://www.doa.go.th
- กรมส่งเสริมการเกษตร: https://www.doae.go.th
- กรมการข้าว: https://www.ricethailand.go.th
- ศูนย์วิจัยข้าว: http://brrd.ricethailand.go.th

### แหล่งข้อมูล PDF

- คู่มือโรคพืช กรมวิชาการเกษตร
- แผ่นพับความรู้ กรมส่งเสริมฯ
- รายงานวิจัย มหาวิทยาลัยเกษตรศาสตร์

---

## 6. Best Practices

### เนื้อหาที่ดี

1. **ครบถ้วน** - มีอาการ, สาเหตุ, วิธีป้องกัน
2. **ชัดเจน** - ใช้ภาษาง่าย เข้าใจง่าย
3. **มีโครงสร้าง** - แบ่งหัวข้อ ใช้ bullet points
4. **อ้างอิงได้** - ระบุแหล่งที่มา

### หลีกเลี่ยง

1. เนื้อหาสั้นเกินไป (< 100 ตัวอักษร)
2. ข้อมูลซ้ำซ้อน
3. ข้อมูลล้าสมัย
4. เนื้อหาคลุมเครือ

### Chunk Size

- **1000 ตัวอักษร** - เหมาะสำหรับเนื้อหาทั่วไป
- **500 ตัวอักษร** - สำหรับ FAQ สั้นๆ
- **2000 ตัวอักษร** - สำหรับบทความยาว

---

## 7. การตรวจสอบ

### ดูจำนวน Knowledge

```sql
SELECT category, COUNT(*)
FROM knowledge
GROUP BY category
ORDER BY COUNT(*) DESC;
```

### ทดสอบการค้นหา

```sql
-- Vector Search
SELECT title, content, similarity
FROM match_knowledge(
    '[embedding_vector]'::vector,
    0.4,
    5
);
```

### ลบข้อมูลซ้ำ

```sql
DELETE FROM knowledge a
USING knowledge b
WHERE a.id > b.id
AND a.title = b.title;
```

---

## 8. Troubleshooting

### ปัญหา: Import ไม่สำเร็จ

```bash
# ตรวจสอบ encoding
file -I your_file.csv

# แปลงเป็น UTF-8
iconv -f TIS-620 -t UTF-8 input.csv > output.csv
```

### ปัญหา: ค้นหาไม่เจอ

1. ตรวจสอบ embedding ถูกสร้างหรือไม่
2. ลด match_threshold (เช่น 0.3)
3. เพิ่ม keyword search fallback

### ปัญหา: ผลลัพธ์ไม่ตรง

1. ปรับปรุงเนื้อหาให้ละเอียดขึ้น
2. เพิ่ม keywords ที่เกี่ยวข้อง
3. แยก category ให้ชัดเจน
