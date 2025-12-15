"""
Re-ranking module using Cross-Encoder for higher accuracy
Uses GPT-4o-mini for Thai language support (better than sentence-transformers for Thai)
"""
import logging
from typing import List, Dict, Optional, Tuple
import asyncio

logger = logging.getLogger(__name__)


async def rerank_products_with_llm(
    query: str,
    products: List[Dict],
    top_k: int = 6,
    openai_client=None,
    required_category: str = None,
    required_category_th: str = None
) -> List[Dict]:
    """
    Re-rank products using GPT-4o-mini as cross-encoder
    This provides better Thai language understanding than traditional cross-encoders

    Parameters:
    - query: The search query
    - products: List of candidate products from hybrid search
    - top_k: Number of top results to return
    - openai_client: OpenAI async client
    - required_category: Required product category (fungicide/insecticide/herbicide)
    - required_category_th: Thai name of required category

    Returns:
    - Re-ranked list of products
    """
    try:
        if not openai_client:
            logger.warning("OpenAI client not available for re-ranking, returning original order")
            return products[:top_k]

        if len(products) <= top_k:
            logger.info(f"Only {len(products)} products, skipping re-ranking")
            return products

        logger.info(f"🔄 Re-ranking {len(products)} products for query: '{query}'")

        # Prepare product summaries for re-ranking (limit to top 15 candidates)
        candidates = products[:15]
        product_texts = []
        for i, p in enumerate(candidates, 1):
            text = f"[{i}] {p.get('product_name', 'N/A')}"
            if p.get('target_pest'):
                text += f" | ศัตรูพืช: {p.get('target_pest', '')[:100]}"
            if p.get('applicable_crops'):
                text += f" | พืช: {p.get('applicable_crops', '')[:80]}"
            if p.get('active_ingredient'):
                text += f" | สาร: {p.get('active_ingredient', '')[:50]}"
            product_texts.append(text)

        products_str = "\n".join(product_texts)

        # Build category constraint text
        category_constraint = ""
        if required_category and required_category_th:
            category_map = {
                "fungicide": "ยาฆ่าเชื้อรา (เช่น propiconazole, difenoconazole, azoxystrobin)",
                "insecticide": "ยาฆ่าแมลง (เช่น cartap, cypermethrin, imidacloprid)",
                "herbicide": "ยาฆ่าวัชพืช (เช่น bispyribac, glyphosate, pretilachlor)"
            }
            category_constraint = f"""

⚠️ สำคัญมาก: คำค้นหานี้ต้องการ **{required_category_th}** เท่านั้น!
- ถ้าเป็นโรคพืช/เชื้อรา → เลือกเฉพาะ {category_map.get('fungicide')}
- ถ้าเป็นแมลง/หนอน/เพลี้ย → เลือกเฉพาะ {category_map.get('insecticide')}
- ถ้าเป็นวัชพืช/หญ้า → เลือกเฉพาะ {category_map.get('herbicide')}

❌ ห้ามจัดอันดับสินค้าที่ไม่ใช่ {required_category_th} ให้อยู่ลำดับต้นๆ"""

        # Cross-encoder prompt for relevance scoring
        prompt = f"""เป็นผู้เชี่ยวชาญจัดอันดับความเกี่ยวข้อง

คำค้นหา: "{query}"
{category_constraint}

รายการผลิตภัณฑ์:
{products_str}

จัดอันดับผลิตภัณฑ์ตามความเกี่ยวข้องกับคำค้นหา โดยพิจารณา:
1. ประเภทสินค้าต้องตรงกับประเภทปัญหา (โรค→ยาฆ่าเชื้อรา, แมลง→ยาฆ่าแมลง, วัชพืช→ยาฆ่าวัชพืช)
2. ศัตรูพืช/โรคที่กำจัดได้ตรงกับที่ค้นหาหรือไม่
3. พืชที่ใช้ได้ตรงกับที่ค้นหาหรือไม่
4. สารสำคัญเหมาะสมกับการกำจัดปัญหาหรือไม่

ตอบเป็นตัวเลขเรียงลำดับจากเกี่ยวข้องมากสุดไปน้อยสุด (เฉพาะหมายเลข คั่นด้วย comma)
เช่น: 3,1,5,2,4

ตอบ:"""

        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",  # Use mini for speed
            messages=[
                {"role": "system", "content": "ตอบเฉพาะตัวเลขเรียงลำดับ คั่นด้วย comma เท่านั้น"},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=100
        )

        ranking_text = response.choices[0].message.content.strip()
        logger.info(f"   Re-ranking response: {ranking_text}")

        # Parse ranking
        try:
            # Extract numbers from response
            import re
            numbers = re.findall(r'\d+', ranking_text)
            ranking_indices = [int(n) - 1 for n in numbers if 0 < int(n) <= len(candidates)]

            # Build re-ranked list
            reranked = []
            seen_indices = set()
            for idx in ranking_indices:
                if idx not in seen_indices and idx < len(candidates):
                    reranked.append(candidates[idx])
                    seen_indices.add(idx)

            # Add any remaining products not in ranking
            for i, p in enumerate(candidates):
                if i not in seen_indices:
                    reranked.append(p)

            logger.info(f"✓ Re-ranked: {[p.get('product_name', '')[:20] for p in reranked[:top_k]]}")
            return reranked[:top_k]

        except Exception as e:
            logger.warning(f"Failed to parse re-ranking: {e}, returning original order")
            return products[:top_k]

    except Exception as e:
        logger.error(f"Re-ranking failed: {e}", exc_info=True)
        return products[:top_k]


async def rerank_with_scores(
    query: str,
    products: List[Dict],
    openai_client=None
) -> List[Tuple[Dict, float]]:
    """
    Re-rank products and return with relevance scores

    Returns list of (product, score) tuples
    """
    try:
        if not openai_client or len(products) == 0:
            return [(p, p.get('similarity', 0.5)) for p in products]

        logger.info(f"🔄 Scoring {len(products)} products for: '{query}'")

        # Limit candidates for efficiency
        candidates = products[:10]

        # Batch scoring prompt
        product_texts = []
        for i, p in enumerate(candidates, 1):
            text = f"[{i}] {p.get('product_name', 'N/A')}"
            if p.get('target_pest'):
                text += f" - {p.get('target_pest', '')[:80]}"
            product_texts.append(text)

        products_str = "\n".join(product_texts)

        prompt = f"""ให้คะแนนความเกี่ยวข้อง 1-10 สำหรับแต่ละผลิตภัณฑ์

คำค้นหา: "{query}"

ผลิตภัณฑ์:
{products_str}

ตอบเป็นคะแนนแต่ละตัว (1-10) คั่นด้วย comma
เช่น: 8,6,9,3,7

คะแนน:"""

        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "ตอบเฉพาะตัวเลขคะแนน คั่นด้วย comma"},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=50
        )

        scores_text = response.choices[0].message.content.strip()

        # Parse scores
        import re
        scores = [float(s) / 10.0 for s in re.findall(r'\d+', scores_text)]

        # Pair products with scores
        scored_products = []
        for i, p in enumerate(candidates):
            score = scores[i] if i < len(scores) else 0.5
            scored_products.append((p, score))

        # Sort by score descending
        scored_products.sort(key=lambda x: x[1], reverse=True)

        logger.info(f"✓ Scored products: {[(p.get('product_name', '')[:15], s) for p, s in scored_products[:5]]}")
        return scored_products

    except Exception as e:
        logger.error(f"Scoring failed: {e}", exc_info=True)
        return [(p, p.get('similarity', 0.5)) for p in products]


# Simple relevance check (lightweight, no LLM)
def simple_relevance_boost(query: str, product: Dict) -> float:
    """
    Quick relevance boost based on exact/partial matches
    Returns bonus score (0.0 to 0.3)
    """
    try:
        bonus = 0.0
        query_lower = query.lower()

        # Check product name match
        product_name = (product.get('product_name') or '').lower()
        if query_lower in product_name:
            bonus += 0.15
        elif any(term in product_name for term in query_lower.split()):
            bonus += 0.05

        # Check target pest match
        target_pest = (product.get('target_pest') or '').lower()
        if query_lower in target_pest:
            bonus += 0.1
        elif any(term in target_pest for term in query_lower.split() if len(term) > 2):
            bonus += 0.03

        # Check applicable crops match
        crops = (product.get('applicable_crops') or '').lower()
        if any(term in crops for term in query_lower.split() if len(term) > 2):
            bonus += 0.05

        return min(bonus, 0.3)  # Cap at 0.3

    except Exception:
        return 0.0
