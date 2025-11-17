# 🚀 Quick Start: Deploy LINE Bot

## 🎯 แนะนำ: Google Cloud Run (ฟรี + เร็ว + ดีที่สุด)

---

## ⚡ Deploy ใน 5 นาที

### ขั้นตอนที่ 1: เตรียม Google Cloud

```bash
# 1. สร้าง Google Cloud account (ถ้ายังไม่มี)
# https://console.cloud.google.com

# 2. สร้าง Project ใหม่
# https://console.cloud.google.com/projectcreate

# 3. Enable Cloud Run API
# https://console.cloud.google.com/apis/library/run.googleapis.com
```

---

### ขั้นตอนที่ 2: Install Google Cloud SDK

#### Windows:
```powershell
# Download และติดตั้ง
# https://cloud.google.com/sdk/docs/install

# หรือใช้ PowerShell
(New-Object Net.WebClient).DownloadFile("https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe", "$env:Temp\GoogleCloudSDKInstaller.exe")
& $env:Temp\GoogleCloudSDKInstaller.exe
```

#### Mac:
```bash
brew install --cask google-cloud-sdk
```

#### Linux:
```bash
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
```

---

### ขั้นตอนที่ 3: Login และตั้งค่า

```bash
# 1. Login
gcloud auth login

# 2. ตั้งค่า project (แทน YOUR_PROJECT_ID ด้วย project ID ของคุณ)
gcloud config set project YOUR_PROJECT_ID

# 3. ตรวจสอบ
gcloud config list
```

---

### ขั้นตอนที่ 4: Deploy!

```bash
# Deploy ด้วยคำสั่งเดียว
gcloud run deploy line-plant-bot \
  --source . \
  --platform managed \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --min-instances 1 \
  --max-instances 10 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --set-env-vars "GEMINI_API_KEY=YOUR_GEMINI_KEY,SUPABASE_URL=YOUR_SUPABASE_URL,SUPABASE_KEY=YOUR_SUPABASE_KEY,LINE_CHANNEL_ACCESS_TOKEN=YOUR_LINE_TOKEN,LINE_CHANNEL_SECRET=YOUR_LINE_SECRET"
```

**หมายเหตุ**: แทนค่า YOUR_* ด้วยค่าจริงจากไฟล์ `.env` ของคุณ

---

### ขั้นตอนที่ 5: อัพเดท LINE Webhook

```bash
# 1. Copy URL จาก output (ตัวอย่าง)
# Service URL: https://line-plant-bot-xxx-as.a.run.app

# 2. ไปที่ LINE Developers Console
# https://developers.line.biz/console/

# 3. เลือก Channel → Messaging API

# 4. Webhook settings:
#    - Webhook URL: https://line-plant-bot-xxx-as.a.run.app/webhook
#    - Use webhook: ON
#    - Verify: คลิก "Verify"

# 5. ควรเห็น "Success" ✅
```

---

### ขั้นตอนที่ 6: ทดสอบ

```bash
# 1. ทดสอบ health check
curl https://line-plant-bot-xxx-as.a.run.app/health

# ควรได้:
# {"status":"healthy","services":{"gemini":"ok","supabase":"ok","line":"ok"}}

# 2. ทดสอบผ่าน LINE
# - เพิ่ม Bot เป็นเพื่อน (QR code ใน LINE Console)
# - ส่งข้อความ "สวัสดี"
# - ส่งรูปภาพพืช
# - ถามคำถาม "เพลี้ยไฟคืออะไร?"
```

---

## 🎉 เสร็จแล้ว!

Bot ของคุณพร้อมใช้งานแล้ว! 🚀

---

## 📊 ดู Logs และ Metrics

### ดู Logs
```bash
# Real-time logs
gcloud run services logs tail line-plant-bot --region asia-southeast1

# หรือดูใน Console
# https://console.cloud.google.com/run
```

### ดู Metrics
```bash
# ไปที่ Cloud Run Console
# https://console.cloud.google.com/run

# เลือก service → Metrics
# จะเห็น:
# - Request count
# - Request latency
# - Container instances
# - Memory usage
# - CPU usage
```

---

## 🔧 การอัพเดท

### อัพเดทโค้ด
```bash
# 1. แก้ไขโค้ด
# 2. Deploy ใหม่
gcloud run deploy line-plant-bot \
  --source . \
  --region asia-southeast1

# หรือใช้คำสั่งสั้นๆ
gcloud run deploy line-plant-bot --source .
```

### อัพเดท Environment Variables
```bash
# อัพเดทตัวแปรเดียว
gcloud run services update line-plant-bot \
  --region asia-southeast1 \
  --update-env-vars GEMINI_API_KEY=new_key

# อัพเดทหลายตัว
gcloud run services update line-plant-bot \
  --region asia-southeast1 \
  --update-env-vars "KEY1=value1,KEY2=value2"
```

---

## 💰 ค่าใช้จ่าย

### Free Tier (ต่อเดือน)
```
✅ 2 ล้าน requests
✅ 360,000 GB-seconds
✅ 180,000 vCPU-seconds

→ ใช้ฟรีได้ถ้า traffic ไม่เยอะมาก
```

### ประมาณการ
```
Traffic น้อย (< 100 users/วัน):
→ ฟรี ✅

Traffic ปานกลาง (100-1000 users/วัน):
→ $5-10/เดือน

Traffic เยอะ (> 1000 users/วัน):
→ $10-30/เดือน
```

### ดูค่าใช้จ่ายจริง
```bash
# ไปที่ Billing
# https://console.cloud.google.com/billing
```

---

## ⚙️ การตั้งค่าเพิ่มเติม

### ปรับ Auto-scaling
```bash
# เพิ่ม max instances
gcloud run services update line-plant-bot \
  --region asia-southeast1 \
  --max-instances 20

# ลด min instances (ประหยัดค่าใช้จ่าย)
gcloud run services update line-plant-bot \
  --region asia-southeast1 \
  --min-instances 0
```

### ปรับ Memory/CPU
```bash
# เพิ่ม memory
gcloud run services update line-plant-bot \
  --region asia-southeast1 \
  --memory 2Gi

# เพิ่ม CPU
gcloud run services update line-plant-bot \
  --region asia-southeast1 \
  --cpu 2
```

### ปรับ Timeout
```bash
# เพิ่ม timeout (max 3600 วินาที)
gcloud run services update line-plant-bot \
  --region asia-southeast1 \
  --timeout 600
```

---

## 🐛 Troubleshooting

### ปัญหา: Deploy ล้มเหลว

```bash
# ตรวจสอบ logs
gcloud run services logs read line-plant-bot --region asia-southeast1 --limit 50

# ตรวจสอบ build logs
gcloud builds list --limit 5
gcloud builds log BUILD_ID
```

### ปัญหา: Bot ไม่ตอบ

```bash
# 1. ตรวจสอบ health check
curl https://YOUR_URL/health

# 2. ตรวจสอบ webhook
curl -X POST https://YOUR_URL/webhook \
  -H "Content-Type: application/json" \
  -d '{"events":[]}'

# 3. ดู logs
gcloud run services logs tail line-plant-bot --region asia-southeast1
```

### ปัญหา: Environment variables ไม่ถูกต้อง

```bash
# ดู environment variables ปัจจุบัน
gcloud run services describe line-plant-bot --region asia-southeast1 --format="value(spec.template.spec.containers[0].env)"

# อัพเดท
gcloud run services update line-plant-bot \
  --region asia-southeast1 \
  --update-env-vars "KEY=value"
```

---

## 🔒 Security Best Practices

### 1. ใช้ Secret Manager (แนะนำ)
```bash
# สร้าง secret
echo -n "your-api-key" | gcloud secrets create gemini-api-key --data-file=-

# ใช้ secret ใน Cloud Run
gcloud run services update line-plant-bot \
  --region asia-southeast1 \
  --update-secrets GEMINI_API_KEY=gemini-api-key:latest
```

### 2. จำกัด Access
```bash
# ลบ public access (ถ้าไม่ต้องการ)
gcloud run services remove-iam-policy-binding line-plant-bot \
  --region asia-southeast1 \
  --member="allUsers" \
  --role="roles/run.invoker"
```

### 3. Enable VPC
```bash
# เชื่อมต่อกับ VPC (สำหรับ security เพิ่ม)
gcloud run services update line-plant-bot \
  --region asia-southeast1 \
  --vpc-connector YOUR_VPC_CONNECTOR
```

---

## 📚 เอกสารเพิ่มเติม

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud Run Pricing](https://cloud.google.com/run/pricing)
- [Cloud Run Best Practices](https://cloud.google.com/run/docs/best-practices)
- [LINE Messaging API](https://developers.line.biz/en/docs/messaging-api/)

---

## 🎯 Alternative: Deploy ด้วย Console (ไม่ต้องใช้ CLI)

### 1. ไปที่ Cloud Run Console
https://console.cloud.google.com/run

### 2. คลิก "Create Service"

### 3. เลือก "Continuously deploy from a repository"

### 4. Connect GitHub
- เลือก repository
- เลือก branch (main)

### 5. ตั้งค่า Build
- Build Type: Dockerfile
- Dockerfile path: /Dockerfile

### 6. ตั้งค่า Service
- Region: asia-southeast1 (Singapore)
- CPU allocation: CPU is always allocated
- Min instances: 1
- Max instances: 10
- Memory: 1 GiB
- CPU: 1

### 7. เพิ่ม Environment Variables
- GEMINI_API_KEY
- SUPABASE_URL
- SUPABASE_KEY
- LINE_CHANNEL_ACCESS_TOKEN
- LINE_CHANNEL_SECRET

### 8. คลิก "Create"

### 9. รอ deploy เสร็จ (~5 นาที)

### 10. Copy URL และอัพเดท LINE Webhook

---

**เสร็จแล้ว! Bot พร้อมใช้งาน 🎉**
