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

from app.services.agents import (
    QueryAnalysis,
    RetrievedDocument,
    RetrievalResult,
    IntentType
)
from app.config import LLM_MODEL_RERANKING, EMBEDDING_MODEL

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_VECTOR_THRESHOLD = 0.25  # Lowered from 0.35 for better recall
DEFAULT_RERANK_THRESHOLD = 0.50
DEFAULT_TOP_K = 10
MIN_RELEVANT_DOCS = 3

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


def _set_cached_embedding(text: str, embedding: list):
    """Store embedding in cache, evict oldest if full"""
    key = hashlib.md5(text.encode()).hexdigest()
    if len(_embedding_cache) >= _EMBEDDING_CACHE_MAX:
        # Evict oldest 10%
        sorted_keys = sorted(_embedding_cache, key=lambda k: _embedding_cache[k]["ts"])
        for k in sorted_keys[:max(1, len(sorted_keys) // 10)]:
            del _embedding_cache[k]
    _embedding_cache[key] = {"embedding": embedding, "ts": time.time()}


class RetrievalAgent:
    """
    Agent 2: Retrieval
    Performs multi-query retrieval with re-ranking
    """

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

    async def _direct_product_lookup(self, product_name: str) -> List[RetrievedDocument]:
        """Direct database lookup by product name (exact/ilike match)"""
        if not self.supabase:
            return []

        try:
            # Try ilike search on product_name
            result = self.supabase.table('products') \
                .select('*') \
                .ilike('product_name', f'%{product_name}%') \
                .limit(5) \
                .execute()

            if not result.data:
                return []

            docs = []
            for item in result.data:
                common_th = item.get('common_name_th') or ''
                doc = RetrievedDocument(
                    id=str(item.get('id', '')),
                    title=item.get('product_name', ''),
                    content=f"สินค้า: {item.get('product_name', '')}\n"
                           f"ชื่อสารไทย: {common_th}\n"
                           f"สารสำคัญ: {item.get('active_ingredient', '')}\n"
                           f"ใช้กำจัด: {(item.get('target_pest') or '')[:200]}\n"
                           f"พืชที่ใช้ได้: {(item.get('applicable_crops') or '')[:200]}",
                    source="products",
                    similarity_score=1.0,
                    rerank_score=1.0,
                    metadata={
                        'product_name': item.get('product_name'),
                        'common_name_th': common_th,
                        'active_ingredient': item.get('active_ingredient'),
                        'target_pest': item.get('target_pest'),
                        'applicable_crops': item.get('applicable_crops'),
                        'category': item.get('product_category') or item.get('category'),
                        'how_to_use': item.get('how_to_use'),
                        'usage_rate': item.get('usage_rate'),
                        'usage_period': item.get('usage_period'),
                        'selling_point': item.get('selling_point'),
                        'action_characteristics': item.get('action_characteristics'),
                        'absorption_method': item.get('absorption_method'),
                        'strategy_group': item.get('strategy_group'),
                        'package_size': item.get('package_size'),
                    }
                )
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
            for kw in keywords[:3]:  # Limit to 3 keywords
                or_conditions.append(f"product_name.ilike.%{kw}%")
                or_conditions.append(f"target_pest.ilike.%{kw}%")
                or_conditions.append(f"active_ingredient.ilike.%{kw}%")
                or_conditions.append(f"common_name_th.ilike.%{kw}%")

            or_filter = ",".join(or_conditions)

            result = self.supabase.table('products') \
                .select('*') \
                .or_(or_filter) \
                .limit(top_k) \
                .execute()

            if not result.data:
                return []

            docs = []
            for item in result.data:
                common_th = item.get('common_name_th') or ''
                doc = RetrievedDocument(
                    id=str(item.get('id', '')),
                    title=item.get('product_name', ''),
                    content=f"สินค้า: {item.get('product_name', '')}\n"
                           f"ชื่อสารไทย: {common_th}\n"
                           f"สารสำคัญ: {item.get('active_ingredient', '')}\n"
                           f"ใช้กำจัด: {(item.get('target_pest') or '')[:200]}\n"
                           f"พืชที่ใช้ได้: {(item.get('applicable_crops') or '')[:200]}",
                    source="products",
                    similarity_score=0.5,
                    metadata={
                        'product_name': item.get('product_name'),
                        'common_name_th': common_th,
                        'active_ingredient': item.get('active_ingredient'),
                        'target_pest': item.get('target_pest'),
                        'applicable_crops': item.get('applicable_crops'),
                        'category': item.get('product_category') or item.get('category'),
                        'how_to_use': item.get('how_to_use'),
                        'usage_rate': item.get('usage_rate'),
                        'usage_period': item.get('usage_period'),
                        'selling_point': item.get('selling_point'),
                        'action_characteristics': item.get('action_characteristics'),
                        'absorption_method': item.get('absorption_method'),
                        'strategy_group': item.get('strategy_group'),
                        'package_size': item.get('package_size'),
                    }
                )
                docs.append(doc)

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

            # Search Skyrocket/Expand products matching keywords in target_pest or selling_point
            or_conditions = []
            for kw in keywords:
                or_conditions.append(f"target_pest.ilike.%{kw}%")
                or_conditions.append(f"selling_point.ilike.%{kw}%")
                or_conditions.append(f"common_name_th.ilike.%{kw}%")
                or_conditions.append(f"active_ingredient.ilike.%{kw}%")
                or_conditions.append(f"applicable_crops.ilike.%{kw}%")

            or_filter = ",".join(or_conditions)

            # Apply category filter if intent requires specific product type
            intent_cat_map = {
                IntentType.DISEASE_TREATMENT: "Fungicide",
                IntentType.PEST_CONTROL: "Insecticide",
                IntentType.WEED_CONTROL: "Herbicide",
            }
            cat_filter = intent_cat_map.get(query_analysis.intent)

            query_builder = self.supabase.table('products') \
                .select('*') \
                .in_('strategy_group', ['Skyrocket', 'Expand']) \
                .or_(or_filter) \
                .limit(top_k)
            if cat_filter:
                query_builder = query_builder.ilike('product_category', f'%{cat_filter}%')
            result = query_builder.execute()

            if not result.data:
                return []

            existing_ids = {d.id for d in existing_docs}
            docs = []
            for item in result.data:
                doc_id = str(item.get('id', ''))
                if doc_id in existing_ids:
                    continue  # Skip duplicates

                common_th = item.get('common_name_th') or ''
                doc = RetrievedDocument(
                    id=doc_id,
                    title=item.get('product_name', ''),
                    content=f"สินค้า: {item.get('product_name', '')}\n"
                           f"ชื่อสารไทย: {common_th}\n"
                           f"สารสำคัญ: {item.get('active_ingredient', '')}\n"
                           f"ใช้กำจัด: {(item.get('target_pest') or '')[:200]}\n"
                           f"พืชที่ใช้ได้: {(item.get('applicable_crops') or '')[:200]}\n"
                           f"จุดเด่น: {(item.get('selling_point') or '')[:200]}",
                    source="products",
                    similarity_score=0.55,
                    metadata={
                        'product_name': item.get('product_name'),
                        'common_name_th': common_th,
                        'active_ingredient': item.get('active_ingredient'),
                        'target_pest': item.get('target_pest'),
                        'applicable_crops': item.get('applicable_crops'),
                        'category': item.get('product_category') or item.get('category'),
                        'how_to_use': item.get('how_to_use'),
                        'usage_rate': item.get('usage_rate'),
                        'usage_period': item.get('usage_period'),
                        'selling_point': item.get('selling_point'),
                        'action_characteristics': item.get('action_characteristics'),
                        'absorption_method': item.get('absorption_method'),
                        'strategy_group': item.get('strategy_group'),
                        'package_size': item.get('package_size'),
                    }
                )
                docs.append(doc)

            if docs:
                logger.info(f"    Supplementary priority search: {len(docs)} Skyrocket/Expand docs found")
            return docs

        except Exception as e:
            logger.error(f"Supplementary priority search error: {e}")
            return []

    async def _enrich_strategy_group(self, docs: List[RetrievedDocument]):
        """Fetch strategy_group, selling_point, applicable_crops from DB for docs missing them (e.g. from RPC)"""
        if not self.supabase:
            return

        # Find docs missing strategy_group or selling_point (RPC doesn't return these)
        missing_ids = [
            doc.id for doc in docs
            if doc.id and (not doc.metadata.get('strategy_group') or not doc.metadata.get('selling_point'))
        ]
        if not missing_ids:
            return

        try:
            result = self.supabase.table('products') \
                .select('id, strategy_group, selling_point, applicable_crops, package_size') \
                .in_('id', [int(i) for i in set(missing_ids) if i.isdigit()]) \
                .execute()

            if result.data:
                enrich_map = {str(r['id']): r for r in result.data}
                enriched = 0
                for doc in docs:
                    if doc.id in enrich_map:
                        r = enrich_map[doc.id]
                        if r.get('strategy_group') and not doc.metadata.get('strategy_group'):
                            doc.metadata['strategy_group'] = r['strategy_group']
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
        top_k: int = DEFAULT_TOP_K
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

            # Stage 0: Direct product lookup if entity has product_name
            all_docs = []
            direct_lookup_ids = set()
            product_name = query_analysis.entities.get('product_name')
            if product_name:
                direct_docs = await self._direct_product_lookup(product_name)
                if direct_docs:
                    all_docs.extend(direct_docs)
                    direct_lookup_ids = {doc.id for doc in direct_docs}
                    logger.info(f"  - Direct lookup found: {len(direct_docs)} docs")

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

                if disease_names_to_check:
                    # Build combined variants from all disease names
                    all_variants = []
                    for d in disease_names_to_check:
                        all_variants.extend(generate_thai_disease_variants(d))
                    all_variants = list(set(all_variants))

                    # Check if any existing doc already matches
                    has_disease_in_docs = any(
                        any(v.lower() in str(doc.metadata.get('target_pest', '')).lower() for v in all_variants)
                        for doc in all_docs
                    ) if all_docs else False

                    if not has_disease_in_docs:
                        logger.info(f"  - Disease fallback: {disease_names_to_check} not in retrieved docs, searching target_pest")
                        fallback_docs = await self._search_by_target_pest(all_variants, query_analysis)
                        if fallback_docs:
                            disease_fallback_ids = {doc.id for doc in fallback_docs}
                            all_docs.extend(fallback_docs)
                            logger.info(f"  - Disease fallback found: {len(fallback_docs)} products via target_pest")

            # Stage 1.5: Fallback keyword search if no results
            if not all_docs:
                fallback_docs = await self._fallback_keyword_search(query_analysis.original_query, top_k)
                all_docs.extend(fallback_docs)
                if fallback_docs:
                    logger.info(f"  - Fallback keyword search found: {len(fallback_docs)} docs")

            # Stage 1.8: Enrich strategy_group for docs missing it (RPC doesn't return it)
            await self._enrich_strategy_group(all_docs)

            # Stage 1.9: Supplementary search for Skyrocket/Expand if none found
            if not direct_lookup_ids:
                priority_docs = await self._supplementary_priority_search(
                    query_analysis, all_docs, top_k
                )
                if priority_docs:
                    all_docs.extend(priority_docs)
                    logger.info(f"  - Supplementary priority search added: {len(priority_docs)} docs")

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
            if self.openai_client and len(unique_docs) > MIN_RELEVANT_DOCS:
                reranked_docs = await self._rerank_with_llm(
                    query_analysis.original_query,
                    unique_docs,
                    query_analysis.intent
                )
            else:
                # Sort by similarity score if no LLM
                reranked_docs = sorted(unique_docs, key=lambda x: x.similarity_score, reverse=True)

            # Stage 3.5: Boost direct lookup docs to top (user asked about specific product)
            if direct_lookup_ids:
                boosted = [doc for doc in reranked_docs if doc.id in direct_lookup_ids]
                others = [doc for doc in reranked_docs if doc.id not in direct_lookup_ids]
                reranked_docs = boosted + others
                logger.info(f"  - Boosted {len(boosted)} direct lookup docs to top")

            # Stage 3.52: Boost disease fallback docs to top (matched via target_pest directly)
            if disease_fallback_ids:
                boosted = [doc for doc in reranked_docs if doc.id in disease_fallback_ids]
                others = [doc for doc in reranked_docs if doc.id not in disease_fallback_ids]
                reranked_docs = boosted + others
                if boosted:
                    logger.info(f"  - Boosted {len(boosted)} disease fallback docs to top")

            # Category-Intent mapping (used in Stages 3.55, 3.65, 3.7)
            intent_category_map = {
                IntentType.DISEASE_TREATMENT: ["Fungicide", "fungicide", "ป้องกันโรค"],
                IntentType.PEST_CONTROL: ["Insecticide", "insecticide", "กำจัดแมลง"],
                IntentType.WEED_CONTROL: ["Herbicide", "herbicide", "กำจัดวัชพืช"],
            }
            expected_categories = intent_category_map.get(query_analysis.intent)

            # Stage 3.55: Category-Intent alignment penalty
            # If user asks about disease, penalize non-fungicide products (e.g. PGR)
            if not direct_lookup_ids:
                if expected_categories:
                    for doc in reranked_docs:
                        cat = str(doc.metadata.get('category') or '').lower()
                        if cat and not any(ec.lower() in cat for ec in expected_categories):
                            penalty = -0.30
                            doc.rerank_score = max(0.0, doc.rerank_score + penalty)
                            logger.info(f"  - Category mismatch penalty {penalty} for {doc.title} (category: {cat}, expected: {expected_categories[0]})")
                    reranked_docs = sorted(reranked_docs, key=lambda d: d.rerank_score, reverse=True)

            # Stage 3.6: Boost Skyrocket/Expand score, penalize Standard
            if not direct_lookup_ids:  # Only when not asking about specific product
                strategy_bonus = {'Skyrocket': 0.15, 'Expand': 0.10, 'Natural': 0.0, 'Standard': -0.05}
                for doc in reranked_docs:
                    sg = doc.metadata.get('strategy_group', '')
                    bonus = strategy_bonus.get(sg, 0.0)
                    if bonus != 0:
                        doc.rerank_score = min(1.0, max(0.0, doc.rerank_score + bonus))
                # Re-sort by boosted rerank_score
                reranked_docs = sorted(reranked_docs, key=lambda d: d.rerank_score, reverse=True)
                logger.info(f"  - Applied strategy group score boost")

            # Stage 3.65: Crop-specific boost — if user asks about specific plant,
            # prioritize products whose applicable_crops is specific to that plant
            # BUT only if category matches intent (no boost for PGR when asking about disease)
            if not direct_lookup_ids:
                plant_type = query_analysis.entities.get('plant_type', '')
                if plant_type:
                    for doc in reranked_docs:
                        # Skip crop-specific boost for category-mismatched products
                        if expected_categories:
                            cat = str(doc.metadata.get('category') or '').lower()
                            if cat and not any(ec.lower() in cat for ec in expected_categories):
                                continue
                        crops = str(doc.metadata.get('applicable_crops') or '')
                        selling = str(doc.metadata.get('selling_point') or '')
                        # "เน้นสำหรับ(ทุเรียน)" or "เฉพาะทุเรียน" → strong match
                        if plant_type in crops and ('เน้นสำหรับ' in crops or f'{plant_type}อันดับ' in selling):
                            doc.rerank_score = min(1.0, doc.rerank_score + 0.20)
                            logger.info(f"  - Crop-specific boost +0.20 for {doc.title} (crops: {crops[:50]})")
                        elif plant_type in crops:
                            doc.rerank_score = min(1.0, doc.rerank_score + 0.05)
                    reranked_docs = sorted(reranked_docs, key=lambda d: d.rerank_score, reverse=True)

            # Stage 3.7: Promote best Skyrocket/Expand to position 1
            # Prefer product whose applicable_crops specifically matches user's plant_type
            # BUT only promote category-matched products when intent is specific
            if not direct_lookup_ids:
                all_priority = [d for d in reranked_docs if d.metadata.get('strategy_group') in ('Skyrocket', 'Expand')]
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
                            if plant_type in crops and ('เน้นสำหรับ' in crops or f'{plant_type}อันดับ' in selling):
                                best_priority = d
                                logger.info(f"  - Crop-specific match: {d.title} (crops: {crops[:50]})")
                                break
                    try:
                        current_pos = reranked_docs.index(best_priority)
                    except ValueError:
                        current_pos = -1
                    if current_pos > 0:
                        reranked_docs.remove(best_priority)
                        reranked_docs.insert(0, best_priority)
                        logger.info(f"  - Promoted {best_priority.title} ({best_priority.metadata.get('strategy_group')}) from pos {current_pos + 1} to 1")

            # Stage 3.8: Ensure disease-matching product is in top 3
            # If query is about disease but no top-3 doc has the disease in target_pest,
            # find and promote the matching doc (e.g. อาร์เทมีส for ราชมพู)
            if not direct_lookup_ids and query_analysis.intent in (IntentType.DISEASE_TREATMENT, IntentType.PRODUCT_RECOMMENDATION):
                from app.utils.text_processing import generate_thai_disease_variants
                _entity_disease = query_analysis.entities.get('disease_name', '')
                _original_disease = self._extract_disease_from_query(query_analysis.original_query)
                _diseases_to_check = [d for d in [_entity_disease, _original_disease] if d]
                if _diseases_to_check:
                    _all_variants = []
                    for d in _diseases_to_check:
                        _all_variants.extend(generate_thai_disease_variants(d))
                    _all_variants = list(set(_all_variants))
                    top_has_match = any(
                        any(v.lower() in str(d.metadata.get('target_pest', '')).lower() for v in _all_variants)
                        for d in reranked_docs[:3]
                    )
                    if not top_has_match:
                        for d in reranked_docs[3:]:
                            target_pest = str(d.metadata.get('target_pest', '')).lower()
                            if any(v.lower() in target_pest for v in _all_variants):
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
            category_filter = None
            intent_category_map = {
                IntentType.DISEASE_TREATMENT: "Fungicide",
                IntentType.PEST_CONTROL: "Insecticide",
                IntentType.WEED_CONTROL: "Herbicide",
                IntentType.NUTRIENT_SUPPLEMENT: "Fertilizer",
            }
            if query_analysis.intent in intent_category_map:
                category_filter = intent_category_map[query_analysis.intent]

            # Try hybrid search (note: hybrid_search_products doesn't support match_threshold or category_filter)
            rpc_params = {
                'query_embedding': embedding,
                'search_query': query,
                'vector_weight': 0.6,
                'keyword_weight': 0.4,
                'match_count': top_k * 2
            }

            result = self.supabase.rpc('hybrid_search_products', rpc_params).execute()

            if not result.data:
                return []

            # Convert to RetrievedDocument with filtering
            docs = []
            for item in result.data:
                similarity = float(item.get('similarity', 0))

                # Filter by threshold
                if similarity < self.vector_threshold:
                    continue

                # Category filter removed - let reranker handle relevance instead

                common_th = item.get('common_name_th') or ''
                doc = RetrievedDocument(
                    id=str(item.get('id', '')),
                    title=item.get('product_name', ''),
                    content=f"สินค้า: {item.get('product_name', '')}\n"
                           f"ชื่อสารไทย: {common_th}\n"
                           f"สารสำคัญ: {item.get('active_ingredient', '')}\n"
                           f"ใช้กำจัด: {item.get('target_pest', '')[:200] if item.get('target_pest') else ''}\n"
                           f"พืชที่ใช้ได้: {item.get('applicable_crops', '')[:200] if item.get('applicable_crops') else ''}",
                    source="products",
                    similarity_score=similarity,
                    metadata={
                        'product_name': item.get('product_name'),
                        'common_name_th': common_th,
                        'active_ingredient': item.get('active_ingredient'),
                        'target_pest': item.get('target_pest'),
                        'applicable_crops': item.get('applicable_crops'),
                        'category': item.get('product_category') or item.get('category'),
                        'how_to_use': item.get('how_to_use'),
                        'usage_rate': item.get('usage_rate'),
                        'usage_period': item.get('usage_period'),
                        'selling_point': item.get('selling_point'),
                        'action_characteristics': item.get('action_characteristics'),
                        'absorption_method': item.get('absorption_method'),
                        'strategy_group': item.get('strategy_group'),
                        'package_size': item.get('package_size'),
                    }
                )
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
        # Known disease name patterns
        _DISEASE_PATTERNS = [
            'แอนแทรคโนส', 'แอนแทคโนส', 'แอคแทคโนส',
            'ฟิวซาเรียม', 'ฟิวสาเรียม', 'ฟูซาเรียม', 'ฟอซาเรียม',
            'ไฟท็อปธอร่า', 'ไฟทอปธอร่า', 'ไฟท็อปโทร่า', 'ไฟธอปทอร่า', 'ไฟท็อป',
            'ราน้ำค้าง', 'ราแป้ง', 'ราสนิม', 'ราสีชมพู', 'ราชมพู',
            'ราดำ', 'ราเขียว', 'ราขาว', 'ราเทา',
            'ใบไหม้', 'ใบจุด', 'ผลเน่า', 'รากเน่า', 'โคนเน่า',
            'กาบใบแห้ง', 'ขอบใบแห้ง', 'เมล็ดด่าง', 'ใบขีดสีน้ำตาล',
            'หอมเลื้อย', 'ใบจุดสีม่วง', 'ใบติด',
            'เน่าคอรวง', 'ใบไหม้แผลใหญ่',
        ]

        # Try known patterns first
        for pattern in _DISEASE_PATTERNS:
            if pattern in query:
                return pattern

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
        """Fallback: ค้นหาสินค้าจาก target_pest โดยตรง (ไม่ใช้ vector search)"""
        try:
            for variant in disease_variants:
                if len(variant) < 3:
                    continue
                result = self.supabase.table('products').select('*').ilike(
                    'target_pest', f'%{variant}%'
                ).limit(5).execute()

                if result.data:
                    docs = []
                    for item in result.data:
                        common_th = item.get('common_name_th') or ''
                        doc = RetrievedDocument(
                            id=str(item.get('id', '')),
                            title=item.get('product_name', ''),
                            content=f"สินค้า: {item.get('product_name', '')}\n"
                                   f"ชื่อสารไทย: {common_th}\n"
                                   f"สารสำคัญ: {item.get('active_ingredient', '')}\n"
                                   f"ใช้กำจัด: {item.get('target_pest', '')[:200] if item.get('target_pest') else ''}\n"
                                   f"พืชที่ใช้ได้: {item.get('applicable_crops', '')[:200] if item.get('applicable_crops') else ''}",
                            source="products",
                            similarity_score=0.50,  # Give reasonable score for direct match
                            metadata={
                                'product_name': item.get('product_name'),
                                'common_name_th': common_th,
                                'active_ingredient': item.get('active_ingredient'),
                                'target_pest': item.get('target_pest'),
                                'applicable_crops': item.get('applicable_crops'),
                                'category': item.get('product_category') or item.get('category'),
                                'how_to_use': item.get('how_to_use'),
                                'usage_rate': item.get('usage_rate'),
                                'usage_period': item.get('usage_period'),
                                'selling_point': item.get('selling_point'),
                                'action_characteristics': item.get('action_characteristics'),
                                'absorption_method': item.get('absorption_method'),
                                'strategy_group': item.get('strategy_group'),
                                'package_size': item.get('package_size'),
                            }
                        )
                        docs.append(doc)
                    return docs
            return []
        except Exception as e:
            logger.error(f"Target pest fallback search error: {e}")
            return []

    async def _search_diseases(self, query: str, top_k: int) -> List[RetrievedDocument]:
        """Search diseases table with vector similarity"""
        if not self.supabase or not self.openai_client:
            return []

        try:
            # Generate embedding
            embedding = await self._generate_embedding(query)
            if not embedding:
                return []

            # Call hybrid search diseases
            result = self.supabase.rpc(
                'hybrid_search_diseases',
                {
                    'query_embedding': embedding,
                    'search_query': query,
                    'vector_weight': 0.6,
                    'keyword_weight': 0.4,
                    'match_threshold': self.vector_threshold,
                    'match_count': top_k
                }
            ).execute()

            if not result.data:
                return []

            # Convert to RetrievedDocument
            docs = []
            for item in result.data:
                symptoms = item.get('symptoms', [])
                if isinstance(symptoms, list):
                    symptoms_text = ', '.join(str(s) for s in symptoms[:3])
                else:
                    symptoms_text = str(symptoms)[:200]

                doc = RetrievedDocument(
                    id=str(item.get('id', '')),
                    title=f"{item.get('name_th', '')} ({item.get('name_en', '')})",
                    content=f"โรค: {item.get('name_th', '')}\n"
                           f"สาเหตุ: {item.get('pathogen', '')}\n"
                           f"อาการ: {symptoms_text}",
                    source="diseases",
                    similarity_score=float(item.get('similarity', 0)),
                    metadata={
                        'name_th': item.get('name_th'),
                        'name_en': item.get('name_en'),
                        'category': item.get('category'),
                        'pathogen': item.get('pathogen'),
                        'symptoms': symptoms,
                    }
                )
                docs.append(doc)

            logger.info(f"    Disease search: {len(docs)} docs for '{query[:30]}...'")
            return docs

        except Exception as e:
            logger.error(f"Disease search error: {e}")
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
            # Prepare document summaries
            doc_texts = []
            for i, doc in enumerate(docs[:15], 1):  # Limit to top 15
                text = f"[{i}] {doc.title}"
                if doc.metadata.get('product_name'):
                    text += f" | สินค้า: {doc.metadata['product_name']}"
                if doc.metadata.get('target_pest'):
                    text += f" | ใช้กำจัด: {str(doc.metadata['target_pest'])[:80]}"
                if doc.metadata.get('applicable_crops'):
                    text += f" | พืช: {str(doc.metadata['applicable_crops'])[:80]}"
                if doc.metadata.get('selling_point'):
                    text += f" | จุดเด่น: {str(doc.metadata['selling_point'])[:80]}"
                if doc.metadata.get('category'):
                    text += f" | ประเภท: {doc.metadata['category']}"
                if doc.metadata.get('strategy_group'):
                    text += f" | Strategy: {doc.metadata['strategy_group']}"
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
4. สินค้า Strategy Skyrocket/Expand ให้ลำดับสูงกว่า Standard
5. ถ้าสินค้าหลายตัวคล้ายกัน ให้เลือกตัวที่ "พืช" ระบุเน้นพืชตรงกับคำถาม (เช่น "เน้นสำหรับ(ทุเรียน)" ตรงกว่า "มะม่วง, ทุเรียน")

ตอบเฉพาะตัวเลขเรียงลำดับ คั่นด้วย comma เช่น: 3,1,5,2,4"""

            response = await self.openai_client.chat.completions.create(
                model=LLM_MODEL_RERANKING,
                messages=[
                    {"role": "system", "content": "ตอบเฉพาะตัวเลขเรียงลำดับ คั่นด้วย comma"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                max_tokens=100
            )

            ranking_text = response.choices[0].message.content.strip()
            logger.info(f"    Rerank response: {ranking_text}")

            # Parse ranking
            numbers = re.findall(r'\d+', ranking_text)
            ranking_indices = [int(n) - 1 for n in numbers if 0 < int(n) <= len(docs)]

            # Build reranked list with scores
            reranked = []
            seen_indices = set()
            for rank, idx in enumerate(ranking_indices):
                if idx not in seen_indices and idx < len(docs):
                    doc = docs[idx]
                    # Assign rerank score based on position (higher = better)
                    doc.rerank_score = 1.0 - (rank / len(ranking_indices))
                    reranked.append(doc)
                    seen_indices.add(idx)

            # Add remaining docs with lower scores
            for i, doc in enumerate(docs):
                if i not in seen_indices:
                    doc.rerank_score = 0.3  # Default low score
                    reranked.append(doc)

            return reranked

        except Exception as e:
            logger.warning(f"LLM rerank failed: {e}, using similarity scores")
            return sorted(docs, key=lambda x: x.similarity_score, reverse=True)
