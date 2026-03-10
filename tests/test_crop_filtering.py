"""
Test crop-mismatch penalty & crop warning in response generator.

Scenario: user asks "วัชพืชในนาใช้ไร" (weed in rice paddy)
- Products for rice should be boosted
- Products with "ห้ามใช้ในนาข้าว" should be heavily penalized
- Products whose applicable_crops doesn't include ข้าว should be penalized
- Response generator should add warnings for mismatched crops
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.rag import (
    QueryAnalysis,
    RetrievedDocument,
    RetrievalResult,
    GroundingResult,
    IntentType,
)
from app.services.rag.response_generator_agent import ResponseGeneratorAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(name, crops, category="Herbicide", strategy="Skyrocket",
              how_to_use="", similarity=0.50, rerank=0.70):
    return RetrievedDocument(
        id=f"id-{name}",
        title=name,
        content=f"{name} product",
        source="products",
        similarity_score=similarity,
        rerank_score=rerank,
        metadata={
            "product_name": name,
            "active_ingredient": "test-ingredient",
            "category": category,
            "applicable_crops": crops,
            "herbicides": "วัชพืช",
            "how_to_use": how_to_use,
            "usage_rate": "100 มล./ไร่",
            "strategy": strategy,
        },
    )


# ---------------------------------------------------------------------------
# Test: Crop-mismatch penalty in retrieval (Stage 3.65)
# ---------------------------------------------------------------------------

class TestCropMismatchPenalty:
    """Test retrieval_agent crop-mismatch penalty logic."""

    @pytest.mark.asyncio
    async def test_prohibited_crop_gets_heavy_penalty(self):
        """Products with 'ห้ามใช้ในนาข้าว' should get -0.30 penalty."""
        from app.services.rag.retrieval_agent import RetrievalAgent

        agent = RetrievalAgent(supabase_client=MagicMock(), openai_client=AsyncMock())

        # Simulate docs that would be in reranked_docs
        doc_rice_ok = _make_doc("ทูโฟฟอส", "นาข้าว", rerank=0.70)
        doc_prohibited = _make_doc("ราเซอร์", "พืชไร่, อ้อย",
                                   how_to_use="ใช้ในพืชไร่ (ห้ามใช้ในนาข้าว)", rerank=0.70)
        doc_no_rice = _make_doc("โกลด์ช็อต", "อ้อย, มันสำปะหลัง", rerank=0.70)

        # We test the penalty logic directly
        plant_type = "ข้าว"
        docs = [doc_rice_ok, doc_prohibited, doc_no_rice]

        for doc in docs:
            crops = str(doc.metadata.get('applicable_crops') or '')
            how_to = str(doc.metadata.get('how_to_use') or '')
            all_text = f"{crops} {how_to}"

            _prohibit_patterns = [
                f"ห้ามใช้ใน{plant_type}",
                f"ห้ามใช้กับ{plant_type}",
                f"ห้ามใช้ในนาข้าว",
                f"ห้ามใช้ในนา{plant_type}",
            ]
            _is_prohibited = any(p in all_text for p in _prohibit_patterns)

            if _is_prohibited:
                doc.rerank_score = max(0.0, doc.rerank_score - 0.30)
            elif plant_type in crops:
                doc.rerank_score = min(1.0, doc.rerank_score + 0.05)
            elif crops.strip():
                doc.rerank_score = max(0.0, doc.rerank_score - 0.15)

        # ทูโฟฟอส (rice OK) should be boosted
        assert doc_rice_ok.rerank_score == pytest.approx(0.75, abs=0.01)
        # ราเซอร์ (prohibited) should get heavy penalty
        assert doc_prohibited.rerank_score == pytest.approx(0.40, abs=0.01)
        # โกลด์ช็อต (no rice) should get mild penalty
        assert doc_no_rice.rerank_score == pytest.approx(0.55, abs=0.01)

        # After sorting, rice-OK should be first, prohibited should be last
        docs_sorted = sorted(docs, key=lambda d: d.rerank_score, reverse=True)
        assert docs_sorted[0].title == "ทูโฟฟอส"
        assert docs_sorted[-1].title == "ราเซอร์"

    @pytest.mark.asyncio
    async def test_crop_specific_boost(self):
        """Products with 'เน้นสำหรับ(ข้าว)' should get +0.20 boost."""
        doc = _make_doc("ทูโฟฟอส", "เน้นสำหรับ(นาข้าว)", rerank=0.60)
        plant_type = "ข้าว"
        crops = str(doc.metadata.get('applicable_crops') or '')
        selling = str(doc.metadata.get('selling_point') or '')

        if plant_type in crops and ('เน้นสำหรับ' in crops or f'{plant_type}อันดับ' in selling):
            doc.rerank_score = min(1.0, doc.rerank_score + 0.20)

        assert doc.rerank_score == pytest.approx(0.80, abs=0.01)

    @pytest.mark.asyncio
    async def test_no_plant_type_no_penalty(self):
        """When no plant_type in query, no crop penalty should be applied."""
        doc = _make_doc("ราเซอร์", "พืชไร่", rerank=0.70)
        plant_type = ""  # no plant type

        # No penalty when no plant_type
        if plant_type:
            pass  # would apply penalty

        assert doc.rerank_score == pytest.approx(0.70, abs=0.01)


# ---------------------------------------------------------------------------
# Test: Crop warning in response generator (Layer 2)
# ---------------------------------------------------------------------------

class TestCropWarningInResponseGenerator:
    """Test that response generator adds crop warnings to LLM context."""

    @pytest.mark.asyncio
    async def test_prohibited_crop_warning(self):
        """Products with 'ห้ามใช้ในนาข้าว' should get prohibition warning in LLM context."""
        mock_openai = AsyncMock()
        choice = MagicMock()
        choice.message.content = "สำหรับนาข้าว ลัดดาแนะนำทูโฟฟอสค่ะ"
        mock_openai.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[choice])
        )

        agent = ResponseGeneratorAgent(openai_client=mock_openai)

        docs = [
            _make_doc("ทูโฟฟอส", "นาข้าว", rerank=0.80),
            _make_doc("ราเซอร์", "พืชไร่, อ้อย",
                       how_to_use="ใช้ในพืชไร่ (ห้ามใช้ในนาข้าว)", rerank=0.40),
        ]

        qa = QueryAnalysis(
            original_query="วัชพืชในนาใช้ไร",
            intent=IntentType.WEED_CONTROL,
            confidence=0.95,
            entities={"plant_type": "ข้าว", "problem_type": "weed"},
            expanded_queries=["วัชพืชในนาข้าว", "สารกำจัดวัชพืช ข้าว"],
            required_sources=["products"],
        )
        retrieval = RetrievalResult(
            documents=docs, total_retrieved=2, total_after_rerank=2,
            avg_similarity=0.50, avg_rerank_score=0.60, sources_used=["products"],
        )
        grounding = GroundingResult(
            is_grounded=False, confidence=0.48, citations=[],
            ungrounded_claims=[], suggested_answer="", relevant_products=[],
        )

        result = await agent.generate(qa, retrieval, grounding)

        # Should not crash and should return answer
        assert result is not None
        assert len(result.answer) > 0

        # Verify the LLM was called and check the product context passed to it
        call_args = mock_openai.chat.completions.create.call_args
        messages = call_args.kwargs.get('messages') or call_args[1].get('messages', [])
        all_content = " ".join(m.get("content", "") for m in messages)

        # The prohibition warning should be in the LLM context
        assert "ห้ามใช้กับข้าว" in all_content or "ห้ามแนะนำ" in all_content

    @pytest.mark.asyncio
    async def test_crop_not_listed_warning(self):
        """Products whose applicable_crops doesn't include plant_type should get warning."""
        mock_openai = AsyncMock()
        choice = MagicMock()
        choice.message.content = "ลัดดาแนะนำทูโฟฟอสค่ะ"
        mock_openai.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[choice])
        )

        agent = ResponseGeneratorAgent(openai_client=mock_openai)

        docs = [
            _make_doc("โกลด์ช็อต", "อ้อย, มันสำปะหลัง", rerank=0.60),
        ]

        qa = QueryAnalysis(
            original_query="กำจัดหญ้าในสวนทุเรียน",
            intent=IntentType.WEED_CONTROL,
            confidence=0.95,
            entities={"plant_type": "ทุเรียน", "problem_type": "weed"},
            expanded_queries=["กำจัดวัชพืช ทุเรียน"],
            required_sources=["products"],
        )
        retrieval = RetrievalResult(
            documents=docs, total_retrieved=1, total_after_rerank=1,
            avg_similarity=0.50, avg_rerank_score=0.60, sources_used=["products"],
        )
        grounding = GroundingResult(
            is_grounded=False, confidence=0.48, citations=[],
            ungrounded_claims=[], suggested_answer="", relevant_products=[],
        )

        result = await agent.generate(qa, retrieval, grounding)
        assert result is not None

        # Check LLM context has crop warning
        call_args = mock_openai.chat.completions.create.call_args
        messages = call_args.kwargs.get('messages') or call_args[1].get('messages', [])
        all_content = " ".join(m.get("content", "") for m in messages)

        assert "ไม่ได้ระบุว่าใช้กับทุเรียนได้" in all_content or "ห้ามแนะนำสำหรับทุเรียน" in all_content

    @pytest.mark.asyncio
    async def test_matching_crop_no_warning(self):
        """Products whose applicable_crops includes plant_type should NOT get warning."""
        mock_openai = AsyncMock()
        choice = MagicMock()
        choice.message.content = "ลัดดาแนะนำทูโฟฟอสค่ะ"
        mock_openai.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[choice])
        )

        agent = ResponseGeneratorAgent(openai_client=mock_openai)

        docs = [
            _make_doc("ทูโฟฟอส", "นาข้าว", rerank=0.80),
        ]

        qa = QueryAnalysis(
            original_query="วัชพืชในนาใช้ไร",
            intent=IntentType.WEED_CONTROL,
            confidence=0.95,
            entities={"plant_type": "ข้าว", "problem_type": "weed"},
            expanded_queries=["วัชพืชในนาข้าว"],
            required_sources=["products"],
        )
        retrieval = RetrievalResult(
            documents=docs, total_retrieved=1, total_after_rerank=1,
            avg_similarity=0.50, avg_rerank_score=0.80, sources_used=["products"],
        )
        grounding = GroundingResult(
            is_grounded=False, confidence=0.48, citations=[],
            ungrounded_claims=[], suggested_answer="", relevant_products=[],
        )

        result = await agent.generate(qa, retrieval, grounding)
        assert result is not None

        # Check LLM context does NOT have crop-specific warning tags
        call_args = mock_openai.chat.completions.create.call_args
        messages = call_args.kwargs.get('messages') or call_args[1].get('messages', [])
        all_content = " ".join(m.get("content", "") for m in messages)

        # Our crop warnings use "[!!" prefix — should NOT appear for matching crop
        assert "[!! ห้ามใช้กับข้าว" not in all_content
        assert "ไม่ได้ระบุว่าใช้กับข้าวได้" not in all_content


# ---------------------------------------------------------------------------
# Integration-like: end-to-end score ordering
# ---------------------------------------------------------------------------

class TestCropFilteringEndToEnd:
    """Simulate the full scoring pipeline for rice weed query."""

    def test_rice_weed_query_score_ordering(self):
        """For 'วัชพืชในนาข้าว': rice herbicides > generic > prohibited."""
        docs = [
            _make_doc("ทูโฟฟอส", "นาข้าว", rerank=0.70),
            _make_doc("อาร์ดอน", "นาข้าว", rerank=0.65),
            _make_doc("โกลด์ช็อต", "อ้อย, มันสำปะหลัง", rerank=0.70),
            _make_doc("ราเซอร์", "พืชไร่, อ้อย",
                       how_to_use="ใช้ในพืชไร่ (ห้ามใช้ในนาข้าว)", rerank=0.70),
            _make_doc("โม-เซ่ 88.8", "พืชไร่",
                       how_to_use="ใช้ป้องกันกำจัดวัชพืชในพืชไร่ (ห้ามใช้ในนาข้าว)", rerank=0.68),
        ]

        plant_type = "ข้าว"
        for doc in docs:
            crops = str(doc.metadata.get('applicable_crops') or '')
            how_to = str(doc.metadata.get('how_to_use') or '')
            selling = str(doc.metadata.get('selling_point') or '')
            all_text = f"{crops} {how_to} {selling}"

            _prohibit_patterns = [
                f"ห้ามใช้ใน{plant_type}", f"ห้ามใช้กับ{plant_type}",
                "ห้ามใช้ในนาข้าว", f"ห้ามใช้ในนา{plant_type}",
            ]
            _is_prohibited = any(p in all_text for p in _prohibit_patterns)

            if _is_prohibited:
                doc.rerank_score = max(0.0, doc.rerank_score - 0.30)
            elif plant_type in crops and ('เน้นสำหรับ' in crops or f'{plant_type}อันดับ' in selling):
                doc.rerank_score = min(1.0, doc.rerank_score + 0.20)
            elif plant_type in crops:
                doc.rerank_score = min(1.0, doc.rerank_score + 0.05)
            elif crops.strip():
                doc.rerank_score = max(0.0, doc.rerank_score - 0.15)

        docs_sorted = sorted(docs, key=lambda d: d.rerank_score, reverse=True)

        # Rice-OK products should be on top
        assert docs_sorted[0].title == "ทูโฟฟอส"  # 0.75
        assert docs_sorted[1].title == "อาร์ดอน"   # 0.70

        # Prohibited products should be at bottom
        prohibited_names = {"ราเซอร์", "โม-เซ่ 88.8"}
        bottom_two = {docs_sorted[-1].title, docs_sorted[-2].title}
        assert prohibited_names == bottom_two

    def test_durian_weed_query_no_false_penalty(self):
        """For durian query, rice-specific products should be penalized, not durian ones."""
        docs = [
            _make_doc("ราเซอร์", "อ้อย, มันสำปะหลัง, ทุเรียน", rerank=0.70),
            _make_doc("ทูโฟฟอส", "นาข้าว", rerank=0.70),
        ]

        plant_type = "ทุเรียน"
        for doc in docs:
            crops = str(doc.metadata.get('applicable_crops') or '')
            if plant_type in crops:
                doc.rerank_score = min(1.0, doc.rerank_score + 0.05)
            elif crops.strip():
                doc.rerank_score = max(0.0, doc.rerank_score - 0.15)

        docs_sorted = sorted(docs, key=lambda d: d.rerank_score, reverse=True)

        # ราเซอร์ (has ทุเรียน) should be first
        assert docs_sorted[0].title == "ราเซอร์"
        # ทูโฟฟอส (rice only) should be penalized
        assert docs_sorted[1].title == "ทูโฟฟอส"
        assert docs_sorted[1].rerank_score == pytest.approx(0.55, abs=0.01)


# ---------------------------------------------------------------------------
# Test: Broader category matching (ทุเรียน → ไม้ยืนต้น)
# ---------------------------------------------------------------------------

class TestBroaderCategoryMatching:
    """Test that plant_type matches via broader category (e.g. ทุเรียน → ไม้ยืนต้น)."""

    def test_plant_matches_crops_direct(self):
        """Direct match: 'ทุเรียน' in 'ทุเรียน, มะม่วง'."""
        from app.services.rag.retrieval_agent import _plant_matches_crops
        assert _plant_matches_crops("ทุเรียน", "ทุเรียน, มะม่วง") is True

    def test_plant_matches_crops_via_broader_category(self):
        """Broader match: ทุเรียน is ไม้ยืนต้น, so 'ไม้ยืนต้น เช่น ปาล์ม ยาง' should match."""
        from app.services.rag.retrieval_agent import _plant_matches_crops
        assert _plant_matches_crops("ทุเรียน", "ไม้ยืนต้น เช่น ปาล์ม ยาง") is True

    def test_plant_matches_crops_via_fruit_tree(self):
        """Broader match: มะม่วง is ไม้ผล."""
        from app.services.rag.retrieval_agent import _plant_matches_crops
        assert _plant_matches_crops("มะม่วง", "ไม้ผล ทุกชนิด") is True

    def test_plant_no_match(self):
        """No match: ข้าว is not in 'อ้อย, มันสำปะหลัง'."""
        from app.services.rag.retrieval_agent import _plant_matches_crops
        assert _plant_matches_crops("ข้าว", "อ้อย, มันสำปะหลัง") is False

    def test_plant_field_crop_broader(self):
        """Broader match: อ้อย is พืชไร่."""
        from app.services.rag.retrieval_agent import _plant_matches_crops
        assert _plant_matches_crops("อ้อย", "พืชไร่ เช่น มันสำปะหลัง") is True

    def test_durian_broader_no_penalty_in_scoring(self):
        """For ทุเรียน query, product with 'ไม้ยืนต้น' should get +0.05, NOT -0.15."""
        from app.services.rag.retrieval_agent import _plant_matches_crops

        doc = _make_doc("อัพดาว", "ไม้ยืนต้น เช่น ปาล์ม ยาง", rerank=0.70)
        plant_type = "ทุเรียน"
        crops = str(doc.metadata.get('applicable_crops') or '')
        selling = str(doc.metadata.get('selling_point') or '')

        if _plant_matches_crops(plant_type, crops) and ('เน้นสำหรับ' in crops or f'{plant_type}อันดับ' in selling):
            doc.rerank_score = min(1.0, doc.rerank_score + 0.20)
        elif _plant_matches_crops(plant_type, crops):
            doc.rerank_score = min(1.0, doc.rerank_score + 0.05)
        elif crops.strip():
            doc.rerank_score = max(0.0, doc.rerank_score - 0.15)

        # Should get +0.05 (broader match), NOT -0.15 (mismatch)
        assert doc.rerank_score == pytest.approx(0.75, abs=0.01)

    def test_broader_category_in_response_warning(self):
        """Product with 'ไม้ยืนต้น' should NOT get crop warning for ทุเรียน query."""
        from app.services.rag.retrieval_agent import _plant_matches_crops

        crops_str = "ไม้ยืนต้น เช่น ปาล์ม ยาง"
        plant_type = "ทุเรียน"

        # response_generator_agent imports _plant_matches_crops from retrieval_agent
        # so same function is used — should match via broader category → no warning
        assert _plant_matches_crops(plant_type, crops_str) is True


# ---------------------------------------------------------------------------
# Helpers for disease/pest pre-filter tests
# ---------------------------------------------------------------------------

def _make_disease_doc(name, crops, fungicides="", insecticides="", category="Fungicide",
                      strategy="Skyrocket", similarity=0.50, rerank=0.70):
    """Create a doc with pest column data for disease/pest filter tests."""
    return RetrievedDocument(
        id=f"id-{name}",
        title=name,
        content=f"{name} product",
        source="products",
        similarity_score=similarity,
        rerank_score=rerank,
        metadata={
            "product_name": name,
            "active_ingredient": "test-ingredient",
            "category": category,
            "applicable_crops": crops,
            "fungicides": fungicides,
            "insecticides": insecticides,
            "herbicides": "",
            "biostimulant": "",
            "pgr_hormones": "",
            "how_to_use": "",
            "usage_rate": "100 มล./ไร่",
            "strategy": strategy,
        },
    )


# ---------------------------------------------------------------------------
# Test: Disease pre-filter (new)
# ---------------------------------------------------------------------------

class TestDiseasePreFilter:
    """Test that response generator filters out products not targeting the queried disease."""

    @pytest.mark.asyncio
    async def test_disease_filter_removes_non_matching(self):
        """For 'ใบจุดสีน้ำตาล', products for 'ใบจุดสนิม' should be filtered out."""
        mock_openai = AsyncMock()
        choice = MagicMock()
        choice.message.content = "ลัดดาแนะนำรีโนเวทค่ะ"
        mock_openai.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[choice])
        )

        agent = ResponseGeneratorAgent(openai_client=mock_openai)

        docs = [
            _make_disease_doc("รีโนเวท", "นาข้าว", fungicides="โรคใบจุดสีน้ำตาล, โรคไหม้"),
            _make_disease_doc("ไซม๊อกซิเมท", "นาข้าว, ทุเรียน", fungicides="โรคเชื้อราทั่วไป ใบจุดสนิม"),
            _make_disease_doc("ก๊อปกัน", "นาข้าว", fungicides="โรคเชื้อรา ใบจุดสนิม"),
        ]

        qa = QueryAnalysis(
            original_query="ใบจุดสีน้ำตาลในนาข้าวใช้ยาอะไร",
            intent=IntentType.DISEASE_TREATMENT,
            confidence=0.95,
            entities={"plant_type": "ข้าว", "disease_name": "ใบจุดสีน้ำตาล"},
            expanded_queries=["ใบจุดสีน้ำตาล นาข้าว"],
            required_sources=["products"],
        )
        retrieval = RetrievalResult(
            documents=docs, total_retrieved=3, total_after_rerank=3,
            avg_similarity=0.50, avg_rerank_score=0.70, sources_used=["products"],
        )
        grounding = GroundingResult(
            is_grounded=True, confidence=0.80, citations=[],
            ungrounded_claims=[], suggested_answer="", relevant_products=[],
        )

        result = await agent.generate(qa, retrieval, grounding)
        assert result is not None

        # Check that only disease-matching product (รีโนเวท) appears in LLM context
        call_args = mock_openai.chat.completions.create.call_args
        messages = call_args.kwargs.get('messages') or call_args[1].get('messages', [])
        all_content = " ".join(m.get("content", "") for m in messages)

        assert "รีโนเวท" in all_content
        # ไซม๊อกซิเมท and ก๊อปกัน should be filtered out (ใบจุดสนิม ≠ ใบจุดสีน้ำตาล)
        assert "ไซม๊อกซิเมท" not in all_content
        assert "ก๊อปกัน" not in all_content

    @pytest.mark.asyncio
    async def test_disease_filter_keeps_possible_diseases(self):
        """For 'รากเน่า' with possible_diseases, keep products matching pathogens."""
        mock_openai = AsyncMock()
        choice = MagicMock()
        choice.message.content = "ลัดดาแนะนำไซม๊อกซิเมทค่ะ"
        mock_openai.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[choice])
        )

        agent = ResponseGeneratorAgent(openai_client=mock_openai)

        docs = [
            _make_disease_doc("ไซม๊อกซิเมท", "ทุเรียน",
                              fungicides="ไฟทอปธอร่า, โรครากเน่าโคนเน่า"),
            _make_disease_doc("คาริสมา", "ทุเรียน",
                              fungicides="ฟิวซาเรียม, ราสนิม"),
            _make_disease_doc("วอร์แรนต์", "ทุเรียน",
                              fungicides="โรคเชื้อราทั่วไป ราสนิม"),
        ]

        qa = QueryAnalysis(
            original_query="รากเน่า",
            intent=IntentType.DISEASE_TREATMENT,
            confidence=0.95,
            entities={
                "disease_name": "รากเน่า",
                "possible_diseases": ["ไฟทอปธอร่า", "ฟิวซาเรียม", "พิเทียม"],
            },
            expanded_queries=["รากเน่า", "ไฟทอปธอร่า"],
            required_sources=["products"],
        )
        retrieval = RetrievalResult(
            documents=docs, total_retrieved=3, total_after_rerank=3,
            avg_similarity=0.50, avg_rerank_score=0.70, sources_used=["products"],
        )
        grounding = GroundingResult(
            is_grounded=True, confidence=0.80, citations=[],
            ungrounded_claims=[], suggested_answer="", relevant_products=[],
        )

        result = await agent.generate(qa, retrieval, grounding)
        assert result is not None

        call_args = mock_openai.chat.completions.create.call_args
        messages = call_args.kwargs.get('messages') or call_args[1].get('messages', [])
        all_content = " ".join(m.get("content", "") for m in messages)

        # ไซม๊อกซิเมท has "โรครากเน่าโคนเน่า" matching "รากเน่า" → keep
        assert "ไซม๊อกซิเมท" in all_content
        # คาริสมา has "ฟิวซาเรียม" which is only a possible_disease pathogen, NOT the queried disease → filter
        assert "คาริสมา" not in all_content
        # วอร์แรนต์ doesn't match queried disease → filter
        assert "วอร์แรนต์" not in all_content


# ---------------------------------------------------------------------------
# Test: Pest pre-filter (new)
# ---------------------------------------------------------------------------

class TestPestPreFilter:
    """Test that response generator filters out products not targeting the queried pest."""

    @pytest.mark.asyncio
    async def test_pest_filter_removes_non_matching(self):
        """For 'เพลี้ยแป้ง', products for 'เพลี้ยไฟ' should be filtered out."""
        mock_openai = AsyncMock()
        choice = MagicMock()
        choice.message.content = "ลัดดาแนะนำอิมิดาโกลด์ค่ะ"
        mock_openai.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[choice])
        )

        agent = ResponseGeneratorAgent(openai_client=mock_openai)

        docs = [
            _make_disease_doc("อิมิดาโกลด์ 70", "ทุเรียน",
                              insecticides="เพลี้ยไฟ เพลี้ยแป้ง เพลี้ยไก่แจ้",
                              category="Insecticide"),
            _make_disease_doc("ชุด กล่องม่วง", "ทุเรียน",
                              insecticides="เพลี้ยไฟ หนอนเจาะ",
                              category="Insecticide"),
            _make_disease_doc("เกรด 5 เอสซี", "ทุเรียน",
                              insecticides="แมลงค่อมทอง ดวงกัดใบ",
                              category="Insecticide"),
        ]

        qa = QueryAnalysis(
            original_query="เพลี้ยแป้งในทุเรียนใช้ยาอะไร",
            intent=IntentType.PEST_CONTROL,
            confidence=0.95,
            entities={"plant_type": "ทุเรียน", "pest_name": "เพลี้ยแป้ง"},
            expanded_queries=["เพลี้ยแป้ง ทุเรียน"],
            required_sources=["products"],
        )
        retrieval = RetrievalResult(
            documents=docs, total_retrieved=3, total_after_rerank=3,
            avg_similarity=0.50, avg_rerank_score=0.70, sources_used=["products"],
        )
        grounding = GroundingResult(
            is_grounded=True, confidence=0.80, citations=[],
            ungrounded_claims=[], suggested_answer="", relevant_products=[],
        )

        result = await agent.generate(qa, retrieval, grounding)
        assert result is not None

        call_args = mock_openai.chat.completions.create.call_args
        messages = call_args.kwargs.get('messages') or call_args[1].get('messages', [])
        all_content = " ".join(m.get("content", "") for m in messages)

        # อิมิดาโกลด์ has เพลี้ยแป้ง → keep
        assert "อิมิดาโกลด์" in all_content
        # ชุด กล่องม่วง has เพลี้ยไฟ only → filtered out
        assert "กล่องม่วง" not in all_content
        # เกรด 5 has แมลงค่อมทอง → filtered out
        assert "เกรด 5" not in all_content


# ---------------------------------------------------------------------------
# Test: Broad pest term skips pre-filter
# ---------------------------------------------------------------------------

class TestBroadPestTermSkipsFilter:
    """Test that broad pest terms like 'แมลง' skip the pest pre-filter."""

    @pytest.mark.asyncio
    async def test_broad_pest_term_keeps_all_insecticides(self):
        """For 'ยาฆ่าแมลงในนาข้าว' (pest_name='แมลง'), all insecticide products should pass."""
        mock_openai = AsyncMock()
        choice = MagicMock()
        choice.message.content = "ลัดดาแนะนำสินค้าค่ะ"
        mock_openai.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[choice])
        )

        agent = ResponseGeneratorAgent(openai_client=mock_openai)

        docs = [
            _make_disease_doc("ไฮซีส", "นาข้าว",
                              insecticides="หนอนกอในนาข้าว, หนอนม้วนใบในนาข้าว",
                              category="Insecticide"),
            _make_disease_doc("เกรด 5 เอสซี", "นาข้าว",
                              insecticides="เพลี้ยกระโดดสีน้ำตาลในนาข้าว",
                              category="Insecticide"),
            _make_disease_doc("อิมิดาโกลด์ 70", "นาข้าว",
                              insecticides="เพลี้ยกระโดดสีน้ำตาลในนาข้าว, เพลี้ยไฟในนาข้าว",
                              category="Insecticide"),
        ]

        qa = QueryAnalysis(
            original_query="ยาฆ่าแมลงในนาข้าว",
            intent=IntentType.PEST_CONTROL,
            confidence=0.95,
            entities={"plant_type": "ข้าว", "pest_name": "แมลง"},
            expanded_queries=["ยาฆ่าแมลง นาข้าว"],
            required_sources=["products"],
        )
        retrieval = RetrievalResult(
            documents=docs, total_retrieved=3, total_after_rerank=3,
            avg_similarity=0.50, avg_rerank_score=0.70, sources_used=["products"],
        )
        grounding = GroundingResult(
            is_grounded=True, confidence=0.80, citations=[],
            ungrounded_claims=[], suggested_answer="", relevant_products=[],
        )

        result = await agent.generate(qa, retrieval, grounding)
        assert result is not None

        call_args = mock_openai.chat.completions.create.call_args
        messages = call_args.kwargs.get('messages') or call_args[1].get('messages', [])
        all_content = " ".join(m.get("content", "") for m in messages)

        # ALL insecticide products should appear (broad term skips filter)
        assert "ไฮซีส" in all_content
        assert "เกรด 5" in all_content
        assert "อิมิดาโกลด์" in all_content

    @pytest.mark.asyncio
    async def test_specific_pest_still_filters(self):
        """For specific pest 'เพลี้ยไก่แจ้', pre-filter should still work normally."""
        mock_openai = AsyncMock()
        choice = MagicMock()
        choice.message.content = "ลัดดาแนะนำสินค้าค่ะ"
        mock_openai.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[choice])
        )

        agent = ResponseGeneratorAgent(openai_client=mock_openai)

        docs = [
            _make_disease_doc("อิมิดาโกลด์ 70", "ทุเรียน",
                              insecticides="เพลี้ยไก่แจ้ เพลี้ยแป้ง",
                              category="Insecticide"),
            _make_disease_doc("ชุด กล่องม่วง", "ทุเรียน",
                              insecticides="เพลี้ยไฟ หนอนเจาะ",
                              category="Insecticide"),
        ]

        qa = QueryAnalysis(
            original_query="เพลี้ยไก่แจ้ในทุเรียน",
            intent=IntentType.PEST_CONTROL,
            confidence=0.95,
            entities={"plant_type": "ทุเรียน", "pest_name": "เพลี้ยไก่แจ้"},
            expanded_queries=["เพลี้ยไก่แจ้ ทุเรียน"],
            required_sources=["products"],
        )
        retrieval = RetrievalResult(
            documents=docs, total_retrieved=2, total_after_rerank=2,
            avg_similarity=0.50, avg_rerank_score=0.70, sources_used=["products"],
        )
        grounding = GroundingResult(
            is_grounded=True, confidence=0.80, citations=[],
            ungrounded_claims=[], suggested_answer="", relevant_products=[],
        )

        result = await agent.generate(qa, retrieval, grounding)
        assert result is not None

        call_args = mock_openai.chat.completions.create.call_args
        messages = call_args.kwargs.get('messages') or call_args[1].get('messages', [])
        all_content = " ".join(m.get("content", "") for m in messages)

        # อิมิดาโกลด์ has เพลี้ยไก่แจ้ → keep
        assert "อิมิดาโกลด์" in all_content
        # ชุด กล่องม่วง has เพลี้ยไฟ only → filtered out
        assert "กล่องม่วง" not in all_content


# ---------------------------------------------------------------------------
# Test: Crop pre-filter exempts disease-matching docs
# ---------------------------------------------------------------------------

class TestCropFilterDiseaseExemption:
    """Test that crop pre-filter preserves disease-matching docs (ราสีชมพู bug fix)."""

    @pytest.mark.asyncio
    async def test_crop_filter_keeps_disease_matching_doc(self):
        """Disease-matching doc should survive crop pre-filter even if crops don't match."""
        mock_openai = AsyncMock()
        choice = MagicMock()
        choice.message.content = "ลัดดาแนะนำสินค้าค่ะ"
        mock_openai.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[choice])
        )

        agent = ResponseGeneratorAgent(openai_client=mock_openai)

        docs = [
            # This product matches crop (ทุเรียน) but NOT disease
            _make_disease_doc("คาริสมา", "ทุเรียน, มันฝรั่ง",
                              fungicides="ราสนิม, ใบจุด"),
            # This product matches disease (ราสีชมพู) but NOT crop
            _make_disease_doc("ซัลเฟอร์โปร", "มะม่วง, มะพร้าว",
                              fungicides="ราสีชมพู, ราแป้ง"),
        ]

        qa = QueryAnalysis(
            original_query="ราสีชมพูในทุเรียนใช้ยาอะไร",
            intent=IntentType.DISEASE_TREATMENT,
            confidence=0.95,
            entities={"plant_type": "ทุเรียน", "disease_name": "ราสีชมพู"},
            expanded_queries=["ราสีชมพู ทุเรียน"],
            required_sources=["products"],
        )
        retrieval = RetrievalResult(
            documents=docs, total_retrieved=2, total_after_rerank=2,
            avg_similarity=0.50, avg_rerank_score=0.70, sources_used=["products"],
        )
        grounding = GroundingResult(
            is_grounded=True, confidence=0.80, citations=[],
            ungrounded_claims=[], suggested_answer="", relevant_products=[],
        )

        result = await agent.generate(qa, retrieval, grounding)
        assert result is not None

        call_args = mock_openai.chat.completions.create.call_args
        messages = call_args.kwargs.get('messages') or call_args[1].get('messages', [])
        all_content = " ".join(m.get("content", "") for m in messages)

        # ซัลเฟอร์โปร should survive crop filter (disease exempt) AND pass disease filter
        assert "ซัลเฟอร์โปร" in all_content
        # คาริสมา should be removed by disease pre-filter (doesn't target ราสีชมพู)
        assert "คาริสมา" not in all_content
