"""
Disease Search Service
RAG + Vector Search สำหรับค้นหาโรคพืชที่เกี่ยวข้อง
"""

import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

from app.services.services import supabase_client, openai_client
from app.services.quick_classifier import ClassificationResult, ProblemCategory

logger = logging.getLogger(__name__)


@dataclass
class DiseaseMatch:
    """ผลลัพธ์การค้นหาโรค"""
    id: int
    disease_key: str
    name_th: str
    name_en: str
    category: str
    pathogen: str
    symptoms: List[str]
    key_features: List[str]
    distinguish_from: str
    severity_indicators: Dict
    similarity: float


def _parse_list_field(data) -> List[str]:
    """
    Parse a field that could be list of str, list of dict, or JSON string.
    Extracts 'th' or 'en' from dicts, converts to list of strings.
    """
    if data is None:
        return []
    if isinstance(data, str):
        try:
            data = eval(data)
        except:
            return [data]
    if not isinstance(data, list):
        return []
    # Handle list of dicts: extract 'th' or 'en' value
    result = []
    for item in data:
        if isinstance(item, dict):
            result.append(item.get('th', item.get('en', str(item))))
        elif isinstance(item, str):
            result.append(item)
        else:
            result.append(str(item))
    return result


async def generate_search_embedding(text: str) -> List[float]:
    """Generate embedding for search query"""
    if not openai_client:
        logger.error("OpenAI client not available")
        return []

    try:
        response = await openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
            encoding_format="float"
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}")
        return []


async def search_diseases(
    classification: ClassificationResult,
    top_k: int = 5
) -> List[DiseaseMatch]:
    """
    Search for relevant diseases based on classification result.
    Uses hybrid search (Vector + Keyword).

    Args:
        classification: ผลจาก quick_classify()
        top_k: จำนวนโรคที่ต้องการ

    Returns:
        List of DiseaseMatch sorted by relevance
    """
    if not supabase_client or not openai_client:
        logger.warning("Supabase or OpenAI client not available")
        return []

    try:
        # Build search query from classification
        search_parts = []

        # Add plant type if known
        if classification.plant_type:
            search_parts.append(classification.plant_type)

        # Add keywords
        if classification.keywords:
            search_parts.extend(classification.keywords)

        # Add summary
        if classification.summary:
            search_parts.append(classification.summary)

        # Add category in Thai
        category_map = {
            ProblemCategory.FUNGAL: "โรคเชื้อรา",
            ProblemCategory.BACTERIAL: "โรคแบคทีเรีย",
            ProblemCategory.VIRAL: "โรคไวรัส",
            ProblemCategory.INSECT: "แมลงศัตรูพืช",
            ProblemCategory.NUTRIENT: "ขาดธาตุอาหาร",
            ProblemCategory.WEED: "วัชพืช",
        }
        if classification.category in category_map:
            search_parts.append(category_map[classification.category])

        search_query = " ".join(search_parts)

        if not search_query.strip():
            logger.warning("Empty search query, skipping search")
            return []

        logger.info(f"Searching diseases: '{search_query[:80]}...' (category: {classification.category.value})")

        # Generate embedding
        query_embedding = await generate_search_embedding(search_query)
        if not query_embedding:
            logger.warning("Failed to generate embedding, trying keyword search only")
            return await _keyword_search_fallback(search_query, classification.category, top_k)

        # Map category for filter
        filter_category = None
        if classification.category not in [ProblemCategory.UNKNOWN, ProblemCategory.HEALTHY]:
            filter_category = classification.category.value

        # Try hybrid search first
        try:
            result = supabase_client.rpc(
                'hybrid_search_diseases',
                {
                    'query_embedding': query_embedding,
                    'search_query': search_query,
                    'vector_weight': 0.6,
                    'keyword_weight': 0.4,
                    'match_threshold': 0.25,
                    'match_count': top_k,
                    'filter_category': filter_category
                }
            ).execute()

            if result.data:
                logger.info(f"Found {len(result.data)} diseases via hybrid search")
                return _parse_search_results(result.data, use_hybrid_score=True)

        except Exception as e:
            logger.warning(f"Hybrid search failed: {e}, falling back to vector search")

        # Fallback to vector search only
        result = supabase_client.rpc(
            'match_diseases',
            {
                'query_embedding': query_embedding,
                'match_threshold': 0.25,
                'match_count': top_k,
                'filter_category': filter_category
            }
        ).execute()

        if result.data:
            logger.info(f"Found {len(result.data)} diseases via vector search")
            return _parse_search_results(result.data, use_hybrid_score=False)

        # No results, try without category filter
        if filter_category:
            logger.info("No results with category filter, trying without filter")
            result = supabase_client.rpc(
                'match_diseases',
                {
                    'query_embedding': query_embedding,
                    'match_threshold': 0.20,
                    'match_count': top_k,
                    'filter_category': None
                }
            ).execute()

            if result.data:
                logger.info(f"Found {len(result.data)} diseases without category filter")
                return _parse_search_results(result.data, use_hybrid_score=False)

        logger.warning("No diseases found in vector search")
        return []

    except Exception as e:
        logger.error(f"Disease search failed: {e}", exc_info=True)
        return []


async def _keyword_search_fallback(
    search_query: str,
    category: ProblemCategory,
    top_k: int
) -> List[DiseaseMatch]:
    """Fallback to keyword search when vector search fails"""
    try:
        filter_category = None
        if category not in [ProblemCategory.UNKNOWN, ProblemCategory.HEALTHY]:
            filter_category = category.value

        result = supabase_client.rpc(
            'keyword_search_diseases',
            {
                'search_query': search_query,
                'match_count': top_k,
                'filter_category': filter_category
            }
        ).execute()

        if result.data:
            logger.info(f"Found {len(result.data)} diseases via keyword search")
            return [
                DiseaseMatch(
                    id=d['id'],
                    disease_key=d['disease_key'],
                    name_th=d['name_th'],
                    name_en=d['name_en'],
                    category=d['category'],
                    pathogen=d.get('pathogen', ''),
                    symptoms=_parse_list_field(d.get('symptoms', [])),
                    key_features=_parse_list_field(d.get('key_features', [])),
                    distinguish_from='',
                    severity_indicators={},
                    similarity=d.get('rank_score', 0.5)
                )
                for d in result.data
            ]

        return []

    except Exception as e:
        logger.error(f"Keyword search fallback failed: {e}")
        return []


def _parse_search_results(data: List[Dict], use_hybrid_score: bool) -> List[DiseaseMatch]:
    """Parse search results into DiseaseMatch objects"""
    results = []
    for d in data:
        # Get similarity score
        if use_hybrid_score:
            similarity = d.get('hybrid_score', 0)
        else:
            similarity = d.get('similarity', 0)

        # Parse symptoms and key_features using helper function
        symptoms = _parse_list_field(d.get('symptoms', []))
        key_features = _parse_list_field(d.get('key_features', []))

        # Parse severity_indicators
        severity_indicators = d.get('severity_indicators', {})
        if isinstance(severity_indicators, str):
            try:
                severity_indicators = eval(severity_indicators)
            except:
                severity_indicators = {}
        if not isinstance(severity_indicators, dict):
            severity_indicators = {}

        results.append(DiseaseMatch(
            id=d['id'],
            disease_key=d['disease_key'],
            name_th=d['name_th'],
            name_en=d['name_en'],
            category=d['category'],
            pathogen=d.get('pathogen', ''),
            symptoms=symptoms,
            key_features=key_features,
            distinguish_from=d.get('distinguish_from', ''),
            severity_indicators=severity_indicators,
            similarity=similarity
        ))

    return results


def build_context_from_diseases(diseases: List[DiseaseMatch]) -> str:
    """
    Build context prompt from matched diseases.
    ใช้เป็น RAG context สำหรับ Gemini

    Args:
        diseases: List of matched diseases

    Returns:
        Formatted string for prompt context
    """
    if not diseases:
        return ""

    context_parts = [
        "## โรค/ปัญหาที่เกี่ยวข้อง (จากฐานข้อมูล):\n",
        "เปรียบเทียบภาพกับโรคต่อไปนี้และเลือกที่ตรงที่สุด:\n"
    ]

    for i, d in enumerate(diseases[:5], 1):
        # Header
        context_parts.append(f"### {i}. {d.name_th} ({d.name_en})")

        # Category in Thai
        category_map = {
            'fungal': 'โรคเชื้อรา',
            'bacterial': 'โรคแบคทีเรีย',
            'viral': 'โรคไวรัส',
            'insect': 'แมลงศัตรูพืช',
            'nutrient': 'ขาดธาตุอาหาร',
            'weed': 'วัชพืช'
        }
        context_parts.append(f"- **หมวดหมู่**: {category_map.get(d.category, d.category)}")

        # Pathogen
        if d.pathogen:
            context_parts.append(f"- **สาเหตุ**: {d.pathogen}")

        # Symptoms (top 3)
        if d.symptoms:
            symptoms_str = "; ".join(d.symptoms[:3])
            context_parts.append(f"- **อาการ**: {symptoms_str}")

        # Key features (top 2)
        if d.key_features:
            features_str = "; ".join(d.key_features[:2])
            context_parts.append(f"- **ลักษณะเด่น**: {features_str}")

        # Distinguish from
        if d.distinguish_from:
            context_parts.append(f"- **แยกจาก**: {d.distinguish_from}")

        # Similarity score
        context_parts.append(f"- **ความใกล้เคียง**: {d.similarity:.2f}")

        context_parts.append("")  # Empty line

    return "\n".join(context_parts)


async def search_diseases_by_text(
    query: str,
    top_k: int = 5
) -> List[DiseaseMatch]:
    """
    Search diseases by text query (without image classification).
    สำหรับคำถามเรื่องพืช/โรคพืชจาก chat

    Args:
        query: คำถามหรือคำค้นหา เช่น "ข้าวระยะไหนเสี่ยง", "โรคทุเรียน"
        top_k: จำนวนผลลัพธ์

    Returns:
        List of DiseaseMatch
    """
    if not supabase_client or not openai_client:
        logger.warning("Supabase or OpenAI client not available")
        return []

    try:
        logger.info(f"Searching diseases by text: '{query[:50]}...'")

        # Generate embedding
        query_embedding = await generate_search_embedding(query)
        if not query_embedding:
            logger.warning("Failed to generate embedding, trying keyword search")
            # Fallback to keyword search
            result = supabase_client.rpc(
                'keyword_search_diseases',
                {
                    'search_query': query,
                    'match_count': top_k,
                    'filter_category': None
                }
            ).execute()

            if result.data:
                return _parse_search_results(result.data, use_hybrid_score=False)
            return []

        # Try hybrid search first
        try:
            result = supabase_client.rpc(
                'hybrid_search_diseases',
                {
                    'query_embedding': query_embedding,
                    'search_query': query,
                    'vector_weight': 0.5,
                    'keyword_weight': 0.5,
                    'match_threshold': 0.20,  # Lower threshold for text queries
                    'match_count': top_k,
                    'filter_category': None
                }
            ).execute()

            if result.data:
                logger.info(f"Found {len(result.data)} diseases via hybrid search")
                return _parse_search_results(result.data, use_hybrid_score=True)
        except Exception as e:
            logger.warning(f"Hybrid search failed: {e}")

        # Fallback to vector search
        result = supabase_client.rpc(
            'match_diseases',
            {
                'query_embedding': query_embedding,
                'match_threshold': 0.20,
                'match_count': top_k,
                'filter_category': None
            }
        ).execute()

        if result.data:
            logger.info(f"Found {len(result.data)} diseases via vector search")
            return _parse_search_results(result.data, use_hybrid_score=False)

        logger.warning("No diseases found")
        return []

    except Exception as e:
        logger.error(f"Disease text search failed: {e}", exc_info=True)
        return []


async def get_disease_by_key(disease_key: str) -> Optional[DiseaseMatch]:
    """Get a specific disease by its key"""
    if not supabase_client:
        return None

    try:
        result = supabase_client.table('diseases').select('*').eq(
            'disease_key', disease_key
        ).eq('is_active', True).limit(1).execute()

        if result.data:
            d = result.data[0]
            return DiseaseMatch(
                id=d['id'],
                disease_key=d['disease_key'],
                name_th=d['name_th'],
                name_en=d['name_en'],
                category=d['category'],
                pathogen=d.get('pathogen', ''),
                symptoms=_parse_list_field(d.get('symptoms', [])),
                key_features=_parse_list_field(d.get('key_features', [])),
                distinguish_from=d.get('distinguish_from', ''),
                severity_indicators=d.get('severity_indicators', {}),
                similarity=1.0
            )

        return None

    except Exception as e:
        logger.error(f"Failed to get disease by key: {e}")
        return None


async def get_all_diseases(
    category: Optional[str] = None,
    limit: int = 100
) -> List[DiseaseMatch]:
    """Get all diseases, optionally filtered by category"""
    if not supabase_client:
        return []

    try:
        query = supabase_client.table('diseases').select('*').eq('is_active', True)

        if category:
            query = query.eq('category', category)

        result = query.order('name_th').limit(limit).execute()

        if result.data:
            return _parse_search_results(result.data, use_hybrid_score=False)

        return []

    except Exception as e:
        logger.error(f"Failed to get all diseases: {e}")
        return []
