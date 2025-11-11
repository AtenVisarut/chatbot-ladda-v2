# 📚 ทำความเข้าใจ Project: LINE Plant Pest & Disease Detection Bot

## 🎯 โปรเจคนี้คืออะไร?

**LINE Bot ที่ใช้ AI ตรวจจับโรคพืชและศัตรูพืช แล้วแนะนำผลิตภัณฑ์ป้องกันกำจัด**

### การทำงานง่ายๆ:
1. เกษตรกรส่งรูปภาพพืชที่มีปัญหาผ่าน LINE
2. AI วิเคราะห์ว่าเป็น **เชื้อรา / ไวรัส / ศัตรูพืช** อะไร
3. ระบบค้นหาผลิตภัณฑ์ที่เหมาะสมจากฐานข้อมูล
4. ส่งคำแนะนำกลับไปให้เกษตรกรเป็นภาษาไทย

---

## 🏗️ สถาปัตยกรรมระบบ (Architecture)

```
┌─────────────┐
│   เกษตรกร   │ ส่งรูปภาพพืช
│  (LINE App) │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────┐
│         LINE Messaging API              │
│  (รับ/ส่งข้อความ, รูปภาพ)              │
└──────┬──────────────────────────────────┘
       │ Webhook
       ▼
┌─────────────────────────────────────────┐
│      FastAPI Server (app/main.py)       │
│  ┌───────────────────────────────────┐  │
│  │  1. รับรูปภาพจาก LINE             │  │
│  │  2. ส่งไป OpenAI Vision           │  │
│  │  3. ค้นหาผลิตภัณฑ์ใน Supabase    │  │
│  │  4. สร้างคำตอบภาษาไทย            │  │
│  │  5. ส่งกลับไปที่ LINE             │  │
│  └───────────────────────────────────┘  │
└──────┬────────────┬─────────────────────┘
       │            │
       ▼            ▼
┌─────────────┐  ┌──────────────────┐
│  OpenAI API │  │    Supabase      │
│             │  │  (PostgreSQL +   │
│ - Vision    │  │   pgvector)      │
│ - Embeddings│  │                  │
│ - LLM       │  │ 43 ผลิตภัณฑ์    │
└─────────────┘  └──────────────────┘
```

---

## 📁 โครงสร้างโปรเจค

```
Chatbot-disease-ladda/
│
├── app/
│   └── main.py                 # ❤️ หัวใจของระบบ - FastAPI server
│
├── scripts/
│   ├── setup_supabase.sql      # สร้างตารางใน Supabase
│   ├── import_csv_to_supabase.py  # Import ข้อมูลผลิตภัณฑ์
│   ├── clear_products.py       # ลบข้อมูลทั้งหมด
│   └── test_direct_search.py   # ทดสอบการค้นหา
│
├── tests/
│   ├── test_supabase.py        # ทดสอบ Supabase
│   ├── test_rag.py             # ทดสอบ RAG system
│   └── test_webhook.py         # ทดสอบ LINE webhook
│
├── docs/
│   ├── SUPABASE_SETUP.md       # คู่มือตั้งค่า Supabase
│   ├── MIGRATION_GUIDE.md      # คู่มือย้ายจาก Pinecone
│   ├── DEPLOYMENT_PRODUCTION.md # คู่มือ deploy
│   └── ...
│
├── Data ICPL product for iDA.csv  # 📊 ข้อมูลผลิตภัณฑ์ 43 รายการ
├── requirements.txt            # Python packages
├── Dockerfile                  # สำหรับ deploy
├── .env                        # 🔒 API keys (ห้าม push!)
├── .env.example                # ตัวอย่าง .env
├── README.md                   # เอกสารหลัก
└── CHANGELOG.md                # บันทึกการเปลี่ยนแปลง
```

---

## 🔧 เทคโนโลยีที่ใช้

### 1. **FastAPI** (Backend Framework)
```python
# app/main.py
from fastapi import FastAPI

app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    # รับข้อความจาก LINE
    # ประมวลผล
    # ส่งกลับ
```

**ทำไมใช้ FastAPI?**
- ⚡ เร็วมาก (async/await)
- 📝 Auto documentation (Swagger UI)
- 🔒 Type safety (Pydantic)
- 🐍 Python modern

---

### 2. **OpenAI API** (AI Engine)

#### 2.1 Vision API (วิเคราะห์รูปภาพ)
```python
response = openai_client.chat.completions.create(
    model="gpt-4o",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "วิเคราะห์โรคพืช"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}}
        ]
    }]
)
```

**Output:**
```json
{
  "disease_name": "เพลี้ยไฟ",
  "pest_type": "ศัตรูพืช",
  "confidence": "สูง",
  "symptoms": "ใบม้วน มีจุดสีเหลือง",
  "severity": "ปานกลาง"
}
```

#### 2.2 Embeddings (สร้าง Vector)
```python
response = openai_client.embeddings.create(
    model="text-embedding-3-small",
    input="เพลี้ยไฟ ทุเรียน"
)
embedding = response.data[0].embedding  # [0.123, -0.456, ...]
```

**ทำไมต้องมี Embeddings?**
- แปลงข้อความเป็นตัวเลข (vector)
- ใช้ค้นหาความคล้ายกัน
- เช่น "เพลี้ยไฟ" คล้าย "เพลี้ยจักจั่น"

---

### 3. **Supabase** (Database + Vector Search)

#### 3.1 PostgreSQL Database
```sql
CREATE TABLE products (
    id BIGSERIAL PRIMARY KEY,
    product_name TEXT,           -- ชื่อสินค้า
    active_ingredient TEXT,      -- สารสำคัญ
    target_pest TEXT,            -- ศัตรูพืชที่กำจัดได้
    applicable_crops TEXT,       -- ใช้ได้กับพืช
    how_to_use TEXT,            -- วิธีใช้
    embedding vector(1536)       -- Vector สำหรับค้นหา
);
```

#### 3.2 Vector Search (ไม่ได้ใช้แล้ว)
เดิมใช้ vector search แต่ไม่ทำงานดีกับภาษาไทย

#### 3.3 Keyword Search (ใช้อันนี้แทน)
```python
# ค้นหาด้วย keyword
response = supabase.table('products').select('*').or_(
    f'target_pest.ilike.%เพลี้ยไฟ%,product_name.ilike.%เพลี้ยไฟ%'
).execute()
```

**ทำไมเปลี่ยนเป็น Keyword Search?**
- ✅ ทำงานดีกว่ากับภาษาไทย
- ✅ เร็วกว่า
- ✅ แม่นยำกว่า

---

### 4. **LINE Messaging API** (Chat Interface)

#### 4.1 รับข้อความ (Webhook)
```python
@app.post("/webhook")
async def webhook(request: Request):
    events = webhook_data.get("events", [])
    for event in events:
        if event["type"] == "message":
            if event["message"]["type"] == "image":
                # ประมวลผลรูปภาพ
```

#### 4.2 ส่งข้อความกลับ
```python
async def reply_line(reply_token: str, message: str):
    url = "https://api.line.me/v2/bot/message/reply"
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": message}]
    }
    await client.post(url, json=payload)
```

---

## 🔄 Flow การทำงานทั้งหมด

### Step-by-Step:

```
1. เกษตรกรส่งรูปภาพ
   ↓
2. LINE ส่ง webhook มาที่ /webhook
   ↓
3. ดาวน์โหลดรูปภาพจาก LINE
   ↓
4. ส่งรูปไป OpenAI Vision
   ↓
5. OpenAI ตอบกลับ: "เพลี้ยไฟ, ศัตรูพืช, ความมั่นใจ: สูง"
   ↓
6. ดึง keywords: ["เพลี้ยไฟ", "ศัตรูพืช", "แมลง"]
   ↓
7. ค้นหาใน Supabase ด้วย keywords
   ↓
8. ได้ผลิตภัณฑ์ 5 รายการ:
   - โมเดิน 50 (เพลี้ยไฟ)
   - อิมิดาโกลด์ 70 (เพลี้ยไฟ)
   - ...
   ↓
9. สร้างข้อความภาษาไทย:
   "ผลตรวจจากภาพ: เพลี้ยไฟ
    ระดับความมั่นใจ: สูง
    สินค้าแนะนำ:
    • โมเดิน 50
    - สารสำคัญ: OMETHOATE 50%
    - ศัตรูพืช: เพลี้ยไฟ..."
   ↓
10. ส่งกลับไปที่ LINE
    ↓
11. เกษตรกรได้รับคำตอบ ✅
```

---

## 💾 ข้อมูลผลิตภัณฑ์

### ไฟล์: `Data ICPL product for iDA.csv`

**มี 43 ผลิตภัณฑ์** แบ่งเป็น:

#### 1. Insecticide (ยากำจัดแมลง)
- โมเดิน 50 → เพลี้ยไฟ
- ไฮซีส → หนอน
- อิมิดาโกลด์ 70 → เพลี้ยกระโดด

#### 2. Fungicide (ยากำจัดเชื้อรา)
- เบนซาน่า เอฟ → แอนแทรคโนส
- ก๊อปกัน → ใบไหม้
- โค-ราซ → โรคเชื้อรา

#### 3. Herbicide (ยากำจัดวัชพืช)
- พาสนาว → วัชพืชทั่วไป
- ราเซอร์ → วัชพืชในพืชไร่

#### 4. PGR (ตัวควบคุมการเจริญเติบโต)
- พรีดิคท์ 25 → ยับยั้งใบอ่อน

### โครงสร้างข้อมูล:
```csv
ชื่อสินค้า,สารสำคัญ,ศัตรูพืชที่กำจัดได้,ใช้ได้กับพืช,วิธีใช้,อัตราการใช้
โมเดิน 50,OMETHOATE 50%,เพลี้ยไฟ เพลี้ยจักจั่น,ทุกพืช,ฉีดพ่น,300cc/200L
```

---

## 🔑 Environment Variables (.env)

```env
# LINE Bot
LINE_CHANNEL_ACCESS_TOKEN=xxx  # สำหรับส่งข้อความ
LINE_CHANNEL_SECRET=xxx        # สำหรับ verify webhook

# OpenAI
OPENAI_API_KEY=xxx             # สำหรับ Vision + Embeddings

# Supabase
SUPABASE_URL=xxx               # Database URL
SUPABASE_KEY=xxx               # API Key
```

**⚠️ สำคัญ:** ห้าม push .env ขึ้น GitHub!

---

## 🧪 การทดสอบ

### 1. ทดสอบ Supabase
```bash
python tests/test_supabase.py
```
**ตรวจสอบ:**
- ✅ เชื่อมต่อได้
- ✅ มี 43 products
- ✅ ค้นหาได้

### 2. ทดสอบ Server
```bash
python app/main.py
# Server: http://localhost:8000
```

### 3. ทดสอบ Health Check
```bash
curl http://localhost:8000/health
```
**Response:**
```json
{
  "status": "healthy",
  "services": {
    "openai": "ok",
    "supabase": "ok",
    "line": "ok"
  }
}
```

---

## 💰 ค่าใช้จ่าย

### ต่อเดือน (100 users, 10 รูป/วัน = 1,000 requests)

| Service | ค่าใช้จ่าย | หมายเหตุ |
|---------|-----------|----------|
| **LINE** | ฟรี | ไม่จำกัด |
| **Supabase** | ฟรี | Free tier 500MB |
| **OpenAI** | ~$30-50 | $0.01-0.05/request |
| **Cloud Run** | ฟรี | Free tier 2M requests |
| **รวม** | **~$30-50** | ส่วนใหญ่เป็น OpenAI |

### ลดค่าใช้จ่าย:
1. ใช้ GPT-4o-mini แทน GPT-4o (ถูกกว่า 10 เท่า)
2. Cache results
3. Rate limiting

---

## 🚀 การ Deploy

### ง่ายที่สุด: Railway
1. https://railway.app
2. Connect GitHub
3. Deploy!

### แนะนำ: Google Cloud Run
```bash
gcloud run deploy plant-disease-bot --source .
```

### ทางเลือก: Render, Heroku

---

## 🔄 Version History

### v2.0 (ปัจจุบัน)
- ✅ ใช้ Supabase แทน Pinecone
- ✅ ตอบเป็น เชื้อรา/ไวรัส/ศัตรูพืช
- ✅ Keyword search แทน vector search
- ✅ 43 ผลิตภัณฑ์จาก ICPL

### v1.0 (เดิม)
- ❌ ใช้ Pinecone
- ❌ ตอบเป็น "โรคใบ"
- ❌ Vector search (ไม่ดีกับภาษาไทย)

---

## 📚 เอกสารเพิ่มเติม

- **README.md** - ภาพรวมโปรเจค
- **ARCHITECTURE.md** - สถาปัตยกรรมละเอียด
- **CHANGELOG.md** - บันทึกการเปลี่ยนแปลง
- **docs/SUPABASE_SETUP.md** - ตั้งค่า Supabase
- **docs/DEPLOYMENT_PRODUCTION.md** - Deploy production
- **QUICK_DEPLOY.md** - Deploy แบบเร็ว

---

## ❓ FAQ

### Q: ทำไมไม่ใช้ vector search?
A: ไม่ทำงานดีกับภาษาไทย, keyword search แม่นยำกว่า

### Q: ทำไมเลือก Supabase?
A: ฟรี, มี PostgreSQL เต็มรูปแบบ, ง่ายกว่า Pinecone

### Q: ค่าใช้จ่ายเท่าไหร่?
A: ~$30-50/เดือน (ส่วนใหญ่เป็น OpenAI)

### Q: Deploy ยังไง?
A: ง่ายที่สุดคือ Railway หรือ Google Cloud Run

### Q: ปลอดภัยไหม?
A: ใช่ - API keys ไม่ถูก push, HTTPS, signature verification

---

## 🎯 สรุป

**โปรเจคนี้คือ:**
- 🤖 LINE Bot ตรวจโรคพืชด้วย AI
- 🔍 ใช้ OpenAI Vision วิเคราะห์รูปภาพ
- 💾 เก็บข้อมูลใน Supabase
- 🎯 แนะนำผลิตภัณฑ์ 43 รายการ
- 🇹🇭 รองรับภาษาไทย 100%
- ⚡ พร้อม deploy production

**เหมาะสำหรับ:**
- เกษตรกร
- ร้านขายปุ๋ย/ยา
- บริษัทเกษตร
- สหกรณ์การเกษตร

---

มีคำถามเพิ่มเติมไหมครับ? 😊
