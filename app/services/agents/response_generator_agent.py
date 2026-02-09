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

from app.services.agents import (
    QueryAnalysis,
    RetrievalResult,
    GroundingResult,
    AgenticRAGResponse,
    IntentType
)
from app.utils.text_processing import post_process_answer, generate_thai_disease_variants, validate_numbers_against_source
from app.config import LLM_MODEL_RESPONSE_GEN
from app.prompts import (
    PRODUCT_QA_PROMPT,
    GREETINGS,
    PRODUCT_CTA,
    ERROR_PROCESSING,
    ERROR_NO_DATA,
    LOW_CONFIDENCE_NOTE,
    get_no_data_response,
)

logger = logging.getLogger(__name__)

# Configuration
LOW_CONFIDENCE_THRESHOLD = 0.5


class ResponseGeneratorAgent:
    """
    Agent 4: Response Generation
    Creates the final user-facing response using LLM with verified product data
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
                has_product_in_query = bool(query_analysis.entities.get('product_name'))
                has_documents = bool(retrieval_result.documents)

                # Check if disease query matched via target_pest (fallback products)
                has_disease_match = False
                disease_name = query_analysis.entities.get('disease_name', '')
                if disease_name and has_documents and query_analysis.intent in (IntentType.DISEASE_TREATMENT, IntentType.PRODUCT_RECOMMENDATION):
                    disease_variants = generate_thai_disease_variants(disease_name)
                    for doc in retrieval_result.documents[:10]:
                        target_pest = str(doc.metadata.get('target_pest', '')).lower()
                        if any(v.lower() in target_pest for v in disease_variants):
                            has_disease_match = True
                            logger.info(f"  - Disease override: '{disease_name}' found in {doc.title} target_pest")
                            break

                # Also try extracting disease from original query (LLM may have changed disease name)
                if not has_disease_match and has_documents and query_analysis.intent in (IntentType.DISEASE_TREATMENT, IntentType.PRODUCT_RECOMMENDATION):
                    import re as _re
                    _DISEASE_PATTERNS_RSP = [
                        'แอนแทรคโนส', 'แอนแทคโนส', 'แอคแทคโนส',
                        'ฟิวซาเรียม', 'ฟิวสาเรียม', 'ฟอซาเรียม',
                        'ราน้ำค้าง', 'ราแป้ง', 'ราสนิม', 'ราสีชมพู', 'ราชมพู',
                        'ราดำ', 'ราเขียว', 'ราขาว', 'ราเทา',
                        'ใบไหม้', 'ใบจุด', 'ผลเน่า', 'รากเน่า', 'โคนเน่า',
                        'กาบใบแห้ง', 'ขอบใบแห้ง', 'ใบติด', 'เน่าคอรวง',
                    ]
                    original_disease = ''
                    for pattern in _DISEASE_PATTERNS_RSP:
                        if pattern in query_analysis.original_query:
                            original_disease = pattern
                            break
                    if original_disease and original_disease != disease_name:
                        original_variants = generate_thai_disease_variants(original_disease)
                        for doc in retrieval_result.documents[:5]:
                            target_pest = str(doc.metadata.get('target_pest', '')).lower()
                            if any(v.lower() in target_pest for v in original_variants):
                                has_disease_match = True
                                logger.info(f"  - Disease override (original query): '{original_disease}' found in {doc.title} target_pest")
                                break

                # Also check possible_diseases from symptom→pathogen mapping
                if not has_disease_match and has_documents and query_analysis.intent in (IntentType.DISEASE_TREATMENT, IntentType.PRODUCT_RECOMMENDATION):
                    _possible_diseases = query_analysis.entities.get('possible_diseases', [])
                    for pd in _possible_diseases:
                        pd_variants = generate_thai_disease_variants(pd)
                        for doc in retrieval_result.documents[:10]:
                            target_pest = str(doc.metadata.get('target_pest', '')).lower()
                            if any(v.lower() in target_pest for v in pd_variants):
                                has_disease_match = True
                                logger.info(f"  - Disease override (symptom→pathogen): '{pd}' found in {doc.title} target_pest")
                                break
                        if has_disease_match:
                            break

                if not has_documents or (
                    grounding_result.confidence < 0.2
                    and not has_crop_specific_top
                    and not (has_product_in_query and has_documents)
                    and not has_disease_match
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

            # Validate numbers against source docs (Phase 1: logging only)
            if retrieval_result and retrieval_result.documents:
                num_check = validate_numbers_against_source(answer, retrieval_result.documents[:5])
                if not num_check["valid"]:
                    logger.warning(f"  - Number validation: {len([m for m in num_check['mismatches'] if not m['found_in_source']])} mismatches found")

            # Add low confidence indicator if needed
            if final_confidence < LOW_CONFIDENCE_THRESHOLD:
                answer = self._add_low_confidence_note(answer)

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

        # Keep all products (including Standard) — just sort by strategy_group priority
        docs_to_use = retrieval_result.documents[:5]

        # Sort by strategy_group priority: Skyrocket > Expand > Natural > Standard
        # ensures Skyrocket/Expand appear first in product context sent to LLM
        _STRATEGY_ORDER = {'Skyrocket': 0, 'Expand': 1, 'Natural': 2, 'Standard': 3}
        docs_to_use.sort(key=lambda d: _STRATEGY_ORDER.get(d.metadata.get('strategy_group', ''), 3))

        # Rescue: ensure disease-matching product is in docs_to_use
        # If query is about disease but no doc in docs_to_use has the disease in target_pest,
        # search full retrieval results and add the matching doc
        if query_analysis.intent.value in ('disease_treatment', 'product_recommendation'):
            _rescue_disease = query_analysis.entities.get('disease_name', '')
            if _rescue_disease:
                _rescue_variants = generate_thai_disease_variants(_rescue_disease)
                _has_in_docs_to_use = any(
                    any(v.lower() in str(d.metadata.get('target_pest', '')).lower() for v in _rescue_variants)
                    for d in docs_to_use
                )
                if not _has_in_docs_to_use:
                    for doc in retrieval_result.documents:
                        if doc in docs_to_use:
                            continue
                        target_pest = str(doc.metadata.get('target_pest', '')).lower()
                        if any(v.lower() in target_pest for v in _rescue_variants):
                            docs_to_use.insert(0, doc)
                            logger.info(f"  - Rescued disease-matching product into docs_to_use: {doc.title}")
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

        # Build product data context from retrieval results
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
            if meta.get('target_pest'):
                part += f"  ใช้กำจัด: {str(meta['target_pest'])}\n"
            if meta.get('applicable_crops'):
                part += f"  พืชที่ใช้ได้: {str(meta['applicable_crops'])}\n"
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
            if meta.get('strategy_group'):
                part += f"  Strategy Group: {meta['strategy_group']}\n"
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
                if plant_type in crops and ('เน้นสำหรับ' in crops or f'{plant_type}อันดับ' in selling):
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

        # Validate disease-product match: check if queried disease is in any product's target_pest
        disease_mismatch_note = ""
        disease_match_note = ""
        disease_name = query_analysis.entities.get('disease_name', '')

        # Also extract disease from original query (LLM may misidentify)
        _DISEASE_PATTERNS_GEN = [
            'แอนแทรคโนส', 'แอนแทคโนส', 'แอคแทคโนส',
            'ฟิวซาเรียม', 'ฟิวสาเรียม', 'ฟอซาเรียม',
            'ราน้ำค้าง', 'ราแป้ง', 'ราสนิม', 'ราสีชมพู', 'ราชมพู',
            'ราดำ', 'ราเขียว', 'ราขาว', 'ราเทา',
            'ใบไหม้', 'ใบจุด', 'ผลเน่า', 'รากเน่า', 'โคนเน่า',
            'กาบใบแห้ง', 'ขอบใบแห้ง', 'ใบติด', 'เน่าคอรวง',
        ]
        original_disease_gen = ''
        for _pat in _DISEASE_PATTERNS_GEN:
            if _pat in query_analysis.original_query:
                original_disease_gen = _pat
                break

        if query_analysis.intent.value in ('disease_treatment', 'product_recommendation'):
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
                    target_pest = str(doc.metadata.get('target_pest', '')).lower()
                    if any(v.lower() in target_pest for v in check_variants):
                        disease_found_in_products = True
                        matched_disease_label = check_disease
                        matched_product_name = doc.metadata.get('product_name', doc.title)
                        break
                if disease_found_in_products:
                    break

            if not disease_found_in_products and disease_name:
                disease_mismatch_note = f"""
[คำเตือนสำคัญ] โรค "{disease_name}" ไม่ปรากฏใน "ใช้กำจัด" (target_pest) ของสินค้าใดเลย
→ ห้ามแนะนำสินค้าใดๆ สำหรับโรคนี้ เพราะไม่มีข้อมูลว่าสินค้าเหล่านี้รักษาโรคนี้ได้
→ ให้ตอบว่า: "ขออภัยค่ะ ตอนนี้ยังไม่มีสินค้าในระบบที่ระบุว่ารักษาโรค{disease_name}ได้โดยตรง แนะนำปรึกษาเจ้าหน้าที่ ICP Ladda เพิ่มเติมค่ะ"
"""
                logger.warning(f"Disease '{disease_name}' NOT found in any product's target_pest — will block recommendation")

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
[หมายเหตุโรค] "{original_disease_gen}" ในคำถาม ตรงกับ "{canonical_form}" ใน target_pest ของ "{matched_product_name}"
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

        prompt = f"""{context_section}คำถาม: "{query_analysis.original_query}"
Intent: {query_analysis.intent.value}
Entities: {json.dumps(query_analysis.entities, ensure_ascii=False)}

ข้อมูลสินค้าที่ผ่านการตรวจสอบแล้ว:
{product_context}

สินค้าที่เกี่ยวข้องกับคำถาม: [{relevant_str}]
{crop_note}{disease_mismatch_note}{disease_match_note}
สร้างคำตอบจากข้อมูลด้านบน (ถ้าเป็นคำถามต่อเนื่อง ให้ใช้ข้อมูลของสินค้าตัวเดิมจากบริบทเท่านั้น ห้ามเปลี่ยนเป็นสินค้าอื่น)
ถ้าผู้ใช้ถามปริมาณการใช้สำหรับพื้นที่ (เช่น 10 ไร่, 20 ไร่) ให้คำนวณจากอัตราใช้ต่อไร่ และถ้ามีข้อมูล "ขนาดบรรจุ" ให้คำนวณจำนวนขวด/ถุง/กระสอบที่ต้องซื้อด้วย"""

        system_prompt = PRODUCT_QA_PROMPT

        try:
            response = await self.openai_client.chat.completions.create(
                model=LLM_MODEL_RESPONSE_GEN,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=700
            )
            answer = response.choices[0].message.content.strip()

            # Post-processing: validate product names in response
            answer = self._validate_product_names(answer, docs_to_use)

            return answer
        except Exception as e:
            logger.error(f"LLM response generation failed: {e}")
            return self._build_fallback_answer(retrieval_result, grounding_result)

    def _validate_product_names(self, answer: str, docs: list) -> str:
        """
        Post-processing: ตรวจสอบว่าสินค้าที่แนะนำอยู่ใน retrieved documents จริง
        ถ้าเจอสินค้าที่ไม่มีใน database → ลบออกจากคำตอบ
        """
        try:
            from app.services.chat import ICP_PRODUCT_NAMES
            import re

            # Build set of allowed product names from retrieved docs + ICP list
            allowed_names = set()
            for doc in docs:
                pname = doc.metadata.get('product_name', '')
                if pname:
                    allowed_names.add(pname)

            # Match text between straight quotes " or curly quotes ""
            for match in re.finditer(r'["\u201c\u201d]([^"\u201c\u201d]+?)["\u201c\u201d]', answer):
                full_match = match.group(0)
                inner_text = match.group(1).strip()

                # Extract product name (strip trailing parenthetical like "(สารสำคัญ)")
                product_mention = re.sub(r'\s*\([^)]+\)\s*$', '', inner_text).strip()

                if not product_mention or len(product_mention) > 30:
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
                    answer = answer.replace(full_match, '"(สินค้านี้ไม่อยู่ในฐานข้อมูล)"')

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
            if meta.get('target_pest'):
                parts.append(f"   - ใช้กำจัด: {str(meta['target_pest'])[:100]}")
            if meta.get('usage_rate'):
                parts.append(f"   - อัตราใช้: {meta['usage_rate']}")
            if meta.get('package_size'):
                parts.append(f"   - ขนาดบรรจุ: {meta['package_size']}")
            parts.append("")

        parts.append(f"\n{PRODUCT_CTA}")
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

    def _add_low_confidence_note(self, answer: str) -> str:
        """Add note when confidence is low"""
        note = f"\n\n{LOW_CONFIDENCE_NOTE}"
        if note not in answer:
            answer += note
        return answer

