# Identity — Chatbot น้องลัดดา (ICP Ladda)

> Project identity สำหรับ AI assistant ที่จะเข้ามาทำงานต่อ
> Last updated: 2026-03-05

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

## 2. Architecture: 3-Agent Agentic RAG Pipeline

> **Updated 2026-02-23:** ปิด Grounding Agent (Agent 3) — เหลือ 3 agents
> เหตุผล: Grounding LLM ให้ confidence ไม่สม่ำเสมอ → ทำให้ตอบได้บ้างไม่ได้บ้าง
> Anti-hallucination ใช้ product name validation + number validation + [CONSTRAINT] tags แทน

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
  [Agentic RAG Pipeline]  (rag/orchestrator.py)
         |
         |===> Stage 0: Pre-Detection       (dictionary, no LLM)
         |===> Agent 1: Query Understanding  (gpt-4o, temp=0.1)
         |===> Agent 2: Retrieval            (embedding + hybrid search + reranking)
         |===> [Agent 3: Grounding]          DISABLED (2026-02-23)
         |===> Agent 4: Response Generation  (gpt-4o, temp=0.1)
         |
         v
  [Memory System]  (memory.py — 50 msgs/user, 10 msgs→LLM)
         |
         v
  [Silent No-Data Check]  (answer is None? → skip reply, admin handles)
         |
         v
  [Reply to User]  (LINE Flex / Text / Facebook text)
```

### LLM Calls per Message: 3 (was 4)
1. **Agent 1** — Query Understanding (gpt-4o)
2. **Agent 2** — Reranking (gpt-4o)
3. **Agent 4** — Response Generation (gpt-4o)

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
│   │   ├── rag/                         # === Agentic RAG Pipeline ===
│   │   │   ├── __init__.py              # Data classes, IntentType enum, AgenticRAGResponse (120 lines)
│   │   │   ├── orchestrator.py          # Pipeline orchestrator + Stage 0 pre-detection (~555 lines)
│   │   │   ├── query_understanding_agent.py  # Agent 1: Intent + entity + query expansion (~415 lines)
│   │   │   ├── retrieval_agent.py       # Agent 2: 10+ stage retrieval (~1,150 lines)
│   │   │   ├── grounding_agent.py       # Agent 3: Grounding (DISABLED) (303 lines)
│   │   │   └── response_generator_agent.py  # Agent 4: LLM answer synthesis (~690 lines)
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
│   │   ├── user_service.py              # User registration via user_ladda(LINE,FACE) only
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
│   ├── identity.md                      # THIS FILE — project identity for AI assistants
│   ├── CHANGELOG_2026-*.txt/md          # 12+ changelog files
│   ├── chatagent.md                     # Chat agent documentation
│   ├── prompt_ladda.md                  # Ladda persona reference
│   └── settings.local.json              # Claude local settings
│
├── test_*.py                            # 22+ test files (root level)
├── requirements.txt                     # Python dependencies (41 packages)
├── Dockerfile                           # Docker (python:3.11-slim)
├── Procfile                             # uvicorn app.main:app
├── runtime.txt                          # python-3.11.9
├── IDENTITY.md                          # Project identity (in-repo version)
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
| 0.7 | **Weed Synonym Injection** (added 2026-02-23) | "หญ้า" → ["วัชพืช","กำจัดวัชพืช"] |
| 0.8 | LLM Fallback (gpt-4o) | เฉพาะเมื่อ dictionary ไม่เจอ |

Output ใช้ tag กำกับ:
- `[CONSTRAINT]` = dictionary-matched → Agent 1 ห้าม override
- `[HINT_LLM]` = LLM fallback → Agent 1 ปรับได้

#### Weed Synonym Map (added 2026-02-23)
เกษตรกรใช้คำว่า "หญ้า" แต่ DB ใช้ "วัชพืช" → vector search ไม่เจอ
```python
_WEED_SYNONYM_MAP = {
    'หญ้า': ['วัชพืช', 'กำจัดวัชพืช', 'ยาฆ่าหญ้า'],
    'กำจัดหญ้า': ['กำจัดวัชพืช', 'วัชพืช'],
    'ยาฆ่าหญ้า': ['สารกำจัดวัชพืช', 'วัชพืช'],
    'หญ้าขึ้น': ['วัชพืช', 'กำจัดวัชพืช'],
    'หญ้างอก': ['วัชพืช', 'หลังวัชพืชงอก'],
}
```

### Agent 1: Query Understanding (~415 lines)

**File:** `rag/query_understanding_agent.py` | **Model:** gpt-4o, temp=0.1

- **Intent Detection** (10 ประเภท): PRODUCT_INQUIRY, PRODUCT_RECOMMENDATION, DISEASE_TREATMENT, PEST_CONTROL, WEED_CONTROL, NUTRIENT_SUPPLEMENT, USAGE_INSTRUCTION, GENERAL_AGRICULTURE, GREETING, UNKNOWN
- **Entity Extraction**: plant_type, disease_name, pest_name, product_name, possible_diseases
- **Query Expansion**: สร้าง 3-5 variations สำหรับ search
- **Weed Synonym Injection** (2026-02-23): inject synonyms จาก hints['weed_synonyms'] เข้า expanded_queries
- **Post-LLM Override**: [CONSTRAINT] entities จะ override ผลจาก LLM เสมอ

### Agent 2: Retrieval (~1,150 lines — ใหญ่ที่สุด)

**File:** `rag/retrieval_agent.py`

| Stage | ทำอะไร |
|-------|--------|
| 0 | Direct Product Lookup (ilike, similarity=1.0) |
| 1 | Parallel Multi-Query Search (hybrid: vector 60% + keyword 40%) |
| 1.1 | Fertilizer Recommendations (ถ้า NUTRIENT intent) |
| 1.2 | Disease Fallback (target_pest ilike + Thai variants) |
| 1.3 | Symptom Keyword Fallback |
| 1.5 | **Fallback Keyword Search** (threshold: `< MIN_RELEVANT_DOCS`, was: `== 0`) |
| 1.8 | Enrich Metadata (strategy_group, selling_point) |
| 1.9 | Supplementary Priority (Skyrocket/Expand match) |
| **1.95** | **Weed Category Fallback** — search ALL Herbicides (added 2026-02-23) |
| 2 | De-duplication (by title) |
| 3 | **LLM Re-ranking** (threshold: `>= MIN_RELEVANT_DOCS`, was: `>`) |
| 3.5-3.8 | Score Adjustments (strategy boost, category penalty, crop-specific) |
| 4 | Threshold Filter (rerank ≥ 0.50 OR similarity ≥ 0.25) |
| 4.5 | Crop-specific Rescue |

**Strategy Group Priority (updated 2026-03-04)**: Skyrocket = Expand (+0.12) > Natural = Standard (0)

### Agent 3: Grounding & Citation — DISABLED

**File:** `rag/grounding_agent.py` (303 lines) | **Status:** DISABLED since 2026-02-23

> ปิดเพราะ Grounding LLM ให้ confidence ไม่สม่ำเสมอสำหรับ query สั้น →
> ทำให้ตอบได้บ้างไม่ได้บ้าง (intermittent "ไม่มีข้อมูล")
> ลด latency ~2 วินาที, ลด cost 25% (ตัด 1 ใน 4 LLM calls)
> Config: `config.py` → `ENABLE_GROUNDING: False`
> Re-enable: เปลี่ยนเป็น `os.getenv("AGENTIC_ENABLE_GROUNDING", "0") == "1"`

### Agent 4: Response Generator (~690 lines)

**File:** `rag/response_generator_agent.py` | **Model:** gpt-4o, temp=0.1

- **Grounding Override System** — bypass grounding failures เมื่อมี match จริง:
  - `has_disease_match` — disease variants ตรงกับ target_pest ของ fungicide
  - `has_pest_match` — pest_name ตรงกับ target_pest ของ insecticide (added 2026-02-23)
  - `has_weed_match` — herbicide category found in results (added 2026-02-23)
  - `has_crop_specific_top` — crop-specific product at position 1
  - `has_product_in_query` — user asked about specific product
- **Disease Rescue**: inject matching doc ถ้า top 5 ไม่มี
- **Product Sorting**: Skyrocket → Expand → Natural → Standard
- **LLM Answer Synthesis** (persona น้องลัดดา)
- **Post-processing**: ลบ markdown/emoji, ตรวจตัวเลข, validate ชื่อสินค้า

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

### Table: `user_ladda(LINE,FACE)` — Single user table (updated 2026-03-05)
- บันทึก user ทุกคน (LINE + Facebook): line_user_id, display_name, created_at, updated_at
- `ensure_user_exists()` → ดึง LINE profile + `register_user_ladda()` insert/update
- ลบ table `users` ออกจาก code แล้ว (เคยใช้ซ้ำซ้อน)

---

## 7. Memory System

**File:** `memory.py` (28.8KB)

| ค่า | ตัวเลข | หน้าที่ |
|-----|--------|---------|
| เก็บ | 50 ข้อความ/user | ลบเก่าอัตโนมัติ |
| ส่ง LLM | 10 ข้อความล่าสุด | context สำหรับ Agent 1 |
| ตัดข้อความ | 2,000 ตัวอักษร | ป้องกัน token เยอะ |
| Preview | 800 ตัวอักษร | metadata preview |

### Topic-Aware Memory (updated 2026-03-05)
- `compute_active_topic()` แบ่ง messages เป็น active vs past ตาม topic boundary
- Boundary detection: ชื่อสินค้าเปลี่ยน, โรค/แมลงเปลี่ยน, คำ "ขอบคุณ/เปลี่ยนเรื่อง"
- Pest keywords: เพลี้ย, หนอน, ด้วง, ไรแดง (เพิ่มจาก disease patterns)
- `get_recommended_products()` คืนเฉพาะรอบล่าสุด ไม่สะสมจากหัวข้อเก่า
- Past products labeled "อ้างอิงเท่านั้น ไม่ใช่สินค้าที่กำลังคุย"

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
| Disease Mismatch Block | สินค้าไม่ match target_pest → ห้าม LLM แนะนำ |
| Product Name Validation | ชื่อสินค้าใน answer ต้องมีใน DB |
| Number Validation | ตรวจตัวเลขใน answer vs source docs |
| **Silent No-Data (3 ชั้น)** | **Centralized filter ที่ webhook — ไม่ว่า code path ไหนตอบ "ไม่มีข้อมูล" ก็ suppress (updated 2026-02-24)** |
| False-Positive Block | Stage 0 validate product_name เมื่อ disease/pest detected |
| Post-LLM Override | ลบ hallucinated product_name ใน recommendation intents |
| **Grounding Override** | disease/pest/weed match → bypass low confidence (added 2026-02-23) |

---

## 9. Platform Support

| Platform | User ID Format | Message Limit | Features | Status |
|----------|---------------|---------------|----------|--------|
| LINE | `U{hex}` | 5,000 chars | text + image + sticker + flex | Production |
| Facebook | `fb:{psid}` | 2,000 chars (auto-split) | text only | Production |

---

## 10. Configuration (config.py)

### Feature Flags
| Flag | Default | ทำอะไร |
|------|---------|--------|
| USE_AGENTIC_RAG | "1" | Enable RAG pipeline |
| ENABLE_IMAGE_DIAGNOSIS | "0" | Enable Gemini Vision |
| USE_RAG_DETECTION | "0" | RAG-based disease detection |
| **ENABLE_GROUNDING** | **False (hardcoded)** | **Grounding agent — DISABLED 2026-02-23** |
| RUN_BACKGROUND_TASKS | "0" | Periodic cleanup tasks |
| MAX_CONCURRENT_TASKS | "100" | Semaphore limit สำหรับ background webhook tasks |

### LLM Models (ทุกตัว default gpt-4o)
| Component | Config Key | Purpose | Active? |
|-----------|-----------|---------|---------|
| Stage 0.8 | LLM_MODEL_ENTITY_EXTRACTION | Entity extraction fallback | Yes |
| Agent 1 | LLM_MODEL_QUERY_UNDERSTANDING | Intent + entity + query expansion | Yes |
| Agent 2 | EMBEDDING_MODEL (text-embedding-3-small) | Vector embedding | Yes |
| Agent 2 | LLM_MODEL_RERANKING | Re-ranking | Yes |
| Agent 3 | LLM_MODEL_GROUNDING | Grounding verification | **DISABLED** |
| Agent 4 | LLM_MODEL_RESPONSE_GEN | Answer synthesis | Yes |
| General | LLM_MODEL_GENERAL_CHAT | Non-agri conversation | Yes |

### Key Thresholds
| ค่า | ตัวเลข | ใช้ทำอะไร |
|-----|--------|-----------|
| Vector Threshold | 0.25 | ค่าต่ำสุด similarity |
| Rerank Threshold | 0.50 | ค่าต่ำสุด rerank score |
| Min Relevant Docs | 3 | การันตีอย่างน้อย 3 docs / trigger fallback |
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

### Strategy Group Priority (updated 2026-03-05)
1. **Skyrocket = Expand** (+0.12 score boost) — แนะนำก่อน
2. **Natural = Standard** (0) — ลำดับตาม relevance

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

## 13. Key Lessons Learned

- **RAG-first is safer**: ส่ง unknown queries ไป general chat → hallucinate. RAG ปลอดภัยกว่า
- **Reranker undoes boosts**: Sorting stages (3.55-3.8) undo earlier boosts → ต้องมี rescue logic
- **disease_mismatch_note blocks LLM**: top 5 docs ไม่ match → LLM บอก "ไม่มี" → ต้อง inject matching doc
- **Grounding causes intermittent failures** (2026-02-23): LLM gives inconsistent confidence for short queries → ปิด grounding, ใช้ match overrides แทน
- **Memory metadata must include full data**: เก็บแค่ product_name → follow-up ตอบไม่ได้
- **FB 2000-char limit**: ต้อง split ที่ sentence boundary
- **1 ซีซี = 1 มล.**: DB อาจใช้ "ซีซี" แต่ตอบเป็น "มล." เสมอ
- **ProductRegistry must be async-loaded**: ต้อง await load ตอน startup
- **[CONSTRAINT] prevents LLM hallucination**: pre-extracted entities ต้อง override LLM output
- **Weed synonym gap** (2026-02-23): "หญ้า" ≠ "วัชพืช" ใน embeddings → ต้อง inject synonyms
- **Fallback threshold bug** (2026-02-23): `if not all_docs` ทำให้ 1-2 docs ไม่ trigger fallback → ใช้ `< MIN_RELEVANT_DOCS`
- **Reranking off-by-one** (2026-02-23): `>` ทำให้ docs == MIN_RELEVANT_DOCS skip LLM reranking → ใช้ `>=`
- **Commit ไม่ครบ = deploy crash** (2026-02-24): webhook.py import ตัวแปรจาก config.py แต่ลืม commit config.py → Railway ImportError ตั้งแต่ push
- **Silent no-data ต้อง centralized** (2026-02-24): มีหลาย code path (RAG, legacy, usage question) → ดัก phrase ที่แต่ละจุดไม่พอ → ต้องดักที่ webhook layer เป็น safety net
- **confidence condition ไม่ควรใช้กับ no-data** (2026-02-24): LLM อาจให้ confidence สูงแต่ตอบ "ไม่มีข้อมูล" → ตัด confidence check ออก ดูแค่ phrase

---

## 14. Changelog

### 2026-02-24 — Silent No-Data v2 (centralized filter + bug fixes)

**Commits:** `8d0c233`, `bb03efe`, `3cb08ba`, `370adb8`

**Problem:** Bot ตอบ "ไม่พบข้อมูล..." ทุกครั้งที่ค้นไม่เจอ (เช่น "ม็อคค่า") → admin ไม่ได้ตอบ เพราะ user เห็นว่า bot ตอบแล้ว

**Root Causes (3 ปัญหาซ้อนกัน):**
1. `webhook.py` import `MAX_CONCURRENT_TASKS` แต่ลืม commit `config.py` → **Railway crash ตั้งแต่ commit แรก** → ใช้ version เก่าที่ไม่มี silent no-data
2. Agentic RAG path: condition `confidence < 0.3` เข้มเกินไป → LLM confidence >= 0.3 + ตอบ "ไม่มีข้อมูล" หลุดได้
3. **Usage question path** (`answer_usage_question`) ไม่มี no-data check เลย → "ม็อคค่าใช้ยังไง" หลุดออกไป

**Fix: 3-Layer Silent No-Data**

| Layer | ทำอะไร | File | Catch |
|-------|--------|------|-------|
| 1 | handler: usage question path + no-data check | `handler.py` | usage questions |
| 2 | handler: ตัด `confidence < 0.3` จาก RAG path | `handler.py` | RAG high-confidence |
| 3 | **webhook: `_is_no_data_answer()` ก่อนส่ง reply** | `webhook.py`, `facebook_webhook.py` | **ทุก code path (safety net)** |

**Centralized Filter (webhook layer):**
```python
_NO_DATA_PHRASES_FINAL = [
    "ไม่พบข้อมูล", "ไม่มีข้อมูล", "ไม่อยู่ในฐานข้อมูล",
    "ไม่มีในระบบ", "ไม่พบสินค้า", "ยังไม่มีสินค้าในระบบ",
    "ไม่พบในระบบ", "ไม่พบในฐานข้อมูล",
]

def _is_no_data_answer(answer: str) -> bool:
    return any(p in answer for p in _NO_DATA_PHRASES_FINAL)

# ใช้ที่ webhook: if answer is not None and not _is_no_data_answer(answer):
```

**ยังตอบปกติ:** greeting, system error, ถามข้อมูลเพิ่ม, general chat, คำตอบปกติ

**Test Results:** 18/18 passed
- 10 no-data answers → SUPPRESS ทุกตัว (ม็อคค่า, ซูเปอร์แมน, etc.)
- 8 normal answers → SEND ทุกตัว (โมเดิน, greeting, แนะนำยา, error msg)

### 2026-02-23 — Weed Retrieval Fix + Grounding Disabled

**Commits:** `352446a`, `83e5d2c`, `79de7bc`

**Problem:** Query "กำจัดหญ้าในสวนทุเรียนใช้อะไร" retrieved only 2 docs → bot answered "ไม่มีข้อมูล" despite having herbicide products. Also, pest queries like "ไรแดง" answered intermittently due to grounding inconsistency.

**Root Causes:**
1. Vector search can't match "หญ้า" (farmer term) to products using "วัชพืช" (formal term)
2. Fallback keyword search only triggered when results == 0, not when insufficient
3. Supplementary search only covers Skyrocket/Expand, missing Natural/Standard herbicides
4. Reranking skipped for exactly MIN_RELEVANT_DOCS results (off-by-one)
5. No grounding override for weed or pest queries → low confidence = "ไม่มีข้อมูล"
6. Grounding LLM gives inconsistent confidence for short queries → intermittent failures

**Fixes Applied (7 changes across 4 files):**

| # | Fix | File | Severity |
|---|-----|------|----------|
| 1 | Weed synonym injection (`_WEED_SYNONYM_MAP`) | `orchestrator.py` | CRITICAL |
| 1b | Inject weed synonyms into expanded_queries | `query_understanding_agent.py` | CRITICAL |
| 2 | Fallback threshold: `not all_docs` → `< MIN_RELEVANT_DOCS` | `retrieval_agent.py` | HIGH |
| 3 | New `_weed_category_fallback_search()` for ALL Herbicides | `retrieval_agent.py` | HIGH |
| 4 | Reranking: `>` → `>=` + baseline rerank_score | `retrieval_agent.py` | MEDIUM |
| 5 | `has_weed_match` grounding override | `response_generator_agent.py` | MEDIUM |
| 6 | `has_pest_match` grounding override | `response_generator_agent.py` | MEDIUM |
| 7 | **Disable grounding agent** (hardcode `ENABLE_GROUNDING: False`) | `config.py` | HIGH |

**Impact:**
- Weed queries now retrieve 5+ herbicide products instead of 0-2
- Pest queries like "ไรแดง" answer consistently (no more intermittent failures)
- Latency reduced ~2 seconds per message (removed 1 LLM call)
- Cost reduced ~25% (3 LLM calls instead of 4)
- Pipeline: 4 agents → 3 active agents

### 2026-02-23 — Image Collection Pipeline (project หมอพืช 3.0 flash)

> งานนี้ทำที่ **sister project**: `chatbot ladda ตัวหลัก 3.0 flash หมอพืช`
> Repo: `https://github.com/AtenVisarut/Chatbot-ladda.git`
> Deploy: `liff-production.up.railway.app`

**Commits:** `d687314`, `12c4aa6`, `0ac9aae`, `cf3ebe9`

**เป้าหมาย:** เก็บทุกรูปที่ user ส่งเข้ามาพร้อม AI metadata → big data สำหรับ train ML model (ResNet/EfficientNet) บน Colab

**ไฟล์ใหม่ 6 ไฟล์:**

| ไฟล์ | หน้าที่ |
|------|---------|
| `app/services/image_collector.py` | Core: compress 768px JPEG 85%, MD5 dedup, upload Supabase Storage, save metadata |
| `migrations/create_image_collections.sql` | Table `image_collections` (30+ fields) + 7 indexes + trigger + views |
| `templates/admin_images.html` | Admin UI: image grid, filters, Collection Summary (By Crop/Disease/Category), verify/reject/relabel modal |
| `scripts/export_ml_dataset.py` | Export เป็น ImageFolder format (PyTorch/Colab) + manifest CSV |
| `scripts/assign_dataset_splits.py` | Assign train/val/test 80/10/10 hash-based deterministic |
| `scripts/colab_download_example.ipynb` | Colab notebook: download + fine-tune EfficientNet-B0 |

**ไฟล์ที่แก้:**

| ไฟล์ | เปลี่ยน |
|------|---------|
| `app/config.py` | +4 config: `IMAGE_COLLECTION_ENABLED`, `IMAGE_MAX_DIMENSION`, `IMAGE_JPEG_QUALITY`, `STORAGE_BUCKET` |
| `app/main.py` | +`asyncio.create_task()` hook หลัง detection, +opt-out "ไม่เก็บรูป"/"ลบรูปฉัน", +5 admin API endpoints |

**Architecture:**
```
User ส่งรูป → Disease Detection (เดิม, ไม่เปลี่ยน)
                    │
                    │ asyncio.create_task() (fire-and-forget, ~0.002ms)
                    ▼
            Image Collector (background)
            ├── Compress 768px (~19ms)
            ├── MD5 dedup
            ├── Upload → Supabase Storage (bucket: Data-plant-disease-imagesl)
            └── Save metadata → image_collections table
```

**Storage path:** `{plant_en}/{category}/{YYYY-MM}/{uuid}.jpg` (เช่น `rice/fungal/2026-02/b346cb285f.jpg`)

**Supabase setup ที่ทำแล้ว:**
- Bucket `Data-plant-disease-imagesl` สร้างแล้ว + 3 storage policies (INSERT/SELECT/DELETE)
- Migration SQL run แล้ว (table + indexes + views)
- ENV `IMAGE_COLLECTION_ENABLED=1` ตั้งแล้วบน Railway
- ทดสอบ upload สำเร็จ (200 OK), ยืนยันรูปเข้า Storage ถูกต้อง

**Admin UI:** `https://liff-production.up.railway.app/admin/images`
- Collection Summary: แยก By Crop / By Disease / By Category
- Reject ไม่ลบรูป — แค่ exclude จาก training dataset
- Views ใช้ `COALESCE(verified_*, ai_*)` — human label ชนะ auto label เสมอ

**Performance:** ทดสอบแล้ว 0 ms impact — ทุกอย่างรัน background ไม่กระทบ response time

### 2026-03-05 — Strategy Equalized + Memory Isolation + Bug Fixes + User Table Refactor

**Commits:** `1d17ae1`, `304a4f4`, `485b2d4`, `3a8d3d9`, `0d43543`

#### 1. Strategy Group Equalized (`1d17ae1`)
| ก่อน | หลัง |
|------|------|
| Skyrocket (+0.15) > Expand (+0.10) > Natural (0) > Standard (-0.05) | Skyrocket = Expand (+0.12) > Natural = Standard (0) |

#### 2. Memory Context Bleeding Fix (`304a4f4`)
**Problem:** คุยสินค้าหลายตัวสลับ → สินค้าจากหัวข้อเก่าปนมาตอบ

| # | Fix | File |
|---|-----|------|
| 1 | `compute_active_topic()` detect boundary ด้วย product + disease + pest keywords | `memory.py` |
| 2 | Boundary รวม assistant reply ไว้ในฝั่ง past (ก่อนหน้ารั่วมาฝั่ง active) | `memory.py` |
| 3 | `get_recommended_products()` คืนเฉพาะรอบล่าสุด ไม่สะสม | `memory.py` |
| 4 | Past products labeled "อ้างอิงเท่านั้น" | `memory.py` |
| 5 | Response prompt แยก follow-up กับเปลี่ยนหัวข้อ | `response_generator_agent.py` |

#### 3. Follow-up Disease Context Fix (`485b2d4`)
**Problem:** "มีตัวอื่นไหม" หลังถามฟิวซาเรียม → แนะนำโค-ราซ (ไม่ได้รักษาฟิวซาเรียม)

- Extract disease จาก conversation context เมื่อ query ไม่มีชื่อโรค
- Filter docs ที่ไม่ match disease ก่อนส่ง LLM
- Fix `context_disease` UnboundLocalError เมื่อ intent เป็น WEED_CONTROL

#### 4. Crash Prevention (`3a8d3d9`)

| # | Bug | File |
|---|-----|------|
| 1 | `context_disease` variable shadowing (reset ค่าที่ extract ได้) | `response_generator_agent.py` |
| 2 | `response.choices[0]` IndexError ถ้า OpenAI ส่ง empty | `response_generator_agent.py` |
| 3 | Division by zero ใน reranking เมื่อ `ranking_indices` ว่าง | `retrieval_agent.py` |
| 4 | `response.data[0]` IndexError ถ้า embedding empty | `retrieval_agent.py` |
| 5 | `product_from_query` NameError ถ้า Stage 0 ImportError | `orchestrator.py` |
| 6 | Broad query multi-product hint → LLM แสดงสินค้าทุกตัว (Mode ก) | `response_generator_agent.py` |

#### 5. User Table Refactor (`0d43543`)
- ลบ table `users` ออกจาก code → ใช้ `user_ladda(LINE,FACE)` เท่านั้น
- `ensure_user_exists()` → ดึง LINE profile + `register_user_ladda()` ตรงๆ
- ลบ functions: `upsert_user`, `update_last_seen`, `is_registration_completed`
- ลบ duplicate `register_user_ladda` calls จาก LINE/FB webhooks
