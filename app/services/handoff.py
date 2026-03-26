"""
Human Handoff Manager — ระบบส่งต่อให้ admin ตอบแทน bot
เมื่อ bot ตอบไม่ได้ (_is_no_data_answer) → สร้าง handoff → admin ตอบผ่าน admin chat
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from supabase import Client
from app.utils.async_db import aexecute

logger = logging.getLogger(__name__)


class HandoffManager:
    """จัดการ handoff ระหว่าง bot กับ admin"""

    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
        logger.info("HandoffManager initialized")

    async def create_handoff(
        self,
        user_id: str,
        platform: str,
        display_name: str = "",
        trigger_message: str = "",
    ) -> Optional[int]:
        """สร้าง handoff เมื่อ bot ตอบไม่ได้ — ไม่สร้างซ้ำถ้ามี pending/active อยู่"""
        try:
            # เช็คว่ามี pending/active อยู่แล้วไหม
            existing = await aexecute(
                self.supabase.table("admin_handoffs")
                .select("id")
                .eq("user_id", user_id)
                .in_("status", ["pending", "active"])
            )
            if existing.data:
                logger.info(
                    f"Handoff already exists for {user_id[:8]}... (id={existing.data[0]['id']})"
                )
                return existing.data[0]["id"]

            data = {
                "user_id": user_id,
                "platform": platform,
                "display_name": display_name or user_id[:12],
                "trigger_message": trigger_message[:500] if trigger_message else "",
                "status": "pending",
            }
            result = await aexecute(
                self.supabase.table("admin_handoffs").insert(data)
            )
            if result.data:
                hid = result.data[0]["id"]
                logger.info(
                    f"Handoff created: id={hid} user={user_id[:8]}... platform={platform}"
                )
                return hid
            return None
        except Exception as e:
            logger.error(f"Failed to create handoff: {e}")
            return None

    async def get_handoffs(
        self, status: Optional[str] = None, limit: int = 50
    ) -> List[dict]:
        """ดึง handoffs ตาม status"""
        try:
            query = (
                self.supabase.table("admin_handoffs")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
            )
            if status:
                if status in ("pending", "active"):
                    query = query.in_("status", ["pending", "active"])
                else:
                    query = query.eq("status", status)
            result = await aexecute(query)
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to get handoffs: {e}")
            return []

    async def get_pending_count(self) -> int:
        """นับ handoff ที่รอตอบ"""
        try:
            result = await aexecute(
                self.supabase.table("admin_handoffs")
                .select("id", count="exact")
                .in_("status", ["pending", "active"])
            )
            return result.count or 0
        except Exception as e:
            logger.error(f"Failed to get pending count: {e}")
            return 0

    async def claim_handoff(self, handoff_id: int, admin_name: str) -> bool:
        """Admin claim handoff → status=active"""
        try:
            await aexecute(self.supabase.table("admin_handoffs").update(
                {"status": "active", "assigned_admin": admin_name}
            ).eq("id", handoff_id))
            logger.info(f"Handoff {handoff_id} claimed by {admin_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to claim handoff: {e}")
            return False

    async def resolve_handoff(
        self, handoff_id: int, admin_name: str = ""
    ) -> bool:
        """Admin resolve handoff → status=resolved"""
        try:
            update = {
                "status": "resolved",
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            }
            if admin_name:
                update["assigned_admin"] = admin_name
            await aexecute(self.supabase.table("admin_handoffs").update(update).eq(
                "id", handoff_id
            ))
            logger.info(f"Handoff {handoff_id} resolved by {admin_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to resolve handoff: {e}")
            return False

    async def get_handoff_for_user(self, user_id: str) -> Optional[dict]:
        """ดึง active/pending handoff ของ user"""
        try:
            result = await aexecute(
                self.supabase.table("admin_handoffs")
                .select("*")
                .eq("user_id", user_id)
                .in_("status", ["pending", "active"])
                .order("created_at", desc=True)
                .limit(1)
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to get handoff for user: {e}")
            return None
