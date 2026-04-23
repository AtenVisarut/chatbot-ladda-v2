"""
Sales-popularity handler (2026-04-23):

Bot has no real sales data. Two-branch handler:
  - Success branch: prior products contain ≥1 priority item → lead with
    "ไม่มีข้อมูลยอดขาย" disclaimer + list the priority subset.
  - No-priority-match branch: return a short admin-handoff marker so the
    webhook's `_is_no_data_answer` filter drops the reply and alerts admin.

Internal classification names (Skyrocket / Expand / Natural / Standard /
Cosmic-star) MUST never appear in any user-facing string.
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


_STRATEGY_SECRETS = ('Skyrocket', 'Expand', 'Natural', 'Standard', 'Cosmic-star')


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
        "ตัวไหนนิยม",
        "อันไหนนิยม",
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
# Handler branches
# =============================================================================

class TestSalesPopularityFollowup:
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
    async def test_filters_to_priority_products(self):
        """Prior list of 5 products → keep only priority strategies, preserve order."""
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
        # Priority products kept, non-priority dropped
        assert 'แกนเตอร์' in result
        assert 'อะนิลการ์ด' in result
        assert 'ทูโฟฟอส' in result
        assert 'ไดนาคลอร์' not in result
        assert 'เลกาซี 10' not in result
        # Order preserved: แกนเตอร์ (1st) → อะนิลการ์ด → ทูโฟฟอส
        assert result.index('แกนเตอร์') < result.index('อะนิลการ์ด') < result.index('ทูโฟฟอส')
        # User-visible disclaimer present
        assert 'ไม่มีข้อมูลยอดขาย' in result
        # Internal strategy names MUST NEVER leak to user-facing copy
        for secret in _STRATEGY_SECRETS:
            assert secret not in result, f"Internal strategy name {secret!r} leaked to user"

    @pytest.mark.asyncio
    async def test_no_priority_match_returns_admin_handoff_marker(self):
        """All prior products are non-priority → short marker that webhook
        drops silently and hands off to admin — no fabricated answer to user."""
        from app.routers.webhook import _is_no_data_answer
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
        # Must pass the webhook's silent-drop filter so admin handles it
        assert _is_no_data_answer(result), (
            f"No-priority-match reply must trigger admin-handoff via "
            f"webhook._is_no_data_answer, got: {result!r}"
        )
        # And of course — no strategy leak even in the handoff marker
        for secret in _STRATEGY_SECRETS:
            assert secret not in result, f"Strategy name {secret!r} leaked in handoff marker"

    @pytest.mark.asyncio
    async def test_preserves_category_context_no_cross_category(self):
        """Regression for dealer screenshot: herbicide list → sales-popularity must
        NOT introduce Fungicide/Insecticide/Biostim that weren't in original list.
        """
        from app.services.chat import handler

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
# Source-level guards — wire-up + admin-handoff must not regress
# =============================================================================

class TestSourceGuards:
    def test_handler_wired_after_safety_intercept(self):
        from app.services.chat import handler
        src = inspect.getsource(handler.handle_natural_conversation)
        assert "_handle_sales_popularity_followup" in src

    def test_admin_handoff_skips_memory_save(self):
        """The admin-handoff branch (no priority match) must NOT call
        add_to_memory — user never sees that reply, so saving would
        corrupt conversation context."""
        from app.services.chat import handler
        src = inspect.getsource(handler.handle_natural_conversation)
        # The wire-up must consult _is_no_data_answer before add_to_memory
        idx = src.find("_handle_sales_popularity_followup")
        assert idx > -1
        block = src[idx : idx + 500]
        assert "_is_no_data_answer" in block, (
            "Sales-popularity wire-up must gate add_to_memory on "
            "webhook._is_no_data_answer so the admin-handoff marker "
            "doesn't pollute conversation memory"
        )
