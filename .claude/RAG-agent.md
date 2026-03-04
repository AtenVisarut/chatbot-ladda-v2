# Multi-Agent Agentic RAG Pipeline — ขั้นตอนการทำงาน

> ระบบค้นคืนและสร้างคำตอบอัตโนมัติแบบหลายเอเจนต์ (Multi-Agent Agentic RAG)
> สำหรับ Chatbot น้องลัดดา — ICP Ladda Agricultural Chatbot

---

## 1. ภาพรวมสถาปัตยกรรม (Architecture Overview)

ระบบใช้สถาปัตยกรรมแบบ **Multi-Agent Agentic RAG (Retrieval-Augmented Generation) Pipeline** ซึ่งแตกต่างจาก RAG ทั่วไปตรงที่ไม่ได้ใช้ framework สำเร็จรูป (เช่น LangChain, LlamaIndex) แต่ออกแบบและพัฒนา pipeline เองทั้งหมด เพื่อรองรับ business logic เฉพาะทางด้านเกษตรกรรม และจัดการกับปัญหา Hallucination ในหลายระดับ

### Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend Framework | FastAPI (Python 3.11) |
| LLM | OpenAI GPT-4o |
| Embedding Model | text-embedding-3-small (1,536 dimensions) |
| Vector Database | Supabase (PostgreSQL + pgvector) |
| Cache | Redis (Upstash) + In-Memory Cache |
| Deploy | Railway (auto-deploy from GitHub) |
| Channels | LINE Messaging API + Facebook Messenger |

### Flow Diagram

```
User Message (LINE / Facebook)
       │
       ▼
┌──────────────────────┐
│   Webhook Router     │  ← LINE signature / FB signature verification
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│   Chat Handler       │  ← Message routing (RAG-First)
│                      │
│  ├─ Greeting?        │──→ ตอบทักทายทันที (ไม่ผ่าน RAG)
│  ├─ Non-Agriculture? │──→ General Chat (LLM neutered)
│  └─ Default          │──→ เข้า RAG Pipeline ▼
└──────────┬───────────┘
           ▼
┌══════════════════════════════════════════════════════════════════╗
║                    AGENTIC RAG PIPELINE                        ║
║                                                                ║
║  ┌────────────────────────────────────────────────────────┐     ║
║  │  Stage 0: Domain-Specific Pre-Processing               │     ║
║  │  (Dictionary-Based — ไม่ใช้ LLM)                       │     ║
║  └───────────────────────┬────────────────────────────────┘     ║
║                          ▼                                     ║
║  ┌────────────────────────────────────────────────────────┐     ║
║  │  Agent 1: Query Understanding                          │     ║
║  │  (GPT-4o — Intent + NER + Query Expansion)             │     ║
║  └───────────────────────┬────────────────────────────────┘     ║
║                          ▼                                     ║
║  ┌────────────────────────────────────────────────────────┐     ║
║  │  Agent 2: Retrieval                                    │     ║
║  │  (Hybrid Search + LLM Reranking + Fallback Strategy)   │     ║
║  └───────────────────────┬────────────────────────────────┘     ║
║                          ▼                                     ║
║  ┌────────────────────────────────────────────────────────┐     ║
║  │  Agent 3: Response Generation                          │     ║
║  │  (GPT-4o — Grounded Answer + Anti-Hallucination)       │     ║
║  └───────────────────────┬────────────────────────────────┘     ║
╚══════════════════════════╪══════════════════════════════════════╝
                           ▼
                    Reply to User
```

### Routing Logic (RAG-First Policy)

ระบบใช้นโยบาย **RAG-First** คือส่งทุกข้อความเข้า RAG Pipeline เป็นค่าเริ่มต้น ยกเว้น 2 กรณี:

| กรณี | เงื่อนไข | การจัดการ |
|------|----------|----------|
| **Greeting** | ข้อความสั้น + match keyword (สวัสดี, ดีค่ะ, hello) | ตอบทักทายทันที ไม่เข้า RAG |
| **Non-Agriculture** | ข้อความสั้น ≤20 ตัวอักษร + match keyword (ขอบคุณ, 555, โอเค) | ส่งไป General Chat (LLM ถูกจำกัด: temp=0.3, max=150 tokens, ห้ามพูดเกษตร/สินค้า) |
| **Override** | มี agriculture keyword (ข้าว, โรค, ยาฆ่า) ในข้อความ | เข้า RAG Pipeline เสมอ แม้จะสั้น |

**เหตุผลที่ใช้ RAG-First:** ป้องกัน Hallucination — ถ้าส่งข้อความที่ไม่แน่ใจไป General Chat จะเสี่ยง LLM ตอบข้อมูลเกษตรที่ไม่ถูกต้อง

---

## 2. Stage 0: Domain-Specific Pre-Processing

**Technique:** Dictionary-Based Entity Extraction & Synonym Resolution
**ไฟล์:** `app/services/rag/orchestrator.py`
**ใช้ LLM:** ไม่ (ยกเว้น Stage 0.8 Fallback)

### หน้าที่

แปลงคำพูดภาษาเกษตรกร (farmer slang) ให้ตรงกับคำในฐานข้อมูล ก่อนส่งให้ LLM ประมวลผล ลดภาระ LLM และป้องกัน LLM ตีความคำเกษตรผิด

### ขั้นตอนย่อย

| Step | Technique | ทำอะไร | ตัวอย่าง |
|------|-----------|--------|----------|
| 0.1 | Farmer Slang Resolution | แปลงคำแสลง 12 คำ → คำทางการ | "ยาดูด" → สารดูดซึม |
| 0.2 | Symptom-Pathogen Mapping | อาการ → เชื้อโรคที่เป็นไปได้ | เหลือง → [ราน้ำค้าง, ขาดธาตุ] |
| 0.3 | Product Name Extraction | จับคู่ชื่อสินค้าจาก ProductRegistry | "โมเดิน" → "โมเดิน 50" |
| 0.4 | Disease Name Extraction | จับคู่ชื่อโรค 30+ pattern | "ราชมพู" → "ราสีชมพู" |
| 0.5 | Plant Type Extraction | จับคู่ชื่อพืช 26 ชนิด | "ทุเรียน" |
| 0.6 | Pest Name Extraction | จับคู่ชื่อแมลง 18 ชนิด | "เพลี้ย" |
| 0.7 | Weed Synonym Injection | แปลงคำ "หญ้า" → คำในฐานข้อมูล | "หญ้า" → ["วัชพืช", "กำจัดวัชพืช"] |
| 0.8 | LLM Fallback | ใช้ LLM สกัด entity เฉพาะเมื่อ dictionary ไม่เจอ | (GPT-4o) |

### Tag System

ผลลัพธ์จาก Stage 0 จะถูกกำกับด้วย tag เพื่อบอก Agent 1 ว่าเชื่อถือได้แค่ไหน:

- **`[CONSTRAINT]`** — entity ที่ match จาก dictionary → Agent 1 ห้าม override ต้องใช้ตามที่กำหนด
- **`[HINT_LLM]`** — entity จาก LLM fallback → Agent 1 สามารถปรับเปลี่ยนได้

### Thai Variant Generation

ระบบ auto-generate variants สำหรับชื่อโรคที่สะกดต่างกัน เพื่อจับคู่ได้ครอบคลุม:

```
ราสีชมพู   ↔  ราชมพู        (ตัดคำ)
แอนแทรคโนส ↔  แอคแทคโนส    (พยัญชนะใกล้เคียง)
ฟิวซาเรียม ↔  ฟอซาเรียม    (สระใกล้เคียง)
โคราช      ↔  โค-ราซ       (ช ↔ ซ)
```

Technique ที่ใช้: **Consonant Swap** (ค↔ก, ท↔ต, ซ↔ส), **Diacritics Stripping**, **Fuzzy Matching** (SequenceMatcher threshold 0.75)

---

## 3. Agent 1: Query Understanding

**Technique:** LLM-Based Intent Classification + Named Entity Recognition + Query Expansion
**ไฟล์:** `app/services/rag/query_understanding_agent.py` (~415 lines)
**Model:** GPT-4o (temperature = 0.1)

### หน้าที่

วิเคราะห์คำถามของผู้ใช้เพื่อเข้าใจเจตนา (intent) สกัดข้อมูลสำคัญ (entity) และสร้าง query หลายรูปแบบสำหรับค้นหา

### 3.1 Intent Classification

จำแนกเจตนาของผู้ใช้ออกเป็น 10 ประเภท:

| Intent | คำอธิบาย | ตัวอย่างคำถาม |
|--------|----------|--------------|
| PRODUCT_INQUIRY | สอบถามข้อมูลสินค้า | "โมเดิน 50 ใช้ยังไง" |
| PRODUCT_RECOMMENDATION | ขอคำแนะนำสินค้า | "ข้าวเป็นโรค ใช้ยาอะไร" |
| DISEASE_TREATMENT | รักษาโรคพืช | "โรคใบไหม้ข้าว รักษายังไง" |
| PEST_CONTROL | กำจัดแมลง | "มีเพลี้ยในสวน ทำยังไง" |
| WEED_CONTROL | กำจัดวัชพืช | "กำจัดหญ้าในนาข้าว" |
| NUTRIENT_SUPPLEMENT | ปุ๋ย/ธาตุอาหาร | "ทุเรียนใบเหลือง ขาดธาตุอะไร" |
| USAGE_INSTRUCTION | วิธีใช้/อัตราผสม | "ผสมยาอัตราเท่าไหร่" |
| GENERAL_AGRICULTURE | เกษตรทั่วไป | "ดูแลมังคุดยังไง" |
| GREETING | ทักทาย | "สวัสดีค่ะ" |
| UNKNOWN | ไม่ทราบเจตนา | — |

### 3.2 Named Entity Recognition (NER)

สกัด entity จากคำถาม:

| Entity | ตัวอย่าง |
|--------|----------|
| `plant_type` | ข้าว, ทุเรียน, มังคุด |
| `disease_name` | ใบไหม้, ราสีชมพู, แอนแทรคโนส |
| `pest_name` | เพลี้ย, ไรแดง, หนอนชอนใบ |
| `product_name` | โมเดิน 50, แอคทีฟ, ทอปกัน |
| `possible_diseases` | [ราน้ำค้าง, ราแป้ง] |

**จุดสำคัญ — Constrained NER:** entity ที่ Stage 0 สกัดไว้แล้วด้วย `[CONSTRAINT]` tag จะ override ผลจาก LLM เสมอ ป้องกัน LLM เปลี่ยนชื่อโรค/สินค้าที่ dictionary match ได้แล้ว

### 3.3 Query Expansion (Multi-Query Generation)

สร้าง query 3-5 รูปแบบจากคำถามเดิม เพื่อเพิ่มโอกาสค้นเจอ:

```
คำถามเดิม: "ข้าวเป็นโรคใบไหม้"

Expanded Queries:
  1. "โรคใบไหม้ข้าว สารป้องกันกำจัด"
  2. "ราใบไหม้ นาข้าว ยาฆ่าเชื้อรา"
  3. "ป้องกันโรคใบไหม้ ข้าว"
  4. "Fungicide rice blast"
```

ถ้ามี Weed Synonym จาก Stage 0 จะ inject เข้า expanded queries ด้วย เช่น:

```
คำถามเดิม: "กำจัดหญ้าในสวนทุเรียน"
Inject: ["วัชพืช", "สารกำจัดวัชพืช"]
```

### Output ของ Agent 1

```python
QueryAnalysis(
    original_query="ข้าวเป็นโรคใบไหม้",
    intent=IntentType.DISEASE_TREATMENT,
    confidence=0.92,
    entities={
        "plant_type": "ข้าว",
        "disease_name": "ใบไหม้"
    },
    expanded_queries=["โรคใบไหม้ข้าว สารป้องกัน", ...],
    required_sources=["products"]
)
```

---

## 4. Agent 2: Retrieval

**Technique:** Hybrid Search (Dense + Sparse) + LLM-Based Reranking + Multi-Stage Fallback
**ไฟล์:** `app/services/rag/retrieval_agent.py` (~1,150 lines)

### หน้าที่

ค้นหาเอกสาร (สินค้า) ที่เกี่ยวข้องกับคำถามจากฐานข้อมูล จัดอันดับใหม่ด้วย LLM และใช้ fallback หลายระดับเพื่อป้องกันไม่ให้ค้นไม่เจอ

### ขั้นตอนการค้นหา (10+ Stages)

```
Query (จาก Agent 1)
      │
      ▼
┌─ Stage 0: Direct Product Lookup ──────────────────┐
│  ถ้าผู้ใช้ระบุชื่อสินค้าตรง → ค้น ilike             │
│  (similarity = 1.0)                                │
└──────────────────────┬────────────────────────────┘
                       ▼
┌─ Stage 1: Parallel Multi-Query Search ────────────┐
│  ค้นทุก expanded query พร้อมกัน                     │
│  Hybrid Search = Vector (60%) + Keyword (40%)      │
└──────────────────────┬────────────────────────────┘
                       ▼
┌─ Stage 1.1-1.3: Supplementary Search ─────────────┐
│  1.1 Fertilizer Recommendations (ถ้า nutrient)     │
│  1.2 Disease Fallback (target_pest ilike)          │
│  1.3 Symptom Keyword Fallback                      │
└──────────────────────┬────────────────────────────┘
                       ▼
┌─ Stage 1.5: Fallback Keyword Search ──────────────┐
│  ถ้า docs < 3 → ค้น keyword กว้างขึ้น               │
└──────────────────────┬────────────────────────────┘
                       ▼
┌─ Stage 1.8-1.9: Metadata Enrichment ──────────────┐
│  1.8 เพิ่ม strategy_group, selling_point            │
│  1.9 Supplementary Priority (Skyrocket/Expand)     │
└──────────────────────┬────────────────────────────┘
                       ▼
┌─ Stage 1.95: Weed Category Fallback ──────────────┐
│  ถ้า weed intent → ค้นสินค้าหมวด Herbicide ทั้งหมด  │
└──────────────────────┬────────────────────────────┘
                       ▼
┌─ Stage 2: De-duplication ─────────────────────────┐
│  ลบ document ซ้ำ (by title)                        │
└──────────────────────┬────────────────────────────┘
                       ▼
┌─ Stage 3: LLM Reranking ─────────────────────────┐
│  GPT-4o ให้คะแนน 0.0-1.0 ว่า doc ตรงกับ query     │
│  (trigger เมื่อ docs ≥ 3)                          │
└──────────────────────┬────────────────────────────┘
                       ▼
┌─ Stage 3.5-3.8: Score Adjustments ────────────────┐
│  3.5 Strategy Group Boost                          │
│  3.6 Category Penalty (ผิดหมวด)                    │
│  3.7 Crop-Specific Boost (ตรงพืช)                  │
│  3.8 Final Sorting                                 │
└──────────────────────┬────────────────────────────┘
                       ▼
┌─ Stage 4: Threshold Filter ───────────────────────┐
│  rerank_score ≥ 0.50 OR similarity ≥ 0.25          │
└──────────────────────┬────────────────────────────┘
                       ▼
┌─ Stage 4.5: Crop-Specific Rescue ─────────────────┐
│  ถ้า docs เหลือ 0 → กู้ doc ที่ตรงพืชกลับมา        │
└──────────────────────┬────────────────────────────┘
                       ▼
                 Retrieved Documents
```

### 4.1 Hybrid Search (Dense + Sparse Retrieval)

**Technique:** Weighted Score Fusion

ค้นหาแบบผสม 2 วิธีพร้อมกัน แล้วรวมคะแนน:

```
Final Score = (Vector Similarity × 0.6) + (Keyword Match × 0.4)
```

| วิธี | Technique | จุดแข็ง | จุดอ่อน |
|------|-----------|--------|--------|
| **Vector Search** (Dense) | Cosine Similarity บน pgvector | เข้าใจความหมาย (semantic) | คำที่ไม่เคยเห็นใน training → ค้นไม่เจอ |
| **Keyword Search** (Sparse) | PostgreSQL tsvector Full-Text Search | แม่นยำกับชื่อเฉพาะ | ไม่เข้าใจ synonym (หญ้า ≠ วัชพืช) |

การผสมทั้ง 2 วิธี ชดเชยจุดอ่อนของกันและกัน

### 4.2 LLM-Based Reranking

**Technique:** Pointwise Reranking via LLM

หลังจากค้นเจอ documents แล้ว ส่งให้ LLM ให้คะแนนแต่ละ document ว่าตรงกับคำถามแค่ไหน (0.0-1.0):

```
Input:  query + document content
Output: relevance score (0.0 - 1.0)

เหตุผลที่ใช้: Vector similarity ไม่แม่นยำ 100%
             LLM เข้าใจ context ลึกกว่า → จัดอันดับใหม่ได้ดีกว่า
```

### 4.3 Strategy Group Priority

สินค้าแต่ละตัวมี Strategy Group ที่บริษัทกำหนด → ใช้ปรับคะแนนหลัง reranking:

| Strategy Group | Score Boost | ความหมาย |
|---------------|-------------|----------|
| **Skyrocket** | +0.15 | สินค้าหลัก ต้องแนะนำก่อน |
| **Expand** | +0.10 | สินค้าขยายตลาด |
| **Natural** | 0 | สินค้าปกติ |
| **Standard** | -0.05 | สินค้าทั่วไป |

### 4.4 Multi-Stage Fallback Strategy

**Technique:** Cascading Retrieval

ถ้าค้นไม่เจอหรือเจอน้อยเกินไป ระบบจะลอง fallback หลายระดับ:

```
เจอ ≥ 3 docs  →  ดำเนินการปกติ
เจอ < 3 docs  →  Trigger Fallback:
    1. Keyword Search กว้างขึ้น
    2. Disease Fallback (target_pest ilike)
    3. Weed Category Fallback (ค้น Herbicide ทั้งหมวด)
    4. Crop-Specific Rescue (กู้ doc ที่ตรงพืช)
```

### Output ของ Agent 2

```python
RetrievalResult(
    documents=[RetrievedDocument(...)],  # เรียงตาม score
    total_retrieved=12,
    total_after_rerank=5,
    avg_similarity=0.65,
    avg_rerank_score=0.78
)
```

---

## 5. Agent 3: Response Generation

**Technique:** Grounded Response Generation + Multi-Layer Anti-Hallucination
**ไฟล์:** `app/services/rag/response_generator_agent.py` (~690 lines)
**Model:** GPT-4o (temperature = 0.1)

### หน้าที่

สร้างคำตอบจาก retrieved documents ในบุคลิก "น้องลัดดา" พร้อมตรวจสอบความถูกต้องหลายชั้นก่อนส่งให้ผู้ใช้

### 5.1 Document Preparation

ก่อนส่งให้ LLM จะจัดเตรียม documents:

1. **Disease Rescue** — ถ้า top 5 ไม่มี doc ที่ match โรคที่ผู้ใช้ถาม → inject matching doc เข้าไป
2. **Product Sorting** — เรียงตาม Strategy Group: Skyrocket → Expand → Natural → Standard
3. **Context Building** — รวม document content + metadata เป็น context ส่ง LLM

### 5.2 Grounding Override System

ระบบ override สำหรับกรณีที่ confidence ต่ำ แต่จริงๆ มีข้อมูลตรงกัน:

| Override Flag | เงื่อนไข | ผลลัพธ์ |
|--------------|----------|---------|
| `has_disease_match` | ชื่อโรคที่ถาม ตรงกับ target_pest ของ fungicide | ตอบคำถามได้ แม้ confidence ต่ำ |
| `has_pest_match` | ชื่อแมลงที่ถาม ตรงกับ target_pest ของ insecticide | ตอบคำถามได้ |
| `has_weed_match` | เจอ herbicide ใน retrieved results | ตอบคำถามได้ |
| `has_crop_specific_top` | สินค้าตรงพืชอยู่อันดับ 1 | ตอบคำถามได้ |
| `has_product_in_query` | ผู้ใช้ถามชื่อสินค้าตรงๆ | ตอบคำถามได้ |

### 5.3 LLM Answer Synthesis

ส่ง prompt + context ให้ GPT-4o สร้างคำตอบในบุคลิกน้องลัดดา:

**กฎของ Persona:**
- ผู้หญิง 23 ปี พี่สาวอบอุ่น ภาษาง่ายๆ
- ห้ามพูดราคา
- ห้ามแนะนำสินค้านอก ICP Ladda
- ห้ามเมนชั่นการเมือง/ศาสนา
- ข้อมูลต้องจากฐานข้อมูลเท่านั้น
- Emoji: เฉพาะ 😊 🌱 สูงสุด 1-2 ต่อข้อความ

**กฎการคำนวณอัตราใช้:**
- 1 ซีซี = 1 มล. → ตอบเป็น "มล." เสมอ
- อัตรา "ต่อ 200 ลิตร" → หาร 10 = ต่อถังพ่น 20 ลิตร
- ผู้ใช้ถามพื้นที่ → อัตราต่อไร่ × จำนวนไร่ + จำนวนขวด (ปัดขึ้น)

### 5.4 Post-Processing — Anti-Hallucination Multi-Layer Validation

คำตอบจาก LLM ต้องผ่านการตรวจสอบหลายชั้นก่อนส่งให้ผู้ใช้:

```
LLM Generated Answer
        │
        ▼
┌─ Layer 1: Markdown/Emoji Cleanup ─────────────┐
│  ลบ markdown formatting + emoji ที่ไม่อนุญาต    │
└──────────────────────┬────────────────────────┘
                       ▼
┌─ Layer 2: Product Name Validation ────────────┐
│  ชื่อสินค้าใน answer ต้องมีในฐานข้อมูล          │
│  ถ้าไม่มี → ลบออก หรือแทนที่ด้วยข้อความ fallback │
└──────────────────────┬────────────────────────┘
                       ▼
┌─ Layer 3: Number Validation ──────────────────┐
│  ตัวเลข (อัตราผสม, ปริมาณ) ต้องตรงกับ source   │
│  ถ้าไม่ตรง → แก้ไขให้ตรง                        │
└──────────────────────┬────────────────────────┘
                       ▼
┌─ Layer 4: Cross-Product Check ────────────────┐
│  ชื่อสินค้าที่ผู้ใช้ถาม → exempt                 │
│  ชื่อสินค้าที่ LLM สร้างเอง → ตรวจสอบเข้มงวด    │
└──────────────────────┬────────────────────────┘
                       ▼
┌─ Layer 5: Boundary Disease Match ─────────────┐
│  ป้องกัน "ใบไหม้" match ใน "กาบใบไหม้"          │
│  ใช้ regex boundary-aware matching             │
└──────────────────────┬────────────────────────┘
                       ▼
┌─ Layer 6: No-Data Filter ─────────────────────┐
│  ถ้าคำตอบ < 120 ตัวอักษร + มีคำว่า "ไม่มีข้อมูล"│
│  → suppress ทั้งคำตอบ                          │
│  ถ้าคำตอบ ≥ 120 ตัวอักษร                       │
│  → strip เฉพาะ no-data phrase เก็บ content จริง  │
└──────────────────────┬────────────────────────┘
                       ▼
                 Final Answer → User
```

---

## 6. ระบบเสริม

### 6.1 Memory System

**ไฟล์:** `app/services/memory.py`

| ค่า | ตัวเลข | หน้าที่ |
|-----|--------|---------|
| เก็บ | 50 ข้อความ/user | ลบเก่าอัตโนมัติ |
| ส่ง LLM | 10 ข้อความล่าสุด | context สำหรับ follow-up |
| ตัดข้อความ | 2,000 ตัวอักษร | ป้องกัน token เยอะ |

Follow-up flow: ดึง product_name จาก memory metadata → enrich จาก DB ถ้าไม่ครบ → ส่งเข้า RAG pipeline

### 6.2 Caching Strategy (2 ชั้น)

| ชั้น | Technology | TTL | ขนาด |
|------|-----------|-----|------|
| L0 | Redis (Upstash) | 3,600s (1 ชม.) | Unlimited |
| L1 | In-Memory (Python dict) | 3,600s (1 ชม.) | 5,000 entries |

ลดจำนวน LLM calls สำหรับคำถามที่ถามซ้ำบ่อย

### 6.3 ProductRegistry (Singleton)

**ไฟล์:** `app/services/product/registry.py`

- Load ข้อมูลสินค้าจาก DB ตอน startup
- Auto-generate Thai variants: consonant swap (ค↔ก, ท↔ต, ซ↔ส), strip diacritics, remove hyphens
- Matching pipeline: exact → diacritics-stripped → fuzzy (SequenceMatcher 0.75)
- ใช้ตรวจสอบชื่อสินค้าตลอด pipeline

---

## 7. สรุป Techniques ที่ใช้ทั้งหมด

| # | Technique | ใช้ใน | วัตถุประสงค์ |
|---|-----------|-------|-------------|
| 1 | Dictionary-Based Entity Extraction | Stage 0 | สกัด entity โดยไม่ใช้ LLM |
| 2 | Synonym Resolution / Query Normalization | Stage 0 | แปลงคำแสลง → คำทางการ |
| 3 | Thai Variant Generation (Fuzzy Matching) | Stage 0, Registry | รองรับการสะกดหลายแบบ |
| 4 | LLM-Based Intent Classification | Agent 1 | จำแนกเจตนาผู้ใช้ |
| 5 | Hybrid NER (Dictionary + LLM) | Agent 1 | สกัด entity แบบ constrained |
| 6 | Multi-Query Expansion | Agent 1 | เพิ่มโอกาสค้นเจอ |
| 7 | Hybrid Search (Dense + Sparse Retrieval) | Agent 2 | ค้นหาแบบผสม vector + keyword |
| 8 | Weighted Score Fusion | Agent 2 | รวมคะแนน 2 วิธีค้นหา |
| 9 | LLM-Based Pointwise Reranking | Agent 2 | จัดอันดับใหม่ด้วย LLM |
| 10 | Cascading Fallback Retrieval | Agent 2 | ป้องกันค้นไม่เจอ |
| 11 | Strategy-Based Score Boosting | Agent 2 | จัดลำดับตาม business priority |
| 12 | Grounded Response Generation | Agent 3 | สร้างคำตอบจาก documents เท่านั้น |
| 13 | Multi-Layer Anti-Hallucination | Agent 3 | ตรวจสอบความถูกต้องหลายชั้น |
| 14 | Boundary-Aware Pattern Matching | Agent 3 | ป้องกัน substring false positive |
| 15 | Conversation Memory (Topic-Aware) | Memory | follow-up ได้ต่อเนื่อง |
| 16 | Two-Layer Caching (Redis + In-Memory) | Cache | ลดค่า API + latency |

---

## 8. LLM Calls per Message

| # | จุดที่เรียก LLM | Model | Temperature | จุดประสงค์ |
|---|----------------|-------|-------------|-----------|
| 1 | Agent 1: Query Understanding | GPT-4o | 0.1 | Intent + Entity + Query Expansion |
| 2 | Agent 2: LLM Reranking | GPT-4o | 0.1 | จัดอันดับ documents |
| 3 | Agent 3: Response Generation | GPT-4o | 0.1 | สร้างคำตอบ |
| (4) | Stage 0.8: Entity Extraction Fallback | GPT-4o | 0.1 | (เฉพาะเมื่อ dictionary ไม่เจอ) |

**ค่าใช้จ่ายเฉลี่ย:** 3 LLM calls ต่อ 1 ข้อความ (เดิม 4 calls ก่อนปิด Grounding Agent)

---

## 9. ข้อมูลอ้างอิง (Keywords สำหรับค้นหา Paper)

- Retrieval-Augmented Generation (RAG) — Lewis et al., 2020
- Agentic RAG / Multi-Agent RAG Systems
- Hybrid Search / Dense-Sparse Retrieval Fusion
- Query Expansion / Multi-Query Retrieval
- LLM Reranking / Cross-Encoder Reranking
- Hallucination Detection & Mitigation in LLMs
- Domain-Specific NLP / Agricultural NLP
- Grounded Text Generation
- pgvector — Open-Source Vector Similarity Search for PostgreSQL
