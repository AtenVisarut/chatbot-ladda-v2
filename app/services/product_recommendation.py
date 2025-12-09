import logging
import json
from typing import List, Dict, Tuple
from app.models import DiseaseDetectionResult, ProductRecommendation
from app.services.services import supabase_client, openai_client
from app.services.cache import get_from_cache, set_to_cache
from app.utils.text_processing import extract_keywords_from_question
from app.services.reranker import rerank_products_with_llm, simple_relevance_boost

logger = logging.getLogger(__name__)

# Configuration for re-ranking
ENABLE_RERANKING = True  # Set to False to disable re-ranking for faster response

# =============================================================================
# โรคที่มีแมลงพาหะ → ควรแนะนำยาฆ่าแมลงแทนยากำจัดเชื้อ
# =============================================================================
VECTOR_DISEASES = {
    # =========================================================================
    # 🌾 ข้าว (RICE) - โรคไวรัสที่มีเพลี้ยเป็นพาหะ
    # =========================================================================
    "โรคจู๋": {"pest": "เพลี้ยกระโดดสีน้ำตาล", "search_query": "เพลี้ยกระโดดสีน้ำตาล ยาฆ่าแมลง BPH", "disease_query": "โรคจู๋ ข้าว บำรุงต้น ฟื้นฟู"},
    "rice ragged stunt": {"pest": "เพลี้ยกระโดดสีน้ำตาล", "search_query": "เพลี้ยกระโดดสีน้ำตาล ยาฆ่าแมลง BPH", "disease_query": "โรคจู๋ ข้าว บำรุงต้น"},
    "ragged stunt": {"pest": "เพลี้ยกระโดดสีน้ำตาล", "search_query": "เพลี้ยกระโดดสีน้ำตาล ยาฆ่าแมลง BPH", "disease_query": "โรคจู๋ ข้าว บำรุงต้น"},
    "โรคใบหงิก": {"pest": "เพลี้ยกระโดดสีน้ำตาล", "search_query": "เพลี้ยกระโดดสีน้ำตาล ยาฆ่าแมลง BPH", "disease_query": "โรคใบหงิก ข้าว บำรุงต้น ฮอร์โมน"},
    "rice grassy stunt": {"pest": "เพลี้ยกระโดดสีน้ำตาล", "search_query": "เพลี้ยกระโดดสีน้ำตาล ยาฆ่าแมลง BPH", "disease_query": "โรคใบหงิก ข้าว บำรุงต้น"},
    "grassy stunt": {"pest": "เพลี้ยกระโดดสีน้ำตาล", "search_query": "เพลี้ยกระโดดสีน้ำตาล ยาฆ่าแมลง BPH", "disease_query": "โรคใบหงิก ข้าว บำรุงต้น"},
    "โรคใบสีส้ม": {"pest": "เพลี้ยจักจั่นเขียว", "search_query": "เพลี้ยจักจั่น ยาฆ่าแมลง GLH", "disease_query": "โรคใบสีส้ม ข้าว บำรุงต้น"},
    "rice orange leaf": {"pest": "เพลี้ยจักจั่นเขียว", "search_query": "เพลี้ยจักจั่น ยาฆ่าแมลง GLH", "disease_query": "โรคใบสีส้ม ข้าว บำรุงต้น"},
    "orange leaf": {"pest": "เพลี้ยจักจั่นเขียว", "search_query": "เพลี้ยจักจั่น ยาฆ่าแมลง GLH", "disease_query": "โรคใบสีส้ม ข้าว บำรุงต้น"},
    "โรคใบขาวข้าว": {"pest": "เพลี้ยจักจั่นเขียว", "search_query": "เพลี้ยจักจั่น ยาฆ่าแมลง GLH", "disease_query": "โรคใบขาว ข้าว บำรุงต้น"},
    "rice tungro": {"pest": "เพลี้ยจักจั่นเขียว", "search_query": "เพลี้ยจักจั่น ยาฆ่าแมลง GLH", "disease_query": "โรคทังโร ข้าว บำรุงต้น"},
    "tungro": {"pest": "เพลี้ยจักจั่นเขียว", "search_query": "เพลี้ยจักจั่น ยาฆ่าแมลง GLH", "disease_query": "โรคทังโร ข้าว บำรุงต้น"},
    "โรคทังโร": {"pest": "เพลี้ยจักจั่นเขียว", "search_query": "เพลี้ยจักจั่น ยาฆ่าแมลง GLH", "disease_query": "โรคทังโร ข้าว บำรุงต้น"},

    # =========================================================================
    # 🍬 อ้อย (SUGARCANE) - โรคไวรัสและไฟโตพลาสมา
    # =========================================================================
    "โรคใบขาวอ้อย": {"pest": "เพลี้ยจักจั่น", "search_query": "เพลี้ยจักจั่น ยาฆ่าแมลง อ้อย"},
    "sugarcane white leaf": {"pest": "เพลี้ยจักจั่น", "search_query": "เพลี้ยจักจั่น ยาฆ่าแมลง อ้อย"},
    "white leaf": {"pest": "เพลี้ยจักจั่น", "search_query": "เพลี้ยจักจั่น ยาฆ่าแมลง"},
    "โรคใบด่างอ้อย": {"pest": "เพลี้ยอ่อน", "search_query": "เพลี้ยอ่อน ยาฆ่าแมลง อ้อย"},
    "sugarcane mosaic": {"pest": "เพลี้ยอ่อน", "search_query": "เพลี้ยอ่อน ยาฆ่าแมลง"},
    "โรคกอตะไคร้": {"pest": "เพลี้ยจักจั่น", "search_query": "เพลี้ยจักจั่น ยาฆ่าแมลง อ้อย"},
    "sugarcane grassy shoot": {"pest": "เพลี้ยจักจั่น", "search_query": "เพลี้ยจักจั่น ยาฆ่าแมลง"},

    # =========================================================================
    # 🥭 มะม่วง (MANGO) - โรคที่มีแมลงเกี่ยวข้อง
    # =========================================================================
    "โรคช่อดำมะม่วง": {"pest": "เพลี้ยจักจั่นมะม่วง เพลี้ยไฟ", "search_query": "เพลี้ยจักจั่นมะม่วง เพลี้ยไฟ ยาฆ่าแมลง"},
    "mango malformation": {"pest": "ไรสี่ขา", "search_query": "ไรสี่ขา ยาฆ่าไร มะม่วง"},
    "โรคยอดไหม้มะม่วง": {"pest": "เพลี้ยจักจั่นมะม่วง", "search_query": "เพลี้ยจักจั่นมะม่วง ยาฆ่าแมลง"},
    "mango hopper burn": {"pest": "เพลี้ยจักจั่นมะม่วง", "search_query": "เพลี้ยจักจั่นมะม่วง ยาฆ่าแมลง"},

    # =========================================================================
    # 🌳 ลำไย (LONGAN) - โรคที่มีแมลงเป็นพาหะ
    # =========================================================================
    "โรคพุ่มไม้กวาด": {"pest": "เพลี้ยจักจั่น ไรสี่ขา", "search_query": "เพลี้ยจักจั่น ไรสี่ขา ยาฆ่าแมลง ลำไย"},
    "witches' broom": {"pest": "เพลี้ยจักจั่น ไรสี่ขา", "search_query": "เพลี้ยจักจั่น ไรสี่ขา ยาฆ่าแมลง ลำไย"},
    "longan witches broom": {"pest": "เพลี้ยจักจั่น ไรสี่ขา", "search_query": "เพลี้ยจักจั่น ไรสี่ขา ยาฆ่าแมลง"},
    "โรคใบไหม้ลำไย": {"pest": "เพลี้ยไฟ ไรแดง", "search_query": "เพลี้ยไฟ ไรแดง ยาฆ่าแมลง ลำไย"},

    # =========================================================================
    # 🍈 ทุเรียน (DURIAN) - แมลงศัตรูพืชสำคัญ
    # =========================================================================
    "เพลี้ยไก่แจ้ทุเรียน": {"pest": "เพลี้ยไก่แจ้", "search_query": "เพลี้ยไก่แจ้ ยาฆ่าแมลง ทุเรียน"},
    "หนอนเจาะผลทุเรียน": {"pest": "หนอนเจาะผล", "search_query": "หนอนเจาะผล ยาฆ่าแมลง ทุเรียน"},
    "เพลี้ยแป้งทุเรียน": {"pest": "เพลี้ยแป้ง", "search_query": "เพลี้ยแป้ง ยาฆ่าแมลง ทุเรียน"},
    "ไรแดงทุเรียน": {"pest": "ไรแดง", "search_query": "ไรแดง ยาฆ่าไร ทุเรียน"},
    "เพลี้ยไฟทุเรียน": {"pest": "เพลี้ยไฟ", "search_query": "เพลี้ยไฟ ยาฆ่าแมลง ทุเรียน"},

    # =========================================================================
    # 🍊 ส้ม/มะนาว (CITRUS) - โรคไวรัสที่มีพาหะ
    # =========================================================================
    "โรคกรีนนิ่ง": {"pest": "เพลี้ยไก่แจ้", "search_query": "เพลี้ยไก่แจ้ ยาฆ่าแมลง ส้ม"},
    "greening": {"pest": "เพลี้ยไก่แจ้", "search_query": "เพลี้ยไก่แจ้ ยาฆ่าแมลง ส้ม"},
    "hlb": {"pest": "เพลี้ยไก่แจ้", "search_query": "เพลี้ยไก่แจ้ ยาฆ่าแมลง ส้ม"},
    "huanglongbing": {"pest": "เพลี้ยไก่แจ้", "search_query": "เพลี้ยไก่แจ้ ยาฆ่าแมลง ส้ม"},
    "โรคทริสเตซ่า": {"pest": "เพลี้ยอ่อน", "search_query": "เพลี้ยอ่อน ยาฆ่าแมลง ส้ม"},
    "tristeza": {"pest": "เพลี้ยอ่อน", "search_query": "เพลี้ยอ่อน ยาฆ่าแมลง ส้ม"},
    "citrus tristeza": {"pest": "เพลี้ยอ่อน", "search_query": "เพลี้ยอ่อน ยาฆ่าแมลง ส้ม"},

    # =========================================================================
    # 🥔 มันสำปะหลัง (CASSAVA) - โรคไวรัสที่มีพาหะ
    # =========================================================================
    "โรคใบด่างมันสำปะหลัง": {"pest": "แมลงหวี่ขาว", "search_query": "แมลงหวี่ขาว ยาฆ่าแมลง มันสำปะหลัง"},
    "cassava mosaic": {"pest": "แมลงหวี่ขาว", "search_query": "แมลงหวี่ขาว ยาฆ่าแมลง มันสำปะหลัง"},
    "cmd": {"pest": "แมลงหวี่ขาว", "search_query": "แมลงหวี่ขาว ยาฆ่าแมลง มันสำปะหลัง"},
    "slcmv": {"pest": "แมลงหวี่ขาว", "search_query": "แมลงหวี่ขาว ยาฆ่าแมลง"},
    "โรคพุ่มแจ้มันสำปะหลัง": {"pest": "เพลี้ยจักจั่น", "search_query": "เพลี้ยจักจั่น ยาฆ่าแมลง มันสำปะหลัง"},
    "cassava witches' broom": {"pest": "เพลี้ยจักจั่น", "search_query": "เพลี้ยจักจั่น ยาฆ่าแมลง"},

    # =========================================================================
    # 🌽 ข้าวโพด (CORN/MAIZE) - โรคไวรัสที่มีพาหะ
    # =========================================================================
    "โรคข้าวโพดแคระ": {"pest": "เพลี้ยจักจั่นข้าวโพด", "search_query": "เพลี้ยจักจั่น ยาฆ่าแมลง ข้าวโพด"},
    "corn stunt": {"pest": "เพลี้ยจักจั่นข้าวโพด", "search_query": "เพลี้ยจักจั่น ยาฆ่าแมลง ข้าวโพด"},
    "โรคข้าวโพดงอย": {"pest": "เพลี้ยจักจั่นข้าวโพด", "search_query": "เพลี้ยจักจั่น ยาฆ่าแมลง ข้าวโพด"},
    "โรคใบลายข้าวโพด": {"pest": "เพลี้ยกระโดดข้าวโพด", "search_query": "เพลี้ยกระโดด ยาฆ่าแมลง ข้าวโพด"},
    "maize stripe": {"pest": "เพลี้ยกระโดดข้าวโพด", "search_query": "เพลี้ยกระโดด ยาฆ่าแมลง ข้าวโพด"},
    "โรคใบด่างข้าวโพด": {"pest": "เพลี้ยอ่อน", "search_query": "เพลี้ยอ่อน ยาฆ่าแมลง ข้าวโพด"},
    "maize mosaic": {"pest": "เพลี้ยอ่อน เพลี้ยกระโดด", "search_query": "เพลี้ยอ่อน เพลี้ยกระโดด ยาฆ่าแมลง"},

    # =========================================================================
    # 🌿 โรคไวรัสทั่วไป
    # =========================================================================
    "โรคใบด่าง": {"pest": "เพลี้ยอ่อน แมลงหวี่ขาว", "search_query": "เพลี้ยอ่อน แมลงหวี่ขาว ยาฆ่าแมลง"},
    "mosaic": {"pest": "เพลี้ยอ่อน", "search_query": "เพลี้ยอ่อน ยาฆ่าแมลง"},
    "โรคใบหด": {"pest": "เพลี้ยอ่อน ไรขาว", "search_query": "เพลี้ยอ่อน ไรขาว ยาฆ่าแมลง"},
    "leaf curl": {"pest": "แมลงหวี่ขาว", "search_query": "แมลงหวี่ขาว ยาฆ่าแมลง"},
    "โรคใบหงิกเหลือง": {"pest": "แมลงหวี่ขาว", "search_query": "แมลงหวี่ขาว ยาฆ่าแมลง"},
}

def get_search_query_for_disease(disease_name: str, pest_type: str = "") -> tuple:
    """
    ตรวจสอบว่าโรคนี้มีแมลงพาหะหรือไม่
    ถ้ามี → return (search_query สำหรับยาฆ่าแมลง, pest_name, disease_search_query)
    ถ้าไม่มี → return (disease_name, None, None)

    Returns: (vector_search_query, pest_name, disease_search_query)
    """
    disease_lower = disease_name.lower()

    # ตรวจสอบว่าเป็นโรคที่มีพาหะหรือไม่
    for key, info in VECTOR_DISEASES.items():
        if key in disease_lower:
            logger.info(f"🐛 โรคนี้มีแมลงพาหะ: {info['pest']} → ค้นหาทั้งยาฆ่าแมลงและยารักษาโรค")
            # Return both: vector search + disease treatment search
            disease_treatment_query = info.get("disease_query", f"{disease_name} ยารักษา โรคพืช")
            return (info["search_query"], info["pest"], disease_treatment_query)

    # ถ้าเป็นไวรัส → แนะนำให้หาพาหะ
    if pest_type and "ไวรัส" in pest_type.lower():
        logger.info("🦠 โรคไวรัส → ค้นหายาฆ่าแมลงสำหรับพาหะ")
        return (f"{disease_name} ยาฆ่าแมลง พาหะ", None, None)

    return (disease_name, None, None)


# =============================================================================
# Hybrid Search Functions (Vector + BM25/Keyword)
# =============================================================================

async def hybrid_search_products(query: str, match_count: int = 15,
                                  vector_weight: float = 0.6,
                                  keyword_weight: float = 0.4) -> List[Dict]:
    """
    Perform Hybrid Search combining Vector Search + Keyword/BM25 Search
    Uses Reciprocal Rank Fusion (RRF) for combining results
    """
    try:
        if not supabase_client or not openai_client:
            logger.warning("Supabase or OpenAI client not available for hybrid search")
            return []

        logger.info(f"🔍 Hybrid Search: '{query}' (vector={vector_weight}, keyword={keyword_weight})")

        # Generate embedding for vector search
        response = await openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=query,
            encoding_format="float"
        )
        query_embedding = response.data[0].embedding

        # Try hybrid_search_products RPC first (if SQL function exists)
        try:
            result = supabase_client.rpc(
                'hybrid_search_products',
                {
                    'query_embedding': query_embedding,
                    'search_query': query,
                    'vector_weight': vector_weight,
                    'keyword_weight': keyword_weight,
                    'match_threshold': 0.15,
                    'match_count': match_count
                }
            ).execute()

            if result.data:
                logger.info(f"✓ Hybrid search returned {len(result.data)} products")
                for p in result.data[:3]:
                    logger.info(f"   → {p.get('product_name')}: hybrid={p.get('hybrid_score', 0):.3f} "
                               f"(vec={p.get('vector_score', 0):.3f}, kw={p.get('keyword_score', 0):.3f})")
                return result.data

        except Exception as e:
            logger.warning(f"hybrid_search_products RPC failed: {e}, falling back to manual hybrid search")

        # Fallback: Manual hybrid search (Vector + Keyword separately)
        return await manual_hybrid_search(query, query_embedding, match_count, vector_weight, keyword_weight)

    except Exception as e:
        logger.error(f"Hybrid search failed: {e}", exc_info=True)
        return []


async def manual_hybrid_search(query: str, query_embedding: List[float],
                                match_count: int = 15,
                                vector_weight: float = 0.6,
                                keyword_weight: float = 0.4) -> List[Dict]:
    """
    Manual Hybrid Search fallback - runs vector and keyword search separately
    then combines with Reciprocal Rank Fusion (RRF)
    """
    try:
        # 1. Vector Search
        vector_results = []
        try:
            result = supabase_client.rpc(
                'match_products',
                {
                    'query_embedding': query_embedding,
                    'match_threshold': 0.15,
                    'match_count': match_count * 2
                }
            ).execute()
            if result.data:
                vector_results = result.data
                logger.info(f"   Vector search: {len(vector_results)} results")
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")

        # 2. Keyword Search (ILIKE fallback)
        keyword_results = []
        try:
            # Try keyword_search_products RPC
            result = supabase_client.rpc(
                'keyword_search_products',
                {
                    'search_query': query,
                    'match_count': match_count * 2
                }
            ).execute()
            if result.data:
                keyword_results = result.data
                logger.info(f"   Keyword search (RPC): {len(keyword_results)} results")
        except Exception as e:
            logger.warning(f"keyword_search_products RPC failed: {e}, trying ILIKE")
            # Fallback: ILIKE search
            try:
                result = supabase_client.table('products')\
                    .select('*')\
                    .or_(f"product_name.ilike.%{query}%,"
                         f"target_pest.ilike.%{query}%,"
                         f"applicable_crops.ilike.%{query}%,"
                         f"active_ingredient.ilike.%{query}%")\
                    .limit(match_count * 2)\
                    .execute()
                if result.data:
                    # Add rank score for ILIKE results
                    for i, p in enumerate(result.data):
                        p['rank'] = 1.0 / (i + 1)  # Simple rank score
                    keyword_results = result.data
                    logger.info(f"   Keyword search (ILIKE): {len(keyword_results)} results")
            except Exception as e2:
                logger.warning(f"ILIKE search failed: {e2}")

        # 3. Combine with RRF (Reciprocal Rank Fusion)
        combined = reciprocal_rank_fusion(
            vector_results, keyword_results,
            vector_weight, keyword_weight
        )

        logger.info(f"✓ Manual hybrid search combined: {len(combined)} products")
        return combined[:match_count]

    except Exception as e:
        logger.error(f"Manual hybrid search failed: {e}", exc_info=True)
        return []


def reciprocal_rank_fusion(vector_results: List[Dict], keyword_results: List[Dict],
                           vector_weight: float = 0.6, keyword_weight: float = 0.4,
                           k: int = 60) -> List[Dict]:
    """
    Combine vector and keyword search results using Reciprocal Rank Fusion (RRF)
    RRF score = sum(1 / (k + rank)) across all result sets

    Parameters:
    - k: constant to prevent high scores for top results (default 60)
    """
    try:
        # Build product lookup and RRF scores
        products_by_id = {}
        rrf_scores = {}

        # Process vector results
        for rank, product in enumerate(vector_results, 1):
            pid = product.get('id') or product.get('product_name')
            if pid:
                products_by_id[pid] = product
                rrf_scores[pid] = rrf_scores.get(pid, 0) + vector_weight * (1 / (k + rank))
                product['vector_rank'] = rank
                product['vector_score'] = product.get('similarity', 0)

        # Process keyword results
        for rank, product in enumerate(keyword_results, 1):
            pid = product.get('id') or product.get('product_name')
            if pid:
                if pid not in products_by_id:
                    products_by_id[pid] = product
                rrf_scores[pid] = rrf_scores.get(pid, 0) + keyword_weight * (1 / (k + rank))
                products_by_id[pid]['keyword_rank'] = rank
                products_by_id[pid]['keyword_score'] = product.get('rank', 0)

        # Add bonus for products appearing in both
        for pid in rrf_scores:
            product = products_by_id[pid]
            if product.get('vector_rank') and product.get('keyword_rank'):
                rrf_scores[pid] += 0.02  # Small bonus for appearing in both

        # Sort by RRF score
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        # Build final results
        combined_results = []
        for pid in sorted_ids:
            product = products_by_id[pid].copy()
            product['hybrid_score'] = rrf_scores[pid]
            product['similarity'] = rrf_scores[pid]  # Use hybrid score as similarity
            combined_results.append(product)

        return combined_results

    except Exception as e:
        logger.error(f"RRF fusion failed: {e}", exc_info=True)
        # Fallback: return vector results
        return vector_results

async def retrieve_product_recommendation(disease_info: DiseaseDetectionResult) -> List[ProductRecommendation]:
    """
    Query products using Hybrid Search (Vector + Keyword/BM25)
    Returns top 3-6 most relevant products

    สำหรับโรคที่มีแมลงพาหะ (เช่น โรคจู๋ของข้าว) จะค้นหายาฆ่าแมลงแทน
    """
    try:
        logger.info("🔍 Retrieving products with Hybrid Search (Vector + Keyword)")

        if not supabase_client:
            logger.warning("Supabase not configured")
            return []

        disease_name = disease_info.disease_name

        # ตรวจสอบว่าโรคนี้มีแมลงพาหะหรือไม่ → ถ้ามี ค้นหาทั้งยาฆ่าแมลงและยารักษาโรค
        pest_type = ""
        if hasattr(disease_info, 'raw_analysis') and disease_info.raw_analysis:
            # ดึง pest_type จาก raw_analysis ถ้ามี
            if "ไวรัส" in disease_info.raw_analysis:
                pest_type = "ไวรัส"

        vector_search_query, pest_name, disease_treatment_query = get_search_query_for_disease(disease_name, pest_type)

        if pest_name:
            logger.info(f"🐛 โรคมีพาหะ: {pest_name}")
            logger.info(f"   → ค้นหายาฆ่าแมลง: {vector_search_query}")
            logger.info(f"   → ค้นหายารักษาโรค: {disease_treatment_query}")
            search_query = vector_search_query  # Primary search is for vector
        else:
            search_query = vector_search_query
            logger.info(f"📝 Searching products for: {disease_name}")

        # Check cache first (ใช้ search_query เป็น key)
        cache_key = f"products:{search_query}"
        cached_products = await get_from_cache("products", cache_key)
        if cached_products:
            logger.info("✓ Using cached product recommendations")
            return [ProductRecommendation(**p) for p in cached_products]

        # Strategy 1: Hybrid Search (Vector + Keyword combined)
        try:
            all_results = []

            # 1. ค้นหายากำจัดพาหะ (ถ้ามี)
            hybrid_results = await hybrid_search_products(
                query=search_query,  # ใช้ search_query แทน disease_name
                match_count=15,
                vector_weight=0.6,
                keyword_weight=0.4
            )
            if hybrid_results:
                # Mark these as vector control products
                for p in hybrid_results:
                    p['recommendation_type'] = 'vector_control' if pest_name else 'disease_treatment'
                all_results.extend(hybrid_results)
                logger.info(f"✓ Primary search found {len(hybrid_results)} products")

            # 2. ค้นหายารักษาโรคเพิ่มเติม (ถ้าโรคมีพาหะ)
            if pest_name and disease_treatment_query:
                disease_results = await hybrid_search_products(
                    query=disease_treatment_query,
                    match_count=10,
                    vector_weight=0.5,
                    keyword_weight=0.5
                )
                if disease_results:
                    # Mark these as disease treatment products
                    for p in disease_results:
                        p['recommendation_type'] = 'disease_treatment'
                    all_results.extend(disease_results)
                    logger.info(f"✓ Disease treatment search found {len(disease_results)} products")

            # Combine and deduplicate
            hybrid_results = all_results

            if hybrid_results:
                logger.info(f"✓ Total hybrid search found {len(hybrid_results)} candidates")

                # Apply simple relevance boost first
                for p in hybrid_results:
                    boost = simple_relevance_boost(disease_name, p)
                    p['hybrid_score'] = p.get('hybrid_score', p.get('similarity', 0)) + boost

                # Sort by boosted score
                hybrid_results.sort(key=lambda x: x.get('hybrid_score', 0), reverse=True)

                # Re-rank top candidates with LLM Cross-Encoder (if enabled)
                if ENABLE_RERANKING and len(hybrid_results) > 6:
                    logger.info("🔄 Applying LLM re-ranking for higher accuracy...")
                    hybrid_results = await rerank_products_with_llm(
                        query=disease_name,
                        products=hybrid_results[:15],  # Top 15 candidates
                        top_k=6,
                        openai_client=openai_client
                    )

                # Filter by hybrid score threshold
                filtered_data = [
                    p for p in hybrid_results
                    if p.get('hybrid_score', p.get('similarity', 0)) > 0.005
                ][:6]

                if filtered_data:
                    logger.info(f"✓ Final {len(filtered_data)} products after re-ranking")
                    filtered_products = build_recommendations_from_data(filtered_data, pest_name=pest_name)

                    # Cache the results
                    if filtered_products:
                        await set_to_cache("products", cache_key, [r.dict() for r in filtered_products])

                    return filtered_products
                else:
                    # No products passed threshold - return empty instead of forcing results
                    logger.warning("⚠️ No products passed relevance threshold - no recommendations")
                    return []

        except Exception as e:
            logger.warning(f"Hybrid search failed: {e}, trying fallback")

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
        recommendations = build_recommendations_from_data(matches_data[:6], pest_name=pest_name)

        # Cache the results
        if recommendations:
            await set_to_cache("products", cache_key, [r.dict() for r in recommendations])

        return recommendations

    except Exception as e:
        logger.error(f"Product search failed: {e}", exc_info=True)
        return []


def build_recommendations_from_data(products_data: List[Dict], pest_name: str = None) -> List[ProductRecommendation]:
    """Build ProductRecommendation list from raw data

    Args:
        products_data: List of product dictionaries
        pest_name: Name of pest vector (if disease has one) - used to add context to recommendations
    """
    recommendations = []
    seen_products = set()

    # Sort to prioritize vector control products first if pest_name is provided
    if pest_name:
        # Put vector_control products first
        products_data = sorted(
            products_data,
            key=lambda x: (0 if x.get('recommendation_type') == 'vector_control' else 1, -x.get('hybrid_score', x.get('similarity', 0)))
        )

    for product in products_data:
        pname = product.get("product_name", "ไม่ระบุชื่อ")

        if pname in seen_products:
            continue
        seen_products.add(pname)

        pest = product.get("target_pest", "")
        if not pest or pest.strip() == "":
            continue

        # ไม่ต้องเพิ่ม prefix เพราะข้อมูล product มีอยู่แล้ว

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
            # เพิ่มผลผลิต - search more broadly
            if crops:
                for crop in crops[:2]:
                    # Primary searches
                    search_queries.append(f"เพิ่มผลผลิต {crop}")
                    search_queries.append(f"บำรุง {crop}")
                    search_queries.append(f"ปุ๋ย {crop}")
                    search_queries.append(f"ฮอร์โมน {crop}")
                    # Also search by crop name directly
                    search_queries.append(crop)
                    # Problem prevention for yield
                    search_queries.append(f"ป้องกันโรค {crop}")
                    search_queries.append(f"บำรุงต้น {crop}")
            else:
                search_queries.append("เพิ่มผลผลิต ปุ๋ย ฮอร์โมน บำรุง")
        
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
        
        # Hybrid search for each query (Vector + Keyword combined)
        all_products = []
        logger.info(f"🔍 Hybrid searching with {len(search_queries)} queries: {search_queries[:5]}")

        for query in search_queries[:5]:  # Top 5 queries
            try:
                logger.info(f"   → Query: '{query}'")

                # Use hybrid search (Vector + Keyword)
                results = await hybrid_search_products(
                    query=query,
                    match_count=15,
                    vector_weight=0.5,  # Balanced weights for intent-based search
                    keyword_weight=0.5
                )

                if results:
                    all_products.extend(results)
                    logger.info(f"   ✓ Found {len(results)} products (hybrid)")
                else:
                    logger.warning(f"   ⚠️ No products found")
            except Exception as e:
                logger.error(f"   ❌ Hybrid search failed: {e}", exc_info=True)
        
        # Remove duplicates and apply relevance boost
        seen = set()
        unique_products = []
        for p in all_products:
            pname = p.get('product_name', '')
            if pname and pname not in seen:
                seen.add(pname)
                # Apply relevance boost based on query terms
                boost = 0
                for query in search_queries[:3]:
                    boost += simple_relevance_boost(query, p)
                p['hybrid_score'] = p.get('hybrid_score', p.get('similarity', 0)) + (boost / 3)
                unique_products.append(p)

        # Sort by boosted score
        unique_products.sort(key=lambda x: x.get('hybrid_score', 0), reverse=True)

        # Re-rank with LLM if enabled and enough candidates
        if ENABLE_RERANKING and len(unique_products) > 6:
            logger.info("🔄 Applying LLM re-ranking for intent-based search...")
            unique_products = await rerank_products_with_llm(
                query=question,
                products=unique_products[:15],
                top_k=10,
                openai_client=openai_client
            )

        logger.info(f"📦 Total products: {len(all_products)}, Unique: {len(unique_products)}")

        if not unique_products:
            # Fallback 1: Search by applicable_crops
            logger.warning("⚠️ No products from vector search, trying applicable_crops search")
            if crops:
                for crop in crops[:2]:
                    try:
                        result = supabase_client.table('products')\
                            .select('*')\
                            .ilike('applicable_crops', f'%{crop}%')\
                            .limit(10)\
                            .execute()

                        if result.data:
                            unique_products.extend(result.data)
                            logger.info(f"✓ Found {len(result.data)} products for crop: {crop}")
                    except Exception as e:
                        logger.warning(f"applicable_crops search failed: {e}")

            # Fallback 2: Search by target_pest for common issues
            if not unique_products and pests:
                for pest in pests[:2]:
                    try:
                        result = supabase_client.table('products')\
                            .select('*')\
                            .ilike('target_pest', f'%{pest}%')\
                            .limit(10)\
                            .execute()

                        if result.data:
                            unique_products.extend(result.data)
                            logger.info(f"✓ Found {len(result.data)} products for pest: {pest}")
                    except Exception as e:
                        logger.warning(f"target_pest search failed: {e}")

            # If still no products, fallback to keyword search
            if not unique_products:
                logger.warning("⚠️ No products found, trying keyword search")
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

# =============================================================================
# Matching Score Product Recommendation
# =============================================================================

def calculate_matching_score(product: Dict, disease_name: str, plant_type: str, growth_stage: str) -> float:
    """
    คำนวณ Matching Score ระหว่าง product กับข้อมูล user

    Weights:
    - 40% - โรค/แมลง ตรงกับ target_pest
    - 30% - พืช ตรงกับ applicable_crops
    - 30% - ระยะ ตรงกับ usage_period

    Returns: score 0.0 - 1.0
    """
    score = 0.0

    target_pest = (product.get("target_pest") or "").lower()
    applicable_crops = (product.get("applicable_crops") or "").lower()
    usage_period = (product.get("usage_period") or "").lower()

    disease_lower = disease_name.lower()
    plant_lower = plant_type.lower() if plant_type else ""
    stage_lower = growth_stage.lower() if growth_stage else ""

    # 1. Disease/Pest Match (40%)
    disease_score = 0.0

    # Direct disease name match
    if disease_lower and disease_lower in target_pest:
        disease_score = 1.0
    else:
        # Check partial matches
        disease_keywords = disease_lower.replace("โรค", "").strip().split()
        for kw in disease_keywords:
            if len(kw) > 2 and kw in target_pest:
                disease_score = max(disease_score, 0.7)
                break

        # Check if product targets related issues
        pest_check_query, pest_name, _ = get_search_query_for_disease(disease_name)
        if pest_name:
            # Disease has vector - check if product targets the vector
            pest_keywords = pest_name.lower().split()
            for kw in pest_keywords:
                if len(kw) > 2 and kw in target_pest:
                    disease_score = max(disease_score, 0.9)
                    break

        # Generic disease type match (เชื้อรา, ไวรัส, etc.)
        disease_types = ["เชื้อรา", "ไวรัส", "แบคทีเรีย", "แมลง", "เพลี้ย", "หนอน"]
        for dt in disease_types:
            if dt in disease_lower and dt in target_pest:
                disease_score = max(disease_score, 0.5)
                break

    score += disease_score * 0.4

    # 2. Plant/Crop Match (30%)
    plant_score = 0.0

    if plant_lower:
        # Direct plant match
        if plant_lower in applicable_crops:
            plant_score = 1.0
        else:
            # Check plant synonyms/variants
            plant_synonyms = {
                "ข้าว": ["ข้าว", "rice", "นาข้าว"],
                "มะม่วง": ["มะม่วง", "mango"],
                "ทุเรียน": ["ทุเรียน", "durian"],
                "ส้ม": ["ส้ม", "มะนาว", "citrus", "ส้มโอ"],
                "ผัก": ["ผัก", "vegetable", "ผักกาด", "คะน้า", "กะหล่ำ"],
                "มันสำปะหลัง": ["มัน", "cassava", "มันสำปะหลัง"],
                "ข้าวโพด": ["ข้าวโพด", "corn", "maize"],
                "อ้อย": ["อ้อย", "sugarcane"],
                "ลำไย": ["ลำไย", "longan"],
                "ยางพารา": ["ยาง", "rubber", "ยางพารา"],
                "ปาล์ม": ["ปาล์ม", "palm", "ปาล์มน้ำมัน"],
                "พริก": ["พริก", "chili", "pepper"],
                "มะเขือ": ["มะเขือ", "eggplant", "tomato", "มะเขือเทศ"],
            }

            for main_plant, synonyms in plant_synonyms.items():
                if any(s in plant_lower for s in synonyms):
                    if any(s in applicable_crops for s in synonyms):
                        plant_score = 0.9
                        break
                    elif main_plant in applicable_crops:
                        plant_score = 0.8
                        break

            # Generic crop match
            if plant_score == 0 and ("พืช" in applicable_crops or "ทุกชนิด" in applicable_crops):
                plant_score = 0.3

    score += plant_score * 0.3

    # 3. Growth Stage Match (30%)
    stage_score = 0.0

    if stage_lower:
        # Extract stage keywords from user input
        stage_keywords_map = {
            "กล้า": ["กล้า", "ปักดำ", "เพาะ", "ต้นอ่อน", "seedling"],
            "แตกกอ": ["แตกกอ", "tillering", "แตกใบ"],
            "ตั้งท้อง": ["ตั้งท้อง", "booting", "ท้อง"],
            "ออกรวง": ["ออกรวง", "flowering", "ออกดอก", "รวง", "heading"],
            "ออกดอก": ["ออกดอก", "ดอก", "flower", "บาน"],
            "ติดผล": ["ติดผล", "ผลอ่อน", "fruiting", "ติดลูก"],
            "ผลโต": ["ผลโต", "ขยายผล", "fruit development"],
            "เก็บเกี่ยว": ["เก็บเกี่ยว", "harvest", "สุก"],
            "ทุกระยะ": ["ทุกระยะ", "ตลอด", "all stage"],
        }

        # Check stage match in usage_period
        for stage_name, keywords in stage_keywords_map.items():
            # Check if user's stage matches
            user_stage_match = any(kw in stage_lower for kw in keywords)

            if user_stage_match:
                # Check if product's usage_period covers this stage
                if any(kw in usage_period for kw in keywords):
                    stage_score = 1.0
                    break
                elif "ทุกระยะ" in usage_period or "ตลอด" in usage_period:
                    stage_score = 0.7
                    break

        # If no specific match, check for general compatibility
        if stage_score == 0:
            # Extract day ranges if present (e.g., "0-20 วัน")
            import re
            user_days = re.findall(r'(\d+)', stage_lower)
            product_days = re.findall(r'(\d+)', usage_period)

            if user_days and product_days:
                # Check if ranges overlap
                try:
                    user_mid = sum(int(d) for d in user_days[:2]) / len(user_days[:2])
                    prod_mid = sum(int(d) for d in product_days[:2]) / len(product_days[:2])

                    # If within 30 days, partial match
                    if abs(user_mid - prod_mid) < 30:
                        stage_score = 0.5
                except:
                    pass

    score += stage_score * 0.3

    return score


async def retrieve_products_with_matching_score(
    detection_result: DiseaseDetectionResult,
    plant_type: str,
    growth_stage: str
) -> List[ProductRecommendation]:
    """
    ค้นหาและแนะนำสินค้าโดยใช้ Matching Score

    Flow:
    1. ค้นหาสินค้าจาก Hybrid Search ตามโรค/แมลง
    2. คำนวณ Matching Score แต่ละสินค้า
    3. เรียงลำดับตาม score
    4. Return top products

    Args:
        detection_result: ผลการวินิจฉัยโรค
        plant_type: ชนิดพืชที่ปลูก
        growth_stage: ระยะการเจริญเติบโต

    Returns:
        List[ProductRecommendation] เรียงตาม matching score
    """
    try:
        logger.info("🎯 Retrieving products with Matching Score")
        logger.info(f"   Disease: {detection_result.disease_name}")
        logger.info(f"   Plant: {plant_type}")
        logger.info(f"   Stage: {growth_stage}")

        if not supabase_client:
            logger.warning("Supabase not configured")
            return []

        disease_name = detection_result.disease_name

        # ตรวจสอบว่าโรคนี้มีแมลงพาหะหรือไม่
        pest_type = ""
        if hasattr(detection_result, 'raw_analysis') and detection_result.raw_analysis:
            if "ไวรัส" in detection_result.raw_analysis:
                pest_type = "ไวรัส"

        vector_search_query, pest_name, disease_treatment_query = get_search_query_for_disease(disease_name, pest_type)

        if pest_name:
            logger.info(f"🐛 โรคมีพาหะ: {pest_name}")

        # 1. Hybrid Search for products
        all_results = []

        # Primary search (vector control if has pest, or disease treatment)
        search_query = vector_search_query
        if plant_type:
            search_query = f"{search_query} {plant_type}"

        logger.info(f"🔍 Primary search: {search_query}")

        hybrid_results = await hybrid_search_products(
            query=search_query,
            match_count=20,
            vector_weight=0.5,
            keyword_weight=0.5
        )

        if hybrid_results:
            all_results.extend(hybrid_results)
            logger.info(f"   → Found {len(hybrid_results)} products")

        # Secondary search for disease treatment (if has vector)
        if pest_name and disease_treatment_query:
            if plant_type:
                disease_treatment_query = f"{disease_treatment_query} {plant_type}"

            logger.info(f"🔍 Disease treatment search: {disease_treatment_query}")

            disease_results = await hybrid_search_products(
                query=disease_treatment_query,
                match_count=15,
                vector_weight=0.5,
                keyword_weight=0.5
            )

            if disease_results:
                all_results.extend(disease_results)
                logger.info(f"   → Found {len(disease_results)} disease treatment products")

        # 2. Calculate Matching Score for each product
        scored_products = []
        seen_products = set()

        for product in all_results:
            pname = product.get("product_name", "")
            if not pname or pname in seen_products:
                continue
            seen_products.add(pname)

            # Skip products without target_pest
            if not product.get("target_pest"):
                continue

            # Calculate matching score
            match_score = calculate_matching_score(
                product=product,
                disease_name=disease_name,
                plant_type=plant_type,
                growth_stage=growth_stage
            )

            # Combine hybrid score with matching score
            hybrid_score = product.get("hybrid_score", product.get("similarity", 0))

            # Final score: 50% matching + 50% hybrid (search relevance)
            final_score = (match_score * 0.5) + (hybrid_score * 0.5)

            product["matching_score"] = match_score
            product["final_score"] = final_score

            scored_products.append(product)

        # 3. Sort by final score
        scored_products.sort(key=lambda x: x.get("final_score", 0), reverse=True)

        # Log top products
        logger.info(f"📊 Top products by Matching Score:")
        for p in scored_products[:5]:
            logger.info(f"   → {p.get('product_name')}: "
                       f"match={p.get('matching_score', 0):.2f}, "
                       f"final={p.get('final_score', 0):.2f}")

        # 4. Filter and build recommendations
        # Keep products with reasonable score (>0.15) or top 6
        min_score = 0.15
        filtered_products = [p for p in scored_products if p.get("final_score", 0) >= min_score]

        if len(filtered_products) < 3:
            # If too few pass threshold, take top 6 anyway
            filtered_products = scored_products[:6]
        else:
            filtered_products = filtered_products[:6]

        if not filtered_products:
            logger.warning("⚠️ No products found with matching score")
            return []

        # Build recommendations
        recommendations = []
        for product in filtered_products:
            rec = ProductRecommendation(
                product_name=product.get("product_name", "ไม่ระบุชื่อ"),
                active_ingredient=product.get("active_ingredient", ""),
                target_pest=product.get("target_pest", ""),
                applicable_crops=product.get("applicable_crops", ""),
                how_to_use=product.get("how_to_use", ""),
                usage_period=product.get("usage_period", ""),
                usage_rate=product.get("usage_rate", ""),
                link_product=product.get("link_product", ""),
                score=product.get("final_score", 0)
            )
            recommendations.append(rec)

        logger.info(f"✓ Returning {len(recommendations)} products with matching score")
        return recommendations

    except Exception as e:
        logger.error(f"Error in retrieve_products_with_matching_score: {e}", exc_info=True)
        return []


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
