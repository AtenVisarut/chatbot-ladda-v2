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
                from app.services.chat import extract_product_name_from_question, detect_problem_type
                detected_product = extract_product_name_from_question(query)
                if detected_product:
                    hints['product_name'] = detected_product
                detected_problem = detect_problem_type(query)
                if detected_problem != 'unknown':
                    hints['problem_type'] = detected_problem
                logger.info(f"  - Hints: {hints}")
            except ImportError:
                logger.warning("Could not import hint functions from chat.py")

            # =================================================================
            # Stage 1: Query Understanding
            # =================================================================
            query_analysis = await self.query_agent.analyze(query, context=context, hints=hints)

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
            if query_analysis.intent == IntentType.UNKNOWN and query_analysis.confidence < 0.3:
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

            # =================================================================
            # Stage 2: Retrieval
            # =================================================================
            retrieval_result = await self.retrieval_agent.retrieve(
                query_analysis=query_analysis,
                top_k=self.config.get('MIN_RELEVANT_DOCS', 5)
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
                grounding_result=grounding_result
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
