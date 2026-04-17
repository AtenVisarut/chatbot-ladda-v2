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
import re

from app.services.rag import (
    QueryAnalysis,
    RetrievalResult,
    GroundingResult,
    AgenticRAGResponse,
    IntentType
)
from app.utils.text_processing import post_process_answer, generate_thai_disease_variants, validate_numbers_against_source
from app.services.rag.retrieval_agent import _plant_matches_crops
from app.config import LLM_MODEL_RESPONSE_GEN, LLM_TEMP_RESPONSE_GEN, LLM_TOKENS_RESPONSE_GEN
from app.prompts import (
    PRODUCT_QA_PROMPT,
    GREETINGS,
    ERROR_PROCESSING,
    ERROR_NO_DATA,
    get_no_data_response,
)

logger = logging.getLogger(__name__)


def _disease_in_pest_text(variant: str, pest_text: str) -> bool:
    """Boundary-aware disease matching against pest text.
    Prevents 'ใบไหม้' from matching inside 'กาบใบไหม้' (different disease).
    Requires the variant to be preceded by start-of-string, space, comma, paren,
    or common Thai prefixes: 'โรค', 'เชื้อรา', 'เชื้อ', 'รา'.
    """
    escaped = re.escape(variant.lower())
    pattern = r'(?:^|[\s,;(]|โรคเชื้อรา|เชื้อรา|โรครา|โรค|เชื้อ|รา)' + escaped
    return bool(re.search(pattern, pest_text.lower()))


def _any_disease_variant_matches(variants: list, pest_text: str) -> bool:
    """Check if any disease variant matches pest text with boundary awareness."""
    return any(_disease_in_pest_text(v, pest_text) for v in variants)


def _get_pest_text_from_meta(metadata: dict) -> str:
    """Get combined pest text from metadata dict (5 pest columns)."""
    from app.utils.pest_columns import get_pest_text
    return get_pest_text(metadata)


class ResponseGeneratorAgent:
    """
    Agent 4: Response Generation
    Creates the final user-facing response using LLM with verified product data
    Primary: Claude Haiku via OpenRouter (fast + low hallucination)
    Fallback: GPT-4o via OpenAI (if OpenRouter fails)
    """

    def __init__(self, openai_client=None):
        self.openai_client = openai_client

    async def generate(
        self,
        query_analysis: QueryAnalysis,
        retrieval_result: RetrievalResult,
        grounding_result: GroundingResult,
        context: str = ""
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

            # Track final confidence/grounded (may be overridden if disease/crop match triggers)
            final_confidence = grounding_result.confidence
            final_grounded = grounding_result.is_grounded

            # Handle no data case — grounding says not relevant
            if not grounding_result.is_grounded:
                # Check if retrieval promoted a crop-specific product (override grounding)
                has_crop_specific_top = False
                plant_type = query_analysis.entities.get('plant_type', '')
                if plant_type and retrieval_result.documents:
                    top_doc = retrieval_result.documents[0]
                    crops = str(top_doc.metadata.get('applicable_crops') or '')
                    selling = str(top_doc.metadata.get('selling_point') or '')
                    if plant_type in crops and ('เน้นสำหรับ' in crops or f'{plant_type}อันดับ' in selling):
                        has_crop_specific_top = True
                        logger.info(f"  - Crop-specific override: {top_doc.title} is at position 1")

                # Check if a specific product was asked about AND found in DB
                has_product_in_query = (
                    bool(query_analysis.entities.get('product_name'))
                    and query_analysis.entities.get('_product_from_query', False)
                )
                has_documents = bool(retrieval_result.documents)

                # Check if disease query matched via pest columns (fallback products)
                has_disease_match = False
                disease_name = query_analysis.entities.get('disease_name', '')
                _BROAD_DISEASE_TERMS_OVERRIDE = {'เชื้อรา', 'โรคเชื้อรา', 'โรคพืช', 'โรคราพืช'}
                # Broad disease terms: match if any Fungicide doc exists
                if disease_name in _BROAD_DISEASE_TERMS_OVERRIDE and has_documents and query_analysis.intent in (IntentType.DISEASE_TREATMENT, IntentType.PRODUCT_RECOMMENDATION):
                    for doc in retrieval_result.documents[:10]:
                        cat = str(doc.metadata.get('category') or doc.metadata.get('product_category') or '').lower()
                        if 'fungicide' in cat:
                            has_disease_match = True
                            logger.info(f"  - Disease override: broad term '{disease_name}' matched Fungicide doc {doc.title}")
                            break

                if not has_disease_match and disease_name and has_documents and query_analysis.intent in (IntentType.DISEASE_TREATMENT, IntentType.PRODUCT_RECOMMENDATION):
                    disease_variants = generate_thai_disease_variants(disease_name)
                    for doc in retrieval_result.documents[:10]:
                        _pest_text = _get_pest_text_from_meta(doc.metadata)
                        if _any_disease_variant_matches(disease_variants, _pest_text):
                            has_disease_match = True
                            logger.info(f"  - Disease override: '{disease_name}' found in {doc.title} pest columns")
                            break

                # Also try extracting disease from original query (LLM may have changed disease name)
                if not has_disease_match and has_documents and query_analysis.intent in (IntentType.DISEASE_TREATMENT, IntentType.PRODUCT_RECOMMENDATION):
                    from app.utils.text_processing import diacritics_match as _dm
                    from app.services.disease.constants import DISEASE_PATTERNS_SORTED as _DP, get_canonical as _gc
                    original_disease = ''
                    for pattern in _DP:
                        if _dm(query_analysis.original_query, pattern):
                            original_disease = _gc(pattern)
                            break
                    if original_disease and original_disease != disease_name:
                        original_variants = generate_thai_disease_variants(original_disease)
                        for doc in retrieval_result.documents[:5]:
                            _pest_text = _get_pest_text_from_meta(doc.metadata)
                            if _any_disease_variant_matches(original_variants, _pest_text):
                                has_disease_match = True
                                logger.info(f"  - Disease override (original query): '{original_disease}' found in {doc.title} pest columns")
                                break

                # Also check possible_diseases from symptom→pathogen mapping
                if not has_disease_match and has_documents and query_analysis.intent in (IntentType.DISEASE_TREATMENT, IntentType.PRODUCT_RECOMMENDATION):
                    _possible_diseases = query_analysis.entities.get('possible_diseases', [])
                    for pd in _possible_diseases:
                        pd_variants = generate_thai_disease_variants(pd)
                        for doc in retrieval_result.documents[:10]:
                            _pest_text = _get_pest_text_from_meta(doc.metadata)
                            if _any_disease_variant_matches(pd_variants, _pest_text):
                                has_disease_match = True
                                logger.info(f"  - Disease override (symptom→pathogen): '{pd}' found in {doc.title} pest columns")
                                break
                        if has_disease_match:
                            break

                # Check if pest query matched insecticide products via pest columns
                has_pest_match = False
                pest_name = query_analysis.entities.get('pest_name', '')
                _BROAD_PEST_TERMS_OVERRIDE = {'แมลง', 'ศัตรูพืช', 'แมลงศัตรูพืช'}
                if pest_name and has_documents and query_analysis.intent in (IntentType.PEST_CONTROL, IntentType.PRODUCT_RECOMMENDATION):
                    if pest_name in _BROAD_PEST_TERMS_OVERRIDE:
                        # Broad pest term — any Insecticide product counts as a match
                        for doc in retrieval_result.documents[:10]:
                            cat = str(doc.metadata.get('category') or '').lower()
                            if 'insecticide' in cat:
                                has_pest_match = True
                                logger.info(f"  - Pest override (broad term): '{pest_name}' → Insecticide product '{doc.title}' found")
                                break
                    else:
                        for doc in retrieval_result.documents[:10]:
                            _pest_text = _get_pest_text_from_meta(doc.metadata).lower()
                            cat = str(doc.metadata.get('category') or '').lower()
                            if pest_name.lower() in _pest_text and 'insecticide' in cat:
                                has_pest_match = True
                                logger.info(f"  - Pest override: '{pest_name}' found in {doc.title} pest columns")
                                break

                # Check if weed query matched herbicide products
                has_weed_match = False
                if has_documents and query_analysis.intent == IntentType.WEED_CONTROL:
                    for doc in retrieval_result.documents[:10]:
                        cat = str(doc.metadata.get('category') or '').lower()
                        if 'herbicide' in cat:
                            has_weed_match = True
                            logger.info(f"  - Weed override: herbicide '{doc.title}' found in results")
                            break

                if not has_documents or (
                    grounding_result.confidence < 0.2
                    and not has_crop_specific_top
                    and not (has_product_in_query and has_documents)
                    and not has_disease_match
                    and not has_pest_match
                    and not has_weed_match
                ):
                    return self._generate_no_data_response(query_analysis)

                # Product found but grounding failed — let LLM explain using actual data
                if has_product_in_query and has_documents:
                    logger.info(f"  - Product-specific override: bypassing grounding for '{query_analysis.entities.get('product_name')}'")
                    # LLM will use the product data to explain (e.g. "ราเซอร์ใช้กำจัดวัชพืช ใช้ได้กับ...")

                # Override confidence when bypass triggered (don't keep 0.00)
                if has_disease_match:
                    final_confidence = max(final_confidence, 0.65)
                    final_grounded = True
                    logger.info(f"  - Confidence override: disease match → {final_confidence:.2f}")
                elif has_pest_match:
                    final_confidence = max(final_confidence, 0.65)
                    final_grounded = True
                    logger.info(f"  - Confidence override: pest match → {final_confidence:.2f}")
                elif has_weed_match:
                    final_confidence = max(final_confidence, 0.65)
                    final_grounded = True
                    logger.info(f"  - Confidence override: weed match → {final_confidence:.2f}")
                elif has_crop_specific_top:
                    final_confidence = max(final_confidence, 0.60)
                    final_grounded = True
                    logger.info(f"  - Confidence override: crop-specific top → {final_confidence:.2f}")
                elif has_product_in_query and has_documents:
                    final_confidence = max(final_confidence, 0.70)
                    final_grounded = True
                    logger.info(f"  - Confidence override: product in query → {final_confidence:.2f}")

            # Generate answer from verified product data using LLM
            answer = await self._generate_llm_response(
                query_analysis, retrieval_result, grounding_result, context
            )

            # Post-process answer (remove markdown artifacts)
            answer = post_process_answer(answer)

            # Validate numbers against source docs
            if retrieval_result and retrieval_result.documents:
                num_check = validate_numbers_against_source(answer, retrieval_result.documents[:5])
                if not num_check["valid"]:
                    bad_count = len([m for m in num_check['mismatches'] if not m['found_in_source']])
                    logger.error(f"  - Number validation FAILED: {bad_count} mismatches found")
                    # Append safety warning to answer
                    answer += "\n\n(หมายเหตุ: กรุณาตรวจสอบอัตราการใช้จากฉลากสินค้าอีกครั้งค่ะ)"

            return AgenticRAGResponse(
                answer=answer,
                confidence=final_confidence,
                citations=grounding_result.citations,
                intent=query_analysis.intent,
                is_grounded=final_grounded,
                sources_used=retrieval_result.sources_used,
                query_analysis=query_analysis,
                retrieval_result=retrieval_result,
                grounding_result=grounding_result
            )

        except Exception as e:
            logger.error(f"ResponseGeneratorAgent error: {e}", exc_info=True)
            return AgenticRAGResponse(
                answer=ERROR_PROCESSING,
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
        grounding_result: GroundingResult,
        context: str = ""
    ) -> str:
        """Generate formatted response using LLM with verified product data"""

        if not self.openai_client:
            return self._build_fallback_answer(retrieval_result, grounding_result)

        # Keep all products (including Standard) — just sort by strategy priority
        docs_to_use = retrieval_result.documents[:7]

        # Guarantee Skyrocket/Expand in top 7 (must match query category)
        # Skip when user asks about a specific product — don't inject unrelated products
        _priority_strategies = {'Skyrocket', 'Expand'}
        _has_priority = any(
            d.metadata.get('strategy') in _priority_strategies for d in docs_to_use
        )
        _skip_inject = bool(query_analysis.entities.get('product_name')) and query_analysis.intent in (IntentType.PRODUCT_INQUIRY, IntentType.USAGE_INSTRUCTION)
        if not _has_priority and len(docs_to_use) >= 7 and not _skip_inject:
            # Determine expected category from intent
            _INTENT_TO_CAT = {
                'disease_treatment': 'fungicide', 'pest_control': 'insecticide',
                'weed_control': 'herbicide',
            }
            _intent_val = query_analysis.intent.value if hasattr(query_analysis.intent, 'value') else str(query_analysis.intent)
            _expected_cat = _INTENT_TO_CAT.get(_intent_val, '')
            # Search beyond top 7 for matching Skyrocket/Expand
            _top_ids = {d.id for d in docs_to_use}
            for d in retrieval_result.documents[7:]:
                _strat = d.metadata.get('strategy', '')
                _cat = (d.metadata.get('category') or '').lower()
                if _strat in _priority_strategies and d.id not in _top_ids:
                    if not _expected_cat or _expected_cat in _cat:
                        docs_to_use[-1] = d  # Replace lowest-ranked
                        logger.info(f"  - Guaranteed {_strat} slot: injected '{d.title}' into top 7 (category: {_cat})")
                        break

        # Sort by strategy priority: Skyrocket=Expand > Natural=Standard=Cosmic-star
        # ensures Skyrocket/Expand appear first in product context sent to LLM
        # Cosmic-star = Biostimulants/Fertilizer group — equal priority, not pushed down
        _STRATEGY_ORDER = {'Skyrocket': 0, 'Expand': 0, 'Natural': 1, 'Standard': 1, 'Cosmic-star': 1}
        docs_to_use.sort(key=lambda d: _STRATEGY_ORDER.get(d.metadata.get('strategy', ''), 3))

        # Rescue: ensure disease-matching product is in docs_to_use
        # If query is about disease but no doc in docs_to_use has the disease in pest columns,
        # search full retrieval results and add the matching doc
        if query_analysis.intent.value in ('disease_treatment', 'product_recommendation'):
            _rescue_disease = query_analysis.entities.get('disease_name', '')
            # Build list of diseases to rescue: disease_name + possible_diseases (from symptom mapping)
            _rescue_diseases_list = []
            if _rescue_disease:
                _rescue_diseases_list.append(_rescue_disease)
            _possible_diseases = query_analysis.entities.get('possible_diseases', [])
            for pd in _possible_diseases:
                if pd not in _rescue_diseases_list:
                    _rescue_diseases_list.append(pd)

            for _rd in _rescue_diseases_list:
                _rescue_variants = generate_thai_disease_variants(_rd)
                _has_in_docs_to_use = any(
                    _any_disease_variant_matches(_rescue_variants, _get_pest_text_from_meta(d.metadata))
                    for d in docs_to_use
                )
                if not _has_in_docs_to_use:
                    for doc in retrieval_result.documents:
                        if doc in docs_to_use:
                            continue
                        _pest_text = _get_pest_text_from_meta(doc.metadata)
                        if _any_disease_variant_matches(_rescue_variants, _pest_text):
                            docs_to_use.insert(0, doc)
                            logger.info(f"  - Rescued disease-matching product into docs_to_use: {doc.title} (for disease: {_rd})")
                            break

        # Filter: when a crop-specific product exists, remove non-specific variants of same family
        # e.g., if พรีดิคท์ 25 is for ทุเรียน specifically, remove พรีดิคท์ 10% and 15
        plant_type_filter = query_analysis.entities.get('plant_type', '')
        if plant_type_filter:
            crop_specific_families = {}
            for doc in docs_to_use:
                crops = str(doc.metadata.get('applicable_crops') or '')
                selling = str(doc.metadata.get('selling_point') or '')
                product_name = doc.metadata.get('product_name', doc.title)
                if plant_type_filter in crops and ('เน้นสำหรับ' in crops or f'{plant_type_filter}อันดับ' in selling):
                    # Extract product family name (first word, e.g. "พรีดิคท์" from "พรีดิคท์ 25")
                    family_key = product_name.split()[0] if ' ' in product_name else product_name
                    crop_specific_families[family_key] = product_name

            if crop_specific_families:
                filtered = []
                for doc in docs_to_use:
                    product_name = doc.metadata.get('product_name', doc.title)
                    crops = str(doc.metadata.get('applicable_crops') or '')
                    selling = str(doc.metadata.get('selling_point') or '')
                    is_crop_specific = plant_type_filter in crops and (
                        'เน้นสำหรับ' in crops or f'{plant_type_filter}อันดับ' in selling
                    )
                    if not is_crop_specific:
                        family_key = product_name.split()[0] if ' ' in product_name else product_name
                        if family_key in crop_specific_families:
                            logger.info(f"  - Removed non-specific variant: {product_name} (family: {family_key})")
                            continue  # Skip non-specific variant
                    filtered.append(doc)
                if filtered:
                    docs_to_use = filtered

        # Pre-filter: when plant_type is known, remove crop-mismatched docs before LLM
        # to prevent LLM from being overwhelmed by "ห้ามแนะนำ" warnings (9/10 mismatch → "ไม่มีข้อมูล")
        # Skip when user asks about a specific product (e.g. "โม-เซ่ ใช้กับทุเรียนได้ไหม")
        # IMPORTANT: Exempt disease/pest-matching docs — they must stay even if crop doesn't match
        _product_from_query = query_analysis.entities.get('_product_from_query', False)
        _queried_product_name = query_analysis.entities.get('product_name', '')
        _is_product_inquiry = query_analysis.intent in (IntentType.PRODUCT_INQUIRY, IntentType.USAGE_INSTRUCTION)
        # Skip crop filter when user asks about a specific product (from query OR context)
        # e.g. "คอนทาฟ ใช้กับมันสำปะหลังได้ไหม" → don't filter out คอนทาฟ
        _skip_crop_filter = _product_from_query or (_is_product_inquiry and bool(_queried_product_name))
        if plant_type_filter and docs_to_use and not _skip_crop_filter:
            # Build disease/pest check for exemption (prevent ราสีชมพู bug: crop filter kills disease doc)
            _ex_disease = query_analysis.entities.get('disease_name', '')
            _ex_possible = query_analysis.entities.get('possible_diseases', [])
            _ex_pest = query_analysis.entities.get('pest_name', '')

            def _exempt_from_crop_filter(d):
                """Keep doc if pest columns match AND crop is compatible.
                Tightened: if applicable_crops is specified but doesn't include
                the queried plant, do NOT exempt even if disease/pest matches.
                This prevents wrong-crop context (e.g. 'ทรงพุ่ม' for rice).
                """
                # Check crop compatibility first — if crop is specified but doesn't match, reject
                _crops = str(d.metadata.get('applicable_crops') or '')
                if _crops.strip() and plant_type_filter and not _plant_matches_crops(plant_type_filter, _crops):
                    return False
                _pt = _get_pest_text_from_meta(d.metadata)
                if _ex_disease and _any_disease_variant_matches(
                        generate_thai_disease_variants(_ex_disease), _pt):
                    return True
                for _pd in _ex_possible:
                    if _any_disease_variant_matches(
                            generate_thai_disease_variants(_pd), _pt):
                        return True
                if _ex_pest and _ex_pest.lower() in _pt.lower():
                    return True
                return False

            # Prohibition patterns — products explicitly banned for this crop
            _prohibit_pats = [
                f"ห้ามใช้ใน{plant_type_filter}", f"ห้ามใช้กับ{plant_type_filter}",
                f"ไม่ควรใช้ใน{plant_type_filter}",
            ]
            if plant_type_filter == "ข้าว":
                _prohibit_pats.extend(["ห้ามใช้ในนาข้าว", "ห้ามใช้ในข้าว"])

            def _is_prohibited_for_crop(d):
                _all = f"{d.metadata.get('applicable_crops', '')} {d.metadata.get('how_to_use', '')}"
                return any(p in _all for p in _prohibit_pats)

            _crop_matched = [
                d for d in docs_to_use
                if (not _is_prohibited_for_crop(d))
                and (_plant_matches_crops(plant_type_filter, str(d.metadata.get('applicable_crops') or ''))
                     or _exempt_from_crop_filter(d))
            ]
            if _crop_matched:
                _removed_count = len(docs_to_use) - len(_crop_matched)
                if _removed_count > 0:
                    docs_to_use = _crop_matched
                    logger.info(f"  - Crop pre-filter: kept {len(_crop_matched)} docs (incl disease/pest exempt), removed {_removed_count} mismatched for '{plant_type_filter}'")

        # =====================================================================
        # Category pre-filter for NUTRIENT_SUPPLEMENT: keep only Biostimulant/PGR
        # Prevents recommending Fungicide/Insecticide for "บำรุง" queries
        # =====================================================================
        # Also trigger for problem_type='nutrient' from Stage 0 (fallback when LLM misclassifies intent)
        _is_nutrient_query = (
            query_analysis.intent == IntentType.NUTRIENT_SUPPLEMENT
            or query_analysis.entities.get('problem_type') == 'nutrient'
        )
        if _is_nutrient_query and docs_to_use and not _product_from_query:
            # Narrow categories when user asks specifically for fertilizer/PGR/biostimulant
            _q_lower = query_analysis.original_query.lower()
            if any(kw in _q_lower for kw in ['ปุ๋ยเกล็ด', 'ปุ๋ยnpk', 'ปุ๋ยน้ำ', 'npk', 'ปุ๋ยสูตร']):
                _NUTRIENT_CATS = {'fertilizer'}
            elif any(kw in _q_lower for kw in ['ฮอร์โมน', 'pgr', 'เร่งดอก', 'ยับยั้งใบอ่อน', 'ราดสาร', 'ชะลอ']):
                _NUTRIENT_CATS = {'pgr'}
            elif any(kw in _q_lower for kw in ['biostimulant', 'สาหร่าย', 'ฟื้นฟูต้น', 'กรดอะมิโน']):
                _NUTRIENT_CATS = {'biostimulants'}
            else:
                _NUTRIENT_CATS = {'biostimulants', 'pgr', 'fertilizer'}
            _nutrient_docs = [
                d for d in docs_to_use
                if any(nc in str(d.metadata.get('category') or d.metadata.get('product_category') or '').lower()
                       for nc in _NUTRIENT_CATS)
                or (('biostimulants' in _NUTRIENT_CATS) and bool(d.metadata.get('biostimulant')))
                or (('pgr' in _NUTRIENT_CATS) and bool(d.metadata.get('pgr_hormones')))
            ]
            if _nutrient_docs:
                _removed_cat = len(docs_to_use) - len(_nutrient_docs)
                if _removed_cat > 0:
                    docs_to_use = _nutrient_docs
                    logger.info(f"  - Nutrient category pre-filter: kept {len(_nutrient_docs)}, removed {_removed_cat} non-nutrient docs")
            else:
                # No nutrient products found — let LLM answer with constraint (don't return early → causes silent)
                logger.warning("  - Nutrient filter: 0 nutrient docs, will let LLM answer with nutrient constraint")

        # =====================================================================
        # Disease/Pest pre-filter: keep only docs whose pest columns match
        # the queried disease/pest. Prevents recommending generic products
        # that don't specifically target the user's problem.
        # e.g. "ใบจุดสีน้ำตาล" → remove products for "ใบจุดสนิม"
        # e.g. "เพลี้ยแป้ง" → remove products for "เพลี้ยไฟ"
        # =====================================================================
        _filter_disease = query_analysis.entities.get('disease_name', '')
        _filter_pest = query_analysis.entities.get('pest_name', '')

        # Broad disease terms — skip pre-filter (category + crop filter is sufficient)
        _BROAD_DISEASE_TERMS = {'เชื้อรา', 'โรคเชื้อรา', 'โรคพืช', 'โรคราพืช'}

        if _filter_disease and docs_to_use and query_analysis.intent.value in (
                'disease_treatment', 'product_recommendation'):
            if _filter_disease in _BROAD_DISEASE_TERMS:
                logger.info(f"  - Disease pre-filter: SKIPPED for broad term '{_filter_disease}' (category filter sufficient)")
            else:
                # Only filter by the EXACT disease user asked about, NOT possible_diseases
                # (possible_diseases are broad pathogens like แอนแทรคโนส that most fungicides match)
                _check_diseases = [_filter_disease]
                _disease_filtered = []
                for d in docs_to_use:
                    _pt = _get_pest_text_from_meta(d.metadata)
                    for _cd in _check_diseases:
                        if _any_disease_variant_matches(
                                generate_thai_disease_variants(_cd), _pt):
                            _disease_filtered.append(d)
                            break
                if _disease_filtered:
                    _removed = len(docs_to_use) - len(_disease_filtered)
                    if _removed > 0:
                        docs_to_use = _disease_filtered
                        logger.info(f"  - Disease pre-filter: kept {len(_disease_filtered)} matching, removed {_removed} non-matching for '{_filter_disease}'")
                else:
                    logger.info(f"  - Disease pre-filter: 0 docs match '{_filter_disease}' — keeping all (mismatch check will handle)")

        elif _filter_pest and docs_to_use and query_analysis.intent.value in (
                'pest_control', 'product_recommendation'):
            # Skip pre-filter for broad/generic pest terms — these are category-level,
            # not specific pests. The intent→category mapping already ensures Insecticide products.
            _BROAD_PEST_TERMS = {'แมลง', 'ศัตรูพืช', 'แมลงศัตรูพืช'}
            if _filter_pest in _BROAD_PEST_TERMS:
                logger.info(f"  - Pest pre-filter: SKIPPED for broad term '{_filter_pest}' (category filter sufficient)")
            else:
                _pest_filtered = [
                    d for d in docs_to_use
                    if _filter_pest.lower() in _get_pest_text_from_meta(d.metadata).lower()
                ]
                if _pest_filtered:
                    _removed = len(docs_to_use) - len(_pest_filtered)
                    if _removed > 0:
                        docs_to_use = _pest_filtered
                        logger.info(f"  - Pest pre-filter: kept {len(_pest_filtered)} matching, removed {_removed} non-matching for '{_filter_pest}'")
                else:
                    logger.info(f"  - Pest pre-filter: 0 docs match '{_filter_pest}' — keeping all")

        # Early extract: disease from conversation context for follow-up queries
        # (full extraction + assignment to disease_name happens later at line ~427)
        # Skip for WEED_CONTROL / PEST_CONTROL — disease context is irrelevant for these intents
        context_disease = ''
        _skip_disease_context = query_analysis.intent in (IntentType.WEED_CONTROL, IntentType.PEST_CONTROL)
        if context and not query_analysis.entities.get('disease_name', '') and not _skip_disease_context:
            from app.utils.text_processing import diacritics_match as _dm_early
            from app.services.disease.constants import DISEASE_PATTERNS_SORTED as _DP_EARLY, get_canonical as _gc_early
            _orig_q = query_analysis.original_query
            _has_disease_in_query = any(_dm_early(_orig_q, _p) for _p in _DP_EARLY)
            if not _has_disease_in_query:
                for _pat in _DP_EARLY:
                    if _dm_early(context, _pat):
                        context_disease = _gc_early(_pat)
                        break

        # Filter out products that don't match disease from context (follow-up queries)
        # e.g. "มีตัวอื่นไหม" after ฟิวซาเรียม → remove fungicides that don't target ฟิวซาเรียม
        if context_disease and docs_to_use:
            _ctx_variants = generate_thai_disease_variants(context_disease)
            _disease_matched = [
                d for d in docs_to_use
                if _any_disease_variant_matches(_ctx_variants, _get_pest_text_from_meta(d.metadata))
            ]
            _disease_unmatched = [d for d in docs_to_use if d not in _disease_matched]
            if _disease_matched:
                # Keep only disease-matched products; unmatched are hidden from LLM
                docs_to_use = _disease_matched
                logger.info(f"  - Context disease filter: kept {len(_disease_matched)} docs matching '{context_disease}', removed {len(_disease_unmatched)}")
            else:
                logger.info(f"  - Context disease filter: no docs match '{context_disease}' — keeping all (mismatch_note will block)")

        # Build product data context from retrieval results
        plant_type = query_analysis.entities.get('plant_type', '')
        product_context_parts = []
        for i, doc in enumerate(docs_to_use, 1):
            meta = doc.metadata
            part = f"[สินค้า {i}] {meta.get('product_name', doc.title)}"
            if meta.get('active_ingredient'):
                part += f" (สารสำคัญ: {meta['active_ingredient']})"
            part += "\n"
            if meta.get('common_name_th'):
                part += f"  ชื่อสารไทย: {meta['common_name_th']}\n"
            if meta.get('category'):
                part += f"  ประเภท: {meta['category']}\n"
            _pest_disp = _get_pest_text_from_meta(meta)
            if _pest_disp:
                part += f"  ใช้กำจัด: {_pest_disp}\n"
            if meta.get('applicable_crops'):
                _crops_str = str(meta['applicable_crops'])
                part += f"  พืชที่ใช้ได้: {_crops_str}\n"
                # Warn LLM if product is not suitable for user's plant_type
                if plant_type and _crops_str.strip():
                    _all_text = f"{_crops_str} {str(meta.get('how_to_use') or '')}"
                    _prohibit_kw = [f"ห้ามใช้ใน{plant_type}", f"ห้ามใช้กับ{plant_type}",
                                    f"ห้ามใช้ในนาข้าว" if plant_type == "ข้าว" else "",
                                    f"ห้ามใช้ในนา{plant_type}" if plant_type == "ข้าว" else ""]
                    _prohibit_kw = [p for p in _prohibit_kw if p]
                    if any(p in _all_text for p in _prohibit_kw):
                        part += f"  [!! ห้ามใช้กับ{plant_type} — ห้ามแนะนำสินค้านี้เด็ดขาด !!]\n"
                    elif not _plant_matches_crops(plant_type, _crops_str):
                        part += f"  [!! สินค้านี้ไม่ได้ระบุว่าใช้กับ{plant_type}ได้ — ห้ามแนะนำสำหรับ{plant_type} !!]\n"
            if meta.get('usage_rate'):
                part += f"  อัตราใช้: {meta['usage_rate']}\n"
            if meta.get('how_to_use'):
                part += f"  วิธีใช้: {str(meta['how_to_use'])}\n"
            if meta.get('usage_period'):
                part += f"  ช่วงการใช้: {str(meta['usage_period'])}\n"
            if meta.get('selling_point'):
                part += f"  จุดเด่น: {str(meta['selling_point'])}\n"
            if meta.get('action_characteristics'):
                part += f"  ลักษณะการออกฤทธิ์: {str(meta['action_characteristics'])}\n"
            if meta.get('absorption_method'):
                part += f"  การดูดซึม: {str(meta['absorption_method'])}\n"
            if meta.get('package_size'):
                part += f"  ขนาดบรรจุ: {meta['package_size']}\n"
            if meta.get('phytotoxicity'):
                part += f"  ความเป็นพิษต่อพืช: {meta['phytotoxicity']}\n"
            if meta.get('chemical_group_rac'):
                part += f"  กลุ่มสาร (RAC): {meta['chemical_group_rac']}\n"
            if meta.get('caution_notes'):
                part += f"  ข้อควรระวังเพิ่มเติม: {meta['caution_notes']}\n"
            # strategy is internal-only — NOT sent to LLM to prevent leaking to users
            product_context_parts.append(part)

        product_context = "\n".join(product_context_parts)

        # Relevant products from grounding — inject crop-specific products from retrieval
        relevant = list(grounding_result.relevant_products)
        plant_type = query_analysis.entities.get('plant_type', '')
        if plant_type and docs_to_use:
            for doc in docs_to_use[:3]:
                crops = str(doc.metadata.get('applicable_crops') or '')
                selling = str(doc.metadata.get('selling_point') or '')
                product_name = doc.metadata.get('product_name', doc.title)
                if _plant_matches_crops(plant_type, crops) and ('เน้นสำหรับ' in crops or f'{plant_type}อันดับ' in selling):
                    if product_name not in relevant:
                        relevant.insert(0, product_name)
                        logger.info(f"  - Injected crop-specific product into relevant: {product_name}")
                    break
        relevant_str = ", ".join(relevant) if relevant else "(ทั้งหมดที่ค้นพบ)"

        # Build context section for follow-up questions
        context_section = ""
        if context:
            context_section = f"""บริบทการสนทนาก่อนหน้า:
{context[:1500]}

สำคัญมาก:
1. ถ้ามี [สินค้าที่กำลังคุยอยู่] ให้ตอบเกี่ยวกับสินค้านั้นเป็นหลัก ห้ามเปลี่ยนเป็นสินค้าอื่น
2. ถ้าผู้ใช้ถามต่อเนื่อง (เช่น "ใช้กับพืชนี้ได้ไหม" "อัตราเท่าไหร่" "ใช้ช่วงไหน") ต้องตอบเกี่ยวกับสินค้าตัวเดิม
3. ถ้าสินค้าที่กำลังคุยไม่เหมาะกับคำถาม ให้บอกตรงๆ ว่าไม่เหมาะ แล้วค่อยเสนอทางเลือกอื่น

"""

        # Nutrient query constraint: tell LLM to focus on biostimulant/PGR data, not recommend Fungicide
        nutrient_constraint_note = ""
        if _is_nutrient_query and not _product_from_query:
            _has_nutrient_data = any(
                bool(d.metadata.get('biostimulant')) or bool(d.metadata.get('pgr_hormones'))
                for d in docs_to_use
            )
            if _has_nutrient_data:
                nutrient_constraint_note = """
[คำเตือนสำคัญ — คำถามเรื่องบำรุง/เร่งดอก/เร่งผล]
→ ห้ามแนะนำสินค้าในฐานะยาป้องกันโรค(Fungicide) หรือยาแมลง(Insecticide)
→ ให้แนะนำเฉพาะสินค้าที่มีข้อมูล "สารกระตุ้นชีวภาพ" หรือ "ฮอร์โมนพืช" เท่านั้น
→ ถ้าสินค้ามีคุณสมบัติทั้งป้องกันโรคและบำรุง ให้เน้นเฉพาะด้านบำรุง/เร่ง ที่ตรงกับคำถาม
"""
            else:
                nutrient_constraint_note = """
[คำเตือนสำคัญ — คำถามเรื่องบำรุง/เร่งดอก/เร่งผล]
→ ข้อมูลสินค้าที่พบไม่ได้ระบุว่าใช้บำรุง/เร่งดอก/เร่งผลโดยตรง
→ ให้ตอบว่า: "สำหรับการบำรุง/เร่งดอก/เร่งผล น้องลัดดาแนะนำปรึกษาเจ้าหน้าที่ ICP Ladda โดยตรงเพื่อคำแนะนำที่เหมาะสมค่ะ"
→ ห้ามแนะนำ Fungicide/Insecticide สำหรับคำถามบำรุง
"""
            logger.info(f"  - Nutrient constraint injected into prompt (has_data={_has_nutrient_data})")

        # Validate disease-product match: check if queried disease is in any product's target_pest
        disease_mismatch_note = ""
        disease_match_note = ""
        disease_name = query_analysis.entities.get('disease_name', '')

        # Also extract disease from original query (LLM may misidentify)
        from app.utils.text_processing import diacritics_match as _dm_gen
        from app.services.disease.constants import DISEASE_PATTERNS_SORTED as _DP_GEN, get_canonical as _gc_gen
        original_disease_gen = ''
        for _pat in _DP_GEN:
            if _dm_gen(query_analysis.original_query, _pat):
                original_disease_gen = _gc_gen(_pat)
                break

        # Extract disease from conversation context (follow-up like "มีตัวอื่นไหม")
        # NOTE: context_disease already initialized earlier (before doc filter block)
        # Skip for WEED_CONTROL / PEST_CONTROL — disease from previous topic is irrelevant
        if not context_disease and context and not disease_name and not original_disease_gen and not _skip_disease_context:
            for _pat in _DP_GEN:
                if _dm_gen(context, _pat):
                    context_disease = _gc_gen(_pat)
                    break
        if context_disease and not disease_name:
            disease_name = context_disease
            logger.info(f"  - Disease extracted from context (follow-up): '{context_disease}'")

        # Include more intents for follow-up queries that carry disease from context
        _disease_check_intents = ('disease_treatment', 'product_recommendation', 'product_inquiry', 'unknown', 'general_agriculture')
        if query_analysis.intent.value in _disease_check_intents and (disease_name or original_disease_gen):
            # Check with entity disease_name first, then original query disease
            disease_found_in_products = False
            matched_disease_label = ''
            matched_product_name = ''

            # Also check possible_diseases from symptom→pathogen mapping
            possible_diseases = query_analysis.entities.get('possible_diseases', [])
            diseases_to_check = [disease_name, original_disease_gen] + possible_diseases

            for check_disease in diseases_to_check:
                if not check_disease:
                    continue
                check_variants = generate_thai_disease_variants(check_disease)
                for doc in docs_to_use:
                    _pest_text = _get_pest_text_from_meta(doc.metadata)
                    if _any_disease_variant_matches(check_variants, _pest_text):
                        disease_found_in_products = True
                        matched_disease_label = check_disease
                        matched_product_name = doc.metadata.get('product_name', doc.title)
                        break
                if disease_found_in_products:
                    break

            if not disease_found_in_products and disease_name:
                # Safety check: re-verify with ALL disease variants against ALL retrieved docs
                # (not just docs_to_use which may have been reduced by crop-filter)
                _all_check_variants = generate_thai_disease_variants(disease_name)
                _all_docs = retrieval_result.documents if retrieval_result else docs_to_use
                _really_missing = not any(
                    _any_disease_variant_matches(_all_check_variants, _get_pest_text_from_meta(d.metadata))
                    for d in _all_docs
                )
                # If found in full docs but not in docs_to_use → rescue the matching doc
                if not _really_missing and not any(
                    _any_disease_variant_matches(_all_check_variants, _get_pest_text_from_meta(d.metadata))
                    for d in docs_to_use
                ):
                    # Inject the disease-matching doc into docs_to_use
                    for d in _all_docs:
                        if _any_disease_variant_matches(_all_check_variants, _get_pest_text_from_meta(d.metadata)):
                            if d not in docs_to_use:
                                if len(docs_to_use) >= 7:
                                    docs_to_use[-1] = d
                                else:
                                    docs_to_use.append(d)
                                disease_found_in_products = True
                                matched_disease_label = disease_name
                                matched_product_name = d.metadata.get('product_name', d.title)
                                logger.info(f"  - Rescued disease-matched doc '{matched_product_name}' from full results (was removed by crop-filter)")
                                break
                if _really_missing:
                    disease_mismatch_note = f"""
[คำเตือนสำคัญ] โรค "{disease_name}" ไม่ปรากฏใน "ใช้กำจัด" ของสินค้าใดเลย
→ ห้ามแนะนำสินค้าใดๆ สำหรับโรคนี้ เพราะไม่มีข้อมูลว่าสินค้าเหล่านี้รักษาโรคนี้ได้
→ ให้ตอบว่า: "ขออภัยค่ะ ตอนนี้ยังไม่มีสินค้าในระบบที่ระบุว่ารักษาโรค{disease_name}ได้โดยตรง แนะนำปรึกษาเจ้าหน้าที่ ICP Ladda เพิ่มเติมค่ะ"
"""
                    logger.warning(f"Disease '{disease_name}' NOT found in any product's pest columns — will block recommendation")
                else:
                    logger.info(f"  - Disease '{disease_name}' found in docs_to_use after rescue — skipping mismatch block")

            # When disease was matched via variant (e.g. ราชมพู→ราสีชมพู), tell LLM
            if disease_found_in_products and original_disease_gen and original_disease_gen != disease_name:
                # Generate the canonical form for LLM context
                canonical_variants = generate_thai_disease_variants(original_disease_gen)
                canonical_form = original_disease_gen
                for v in canonical_variants:
                    if 'สี' in v and v != original_disease_gen:
                        canonical_form = v
                        break
                disease_match_note = f"""
[หมายเหตุโรค] "{original_disease_gen}" ในคำถาม ตรงกับ "{canonical_form}" ในข้อมูลสินค้า "{matched_product_name}"
→ ให้แนะนำสินค้า "{matched_product_name}" สำหรับโรคนี้
"""
                logger.info(f"  - Disease match note: '{original_disease_gen}' → '{canonical_form}' in {matched_product_name}")

        # Build crop-specific note if applicable
        crop_note = ""
        if plant_type and docs_to_use:
            for doc in docs_to_use[:3]:
                crops = str(doc.metadata.get('applicable_crops') or '')
                selling = str(doc.metadata.get('selling_point') or '')
                pname = doc.metadata.get('product_name', doc.title)
                if plant_type in crops and ('เน้นสำหรับ' in crops or f'{plant_type}อันดับ' in selling):
                    crop_note = f"\nหมายเหตุ: {pname} เป็นสินค้าที่เน้นสำหรับ{plant_type}โดยเฉพาะ ให้แนะนำเป็นตัวแรก\n"
                    break

        # Detect multi-variant: hint LLM to use Mode ก when user asks a product family name
        # that matches multiple variants (e.g. "นาแดน" → นาแดน-จี + นาแดน 6 จี)
        multi_variant_note = ""
        product_name_query = query_analysis.entities.get('product_name', '')
        if product_name_query and len(docs_to_use) >= 2:
            original_q = query_analysis.original_query
            # Check if user typed a SPECIFIC variant name that matches exactly one product
            exact_variant_in_query = None
            for doc in docs_to_use:
                pname = doc.metadata.get('product_name', '')
                # Check product_name in query
                if pname and len(pname) > len(product_name_query) and pname in original_q:
                    exact_variant_in_query = pname
                    break
                # Also check aliases (e.g. user types "นาแดน-จี" → alias of "นาแดน 4 จี")
                aliases_str = doc.metadata.get('aliases', '') or ''
                if aliases_str:
                    for alias in [a.strip() for a in aliases_str.split(',') if a.strip()]:
                        if len(alias) > len(product_name_query) and alias in original_q:
                            exact_variant_in_query = pname
                            break
                if exact_variant_in_query:
                    break
            if not exact_variant_in_query:
                # User asked family name only → filter to matching products and hint Mode ก
                matching = [d for d in docs_to_use
                            if product_name_query in d.metadata.get('product_name', '')]
                if len(matching) >= 2:
                    names = [d.metadata.get('product_name', d.title) for d in matching]
                    multi_variant_note = f"\n[หมายเหตุ: มีสินค้าหลายตัว] ผู้ใช้ถาม \"{product_name_query}\" ซึ่งมี {len(names)} รุ่น: {', '.join(names)} — ให้แสดงรายการสั้นๆ เฉพาะสินค้าตระกูล \"{product_name_query}\" ให้เกษตรกรเลือก (ใช้ Mode ก) ห้ามแสดงสินค้าอื่นที่ไม่ใช่ตระกูลนี้\n"
                    logger.info(f"  - Multi-variant hint: {names} → Mode ก")
            else:
                multi_variant_note = f"\n[หมายเหตุ] ผู้ใช้ถามเฉพาะ \"{exact_variant_in_query}\" → ตอบรายละเอียดเต็มของสินค้านี้ตัวเดียว (ใช้ Mode ข) ห้ามแสดงเป็น list ให้เลือก\n"
                logger.info(f"  - Specific variant in query: '{exact_variant_in_query}' → Mode ข")

        # Broad query with multiple products → hint LLM to show all (Mode ก)
        # Exception: if user asks for comparison → use Mode ข (detailed) instead
        _COMPARISON_KEYWORDS = ['ต่างกันยังไง', 'ต่างกันอย่างไร', 'เปรียบเทียบ', 'ใช้ต่างกัน', 'แตกต่าง', 'เทียบกัน']
        _is_comparison = any(kw in query_analysis.original_query for kw in _COMPARISON_KEYWORDS)
        if not multi_variant_note and not product_name_query and len(docs_to_use) >= 3:
            unique_names = list(dict.fromkeys(
                d.metadata.get('product_name', '') for d in docs_to_use if d.metadata.get('product_name')
            ))
            if len(unique_names) >= 3:
                if _is_comparison:
                    multi_variant_note = (
                        f"\n[หมายเหตุ: ผู้ใช้ขอเปรียบเทียบ] สินค้า {len(unique_names)} ตัว: "
                        f"{', '.join(unique_names)} — ตอบรายละเอียดทุกตัวเปรียบเทียบกัน (ใช้ Mode ข) ห้ามบอกให้ถามแยก\n"
                    )
                    logger.info(f"  - Comparison query: {len(unique_names)} products → Mode ข")
                else:
                    multi_variant_note = (
                        f"\n[หมายเหตุ: มีสินค้าหลายตัว] มีสินค้าที่ตรงกับคำถาม {len(unique_names)} ตัว: "
                        f"{', '.join(unique_names)} — แสดงรายการสั้นๆ ทุกตัวให้เกษตรกรเลือก (ใช้ Mode ก)\n"
                    )
                    logger.info(f"  - Broad query multi-product hint: {len(unique_names)} products → Mode ก")

        # Build category match note for alternatives
        category_match_note = ""
        product_name_entity = query_analysis.entities.get('product_name', '')
        if product_name_entity and docs_to_use:
            for doc in docs_to_use:
                if product_name_entity.lower() in doc.metadata.get('product_name', '').lower():
                    queried_cat = doc.metadata.get('category', '')
                    if queried_cat:
                        category_match_note = (
                            f"\n[สำคัญ: ประเภทสินค้าที่ผู้ใช้ถาม] สินค้า \"{product_name_entity}\" "
                            f"เป็นประเภท \"{queried_cat}\" — ถ้าสินค้านี้ไม่เหมาะกับพืชที่ถาม "
                            f"ให้แนะนำเฉพาะสินค้าประเภทเดียวกัน (\"{queried_cat}\") เท่านั้น "
                            f"ห้ามแนะนำสินค้าต่างประเภท\n"
                        )
                    break

        prompt = f"""{context_section}คำถาม: "{query_analysis.original_query}"
Intent: {query_analysis.intent.value}
Entities: {json.dumps(query_analysis.entities, ensure_ascii=False)}

ข้อมูลสินค้าที่ผ่านการตรวจสอบแล้ว:
{product_context}

สินค้าที่เกี่ยวข้องกับคำถาม: [{relevant_str}]
{crop_note}{disease_mismatch_note}{disease_match_note}{multi_variant_note}{category_match_note}{nutrient_constraint_note}
สร้างคำตอบจากข้อมูลด้านบน
- ถ้าเป็นคำถามต่อเนื่องเกี่ยวกับสินค้าตัวเดิม (เช่น "วิธีใช้" "อัตราผสม") → ตอบเกี่ยวกับสินค้าตัวเดิม
- ถ้าผู้ใช้เปลี่ยนหัวข้อ (ถามโรค/แมลง/สินค้าใหม่) → ยึดคำถามปัจจุบันเป็นหลัก ไม่ต้องอ้างอิงสินค้าเก่าจากบริบท
- ห้ามแนะนำสินค้าที่ไม่มีชื่อโรค/แมลง/วัชพืชนั้นใน "ใช้กำจัด" ของสินค้า ถึงแม้จะเป็นสินค้าประเภทเดียวกัน (เช่น fungicide ด้วยกัน) ก็ห้ามแนะนำถ้าข้อมูลกลุ่มสารไม่ match
เมื่อแนะนำสินค้า:
- แสดงอัตราตามที่ระบุในข้อมูลสินค้าเท่านั้น ห้ามคำนวณ คูณ หาร หรือแปลงหน่วยเอง
- ถ้าผู้ใช้ถามให้คำนวณ (เช่น "10 ไร่ใช้เท่าไหร่" / "1 ขวดใช้ได้กี่ไร่") → ตอบว่า "ขณะนี้ ไอ ซี พี ลัดดา กำลังตรวจสอบข้อมูลให้คุณลูกค้าค่ะ แอดมินจะแจ้งให้ทราบอีกครั้งนะคะ ต้องขออภัยในความล่าช้าด้วยค่ะ 🙏🙏"
- ถ้าผู้ใช้ถามให้สลับสาร/กลุ่มสาร และข้อมูลสินค้าไม่ได้ระบุไว้ → ตอบว่า "ขณะนี้ ไอ ซี พี ลัดดา กำลังตรวจสอบข้อมูลให้คุณลูกค้าค่ะ แอดมินจะแจ้งให้ทราบอีกครั้งนะคะ ต้องขออภัยในความล่าช้าด้วยค่ะ 🙏🙏"

[ห้ามมั่วข้อมูลเด็ดขาด]
- ตอบเฉพาะข้อมูลที่ปรากฏในข้อมูลสินค้าด้านบน ห้ามแต่งเอง
- ห้ามเดาตัวเลขขนาดบรรจุ น้ำหนัก ราคา กลไกการออกฤทธิ์ การดูดซึม
- ห้ามแต่งตัวเลขที่ไม่มีในข้อมูล (ห้ามเดาขนาดบรรจุ ราคา สารสำคัญ) ห้ามคำนวณ คูณ หาร แปลงหน่วยเอง
- ห้ามเดาสี ลักษณะ หรือรูปลักษณ์ของสินค้า (เช่น "น้ำสีใส" "เม็ดสีขาว" "ผงสีเหลือง") ถ้าข้อมูลไม่ได้ระบุสีหรือลักษณะไว้ → ตอบว่า "ไม่มีข้อมูลเรื่องสีหรือลักษณะของสินค้าในระบบค่ะ"
- ถ้าข้อมูลที่ถามไม่มีในข้อมูลด้านบน ให้ตอบว่า "ขออภัยค่ะ ไม่มีข้อมูลส่วนนี้ในระบบ"
- ห้ามใช้ความรู้ทั่วไปมาตอบแทนข้อมูลจริง
- ห้ามตอบว่าผสมร่วมได้/ใช้ร่วมกับปุ๋ยหรือสารอื่นได้ ถ้าข้อมูลวิธีใช้ไม่ได้ระบุเรื่องนี้ไว้ → ตอบว่าข้อมูลในระบบไม่ได้ระบุเรื่องการผสมร่วม แนะนำสอบถามเจ้าหน้าที่ ICP Ladda โดยตรงค่ะ"""

        system_prompt = PRODUCT_QA_PROMPT

        try:
            _messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
            _llm_params = dict(
                messages=_messages,
                temperature=LLM_TEMP_RESPONSE_GEN,
                max_completion_tokens=LLM_TOKENS_RESPONSE_GEN
            )

            response = await self.openai_client.chat.completions.create(
                model=LLM_MODEL_RESPONSE_GEN, **_llm_params
            )

            if not response or not response.choices:
                logger.error("LLM returned empty response")
                return self._build_fallback_answer(retrieval_result, grounding_result)
            answer = response.choices[0].message.content.strip()

            # Post-processing: validate product names in response
            answer = self._validate_product_names(answer, docs_to_use, query_analysis)

            return answer
        except Exception as e:
            logger.error(f"LLM response generation failed: {e}")
            return self._build_fallback_answer(retrieval_result, grounding_result)

    # Non-product terms that may appear in quotes (weed species, disease, pest, crop names)
    _NON_PRODUCT_KEYWORDS = {
        # Weed/crop species
        'หญ้า', 'วัชพืช', 'ข้าวนก', 'ผักปอด', 'เซ่ง', 'โสน', 'กก',
        # Disease/pathogen
        'โรค', 'เชื้อรา', 'รา', 'แอนแทรคโนส', 'ฟิวซาเรียม', 'ไฟท็อป', 'ไฟทิป', 'ไฟทอป',
        'เน่า', 'ไหม้', 'จุด', 'แห้ง', 'ด่าง', 'สนิม',
        # Insect/pest
        'เพลี้ย', 'หนอน', 'แมลง', 'ด้วง', 'ไร', 'บั่ว', 'จักจั่น', 'ทริปส์',
        # Crop names
        'ข้าว', 'ทุเรียน', 'มะม่วง', 'ลำไย', 'มังคุด', 'อ้อย', 'ข้าวโพด',
        # Generic terms
        'ดื้อยา', 'ดื้อสาร', 'ใบ', 'ดอก', 'ผล', 'ราก', 'กิ่ง', 'ลำต้น',
        # Category/group terms (not product names)
        'Insecticide', 'Fungicide', 'Herbicide', 'Biostimulants', 'Fertilizer', 'PGR',
        'insecticide', 'fungicide', 'herbicide', 'biostimulants', 'fertilizer', 'pgr',
        'IRAC', 'FRAC', 'HRAC', 'irac', 'frac', 'hrac',
        'กลุ่มสาร', 'กลุ่มเคมี', 'สารกำจัดแมลง', 'สารกำจัดเชื้อรา', 'สารกำจัดวัชพืช',
    }

    def _validate_product_names(self, answer: str, docs: list, query_analysis: QueryAnalysis = None) -> str:
        """
        Post-processing: ตรวจสอบว่าสินค้าที่แนะนำอยู่ใน retrieved documents จริง
        ถ้าเจอสินค้าที่ไม่มีใน database → ลบออกจากคำตอบ
        """
        try:
            from app.services.chat.handler import ICP_PRODUCT_NAMES
            import re

            # Build set of allowed product names from retrieved docs + ICP list
            allowed_names = set()
            for doc in docs:
                pname = doc.metadata.get('product_name', '')
                if pname:
                    allowed_names.add(pname)

            # Exempt: product that user asked about directly (+ its aliases)
            _queried_product = ''
            _queried_aliases = set()
            if query_analysis:
                _queried_product = query_analysis.entities.get('product_name', '')
                if _queried_product:
                    # Add the product name itself + all aliases
                    _queried_aliases.add(_queried_product)
                    aliases_list = ICP_PRODUCT_NAMES.get(_queried_product, [])
                    for a in aliases_list:
                        _queried_aliases.add(a)

            # Match text between straight quotes " or curly quotes ""
            for match in re.finditer(r'["\u201c\u201d]([^"\u201c\u201d]+?)["\u201c\u201d]', answer):
                full_match = match.group(0)
                inner_text = match.group(1).strip()

                # Extract product name (strip trailing parenthetical like "(สารสำคัญ)")
                product_mention = re.sub(r'\s*\([^)]+\)\s*$', '', inner_text).strip()

                if not product_mention or len(product_mention) > 30:
                    continue

                # Skip non-product quoted text (weed species, disease, pest, crop names)
                if any(kw in product_mention for kw in self._NON_PRODUCT_KEYWORDS):
                    continue

                is_known = any(
                    product_mention in name or name in product_mention
                    for name in allowed_names
                ) or any(
                    product_mention in name or name in product_mention
                    for name in ICP_PRODUCT_NAMES.keys()
                )

                if not is_known:
                    logger.warning(f"HALLUCINATED product detected: '{product_mention}' - not in database!")
                    answer = answer.replace(full_match, '')

            # Pass 2: Scan for unquoted product names from ICP_PRODUCT_NAMES
            for icp_name in ICP_PRODUCT_NAMES.keys():
                if len(icp_name) < 3:  # Skip very short names to avoid false matches
                    continue
                if icp_name in answer:
                    # Skip if this is the product the user asked about
                    if any(icp_name in qa or qa in icp_name for qa in _queried_aliases):
                        continue
                    # Check if this product is in allowed docs
                    is_allowed = any(
                        icp_name in name or name in icp_name
                        for name in allowed_names
                    )
                    if not is_allowed:
                        # Product exists in ICP DB but not in retrieved docs → remove from answer
                        logger.warning(f"CROSS-PRODUCT hallucination removed: '{icp_name}' not in retrieved docs")
                        # Remove the entire line containing the hallucinated product
                        import re as _re
                        answer = _re.sub(r'[^\n]*' + _re.escape(icp_name) + r'[^\n]*\n?', '', answer)

        except Exception as e:
            logger.error(f"Product name validation error: {e}")

        return answer

    def _build_fallback_answer(
        self,
        retrieval_result: RetrievalResult,
        grounding_result: GroundingResult
    ) -> str:
        """Build answer without LLM from raw product data"""
        if not retrieval_result.documents:
            return ERROR_NO_DATA

        parts = ["จากข้อมูลในฐานข้อมูล:\n"]
        for i, doc in enumerate(retrieval_result.documents[:3], 1):
            meta = doc.metadata
            name = meta.get('product_name') or doc.title
            ingredient = meta.get('active_ingredient')
            if ingredient:
                name = f"{name} ({ingredient})"
            parts.append(f"{i}. {name}")
            _pest_disp = _get_pest_text_from_meta(meta)
            if _pest_disp:
                parts.append(f"   - ใช้กำจัด: {_pest_disp[:100]}")
            if meta.get('usage_rate'):
                parts.append(f"   - อัตราใช้: {meta['usage_rate']}")
            if meta.get('package_size'):
                parts.append(f"   - ขนาดบรรจุ: {meta['package_size']}")
            if meta.get('phytotoxicity'):
                parts.append(f"   - ความเป็นพิษต่อพืช: {meta['phytotoxicity']}")
            if meta.get('caution_notes'):
                parts.append(f"   - ข้อควรระวังเพิ่มเติม: {meta['caution_notes']}")
            parts.append("")

        return "\n".join(parts)

    def _generate_greeting_response(self, query_analysis: QueryAnalysis) -> AgenticRAGResponse:
        """Generate response for greeting intent"""
        import random
        answer = random.choice(GREETINGS)

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
        answer = get_no_data_response(
            query_analysis.intent.value,
            query_analysis.entities
        )

        return AgenticRAGResponse(
            answer=answer,
            confidence=0.0,
            citations=[],
            intent=query_analysis.intent,
            is_grounded=False,
            sources_used=[]
        )


