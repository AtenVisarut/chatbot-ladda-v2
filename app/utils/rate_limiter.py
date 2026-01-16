import time
import logging
from typing import List
from app.config import USER_RATE_LIMIT, USER_RATE_WINDOW
from app.services.cache import get_from_memory_cache, set_to_memory_cache

logger = logging.getLogger(__name__)


async def check_user_rate_limit(user_id: str) -> bool:
    """
    Check if user exceeded rate limit using In-Memory Cache (L1)
    
    ใช้ Memory Cache โดยตรงเพื่อความเร็ว (~0.1ms)
    ไม่ต้อง query Supabase ทุก request
    
    Algorithm: Sliding Window
    - เก็บ timestamps ของ requests ใน window
    - ถ้าเกิน limit → reject
    """
    current_time = time.time()
    cache_key = f"ratelimit:{user_id}"
    
    # Get current timestamps from L1 memory cache (fast!)
    timestamps = get_from_memory_cache(cache_key)
    
    if not timestamps:
        timestamps = []
    
    # Remove old timestamps outside the window
    valid_timestamps = [
        ts for ts in timestamps
        if current_time - ts < USER_RATE_WINDOW
    ]
    
    # Check if exceeded limit
    if len(valid_timestamps) >= USER_RATE_LIMIT:
        logger.warning(f"Rate limit exceeded for user {user_id[:8]}... ({len(valid_timestamps)}/{USER_RATE_LIMIT})")
        return False
    
    # Add current request
    valid_timestamps.append(current_time)
    
    # Save back to L1 memory cache with TTL = Window size
    set_to_memory_cache(cache_key, valid_timestamps, ttl=USER_RATE_WINDOW)
    
    return True


async def cleanup_rate_limit_data():
    """
    Clean up old rate limit data.
    
    With In-Memory Cache, this is handled automatically by TTL.
    Kept for compatibility with existing imports.
    """
    pass


def get_rate_limit_status(user_id: str) -> dict:
    """Get current rate limit status for a user"""
    current_time = time.time()
    cache_key = f"ratelimit:{user_id}"
    
    timestamps = get_from_memory_cache(cache_key)
    
    if not timestamps:
        return {
            "user_id": user_id[:8] + "...",
            "requests_in_window": 0,
            "limit": USER_RATE_LIMIT,
            "window_seconds": USER_RATE_WINDOW,
            "remaining": USER_RATE_LIMIT
        }
    
    valid_timestamps = [
        ts for ts in timestamps
        if current_time - ts < USER_RATE_WINDOW
    ]
    
    return {
        "user_id": user_id[:8] + "...",
        "requests_in_window": len(valid_timestamps),
        "limit": USER_RATE_LIMIT,
        "window_seconds": USER_RATE_WINDOW,
        "remaining": max(0, USER_RATE_LIMIT - len(valid_timestamps))
    }
