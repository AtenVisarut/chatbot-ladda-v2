# ✅ สถานะ Memory System

## 📋 สรุป

### โค้ด: ✅ พร้อมใช้งาน
- ✅ ใช้ Supabase แล้ว (ไม่ใช่ in-memory)
- ✅ ฟังก์ชันทั้งหมดเป็น async
- ✅ มี error handling

### Database: ❓ ต้องตรวจสอบ
- ❓ Table `conversation_memory` ถูกสร้างแล้วหรือยัง?

---

## 🔍 ตรวจสอบ

### Step 1: เช็คว่า Table มีหรือยัง

ไปที่ **Supabase Dashboard** → **Table Editor**

ดูว่ามี table ชื่อ `conversation_memory` หรือไม่?

#### ถ้ามี ✅
- Memory system พร้อมใช้งานแล้ว!

#### ถ้าไม่มี ❌
- ต้องสร้าง table ก่อน

---

## 🔧 วิธีสร้าง Table (ถ้ายังไม่มี)

### Option 1: ใช้ SQL Editor (แนะนำ)

1. ไปที่ **Supabase Dashboard**
2. เลือก **SQL Editor**
3. Copy SQL นี้:

```sql
-- Create conversation_memory table
CREATE TABLE IF NOT EXISTS conversation_memory (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_conversation_memory_user_id 
ON conversation_memory(user_id);

CREATE INDEX IF NOT EXISTS idx_conversation_memory_created_at 
ON conversation_memory(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_conversation_memory_user_created 
ON conversation_memory(user_id, created_at DESC);

-- Enable RLS
ALTER TABLE conversation_memory ENABLE ROW LEVEL SECURITY;

-- Create policy
CREATE POLICY "Allow all operations on conversation_memory" 
ON conversation_memory 
FOR ALL 
USING (true) 
WITH CHECK (true);

-- Grant permissions
GRANT ALL ON conversation_memory TO authenticated;
GRANT ALL ON conversation_memory TO anon;
GRANT USAGE, SELECT ON SEQUENCE conversation_memory_id_seq TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE conversation_memory_id_seq TO anon;
```

4. กด **Run**

### Option 2: ใช้ Script ที่มีอยู่แล้ว

```bash
# ไฟล์อยู่ที่
scripts/create_conversation_memory_table.sql

# Copy SQL จากไฟล์นี้ไปรันใน Supabase SQL Editor
```

---

## 🧪 ทดสอบว่า Memory ทำงานหรือไม่

### Test 1: เช็คว่า Table มีหรือยัง

```sql
-- รันใน Supabase SQL Editor
SELECT * FROM conversation_memory LIMIT 1;
```

**ผลลัพธ์**:
- ✅ ถ้าได้ผลลัพธ์ (แม้จะว่างเปล่า) = Table มีแล้ว
- ❌ ถ้า error "relation does not exist" = ยังไม่มี table

### Test 2: ทดสอบ Insert

```sql
-- รันใน Supabase SQL Editor
INSERT INTO conversation_memory (user_id, role, content)
VALUES ('test_user', 'user', 'สวัสดี');

SELECT * FROM conversation_memory WHERE user_id = 'test_user';
```

**ผลลัพธ์**:
- ✅ ถ้า insert สำเร็จ = Memory system พร้อมใช้งาน!

### Test 3: ทดสอบผ่าน LINE Bot

```
1. ส่งข้อความ: "สวัสดี"
2. Bot ตอบ: "สวัสดีค่ะ! มีอะไรให้ช่วยไหมคะ?"
3. ส่งข้อความ: "ขอบคุณ"
4. Bot ตอบ: "ยินดีค่ะ! มีอะไรให้ช่วยเพิ่มเติมไหมคะ?"
   ← ถ้าตอบแบบนี้ = Memory ทำงาน!
```

---

## 📊 ตรวจสอบข้อมูลใน Memory

### ดูข้อความทั้งหมด

```sql
SELECT 
    user_id,
    role,
    content,
    created_at
FROM conversation_memory
ORDER BY created_at DESC
LIMIT 20;
```

### นับจำนวนข้อความ

```sql
SELECT 
    COUNT(*) as total_messages,
    COUNT(DISTINCT user_id) as total_users
FROM conversation_memory;
```

### ดูข้อความของ User คนหนึ่ง

```sql
SELECT 
    role,
    content,
    created_at
FROM conversation_memory
WHERE user_id = 'YOUR_USER_ID'
ORDER BY created_at DESC
LIMIT 10;
```

---

## 🐛 Troubleshooting

### Problem 1: "relation does not exist"
**สาเหตุ**: Table ยังไม่ถูกสร้าง

**แก้ไข**: รัน SQL script ใน Supabase SQL Editor

### Problem 2: "permission denied"
**สาเหตุ**: ไม่มี permission

**แก้ไข**:
```sql
GRANT ALL ON conversation_memory TO authenticated;
GRANT ALL ON conversation_memory TO anon;
```

### Problem 3: Memory ไม่ทำงาน
**สาเหตุ**: Supabase client ไม่ได้ connect

**แก้ไข**: ตรวจสอบ `.env`
```env
SUPABASE_URL=your_url
SUPABASE_KEY=your_key
```

### Problem 4: Bot ไม่จำบทสนทนา
**สาเหตุ**: ฟังก์ชัน memory ไม่ถูกเรียกใช้

**แก้ไข**: ตรวจสอบ logs
```python
# ดู logs ว่ามี "✓ Added to memory" หรือไม่
```

---

## ✅ Checklist

ก่อนใช้งาน Memory System ให้เช็คว่า:

- [ ] Table `conversation_memory` ถูกสร้างแล้ว
- [ ] Indexes ถูกสร้างแล้ว
- [ ] RLS policies ถูกตั้งค่าแล้ว
- [ ] Permissions ถูก grant แล้ว
- [ ] `.env` มี SUPABASE_URL และ SUPABASE_KEY
- [ ] ทดสอบ insert ข้อมูลได้
- [ ] ทดสอบผ่าน LINE Bot แล้ว

---

## 🎯 สรุป

### ถ้า Table มีแล้ว:
✅ **Memory system พร้อมใช้งาน!**
- บทสนทนาจะถูกเก็บใน Supabase
- Bot จะจำบทสนทนาก่อนหน้า
- ไม่หายเมื่อ restart server

### ถ้า Table ยังไม่มี:
❌ **ต้องสร้าง table ก่อน**
1. ไปที่ Supabase SQL Editor
2. รัน SQL script
3. ทดสอบ insert
4. เริ่มใช้งาน!

---

**ต้องการให้ช่วยตรวจสอบหรือสร้าง table ไหมครับ?** 😊
