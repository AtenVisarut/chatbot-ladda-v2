"""
Agentic RAG Orchestrator

Main entry point for the 4-agent RAG pipeline:
1. QueryUnderstandingAgent - Semantic intent detection, entity extraction
2. RetrievalAgent - Multi-query retrieval with re-ranking
3. GroundingAgent - Citation extraction, hallucination detection
4. ResponseGeneratorAgent - Answer synthesis with confidence scoring

Usage:
    from app.services.rag.orchestrator import AgenticRAG

    rag = AgenticRAG()
    response = await rag.process("โมเดิน ใช้กับทุเรียนได้ไหม")
    print(response.answer)
    print(f"Confidence: {response.confidence}")
    print(f"Citations: {len(response.citations)}")
"""

import logging
import time
from typing import Optional

from app.dependencies import openai_client, supabase_client
from app.services.rag import (
    IntentType,
    QueryAnalysis,
    AgenticRAGResponse
)
from app.services.rag.query_understanding_agent import QueryUnderstandingAgent
from app.services.rag.retrieval_agent import RetrievalAgent
from app.services.rag.grounding_agent import GroundingAgent
from app.services.rag.response_generator_agent import ResponseGeneratorAgent
from app.config import AGENTIC_RAG_CONFIG, LLM_MODEL_ENTITY_EXTRACTION

logger = logging.getLogger(__name__)


async def _llm_entity_extraction(query: str, product_list: list, openai_client_instance) -> dict:
    """
    LLM fallback: ใช้ gpt-4o-mini extract entities เมื่อ dictionary ไม่เจออะไร.
    Returns dict with keys: disease_name, pest_name, product_name, plant_type (all optional).
    Values tagged as [HINT_LLM] to distinguish from dictionary [CONSTRAINT].
    """
    try:
        products_str = ", ".join(product_list[:50])
        prompt = f"""จากคำถามเกษตรกรรมต่อไปนี้ ให้ดึง entity ที่เกี่ยวข้อง

คำถาม: "{query}"

รายชื่อสินค้าในระบบ: [{products_str}]

ตอบเป็น JSON เท่านั้น (ไม่มี markdown):
{{
    "disease_name": "<ชื่อโรคพืช ถ้ามี หรือ null>",
    "pest_name": "<ชื่อแมลง/ศัตรูพืช ถ้ามี หรือ null>",
    "product_name": "<ชื่อสินค้าจากรายชื่อข้างบน ถ้ามี หรือ null>",
    "plant_type": "<ชื่อพืช ถ้ามี หรือ null>"
}}

กฎ:
- ถ้าคำถามบอกอาการพืช (เช่น จุดสีน้ำตาลบนใบ, ใบเหลือง, ลำต้นเน่า) ให้ระบุชื่อโรคที่น่าจะเป็นสาเหตุใน disease_name
- ถ้าไม่แน่ใจเรื่องโรค ให้ใส่อาการเป็น disease_name (เช่น "ใบจุด", "รากเน่า")
- product_name ต้องเป็นชื่อจากรายชื่อข้างบนเท่านั้น ถ้าไม่มีให้ใส่ null
- ตอบ JSON เท่านั้น ห้ามมี text อื่น"""

        response = await openai_client_instance.chat.completions.create(
            model=LLM_MODEL_ENTITY_EXTRACTION,
            messages=[
                {"role": "system", "content": "คุณเป็นผู้เชี่ยวชาญด้านเกษตร ดึง entity จากคำถาม ตอบ JSON เท่านั้น"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_completion_tokens=200
        )

        import json
        import re as _re
        text = response.choices[0].message.content.strip()
        # Remove markdown code blocks if present
        if text.startswith("```"):
            text = _re.sub(r'^```(?:json)?\n?', '', text)
            text = _re.sub(r'\n?```$', '', text)

        data = json.loads(text)
        # Filter out null values
        result = {k: v for k, v in data.items() if v is not None}
        logger.info(f"  - LLM entity extraction: {result}")
        return result

    except Exception as e:
        logger.warning(f"LLM entity extraction failed: {e}")
        return {}


class AgenticRAG:
    """
    Agentic RAG Pipeline Orchestrator

    Coordinates the 4-agent pipeline for Q&A:
    Query -> Understanding -> Retrieval -> Grounding -> Response
    """

    def __init__(
        self,
        openai_client_instance=None,
        supabase_client_instance=None,
        config: dict = None
    ):
        """
        Initialize the Agentic RAG pipeline

        Args:
            openai_client_instance: OpenAI async client (defaults to global)
            supabase_client_instance: Supabase client (defaults to global)
            config: Configuration overrides
        """
        self.openai_client = openai_client_instance or openai_client
        self.supabase_client = supabase_client_instance or supabase_client
        self.config = config or AGENTIC_RAG_CONFIG

        # Initialize agents
        self.query_agent = QueryUnderstandingAgent(
            openai_client=self.openai_client
        )
        self.retrieval_agent = RetrievalAgent(
            supabase_client=self.supabase_client,
            openai_client=self.openai_client,
            vector_threshold=self.config.get('VECTOR_THRESHOLD', 0.35),
            rerank_threshold=self.config.get('RERANK_THRESHOLD', 0.50)
        )
        self.grounding_agent = GroundingAgent(
            openai_client=self.openai_client
        )
        self.response_agent = ResponseGeneratorAgent(
            openai_client=self.openai_client
        )

        logger.info("AgenticRAG initialized with config: %s", self.config)

    async def process(
        self,
        query: str,
        context: str = "",
        user_id: str = None
    ) -> AgenticRAGResponse:
        """
        Process a user query through the 4-agent pipeline

        Args:
            query: User's question
            context: Optional conversation context
            user_id: Optional user ID for personalization

        Returns:
            AgenticRAGResponse with answer, citations, confidence, etc.
        """
        start_time = time.time()

        try:
            logger.info(f"AgenticRAG.process: '{query[:50]}...'")

            # =================================================================
            # Stage 0: Pre-detect hints using keyword functions
            # =================================================================
            hints = {}
            try:
                from app.services.chat.handler import (
                    extract_product_name_from_question, detect_problem_type,
                    ICP_PRODUCT_NAMES, extract_plant_type_from_question,
                    DISEASE_KEYWORDS, INSECT_KEYWORDS,
                    resolve_farmer_slang
                )
                from app.utils.text_processing import generate_thai_disease_variants, resolve_symptom_to_pathogens, diacritics_match
                import re

                # --- Farmer Slang Resolution ---
                slang_result = resolve_farmer_slang(query)
                if slang_result["matched_slangs"]:
                    hints['resolved_slang'] = slang_result["hints"]
                    hints['extra_search_terms'] = slang_result["search_terms"]
                    if slang_result["problem_type"]:
                        hints['problem_type'] = slang_result["problem_type"]
                    logger.info(f"  - Farmer slang: {slang_result['matched_slangs']} → hints='{slang_result['hints']}'")

                # --- Symptom→Pathogen Resolution ---
                possible_diseases = resolve_symptom_to_pathogens(query)
                if possible_diseases:
                    hints['possible_diseases'] = possible_diseases
                    logger.info(f"  - Symptom→Pathogen: {possible_diseases}")

                detected_product = extract_product_name_from_question(query)
                product_from_query = bool(detected_product)
                # If no product in current query, try extracting from context (follow-up questions)
                if not detected_product and context:
                    # Split context into active topic vs past sections
                    _active_section = ""
                    _past_section = ""
                    if "[บทสนทนาปัจจุบัน]" in context:
                        # Extract active topic section
                        parts = context.split("[สรุปหัวข้อก่อนหน้า]")
                        _active_part = parts[0]
                        _past_section = parts[1] if len(parts) > 1 else ""
                        # Remove the section header
                        _active_section = _active_part.replace("[บทสนทนาปัจจุบัน]", "").strip()
                    else:
                        # Legacy format — treat all as active
                        _active_section = context

                    # Strategy 0: Use metadata-based [สินค้าล่าสุดในบทสนทนา] section
                    # ONLY for short follow-ups — skip if query introduces a new topic
                    _plant_in_query = extract_plant_type_from_question(query)
                    # NOTE: 'รา' and 'ไร' omitted — too short, false-positive in ราคา/อะไร/ไร่
                    # Layer 2 (query_understanding_agent skip set) handles those edge cases
                    _disease_pest_keywords = ['โรค', 'เพลี้ย', 'หนอน', 'ด้วง', 'แมลง', 'เชื้อ', 'ราแป้ง', 'ราน้ำ', 'ราสี', 'ราสนิม', 'ราดำ', 'ไรแดง', 'ไรขาว']
                    _has_disease_pest_kw = any(kw in query for kw in _disease_pest_keywords)
                    # Applicability pattern: plant + usage verb = asking "can this product be used on [plant]?"
                    # e.g. "ใช้ในทุเรียนได้มั้ย", "ฉีดมะม่วงได้ไหม" → NOT a new topic
                    _usage_verbs = ['ใช้', 'ฉีด', 'พ่น', 'ผสม', 'ราด', 'หยด', 'รด']
                    _is_applicability = _plant_in_query and any(v in query for v in _usage_verbs)
                    _has_new_topic = (_plant_in_query and not _is_applicability) or _has_disease_pest_kw
                    if _has_new_topic:
                        logger.info(f"  - Strategy 0 skipped: query has new topic (plant={_plant_in_query})")
                    else:
                        for line in context.split('\n'):
                            if line.startswith("[สินค้าล่าสุดในบทสนทนา]"):
                                # Extract first product (= most relevant from last recommendation)
                                section_text = line.replace("[สินค้าล่าสุดในบทสนทนา]", "").strip()
                                if section_text:
                                    for product_name in section_text.split(','):
                                        pname = product_name.strip()
                                        if pname in ICP_PRODUCT_NAMES:
                                            detected_product = pname
                                            logger.info(f"  - Product from metadata (recent recommendation): {detected_product}")
                                            break
                                break

                    # Strategy 1: Scan active topic text (bottom-up, last assistant msg)
                    if not detected_product and _active_section:
                        active_lines = _active_section.strip().split('\n')
                        for line in reversed(active_lines):
                            if line.startswith('[') and ']' in line:
                                continue
                            detected_product = extract_product_name_from_question(line)
                            if detected_product:
                                logger.info(f"  - Product from active topic: {detected_product}")
                                break
                            # Stop after reaching a role prefix (= next message boundary)
                            if line.startswith("ผู้ใช้:") or line.startswith("น้องลัดดา:"):
                                break

                    # Strategy 2: Fallback to [สินค้าที่แนะนำไปแล้ว] section
                    # ONLY if query is a true follow-up (usage question) without disease/pest
                    # NOT for queries asking for new recommendations
                    if not detected_product:
                        has_disease_or_pest = hints.get('disease_name') or hints.get('pest_name')
                        is_short_followup = len(query.strip()) < 40
                        _RECOMMENDATION_KEYWORDS = [
                            "แนะนำ", "มีอะไร", "มีไหม", "ตัวไหนดี", "อะไรดี",
                            "ควรใช้อะไร", "ใช้อะไรดี", "มียาอะไร",
                        ]
                        is_asking_for_recommendations = any(kw in query for kw in _RECOMMENDATION_KEYWORDS)
                        if is_short_followup and not has_disease_or_pest and not is_asking_for_recommendations:
                            # Scan bottom-up to find [สินค้าที่แนะนำไปแล้ว] section first
                            for line in reversed(context.split('\n')):
                                if line.startswith("[สินค้าที่แนะนำไปแล้ว]"):
                                    for product_name in ICP_PRODUCT_NAMES.keys():
                                        if product_name in line:
                                            detected_product = product_name
                                            logger.info(f"  - Product from summary section (follow-up): {detected_product}")
                                            break
                                    break
                if detected_product:
                    hints['product_name'] = detected_product
                    hints['_product_from_query'] = product_from_query
                detected_problem = detect_problem_type(query)
                if detected_problem != 'unknown':
                    hints['problem_type'] = detected_problem

                # --- Pre-LLM Entity Extraction: Disease ---
                from app.services.disease.constants import DISEASE_PATTERNS_SORTED, get_canonical
                for pattern in DISEASE_PATTERNS_SORTED:
                    if diacritics_match(query, pattern):
                        hints['disease_name'] = get_canonical(pattern)
                        hints['disease_variants'] = generate_thai_disease_variants(pattern)
                        logger.info(f"  - Pre-extracted disease: '{pattern}' variants={hints['disease_variants']}")
                        break

                # --- Pre-LLM Entity Extraction: Plant type ---
                detected_plant = extract_plant_type_from_question(query)
                if detected_plant:
                    hints['plant_type'] = detected_plant
                    logger.info(f"  - Pre-extracted plant: '{detected_plant}'")

                # --- Pre-LLM Entity Extraction: Pest name ---
                _PEST_PATTERNS_STAGE0 = [
                    'เพลี้ยไฟ', 'เพลี้ยอ่อน', 'เพลี้ยแป้ง', 'เพลี้ยกระโดด',
                    'เพลี้ยจักจั่น', 'เพลี้ย',
                    'หนอนกอ', 'หนอนเจาะ', 'หนอนใย', 'หนอนกระทู้', 'หนอน',
                    'ด้วงงวง', 'ด้วง',
                    'แมลงวันผล', 'แมลงหวี่ขาว', 'แมลงวัน', 'แมลง',
                    'ไรแดง', 'ไรขาว', 'ไรแมง', 'ตัวไร',
                    'ทริปส์', 'จักจั่น', 'มด', 'ปลวก',
                ]
                for pattern in _PEST_PATTERNS_STAGE0:
                    if diacritics_match(query, pattern):
                        hints['pest_name'] = pattern  # canonical pattern
                        logger.info(f"  - Pre-extracted pest: '{pattern}'")
                        break

                # --- Weed Synonym Injection ---
                # "หญ้า" doesn't match product embeddings that use "วัชพืช"
                # Inject synonyms so vector search finds herbicide products
                if hints.get('problem_type') == 'weed':
                    _WEED_SYNONYM_MAP = {
                        'หญ้า': ['วัชพืช', 'กำจัดวัชพืช', 'ยาฆ่าหญ้า'],
                        'กำจัดหญ้า': ['กำจัดวัชพืช', 'วัชพืช'],
                        'ยาฆ่าหญ้า': ['สารกำจัดวัชพืช', 'วัชพืช'],
                        'หญ้าขึ้น': ['วัชพืช', 'กำจัดวัชพืช'],
                        'หญ้างอก': ['วัชพืช', 'หลังวัชพืชงอก'],
                    }
                    weed_synonyms = set()
                    for pattern, synonyms in _WEED_SYNONYM_MAP.items():
                        if pattern in query:
                            weed_synonyms.update(synonyms)
                    if not weed_synonyms:
                        weed_synonyms = {'วัชพืช', 'กำจัดวัชพืช'}
                    hints['weed_synonyms'] = list(weed_synonyms)
                    logger.info(f"  - Weed synonyms injected: {hints['weed_synonyms']}")

                # --- Validate: drop product when query is about a new topic ---
                # Case 1: Disease/pest entity detected + product not literally in query
                #   e.g. "โรครากเน่าโคนเน่า" → fuzzy "โค-ราซ" (false positive)
                # Case 2: Product from context + disease/pest topic + product not in query
                #   e.g. focus=ไซม๊อกซิเมท but query "ไฟท็อป ใช้สารอะไร" (new topic)
                if hints.get('product_name'):
                    product_aliases = ICP_PRODUCT_NAMES.get(hints['product_name'], [])
                    product_literally_in_query = any(
                        alias.lower() in query.lower() for alias in product_aliases
                    )
                    # Check if current msg mentions a DIFFERENT product explicitly
                    new_product_in_query = extract_product_name_from_question(query)
                    has_new_different_product = (
                        new_product_in_query
                        and new_product_in_query != hints['product_name']
                    )
                    drop_reason = None
                    if has_new_different_product:
                        drop_reason = f"new product '{new_product_in_query}' explicitly mentioned"
                        hints['product_name'] = new_product_in_query
                    elif (hints.get('disease_name') or hints.get('pest_name')) and not product_literally_in_query:
                        drop_reason = "disease/pest detected, product not in query"
                    elif (not product_from_query and not product_literally_in_query
                            and hints.get('problem_type') in ('disease', 'pest', 'weed', 'nutrient')):
                        drop_reason = f"new {hints['problem_type']} topic, product from context"
                    # Case 4: Vague/generic query — no specific entity, product from memory
                    elif not product_from_query and not product_literally_in_query:
                        # Keep if user references previous product ("ยาตัวนี้", "ตัวนั้น")
                        _REFERENCING_PATTERNS = [
                            'ตัวนี้', 'ยาตัวนี้', 'ตัวนั้น', 'ยานี้', 'สินค้านี้',
                            'ยาตัวแรก', 'ยาตัวที่',
                        ]
                        _has_reference = any(p in query for p in _REFERENCING_PATTERNS)

                        # Keep if short follow-up about usage ("ใช้ยังไง", "ผสมกี่")
                        _FOLLOWUP_USAGE = [
                            'ใช้ยังไง', 'ใช้เท่าไหร่', 'ผสมกี่', 'ฉีดกี่', 'พ่นกี่',
                            'ผสมเท่าไหร่', 'อัตราเท่าไหร่', 'ใช้กี่', 'ราดกี่',
                            'ใช้ช่วงไหน', 'ใช้ตอนไหน', 'ใช้ได้กี่', 'ได้ผลไหม',
                        ]
                        _is_usage_followup = len(query.strip()) < 30 and any(p in query for p in _FOLLOWUP_USAGE)

                        if not _has_reference and not _is_usage_followup:
                            _has_specific_entity = bool(
                                hints.get('disease_name') or hints.get('pest_name')
                                or hints.get('plant_type')
                                or (hints.get('problem_type') and hints['problem_type'] != 'unknown')
                            )
                            if not _has_specific_entity:
                                drop_reason = "vague/generic query, no specific entity, product from memory"
                    if drop_reason and not has_new_different_product:
                        logger.info(f"  - Drop product: '{hints['product_name']}' ({drop_reason})")
                        del hints['product_name']
                    elif has_new_different_product:
                        logger.info(f"  - Switch product: → '{hints['product_name']}' ({drop_reason})")

                # --- 2C: Ambiguous product detection ---
                # If user asks a follow-up but no product is clear, and context has 2+ products
                if (not hints.get('product_name') and not product_from_query and context):
                    # Scan context for product names
                    context_products = set()
                    for pname in ICP_PRODUCT_NAMES.keys():
                        if pname in context:
                            context_products.add(pname)
                    # Also check [สินค้าที่แนะนำไปแล้ว] section
                    if len(context_products) >= 2:
                        # Check if query is a follow-up question (short, no product name)
                        followup_patterns = [
                            "ใช้ยังไง", "ใช้เท่าไหร่", "อัตราเท่าไหร่", "ผสมเท่าไหร่",
                            "ใช้ช่วงไหน", "ตัวไหนดี", "ตัวไหนเหมาะ", "ใช้กี่",
                            "พ่นกี่", "ฉีดกี่", "ใช้กับ", "เหมาะกับ"
                        ]
                        recommendation_keywords = ["แนะนำยา", "แนะนำสาร", "ช่วยแนะนำ", "ใช้อะไรดี", "ใช้ตัวไหนดี", "ยาอะไรดี"]
                        is_recommendation = any(kw in query for kw in recommendation_keywords)
                        is_followup = (
                            any(p in query for p in followup_patterns)
                            and len(query) < 50
                            and not is_recommendation
                        )
                        if is_followup:
                            products_list = sorted(context_products)[:4]
                            clarify_msg = f"ขอถามหน่อยค่ะ หมายถึง " + " หรือ ".join(f'"{p}"' for p in products_list) + " คะ?"
                            hints['ambiguous_products'] = products_list
                            logger.info(f"  - Ambiguous products: {products_list}, will ask user")
                            return AgenticRAGResponse(
                                answer=clarify_msg,
                                confidence=0.5,
                                citations=[],
                                intent=IntentType.UNKNOWN,
                                is_grounded=True,
                                sources_used=[],
                                processing_time_ms=(time.time() - start_time) * 1000
                            )

                # --- LLM Fallback Entity Extraction ---
                # When dictionary scan finds nothing and query is long enough
                _has_any_entity = (
                    hints.get('disease_name') or hints.get('pest_name')
                    or hints.get('product_name')
                )
                _is_greeting = hints.get('problem_type') == 'greeting'
                if not _has_any_entity and not _is_greeting and len(query.strip()) >= 10:
                    llm_entities = await _llm_entity_extraction(
                        query,
                        list(ICP_PRODUCT_NAMES.keys()),
                        self.openai_client
                    )
                    if llm_entities:
                        # Tag as HINT_LLM — Agent 1 can adjust these
                        for key in ('disease_name', 'pest_name', 'product_name', 'plant_type'):
                            if llm_entities.get(key) and not hints.get(key):
                                hints[key] = llm_entities[key]
                                hints.setdefault('_llm_fallback_keys', []).append(key)
                        logger.info(f"  - LLM fallback entities applied: {llm_entities}")

                logger.info(f"  - Hints: {hints}")
            except ImportError:
                logger.warning("Could not import hint functions from chat.py")

            # =================================================================
            # Stage 1: Query Understanding
            # =================================================================
            query_analysis = await self.query_agent.analyze(query, context=context, hints=hints)

            # Inject possible_diseases from symptom mapping into entities for downstream use
            if hints.get('possible_diseases'):
                query_analysis.entities['possible_diseases'] = hints['possible_diseases']

            # Handle greeting intent directly
            if query_analysis.intent == IntentType.GREETING:
                response = await self.response_agent.generate(
                    query_analysis=query_analysis,
                    retrieval_result=None,
                    grounding_result=None
                )
                response.processing_time_ms = (time.time() - start_time) * 1000
                return response

            # Handle unknown intent with low confidence
            # But if query contains product-related keywords, still try retrieval
            product_keywords = ["ใช้สาร", "ใช้ยา", "ใช้อะไร", "รักษา", "กำจัด", "ฉีด", "พ่น", "ผสม", "อัตรา"]
            has_product_keywords = any(kw in query for kw in product_keywords)
            if query_analysis.intent == IntentType.UNKNOWN and query_analysis.confidence < 0.3 and not has_product_keywords:
                logger.info("Low confidence unknown intent, routing to general chat")
                return AgenticRAGResponse(
                    answer=None,  # Signal to use general chat
                    confidence=query_analysis.confidence,
                    citations=[],
                    intent=query_analysis.intent,
                    is_grounded=False,
                    sources_used=[],
                    query_analysis=query_analysis,
                    processing_time_ms=(time.time() - start_time) * 1000
                )
            elif query_analysis.intent == IntentType.UNKNOWN and has_product_keywords:
                logger.info("Unknown intent but has product keywords, forcing retrieval")
                query_analysis.required_sources = ["products"]

            # =================================================================
            # Stage 2: Retrieval
            # =================================================================
            retrieval_result = await self.retrieval_agent.retrieve(
                query_analysis=query_analysis,
                top_k=self.config.get('RETRIEVAL_TOP_K', 10)
            )

            # =================================================================
            # Stage 3: Grounding
            # =================================================================
            if self.config.get('ENABLE_GROUNDING', True):
                grounding_result = await self.grounding_agent.ground(
                    query_analysis=query_analysis,
                    retrieval_result=retrieval_result
                )
            else:
                # Skip grounding, use retrieval directly
                from app.services.rag import GroundingResult
                grounding_result = GroundingResult(
                    is_grounded=bool(retrieval_result.documents),
                    confidence=retrieval_result.avg_similarity,
                    citations=[],
                    ungrounded_claims=[],
                    suggested_answer=""
                )

            # =================================================================
            # Stage 4: Response Generation
            # =================================================================
            response = await self.response_agent.generate(
                query_analysis=query_analysis,
                retrieval_result=retrieval_result,
                grounding_result=grounding_result,
                context=context
            )

            response.processing_time_ms = (time.time() - start_time) * 1000
            logger.info(f"AgenticRAG completed in {response.processing_time_ms:.0f}ms")
            logger.info(f"  - Answer length: {len(response.answer) if response.answer else 0}")
            logger.info(f"  - Confidence: {response.confidence:.2f}")
            logger.info(f"  - Grounded: {response.is_grounded}")

            return response

        except Exception as e:
            logger.error(f"AgenticRAG.process error: {e}", exc_info=True)
            return AgenticRAGResponse(
                answer="ขออภัยค่ะ เกิดข้อผิดพลาดในการประมวลผล กรุณาลองใหม่อีกครั้งนะคะ",
                confidence=0.0,
                citations=[],
                intent=IntentType.UNKNOWN,
                is_grounded=False,
                sources_used=[],
                processing_time_ms=(time.time() - start_time) * 1000
            )

    async def process_simple(self, query: str) -> str:
        """
        Simple interface that returns just the answer string

        Args:
            query: User's question

        Returns:
            Answer string (or None to signal use general chat)
        """
        response = await self.process(query)
        return response.answer


# Global singleton instance
_agentic_rag_instance: Optional[AgenticRAG] = None


def get_agentic_rag() -> AgenticRAG:
    """Get or create the global AgenticRAG instance"""
    global _agentic_rag_instance
    if _agentic_rag_instance is None:
        _agentic_rag_instance = AgenticRAG()
    return _agentic_rag_instance


async def process_with_agentic_rag(query: str, context: str = "") -> AgenticRAGResponse:
    """
    Convenience function to process a query with the global AgenticRAG instance

    Args:
        query: User's question
        context: Optional conversation context

    Returns:
        AgenticRAGResponse
    """
    rag = get_agentic_rag()
    return await rag.process(query, context)
