# Identity — Chatbot น้องลัดดา (ICP Ladda)

> Project identity สำหรับ AI assistant ที่จะเข้ามาทำงานต่อ
> Last updated: 2026-04-23 (diagnostic path + greeting + capability follow-up + open-category clarify + weed-name precision + context-disease leakage fix + sales-popularity follow-up + comparison follow-up cross-category guard + shared followup_patterns + plant-restate guard + typo/space/diacritic normalizer + strategy-leak guard) — `test-dev` branch

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

### Table: `products2` (47 rows) — NEW (2026-03-05)

> โครงสร้างใหม่จาก CSV ข้อมูลสินค้า ICP Ladda พร้อม columns เพิ่มเติม

| Column | Type | Description |
|--------|------|-------------|
| product_name | text (unique) | ชื่อสินค้า |
| common_name_th | text | ชื่อสามัญภาษาไทย |
| active_ingredient | text | สารสำคัญ |
| chemical_group_rac | text | กลุ่มสารเคมี กลุ่ม 1-29 ตาม RAC |
| herbicides | text | วัชพืชที่กำจัดได้ |
| fungicides | text | โรคที่กำจัดได้ |
| insecticides | text | แมลงที่กำจัดได้ |
| biostimulant | text | Plant Biostimulant |
| pgr_hormones | text | PGR/Hormones |
| applicable_crops | text | พืชที่ใช้ได้ |
| how_to_use | text | วิธีใช้ |
| usage_period | text | ช่วงเวลาที่ควรใช้ |
| usage_rate | text | อัตราการใช้ |
| product_category | text | Insecticide / Herbicide / Fungicide / PGR / Biostimulants |
| package_size | text | ขนาดบรรจุ |
| physical_form | text | รูปแบบ (น้ำ/เม็ด/ผง) |
| selling_point | text | จุดเด่นสินค้า |
| absorption_method | text | วิธีการดูดซึม (Systemic/Contact) |
| mechanism_of_action | text | กลไกการออกฤทธิ์ |
| action_characteristics | text | ลักษณะการออกฤทธิ์ |
| phytotoxicity | text | ความเป็นพิษต่อพืชประธาน |
| strategy | text | Expand / Natural / Skyrocket / Standard |
| embedding | vector(1536) | text-embedding-3-small (gen ใหม่ทั้งหมด) |
| search_vector | tsvector | Full-text search (auto-generated) |

**Differences from `products` table:**
- แยกคอลัมน์ target_pest → herbicides / fungicides / insecticides (ตาม CSV)
- เพิ่ม: chemical_group_rac, biostimulant, pgr_hormones, physical_form, absorption_method, mechanism_of_action, action_characteristics
- strategy แทน strategy_group, ไม่มี pathogen_type

### Hybrid Search: `hybrid_search_products2` (RPC)
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

#### 6. products2 Table — New Product Structure (`17e4c48+`)
**Source:** `ICP_product - products_rows (2).csv` (47 สินค้า, 23 คอลัมน์)

| Step | Action | File |
|------|--------|------|
| 1 | สร้าง SQL schema + indexes + RPC hybrid search | `sql_parts/create_products2.sql` |
| 2 | สร้าง migration script: CSV → embedding → Supabase | `migrations/populate_products2.py` |
| 3 | Generate embeddings ใหม่ทั้ง 47 ตัว (text-embedding-3-small) | OpenAI API |
| 4 | Insert 47/47 สำเร็จ พร้อม embedding 1536 dims | Supabase products2 |

**Embedding text สร้างจาก:** product_name + common_name_th + active_ingredient + product_category + insecticides/fungicides/herbicides + applicable_crops + how_to_use + usage_period + usage_rate + selling_point + absorption_method + mechanism_of_action + action_characteristics + phytotoxicity + strategy

**CSV Column Mapping (22/23 mapped, skip: embedding จาก CSV):**
- กลุ่มสารเคมี RAC → `chemical_group_rac`
- Herbicides/Fungicides/Insecticides → `herbicides`/`fungicides`/`insecticides`
- Plant Biostimulant → `biostimulant`
- PGR/Hormones → `pgr_hormones`

---

### 2026-04-21 — Pre-Launch Hardening (4 commits)

**Commits:** `314762f`, `b90bddb`, `ee6735d`, `5bf8971`

**Context:** เตรียม bot ให้ปล่อย dealer + เกษตรกรใช้งาน — ปิดช่องโหว่ที่อาจทำให้ bot hallucinate หรือให้คำแนะนำผิดที่กระทบความปลอดภัย

#### 1. Bug Fixes (`314762f`)

| # | จุด | เดิม | หลัง |
|---|-----|------|------|
| 1 | `orchestrator.py` `_bot_asked_for_context` | จับเฉพาะ `"ระยะของพืชตอนนี้"` → miss กรณีที่ bot ถาม `"ระยะของทุเรียนตอนนี้"` | `"ระยะของ" + "ตอนนี้"` (fix ใน `ee6735d` narrow กลับเพราะกว้างไป) |
| 2 | `orchestrator.py` `_STAGE_WORDS` | มี `"ใบอ่อน"` ซ้ำ 2 ครั้ง | ลบ duplicate |
| 3 | `registry.py` `_TYPO_FIXES["ยางพารา"]` | `["ยาง", "ยางพารา"]` (ซ้ำกับ key) | `["ยางพา"]` → แก้เป็น `["ยางพา", "ยาง"]` (ee6735d) |
| 4 | `response_generator_agent.py` `best_pick_note` | "ห้ามแนะนำตัวใหม่นอก list เดิม" ขัดกับ logic | 3-case: ใน list / ตัวอื่นดีกว่า / ไม่มีเหมาะเลย |

**Efficiency cleanup:**
- `_STAGE_WORDS` → module-level constant (เดิม rebuild ทุก message)
- `import re` hoisted to top (ลบ 2 จุดใน method body)
- `context[-1500:]` cache เป็น `_ctx_recent` (เดิม slice 3 ครั้ง)
- `PlantRegistry` import → module-level

#### 2. Safety Intercept Pre-RAG (`b90bddb`)

เพิ่ม `_check_unsupported_question()` ใน `handler.py` — intercept ก่อน RAG สำหรับคำถามที่ bot **ไม่มีข้อมูลพร้อม** → redirect ไป dealer แทน hallucinate

| Type | Keywords | Response |
|------|----------|----------|
| **Tank mix** | "ผสมร่วมกัน", "ใช้ร่วมกัน", "ฉีดพร้อมกัน", "tank mix", "รวมยาได้ไหม" | แจ้งไม่มีข้อมูล → dealer |
| **PHI** | "ระยะหยุดยา", "หยุดพ่นกี่วัน", "ก่อนเก็บเกี่ยวกี่วัน", "pre-harvest" | อ่านฉลาก + dealer |
| **Resistance** | "ดื้อยา", "ต้านทานยา", "ยาไม่ได้ผลแล้ว" | dealer วางแผนหมุนเวียนกลุ่มยา |

**Pass-through (ไม่ block):** ถามอัตราผสม ("ผสมกี่ซีซี"), ระยะก่อนเก็บเกี่ยว (growth stage), "ยาได้ผลไหม"

#### 3. Facebook Image Handling (`b90bddb`)

- เดิม: ตอบ "กำลังตรวจสอบข้อมูล..." (misleading — ไม่ได้จะตอบจริง)
- หลัง: "ยังไม่สามารถวิเคราะห์รูปทาง FB ได้ + แนะนำพิมพ์อาการเป็นข้อความ"
- **LINE ยังใช้รูปได้ตามปกติ** (image disease diagnosis flow)

#### 4. Post-Audit Fixes (`ee6735d`)

Run audit agent หลัง commit → พบ:
- `"ระยะของ"` กว้างไป (match "ระยะของการใช้ยา") → narrow เป็น `("ระยะของ" + "ตอนนี้")` OR `"ระยะของวัชพืช"`
- ลบ `"ยาง"` จาก typo list → regression (เกษตรกรพิมพ์ "ยาง" เดี่ยวๆ) → restore
- Tone intercepts ไม่สม่ำเสมอ → เพิ่ม 😊 ให้ PHI

#### 5. CI Lint Fix (`5bf8971`)

Pre-existing ruff errors ที่ block CI:
- `webhook.py:263` F821 `display_name` undefined → ใช้ `user_id` แทน
- `ws.py:33` F823 `_connections -= x` ทำให้เป็น local var → `.difference_update()`
- `handler.py:1290,1294` E701 one-liner `if x: y()` → split 2 lines

#### Test Results
- **1,350 passed, 117 skipped** (integration tests ที่ต้องการ live DB)
- New: `tests/test_safety_intercept.py` (9 tests, ครอบคลุม block + pass-through + audit regression)

#### Critical Files Touched
- [app/services/chat/handler.py](app/services/chat/handler.py) — safety intercept + lint fix
- [app/services/rag/orchestrator.py](app/services/rag/orchestrator.py) — `_STAGE_WORDS` hoist + narrow `"ระยะของ"` check
- [app/services/rag/response_generator_agent.py](app/services/rag/response_generator_agent.py) — best_pick 3-case + cache context
- [app/services/plant/registry.py](app/services/plant/registry.py) — typo restore
- [app/routers/facebook_webhook.py](app/routers/facebook_webhook.py) — honest image reply
- [app/routers/webhook.py](app/routers/webhook.py), [app/routers/ws.py](app/routers/ws.py) — CI lint

#### Known Limitations (ไม่ fix รอ data พร้อม)
- Tank mix matrix (สินค้าไหนผสมกับสินค้าไหนได้)
- PHI ครบทุก SKU ในฉลาก
- Resistance management — ต้องการ IRAC/FRAC rotation rules

#### UX Recommendation ก่อน launch
- **ถาม best-pick แค่เมื่อไม่รู้พืช/ระยะ** — รู้แล้วเลือกทันที (ไม่ถามซ้ำ)
- **Dealer group** soft launch ก่อน → เก็บ feedback → ค่อยเปิดเกษตรกรกลุ่มใหญ่

---

### 2026-04-21 (late) — Best-pick stage scan scoped to user turns

**Context:** Railway log หลัง deploy `5bf8971` พบ case "ตัวไหนใช้ดีที่สุดครับ" สำหรับข้าว → bot ตอบ "ชุดกล่องเหลือง" ตรงๆ โดย**ไม่ถามระยะ** — ผิด flow ที่ควรถาม crop + stage ก่อน pick

**Root cause:** ใน `response_generator_agent.py` บรรทัด 1067 scan `_ctx_recent` ทั้งก้อน (user + bot turns) → bot's previous reply ที่มีคำว่า `"ในระยะข้าวอายุ 10-15 วัน"` ทำให้ `_known_stage=True` แบบ false positive → ข้าม branch "ถาม missing" ไป pick ทันที

**Fix:** filter `_ctx_recent` → เก็บเฉพาะบรรทัดที่ขึ้นต้นด้วย `"ผู้ใช้:"` ก่อน scan stage keywords

```python
_user_ctx = "\n".join(
    line for line in _ctx_recent.split("\n") if line.startswith("ผู้ใช้:")
)
_known_stage = any(kw in _user_ctx for kw in _known_stage_keywords)
```

**Why user-turns-only:** memory.py format `"ผู้ใช้: ..."` / `"น้องลัดดา: ..."` — bot เองมักพูด "ระยะ..." ใน recommendation (ไม่ใช่ signal ว่า user ให้ context แล้ว) แต่ถ้า user พิมพ์ "ระยะติดผล" เอง → ใช่ signal จริง

**Scope ของ fix:** กระทบแค่ `_known_stage` — `_known_plant` ยัง scan ทั้ง context ได้ (plant names จาก bot reply ก็ถือว่า confirmed context)

**Test:** `tests/test_best_pick_clarify.py::TestSourceWiring::test_known_stage_scans_user_turns_only` — ตรวจ source ว่า filter ผ่าน `line.startswith("ผู้ใช้:")` และใช้ `_user_ctx` ใน scan

**Files touched:**
- [app/services/rag/response_generator_agent.py](app/services/rag/response_generator_agent.py) — bot-turn filter
- [tests/test_best_pick_clarify.py](tests/test_best_pick_clarify.py) — regression test

**Test results:** 1310 passed, 117 skipped (full suite), lint clean บน `app/`

---

### 2026-04-21 (late 2) — Rice stage vocab + classifier bleed fix

**Context:** Railway log 13:57 — user ถาม "เพลี้ยกระโดดข้าว" → bot แนะนำ 5 ยาฆ่าแมลงถูก (ไบเตอร์, โบว์แลน 285, โบว์แลน, อิมิดาโกลด์ 70, อัลแรม) + ถามระยะข้าว → user ตอบ `"แตกกอ"` → bot ตอบ **"ไม่มีข้อมูลสินค้าที่เหมาะสมในระบบ"** ทั้งที่ ไบเตอร์ ยังอยู่ใน direct lookup

**Root causes (3 ชั้น):**

1. `_STAGE_WORDS` ใน `orchestrator.py` ขาดระยะข้าวที่ bot ตัวเองแนะนำใน template — `"แตกกอ", "ตั้งท้อง", "ออกรวง", "สุก", "เก็บเกี่ยว"` → Stage -1 clarification merge miss
2. `NUTRIENT_KEYWORDS` ใน `handler.py` มี `"แตกกอ", "ออกรวง", "ตั้งท้อง", "เร่ง"` (phenology ใส่ผิดที่) → `detect_problem_types("แตกกอ") → ['nutrient']` → orchestrator drop product + clear state
3. `"ติดดอก", "ติดผล"` ก็อยู่ใน NUTRIENT_KEYWORDS (stage words จริง) → บั๊กซ้ำกับทุกครั้งที่ user ตอบสั้นๆ ด้วย stage name

**Fix:**

| จุด | เดิม | หลัง |
|-----|------|------|
| `_STAGE_WORDS` (orchestrator) | 23 คำ (fruit-tree centric) | 35 คำ ครอบ rice/corn/cane/cassava/bulb/rubber |
| `_known_stage_keywords` (response_generator) | 19 คำ | 30 คำ ตรงกับ `_CROP_STAGES` |
| `NUTRIENT_KEYWORDS` (handler) | มี `"แตกกอ","ออกรวง","ตั้งท้อง","เร่ง","ติดดอก","ติดผล"` | ลบออก เหลือเฉพาะ nutrient intent จริง (`"เร่งแตกกอ","เร่งออกรวง","เร่งตั้งท้อง"`) |
| `_CROP_STAGES["ผัก"]` | `"โต"` (กำกวม) | `"โตเต็มที่"` |

**Key insight:**
- `"แตกกอ"` (bare) = **phenology** — ตอบคำถาม "ตอนนี้ระยะไหน" → ต้อง merge กับ topic เดิม (เพลี้ย)
- `"เร่งแตกกอ"` (compound) = **nutrient intent** — ผู้ใช้อยากได้ปุ๋ย/สารกระตุ้น → route เป็น nutrient

**Tests:** เพิ่ม [tests/test_stage_coverage.py](tests/test_stage_coverage.py) — **395 assertions**:
- Every stage ใน `_CROP_STAGES` ต้อง match `_STAGE_WORDS` (สำหรับทุกพืช 25 ชนิด × ทุกระยะ)
- Pure stage reply (22 คำ) ต้องไม่ classify เป็น nutrient
- Compound nutrient intent (6 queries) ยัง route เป็น nutrient
- Sync guard: mirror ใน `test_best_pick_clarify.py` ต้องมีระยะข้าวด้วย
- Regression: Railway log exact case ต้อง pass Stage -1 merge

**Files touched:**
- [app/services/chat/handler.py](app/services/chat/handler.py) — `NUTRIENT_KEYWORDS` purge
- [app/services/rag/orchestrator.py](app/services/rag/orchestrator.py) — `_STAGE_WORDS` expand
- [app/services/rag/response_generator_agent.py](app/services/rag/response_generator_agent.py) — `_known_stage_keywords` + `_CROP_STAGES["ผัก"]` fix
- [tests/test_stage_coverage.py](tests/test_stage_coverage.py) — new
- [tests/test_best_pick_clarify.py](tests/test_best_pick_clarify.py) — mirror update

**Test results:** 1683 passed, 117 skipped (full suite), lint clean

---

### 2026-04-21 (late 3) — Symptom word-order variants for diagnostic queries

**Context:** ทดสอบคำถามเชิงวินิจฉัยแบบกว้าง `"ยางพาราเป็นจุดสีน้ำตาลที่ใบเกิดจากอะไร"` → bot ไม่ resolve ไป pathogen ได้ เพราะ `diacritics_match` เป็น **substring match** (exact word order) แต่ vocab ใน `SYMPTOM_PATHOGEN_MAP` / `DISEASE_PATTERNS` เก็บ canonical order เดียว (เช่น `"ใบจุดสีน้ำตาล"`) — query ของผู้ใช้ที่เขียน `"จุดสีน้ำตาลที่ใบ"` จึง miss

**Decision:** เลือก **low-risk additive path** (ผู้ใช้สั่ง "แก้ไขด้วยรูปแบบที่ไม่มีความเสี่ยงไปก่อน")
- ไม่เพิ่ม pathogen ใหม่ ไม่เพิ่ม canonical disease ใหม่ ไม่แก้ logic
- เฉพาะ word-order variants ที่ชี้ไปหา pathogen / canonical ที่มีอยู่แล้ว

**Fix:**

| จุด | เพิ่ม |
|-----|------|
| `SYMPTOM_PATHOGEN_MAP` ([text_processing.py](app/utils/text_processing.py)) | 9 variants: `"จุดที่ใบ"`, `"จุดบนใบ"`, `"ใบมีจุด"`, `"ใบเป็นจุด"`, `"จุดสีน้ำตาล"`, `"จุดน้ำตาล"`, `"ใบเป็นแผลไหม้"`, `"ใบหลุดร่วง"`, `"น้ำยางไหล"` — ทั้งหมด route ไป pathogen ที่มีอยู่แล้ว (เซอโคสปอร่า / แอนแทรคโนส / ไฟทอปธอร่า) |
| `DISEASE_PATTERNS` + `DISEASE_CANONICAL` ([constants.py](app/services/disease/constants.py)) | 6 surface forms (เฉพาะ `ใบจุด*` family) → canonical เดิม (`ใบจุด`, `ใบจุดสีน้ำตาล`) |

**สิ่งที่จงใจไม่ทำ:**
- **ไม่เพิ่ม `ใบร่วง` / `โรคใบร่วง` / `ใบหลุดร่วง` เป็น DISEASE_PATTERNS** — `ใบร่วง` อยู่ใน `NUTRIENT_KEYWORDS` ([handler.py:316](app/services/chat/handler.py#L316)) อยู่แล้ว และ `SYMPTOM_PATHOGEN_MAP` มี entry `"ใบร่วง"` → `["แอนแทรคโนส", "ไฟทอปธอร่า"]` พร้อม `"ใบหลุดร่วง"` variant ใหม่ → เส้นทาง symptom-resolution ทำงานโดยไม่ต้องเพิ่ม disease canonical ที่ products3 ไม่การันตีว่ามี
- ไม่แตะ `query_understanding_agent.py` / `retrieval_agent.py` / `[CONSTRAINT]` logic

**Tests:** เพิ่ม [tests/test_symptom_resolution.py](tests/test_symptom_resolution.py) — 43 assertions:
- ทุก variant ต้อง route ไป pathogen / canonical ที่ whitelist ไว้ (ไม่หลุด new pathogen)
- End-to-end `resolve_symptom_to_pathogens` ของ Railway-style query
- Stage 0 extraction picks canonical สำหรับ word-order variants
- Dedupe guard (overlap 2 variants ต้องไม่ซ้ำใน result)
- Negative guard (query ที่ไม่เกี่ยว → empty list)
- Longest-match precedence preserved

**Files touched:**
- [app/utils/text_processing.py](app/utils/text_processing.py) — `SYMPTOM_PATHOGEN_MAP` +9 entries
- [app/services/disease/constants.py](app/services/disease/constants.py) — `DISEASE_PATTERNS` +6 / `DISEASE_CANONICAL` +6
- [tests/test_symptom_resolution.py](tests/test_symptom_resolution.py) — new

**Test results:** 1757 passed, 117 skipped (full suite), lint clean

---

### 2026-04-22 — Diagnostic-intent path + crop priors (`test-dev` branch)

**Context:** Plan [`validated-swimming-quail.md`](/Users/aten/.claude/plans/validated-swimming-quail.md) — เปิดเส้นทาง diagnostic query (`"ยางพาราเป็นจุดสีน้ำตาลที่ใบเกิดจากอะไร"`) แบบปิดความเสี่ยง 6 ด้าน: data integrity / regression / perf / tests / revert / user trust. **ทำบน `test-dev` branch เท่านั้น ไม่ push ไป `main`** — รอ manual QA บน staging ก่อน

**Decision matrix (user):**
- Model: `LLM_MODEL_QUERY_UNDERSTANDING` `gpt-4o-mini` → **`gpt-4.1-mini`** (smarter, low-temp 0.1, OpenAI native, no new SDK)
- Priors scope: Top 8 พืชหลัก (ยางพารา, ทุเรียน, ข้าว, ข้าวโพด, มันสำปะหลัง, อ้อย, มะม่วง, ปาล์ม) — ~80% traffic

**Changes:**

| § | File | What |
|---|------|------|
| §2 | [app/services/disease/diagnostic_intent.py](app/services/disease/diagnostic_intent.py) | **New.** `is_diagnostic_query()` keyword check: "เกิดจาก", "สาเหตุ", "โรคอะไร", "เพราะอะไร", "เป็นโรคอะไร", "อาการแบบนี้", "ทำไม", "คืออะไร" |
| §3 | [app/services/disease/crop_disease_priors.py](app/services/disease/crop_disease_priors.py) | **New.** `CROP_DISEASE_PRIORS` (8 crops × common symptoms) + `_SYMPTOM_VARIANT_GROUPS` (word-order variants) + `resolve_crop_symptom_to_diseases()` |
| §4 | [app/services/rag/orchestrator.py](app/services/rag/orchestrator.py) | Conditional hint refinement: if `DIAGNOSTIC_INTENT_ENABLED` + diagnostic intent + `plant_type` → prepend crop-specific diseases to `possible_diseases`. **ไม่ถอด `[CONSTRAINT]` ใดๆ** |
| §5 | [app/services/rag/response_generator_agent.py](app/services/rag/response_generator_agent.py) | `hedge_note` (inject "จากอาการที่เล่า สาเหตุอาจเป็น X หรือ Y") เฉพาะเมื่อ `diagnostic_intent=True + disease_name=None + possible_diseases≥2` |
| §6 | [app/config.py](app/config.py) | `LLM_MODEL_QUERY_UNDERSTANDING` default → `gpt-4.1-mini` (env var override คงไว้) |
| §7 | [app/services/rag/query_understanding_agent.py](app/services/rag/query_understanding_agent.py) | Defense-in-depth: ถ้า LLM คืน `disease_name` ที่ไม่ Thai หรือไม่ match `DISEASE_PATTERNS` → zero out (กันกรณี smarter model normalize "รากเน่า" → "Phytophthora root rot") |
| §8 | [app/config.py](app/config.py) | `DIAGNOSTIC_INTENT_ENABLED` feature flag (default `false`) |
| §9 | All 3 RAG agents | Structured `[DIAG]` log lines: priors source, hedge application, LLM rejections |
| §10 | [tests/test_diagnostic_intent.py](tests/test_diagnostic_intent.py) | **New.** 48 assertions — intent detection, priors whitelist, weight ordering, dedupe, flag gating, English/non-DB disease rejection |

**Anti-hallucination stack (3 layers):**
1. `[CONSTRAINT]` from Stage 0 disease extraction (pre-existing)
2. Defense-in-depth validation — reject English/non-canonical (new §7)
3. Post-LLM `hints[disease_name]` override (pre-existing lines 245-247)

**Hedge trigger condition (เด็ดขาด):**
- `entities.diagnostic_intent == True`
- `entities.disease_name is None`
- `len(entities.possible_diseases) >= 2`

→ ถ้าใดใดไม่ครบ → fallback ไป existing confident-answer path

**Whitelist guard (กัน "แต่งเชื้อ"):**
- `test_all_priors_reference_known_diseases` ตรวจทุก disease ใน `CROP_DISEASE_PRIORS` values → ต้องอยู่ใน `DISEASE_PATTERNS ∪ DISEASE_CANONICAL.values() ∪ SYMPTOM_PATHOGEN_MAP.values()`
- ไม่มี pathogen ใหม่ ไม่มี canonical ใหม่

**Flag-off regression:**
- Default `DIAGNOSTIC_INTENT_ENABLED=false` → orchestrator ข้าม block §4 ทั้งหมด → behavior = main branch
- ยืนยันด้วย test suite: 1805 passed (เดิม 1757 + 48 new), ไม่มี test เดิมเสีย

**Next steps (§11 staged rollout):**
1. Deploy `test-dev` branch → Railway staging env (set `DIAGNOSTIC_INTENT_ENABLED=true`)
2. Manual QA 20 diagnostic queries ผ่าน LINE
3. Monitor Railway log 48 ชม. หา `[DIAG] llm_disease_rejected` events
4. If clean → merge `test-dev` → `main` (flag ยังคง `false` ใน prod)
5. Canary 10% ก่อน full rollout

**Test results:** 1805 passed, 117 skipped (full suite), ruff clean

---

### 2026-04-22 (late) — Greeting false-positive fix (`test-dev`)

**Problem:** User types follow-up question `"ใช้ตัวไหนดีคับ"` → routed to greeting fast path → RAG skipped, user gets "สวัสดีค่ะ คุณลูกค้า..." instead of product recommendation.

**Root cause:** [handler.py:1241-1252](app/services/chat/handler.py#L1241) matches `GREETING_KEYWORDS` as substring. `"ดีคับ"`/`"ดีครับ"` are 5/6-char members of that list; the existing short-keyword guard only skips keywords ≤2 chars (`"ดี"`, `"hi"`). Follow-up questions ending in `"...ดีคับ"` slipped through.

**Fix:** Added question-marker guard — if message contains `"ไหน", "อะไร", "ยังไง", "เท่าไร", "เท่าไหร่", "ไหม", "มั้ย", "กี่", "ทำไม"` → skip greeting fast path, let it flow to RAG.

| Input | Before | After |
|-------|--------|-------|
| `"สวัสดีครับ"` | greeting ✓ | greeting ✓ |
| `"ใช้ตัวไหนดีคับ"` | greeting ✗ (bug) | RAG ✓ |
| `"ใช้อะไรดีครับ"` | greeting ✗ (bug) | RAG ✓ |
| `"ราคาเท่าไรครับ"` | RAG ✓ | RAG ✓ |

**File:** [tests/test_greeting_detection.py](tests/test_greeting_detection.py) — new, 20 assertions (10 false-positive regressions + 8 true-positive preservation + agri-guard + long-message guard)

**Test results:** 1825 passed (1805 + 20), ruff clean

---

### 2026-04-22 (late 2) — Capability/MoA follow-up not dropping product context (`test-dev`)

**Problem (from Railway log):** User asked `"กำจัดอะไรได้บ้าง และ อยู่กลุ่ม moaอะไรคับ"` after bot recommended `ไบเตอร์`. Bot replied *"สำหรับผลิตภัณฑ์ 'ไบเตอร์' ขออภัยค่ะ ไม่มีข้อมูลในระบบ"* — "ยิ่งคุยยิ่งแย่" pattern.

**Root cause — two layers:**

1. **Orchestrator dropped the product.** [orchestrator.py:603](app/services/rag/orchestrator.py#L603) `_FOLLOWUP_USAGE` covered usage/dose questions (`"ใช้ยังไง"`, `"ผสมกี่"`) and RAC codes (`irac/frac/hrac/rac`) — but missed capability/MoA phrasing: `"กำจัดอะไร"`, `"moa"`, `"ออกฤทธิ์"`, `"สารออกฤทธิ์"`. So the query was classified as "vague, no specific entity" → product dropped + conversation state cleared.

2. **Response generator over-filtered by stale context disease.** [response_generator_agent.py:616](app/services/rag/response_generator_agent.py#L616) `_skip_disease_context` only skipped WEED/PEST/NUTRIENT/USAGE intents and comparison phrasing. Capability queries classified as `PRODUCT_INQUIRY` still ran the context-disease filter → the previous turn's `แอนแทรคโนส` narrowed 23 docs → 1 doc → Agent 3 saw nothing relevant → "ไม่มีข้อมูล".

**Fix:**

- [orchestrator.py](app/services/rag/orchestrator.py): Added capability/MoA keywords (`'กำจัดอะไร', 'ฆ่าอะไร', 'ออกฤทธิ์', 'สารออกฤทธิ์', 'สารสำคัญ', 'moa'`) to `_FOLLOWUP_USAGE`. Raised length cap 40→60 (longer natural queries like the log example). Switched to `.lower()` for case-insensitive MoA/IRAC.
- [response_generator_agent.py](app/services/rag/response_generator_agent.py): New `_CAPABILITY_PAT` skip-trigger — if query contains any of those patterns, skip context-disease filtering. Stale carried-over disease no longer narrows the doc pool when user is asking about product spectrum/mechanism.

**Trace through the log example after fix:**

| Layer | Before | After |
|-------|--------|-------|
| Orchestrator product drop | `Drop product: 'ไบเตอร์' (vague/generic)` | product kept (matched `"กำจัดอะไร"`, `"moa"`) |
| Conversation state | cleared | preserved |
| Response gen filter | 23 → 1 doc (by `แอนแทรคโนส`) | 23 docs kept |
| Final answer | "ไม่มีข้อมูล" | full answer about ไบเตอร์ capability + MoA |

**File:** [tests/test_followup_capability.py](tests/test_followup_capability.py) — new, 18 assertions covering the capability-followup recognition (10 cases) and capability-context-skip behavior (8 cases incl. negatives).

**Test results:** 1843 passed (1825 + 18), ruff clean

---

### 2026-04-22 (late 3) — Open-category clarify (`test-dev`)

**Problem:** เมื่อ user ถามปลายเปิดไม่มี crop เช่น `"แนะนำยาฆ่าหญ้าหน่อย"` / `"อยากได้กำจัดแมลง"` / `"มีปุ๋ยไหม"` — pipeline พยายาม rank ทั้ง category ซึ่งคืนสินค้าไม่ตรง intent (herbicide ที่ใช้กับข้าวอาจไม่เหมาะกับอ้อย) → accuracy ลด และ user ต้องเดาว่าควรถามอะไร.

**Fix:** Detector + clarify prompt + resume 2 turn loop เพื่อเก็บ crop (+ อาการ/ระยะ) ก่อนเข้า RAG.

- [app/services/category_clarify.py](app/services/category_clarify.py): ใหม่. `CategoryType` enum (HERBICIDE / INSECTICIDE / FUNGICIDE / FERTILIZER) + trigger keywords per category + 4 clarify messages (น้องลัดดาถาม, ยกตัวอย่างเดียว, ไม่บังคับ format) + `detect_open_category_query()` (gating: keyword match, no crop, < 40 chars, no escape word "ทั่วไป") + `resume_query_from_clarify()` (merge user reply → well-formed RAG query).
- [app/services/chat/handler.py:1270](app/services/chat/handler.py#L1270): Hook หลัง greeting fast-path. (1) ถ้ามี `pending_category_clarify` ใน `conversation_state` → rewrite message แล้ว fall-through เข้า RAG ตามปกติ. (2) ถ้าเป็น open-category query + ไม่มี `active_product` → save pending + return clarify prompt. Skip clarify ระหว่าง conversation ที่มี product อยู่แล้ว (user น่าจะถาม follow-up ไม่ใช่ start fresh).
- Schema: ใช้ field ใหม่ `pending_category_clarify` ใน `conversation_state` (flat dict, ไม่ต้อง migration).

**UX design (after user feedback "ไม่ต้องบังคับ user format"):** 1 example per category, free-form reply accepted.
- Herbicide: crop-only reply (pre-emergent สินค้าไม่ผูกกับอาการ): `"ข้าว"` → `"แนะนำยาฆ่าหญ้าในข้าว"`
- Other 3: crop + symptom/stage free-form: `"ข้าวใช้กับหนอน"` → `"ยาฆ่าแมลง ข้าวใช้กับหนอน"`, `"บำรุงต้นเพิ่มสารอาหารทุเรียน"` → `"ปุ๋ย บำรุงต้นเพิ่มสารอาหารทุเรียน"`

**File:** [tests/test_category_clarify.py](tests/test_category_clarify.py) — new, 40 assertions (detection positives + skip cases + escape words + long-query skip + message shape + resume — including the exact free-form examples user requested).

**Test results:** 1883 passed (1843 + 40), ruff clean

---

### 2026-04-22 (late 4) — Welcome refresh + remove "คู่มือ" banner (`test-dev`)

**Problem:** (1) `get_usage_guide_text()` opened with `"📖 คู่มือการใช้งานน้องลัดดา"` banner + separator row — redundant noise ahead of the actual examples. (2) `WELCOME_MESSAGE` (first reply when user adds LINE friend) said only `"ถามเรื่องสินค้า — ใช้กับพืชอะไร อัตราผสม วิธีใช้ ถามมาได้หมดเลย"` — too abstract; new users didn't know what to actually type.

**Fix:**
- [app/utils/line/text_messages.py:48](app/utils/line/text_messages.py#L48): Removed the `"📖 คู่มือการใช้งานน้องลัดดา"` header + separator line from `get_usage_guide_text()`. The content now opens directly with `"💬 ถามข้อมูลสินค้า ICP กับน้องลัดดาได้นะคะ:"` and the bullet list.
- [app/prompts.py:309](app/prompts.py#L309): Rewrote `WELCOME_MESSAGE` with 5 concrete example questions covering the 4 categories + product-lookup: pest (`เพลี้ยไฟทุเรียน`), disease (`ข้าวใบจุดสีน้ำตาล`), herbicide (`ยาฆ่าหญ้าในข้าวโพด`), fertilizer (`ปุ๋ยบำรุงทุเรียนช่วงออกดอก`), product spec (`อาร์ดอนใช้กับพืชอะไร`). Keeps `"ช่วยเหลือ"` escape hatch.

---

### 2026-04-22 (late 5) — Weed-name precision fix (`test-dev`)

**Problem:** Query `"ข้าวดีดตัวไหนจัดการได้"` returned 6 herbicides but only #1 (ทูโฟพอส — 2,4-D + อะนิโลฟอส) actually targets ข้าวดีด (weedy rice). #2–6 were generic rice herbicides for other weeds (ข้าวนก, ใบแคบ/ใบกว้าง, pre-emergents). Root cause: no specific weed-name extraction in Stage 0 — `_WEED_SYNONYM_MAP` only caught generic `"หญ้า"`/`"กำจัดหญ้า"`, so retrieval fell back to broad rice-herbicide search without any precision filter.

**Fix (Option A — minimal, parallel to existing insecticide pipeline):**

- [app/services/rag/orchestrator.py:519-537](app/services/rag/orchestrator.py#L519-L537): Added `_WEED_PATTERNS_STAGE0` (18 entries: ข้าวดีด, หญ้าข้าวนก, หญ้าดอกขาว, หญ้าหนวดแมว, หญ้าตีนกา, กกทราย, ใบแคบ, ใบกว้าง, ...) with longest-first ordering. On match, sets `hints['weed_name']`.
- [app/services/rag/query_understanding_agent.py:95-96, 273-275](app/services/rag/query_understanding_agent.py#L95): Added `weed_name` `[CONSTRAINT]` hint + post-LLM override into `entities['weed_type']` (reuses existing entity field — no new schema).
- [app/services/rag/retrieval_agent.py](app/services/rag/retrieval_agent.py): Added `_weed_column_fallback_search()` (parallel to `_pest_column_fallback_search`) + Stage 1.965 trigger when `weed_match_count < 3` + Stage 3.545 precision filter that prunes Herbicide docs whose `herbicides` column doesn't mention the specific weed (keeps non-Herbicide docs untouched so complementary products still surface).
- Broad terms (`หญ้า`, `วัชพืช`, `ใบแคบ`, `ใบกว้าง`) bypass the prune to avoid over-filtering when user genuinely wants generic recommendations.

**Tests:** [tests/test_weed_precision.py](tests/test_weed_precision.py) — 20 new assertions (extraction, generic/unrelated negatives, longest-match, prune simulation for `ข้าวดีด` bug repro, non-herbicide preservation, ordering, whitelist parity with orchestrator source).

**Results:** 1903 passed (1883 + 20), ruff clean. Bug from screenshot fixed in simulation — only docs whose herbicides column contains `"ข้าวดีด"` remain for that query.

### 2026-04-22 (late 6) — Context-disease leakage blocking product-inquiry (`test-dev`)

**Problem:** Dealer queried `"โมเดินใช้ทำอะไร"` after a previous turn had mentioned `แอนแทรคโนส`. Bot answered `"สำหรับ 'โมเดิน' น้องลัดดาไม่มีข้อมูลในระบบค่ะ..."` **even though direct lookup successfully found โมเดิน** (log: `Direct lookup: 1 docs for 'โมเดิน'`). Root cause: [response_generator_agent.py:602-645](app/services/rag/response_generator_agent.py#L602) extracted `context_disease = 'แอนแทรคโนส'` from memory → fired `disease_mismatch_note` because แอนแทรคโนส isn't in โมเดิน's pest columns → LLM produced "ไม่มีข้อมูล" + then recommended unrelated thrips products from pest-expanded queries.

**Fix ([response_generator_agent.py:628-645](app/services/rag/response_generator_agent.py#L628)):**

- Expanded `_CAPABILITY_PAT` with `'ทำอะไร', 'ใช้ทำอะไร', 'คืออะไร', 'ใช้ยังไง', 'สรรพคุณ'` — product-info phrasings that the prior list (`กำจัดอะไร`/`ฆ่าอะไร`/`moa`/`irac`) missed.
- Added 4th skip branch: if `extract_product_name_from_question(original_query)` returns a known product name, set `_skip_disease_context = True`. When user names a specific product, context disease from prior turn must not filter/block the product-inquiry answer. Flag covers both the early doc-filter block (line 647) AND the late mismatch-note block (line 802) via same variable.

**Tests:** [tests/test_context_following.py](tests/test_context_following.py) — new source-level guard `test_response_generator_skips_disease_when_query_names_product` asserting `extract_product_name_from_question` is wired into skip logic + the 5 new capability patterns are present.

**Results:** 1904 passed (1903 + 1), ruff clean. Reproduction confirmed: when reproduced with empty context the bot answered correctly — bug was context-carryover, not a retrieval failure.

### 2026-04-22 (late 7) — Sales-popularity follow-up cross-category leakage (`test-dev`)

**Problem:** Dealer screenshot showed Turn 1 listed 9 herbicides, Turn 2 (`"ขอสินค้าขายดี"`) returned a cross-category mix (fungicide/insecticide/biostim) with hallucinated "best seller" framing. Two failures: (1) **Lost context** — RAG pipeline didn't reuse the previous herbicide list so retrieval surfaced unrelated products; (2) **No real sales data** — ICP has no live sales-rank source, so any "best seller" reply is made up.

**Fix ([app/services/chat/handler.py:1109-1183](app/services/chat/handler.py#L1109) + wire-up at [L1260](app/services/chat/handler.py#L1260)):**

- New pattern table `_SALES_POPULARITY_PATTERNS` (ขายดี / ยอดนิยม / ฮิต / popular / best seller / …) + helper `_is_sales_popularity_query`.
- New handler `_handle_sales_popularity_followup(user_id, message)`:
  - Pattern miss → `None` (fall through to RAG).
  - No `active_products` in conversation state → `None`.
  - Fetch `product_name, strategy, common_name_th, selling_point` from `products3` via `in_` filter on prior list (cap 10).
  - Filter to `{'Skyrocket', 'Expand'}` (ICP push-priority groups); preserve prior order.
  - Response always leads with explicit disclaimer **"น้องลัดดายังไม่มีข้อมูลยอดขายในระบบค่ะ"** — no hallucinated rank.
  - If filtered list is empty → dedicated "ยังไม่มีตัวที่อยู่ในกลุ่มสินค้าหลัก" reply.
- Wired into `handle_natural_conversation` as step 2.6 (after safety intercept, before usage/RAG routing); memoized as `sales_popularity_followup` message type.
- Added `get_conversation_state` import from `app.services.cache`.

**Tests:** [tests/test_sales_popularity_followup.py](tests/test_sales_popularity_followup.py) — 21 cases: pattern detection (Thai + English), no-state/empty-state/no-match fall-through, Skyrocket/Expand filter with Standard/Natural exclusion + order preservation, disclaimer-only branch for all-non-priority lists, cross-category leakage regression (forbidden list from dealer screenshot), source-level guards on wire-up + filter constants.

**Results:** 1925 passed (1904 + 21), ruff clean. Preserves category context without touching RAG retrieval path — follow-up is intercepted before pipeline.

### 2026-04-23 — Comparison follow-up cross-category guard (`test-dev`)

**Problem:** Dealer LINE session — bot listed 9 nutrient products in turn 1 (บอมส์ มิกซ์, ไฮจิพ 5%, ไฮจิพ 20, …); user replied `"ตัวไหนดี"` in turn 2. Bot responded asking about **weed stage + durian age** — totally unrelated category.

**Root cause (traced from log):** 3 compounding bugs in the RAG pipeline:

1. **`orchestrator.py:278`** correctly detected comparison follow-up (pattern `ตัวไหนดี` in `_COMPARE_PATTERNS`) and set `hints['product_names']` = 5 active nutrients — but did **not propagate a flag** to downstream agents.
2. **`query_understanding_agent.py:332-373`** — LLM generated `expanded_queries = ['แนะนำยากำจัดวัชพืชในอ้อย', 'ยากำจัดวัชพืชในอ้อย ตัวไหนดี', 'ยากำจัดวัชพืชในไร่อ้อย …']` (hallucinated category from earlier conversation turns). Agent appended variants to expansion but never **clamped** the LLM output even though `product_names` was definitive.
3. **`retrieval_agent.py:708`** fanned out over hallucinated queries → 60 cross-category docs → 38 after dedup, polluting the context.
4. **`response_generator_agent.py:946`** — `_COMPARISON_KEYWORDS = ['ต่างกันยังไง', 'เปรียบเทียบ', ...]` **missing `ตัวไหนดี`/`อันไหนดี`** (out of sync with orchestrator's list) → Mode ก (clarify) fired instead of Mode ข (compare) → LLM generated clarifying question from polluted docs.

**Fix (4 files):**

- [orchestrator.py:278](app/services/rag/orchestrator.py#L278) — propagate `hints['_comparison_followup'] = True` alongside `product_names`.
- [query_understanding_agent.py](app/services/rag/query_understanding_agent.py) — after expansion build, if `hints['_comparison_followup']` + `product_names` → **replace** (not extend) `expanded_queries = list(hints['product_names'])` and set `entities['_comparison_followup'] = True`. Prevents LLM hallucination from reaching retrieval.
- [retrieval_agent.py:707-722](app/services/rag/retrieval_agent.py#L707) — gate `_comparison_followup = entities.get('_comparison_followup') and direct_lookup_ids`. When true: skip `_multi_source_retrieval`, skip Stage 1.2 disease fallback, Stage 1.3 symptom fallback, Stage 1.5 keyword fallback. Only direct-lookup docs proceed downstream.
- [response_generator_agent.py:946](app/services/rag/response_generator_agent.py#L946) — sync `_COMPARISON_KEYWORDS` with orchestrator's list (add `ตัวไหนดี`, `อันไหนดี`, `ตัวไหนเหมาะ`, `อันไหนเหมาะ`, `ต่างกัน`, `ใช้ต่าง`); `_is_comparison` also honors `entities['_comparison_followup']` → Mode ข wins over Mode ก.

**Tests:** [tests/test_comparison_followup.py](tests/test_comparison_followup.py) — 6 source-level guards: orchestrator propagates flag + has `ตัวไหนดี` pattern; query-understanding clamps via `expanded_queries = list(hints['product_names'])`; retrieval gates on `_comparison_followup + direct_lookup_ids`; response generator syncs patterns + honors entity flag.

**Results:** 1931 passed (1925 + 6), ruff clean. Comparison follow-ups short-circuit to direct-lookup-only retrieval → category context preserved, no LLM hallucination leakage.

### 2026-04-23 (late) — Shared follow-up patterns + plant-restate guard + cross-plant/phrasing coverage (`test-dev`)

**Motivation:** The previous comparison fix shipped with three brittle spots: (1) orchestrator and response generator each kept their own pattern list, so drift would re-introduce the bug; (2) patterns were narrow — only `ตัวไหนดี`/`อันไหนดี` — missing `ตัวไหนเหมาะ`, `แบบไหนดี`, `รุ่นไหนดี`, `ตัวไหนได้ผล`, English variants; (3) "`ตัวไหนดีสำหรับข้าว`" when state already tracked rice would be misclassified as a new topic by the `_plant_in_q_s and not _is_app` branch, dropping the comparison follow-up.

**Fix (3 files + 1 new module):**

- **New: [app/services/rag/followup_patterns.py](app/services/rag/followup_patterns.py)** — single source of truth. Exports `COMPARISON_FOLLOWUP_PATTERNS` (Thai `ตัวไหน…` / `อันไหน…` / `แบบไหน…` / `รุ่นไหน…` families + explicit compare verbs + English) and `is_comparison_followup(query)` helper.
- **[orchestrator.py](app/services/rag/orchestrator.py)** — import and use `is_comparison_followup`; replace inline `_COMPARE_PATTERNS` list. Plant-restate guard: `_plant_would_be_new = _plant_in_q_s and not _is_app and not (_is_compare and not _different_plant)` — same-plant re-statement on a compare phrasing stays in follow-up mode; different-plant correctly routes as new topic.
- **[response_generator_agent.py](app/services/rag/response_generator_agent.py)** — delete private `_COMPARISON_KEYWORDS` list; use shared `is_comparison_followup`.

**Tests:**

- [tests/test_comparison_followup.py](tests/test_comparison_followup.py) — 43 tests: 33 pattern unit tests (parametrized matches + non-matches: `ตัวไหนดี/เหมาะ/เด็ด/เวิร์ค/ได้ผล/น่าใช้/เจ๋ง/เด่น/คุ้ม`, `อันไหน…`, `แบบไหน…`, `รุ่นไหน…`, `ใช้ต่างกัน`, `เปรียบเทียบ`, `which is good`, `best one`, `compare them`) + 10 source-level guards (orchestrator uses shared module + has plant-restate guard; response generator uses shared module).
- [tests/test_comparison_followup_e2e.py](tests/test_comparison_followup_e2e.py) — 15 end-to-end tests (real Supabase + OpenAI):
  - 2 rice-nutrient scenarios (2-turn flow + pre-seeded direct turn 2)
  - **4 cross-plant × cross-category** (rice/herbicide, durian/fungicide, mango/PGR, rice/insecticide) — each seeds `active_products`, sends `ตัวไหนดี`, asserts answer stays on seeded products and doesn't leak other-category clarifying questions.
  - **7 phrasing variations** (`ตัวไหนดี`, `ตัวไหนเหมาะ`, `ตัวไหนได้ผล`, `อันไหนดี`, `แบบไหนดี`, `ใช้ต่างกันยังไง`, `เปรียบเทียบให้หน่อย`) — each must route to the comparison path with rice-nutrient seed.
  - 2 plant-restate cases: same-plant re-statement keeps context; different-plant correctly switches topic.

**Results:** Full suite 1983 passed (1931 + 37 new unit + 15 e2e), ruff clean. Integration tests hit real APIs — 2m 35s for 15 e2e cases; full suite 3m 19s end-to-end.

### 2026-04-23 (late 2) — Typo/space/diacritic normalizer for follow-up patterns (`test-dev`)

**Motivation:** Substring-only matching missed 3 classes of real-user edge cases: (1) typos where the short vowel ั is omitted (`ตวไหนดี`); (2) internal whitespace (`ตัวไหน ดี`, `ตัว ไหน ดี`); (3) tone-mark variations. Honorifics (ครับ/คับ/ค่ะ/คะ/…) and most suffixes already worked because they're pure appends.

**Fix — Phase 1 only (scope-controlled):** [app/services/rag/followup_patterns.py](app/services/rag/followup_patterns.py) — added `_normalize(text)` that applies in order: (a) lowercase, (b) strip all whitespace (Thai has no word spaces), (c) reuse `strip_thai_diacritics` (tone marks + thanthakhat + mai taikhu), (d) strip `ั` (common typo omission). Pre-compute normalized patterns once at import time (constant pattern list, hot path). `is_comparison_followup` now compares normalized query against normalized patterns.

**Phase 2 (LLM-assisted fallback) deliberately deferred** — recorded in [problem.md](../problem.md). YAGNI: no real-world evidence that keyword + normalizer misses legitimate follow-ups, and LLM fallback adds non-determinism + test flakiness. Revisit if log shows ≥3 production cases of miss.

**Tests:** 12 new in [tests/test_comparison_followup.py](tests/test_comparison_followup.py) `TestSharedPatterns`:
- `test_tolerant_matches` (parametrized, 23 cases): honorifics, missing `ั`, internal whitespace, combined
- `test_normalizer_no_false_positive` (6 cases): aggressive normalization must not false-match `ซื้อที่ไหนดี`, `ขายดีครับ`, `ใช้ยังไงครับ`, etc.

**Results:** 1995 passed (1983 + 12 new unit), ruff clean. Excluded e2e from this run — no pipeline change, only pattern matching layer; prior 15 e2e cases remain valid.

### 2026-04-23 (late 3) — Strategy-group name leak fix + admin-handoff for sales-popularity (`test-dev`)

**Problem:** Dealer screenshot showed user-facing leak of internal strategy classification: reply read *"จากสินค้าที่แนะนำก่อนหน้านี้ ยังไม่มีตัวที่อยู่ในกลุ่มสินค้าหลัก **(Skyrocket/Expand)** ของ ICP Ladda ค่ะ"*. `Skyrocket` / `Expand` / `Natural` / `Standard` / `Cosmic-star` are confidential internal business classifications — they must never reach a user-visible reply or an LLM prompt that the model could paraphrase.

**Fix:**

- [app/services/chat/handler.py](app/services/chat/handler.py) — rewrite `_handle_sales_popularity_followup` reply copy:
  - **Success branch** (priority match exists): lead with disclaimer *"น้องลัดดายังไม่มีข้อมูลยอดขายในระบบค่ะ"*, list priority products by name with active-ingredient + selling point, close with *"ถ้าอยากได้รายละเอียดตัวไหนเพิ่มเติม บอกน้องลัดดาได้เลยค่ะ"* — **no mention of the strategy group at all**.
  - **No-priority-match branch**: return short marker `"ไม่มีข้อมูลยอดขายในระบบ"` that passes `webhook._is_no_data_answer` — triggers silent drop + `fire_no_data_alert` so admin answers manually. Better than fabricating a best-seller answer.
  - Wire-up: gate `add_to_memory` on `_is_no_data_answer(reply)` — the admin-handoff marker must not pollute conversation memory since the user never sees it.
- [app/services/rag/response_generator_agent.py:1165](app/services/rag/response_generator_agent.py#L1165) — remove `strategy=Skyrocket/Expand` from `best_pick_note` LLM prompt body; replaced with neutral *"เลือกตัวที่อยู่ลำดับต้น…(ระบบจัดเรียงไว้แล้ว)"*.
- [app/services/rag/retrieval_agent.py:1596](app/services/rag/retrieval_agent.py#L1596) — remove `Strategy Skyrocket/Expand ให้ลำดับสูงกว่า Natural/Standard` from rerank prompt; replaced with *"ใช้ลำดับใน metadata เป็น tiebreaker (ระบบจัดลำดับความสำคัญไว้แล้ว)"*. Reranker output is only integers so low leak risk, but defense-in-depth.
- Pattern: added `ตัวไหนนิยม`, `อันไหนนิยม`, `แบบไหนนิยม`, `รุ่นไหนนิยม` to `_SALES_POPULARITY_PATTERNS` — natural Thai construction missed by prior `ที่นิยม` / `ยอดนิยม` / `นิยมที่สุด` list.

**Tests:**

- New: [tests/test_no_strategy_leak.py](tests/test_no_strategy_leak.py) — static AST scanner across 5 files (`handler`, `orchestrator`, `response_generator_agent`, `retrieval_agent`, `query_understanding_agent`). For each file, collect every sentence-length string literal (excluding docstrings and `logger.*()` call arguments — those are internal), and assert no strategy name appears via word-boundary match. Includes end-to-end check exercising both handler branches (success + admin-handoff) with mocked state. Guards the `prompts.py` rule 15 still names all 5 strategy values so the LLM knows what to suppress (defense-in-depth).
- [tests/test_sales_popularity_followup.py](tests/test_sales_popularity_followup.py) — rewritten: split `test_filters_to_priority_products` (priority subset, order preserved, disclaimer present, **no strategy name in reply**) + `test_no_priority_match_returns_admin_handoff_marker` (asserts reply passes `webhook._is_no_data_answer` → silent drop + admin alert).
- Source guards: `test_admin_handoff_skips_memory_save` checks wire-up consults `_is_no_data_answer` before `add_to_memory`.

**Results:** 2004 passed (1995 + 9 new), ruff clean. Excluded e2e from this run — reply copy is the only user-visible surface that changed; prior e2e cases remain valid.

