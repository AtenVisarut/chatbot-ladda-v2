"""
Agentic RAG Orchestrator

Main entry point for the 3-agent RAG pipeline:
1. QueryUnderstandingAgent - Semantic intent detection, entity extraction
2. RetrievalAgent - Multi-query retrieval with re-ranking
3. ResponseGeneratorAgent - Answer synthesis with confidence scoring

Usage:
    from app.services.rag.orchestrator import AgenticRAG

    rag = AgenticRAG()
    response = await rag.process("โมเดิน ใช้กับทุเรียนได้ไหม")
    print(response.answer)
    print(f"Confidence: {response.confidence}")
    print(f"Citations: {len(response.citations)}")
"""

import asyncio
import logging
import re
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
from app.services.rag.response_generator_agent import ResponseGeneratorAgent
from app.config import AGENTIC_RAG_CONFIG

logger = logging.getLogger(__name__)

_STAGE_WORDS = (
    # Fruit trees — ใบ/ดอก/ผล
    "ใบอ่อน", "ใบแก่", "แตกใบ", "แตกยอด",
    "ออกดอก", "กำลังออกดอก", "ระยะดอก", "ระยะก่อนออกดอก", "ดอก",
    "ติดผล", "กำลังติดผล", "ระยะติดผล", "ระยะผล",
    "ผลเล็ก", "ผลอ่อน", "ผลแก่",
    # Post-harvest
    "หลังเก็บเกี่ยว", "หลังเก็บ", "ก่อนเก็บ", "ก่อนเก็บเกี่ยว",
    # Seedling / vegetative — ทั่วไป
    "ระยะ", "ต้นกล้า", "ต้นอ่อน", "ต้นเล็ก", "เพาะกล้า", "ปลูกใหม่",
    "โตเต็มที่",
    # Rice (ข้าว) — ต้องครบเพราะ bot ใช้ตัวอย่างระยะข้าวใน best-pick prompt
    "แตกกอ", "ตั้งท้อง", "ออกรวง", "สุก", "เก็บเกี่ยว",
    # Corn/beans (ข้าวโพด, ถั่ว) — ฝัก + ก่อนออกดอก
    "ก่อนออกดอก", "ติดฝัก", "ออกฝัก", "ฝักแก่",
    # Sugarcane (อ้อย)
    "ยืดปล้อง",
    # Cassava (มันสำปะหลัง)
    "สร้างหัว",
    # Onion / garlic / potato — ลงหัว
    "ลงหัว",
    # Rubber (ยางพารา)
    "ให้น้ำยาง",
)


class AgenticRAG:
    """
    Agentic RAG Pipeline Orchestrator

    Coordinates the 3-agent pipeline for Q&A:
    Query -> Understanding -> Retrieval -> Response
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
            # Stage -1: Clarification reply detection
            # If bot previously asked for missing context (stage/plant/rate)
            # and user's current reply is a short stage-only answer → merge with
            # the root topic from the earlier user message so the pipeline
            # continues the original intent (disease/pest/weed) instead of
            # classifying the bare stage word as a new nutrient query.
            # =================================================================
            if context:
                _is_short_stage_reply = (
                    len(query.strip()) < 30
                    and any(kw in query for kw in _STAGE_WORDS)
                )
                # Was the bot's last message an ask-back for stage/plant?
                # Match bot's generated patterns: f"ระยะของ{plant}ตอนนี้" / "ระยะของพืชตอนนี้" / "ระยะของวัชพืช"
                # (avoid false positives on user's "ระยะของการใช้ยา" etc.)
                _bot_asked_for_context = (
                    "ขอทราบข้อมูลเพิ่มเติม" in context
                    or ("ระยะของ" in context and "ตอนนี้" in context)
                    or "ระยะของวัชพืช" in context
                    or "ใช้กับพืชอะไร" in context
                )
                if _is_short_stage_reply and _bot_asked_for_context:
                    # Find the MOST RECENT substantive ผู้ใช้: line in context
                    # — that is the CURRENT topic the user is on, not the
                    # first topic of the session.
                    # Skip best-pick intermediaries ("ตัวไหนดีสุด") and
                    # stage-only replies (the current one) so we find the
                    # real product/problem question.
                    _user_msgs = re.findall(r"ผู้ใช้:\s*(.+?)(?=\n|$)", context)
                    _SKIP_PATTERNS = (
                        "ตัวไหนดี", "อันไหนดี", "แนะนำตัวไหน", "สรุปตัวไหน",
                        "ใช้ตัวไหน", "เลือกตัวไหน",
                    )
                    _root_topic = None
                    # Reverse iteration: prefer most recent topic
                    for msg in reversed(_user_msgs):
                        msg = msg.strip()
                        if len(msg) < 10:
                            continue
                        if any(p in msg for p in _SKIP_PATTERNS):
                            continue
                        # Skip messages that are themselves stage-only replies
                        # (keeps us from picking up an earlier clarification echo)
                        if (len(msg) < 30
                                and any(w in msg for w in _STAGE_WORDS)
                                and not any(w in msg for w in ("ยา", "ใช้", "แนะนำ",
                                                              "โรค", "หนอน", "เพลี้ย",
                                                              "หญ้า", "บำรุง"))):
                            continue
                        _root_topic = msg
                        break
                    if _root_topic:
                        logger.info(
                            f"  - Clarification reply: merging with latest topic\n"
                            f"    latest: {_root_topic[:60]}\n"
                            f"    reply: {query}"
                        )
                        query = f"{_root_topic} {query.strip()}"

            # =================================================================
            # Stage 0: Pre-detect hints using keyword functions
            # =================================================================
            hints = {}
            detected_product = None
            product_from_query = False
            product_literally_in_query = False
            try:
                from app.services.chat.handler import (
                    extract_product_name_from_question, extract_all_product_names_from_question,
                    detect_problem_types,
                    ICP_PRODUCT_NAMES, extract_plant_type_from_question,
                    DISEASE_KEYWORDS, INSECT_KEYWORDS,
                    resolve_farmer_slang
                )
                from app.utils.text_processing import generate_thai_disease_variants, resolve_symptom_to_pathogens, diacritics_match

                _skip_context_product = False  # flag: ถ้า new_topic detected → ไม่ดึง product จาก context

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

                # Extract all product names (supports multi-product comparison)
                all_detected_products = extract_all_product_names_from_question(query)
                detected_product = all_detected_products[0] if all_detected_products else None
                product_from_query = bool(detected_product)
                if len(all_detected_products) > 1:
                    hints['product_names'] = all_detected_products
                    logger.info(f"  - Multi-product query: {all_detected_products}")

                # Fix #2: Topic boundary — when user pipelines a NEW product that
                # differs from active_product in conversation state, treat as new
                # topic and skip stale memory context (prevents disease/products
                # from older turns polluting retrieval).
                if user_id and product_from_query:
                    try:
                        from app.services.cache import get_conversation_state
                        _prev_state = await get_conversation_state(user_id)
                        if _prev_state and _prev_state.get('active_product'):
                            _prev = _prev_state['active_product']
                            if _prev not in all_detected_products:
                                _skip_context_product = True
                                logger.info(f"  - New-product topic: query has {all_detected_products}, state had '{_prev}' — skipping context")
                    except Exception:
                        pass
                # ── Strategy -1: Conversation State (most reliable for follow-ups) ──
                # Read explicit state instead of scanning text heuristically
                if not detected_product and user_id:
                    try:
                        from app.services.cache import get_conversation_state
                        conv_state = await get_conversation_state(user_id)
                        if conv_state and conv_state.get('active_product'):
                            _plant_in_q_s = extract_plant_type_from_question(query)
                            _dp_kw = ['โรค', 'เพลี้ย', 'หนอน', 'ด้วง', 'แมลง', 'เชื้อ', 'ราแป้ง', 'ราน้ำ', 'ราสี', 'ราสนิม', 'ราดำ', 'ไรแดง', 'ไรขาว',
                                     'ยับยั้ง', 'หญ้า', 'วัชพืช', 'ปุ๋ย', 'ฮอร์โมน', 'สารควบคุม', 'แตกใบอ่อน', 'ใบอ่อน']
                            _has_dp = any(kw in query for kw in _dp_kw)
                            # "ใช้ยาอะไร" / "ใช้ตัวไหน" = ถามหาสินค้าใหม่ → new topic
                            _ask_new_product = ['ยาอะไร', 'ใช้ยาอะไร', 'ใช้ตัวไหน', 'ใช้อะไรดี',
                                               'แนะนำตัวไหน', 'ใช้อะไร', 'มียาอะไร', 'แนะนำยา']
                            _is_asking_new = any(kw in query for kw in _ask_new_product)
                            _uv = ['ใช้', 'ฉีด', 'พ่น', 'ผสม', 'ราด', 'หยด', 'รด',
                                   'บำรุง', 'เร่ง', 'พัฒนา', 'เสริม', 'กระตุ้น']
                            _is_app = _plant_in_q_s and any(v in query for v in _uv)
                            # ถ้าไม่มีชื่อสินค้าและไม่มีชื่อพืช → subjectless follow-up → ไม่ถือเป็น new topic
                            _subjectless = not detected_product and not _plant_in_q_s
                            # ถ้าพืชใน query ต่างจากพืชใน state → new topic ทันที
                            _state_plant = conv_state.get('active_plant', '')
                            _different_plant = _plant_in_q_s and _state_plant and _plant_in_q_s != _state_plant
                            # Comparison follow-up re-stating the same plant ("ตัวไหนดีสำหรับข้าว"
                            # while state.active_plant=ข้าว) is narrowing-down, not a topic switch.
                            from app.services.rag.followup_patterns import is_comparison_followup
                            _is_compare = is_comparison_followup(query)
                            _plant_would_be_new = _plant_in_q_s and not _is_app and not (_is_compare and not _different_plant)
                            _new_topic = _different_plant or _plant_would_be_new or (_has_dp and not _subjectless) or _is_asking_new
                            if not _new_topic:
                                detected_product = conv_state['active_product']
                                logger.info(f"  - Product from conversation state: {detected_product}")
                                # Fix #1: Comparison follow-up → use ALL last-turn products (not just 1)
                                # so "ใช้แตกต่างกันยังไง" after bot showed 2 variants retrieves both
                                _active_products = conv_state.get('active_products') or []
                                if _is_compare and len(_active_products) >= 2:
                                    hints['product_names'] = list(_active_products)
                                    hints['_comparison_followup'] = True
                                    all_detected_products = list(_active_products)
                                    logger.info(f"  - Comparison follow-up: using all {len(_active_products)} products from state: {_active_products}")
                            else:
                                _skip_context_product = True
                                logger.info(f"  - State has '{conv_state['active_product']}' but query has new topic (plant:{_plant_in_q_s} vs state:{_state_plant}), skipping")
                    except Exception as e:
                        logger.warning(f"  - Conversation state read failed (non-critical): {e}")

                # If no product in current query, try extracting from context (follow-up questions)
                # Skip if new_topic was detected — ป้องกันดึง product เก่าจาก context
                if not detected_product and context and not _skip_context_product:
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
                    _usage_verbs = ['ใช้', 'ฉีด', 'พ่น', 'ผสม', 'ราด', 'หยด', 'รด',
                                    'บำรุง', 'เร่ง', 'พัฒนา', 'เสริม', 'กระตุ้น']
                    # Explicit applicability check phrases ("ใช้ได้มั้ย/ได้ไหม/ใช้ได้ป่ะ")
                    _APPLICABILITY_PHRASES = [
                        'ใช้ได้มั้ย', 'ใช้ได้ไหม', 'ใช้ได้ป่ะ', 'ใช้ได้รึเปล่า',
                        'ฉีดได้มั้ย', 'ฉีดได้ไหม', 'พ่นได้มั้ย', 'พ่นได้ไหม',
                        'กับ{plant}ได้', 'ใน{plant}ได้', 'ใช้กับ', 'ใช้ในได้',
                    ]
                    _has_applicability_phrase = any(p.replace('{plant}', _plant_in_query or '') in query for p in _APPLICABILITY_PHRASES if '{plant}' not in p or _plant_in_query) or any(
                        kw in query for kw in ['ใช้ได้มั้ย', 'ใช้ได้ไหม', 'ฉีดได้มั้ย', 'ฉีดได้ไหม', 'ได้มั้ย', 'ได้ไหม']
                    )
                    _is_applicability = _plant_in_query and any(v in query for v in _usage_verbs)
                    _has_new_topic = (_plant_in_query and not _is_applicability) or (_has_disease_pest_kw and not _has_applicability_phrase)

                    # Extract previous product from context regardless of new-topic detection —
                    # needed so we can annotate "user ถาม applicability ของสินค้านี้"
                    _prev_product_from_context: Optional[str] = None
                    for line in context.split('\n'):
                        if line.startswith("[สินค้าล่าสุดในบทสนทนา]"):
                            section_text = line.replace("[สินค้าล่าสุดในบทสนทนา]", "").strip()
                            if section_text:
                                for product_name in section_text.split(','):
                                    pname = product_name.strip()
                                    if pname in ICP_PRODUCT_NAMES:
                                        _prev_product_from_context = pname
                                        break
                            break

                    if _has_new_topic:
                        logger.info(f"  - Strategy 0 skipped: query has new topic (plant={_plant_in_query})")
                        # Still capture previous product as 'asked_product' when applicability phrasing present
                        if _has_applicability_phrase and _prev_product_from_context:
                            hints['asked_product'] = _prev_product_from_context
                            # Ensure retrieval fetches asked_product's doc alongside new pest/plant search
                            _pnames = list(hints.get('product_names') or [])
                            if _prev_product_from_context not in _pnames:
                                _pnames.insert(0, _prev_product_from_context)
                                hints['product_names'] = _pnames
                            logger.info(f"  - Applicability question: asked_product='{_prev_product_from_context}' (query about new pest/plant)")
                    else:
                        if _prev_product_from_context:
                            detected_product = _prev_product_from_context
                            logger.info(f"  - Product from metadata (recent recommendation): {detected_product}")
                        # Mark as applicability when phrase present — lets LLM know to confirm/deny
                        if _has_applicability_phrase and detected_product:
                            hints['asked_product'] = detected_product
                            logger.info(f"  - Applicability question: asked_product='{detected_product}'")

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
                detected_problems = detect_problem_types(query)
                if detected_problems:
                    hints['problem_type'] = detected_problems[0]
                if len(detected_problems) > 1:
                    hints['problem_types'] = detected_problems
                    logger.info(f"  - Compound intent: {detected_problems}")

                # --- Pre-LLM Entity Extraction: Disease ---
                from app.services.disease.constants import DISEASE_PATTERNS_SORTED, get_canonical
                for pattern in DISEASE_PATTERNS_SORTED:
                    if diacritics_match(query, pattern):
                        hints['disease_name'] = get_canonical(pattern)
                        hints['disease_variants'] = generate_thai_disease_variants(pattern)
                        logger.info(f"  - Pre-extracted disease: '{pattern}' variants={hints['disease_variants']}")
                        break

                # --- Broad disease term detection (e.g. "เชื้อรา" = generic fungal disease) ---
                if not hints.get('disease_name') and hints.get('problem_type') == 'disease':
                    _BROAD_DISEASE_KW = {'เชื้อรา': 'เชื้อรา', 'โรคเชื้อรา': 'เชื้อรา', 'โรคราพืช': 'เชื้อรา'}
                    for kw, canonical in _BROAD_DISEASE_KW.items():
                        if kw in query:
                            hints['disease_name'] = canonical
                            logger.info(f"  - Pre-extracted broad disease: '{canonical}'")
                            break

                # --- Pre-LLM Entity Extraction: Plant type ---
                detected_plant = extract_plant_type_from_question(query)
                if detected_plant:
                    hints['plant_type'] = detected_plant
                    logger.info(f"  - Pre-extracted plant: '{detected_plant}'")

                # --- Diagnostic Intent + Crop-Specific Disease Priors ---
                # Gated by DIAGNOSTIC_INTENT_ENABLED flag for safe rollout.
                # Only refines possible_diseases when: flag on + intent is
                # diagnostic ("เกิดจากอะไร", etc.) + plant_type known.
                # Never removes or overrides a Stage 0 pinned disease_name —
                # hedge + priors flow through hints, existing CONSTRAINT
                # path is untouched.
                from app.config import DIAGNOSTIC_INTENT_ENABLED
                if DIAGNOSTIC_INTENT_ENABLED:
                    from app.services.disease.diagnostic_intent import is_diagnostic_query
                    from app.services.disease.crop_disease_priors import resolve_crop_symptom_to_diseases
                    if is_diagnostic_query(query):
                        hints['diagnostic_intent'] = True
                        crop = hints.get('plant_type')
                        if crop:
                            crop_diseases = resolve_crop_symptom_to_diseases(crop, query)
                            if crop_diseases:
                                generic = hints.get('possible_diseases', []) or []
                                hints['possible_diseases'] = crop_diseases + [
                                    d for d in generic if d not in crop_diseases
                                ]
                                hints['_prior_source'] = 'crop_specific'
                                logger.info(
                                    f"[DIAG] plant={crop} priors_used=crop_specific "
                                    f"candidates={hints['possible_diseases']}"
                                )
                            elif hints.get('possible_diseases'):
                                hints['_prior_source'] = 'generic_symptom'
                                logger.info(
                                    f"[DIAG] plant={crop} priors_used=generic_symptom "
                                    f"candidates={hints['possible_diseases']}"
                                )

                # --- Pre-LLM Entity Extraction: Pest name ---
                # Compound words: "ยาเพลี้ย", "ยาหนอน" → extract pest name
                _PEST_COMPOUND_WORD_MAP = {
                    'ยาเพลี้ย': 'เพลี้ย', 'ยาหนอน': 'หนอน', 'ยาแมลง': 'แมลง',
                    'ยาฆ่าเพลี้ย': 'เพลี้ย', 'ยาฆ่าหนอน': 'หนอน', 'ยาฆ่าแมลง': 'แมลง',
                    'สารกำจัดเพลี้ย': 'เพลี้ย', 'สารกำจัดหนอน': 'หนอน', 'สารกำจัดแมลง': 'แมลง',
                    'กำจัดเพลี้ย': 'เพลี้ย', 'กำจัดหนอน': 'หนอน', 'กำจัดแมลง': 'แมลง',
                }
                for _compound, _pest in _PEST_COMPOUND_WORD_MAP.items():
                    if _compound in query:
                        hints['pest_name'] = _pest
                        logger.info(f"  - Pre-extracted pest (compound): '{_compound}' → '{_pest}'")
                        break

                _PEST_PATTERNS_STAGE0 = [
                    # Specific before generic (longest-first matching)
                    'เพลี้ยกระโดดสีน้ำตาล', 'เพลี้ยจักจั่นข้าวโพด', 'เพลี้ยกระโดดข้าวโพด',
                    'เพลี้ยจักจั่นมะม่วง', 'เพลี้ยจักจั่นเขียว', 'เพลี้ยจักจั่นฝอย',
                    'เพลี้ยไก่แจ้', 'เพลี้ยกระโดด', 'เพลี้ยจักจั่น', 'เพลี้ยหอย',
                    'เพลี้ยไฟ', 'เพลี้ยอ่อน', 'เพลี้ยแป้ง', 'เพลี้ย',
                    'หนอนเจาะผล', 'หนอนชอนใบ', 'หนอนกระทู้',
                    'หนอนกอ', 'หนอนเจาะ', 'หนอนใย', 'หนอน',
                    'แมลงค่อมทอง', 'แมลงวันผล', 'แมลงหวี่ขาว', 'แมลงวัน', 'แมลง',
                    'ด้วงงวง', 'ด้วง',
                    'ไรสี่ขา', 'ไรแดง', 'ไรขาว', 'ไรแมง', 'ตัวไร',
                    'ทริปส์', 'จักจั่น', 'มด', 'ปลวก',
                ]
                # Only check pattern list if compound word didn't match
                if 'pest_name' not in hints:
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

                # --- Specific Weed Name Extraction (Stage 0) ---
                # Parallel to _PEST_PATTERNS_STAGE0: catches weeds with proper names
                # so retrieval can verify products actually target them.
                # Without this, "ข้าวดีด" just becomes generic "หญ้า" and any
                # rice herbicide matches, even those targeting ข้าวนก instead.
                _WEED_PATTERNS_STAGE0 = [
                    # Specific before generic (longest-first matching)
                    'หญ้าข้าวนก', 'ข้าวดีด', 'ข้าวตีด', 'ข้าวนก',
                    'หญ้าดอกขาว', 'หญ้าหนวดแมว', 'หญ้าแห้วหมู',
                    'หญ้าตีนกา', 'หญ้าตีนนก', 'หญ้าปากควาย',
                    'หญ้านกสีชมพู', 'หญ้าไม้กวาด', 'หญ้าขจรจบ',
                    'กกทราย', 'กกขนาก', 'ผักปราบ', 'ผักบุ้งนา',
                    'ใบแคบ', 'ใบกว้าง',
                ]
                for pattern in _WEED_PATTERNS_STAGE0:
                    if diacritics_match(query, pattern):
                        hints['weed_name'] = pattern
                        logger.info(f"  - Pre-extracted weed: '{pattern}'")
                        break

                # --- Nutrient Synonym Injection ---
                # "เร่งดอก" is PGR/Biostimulant, not "ปุ๋ย" in embeddings
                # Inject synonyms so vector search finds PGR/Biostimulant products
                if hints.get('problem_type') == 'nutrient':
                    _NUTRIENT_SYNONYM_MAP = {
                        'เร่งดอก': ['สารเร่งดอก', 'ฮอร์โมนพืช', 'PGR', 'บำรุงดอก'],
                        'เร่งผล': ['สารเร่งผล', 'ฮอร์โมนพืช', 'PGR', 'บำรุงผล'],
                        'บำรุง': ['สารบำรุงพืช', 'biostimulant', 'ธาตุอาหาร'],
                        'ติดดอก': ['สารเร่งดอก', 'ฮอร์โมนพืช', 'PGR'],
                        'ติดผล': ['สารเร่งผล', 'ฮอร์โมนพืช', 'PGR'],
                    }
                    nutrient_synonyms = set()
                    for pattern, synonyms in _NUTRIENT_SYNONYM_MAP.items():
                        if pattern in query:
                            nutrient_synonyms.update(synonyms)
                    if nutrient_synonyms:
                        hints['nutrient_synonyms'] = list(nutrient_synonyms)
                        logger.info(f"  - Nutrient synonyms injected: {hints['nutrient_synonyms']}")

                # --- Query Intent Pattern Detection ---
                _QUERY_INTENT_PATTERNS = {
                    'mixing': ['ผสมกันได้ไหม', 'ผสมกัน', 'ผสมร่วม', 'ใช้ร่วมกัน', 'ใช้ด้วยกัน', 'ฉีดพร้อมกัน', 'ผสมได้มั้ย', 'ผสมได้ไหม'],
                    'safety_period': ['เก็บเกี่ยวได้กี่วัน', 'หลังฉีดกี่วัน', 'ระยะปลอดภัย', 'เว้นกี่วัน', 'กี่วันถึงเก็บ', 'หยุดพ่นกี่วัน'],
                    'comparison': ['เปรียบเทียบ', 'ต่างกันยังไง', 'ต่างกันอย่างไร', 'ตัวไหนดีกว่า', 'เทียบกับ'],
                    'substitution': ['ใช้แทน', 'แทนกันได้ไหม', 'ทดแทน', 'เหมือนกันไหม'],
                }
                for _pattern_type, _patterns in _QUERY_INTENT_PATTERNS.items():
                    matched_pat = next((_pat for _pat in _patterns if _pat in query), None)
                    if matched_pat:
                        hints['query_intent'] = _pattern_type
                        logger.info(f"  - Query intent pattern: '{matched_pat}' → {_pattern_type}")
                        break

                # --- Number/Unit Extraction ---
                _NUM_UNIT_PATTERNS = [
                    (r'(\d+)\s*วัน', 'growth_stage_days'),
                    (r'(\d+)\s*ลิตร', 'sprayer_volume_liters'),
                    (r'(\d+)\s*ไร่', 'area_rai'),
                    (r'(\d+)\s*ซีซี', 'dosage_cc'),
                ]
                for _pattern, _entity_key in _NUM_UNIT_PATTERNS:
                    _match = re.search(_pattern, query)
                    if _match:
                        hints[_entity_key] = int(_match.group(1))
                        logger.info(f"  - Extracted {_entity_key}: {_match.group(1)}")

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
                    # IMPORTANT: Use exact match (all_detected_products from line ~135)
                    # NOT extract_product_name_from_question which includes fuzzy matching
                    # that causes false positives (e.g. "ทุเรียน" fuzzy→"รีโนเวท")
                    new_product_in_query = all_detected_products[0] if all_detected_products else None
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
                        # or about the product's properties ("กำจัดอะไร", "MoA", "สารออกฤทธิ์")
                        _FOLLOWUP_USAGE = [
                            'ใช้ยังไง', 'ใช้เท่าไหร่', 'ผสมกี่', 'ฉีดกี่', 'พ่นกี่',
                            'ผสมเท่าไหร่', 'อัตราเท่าไหร่', 'ใช้กี่', 'ราดกี่',
                            'ใช้ช่วงไหน', 'ใช้ตอนไหน', 'ใช้ได้กี่', 'ได้ผลไหม',
                            'ได้ช่วงไหน', 'ช่วงไหนได้', 'ใช้ได้ไหม', 'ใช้กับ',
                            'กลุ่มสาร', 'กลุ่มเคมี', 'irac', 'frac', 'hrac', 'rac', 'moa',
                            'ขนาดบรรจุ', 'กี่ลิตร', 'กี่กรัม', 'ขนาดไหน',
                            # Product capability / mechanism follow-ups
                            # "ไบเตอร์กำจัดอะไรได้บ้าง" / "อยู่กลุ่ม moa อะไร" / "สารออกฤทธิ์คืออะไร"
                            'กำจัดอะไร', 'ฆ่าอะไร', 'กำจัดได้', 'ฆ่าได้',
                            'ออกฤทธิ์', 'สารออกฤทธิ์', 'สารสำคัญ', 'active ingredient',
                        ]
                        _is_usage_followup = len(query.strip()) < 60 and any(p in query.lower() for p in _FOLLOWUP_USAGE)

                        # Keep if comparison follow-up ("ต่างกันยังไง", "แตกต่างกัน")
                        # User comparing previous products — product context MUST be preserved
                        _FOLLOWUP_COMPARE = [
                            'ต่างกัน', 'แตกต่าง', 'เปรียบเทียบ', 'อันไหนดี', 'ตัวไหนดี',
                            'อันไหนดีกว่า', 'ตัวไหนดีกว่า', 'ใช้ต่าง',
                        ]
                        _is_compare_followup = any(p in query for p in _FOLLOWUP_COMPARE)

                        if not _has_reference and not _is_usage_followup and not _is_compare_followup:
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
                        # Clear conversation state so stale product doesn't persist
                        if user_id:
                            try:
                                from app.services.cache import clear_conversation_state
                                await clear_conversation_state(user_id)
                                logger.info(f"  - Conversation state cleared (topic change)")
                            except Exception:
                                pass
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

                logger.info(f"  - Hints: {hints}")
            except ImportError:
                logger.warning("Could not import hint functions from chat.py")

            # =================================================================
            # Stage 1: Query Understanding + Pre-fetch embedding (parallel)
            # =================================================================
            # Start embedding the original query NOW while Agent 1 thinks
            # This saves ~1-2s because embedding doesn't need Agent 1's result
            prefetch_task = None
            if self.retrieval_agent and self.retrieval_agent.openai_client:
                prefetch_task = asyncio.create_task(
                    self.retrieval_agent._search_products(query, 10, None)
                )
                logger.info("  - Started parallel pre-fetch embedding for original query")

            # All queries go through Agent 1 LLM for accurate intent + expanded queries
            # Stage 0 hints are passed as [CONSTRAINT]/[HINT] to guide LLM
            query_analysis = await self.query_agent.analyze(query, context=context, hints=hints)

            # Inject possible_diseases from symptom mapping into entities for downstream use
            if hints.get('possible_diseases'):
                query_analysis.entities['possible_diseases'] = hints['possible_diseases']

            # Inject problem_type from Stage 0 for downstream category filtering
            if hints.get('problem_type') and hints['problem_type'] != 'unknown':
                query_analysis.entities['problem_type'] = hints['problem_type']

            # Handle greeting intent directly
            if query_analysis.intent == IntentType.GREETING:
                if prefetch_task:
                    prefetch_task.cancel()
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
                if prefetch_task:
                    prefetch_task.cancel()
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

            # Collect pre-fetched results (completed during Agent 1)
            prefetch_docs = []
            if prefetch_task:
                try:
                    prefetch_docs = await prefetch_task
                    if prefetch_docs:
                        logger.info(f"  - Pre-fetch completed: {len(prefetch_docs)} docs found during Agent 1")
                except Exception:
                    pass  # Pre-fetch failed, retrieval will handle it

            # =================================================================
            # Stage 2: Retrieval (with pre-fetched docs injected)
            # =================================================================
            retrieval_result = await self.retrieval_agent.retrieve(
                query_analysis=query_analysis,
                top_k=self.config.get('RETRIEVAL_TOP_K', 10),
                prefetch_docs=prefetch_docs,
                skip_rerank=False
            )

            # =================================================================
            # Stage 3: Create grounding result from retrieval
            # =================================================================
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


async def process_with_agentic_rag(
    query: str, context: str = "", user_id: str = None,
) -> AgenticRAGResponse:
    """
    Convenience function to process a query with the global AgenticRAG instance

    Args:
        query: User's question
        context: Optional conversation context
        user_id: Optional user ID (enables conversation state lookup)

    Returns:
        AgenticRAGResponse
    """
    rag = get_agentic_rag()
    return await rag.process(query, context, user_id=user_id)
