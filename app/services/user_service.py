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
from app.utils.async_db import aexecute

logger = logging.getLogger(__name__)

LINE_PROFILE_API = "https://api.line.me/v2/bot/profile/{user_id}"
FB_GRAPH_API = "https://graph.facebook.com/v21.0/{psid}"

TABLE = 'user_ladda(LINE,FACE)'

# Cache FB profile failures to avoid spamming Graph API every poll cycle
# Key: psid, Value: timestamp of last failure
_fb_profile_fail_cache: Dict[str, float] = {}
_FB_FAIL_CACHE_TTL = 3600  # Don't retry for 1 hour after failure


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


async def get_facebook_profile(psid: str, skip_cache: bool = False) -> Optional[Dict]:
    """
    Fetch user profile from Facebook Graph API.

    Uses failure cache to avoid spamming Graph API on repeated failures
    (e.g. missing permissions).

    Returns:
        dict with keys: first_name, last_name, profile_pic
        None if failed
    """
    if not FB_PAGE_ACCESS_TOKEN:
        logger.warning("FB_PAGE_ACCESS_TOKEN is empty — cannot fetch FB profile")
        return None

    # Check failure cache (skip if called from debug endpoint)
    if not skip_cache and psid in _fb_profile_fail_cache:
        import time
        age = time.time() - _fb_profile_fail_cache[psid]
        if age < _FB_FAIL_CACHE_TTL:
            logger.debug(f"Skipping FB profile for {psid} — cached failure ({int(age)}s ago)")
            return None
        else:
            del _fb_profile_fail_cache[psid]

    try:
        params = {
            "fields": "first_name,last_name,profile_pic",
            "access_token": FB_PAGE_ACCESS_TOKEN,
        }
        url = FB_GRAPH_API.format(psid=psid)
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)

        if response.status_code == 200:
            profile = response.json()
            name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
            logger.info(f"Fetched FB profile for {psid}: {name}")
            # Clear failure cache on success
            _fb_profile_fail_cache.pop(psid, None)
            return profile
        else:
            import time
            _fb_profile_fail_cache[psid] = time.time()
            logger.warning(
                f"Failed to fetch FB profile for {psid}: "
                f"status={response.status_code} body={response.text[:200]}"
            )
            return None

    except Exception as e:
        import time
        _fb_profile_fail_cache[psid] = time.time()
        logger.error(f"Error fetching FB profile for {psid}: {e}")
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
        result = await aexecute(supabase_client.table(TABLE) \
            .select('id, line_user_id') \
            .eq('line_user_id', user_id))

        now = datetime.now(timezone.utc).isoformat()

        if result.data and len(result.data) > 0:
            # Existing user → update updated_at (+ display_name if provided)
            update_data = {"updated_at": now}
            if display_name:
                update_data["display_name"] = display_name

            await aexecute(supabase_client.table(TABLE) \
                .update(update_data) \
                .eq('line_user_id', user_id))
            logger.debug(f"✓ Updated user_ladda for {user_id}")
        else:
            # New user → insert
            # Better fallback name for FB users
            if not display_name:
                if user_id.startswith("fb:"):
                    fallback = f"FB User #{user_id[-4:]}"
                else:
                    fallback = f"User_{user_id[:8]}"
            else:
                fallback = display_name

            insert_data = {
                "line_user_id": user_id,
                "display_name": fallback,
                "created_at": now,
                "updated_at": now,
            }
            await aexecute(supabase_client.table(TABLE) \
                .insert(insert_data))
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
            await aexecute(supabase_client.table(TABLE) \
                .update({"display_name": display_name}) \
                .eq("line_user_id", user_id))
            logger.info(f"Refreshed display_name for {user_id[:12]}... → {display_name}")

        return display_name
    except Exception as e:
        logger.error(f"Error refreshing display_name for {user_id}: {e}")
        return None


# In-memory cache of known user IDs — skip DB check for repeat messages
_known_users: set = set()


async def ensure_user_exists(user_id: str) -> bool:
    """
    Ensure user exists in user_ladda(LINE,FACE) table.
    Fetches LINE/Facebook profile for display_name.
    Uses in-memory cache to skip DB for known users.
    For FB users with fallback names, retries fetching real name.
    """
    if user_id in _known_users:
        # FB users with fallback name → retry fetching real name
        if user_id.startswith("fb:"):
            try:
                if supabase_client:
                    result = await aexecute(supabase_client.table(TABLE)
                        .select('display_name')
                        .eq('line_user_id', user_id))
                    if result.data and result.data[0].get('display_name', '').startswith('FB User'):
                        await refresh_display_name(user_id)
            except Exception:
                pass
        return True

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

        success = await register_user_ladda(user_id, display_name)
        if success:
            _known_users.add(user_id)
        return success

    except Exception as e:
        logger.error(f"Error ensuring user exists {user_id}: {e}", exc_info=True)
        return False
