import logging
import json
from typing import List, Dict
from app.models import DiseaseDetectionResult, ProductRecommendation
from app.services.services import supabase_client, e5_model, openai_client
import logging
import json
from typing import List, Dict
from app.models import DiseaseDetectionResult, ProductRecommendation
from app.services.services import supabase_client, openai_client
from app.services.cache import get_from_cache, set_to_cache
from app.utils.text_processing import extract_keywords_from_question

logger = logging.getLogger(__name__)

async def retrieve_product_recommendation(disease_info: DiseaseDetectionResult) -> List[ProductRecommendation]:
    """
    Query products using Vector Search + Gemini filtering
    Returns top 3-5 most relevant products
    """
    try:
        logger.info("🔍 Retrieving products with Vector Search + Gemini Filter")

        if not supabase_client:
            logger.warning("Supabase not configured")
            return []

        disease_name = disease_info.disease_name
        logger.info(f"📝 Searching products for: {disease_name}")
        
        # Check cache first
        cache_key = f"products:{disease_name}"
        # Use "products" as cache type
        cached_products = await get_from_cache("products", cache_key)
        if cached_products:
            logger.info("✓ Using cached product recommendations")
            return [ProductRecommendation(**p) for p in cached_products]
        
        # Strategy 1: Vector search by disease name (most accurate)
        try:
            if openai_client:
                # Generate embedding for disease name using OpenAI
                response = await openai_client.embeddings.create(
                    model="text-embedding-3-small",
                    input=disease_name,
                    encoding_format="float"
                )
                query_embedding = response.data[0].embedding
                logger.info("✓ Product query embedding generated (OpenAI)")
                
                # Vector search in products table
                result = supabase_client.rpc(
                    'match_products',
                    {
                        'query_embedding': query_embedding,
                        'match_threshold': 0.3,  # Lower threshold for more candidates
                        'match_count': 15  # Get more candidates
                    }
                ).execute()
                
                if result.data and len(result.data) > 0:
                    logger.info(f"✓ Found {len(result.data)} product candidates via vector search")
                    
                    # Use similarity scores directly (NO AI filtering - saves ~100 tokens)
                    # Filter by similarity threshold
                    filtered_data = [
                        p for p in result.data 
                        if p.get('similarity', 0) > 0.4
                    ][:6]  # Top 6 candidates
                    
                    if filtered_data:
                        logger.info(f"✓ Filtered {len(filtered_data)} products by similarity (no AI)")
                        filtered_products = build_recommendations_from_data(filtered_data)
                        
                        # Cache the results
                        if filtered_products:
                            # Use "products" as cache type
                            await set_to_cache("products", cache_key, [r.dict() for r in filtered_products])
                        
                        return filtered_products
                    else:
                        logger.warning("⚠️ No products passed similarity threshold, using top vector results")
                        # Fallback: use top vector search results
                        return build_recommendations_from_data(result.data[:6])
                else:
                    logger.info("No products found via vector search, trying keyword search")
            else:
                logger.warning("OpenAI client not available, using keyword search")
        except Exception as e:
            logger.warning(f"Vector search failed: {e}, trying keyword search")
        
        # Strategy 2: Keyword search fallback
        matches_data = []
        
        # Search in target_pest field
        try:
            result = supabase_client.table('products')\
                .select('*')\
                .ilike('target_pest', f'%{disease_name}%')\
                .limit(10)\
                .execute()
            
            if result.data:
                matches_data.extend(result.data)
                logger.info(f"Found {len(result.data)} products in target_pest")
        except Exception as e:
            logger.warning(f"target_pest search failed: {e}")
        
        # If no results, search by pest type
        if not matches_data:
            try:
                pest_keywords = []
                if "เชื้อรา" in disease_info.raw_analysis:
                    pest_keywords = ["เชื้อรา", "โรคพืช"]
                elif "ไวรัส" in disease_info.raw_analysis:
                    pest_keywords = ["ไวรัส"]
                elif "ศัตรูพืช" in disease_info.raw_analysis or "แมลง" in disease_info.raw_analysis:
                    pest_keywords = ["แมลง", "ศัตรูพืช", "เพลี้ย"]
                elif "วัชพืช" in disease_info.raw_analysis:
                    pest_keywords = ["วัชพืช", "หญ้า"]
                
                for keyword in pest_keywords:
                    result = supabase_client.table('products')\
                        .select('*')\
                        .ilike('target_pest', f'%{keyword}%')\
                        .limit(5)\
                        .execute()
                    
                    if result.data:
                        matches_data.extend(result.data)
                        logger.info(f"Found {len(result.data)} products for keyword: {keyword}")
                        break
                        
            except Exception as e:
                logger.warning(f"Keyword search failed: {e}")
        
        if not matches_data:
            logger.warning("No products found with any search strategy")
            return []
        
        logger.info(f"Total products found: {len(matches_data)}")
        recommendations = build_recommendations_from_data(matches_data[:6])
        
        # Cache the results
        if recommendations:
            # Use "products" as cache type
            await set_to_cache("products", cache_key, [r.dict() for r in recommendations])
        
        return recommendations

    except Exception as e:
        logger.error(f"Product search failed: {e}", exc_info=True)
        return []


def build_recommendations_from_data(products_data: List[Dict]) -> List[ProductRecommendation]:
    """Build ProductRecommendation list from raw data"""
    recommendations = []
    seen_products = set()
    
    for product in products_data:
        pname = product.get("product_name", "ไม่ระบุชื่อ")
        
        if pname in seen_products:
            continue
        seen_products.add(pname)
        
        pest = product.get("target_pest", "")
        if not pest or pest.strip() == "":
            continue
        
        rec = ProductRecommendation(
            product_name=pname,
            active_ingredient=product.get("active_ingredient", ""),
            target_pest=pest,
            applicable_crops=product.get("applicable_crops", ""),
            how_to_use=product.get("how_to_use", ""),
            usage_period=product.get("usage_period", ""),
            usage_rate=product.get("usage_rate", ""),
            link_product=product.get("link_product", ""),
            score=product.get("similarity", 0.7)
        )
        recommendations.append(rec)
    
    return recommendations

async def recommend_products_by_intent(question: str, keywords: dict) -> str:
    """แนะนำผลิตภัณฑ์ตาม intent ของผู้ใช้ (เพิ่มผลผลิต, แก้ปัญหา, ฯลฯ)"""
    try:
        intent = keywords.get('intent')
        logger.info(f"🎯 Intent-based recommendation: {intent}")
        logger.info(f"📝 Keywords: crops={keywords.get('crops')}, pests={keywords.get('pests')}")
        
        if not supabase_client:
            logger.error("❌ Supabase client not available")
            return await answer_product_question(question, keywords)
        
        if not openai_client:
            logger.error("❌ OpenAI client not available")
            return await answer_product_question(question, keywords)
        
        intent = keywords.get("intent")
        crops = keywords.get("crops", [])
        pests = keywords.get("pests", [])
        
        # Build search query based on intent
        search_queries = []
        
        if intent == "increase_yield":
            # เพิ่มผลผลิต
            if crops:
                for crop in crops[:2]:
                    search_queries.append(f"เพิ่มผลผลิต {crop}")
                    search_queries.append(f"ปุ๋ยบำรุง {crop}")
                    search_queries.append(f"ฮอร์โมน {crop}")
                    # English variants for English crop names
                    if any(c.isalpha() for c in crop):
                        search_queries.append(f"increase yield {crop}")
                        search_queries.append(f"fertilizer for {crop}")
                        search_queries.append(f"plant hormone {crop}")
            else:
                search_queries.append("เพิ่มผลผลิต ปุ๋ย ฮอร์โมน")
        
        elif intent == "solve_problem":
            # แก้ปัญหาศัตรูพืช
            if pests and crops:
                for pest in pests[:2]:
                    for crop in crops[:2]:
                        search_queries.append(f"กำจัด {pest} {crop}")
                        # English variants
                        if any(c.isalpha() for c in crop) or any(c.isalpha() for c in pest):
                            search_queries.append(f"control {pest} {crop}")
                            search_queries.append(f"manage {pest} on {crop}")
            elif pests:
                for pest in pests[:2]:
                    search_queries.append(f"กำจัด {pest}")
                    if any(c.isalpha() for c in pest):
                        search_queries.append(f"control {pest}")
            elif crops:
                for crop in crops[:2]:
                    search_queries.append(f"ป้องกันโรค {crop}")
                    if any(c.isalpha() for c in crop):
                        search_queries.append(f"prevent disease {crop}")
        
        elif intent == "general_care":
            # ดูแลทั่วไป
            if crops:
                for crop in crops[:2]:
                    search_queries.append(f"ดูแล {crop}")
                    search_queries.append(f"บำรุง {crop}")
        
        else:
            # Default: product inquiry
            if crops:
                search_queries.append(f"ผลิตภัณฑ์ {crops[0]}")
            if pests:
                search_queries.append(f"กำจัด {pests[0]}")
        
        # Vector search for each query
        all_products = []
        logger.info(f"🔍 Searching with {len(search_queries)} queries: {search_queries[:3]}")
        
        for query in search_queries[:3]:  # Top 3 queries
            try:
                logger.info(f"   → Query: '{query}'")
                
                # Generate embedding using OpenAI
                response = await openai_client.embeddings.create(
                    model="text-embedding-3-small",
                    input=query,
                    encoding_format="float"
                )
                query_embedding = response.data[0].embedding
                
                result = supabase_client.rpc(
                    'match_products',
                    {
                        'query_embedding': query_embedding,
                        'match_threshold': 0.25,  # Lower threshold for more results
                        'match_count': 10
                    }
                ).execute()
                
                if result.data:
                    all_products.extend(result.data)
                    logger.info(f"   ✓ Found {len(result.data)} products")
                else:
                    logger.warning(f"   ⚠️ No products found")
            except Exception as e:
                logger.error(f"   ❌ Vector search failed: {e}", exc_info=True)
        
        # Remove duplicates
        seen = set()
        unique_products = []
        for p in all_products:
            pname = p.get('product_name', '')
            if pname and pname not in seen:
                seen.add(pname)
                unique_products.append(p)
        
        logger.info(f"📦 Total products: {len(all_products)}, Unique: {len(unique_products)}")
        
        if not unique_products:
            # Fallback to keyword search
            logger.warning("⚠️ No products from vector search, trying keyword search")
            return await answer_product_question(question, keywords)
        
        # Log product names
        product_names = [p.get('product_name', 'N/A') for p in unique_products[:5]]
        logger.info(f"📋 Top products: {', '.join(product_names)}")
        
        # Use Gemini to filter and create natural response
        products_text = ""
        for idx, p in enumerate(unique_products[:15], 1):  # Top 15 for Gemini
            products_text += f"\n[{idx}] {p.get('product_name', 'N/A')}"
            products_text += f"\n    • สารสำคัญ: {p.get('active_ingredient', 'N/A')}"
            products_text += f"\n    • ศัตรูพืชที่กำจัดได้: {p.get('target_pest', 'N/A')[:150]}"
            products_text += f"\n    • วิธีใช้: {p.get('how_to_use', 'N/A')[:200]}"
            products_text += f"\n    • อัตราการใช้: {p.get('usage_rate', 'N/A')}"
            if p.get('usage_period'):
                products_text += f"\n    • ช่วงการใช้: {p.get('usage_period')}"
            products_text += f"\n    • ใช้กับพืช: {p.get('applicable_crops', 'N/A')[:100]}"
            products_text += f"\n    • Similarity: {p.get('similarity', 0):.0%}\n"
        
        # Create intent-specific prompt
        if intent == "increase_yield":
            prompt = f"""คุณคือผู้ช่วยแนะนำผลิตภัณฑ์จาก ICP Ladda

คำถามจากเกษตรกร: {question}

ผลิตภัณฑ์ที่มีในระบบ (ห้ามแนะนำนอกจากนี้):
{products_text}

🚨 **กฎที่ห้ามละเมิด**:
1. ใช้เฉพาะผลิตภัณฑ์จากรายการข้างต้นเท่านั้น
2.  ห้ามสร้างชื่อผลิตภัณฑ์ใหม่
3. ห้ามแนะนำผลิตภัณฑ์ที่ไม่ได้อยู่ในรายการ
4. ถ้าไม่มีผลิตภัณฑ์ที่เหมาะสม ให้บอกตรงๆว่า "ไม่พบผลิตภัณฑ์ที่เหมาะสมในระบบ"

📋 **วิธีตอบ**:
1. เลือก 3-5 ผลิตภัณฑ์จากรายการข้างต้น
2. ใช้ชื่อผลิตภัณฑ์ตามที่ระบุในรายการเท่านั้น
3. คัดลอกรายละเอียดจากรายการโดยตรง ห้ามแต่งเติม
4. แสดงข้อมูลครบถ้วนตามนี้:
   - ชื่อผลิตภัณฑ์ (ตามรายการ)
   - สารสำคัญ (ตามรายการ)
   - ช่วงการใช้ (ตามรายการ)
   - ใช้กับพืช (ตามรายการ)
   - วิธีใช้ (ตามรายการ)
   - อัตราการใช้ (ตามรายการ)

5. ใช้ภาษาง่ายๆ พร้อม emoji
6. ไม่ใช้ markdown

ตอบคำถาม:"""
        
        elif intent == "solve_problem":
            prompt = f"""คุณคือผู้ช่วยแนะนำผลิตภัณฑ์จาก ICP Ladda

คำถามจากเกษตรกร: {question}

ผลิตภัณฑ์ที่มีในระบบ (ห้ามแนะนำนอกจากนี้):
{products_text}

ศัตรูพืชที่พบ: {', '.join(pests) if pests else 'ไม่ระบุ'}
พืชที่ปลูก: {', '.join(crops) if crops else 'ไม่ระบุ'}

🚨 **กฎที่ห้ามละเมิด**:
1. ใช้เฉพาะผลิตภัณฑ์จากรายการข้างต้นเท่านั้น
2. ห้ามสร้างชื่อผลิตภัณฑ์ใหม่
3. ห้ามแนะนำผลิตภัณฑ์ที่ไม่ได้อยู่ในรายการ
4. เลือกเฉพาะผลิตภัณฑ์ที่กำจัดศัตรูพืชที่ระบุได้

📋 **วิธีตอบ**:
1. เลือก 3-5 ผลิตภัณฑ์จากรายการข้างต้น
2. ใช้ชื่อผลิตภัณฑ์ตามที่ระบุในรายการเท่านั้น
3. คัดลอกรายละเอียดจากรายการโดยตรง ห้ามแต่งเติม
4. แสดงข้อมูลครบถ้วนตามนี้:
   - ชื่อผลิตภัณฑ์ (ตามรายการ)
   - สารสำคัญ (ตามรายการ)
   - ช่วงการใช้ (ตามรายการ)
   - ใช้กับพืช (ตามรายการ)
   - วิธีใช้ (ตามรายการ)
   - อัตราการใช้ (ตามรายการ)

5. ใช้ภาษาง่ายๆ พร้อม emoji
6. ไม่ใช้ markdown

ตอบคำถาม:"""
        
        else:
            # General product inquiry
            prompt = f"""คุณคือผู้ช่วยแนะนำผลิตภัณฑ์จาก ICP Ladda

คำถามจากเกษตรกร: {question}

ผลิตภัณฑ์ที่มีในระบบ (ห้ามแนะนำนอกจากนี้):
{products_text}

🚨 **กฎที่ห้ามละเมิด**:
1. ใช้เฉพาะผลิตภัณฑ์จากรายการข้างต้นเท่านั้น
2. ห้ามสร้างชื่อผลิตภัณฑ์ใหม่
3. ห้ามแนะนำผลิตภัณฑ์ที่ไม่ได้อยู่ในรายการ

📋 **วิธีตอบ**:
1. เลือก 3-5 ผลิตภัณฑ์จากรายการข้างต้น  
2. ใช้ชื่อ exact ตามรายการเท่านั้น
3. คัดลอกรายละเอียดจากรายการ
4. ใช้ภาษาง่ายๆ พร้อม emoji
5. ไม่ใช้ markdown

ตอบคำถาม:"""
        
        # Check if AI is available
        if not openai_client:
            logger.warning("OpenAI not available, using simple format")
            return await format_product_list_simple(unique_products[:5], question, intent)
        
        try:
            response = await openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a strict product assistant. ONLY recommend products from the provided list. Never create or suggest products not in the list."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # ลดลงจาก 0.7 → 0.1 เพื่อลดการสร้างสรรค์
                max_tokens=800
            )
            answer = response.choices[0].message.content.strip()
            answer = answer.replace("```", "").replace("**", "").replace("##", "")
            
            # Add footer
            answer += "\n\n" + "="*40
            answer += "\n📚 ดูรายละเอียดผลิตภัณฑ์ทั้งหมด:"
            answer += "\n🔗 https://www.icpladda.com/about/"
            answer += "\n\n💡 หากต้องการข้อมูลเพิ่มเติม กรุณาถามได้เลยค่ะ 😊"
            
            logger.info(f"✓ Intent-based answer generated ({intent})")
            return answer
            
        except Exception as e:
            logger.error(f"AI generation failed: {e}", exc_info=True)
            # Fallback to simple product list
            return await format_product_list_simple(unique_products[:5], question, intent)
        
    except Exception as e:
        logger.error(f"Error in intent-based recommendation: {e}", exc_info=True)
        return await answer_product_question(question, keywords)

async def format_product_list_simple(products: list, question: str, intent: str) -> str:
    """Format product list as simple fallback"""
    if intent == "increase_yield":
        header = "🌱 ผลิตภัณฑ์แนะนำสำหรับเพิ่มผลผลิต:\n"
    elif intent == "solve_problem":
        header = "💊 ผลิตภัณฑ์แนะนำสำหรับแก้ปัญหาศัตรูพืช:\n"
    else:
        header = "📦 ผลิตภัณฑ์แนะนำ:\n"
    
    response = header
    for idx, p in enumerate(products, 1):
        response += f"\n{idx}. {p.get('product_name', 'N/A')}"
        
        # สารสำคัญ
        if p.get('active_ingredient'):
            response += f"\n   - สารสำคัญ: {p.get('active_ingredient')}"
        
        # ศัตรูพืชที่กำจัดได้
        if p.get('target_pest'):
            pest = p.get('target_pest')[:150] + "..." if len(p.get('target_pest', '')) > 150 else p.get('target_pest', '')
            response += f"\n   - ศัตรูพืชที่กำจัดได้: {pest}"
        
        # วิธีใช้
        if p.get('how_to_use'):
            how_to = p.get('how_to_use')[:200] + "..." if len(p.get('how_to_use', '')) > 200 else p.get('how_to_use', '')
            response += f"\n   - วิธีใช้: {how_to}"
        
        # อัตราการใช้
        if p.get('usage_rate'):
            response += f"\n   - อัตราการใช้: {p.get('usage_rate')}"
        
        # ช่วงการใช้
        if p.get('usage_period'):
            response += f"\n   - ช่วงการใช้: {p.get('usage_period')}"
        
        # ใช้กับพืช
        if p.get('applicable_crops'):
            crops = p.get('applicable_crops')[:100] + "..." if len(p.get('applicable_crops', '')) > 100 else p.get('applicable_crops', '')
            response += f"\n   - ใช้กับพืช: {crops}"
        
        response += "\n"
    
    response += "\n📚 ดูรายละเอียดเพิ่มเติม: https://www.icpladda.com/about/"
    return response

async def answer_product_question(question: str, keywords: dict) -> str:
    """Answer product-specific questions with high accuracy"""
    try:
        logger.info(f"Product-specific query: {question[:50]}...")
        
        if not supabase_client:
            return "ขออภัยค่ะ ระบบไม่พร้อมใช้งานในขณะนี้"
        
        products_data = []
        
        # Search by pest/disease
        if keywords["pests"]:
            for pest in keywords["pests"][:2]:
                result = supabase_client.table('products')\
                    .select('*')\
                    .ilike('target_pest', f'%{pest}%')\
                    .limit(5)\
                    .execute()
                if result.data:
                    products_data.extend(result.data)
        
        # Search by crop
        if keywords["crops"]:
            for crop in keywords["crops"][:2]:
                result = supabase_client.table('products')\
                    .select('*')\
                    .ilike('applicable_crops', f'%{crop}%')\
                    .limit(5)\
                    .execute()
                if result.data:
                    products_data.extend(result.data)
        
        # Search by product name
        if keywords["products"]:
            for prod in keywords["products"]:
                if len(prod) > 3:
                    result = supabase_client.table('products')\
                        .select('*')\
                        .ilike('product_name', f'%{prod}%')\
                        .limit(5)\
                        .execute()
                    if result.data:
                        products_data.extend(result.data)
        
        # If no specific keywords, get general products
        if not products_data:
            result = supabase_client.table('products')\
                .select('*')\
                .limit(10)\
                .execute()
            if result.data:
                products_data = result.data
        
        if not products_data:
            return "ขออภัยค่ะ ไม่พบผลิตภัณฑ์ที่เกี่ยวข้อง กรุณาระบุชื่อพืชหรือศัตรูพืชที่ต้องการกำจัดค่ะ 🌱"
        
        # Remove duplicates
        seen = set()
        unique_products = []
        for p in products_data:
            pname = p.get('product_name', '')
            if pname and pname not in seen:
                seen.add(pname)
                unique_products.append(p)
        
        # Use Gemini to filter and format response
        products_text = ""
        for idx, p in enumerate(unique_products[:10], 1):
            products_text += f"\n[{idx}] {p.get('product_name', 'N/A')}"
            products_text += f"\n    สารสำคัญ: {p.get('active_ingredient', 'N/A')}"
            products_text += f"\n    ศัตรูพืช: {p.get('target_pest', 'N/A')[:100]}"
            products_text += f"\n    ใช้กับพืช: {p.get('applicable_crops', 'N/A')[:80]}"
            products_text += f"\n    ช่วงการใช้: {p.get('usage_period', 'N/A')}"
            products_text += f"\n    อัตราใช้: {p.get('usage_rate', 'N/A')}"
            products_text += "\n"
        
        prompt = f"""คุณคือผู้เชี่ยวชาญด้านผลิตภัณฑ์ป้องกันกำจัดศัตรูพืชของ ICP Ladda

คำถามจากเกษตรกร: {question}

ผลิตภัณฑ์ที่พบในระบบ:
{products_text}

คำแนะนำในการตอบ:
1. **วิเคราะห์คำถาม** - เข้าใจว่าเกษตรกรต้องการอะไร
2. **เลือกผลิตภัณฑ์ที่เหมาะสม** - เลือก 3-5 รายการที่ตรงที่สุด
3. **จัดลำดับ** - ผลิตภัณฑ์ที่เหมาะสมที่สุดก่อน
4. **แสดงรายละเอียด**:
   - ชื่อผลิตภัณฑ์
   - สารสำคัญ
   - ศัตรูพืชที่กำจัดได้
   - พืชที่ใช้ได้
   - อัตราการใช้
   - วิธีใช้โดยย่อ
5. **เพิ่มคำแนะนำ**:
   - อ่านฉลากก่อนใช้
   - ใช้อุปกรณ์ป้องกันตัว
   - ทดสอบในพื้นที่เล็กก่อน
6. **ใช้ภาษาง่ายๆ** 
7. **ไม่ใช้ markdown** - ตอบเป็นข้อความธรรมดา

**เกณฑ์การเลือก**:
- ถ้าถามเกี่ยวกับพืชเฉพาะ → เลือกเฉพาะที่ใช้กับพืชนั้นได้
- ถ้าถามเกี่ยวกับศัตรูพืช → เลือกที่กำจัดศัตรูพืชนั้นได้
- ถ้าถามทั่วไป → แนะนำผลิตภัณฑ์ยอดนิยม 3-5 รายการ

ตอบคำถาม:"""

        try:
            response = await openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are an agricultural product expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=800
            )
            answer = response.choices[0].message.content.strip()
            answer = answer.replace("```", "").replace("**", "").replace("##", "")
            
            # Add footer
            answer += "\n\n" + "="*40
            answer += "\n📚 ดูรายละเอียดผลิตภัณฑ์ทั้งหมด:"
            answer += "\n🔗 https://www.icpladda.com/about/"
            answer += "\n\n💡 หากต้องการข้อมูลเพิ่มเติม กรุณาถามได้เลยค่ะ 😊"
            
            logger.info("✓ Product answer generated successfully")
            return answer
            
        except Exception as e:
            logger.error(f"Gemini generation failed: {e}")
            # Fallback: return top 3 products directly
            response = "💊 ผลิตภัณฑ์แนะนำจาก ICP Ladda:\n"
            for idx, p in enumerate(unique_products[:3], 1):
                response += f"\n{idx}. {p.get('product_name')}"
                if p.get('active_ingredient'):
                    response += f"\n   สารสำคัญ: {p.get('active_ingredient')}"
                if p.get('target_pest'):
                    pest = p.get('target_pest')[:80] + "..." if len(p.get('target_pest', '')) > 80 else p.get('target_pest', '')
                    response += f"\n   ศัตรูพืช: {pest}"
                if p.get('applicable_crops'):
                    crops = p.get('applicable_crops')[:60] + "..." if len(p.get('applicable_crops', '')) > 60 else p.get('applicable_crops', '')
                    response += f"\n   ใช้กับพืช: {crops}"
                if p.get('usage_period'):
                    response += f"\n   ช่วงการใช้: {p.get('usage_period')}"
                if p.get('usage_rate'):
                    response += f"\n   อัตราใช้: {p.get('usage_rate')}"
                response += "\n"
            
            response += "\n📚 ดูรายละเอียดเพิ่มเติม: https://www.icpladda.com/about/"
            return response
        
    except Exception as e:
        logger.error(f"Error in product Q&A: {e}", exc_info=True)
        return "ขออภัยค่ะ ไม่สามารถค้นหาผลิตภัณฑ์ได้ในขณะนี้ กรุณาลองใหม่อีกครั้งค่ะ 🙏"
