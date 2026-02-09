"""
Agentic RAG Orchestrator

Main entry point for the 4-agent RAG pipeline:
1. QueryUnderstandingAgent - Semantic intent detection, entity extraction
2. RetrievalAgent - Multi-query retrieval with re-ranking
3. GroundingAgent - Citation extraction, hallucination detection
4. ResponseGeneratorAgent - Answer synthesis with confidence scoring

Usage:
    from app.services.agentic_rag import AgenticRAG

    rag = AgenticRAG()
    response = await rag.process("โมเดิน ใช้กับทุเรียนได้ไหม")
    print(response.answer)
    print(f"Confidence: {response.confidence}")
    print(f"Citations: {len(response.citations)}")
"""

import logging
import time
from typing import Optional

from app.services.services import openai_client, supabase_client
from app.services.agents import (
    IntentType,
    QueryAnalysis,
    AgenticRAGResponse
)
from app.services.agents.query_understanding_agent import QueryUnderstandingAgent
from app.services.agents.retrieval_agent import RetrievalAgent
from app.services.agents.grounding_agent import GroundingAgent
from app.services.agents.response_generator_agent import ResponseGeneratorAgent
from app.config import AGENTIC_RAG_CONFIG

logger = logging.getLogger(__name__)


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
                from app.services.chat import (
                    extract_product_name_from_question, detect_problem_type,
                    ICP_PRODUCT_NAMES, extract_plant_type_from_question,
                    DISEASE_KEYWORDS, INSECT_KEYWORDS,
                    resolve_farmer_slang
                )
                from app.utils.text_processing import generate_thai_disease_variants, resolve_symptom_to_pathogens
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
                    # Strategy 0: Check [สินค้าที่กำลังคุยอยู่] marker FIRST (highest priority)
                    focus_match = re.search(r'\[สินค้าที่กำลังคุยอยู่\]\s*(\S+)', context)
                    if focus_match:
                        product_candidate = focus_match.group(1).strip()
                        if product_candidate in ICP_PRODUCT_NAMES:
                            detected_product = product_candidate
                            logger.info(f"  - Product from current focus marker: {detected_product}")

                    # Strategy 1: Fallback to bottom-up search (3 most recent msgs only)
                    if not detected_product:
                        context_lines = context.strip().split('\n')
                        msgs_checked = 0
                        for line in reversed(context_lines):
                            # Skip summary section lines
                            if line.startswith('[') and ']' in line:
                                continue
                            detected_product = extract_product_name_from_question(line)
                            if detected_product:
                                logger.info(f"  - Product from context (recent 3 msgs): {detected_product}")
                                break
                            msgs_checked += 1
                            if msgs_checked >= 3:
                                break

                    # Strategy 2: Fallback to [สินค้าที่แนะนำไปแล้ว] section
                    if not detected_product:
                        for line in context.split('\n'):
                            if 'สินค้าที่แนะนำ' in line:
                                for product_name in ICP_PRODUCT_NAMES.keys():
                                    if product_name in line:
                                        detected_product = product_name
                                        logger.info(f"  - Product from summary section: {detected_product}")
                                        break
                                break
                if detected_product:
                    hints['product_name'] = detected_product
                detected_problem = detect_problem_type(query)
                if detected_problem != 'unknown':
                    hints['problem_type'] = detected_problem

                # --- Pre-LLM Entity Extraction: Disease ---
                # (defined here so we can validate product vs disease below)
                _DISEASE_PATTERNS_STAGE0 = [
                    'แอนแทรคโนส', 'แอนแทคโนส', 'แอคแทคโนส',
                    'ฟิวซาเรียม', 'ฟิวสาเรียม', 'ฟูซาเรียม', 'ฟอซาเรียม',
                    'ไฟท็อปธอร่า', 'ไฟทอปธอร่า', 'ไฟท็อปโทร่า', 'ไฟธอปทอร่า', 'ไฟท็อป',
                    'ราน้ำค้าง', 'ราแป้ง', 'ราสนิม', 'ราสีชมพู', 'ราชมพู',
                    'ราดำ', 'ราเขียว', 'ราขาว', 'ราเทา',
                    'ใบไหม้แผลใหญ่', 'ใบไหม้', 'ใบจุดสีม่วง', 'ใบจุด',
                    'ผลเน่า', 'รากเน่า', 'โคนเน่า', 'ลำต้นเน่า', 'เน่าคอรวง',
                    'กาบใบแห้ง', 'ขอบใบแห้ง', 'เมล็ดด่าง', 'ใบขีดสีน้ำตาล',
                    'หอมเลื้อย', 'ใบติด', 'ใบด่าง', 'ใบหงิก', 'ดอกกระถิน',
                ]
                # Sort by length descending so longer patterns match first
                for pattern in sorted(_DISEASE_PATTERNS_STAGE0, key=len, reverse=True):
                    if pattern in query:
                        hints['disease_name'] = pattern
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
                    if pattern in query:
                        hints['pest_name'] = pattern
                        logger.info(f"  - Pre-extracted pest: '{pattern}'")
                        break

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
                            and hints.get('problem_type') in ('disease', 'pest')):
                        drop_reason = f"new {hints['problem_type']} topic, product from context"
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
                        is_followup = any(p in query for p in followup_patterns) and len(query) < 50
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
                from app.services.agents import GroundingResult
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
