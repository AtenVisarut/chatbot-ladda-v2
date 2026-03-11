"""
User Service
Handles user profile tracking via user_ladda(LINE,FACE) table only.
"""

import logging
from typing import Optional, Dict
from datetime import datetime, timezone
import httpx
from app.dependencies import supabase_client
from app.config import LINE_CHANNEL_ACCESS_TOKEN, FB_PAGE_ACCESS_TOKEN

logger = logging.getLogger(__name__)

LINE_PROFILE_API = "https://api.line.me/v2/bot/profile/{user_id}"
FB_GRAPH_API = "https://graph.facebook.com/v21.0/{psid}"

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


async def get_facebook_profile(psid: str) -> Optional[Dict]:
    """
    Fetch user profile from Facebook Graph API

    Returns:
        dict with keys: first_name, last_name, profile_pic
        None if failed
    """
    if not FB_PAGE_ACCESS_TOKEN:
        return None
    try:
        params = {
            "fields": "first_name,last_name,profile_pic",
            "access_token": FB_PAGE_ACCESS_TOKEN,
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(
                FB_GRAPH_API.format(psid=psid),
                params=params,
                timeout=10.0,
            )

        if response.status_code == 200:
            profile = response.json()
            name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
            logger.info(f"Fetched FB profile for {psid}: {name}")
            return profile
        else:
            logger.warning(f"Failed to fetch FB profile: {response.status_code}")
            return None

    except Exception as e:
        logger.error(f"Error fetching FB profile for {psid}: {e}")
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


async def refresh_display_name(user_id: str) -> Optional[str]:
    """Re-fetch profile and update display_name for users with fallback names (User_xxx)."""
    try:
        display_name = None
        if user_id.startswith("fb:"):
            psid = user_id.replace("fb:", "", 1)
            profile = await get_facebook_profile(psid)
            if profile:
                display_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
        else:
            profile = await get_line_profile(user_id)
            if profile:
                display_name = profile.get("displayName")

        if display_name and supabase_client:
            supabase_client.table(TABLE) \
                .update({"display_name": display_name}) \
                .eq("line_user_id", user_id) \
                .execute()
            logger.info(f"Refreshed display_name for {user_id[:12]}... → {display_name}")

        return display_name
    except Exception as e:
        logger.error(f"Error refreshing display_name for {user_id}: {e}")
        return None


async def ensure_user_exists(user_id: str) -> bool:
    """
    Ensure user exists in user_ladda(LINE,FACE) table.
    Fetches LINE/Facebook profile for display_name.
    """
    try:
        display_name = None
        if user_id.startswith("fb:"):
            # Facebook user — fetch profile via Graph API
            psid = user_id.replace("fb:", "", 1)
            profile = await get_facebook_profile(psid)
            if profile:
                display_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
        else:
            # LINE user — fetch profile via LINE API
            profile = await get_line_profile(user_id)
            if profile:
                display_name = profile.get("displayName")

        return await register_user_ladda(user_id, display_name)

    except Exception as e:
        logger.error(f"Error ensuring user exists {user_id}: {e}", exc_info=True)
        return False
