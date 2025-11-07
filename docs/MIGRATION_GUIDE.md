# Migration Guide: Pinecone → Supabase

คู่มือการย้ายระบบจาก Pinecone ไป Supabase

## สิ่งที่เปลี่ยนแปลง

### 1. Vector Database
- **เดิม:** Pinecone (Cloud-based vector DB)
- **ใหม่:** Supabase + pgvector (PostgreSQL extension)

### 2. การตอบกลับ
- **เดิม:** ตอบเป็น "โรคใบ"
- **ใหม่:** ตอบเป็น "เชื้อรา/ไวรัส/ศัตรูพืช"

### 3. แหล่งข้อมูลผลิตภัณฑ์
- ใช้ `Data ICPL product for iDA.csv` เป็นแหล่งเดียว

## ขั้นตอนการ Migration

### Step 1: Setup Supabase

1. สร้าง Supabase project ใหม่
2. รัน SQL script:
   ```bash
   # Copy โค้ดจาก scripts/setup_supabase.sql
   # Paste ใน Supabase SQL Editor
   ```

### Step 2: อัพเดท Environment Variables

แก้ไขไฟล์ `.env`:

```env
# ลบ Pinecone config
# PINECONE_API_KEY=...
# PINECONE_INDEX_NAME=...

# เพิ่ม Supabase config
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key-here
```

### Step 3: ติดตั้ง Dependencies ใหม่

```bash
pip uninstall pinecone-client pinecone
pip install supabase openai python-dotenv
```

หรือ

```bash
pip install -r requirements.txt
```

### Step 4: Import ข้อมูล

```bash
python scripts/import_csv_to_supabase.py
```

### Step 5: ทดสอบระบบ

```bash
python app/main.py
```

ทดสอบผ่าน LINE Bot หรือ API endpoint

## การเปรียบเทียบ Code

### Pinecone (เดิม)

```python
from pinecone import Pinecone

# Initialize
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)

# Query
results = index.query(
    vector=query_vec,
    top_k=8,
    include_metadata=True
)
```

### Supabase (ใหม่)

```python
from supabase import create_client

# Initialize
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Query
response = supabase.rpc(
    'match_products',
    {
        'query_embedding': query_vec,
        'match_threshold': 0.30,
        'match_count': 8
    }
).execute()
```

## ข้อดีของ Supabase

### 1. ประหยัดค่าใช้จ่าย
- Pinecone: ~$70/เดือน (Starter plan)
- Supabase: ฟรี (Free tier) หรือ $25/เดือน (Pro)

### 2. ฟีเจอร์เพิ่มเติม
- PostgreSQL database เต็มรูปแบบ
- Real-time subscriptions
- Authentication built-in
- Storage สำหรับไฟล์
- Edge Functions

### 3. ความยืดหยุ่น
- Query ข้อมูลแบบ SQL ได้
- Join กับตารางอื่นได้
- Full-text search
- JSON operations

### 4. Self-hosted Option
- สามารถ host เองได้ถ้าต้องการ
- ไม่ vendor lock-in

## ข้อควรระวัง

### 1. Performance
- pgvector เร็วกว่า Pinecone เล็กน้อยในข้อมูลน้อย
- Pinecone เร็วกว่าในข้อมูลมาก (>1M vectors)
- สำหรับ use case นี้ (~100 products) Supabase เพียงพอ

### 2. Scaling
- Supabase Free tier: 500MB database
- ถ้าข้อมูลเยอะมาก อาจต้อง upgrade plan

### 3. Embedding Dimensions
- ใช้ `text-embedding-3-small` (1536 dimensions)
- ถ้าเปลี่ยนโมเดล ต้องสร้างตารางใหม่

## Rollback Plan

ถ้าต้องการกลับไปใช้ Pinecone:

1. เก็บ backup ของ `.env` เดิม
2. เก็บ code เดิมไว้ใน branch แยก
3. Pinecone data ยังอยู่ (ถ้าไม่ลบ index)

```bash
git checkout pinecone-version
pip install pinecone==5.4.2
# อัพเดท .env กลับไปใช้ Pinecone
```

## ตรวจสอบการทำงาน

### Test Checklist

- [ ] Supabase connection สำเร็จ
- [ ] Import ข้อมูล CSV สำเร็จ
- [ ] Vector search ทำงานได้
- [ ] LINE Bot ตอบกลับได้
- [ ] แนะนำผลิตภัณฑ์ถูกต้อง
- [ ] ตอบเป็น "เชื้อรา/ไวรัส/ศัตรูพืช"

### Test Query

```python
# Test vector search
from supabase import create_client
from openai import OpenAI

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Generate test embedding
response = openai_client.embeddings.create(
    model="text-embedding-3-small",
    input="เพลี้ยไฟ ทุเรียน"
)
embedding = response.data[0].embedding

# Search
results = supabase.rpc(
    'match_products',
    {
        'query_embedding': embedding,
        'match_threshold': 0.3,
        'match_count': 5
    }
).execute()

print(f"Found {len(results.data)} products")
for product in results.data:
    print(f"- {product['product_name']} (similarity: {product['similarity']:.2f})")
```

## Support

หากมีปัญหา:
1. ตรวจสอบ logs ใน Supabase Dashboard
2. ดู error messages ใน console
3. อ่าน [SUPABASE_SETUP.md](./SUPABASE_SETUP.md)
4. ดู [Troubleshooting section](./SUPABASE_SETUP.md#troubleshooting)
