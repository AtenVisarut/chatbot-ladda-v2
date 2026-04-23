"""
Sales-popularity follow-up handler (2026-04-23):

Fixes cross-category answer when user asks "ขายดี/นิยม" after a product list:
- Reuse previous turn's active_products (preserve category)
- Filter to Skyrocket/Expand strategy (ICP's push priorities)
- Disclose that real sales data isn't in the system
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# Pattern detection
# =============================================================================

class TestPatternDetection:
    """_is_sales_popularity_query should match Thai + English sales phrasings."""

    @pytest.mark.parametrize("query", [
        "ขอสินค้าขายดีเลยได้ไหม",
        "ตัวไหนขายดี",
        "ขายดีที่สุดคือตัวไหน",
        "อยากได้ตัวยอดนิยม",
        "ที่นิยมใช้คือตัวไหน",
        "ฮิตที่สุด",
        "popular product",
        "best seller",
    ])
    def test_matches(self, query):
        from app.services.chat.handler import _is_sales_popularity_query
        assert _is_sales_popularity_query(query), f"Should match: {query!r}"

    @pytest.mark.parametrize("query", [
        "อัตราใช้เท่าไหร่",
        "ใช้ยังไง",
        "คาริสมาใช้อะไร",
        "มีปุ๋ยแนะนำไหม",
        "แนะนำสินค้า",
    ])
    def test_non_matches(self, query):
        from app.services.chat.handler import _is_sales_popularity_query
        assert not _is_sales_popularity_query(query), f"Should not match: {query!r}"


# =============================================================================
# Follow-up handler — context preservation + strategy filter
# =============================================================================

class TestSalesPopularityFollowup:
    """Handler returns filtered response only when prior state exists."""

    @pytest.mark.asyncio
    async def test_no_pattern_returns_none(self):
        from app.services.chat.handler import _handle_sales_popularity_followup
        with patch("app.services.chat.handler.get_conversation_state",
                   new_callable=AsyncMock, return_value={'active_products': ['แกนเตอร์']}):
            result = await _handle_sales_popularity_followup('u1', 'ใช้ยังไง')
            assert result is None

    @pytest.mark.asyncio
    async def test_no_state_returns_none(self):
        """Pattern matches but no prior state → fall through to RAG."""
        from app.services.chat.handler import _handle_sales_popularity_followup
        with patch("app.services.chat.handler.get_conversation_state",
                   new_callable=AsyncMock, return_value=None):
            result = await _handle_sales_popularity_followup('u1', 'ตัวไหนขายดี')
            assert result is None

    @pytest.mark.asyncio
    async def test_empty_active_products_returns_none(self):
        from app.services.chat.handler import _handle_sales_popularity_followup
        with patch("app.services.chat.handler.get_conversation_state",
                   new_callable=AsyncMock, return_value={'active_products': []}):
            result = await _handle_sales_popularity_followup('u1', 'ตัวไหนขายดี')
            assert result is None

    @pytest.mark.asyncio
    async def test_filters_to_skyrocket_expand(self):
        """Prior list of 5 products → keep only Skyrocket + Expand, preserve order."""
        from app.services.chat import handler

        state = {'active_products': ['แกนเตอร์', 'ไดนาคลอร์', 'อะนิลการ์ด', 'ทูโฟฟอส', 'เลกาซี 10']}
        db_rows = [
            {'product_name': 'แกนเตอร์', 'strategy': 'Skyrocket', 'common_name_th': 'โพรพานิล', 'selling_point': 'ครอบคลุม'},
            {'product_name': 'ไดนาคลอร์', 'strategy': 'Standard', 'common_name_th': 'บิวทาคลอร์', 'selling_point': ''},
            {'product_name': 'อะนิลการ์ด', 'strategy': 'Skyrocket', 'common_name_th': 'อะนิโลฟอส', 'selling_point': 'ใบแคบ/ใบกว้าง'},
            {'product_name': 'ทูโฟฟอส', 'strategy': 'Skyrocket', 'common_name_th': '2,4-D', 'selling_point': 'ข้าวดีด'},
            {'product_name': 'เลกาซี 10', 'strategy': 'Natural', 'common_name_th': '', 'selling_point': ''},
        ]

        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value.data = db_rows

        with patch("app.services.chat.handler.get_conversation_state",
                   new_callable=AsyncMock, return_value=state), \
             patch("app.services.chat.handler.supabase_client", mock_sb):
            result = await handler._handle_sales_popularity_followup('u1', 'ตัวไหนขายดี')

        assert result is not None
        # Expected: 3 Skyrocket products in order, no Standard/Natural
        assert 'แกนเตอร์' in result
        assert 'อะนิลการ์ด' in result
        assert 'ทูโฟฟอส' in result
        assert 'ไดนาคลอร์' not in result
        assert 'เลกาซี 10' not in result
        # Order preserved: แกนเตอร์ (1st) → อะนิลการ์ด → ทูโฟฟอส
        assert result.index('แกนเตอร์') < result.index('อะนิลการ์ด') < result.index('ทูโฟฟอส')
        # Disclaimer present
        assert 'ไม่มีข้อมูลยอดขาย' in result
        assert 'Skyrocket' in result or 'Expand' in result

    @pytest.mark.asyncio
    async def test_no_sky_expand_in_list_returns_disclaimer(self):
        """All prior products are Standard/Natural → explicit 'no push product' reply."""
        from app.services.chat import handler

        state = {'active_products': ['ไดนาคลอร์', 'เลกาซี 10']}
        db_rows = [
            {'product_name': 'ไดนาคลอร์', 'strategy': 'Standard', 'common_name_th': '', 'selling_point': ''},
            {'product_name': 'เลกาซี 10', 'strategy': 'Natural', 'common_name_th': '', 'selling_point': ''},
        ]
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value.data = db_rows

        with patch("app.services.chat.handler.get_conversation_state",
                   new_callable=AsyncMock, return_value=state), \
             patch("app.services.chat.handler.supabase_client", mock_sb):
            result = await handler._handle_sales_popularity_followup('u1', 'ตัวไหนขายดี')

        assert result is not None
        assert 'ไม่มีข้อมูลยอดขาย' in result
        assert 'ยังไม่มีตัวที่อยู่ในกลุ่มสินค้าหลัก' in result

    @pytest.mark.asyncio
    async def test_preserves_category_context_no_cross_category(self):
        """Regression for dealer screenshot: herbicide list → sales-popularity must
        NOT introduce Fungicide/Insecticide/Biostim that weren't in original list.
        """
        from app.services.chat import handler

        # Turn 1 listed only herbicides
        state = {'active_products': ['แกนเตอร์', 'อะนิลการ์ด']}
        db_rows = [
            {'product_name': 'แกนเตอร์', 'strategy': 'Skyrocket', 'common_name_th': '', 'selling_point': ''},
            {'product_name': 'อะนิลการ์ด', 'strategy': 'Skyrocket', 'common_name_th': '', 'selling_point': ''},
        ]
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value.data = db_rows

        with patch("app.services.chat.handler.get_conversation_state",
                   new_callable=AsyncMock, return_value=state), \
             patch("app.services.chat.handler.supabase_client", mock_sb):
            result = await handler._handle_sales_popularity_followup('u1', 'ตัวไหนขายดี')

        # Must not contain unrelated-category products from the screenshot bug
        for forbidden in ('คาริสมา', 'บอมส์', 'NPK', 'แจ๊ส', 'แซด-ซีโร่', 'เมลสัน'):
            assert forbidden not in result, f"Cross-category leakage: {forbidden!r} appeared"


# =============================================================================
# Source-level guard — wire-up must not regress
# =============================================================================

class TestSourceGuards:
    """Handler must be invoked from handle_natural_conversation flow."""

    def test_handler_wired_after_safety_intercept(self):
        from app.services.chat import handler
        src = inspect.getsource(handler.handle_natural_conversation)
        assert "_handle_sales_popularity_followup" in src, (
            "handle_natural_conversation doesn't invoke sales-popularity handler"
        )

    def test_handler_uses_state_and_strategy_filter(self):
        from app.services.chat import handler
        src = inspect.getsource(handler._handle_sales_popularity_followup)
        assert "get_conversation_state" in src
        assert "active_products" in src
        assert "Skyrocket" in src and "Expand" in src
