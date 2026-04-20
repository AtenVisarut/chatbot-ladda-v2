"""
Tests — fire_no_data_alert() creates both a handoff and an analytics_alert
when the bot cannot answer. Also covers the admin_templates API endpoints
(source-level contract checks).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestFireNoDataAlert:
    """Helper must trigger BOTH handoff creation AND analytics_alerts insert"""

    @pytest.mark.asyncio
    async def test_fires_handoff_and_alert(self):
        from app.services import handoff as handoff_mod

        fake_handoff_mgr = MagicMock()
        fake_handoff_mgr.create_handoff = AsyncMock(return_value=42)
        fake_alert_mgr = MagicMock()
        fake_alert_mgr._create_alert = AsyncMock(return_value=None)

        with patch.object(handoff_mod, "__name__", handoff_mod.__name__), \
             patch("app.dependencies.handoff_manager", fake_handoff_mgr), \
             patch("app.dependencies.alert_manager", fake_alert_mgr):
            await handoff_mod.fire_no_data_alert(
                user_id="U_test_123",
                platform="line",
                question="โรคใบไหม้ข้าว ใช้ยาอะไร",
            )
            # Give the create_task coroutines a tick to run
            await asyncio.sleep(0.05)

        assert fake_handoff_mgr.create_handoff.await_count == 1, (
            "create_handoff should be called exactly once"
        )
        call = fake_handoff_mgr.create_handoff.await_args
        assert call.kwargs.get("user_id") == "U_test_123"
        assert call.kwargs.get("platform") == "line"

        assert fake_alert_mgr._create_alert.await_count == 1, (
            "_create_alert should be called exactly once"
        )
        acall = fake_alert_mgr._create_alert.await_args
        assert acall.kwargs.get("alert_type") == "bot_cannot_answer"
        assert acall.kwargs.get("severity") == "warning"
        msg = acall.kwargs.get("message", "")
        assert "โรคใบไหม้ข้าว" in msg, f"Alert message should embed question, got: {msg}"
        assert "line" in msg.lower()

    @pytest.mark.asyncio
    async def test_silent_when_managers_unavailable(self):
        """ถ้า handoff/alert manager ไม่พร้อม — ไม่ควร raise exception"""
        from app.services import handoff as handoff_mod

        with patch("app.dependencies.handoff_manager", None), \
             patch("app.dependencies.alert_manager", None):
            # Must not raise
            await handoff_mod.fire_no_data_alert(
                user_id="U_null", platform="line", question="test",
            )
            await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_does_not_block_on_error(self):
        """ถ้า create_handoff fail — fire_no_data_alert ยัง return เรียบร้อย"""
        from app.services import handoff as handoff_mod

        bad_handoff = MagicMock()
        bad_handoff.create_handoff = AsyncMock(side_effect=Exception("DB down"))
        bad_alert = MagicMock()
        bad_alert._create_alert = AsyncMock(side_effect=Exception("DB down"))

        with patch("app.dependencies.handoff_manager", bad_handoff), \
             patch("app.dependencies.alert_manager", bad_alert):
            await handoff_mod.fire_no_data_alert(
                user_id="U_err", platform="facebook", question="fail",
            )
            await asyncio.sleep(0.05)


class TestWebhookIntegration:
    """webhook.py + facebook_webhook.py must import and use fire_no_data_alert"""

    def test_line_webhook_imports_fire_no_data_alert(self):
        import inspect
        from app.routers import webhook
        src = inspect.getsource(webhook)
        assert "fire_no_data_alert" in src, (
            "webhook.py must import fire_no_data_alert"
        )
        # Old direct create_handoff paths should be replaced
        assert "handoff_manager.create_handoff" not in src, (
            "webhook.py still calls handoff_manager.create_handoff directly — "
            "should use fire_no_data_alert instead (which also creates alert)"
        )

    def test_facebook_webhook_imports_fire_no_data_alert(self):
        import inspect
        from app.routers import facebook_webhook
        src = inspect.getsource(facebook_webhook)
        assert "fire_no_data_alert" in src, (
            "facebook_webhook.py must import fire_no_data_alert"
        )
        assert "handoff_manager.create_handoff" not in src, (
            "facebook_webhook.py still calls handoff_manager.create_handoff directly"
        )


class TestAdminTemplatesAPI:
    """Source-level checks: CRUD endpoints exist for admin_templates"""

    @pytest.mark.parametrize("path,method", [
        ("/api/admin/templates", "GET"),
        ("/api/admin/templates", "POST"),
        ("/api/admin/templates/{tid}", "PUT"),
        ("/api/admin/templates/{tid}", "DELETE"),
        ("/api/admin/templates/{tid}/use", "POST"),
    ])
    def test_endpoint_registered(self, path, method):
        from app.routers import admin_chat

        # Find the route on the router
        method_matches = [
            r for r in admin_chat.router.routes
            if getattr(r, "path", "") == path
            and method in getattr(r, "methods", set())
        ]
        assert method_matches, (
            f"{method} {path} endpoint not registered in admin_chat router"
        )

    def test_template_endpoints_require_auth(self):
        import inspect
        from app.routers import admin_chat
        src = inspect.getsource(admin_chat)
        # All 5 endpoint functions should call _require_auth
        for fn_name in (
            "list_templates", "create_template",
            "update_template", "delete_template",
            "increment_template_usage",
        ):
            assert fn_name in src, f"Missing endpoint fn: {fn_name}"
            # Locate the function def and check _require_auth is called inside
            fn = getattr(admin_chat, fn_name, None)
            assert fn is not None, f"Function {fn_name} not exported"
            fn_src = inspect.getsource(fn)
            assert "_require_auth" in fn_src, (
                f"{fn_name} should call _require_auth(request)"
            )


class TestAlertManagerStillWorks:
    """Smoke test — AlertManager._create_alert signature matches helper usage"""

    def test_alert_manager_create_alert_signature(self):
        import inspect
        from app.services.analytics import AlertManager
        sig = inspect.signature(AlertManager._create_alert)
        params = list(sig.parameters.keys())
        # Expected: self, alert_type, message, severity
        assert params[1:4] == ["alert_type", "message", "severity"], (
            f"AlertManager._create_alert signature changed: {params}"
        )
