# 🚀 คู่มือ Deploy ไป Render.com

## 📋 ข้อมูลเบื้องต้น

**Render.com** เป็น Platform-as-a-Service (PaaS) ที่:
- ✅ มี Free Tier (750 ชั่วโมง/เดือน)
- ✅ Deploy ง่าย จาก GitHub
- ✅ รองรับ Python/FastAPI
- ✅ Auto-deploy เมื่อ push code
- ⚠️ Free tier จะ sleep หลังไม่มีการใช้งาน 15 นาที

---

## 🎯 ขั้นตอนการ Deploy

### ขั้นตอนที่ 1: เตรียม Code

**1.1 ตรวจสอบไฟล์สำคัญ**

ตรวจสอบว่ามีไฟล์เหล่านี้:
- ✅ `requirements.txt` - Python dependencies
- ✅ `app/main.py` - FastAPI application
- ✅ `.gitignore` - ไม่ commit .env
- ✅ `render.yaml` - Render configuration (optional)

**1.2 สร้าง/อัปเดต `.gitignore`**

```gitignore
# Environment
.env
venv/
venv311/
__pycache__/
*.pyc

# Data files
*.csv
*.pdf

# IDE
.vscode/
.idea/

# Logs
logs/
*.log
```

**1.3 สร้าง `start.sh` (สำหรับ Render)**

```bash
#!/bin/bash
# Download E5 model on first run
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-base')"

# Start the server
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

ทำให้ executable:
```bash
chmod +x start.sh
```

---

### ขั้นตอนที่ 2: Push Code ไป GitHub

**2.1 สร้าง Git Repository (ถ้ายังไม่มี)**

```bash
git init
git add .
git commit -m "Initial commit - Ready for Render deployment"
```

**2.2 สร้าง Repository บน GitHub**

1. ไปที่ https://github.com/new
2. ตั้งชื่อ repository เช่น `line-plant-disease-bot`
3. เลือก **Private** (แนะนำ)
4. คลิก **Create repository**

**2.3 Push Code**

```bash
git remote add origin https://github.com/YOUR_USERNAME/line-plant-disease-bot.git
git branch -M main
git push -u origin main
```

---

### ขั้นตอนที่ 3: สร้าง Web Service บน Render

**3.1 สมัคร/Login Render**

1. ไปที่ https://render.com
2. Sign up หรือ Login (แนะนำใช้ GitHub account)

**3.2 สร้าง Web Service**

1. คลิก **New +** → **Web Service**
2. เชื่อมต่อ GitHub repository ของคุณ
3. เลือก repository `line-plant-disease-bot`
4. คลิก **Connect**

**3.3 ตั้งค่า Web Service**

กรอกข้อมูลดังนี้:

| Field | Value |
|-------|-------|
| **Name** | `line-plant-disease-bot` (หรือชื่อที่ต้องการ) |
| **Region** | `Singapore` (ใกล้ไทยที่สุด) |
| **Branch** | `main` |
| **Root Directory** | (ว่างไว้) |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `./start.sh` หรือ `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| **Instance Type** | `Free` |

---

### ขั้นตอนที่ 4: ตั้งค่า Environment Variables

ใน Render Dashboard → **Environment** tab:

คลิก **Add Environment Variable** และเพิ่ม:

```
LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
LINE_CHANNEL_SECRET=your_line_channel_secret
GEMINI_API_KEY=your_gemini_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
```

⚠️ **สำคัญ:** ห้าม commit .env ไป GitHub!

---

### ขั้นตอนที่ 5: Deploy

1. คลิก **Create Web Service**
2. รอ Render build และ deploy (ประมาณ 5-10 นาที)
3. ดู logs เพื่อตรวจสอบว่า deploy สำเร็จ

**ตรวจสอบ Logs:**
- ✅ `E5 model initialized successfully`
- ✅ `Supabase initialized successfully`
- ✅ `Gemini initialized successfully`
- ✅ `Application startup complete`

---

### ขั้นตอนที่ 6: ตั้งค่า LINE Webhook

**6.1 คัดลอก Render URL**

หลัง deploy สำเร็จ จะได้ URL เช่น:
```
https://line-plant-disease-bot.onrender.com
```

**6.2 ตั้งค่า Webhook ใน LINE Developers**

1. ไปที่ https://developers.line.biz/console/
2. เลือก Channel ของคุณ
3. ไปที่ **Messaging API** tab
4. ตั้งค่า **Webhook URL**:
   ```
   https://line-plant-disease-bot.onrender.com/webhook
   ```
5. เปิด **Use webhook**: ON
6. คลิก **Verify** เพื่อทดสอบ
7. ควรเห็น **Success** ✅

---

## 🧪 ทดสอบ

### ทดสอบ API Endpoint

```bash
# ทดสอบ health check
curl https://line-plant-disease-bot.onrender.com/

# ควรได้
{"status":"ok","message":"LINE Plant Disease Detection Bot is running"}
```

### ทดสอบใน LINE

1. เพิ่ม LINE Bot เป็นเพื่อน
2. ส่งรูปภาพโรคพืช
3. ตรวจสอบว่า Bot ตอบกลับพร้อม **ช่วงการใช้**

---

## 📊 ตรวจสอบ Logs

**ดู Real-time Logs:**
1. ไปที่ Render Dashboard
2. เลือก Web Service ของคุณ
3. คลิก **Logs** tab
4. ดู logs แบบ real-time

**ตัวอย่าง Logs ที่ดี:**
```
E5 model initialized successfully (768 dimensions)
Supabase initialized successfully (fallback)
Gemini initialized successfully (gemini-2.5-flash)
Using Supabase Vector Search + Gemini Filtering
Application startup complete.
Uvicorn running on http://0.0.0.0:10000
```

---

## ⚙️ การตั้งค่าเพิ่มเติม

### 1. Auto-Deploy

Render จะ auto-deploy เมื่อ push code ใหม่:
```bash
git add .
git commit -m "Update: Add usage_period feature"
git push origin main
```

Render จะ detect และ deploy อัตโนมัติ

### 2. Keep Service Awake (Free Tier)

Free tier จะ sleep หลัง 15 นาที ไม่มีการใช้งาน

**วิธีแก้:**
- ใช้ Cron job ping ทุก 10 นาที
- หรือ upgrade เป็น Paid plan ($7/month)

**ตัวอย่าง Cron (UptimeRobot):**
1. สมัคร https://uptimerobot.com (ฟรี)
2. เพิ่ม Monitor:
   - Type: HTTP(s)
   - URL: `https://line-plant-disease-bot.onrender.com/`
   - Interval: 5 minutes

### 3. Custom Domain (Optional)

1. ไปที่ **Settings** → **Custom Domain**
2. เพิ่ม domain ของคุณ
3. ตั้งค่า DNS ตามที่ Render แนะนำ

---

## 🐛 Troubleshooting

### ปัญหา: Build Failed

**สาเหตุ:**
- `requirements.txt` ผิด
- Python version ไม่ตรง

**วิธีแก้:**
```bash
# ตรวจสอบ requirements.txt
pip freeze > requirements.txt

# ระบุ Python version ใน render.yaml
python_version: "3.11"
```

### ปัญหา: E5 Model Download ช้า

**สาเหตุ:**
- E5 model ขนาดใหญ่ (500MB+)
- Download ทุกครั้งที่ deploy

**วิธีแก้:**
- ใช้ Render Disk (Paid feature)
- หรือใช้ OpenAI embeddings แทน

### ปัญหา: Memory Limit

**สาเหตุ:**
- Free tier มี RAM 512MB
- E5 model ใช้ RAM เยอะ

**วิธีแก้:**
1. Upgrade เป็น Starter plan ($7/month, 512MB → 2GB)
2. หรือใช้ OpenAI embeddings (ไม่ต้องโหลด model)

### ปัญหา: Service Sleep

**สาเหตุ:**
- Free tier sleep หลัง 15 นาที

**วิธีแก้:**
- ใช้ UptimeRobot ping ทุก 10 นาที
- หรือ upgrade เป็น Paid plan

---

## 💰 ค่าใช้จ่าย

### Free Tier
- ✅ 750 ชั่วโมง/เดือน (พอใช้ 1 service)
- ✅ 512MB RAM
- ✅ Shared CPU
- ⚠️ Sleep หลัง 15 นาที ไม่ใช้งาน
- ⚠️ Cold start ช้า (30-60 วินาที)

### Starter Plan ($7/month)
- ✅ Always on (ไม่ sleep)
- ✅ 512MB RAM
- ✅ Faster startup
- ✅ Custom domain

### Standard Plan ($25/month)
- ✅ 2GB RAM
- ✅ Dedicated CPU
- ✅ Auto-scaling

**คำแนะนำ:**
- ทดสอบใช้ Free tier ก่อน
- ถ้าใช้งานจริง upgrade เป็น Starter ($7/month)

---

## 📝 Checklist

ก่อน Deploy ตรวจสอบ:

- [ ] ✅ Code ทำงานได้ใน local
- [ ] ✅ มี `requirements.txt`
- [ ] ✅ มี `.gitignore` (ไม่ commit .env)
- [ ] ✅ Push code ไป GitHub
- [ ] ✅ สร้าง Web Service บน Render
- [ ] ✅ ตั้งค่า Environment Variables
- [ ] ✅ Deploy สำเร็จ
- [ ] ✅ ตั้งค่า LINE Webhook
- [ ] ✅ ทดสอบส่งรูปภาพใน LINE
- [ ] ✅ ตรวจสอบว่า usage_period แสดงผล

---

## 🎯 สรุป

**ขั้นตอนสั้นๆ:**
1. Push code ไป GitHub
2. สร้าง Web Service บน Render
3. ตั้งค่า Environment Variables
4. Deploy
5. ตั้งค่า LINE Webhook
6. ทดสอบ

**เวลาที่ใช้:** ประมาณ 15-20 นาที

**ค่าใช้จ่าย:** ฟรี (Free tier) หรือ $7/month (Starter)

---

## 📚 Resources

- Render Docs: https://render.com/docs
- LINE Messaging API: https://developers.line.biz/en/docs/messaging-api/
- FastAPI Deployment: https://fastapi.tiangolo.com/deployment/

---

**Version:** 1.0  
**Last Updated:** 2024-11-18  
**Status:** Ready to Deploy ✅
