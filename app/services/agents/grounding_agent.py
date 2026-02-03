"""
Grounding Agent

Responsibilities:
- Verify that answer is grounded in retrieved documents
- Extract citations from documents
- Detect hallucinated/ungrounded claims
- Generate grounded answer when needed
"""

import logging
import json
import re
from typing import List, Dict

from app.services.agents import (
    RetrievedDocument,
    RetrievalResult,
    Citation,
    GroundingResult,
    QueryAnalysis,
    IntentType
)

logger = logging.getLogger(__name__)

# Configuration
MIN_GROUNDING_CONFIDENCE = 0.5
MAX_CITATIONS = 3


class GroundingAgent:
    """
    Agent 3: Grounding
    Ensures answers are grounded in retrieved knowledge
    """

    def __init__(self, openai_client=None):
        self.openai_client = openai_client

    async def ground(
        self,
        query_analysis: QueryAnalysis,
        retrieval_result: RetrievalResult,
        draft_answer: str = None
    ) -> GroundingResult:
        """
        Ground the answer in retrieved documents

        If draft_answer is provided, verify it against documents.
        Otherwise, generate a grounded answer from documents.

        Returns:
            GroundingResult with citations and grounding status
        """
        try:
            logger.info(f"GroundingAgent: Processing {len(retrieval_result.documents)} documents")

            # If no documents, cannot ground
            if not retrieval_result.documents:
                return GroundingResult(
                    is_grounded=False,
                    confidence=0.0,
                    citations=[],
                    ungrounded_claims=["ไม่พบข้อมูลในฐานข้อมูล"],
                    suggested_answer="ขออภัยค่ะ ไม่พบข้อมูลที่เกี่ยวข้องในฐานข้อมูลค่ะ",
                    grounding_notes="No documents retrieved"
                )

            # Extract key information from documents
            doc_summaries = self._extract_document_info(retrieval_result.documents)

            # Generate grounded answer using LLM
            if self.openai_client:
                result = await self._llm_ground(
                    query_analysis,
                    retrieval_result.documents,
                    doc_summaries,
                    draft_answer
                )
                return result
            else:
                # Fallback: use documents directly
                return self._fallback_ground(retrieval_result.documents, query_analysis)

        except Exception as e:
            logger.error(f"GroundingAgent error: {e}", exc_info=True)
            return GroundingResult(
                is_grounded=False,
                confidence=0.0,
                citations=[],
                ungrounded_claims=[str(e)],
                suggested_answer="ขออภัยค่ะ เกิดข้อผิดพลาดในการประมวลผล",
                grounding_notes=f"Error: {str(e)}"
            )

    def _extract_document_info(self, docs: List[RetrievedDocument]) -> List[Dict]:
        """Extract key information from documents for grounding"""
        summaries = []
        for doc in docs[:10]:  # Limit to top 10
            summary = {
                'id': doc.id,
                'title': doc.title,
                'source': doc.source,
                'content': doc.content[:300],
                'product_name': doc.metadata.get('product_name'),
                'chemical_name': doc.metadata.get('chemical_name'),
                'usage_rate': doc.metadata.get('usage_rate'),
                'target_pest': doc.metadata.get('target_pest'),
                'category': doc.metadata.get('category'),
            }
            summaries.append(summary)
        return summaries

    async def _llm_ground(
        self,
        query_analysis: QueryAnalysis,
        docs: List[RetrievedDocument],
        doc_summaries: List[Dict],
        draft_answer: str = None
    ) -> GroundingResult:
        """Use LLM to verify/generate grounded answer"""

        # Build context from documents
        context_parts = []
        for i, summary in enumerate(doc_summaries, 1):
            part = f"[เอกสาร {i}]\n"
            part += f"หัวข้อ: {summary['title']}\n"
            if summary.get('product_name'):
                part += f"สินค้า: {summary['product_name']}"
                if summary.get('chemical_name'):
                    part += f" (สารสำคัญ: {summary['chemical_name']})"
                part += "\n"
            if summary.get('usage_rate'):
                part += f"อัตราใช้: {summary['usage_rate']}\n"
            if summary.get('target_pest'):
                target = str(summary['target_pest'])[:150]
                part += f"ใช้กำจัด: {target}\n"
            if summary.get('content'):
                part += f"เนื้อหา: {summary['content']}\n"
            context_parts.append(part)

        context = "\n".join(context_parts)

        # Build allowed products list
        allowed_products = []
        for summary in doc_summaries:
            if summary.get('product_name'):
                allowed_products.append(summary['product_name'])
        allowed_products_str = ", ".join(set(allowed_products)) if allowed_products else "(ไม่มี)"

        prompt = f"""วิเคราะห์และสร้างคำตอบที่ grounded จากข้อมูลในฐานข้อมูลเท่านั้น

คำถาม: "{query_analysis.original_query}"
Intent: {query_analysis.intent.value}
Entities: {json.dumps(query_analysis.entities, ensure_ascii=False)}

ข้อมูลจากฐานข้อมูล:
{context}

สินค้าที่อนุญาตให้แนะนำ: [{allowed_products_str}]

ตอบเป็น JSON (ไม่มี markdown):
{{
    "is_grounded": true/false,
    "confidence": 0.0-1.0,
    "citations": [
        {{"doc_id": "X", "title": "...", "quoted_text": "ข้อความที่อ้างอิง"}}
    ],
    "ungrounded_claims": ["claim ที่ไม่มีในฐานข้อมูล"],
    "answer": "คำตอบที่ grounded จากข้อมูลเท่านั้น"
}}

กฎเหล็ก:
1. ห้ามแต่งข้อมูลเด็ดขาด - ใช้เฉพาะข้อมูลจากฐานข้อมูลที่ให้มา
2. แนะนำได้เฉพาะสินค้าในรายการ [{allowed_products_str}] เท่านั้น
3. ถ้าไม่มีข้อมูลเพียงพอ → is_grounded=false และ answer="ไม่พบข้อมูล..."
4. ต้องมี citations อย่างน้อย 1 รายการถ้า is_grounded=true
5. อัตราการใช้ต้องมาจากฐานข้อมูลโดยตรง ห้ามคำนวณเอง
6. ชื่อสินค้าต้องแสดงในรูปแบบ "ชื่อสินค้า (สารสำคัญ)" เช่น "โมเดิน 50 (โปรฟีโนฟอส)"

รูปแบบคำตอบ:
- เริ่มด้วย "จากข้อมูลสินค้า" หรือ "จากข้อมูลในฐานข้อมูล"
- ห้ามใช้ ** หรือ ##
- ใช้ emoji นำหน้าหัวข้อ เช่น 🦠 🌿 💊 📋 ⚖️ 📅 ⚠️ 💡
- ใช้ ━━━━━━━━━━━━━━━ คั่นระหว่างส่วนหลักๆ
- ปิดท้ายด้วย "ถ้าบอกขนาดถังพ่น น้องลัดดาช่วยคำนวณอัตราให้ได้ค่ะ" (ถ้าเป็นคำถามเรื่องสินค้า)"""

        response = await self.openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "คุณคือระบบตรวจสอบความถูกต้องของคำตอบ ตอบเป็น JSON เท่านั้น ห้ามแต่งข้อมูล"
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=800
        )

        response_text = response.choices[0].message.content.strip()

        try:
            # Remove markdown if present
            if response_text.startswith("```"):
                response_text = re.sub(r'^```(?:json)?\n?', '', response_text)
                response_text = re.sub(r'\n?```$', '', response_text)

            data = json.loads(response_text)

            # Build citations
            citations = []
            for cit in data.get("citations", [])[:MAX_CITATIONS]:
                citations.append(Citation(
                    doc_id=str(cit.get("doc_id", "")),
                    doc_title=cit.get("title", ""),
                    source="products",
                    quoted_text=cit.get("quoted_text", ""),
                    confidence=data.get("confidence", 0.5)
                ))

            return GroundingResult(
                is_grounded=data.get("is_grounded", False),
                confidence=float(data.get("confidence", 0.5)),
                citations=citations,
                ungrounded_claims=data.get("ungrounded_claims", []),
                suggested_answer=data.get("answer", ""),
                grounding_notes=f"LLM grounding with {len(doc_summaries)} docs"
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse grounding response: {e}")
            return self._fallback_ground(docs, query_analysis)

    def _fallback_ground(
        self,
        docs: List[RetrievedDocument],
        query_analysis: QueryAnalysis
    ) -> GroundingResult:
        """Fallback grounding without LLM"""
        if not docs:
            return GroundingResult(
                is_grounded=False,
                confidence=0.0,
                citations=[],
                ungrounded_claims=["ไม่พบข้อมูล"],
                suggested_answer="ขออภัยค่ะ ไม่พบข้อมูลในฐานข้อมูล",
                grounding_notes="Fallback: no documents"
            )

        # Build answer from top documents
        top_doc = docs[0]
        answer_parts = ["จากข้อมูลในฐานข้อมูล:\n"]

        for i, doc in enumerate(docs[:3], 1):
            product_name = doc.metadata.get('product_name') or doc.title
            chemical = doc.metadata.get('chemical_name')
            if chemical:
                product_name = f"{product_name} ({chemical})"

            answer_parts.append(f"{i}. {product_name}")

            if doc.metadata.get('target_pest'):
                answer_parts.append(f"   - ใช้กำจัด: {str(doc.metadata['target_pest'])[:100]}")
            if doc.metadata.get('usage_rate'):
                answer_parts.append(f"   - อัตราใช้: {doc.metadata['usage_rate']}")
            answer_parts.append("")

        answer_parts.append("\nถ้าบอกขนาดถังพ่น น้องลัดดาช่วยคำนวณอัตราให้ได้ค่ะ")

        # Build citations
        citations = []
        for doc in docs[:MAX_CITATIONS]:
            citations.append(Citation(
                doc_id=doc.id,
                doc_title=doc.title,
                source=doc.source,
                quoted_text=doc.content[:100],
                confidence=doc.similarity_score
            ))

        avg_score = sum(d.similarity_score for d in docs[:3]) / min(3, len(docs))

        return GroundingResult(
            is_grounded=avg_score >= MIN_GROUNDING_CONFIDENCE,
            confidence=avg_score,
            citations=citations,
            ungrounded_claims=[],
            suggested_answer="\n".join(answer_parts),
            grounding_notes="Fallback grounding"
        )
