"""
Response Generator Agent

Responsibilities:
- Synthesize final answer from grounded content
- Format citations for readability
- Add confidence indicators when needed
- Handle fallback responses when no data found
"""

import logging
from typing import Optional

from app.services.agents import (
    QueryAnalysis,
    RetrievalResult,
    GroundingResult,
    AgenticRAGResponse,
    IntentType
)
from app.utils.text_processing import post_process_answer

logger = logging.getLogger(__name__)

# Configuration
LOW_CONFIDENCE_THRESHOLD = 0.5
SHOW_CITATIONS = False  # Whether to show citation references in answer


class ResponseGeneratorAgent:
    """
    Agent 4: Response Generation
    Creates the final user-facing response
    """

    def __init__(self, openai_client=None):
        self.openai_client = openai_client

    async def generate(
        self,
        query_analysis: QueryAnalysis,
        retrieval_result: RetrievalResult,
        grounding_result: GroundingResult
    ) -> AgenticRAGResponse:
        """
        Generate final response from pipeline results

        Returns:
            AgenticRAGResponse with answer, citations, and metadata
        """
        try:
            logger.info(f"ResponseGeneratorAgent: Generating response")
            logger.info(f"  - Grounded: {grounding_result.is_grounded}")
            logger.info(f"  - Confidence: {grounding_result.confidence:.2f}")

            # Handle special intents
            if query_analysis.intent == IntentType.GREETING:
                return self._generate_greeting_response(query_analysis)

            # Handle no data case
            if not grounding_result.is_grounded and not retrieval_result.documents:
                return self._generate_no_data_response(query_analysis)

            # Get the grounded answer
            answer = grounding_result.suggested_answer

            # Post-process answer (remove markdown, emoji, etc.)
            answer = post_process_answer(answer)

            # Add low confidence indicator if needed
            if grounding_result.confidence < LOW_CONFIDENCE_THRESHOLD:
                answer = self._add_low_confidence_note(answer)

            # Add citation references if enabled
            if SHOW_CITATIONS and grounding_result.citations:
                answer = self._add_citation_references(answer, grounding_result)

            return AgenticRAGResponse(
                answer=answer,
                confidence=grounding_result.confidence,
                citations=grounding_result.citations,
                intent=query_analysis.intent,
                is_grounded=grounding_result.is_grounded,
                sources_used=retrieval_result.sources_used,
                query_analysis=query_analysis,
                retrieval_result=retrieval_result,
                grounding_result=grounding_result
            )

        except Exception as e:
            logger.error(f"ResponseGeneratorAgent error: {e}", exc_info=True)
            return AgenticRAGResponse(
                answer="ขออภัยค่ะ เกิดข้อผิดพลาดในการประมวลผล กรุณาลองใหม่อีกครั้งนะคะ",
                confidence=0.0,
                citations=[],
                intent=query_analysis.intent,
                is_grounded=False,
                sources_used=[]
            )

    def _generate_greeting_response(self, query_analysis: QueryAnalysis) -> AgenticRAGResponse:
        """Generate response for greeting intent"""
        greetings = [
            "สวัสดีค่ะ วันนี้สบายดีไหมคะ มีอะไรให้น้องลัดดาช่วยมั้ยคะ",
            "สวัสดีค่ะ น้องลัดดายินดีให้บริการค่ะ มีเรื่องอะไรสอบถามได้เลยค่ะ",
            "ดีค่ะ วันนี้มีเรื่องอะไรมาคุยกันคะ",
        ]

        import random
        answer = random.choice(greetings)

        return AgenticRAGResponse(
            answer=answer,
            confidence=1.0,
            citations=[],
            intent=IntentType.GREETING,
            is_grounded=True,
            sources_used=[]
        )

    def _generate_no_data_response(self, query_analysis: QueryAnalysis) -> AgenticRAGResponse:
        """Generate response when no relevant data found"""

        # Customize response based on intent
        if query_analysis.intent == IntentType.PRODUCT_INQUIRY:
            product = query_analysis.entities.get('product_name', 'สินค้านี้')
            answer = f"ขออภัยค่ะ ไม่พบข้อมูลเกี่ยวกับ \"{product}\" ในฐานข้อมูลค่ะ\n\nกรุณาตรวจสอบชื่อสินค้าอีกครั้ง หรือสอบถามเกี่ยวกับสินค้าอื่นได้เลยค่ะ"

        elif query_analysis.intent == IntentType.DISEASE_TREATMENT:
            disease = query_analysis.entities.get('disease_name', 'โรคนี้')
            plant = query_analysis.entities.get('plant_type', '')
            plant_text = f"ใน{plant}" if plant else ""
            answer = f"น้องลัดดาขอเช็คให้ก่อนนะคะ จากข้อมูลสินค้า ยังไม่พบตัวยาที่ระบุใช้กับ \"{disease}\" {plant_text}โดยตรงค่ะ\n\nรบกวนบอกเพิ่มหน่อยว่าเป็นพืชอะไร และอยู่ช่วงไหน (แตกใบอ่อน/ออกดอก/ติดผล) จะได้ค้นหาตัวที่เหมาะให้ตรงที่สุดนะคะ"

        elif query_analysis.intent == IntentType.PEST_CONTROL:
            pest = query_analysis.entities.get('pest_name', 'แมลงนี้')
            answer = f"น้องลัดดาขอเช็คให้ก่อนนะคะ จากข้อมูลสินค้า ยังไม่พบตัวยาที่ระบุใช้กำจัด \"{pest}\" โดยตรงค่ะ\n\nรบกวนบอกเพิ่มหน่อยว่าเป็นพืชอะไร จะได้ค้นหาตัวที่เหมาะให้ตรงที่สุดนะคะ"

        elif query_analysis.intent == IntentType.WEED_CONTROL:
            plant = query_analysis.entities.get('plant_type', '')
            if plant:
                answer = f"น้องลัดดาขอเช็คให้ก่อนนะคะ ยังไม่พบข้อมูลยากำจัดวัชพืชสำหรับ{plant}โดยตรงค่ะ\n\nรบกวนบอกเพิ่มหน่อยว่าเป็นวัชพืชประเภทไหน (ใบแคบ/ใบกว้าง/กก) จะได้แนะนำตัวที่เหมาะค่ะ"
            else:
                answer = "น้องลัดดาขอเช็คให้ก่อนนะคะ\n\nรบกวนบอกเพิ่มหน่อยว่า:\n- เป็นพืชอะไรคะ (เช่น ข้าว, ข้าวโพด)\n- วัชพืชประเภทไหน (ใบแคบ/ใบกว้าง/กก)\n\nจะได้แนะนำยากำจัดวัชพืชที่เหมาะสมค่ะ"

        elif query_analysis.intent == IntentType.USAGE_INSTRUCTION:
            answer = "ขอทราบรายละเอียดเพิ่มเติมค่ะ\n- ต้องการทราบข้อมูลของสินค้าตัวไหนคะ?\n- และใช้กับพืชอะไรคะ?\n\nเพื่อให้น้องลัดดาตอบได้ถูกต้องค่ะ"

        else:
            answer = "น้องลัดดาขอเช็คให้ก่อนนะคะ จากข้อมูลสินค้า ยังไม่พบข้อมูลที่ตรงกับคำถามโดยตรงค่ะ\n\nรบกวนบอกเพิ่มหน่อยว่า:\n- เป็นพืชอะไรคะ (เช่น ข้าว, ทุเรียน, มะม่วง)\n- ปัญหาที่พบ (เช่น โรค, แมลง, วัชพืช)\n\nจะได้ค้นหาตัวที่เหมาะให้ตรงที่สุดนะคะ"

        return AgenticRAGResponse(
            answer=answer,
            confidence=0.0,
            citations=[],
            intent=query_analysis.intent,
            is_grounded=False,
            sources_used=[]
        )

    def _add_low_confidence_note(self, answer: str) -> str:
        """Add note when confidence is low"""
        note = "\n\n(หมายเหตุ: คำตอบนี้อาจไม่ครบถ้วน หากต้องการข้อมูลเพิ่มเติม กรุณาระบุรายละเอียดเพิ่มค่ะ)"
        if note not in answer:
            answer += note
        return answer

    def _add_citation_references(self, answer: str, grounding_result: GroundingResult) -> str:
        """Add citation references at the end of answer"""
        if not grounding_result.citations:
            return answer

        citation_lines = ["\n\nอ้างอิง:"]
        for i, cit in enumerate(grounding_result.citations[:3], 1):
            citation_lines.append(f"[{i}] {cit.doc_title}")

        return answer + "\n".join(citation_lines)


async def format_response_for_intent(
    intent: IntentType,
    grounded_answer: str,
    entities: dict
) -> str:
    """
    Format the grounded answer based on intent type

    This ensures consistent formatting across different question types
    """

    # Already formatted by grounding agent, just return
    return grounded_answer
