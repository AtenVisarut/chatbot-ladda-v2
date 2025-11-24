import logging
from app.services.services import openai_client
from app.services.memory import add_to_memory, get_conversation_context
from app.services.knowledge_base import answer_question_with_knowledge
from app.utils.text_processing import extract_keywords_from_question, post_process_answer
from app.services.product_recommendation import recommend_products_by_intent

logger = logging.getLogger(__name__)

async def handle_natural_conversation(user_id: str, message: str) -> str:
    """Handle natural conversation with context and intent detection"""
    try:
        # 1. Add user message to memory
        await add_to_memory(user_id, "user", message)
        
        # 2. Get conversation context
        context = await get_conversation_context(user_id)
        
        # 3. Analyze intent and keywords
        keywords = extract_keywords_from_question(message)
        
        # 4. Route based on intent
        if keywords["is_product_query"]:
            logger.info(f"Routing to product recommendation (Intent: {keywords.get('intent')})")
            answer = await recommend_products_by_intent(message, keywords)
            
            # Extract product names from the answer for analytics
            from app.services.services import analytics_tracker
            if analytics_tracker:
                # Simple extraction: find product names in numbered list (1. ProductName\n)
                import re
                product_pattern = r'\d+\.\s+([^\n]+?)(?:\n|$)'
                product_matches = re.findall(product_pattern, answer)
                # Clean product names (remove emoji and extra text)
                product_names = []
                for match in product_matches:
                    # Stop at first newline or special character like สารสำคัญ
                    clean_name = match.split('\n')[0].strip()
                    # Remove common prefixes
                    clean_name = clean_name.replace('ชื่อผลิตภัณฑ์:', '').strip()
                    if clean_name and len(clean_name) > 3:  # Avoid junk
                        product_names.append(clean_name)
                
                if product_names:
                    await analytics_tracker.track_product_recommendation(
                        user_id=user_id,
                        disease_name="Q&A",  # Indicate this came from Q&A
                        products=product_names[:5]  # Top 5 products
                    )
                    logger.info(f"Tracked {len(product_names)} products from Q&A")
            
            # Add assistant response to memory
            await add_to_memory(user_id, "assistant", answer)
            return answer
            
        elif keywords["pests"] or keywords["crops"]:
            logger.info("Routing to knowledge base (Agricultural query)")
            answer = await answer_question_with_knowledge(message, context)
            
            # Add assistant response to memory
            await add_to_memory(user_id, "assistant", answer)
            return answer
            
        else:
            logger.info("Routing to general chat")
            # General conversation with persona
            prompt = f"""คุณคือ "น้องลัดดา" ผู้ช่วยอัจฉริยะของ ICP Ladda
            
บุคลิก:
- ร่าเริง เป็นมิตร สุภาพ (ลงท้ายด้วย ค่ะ/นะคะ)
- มีความรู้เรื่องเกษตรประสบการณ์20ปี
- ชอบช่วยเหลือเกษตรกร
- ใช้ emoji ประกอบการสนทนา 🌿 😊

บริบทการสนทนา:
{context}

ข้อความล่าสุดจากผู้ใช้: {message}

ตอบกลับอย่างเป็นธรรมชาติ:"""

            response = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "คุณคือ 'น้องลัดดา' ผู้ช่วยอัจฉริยะของ ICP Ladda"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500
            )
            answer = post_process_answer(response.choices[0].message.content)
            
            # Add assistant response to memory
            await add_to_memory(user_id, "assistant", answer)
            return answer

    except Exception as e:
        logger.error(f"Error in natural conversation: {e}", exc_info=True)
        return "ขออภัยค่ะ น้องลัดดามึนหัวนิดหน่อย คุยเรื่องอื่นกันก่อนได้ไหมคะ 😅"
