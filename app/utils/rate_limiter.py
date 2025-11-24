import time
import logging
from typing import List
from app.config import USER_RATE_LIMIT, USER_RATE_WINDOW
from app.services.cache import get_from_cache, set_to_cache

logger = logging.getLogger(__name__)

async def check_user_rate_limit(user_id: str) -> bool:
    """Check if user exceeded rate limit using Supabase Cache"""
    current_time = time.time()
    cache_key = f"ratelimit:{user_id}"
    
    # Get current timestamps from cache
    # Note: We use "ratelimit" as the cache type prefix
    timestamps = await get_from_cache("ratelimit", user_id)
    
    if not timestamps:
        timestamps = []
    
    # Remove old timestamps outside the window
    valid_timestamps = [
        ts for ts in timestamps
        if current_time - ts < USER_RATE_WINDOW
    ]
    
    # Check if exceeded limit
    if len(valid_timestamps) >= USER_RATE_LIMIT:
        logger.warning(f"Rate limit exceeded for user {user_id[:8]}...")
        return False
    
    # Add current request
    valid_timestamps.append(current_time)
    
    # Save back to cache with TTL = Window size
    # This ensures data automatically expires if user stops sending requests
    await set_to_cache("ratelimit", user_id, valid_timestamps, ttl=USER_RATE_WINDOW)
    
    return True

async def cleanup_rate_limit_data():
    """
    Clean up old rate limit data.
    With Supabase Cache, this is handled automatically by TTL and cleanup_expired_cache.
    Kept for compatibility with existing imports.
    """
    pass
