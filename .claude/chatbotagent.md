# Chatbot Flow Diagram — น้องลัดดา (ICP Ladda)

> Updated: 2026-03-23 | After: Supabase migration, dead code cleanup, hallucination fixes, session timeout

---

## 1. Overview Flow

```
LINE/FB Message
       |
       v
  [Webhook Router]  ──── POST /webhook (signature verify)
       |
       v
  [Event Dispatch]  ──── asyncio.create_task() (return 200 ทันที)
       |
       +──── Follow Event ──────────> Welcome Message
       |
       +──── Sticker Message ───────> Sticker Reply
       |
       +──── Image Message ─────────> Image Diagnosis Flow (DISABLED)
       |
       +──── Text Message ──────────> Main Routing
              |
              v
     [handle_natural_conversation()]
              |
              +── Quick Command? ────> Instant Reply (วิธีใช้, ดูผลิตภัณฑ์, reset)
              |
              +── Pending Context? ──> Image Diagnosis Continue (DISABLED)
              |
              +── Usage Question? ───> answer_usage_question()
              |
              +── Greeting? ─────────> Random Greeting (no LLM)
              |
              +── Cached? ───────────> Return Cached Answer
              |
              +── RAG or General? ───> Decision ─── RAG-First (default)
                     |                         |
                     v                         v
              [AgenticRAG Pipeline]    [General Chat] (non-agri only)
                     |
                     v
              [No-Data Filter]
                     |
                     +── No data → NO_DATA_REPLY ("ขณะนี้ ไอ ซี พี ลัดดา กำลังตรวจสอบ...")
                     +── Has data → reply_line() / push_line()
```

---

## 2. Main Routing — handler.py

```
handle_natural_conversation(user_id, message)
       |
       v
  1. add_to_memory(user_id, "user", message)     ─── parallel ──┐
  2. context = get_enhanced_context(user_id)      ─── parallel ──┘
       |                                                   |
       |                              Session timeout (6h) ─── ถ้าหายไป >6 ชม. → context ว่าง
       v
  +----- is_usage_question(message)? ----+
  |  YES                                 |  NO
  v                                      v
  มี product_name ใน query/context?    +----- is_greeting(msg)? -----+
  |  YES           |  NO               |  YES                       |  NO
  v                v                   v                            v
  answer_usage    skip → ไปต่อ     Random Greeting              +----- cached? -----+
  _question()                     (no LLM call)               |  YES               |  NO
                                                              v                    v
                                                          Return cache       Route Decision
                                                                                   |
                                                                                   v
                                                              +--- explicit_match OR NOT is_non_agri ---+
                                                              |  YES (RAG)                              |  NO
                                                              v                                         v
                                                     AgenticRAG.process()                   handle_general_chat()
                                                              |                             (gpt-4o, temp=0.3)
                                                              v
                                                     answer + no-data check
                                                              |
                                                     +--- is_no_data? ---+
                                                     |  YES              |  NO
                                                     v                   v
                                                NO_DATA_REPLY        Return answer
                                                (แจ้ง admin)         + save to memory/cache
```

### Route Decision Logic

```
explicit_match = is_agriculture_question(msg)
               OR is_product_question(msg)
               OR is_fertilizer_query
               OR has_product_name

is_non_agri = _is_clearly_non_agriculture(msg)  # short + non-agri keywords

route_to_rag = explicit_match OR (NOT is_non_agri)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
               RAG-First: default ไป RAG เสมอ
               ยกเว้นชัดเจนว่าไม่ใช่เกษตร
```

---

## 3. Agentic RAG Pipeline — orchestrator.py

```
AgenticRAG.process(query, context, user_id)
       |
       v
=== Stage 0: Dictionary Pre-Detection (NO LLM) ===
       |
       +-- resolve_farmer_slang(query)         → hints['resolved_slang'] (31 slang terms)
       +-- resolve_symptom_to_pathogens(query)  → hints['possible_diseases'] (21 symptom mappings)
       +-- extract_product_name(query/context)  → hints['product_name']
       +-- DISEASE_PATTERNS_SORTED matching     → hints['disease_name'] + variants (30+ โรค)
       +-- extract_plant_type(query)            → hints['plant_type'] (36+ พืช)
       +-- PEST_PATTERNS matching               → hints['pest_name'] (18 ชนิด)
       +-- detect_problem_types(query)          → hints['problem_type'] (disease/insect/weed/nutrient)
       +-- weed synonym injection               → hints['weed_synonyms']
       +-- nutrient synonym injection            → hints['nutrient_synonyms']
       +-- product validation (drop if invalid) → clean hints
       +-- ambiguous product detection          → clarify_msg (early return)
       |
       v
  hints = {
      product_name, disease_name, plant_type, pest_name,
      problem_type, resolved_slang, possible_diseases,
      weed_synonyms, nutrient_synonyms, _product_from_query
  }
       |
       v
=== Stage 1: Query Understanding Agent (gpt-4o-mini) ===
       |
       +-- LLM receives: query + context + hints ([CONSTRAINT]/[HINT] tags)
       +-- Output: intent, confidence, entities, expanded_queries
       |
       +-- intent == GREETING? ────────> Generate greeting (early return)
       +-- intent == UNKNOWN + conf<0.3? ──> return None (general chat)
       +-- intent == UNKNOWN + product keywords? ──> force retrieval
       |
       v
=== Stage 2: Retrieval Agent (embedding + gpt-4o-mini rerank) ===
       |
       +-- Stage 0: Direct Lookup (exact product_name match)
       +-- Stage 1: Multi-Query Vector Search (parallel embedding):
       |      hybrid_search_products3 RPC (vector similarity)
       +-- Stage 1.1: Fertilizer Recommendations (ถ้า NUTRIENT intent)
       +-- Stage 1.2: Disease Fallback (target_pest ilike)
       +-- Stage 1.3: Symptom Keyword Fallback
       +-- Stage 1.5: Fallback Keyword Search
       +-- Stage 1.8: Enrich Metadata (strategy_group, selling_point)
       +-- Stage 1.9: Supplementary Priority (Skyrocket/Expand match)
       +-- Stage 1.95: Weed Category Fallback (ALL Herbicides)
       +-- Stage 1.96: Pest Column Fallback (insecticides column search)
       +-- Stage 2: De-duplication (by title)
       |
       +-- Stage 3: LLM Re-ranking (gpt-4o-mini):
       |      Input: top-15 docs metadata + query
       |      Output: relevance ranking numbers
       |      (skip when direct lookup found product)
       |
       +-- Stage 3.5: Strategy Group Score Boost (Skyrocket/Expand +0.12)
       +-- Stage 3.55: Category Penalty (off-category docs penalized)
       +-- Stage 3.65: Crop-Mismatch Penalty:
       |      - prohibited: -0.30
       |      - no-match: -0.15
       |      - match: +0.05
       |      - emphasized: +0.20
       |      Uses _PLANT_BROADER_CATEGORIES (ข้าว→พืชไร่, ทุเรียน→ไม้ผล, etc.)
       +-- Stage 3.7: Promote best Skyrocket/Expand to position 1
       |      (skip bundle products: ชุด/กล่อง/รวง)
       +-- Stage 3.8: Disease-matching product rescue to top 3
       +-- Stage 4: Threshold Filter (rerank ≥ 0.50 OR similarity ≥ 0.25)
       +-- Stage 4.5: Crop-specific Rescue
       |
       v
  RetrievalResult = { documents[], avg_similarity, total_results }
       |
       v
=== Grounding Check ===
       |
       +-- is_grounded = bool(documents) OR has_disease_match OR has_pest_match OR has_weed_match
       +-- confidence = calculated from similarity + match flags
       |
       v
=== Agent 4: Response Generation (gpt-4o) ===
       |
       +-- Crop Pre-Filter: กรอง crop-mismatched docs ก่อนส่ง LLM
       +-- Crop Warning Injection: [!! ห้ามใช้/ไม่ได้ระบุ !!] tags
       +-- System Prompt: น้องลัดดา persona + PRODUCT_QA_PROMPT
       +-- Input: query + context + filtered documents
       +-- Anti-hallucination: allowed_products list, [CONSTRAINT] tags
       +-- Nutrient constraint: ห้ามแนะนำยาฆ่าแมลงเมื่อถาม nutrient
       +-- Number validation (post-generation check)
       +-- Product name validation (ชื่อต้องอยู่ใน DB)
       +-- post_process_answer() (clean markdown artifacts)
       |
       v
  AgenticRAGResponse = {
      answer, confidence, citations,
      intent, is_grounded, sources_used,
      processing_time_ms
  }
```

---

## 4. LLM Calls Per Query

```
Query: "กำจัดเพลี้ยในส้ม ใช้อะไรดี"

  Call 1: Query Understanding    [gpt-4o-mini]      ~2-3s
  Call 2: Embedding (parallel)   [text-embedding-3-small]  ~0.3s
  Call 3: Re-rank                [gpt-4o-mini]      ~0.5-1s
  Call 4: Response Generation    [gpt-4o]           ~4-5s
  ──────────────────────────────────────────────
  Total:                                            ~10-11s (Railway)

  DB Queries: ~8-12 per message
              1x user_ladda(LINE,FACE) (register/check)
              3-4x memory_chatladda (read + write user + write bot + cleanup)
              2x cache (check hit + save response)
              2-4x products3 (direct lookup + hybrid search + enrich)
              1x analytics_events (log)
```

### Response Time Breakdown (measured 2026-03-23)

| Component | Time | % |
|-----------|------|---|
| Agent 4 (gpt-4o response gen) | ~5s | 46% |
| Agent 1 (gpt-4o-mini intent) | ~3s | 28% |
| Pre-DB (user, memory, cache) | ~1.9s | 17% |
| Retrieval (vector + keyword) | ~1.4s | 13% |
| Reranker (gpt-4o-mini) | ~0.6s | 6% |
| **Average total** | **~10.8s** | |

---

## 5. Database — Supabase (project: nvtdtyrwvfuvldccpprc)

### 7 Tables

| Table | Config | ใช้ทำอะไร |
|-------|--------|----------|
| `products3` | `PRODUCT_TABLE` env var | สินค้า 47 ตัว + embedding vector(1536) |
| `memory_chatladda` | `MEMORY_TABLE` env var | Conversation memory (แยกจาก project หมอพืช) |
| `user_ladda(LINE,FACE)` | hardcode | User profiles (42 users) |
| `cache` | hardcode | L2 cache (key-value + TTL) |
| `analytics_events` | hardcode | Event tracking (question, product_rec, error) |
| `analytics_alerts` | hardcode | Alert notifications |
| `admin_handoffs` | hardcode | Handoff to admin |

### RPC Functions

| Function | ใช้ทำอะไร |
|----------|----------|
| `hybrid_search_products3` | Vector similarity search (params: query_embedding, search_query, vector_weight, keyword_weight, match_threshold, match_count) |

### ไม่ใช้แล้ว (ลบ code references แล้ว 2026-03-23)
- `diseases` table
- `knowledge` table
- `hybrid_search_diseases` RPC
- `match_knowledge` RPC

---

## 6. No-Data Response (updated 2026-03-23)

```
เดิม: bot เงียบ (return None) → admin จัดการ
ใหม่: bot ตอบ NO_DATA_REPLY ทุกกรณี

NO_DATA_REPLY = "ขณะนี้ ไอ ซี พี ลัดดา กำลังตรวจสอบข้อมูลให้คุณลูกค้าค่ะ
                 แอดมินแจ้งให้ทราบอีกครั้งนะคะ ต้องขออภัยในความล่าช้าด้วยค่ะ 🙏🙏"

Trigger conditions (7 จุด):
  1. ไม่พบ product_docs
  2. ไม่พบ diseases ใน DB
  3. Usage answer สั้น + no-data phrase
  4. Cache hit มี no-data phrase
  5. RAG not grounded + confidence 0
  6. RAG answer สั้น + no-data phrase
  7. Legacy path no-data
```

---

## 7. Memory & Context System

```
User sends message
     |
     v
add_to_memory(user_id, "user", message)     ─── parallel
get_enhanced_context(user_id, current_query)  ─── parallel
     |
     v
Session Timeout Check (MEMORY_SESSION_TIMEOUT_HOURS = 6)
     |
     +── Last message > 6 hours ago → return "" (start fresh)
     +── Last message ≤ 6 hours → build context
     |
     v
compute_active_topic(messages, current_query)
     |
     +-- [บทสนทนาปัจจุบัน] → active topic messages
     +-- [สินค้าล่าสุดในบทสนทนา] → recent product names from metadata
     +-- [สรุปหัวข้อก่อนหน้า] → older topic summary
     +-- [สินค้าที่เคยแนะนำในอดีต] → all recommended products
     +-- [หัวข้อที่กำลังคุย] → topics + plants
     |
     v
context string → passed to RAG pipeline + handler
```

### Memory Config

| ค่า | ตัวเลข | หน้าที่ |
|-----|--------|---------|
| เก็บ | 50 ข้อความ/user | ลบเก่าอัตโนมัติ (ไม่มี TTL) |
| ส่ง LLM | 10 ข้อความล่าสุด | context สำหรับ Agent 1 |
| ตัดข้อความ | 2,000 ตัวอักษร | ป้องกัน token เยอะ |
| Preview | 800 ตัวอักษร | metadata preview |
| Session timeout | 6 ชม. | ถ้าหายไปเกิน 6 ชม. → ไม่ส่ง context เก่า |
| Cache TTL | 1 ชม. | คำตอบเดิมใช้ซ้ำ |
| Conversation State TTL | 30 นาที | จำ product/intent ที่กำลังคุย |

---

## 8. Anti-Hallucination Safeguards

| Layer | วิธีการ |
|-------|---------|
| RAG-First Routing | ทุกอย่างเข้า RAG (ไม่ส่ง general chat ที่มั่วได้) |
| General Chat neutered | temp=0.3, max=150 tokens, ห้ามพูดเกษตร/สินค้า |
| [CONSTRAINT] Tags | dictionary-matched entities → LLM ห้าม override |
| Product Name Validation | ชื่อสินค้าใน answer ต้องมีใน DB |
| Number Validation | ตรวจตัวเลขใน answer vs source docs |
| Crop-Mismatch Penalty | Stage 3.65: ห้ามใช้ -0.30, ไม่ระบุ -0.15, ตรง +0.05 |
| Crop Warning Tags | inject [!! ห้ามใช้/ไม่ได้ระบุ !!] ลงใน LLM context |
| Broader Crop Category | ข้าว→พืชไร่, ทุเรียน→ไม้ผล — ป้องกัน false penalty |
| Boundary Disease Match | regex ป้องกัน ใบไหม้ match กาบใบไหม้ |
| Cross-Product Exempt | สินค้าที่ user ถามไม่ถูก replace |
| Bundle Product Guard | ชุด/กล่อง/รวง ไม่ force-promote to #1 |
| Crop Pre-Filter | กรอง crop-mismatched docs ก่อนส่ง LLM |
| No-Data Reply | ไม่พบข้อมูล → ตอบข้อความกำลังตรวจสอบ (ไม่เงียบ) |
| Session Timeout | หายไป >6 ชม. → ไม่ส่ง context เก่าที่ไม่เกี่ยว |

---

## 9. Key Config Values (config.py)

| Constant | Value | ใช้ที่ |
|----------|-------|--------|
| LLM_MODEL_QUERY_UNDERSTANDING | gpt-4o-mini | Agent 1 |
| LLM_MODEL_RERANKING | gpt-4o-mini | Agent 2 (re-rank) |
| LLM_MODEL_RESPONSE_GEN | gpt-4o | Agent 4 |
| LLM_MODEL_GENERAL_CHAT | gpt-4o | General chat |
| EMBEDDING_MODEL | text-embedding-3-small | Vector search |
| LLM_TEMP_RESPONSE_GEN | 0.2 | Agent 4 creativity |
| LLM_TOKENS_RESPONSE_GEN | 600 | Agent 4 max output |
| VECTOR_THRESHOLD | 0.25 | Minimum vector similarity |
| RERANK_THRESHOLD | 0.50 | Minimum rerank score |
| PRODUCT_TABLE | products3 | Supabase table name |
| PRODUCT_RPC | hybrid_search_products3 | Supabase RPC function |
| MEMORY_TABLE | memory_chatladda | Conversation memory table |
| MEMORY_SESSION_TIMEOUT_HOURS | 6 | Session timeout (hours) |
| CACHE_TTL | 3600 | Cache expiry (1 hour) |
| CONVERSATION_STATE_TTL | 1800 | Conversation state expiry (30 min) |
| MAX_MEMORY_MESSAGES | 50 | Messages kept per user |
| MEMORY_CONTEXT_WINDOW | 10 | Messages sent to LLM |

---

## 10. Files Reference

| File | Role |
|------|------|
| `app/main.py` | FastAPI app + lifespan |
| `app/config.py` | Centralized config + LLM parameters + env vars |
| `app/prompts.py` | Persona + prompt templates + anti-hallucination |
| `app/routers/webhook.py` | LINE webhook entry point + event dispatch |
| `app/routers/facebook_webhook.py` | FB Messenger webhook |
| `app/routers/admin.py` | Admin login/logout, embeddings, cache |
| `app/routers/admin_chat.py` | Admin chat — ตอบแทน bot |
| `app/routers/dashboard.py` | Dashboard HTML + analytics API |
| `app/services/chat/handler.py` | Main routing + RAG-first logic (~1,350 lines) |
| `app/services/rag/orchestrator.py` | RAG pipeline coordinator + Stage 0 (~540 lines) |
| `app/services/rag/query_understanding_agent.py` | Agent 1: Intent + entity extraction (~415 lines) |
| `app/services/rag/retrieval_agent.py` | Agent 2: Vector search + re-rank (~1,090 lines) |
| `app/services/rag/response_generator_agent.py` | Agent 4: Answer synthesis (~690 lines) |
| `app/services/product/recommendation.py` | Product recommendation engine (~150KB) |
| `app/services/product/registry.py` | ProductRegistry singleton (DB-driven) |
| `app/services/memory.py` | Conversation memory + session timeout |
| `app/services/cache.py` | Redis/in-memory cache |
| `app/services/analytics.py` | Analytics tracking (question, product_rec, error) |
| `app/services/handoff.py` | Admin handoff manager |
| `app/services/user_service.py` | User profile tracking |
| `app/utils/text_processing.py` | Thai variant gen, diacritics, number validation |
| `app/utils/line/helpers.py` | LINE API: reply, push, verify |
| `app/utils/line/flex_messages.py` | LINE Flex Message templates (~120KB) |
| `app/utils/facebook/helpers.py` | FB API: send_message, verify |
| `migrations/generate_embeddings.py` | Generate embeddings for products |
| `migrations/setup_new_supabase_7tables.py` | Setup 7 tables in new Supabase |
| `.github/workflows/ci.yml` | CI pipeline (lint+test+import+docker) |
| `tests/` | 133+ pytest tests |

---

## 11. CI/CD Pipeline

```
Push/PR → main branch
    │
    ├── [1] Lint (ruff) ──────── syntax errors ใน app/
    │
    ├── [2] Test (pytest 133+) ── imports + health + config + RAG + Thai text + crop filtering
    │
    ├── [3] Import Check ─────── verify critical modules load cleanly
    │
    └── [4] Docker Build ─────── build image (ต้อง test ผ่านก่อน)

Deploy: Railway auto-deploy from GitHub main branch
        Dockerfile: gunicorn -w ${WEB_CONCURRENCY:-8} -k uvicorn.workers.UvicornWorker
```

---

## 12. Platform Support

| Platform | User ID Format | Message Limit | Features | Status |
|----------|---------------|---------------|----------|--------|
| LINE | `U{hex}` | 5,000 chars | text + image + sticker + flex | Production |
| Facebook | `fb:{psid}` | 2,000 chars (auto-split) | text only | Production |
