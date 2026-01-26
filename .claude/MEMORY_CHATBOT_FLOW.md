# Chatbot Flow Memory - ระบบวินิจฉัยโรคพืชอัจฉริยะ

## Tech Stack
- **Backend**: FastAPI (Python 3.11)
- **Messaging**: LINE Messaging API
- **Vision AI**: Gemini 3 Flash (OpenRouter)
- **Chat AI**: GPT-4o-mini (OpenAI)
- **Database**: Supabase (PostgreSQL)
- **Cache**: Redis (Upstash) + In-Memory Fallback
- **Frontend**: LIFF (LINE Front-end Framework)

## File Structure
```
app/
├── main.py                      # Entry point, webhook handler
├── config.py                    # Configuration
├── models.py                    # Data models
├── services/
│   ├── disease_detection.py     # วินิจฉัยโรคด้วย Gemini Vision
│   ├── product_recommendation.py # แนะนำสินค้า (line 1892: retrieve_products_with_matching_score)
│   ├── response_generator.py    # สร้าง Flex Message
│   ├── chat.py                  # Natural language Q&A
│   ├── cache.py                 # In-Memory Cache (L1) + Supabase (L2)
│   ├── redis_cache.py           # Redis Cache สำหรับ scale-out (2026-01-26)
│   └── memory.py                # Conversation memory
├── utils/
│   └── rate_limiter.py          # Rate limiting
liff/
├── index.html                   # หน้าลงทะเบียน
├── diseases.html                # หน้าเลือกพืช
├── diseases-rice.html           # โรคข้าว
├── diseases-corn.html           # โรคข้าวโพด
├── diseases-durian.html         # โรคทุเรียน
├── diseases-cassava.html        # โรคมันสำปะหลัง
└── diseases-sugarcane.html      # โรคอ้อย
```

## Disease Detection Flow (3-Step Questions)

1. **User ส่งรูปพืช** → Check registration
2. **Step 1**: ถามชนิดพืช (บังคับ) - state: `awaiting_plant_type`
   - Quick Reply: ข้าว | ทุเรียน | ข้าวโพด | มันสำปะหลัง | อ้อย | อื่นๆ
3. **Step 2**: ถามตำแหน่ง (ข้ามได้) - state: `awaiting_position`
   - Quick Reply: ใบ | ลำต้น | ผล | ราก | กาบใบ | รวง | กิ่ง | ข้าม
4. **Step 3**: ถามลักษณะ (ข้ามได้) - state: `awaiting_symptom`
   - Quick Reply: จุดสี | ลักษณะแผล | สีของใบ | เหี่ยว/แห้ง | แมลง | ข้าม
5. **Download image** → `smart_detect_disease()` → Gemini Vision
6. **Ask growth stage** - state: `awaiting_growth_stage`
7. **Product recommendation** → `retrieve_products_with_matching_score()`

## Product Recommendation Flow

### Pre-filters
- `is_bacterial_disease()` → ไม่แนะนำ Fungicide
- `is_no_product_disease()` → โรคที่บริษัทไม่มียา (ยกเว้น HAS_PRODUCT_EXCEPTIONS)

### Search Strategy
1. **Direct Query** - ค้นหาจาก column `target_pest`
2. **Hybrid Search** (fallback ถ้า < 3 ตัว) - Vector 50% + Keyword 50%
3. **Multi-layer Filtering** - category, plant, oomycetes/fungi
4. **Scoring** - 40% target_pest + 30% plant + 30% growth_stage

### Keyword Lists
| List | Purpose |
|------|---------|
| `BACTERIAL_KEYWORDS` | โรคแบคทีเรีย → ไม่แนะนำ Fungicide |
| `NO_PRODUCT_DISEASES` | โรคที่ไม่มียา (เช่น โรคไหม้ข้าว) |
| `HAS_PRODUCT_EXCEPTIONS` | ยกเว้นจาก NO_PRODUCT (เช่น โรคไหม้คอรวง) |
| `FUNGAL_KEYWORDS` | โรคเชื้อรา |
| `INSECT_KEYWORDS` | แมลง |
| `OOMYCETES_DISEASES` | โรค Oomycetes |
| `VECTOR_DISEASES` | โรคที่มีแมลงพาหะ |

## Rate Limiting (Updated 2026-01-26)
- 10 requests / 60 seconds per user
- Image cooldown: 10 seconds between image requests
- Max concurrent analysis: 10 simultaneous requests
- Algorithm: Redis INCR with TTL (or Sliding Window for Memory fallback)
- Storage: Redis (primary) → In-Memory (fallback)

## Cache System (Two-Layer Architecture)

### Layer 1: Redis (Primary) - `app/services/redis_cache.py`
- Provider: Upstash Redis (Serverless)
- รองรับ scale-out (หลาย instances)
- ข้อมูลไม่หายเมื่อ restart

| Type | Key Pattern | TTL |
|------|-------------|-----|
| Rate Limit | `ratelimit:{user_id}` | 60 sec |
| Image Cooldown | `img_cooldown:{user_id}` | 10 sec |
| Concurrent Counter | `concurrent_analysis_count` | 300 sec |

### Layer 2: In-Memory + Supabase (Fallback) - `app/services/cache.py`
- ใช้เมื่อ Redis ไม่พร้อม
- L1: In-Memory (~0.1ms)
- L2: Supabase (~50-200ms)

| Type | Key Pattern | TTL |
|------|-------------|-----|
| Detection | `detection:{image_hash}` | 1 hour |
| Context | `context:{user_id}` | 30 min |
| Rate Limit | `ratelimit:{user_id}` | 60 sec |

## Database Tables
- `users` - ข้อมูลผู้ใช้ LINE
- `diseases` - ข้อมูลโรคพืช
- `products` - สินค้า (target_pest, product_category, pathogen_type)
- `cache` - Cache storage
- `conversation_memory` - ประวัติการสนทนา

## Important Code Locations
- **Webhook handler**: `app/main.py`
- **Product recommendation**: `app/services/product_recommendation.py:1892` (`retrieve_products_with_matching_score`)
- **Disease detection**: `app/services/disease_detection.py` (`smart_detect_disease`)
- **Cache management**: `app/services/cache.py` (In-Memory + Supabase)
- **Redis cache**: `app/services/redis_cache.py` (Scale-out support)
- **Rate limiter**: `app/utils/rate_limiter.py` (Redis + Memory fallback)

## Environment Variables (Redis)
```bash
# Upstash REST API (recommended)
UPSTASH_REDIS_REST_URL=https://xxx.upstash.io
UPSTASH_REDIS_REST_TOKEN=xxx

# Or standard Redis
REDIS_URL=redis://default:xxx@xxx:6379
```

---
*Created: 2026-01-21*
*Updated: 2026-01-26 (Redis cache, rate limiting improvements)*
*Source: flow chatbot.md v2.7*
