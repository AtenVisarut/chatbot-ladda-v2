# ⚡ Quick Deploy Guide (5 นาที)

คู่มือ Deploy แบบเร็วสำหรับคนรีบ

## 🎯 ขั้นตอนสั้นๆ

### 1. เตรียม API Keys (2 นาที)

```bash
# LINE Bot
https://developers.line.biz/console/
→ Create Messaging API channel
→ Copy: Channel Access Token + Channel Secret

# OpenAI
https://platform.openai.com/api-keys
→ Create new secret key
→ เติมเงิน $5-10

# Supabase (ทำแล้ว ✓)
→ มี 43 products แล้ว
```

### 2. Deploy ด้วย Railway (1 นาที)

**ง่ายที่สุด - แนะนำ!**

1. ไปที่ https://railway.app
2. Sign up ด้วย GitHub
3. New Project → Deploy from GitHub
4. เลือก repo: `AtenVisarut/Chatbot-ladda`
5. เพิ่ม Environment Variables:
   ```
   LINE_CHANNEL_ACCESS_TOKEN=xxx
   LINE_CHANNEL_SECRET=xxx
   OPENAI_API_KEY=xxx
   SUPABASE_URL=xxx
   SUPABASE_KEY=xxx
   ```
6. Deploy!
7. Copy URL: `https://xxx.railway.app`

### 3. ตั้งค่า LINE Webhook (1 นาที)

1. กลับไป LINE Console
2. Messaging API → Webhook URL
3. ใส่: `https://xxx.railway.app/webhook`
4. Verify → Success!
5. Enable webhook

### 4. ทดสอบ (1 นาที)

1. Scan QR code (ใน LINE Console)
2. ส่งรูปภาพพืช
3. รอ 5-10 วินาที
4. ได้คำตอบ! 🎉

---

## 🚀 ทางเลือกอื่น

### Google Cloud Run (ฟรี tier ดีกว่า)

```bash
# ติดตั้ง gcloud CLI
https://cloud.google.com/sdk/docs/install

# Deploy
gcloud run deploy plant-disease-bot \
  --source . \
  --region asia-southeast1 \
  --allow-unauthenticated

# หรือใช้ script
./deploy.sh  # Linux/Mac
deploy.bat   # Windows
```

### Render (ฟรี)

1. https://render.com
2. New → Web Service
3. Connect GitHub repo
4. Environment: Docker
5. เพิ่ม Environment Variables
6. Deploy

---

## 💰 ค่าใช้จ่าย

| Platform | ฟรี | Paid |
|----------|-----|------|
| Railway | $5/mo | $20/mo |
| Cloud Run | 2M requests | ~$5/mo |
| Render | 750 hrs | $7/mo |
| OpenAI | - | ~$30-50/mo |

**รวม: ~$35-60/เดือน** (ส่วนใหญ่เป็น OpenAI)

---

## 🐛 แก้ปัญหาเร็ว

### Webhook Verify Failed
```bash
# ตรวจสอบ server ทำงาน
curl https://your-url.railway.app/health
```

### Bot ไม่ตอบ
```bash
# ดู logs
railway logs  # Railway
gcloud run logs tail  # Cloud Run
```

### OpenAI Error
```bash
# ตรวจสอบ billing
https://platform.openai.com/account/billing
```

---

## ✅ Checklist

- [ ] LINE Bot สร้างแล้ว
- [ ] OpenAI API key + เติมเงิน
- [ ] Deploy สำเร็จ
- [ ] Webhook URL ตั้งค่าแล้ว
- [ ] ทดสอบส่งรูปได้
- [ ] Bot ตอบกลับได้

---

## 📚 เอกสารเพิ่มเติม

- [DEPLOYMENT_PRODUCTION.md](docs/DEPLOYMENT_PRODUCTION.md) - คู่มือละเอียด
- [README.md](README.md) - ภาพรวมโปรเจค
- [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) - แก้ปัญหา

---

**เวลาทั้งหมด: ~5 นาที** ⚡

พร้อมใช้งานแล้ว! 🎉
