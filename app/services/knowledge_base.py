import logging
import json
from typing import List, Dict, Optional
from app.services.services import supabase_client, openai_client
from app.services.cache import get_from_cache, set_to_cache
from app.utils.text_processing import clean_knowledge_text, post_process_answer

logger = logging.getLogger(__name__)

async def answer_question_with_knowledge(question: str, context: str = "") -> str:
    """Answer general questions using Knowledge Base (RAG)"""
    try:
        logger.info(f"Processing question: {question[:50]}...")
        
        # Check cache first
        cache_key = f"qa:{question}"
        # Use "knowledge" as cache type
        cached_answer = await get_from_cache("knowledge", cache_key)
        if cached_answer:
            logger.info("✓ Using cached answer")
            return cached_answer
        
        if not supabase_client:
            return "ขออภัยค่ะ ระบบฐานข้อมูลไม่พร้อมใช้งานในขณะนี้"
        
        relevant_docs = []
        
        # Strategy 1: Vector Search (using OpenAI Embeddings)
        if openai_client:
            try:
                # Generate embedding using OpenAI
                response = await openai_client.embeddings.create(
                    model="text-embedding-3-small",
                    input=question,
                    encoding_format="float"
                )
                query_embedding = response.data[0].embedding
                
                result = supabase_client.rpc(
                    'match_knowledge',
                    {
                        'query_embedding': query_embedding,
                        'match_threshold': 0.35,  # ลด threshold เพื่อให้ค้นหาปุ๋ยได้ดีขึ้น
                        'match_count': 5
                    }
                ).execute()
                
                if result.data:
                    relevant_docs.extend(result.data)
                    logger.info(f"✓ Found {len(result.data)} docs via vector search (OpenAI)")
            except Exception as e:
                logger.warning(f"Vector search failed: {e}")
        
        # Strategy 2: Keyword Search (Fallback/Supplement)
        if len(relevant_docs) < 3:
            try:
                # Extract keywords (simple split for now)
                keywords = [w for w in question.split() if len(w) > 3]
                
                for keyword in keywords[:3]:
                    result = supabase_client.table('knowledge')\
                        .select('content, category')\
                        .ilike('content', f'%{keyword}%')\
                        .limit(3)\
                        .execute()
                    
                    if result.data:
                        relevant_docs.extend(result.data)
                        logger.info(f"✓ Found {len(result.data)} docs via keyword: {keyword}")
            except Exception as e:
                logger.warning(f"Keyword search failed: {e}")
        
        # Deduplicate docs
        seen_content = set()
        unique_docs = []
        for doc in relevant_docs:
            content = doc.get('content', '')
            if content and content not in seen_content:
                seen_content.add(content)
                unique_docs.append(doc)
        
        # If no docs found, use OpenAI without context (General Knowledge)
        # แต่ห้ามแนะนำชื่อสินค้าเฉพาะ
        if not unique_docs:
            logger.info("No relevant docs found, using general knowledge")
            prompt = f"""คุณคือผู้เชี่ยวชาญด้านการเกษตรของไทย 20ปี

คำถาม: {question}

บริบทการสนทนา:
{context}

**ข้อกำหนดสำคัญ**:
1. ตอบคำถามอย่างกระชับ เป็นกันเอง และถูกต้องตามหลักวิชาการ
2. **ห้ามแนะนำชื่อผลิตภัณฑ์/ยา/สารเคมีเฉพาะเจาะจง** เช่น ทริสโซล, เบนโนมิล, ฟอสอีทิลอะลูมิเนียม เป็นต้น
3. ถ้าถามเรื่องสินค้า/ผลิตภัณฑ์ → บอกให้พิมพ์ "ดูผลิตภัณฑ์" เพื่อดูแคตตาล็อกสินค้า ICP Ladda
4. แนะนำได้เฉพาะ **ประเภทของสาร** เช่น "ยาฆ่าเชื้อรา", "ยาฆ่าแมลง" แต่ห้ามระบุชื่อสินค้า
5. แนะนำวิธีการทั่วไป เช่น การตัดแต่งกิ่ง, การจัดการน้ำ, การใช้ปุ๋ย

ตอบคำถาม:"""

            if openai_client:
                response = await openai_client.chat.completions.create(
                    model="gpt-4o-mini",  # Text-only queries use cheaper model
                    messages=[
                        {"role": "system", "content": "คุณคือผู้เชี่ยวชาญด้านการเกษตร ห้ามแนะนำชื่อสินค้าหรือยาเฉพาะเจาะจง เพราะอาจไม่ตรงกับสินค้าในระบบ"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.5
                )
                answer = post_process_answer(response.choices[0].message.content)
            else:
                answer = "ขออภัยค่ะ ระบบ AI ไม่พร้อมใช้งานในขณะนี้"

            # Cache result
            # Use "knowledge" as cache type
            await set_to_cache("knowledge", cache_key, answer)
            return answer
        
        # Build context from docs
        knowledge_context = ""
        for idx, doc in enumerate(unique_docs[:5], 1):
            cleaned_content = clean_knowledge_text(doc.get('content', ''))
            knowledge_context += f"\n[เอกสาร {idx}] {doc.get('title', '')}: {cleaned_content}\n"
        
        # Generate answer with RAG
        prompt = f"""คุณคือ "น้องลัดดา" ผู้เชี่ยวชาญด้านการเกษตรของ ICP Ladda

คำถาม: {question}

ข้อมูลอ้างอิง:
{knowledge_context}

**รูปแบบการตอบ** (สำคัญมาก):
- ตอบสั้นกระชับ ไม่เกิน 5-6 บรรทัด
- แนะนำสินค้าแค่ 2-3 ตัวเลือกที่ดีที่สุด
- แต่ละตัวเลือกขึ้นบรรทัดใหม่
- ใช้รูปแบบนี้:

[ชื่อสินค้า]
• ประโยชน์: ...
• อัตราใช้: ...

- ลงท้ายด้วยคำแนะนำสั้นๆ
- ใช้ภาษาเป็นกันเอง ไม่ต้องใส่ emoji
- ห้ามใช้ markdown (**, ##, ```)

ตอบ:"""

        if openai_client:
            response = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "คุณคือน้องลัดดา ตอบสั้นกระชับ แนะนำแค่ 2-3 ตัวเลือก แต่ละตัวขึ้นบรรทัดใหม่ ห้ามใช้ markdown"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=400,
                temperature=0.5
            )
            answer = post_process_answer(response.choices[0].message.content)
        else:
            answer = "ขออภัยค่ะ ระบบ AI ไม่พร้อมใช้งานในขณะนี้"
        
        # Cache result
        # Use "knowledge" as cache type
        await set_to_cache("knowledge", cache_key, answer)
        
        return answer

    except Exception as e:
        logger.error(f"Error answering question: {e}", exc_info=True)
        return "ขออภัยค่ะ เกิดข้อผิดพลาดในการประมวลผลคำถาม กรุณาลองใหม่อีกครั้งนะคะ"

