"""
User Service
Handles LINE user profile tracking and database operations
"""

import logging
from typing import Optional, Dict
import httpx
from app.services.services import supabase_client
from app.config import LINE_CHANNEL_ACCESS_TOKEN

logger = logging.getLogger(__name__)

LINE_PROFILE_API = "https://api.line.me/v2/bot/profile/{user_id}"


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
    """Get user from database"""
    try:
        if not supabase_client:
            return None
            
        result = supabase_client.table('users')\
            .select('*')\
            .eq('line_user_id', user_id)\
            .execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        return None
        
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}")
        return None


async def upsert_user(user_id: str, profile_data: Dict) -> bool:
    """
    Create or update user record (simplified for registration schema)
    
    Args:
        user_id: LINE user ID
        profile_data: Profile data from LINE API
    """
    try:
        if not supabase_client:
            logger.error("Supabase client not available")
            return False
        
        # Simple upsert with only columns that exist in the table
        data = {
            "line_user_id": user_id,
            "display_name": profile_data.get('displayName', 'Unknown')
        }
        
        supabase_client.table('users').upsert(data).execute()
        logger.info(f"✓ Upserted user {user_id}: {data['display_name']}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error upserting user {user_id}: {e}", exc_info=True)
        return False


async def update_last_seen(user_id: str) -> bool:
    """Update user's last interaction (simplified)"""
    try:
        if not supabase_client:
            return False
        
        existing_user = await get_user(user_id)
        if not existing_user:
            logger.warning(f"User {user_id} not found for update")
            return False
        
        # Just verify user exists
        logger.debug(f"✓ Verified user {user_id} exists")
        return True
        
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {e}")
        return False


async def is_registration_completed(user_id: str) -> bool:
    """
    Check if user has completed registration

    Args:
        user_id: LINE user ID

    Returns:
        True if registration_completed is True, False otherwise
    """
    try:
        user = await get_user(user_id)
        if user and user.get('registration_completed') == True:
            return True
        return False
    except Exception as e:
        logger.error(f"Error checking registration status for {user_id}: {e}")
        return False


async def ensure_user_exists(user_id: str) -> bool:
    """
    Ensure user exists in database
    Fetches profile from LINE if new user
    
    Args:
        user_id: LINE user ID
    
    Returns:
        True if user exists/created, False if failed
    """
    try:
        # Check if user exists
        user = await get_user(user_id)
        
        if user:
            # User exists
            await update_last_seen(user_id)
            return True
        
        # New user - fetch profile from LINE
        logger.info(f"🆕 New user detected: {user_id}")
        profile = await get_line_profile(user_id)
        
        if profile:
            # Create user with profile data
            success = await upsert_user(user_id, profile)
            if success:
                logger.info(f"✅ User {user_id} registered successfully")
            return success
        else:
            # Profile fetch failed, create with minimal data
            logger.warning(f"Failed to fetch profile for {user_id}, creating with minimal data")
            minimal_profile = {
                "displayName": f"User_{user_id[:8]}",
                "pictureUrl": None,
                "statusMessage": None
            }
            return await upsert_user(user_id, minimal_profile)
        
    except Exception as e:
        logger.error(f"Error ensuring user exists {user_id}: {e}", exc_info=True)
        return False
