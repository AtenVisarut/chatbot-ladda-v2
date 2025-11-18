# 📁 Project Structure

โครงสร้าง Project หลังจาก Cleanup (2024-11-18)

```
LINE-Plant-Disease-Bot/
│
├── 📱 app/                          # โค้ดหลักของแอปพลิเคชัน
│   ├── __pycache__/
│   └── main.py                      # FastAPI application (2,220 lines)
│
├── 📚 docs/                         # เอกสารทั้งหมด
│   ├── ACCURACY_IMPROVEMENTS.md     # การปรับปรุงความแม่นยำ
│   ├── ADVANCED_FEATURES.md         # ฟีเจอร์ขั้นสูง
│   ├── CSV_IMPORT_GUIDE.md          # คู่มือ import CSV
│   ├── CSV_STRUCTURE.md             # โครงสร้าง CSV
│   ├── DEPLOYMENT_PRODUCTION.md     # คู่มือ deploy (หลัก)
│   ├── FIX_PDF_INSTALL.md           # แก้ปัญหา PDF
│   ├── INSTALL.md                   # คู่มือติดตั้ง
│   ├── INTENT_BASED_RECOMMENDATION.md  # Intent-based system
│   ├── MIGRATION_GUIDE.md           # คู่มือ migrate
│   ├── PRODUCT_QUERY_ENHANCEMENT.md # การปรับปรุง product query
│   ├── PRODUCT_QUERY_EXAMPLES.md    # ตัวอย่าง product query
│   ├── START_HERE.md                # เริ่มต้นที่นี่
│   └── SYSTEM_FLOW_EXPLAINED.md     # อธิบาย system flow
│
├── 🧪 tests/                        # ไฟล์ทดสอบ
│   ├── load_test.py                 # Load testing script
│   ├── LOAD_TESTING.md              # คู่มือ load testing
│   ├── test_imports.py              # ทดสอบ imports
│   ├── test_line_image.py           # ทดสอบ LINE image
│   ├── test_supabase.py             # ทดสอบ Supabase
│   └── test_webhook.py              # ทดสอบ LINE webhook
│
├── 🔧 scripts/                      # Scripts สำหรับ setup
│   ├── __pycache__/
│   ├── clear_products.py            # ลบข้อมูล products
│   ├── create_conversation_memory_table.sql  # สร้าง memory table
│   ├── create_match_products_function.sql    # สร้าง RPC function
│   ├── generate_embeddings.py       # Generate embeddings
│   ├── import_csv_to_supabase.py    # Import CSV ไป Supabase
│   ├── import_direct_sql.py         # Import ด้วย SQL
│   ├── import_fixed_vectors.py      # Import vectors
│   ├── import_with_direct_ip.py     # Import ด้วย direct IP
│   ├── import_with_embeddings.py    # Import พร้อม embeddings
│   ├── import_without_embeddings.py # Import ไม่มี embeddings
│   ├── preview_csv.py               # ดูตัวอย่าง CSV
│   ├── preview_files.py             # ดูตัวอย่างไฟล์
│   ├── preview_pdf.py               # ดูตัวอย่าง PDF
│   ├── setup_complete_vector_db.sql # Setup vector database
│   ├── setup_knowledge_e5_768.sql   # Setup knowledge table
│   └── setup_supabase.sql           # Setup Supabase
│
├── ⚙️ config/                       # ไฟล์ config
│   ├── PAYLOAD_EXAMPLES.md          # ตัวอย่าง payload
│   ├── PROJECT_STRUCTURE.md         # โครงสร้าง project (เก่า)
│   └── PROJECT_SUMMARY.md           # สรุป project
│
├── 📊 logs/                         # Log files
│   └── .gitkeep
│
├── 📄 Root Files                    # ไฟล์ที่ root
│   ├── .dockerignore                # Docker ignore rules
│   ├── .env                         # Environment variables (ไม่ commit)
│   ├── .gitignore                   # Git ignore rules
│   ├── CLEANUP_REPORT.md            # รายงานการลบไฟล์
│   ├── Data ICPL product for iDA.csv  # ข้อมูลผลิตภัณฑ์
│   ├── deploy.bat                   # Windows deployment script
│   ├── Dockerfile                   # Docker configuration
│   ├── FEATURE_IDEAS.md             # ไอเดียฟีเจอร์ใหม่
│   ├── fly.toml                     # Fly.io config
│   ├── KNOWLEDGE_TABLE_GUIDE.md     # คู่มือ knowledge table
│   ├── PERFORMANCE_IMPROVEMENTS.md  # สรุปการปรับปรุง performance
│   ├── PROJECT_STRUCTURE.md         # ไฟล์นี้
│   ├── QUICK_START_PERFORMANCE.md   # Quick start guide
│   ├── railway.json                 # Railway config
│   ├── README.md                    # เอกสารหลัก
│   ├── render.yaml                  # Render config
│   ├── requirements.txt             # Python dependencies
│   ├── SYSTEM_DIAGRAM.md            # System diagram
│   └── fix_cache_issue.md           # แก้ปัญหา cache
│
└── 🐍 venv311/                      # Virtual environment (ไม่ commit)
```

---

## 📊 สถิติ

### จำนวนไฟล์:
- **Core Code:** 1 ไฟล์ (main.py)
- **Documentation:** 17 ไฟล์
- **Tests:** 6 ไฟล์
- **Scripts:** 21 ไฟล์
- **Config:** 3 ไฟล์
- **Root Files:** 16 ไฟล์

### ขนาดโค้ด:
- **app/main.py:** ~2,220 lines
- **Total Python Code:** ~3,000+ lines
- **Documentation:** ~5,000+ lines

---

## 🎯 ไฟล์สำคัญ

### 1. Core Application
```
app/main.py                          # FastAPI application
├── Caching System                   # ลด API cost 90%
├── Rate Limiting                    # ป้องกัน spam
├── Memory Cleanup                   # ป้องกัน memory leak
├── Disease Detection                # Gemini Vision
├── Product Recommendation           # Supabase Vector Search
├── Knowledge Base Q&A               # RAG system
└── LINE Webhook Handler             # LINE integration
```

### 2. Setup Scripts (ใช้ครั้งแรก)
```
scripts/setup_supabase.sql           # Setup database
scripts/setup_knowledge_e5_768.sql   # Setup knowledge table
scripts/import_csv_to_supabase.py    # Import products
scripts/generate_embeddings.py       # Generate embeddings
```

### 3. Testing
```
tests/load_test.py                   # Load testing
tests/test_supabase.py               # Supabase connection test
tests/test_webhook.py                # LINE webhook test
```

### 4. Documentation
```
README.md                            # เอกสารหลัก
docs/START_HERE.md                   # เริ่มต้นใช้งาน
docs/INSTALL.md                      # คู่มือติดตั้ง
docs/DEPLOYMENT_PRODUCTION.md        # คู่มือ deploy
PERFORMANCE_IMPROVEMENTS.md          # Performance guide
QUICK_START_PERFORMANCE.md           # Quick start
```

---

## 🚀 Quick Start

### 1. ติดตั้ง
```bash
pip install -r requirements.txt
```

### 2. Setup Database
```bash
# รัน SQL scripts ใน Supabase
# 1. setup_supabase.sql
# 2. setup_knowledge_e5_768.sql
# 3. create_conversation_memory_table.sql
# 4. create_match_products_function.sql

# Import ข้อมูล
python scripts/import_csv_to_supabase.py
```

### 3. Configure
```bash
# แก้ไข .env
LINE_CHANNEL_ACCESS_TOKEN=xxx
LINE_CHANNEL_SECRET=xxx
GEMINI_API_KEY=xxx
SUPABASE_URL=xxx
SUPABASE_KEY=xxx
```

### 4. Run
```bash
python app/main.py
```

### 5. Test
```bash
python tests/test_supabase.py
python tests/load_test.py
```

---

## 📚 Documentation Guide

### เริ่มต้นใช้งาน:
1. **README.md** - ภาพรวม project
2. **docs/START_HERE.md** - เริ่มต้นที่นี่
3. **docs/INSTALL.md** - ติดตั้งทีละขั้นตอน

### Deploy:
1. **docs/DEPLOYMENT_PRODUCTION.md** - คู่มือ deploy (หลัก)
2. **QUICK_START_PERFORMANCE.md** - Quick start guide

### Performance:
1. **PERFORMANCE_IMPROVEMENTS.md** - สรุปการปรับปรุง
2. **tests/LOAD_TESTING.md** - คู่มือ load testing

### Advanced:
1. **docs/ADVANCED_FEATURES.md** - ฟีเจอร์ขั้นสูง
2. **docs/INTENT_BASED_RECOMMENDATION.md** - Intent system
3. **docs/PRODUCT_QUERY_ENHANCEMENT.md** - Product query

---

## 🔄 Development Workflow

### 1. Local Development
```bash
# เริ่ม server
python app/main.py

# ทดสอบ
python tests/test_supabase.py

# Load test
python tests/load_test.py
```

### 2. Before Deploy
```bash
# ตรวจสอบ code
python -m py_compile app/main.py

# ทดสอบ
python tests/test_supabase.py
python tests/load_test.py

# ตรวจสอบ dependencies
pip list
```

### 3. Deploy
```bash
# Google Cloud Run
gcloud run deploy plant-disease-bot --source .

# หรือใช้ Docker
docker build -t plant-disease-bot .
docker run -p 8000:8000 plant-disease-bot
```

---

## 🛠️ Maintenance

### ทุกวัน:
- ตรวจสอบ logs
- ดู cache stats: `curl http://localhost:8000/cache/stats`

### ทุกสัปดาห์:
- รัน load test
- ตรวจสอบ API usage
- Update dependencies

### ทุกเดือน:
- Review performance metrics
- Update documentation
- Backup database

---

## 📞 Support

### ปัญหาที่พบบ่อย:

1. **Server ไม่ start:**
   ```bash
   # ตรวจสอบ dependencies
   pip install -r requirements.txt
   
   # ตรวจสอบ .env
   cat .env
   ```

2. **Supabase connection failed:**
   ```bash
   python tests/test_supabase.py
   ```

3. **Rate limiting ไม่ทำงาน:**
   ```bash
   pip install slowapi==0.1.9
   ```

### Documentation:
- **README.md** - เอกสารหลัก
- **docs/START_HERE.md** - เริ่มต้น
- **CLEANUP_REPORT.md** - รายงานการลบไฟล์

---

**Version:** 2.0 (After Cleanup)  
**Last Updated:** 2024-11-18  
**Status:** Production Ready ✅
