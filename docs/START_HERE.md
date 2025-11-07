# 🌱 START HERE - LINE Plant Disease Detection Bot

Welcome! This is your complete guide to get started quickly.

## 📋 What You Have

A production-ready AI chatbot that:
- ✅ Receives plant images via LINE chat
- ✅ Detects diseases using Google Gemini Vision
- ✅ Recommends products using Pinecone RAG
- ✅ Responds in Thai language
- ✅ Ready for deployment

## 🚀 Quick Start (3 Steps)

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Configure API Keys
```bash
# Copy example file
cp .env.example .env

# Edit .env with your keys:
# - LINE_CHANNEL_ACCESS_TOKEN
# - LINE_CHANNEL_SECRET
# - GEMINI_API_KEY
# - PINECONE_API_KEY
```

### Step 3: Run Setup & Start
```bash
# Setup Pinecone
python setup_pinecone.py

# Add products
python populate_products.py

# Start server
python main.py
```

**That's it!** Server runs on http://localhost:8000

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| **INSTALL.md** | Complete installation guide |
| **README.md** | Full documentation & features |
| **DEPLOYMENT.md** | Deploy to cloud platforms |
| **PAYLOAD_EXAMPLES.md** | API examples & flow |
| **PROJECT_SUMMARY.md** | Architecture overview |

## 🔑 Getting API Keys

### LINE (Required)
1. Go to https://developers.line.biz/console/
2. Create Messaging API channel
3. Get Channel Access Token & Secret

### Google Gemini (Required)
1. Go to https://makersuite.google.com/app/apikey
2. Create API key
3. Copy key

### Pinecone (Required)
1. Go to https://app.pinecone.io/
2. Sign up free
3. Get API key

## 📁 Project Files

```
├── main.py                    ⭐ Main application
├── requirements.txt           📦 Dependencies
├── .env.example              🔧 Config template
│
├── setup_pinecone.py         🗄️ Setup database
├── populate_products.py      📊 Add products
├── test_webhook.py           🧪 Test webhook
│
├── quickstart.sh/.bat        ⚡ Auto setup
├── Dockerfile                🐳 Docker config
│
└── Documentation/
    ├── INSTALL.md            📖 Installation
    ├── README.md             📖 Full docs
    ├── DEPLOYMENT.md         📖 Deploy guide
    ├── PAYLOAD_EXAMPLES.md   📖 API examples
    └── PROJECT_SUMMARY.md    📖 Overview
```

## 🎯 What Each File Does

### Core Application
- **main.py** - FastAPI server with all business logic
  - Disease detection with Gemini Vision
  - Product recommendations with Pinecone RAG
  - LINE webhook handling
  - Thai response generation

### Setup Scripts
- **setup_pinecone.py** - Creates Pinecone vector database
- **populate_products.py** - Uploads product catalog
- **test_webhook.py** - Tests LINE webhook locally

### Configuration
- **.env.example** - Template for API keys
- **requirements.txt** - Python packages needed
- **Dockerfile** - Container configuration

### Quick Start
- **quickstart.sh** - Auto setup for Linux/Mac
- **quickstart.bat** - Auto setup for Windows

## 🔄 Complete Flow

```
1. User sends plant image to LINE bot
   ↓
2. LINE sends webhook to your server
   ↓
3. Server downloads image from LINE
   ↓
4. Gemini Vision analyzes image
   → Detects: "โรคใบจุด" (Leaf spot disease)
   ↓
5. Pinecone searches for relevant products
   → Finds: Top 5 matching products
   ↓
6. Gemini LLM generates Thai response
   → Combines disease info + products
   ↓
7. Server replies to LINE user
   ↓
8. User receives analysis in Thai
```

## ⚙️ System Requirements

- Python 3.9+
- 512MB RAM minimum
- Internet connection
- LINE Developer Account
- Google Cloud Account
- Pinecone Account

## 🧪 Testing

### Test Health
```bash
curl http://localhost:8000/health
```

### Test Webhook
```bash
python test_webhook.py
```

### Test with LINE
1. Add bot as friend (scan QR in LINE console)
2. Send plant image
3. Receive analysis

## 🚀 Deployment Options

Choose one:

1. **Google Cloud Run** ⭐ Recommended
   - Serverless, auto-scaling
   - Free tier available
   - See DEPLOYMENT.md

2. **Docker**
   - Works anywhere
   - Consistent environment
   - See Dockerfile

3. **Heroku**
   - Simple deployment
   - Free tier available
   - See DEPLOYMENT.md

4. **Other Clouds**
   - AWS, Azure, DigitalOcean
   - See DEPLOYMENT.md

## 📊 Example Response

When user sends plant image:

```
🔍 ผลการตรวจสอบโรคพืช

โรคที่พบ: โรคใบจุด
ระดับความมั่นใจ: สูง
ความรุนแรง: ปานกลาง

📋 อาการที่พบ:
พบจุดสีน้ำตาลขนาดเล็กกระจายทั่วใบ

💊 ผลิตภัณฑ์แนะนำ:

🌿 ปุ๋ยอินทรีย์ชีวภาพ Premium
ปุ๋ยอินทรีย์คุณภาพสูง เสริมสร้างภูมิคุ้มกันพืช
💡 วิธีใช้: ใช้ 2-3 ครั้งต่อเดือน

🌿 สารป้องกันกำจัดโรคพืช Bio-Safe
สารชีวภาพป้องกันโรคพืช ปลอดภัย
💡 วิธีใช้: พ่นทุก 7-10 วัน

📌 คำแนะนำเพิ่มเติม:
- ตรวจสอบพืชอย่างสม่ำเสมอ
- รักษาความสะอาดแปลงปลูก
```

## 🛠️ Customization

### Add Your Products
Edit `populate_products.py`:
```python
PRODUCT_CATALOG = [
    {
        "id": "prod-001",
        "product_name": "Your Product Name",
        "description": "Product description",
        "usage": "How to use",
        ...
    }
]
```

### Modify Response Format
Edit `generate_final_response()` in `main.py`

### Change Language
Modify prompts in `detect_disease()` and `generate_final_response()`

## ❓ Common Issues

### "Module not found"
```bash
pip install -r requirements.txt
```

### "Invalid API key"
- Check `.env` file
- Verify keys in respective consoles

### "Port already in use"
```bash
# Use different port
uvicorn main:app --port 8001
```

### "Webhook verification failed"
- Ensure HTTPS (use ngrok for testing)
- Check LINE_CHANNEL_SECRET

## 📞 Need Help?

1. **Installation issues** → Read INSTALL.md
2. **Deployment issues** → Read DEPLOYMENT.md
3. **API examples** → Read PAYLOAD_EXAMPLES.md
4. **Architecture questions** → Read PROJECT_SUMMARY.md
5. **General info** → Read README.md

## ✅ Pre-Launch Checklist

Before going live:

- [ ] All API keys configured
- [ ] Pinecone index created
- [ ] Products uploaded
- [ ] Server starts without errors
- [ ] Health check returns "healthy"
- [ ] LINE webhook verified
- [ ] Test with real plant images
- [ ] Responses in Thai
- [ ] Error handling tested
- [ ] Deployed to production
- [ ] Monitoring setup

## 🎉 You're Ready!

Everything you need is here. Follow the Quick Start above and you'll be running in minutes.

**Next Steps:**
1. Get your API keys
2. Run `pip install -r requirements.txt`
3. Configure `.env`
4. Run setup scripts
5. Start server
6. Test with LINE

Good luck! 🚀

---

**Questions?** Check the documentation files listed above.
