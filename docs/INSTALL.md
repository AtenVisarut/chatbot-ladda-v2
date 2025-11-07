# Installation Guide

Complete step-by-step installation guide for LINE Plant Disease Detection Bot.

## Prerequisites

Before you begin, ensure you have:

- ✅ Python 3.9 or higher
- ✅ pip (Python package manager)
- ✅ LINE Developer Account
- ✅ Google Cloud Account (for Gemini API)
- ✅ Pinecone Account

## Step 1: Get API Keys

### 1.1 LINE Messaging API

1. Go to [LINE Developers Console](https://developers.line.biz/console/)
2. Login with your LINE account
3. Click "Create a new provider" (or use existing)
4. Click "Create a new channel" → "Messaging API"
5. Fill in required information:
   - Channel name: "Plant Disease Bot"
   - Channel description: "AI plant disease detection"
   - Category: Agriculture
6. After creation, go to "Messaging API" tab
7. Copy **Channel Access Token** (long-lived)
8. Go to "Basic settings" tab
9. Copy **Channel Secret**

### 1.2 Google Gemini API

1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Login with your Google account
3. Click "Create API Key"
4. Select or create a Google Cloud project
5. Copy the **API Key**

### 1.3 Pinecone API

1. Go to [Pinecone](https://app.pinecone.io/)
2. Sign up for free account
3. After login, go to "API Keys"
4. Copy your **API Key**
5. Note your **Environment** (e.g., us-east-1)

## Step 2: Clone or Download Project

### Option A: Using Git
```bash
git clone https://github.com/your-repo/line-plant-bot.git
cd line-plant-bot
```

### Option B: Download ZIP
1. Download project ZIP file
2. Extract to your desired location
3. Open terminal/command prompt in that folder

## Step 3: Install Python Dependencies

⚠️ **Python 3.13 Users:** See PYTHON_313_NOTES.md for compatibility information.

### Quick Test
First, verify your Python version:
```bash
python --version
```

### Windows
```bash
pip install -r requirements.txt
```

### Linux/Mac
```bash
pip3 install -r requirements.txt
```

### Verify Installation
After installing, test all imports:
```bash
python test_imports.py
```

### Using Virtual Environment (Recommended)

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**Linux/Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Step 4: Configure Environment Variables

1. Copy the example environment file:

**Windows:**
```bash
copy .env.example .env
```

**Linux/Mac:**
```bash
cp .env.example .env
```

2. Edit `.env` file with your API keys:

```env
# LINE Configuration
LINE_CHANNEL_ACCESS_TOKEN=your_actual_line_token_here
LINE_CHANNEL_SECRET=your_actual_line_secret_here

# Google Gemini API
GEMINI_API_KEY=your_actual_gemini_key_here

# Pinecone Configuration
PINECONE_API_KEY=your_actual_pinecone_key_here
PINECONE_INDEX_NAME=plant-products
```

**Important:** Replace all `your_actual_*_here` with your real API keys!

## Step 5: Setup Pinecone Index

Run the setup script:

```bash
python setup_pinecone.py
```

This will:
- Connect to Pinecone
- Create index named "plant-products"
- Configure for 768-dimensional vectors
- Use cosine similarity metric

Expected output:
```
🔧 Initializing Pinecone...
🚀 Creating new index: plant-products
⏳ This may take a minute...
✅ Index 'plant-products' created successfully!
```

## Step 6: Populate Product Data

Run the population script:

```bash
python populate_products.py
```

This will:
- Display product catalog
- Ask for confirmation
- Upload products to Pinecone

Expected output:
```
📦 Preparing to upload 8 products...
  ✓ Prepared: ปุ๋ยอินทรีย์ชีวภาพ Premium
  ✓ Prepared: สารป้องกันกำจัดโรคพืช Bio-Safe
  ...
⬆️  Uploading to Pinecone...
✅ Successfully uploaded 8 products!
```

## Step 7: Test Local Server

Start the server:

```bash
python main.py
```

Expected output:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Test health endpoint:

**Open browser:** http://localhost:8000/health

**Or use curl:**
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "services": {
    "gemini": "ok",
    "pinecone": "ok",
    "line": "ok"
  }
}
```

## Step 8: Configure LINE Webhook

### 8.1 Expose Local Server (for testing)

**Option A: Using ngrok (Recommended for testing)**

1. Download [ngrok](https://ngrok.com/download)
2. Run:
```bash
ngrok http 8000
```
3. Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`)

**Option B: Deploy to cloud (for production)**

See DEPLOYMENT.md for cloud deployment options.

### 8.2 Set Webhook in LINE Console

1. Go to [LINE Developers Console](https://developers.line.biz/console/)
2. Select your channel
3. Go to "Messaging API" tab
4. Find "Webhook settings"
5. Set Webhook URL:
   - Testing: `https://your-ngrok-url.ngrok.io/webhook`
   - Production: `https://your-domain.com/webhook`
6. Click "Verify" (should show success)
7. Enable "Use webhook"
8. Disable "Auto-reply messages"
9. Disable "Greeting messages"

## Step 9: Test with LINE

1. In LINE Developers Console, find your bot's QR code
2. Scan QR code with LINE app to add bot as friend
3. Send a text message (should get help message)
4. Send a plant image (should get disease analysis)

## Troubleshooting

### Issue: "Module not found" error

**Solution:**
```bash
pip install -r requirements.txt --upgrade
```

### Issue: "Invalid API key" error

**Solution:**
- Double-check API keys in `.env` file
- Ensure no extra spaces or quotes
- Verify keys are active in respective consoles

### Issue: "Pinecone connection failed"

**Solution:**
- Verify PINECONE_API_KEY is correct
- Check internet connection
- Ensure Pinecone account is active

### Issue: "LINE webhook verification failed"

**Solution:**
- Ensure server is running
- Check webhook URL is HTTPS
- Verify LINE_CHANNEL_SECRET is correct
- Check server logs for errors

### Issue: "Port 8000 already in use"

**Solution:**

**Windows:**
```bash
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

**Linux/Mac:**
```bash
lsof -ti:8000 | xargs kill -9
```

Or run on different port:
```bash
uvicorn main:app --port 8001
```

### Issue: "Gemini API quota exceeded"

**Solution:**
- Check your Google Cloud quota
- Wait for quota reset
- Upgrade to paid plan if needed

## Verification Checklist

Before going to production, verify:

- [ ] All dependencies installed
- [ ] `.env` file configured with real API keys
- [ ] Pinecone index created
- [ ] Products uploaded to Pinecone
- [ ] Local server starts without errors
- [ ] Health endpoint returns "healthy"
- [ ] LINE webhook verified successfully
- [ ] Bot responds to text messages
- [ ] Bot analyzes plant images correctly
- [ ] Responses are in Thai language
- [ ] Error handling works (test with invalid image)

## Next Steps

After successful installation:

1. **For Development:**
   - Keep using ngrok for testing
   - Monitor logs for errors
   - Test with various plant images

2. **For Production:**
   - Deploy to cloud platform (see DEPLOYMENT.md)
   - Set up monitoring and alerts
   - Configure auto-scaling
   - Set up backup procedures

## Getting Help

If you encounter issues:

1. Check logs in terminal
2. Review error messages
3. Consult README.md
4. Check DEPLOYMENT.md for deployment issues
5. Review PAYLOAD_EXAMPLES.md for API examples

## Quick Reference

### Start Server
```bash
python main.py
```

### Test Health
```bash
curl http://localhost:8000/health
```

### View Logs
Logs appear in terminal where server is running

### Stop Server
Press `Ctrl+C` in terminal

### Update Dependencies
```bash
pip install -r requirements.txt --upgrade
```

---

**Installation Complete!** 🎉

Your LINE Plant Disease Detection Bot is ready to use.
