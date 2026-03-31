"""
WebSocket endpoint for Dashboard real-time updates.
Events: chat messages, handoff notifications, stats updates, alerts.
"""
import asyncio
import json
import logging
import time
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

# Connected admin clients
_connections: Set[WebSocket] = set()
_lock = asyncio.Lock()


async def broadcast(event: str, data: dict):
    """Broadcast event to all connected admin clients."""
    if not _connections:
        return
    message = json.dumps({"event": event, "data": data, "ts": time.time()})
    disconnected = set()
    async with _lock:
        for ws in _connections:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.add(ws)
        _connections -= disconnected


async def emit_new_message(user_id: str, display_name: str, platform: str, content: str):
    """Emit when user sends a new message."""
    await broadcast("chat:new_message", {
        "user_id": user_id,
        "display_name": display_name,
        "platform": platform,
        "content": content[:200],
    })


async def emit_bot_reply(user_id: str, content: str):
    """Emit when bot replies to user."""
    await broadcast("chat:bot_reply", {
        "user_id": user_id,
        "content": content[:200],
    })


async def emit_handoff(handoff_id: int, user_id: str, display_name: str, trigger_message: str, status: str):
    """Emit handoff status change."""
    await broadcast(f"handoff:{status}", {
        "handoff_id": handoff_id,
        "user_id": user_id,
        "display_name": display_name,
        "trigger_message": trigger_message[:100],
        "status": status,
    })


async def emit_alert(alert_type: str, message: str, severity: str):
    """Emit new system alert."""
    await broadcast("alert:new", {
        "alert_type": alert_type,
        "message": message,
        "severity": severity,
    })


async def _stats_loop(ws: WebSocket):
    """Send dashboard stats every 30 seconds."""
    while True:
        try:
            await asyncio.sleep(30)
            from app.dependencies import supabase_client
            if not supabase_client:
                continue

            # Quick stats
            from app.utils.async_db import aexecute
            events = await aexecute(
                supabase_client.table('ladda_analyst_event')
                .select('id', count='exact')
            )
            users = await aexecute(
                supabase_client.table('user_ladda(LINE,FACE)')
                .select('id', count='exact')
            )

            await ws.send_text(json.dumps({
                "event": "stats:update",
                "data": {
                    "total_events": events.count or 0,
                    "total_users": users.count or 0,
                },
                "ts": time.time(),
            }))
        except (WebSocketDisconnect, Exception):
            break


@router.websocket("/ws/admin")
async def admin_websocket(ws: WebSocket):
    """WebSocket endpoint for admin dashboard real-time updates."""
    await ws.accept()
    logger.info("WebSocket: admin connected")

    async with _lock:
        _connections.add(ws)

    stats_task = asyncio.create_task(_stats_loop(ws))

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                event = msg.get("event", "")
                data = msg.get("data", {})

                if event == "chat:send":
                    # Admin sends message to user
                    user_id = data.get("user_id", "")
                    message = data.get("message", "")
                    if user_id and message:
                        from app.routers.admin_chat import _send_message_to_user
                        result = await _send_message_to_user(user_id, message)
                        await ws.send_text(json.dumps({
                            "event": "chat:sent",
                            "data": {"user_id": user_id, "success": result},
                        }))

                elif event == "handoff:claim":
                    handoff_id = data.get("handoff_id")
                    if handoff_id:
                        from app.services.handoff import claim_handoff
                        await claim_handoff(handoff_id, "admin")
                        await broadcast("handoff:claimed", {"handoff_id": handoff_id})

                elif event == "handoff:resolve":
                    handoff_id = data.get("handoff_id")
                    if handoff_id:
                        from app.services.handoff import resolve_handoff
                        await resolve_handoff(handoff_id)
                        await broadcast("handoff:resolved", {"handoff_id": handoff_id})

                elif event == "ping":
                    await ws.send_text(json.dumps({"event": "pong", "ts": time.time()}))

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        logger.info("WebSocket: admin disconnected")
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
    finally:
        stats_task.cancel()
        async with _lock:
            _connections.discard(ws)
