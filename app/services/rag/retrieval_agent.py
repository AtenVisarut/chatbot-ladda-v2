"""
Retrieval Agent

Responsibilities:
- Multi-query retrieval from products, diseases tables
- De-duplication of results
- Re-ranking with LLM cross-encoder
- Relevance filtering based on threshold
"""

import logging
import asyncio
import re
import hashlib
import time
from typing import List, Dict

from app.services.rag import (
    QueryAnalysis,
    RetrievedDocument,
    RetrievalResult,
    IntentType
)
from app.config import LLM_MODEL_RERANKING, EMBEDDING_MODEL, LLM_TEMP_RERANKING, LLM_TOKENS_RERANKING, PRODUCT_TABLE, PRODUCT_RPC
from app.utils.async_db import aexecute

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_VECTOR_THRESHOLD = 0.25  # Lowered from 0.35 for better recall
DEFAULT_RERANK_THRESHOLD = 0.50
DEFAULT_TOP_K = 10
MIN_RELEVANT_DOCS = 3

# Columns used by _build_doc_from_row — excludes embedding (1536 floats), row_hash, timestamps
_PRODUCT_COLUMNS = (
    "id, product_name, common_name_th, active_ingredient, "
    "fungicides, insecticides, herbicides, biostimulant, pgr_hormones, fertilizer, "
    "applicable_crops, product_category, how_to_use, usage_rate, usage_period, "
    "selling_point, action_characteristics, absorption_method, strategy, "
    "package_size, physical_form, phytotoxicity, chemical_group_rac, caution_notes, aliases"
)

# ============================================================================
# Embedding LRU Cache — avoids re-computing identical embeddings
# ============================================================================
_EMBEDDING_CACHE_MAX = 500
_EMBEDDING_CACHE_TTL = 3600  # 1 hour
_embedding_cache: Dict[str, dict] = {}  # key -> {"embedding": [...], "ts": float}


def _get_cached_embedding(text: str):
    """Return cached embedding list or None"""
    key = hashlib.md5(text.encode()).hexdigest()
    entry = _embedding_cache.get(key)
    if entry and (time.time() - entry["ts"]) < _EMBEDDING_CACHE_TTL:
        return entry["embedding"]
    return None


async def _generate_embedding_standalone(text: str, openai_client) -> list:
    """Generate embedding without RetrievalAgent instance (for semantic cache)."""
    cached = _get_cached_embedding(text)
    if cached is not None:
        return cached
    try:
        from app.config import EMBEDDING_MODEL
        response = await openai_client.embeddings.create(
            model=EMBEDDING_MODEL, input=text, encoding_format="float"
        )
        embedding = response.data[0].embedding
        _set_cached_embedding(text, embedding)
        return embedding
    except Exception:
        return []


def _set_cached_embedding(text: str, embedding: list):
    """Store embedding in cache, evict oldest if full"""
    key = hashlib.md5(text.encode()).hexdigest()
    if len(_embedding_cache) >= _EMBEDDING_CACHE_MAX:
        # Evict oldest 10%
        sorted_keys = sorted(_embedding_cache, key=lambda k: _embedding_cache[k]["ts"])
        for k in sorted_keys[:max(1, len(sorted_keys) // 10)]:
            del _embedding_cache[k]
    _embedding_cache[key] = {"embedding": embedding, "ts": time.time()}


# Broader category mapping: specific plant → parent categories
# Used in Stage 3.65 crop-mismatch and Stage 3.7 priority promotion
# e.g. ทุเรียน is ไม้ยืนต้น, so "ไม้ยืนต้น เช่น ปาล์ม ยาง" should match ทุเรียน
_PLANT_BROADER_CATEGORIES = {
    'ทุเรียน': ['ไม้ยืนต้น', 'ไม้ผล'],
    'มะม่วง': ['ไม้ยืนต้น', 'ไม้ผล'],
    'ลำไย': ['ไม้ยืนต้น', 'ไม้ผล'],
    'มังคุด': ['ไม้ยืนต้น', 'ไม้ผล'],
    'เงาะ': ['ไม้ยืนต้น', 'ไม้ผล'],
    'ลิ้นจี่': ['ไม้ยืนต้น', 'ไม้ผล'],
    'ส้ม': ['ไม้ยืนต้น', 'ไม้ผล'],
    'ยางพารา': ['ไม้ยืนต้น'],
    'ปาล์ม': ['ไม้ยืนต้น'],
    'ปาล์มน้ำมัน': ['ไม้ยืนต้น'],
    'มะพร้าว': ['ไม้ยืนต้น', 'ไม้ผล'],
    'กาแฟ': ['ไม้ยืนต้น'],
    'ข้าว': ['พืชไร่', 'นาข้าว'],
    'ข้าวโพด': ['พืชไร่'],
    'อ้อย': ['พืชไร่'],
    'มันสำปะหลัง': ['พืชไร่'],
    # เพิ่ม 2026-03-19: พืชใหม่
    'ส้มโอ': ['ไม้ยืนต้น', 'ไม้ผล'],
    'มะละกอ': ['ไม้ผล'],
    'แตงโม': ['พืชผัก'],
    'แตงกวา': ['พืชผัก'],
    'ฟักทอง': ['พืชผัก'],
    'องุ่น': ['ไม้ผล'],
    'ลองกอง': ['ไม้ยืนต้น', 'ไม้ผล'],
    'มะม่วงหิมพานต์': ['ไม้ยืนต้น'],
    'ข้าวเหนียว': ['พืชไร่'],
}


# Thai substring disambiguation: prevent "ข้าว" matching "ข้าวโพด", etc.
# Map: short plant name → list of longer plant names that contain it as prefix
_PLANT_FALSE_POSITIVES = {
    'ข้าว': ['ข้าวโพด', 'ข้าวฟ่าง', 'ข้าวเหนียว'],
    'ส้ม': ['ส้มโอ'],
    'กล้วย': ['กล้วยไม้'],
    'มะม่วง': ['มะม่วงหิมพานต์'],
}


def _plant_in_text_boundary(plant_type: str, text: str) -> bool:
    """Check if plant_type appears in text without being part of a longer word.

    e.g. 'ข้าว' should match 'นาข้าว' and 'ข้าว, อ้อย' but NOT 'ข้าวโพด'.
    """
    if plant_type not in text:
        return False
    false_positives = _PLANT_FALSE_POSITIVES.get(plant_type, [])
    if not false_positives:
        return True
    # Check every occurrence of plant_type in text
    start = 0
    while True:
        idx = text.find(plant_type, start)
        if idx == -1:
            return False  # no more occurrences
        # Check if this occurrence is part of a false positive
        remainder = text[idx:]
        is_false_positive = any(remainder.startswith(fp) for fp in false_positives)
        if not is_false_positive:
            return True  # genuine match found
        start = idx + len(plant_type)


def _plant_matches_crops(plant_type: str, crops_str: str) -> bool:
    """Check if plant_type matches crops string (direct or via broader category).

    Uses boundary-aware matching to avoid false positives like ข้าว→ข้าวโพด.
    """
    if _plant_in_text_boundary(plant_type, crops_str):
        return True
    for cat in _PLANT_BROADER_CATEGORIES.get(plant_type, []):
        if cat in crops_str:
            return True
    return False


class RetrievalAgent:
    """
    Agent 2: Retrieval
    Performs multi-query retrieval with re-ranking
    """

    # Category-Intent mapping (single source, used in _search_products + retrieve stages)
    # NOTE: NUTRIENT_SUPPLEMENT covers Biostimulants + PGR (multi-category)
    INTENT_CATEGORY_MAP = {
        IntentType.DISEASE_TREATMENT: "Fungicide",
        IntentType.PEST_CONTROL: "Insecticide",
        IntentType.WEED_CONTROL: "Herbicide",
    }

    # Category variants for reranking stages (includes Thai labels)
    INTENT_CATEGORY_VARIANTS = {
        IntentType.DISEASE_TREATMENT: ["Fungicide", "fungicide", "ป้องกันโรค"],
        IntentType.PEST_CONTROL: ["Insecticide", "insecticide", "กำจัดแมลง"],
        IntentType.WEED_CONTROL: ["Herbicide", "herbicide", "กำจัดวัชพืช"],
        IntentType.NUTRIENT_SUPPLEMENT: ["Biostimulants", "biostimulants", "PGR", "pgr", "Fertilizer", "fertilizer", "บำรุง", "ฮอร์โมน", "ปุ๋ย"],
    }

    def __init__(
        self,
        supabase_client=None,
        openai_client=None,
        vector_threshold: float = DEFAULT_VECTOR_THRESHOLD,
        rerank_threshold: float = DEFAULT_RERANK_THRESHOLD
    ):
        self.supabase = supabase_client
        self.openai_client = openai_client
        self.vector_threshold = vector_threshold
        self.rerank_threshold = rerank_threshold

    @staticmethod
    def _build_doc_from_row(item: dict, similarity: float, content_extra: str = "") -> 'RetrievedDocument':
        """Build a RetrievedDocument from a DB row dict (single source for metadata construction)."""
        common_th = item.get('common_name_th') or ''
        content = (
            f"สินค้า: {item.get('product_name', '')}\n"
            f"ชื่อสารไทย: {common_th}\n"
            f"สารสำคัญ: {item.get('active_ingredient', '')}\n"
            f"สารกำจัดเชื้อรา: {(item.get('fungicides') or '')[:100]}\n"
            f"สารกำจัดแมลง: {(item.get('insecticides') or '')[:100]}\n"
            f"สารกำจัดวัชพืช: {(item.get('herbicides') or '')[:100]}\n"
            f"พืชที่ใช้ได้: {(item.get('applicable_crops') or '')[:200]}"
        )
        if content_extra:
            content += f"\n{content_extra}"
        return RetrievedDocument(
            id=str(item.get('id', '')),
            title=item.get('product_name', ''),
            content=content,
            source="products",
            similarity_score=similarity,
            metadata={
                'product_name': item.get('product_name'),
                'common_name_th': common_th,
                'active_ingredient': item.get('active_ingredient'),
                'fungicides': item.get('fungicides'),
                'insecticides': item.get('insecticides'),
                'herbicides': item.get('herbicides'),
                'biostimulant': item.get('biostimulant'),
                'pgr_hormones': item.get('pgr_hormones'),
                'applicable_crops': item.get('applicable_crops'),
                'category': item.get('product_category') or item.get('category'),
                'how_to_use': item.get('how_to_use'),
                'usage_rate': item.get('usage_rate'),
                'usage_period': item.get('usage_period'),
                'selling_point': item.get('selling_point'),
                'action_characteristics': item.get('action_characteristics'),
                'absorption_method': item.get('absorption_method'),
                'strategy': item.get('strategy'),
                'package_size': item.get('package_size'),
                'physical_form': item.get('physical_form'),
                'phytotoxicity': item.get('phytotoxicity'),
                'chemical_group_rac': item.get('chemical_group_rac'),
                'fertilizer': item.get('fertilizer'),
                'caution_notes': item.get('caution_notes'),
                'aliases': item.get('aliases'),
            }
        )

    @staticmethod
    def _infer_expected_categories(query_analysis):
        """Infer expected categories from entities when intent doesn't specify."""
        entities = query_analysis.entities

        # Priority: pest > disease > weed > query keywords
        if entities.get('pest_name'):
            return ["Insecticide", "insecticide", "กำจัดแมลง"]
        if entities.get('disease_name'):
            return ["Fungicide", "fungicide", "ป้องกันโรค"]
        if entities.get('weed_type'):
            return ["Herbicide", "herbicide", "กำจัดวัชพืช"]

        # Keyword fallback from original query
        query = query_analysis.original_query
        if any(kw in query for kw in ['เพลี้ย','หนอน','ด้วง','แมลง','ไรแดง','ไรขาว','ทริปส์','จักจั่น','บั่ว']):
            return ["Insecticide", "insecticide", "กำจัดแมลง"]
        if any(kw in query for kw in ['โรค','เชื้อรา','ราน้ำ','ราแป้ง','ราสนิม','ราสี','แอนแทรคโนส']):
            return ["Fungicide", "fungicide", "ป้องกันโรค"]
        if any(kw in query for kw in ['วัชพืช','หญ้า','ยาฆ่าหญ้า','กำจัดหญ้า']):
            return ["Herbicide", "herbicide", "กำจัดวัชพืช"]
        # Nutrient/Biostimulant keyword fallback — prevents Fungicide for "บำรุง" queries
        if any(kw in query for kw in ['บำรุง','เร่งดอก','เร่งผล','ติดดอก','ติดผล','ธาตุอาหาร','ขาดธาตุ','ต้นโทรม','ลูกดก','ปุ๋ย']):
            return ["Biostimulants", "biostimulants", "PGR", "pgr", "Fertilizer", "fertilizer", "บำรุง", "ฮอร์โมน"]

        return None

    async def _direct_product_lookup(self, product_name: str) -> List[RetrievedDocument]:
        """Direct database lookup by product name (exact/ilike match)"""
        if not self.supabase:
            return []

        try:
            # Step 1: Exact match first (prevents bundle false positive,
            # e.g. "ไฮซีส" should NOT match "ชุด กล่องม่วง (แอสไปร์ + ไฮซีส)")
            result = await aexecute(self.supabase.table(PRODUCT_TABLE) \
                .select(_PRODUCT_COLUMNS) \
                .eq('product_name', product_name) \
                .limit(5))

            # Step 2: Fallback to ilike if exact match finds nothing
            if not result.data:
                result = await aexecute(self.supabase.table(PRODUCT_TABLE) \
                    .select(_PRODUCT_COLUMNS) \
                    .ilike('product_name', f'%{product_name}%') \
                    .limit(5))

            if not result.data:
                return []

            docs = []
            for item in result.data:
                doc = self._build_doc_from_row(item, similarity=1.0)
                doc.rerank_score = 1.0
                docs.append(doc)

            logger.info(f"    Direct lookup: {len(docs)} docs for '{product_name}'")
            return docs

        except Exception as e:
            logger.error(f"Direct product lookup error: {e}")
            return []

    async def _fallback_keyword_search(self, query: str, top_k: int = 5) -> List[RetrievedDocument]:
        """Fallback keyword search when vector search returns no results"""
        if not self.supabase:
            return []

        try:
            # Extract potential keywords from query
            keywords = re.findall(r'[\u0E00-\u0E7F]+|[a-zA-Z]+', query)
            keywords = [kw for kw in keywords if len(kw) >= 3]

            if not keywords:
                return []

            # Build OR filter for ilike search
            or_conditions = []
            from app.utils.pest_columns import build_pest_or_conditions
            for kw in keywords[:3]:  # Limit to 3 keywords
                or_conditions.append(f"product_name.ilike.%{kw}%")
                or_conditions.extend(build_pest_or_conditions(kw))
                or_conditions.append(f"active_ingredient.ilike.%{kw}%")
                or_conditions.append(f"common_name_th.ilike.%{kw}%")

            or_filter = ",".join(or_conditions)

            result = await aexecute(self.supabase.table(PRODUCT_TABLE) \
                .select(_PRODUCT_COLUMNS) \
                .or_(or_filter) \
                .limit(top_k))

            if not result.data:
                return []

            docs = [self._build_doc_from_row(item, similarity=0.5) for item in result.data]

            logger.info(f"    Fallback keyword search: {len(docs)} docs for '{query[:30]}...'")
            return docs

        except Exception as e:
            logger.error(f"Fallback keyword search error: {e}")
            return []

    async def _supplementary_priority_search(
        self, query_analysis: QueryAnalysis, existing_docs: List[RetrievedDocument], top_k: int = 5
    ) -> List[RetrievedDocument]:
        """Search for Skyrocket/Expand products matching query entities (always runs)"""
        if not self.supabase:
            return []

        try:
            # Build keywords from query analysis entities + expanded queries
            keywords = []
            entities = query_analysis.entities
            for key in ['pest_name', 'disease_name', 'plant_type', 'symptom', 'growth_stage']:
                val = entities.get(key)
                if val:
                    if isinstance(val, list):
                        keywords.extend(val)
                    else:
                        keywords.append(str(val))

            # Also extract from expanded queries (LLM-generated)
            for eq in query_analysis.expanded_queries[:3]:
                # Split by spaces (expanded queries usually have spaces)
                parts = eq.split()
                for p in parts:
                    if len(p) >= 3 and p not in keywords:
                        keywords.append(p)

            # Deduplicate and limit
            seen = set()
            unique_kw = []
            for kw in keywords:
                if kw not in seen and len(kw) >= 2:
                    seen.add(kw)
                    unique_kw.append(kw)
            keywords = unique_kw[:6]

            if not keywords:
                return []

            logger.info(f"    Supplementary priority search keywords: {keywords}")

            # Search Skyrocket/Expand products matching keywords in pest columns or selling_point
            from app.utils.pest_columns import build_pest_or_conditions
            or_conditions = []
            for kw in keywords:
                or_conditions.extend(build_pest_or_conditions(kw))
                or_conditions.append(f"selling_point.ilike.%{kw}%")
                or_conditions.append(f"common_name_th.ilike.%{kw}%")
                or_conditions.append(f"active_ingredient.ilike.%{kw}%")
                or_conditions.append(f"applicable_crops.ilike.%{kw}%")

            or_filter = ",".join(or_conditions)

            # Apply category filter if intent requires specific product type
            cat_filter = self.INTENT_CATEGORY_MAP.get(query_analysis.intent)
            if not cat_filter:
                inferred = self._infer_expected_categories(query_analysis)
                if inferred:
                    cat_filter = inferred[0]

            query_builder = self.supabase.table(PRODUCT_TABLE) \
                .select(_PRODUCT_COLUMNS) \
                .in_('strategy', ['Skyrocket', 'Expand']) \
                .or_(or_filter) \
                .limit(top_k)
            if cat_filter:
                query_builder = query_builder.ilike('product_category', f'%{cat_filter}%')
            result = await aexecute(query_builder)

            if not result.data:
                return []

            existing_ids = {d.id for d in existing_docs}
            docs = []
            for item in result.data:
                doc_id = str(item.get('id', ''))
                if doc_id in existing_ids:
                    continue  # Skip duplicates

                selling_extra = f"จุดเด่น: {(item.get('selling_point') or '')[:200]}"
                doc = self._build_doc_from_row(item, similarity=0.35, content_extra=selling_extra)
                docs.append(doc)

            if docs:
                logger.info(f"    Supplementary priority search: {len(docs)} Skyrocket/Expand docs found")
            return docs

        except Exception as e:
            logger.error(f"Supplementary priority search error: {e}")
            return []

    async def _weed_category_fallback_search(
        self, query_analysis: QueryAnalysis, existing_docs: List[RetrievedDocument], top_k: int = 20
    ) -> List[RetrievedDocument]:
        """Search ALL Herbicide products when weed query has insufficient results.

        Unlike _supplementary_priority_search (Skyrocket/Expand only), this catches
        Natural/Standard herbicides too.  top_k=20 to ensure all herbicides are retrieved
        (DB has 11+ herbicides, limit too low causes crop-matching products like พาสนาว to be missed).
        """
        if not self.supabase:
            return []

        try:
            keywords = []
            plant_type = query_analysis.entities.get('plant_type', '')
            if plant_type:
                keywords.append(plant_type)
            keywords.extend(['วัชพืช', 'หญ้า'])

            # Build OR filter on pest columns, applicable_crops, selling_point
            from app.utils.pest_columns import build_pest_or_conditions
            or_conditions = []
            for kw in keywords:
                or_conditions.extend(build_pest_or_conditions(kw))
                or_conditions.append(f"applicable_crops.ilike.%{kw}%")
                or_conditions.append(f"selling_point.ilike.%{kw}%")
            or_filter = ",".join(or_conditions)

            existing_ids = {d.id for d in existing_docs}

            result = await aexecute(self.supabase.table(PRODUCT_TABLE) \
                .select(_PRODUCT_COLUMNS) \
                .ilike('product_category', '%Herbicide%') \
                .or_(or_filter) \
                .limit(top_k))

            if not result.data:
                return []

            docs = []
            for item in result.data:
                doc_id = str(item.get('id', ''))
                if doc_id in existing_ids:
                    continue
                selling_extra = f"จุดเด่น: {(item.get('selling_point') or '')[:200]}"
                doc = self._build_doc_from_row(item, similarity=0.50, content_extra=selling_extra)
                docs.append(doc)

            if docs:
                logger.info(f"    Weed category fallback: {len(docs)} Herbicide docs found")
            return docs

        except Exception as e:
            logger.error(f"Weed category fallback search error: {e}")
            return []

    async def _pest_column_fallback_search(
        self, query_analysis: QueryAnalysis, existing_docs: List[RetrievedDocument], top_k: int = 10
    ) -> List[RetrievedDocument]:
        """Search Insecticide products by pest_name in insecticides column.

        Triggered when PEST_CONTROL query has a specific pest_name but
        none of the retrieved docs mention it in their insecticides text.
        This catches products that vector search missed.
        """
        if not self.supabase:
            return []

        pest_name = query_analysis.entities.get('pest_name', '')
        if not pest_name:
            return []

        # Skip broad terms — they match everything, no targeted fallback needed
        _BROAD = {'แมลง', 'ศัตรูพืช', 'แมลงศัตรูพืช'}
        if pest_name in _BROAD:
            return []

        try:
            from app.utils.pest_columns import build_pest_or_conditions
            or_conditions = build_pest_or_conditions(pest_name)
            if not or_conditions:
                return []
            or_filter = ",".join(or_conditions)

            existing_ids = {d.id for d in existing_docs}

            result = await aexecute(self.supabase.table(PRODUCT_TABLE) \
                .select(_PRODUCT_COLUMNS) \
                .ilike('product_category', '%Insecticide%') \
                .or_(or_filter) \
                .limit(top_k))

            if not result.data:
                return []

            docs = []
            for item in result.data:
                doc_id = str(item.get('id', ''))
                if doc_id in existing_ids:
                    continue
                # Verify pest_name actually appears in insecticides text
                ins_text = (item.get('insecticides') or '').lower()
                if pest_name.lower() not in ins_text:
                    continue
                selling_extra = f"จุดเด่น: {(item.get('selling_point') or '')[:200]}"
                doc = self._build_doc_from_row(item, similarity=0.35, content_extra=selling_extra)
                docs.append(doc)

            if docs:
                logger.info(f"    Pest column fallback: {len(docs)} Insecticide docs matching '{pest_name}'")
            return docs

        except Exception as e:
            logger.error(f"Pest column fallback search error: {e}")
            return []

    async def _enrich_strategy(self, docs: List[RetrievedDocument]):
        """Fetch strategy, selling_point, applicable_crops from DB for docs missing them (e.g. from RPC)"""
        if not self.supabase:
            return

        # Find docs missing strategy or selling_point (RPC doesn't return these)
        missing_ids = [
            doc.id for doc in docs
            if doc.id and (not doc.metadata.get('strategy') or not doc.metadata.get('selling_point'))
        ]
        if not missing_ids:
            return

        try:
            result = await aexecute(self.supabase.table(PRODUCT_TABLE) \
                .select('id, strategy, selling_point, applicable_crops, package_size') \
                .in_('id', [int(i) for i in set(missing_ids) if i.isdigit()]))

            if result.data:
                enrich_map = {str(r['id']): r for r in result.data}
                enriched = 0
                for doc in docs:
                    if doc.id in enrich_map:
                        r = enrich_map[doc.id]
                        if r.get('strategy') and not doc.metadata.get('strategy'):
                            doc.metadata['strategy'] = r['strategy']
                        if r.get('selling_point') and not doc.metadata.get('selling_point'):
                            doc.metadata['selling_point'] = r['selling_point']
                        if r.get('applicable_crops') and not doc.metadata.get('applicable_crops'):
                            doc.metadata['applicable_crops'] = r['applicable_crops']
                        if r.get('package_size') and not doc.metadata.get('package_size'):
                            doc.metadata['package_size'] = r['package_size']
                        enriched += 1
                logger.info(f"  - Enriched metadata for {enriched} docs (from {len(enrich_map)} DB rows)")
        except Exception as e:
            logger.warning(f"Metadata enrichment failed: {e}")

    async def retrieve(
        self,
        query_analysis: QueryAnalysis,
        top_k: int = DEFAULT_TOP_K,
        prefetch_docs: list = None,
        skip_rerank: bool = False
    ) -> RetrievalResult:
        """
        Perform retrieval based on query analysis

        Stages:
        1. Initial retrieval (parallel from multiple sources)
        2. De-duplication
        3. Re-ranking with LLM
        4. Relevance filtering

        Returns:
            RetrievalResult with ranked documents
        """
        try:
            logger.info(f"RetrievalAgent: Starting retrieval for '{query_analysis.original_query[:50]}...'")
            logger.info(f"  - Intent: {query_analysis.intent}")
            logger.info(f"  - Sources: {query_analysis.required_sources}")
            logger.info(f"  - Expanded queries: {len(query_analysis.expanded_queries)}")

            # Stage 0: Direct product lookup if entity has product_name(s)
            all_docs = []
            # Inject pre-fetched docs from parallel embedding (started during Agent 1)
            if prefetch_docs:
                all_docs.extend(prefetch_docs)
                logger.info(f"  - Injected {len(prefetch_docs)} pre-fetched docs")
            direct_lookup_ids = set()
            symptom_fallback_ids = set()
            pest_fallback_ids = set()
            product_name = query_analysis.entities.get('product_name')
            # Support multi-product queries (e.g. "แกนเตอร์กับแมสฟอดใช้ต่างกันยังไง")
            product_names_list = query_analysis.entities.get('product_names', [])
            if not product_names_list and product_name:
                product_names_list = [product_name]
            for _pname in product_names_list:
                direct_docs = await self._direct_product_lookup(_pname)
                if direct_docs:
                    all_docs.extend(direct_docs)
                    direct_lookup_ids.update(doc.id for doc in direct_docs)
            if direct_lookup_ids:
                logger.info(f"  - Direct lookup found: {len(direct_lookup_ids)} docs for {product_names_list}")

            # Stage 1: Parallel retrieval from multiple sources
            multi_docs = await self._multi_source_retrieval(query_analysis, top_k)
            all_docs.extend(multi_docs)

            # Stage 1.2: Consolidated disease fallback (runs ONCE after all vector searches)
            # Checks if disease is in any retrieved doc's target_pest
            # If not, does a single direct DB lookup instead of per-query fallbacks
            disease_fallback_ids = set()
            if query_analysis.intent in (IntentType.DISEASE_TREATMENT, IntentType.PRODUCT_RECOMMENDATION):
                from app.utils.text_processing import generate_thai_disease_variants

                # Collect all disease names to check (entity + original query)
                disease_names_to_check = set()
                entity_disease = query_analysis.entities.get('disease_name', '')
                if entity_disease:
                    disease_names_to_check.add(entity_disease)
                original_disease = self._extract_disease_from_query(query_analysis.original_query)
                if original_disease:
                    disease_names_to_check.add(original_disease)

                # Split combined disease names like "ใบจุดและใบขีดสีน้ำตาล" → ["ใบจุด", "ใบขีดสีน้ำตาล"]
                _split_names = set()
                for dname in list(disease_names_to_check):
                    for sep in ['และ', 'กับ', ',']:
                        if sep in dname:
                            parts = [p.strip() for p in dname.split(sep) if p.strip() and len(p.strip()) >= 3]
                            _split_names.update(parts)
                if _split_names:
                    disease_names_to_check.update(_split_names)
                    logger.info(f"  - Disease split: added {_split_names} from combined names")

                if disease_names_to_check:
                    # Broad disease terms — search by category instead of literal text
                    _BROAD_DISEASE_TERMS = {'เชื้อรา', 'โรคเชื้อรา', 'โรคพืช', 'โรคราพืช'}
                    _is_broad_disease = any(d in _BROAD_DISEASE_TERMS for d in disease_names_to_check)

                    if _is_broad_disease:
                        # Broad disease: search Fungicide category + crop filter
                        plant_type = query_analysis.entities.get('plant_type', '')
                        logger.info(f"  - Disease fallback: broad term {disease_names_to_check}, searching Fungicide category" +
                                    (f" for crop '{plant_type}'" if plant_type else ""))
                        fallback_docs = await self._broad_disease_category_search(plant_type, all_docs)
                        if fallback_docs:
                            disease_fallback_ids = {doc.id for doc in fallback_docs}
                            all_docs.extend(fallback_docs)
                            logger.info(f"  - Broad disease fallback found: {len(fallback_docs)} Fungicide products")
                    else:
                        # Build combined variants from all disease names
                        all_variants = []
                        for d in disease_names_to_check:
                            all_variants.extend(generate_thai_disease_variants(d))
                        all_variants = list(set(all_variants))

                        # Check if any existing doc already matches
                        from app.utils.pest_columns import get_pest_text_lower
                        has_disease_in_docs = any(
                            any(v.lower() in get_pest_text_lower(doc.metadata) for v in all_variants)
                            for doc in all_docs
                        ) if all_docs else False

                        if not has_disease_in_docs:
                            logger.info(f"  - Disease fallback: {disease_names_to_check} not in retrieved docs, searching pest columns")
                            fallback_docs = await self._search_by_target_pest(all_variants, query_analysis)
                            if fallback_docs:
                                disease_fallback_ids = {doc.id for doc in fallback_docs}
                                all_docs.extend(fallback_docs)
                                logger.info(f"  - Disease fallback found: {len(fallback_docs)} products via pest columns")

            # Stage 1.3: Symptom-based pest columns fallback
            # Matches symptom phrases (ไม่โต, ไม่กินปุ๋ย, เหลือง, etc.) against DB pest columns
            if query_analysis.intent in (
                IntentType.NUTRIENT_SUPPLEMENT, IntentType.PRODUCT_RECOMMENDATION,
                IntentType.GENERAL_AGRICULTURE, IntentType.UNKNOWN,
            ):
                symptom_docs = await self._search_by_symptom_keywords(
                    query_analysis.original_query, query_analysis
                )
                if symptom_docs:
                    existing_ids = {d.id for d in all_docs}
                    new_docs = [d for d in symptom_docs if d.id not in existing_ids]
                    if new_docs:
                        symptom_fallback_ids = {d.id for d in new_docs}
                        all_docs.extend(new_docs)
                        logger.info(f"  - Symptom fallback found: {len(new_docs)} new docs via pest columns")

            # Stage 1.5: Fallback keyword search if insufficient results
            if len(all_docs) < MIN_RELEVANT_DOCS:
                fallback_docs = await self._fallback_keyword_search(query_analysis.original_query, top_k)
                existing_ids = {d.id for d in all_docs}
                new_fallback = [d for d in fallback_docs if d.id not in existing_ids]
                all_docs.extend(new_fallback)
                if new_fallback:
                    logger.info(f"  - Fallback keyword added: {len(new_fallback)} new docs")

            # Stage 1.8: Enrich strategy for docs missing it (RPC doesn't return it)
            await self._enrich_strategy(all_docs)

            # Stage 1.9: Supplementary search for Skyrocket/Expand if none found
            if not direct_lookup_ids:
                priority_docs = await self._supplementary_priority_search(
                    query_analysis, all_docs, top_k
                )
                if priority_docs:
                    all_docs.extend(priority_docs)
                    logger.info(f"  - Supplementary priority search added: {len(priority_docs)} docs")

            # Stage 1.95: Weed category fallback — search ALL Herbicides when still insufficient
            # Trigger for WEED_CONTROL intent OR any query with weed_type entity
            # (LLM sometimes classifies weed queries as PRODUCT_RECOMMENDATION)
            _has_weed_entity = bool(query_analysis.entities.get('weed_type'))
            if (query_analysis.intent == IntentType.WEED_CONTROL or _has_weed_entity) and len(all_docs) < MIN_RELEVANT_DOCS:
                weed_docs = await self._weed_category_fallback_search(query_analysis, all_docs)
                if weed_docs:
                    all_docs.extend(weed_docs)
                    logger.info(f"  - Weed category fallback added: {len(weed_docs)} docs")

            # Stage 1.96: Pest column fallback — search insecticides column for specific pest_name
            # Triggered when vector search missed products that DO target the queried pest
            pest_name = query_analysis.entities.get('pest_name', '')
            if pest_name and query_analysis.intent in (IntentType.PEST_CONTROL, IntentType.PRODUCT_RECOMMENDATION):
                # Count how many retrieved docs mention pest_name in insecticides
                _pest_match_count = sum(
                    1 for d in all_docs
                    if pest_name.lower() in (d.metadata.get('insecticides') or '').lower()
                )
                if _pest_match_count < 3:
                    logger.info(f"  - Stage 1.96: pest_match_count={_pest_match_count} < 3, triggering fallback for '{pest_name}'")
                    pest_fallback_docs = await self._pest_column_fallback_search(query_analysis, all_docs)
                    if pest_fallback_docs:
                        pest_fallback_ids = {d.id for d in pest_fallback_docs}
                        all_docs.extend(pest_fallback_docs)
                        logger.info(f"  - Pest column fallback added: {len(pest_fallback_docs)} docs for '{pest_name}'")

            # Stage 1.97: Fertilizer form-specific fallback
            # "ปุ๋ยเกล็ด" → fetch Fertilizer + physical_form=ผง/เกล็ด (NPK)
            # "ปุ๋ยน้ำ" → fetch Fertilizer + physical_form=น้ำ (บอมส์ ซิงค์/แม็กซ์/ไวท์)
            if query_analysis.intent == IntentType.NUTRIENT_SUPPLEMENT:
                _q_lower = query_analysis.original_query.lower()
                _fert_form = None
                if any(kw in _q_lower for kw in ['ปุ๋ยเกล็ด', 'ปุ๋ยสูตร', 'ปุ๋ยnpk']):
                    _fert_form = ['ผง', 'เกล็ด']
                elif 'ปุ๋ยน้ำ' in _q_lower:
                    _fert_form = ['น้ำ']
                if _fert_form:
                    try:
                        _existing_ids = {d.id for d in all_docs}
                        _q_builder = self.supabase.table(PRODUCT_TABLE) \
                            .select(_PRODUCT_COLUMNS) \
                            .eq('product_category', 'Fertilizer')
                        if len(_fert_form) == 1:
                            _q_builder = _q_builder.eq('physical_form', _fert_form[0])
                        else:
                            _q_builder = _q_builder.in_('physical_form', _fert_form)
                        _fert_result = await aexecute(_q_builder)
                        if _fert_result.data:
                            _fert_docs = [self._build_doc_from_row(item, similarity=0.70)
                                          for item in _fert_result.data
                                          if str(item.get('id')) not in _existing_ids]
                            all_docs.extend(_fert_docs)
                            logger.info(f"  - Fertilizer form fallback: added {len(_fert_docs)} docs for form={_fert_form}")
                    except Exception as e:
                        logger.warning(f"Fertilizer form fallback failed: {e}")

            total_retrieved = len(all_docs)
            logger.info(f"  - Total retrieved: {total_retrieved}")

            if not all_docs:
                return RetrievalResult(
                    documents=[],
                    total_retrieved=0,
                    total_after_rerank=0,
                    avg_similarity=0.0,
                    avg_rerank_score=0.0,
                    sources_used=query_analysis.required_sources
                )

            # Stage 2: De-duplication
            unique_docs = self._deduplicate(all_docs)
            logger.info(f"  - After dedup: {len(unique_docs)}")

            # Stage 3: Re-ranking with LLM
            # Skip rerank when: direct lookup, ≤3 docs, or caller requests skip (Stage 0 confident)
            skip_rerank = skip_rerank or bool(direct_lookup_ids) or len(unique_docs) <= 3
            if skip_rerank:
                logger.info(f"  - Skipping LLM rerank (direct_lookup={bool(direct_lookup_ids)}, docs={len(unique_docs)})")

            if self.openai_client and len(unique_docs) >= MIN_RELEVANT_DOCS and not skip_rerank:
                reranked_docs = await self._rerank_with_llm(
                    query_analysis.original_query,
                    unique_docs,
                    query_analysis.intent
                )
            else:
                # Sort by similarity score if no LLM
                reranked_docs = sorted(unique_docs, key=lambda x: x.similarity_score, reverse=True)
                # Assign baseline rerank_score so downstream stages don't break
                for doc in reranked_docs:
                    if doc.rerank_score == 0.0:
                        doc.rerank_score = doc.similarity_score

            # Stage 3.5: Boost direct lookup docs to top (user asked about specific product)
            if direct_lookup_ids:
                boosted = [doc for doc in reranked_docs if doc.id in direct_lookup_ids]
                others = [doc for doc in reranked_docs if doc.id not in direct_lookup_ids]
                reranked_docs = boosted + others
                logger.info(f"  - Boosted {len(boosted)} direct lookup docs to top")

            # Stage 3.52: Boost disease fallback docs to top (matched via pest columns directly)
            if disease_fallback_ids:
                boosted = [doc for doc in reranked_docs if doc.id in disease_fallback_ids]
                others = [doc for doc in reranked_docs if doc.id not in disease_fallback_ids]
                reranked_docs = boosted + others
                if boosted:
                    logger.info(f"  - Boosted {len(boosted)} disease fallback docs to top")

            # Stage 3.53: Boost symptom fallback docs to top (matched via pest column symptom keywords)
            if symptom_fallback_ids:
                boosted = [doc for doc in reranked_docs if doc.id in symptom_fallback_ids]
                others = [doc for doc in reranked_docs if doc.id not in symptom_fallback_ids]
                reranked_docs = boosted + others
                if boosted:
                    logger.info(f"  - Boosted {len(boosted)} symptom fallback docs to top")

            # Stage 3.54: Boost pest column fallback docs (matched pest_name in insecticides column)
            if pest_fallback_ids:
                boosted = [doc for doc in reranked_docs if doc.id in pest_fallback_ids]
                others = [doc for doc in reranked_docs if doc.id not in pest_fallback_ids]
                reranked_docs = boosted + others
                if boosted:
                    logger.info(f"  - Boosted {len(boosted)} pest fallback docs to top")

            # Category-Intent mapping (used in Stages 3.55, 3.65, 3.7)
            expected_categories = self.INTENT_CATEGORY_VARIANTS.get(query_analysis.intent)

            # Narrow NUTRIENT_SUPPLEMENT when user asks specifically for "ปุ๋ย" / fertilizer
            # Prevents mixing Biostimulants/PGR when user wants plain Fertilizer (NPK)
            if query_analysis.intent == IntentType.NUTRIENT_SUPPLEMENT:
                _q_lower = query_analysis.original_query.lower()
                _fert_specific = ['ปุ๋ยเกล็ด', 'ปุ๋ยnpk', 'ปุ๋ยน้ำ', 'npk', 'ปุ๋ยสูตร']
                _pgr_specific = ['ฮอร์โมน', 'pgr', 'เร่งดอก', 'ยับยั้งใบอ่อน', 'ราดสาร', 'ชะลอ']
                _bio_specific = ['biostimulant', 'สาหร่าย', 'ฟื้นฟูต้น', 'กรดอะมิโน']
                if any(kw in _q_lower for kw in _fert_specific):
                    expected_categories = ["Fertilizer", "fertilizer", "ปุ๋ย"]
                    logger.info(f"  - Narrowed to Fertilizer only (user asked specifically for ปุ๋ย/NPK)")
                elif any(kw in _q_lower for kw in _pgr_specific):
                    expected_categories = ["PGR", "pgr", "ฮอร์โมน"]
                    logger.info(f"  - Narrowed to PGR only")
                elif any(kw in _q_lower for kw in _bio_specific):
                    expected_categories = ["Biostimulants", "biostimulants"]
                    logger.info(f"  - Narrowed to Biostimulants only")

            # Infer from entities when intent doesn't specify (PRODUCT_RECOMMENDATION, UNKNOWN, etc.)
            if not expected_categories:
                expected_categories = self._infer_expected_categories(query_analysis)
                if expected_categories:
                    logger.info(f"  - Inferred expected_categories from entities: {expected_categories[0]}")

            # Stage 3.55: Category-Intent alignment penalty
            # If user asks about disease, penalize non-fungicide products (e.g. PGR)
            # When direct_lookup found a product, infer expected category from it
            _product_from_query = query_analysis.entities.get('_product_from_query', True)
            if direct_lookup_ids and not expected_categories and _product_from_query:
                for doc in reranked_docs:
                    if doc.id in direct_lookup_ids:
                        cat = doc.metadata.get('category') or ''
                        if 'วัชพืช' in cat or 'herbicide' in cat.lower():
                            expected_categories = ["Herbicide", "herbicide", "กำจัดวัชพืช"]
                        elif 'แมลง' in cat or 'insecticide' in cat.lower():
                            expected_categories = ["Insecticide", "insecticide", "กำจัดแมลง"]
                        elif 'โรค' in cat or 'fungicide' in cat.lower():
                            expected_categories = ["Fungicide", "fungicide", "ป้องกันโรค"]
                        if expected_categories:
                            logger.info(f"  - Inferred category from direct lookup: {expected_categories[0]}")
                        break

            if expected_categories:
                # Adaptive penalty: stronger when enough correct-category docs exist
                _correct_cat_count = sum(
                    1 for d in reranked_docs
                    if any(ec.lower() in str(d.metadata.get('category') or '').lower() for ec in expected_categories)
                )
                _cat_penalty = -0.90 if _correct_cat_count >= 3 else -0.75
                for doc in reranked_docs:
                    if doc.id in direct_lookup_ids:
                        continue  # Don't penalize the queried product itself
                    cat = str(doc.metadata.get('category') or '').lower()
                    if cat and not any(ec.lower() in cat for ec in expected_categories):
                        doc.rerank_score = max(0.0, doc.rerank_score + _cat_penalty)
                        logger.info(f"  - Category mismatch penalty {_cat_penalty} for {doc.title} (category: {cat}, expected: {expected_categories[0]})")
                reranked_docs = sorted(reranked_docs, key=lambda d: d.rerank_score, reverse=True)

            # Stage 3.6: Boost Skyrocket/Expand score, penalize Standard
            if not direct_lookup_ids:  # Only when not asking about specific product
                strategy_bonus = {'Skyrocket': 0.12, 'Expand': 0.12, 'Natural': 0.0, 'Standard': 0.0}
                _BUNDLE_KW_36 = ['ชุด', 'กล่อง', 'รวง']
                for doc in reranked_docs:
                    sg = doc.metadata.get('strategy', '')
                    bonus = strategy_bonus.get(sg, 0.0)
                    # Bundle products get half bonus (they match too broadly)
                    if bonus != 0 and any(bk in doc.title for bk in _BUNDLE_KW_36):
                        bonus = bonus * 0.5
                    if bonus != 0:
                        doc.rerank_score = min(1.0, max(0.0, doc.rerank_score + bonus))
                # Re-sort by boosted rerank_score
                reranked_docs = sorted(reranked_docs, key=lambda d: d.rerank_score, reverse=True)
                logger.info(f"  - Applied strategy group score boost")

            # Stage 3.65: Crop-specific boost & mismatch penalty
            # If user asks about specific plant:
            #   - Boost products whose applicable_crops matches plant_type
            #   - Penalize products that don't mention plant_type
            #   - Heavy penalty for products that explicitly say "ห้ามใช้ใน..." for plant_type
            if not direct_lookup_ids:
                plant_type = query_analysis.entities.get('plant_type', '')
                if plant_type:
                    for doc in reranked_docs:
                        # Skip crop adjustments for category-mismatched products
                        if expected_categories:
                            cat = str(doc.metadata.get('category') or '').lower()
                            if cat and not any(ec.lower() in cat for ec in expected_categories):
                                continue
                        crops = str(doc.metadata.get('applicable_crops') or '')
                        selling = str(doc.metadata.get('selling_point') or '')
                        how_to = str(doc.metadata.get('how_to_use') or '')
                        all_text = f"{crops} {how_to} {selling}"

                        # Check for explicit prohibition: "ห้ามใช้ในนาข้าว", "ห้ามใช้ในสวนทุเรียน" etc.
                        _prohibit_patterns = [
                            f"ห้ามใช้ใน{plant_type}",
                            f"ห้ามใช้กับ{plant_type}",
                            f"ไม่ควรใช้ใน{plant_type}",
                            f"ห้ามใช้ในนา{plant_type}" if plant_type == "ข้าว" else "",
                            f"ห้ามใช้ในนาข้าว" if plant_type == "ข้าว" else "",
                            f"ห้ามใช้ในสวน{plant_type}" if plant_type not in ("ข้าว",) else "",
                        ]
                        _prohibit_patterns = [p for p in _prohibit_patterns if p]
                        _is_prohibited = any(p in all_text for p in _prohibit_patterns)

                        if _is_prohibited:
                            # Heavy penalty — explicitly prohibited for this crop
                            doc.rerank_score = max(0.0, doc.rerank_score - 0.30)
                            logger.info(f"  - Crop-prohibited penalty -0.30 for {doc.title} (prohibited for {plant_type})")
                        elif _plant_matches_crops(plant_type, crops) and ('เน้นสำหรับ' in crops or f'{plant_type}อันดับ' in selling):
                            # "เน้นสำหรับ(ทุเรียน)" or "เฉพาะทุเรียน" → strong match
                            doc.rerank_score = min(1.0, doc.rerank_score + 0.20)
                            logger.info(f"  - Crop-specific boost +0.20 for {doc.title} (crops: {crops[:50]})")
                        elif _plant_matches_crops(plant_type, crops):
                            # Crop mentioned directly or via broader category
                            doc.rerank_score = min(1.0, doc.rerank_score + 0.05)
                            logger.info(f"  - Crop-broader-match +0.05 for {doc.title} (crops: {crops[:50]}, plant: {plant_type})")
                        elif crops.strip():
                            # Has applicable_crops but plant_type not in it → mild penalty
                            doc.rerank_score = max(0.0, doc.rerank_score - 0.15)
                            logger.info(f"  - Crop-mismatch penalty -0.15 for {doc.title} (crops: {crops[:50]}, wanted: {plant_type})")
                    reranked_docs = sorted(reranked_docs, key=lambda d: d.rerank_score, reverse=True)

            # Stage 3.7: Promote best Skyrocket/Expand to position 1
            # Prefer product whose applicable_crops specifically matches user's plant_type
            # BUT only promote category-matched products when intent is specific
            if not direct_lookup_ids:
                all_priority = [d for d in reranked_docs if d.metadata.get('strategy') in ('Skyrocket', 'Expand')]
                # Filter by category alignment if intent requires specific category
                if expected_categories and all_priority:
                    category_matched = [
                        d for d in all_priority
                        if not str(d.metadata.get('category') or '').lower()
                        or any(ec.lower() in str(d.metadata.get('category') or '').lower() for ec in expected_categories)
                    ]
                    if category_matched:
                        all_priority = category_matched
                if all_priority:
                    best_priority = all_priority[0]
                    # If user mentions specific plant, prefer crop-specific product
                    plant_type = query_analysis.entities.get('plant_type', '')
                    if plant_type:
                        for d in all_priority:
                            crops = str(d.metadata.get('applicable_crops') or '')
                            selling = str(d.metadata.get('selling_point') or '')
                            if _plant_matches_crops(plant_type, crops) and ('เน้นสำหรับ' in crops or f'{plant_type}อันดับ' in selling):
                                best_priority = d
                                logger.info(f"  - Crop-specific match: {d.title} (crops: {crops[:50]})")
                                break
                    try:
                        current_pos = reranked_docs.index(best_priority)
                    except ValueError:
                        current_pos = -1
                    # Skip promotion for bundle products (they match too many queries)
                    _BUNDLE_KW = ['ชุด', 'กล่อง', 'รวง']
                    _is_bundle = any(bk in best_priority.title for bk in _BUNDLE_KW)
                    if current_pos > 0 and not _is_bundle:
                        reranked_docs.remove(best_priority)
                        reranked_docs.insert(0, best_priority)
                        logger.info(f"  - Promoted {best_priority.title} ({best_priority.metadata.get('strategy')}) from pos {current_pos + 1} to 1")
                    elif _is_bundle:
                        logger.info(f"  - Skip bundle promotion: {best_priority.title}")

            # Stage 3.8: Ensure disease-matching product is in top 3
            # If query is about disease but no top-3 doc has the disease in pest columns,
            # find and promote the matching doc (e.g. อาร์เทมิส for ราชมพู)
            if not direct_lookup_ids and query_analysis.intent in (IntentType.DISEASE_TREATMENT, IntentType.PRODUCT_RECOMMENDATION):
                from app.utils.text_processing import generate_thai_disease_variants
                from app.utils.pest_columns import get_pest_text_lower as _gptl
                _entity_disease = query_analysis.entities.get('disease_name', '')
                _original_disease = self._extract_disease_from_query(query_analysis.original_query)
                _diseases_to_check = [d for d in [_entity_disease, _original_disease] if d]
                if _diseases_to_check:
                    _all_variants = []
                    for d in _diseases_to_check:
                        _all_variants.extend(generate_thai_disease_variants(d))
                    _all_variants = list(set(_all_variants))
                    top_has_match = any(
                        any(v.lower() in _gptl(d.metadata) for v in _all_variants)
                        for d in reranked_docs[:3]
                    )
                    if not top_has_match:
                        for d in reranked_docs[3:]:
                            _pest_text = _gptl(d.metadata)
                            if any(v.lower() in _pest_text for v in _all_variants):
                                reranked_docs.remove(d)
                                reranked_docs.insert(0, d)
                                logger.info(f"  - Rescued disease-matched product: {d.title} to position 1")
                                break

            # Stage 4: Filter by rerank threshold
            filtered_docs = [
                doc for doc in reranked_docs
                if doc.rerank_score >= self.rerank_threshold or doc.similarity_score >= self.vector_threshold
                or doc.id in direct_lookup_ids
                or doc.id in disease_fallback_ids
                or doc.id in symptom_fallback_ids
                or doc.id in pest_fallback_ids
            ]

            # Ensure we have at least some results
            if len(filtered_docs) < MIN_RELEVANT_DOCS and len(reranked_docs) > 0:
                filtered_docs = reranked_docs[:MIN_RELEVANT_DOCS]

            # Stage 4.5: Ensure crop-specific priority product is in results
            if not direct_lookup_ids:
                plant_type = query_analysis.entities.get('plant_type', '')
                if plant_type:
                    # Check if a crop-specific product is already in filtered_docs
                    has_crop_specific = False
                    for d in filtered_docs:
                        crops = str(d.metadata.get('applicable_crops') or '')
                        selling = str(d.metadata.get('selling_point') or '')
                        if plant_type in crops and ('เน้นสำหรับ' in crops or f'{plant_type}อันดับ' in selling):
                            has_crop_specific = True
                            break

                    if not has_crop_specific:
                        # Search full reranked list for crop-specific product
                        for d in reranked_docs:
                            crops = str(d.metadata.get('applicable_crops') or '')
                            selling = str(d.metadata.get('selling_point') or '')
                            if plant_type in crops and ('เน้นสำหรับ' in crops or f'{plant_type}อันดับ' in selling):
                                if d not in filtered_docs:
                                    filtered_docs.insert(0, d)
                                    logger.info(f"  - Rescued crop-specific product: {d.title} to pos 1")
                                break

            total_after_rerank = len(filtered_docs)
            avg_similarity = sum(d.similarity_score for d in filtered_docs) / len(filtered_docs) if filtered_docs else 0
            avg_rerank_score = sum(d.rerank_score for d in filtered_docs) / len(filtered_docs) if filtered_docs else 0

            logger.info(f"  - After filter: {total_after_rerank}")
            logger.info(f"  - Avg similarity: {avg_similarity:.3f}, Avg rerank: {avg_rerank_score:.3f}")

            return RetrievalResult(
                documents=filtered_docs[:top_k],
                total_retrieved=total_retrieved,
                total_after_rerank=total_after_rerank,
                avg_similarity=avg_similarity,
                avg_rerank_score=avg_rerank_score,
                sources_used=list(set(d.source for d in filtered_docs))
            )

        except Exception as e:
            logger.error(f"RetrievalAgent error: {e}", exc_info=True)
            return RetrievalResult(
                documents=[],
                total_retrieved=0,
                total_after_rerank=0,
                avg_similarity=0.0,
                avg_rerank_score=0.0,
                sources_used=[]
            )

    async def _multi_source_retrieval(
        self,
        query_analysis: QueryAnalysis,
        top_k: int
    ) -> List[RetrievedDocument]:
        """Retrieve from multiple sources in parallel"""
        all_docs = []
        tasks = []

        # Build retrieval tasks — products table only
        for query in query_analysis.expanded_queries:
            tasks.append(self._search_products(query, top_k, query_analysis))

        # Execute all searches in parallel
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    all_docs.extend(result)
                elif isinstance(result, Exception):
                    logger.warning(f"Search task failed: {result}")

        return all_docs

    async def _search_products(
        self,
        query: str,
        top_k: int,
        query_analysis: QueryAnalysis
    ) -> List[RetrievedDocument]:
        """Search products table with vector similarity"""
        if not self.supabase or not self.openai_client:
            return []

        try:
            # Generate embedding
            embedding = await self._generate_embedding(query)
            if not embedding:
                return []

            # Determine category filter based on intent (English values matching products table)
            category_filter = self.INTENT_CATEGORY_MAP.get(query_analysis.intent) if query_analysis else None

            # Try hybrid search (note: hybrid_search_products doesn't support match_threshold or category_filter)
            rpc_params = {
                'query_embedding': embedding,
                'search_query': query,
                'vector_weight': 0.6,
                'keyword_weight': 0.4,
                'match_count': top_k * 2
            }

            result = await aexecute(self.supabase.rpc(PRODUCT_RPC, rpc_params))

            if not result.data:
                return []

            # Convert to RetrievedDocument with filtering
            docs = []
            _original_query_lower = query_analysis.original_query.lower() if query_analysis and query_analysis.original_query else query.lower()
            for item in result.data:
                similarity = float(item.get('similarity', 0))

                # Name-match boost: user ถามชื่อสินค้าตรง → boost score +0.25
                # ป้องกัน "แจ๊ส" → ได้ "เกรค" (vector similarity สูงเพราะ insecticide คล้ายกัน)
                _pname = str(item.get('product_name', '')).lower()
                if _original_query_lower and _pname and _pname in _original_query_lower:
                    similarity = min(1.0, similarity + 0.25)

                # Filter by threshold
                if similarity < self.vector_threshold:
                    continue

                # Category filter removed - let reranker handle relevance instead

                doc = self._build_doc_from_row(item, similarity=similarity)
                docs.append(doc)

            logger.info(f"    Product search: {len(docs)} docs for '{query[:30]}...'")

            return docs

        except Exception as e:
            logger.error(f"Product search error: {e}")
            return []

    def _extract_disease_from_query(self, query: str) -> str:
        """Extract disease name from query text when entities are not available"""
        # Known disease keywords to remove from extraction
        _STOP_WORDS = {
            'ใช้', 'ยา', 'อะไร', 'รักษา', 'ครับ', 'ค่ะ', 'คะ', 'ได้', 'บ้าง',
            'มี', 'ไหม', 'กำจัด', 'ป้องกัน', 'แนะนำ', 'ดี', 'หน่อย', 'สำหรับ',
            'วิธี', 'อย่างไร', 'ยังไง', 'ทำ', 'จะ', 'ต้อง', 'ควร', 'โรค',
            'แก้', 'แก้ไข', 'ช่วย', 'อัตรา', 'ผสม', 'ฉีด', 'พ่น',
        }
        # Known disease name patterns (single source of truth)
        from app.services.disease.constants import DISEASE_PATTERNS_SORTED, get_canonical
        # Try known patterns first (diacritics-tolerant)
        from app.utils.text_processing import diacritics_match
        for pattern in DISEASE_PATTERNS_SORTED:
            if diacritics_match(query, pattern):
                return get_canonical(pattern)

        # Try extracting from "โรค..." prefix
        import re
        match = re.search(r'โรค(\S+)', query)
        if match:
            return match.group(0)  # include โรค prefix

        # Extract first Thai word that's not a stop word
        words = re.findall(r'[\u0e00-\u0e7f]+', query)
        for word in words:
            if word not in _STOP_WORDS and len(word) > 3:
                return word

        return ''

    async def _search_by_target_pest(
        self,
        disease_variants: list,
        query_analysis: QueryAnalysis
    ) -> List[RetrievedDocument]:
        """Fallback: ค้นหาสินค้าจาก pest columns โดยตรง (ไม่ใช้ vector search)"""
        from app.utils.pest_columns import build_pest_or_filter
        try:
            for variant in disease_variants:
                if len(variant) < 3:
                    continue
                or_filter = build_pest_or_filter(variant)
                result = await aexecute(self.supabase.table(PRODUCT_TABLE).select(_PRODUCT_COLUMNS).or_(
                    or_filter
                ).limit(5))

                if result.data:
                    docs = [self._build_doc_from_row(item, similarity=0.50) for item in result.data]
                    return docs
            return []
        except Exception as e:
            logger.error(f"Pest columns fallback search error: {e}")
            return []

    async def _broad_disease_category_search(
        self, plant_type: str, existing_docs: List[RetrievedDocument], top_k: int = 15
    ) -> List[RetrievedDocument]:
        """Fallback for broad disease terms like 'เชื้อรา': search all Fungicide products,
        then filter by crop if plant_type is specified."""
        if not self.supabase:
            return []
        try:
            result = await aexecute(self.supabase.table(PRODUCT_TABLE) \
                .select(_PRODUCT_COLUMNS) \
                .ilike('product_category', '%Fungicide%') \
                .limit(top_k))

            if not result.data:
                return []

            existing_ids = {d.id for d in existing_docs}
            docs = []
            for item in result.data:
                if str(item['id']) in existing_ids:
                    continue
                # If plant_type specified, filter by crop match
                if plant_type:
                    crops = item.get('applicable_crops', '') or ''
                    fungi = item.get('fungicides', '') or ''
                    combined = f"{crops} {fungi}"
                    if not _plant_matches_crops(plant_type, combined):
                        continue
                docs.append(self._build_doc_from_row(item, similarity=0.50))

            return docs
        except Exception as e:
            logger.error(f"Broad disease category search error: {e}")
            return []

    async def _search_by_symptom_keywords(
        self, query: str, query_analysis: QueryAnalysis
    ) -> List[RetrievedDocument]:
        """Fallback: search products by symptom keywords matched against pest columns.

        Unlike _search_by_target_pest (disease-specific), this matches general symptom
        phrases like ไม่โต, ไม่กินปุ๋ย, เหลือง etc. against the DB — no hardcoded product names.
        """
        if not self.supabase:
            return []

        try:
            # Symptom phrases to look for in the query (ordered longest-first to prefer specific matches)
            symptom_patterns = [
                r'รวงไม่สม่ำเสมอ', r'แตกกอไม่ดี',
                r'ไม่กินปุ๋ย', r'ไม่แตกกอ', r'ไม่ออกดอก', r'ไม่ติดผล',
                r'เมาตอซัง', r'ใบเหลือง', r'ใบไหม้', r'ใบจุด',
                r'ดอกร่วง', r'ผลร่วง', r'ผลเน่า', r'รากเน่า', r'ลำต้นเน่า',
                r'ต้นเตี้ย', r'รากดำ', r'เหี่ยว',
                r'ไม่โต', r'เหลือง',
            ]

            matched_symptoms = []
            for pattern in symptom_patterns:
                if re.search(pattern, query):
                    matched_symptoms.append(pattern)

            if not matched_symptoms:
                return []

            logger.info(f"    Symptom keyword fallback: matched {matched_symptoms}")

            # Build OR filter across pest columns
            from app.utils.pest_columns import build_pest_or_conditions
            or_conditions = []
            for s in matched_symptoms:
                or_conditions.extend(build_pest_or_conditions(s))
            or_filter = ",".join(or_conditions)

            query_builder = self.supabase.table(PRODUCT_TABLE).select(_PRODUCT_COLUMNS).or_(or_filter).limit(10)

            # Narrow by plant type if available
            plant_type = query_analysis.entities.get('plant_type', '')
            if plant_type:
                query_builder = query_builder.ilike('applicable_crops', f'%{plant_type}%')

            result = await aexecute(query_builder)

            if not result.data:
                return []

            docs = [self._build_doc_from_row(item, similarity=0.60) for item in result.data]
            logger.info(f"    Symptom keyword fallback: {len(docs)} docs found")
            return docs

        except Exception as e:
            logger.error(f"Symptom keyword fallback search error: {e}")
            return []

    async def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for search query (with LRU cache)"""
        # Check cache first
        cached = _get_cached_embedding(text)
        if cached is not None:
            return cached

        try:
            response = await self.openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text,
                encoding_format="float"
            )
            if not response.data:
                logger.error("OpenAI embedding returned empty data")
                return []
            embedding = response.data[0].embedding
            _set_cached_embedding(text, embedding)
            return embedding
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return []

    def _deduplicate(self, docs: List[RetrievedDocument]) -> List[RetrievedDocument]:
        """Remove duplicate documents based on content similarity"""
        seen_titles = set()
        unique_docs = []

        for doc in docs:
            # Create a normalized key from title
            key = doc.title.lower().strip()
            if key not in seen_titles:
                seen_titles.add(key)
                unique_docs.append(doc)

        return unique_docs

    async def _rerank_with_llm(
        self,
        query: str,
        docs: List[RetrievedDocument],
        intent: IntentType
    ) -> List[RetrievedDocument]:
        """Re-rank documents using LLM as cross-encoder"""
        if not self.openai_client or len(docs) <= 1:
            return docs

        try:
            # Guarantee Skyrocket/Expand in rerank window (category must match intent)
            rerank_pool = list(docs[:15])
            _rerank_ids = {d.id for d in rerank_pool}
            _priority_strategies = {'Skyrocket', 'Expand'}
            _has_priority = any(
                d.metadata.get('strategy') in _priority_strategies for d in rerank_pool
            )
            if not _has_priority:
                # Find best Skyrocket/Expand from remaining docs that matches expected category
                _expected_cat = self.INTENT_CATEGORY_MAP.get(intent, '').lower()
                for d in docs[15:]:
                    _strat = d.metadata.get('strategy', '')
                    _cat = (d.metadata.get('category') or '').lower()
                    if _strat in _priority_strategies and d.id not in _rerank_ids:
                        # Must match category OR no category filter (e.g. product_recommendation)
                        if not _expected_cat or _expected_cat in _cat:
                            rerank_pool[-1] = d  # Replace last (lowest score)
                            logger.info(f"  - Injected {_strat} product '{d.title}' into rerank window (category: {_cat})")
                            break

            # Prepare document summaries
            doc_texts = []
            for i, doc in enumerate(rerank_pool, 1):
                text = f"[{i}] {doc.title}"
                if doc.metadata.get('product_name'):
                    text += f" | สินค้า: {doc.metadata['product_name']}"
                from app.utils.pest_columns import get_pest_text
                _pest = get_pest_text(doc.metadata)
                if _pest:
                    text += f" | ใช้กำจัด: {_pest[:80]}"
                if doc.metadata.get('applicable_crops'):
                    text += f" | พืช: {str(doc.metadata['applicable_crops'])[:80]}"
                if doc.metadata.get('selling_point'):
                    text += f" | จุดเด่น: {str(doc.metadata['selling_point'])[:80]}"
                if doc.metadata.get('category'):
                    text += f" | ประเภท: {doc.metadata['category']}"
                if doc.metadata.get('strategy'):
                    text += f" | Strategy: {doc.metadata['strategy']}"
                doc_texts.append(text)

            docs_str = "\n".join(doc_texts)

            # Build intent-specific constraint
            intent_constraint = ""
            if intent == IntentType.DISEASE_TREATMENT:
                intent_constraint = "\nต้องการยาป้องกัน/รักษาโรคพืช (fungicide)"
            elif intent == IntentType.PEST_CONTROL:
                intent_constraint = "\nต้องการยากำจัดแมลง (insecticide)"
            elif intent == IntentType.WEED_CONTROL:
                intent_constraint = "\nต้องการยากำจัดวัชพืช (herbicide)"

            prompt = f"""จัดอันดับความเกี่ยวข้องของเอกสารกับคำถาม

คำถาม: "{query}"{intent_constraint}

เอกสาร:
{docs_str}

จัดอันดับจากเกี่ยวข้องมากที่สุดไปน้อยที่สุด
พิจารณา:
1. เนื้อหาตรงกับคำถามหรือไม่
2. ประเภทสินค้าตรงกับปัญหาหรือไม่
3. พืช/ศัตรูพืชที่ระบุตรงกันหรือไม่
4. สินค้า Strategy Skyrocket/Expand ให้ลำดับสูงกว่า Natural/Standard
5. ถ้าสินค้าหลายตัวคล้ายกัน ให้เลือกตัวที่ "พืช" ระบุเน้นพืชตรงกับคำถาม (เช่น "เน้นสำหรับ(ทุเรียน)" ตรงกว่า "มะม่วง, ทุเรียน")

ตอบเฉพาะตัวเลขเรียงลำดับ คั่นด้วย comma เช่น: 3,1,5,2,4"""

            response = await self.openai_client.chat.completions.create(
                model=LLM_MODEL_RERANKING,
                messages=[
                    {"role": "system", "content": "ตอบเฉพาะตัวเลขเรียงลำดับ คั่นด้วย comma"},
                    {"role": "user", "content": prompt}
                ],
                temperature=LLM_TEMP_RERANKING,
                max_completion_tokens=LLM_TOKENS_RERANKING
            )

            if not response.choices:
                logger.warning("LLM rerank returned empty choices, using similarity scores")
                return sorted(docs, key=lambda x: x.similarity_score, reverse=True)
            ranking_text = response.choices[0].message.content.strip()
            logger.info(f"    Rerank response: {ranking_text}")

            # Parse ranking (safe int conversion)
            numbers = re.findall(r'\d+', ranking_text)
            ranking_indices = []
            for n in numbers:
                try:
                    num = int(n)
                    if 0 < num <= len(rerank_pool):
                        ranking_indices.append(num - 1)
                except ValueError:
                    pass

            # Build reranked list with scores
            reranked = []
            seen_indices = set()
            _reranked_ids = set()
            total_ranked = max(len(ranking_indices), 1)  # prevent division by zero
            for rank, idx in enumerate(ranking_indices):
                if idx not in seen_indices and idx < len(rerank_pool):
                    doc = rerank_pool[idx]
                    # Assign rerank score based on position (higher = better)
                    doc.rerank_score = 1.0 - (rank / total_ranked)
                    reranked.append(doc)
                    seen_indices.add(idx)
                    _reranked_ids.add(doc.id)

            # Add remaining docs with lower scores (from full docs list)
            for i, doc in enumerate(docs):
                if doc.id not in _reranked_ids:
                    doc.rerank_score = 0.3  # Default low score
                    reranked.append(doc)

            return reranked

        except Exception as e:
            logger.warning(f"LLM rerank failed: {e}, using similarity scores")
            return sorted(docs, key=lambda x: x.similarity_score, reverse=True)
