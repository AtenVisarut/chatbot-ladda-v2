# 🚀 Deploy ไป Render - Quick Guide

## ✅ เตรียมพร้อมแล้ว!

ไฟล์ที่จำเป็นมีครบแล้ว:
- ✅ `render.yaml` - Render configuration
- ✅ `requirements.txt` - Python dependencies
- ✅ `start.sh` - Startup script
- ✅ `app/main.py` - FastAPI app with health check
- ✅ `.gitignore` - ไม่ commit sensitive files

---

## 🎯 ขั้นตอนการ Deploy (5 นาที)

### 1️⃣ Push Code ไป GitHub

```bash
# ตรวจสอบว่ามี .gitignore
cat .gitignore

# Add และ commit
git add .
git commit -m "Ready for Render deployment with usage_period"

# Push (ถ้ายังไม่มี remote)
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main

# หรือถ้ามี remote แล้ว
git push origin main
```

### 2️⃣ สร้าง Web Service บน Render

1. ไปที่ https://render.com
2. Login ด้วย GitHub account
3. คลิก **New +** → **Web Service**
4. เลือก repository ของคุณ
5. คลิก **Connect**

### 3️⃣ Render จะอ่าน render.yaml อัตโนมัติ

Render จะตั้งค่าตาม `render.yaml`:
- ✅ Name: `line-plant-bot`
- ✅ Region: Singapore
- ✅ Plan: Free
- ✅ Build: `pip install -r requirements.txt`
- ✅ Start: `./start.sh`

### 4️⃣ เพิ่ม Environment Variables

ใน Render Dashboard → **Environment** tab:

```
LINE_CHANNEL_ACCESS_TOKEN=your_token_here
LINE_CHANNEL_SECRET=your_secret_here
GEMINI_API_KEY=your_gemini_key_here
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_key_here
```

⚠️ **สำคัญ:** คัดลอกจาก `.env` ของคุณ

### 5️⃣ Deploy!

1. คลิก **Create Web Service**
2. รอ 5-10 นาที (download E5 model ใช้เวลานาน)
3. ดู logs:
   ```
   ✓ E5 model ready!
   ✓ Starting FastAPI server...
   ✓ Application startup complete
   ```

### 6️⃣ ตั้งค่า LINE Webhook

1. คัดลอก Render URL: `https://line-plant-bot.onrender.com`
2. ไปที่ LINE Developers Console
3. เลือก Channel → **Messaging API**
4. ตั้งค่า Webhook URL:
   ```
   https://line-plant-bot.onrender.com/webhook
   ```
5. เปิด **Use webhook**: ON
6. คลิก **Verify** → ควรเห็น **Success** ✅

---

## 🧪 ทดสอบ

### ทดสอบ API

```bash
# Health check
curl https://line-plant-bot.onrender.com/

# ควรได้
{"status":"ok","service":"LINE Plant Disease Detection Bot","version":"1.0.0"}
```

### ทดสอบใน LINE

1. เพิ่ม LINE Bot เป็นเพื่อน
2. ส่งรูปภาพโรคพืช
3. ตรวจสอบว่า Bot ตอบกลับพร้อม **"ช่วงการใช้"**

ตัวอย่างที่ควรเห็น:
```
💊 ผลิตภัณฑ์แนะนำ:

1. โมเดิน 50
   สารสำคัญ: OMETHOATE 50% W/V SL
   ศัตรูพืช: เพลี้ยไฟ เพลี้ยจักจั่นฝอย
   ใช้กับพืช: ปลอดภัยใช้ได้ทุกพืช
   ช่วงการใช้: ป้องกันแมลงในระยะแตกใบอ่อน ⬅️ ต้องมี!
   อัตราใช้: 300 ซีซีต่อ 200 ลิตร
```

---

## 📊 ดู Logs

ใน Render Dashboard → **Logs** tab:

**Logs ที่ดี:**
```
Checking E5 model...
Loading E5 model...
E5 model ready!

Starting FastAPI server...
==========================================
E5 model initialized successfully (768 dimensions)
Supabase initialized successfully (fallback)
Gemini initialized successfully (gemini-2.5-flash)
Using Supabase Vector Search + Gemini Filtering
Application startup complete.
Uvicorn running on http://0.0.0.0:10000
```

---

## ⚠️ ข้อควรระวัง (Free Tier)

### 1. Service จะ Sleep
- Free tier sleep หลัง 15 นาที ไม่ใช้งาน
- Cold start ใช้เวลา 30-60 วินาที
- ครั้งแรกที่ใช้หลัง sleep จะช้า

**วิธีแก้:**
- ใช้ UptimeRobot ping ทุก 10 นาที (ฟรี)
- หรือ upgrade เป็น Starter plan ($7/month)

### 2. E5 Model Download
- ครั้งแรก deploy จะ download E5 model (500MB+)
- ใช้เวลา 5-10 นาที
- Deploy ครั้งต่อไปจะเร็วขึ้น (มี cache)

### 3. Memory Limit
- Free tier: 512MB RAM
- E5 model ใช้ RAM ประมาณ 300-400MB
- ถ้า out of memory → upgrade เป็น Starter

---

## 🔄 Auto-Deploy

Render จะ auto-deploy เมื่อ push code ใหม่:

```bash
# แก้ไข code
git add .
git commit -m "Update: Fix bug"
git push origin main

# Render จะ deploy อัตโนมัติ
```

---

## 💰 ค่าใช้จ่าย

| Plan | ราคา | RAM | Features |
|------|------|-----|----------|
| **Free** | ฟรี | 512MB | Sleep หลัง 15 นาที, 750 ชม/เดือน |
| **Starter** | $7/เดือน | 512MB | Always on, ไม่ sleep |
| **Standard** | $25/เดือน | 2GB | Dedicated CPU, Auto-scaling |

**คำแนะนำ:**
- ทดสอบใช้ **Free** ก่อน
- ใช้งานจริงควร upgrade เป็น **Starter** ($7/เดือน)

---

## 🐛 Troubleshooting

### ปัญหา: Build Failed

```bash
# ตรวจสอบ requirements.txt
pip freeze > requirements.txt
git add requirements.txt
git commit -m "Update requirements"
git push
```

### ปัญหา: E5 Model ไม่โหลด

ดู logs ว่ามี error อะไร:
```
Error: No space left on device
```

**วิธีแก้:** Upgrade เป็น Starter plan

### ปัญหา: Webhook Verify Failed

1. ตรวจสอบ URL ถูกต้อง: `https://line-plant-bot.onrender.com/webhook`
2. ตรวจสอบ Environment Variables ครบ
3. ดู Render logs มี error อะไร

### ปัญหา: Bot ไม่ตอบ

1. ตรวจสอบ service ยัง running อยู่
2. ดู logs มี error อะไร
3. ทดสอบ health check: `curl https://line-plant-bot.onrender.com/`

---

## ✅ Checklist

- [ ] Push code ไป GitHub
- [ ] สร้าง Web Service บน Render
- [ ] ตั้งค่า Environment Variables (5 ตัว)
- [ ] Deploy สำเร็จ (ดู logs)
- [ ] ตั้งค่า LINE Webhook
- [ ] Verify webhook สำเร็จ
- [ ] ทดสอบส่งรูปภาพใน LINE
- [ ] ตรวจสอบว่า "ช่วงการใช้" แสดงผล

---

## 🎉 สำเร็จ!

หลัง deploy สำเร็จ:
- ✅ Bot ทำงานบน Render
- ✅ ตอบกลับอัตโนมัติใน LINE
- ✅ แสดง "ช่วงการใช้" ครบถ้วน
- ✅ ใช้ E5 model (ฟรี, ไม่เสีย API cost)

---

**เวลาที่ใช้:** 10-15 นาที  
**ค่าใช้จ่าย:** ฟรี (Free tier)  
**Status:** Ready to Deploy ✅
