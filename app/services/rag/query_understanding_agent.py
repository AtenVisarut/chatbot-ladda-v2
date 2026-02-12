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
from app.config import LLM_MODEL_QUERY_UNDERSTANDING

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
        # [HINT_LLM] = from LLM fallback extraction, Agent 1 can adjust freely
        hint_section = ""
        llm_fallback_keys = hints.get('_llm_fallback_keys', [])
        if hints.get('product_name'):
            if 'product_name' in llm_fallback_keys:
                hint_section += f"\n[HINT_LLM] ระบบ AI ตรวจพบชื่อสินค้า: \"{hints['product_name']}\" — สามารถปรับได้ตามบริบท"
            else:
                hint_section += f"\n[CONSTRAINT] ระบบตรวจพบชื่อสินค้า: \"{hints['product_name']}\" — ห้ามเปลี่ยนชื่อ ต้องใช้ชื่อนี้ใน entities.product_name เท่านั้น"
        if hints.get('disease_name'):
            if 'disease_name' in llm_fallback_keys:
                hint_section += f"\n[HINT_LLM] ระบบ AI ตรวจพบชื่อโรค: \"{hints['disease_name']}\" — สามารถปรับได้ตามบริบท"
            else:
                hint_section += f"\n[CONSTRAINT] ระบบตรวจพบชื่อโรค: \"{hints['disease_name']}\" — ห้ามเปลี่ยนชื่อโรค ต้องใช้ชื่อนี้ใน entities.disease_name เท่านั้น (ห้ามแปลหรือเปลี่ยนเป็นชื่ออื่น)"
        if hints.get('plant_type'):
            if 'plant_type' in llm_fallback_keys:
                hint_section += f"\n[HINT_LLM] ระบบ AI ตรวจพบชื่อพืช: \"{hints['plant_type']}\" — สามารถปรับได้ตามบริบท"
            else:
                hint_section += f"\n[CONSTRAINT] ระบบตรวจพบชื่อพืช: \"{hints['plant_type']}\" — ใช้ชื่อนี้ใน entities.plant_type"
        if hints.get('pest_name'):
            if 'pest_name' in llm_fallback_keys:
                hint_section += f"\n[HINT_LLM] ระบบ AI ตรวจพบชื่อแมลง/ศัตรูพืช: \"{hints['pest_name']}\" — สามารถปรับได้ตามบริบท"
            else:
                hint_section += f"\n[CONSTRAINT] ระบบตรวจพบชื่อแมลง/ศัตรูพืช: \"{hints['pest_name']}\" — ห้ามเปลี่ยนชื่อ ต้องใช้ชื่อนี้ใน entities.pest_name เท่านั้น"
        if hints.get('problem_type') and hints['problem_type'] != 'unknown':
            problem_map = {'disease': 'โรคพืช', 'insect': 'แมลง', 'nutrient': 'ธาตุอาหาร', 'weed': 'วัชพืช'}
            hint_section += f"\n[HINT] ระบบตรวจพบประเภทปัญหา: {problem_map.get(hints['problem_type'], hints['problem_type'])}"
        if hints.get('resolved_slang'):
            hint_section += f"\n[HINT] ภาษาชาวบ้าน: {hints['resolved_slang']}"
        if hints.get('possible_diseases'):
            diseases_str = ", ".join(hints['possible_diseases'])
            hint_section += f"\n[HINT] อาการในคำถามอาจเกิดจากโรค: {diseases_str} — ให้ใช้โรคเหล่านี้ใน expanded_queries เพื่อค้นหาสินค้าที่เหมาะสม"

        products_str = ", ".join(ProductRegistry.get_instance().get_canonical_list())

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
- nutrient_supplement: การเสริมธาตุอาหาร (เช่น "ดอกร่วง ติดดอก")
- usage_instruction: วิธีใช้/อัตราผสม (เช่น "อัตราการใช้", "ผสมกี่ซีซี")
- general_agriculture: คำถามเกษตรทั่วไป
- greeting: ทักทาย (เช่น "สวัสดี", "ดีจ้า")
- unknown: ไม่เกี่ยวกับเกษตร

required_sources:
- ใช้ ["products"] เสมอ (ข้อมูลสินค้าเป็นแหล่งหลักเพียงแหล่งเดียว)

กฎสำคัญ:
- [CONSTRAINT] คือข้อมูลที่ระบบตรวจจับได้จากพจนานุกรม — ห้ามเปลี่ยนแปลง ห้ามแปล ห้ามเปลี่ยนชื่อ ต้องใส่ค่าตามที่ระบุเท่านั้น
- [HINT] คือคำแนะนำ — สามารถปรับได้ตามบริบท
- [HINT_LLM] คือ entity ที่ AI อีกตัวตรวจพบ — ใช้เป็นแนวทางเริ่มต้นแต่สามารถปรับเปลี่ยนได้ตามที่คุณวิเคราะห์
- ถ้าคำถามมีคำว่า "ใช้สาร", "ใช้ยา", "ใช้อะไร", "รักษา", "แก้ยังไง", "ฉีดอะไร", "พ่นอะไร" → ต้องเป็น product-related intent (ห้ามเป็น unknown)
- ถ้าคำถามพูดถึงอาการพืช/สภาพพืช (เช่น ใบเพสลาด, ใบไหม้, ใบเหลือง, ดอกร่วง, ผลร่วง, รากเน่า) → จัดเป็น disease_treatment หรือ nutrient_supplement
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
            temperature=0.1,
            max_completion_tokens=500
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

            # Post-LLM override: pre-extracted entities take priority
            # This prevents LLM from "translating" ราชมพู→ฟอซาเรียม etc.
            # SKIP override for [HINT_LLM] entities — let Agent 1 adjust freely
            llm_fallback_keys = hints.get('_llm_fallback_keys', [])
            if hints.get('disease_name') and entities.get('disease_name') != hints['disease_name']:
                if 'disease_name' not in llm_fallback_keys:
                    logger.info(f"  - Override disease: LLM='{entities.get('disease_name')}' → pre-extracted='{hints['disease_name']}'")
                    entities['disease_name'] = hints['disease_name']
                else:
                    logger.info(f"  - LLM fallback disease: keeping Agent 1 value='{entities.get('disease_name')}' (hint was '{hints['disease_name']}')")
            if hints.get('plant_type') and not entities.get('plant_type'):
                entities['plant_type'] = hints['plant_type']
            if hints.get('pest_name') and entities.get('pest_name') != hints['pest_name']:
                if 'pest_name' not in llm_fallback_keys:
                    logger.info(f"  - Override pest: LLM='{entities.get('pest_name')}' → pre-extracted='{hints['pest_name']}'")
                    entities['pest_name'] = hints['pest_name']
                else:
                    logger.info(f"  - LLM fallback pest: keeping Agent 1 value='{entities.get('pest_name')}' (hint was '{hints['pest_name']}')")
            if hints.get('product_name') and entities.get('product_name') != hints['product_name']:
                if 'product_name' not in llm_fallback_keys:
                    # If LLM says None + intent is recommendation → respect LLM's None
                    # (user is asking for NEW recommendations, not follow-up about existing product)
                    _rec_intents_for_override = {
                        IntentType.PRODUCT_RECOMMENDATION, IntentType.DISEASE_TREATMENT,
                        IntentType.PEST_CONTROL, IntentType.NUTRIENT_SUPPLEMENT,
                    }
                    llm_said_none = entities.get('product_name') is None
                    if llm_said_none and intent in _rec_intents_for_override:
                        logger.info(f"  - Skip product override: LLM correctly found no product (intent={intent}, hint='{hints['product_name']}')")
                    else:
                        logger.info(f"  - Override product: LLM='{entities.get('product_name')}' → pre-extracted='{hints['product_name']}'")
                        entities['product_name'] = hints['product_name']
                else:
                    logger.info(f"  - LLM fallback product: keeping Agent 1 value='{entities.get('product_name')}' (hint was '{hints['product_name']}')")

            # Remove LLM-hallucinated product_name for recommendation/treatment queries
            # e.g. "โรครากเน่าโคนเน่า แก้ยังไง" → LLM adds product_name=โค-ราซ (wrong!)
            _recommendation_intents = {
                IntentType.DISEASE_TREATMENT, IntentType.PEST_CONTROL,
                IntentType.PRODUCT_RECOMMENDATION, IntentType.WEED_CONTROL,
                IntentType.NUTRIENT_SUPPLEMENT,
            }
            if (intent in _recommendation_intents
                    and entities.get('product_name')
                    and not hints.get('product_name')):
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
        plants = ["ข้าว", "ทุเรียน", "มะม่วง", "ส้ม", "พริก", "ข้าวโพด", "อ้อย", "ลำไย"]
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
