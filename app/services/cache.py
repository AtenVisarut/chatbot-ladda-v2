import time
import hashlib
import logging
import json
import base64
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from app.config import CACHE_TTL, PENDING_CONTEXT_TTL
from app.services.services import supabase_client

logger = logging.getLogger(__name__)

def get_image_hash(image_bytes: bytes) -> str:
    """Generate hash for image caching"""
    return hashlib.md5(image_bytes).hexdigest()

def get_cache_key(prefix: str, key: str) -> str:
    """Generate cache key with prefix"""
    return f"{prefix}:{key}"

async def get_from_cache(cache_type: str, key: str) -> Optional[Any]:
    """Get item from Supabase cache"""
    try:
        if not supabase_client:
            return None
            
        full_key = f"{cache_type}:{key}"
        
        # Query cache table
        result = supabase_client.table('cache')\
            .select('value, expires_at')\
            .eq('key', full_key)\
            .gt('expires_at', datetime.now(timezone.utc).isoformat())\
            .execute()
            
        if result.data:
            logger.info(f"✓ Cache hit: {full_key[:50]}")
            return result.data[0]['value']
            
        return None
    except Exception as e:
        logger.error(f"Cache get error: {e}")
        return None

async def set_to_cache(cache_type: str, key: str, data: Any, ttl: int = CACHE_TTL):
    """Set item to Supabase cache"""
    try:
        if not supabase_client:
            return
            
        full_key = f"{cache_type}:{key}"
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()
        
        # Upsert to cache table
        supabase_client.table('cache').upsert({
            'key': full_key,
            'value': data,
            'expires_at': expires_at
        }).execute()
        
        logger.info(f"✓ Cache set: {full_key[:50]}")
    except Exception as e:
        logger.error(f"Cache set error: {e}")

# ============================================================================
# Pending Context Helpers (Special handling for image bytes)
# ============================================================================

async def save_pending_context(user_id: str, context_data: Dict[str, Any]):
    """Save pending context to Supabase (handles bytes serialization)"""
    try:
        # Create a copy to modify
        data_to_save = context_data.copy()
        
        # Convert bytes to base64 string for JSON storage
        if "image_bytes" in data_to_save and isinstance(data_to_save["image_bytes"], bytes):
            data_to_save["image_bytes"] = base64.b64encode(data_to_save["image_bytes"]).decode('utf-8')
            data_to_save["_is_bytes"] = True
            
        await set_to_cache("context", user_id, data_to_save, ttl=PENDING_CONTEXT_TTL)
        
    except Exception as e:
        logger.error(f"Error saving pending context: {e}")

async def get_pending_context(user_id: str) -> Optional[Dict[str, Any]]:
    """Get pending context from Supabase (handles bytes deserialization)"""
    try:
        data = await get_from_cache("context", user_id)
        if not data:
            return None
            
        # Convert base64 string back to bytes
        if data.get("_is_bytes") and "image_bytes" in data:
            data["image_bytes"] = base64.b64decode(data["image_bytes"])
            
        return data
    except Exception as e:
        logger.error(f"Error getting pending context: {e}")
        return None

async def delete_pending_context(user_id: str):
    """Delete pending context"""
    try:
        if not supabase_client:
            return
        full_key = f"context:{user_id}"
        supabase_client.table('cache').delete().eq('key', full_key).execute()
    except Exception as e:
        logger.error(f"Error deleting context: {e}")

# ============================================================================
# Cleanup & Stats
# ============================================================================

async def cleanup_expired_cache():
    """Clean up expired cache entries in Supabase"""
    try:
        if not supabase_client:
            return
            
        # Delete rows where expires_at < now
        result = supabase_client.table('cache')\
            .delete()\
            .lt('expires_at', datetime.now(timezone.utc).isoformat())\
            .execute()
            
        if result.data:
            logger.info(f"Cache cleanup: removed {len(result.data)} expired entries")
    except Exception as e:
        logger.error(f"Cache cleanup error: {e}")

async def clear_all_caches():
    """Clear all cache entries"""
    try:
        if not supabase_client:
            return
        supabase_client.table('cache').delete().neq('key', '0').execute() # Delete all
        logger.info("All caches cleared from Supabase")
    except Exception as e:
        logger.error(f"Error clearing all caches: {e}")

async def get_cache_stats() -> dict:
    """Get cache statistics from Supabase"""
    try:
        if not supabase_client:
            return {"status": "Supabase not connected"}
            
        # Count total items
        result = supabase_client.table('cache').select('key', count='exact').execute()
        total = result.count if result.count is not None else 0
        
        return {
            "total_cache_items": total,
            "storage": "Supabase (Persistent)"
        }
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        return {"error": str(e)}
