"""
Response Generator Agent

Responsibilities:
- Synthesize final answer from grounded/verified product data
- Generate formatted response using LLM with "น้องลัดดา" persona
- Format citations for readability
- Add confidence indicators when needed
- Handle fallback responses when no data found
"""

import logging
import json

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


class ResponseGeneratorAgent:
    """
    Agent 4: Response Generation
    Creates the final user-facing response using LLM with verified product data
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
        Generate final response from pipeline results using LLM

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

            # Generate answer from verified product data using LLM
            answer = await self._generate_llm_response(
                query_analysis, retrieval_result, grounding_result
            )

            # Post-process answer (remove markdown artifacts)
            answer = post_process_answer(answer)

            # Add low confidence indicator if needed
            if grounding_result.confidence < LOW_CONFIDENCE_THRESHOLD:
                answer = self._add_low_confidence_note(answer)

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

    async def _generate_llm_response(
        self,
        query_analysis: QueryAnalysis,
        retrieval_result: RetrievalResult,
        grounding_result: GroundingResult
    ) -> str:
        """Generate formatted response using LLM with verified product data"""

        if not self.openai_client:
            return self._build_fallback_answer(retrieval_result, grounding_result)

        # Build product data context from retrieval results
        product_context_parts = []
        for i, doc in enumerate(retrieval_result.documents[:5], 1):
            meta = doc.metadata
            part = f"[สินค้า {i}] {meta.get('product_name', doc.title)}"
            if meta.get('active_ingredient'):
                part += f" (สารสำคัญ: {meta['active_ingredient']})"
            part += "\n"
            if meta.get('category'):
                part += f"  ประเภท: {meta['category']}\n"
            if meta.get('target_pest'):
                part += f"  ใช้กำจัด: {str(meta['target_pest'])[:200]}\n"
            if meta.get('applicable_crops'):
                part += f"  พืชที่ใช้ได้: {str(meta['applicable_crops'])[:200]}\n"
            if meta.get('usage_rate'):
                part += f"  อัตราใช้: {meta['usage_rate']}\n"
            if meta.get('how_to_use'):
                part += f"  วิธีใช้: {str(meta['how_to_use'])[:200]}\n"
            if meta.get('usage_period'):
                part += f"  ช่วงการใช้: {str(meta['usage_period'])[:150]}\n"
            product_context_parts.append(part)

        product_context = "\n".join(product_context_parts)

        # Relevant products from grounding
        relevant = grounding_result.relevant_products
        relevant_str = ", ".join(relevant) if relevant else "(ทั้งหมดที่ค้นพบ)"

        prompt = f"""คำถาม: "{query_analysis.original_query}"
Intent: {query_analysis.intent.value}
Entities: {json.dumps(query_analysis.entities, ensure_ascii=False)}

ข้อมูลสินค้าที่ผ่านการตรวจสอบแล้ว:
{product_context}

สินค้าที่เกี่ยวข้องกับคำถาม: [{relevant_str}]

สร้างคำตอบจากข้อมูลด้านบนเท่านั้น"""

        system_prompt = """คุณคือ "น้องลัดดา" ผู้เชี่ยวชาญด้านการเกษตรของ ICP Ladda

กฎเหล็ก:
1. ห้ามแต่งข้อมูลเด็ดขาด - ใช้เฉพาะข้อมูลจากฐานข้อมูลที่ให้มา
2. แนะนำได้เฉพาะสินค้าที่อยู่ใน "สินค้าที่เกี่ยวข้องกับคำถาม" เท่านั้น
3. อัตราการใช้ต้องมาจากข้อมูลโดยตรง ห้ามคำนวณเอง
4. ชื่อสินค้าต้องแสดง "ชื่อสินค้า (สารสำคัญ)" เช่น "โมเดิน 50 (โปรฟีโนฟอส)"

รูปแบบคำตอบ:
- เริ่มด้วย "จากข้อมูลสินค้า" + คำอธิบาย
- ใช้ emoji นำหน้าหัวข้อ: 🦠 🌿 💊 📋 ⚖️ 📅 ⚠️ 💡
- ใช้ ━━━━━━━━━━━━━━━ คั่นส่วนหลักๆ
- ห้ามใช้ ** หรือ ##
- ถ้าเป็นวัชพืช → จัดกลุ่ม: ก่อนวัชพืชงอก / หลังวัชพืชงอก
- ถ้าเป็นแมลง/โรค → ระบุ: อัตราใช้, วิธีใช้, ช่วงใช้
- ปิดท้ายด้วย "ถ้าบอกขนาดถังพ่น น้องลัดดาช่วยคำนวณอัตราให้ได้ค่ะ" (ถ้าเป็นคำถามเรื่องสินค้า)
- ตอบกระชับ ตรงประเด็น"""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=700
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"LLM response generation failed: {e}")
            return self._build_fallback_answer(retrieval_result, grounding_result)

    def _build_fallback_answer(
        self,
        retrieval_result: RetrievalResult,
        grounding_result: GroundingResult
    ) -> str:
        """Build answer without LLM from raw product data"""
        if not retrieval_result.documents:
            return "ขออภัยค่ะ ไม่พบข้อมูลในฐานข้อมูลค่ะ"

        parts = ["จากข้อมูลในฐานข้อมูล:\n"]
        for i, doc in enumerate(retrieval_result.documents[:3], 1):
            meta = doc.metadata
            name = meta.get('product_name') or doc.title
            ingredient = meta.get('active_ingredient')
            if ingredient:
                name = f"{name} ({ingredient})"
            parts.append(f"{i}. {name}")
            if meta.get('target_pest'):
                parts.append(f"   - ใช้กำจัด: {str(meta['target_pest'])[:100]}")
            if meta.get('usage_rate'):
                parts.append(f"   - อัตราใช้: {meta['usage_rate']}")
            parts.append("")

        parts.append("\nถ้าบอกขนาดถังพ่น น้องลัดดาช่วยคำนวณอัตราให้ได้ค่ะ")
        return "\n".join(parts)

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

