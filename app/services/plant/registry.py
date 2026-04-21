"""
PlantRegistry — DB-driven plant-name registry with longest-first matching.

Loads plant names from `products3.applicable_crops` at startup.
Auto-refreshes every 15 minutes so newly-added plants appear without
a service restart.

Solves the substring-match bug where "ข้าวโพด" was matching "ข้าว" first
simply because "ข้าว" appeared earlier in a hardcoded plants list.

Usage:
    registry = PlantRegistry.get_instance()
    await registry.load_from_db(supabase_client)
    plant = registry.extract("ใช้ยาอะไรฆ่าหญ้าในข้าวโพด")  # → "ข้าวโพด"
"""

from __future__ import annotations

import logging
import re
import time
from typing import Dict, List, Optional, Set

from app.utils.async_db import aexecute

logger = logging.getLogger(__name__)


# =============================================================================
# Static data: typo corrections + synonyms that DB won't teach us
# =============================================================================

# Common farmer typos/misspellings observed in the wild (canonical → list of typos)
# The registry will match any typo but return the canonical form.
_TYPO_FIXES: Dict[str, List[str]] = {
    "ทุเรียน": ["ทุเรีย", "ทุลเรียน", "ทุเรี่ยน"],
    "มันสำปะหลัง": ["มันสัม", "มันสัมปะหลัง", "มันสำปะหรัง"],
    "ยางพารา": ["ยางพา"],
    "ลำไย": ["ลำใย"],
    "ลิ้นจี่": ["ลิ้นจี"],
}

# Regional / colloquial synonyms → canonical
_SYNONYMS: Dict[str, str] = {
    "นาข้าว": "ข้าว",
    "ข้าวนา": "ข้าว",
    "ต้นทุเรียน": "ทุเรียน",
    "สวนทุเรียน": "ทุเรียน",
    "ไร่ข้าวโพด": "ข้าวโพด",
    "ไร่อ้อย": "อ้อย",
    "สวนลำไย": "ลำไย",
    "สวนมะม่วง": "มะม่วง",
    "สวนส้ม": "ส้ม",
}

# Plants that might appear in free-text user queries but aren't in DB
# (we still want to detect them so we can respond "no product for this crop")
_KNOWN_EXTRA_PLANTS: Set[str] = {
    "เงาะ", "มังคุด", "มะละกอ", "แตงโม", "ฟักทอง", "องุ่น",
    "ลองกอง", "กาแฟ", "สับปะรด", "ถั่ว", "ฝรั่ง", "ชมพู่",
    "ส้มโอ", "มะนาว", "กล้วย", "ข้าวเหนียว", "ไม้ผล",
    "มะม่วงหิมพานต์", "ปาล์ม",
}


# =============================================================================
# Registry
# =============================================================================


class PlantRegistry:
    """Singleton registry of plant names, loaded from DB."""

    _instance: Optional["PlantRegistry"] = None
    _AUTO_REFRESH_INTERVAL = 900  # 15 minutes

    def __init__(self):
        # Canonical plant name → set of typo/synonym aliases that also match it
        self._canonical_to_aliases: Dict[str, List[str]] = {}
        # Flat sorted list (longest first) used for matching
        self._sorted_names: List[str] = []
        # Lookup from any-name (alias/typo/canonical) → canonical
        self._lookup: Dict[str, str] = {}
        self._loaded: bool = False
        self._load_time: float = 0.0

    @classmethod
    def get_instance(cls) -> "PlantRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def loaded(self) -> bool:
        return self._loaded

    # -------------------------------------------------------------------------
    # Loading
    # -------------------------------------------------------------------------

    async def load_from_db(self, supabase_client) -> bool:
        """Load plant names from products3.applicable_crops."""
        plants: Set[str] = set()
        try:
            if supabase_client is None:
                raise RuntimeError("supabase_client is None")
            from app.config import PRODUCT_TABLE
            result = await aexecute(
                supabase_client.table(PRODUCT_TABLE).select("applicable_crops")
            )
            if not result.data:
                raise RuntimeError("No products returned")
            for row in result.data:
                crops_raw = row.get("applicable_crops") or ""
                for p in self._split_crops(crops_raw):
                    if len(p) >= 2:
                        plants.add(p)
            logger.info(
                f"PlantRegistry: loaded {len(plants)} distinct plants from DB"
            )
        except Exception as e:
            logger.warning(f"PlantRegistry: DB load failed ({e}), using fallback")
            plants = set(_KNOWN_EXTRA_PLANTS)

        # Merge DB plants + known extras
        plants.update(_KNOWN_EXTRA_PLANTS)

        # Build canonical map with typo/synonym aliases
        self._build_index(plants)
        self._loaded = True
        self._load_time = time.time()
        logger.info(
            f"PlantRegistry: indexed {len(self._sorted_names)} entries "
            f"({len(self._canonical_to_aliases)} canonicals)"
        )
        return True

    @staticmethod
    def _split_crops(text: str) -> List[str]:
        # DB is inconsistent — split on , / newline / space+space
        return [p.strip() for p in re.split(r"[,/\n]+", text) if p.strip()]

    def _build_index(self, db_plants: Set[str]) -> None:
        self._canonical_to_aliases = {}
        self._lookup = {}

        all_canonicals = set(db_plants)
        # Canonicalize DB typos too: if both "ลำไย" and "ลำใย" exist in DB,
        # treat ลำใย as alias of ลำไย
        for canonical, typos in _TYPO_FIXES.items():
            all_canonicals.add(canonical)

        # Build lookup map: self
        for c in all_canonicals:
            self._lookup[c.lower()] = c
            self._canonical_to_aliases.setdefault(c, [c])

        # Typos
        for canonical, typos in _TYPO_FIXES.items():
            for t in typos:
                self._lookup[t.lower()] = canonical
                if t not in self._canonical_to_aliases[canonical]:
                    self._canonical_to_aliases[canonical].append(t)

        # Synonyms
        for syn, canonical in _SYNONYMS.items():
            # Ensure canonical exists
            self._canonical_to_aliases.setdefault(canonical, [canonical])
            self._lookup[syn.lower()] = canonical
            if syn not in self._canonical_to_aliases[canonical]:
                self._canonical_to_aliases[canonical].append(syn)

        # Sort all match-strings by length desc — CRITICAL for longest-first match
        all_match_strings = list(self._lookup.keys())
        all_match_strings.sort(key=len, reverse=True)
        self._sorted_names = all_match_strings

    # -------------------------------------------------------------------------
    # Refresh
    # -------------------------------------------------------------------------

    async def refresh_if_stale(self, supabase_client) -> bool:
        """Reload from DB if older than _AUTO_REFRESH_INTERVAL."""
        if not self._loaded:
            return await self.load_from_db(supabase_client)
        if time.time() - self._load_time < self._AUTO_REFRESH_INTERVAL:
            return False
        logger.info("PlantRegistry: auto-refreshing from DB")
        prev = len(self._sorted_names)
        await self.load_from_db(supabase_client)
        curr = len(self._sorted_names)
        if curr != prev:
            logger.info(f"PlantRegistry: refreshed {prev} → {curr} entries")
        return True

    # -------------------------------------------------------------------------
    # Extraction
    # -------------------------------------------------------------------------

    def extract(self, question: str) -> Optional[str]:
        """
        Extract plant name from question. Longest-match wins so compound
        names (ข้าวโพด / ปาล์มน้ำมัน / ส้มโอ) are preferred over shorter
        substrings (ข้าว / ปาล์ม / ส้ม).
        """
        if not self._loaded or not question:
            return None
        q = question.lower()
        for name in self._sorted_names:
            if name in q:
                return self._lookup[name]
        return None

    def get_canonical_list(self) -> List[str]:
        return sorted(self._canonical_to_aliases.keys())

    def get_aliases(self, canonical: str) -> List[str]:
        return list(self._canonical_to_aliases.get(canonical, []))


# -----------------------------------------------------------------------------
# Convenience accessor
# -----------------------------------------------------------------------------


def extract_plant(question: str) -> Optional[str]:
    """Sync convenience — assumes registry already loaded at app startup."""
    return PlantRegistry.get_instance().extract(question)
