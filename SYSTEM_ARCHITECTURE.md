# SYSTEM ARCHITECTURE - น้องลัดดา Chatbot v2.6

## สถาปัตยกรรมภาพรวม

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER (LINE App)                                 │
│                    ส่ง รูปภาพ / ข้อความ / ตำแหน่ง                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LINE Platform                                        │
│                    Webhook → FastAPI Server                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FastAPI Application                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 1. Verify LINE Signature                                            │   │
│  │ 2. Check Rate Limit (10 req/min)                                    │   │
│  │ 3. Auto-register User                                               │   │
│  │ 4. Route to Handler                                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
    ┌──────────┐            ┌──────────────┐          ┌─────────────┐
    │  Image   │            │    Text      │          │  Location   │
    │ Handler  │            │   Handler    │          │   Handler   │
    └──────────┘            └──────────────┘          └─────────────┘
          │                         │                         │
          ▼                         ▼                         ▼
   Disease Detection         Chat/Q&A System           Weather API
          │                         │                         │
          ▼                         ▼                         ▼
   Product Recommend         Knowledge Base            Agro-Risk API
```

---

## Changelog v2.6 (December 2024)

### 🆕 การเปลี่ยนแปลงหลัก

| หัวข้อ | ก่อน (v2.5) | หลัง (v2.6) |
|--------|-------------|-------------|
| **Product Search** | Hybrid Search First | **Direct Query First** + Hybrid Fallback |
| **Re-ranker** | ใช้ทุกครั้ง (เสียเวลา 1-2s) | **ไม่จำเป็นแล้ว** (Direct Query แม่นยำพอ) |
| **Oomycetes Filter** | Filter จาก Hybrid results | **Direct Query by pathogen_type** |
| **โรคกาบใบข้าว** | ไม่มีกฎแยก | **เพิ่มกฎแยก 3 โรค** (กาบใบแห้ง/เน่า/ไหม้) |
| **Response Time** | 3-5 วินาที | **0.7-1.5 วินาที** |

---

## 1. External APIs และหน้าที่

| API | Provider | หน้าที่ | Model/Endpoint |
|-----|----------|---------|----------------|
| **LINE Messaging API** | LINE | รับ/ส่งข้อความ, รูปภาพ | `/v2/bot/message/*` |
| **Gemini 2.5 Pro** | Google (via OpenRouter) | วิเคราะห์โรคพืชจากรูป (Vision) | `google/gemini-2.5-pro-preview` |
| **Gemini 2.5 Flash** | Google (via OpenRouter) | จำแนกประเภทเบื้องต้น (เร็ว) | `google/gemini-2.5-flash-preview` |
| **GPT-4o-mini** | OpenAI | Chat/Q&A | `gpt-4o-mini` |
| **text-embedding-ada-002** | OpenAI | สร้าง Vector Embeddings | `text-embedding-ada-002` |
| **Supabase** | Supabase | Database + Vector Search | PostgreSQL + pgvector |
| **Agro-Risk API** | Thai Water | ข้อมูลสภาพอากาศ, ความเสี่ยงพืช | `/api/v1/weather/*` |

---

## 2. Disease Detection Flow (วิเคราะห์โรคพืช)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DISEASE DETECTION FLOW                                │
└─────────────────────────────────────────────────────────────────────────────┘

User ส่งรูปภาพ
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 1: ตรวจสอบการลงทะเบียน                                                  │
│ ├─ is_registration_completed(user_id)                                        │
│ └─ ถ้ายังไม่ลงทะเบียน → ส่ง LIFF Registration                               │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 2: ดึงรูปจาก LINE                                                       │
│ ├─ get_image_content_from_line(message_id)                                   │
│ └─ Endpoint: https://api-data.line.me/v2/bot/message/{id}/content           │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3: วิเคราะห์โรค (Gemini 2.5 Pro)                                        │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │ smart_detect_disease(image_bytes, extra_user_info)                 │     │
│  │                                                                    │     │
│  │  1. Check Cache (image_hash)                                      │     │
│  │  2. Encode Image → Base64                                         │     │
│  │  3. Generate Prompt with Differentiation Rules                    │     │
│  │  4. Call Gemini 2.5 Pro (Timeout: 60s)                            │     │
│  │  5. Parse JSON Response                                           │     │
│  │  6. Cache Result (TTL: 1 hour)                                    │     │
│  └────────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 4: ถามระยะการปลูก → Step 5: ค้นหาและแนะนำสินค้า (ดู Section 3)         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 กฎการแยกโรคที่สำคัญ (Differentiation Rules)

#### 🌾 โรคกาบใบข้าว 3 โรค (NEW in v2.6)

| ลักษณะ | กาบใบแห้ง (Sheath Blight) | กาบใบเน่า (Sheath Rot) | ใบไหม้ (Rice Blast) |
|--------|--------------------------|----------------------|---------------------|
| **⭐ ตำแหน่ง** | **กาบใบ** (ใกล้ระดับน้ำ) | **กาบใบธง** (ใกล้รวง) | **แผ่นใบ** (ไม่ใช่กาบ) |
| **เชื้อสาเหตุ** | Rhizoctonia solani | Sarocladium oryzae | Pyricularia oryzae |
| **รูปร่างแผล** | วงรี/รูปไข่ ใหญ่ | ไม่แน่นอน เป็นแถบ | รูปเพชร/ตา หัวท้ายแหลม |
| **ลักษณะพิเศษ** | มี **sclerotia** สีน้ำตาล | รวงข้าวไม่ออก/ลีบ | อาจลามไปคอรวง |

**วิธีจำ:**
- แผลที่ **กาบใบ** + มี sclerotia = **กาบใบแห้ง**
- แผลที่ **กาบใบธง** + รวงไม่ออก = **กาบใบเน่า**
- แผล **รูปเพชร บนแผ่นใบ** = **ใบไหม้**

#### อื่นๆ
- Brown Spot vs Leaf Spot vs Anthracnose
- Rice Blast vs Brown Spot vs Bacterial Leaf Blight
- เพลี้ยกระโดด vs เพลี้ยจักจั่น vs เพลี้ยไฟ

---

## 3. Product Recommendation Flow (แนะนำสินค้า) 🆕 v2.6

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              PRODUCT RECOMMENDATION FLOW (v2.6 - Direct Query First)        │
└─────────────────────────────────────────────────────────────────────────────┘

Input: disease_name + plant_type + growth_stage
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🆕 STEP 1: Direct Query First (แม่นยำ 100%)                                  │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │ query_products_by_target_pest(disease_name)                        │     │
│  │                                                                    │     │
│  │  SELECT * FROM products                                           │     │
│  │  WHERE target_pest ILIKE '%keyword%'                              │     │
│  │                                                                    │     │
│  │  ✅ ถ้าพบ → ได้ผลลัพธ์ที่ตรงกับโรค 100%                           │     │
│  │  ⚠️ ถ้าไม่พบ → ไปขั้นตอนถัดไป                                     │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
│  ตัวอย่าง:                                                                   │
│  disease_name = "โรคกาบใบแห้ง"                                              │
│  → keywords: ["กาบใบ", "sheath", "rhizoctonia"]                             │
│  → SELECT * FROM products WHERE target_pest ILIKE '%กาบใบ%'                 │
│  → ผลลัพธ์: เทอราโน่, รีโนเวท (ตรง 100%)                                    │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼ (ถ้าได้ < 3 ตัว)
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: Hybrid Search Fallback                                               │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │ hybrid_search_products(query, match_count=20)                      │     │
│  │                                                                    │     │
│  │  Vector Search (50%) + Keyword Search (50%)                       │     │
│  │  → รวมเฉพาะที่ยังไม่มีใน Direct Query results                     │     │
│  └────────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 3: Filter by Category & Plant                                           │
│                                                                              │
│  filter_products_by_category() → กรองตามประเภทยา                            │
│  filter_products_by_plant() → กรองตามชนิดพืช                                │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🆕 STEP 4: Pathogen Type Filter (Oomycetes vs Fungi)                         │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │ is_oomycetes_disease(disease_name) ?                               │     │
│  │                                                                    │     │
│  │  YES → fetch_products_by_pathogen_type("oomycetes", plant_type)   │     │
│  │        🆕 Direct Query แทน Filter (ได้ครบทุกตัว!)                  │     │
│  │        → คาริสมา, วอร์แรนต์, ไซม๊อกซิเมท                          │     │
│  │                                                                    │     │
│  │  NO  → filter_products_for_fungi()                                 │     │
│  │        → เทอราโน่, อาร์เทมีส, ท็อปกัน                              │     │
│  └────────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 5: Calculate Matching Score & Return                                    │
│                                                                              │
│  calculate_matching_score() → คำนวณคะแนนความเกี่ยวข้อง                      │
│  build_recommendations_from_data() → สร้าง ProductRecommendation            │
│  create_product_carousel_flex() → สร้าง Flex Message                         │
│                                                                              │
│  ❌ Re-ranker ไม่จำเป็นแล้ว (Direct Query แม่นยำพอ)                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 เปรียบเทียบ v2.5 vs v2.6

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ v2.5 (Hybrid Search First):                                                  │
│                                                                              │
│  Hybrid Search → 20 ตัว (ปนกันหลายประเภท)                                   │
│       │                                                                      │
│       ▼                                                                      │
│  Filter by Category/Plant → อาจเหลือไม่ตรง                                  │
│       │                                                                      │
│       ▼                                                                      │
│  Re-ranker (LLM) → +1-2 วินาที → จัดอันดับใหม่                              │
│       │                                                                      │
│       ▼                                                                      │
│  Results → อาจไม่ตรง 100%                                                   │
│                                                                              │
│  ❌ ช้า (3-5 วินาที)                                                        │
│  ❌ ใช้ token มาก (Re-ranker)                                               │
│  ❌ อาจไม่แม่นยำ                                                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ v2.6 (Direct Query First):                                                   │
│                                                                              │
│  Direct Query by target_pest → 2-5 ตัว (ตรงกับโรค 100%)                     │
│       │                                                                      │
│       ▼ (ถ้าได้ < 3 ตัว)                                                    │
│  Hybrid Search Fallback → เพิ่มเติม                                         │
│       │                                                                      │
│       ▼                                                                      │
│  Filter & Score → Results                                                    │
│                                                                              │
│  ✅ เร็ว (0.7-1.5 วินาที)                                                   │
│  ✅ ประหยัด token (ไม่ต้อง Re-rank)                                         │
│  ✅ แม่นยำ 100%                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Pathogen Type System (ระบบจำแนกประเภทเชื้อก่อโรค)

### 4.1 ทำไมต้องมี pathogen_type?

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ปัญหา: ยากำจัดเชื้อราไม่ได้ใช้ได้กับทุกโรค!                                  │
│                                                                              │
│ Oomycetes (เชื้อราชั้นต่ำ)          True Fungi (เชื้อราแท้)                  │
│ ├─ Phytophthora                     ├─ Colletotrichum (Anthracnose)         │
│ ├─ Pythium                          ├─ Cercospora (Leaf Spot)               │
│ └─ ต้องใช้ยาเฉพาะ:                   └─ ใช้ยาทั่วไป:                          │
│    • Propamocarb                       • Propiconazole                       │
│    • Fosetyl-Al                        • Azoxystrobin                        │
│    • Metalaxyl                         • Mancozeb                            │
│    • Cymoxanil                         • Carbendazim                         │
│                                                                              │
│ ❌ ถ้าใช้ Mancozeb รักษา Phytophthora → ไม่ได้ผล!                           │
│ ❌ ถ้าใช้ Propamocarb รักษา Leaf Spot → เปลืองเงิน ไม่จำเป็น!               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 pathogen_type Values

| pathogen_type | คำอธิบาย | ตัวอย่างสินค้า |
|---------------|----------|---------------|
| `oomycetes` | ยาเฉพาะ Phytophthora/Pythium | คาริสมา, วอร์แรนต์, ไซม๊อกซิเมท |
| `fungi` | ยากำจัดเชื้อราทั่วไป | เทอราโน่, อาร์เทมีส, ท็อปกัน |
| `insect` | ยากำจัดแมลง | เกรค, อิมิดาโกลด์, ไฮซีส |
| `herbicide` | ยากำจัดวัชพืช | อัพดาว, พาสนาว, ซิมเมอร์ |
| `pgr` | สารควบคุมการเจริญเติบโต | พรีดิคท์ |

### 4.3 🆕 Direct Query for Oomycetes (v2.6)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ v2.5: Filter จาก Hybrid Search results                                       │
│                                                                              │
│  Hybrid Search → [คาริสมา, ท็อปกัน, โค-ราช, ...]                            │
│       │                                                                      │
│       ▼                                                                      │
│  filter_products_for_oomycetes() → [คาริสมา]                                │
│                                                                              │
│  ❌ ปัญหา: ถ้า Hybrid Search ไม่คืน วอร์แรนต์/ไซม๊อกซิเมท                   │
│           → Filter จะไม่เห็นมัน → ได้แค่ 1 ตัว                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ v2.6: Direct Query by pathogen_type                                          │
│                                                                              │
│  fetch_products_by_pathogen_type("oomycetes", plant_type)                   │
│       │                                                                      │
│       ▼                                                                      │
│  SELECT * FROM products WHERE pathogen_type = 'oomycetes'                    │
│       │                                                                      │
│       ▼                                                                      │
│  [คาริสมา, วอร์แรนต์, ไซม๊อกซิเมท] → ครบ 3 ตัว! ✅                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Hybrid Search SQL Function

```sql
┌─────────────────────────────────────────────────────────────────────────────┐
│                    hybrid_search_products()                                  │
│                         PostgreSQL Function                                  │
└─────────────────────────────────────────────────────────────────────────────┘

Input Parameters:
├─ query_embedding: vector(1536)
├─ search_query: text
├─ vector_weight: float (0.5)     -- ปรับจาก 0.6 เป็น 0.5
├─ keyword_weight: float (0.5)    -- ปรับจาก 0.4 เป็น 0.5
├─ match_threshold: float (0.15)
└─ match_count: int (15)

Output: products with pathogen_type, vector_score, keyword_score, hybrid_score
```

---

## 6. Database Schema

### 6.1 products table

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    product_name TEXT,
    product_category TEXT,          -- "ป้องกันโรค", "กำจัดแมลง", "กำจัดวัชพืช"
    active_ingredient TEXT,
    target_pest TEXT,               -- ⭐ ใช้ Direct Query
    applicable_crops TEXT,
    usage_rate TEXT,
    usage_period TEXT,
    how_to_use TEXT,
    link_product TEXT,

    -- Vector Search
    embedding VECTOR(1536),
    search_vector TSVECTOR,

    -- Pathogen Classification
    pathogen_type TEXT              -- ⭐ 'oomycetes', 'fungi', 'insect', etc.
);

-- Indexes
CREATE INDEX idx_products_embedding ON products USING ivfflat (embedding);
CREATE INDEX idx_products_search_vector ON products USING GIN(search_vector);
CREATE INDEX idx_products_pathogen_type ON products(pathogen_type);
CREATE INDEX idx_products_target_pest ON products USING GIN(to_tsvector('simple', target_pest));
```

---

## 7. File Structure

```
chatbot-ladda/
├── app/
│   ├── main.py                      # FastAPI entry, webhook handler
│   ├── config.py                    # Environment variables
│   ├── models.py                    # Pydantic models
│   │
│   ├── services/
│   │   ├── disease_detection.py     # Gemini vision + Differentiation Rules
│   │   ├── product_recommendation.py # 🆕 Direct Query First + Hybrid Fallback
│   │   ├── chat.py                  # Q&A conversation
│   │   ├── knowledge_base.py        # RAG knowledge search
│   │   ├── reranker.py              # LLM re-ranking (ใช้ใน chat เท่านั้น)
│   │   ├── cache.py                 # Caching system
│   │   ├── user_service.py          # User management
│   │   └── agro_risk.py             # Weather API
│   │
│   └── utils/
│       ├── line_helpers.py          # LINE API utilities
│       ├── flex_messages.py         # Flex Message templates
│       └── rate_limiter.py          # Rate limiting
│
├── scripts/
│   ├── add_pathogen_type.py         # กำหนด pathogen_type ให้สินค้า
│   ├── test_reranker_comparison.py  # 🆕 Test script เปรียบเทียบ
│   └── update_hybrid_search_pathogen.sql
│
├── SYSTEM_ARCHITECTURE.md           # This file
└── requirements.txt
```

---

## 8. Performance Comparison

| Metric | v2.5 | v2.6 | Improvement |
|--------|------|------|-------------|
| **Response Time** | 3-5 sec | 0.7-1.5 sec | **3x faster** |
| **Accuracy (Oomycetes)** | 1/3 ตัว | 3/3 ตัว | **100%** |
| **Token Usage** | High (Re-rank) | Low | **ประหยัด 50%+** |
| **API Calls** | 3-4 calls | 1-2 calls | **ลด 50%** |

---

## 9. Error Handling

| Error | Fallback Strategy |
|-------|-------------------|
| Gemini API Timeout | Retry 1x, then return generic error |
| Direct Query No Results | Fallback to Hybrid Search |
| Vector Search Failed | Fallback to Keyword Search (ILIKE) |
| No Products Found | Return empty list with message |
| JSON Parse Error | Robust parsing with regex |

---

## 10. Key Functions (v2.6)

### Product Recommendation

| Function | Description | ใช้ใน |
|----------|-------------|-------|
| `query_products_by_target_pest()` | 🆕 Direct Query จาก target_pest | Step 1 |
| `fetch_products_by_pathogen_type()` | 🆕 Direct Query by pathogen_type | Oomycetes |
| `hybrid_search_products()` | Vector + Keyword Search | Fallback |
| `filter_products_for_oomycetes()` | Filter by pathogen_type='oomycetes' | Backup |
| `filter_products_for_fungi()` | Filter by pathogen_type='fungi' | Fungi diseases |
| `calculate_matching_score()` | คำนวณความเกี่ยวข้อง | Scoring |

### Disease Detection

| Function | Description |
|----------|-------------|
| `smart_detect_disease()` | Entry point - เลือก v1 หรือ v2 |
| `detect_disease_v2()` | 3-step analysis (classify → analyze → verify) |
| `is_oomycetes_disease()` | ตรวจสอบว่าเป็น Oomycetes หรือไม่ |

---

*Last Updated: December 2024*
*Version: 2.6.0 (Direct Query First + Sheath Disease Rules)*
