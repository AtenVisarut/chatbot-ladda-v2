# SYSTEM ARCHITECTURE - น้องลัดดา Chatbot v2.5

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

## 1. External APIs และหน้าที่

| API | Provider | หน้าที่ | Model/Endpoint |
|-----|----------|---------|----------------|
| **LINE Messaging API** | LINE | รับ/ส่งข้อความ, รูปภาพ | `/v2/bot/message/*` |
| **Gemini 2.5 Pro** | Google (via OpenRouter) | วิเคราะห์โรคพืชจากรูป (Vision) | `google/gemini-2.5-pro-preview` |
| **Gemini 2.5 Flash** | Google (via OpenRouter) | จำแนกประเภทเบื้องต้น (เร็ว) | `google/gemini-2.5-flash-preview` |
| **GPT-4o-mini** | OpenAI | Chat/Q&A, Re-ranking สินค้า | `gpt-4o-mini` |
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
│ Step 3: ถามข้อมูลเพิ่มเติม (Optional)                                        │
│ ├─ "ปัญหาพบที่ส่วนไหนของพืช?"                                                │
│ ├─ "ใช้เวลานานแค่ไหนแล้ว?"                                                   │
│ └─ "มีการใช้สารเคมีหรือปุ๋ยอะไรก่อนหน้า?"                                     │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 4: วิเคราะห์โรค (Gemini 2.5 Pro)                                        │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │ smart_detect_disease(image_bytes, extra_user_info)                 │     │
│  │                                                                    │     │
│  │  1. Check Cache (image_hash) → ถ้ามี return ทันที                  │     │
│  │  2. Encode Image → Base64                                         │     │
│  │  3. Generate Prompt:                                              │     │
│  │     • Disease Database (Fungal, Bacterial, Viral, Insect)         │     │
│  │     • 6-Step Analysis Process                                     │     │
│  │     • Differentiation Tables                                      │     │
│  │  4. Call Gemini 2.5 Pro (OpenRouter)                              │     │
│  │     • Timeout: 60 seconds                                         │     │
│  │  5. Parse JSON Response                                           │     │
│  │  6. Cache Result (TTL: 1 hour)                                    │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
│  Output: DiseaseDetectionResult                                              │
│  ├─ disease_name: ชื่อโรค (ไทย + English)                                    │
│  ├─ confidence: ความเชื่อมั่น (0-100%)                                       │
│  ├─ severity: ระดับความรุนแรง (ต่ำ/ปานกลาง/สูง)                              │
│  ├─ symptoms: อาการที่พบ                                                     │
│  ├─ cause: สาเหตุ (เชื้อรา/แบคทีเรีย/ไวรัส/แมลง)                              │
│  ├─ treatment: วิธีรักษา                                                     │
│  ├─ prevention: วิธีป้องกัน                                                  │
│  └─ plant_type: ชนิดพืช                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 5: ตรวจสอบว่าควรแนะนำสินค้าหรือไม่                                       │
│                                                                              │
│  Skip Keywords (ไม่แนะนำสินค้า):                                             │
│  • "ไม่พบ", "ปกติ", "สุขภาพดี", "healthy"                                   │
│  • "ขาดธาตุ", "ขาดไนโตรเจน", "Deficiency"                                   │
│                                                                              │
│  ถ้า skip → ส่งผลวิเคราะห์โดยไม่มีสินค้า                                     │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 6: ถามระยะการปลูก                                                       │
│ • ระยะกล้า (0-20 วัน)                                                        │
│ • ระยะแตกกอ (20-50 วัน)                                                      │
│ • ระยะตั้งท้อง (50-70 วัน)                                                   │
│ • ระยะออกรวง (70-90 วัน)                                                     │
│ • ระยะเก็บเกี่ยว (90+ วัน)                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 7: ค้นหาและแนะนำสินค้า → ดู Section 3                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Product Recommendation Flow (แนะนำสินค้า)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     PRODUCT RECOMMENDATION FLOW                              │
└─────────────────────────────────────────────────────────────────────────────┘

Input: disease_name + plant_type + growth_stage
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 0: Pre-filtering                                                        │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │ is_bacterial_disease(disease_name)                                 │     │
│  │ • ถ้าเป็นโรคแบคทีเรีย → return [] (ไม่มียาในฐานข้อมูล)             │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                              │                                               │
│                              ▼                                               │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │ get_required_category(disease_name)                                │     │
│  │ • โรคเชื้อรา → "ป้องกันโรค" (Fungicide)                            │     │
│  │ • แมลง → "กำจัดแมลง" (Insecticide)                                 │     │
│  │ • วัชพืช → "กำจัดวัชพืช" (Herbicide)                               │     │
│  └────────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 1: Dynamic Query (ค้นหาตรงจาก target_pest)                              │
│                                                                              │
│  SELECT * FROM products                                                      │
│  WHERE target_pest ILIKE '%keyword%'                                         │
│  AND product_category = required_category                                    │
│                                                                              │
│  ✅ ถ้าพบ → return ผลลัพธ์ทันที (ไม่ต้องทำ Vector Search)                    │
└─────────────────────────────────────────────────────────────────────────────┘
      │ (ถ้าไม่พบ)
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 2: Hybrid Search (Vector + Keyword)                                     │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │                    hybrid_search_products()                        │     │
│  │                         SQL Function                               │     │
│  │                                                                    │     │
│  │  ┌──────────────────────┐    ┌──────────────────────┐             │     │
│  │  │   Vector Search      │    │   Keyword Search     │             │     │
│  │  │     (60% weight)     │    │     (40% weight)     │             │     │
│  │  ├──────────────────────┤    ├──────────────────────┤             │     │
│  │  │ • OpenAI Embedding   │    │ • Full-Text Search   │             │     │
│  │  │ • pgvector similarity│    │ • ILIKE matching     │             │     │
│  │  │ • ค้นหาความหมาย       │    │ • ค้นหาคำตรง          │             │     │
│  │  └──────────────────────┘    └──────────────────────┘             │     │
│  │              │                         │                          │     │
│  │              └────────────┬────────────┘                          │     │
│  │                           ▼                                       │     │
│  │              ┌──────────────────────┐                             │     │
│  │              │ Reciprocal Rank      │                             │     │
│  │              │ Fusion (RRF)         │                             │     │
│  │              │ รวมคะแนนทั้ง 2 วิธี    │                             │     │
│  │              └──────────────────────┘                             │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
│  hybrid_score = (0.6 × vector_score) + (0.4 × keyword_score) + bonus        │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3: Pathogen Type Filtering (สำคัญมาก!)                                  │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │ is_oomycetes_disease(disease_name) ?                               │     │
│  │                                                                    │     │
│  │  YES → filter_products_for_oomycetes()                             │     │
│  │        กรองเฉพาะ pathogen_type = 'oomycetes'                       │     │
│  │        ✅ คาริสมา (Propamocarb)                                    │     │
│  │        ✅ วอร์แรนต์ (Fosetyl-Al)                                   │     │
│  │        ✅ ไซม๊อกซิเมท (Cymoxanil)                                  │     │
│  │                                                                    │     │
│  │  NO → filter_products_for_fungi()                                  │     │
│  │       กรองเฉพาะ pathogen_type = 'fungi'                            │     │
│  │       ✅ เทอราโน่ (Propiconazole)                                  │     │
│  │       ✅ อาร์เทมีส (Azoxystrobin)                                  │     │
│  │       ✅ ท็อปกัน (Mancozeb)                                        │     │
│  │       ❌ คาริสมา (Propamocarb) → กรองออก                           │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
│  Oomycetes Diseases:                                                         │
│  • โรครากเน่าโคนเน่า (Phytophthora Root Rot)                                 │
│  • โรคผลเน่า (Fruit Rot - Phytophthora)                                      │
│  • โรคยางไหล (Gummosis)                                                      │
│  • ราน้ำค้าง (Downy Mildew - Pythium)                                        │
│                                                                              │
│  Fungi Diseases:                                                             │
│  • โรคใบจุด (Leaf Spot)                                                      │
│  • โรคแอนแทรคโนส (Anthracnose)                                               │
│  • โรคราสนิม (Rust)                                                          │
│  • โรคดอกกระถิน (False Smut)                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 4: Additional Filtering                                                 │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │ filter_products_by_category()                                      │     │
│  │ • กรองเฉพาะประเภทยาที่ต้องการ                                      │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                              │                                               │
│                              ▼                                               │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │ filter_products_by_plant()                                         │     │
│  │ • กรองเฉพาะยาที่ใช้ได้กับพืชชนิดนั้น                               │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                              │                                               │
│                              ▼                                               │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │ simple_relevance_boost()                                           │     │
│  │ • เพิ่มคะแนนถ้า target_pest ตรงกับโรค                              │     │
│  └────────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 5: LLM Re-ranking (Optional)                                            │
│                                                                              │
│  rerank_products_with_llm(query, products, top_k=6)                          │
│  • Model: GPT-4o-mini                                                        │
│  • Input: Top 15 candidates                                                  │
│  • Output: Re-ranked top 6                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 6: Build Response                                                       │
│                                                                              │
│  • build_recommendations_from_data(products[:6])                             │
│  • create_product_carousel_flex()                                            │
│  • Cache results (TTL: 1 hour)                                               │
│                                                                              │
│  Output: Flex Message Carousel                                               │
│  ├─ ชื่อสินค้า                                                               │
│  ├─ สารออกฤทธิ์                                                              │
│  ├─ ศัตรูพืชที่กำจัดได้                                                       │
│  ├─ วิธีใช้ + อัตราการใช้                                                     │
│  └─ Link สินค้า                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Hybrid Search SQL Function (รายละเอียด)

```sql
┌─────────────────────────────────────────────────────────────────────────────┐
│                    hybrid_search_products()                                  │
│                         PostgreSQL Function                                  │
└─────────────────────────────────────────────────────────────────────────────┘

Input Parameters:
├─ query_embedding: vector(1536)  -- จาก OpenAI
├─ search_query: text             -- คำค้นหา
├─ vector_weight: float (0.6)     -- น้ำหนัก Vector
├─ keyword_weight: float (0.4)    -- น้ำหนัก Keyword
├─ match_threshold: float (0.15)  -- threshold ขั้นต่ำ
└─ match_count: int (15)          -- จำนวนผลลัพธ์

┌─────────────────────────────────────────────────────────────────────────────┐
│ WITH vector_results AS (                                                     │
│     -- Vector Search: ค้นหาตามความหมาย                                       │
│     SELECT id,                                                               │
│            1 - (embedding <=> query_embedding) as v_score                    │
│     FROM products                                                            │
│     WHERE similarity > threshold                                             │
│     LIMIT 30                                                                 │
│ ),                                                                           │
│                                                                              │
│ keyword_results AS (                                                         │
│     -- Keyword Search: ค้นหาคำตรง                                            │
│     SELECT id,                                                               │
│            ts_rank_cd(search_vector, query) as k_score                       │
│     FROM products                                                            │
│     WHERE search_vector @@ query                                             │
│        OR product_name ILIKE '%query%'                                       │
│        OR target_pest ILIKE '%query%'                                        │
│     LIMIT 30                                                                 │
│ ),                                                                           │
│                                                                              │
│ combined AS (                                                                │
│     -- รวมคะแนน (RRF)                                                        │
│     SELECT                                                                   │
│         COALESCE(v.id, k.id) as id,                                          │
│         0.6 * v_score + 0.4 * k_score + bonus as hybrid_score               │
│     FROM vector_results v                                                    │
│     FULL OUTER JOIN keyword_results k ON v.id = k.id                         │
│ )                                                                            │
│                                                                              │
│ SELECT p.*, c.hybrid_score, p.pathogen_type                                  │
│ FROM combined c                                                              │
│ JOIN products p ON p.id = c.id                                               │
│ ORDER BY hybrid_score DESC                                                   │
│ LIMIT match_count;                                                           │
└─────────────────────────────────────────────────────────────────────────────┘

Example Scoring:
┌────────────┬──────────────┬───────────────┬───────┬──────────────┐
│ Product    │ Vector Score │ Keyword Score │ Bonus │ Hybrid Score │
├────────────┼──────────────┼───────────────┼───────┼──────────────┤
│ คาริสมา    │ 0.80         │ 0.90          │ 0.10  │ 0.94         │
│ วอร์แรนต์  │ 0.75         │ 0.85          │ 0.10  │ 0.89         │
│ ท็อปกัน    │ 0.50         │ 0.30          │ 0.10  │ 0.52         │
└────────────┴──────────────┴───────────────┴───────┴──────────────┘
```

---

## 5. Pathogen Type System (ระบบจำแนกประเภทเชื้อก่อโรค)

### 5.1 ทำไมต้องมี pathogen_type?

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

### 5.2 pathogen_type Values

| pathogen_type | คำอธิบาย | ตัวอย่างสินค้า |
|---------------|----------|---------------|
| `oomycetes` | ยาเฉพาะ Phytophthora/Pythium | คาริสมา, วอร์แรนต์, ไซม๊อกซิเมท |
| `fungi` | ยากำจัดเชื้อราทั่วไป | เทอราโน่, อาร์เทมีส, ท็อปกัน |
| `insect` | ยากำจัดแมลง | เกรค, อิมิดาโกลด์, ไฮซีส |
| `herbicide` | ยากำจัดวัชพืช | อัพดาว, พาสนาว, ซิมเมอร์ |
| `pgr` | สารควบคุมการเจริญเติบโต | พรีดิคท์ |

### 5.3 Filter Flow

```
                    ┌─────────────────┐
                    │  Disease Name   │
                    └────────┬────────┘
                             │
                             ▼
              ┌─────────────────────────────┐
              │ is_oomycetes_disease()?     │
              └──────────┬──────────────────┘
                         │
          ┌──────────────┴──────────────┐
          │ YES                         │ NO
          ▼                             ▼
┌─────────────────────┐      ┌─────────────────────┐
│ filter_for_oomycetes│      │ filter_for_fungi    │
│ pathogen_type =     │      │ pathogen_type =     │
│   'oomycetes'       │      │   'fungi'           │
└─────────────────────┘      └─────────────────────┘
          │                             │
          ▼                             ▼
┌─────────────────────┐      ┌─────────────────────┐
│ ✅ คาริสมา          │      │ ✅ เทอราโน่         │
│ ✅ วอร์แรนต์        │      │ ✅ อาร์เทมีส        │
│ ✅ ไซม๊อกซิเมท      │      │ ✅ ท็อปกัน          │
│ ❌ ท็อปกัน (กรองออก)│      │ ❌ คาริสมา (กรองออก)│
└─────────────────────┘      └─────────────────────┘
```

---

## 6. Database Schema

### 6.1 products table

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    product_name TEXT,                    -- ชื่อสินค้า
    product_category TEXT,                -- "ป้องกันโรค", "กำจัดแมลง", "กำจัดวัชพืช"
    active_ingredient TEXT,               -- สารออกฤทธิ์
    target_pest TEXT,                     -- ศัตรูพืชที่กำจัดได้ (ใช้ค้นหา)
    applicable_crops TEXT,                -- พืชที่ใช้ได้
    usage_rate TEXT,                      -- อัตราการใช้
    usage_period TEXT,                    -- ช่วงเวลาใช้
    how_to_use TEXT,                      -- วิธีใช้
    link_product TEXT,                    -- Link สินค้า

    -- Vector Search
    embedding VECTOR(1536),               -- OpenAI embedding
    search_vector TSVECTOR,               -- Full-text search vector

    -- Pathogen Classification (NEW!)
    pathogen_type TEXT                    -- 'oomycetes', 'fungi', 'insect', etc.
);

-- Indexes
CREATE INDEX idx_products_embedding ON products USING ivfflat (embedding);
CREATE INDEX idx_products_search_vector ON products USING GIN(search_vector);
CREATE INDEX idx_products_pathogen_type ON products(pathogen_type);
```

### 6.2 Other Tables

```sql
-- users: ข้อมูลผู้ใช้
CREATE TABLE users (
    id UUID PRIMARY KEY,
    line_user_id TEXT UNIQUE,
    display_name TEXT,
    phone TEXT,
    province TEXT,
    crops_grown TEXT[],
    registration_completed BOOLEAN DEFAULT FALSE
);

-- conversation_memory: ประวัติการสนทนา
CREATE TABLE conversation_memory (
    id UUID PRIMARY KEY,
    user_id TEXT,
    role TEXT,              -- "user" or "assistant"
    content TEXT,
    created_at TIMESTAMP
);

-- cache: Cache ผลการวิเคราะห์
CREATE TABLE cache (
    id UUID PRIMARY KEY,
    cache_type TEXT,        -- "detection", "products"
    cache_key TEXT,
    value JSONB,
    expires_at TIMESTAMP
);

-- knowledge: ฐานความรู้เกษตร
CREATE TABLE knowledge (
    id UUID PRIMARY KEY,
    title TEXT,
    content TEXT,
    category TEXT,
    embedding VECTOR(1536)
);
```

---

## 7. Special Cases

### 7.1 Vector Diseases (โรคที่มีแมลงพาหะ)

```
โรคจู๋ (Rice Ragged Stunt Virus)
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ โรคไวรัส → ไม่มียารักษา → ต้องกำจัดพาหะ                                      │
│                                                                              │
│ พาหะ: เพลี้ยกระโดดสีน้ำตาล (Brown Planthopper)                               │
│                                                                              │
│ search_query: "เพลี้ยกระโดดสีน้ำตาล ยาฆ่าแมลง BPH"                          │
│ required_category: "กำจัดแมลง" (ไม่ใช่ "ป้องกันโรค")                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Bacterial Diseases

```
โรคขอบใบแห้ง (Bacterial Leaf Blight)
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ is_bacterial_disease() = True                                                │
│                                                                              │
│ → return [] (ไม่แนะนำสินค้า)                                                 │
│ → แนะนำวิธีจัดการอื่น:                                                       │
│   • ใช้พันธุ์ต้านทาน                                                         │
│   • ลดปุ๋ยไนโตรเจน                                                          │
│   • ระบายน้ำให้ดี                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. File Structure

```
chatbot-ladda/
├── app/
│   ├── main.py                      # FastAPI entry, webhook handler
│   ├── config.py                    # Environment variables
│   ├── models.py                    # Pydantic models
│   │
│   ├── services/
│   │   ├── disease_detection.py     # Gemini vision analysis
│   │   ├── product_recommendation.py # Product search & pathogen filtering
│   │   ├── chat.py                  # Q&A conversation
│   │   ├── knowledge_base.py        # RAG knowledge search
│   │   ├── reranker.py              # LLM re-ranking
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
│   ├── setup_hybrid_search.sql      # สร้าง SQL functions
│   └── update_hybrid_search_pathogen.sql
│
├── SYSTEM_ARCHITECTURE.md           # This file
└── requirements.txt
```

---

## 9. Configuration

```python
# Environment Variables
LINE_CHANNEL_ACCESS_TOKEN    # LINE Bot Token
LINE_CHANNEL_SECRET          # LINE Signature Verification
OPENAI_API_KEY              # OpenAI (Embeddings, Chat)
OPENROUTER_API_KEY          # Gemini 2.5 Pro
SUPABASE_URL                # Database URL
SUPABASE_KEY                # Database Key

# Timeouts
API_TIMEOUT = 60            # Disease Detection
CACHE_TTL = 3600            # 1 hour

# Rate Limiting
RATE_LIMIT = 10             # requests/minute/user
```

---

## 10. Error Handling

| Error | Fallback Strategy |
|-------|-------------------|
| Gemini API Timeout | Retry 1x, then return generic error |
| Vector Search Failed | Fallback to Keyword Search (ILIKE) |
| RPC Not Found | Fallback to manual hybrid search |
| No Products Found | Return empty list with message |
| JSON Parse Error | Robust parsing with regex |
| Rate Limit Exceeded | Return "กรุณารอสักครู่" |
| User Not Registered | Redirect to LIFF Registration |

---

*Last Updated: December 2024*
*Version: 2.5.2 (with pathogen_type filtering)*
