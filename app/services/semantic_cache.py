"""
Semantic Cache — In-Memory with 3-Layer Protection
ค้นหา cached response ด้วย cosine similarity แทน exact match
ป้องกัน false match ด้วย: similarity ≥ threshold + plant_type ตรง + TTL
"""
import logging
import math
import time
import threading
from typing import List, Dict, Optional

from app.config import (
    SEMANTIC_CACHE_ENABLED,
    SEMANTIC_CACHE_THRESHOLD,
    SEMANTIC_CACHE_TTL,
    SEMANTIC_CACHE_MAX_ENTRIES,
)

logger = logging.getLogger(__name__)

_semantic_cache: List[Dict] = []
_lock = threading.Lock()


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


async def search_semantic_cache(
    query_embedding: List[float],
    plant_type: str = "",
    threshold: Optional[float] = None,
) -> Optional[Dict]:
    """ค้นหา cached response ที่ความหมายคล้ายกัน (3-layer protection)."""
    if not SEMANTIC_CACHE_ENABLED or not query_embedding:
        return None

    if threshold is None:
        threshold = SEMANTIC_CACHE_THRESHOLD

    now = time.time()
    best_match = None
    best_sim = 0.0

    with _lock:
        for entry in _semantic_cache:
            # Layer 3: TTL check
            if now - entry["created_at"] > SEMANTIC_CACHE_TTL:
                continue

            # Layer 2: plant_type check
            entry_plant = entry.get("plant_type", "")
            if plant_type and entry_plant and plant_type != entry_plant:
                continue
            if plant_type and not entry_plant:
                continue

            # Layer 1: similarity check
            sim = _cosine_similarity(query_embedding, entry["embedding"])
            if sim >= threshold and sim > best_sim:
                best_sim = sim
                best_match = entry

    if best_match:
        logger.info(f"✓ Semantic cache hit (sim={best_sim:.3f}, plant={plant_type or 'none'})")
        return {
            "response": best_match["response"],
            "similarity": best_sim,
            "query_text": best_match["query_text"],
            "plant_type": best_match.get("plant_type", ""),
        }

    logger.info(f"⏭️ Semantic cache miss (best_sim={best_sim:.3f} < {threshold}, plant={plant_type or 'none'})")
    return None


async def store_semantic_cache(
    query_text: str,
    query_embedding: List[float],
    response: str,
    plant_type: str = "",
) -> None:
    """เก็บ response + embedding ไว้ใน in-memory cache."""
    if not SEMANTIC_CACHE_ENABLED or not query_embedding:
        return

    entry = {
        "query_text": query_text,
        "embedding": query_embedding,
        "response": response,
        "plant_type": plant_type,
        "created_at": time.time(),
    }

    with _lock:
        # Evict expired entries
        now = time.time()
        _semantic_cache[:] = [
            e for e in _semantic_cache
            if now - e["created_at"] <= SEMANTIC_CACHE_TTL
        ]

        # Evict oldest if full
        if len(_semantic_cache) >= SEMANTIC_CACHE_MAX_ENTRIES:
            _semantic_cache.sort(key=lambda e: e["created_at"])
            del _semantic_cache[:max(1, len(_semantic_cache) // 5)]

        _semantic_cache.append(entry)

    logger.info(f"✓ Semantic cache stored (plant={plant_type or 'none'}, entries={len(_semantic_cache)})")


def clear_semantic_cache() -> None:
    """ล้าง semantic cache ทั้งหมด (สำหรับ test)."""
    with _lock:
        _semantic_cache.clear()
