# IDENTITY.md — Chatbot น้องลัดดา (ICP Ladda)

> Project identity document สำหรับ AI assistant ที่จะเข้ามาทำงานต่อ
> Last updated: 2026-02-23

---

## 1. Project Overview

**Chatbot น้องลัดดา** คือ LINE / Facebook Messenger chatbot ให้คำปรึกษาเรื่องสินค้าเคมีเกษตรของ **ICP Ladda**

| Key | Value |
|-----|-------|
| Repo | `https://github.com/AtenVisarut/chatbot-ladda-v2.git` (branch `main`) |
| Framework | FastAPI (Python 3.11.9) + Uvicorn |
| Database | Supabase (PostgreSQL + pgvector) |
| LLM | OpenAI gpt-4o (ทุก agent), embedding: text-embedding-3-small |
| Cache | Redis (Upstash) + in-memory |
| Deploy | Railway (auto-deploy จาก GitHub) |
| Persona | "น้องลัดดา" — ผู้หญิง 23 ปี พี่สาวอบอุ่น สุภาพ ภาษาง่าย |
| Channels | LINE Messaging API + Facebook Messenger |

---

## 2. Architecture: 4-Agent Agentic RAG Pipeline

```
LINE / Facebook Messenger
         |
         v
  [Webhook Router]  (webhook.py / facebook_webhook.py)
         |
         v
  [Chat Handler]  (chat/handler.py — 1,442 lines)
         |
         |--- Greeting? ---------> "สวัสดีค่ะ..." (ตอบทันที)
         |
         |--- Non-Agri? ---------> General Chat (neutered LLM)
         |    (สั้น ≤20 ตัว +      temp=0.3, max_tokens=150
         |     ขอบคุณ/ลาก่อน/OK)   ห้ามพูดเรื่องเกษตร/สินค้า
         |
         v
  [Agentic RAG Pipeline]  (rag/orchestrator.py — 539 lines)
         |
         |===> Stage 0: Pre-Detection   (dictionary, no LLM)
         |===> Agent 1: Query Understanding  (gpt-4o, temp=0.1)
         |===> Agent 2: Retrieval            (embedding + hybrid search)
         |===> Agent 3: Grounding & Citation (gpt-4o, temp=0)
         |===> Agent 4: Response Generation  (gpt-4o, temp=0.1)
         |
         v
  [Memory System]  (memory.py — 50 msgs/user, 10 msgs→LLM)
         |
         v
  [Reply to User]  (LINE Flex / Text / Facebook text)
```

### Routing Logic (RAG-First)
- **Default**: ทุกข้อความเข้า RAG pipeline
- **Greeting**: สั้น + match keyword (สวัสดี, ดีค่ะ, hello) → ตอบทันที
- **Non-Agriculture**: สั้น ≤20 ตัว + match keyword (ขอบคุณ, 555, โอเค) → General Chat
- **Override**: ถ้ามี agriculture keyword (ข้าว, โรค, ยาฆ่า) → ไป RAG เสมอ

---

## 3. File Structure (ปัจจุบัน)

```
Chatbot-ladda/
├── app/
│   ├── main.py                          # FastAPI init + middleware + 5 routers (136 lines)
│   ├── config.py                        # Env vars, models, thresholds (96 lines)
│   ├── models.py                        # Pydantic data models
│   ├── dependencies.py                  # Client init (OpenAI, Supabase, Analytics) (34 lines)
│   ├── prompts.py                       # Persona + prompts + anti-hallucination (284 lines)
│   │
│   ├── routers/
│   │   ├── webhook.py                   # LINE webhook (follow/image/text/sticker) (27KB)
│   │   ├── facebook_webhook.py          # FB Messenger webhook (GET verify + POST) (5.6KB)
│   │   ├── admin.py                     # login/logout, regenerate-embeddings, cache (4.3KB)
│   │   ├── dashboard.py                 # Dashboard HTML + analytics API (1.7KB)
│   │   └── health.py                    # /, /health, /cache/stats
│   │
│   ├── services/
│   │   ├── rag/                         # === Agentic RAG Pipeline (3,084 lines total) ===
│   │   │   ├── __init__.py              # Data classes, IntentType enum, AgenticRAGResponse (120 lines)
│   │   │   ├── orchestrator.py          # Pipeline orchestrator + Stage 0 pre-detection (539 lines)
│   │   │   ├── query_understanding_agent.py  # Agent 1: Intent + entity + query expansion (401 lines)
│   │   │   ├── retrieval_agent.py       # Agent 2: 10+ stage retrieval (1,077 lines)
│   │   │   ├── grounding_agent.py       # Agent 3: Grounding + citation verification (303 lines)
│   │   │   └── response_generator_agent.py  # Agent 4: LLM answer synthesis (644 lines)
│   │   │
│   │   ├── chat/                        # === Chat Routing ===
│   │   │   ├── handler.py               # Message routing + RAG-first logic (1,442 lines / 93KB)
│   │   │   └── quick_classifier.py      # Quick intent classification (11.7KB)
│   │   │
│   │   ├── disease/                     # === Disease Detection ===
│   │   │   ├── constants.py             # Disease patterns + canonical names (30+ โรค)
│   │   │   ├── detection.py             # Gemini Vision disease detection
│   │   │   ├── search.py                # Disease search utilities
│   │   │   ├── database.py              # Disease database operations
│   │   │   └── response.py              # Disease response formatting
│   │   │
│   │   ├── product/                     # === Product System ===
│   │   │   ├── registry.py              # ProductRegistry singleton (DB-driven, Thai variants) (20KB)
│   │   │   └── recommendation.py        # Product recommendation engine (152KB!)
│   │   │
│   │   ├── memory.py                    # Conversation memory (50 msgs, topic-aware) (28.8KB)
│   │   ├── context_handler.py           # Context management (11.2KB)
│   │   ├── user_service.py              # User profile tracking + registration (7.6KB)
│   │   ├── knowledge_base.py            # RAG knowledge search (6.1KB)
│   │   ├── cache.py                     # In-memory caching layer (12.5KB)
│   │   ├── redis_cache.py              # Redis/Upstash caching (13.7KB)
│   │   ├── analytics.py                 # Analytics tracking (22KB)
│   │   ├── reranker.py                  # LLM re-ranking (7.7KB)
│   │   └── welcome.py                   # Welcome messages, help menu
│   │
│   └── utils/
│       ├── text_processing.py           # Thai variant gen, diacritics, number validation (25KB)
│       ├── rate_limiter.py              # Per-user rate limiting (9.1KB)
│       ├── line/
│       │   ├── helpers.py               # LINE API: reply, push, verify signature (6.3KB)
│       │   ├── text_messages.py         # Text message templates (17.4KB)
│       │   ├── flex_messages.py         # LINE Flex Message templates (120KB!)
│       │   ├── question_templates.py    # Question templates (2.7KB)
│       │   └── response_template.py     # Response formatting (8.5KB)
│       └── facebook/
│           └── helpers.py               # FB API: send_message, verify, split (3.4KB)
│
├── api/
│   └── index.py                         # Serverless entry point
│
├── scripts/                             # Helper scripts (update_artemis.py, etc.)
├── migrations/                          # SQL migrations + embedding generation
├── sql_parts/                           # SQL function fixes
├── templates/
│   ├── dashboard.html                   # Dashboard UI (41.5KB)
│   └── login.html                       # Admin login (4.3KB)
├── docs/                                # 15+ documentation files
├── data/                                # Knowledge base templates
├── config/                              # Project structure docs
│
├── .claude/                             # Claude changelogs + agent docs
│   ├── CHANGELOG_2026-*.txt/md          # 12 changelog files
│   ├── chatagent.md                     # Chat agent documentation
│   ├── prompt_ladda.md                  # Ladda persona reference
│   └── settings.local.json              # Claude local settings
│
├── test_*.py                            # 22+ test files (root level)
├── requirements.txt                     # Python dependencies (41 packages)
├── Dockerfile                           # Docker (python:3.11-slim)
├── Procfile                             # uvicorn app.main:app
├── runtime.txt                          # python-3.11.9
├── IDENTITY.md                          # Project identity (this file)
├── SYSTEM_ARCHITECTURE.md               # Architecture docs (older, v2.6)
└── README.md                            # Project README
```

---

## 4. RAG Pipeline Detail

### Stage 0: Pre-Detection (ไม่ใช้ LLM)

**File:** `rag/orchestrator.py`

| Step | ทำอะไร | ตัวอย่าง |
|------|--------|----------|
| 0.1 | Farmer Slang Resolution (12 คำ) | "ยาดูด" → สารดูดซึม |
| 0.2 | Symptom → Pathogen Mapping | เหลือง → [ราน้ำค้าง, ขาดธาตุ] |
| 0.3 | Product Name Extraction (ProductRegistry) | "โมเดิน" → "โมเดิน 50" |
| 0.4 | Disease Name Extraction (30+ patterns) | "ราชมพู" → "ราสีชมพู" |
| 0.5 | Plant Type Extraction (26 พืช) | "ทุเรียน" |
| 0.6 | Pest Name Extraction (18 ชนิด) | "เพลี้ย" |
| 0.7 | LLM Fallback (gpt-4o) | เฉพาะเมื่อ dictionary ไม่เจอ |

Output ใช้ tag กำกับ:
- `[CONSTRAINT]` = dictionary-matched → Agent 1 ห้าม override
- `[HINT_LLM]` = LLM fallback → Agent 1 ปรับได้

### Agent 1: Query Understanding (401 lines)

**File:** `rag/query_understanding_agent.py` | **Model:** gpt-4o, temp=0.1

- **Intent Detection** (10 ประเภท): PRODUCT_INQUIRY, PRODUCT_RECOMMENDATION, DISEASE_TREATMENT, PEST_CONTROL, WEED_CONTROL, NUTRIENT_SUPPLEMENT, USAGE_INSTRUCTION, GENERAL_AGRICULTURE, GREETING, UNKNOWN
- **Entity Extraction**: plant_type, disease_name, pest_name, product_name, possible_diseases
- **Query Expansion**: สร้าง 3-5 variations สำหรับ search
- **Post-LLM Override**: [CONSTRAINT] entities จะ override ผลจาก LLM เสมอ

### Agent 2: Retrieval (1,077 lines — ใหญ่ที่สุด)

**File:** `rag/retrieval_agent.py`

| Stage | ทำอะไร |
|-------|--------|
| 0 | Direct Product Lookup (ilike, similarity=1.0) |
| 1 | Parallel Multi-Query Search (hybrid: vector 60% + keyword 40%) |
| 1.1 | Fertilizer Recommendations (ถ้า NUTRIENT intent) |
| 1.2 | Disease Fallback (target_pest ilike + Thai variants) |
| 1.3 | Symptom Keyword Fallback |
| 1.5 | Fallback Keyword Search |
| 1.8 | Enrich Metadata (strategy_group, selling_point) |
| 1.9 | Supplementary Priority (Skyrocket/Expand match) |
| 2 | De-duplication (by title) |
| 3 | LLM Re-ranking (gpt-4o cross-encoder) |
| 3.5-3.8 | Score Adjustments (strategy boost, category penalty, crop-specific) |
| 4 | Threshold Filter (rerank ≥ 0.50 OR similarity ≥ 0.25) |
| 4.5 | Crop-specific Rescue |

**Strategy Group Priority**: Skyrocket (+0.15) > Expand (+0.10) > Natural (0) > Standard (-0.05)

### Agent 3: Grounding & Citation (303 lines)

**File:** `rag/grounding_agent.py` | **Model:** gpt-4o, temp=0

- ตรวจว่า retrieved docs เกี่ยวข้องกับคำถามจริงไหม
- สร้าง citations (max 3)
- Output: `is_grounded`, `confidence` (0.00-1.00), `relevant_products`
- **Note:** ENABLE_GROUNDING=0 (disabled by default ในปัจจุบัน)

### Agent 4: Response Generator (644 lines)

**File:** `rag/response_generator_agent.py` | **Model:** gpt-4o, temp=0.1

- Confidence Override: ถ้า grounding ต่ำแต่มี disease/crop/product match → override
- Disease Rescue: inject matching doc ถ้า top 5 ไม่มี
- Product Sorting: Skyrocket → Expand → Natural → Standard
- LLM Answer Synthesis (persona น้องลัดดา)
- Post-processing: ลบ markdown/emoji, ตรวจตัวเลข, validate ชื่อสินค้า

---

## 5. Data Classes (rag/__init__.py)

```python
class IntentType(str, Enum):
    product_inquiry, product_recommendation, disease_treatment,
    pest_control, weed_control, nutrient_supplement, usage_instruction,
    general_agriculture, greeting, unknown

class QueryAnalysis:
    original_query, intent, confidence, entities, expanded_queries, required_sources

class RetrievedDocument:
    id, title, content, source, similarity_score, rerank_score, metadata

class RetrievalResult:
    documents, total_retrieved, total_after_rerank, avg_similarity, avg_rerank_score

class Citation:
    doc_id, doc_title, source, quoted_text, confidence

class GroundingResult:
    is_grounded, confidence, citations, ungrounded_claims, relevant_products

class AgenticRAGResponse:
    answer, confidence, citations, intent, is_grounded, sources_used,
    processing_time_ms, query_analysis, retrieval_result, grounding_result
```

---

## 6. Database Schema

### Table: `products` (~47 rows)

| Column | Type | Description |
|--------|------|-------------|
| product_name | text | ชื่อสินค้า (unique) |
| active_ingredient | text | สารสำคัญ |
| product_category | text | ป้องกันโรค / กำจัดแมลง / กำจัดวัชพืช / ปุ๋ย |
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
| pathogen_type | text | oomycetes / fungi / insect / herbicide / pgr |
| embedding | vector(1536) | text-embedding-3-small |
| search_vector | tsvector | Full-text search (auto-trigger) |

### Hybrid Search: `hybrid_search_products` (RPC)
```
score = (vector_similarity * 0.6) + (keyword_match * 0.4)
```

### Table: `fertilizer_recommendations` (19 rows)
- 6 crops x growth stages, ใช้ ilike filter

### Table: `conversation_memory`
- user_id (LINE `U{hex}` / Facebook `fb:{psid}`), role, content, metadata, created_at
- 50 msgs/user, 10 msgs sent to LLM, content truncated at 2,000 chars

### Table: `user_ladda` (LINE / Facebook)
- บันทึก user ทุกคน: line_user_id, display_name, created_at, updated_at

---

## 7. Memory System

**File:** `memory.py` (28.8KB)

| ค่า | ตัวเลข | หน้าที่ |
|-----|--------|---------|
| เก็บ | 50 ข้อความ/user | ลบเก่าอัตโนมัติ |
| ส่ง LLM | 10 ข้อความล่าสุด | context สำหรับ Agent 1 |
| ตัดข้อความ | 2,000 ตัวอักษร | ป้องกัน token เยอะ |
| Preview | 800 ตัวอักษร | metadata preview |

### Metadata Structure (เก็บคู่กับ assistant message)
```json
{
    "type": "product_recommendation",
    "disease_name": "ราสีชมพู",
    "products": [{
        "product_name": "อาร์เทมิส",
        "how_to_use": "ฉีดพ่นให้ทั่วทรงพุ่ม",
        "usage_rate": "10 มล. ต่อน้ำ 20 ลิตร",
        "package_size": "1 ลิตร",
        "phytotoxicity": "ปลอดภัยต่อพืชประธาน"
    }]
}
```

### Follow-up Flow
1. handler.py ดึง product_name จาก memory metadata
2. ถ้าข้อมูลไม่ครบ → enrich จาก DB
3. ส่งข้อมูลครบถ้วนเข้า RAG pipeline

---

## 8. Anti-Hallucination Safeguards

| Layer | วิธีการ |
|-------|---------|
| RAG-First Routing | ทุกอย่างเข้า RAG (ไม่ส่ง general chat ที่มั่วได้) |
| General Chat neutered | temp=0.3, max=150 tokens, ห้ามพูดเกษตร/สินค้า |
| [CONSTRAINT] Tags | dictionary-matched entities → LLM ห้าม override |
| Grounding Agent | LLM verify ว่า docs เกี่ยวข้องจริง |
| Disease Mismatch Block | สินค้าไม่ match target_pest → ห้าม LLM แนะนำ |
| Product Name Validation | ชื่อสินค้าใน answer ต้องมีใน DB |
| Number Validation | ตรวจตัวเลขใน answer vs source docs |
| No-Data Response | conf < 0.20 → "ยังไม่มีข้อมูล" |
| False-Positive Block | Stage 0 validate product_name เมื่อ disease/pest detected |
| Post-LLM Override | ลบ hallucinated product_name ใน recommendation intents |

---

## 9. Platform Support

| Platform | User ID Format | Message Limit | Features | Status |
|----------|---------------|---------------|----------|--------|
| LINE | `U{hex}` | 5,000 chars | text + image + sticker + flex | Production |
| Facebook | `fb:{psid}` | 2,000 chars (auto-split) | text only | Production |

### LINE Webhook: `/webhook`
- Follow event → welcome message + register user_ladda
- Image message → 2-step diagnosis (plant type → growth stage → analyze via Gemini 2.5 Pro)
- Text message → routing → RAG/general chat
- Sticker → "ขอบคุณค่ะ!"

### Facebook Webhook: `/facebook/webhook`
- GET → verify token
- POST → same `handle_natural_conversation()` as LINE
- User ID namespaced as `fb:{psid}`

---

## 10. Configuration (config.py)

### Feature Flags
| Flag | Default | ทำอะไร |
|------|---------|--------|
| USE_AGENTIC_RAG | "1" | Enable RAG pipeline |
| ENABLE_IMAGE_DIAGNOSIS | "0" | Enable Gemini Vision |
| USE_RAG_DETECTION | "0" | RAG-based disease detection |
| ENABLE_GROUNDING | "0" | Enable grounding agent |
| RUN_BACKGROUND_TASKS | "0" | Periodic cleanup tasks |

### LLM Models (ทุกตัว default gpt-4o)
| Component | Config Key | Purpose |
|-----------|-----------|---------|
| Stage 0.7 | LLM_MODEL_ENTITY_EXTRACTION | Entity extraction fallback |
| Agent 1 | LLM_MODEL_QUERY_UNDERSTANDING | Intent + entity + query expansion |
| Agent 2 | EMBEDDING_MODEL (text-embedding-3-small) | Vector embedding |
| Agent 2 | LLM_MODEL_RERANKING | Re-ranking |
| Agent 3 | LLM_MODEL_GROUNDING | Grounding verification |
| Agent 4 | LLM_MODEL_RESPONSE_GEN | Answer synthesis |
| General | LLM_MODEL_GENERAL_CHAT | Non-agri conversation |

### Key Thresholds
| ค่า | ตัวเลข | ใช้ทำอะไร |
|-----|--------|-----------|
| Vector Threshold | 0.25 | ค่าต่ำสุด similarity |
| Rerank Threshold | 0.50 | ค่าต่ำสุด rerank score |
| Min Relevant Docs | 3 | การันตีอย่างน้อย 3 docs |
| Cache TTL | 3600s (1 ชม.) | ลดค่า API |
| Max Cache | 5,000 entries | Memory limit |
| Rate Limit | 20 req/min per user | ป้องกัน spam |
| Memory | 50 msgs เก็บ / 10 msgs ส่ง LLM | context window |

---

## 11. Key Patterns & Conventions

### Thai Disease Variants
ระบบ auto-generate variants สำหรับชื่อโรคสะกดต่างกัน:
- ราสีชมพู ↔ ราชมพู
- แอนแทรคโนส ↔ แอคแทคโนส
- ฟิวซาเรียม ↔ ฟอซาเรียม

### ProductRegistry (DB-driven singleton)
- Load จาก DB ตอน startup
- Auto-generate Thai variants: consonant swap (ค↔ก, ท↔ต, ซ↔ส), strip diacritics, remove hyphens
- Matching pipeline: exact → diacritics-stripped → fuzzy (SequenceMatcher 0.75)
- `ICP_PRODUCT_NAMES` ใน handler.py เป็น `_ProductNamesProxy` delegate

### Strategy Group Priority
1. **Skyrocket** (+0.15 score boost) — แนะนำก่อนเสมอ
2. **Expand** (+0.10)
3. **Natural** (0)
4. **Standard** (-0.05)

### Dosage Calculation Rules
- 1 ซีซี = 1 มล. → ตอบเป็น "มล." เสมอ
- อัตรา "ต่อ 200 ลิตร" → หาร 10 = ต่อถังพ่น 20 ลิตร
- ผู้ใช้ถามพื้นที่ → อัตราต่อไร่ × จำนวนไร่ + จำนวนขวด (ปัดขึ้น)

### Persona Rules (prompts.py)
- ห้ามพูดราคา
- ห้ามแนะนำสินค้านอก ICP Ladda
- ห้ามเมนชั่นการเมือง/ศาสนา
- ห้ามมั่วข้อมูล — ต้องจาก DB เท่านั้น
- Emoji: เฉพาะ 😊 🌱 สูงสุด 1-2 ต่อข้อความ

---

## 12. Security

| จุด | มาตรการ |
|-----|---------|
| LINE Webhook | X-Line-Signature verification (HMAC-SHA256) |
| Facebook Webhook | X-Hub-Signature-256 verification |
| Secret ไม่ตั้ง | Reject ทุก request |
| Payload size | 256 KB limit (HTTP 413) |
| Rate limit | 20 req/min per user |
| Admin | Username/password + session cookie |
| CORS | Allow all origins (configured in main.py) |

---

## 13. Dependencies (requirements.txt)

| Category | Package | Version |
|----------|---------|---------|
| Web | fastapi | 0.115.0 |
| | uvicorn | 0.32.0 |
| | pydantic | 2.9.2 |
| HTTP | httpx | 0.27.2 |
| LLM | openai | 1.54.0 |
| Database | supabase | 2.8.0 |
| Image | Pillow | 10.4.0 |
| Rate Limit | slowapi | 0.1.9 |
| Cache | redis | >=5.0.0 |
| | upstash-redis | >=1.0.0 |
| Messaging | line-bot-sdk | 3.14.0 |
| Templates | jinja2 | 3.1.4 |
| Security | itsdangerous | 2.2.0 |

---

## 14. Key Lessons Learned

- **RAG-first is safer**: ส่ง unknown queries ไป general chat → hallucinate. RAG ปลอดภัยกว่า
- **Reranker undoes boosts**: Sorting stages (3.55-3.8) undo earlier boosts → ต้องมี rescue logic
- **disease_mismatch_note blocks LLM**: top 5 docs ไม่ match → LLM บอก "ไม่มี" → ต้อง inject matching doc
- **Grounding can return 0.00**: แม้มี valid products → ต้อง confidence override
- **Memory metadata must include full data**: เก็บแค่ product_name → follow-up ตอบไม่ได้
- **FB 2000-char limit**: ต้อง split ที่ sentence boundary
- **1 ซีซี = 1 มล.**: DB อาจใช้ "ซีซี" แต่ตอบเป็น "มล." เสมอ
- **ProductRegistry must be async-loaded**: ต้อง await load ตอน startup
- **[CONSTRAINT] prevents LLM hallucination**: pre-extracted entities ต้อง override LLM output
