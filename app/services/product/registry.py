"""
Product Registry — DB-driven product name registry with auto-generated Thai variants.

Loads product names from DB at startup, generates Thai typo variants automatically,
and provides matching (exact → diacritics-stripped → fuzzy) for user queries.

Usage:
    registry = ProductRegistry.get_instance()
    await registry.load_from_db(supabase_client)
    product = registry.extract_product_name("โทมาหอค ใช้ยังไง")  # → "โทมาฮอค"
"""

import logging
import re
import time
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from app.utils.async_db import aexecute

logger = logging.getLogger(__name__)

# Thai diacritics pattern (same as text_processing.py)
_THAI_DIACRITICS = re.compile(r'[\u0E48\u0E49\u0E4A\u0E4B\u0E47\u0E4C]')


def _strip_diacritics(text: str) -> str:
    return _THAI_DIACRITICS.sub('', text)


# Consonant swap pairs for auto-generating Thai typo variants
_CONSONANT_SWAPS = [
    ('ค', 'ก'), ('ท', 'ต'), ('ซ', 'ส'), ('ห', 'ฮ'),
    ('พ', 'ป'), ('บ', 'ป'), ('ฟ', 'ฝ'),
]


def _generate_thai_variants(name: str) -> List[str]:
    """
    Auto-generate common Thai typo variants for a product name.

    Rules:
    1. Consonant swaps: ค↔ก, ท↔ต, ซ↔ส, ห↔ฮ, พ↔ป, บ↔ป, ฟ↔ฝ
    2. Strip diacritics (่ ้ ๊ ๋ ็ ์)
    3. Remove hyphen
    4. Number variants: "โมเดิน 50" → "โมเดิน50", "โมเดิน"
    """
    variants = set()
    name_lower = name.lower()

    # Original
    variants.add(name_lower)

    # Rule 1: Consonant swaps — apply each swap independently
    for a, b in _CONSONANT_SWAPS:
        if a in name_lower:
            variants.add(name_lower.replace(a, b))
        if b in name_lower:
            variants.add(name_lower.replace(b, a))

    # Rule 2: Diacritics-stripped version
    stripped = _strip_diacritics(name_lower)
    if stripped != name_lower:
        variants.add(stripped)

    # Rule 3: Remove hyphens
    if '-' in name_lower:
        variants.add(name_lower.replace('-', ''))

    # Rule 4: Number variants — "โมเดิน 50" → "โมเดิน50", "โมเดิน"
    num_match = re.match(r'^(.+?)\s+(\d+)$', name_lower)
    if num_match:
        base, num = num_match.group(1), num_match.group(2)
        variants.add(f"{base}{num}")  # no space
        variants.add(base)            # no number

    # Also check "name + space + number" in original
    num_match2 = re.match(r'^(.+?)(\d+)$', name_lower)
    if num_match2 and not num_match:
        base = num_match2.group(1)
        num = num_match2.group(2)
        variants.add(f"{base} {num}")  # with space
        variants.add(base)             # no number

    return sorted(variants)


# =========================================================================
# Fallback product data — snapshot of current ICP_PRODUCT_NAMES
# Used only when DB is unavailable
# =========================================================================
_FALLBACK_PRODUCTS = {
    # NOTE: auto-variants already handle consonant swaps (ค↔ก,ท↔ต,ซ↔ส,ห↔ฮ,พ↔ป,บ↔ป,ฟ↔ฝ),
    #       diacritics stripping, hyphen removal, and number spacing.
    #       Aliases here cover: English names, short forms, nicknames, unusual typos.
    "กะรัต": ["กะรัต", "กะรัต 35", "กะหรัต", "การัต", "กระรัต", "karat"],
    "ก็อปกัน": ["ก็อปกัน", "กอปกัน", "ท็อปกัน", "ทอปกัน", "ก๊อปกัน", "topgun", "top gun"],
    "คาริสมา": ["คาริสมา", "คาริสม่า", "คาริส", "charisma", "คริสม่า"],
    "ซิมเมอร์": ["ซิมเมอร์", "ซิมเมอ", "simmer", "ชิมเมอร์"],
    "ซีเอ็มจี": ["ซีเอ็มจี", "cmg", "ซีเอมจี", "ซีเอมจี"],
    "ทูโฟฟอส": ["ทูโฟฟอส", "ทูโฟ", "ทูโฟโฟส", "ทูโฟฟอร์ส", "2-4-d"],
    "นาแดน": ["นาแดน", "นาแดน 6 จี", "นาแดน-จี", "นาแดนจี", "นาแดน6จี", "nadan"],
    "บลูไวท์": ["บลูไวท์", "บลูไวต์", "bluewhite", "blue white", "บลูไว"],
    "พรีดิคท์": ["พรีดิคท์", "พรีดิค", "predict", "พรีดิก", "พรีดิกท์"],
    "พาสนาว": ["พาสนาว", "พาสนาว์", "passnow", "พาสหนาว"],
    "พานาส": ["พานาส", "เลกาซี 20 + พานาส", "panas"],
    "ราเซอร์": ["ราเซอร์", "เรเซอร์", "racer", "razor", "razer"],
    "รีโนเวท": ["รีโนเวท", "รีโนเวต", "renovate", "รีโนเวท์"],
    "วอร์แรนต์": ["วอร์แรนต์", "วอแรนต์", "warrant", "วอร์แรน", "วอแรน"],
    "อะนิลการ์ด": ["อะนิลการ์ด", "อนิลการ์ด", "anilguard", "อะนิลการ์", "อนิลการ์"],
    "อัพดาว": ["อัพดาว", "อัปดาว", "updown", "อัพดาวน์", "อัปดาวน์"],
    "อาร์ดอน": ["อาร์ดอน", "อาดอน", "ardon"],
    "อาร์เทมิส": ["อาร์เทมิส", "อาร์เทมีส", "อาเทมิส", "artemis", "อาทิมิส"],
    "อิมิดาโกลด์": ["อิมิดาโกลด์", "อิมิดา", "อิมิดาโกล", "imidagold", "อิมิดาโกลด์70", "อิมิดาโกลด์ 70", "imida"],
    "เกรค": ["เกรค", "เกรค 5 เอสซี", "เกรด", "เกรด5", "เกรค5", "เกรด 5", "grace", "เกร็ค", "เกรค 5"],
    "เคเซีย": ["เคเซีย", "เคเซีย์", "kesia", "cassia", "คาเซีย"],
    "เทอราโน": ["เทอราโน่", "เทอราโน", "terano", "เทอร่าโน่"],
    "เบนซาน่า": ["เบนซาน่า", "เบนซาน่า เอฟ", "benzana", "เบนซานา", "เบนซาน่าเอฟ"],
    "เมลสัน": ["เมลสัน", "เมลซัน", "melson"],
    "แกนเตอร์": ["แกนเตอร์", "แกนเตอ", "แกนเตอร", "ganter"],
    "แจ๊ส": ["แจ๊ส", "แจส", "jazz"],
    "แมสฟอร์ด": ["แมสฟอร์ด", "แมสฟอด", "massford", "แมสฟอร์"],
    "แอนดาแม็กซ์": ["แอนดาแม็กซ์", "แอนดาแมกซ์", "แอนดาแม็ก", "andamax", "แอนด้าแม็กซ์"],
    "แอสไปร์": ["แอสไปร์", "แอสไปร", "aspire"],
    "โค-ราซ": ["โค-ราซ", "โคราซ", "koraz", "โคราช", "โคราท", "korat"],
    "โคเบิล": ["โคเบิล", "โคเบิ้ล", "cobalt", "โคบอล"],
    "โซนิก": ["โซนิก", "sonic", "โซนิค"],
    "โทมาฮอค": ["โทมาฮอค", "โทมาฮอก", "โทมาหอค", "tomahawk", "โทม่าฮอค"],
    "โม-เซ่": ["โม-เซ่", "โมเซ่", "โมเซ", "moze"],
    "โมเดิน": ["โมเดิน", "โมเดิน 50", "โมเดิน50", "modern", "โมเดิ้น"],
    "โฮป": ["โฮป", "hope"],
    "ไซม๊อกซิเมท": ["ไซม๊อกซิเมท", "ไซมอกซิเมท", "cymoximate", "ไซม๊อก", "cymox", "ไซม็อกซิเมท"],
    "ไดแพ๊กซ์": ["ไดแพ๊กซ์", "ไดแพกซ์", "dipax", "ไดแพ็กซ์"],
    "ไพรซีน": ["ไพรซีน", "ไพรซิน", "pricine"],
    "ไฮซีส": ["ไฮซีส", "ไฮซิส", "hysis"],
    "ชุดกล่องม่วง": ["ชุดกล่องม่วง", "กล่องม่วง", "ชุดม่วง"],
    "เลกาซี": ["เลกาซี", "legacy", "เลกาซี่"],
    "โตโร่": ["โตโร่", "โตโร", "toro"],
    "โบร์แลน": ["โบร์แลน", "โบรแลน", "borlan", "โบแลน"],
    "ธานอส": ["ธานอส", "thanos"],
    "ไกลโฟเสท": ["ไกลโฟเสท", "glyphosate", "ไกลโฟเซท", "ไกรโฟเสท", "ไกลโฟเสต"],
    "ไดพิม": ["ไดพิม", "ไดพิม 90", "ไดพิม90", "daipim"],
    "อาทราซีน": ["อาทราซีน", "อาทราซีน80", "atrazine", "อาทราซีน 80"],
    "เวคเตอร์": ["เวคเตอร์", "vector", "เว็คเตอร์"],
    "ชุดเขียวพุ่งไว": ["ชุดเขียวพุ่งไว", "กล่องเขียว", "เขียวพุ่งไว", "ชุดเขียว"],
    "รวงใหญ่ชุดทอง": ["รวงใหญ่ชุดทอง", "ชุดทอง", "กล่องทอง", "รวงใหญ่"],
}


class ProductRegistry:
    """
    Singleton registry of product names, loaded from DB at startup.

    Provides:
    - extract_product_name(question) — exact + diacritics + fuzzy match
    - fuzzy_match(text, threshold) — fuzzy only
    - get_canonical_list() — flat list of canonical names
    - get_aliases(name) — aliases for a product
    - is_known_product(name) — check if name is canonical
    - get_product_names_dict() — dict of canonical → [aliases]
    """

    _instance: Optional['ProductRegistry'] = None

    _AUTO_REFRESH_INTERVAL = 900  # 15 minutes — auto-reload from DB

    def __init__(self):
        self._products: Dict[str, List[str]] = {}       # canonical → [aliases]
        self._canonical_list: List[str] = []             # flat list for LLM prompt
        self._alias_index: Dict[str, str] = {}           # lowercase alias → canonical
        self._stripped_index: Dict[str, str] = {}         # diacritics-stripped alias → canonical
        self._loaded: bool = False
        self._load_time: float = 0

    @classmethod
    def get_instance(cls) -> 'ProductRegistry':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def loaded(self) -> bool:
        return self._loaded

    # =====================================================================
    # Loading
    # =====================================================================

    async def load_from_db(self, supabase_client) -> bool:
        """
        Load product names from DB products table.
        Auto-generates Thai typo variants for each product.
        Falls back to _FALLBACK_PRODUCTS if DB is unavailable.
        """
        products: Dict[str, List[str]] = {}
        try:
            if supabase_client is None:
                raise RuntimeError("supabase_client is None")

            from app.config import PRODUCT_TABLE
            result = await aexecute(supabase_client.table(PRODUCT_TABLE).select('product_name, aliases, product_category'))
            if not result.data:
                raise RuntimeError("No products returned from DB")

            db_names = sorted(set(row['product_name'] for row in result.data if row.get('product_name')))
            logger.info(f"ProductRegistry: loaded {len(db_names)} products from DB")

            # Build lookup: product_name → aliases string from DB
            db_aliases_map: Dict[str, str] = {}
            db_category_map: Dict[str, str] = {}
            for row in result.data:
                name = row.get('product_name')
                if name and row.get('aliases'):
                    db_aliases_map[name] = row['aliases']
                if name and row.get('product_category'):
                    db_category_map[name] = row['product_category']

            for name in db_names:
                auto_variants = _generate_thai_variants(name)
                # Merge with fallback hand-crafted aliases if available
                fallback_aliases = _FALLBACK_PRODUCTS.get(name, [])

                # Parse DB aliases (comma-separated)
                db_aliases = []
                if name in db_aliases_map:
                    db_aliases = [a.strip().lower() for a in db_aliases_map[name].split(',') if a.strip()]

                all_aliases = sorted(set(auto_variants + [a.lower() for a in fallback_aliases] + db_aliases))
                products[name] = all_aliases

            # Also include fallback-only products (e.g. from knowledge table) not in DB
            for name, aliases in _FALLBACK_PRODUCTS.items():
                if name not in products:
                    auto_variants = _generate_thai_variants(name)
                    all_aliases = sorted(set(auto_variants + [a.lower() for a in aliases]))
                    products[name] = all_aliases
                    logger.debug(f"  fallback-only product: {name}")

        except Exception as e:
            logger.warning(f"ProductRegistry: DB load failed ({e}), using fallback data")
            for name, aliases in _FALLBACK_PRODUCTS.items():
                auto_variants = _generate_thai_variants(name)
                all_aliases = sorted(set(auto_variants + [a.lower() for a in aliases]))
                products[name] = all_aliases

        self._build_index(products, db_category_map)
        return self._loaded

    async def refresh_if_stale(self, supabase_client) -> bool:
        """
        Auto-refresh from DB if more than _AUTO_REFRESH_INTERVAL seconds since last load.
        Call this periodically (e.g., before each message) to keep registry in sync with DB.
        Returns True if a refresh was performed.
        """
        if not self._loaded:
            return await self.load_from_db(supabase_client)
        elapsed = time.time() - self._load_time
        if elapsed < self._AUTO_REFRESH_INTERVAL:
            return False
        logger.info(f"ProductRegistry: auto-refreshing ({elapsed:.0f}s since last load)")
        prev_count = len(self._canonical_list)
        await self.load_from_db(supabase_client)
        new_count = len(self._canonical_list)
        if new_count != prev_count:
            logger.info(f"ProductRegistry: refreshed {prev_count} → {new_count} products")
        return True

    def load_from_dict(self, products_dict: Dict[str, List[str]]) -> None:
        """Load from a dict directly (for testing or fallback)."""
        products: Dict[str, List[str]] = {}
        for name, aliases in products_dict.items():
            auto_variants = _generate_thai_variants(name)
            all_aliases = sorted(set(auto_variants + [a.lower() for a in aliases]))
            products[name] = all_aliases
        self._build_index(products)

    def _build_index(self, products: Dict[str, List[str]], category_map: Dict[str, str] = None) -> None:
        """Build reverse-lookup indexes from products dict."""
        self._products = products
        self._canonical_list = sorted(products.keys())
        self._category_map = category_map or {}

        # Build alias → canonical index (longest aliases first for greedy match)
        alias_index: Dict[str, str] = {}
        stripped_index: Dict[str, str] = {}
        for canonical, aliases in products.items():
            canonical_lower = canonical.lower()
            # Canonical name itself is an alias
            alias_index[canonical_lower] = canonical
            stripped_index[_strip_diacritics(canonical_lower)] = canonical
            for alias in aliases:
                alias_lower = alias.lower()
                alias_index[alias_lower] = canonical
                stripped = _strip_diacritics(alias_lower)
                stripped_index[stripped] = canonical

        self._alias_index = alias_index
        self._stripped_index = stripped_index
        self._loaded = True
        self._load_time = time.time()
        logger.info(f"ProductRegistry: indexed {len(self._canonical_list)} products, {len(alias_index)} aliases")

    # =====================================================================
    # Matching
    # =====================================================================

    def extract_product_name(self, question: str) -> Optional[str]:
        """
        Extract product name from user question.
        Pipeline: exact substring → diacritics-stripped → fuzzy match.
        """
        self._ensure_loaded()
        question_lower = question.lower()

        # Step 1: Exact substring match — scan aliases sorted by length (longest first)
        # to prefer more specific matches
        sorted_aliases = sorted(self._alias_index.keys(), key=len, reverse=True)
        for alias in sorted_aliases:
            if alias in question_lower:
                return self._alias_index[alias]

        # Step 2: Diacritics-stripped match
        question_stripped = _strip_diacritics(question_lower)
        sorted_stripped = sorted(self._stripped_index.keys(), key=len, reverse=True)
        for stripped_alias in sorted_stripped:
            if stripped_alias in question_stripped:
                return self._stripped_index[stripped_alias]

        # Step 3: Fuzzy match (fallback)
        return self.fuzzy_match(question)

    def extract_all_product_names(self, question: str) -> list:
        """
        Extract ALL product names from user question (for multi-product comparison queries).
        Returns list of unique canonical product names found.

        If user types a base name (e.g. "โบว์แลน") that has variants (e.g. "โบว์แลน 285"),
        returns ALL variants of that family.
        """
        self._ensure_loaded()
        question_lower = question.lower()
        found = []
        seen = set()
        remaining = question_lower

        # Scan aliases longest-first; remove matched span to find remaining products
        sorted_aliases = sorted(self._alias_index.keys(), key=len, reverse=True)
        for alias in sorted_aliases:
            if alias in remaining:
                canonical = self._alias_index[alias]
                if canonical not in seen:
                    found.append(canonical)
                    seen.add(canonical)
                # Remove matched span so it doesn't interfere with next match
                remaining = remaining.replace(alias, ' ', 1)

        # Also try diacritics-stripped matching on remaining text
        if remaining.strip():
            remaining_stripped = _strip_diacritics(remaining)
            sorted_stripped = sorted(self._stripped_index.keys(), key=len, reverse=True)
            for stripped_alias in sorted_stripped:
                if stripped_alias in remaining_stripped:
                    canonical = self._stripped_index[stripped_alias]
                    if canonical not in seen:
                        found.append(canonical)
                        seen.add(canonical)
                    remaining_stripped = remaining_stripped.replace(stripped_alias, ' ', 1)

        # Family expansion: if user typed base name, include all variants
        # e.g. "โบว์แลน" → ["โบว์แลน", "โบว์แลน 285"]
        # e.g. "พรีดิคท์" → ["พรีดิคท์ 10%", "พรีดิคท์ 15%", "พรีดิคท์ 25% เอฟ"]
        all_canonical = self.get_canonical_list()

        # Find shortest canonical name that appears in query (the "base")
        # This handles case where "โบว์แลน" alias → maps to "โบว์แลน 285" but
        # product "โบว์แลน" (base) also exists as separate product
        base_candidates = []
        for canonical in all_canonical:
            c_lower = canonical.lower()
            if c_lower in question_lower:
                base_candidates.append(canonical)
        # Sort by length: shortest = base name
        base_candidates.sort(key=len)

        if base_candidates:
            base = base_candidates[0]
            base_lower = base.lower()
            # Skip family expansion if a longer variant is already in query
            # e.g. "โบว์แลน 285" → don't expand to include plain "โบว์แลน"
            has_longer = any(
                c != base and c.lower() in question_lower and len(c) > len(base)
                for c in base_candidates
            )
            if not has_longer:
                # Add base itself if not found
                if base not in seen:
                    found.insert(0, base)
                    seen.add(base)
                # Add all variants
                for other in all_canonical:
                    if other == base or other in seen:
                        continue
                    other_lower = other.lower()
                    if other_lower.startswith(base_lower) and len(other_lower) > len(base_lower):
                        next_char = other_lower[len(base_lower):len(base_lower)+1]
                        if next_char in (' ', '%', '-') or next_char.isdigit():
                            found.append(other)
                            seen.add(other)

        return found

    def fuzzy_match(self, text: str, threshold: float = 0.75) -> Optional[str]:
        """
        Fuzzy matching for misspelled product names.
        e.g. "แแกนเตอ" → "แกนเตอร์", "โมเดิ้น" → "โมเดิน"
        """
        self._ensure_loaded()
        tokens = re.findall(r'[\u0E00-\u0E7F]+|[a-zA-Z]+', text)

        best_match = None
        best_score = 0.0

        for token in tokens:
            if len(token) < 4:
                continue
            token_lower = token.lower()
            for alias, canonical in self._alias_index.items():
                # Direct comparison
                score = SequenceMatcher(None, token_lower, alias).ratio()
                if score > best_score and score >= threshold:
                    best_score = score
                    best_match = canonical

                # Sliding window for long tokens
                alias_len = len(alias)
                if len(token_lower) > alias_len + 1 and alias_len >= 3:
                    for i in range(len(token_lower) - alias_len + 2):
                        end = min(i + alias_len + 1, len(token_lower))
                        sub = token_lower[i:end]
                        # Skip substrings shorter than alias (edge artifacts)
                        if len(sub) < alias_len:
                            continue
                        score = SequenceMatcher(None, sub, alias).ratio()
                        if score > best_score and score >= threshold:
                            best_score = score
                            best_match = canonical

        return best_match

    # =====================================================================
    # Query API (backward-compatible)
    # =====================================================================

    def get_canonical_list(self) -> List[str]:
        """Flat sorted list of canonical product names (for LLM prompt)."""
        self._ensure_loaded()
        return list(self._canonical_list)

    def get_names_by_categories(self, categories: List[str]) -> List[str]:
        """Get product names filtered by category (case-insensitive).
        Returns sorted list of product names matching any of the given categories."""
        self._ensure_loaded()
        cats_lower = {c.lower() for c in categories}
        return sorted(
            name for name, cat in self._category_map.items()
            if cat.lower() in cats_lower
        )

    def get_aliases(self, name: str) -> List[str]:
        """Get aliases for a canonical product name."""
        self._ensure_loaded()
        return list(self._products.get(name, [name.lower()]))

    def is_known_product(self, name: str) -> bool:
        """Check if name is a known canonical product name."""
        self._ensure_loaded()
        return name in self._products

    def get_product_names_dict(self) -> Dict[str, List[str]]:
        """Get full products dict {canonical: [aliases]}."""
        self._ensure_loaded()
        return dict(self._products)

    def resolve_alias(self, alias: str) -> Optional[str]:
        """Resolve an alias to canonical name, or None."""
        self._ensure_loaded()
        return self._alias_index.get(alias.lower())

    # =====================================================================
    # Internal
    # =====================================================================

    def _ensure_loaded(self) -> None:
        """Ensure the registry is loaded. If not, load from fallback."""
        if not self._loaded:
            logger.warning("ProductRegistry: not loaded yet, using fallback data")
            self.load_from_dict(_FALLBACK_PRODUCTS)
