# Changelog

All notable changes to this project will be documented in this file.

## [2.0.0] - 2024-11-07

### 🎉 Major Changes - Supabase Migration

#### Changed
- **Vector Database**: Migrated from Pinecone to Supabase + pgvector
- **Detection Type**: Changed from "โรคใบ" to specific types:
  - เชื้อรา (Fungus)
  - ไวรัส (Virus)
  - ศัตรูพืช (Pest)
- **Product Source**: Now uses `Data ICPL product for iDA.csv` exclusively

#### Added
- ✨ Supabase integration with pgvector extension
- ✨ New detection categories (fungus/virus/pest)
- ✨ Enhanced Thai language responses
- 📄 `docs/SUPABASE_SETUP.md` - Complete setup guide
- 📄 `docs/MIGRATION_GUIDE.md` - Migration instructions
- 🧪 `tests/test_supabase.py` - Integration tests
- 📜 `scripts/setup_supabase.sql` - Database schema
- 🔧 `scripts/import_csv_to_supabase.py` - Data import tool

#### Removed
- ❌ Pinecone dependencies
- ❌ `scripts/setup_pinecone.py`
- ❌ `scripts/import_csv_to_pinecone.py`
- ❌ PDF import functionality (CSV only)

#### Benefits
- 💰 **Cost Savings**: Supabase free tier vs Pinecone $70/month
- 🚀 **Better Performance**: PostgreSQL + pgvector
- 🔒 **Data Control**: Self-hosted option available
- 📊 **Full Database**: SQL queries, joins, full-text search
- 🛠️ **Easier Maintenance**: Unified platform

### Technical Details

#### Dependencies Updated
```diff
- pinecone==5.4.2
+ supabase==2.3.4
+ openai==1.54.0
```

#### Environment Variables Changed
```diff
- PINECONE_API_KEY
- PINECONE_INDEX_NAME
+ SUPABASE_URL
+ SUPABASE_KEY
```

#### API Changes
- Vector search now uses Supabase RPC function `match_products`
- Metadata structure simplified for better performance
- Embedding model remains `text-embedding-3-small` (1536 dimensions)

### Migration Path

For existing users:
1. Follow [MIGRATION_GUIDE.md](docs/MIGRATION_GUIDE.md)
2. Setup Supabase project
3. Run SQL schema script
4. Import CSV data
5. Update environment variables
6. Test with `python tests/test_supabase.py`

---

## [1.0.0] - 2024-10-XX

### Initial Release

#### Features
- 🔍 Plant disease detection using OpenAI Vision
- 🎯 Product recommendations using Pinecone RAG
- 💬 LINE Messaging API integration
- 🇹🇭 Thai language support
- 📊 Minimal RAG output (5 fields)

#### Components
- FastAPI backend
- OpenAI GPT-4 Vision for image analysis
- Pinecone for vector similarity search
- LINE Messaging API for chat interface

#### Documentation
- Installation guide
- Deployment guide
- Troubleshooting guide
- CSV import guide

---

## Version Comparison

| Feature | v1.0 (Pinecone) | v2.0 (Supabase) |
|---------|-----------------|-----------------|
| Vector DB | Pinecone | Supabase + pgvector |
| Detection | โรคใบ | เชื้อรา/ไวรัส/ศัตรูพืช |
| Cost | $70/month | Free tier available |
| Database | Vector only | Full PostgreSQL |
| Self-hosted | No | Yes (optional) |
| Setup Time | 10 min | 15 min |

---

## Upgrade Notes

### Breaking Changes in v2.0

1. **Environment Variables**
   - Must update `.env` file with Supabase credentials
   - Remove Pinecone variables

2. **Data Import**
   - Must re-import data to Supabase
   - CSV format remains the same

3. **API Response**
   - Detection type now includes pest category
   - Response format slightly different

### Non-Breaking Changes

- LINE webhook URL remains the same
- Image upload process unchanged
- Product recommendation format similar
- Thai language responses improved but compatible

---

## Future Plans

### v2.1 (Planned)
- [ ] Multi-language support (English, Chinese)
- [ ] Image history tracking
- [ ] User feedback system
- [ ] Analytics dashboard

### v2.2 (Planned)
- [ ] Mobile app integration
- [ ] Batch image processing
- [ ] Advanced filtering options
- [ ] Export recommendations to PDF

### v3.0 (Planned)
- [ ] Custom model training
- [ ] Real-time notifications
- [ ] Integration with e-commerce
- [ ] Farmer community features

---

## Support

For questions about changes:
- Read [MIGRATION_GUIDE.md](docs/MIGRATION_GUIDE.md)
- Check [SUPABASE_SETUP.md](docs/SUPABASE_SETUP.md)
- Run tests: `python tests/test_supabase.py`

---

**Note**: This project follows [Semantic Versioning](https://semver.org/).
