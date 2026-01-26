"""
Test Redis Cache Module

วิธีรัน:
    # ไม่มี Redis (test fallback)
    python -m pytest tests/test_redis_cache.py -v

    # มี Redis (set environment variables ก่อน)
    export REDIS_URL=redis://localhost:6379
    python -m pytest tests/test_redis_cache.py -v

    # หรือใช้ Upstash
    export UPSTASH_REDIS_REST_URL=https://xxx.upstash.io
    export UPSTASH_REDIS_REST_TOKEN=xxx
    python -m pytest tests/test_redis_cache.py -v
"""
import os
import sys
import time
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_redis_connection():
    """Test Redis connection status"""
    from app.services.redis_cache import is_redis_available, get_redis_stats

    stats = get_redis_stats()
    print(f"\n📊 Redis Stats: {stats}")

    if is_redis_available():
        print("✅ Redis is connected")
        assert stats["status"] == "connected"
    else:
        print("⚠️ Redis not available - using memory cache fallback")
        assert stats["status"] in ["not_connected", "error"]


def test_rate_limit_redis():
    """Test rate limiting with Redis"""
    from app.services.redis_cache import (
        is_redis_available,
        check_rate_limit_redis,
        clear_user_rate_limit
    )

    if not is_redis_available():
        print("⏭️ Skipping Redis rate limit test (Redis not available)")
        return

    test_user = "test_user_rate_limit"

    # Clear any existing data
    clear_user_rate_limit(test_user)

    # Test rate limit (limit=3 for quick testing)
    print("\n🧪 Testing rate limit (limit=3, window=5s)")

    # First 3 requests should pass
    for i in range(3):
        allowed, remaining = check_rate_limit_redis(test_user, limit=3, window=5)
        print(f"  Request {i+1}: allowed={allowed}, remaining={remaining}")
        assert allowed is True
        assert remaining == 3 - (i + 1)

    # 4th request should fail
    allowed, remaining = check_rate_limit_redis(test_user, limit=3, window=5)
    print(f"  Request 4: allowed={allowed}, remaining={remaining}")
    assert allowed is False
    assert remaining == 0

    # Wait for window to expire
    print("  Waiting 6s for window to expire...")
    time.sleep(6)

    # Should be allowed again
    allowed, remaining = check_rate_limit_redis(test_user, limit=3, window=5)
    print(f"  Request after wait: allowed={allowed}, remaining={remaining}")
    assert allowed is True

    # Cleanup
    clear_user_rate_limit(test_user)
    print("✅ Rate limit test passed")


def test_image_cooldown_redis():
    """Test image cooldown with Redis"""
    from app.services.redis_cache import (
        is_redis_available,
        check_image_cooldown_redis,
        clear_user_cooldown
    )

    if not is_redis_available():
        print("⏭️ Skipping Redis cooldown test (Redis not available)")
        return

    test_user = "test_user_cooldown"

    # Clear any existing data
    clear_user_cooldown(test_user)

    print("\n🧪 Testing image cooldown (cooldown=3s)")

    # First request should pass
    allowed, remaining = check_image_cooldown_redis(test_user, cooldown=3)
    print(f"  Request 1: allowed={allowed}, remaining={remaining}")
    assert allowed is True
    assert remaining == 0

    # Second request immediately should fail
    allowed, remaining = check_image_cooldown_redis(test_user, cooldown=3)
    print(f"  Request 2 (immediate): allowed={allowed}, remaining={remaining}")
    assert allowed is False
    assert remaining > 0

    # Wait for cooldown
    print("  Waiting 4s for cooldown...")
    time.sleep(4)

    # Should be allowed again
    allowed, remaining = check_image_cooldown_redis(test_user, cooldown=3)
    print(f"  Request after wait: allowed={allowed}, remaining={remaining}")
    assert allowed is True

    # Cleanup
    clear_user_cooldown(test_user)
    print("✅ Image cooldown test passed")


def test_concurrent_analysis_slot():
    """Test concurrent analysis slot limiter"""
    from app.services.redis_cache import (
        is_redis_available,
        acquire_analysis_slot,
        release_analysis_slot,
        get_analysis_queue_status,
        reset_analysis_counter
    )

    if not is_redis_available():
        print("⏭️ Skipping concurrent slot test (Redis not available)")
        return

    # Reset counter
    reset_analysis_counter()

    print("\n🧪 Testing concurrent analysis slots (max=3)")

    # Acquire 3 slots
    for i in range(3):
        acquired = acquire_analysis_slot(max_concurrent=3)
        status = get_analysis_queue_status(max_concurrent=3)
        print(f"  Slot {i+1}: acquired={acquired}, current={status.get('current', 0)}")
        assert acquired is True

    # 4th slot should fail
    acquired = acquire_analysis_slot(max_concurrent=3)
    print(f"  Slot 4: acquired={acquired} (should be False)")
    assert acquired is False

    # Release one slot
    release_analysis_slot()
    status = get_analysis_queue_status(max_concurrent=3)
    print(f"  After release: current={status.get('current', 0)}")

    # Should be able to acquire again
    acquired = acquire_analysis_slot(max_concurrent=3)
    print(f"  After release, acquire: acquired={acquired}")
    assert acquired is True

    # Cleanup
    reset_analysis_counter()
    print("✅ Concurrent analysis slot test passed")


def test_rate_limiter_module():
    """Test rate_limiter module with automatic backend selection"""
    from app.utils.rate_limiter import (
        get_cache_backend_info,
        get_rate_limit_status
    )

    print("\n🧪 Testing rate_limiter module")

    # Check backend info
    backend_info = get_cache_backend_info()
    print(f"  Backend: {backend_info.get('backend', 'unknown')}")
    print(f"  Status: {backend_info.get('status', 'unknown')}")

    # Check rate limit status
    status = get_rate_limit_status("test_user_status")
    print(f"  Rate limit status: {status}")

    assert "remaining" in status
    assert "limit" in status
    print("✅ Rate limiter module test passed")


async def test_async_rate_limit():
    """Test async rate limit function"""
    from app.utils.rate_limiter import check_user_rate_limit, check_image_cooldown

    print("\n🧪 Testing async rate limit functions")

    test_user = "test_async_user"

    # Test rate limit
    allowed = await check_user_rate_limit(test_user)
    print(f"  Rate limit check: allowed={allowed}")
    assert isinstance(allowed, bool)

    # Test image cooldown
    allowed, remaining = await check_image_cooldown(test_user, cooldown=1)
    print(f"  Image cooldown: allowed={allowed}, remaining={remaining}")
    assert isinstance(allowed, bool)
    assert isinstance(remaining, int)

    print("✅ Async rate limit test passed")


def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("🧪 Redis Cache Tests")
    print("=" * 60)

    test_redis_connection()
    test_rate_limit_redis()
    test_image_cooldown_redis()
    test_concurrent_analysis_slot()
    test_rate_limiter_module()

    # Run async test
    asyncio.run(test_async_rate_limit())

    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
