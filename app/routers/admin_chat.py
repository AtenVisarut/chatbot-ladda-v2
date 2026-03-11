"""
Admin Chat Router — หน้า chat สำหรับ admin ตอบแทน bot
ดึงข้อมูลแชทจาก conversation_memory + admin_handoffs
ส่งข้อความกลับผ่าน LINE Push API / FB Send API
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.dependencies import supabase_client, handoff_manager
from app.services.memory import add_to_memory
from app.services.user_service import refresh_display_name
from app.utils.line.helpers import push_line
from app.utils.facebook.helpers import send_facebook_message, split_message

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")
limiter = Limiter(key_func=get_remote_address)


def _require_auth(request: Request):
    """Check admin session"""
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="Unauthorized")


# ============================================================================
# HTML Page
# ============================================================================


@router.get("/admin/chat", response_class=HTMLResponse)
@limiter.limit("30/minute")
async def admin_chat_page(request: Request):
    if not request.session.get("user"):
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("admin_chat.html", {"request": request})


# ============================================================================
# Conversations API
# ============================================================================


@router.get("/api/admin/conversations")
@limiter.limit("120/minute")
async def get_conversations(request: Request):
    """ดึงรายการแชทจาก user_ladda เป็นหลัก + ดึง preview จาก conversation_memory"""
    _require_auth(request)
    if not supabase_client:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        # Step 1: ดึง ALL registered users จาก user_ladda (แหล่งหลัก)
        users_result = (
            supabase_client.table("user_ladda(LINE,FACE)")
            .select("line_user_id, display_name, updated_at")
            .order("updated_at", desc=True)
            .execute()
        )
        all_users = users_result.data or []

        # Step 2: สร้าง sessions จาก user_ladda (ทุกคนที่ลงทะเบียน)
        sessions = {}
        for u in all_users:
            uid = u["line_user_id"]
            sessions[uid] = {
                "user_id": uid,
                "display_name": u.get("display_name") or uid[:14],
                "platform": "facebook" if uid.startswith("fb:") else "line",
                "last_message": "",
                "last_role": "",
                "last_activity": u.get("updated_at", ""),
                "message_count": 0,
                "has_handoff": False,
                "handoff_id": None,
            }

        # Step 3: ดึง recent messages (7 วัน) เพื่อ preview + sort
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=7)
        ).isoformat()
        msg_result = (
            supabase_client.table("conversation_memory")
            .select("user_id, content, role, created_at")
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(3000)
            .execute()
        )

        for msg in msg_result.data or []:
            uid = msg["user_id"]
            if uid in sessions:
                sessions[uid]["message_count"] += 1
                # อัพเดท last_message/last_activity ถ้ายังว่าง (เอาอันล่าสุด)
                if not sessions[uid]["last_message"]:
                    sessions[uid]["last_message"] = (msg["content"] or "")[:100]
                    sessions[uid]["last_role"] = msg["role"]
                    sessions[uid]["last_activity"] = msg["created_at"]

        # Step 4: Auto-refresh fallback display names (User_xxx → real name)
        for uid, sess in sessions.items():
            if sess["display_name"].startswith("User_"):
                try:
                    new_name = await refresh_display_name(uid)
                    if new_name:
                        sess["display_name"] = new_name
                except Exception:
                    pass

        # Step 5: Mark handoffs
        handoff_convos = []
        if handoff_manager:
            handoffs = await handoff_manager.get_handoffs(status="pending")
            for h in handoffs:
                uid = h["user_id"]
                if uid in sessions:
                    sessions[uid]["has_handoff"] = True
                    sessions[uid]["handoff_id"] = h["id"]

            handoff_convos = sorted(
                [s for s in sessions.values() if s["has_handoff"]],
                key=lambda x: x["last_activity"],
                reverse=True,
            )

        # Step 6: Sort — active users first (มี messages ใน 7 วัน), inactive ตามหลัง
        active = sorted(
            [s for s in sessions.values() if s["message_count"] > 0 and not s["has_handoff"]],
            key=lambda x: x["last_activity"],
            reverse=True,
        )
        inactive = sorted(
            [s for s in sessions.values() if s["message_count"] == 0 and not s["has_handoff"]],
            key=lambda x: x["last_activity"],
            reverse=True,
        )

        return {
            "handoffs": handoff_convos,
            "recent": active + inactive,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/admin/conversations/{user_id:path}/messages")
@limiter.limit("120/minute")
async def get_conversation_messages(
    request: Request, user_id: str, limit: int = 30
):
    """ดึงประวัติแชทของ user"""
    _require_auth(request)
    if not supabase_client:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        result = (
            supabase_client.table("conversation_memory")
            .select("role, content, metadata, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        messages = list(reversed(result.data or []))

        # Enrich: mark admin replies vs bot replies
        for msg in messages:
            metadata = msg.get("metadata") or {}
            if isinstance(metadata, dict) and metadata.get("type") == "admin_reply":
                msg["sender_type"] = "admin"
                msg["admin_name"] = metadata.get("admin", "admin")
            elif msg["role"] == "assistant":
                msg["sender_type"] = "bot"
            else:
                msg["sender_type"] = "user"

        # Get handoff info
        handoff = None
        if handoff_manager:
            handoff = await handoff_manager.get_handoff_for_user(user_id)

        # Get display name
        display_name = user_id[:12]
        try:
            user_result = (
                supabase_client.table("user_ladda(LINE,FACE)")
                .select("display_name")
                .eq("line_user_id", user_id)
                .limit(1)
                .execute()
            )
            if user_result.data and user_result.data[0].get("display_name"):
                display_name = user_result.data[0]["display_name"]
        except Exception:
            pass

        platform = "facebook" if user_id.startswith("fb:") else "line"

        return {
            "user_id": user_id,
            "display_name": display_name,
            "platform": platform,
            "messages": messages,
            "handoff": handoff,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get messages for {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Send Message API
# ============================================================================


class SendMessageRequest(BaseModel):
    message: str


@router.post("/api/admin/conversations/{user_id:path}/send")
@limiter.limit("60/minute")
async def send_admin_message(
    request: Request, user_id: str, body: SendMessageRequest
):
    """Admin ส่งข้อความไปหา user ผ่าน LINE/FB"""
    _require_auth(request)

    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    platform = "facebook" if user_id.startswith("fb:") else "line"
    admin_name = request.session.get("user", "admin")

    try:
        # ส่งข้อความไปหา user
        if platform == "line":
            await push_line(user_id, message)
        else:
            psid = user_id.replace("fb:", "", 1)
            chunks = split_message(message)
            for chunk in chunks:
                await send_facebook_message(psid, chunk)

        # บันทึกใน conversation_memory
        await add_to_memory(
            user_id,
            "assistant",
            message,
            metadata={"type": "admin_reply", "admin": admin_name},
        )

        # Claim handoff if pending
        if handoff_manager:
            handoff = await handoff_manager.get_handoff_for_user(user_id)
            if handoff and handoff["status"] == "pending":
                await handoff_manager.claim_handoff(handoff["id"], admin_name)

        logger.info(
            f"Admin {admin_name} sent message to {user_id[:8]}... via {platform}"
        )
        return {"status": "sent", "platform": platform}

    except Exception as e:
        logger.error(f"Failed to send admin message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Handoff Management API
# ============================================================================


@router.get("/api/admin/handoffs")
@limiter.limit("120/minute")
async def get_handoffs(request: Request, status: Optional[str] = None):
    """ดึงรายการ handoffs"""
    _require_auth(request)
    if not handoff_manager:
        return {"handoffs": [], "count": 0}

    handoffs = await handoff_manager.get_handoffs(status=status)
    return {"handoffs": handoffs, "count": len(handoffs)}


@router.get("/api/admin/handoffs/count")
@limiter.limit("300/minute")
async def get_handoff_count(request: Request):
    """จำนวน pending handoffs (สำหรับ badge)"""
    # No auth required for badge polling (lightweight)
    if not handoff_manager:
        return {"pending": 0}
    count = await handoff_manager.get_pending_count()
    return {"pending": count}


@router.post("/api/admin/handoffs/{handoff_id}/claim")
@limiter.limit("60/minute")
async def claim_handoff(request: Request, handoff_id: int):
    """Admin claim handoff"""
    _require_auth(request)
    if not handoff_manager:
        raise HTTPException(status_code=503, detail="Handoff service not available")

    admin_name = request.session.get("user", "admin")
    success = await handoff_manager.claim_handoff(handoff_id, admin_name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to claim handoff")
    return {"status": "claimed", "admin": admin_name}


@router.post("/api/admin/handoffs/{handoff_id}/resolve")
@limiter.limit("60/minute")
async def resolve_handoff(request: Request, handoff_id: int):
    """Admin resolve handoff → bot กลับมา auto-reply"""
    _require_auth(request)
    if not handoff_manager:
        raise HTTPException(status_code=503, detail="Handoff service not available")

    admin_name = request.session.get("user", "admin")
    success = await handoff_manager.resolve_handoff(handoff_id, admin_name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to resolve handoff")
    return {"status": "resolved", "admin": admin_name}
