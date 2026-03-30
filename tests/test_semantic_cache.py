"""Unit tests for Semantic Cache — 9 test cases."""
import asyncio
import time
import math
import pytest
from unittest.mock import patch


# Helper: create a fake embedding vector
def _make_embedding(seed: float, dims: int = 1536) -> list:
    """Create a deterministic embedding vector from seed."""
    import random
    rng = random.Random(seed)
    vec = [rng.gauss(0, 1) for _ in range(dims)]
    mag = math.sqrt(sum(x * x for x in vec))
    return [x / mag for x in vec]  # normalize


# Similar embedding (rotated slightly)
def _make_similar_embedding(base: list, similarity: float = 0.95) -> list:
    """Create a vector with approximately `similarity` cosine to `base`."""
    import random
    rng = random.Random(42)
    noise = [rng.gauss(0, 1) for _ in range(len(base))]
    mag_noise = math.sqrt(sum(x * x for x in noise))
    noise = [x / mag_noise for x in noise]

    # blend: sim * base + sqrt(1-sim^2) * noise
    blend_factor = math.sqrt(1 - similarity * similarity)
    result = [similarity * b + blend_factor * n for b, n in zip(base, noise)]
    mag = math.sqrt(sum(x * x for x in result))
    return [x / mag for x in result]


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear semantic cache before each test."""
    from app.services.semantic_cache import clear_semantic_cache
    clear_semantic_cache()
    yield
    clear_semantic_cache()


@pytest.mark.asyncio
async def test_exact_same_query():
    """Exact same embedding → similarity = 1.0 → hit."""
    from app.services.semantic_cache import store_semantic_cache, search_semantic_cache

    emb = _make_embedding(1.0)
    await store_semantic_cache("เพลี้ยไฟทุเรียน", emb, "ใช้อิมิดาโกลด์ค่ะ", "ทุเรียน")

    result = await search_semantic_cache(emb, "ทุเรียน")
    assert result is not None
    assert result["similarity"] > 0.99
    assert "อิมิดาโกลด์" in result["response"]


@pytest.mark.asyncio
async def test_similar_query_same_plant():
    """Similar embedding (sim=0.95) + same plant → hit."""
    from app.services.semantic_cache import store_semantic_cache, search_semantic_cache

    emb_original = _make_embedding(2.0)
    emb_similar = _make_similar_embedding(emb_original, 0.95)

    await store_semantic_cache("เพลี้ยไฟทุเรียน ใช้ยาอะไร", emb_original, "แนะนำอิมิดาโกลด์ค่ะ", "ทุเรียน")

    result = await search_semantic_cache(emb_similar, "ทุเรียน")
    assert result is not None
    assert result["similarity"] >= 0.93


@pytest.mark.asyncio
async def test_similar_query_different_plant():
    """Similar embedding but different plant → miss (Layer 2 protection)."""
    from app.services.semantic_cache import store_semantic_cache, search_semantic_cache

    emb_original = _make_embedding(3.0)
    emb_similar = _make_similar_embedding(emb_original, 0.95)

    await store_semantic_cache("เพลี้ยไฟทุเรียน", emb_original, "ใช้อิมิดาโกลด์ค่ะ", "ทุเรียน")

    # Different plant: มะม่วง ≠ ทุเรียน → must miss
    result = await search_semantic_cache(emb_similar, "มะม่วง")
    assert result is None


@pytest.mark.asyncio
async def test_below_threshold():
    """Similarity below threshold (0.80 < 0.93) → miss."""
    from app.services.semantic_cache import store_semantic_cache, search_semantic_cache

    emb_original = _make_embedding(4.0)
    emb_different = _make_similar_embedding(emb_original, 0.80)

    await store_semantic_cache("เพลี้ยไฟทุเรียน", emb_original, "ใช้อิมิดาโกลด์ค่ะ", "ทุเรียน")

    result = await search_semantic_cache(emb_different, "ทุเรียน")
    assert result is None


@pytest.mark.asyncio
async def test_expired_entry():
    """Expired entry (TTL passed) → miss (Layer 3 protection)."""
    from app.services.semantic_cache import store_semantic_cache, search_semantic_cache, _semantic_cache

    emb = _make_embedding(5.0)
    await store_semantic_cache("เพลี้ยไฟทุเรียน", emb, "ใช้อิมิดาโกลด์ค่ะ", "ทุเรียน")

    # Manually expire the entry
    with patch("app.services.semantic_cache.SEMANTIC_CACHE_TTL", 0):
        _semantic_cache[0]["created_at"] = time.time() - 10
        result = await search_semantic_cache(emb, "ทุเรียน")
        assert result is None


@pytest.mark.asyncio
async def test_store_and_search():
    """Store multiple entries, search returns best match."""
    from app.services.semantic_cache import store_semantic_cache, search_semantic_cache

    emb1 = _make_embedding(6.0)
    emb2 = _make_embedding(7.0)
    emb3 = _make_embedding(8.0)

    await store_semantic_cache("เพลี้ยไฟทุเรียน", emb1, "answer1", "ทุเรียน")
    await store_semantic_cache("หนอนกอข้าว", emb2, "answer2", "ข้าว")
    await store_semantic_cache("ราสีชมพูทุเรียน", emb3, "answer3", "ทุเรียน")

    # Search with emb1 → should find answer1
    result = await search_semantic_cache(emb1, "ทุเรียน")
    assert result is not None
    assert result["response"] == "answer1"


@pytest.mark.asyncio
async def test_eviction():
    """Cache evicts oldest entries when exceeding MAX_ENTRIES."""
    from app.services.semantic_cache import store_semantic_cache, _semantic_cache

    with patch("app.services.semantic_cache.SEMANTIC_CACHE_MAX_ENTRIES", 5):
        for i in range(8):
            emb = _make_embedding(100.0 + i)
            await store_semantic_cache(f"query_{i}", emb, f"answer_{i}", "ทุเรียน")

        assert len(_semantic_cache) <= 5


@pytest.mark.asyncio
async def test_empty_cache():
    """Empty cache → always miss."""
    from app.services.semantic_cache import search_semantic_cache

    emb = _make_embedding(9.0)
    result = await search_semantic_cache(emb, "ทุเรียน")
    assert result is None


@pytest.mark.asyncio
async def test_no_plant_both_empty():
    """Both query and cache have no plant → hit (general query match)."""
    from app.services.semantic_cache import store_semantic_cache, search_semantic_cache

    emb = _make_embedding(10.0)
    await store_semantic_cache("สวัสดีค่ะ", emb, "สวัสดีค่ะ ยินดีต้อนรับ", "")

    result = await search_semantic_cache(emb, "")
    assert result is not None
    assert result["similarity"] > 0.99
