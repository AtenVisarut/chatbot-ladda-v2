# 📁 โครงสร้าง Project ที่แนะนำ

## 🎯 โครงสร้างใหม่

```
line-plant-disease-bot/
│
├── app/                          # โค้ดหลักของแอปพลิเคชัน
│   ├── __init__.py
│   ├── main.py                   # FastAPI application
│   ├── models.py                 # Pydantic models (ถ้าแยก)
│   ├── services/                 # Business logic
│   │   ├── __init__.py
│   │   ├── disease_detection.py # Gemini/OpenAI logic
│   │   ├── product_recommendation.py # Pinecone RAG
│   │   └── line_messaging.py    # LINE API
│   └── utils/                    # Helper functions
│       ├── __init__.py
│       └── image_processing.py
│
├── docs/                         # เอกสารทั้งหมด
│   ├── START_HERE.md            # เริ่มต้นที่นี่
│   ├── INSTALL.md               # คู่มือติดตั้ง
│   ├── DEPLOYMENT.md            # คู่มือ deploy
│   ├── ARCHITECTURE.md          # สถาปัตยกรรม
│   ├── TROUBLESHOOTING.md       # แก้ปัญหา
│   ├── QUICK_REFERENCE.md       # คำสั่งด่วน
│   ├── OPENAI_SETUP.md          # Setup OpenAI
│   ├── NGROK_SETUP.md           # Setup ngrok
│   └── ...
│
├── tests/                        # ไฟล์ทดสอบ
│   ├── __init__.py
│   ├── test_webhook.py          # ทดสอบ webhook
│   ├── test_openai.py           # ทดสอบ OpenAI
│   ├── test_imports.py          # ทดสอบ imports
│   └── quick_test.py            # ทดสอบรวม
│
├── scripts/                      # สคริปต์ setup และ utility
│   ├── setup_pinecone.py        # สร้าง Pinecone index
│   ├── populate_products.py     # เพิ่มข้อมูลผลิตภัณฑ์
│   ├── quickstart.sh            # Quick start (Linux/Mac)
│   └── quickstart.bat           # Quick start (Windows)
│
├── config/                       # ไฟล์ config
│   ├── .env.example             # ตัวอย่าง environment variables
│   └── logging.conf             # Logging config (ถ้ามี)
│
├── data/                         # ข้อมูล
│   ├── products/                # ข้อมูลผลิตภัณฑ์
│   └── samples/                 # รูปตัวอย่าง
│
├── .env                          # Environment variables (ไม่ commit)
├── .gitignore                    # Git ignore rules
├── requirements.txt              # Python dependencies
├── Dockerfile                    # Docker configuration
├── .dockerignore                 # Docker ignore rules
├── README.md                     # เอกสารหลัก
└── reorganize_project.py         # สคริปต์จัดระเบียบ
```

## 🔄 วิธีจัดระเบียบ

### ตัวเลือกที่ 1: ใช้สคริปต์อัตโนมัติ (แนะนำ)

```bash
python reorganize_project.py
```

สคริปต์จะ:
- ✅ สร้างโฟลเดอร์ทั้งหมด
- ✅ ย้ายไฟล์ไปยังตำแหน่งที่เหมาะสม
- ✅ สร้าง README ใหม่
- ✅ เก็บไฟล์เดิมไว้เผื่อมีปัญหา

### ตัวเลือกที่ 2: ทำเองทีละขั้นตอน

#### 1. สร้างโฟลเดอร์

```bash
# Windows
mkdir app docs tests scripts config data

# Linux/Mac
mkdir -p app docs tests scripts config data
```

#### 2. ย้ายเอกสาร

```bash
# Windows
move *.md docs\

# Linux/Mac
mv *.md docs/
```

ยกเว้น README.md ให้เก็บไว้ที่ root

#### 3. ย้ายไฟล์ทดสอบ

```bash
# Windows
move test_*.py tests\
move quick_test.py tests\

# Linux/Mac
mv test_*.py tests/
mv quick_test.py tests/
```

#### 4. ย้ายสคริปต์

```bash
# Windows
move setup_pinecone.py scripts\
move populate_products.py scripts\
move quickstart.* scripts\

# Linux/Mac
mv setup_pinecone.py scripts/
mv populate_products.py scripts/
mv quickstart.* scripts/
```

#### 5. ย้าย config

```bash
# Windows
move .env.example config\

# Linux/Mac
mv .env.example config/
```

#### 6. จัดการโค้ดหลัก

```bash
# คัดลอก main.py ไปยัง app/
# Windows
copy main.py app\main.py

# Linux/Mac
cp main.py app/main.py
```

## 🎯 ข้อดีของโครงสร้างใหม่

### 1. แยกหมวดหมู่ชัดเจน
- ✅ โค้ด → `app/`
- ✅ เอกสาร → `docs/`
- ✅ ทดสอบ → `tests/`
- ✅ Setup → `scripts/`

### 2. ง่ายต่อการหา
- ✅ ต้องการเอกสาร → ดูใน `docs/`
- ✅ ต้องการทดสอบ → ดูใน `tests/`
- ✅ ต้องการ setup → ดูใน `scripts/`

### 3. มาตรฐาน Python Project
- ✅ ตาม best practices
- ✅ ง่ายต่อการ maintain
- ✅ เหมาะกับ team work

### 4. พร้อม Scale
- ✅ แยก services ได้
- ✅ เพิ่ม modules ง่าย
- ✅ Test แยกชัดเจน

## 📝 การใช้งานหลังจัดระเบียบ

### รัน Server

```bash
# แบบเดิม
python main.py

# แบบใหม่
python app/main.py

# หรือ
python -m app.main
```

### รัน Tests

```bash
# แบบเดิม
python test_openai.py

# แบบใหม่
python tests/test_openai.py
```

### รัน Setup Scripts

```bash
# แบบเดิม
python setup_pinecone.py

# แบบใหม่
python scripts/setup_pinecone.py
```

## 🔧 อัพเดท Import Paths

ถ้าแยก services ใน `app/services/` ต้องอัพเดท imports:

```python
# แบบเดิม (ทุกอย่างใน main.py)
# ไม่ต้องเปลี่ยน

# แบบใหม่ (ถ้าแยก services)
from app.services.disease_detection import detect_disease
from app.services.product_recommendation import retrieve_products
from app.services.line_messaging import send_reply
```

## 📋 Checklist หลังจัดระเบียบ

- [ ] ทุกไฟล์อยู่ในโฟลเดอร์ที่ถูกต้อง
- [ ] ลบไฟล์ซ้ำ/ไม่ใช้แล้ว
- [ ] อัพเดท README.md
- [ ] ทดสอบรัน server: `python app/main.py`
- [ ] ทดสอบ scripts: `python scripts/setup_pinecone.py`
- [ ] ทดสอบ tests: `python tests/test_openai.py`
- [ ] อัพเดท .gitignore ถ้าจำเป็น
- [ ] Commit changes

## 🎨 โครงสร้างขั้นสูง (Optional)

ถ้าต้องการแยกโค้ดให้ละเอียดขึ้น:

```
app/
├── __init__.py
├── main.py                    # FastAPI app
├── config.py                  # Configuration
├── models/                    # Data models
│   ├── __init__.py
│   ├── disease.py
│   └── product.py
├── services/                  # Business logic
│   ├── __init__.py
│   ├── disease_detection.py
│   ├── product_recommendation.py
│   └── line_messaging.py
├── api/                       # API endpoints
│   ├── __init__.py
│   ├── webhook.py
│   └── health.py
└── utils/                     # Utilities
    ├── __init__.py
    ├── image.py
    └── logging.py
```

## 💡 Tips

1. **เริ่มจากง่าย** - ใช้โครงสร้างพื้นฐานก่อน
2. **แยกทีละน้อย** - ค่อยๆ แยก services เมื่อโค้ดใหญ่ขึ้น
3. **Test บ่อยๆ** - ทดสอบหลังย้ายไฟล์ทุกครั้ง
4. **Backup** - เก็บ backup ก่อนจัดระเบียบ
5. **Git commit** - Commit ก่อนและหลังจัดระเบียบ

---

**พร้อมจัดระเบียบแล้ว!** รัน `python reorganize_project.py` 🗂️
