# IDENTITY.md — Chatbot น้องลัดดา (ICP Ladda)

> Project identity document สำหรับ AI assistant ที่จะเข้ามาทำงานต่อ
> Last updated: 2026-02-22

---

## 1. Project Overview

**Chatbot น้องลัดดา** คือ LINE / Facebook Messenger chatbot สำหรับให้คำปรึกษาเรื่องสินค้าเคมีเกษตรของ **ICP Ladda**

- **Repo**: `https://github.com/AtenVisarut/chatbot-ladda-v2.git` (branch `main`)
- **Framework**: FastAPI (Python 3.11)
- **Database**: Supabase (PostgreSQL + pgvector)
- **LLM**: OpenAI gpt-4o (ทุก agent), embedding: text-embedding-3-small
- **Deploy**: Railway (auto-deploy จาก GitHub)
- **Persona**: "น้องลัดดา" — ผู้หญิง 23 ปี พี่สาวอบอุ่น สุภาพ ภาษาง่าย

---

## 2. Architecture: 4-Agent Agentic RAG Pipeline

```
LINE / Facebook Messenger
         |
         v
  [Webhook Router]
         |
         v
  [Message Handler] --- Greeting? ---> "สวัสดีค่ะ..." (ตอบทันที)
         |
         |--- Non-Agri? ------------> General Chat (neutered LLM)
         |    (สั้น ≤20 ตัว +          temp=0.3, max_tokens=150
         |     ขอบคุณ/ลาก่อน/OK)      ห้ามพูดเรื่องเกษตร/สินค้า
         |
         v
  [Agentic RAG Pipeline] <--- DEFAULT: ทุกอย่างที่ไม่ใช่ greeting/non-agri
         |
         |====> Agent 1: Query Understanding  (gpt-4o)
         |====> Agent 2: Retrieval            (embedding + hybrid search)
         |====> Agent 3: Grounding & Citation (gpt-4o)
         |====> Agent 4: Response Generation  (gpt-4o)
         |
         v
  [Memory System] --- บันทึก user + assistant message
         |
         v
  [Reply to User] --- LINE / Facebook
```

### Routing Logic (RAG-First)

ทุกข้อความเข้า RAG pipeline เป็น default ยกเว้น:
- **Greeting**: สั้น + match keyword (สวัสดี, ดีค่ะ, hello) → ตอบทันที
- **Non-Agriculture**: สั้น ≤20 ตัว + match keyword (ขอบคุณ, 555, โอเค, ปรึกษาหน่อย) → General Chat
- ข้อความที่มี agriculture keyword (ข้าว, โรค, ยาฆ่า) → ไป RAG เสมอ แม้จะ match non-agri keyword ด้วย

---

## 3. File Structure

```
app/
├── main.py                          # FastAPI init + middleware + router includes (128 lines)
├── config.py                        # Env vars (API keys, models, thresholds)
├── dependencies.py                  # Client init (OpenAI, Supabase, Analytics)
├── prompts.py                       # System prompts + anti-hallucination constraints
│
├── routers/
│   ├── webhook.py                   # LINE webhook (follow/image/text/sticker)
│   ├── facebook_webhook.py          # FB Messenger webhook (GET verify + POST handler)
│   ├── admin.py                     # login/logout, regenerate-embeddings, cache clear
│   ├── dashboard.py                 # Dashboard HTML + analytics API
│   └── health.py                    # /, /health, /cache/stats
│
├── services/
│   ├── rag/
│   │   ├── orchestrator.py          # Pipeline orchestrator + Stage 0 pre-detection
│   │   ├── query_understanding_agent.py  # Agent 1: Intent + entity + query expansion
│   │   ├── retrieval_agent.py       # Agent 2: 10+ stage retrieval
│   │   ├── grounding_agent.py       # Agent 3: Grounding + citation verification
│   │   └── response_generator_agent.py  # Agent 4: LLM answer synthesis
│   │
│   ├── chat/
│   │   ├── handler.py               # Message routing + RAG-first logic + usage detection
│   │   └── quick_classifier.py      # Quick intent classification
│   │
│   ├── disease/
│   │   ├── constants.py             # Disease patterns + canonical names (30+ โรค)
│   │   ├── detection.py             # Image-based disease detection
│   │   ├── search.py                # Disease search utilities
│   │   ├── database.py              # Disease database operations
│   │   └── response.py              # Disease response formatting
│   │
│   ├── product/
│   │   ├── registry.py              # ProductRegistry singleton (DB-driven, auto Thai variants)
│   │   └── recommendation.py        # Product recommendation logic
│   │
│   ├── memory.py                    # Conversation memory (50 msgs, topic-aware context)
│   ├── user_service.py              # User profile tracking + user_ladda registration
│   ├── cache.py                     # Cache operations (pending context, etc.)
│   ├── analytics.py                 # Analytics tracking
│   └── welcome.py                   # Welcome messages, help menu, product catalog
│
├── utils/
│   ├── text_processing.py           # Thai variant generation, diacritics stripping, number validation
│   ├── rate_limiter.py              # Per-user rate limiting
│   ├── line/
│   │   ├── helpers.py               # LINE API: reply, push, verify signature
│   │   ├── text_messages.py         # Text message templates
│   │   └── flex_messages.py         # LINE Flex Message templates
│   └── facebook/
│       └── helpers.py               # FB API: send_message, verify_signature, split_message
│
└── api/                             # (Data Management Tool — Next.js frontend)
    ├── add-product/route.ts         # Add single product API
    └── upload-products/             # CSV upload API
```

---

## 4. RAG Pipeline Detail

### Stage 0: Pre-Detection (ไม่ใช้ LLM)

**File:** `orchestrator.py`

ก่อนเข้า Agent 1 ระบบจะ extract entities โดยไม่ใช้ LLM:

| Step | ทำอะไร | ตัวอย่าง |
|------|--------|----------|
| 0.1 | Farmer Slang Resolution (12 คำ) | "ยาดูด" → สารดูดซึม |
| 0.2 | Symptom → Pathogen Mapping | เหลือง → [ราน้ำค้าง, ขาดธาตุ] |
| 0.3 | Product Name Extraction (ProductRegistry) | "โมเดิน" → "โมเดิน 50" |
| 0.4 | Disease Name Extraction (30+ patterns) | "ราชมพู" → "ราสีชมพู" |
| 0.5 | Plant Type Extraction (26 พืช) | "ทุเรียน" |
| 0.6 | Pest Name Extraction (18 ชนิด) | "เพลี้ย" |
| 0.7 | LLM Fallback (gpt-4o-mini) | เฉพาะเมื่อ dictionary ไม่เจอ |

Output ใช้ tag กำกับ:
- `[CONSTRAINT]` = dictionary-matched → Agent 1 ห้าม override
- `[HINT_LLM]` = LLM fallback → Agent 1 ปรับได้

### Agent 1: Query Understanding

**File:** `query_understanding_agent.py` | **Model:** gpt-4o, temp=0.1

- Intent Detection (10 ประเภท): PRODUCT_INQUIRY, PRODUCT_RECOMMENDATION, DISEASE_TREATMENT, PEST_CONTROL, WEED_CONTROL, NUTRIENT_SUPPLEMENT, USAGE_INSTRUCTION, GENERAL_AGRICULTURE, GREETING, UNKNOWN
- Entity Extraction: plant_type, disease_name, pest_name, product_name, possible_diseases
- Query Expansion: สร้าง 3-5 variations สำหรับ search
- **Post-LLM Override**: [CONSTRAINT] entities จะ override ผลจาก LLM เสมอ

### Agent 2: Retrieval (10+ Stages)

**File:** `retrieval_agent.py`

| Stage | ทำอะไร |
|-------|--------|
| 0 | Direct Product Lookup (ilike, similarity=1.0) |
| 1 | Parallel Multi-Query Search (hybrid: vector 60% + keyword 40%) |
| 1.1 | Fertilizer Recommendations (ถ้า NUTRIENT intent) |
| 1.2 | Disease Fallback (target_pest ilike + Thai variants) |
| 1.3 | Symptom Keyword Fallback (ilike target_pest + filter by crop) |
| 1.5 | Fallback Keyword Search (ถ้ายังไม่มี docs เลย) |
| 1.8 | Enrich Metadata (strategy_group, selling_point จาก DB) |
| 1.9 | Supplementary Priority (หา Skyrocket/Expand ที่ match) |
| 2 | De-duplication (by title) |
| 3 | LLM Re-ranking (gpt-4o cross-encoder) |
| 3.5-3.8 | Score Adjustments (strategy boost, category penalty, crop-specific) |
| 4 | Threshold Filter (rerank ≥ 0.50 OR similarity ≥ 0.25) |
| 4.5 | Crop-specific Rescue |

**Strategy Group Priority**: Skyrocket (+0.15) > Expand (+0.10) > Natural (0) > Standard (-0.05)

### Agent 3: Grounding & Citation

**File:** `grounding_agent.py` | **Model:** gpt-4o, temp=0

- ตรวจว่า retrieved docs เกี่ยวข้องกับคำถามจริงไหม
- สินค้าไหนตรงประเด็น
- สร้าง citations (max 3)
- Output: `is_grounded`, `confidence` (0.00-1.00), `relevant_products`

### Agent 4: Response Generator

**File:** `response_generator_agent.py` | **Model:** gpt-4o, temp=0.1

- Confidence Override: ถ้า grounding ต่ำแต่มี disease/crop/product match → override
- Disease Rescue: inject matching doc ถ้า top 5 ไม่มี
- Product Sorting: Skyrocket → Expand → Natural → Standard
- LLM Answer Synthesis (persona น้องลัดดา)
- Post-processing: ลบ markdown, ตรวจตัวเลข, validate ชื่อสินค้า

---

## 5. Memory System

**File:** `memory.py` | **Storage:** Supabase `conversation_memory`

| ค่า | ตัวเลข | หน้าที่ |
|-----|--------|---------|
| เก็บ | 50 ข้อความ / user | ลบเก่าอัตโนมัติ |
| ส่ง LLM | 10 ข้อความล่าสุด | context สำหรับ Agent 1 |
| ตัดข้อความ | 2,000 ตัวอักษร | ป้องกัน token เยอะ |

### Metadata Structure (เก็บคู่กับ assistant message)

```json
{
    "type": "product_recommendation",
    "disease_name": "ราสีชมพู",
    "products": [
        {
            "product_name": "อาร์เทมิส",
            "how_to_use": "ฉีดพ่นให้ทั่วทรงพุ่ม",
            "usage_rate": "10 มล. ต่อน้ำ 20 ลิตร",
            "package_size": "1 ลิตร",
            "phytotoxicity": "ปลอดภัยต่อพืชประธาน"
        }
    ]
}
```

### Follow-up Flow

เมื่อ user ถามต่อเนื่อง (เช่น "ใช้กี่ซีซี", "กี่กระสอบ") โดยไม่ระบุชื่อสินค้า:
1. `handler.py` ดึง product_name จาก memory metadata
2. ถ้าข้อมูลไม่ครบ → enrich จาก DB (package_size, how_to_use, phytotoxicity)
3. ส่งข้อมูลครบถ้วนเข้า RAG pipeline

---

## 6. Database Schema

### Table: `products` (47 rows)

| Column | Type | Description |
|--------|------|-------------|
| product_name | text | ชื่อสินค้า (unique) |
| active_ingredient | text | สารสำคัญ |
| product_category | text | Insecticide / Fungicide / Herbicide / PGR / Fertilizer |
| target_pest | text | โรค/แมลง/วัชพืช ที่กำจัดได้ |
| applicable_crops | text | พืชที่ใช้ได้ |
| how_to_use | text | วิธีใช้ |
| usage_rate | text | อัตราการใช้ |
| usage_period | text | ช่วงเวลาที่ควรใช้ |
| selling_point | text | จุดเด่นสินค้า |
| package_size | text | ขนาดบรรจุ |
| phytotoxicity | text | ความเป็นพิษต่อพืชประธาน |
| strategy_group | text | Skyrocket / Expand / Natural / Standard |
| common_name_th | text | ชื่อสามัญภาษาไทย |
| embedding | vector(1536) | text-embedding-3-small |
| search_vector | tsvector | Full-text search (auto-trigger) |

### Search: Hybrid (RPC `hybrid_search_products`)

```
score = (vector_similarity * 0.6) + (keyword_match * 0.4)
```
- **Keyword**: auto-update ผ่าน Postgres trigger เมื่อ INSERT/UPDATE
- **Vector**: ต้อง regenerate ด้วย admin endpoint `/admin/regenerate-embeddings`

### Table: `fertilizer_recommendations` (19 rows)

- 6 crops x growth stages
- ใช้ ilike filter (ไม่ใช้ RPC เพราะข้อมูลน้อย)
- Trigger: NUTRIENT_SUPPLEMENT intent หรือ fertilizer keywords

### Table: `conversation_memory`

| Column | Type | Description |
|--------|------|-------------|
| user_id | string | LINE `U{hex}` / Facebook `fb:{psid}` |
| role | string | `user` / `assistant` |
| content | string | ข้อความ (max 2,000 chars) |
| metadata | json | สินค้า/โรค/แมลงที่คุย |
| created_at | timestamp | เวลาที่เก็บ |

### Table: `user_ladda(LINE,FACE)`

- บันทึก user ทุกคนที่ add LINE หรือส่งข้อความผ่าน Facebook
- Columns: `line_user_id`, `display_name`, `created_at`, `updated_at`

---

## 7. Anti-Hallucination Safeguards

| Layer | วิธีการ |
|-------|---------|
| **RAG-First Routing** | ทุกอย่างเข้า RAG (ไม่ส่ง general chat ที่มั่วได้) |
| **General Chat neutered** | temp=0.3, max=150 tokens, ห้ามพูดเกษตร/สินค้า |
| **[CONSTRAINT] Tags** | dictionary-matched entities → LLM ห้าม override |
| **Grounding Agent** | LLM verify ว่า docs เกี่ยวข้องจริง |
| **Disease Mismatch Block** | สินค้าไม่ match target_pest → ห้าม LLM แนะนำ |
| **Product Name Validation** | เช็คชื่อสินค้าใน answer ต้องมีใน DB |
| **Number Validation** | ตรวจตัวเลขใน answer vs source docs |
| **No-Data Response** | conf < 0.20 → "ยังไม่มีข้อมูล" แทนการมั่วตอบ |

---

## 8. Platform Support

| Platform | User ID Format | Message Limit | Sticker | Status |
|----------|---------------|---------------|---------|--------|
| LINE | `U{hex}` | 5,000 chars | รับ+ส่งได้ | Production |
| Facebook Messenger | `fb:{psid}` | 2,000 chars (auto-split) | รับได้ ส่งไม่ได้ | Production (text only) |

### LINE Webhook: `/webhook`
- Follow event → welcome message + register user_ladda
- Image message → 2-step diagnosis (plant type → growth stage → analyze)
- Text message → routing → RAG/general chat
- Sticker → "ขอบคุณค่ะ! 😊"

### Facebook Webhook: `/facebook/webhook`
- GET → verify token (one-time setup)
- POST → receive messages → same `handle_natural_conversation()` as LINE
- User ID namespaced as `fb:{psid}` to separate memory

---

## 9. Key Patterns & Conventions

### Thai Disease Variants
ระบบ auto-generate variants สำหรับชื่อโรคสะกดต่างกัน:
- ราสีชมพู ↔ ราชมพู
- แอนแทรคโนส ↔ แอคแทคโนส
- ฟิวซาเรียม ↔ ฟอซาเรียม

### ProductRegistry (DB-driven)
- Singleton ที่ load จาก DB ตอน startup
- Auto-generate Thai variants: consonant swap (ค↔ก,ท↔ต,ซ↔ส), strip diacritics, remove hyphens
- Matching pipeline: exact → diacritics-stripped → fuzzy (SequenceMatcher 0.75)
- `ICP_PRODUCT_NAMES` ใน handler.py เป็น `_ProductNamesProxy` ที่ delegate ไป registry

### Strategy Group Priority
สินค้าถูกจัดลำดับตาม business priority:
1. **Skyrocket** (+0.15 score boost) — แนะนำก่อนเสมอ
2. **Expand** (+0.10)
3. **Natural** (0)
4. **Standard** (-0.05) — แนะนำเมื่อไม่มีตัวอื่นตรง

### Dosage Calculation Rules (prompts.py)
- 1 ซีซี = 1 มล. → ตอบเป็น "มล." เสมอ
- อัตรา "ต่อ 200 ลิตร" → หาร 10 = ต่อถังพ่น 20 ลิตร
- ผู้ใช้ถามพื้นที่ → อัตราต่อไร่ × จำนวนไร่ + จำนวนขวด (ปัดขึ้น)
- ถามหน่วย "ฝาขวด/ช้อน" → แนะนำถ้วยตวง

---

## 10. Configuration (config.py)

### Environment Variables

| Variable | ใช้ทำอะไร |
|----------|-----------|
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API |
| `LINE_CHANNEL_SECRET` | LINE signature verification |
| `OPENAI_API_KEY` | GPT-4o + embeddings |
| `SUPABASE_URL` / `SUPABASE_KEY` | Database |
| `FB_PAGE_ACCESS_TOKEN` | Facebook Send API |
| `FB_VERIFY_TOKEN` | Facebook webhook verification |
| `FB_APP_SECRET` | Facebook signature verification |
| `USE_AGENTIC_RAG` | Enable RAG pipeline (default: "1") |
| `ENABLE_IMAGE_DIAGNOSIS` | Enable image analysis (default: "0") |

### Key Thresholds

| ค่า | ตัวเลข | ใช้ทำอะไร |
|-----|--------|-----------|
| Vector Threshold | 0.25 | ค่าต่ำสุด similarity |
| Rerank Threshold | 0.50 | ค่าต่ำสุด rerank score |
| Min Relevant Docs | 3 | การันตีอย่างน้อย 3 docs |
| Embedding Cache | 500 entries, TTL 1 ชม. | ลดค่า API |
| Rate Limit | 20 req/min per user | ป้องกัน spam |
| Memory | 50 msgs เก็บ / 10 msgs ส่ง LLM | context window |

### LLM Models (ทุก agent ใช้ gpt-4o)

| Component | Model | Purpose |
|-----------|-------|---------|
| Stage 0.7 | gpt-4o | Entity extraction fallback |
| Agent 1 | gpt-4o | Intent + entity + query expansion |
| Agent 2 | text-embedding-3-small | Vector embedding (cached) |
| Agent 2 | gpt-4o | Re-ranking |
| Agent 3 | gpt-4o | Grounding verification |
| Agent 4 | gpt-4o | Answer synthesis |
| General Chat | gpt-4o | Non-agri conversation |

**ค่าใช้จ่ายโดยประมาณ: ~$0.03 / คำถาม**

---

## 11. Key Lessons Learned

- **RAG-first is safer than keyword-gating**: ส่ง unknown queries ไป general chat ทำให้ hallucinate ส่ง RAG ปลอดภัยกว่า
- **Reranker undoes boosts**: Sorting stages (3.55-3.8) สามารถ undo earlier boosts ต้องมี rescue logic หลัง sort
- **disease_mismatch_note blocks LLM**: ถ้า top 5 docs ไม่ match disease → LLM บอก "ไม่มีสินค้า" ต้อง inject matching doc
- **Grounding agent can return 0.00**: แม้มี valid products → ต้อง confidence override
- **Memory metadata must include full product data**: ถ้าเก็บแค่ product_name → follow-up questions ตอบไม่ได้
- **FB Messenger 2000-char limit**: ต้อง split ที่ sentence boundary ไม่ใช่ hard-cut
- **1 ซีซี = 1 มล.**: ข้อมูลใน DB อาจใช้ "ซีซี" แต่ต้องตอบเป็น "มล." เสมอ

---

## 12. Data Management Tool (Next.js Frontend)

```
/                  → Hub (4 ปุ่ม)
/diseases          → Disease CSV Upload
/products          → Product CSV Upload
/products/add      → Add Product กรอกมือ (16 fields)
/dashboard         → Dashboard สถิติ
```

- product_name ซ้ำ = update, ใหม่ = insert
- Embedding สร้างอัตโนมัติผ่าน DB trigger (keyword) แต่ vector ต้อง regenerate ด้วย admin endpoint

---

## 13. Security

| จุด | มาตรการ |
|-----|---------|
| LINE Webhook | X-Line-Signature verification (HMAC-SHA256) |
| Facebook Webhook | X-Hub-Signature-256 verification |
| Secret ไม่ตั้ง | Reject ทุก request (return False) |
| Payload size | 256 KB limit (HTTP 413) |
| Rate limit | 20 req/min per user |
| Admin | Username/password auth + session cookie |
