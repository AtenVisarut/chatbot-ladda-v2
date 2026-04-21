"""
Query Understanding Agent

Responsibilities:
- Semantic intent detection using LLM (not keyword matching)
- Entity extraction: product_name, plant_type, disease_name, pest_name
- Query expansion for multi-query retrieval
- Determine required sources: products, diseases
"""

import logging
import json
import re
from typing import List, Dict

from app.services.rag import IntentType, QueryAnalysis
from app.config import LLM_MODEL_QUERY_UNDERSTANDING, LLM_TEMP_QUERY_UNDERSTANDING, LLM_TOKENS_QUERY_UNDERSTANDING

logger = logging.getLogger(__name__)

from app.services.product.registry import ProductRegistry


class QueryUnderstandingAgent:
    """
    Agent 1: Query Understanding
    Uses LLM to semantically understand user queries
    """

    def __init__(self, openai_client=None):
        self.openai_client = openai_client

    async def analyze(self, query: str, context: str = "", hints: dict = None) -> QueryAnalysis:
        """
        Analyze user query to extract intent, entities, and generate expanded queries

        Args:
            query: Current user message
            context: Conversation history for understanding follow-up messages
            hints: Pre-detected hints dict with keys: product_name, problem_type

        Returns:
            QueryAnalysis with intent, entities, expanded_queries, required_sources
        """
        try:
            logger.info(f"QueryUnderstandingAgent: Analyzing '{query[:50]}...'")

            # Build hints from external detection functions if not provided
            if hints is None:
                hints = {}

            if not self.openai_client:
                logger.warning("OpenAI client not available, using fallback analysis")
                return self._fallback_analysis(query)

            # Use LLM for semantic understanding with hints
            result = await self._llm_analyze(query, context=context, hints=hints)
            logger.info(f"QueryUnderstandingAgent: intent={result.intent}, confidence={result.confidence:.2f}")
            return result

        except Exception as e:
            logger.error(f"QueryUnderstandingAgent error: {e}", exc_info=True)
            return self._fallback_analysis(query)

    async def _llm_analyze(self, query: str, context: str = "", hints: dict = None) -> QueryAnalysis:
        """Use LLM for semantic query analysis with conversation context and hints"""

        if hints is None:
            hints = {}

        context_section = ""
        if context:
            context_section = f"""บริบทการสนทนาก่อนหน้า:
{context[:4000]}

สำคัญ: ถ้าคำถามเป็นการถามต่อเนื่อง (เช่น "ใช้กับพืชนี้ได้ไหม" "ตัวไหนเหมาะกับ..." "ใช้ช่วงไหน") ต้องดูว่าก่อนหน้านี้พูดถึงสินค้าตัวไหน แล้วใส่ชื่อสินค้านั้นใน entities.product_name เสมอ

"""

        # Build hint/constraint sections
        # [CONSTRAINT] = dictionary-matched, LLM must NOT override
        # [HINT] = softer suggestion, LLM may adjust
        hint_section = ""
        if hints.get('product_names') and len(hints['product_names']) > 1:
            names_str = ", ".join(f'"{n}"' for n in hints['product_names'])
            hint_section += f"\n[CONSTRAINT] ระบบตรวจพบสินค้าหลายตัว: {names_str} — ใส่ตัวแรกใน entities.product_name"
        elif hints.get('product_name'):
            hint_section += f"\n[CONSTRAINT] ระบบตรวจพบชื่อสินค้า: \"{hints['product_name']}\" — ห้ามเปลี่ยนชื่อ ต้องใช้ชื่อนี้ใน entities.product_name เท่านั้น"
        if hints.get('disease_name'):
            hint_section += f"\n[CONSTRAINT] ระบบตรวจพบชื่อโรค: \"{hints['disease_name']}\" — ห้ามเปลี่ยนชื่อโรค ต้องใช้ชื่อนี้ใน entities.disease_name เท่านั้น (ห้ามแปลหรือเปลี่ยนเป็นชื่ออื่น)"
        if hints.get('plant_type'):
            hint_section += f"\n[CONSTRAINT] ระบบตรวจพบชื่อพืช: \"{hints['plant_type']}\" — ใช้ชื่อนี้ใน entities.plant_type"
        if hints.get('pest_name'):
            hint_section += f"\n[CONSTRAINT] ระบบตรวจพบชื่อแมลง/ศัตรูพืช: \"{hints['pest_name']}\" — ห้ามเปลี่ยนชื่อ ต้องใช้ชื่อนี้ใน entities.pest_name เท่านั้น"
        if hints.get('problem_type') and hints['problem_type'] != 'unknown':
            problem_map = {'disease': 'โรคพืช', 'insect': 'แมลง', 'nutrient': 'ธาตุอาหาร/บำรุง', 'weed': 'วัชพืช'}
            if hints['problem_type'] == 'nutrient':
                # Nutrient must be CONSTRAINT — LLM often misclassifies "บำรุง" as product_recommendation
                hint_section += f"\n[CONSTRAINT] ประเภทปัญหา: ธาตุอาหาร/บำรุง — intent ต้องเป็น nutrient_supplement (ห้ามใช้ product_recommendation)"
            else:
                hint_section += f"\n[HINT] ระบบตรวจพบประเภทปัญหา: {problem_map.get(hints['problem_type'], hints['problem_type'])}"
        if hints.get('resolved_slang'):
            hint_section += f"\n[HINT] ภาษาชาวบ้าน: {hints['resolved_slang']}"
        if hints.get('possible_diseases'):
            diseases_str = ", ".join(hints['possible_diseases'])
            hint_section += f"\n[HINT] อาการในคำถามอาจเกิดจากโรค: {diseases_str} — ให้ใช้โรคเหล่านี้ใน expanded_queries เพื่อค้นหาสินค้าที่เหมาะสม"

        # Reduce product list based on problem_type hint (91 → ~20 names)
        _registry = ProductRegistry.get_instance()
        _problem_type = hints.get('problem_type', '')
        _PROBLEM_TO_CATEGORIES = {
            'disease': ['Fungicide'],
            'insect': ['Insecticide'],
            'weed': ['Herbicide'],
            'nutrient': ['Biostimulants', 'PGR', 'Fertilizer'],
        }
        _hint_categories = _PROBLEM_TO_CATEGORIES.get(_problem_type, [])
        if _hint_categories:
            _filtered = _registry.get_names_by_categories(_hint_categories)
            products_str = ", ".join(_filtered) if _filtered else ", ".join(_registry.get_canonical_list())
        else:
            products_str = ", ".join(_registry.get_canonical_list())

        prompt = f"""{context_section}วิเคราะห์คำถามของผู้ใช้และตอบเป็น JSON
ถ้าคำถามเป็นข้อความสั้นหรือเป็นการถามต่อ (เช่น 'ใช้ช่วงไหน' 'ผสมกี่ลิตร' 'ใช้ยังไง' 'ใช้เท่าไหร่' 'ใช้กี่ไร่'):
- ดูบริบทก่อนหน้าเพื่อหาสินค้าที่น้องลัดดาแนะนำล่าสุด
- ใส่ชื่อสินค้านั้นใน entities.product_name
- intent ควรเป็น usage_instruction
{hint_section}

รายชื่อสินค้า ICP ในระบบ: [{products_str}]
(ถ้าชื่อในคำถามคล้ายชื่อสินค้าใดๆ ให้ถือว่าเป็น product_inquiry)

คำถาม: "{query}"

ตอบเป็น JSON format เท่านั้น (ไม่มี markdown):
{{
    "intent": "<intent_type>",
    "confidence": <0.0-1.0>,
    "entities": {{
        "product_name": "<ชื่อสินค้าถ้ามี หรือ null>",
        "plant_type": "<ชื่อพืชถ้ามี หรือ null>",
        "disease_name": "<ชื่อโรคถ้ามี หรือ null>",
        "pest_name": "<ชื่อแมลง/ศัตรูพืชถ้ามี หรือ null>",
        "weed_type": "<ประเภทวัชพืชถ้ามี หรือ null>",
        "growth_stage": "<ระยะการเจริญเติบโตถ้ามี หรือ null>"
    }},
    "expanded_queries": ["<คำค้นหาภาษาไทย1>", "<คำค้นหาภาษาไทย2>", "<คำค้นหาภาษาไทย3>"],
    "required_sources": ["<source1>", "<source2>"]
}}

intent_type ที่เป็นไปได้:
- product_inquiry: ถามเกี่ยวกับสินค้าเฉพาะ (เช่น "โมเดิน ใช้ยังไง", "แกนเตอร์ คืออะไร")
- product_recommendation: ขอแนะนำสินค้า (เช่น "แนะนำยากำจัดแมลง")
- disease_treatment: การรักษาโรคพืช (เช่น "ราน้ำค้าง รักษายังไง", "เป็นรากเน่า")
- pest_control: การกำจัดแมลง (เช่น "กำจัดเพลี้ยในทุเรียน")
- weed_control: การกำจัดวัชพืช (เช่น "หญ้าในนาข้าว")
- nutrient_supplement: การเสริมธาตุอาหาร รวมถึง PGR/ฮอร์โมนพืช (เช่น "ดอกร่วง ติดดอก", "ยับยั้งใบอ่อน", "เร่งดอก", "ชะลอยอด")
- usage_instruction: วิธีใช้/อัตราผสม (เช่น "อัตราการใช้", "ผสมกี่ซีซี")
- general_agriculture: คำถามเกษตรทั่วไป
- greeting: ทักทาย (เช่น "สวัสดี", "ดีจ้า")
- unknown: ไม่เกี่ยวกับเกษตร

หมวดหมู่สินค้า ICP (ใช้ประกอบการวิเคราะห์ intent):
- Fungicide: ป้องกัน/รักษาโรคพืช (ราน้ำค้าง, แอนแทรคโนส, รากเน่า, ราสนิม, ใบจุด, ใบไหม้)
- Insecticide: กำจัดแมลงศัตรูพืช (เพลี้ย, หนอน, ไร, ทริปส์, แมลงค่อมทอง, ด้วง, บั่ว)
- Herbicide: กำจัดวัชพืช (หญ้า, วัชพืช, ไมยราบ)
- PGR (ฮอร์โมนพืช): ควบคุมการเจริญเติบโต (ยับยั้งใบอ่อน, ชะลอยอด, กดใบอ่อน, แต่งทรงพุ่ม, เร่งดอก, ชะลอการแตกใบ, ราดสาร) → intent=nutrient_supplement
- Biostimulants: สารกระตุ้น/บำรุงพืช (ฟื้นฟูต้น, เสริมธาตุ, กระตุ้นราก, เพิ่มความหวาน) → intent=nutrient_supplement
- Fertilizer: ปุ๋ย NPK (เร่งผล, ขยายผล, บำรุงดิน, สะสมอาหาร) → intent=nutrient_supplement

required_sources:
- ใช้ ["products"] เสมอ (ข้อมูลสินค้าเป็นแหล่งหลักเพียงแหล่งเดียว)

กฎสำคัญ:
- [CONSTRAINT] คือข้อมูลที่ระบบตรวจจับได้จากพจนานุกรม — ห้ามเปลี่ยนแปลง ห้ามแปล ห้ามเปลี่ยนชื่อ ต้องใส่ค่าตามที่ระบุเท่านั้น
- [HINT] คือคำแนะนำ — สามารถปรับได้ตามบริบท
- ถ้าคำถามมีคำว่า "ใช้สาร", "ใช้ยา", "ใช้อะไร", "รักษา", "แก้ยังไง", "ฉีดอะไร", "พ่นอะไร" → ต้องเป็น product-related intent (ห้ามเป็น unknown)
- ถ้าคำถามพูดถึงอาการพืช/สภาพพืช (เช่น ใบเพสลาด, ใบไหม้, ใบเหลือง, ดอกร่วง, ผลร่วง, รากเน่า) → จัดเป็น disease_treatment หรือ nutrient_supplement
- ถ้าคำถามพูดถึงการควบคุมการเจริญเติบโต (ยับยั้งใบอ่อน, ชะลอยอด, กดใบอ่อน, แต่งทรงพุ่ม, ราดสาร, ชะลอการแตกใบ, เร่งดอก, เร่งผล) → จัดเป็น nutrient_supplement เสมอ (ไม่ใช่ disease_treatment หรือ pest_control)
- ห้ามสร้าง query ภาษาอังกฤษ (ฐานข้อมูลเป็นภาษาไทย)
- สร้างคำค้นหาภาษาไทยเท่านั้น
- รวมชื่อสินค้า + พืช + ปัญหา ในรูปแบบต่างๆ

ตัวอย่าง:
1. "คาริส ใช้ยังไง" → intent=product_inquiry, product_name="คาริสมา", expanded_queries=["คาริสมา วิธีใช้", "คาริสมา อัตราผสม", "คาริสมา"]
2. "เป็นรากเน่า ใช้ยาไรครับ" → intent=disease_treatment, disease_name="รากเน่า", expanded_queries=["รากเน่า ยาป้องกัน", "โรครากเน่า สารป้องกัน", "รากเน่า"]
3. "สวัสดีครับ" → intent=greeting, confidence=0.95
4. "ทูโฟโฟส ใช้ยังไง" → intent=product_inquiry, product_name="ทูโฟฟอส", expanded_queries=["ทูโฟฟอส วิธีใช้", "ทูโฟฟอส อัตรา", "ทูโฟฟอส"]
5. "แมลงในข้าว กำจัดยังไง" → intent=pest_control, plant_type="ข้าว", expanded_queries=["กำจัดแมลง ข้าว", "ยาฆ่าแมลง ข้าว", "แมลงศัตรูข้าว"]
6. "ข้าวเป็นราน้ำค้าง" → intent=disease_treatment, plant_type="ข้าว", disease_name="ราน้ำค้าง", expanded_queries=["ราน้ำค้าง ข้าว", "ป้องกันราน้ำค้าง", "ราน้ำค้าง"]
7. "โมเดิน 50 อัตราผสมเท่าไหร่" → intent=usage_instruction, product_name="โมเดิน", expanded_queries=["โมเดิน อัตราผสม", "โมเดิน 50 วิธีใช้", "โมเดิน"]
8. "ใบเพสลาด ใช้สารอะไรรักษา" → intent=nutrient_supplement, plant_type="ทุเรียน", expanded_queries=["ใบเพสลาด ทุเรียน", "สารชะลอการเจริญเติบโต ทุเรียน", "เพสลาด"]
9. "ทุเรียนใบเหลือง ใช้ยาอะไร" → intent=disease_treatment, plant_type="ทุเรียน", expanded_queries=["ทุเรียน ใบเหลือง", "โรคทุเรียน", "ยารักษาทุเรียน"]
10. "ยับยั้งใบอ่อนมะม่วง ใช้อะไร" → intent=nutrient_supplement, plant_type="มะม่วง", expanded_queries=["ยับยั้งใบอ่อน มะม่วง", "สารชะลอการแตกใบ มะม่วง", "ฮอร์โมนพืช มะม่วง"]
11. "ราดสารทุเรียน" → intent=nutrient_supplement, plant_type="ทุเรียน", expanded_queries=["ราดสาร ทุเรียน", "สารชะลอการเจริญเติบโต ทุเรียน", "พาโคลบิวทราซอล ทุเรียน"]
12. "มีปุ๋ยแนะนำไหม" → intent=nutrient_supplement, expanded_queries=["ปุ๋ยแนะนำ", "ปุ๋ยบำรุง", "สารบำรุงพืช"]
"""

        response = await self.openai_client.chat.completions.create(
            model=LLM_MODEL_QUERY_UNDERSTANDING,
            messages=[
                {
                    "role": "system",
                    "content": "คุณเป็นผู้เชี่ยวชาญด้านการวิเคราะห์คำถามการเกษตร ตอบเป็น JSON เท่านั้น ไม่มี markdown"
                },
                {"role": "user", "content": prompt}
            ],
            temperature=LLM_TEMP_QUERY_UNDERSTANDING,
            max_completion_tokens=LLM_TOKENS_QUERY_UNDERSTANDING
        )

        response_text = response.choices[0].message.content.strip()

        # Parse JSON response
        try:
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = re.sub(r'^```(?:json)?\n?', '', response_text)
                response_text = re.sub(r'\n?```$', '', response_text)

            data = json.loads(response_text)

            # Map intent string to IntentType enum
            intent_map = {
                "product_inquiry": IntentType.PRODUCT_INQUIRY,
                "product_recommendation": IntentType.PRODUCT_RECOMMENDATION,
                "disease_treatment": IntentType.DISEASE_TREATMENT,
                "pest_control": IntentType.PEST_CONTROL,
                "weed_control": IntentType.WEED_CONTROL,
                "nutrient_supplement": IntentType.NUTRIENT_SUPPLEMENT,
                "usage_instruction": IntentType.USAGE_INSTRUCTION,
                "general_agriculture": IntentType.GENERAL_AGRICULTURE,
                "greeting": IntentType.GREETING,
                "unknown": IntentType.UNKNOWN,
            }

            intent = intent_map.get(data.get("intent", "unknown"), IntentType.UNKNOWN)

            # Clean entities (remove null values)
            entities = {k: v for k, v in data.get("entities", {}).items() if v is not None}

            # Defense in depth: reject non-Thai / non-DB disease_name values.
            # A smarter Agent 1 model (gpt-4.1-mini) may try to "improve"
            # ราชมพู → "Corticium salmonicolor" or translate "รากเน่า" to
            # "Phytophthora root rot"; downstream retrieval keys on Thai
            # canonicals in products3.pest columns and would miss.
            _llm_disease = entities.get('disease_name')
            if _llm_disease:
                from app.services.disease.constants import DISEASE_PATTERNS
                _is_thai = any('฀' <= c <= '๿' for c in _llm_disease)
                _db_match = any(
                    p in _llm_disease or _llm_disease in p for p in DISEASE_PATTERNS
                )
                if not _is_thai or not _db_match:
                    logger.warning(
                        f"[DIAG] llm_disease_rejected='{_llm_disease}' "
                        f"reason={'non_thai' if not _is_thai else 'no_db_match'}"
                    )
                    entities.pop('disease_name', None)

            # Post-LLM override: pre-extracted entities take priority
            # This prevents LLM from "translating" ราชมพู→ฟอซาเรียม etc.
            if hints.get('disease_name') and entities.get('disease_name') != hints['disease_name']:
                logger.info(f"  - Override disease: LLM='{entities.get('disease_name')}' → pre-extracted='{hints['disease_name']}'")
                entities['disease_name'] = hints['disease_name']
            if hints.get('plant_type') and not entities.get('plant_type'):
                entities['plant_type'] = hints['plant_type']
            if hints.get('pest_name') and entities.get('pest_name') != hints['pest_name']:
                logger.info(f"  - Override pest: LLM='{entities.get('pest_name')}' → pre-extracted='{hints['pest_name']}'")
                entities['pest_name'] = hints['pest_name']
            if hints.get('product_name') and entities.get('product_name') != hints['product_name']:
                # If LLM says None + intent is recommendation → respect LLM's None
                # (user is asking for NEW recommendations, not follow-up about existing product)
                _rec_intents_for_override = {
                    IntentType.PRODUCT_RECOMMENDATION, IntentType.DISEASE_TREATMENT,
                    IntentType.PEST_CONTROL, IntentType.NUTRIENT_SUPPLEMENT,
                    IntentType.GENERAL_AGRICULTURE,
                }
                llm_said_none = entities.get('product_name') is None
                hint_from_query = hints.get('_product_from_query', False)
                if llm_said_none and intent in _rec_intents_for_override:
                    logger.info(f"  - Skip product override: LLM correctly found no product (intent={intent}, hint='{hints['product_name']}')")
                elif not llm_said_none and not hint_from_query:
                    # LLM found a specific product, but hint is from context scan (less reliable)
                    # Trust LLM — it has full conversation context
                    logger.info(f"  - Keep LLM product: '{entities.get('product_name')}' (context hint='{hints['product_name']}')")
                else:
                    logger.info(f"  - Override product: LLM='{entities.get('product_name')}' → pre-extracted='{hints['product_name']}'")
                    entities['product_name'] = hints['product_name']

            # Propagate flags for downstream agents (retrieval, response)
            if '_product_from_query' in hints:
                entities['_product_from_query'] = hints['_product_from_query']
            if hints.get('product_names'):
                entities['product_names'] = hints['product_names']
            # asked_product: previous product that user is asking applicability for
            # e.g. "ถ้าเพลี้ยจั๊กจั่นในทุเรียนล่ะ ใช้ได้มั้ย" after asking about เกรก 5
            # → asked_product="เกรก 5 เอสซี"; response must confirm or deny applicability
            if hints.get('asked_product'):
                entities['asked_product'] = hints['asked_product']

            # Diagnostic-intent flags (§4) — propagated to Agent 3 so the
            # response template can switch to hedge language when the bot
            # is choosing between multiple disease candidates.
            if hints.get('diagnostic_intent'):
                entities['diagnostic_intent'] = True
            if hints.get('_prior_source'):
                entities['_prior_source'] = hints['_prior_source']
            if hints.get('possible_diseases'):
                entities['possible_diseases'] = hints['possible_diseases']

            # Remove LLM-hallucinated product_name for recommendation/treatment queries
            # e.g. "โรครากเน่าโคนเน่า แก้ยังไง" → LLM adds product_name=โค-ราซ (wrong!)
            _recommendation_intents = {
                IntentType.DISEASE_TREATMENT, IntentType.PEST_CONTROL,
                IntentType.PRODUCT_RECOMMENDATION, IntentType.WEED_CONTROL,
                IntentType.NUTRIENT_SUPPLEMENT,
            }
            if (intent in _recommendation_intents
                    and entities.get('product_name')
                    and not hints.get('product_name')
                    and not hints.get('product_names')):
                logger.info(f"  - Remove hallucinated product: LLM added '{entities['product_name']}' but user didn't mention any product")
                del entities['product_name']

            # Get expanded queries
            expanded_queries = data.get("expanded_queries", [query])
            if not expanded_queries:
                expanded_queries = [query]

            # Inject disease variants into expanded queries for better retrieval
            if hints.get('disease_variants'):
                for variant in hints['disease_variants']:
                    if variant not in expanded_queries and variant != query:
                        expanded_queries.append(variant)

            # Inject extra search terms from farmer slang resolution
            if hints.get('extra_search_terms'):
                plant_type = entities.get('plant_type', '')
                for term in hints['extra_search_terms']:
                    search_q = f"{term} {plant_type}".strip() if plant_type else term
                    if search_q not in expanded_queries:
                        expanded_queries.append(search_q)

            # Inject possible diseases from symptom mapping
            if hints.get('possible_diseases'):
                plant_type = entities.get('plant_type', '')
                for disease in hints['possible_diseases']:
                    search_q = f"{disease} {plant_type}".strip() if plant_type else disease
                    if search_q not in expanded_queries:
                        expanded_queries.append(search_q)

            # Inject weed synonyms for better herbicide retrieval
            if hints.get('weed_synonyms'):
                plant_type = entities.get('plant_type', '')
                for synonym in hints['weed_synonyms']:
                    search_q = f"{synonym} {plant_type}".strip() if plant_type else synonym
                    if search_q not in expanded_queries:
                        expanded_queries.append(search_q)

            # Inject nutrient synonyms for better PGR/Biostimulant retrieval
            if hints.get('nutrient_synonyms'):
                plant_type = entities.get('plant_type', '')
                for synonym in hints['nutrient_synonyms']:
                    search_q = f"{synonym} {plant_type}".strip() if plant_type else synonym
                    if search_q not in expanded_queries:
                        expanded_queries.append(search_q)

            # Force products-only source (products table is the sole data source)
            required_sources = ["products"]

            return QueryAnalysis(
                original_query=query,
                intent=intent,
                confidence=float(data.get("confidence", 0.5)),
                entities=entities,
                expanded_queries=expanded_queries,
                required_sources=required_sources
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            return self._fallback_analysis(query)

    def _fallback_analysis(self, query: str) -> QueryAnalysis:
        """Fallback to keyword-based analysis when LLM is not available"""
        query_lower = query.lower()

        # Intent detection using keywords
        intent = IntentType.UNKNOWN
        confidence = 0.5
        entities = {}

        # Product inquiry patterns (full ICP product list)
        product_keywords = ProductRegistry.get_instance().get_canonical_list()
        for product in product_keywords:
            if product in query_lower:
                intent = IntentType.PRODUCT_INQUIRY
                entities["product_name"] = product
                confidence = 0.8
                break

        # Disease treatment patterns
        disease_keywords = ["โรค", "ราน้ำค้าง", "ราแป้ง", "ใบไหม้", "เชื้อรา", "รักษา"]
        if any(kw in query_lower for kw in disease_keywords):
            if intent == IntentType.UNKNOWN:
                intent = IntentType.DISEASE_TREATMENT
                confidence = 0.7

        # Pest control patterns
        pest_keywords = ["แมลง", "เพลี้ย", "หนอน", "ด้วง", "กำจัด", "ฆ่า"]
        if any(kw in query_lower for kw in pest_keywords):
            if intent == IntentType.UNKNOWN:
                intent = IntentType.PEST_CONTROL
                confidence = 0.7

        # Weed control patterns
        weed_keywords = ["หญ้า", "วัชพืช", "ยาฆ่าหญ้า"]
        if any(kw in query_lower for kw in weed_keywords):
            if intent == IntentType.UNKNOWN:
                intent = IntentType.WEED_CONTROL
                confidence = 0.7

        # Nutrient supplement patterns
        nutrient_keywords = ["บำรุง", "ธาตุอาหาร", "ดอกร่วง", "ติดดอก", "ติดผล"]
        if any(kw in query_lower for kw in nutrient_keywords):
            if intent == IntentType.UNKNOWN:
                intent = IntentType.NUTRIENT_SUPPLEMENT
                confidence = 0.6

        # Usage instruction patterns
        usage_keywords = ["วิธีใช้", "อัตรา", "ผสม", "ใช้ยังไง"]
        if any(kw in query_lower for kw in usage_keywords):
            if intent == IntentType.UNKNOWN:
                intent = IntentType.USAGE_INSTRUCTION
                confidence = 0.7

        # Greeting patterns
        greeting_keywords = ["สวัสดี", "ดีจ้า", "หวัดดี", "hello"]
        if any(kw in query_lower for kw in greeting_keywords):
            intent = IntentType.GREETING
            confidence = 0.9

        # Extract plant type
        plants = sorted(["ข้าว", "ทุเรียน", "มะม่วง", "ส้ม", "พริก", "ข้าวโพด", "อ้อย", "ลำไย", "ข้าวฟ่าง"], key=len, reverse=True)
        for plant in plants:
            if plant in query_lower:
                entities["plant_type"] = plant
                break

        return QueryAnalysis(
            original_query=query,
            intent=intent,
            confidence=confidence,
            entities=entities,
            expanded_queries=[query],
            required_sources=self._determine_sources(intent)
        )

    def _determine_sources(self, intent: IntentType) -> List[str]:
        """Determine which data sources to query based on intent — products only"""
        if intent == IntentType.GREETING:
            return []
        return ["products"]
