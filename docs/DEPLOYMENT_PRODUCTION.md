# 🚀 Production Deployment Guide

คู่มือการ Deploy LINE Plant Pest & Disease Detection Bot สำหรับใช้งานจริง

## 📋 สิ่งที่ต้องเตรียม

### 1. บัญชีและ API Keys ที่จำเป็น

- ✅ **LINE Developers Account** (ฟรี)
  - LINE Channel Access Token
  - LINE Channel Secret
  
- ✅ **OpenAI Account** (มีค่าใช้จ่าย ~$0.01-0.10 ต่อรูป)
  - OpenAI API Key
  - Credit card สำหรับ billing
  
- ✅ **Supabase Account** (ฟรี หรือ $25/เดือน)
  - Supabase URL
  - Supabase Anon Key
  
- ✅ **Cloud Platform** (เลือก 1 อย่าง)
  - Google Cloud Run (แนะนำ - ฟรี tier)
  - Railway (ฟรี $5/เดือน)
  - Render (ฟรี tier)
  - Heroku ($7/เดือน)

---

## 🎯 ขั้นตอนการ Deploy (แนะนำ: Google Cloud Run)

### Step 1: เตรียม LINE Bot

#### 1.1 สร้าง LINE Channel

1. ไปที่ https://developers.line.biz/console/
2. คลิก **"Create a new provider"**
3. ตั้งชื่อ Provider (เช่น "Plant Disease Bot")
4. คลิก **"Create a Messaging API channel"**
5. กรอกข้อมูล:
   - Channel name: `Plant Disease Detection`
   - Channel description: `AI-powered plant disease detection`
   - Category: `Technology`
   - Subcategory: `AI/Machine Learning`
6. คลิก **"Create"**

#### 1.2 ตั้งค่า LINE Channel

1. ไปที่ **"Messaging API"** tab
2. เปิดใช้งาน:
   - ✅ Use webhooks: **Enabled**
   - ✅ Allow bot to join group chats: **Enabled** (ถ้าต้องการ)
   - ❌ Auto-reply messages: **Disabled**
   - ❌ Greeting messages: **Disabled**
3. Copy **Channel access token** (long-lived)
4. Copy **Channel secret**

---

### Step 2: เตรียม OpenAI API

#### 2.1 สร้าง API Key

1. ไปที่ https://platform.openai.com/api-keys
2. คลิก **"Create new secret key"**
3. ตั้งชื่อ: `plant-disease-bot`
4. Copy API key (จะแสดงครั้งเดียว!)
5. เก็บไว้ในที่ปลอดภัย

#### 2.2 เติมเงิน (Billing)

1. ไปที่ https://platform.openai.com/account/billing
2. คลิก **"Add payment method"**
3. เพิ่มบัตรเครดิต
4. เติมเงินขั้นต่ำ $5-10 (ใช้ได้นาน)

**ค่าใช้จ่ายโดยประมาณ:**
- GPT-4 Vision: ~$0.01-0.03 ต่อรูป
- Embeddings: ~$0.0001 ต่อ query
- **รวม: ~$0.01-0.05 ต่อการใช้งาน 1 ครั้ง**

---

### Step 3: Setup Supabase (ทำแล้ว)

✅ คุณทำเสร็จแล้ว! แต่ตรวจสอบอีกครั้ง:

1. Database มี 43 products ✓
2. RPC function `match_products` ทำงาน ✓
3. API keys ใช้งานได้ ✓

---

### Step 4: Deploy ไป Google Cloud Run

#### 4.1 ติดตั้ง Google Cloud CLI

**Windows:**
```powershell
# Download และติดตั้งจาก
https://cloud.google.com/sdk/docs/install
```

**หรือใช้ Cloud Shell (แนะนำ - ไม่ต้องติดตั้ง)**

#### 4.2 Login และ Setup Project

```bash
# Login
gcloud auth login

# สร้าง project ใหม่
gcloud projects create plant-disease-bot --name="Plant Disease Bot"

# Set project
gcloud config set project plant-disease-bot

# Enable APIs
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

#### 4.3 สร้าง Dockerfile (มีอยู่แล้ว)

ตรวจสอบว่ามี `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "app/main.py"]
```

#### 4.4 Deploy!

```bash
# Deploy ด้วยคำสั่งเดียว
gcloud run deploy plant-disease-bot \
  --source . \
  --platform managed \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --set-env-vars "LINE_CHANNEL_ACCESS_TOKEN=your_token" \
  --set-env-vars "LINE_CHANNEL_SECRET=your_secret" \
  --set-env-vars "OPENAI_API_KEY=your_key" \
  --set-env-vars "SUPABASE_URL=your_url" \
  --set-env-vars "SUPABASE_KEY=your_key"
```

**หรือใช้ไฟล์ .env:**

```bash
# สร้างไฟล์ .env.yaml
cat > .env.yaml << EOF
LINE_CHANNEL_ACCESS_TOKEN: "your_token"
LINE_CHANNEL_SECRET: "your_secret"
OPENAI_API_KEY: "your_key"
SUPABASE_URL: "your_url"
SUPABASE_KEY: "your_key"
EOF

# Deploy
gcloud run deploy plant-disease-bot \
  --source . \
  --platform managed \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --env-vars-file .env.yaml
```

#### 4.5 รับ URL

หลัง deploy สำเร็จ จะได้ URL เช่น:
```
https://plant-disease-bot-xxxxx-as.a.run.app
```

---

### Step 5: เชื่อม LINE Webhook

#### 5.1 ตั้งค่า Webhook URL

1. กลับไปที่ LINE Developers Console
2. ไปที่ **"Messaging API"** tab
3. ที่ **"Webhook settings"**:
   - Webhook URL: `https://your-cloud-run-url.run.app/webhook`
   - คลิก **"Update"**
   - คลิก **"Verify"** (ต้องได้ Success)
   - เปิด **"Use webhook"**: Enabled

#### 5.2 ทดสอบ

1. เปิด LINE app
2. Scan QR code ของ bot (ใน LINE Console)
3. ส่งข้อความ "สวัสดี"
4. ส่งรูปภาพพืชที่มีปัญหา
5. รอ bot ตอบกลับ (~5-10 วินาที)

---

## 🔄 ทางเลือกอื่น: Railway (ง่ายกว่า)

### Deploy ด้วย Railway

1. ไปที่ https://railway.app
2. Sign up ด้วย GitHub
3. คลิก **"New Project"**
4. เลือก **"Deploy from GitHub repo"**
5. เลือก repository: `AtenVisarut/Chatbot-ladda`
6. Railway จะ detect Dockerfile อัตโนมัติ
7. เพิ่ม Environment Variables:
   ```
   LINE_CHANNEL_ACCESS_TOKEN=xxx
   LINE_CHANNEL_SECRET=xxx
   OPENAI_API_KEY=xxx
   SUPABASE_URL=xxx
   SUPABASE_KEY=xxx
   ```
8. คลิก **"Deploy"**
9. รับ URL: `https://your-app.railway.app`
10. ตั้งค่า LINE Webhook URL

**ข้อดี:**
- ✅ ง่ายมาก ไม่ต้องใช้ CLI
- ✅ Auto-deploy เมื่อ push GitHub
- ✅ ฟรี $5/เดือน

**ข้อเสีย:**
- ❌ ฟรีแค่ $5/เดือน (พอใช้ ~500-1000 requests)

---

## 💰 ค่าใช้จ่ายโดยประมาณ

### ต่อเดือน (100 users, 10 รูป/วัน)

| Service | Free Tier | Paid | หมายเหตุ |
|---------|-----------|------|----------|
| **Supabase** | ฟรี (500MB) | $25/mo | ฟรีพอใช้ |
| **OpenAI** | - | ~$30-50/mo | ขึ้นกับการใช้งาน |
| **Google Cloud Run** | ฟรี (2M requests) | ~$0-5/mo | ฟรีพอใช้ |
| **LINE** | ฟรี | ฟรี | ฟรีตลอด |
| **รวม** | ~$30-50/mo | ~$60-80/mo | ส่วนใหญ่เป็น OpenAI |

### ลดค่าใช้จ่าย:

1. **ใช้ GPT-4o-mini แทน GPT-4o** (ถูกกว่า 10 เท่า)
2. **Cache embeddings** (ไม่ต้องสร้างใหม่ทุกครั้ง)
3. **Rate limiting** (จำกัดการใช้งานต่อ user)
4. **Batch processing** (รวม requests)

---

## 🔒 Security Best Practices

### 1. ป้องกัน API Keys

```bash
# ใช้ Secret Manager (Google Cloud)
gcloud secrets create openai-api-key --data-file=-
# paste key และ Ctrl+D

# Deploy with secret
gcloud run deploy plant-disease-bot \
  --set-secrets="OPENAI_API_KEY=openai-api-key:latest"
```

### 2. Rate Limiting

เพิ่มใน `app/main.py`:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/webhook")
@limiter.limit("10/minute")  # จำกัด 10 requests ต่อนาที
async def webhook(...):
    ...
```

### 3. Monitoring

```bash
# ดู logs
gcloud run logs read plant-disease-bot --limit=50

# ดู metrics
gcloud run services describe plant-disease-bot
```

---

## 📊 Monitoring & Maintenance

### 1. ตรวจสอบ Health

```bash
# Health check
curl https://your-app.run.app/health

# Response:
{
  "status": "healthy",
  "services": {
    "openai": "ok",
    "supabase": "ok",
    "line": "ok"
  }
}
```

### 2. ดู Logs

**Google Cloud Console:**
1. ไปที่ Cloud Run
2. คลิก service name
3. ไปที่ **"Logs"** tab

**หรือใช้ CLI:**
```bash
gcloud run logs tail plant-disease-bot
```

### 3. Alert Setup

```bash
# สร้าง alert เมื่อ error rate สูง
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="High Error Rate" \
  --condition-threshold-value=0.05
```

---

## 🐛 Troubleshooting

### ปัญหาที่พบบ่อย:

#### 1. LINE Webhook Verify Failed

**สาเหตุ:**
- URL ผิด
- Server ยังไม่ทำงาน
- Signature verification ผิด

**แก้ไข:**
```bash
# ตรวจสอบ server
curl https://your-app.run.app/

# ตรวจสอบ webhook
curl -X POST https://your-app.run.app/webhook
```

#### 2. OpenAI API Error

**สาเหตุ:**
- API key ผิด
- ไม่มีเครดิต
- Rate limit

**แก้ไข:**
```bash
# ตรวจสอบ billing
https://platform.openai.com/account/billing

# ตรวจสอบ usage
https://platform.openai.com/account/usage
```

#### 3. Supabase Connection Failed

**สาเหตุ:**
- URL หรือ Key ผิด
- Database ไม่มีข้อมูล

**แก้ไข:**
```bash
# ทดสอบ connection
python tests/test_supabase.py
```

#### 4. Slow Response

**สาเหตุ:**
- Cold start (Cloud Run)
- OpenAI API ช้า

**แก้ไข:**
```bash
# เพิ่ม min instances (ไม่ cold start)
gcloud run services update plant-disease-bot \
  --min-instances=1
```

---

## 🔄 Update & Redeploy

### วิธีที่ 1: Manual Deploy

```bash
# Pull code ใหม่
git pull origin main

# Deploy
gcloud run deploy plant-disease-bot --source .
```

### วิธีที่ 2: Auto Deploy (CI/CD)

สร้างไฟล์ `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Cloud Run

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - uses: google-github-actions/setup-gcloud@v0
        with:
          service_account_key: ${{ secrets.GCP_SA_KEY }}
          project_id: plant-disease-bot
      
      - name: Deploy
        run: |
          gcloud run deploy plant-disease-bot \
            --source . \
            --region asia-southeast1
```

---

## 📈 Scaling

### เมื่อ users เยอะขึ้น:

```bash
# เพิ่ม max instances
gcloud run services update plant-disease-bot \
  --max-instances=10

# เพิ่ม memory
gcloud run services update plant-disease-bot \
  --memory=1Gi

# เพิ่ม CPU
gcloud run services update plant-disease-bot \
  --cpu=2
```

---

## ✅ Checklist ก่อน Go Live

- [ ] LINE Bot verified
- [ ] OpenAI billing setup
- [ ] Supabase มีข้อมูล 43 products
- [ ] Deploy สำเร็จ
- [ ] Webhook URL ตั้งค่าแล้ว
- [ ] ทดสอบส่งรูปได้
- [ ] ทดสอบแนะนำผลิตภัณฑ์ได้
- [ ] Monitoring setup
- [ ] Backup plan
- [ ] Documentation อัพเดท

---

## 🎉 เสร็จแล้ว!

Bot พร้อมใช้งานจริงแล้ว! 🚀

**Next Steps:**
1. แชร์ QR code ให้ users
2. รวบรวม feedback
3. ปรับปรุงระบบ
4. เพิ่มฟีเจอร์ใหม่

**Support:**
- 📧 Email: support@example.com
- 💬 LINE: @plantbot
- 🐛 Issues: GitHub Issues

---

**Version:** 2.0  
**Last Updated:** 2024-11-07  
**Status:** Production Ready ✅
