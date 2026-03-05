"""
User Service
Handles user profile tracking via user_ladda(LINE,FACE) table only.
"""

import logging
from typing import Optional, Dict
from datetime import datetime, timezone
import httpx
from app.dependencies import supabase_client
from app.config import LINE_CHANNEL_ACCESS_TOKEN

logger = logging.getLogger(__name__)

LINE_PROFILE_API = "https://api.line.me/v2/bot/profile/{user_id}"

TABLE = 'user_ladda(LINE,FACE)'


async def get_line_profile(user_id: str) -> Optional[Dict]:
    """
    Fetch user profile from LINE API

    Returns:
        dict with keys: userId, displayName, pictureUrl, statusMessage
        None if failed
    """
    try:
        headers = {
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                LINE_PROFILE_API.format(user_id=user_id),
                headers=headers,
                timeout=10.0
            )

        if response.status_code == 200:
            profile = response.json()
            logger.info(f"✓ Fetched LINE profile for {user_id}: {profile.get('displayName')}")
            return profile
        else:
            logger.error(f"Failed to fetch LINE profile: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error fetching LINE profile for {user_id}: {e}", exc_info=True)
        return None


async def get_user(user_id: str) -> Optional[Dict]:
    """Get user from user_ladda(LINE,FACE) table"""
    try:
        if not supabase_client:
            return None

        result = supabase_client.table(TABLE)\
            .select('*')\
            .eq('line_user_id', user_id)\
            .execute()

        if result.data and len(result.data) > 0:
            return result.data[0]
        return None

    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}")
        return None


async def register_user_ladda(user_id: str, display_name: Optional[str] = None) -> bool:
    """
    Register or update user in user_ladda(LINE,FACE) table.

    - New user → insert row
    - Existing user → update updated_at (and display_name if provided)

    Args:
        user_id: LINE user ID or fb:{psid} for Facebook users
        display_name: Display name (optional, mainly from LINE profile)
    """
    try:
        if not supabase_client:
            logger.warning("Supabase client not available — skip register_user_ladda")
            return False

        # Check if user already exists
        result = supabase_client.table(TABLE) \
            .select('id, line_user_id') \
            .eq('line_user_id', user_id) \
            .execute()

        now = datetime.now(timezone.utc).isoformat()

        if result.data and len(result.data) > 0:
            # Existing user → update updated_at (+ display_name if provided)
            update_data = {"updated_at": now}
            if display_name:
                update_data["display_name"] = display_name

            supabase_client.table(TABLE) \
                .update(update_data) \
                .eq('line_user_id', user_id) \
                .execute()
            logger.debug(f"✓ Updated user_ladda for {user_id}")
        else:
            # New user → insert
            insert_data = {
                "line_user_id": user_id,
                "display_name": display_name or f"User_{user_id[:8]}",
                "created_at": now,
                "updated_at": now,
            }
            supabase_client.table(TABLE) \
                .insert(insert_data) \
                .execute()
            logger.info(f"🆕 Registered new user_ladda: {user_id} ({display_name or 'no name'})")

        return True

    except Exception as e:
        logger.error(f"Error in register_user_ladda for {user_id}: {e}", exc_info=True)
        return False


async def ensure_user_exists(user_id: str) -> bool:
    """
    Ensure user exists in user_ladda(LINE,FACE) table.
    Fetches LINE profile for display_name if new LINE user.
    """
    try:
        # For LINE users, fetch profile to get display_name
        display_name = None
        if not user_id.startswith("fb:"):
            profile = await get_line_profile(user_id)
            if profile:
                display_name = profile.get("displayName")

        return await register_user_ladda(user_id, display_name)

    except Exception as e:
        logger.error(f"Error ensuring user exists {user_id}: {e}", exc_info=True)
        return False
