# LINE Plant Pest & Disease Detection Bot 🌱

AI-powered plant pest and disease detection system using LINE Messaging API, OpenAI Vision, and Supabase RAG.

ระบบตรวจจับเชื้อรา ไวรัส และศัตรูพืช พร้อมแนะนำผลิตภัณฑ์ป้องกันกำจัด

## ✨ Features

- 🔍 **Pest & Disease Detection**: Analyze plant images using OpenAI Vision API
  - ตรวจจับเชื้อรา (Fungus) - แอนแทรคโนส, ใบไหม้, ราน้ำค้าง
  - ตรวจจับไวรัส (Virus) - โรคใบด่าง, โรคใบหงิก
  - ตรวจจับศัตรูพืช (Pest) - เพลี้ยไฟ, หนอน, แมลง, ไร
- 🎯 **Product Recommendations**: RAG-based product suggestions from Supabase
- 💬 **LINE Integration**: Seamless chat interface via LINE Messaging API
- 🇹🇭 **Thai Language**: Full Thai language support
- 📊 **Minimal Output**: Clean, focused recommendations (5 key fields)
- 🌱 **ICPL Products**: Recommendations from Data ICPL product catalog

## 🏗️ Tech Stack

- **Backend**: FastAPI (Python)
- **AI Vision**: OpenAI GPT-4 Vision
- **Vector DB**: Supabase + pgvector
- **Embeddings**: OpenAI text-embedding-3-small
- **Messaging**: LINE Messaging API
- **Database**: PostgreSQL (via Supabase)

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```env
LINE_CHANNEL_ACCESS_TOKEN=your_line_token
LINE_CHANNEL_SECRET=your_line_secret
OPENAI_API_KEY=your_openai_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
```

### 3. Setup Supabase

1. สร้าง Supabase project
2. รัน SQL script: `scripts/setup_supabase.sql`
3. Import ข้อมูล:

```bash
python scripts/import_csv_to_supabase.py
```

### 4. Test Connection

```bash
python tests/test_supabase.py
```

### 5. Run Server

```bash
python app/main.py
```

Server will start at `http://localhost:8000`

## 📖 Documentation

- [Supabase Setup Guide](docs/SUPABASE_SETUP.md) ⭐ **NEW**
- [Migration Guide (Pinecone → Supabase)](docs/MIGRATION_GUIDE.md) ⭐ **NEW**
- [Installation Guide](docs/INSTALL.md)
- [Deployment Guide](docs/DEPLOYMENT.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [CSV Import Guide](docs/CSV_IMPORT_GUIDE.md)

## 🔄 How It Works

1. **User sends image** via LINE chat
2. **OpenAI Vision** analyzes the image for pest/disease
   - Identifies: เชื้อรา, ไวรัส, or ศัตรูพืช
3. **Embedding generation** creates vector from pest/disease info
4. **Supabase search** finds relevant products using pgvector
5. **Response generation** creates friendly Thai message
6. **LINE reply** sends recommendations back to user

## 🐛 Detection Types

### เชื้อรา (Fungus)
- แอนแทรคโนส (Anthracnose)
- ใบไหม้ (Leaf blight)
- ราน้ำค้าง (Powdery mildew)
- ราสนิม (Rust)

### ไวรัส (Virus)
- โรคใบด่าง (Mosaic virus)
- โรคใบหงิก (Leaf curl)

### ศัตรูพืช (Pest)
- เพลี้ยไฟ (Thrips)
- หนอน (Caterpillars)
- แมลง (Insects)
- ไร (Mites)

## 📊 Product Recommendations

ระบบจะแนะนำผลิตภัณฑ์จาก **Data ICPL product for iDA.csv** โดยแสดง:

1. **ชื่อสินค้า** (Product Name)
2. **สารสำคัญ** (Active Ingredient)
3. **ศัตรูพืชที่กำจัดได้** (Target Pest)
4. **ใช้ได้กับพืช** (Applicable Crops)
5. **วิธีใช้** (How to Use)

## 🧪 Testing

### Test Supabase Connection

```bash
python tests/test_supabase.py
```

### Test API Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Root endpoint
curl http://localhost:8000/
```

### Test LINE Webhook

1. Use ngrok to expose local server:
```bash
ngrok http 8000
```

2. Update LINE webhook URL with ngrok URL

3. Send test image via LINE chat

## 🌐 Deployment

### Google Cloud Run

```bash
gcloud run deploy plant-bot \
  --source . \
  --platform managed \
  --region asia-southeast1 \
  --allow-unauthenticated
```

### Docker

```bash
docker build -t plant-bot .
docker run -p 8000:8000 --env-file .env plant-bot
```

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed instructions.

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Bot access token | Yes |
| `LINE_CHANNEL_SECRET` | LINE Bot channel secret | Yes |
| `OPENAI_API_KEY` | OpenAI API key | Yes |
| `SUPABASE_URL` | Supabase project URL | Yes |
| `SUPABASE_KEY` | Supabase anon key | Yes |

## 📁 Project Structure

```
.
├── app/
│   └── main.py              # FastAPI application
├── scripts/
│   ├── setup_supabase.sql   # Database schema
│   └── import_csv_to_supabase.py  # Data import
├── tests/
│   └── test_supabase.py     # Integration tests
├── docs/
│   ├── SUPABASE_SETUP.md    # Setup guide
│   ├── MIGRATION_GUIDE.md   # Migration guide
│   └── ...
├── Data ICPL product for iDA.csv  # Product data
├── requirements.txt         # Python dependencies
└── .env                     # Configuration (create this)
```

## 🆕 What's New (Supabase Migration)

### Changed
- ✅ Migrated from Pinecone to Supabase + pgvector
- ✅ Detection now identifies เชื้อรา/ไวรัส/ศัตรูพืช (not just "โรคใบ")
- ✅ Product recommendations from ICPL CSV data
- ✅ Improved Thai language responses

### Benefits
- 💰 Lower cost (Supabase free tier vs Pinecone $70/mo)
- 🚀 Full PostgreSQL database capabilities
- 🔒 Better data control and security
- 📈 Easier to scale and maintain

## 🐛 Troubleshooting

### "Supabase connection failed"
- Check SUPABASE_URL and SUPABASE_KEY in .env
- Verify Supabase project is active
- Run `python tests/test_supabase.py`

### "No products found"
- Run import script: `python scripts/import_csv_to_supabase.py`
- Check products table in Supabase dashboard
- Verify CSV file exists

### "OpenAI API error"
- Check OPENAI_API_KEY is valid
- Verify API quota/billing
- Check internet connection

See [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for more solutions.

## 📝 License

This project is for educational and commercial use.

## 🤝 Contributing

Contributions welcome! Please read the documentation first.

## 📧 Support

For issues and questions:
1. Check [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
2. Review [SUPABASE_SETUP.md](docs/SUPABASE_SETUP.md)
3. Test with `python tests/test_supabase.py`

---

**Version**: 2.0 (Supabase)  
**Last Updated**: 2024  
**Status**: Production Ready ✅
