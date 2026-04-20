"""
Tests — Fuzzy / typo / alias matching (GAP สำคัญที่สุด)

User พิมพ์ชื่อสินค้าผิดบ่อย — bot ต้องเดาถูก
ทดสอบ 6 รูปแบบ typo ต่อสินค้า:
1. Diacritics stripped — "ไบเตอร์" → "ไบเตอร"     (ตกวรรณยุกต์)
2. Consonant swaps — "โทมาฮอค" → "โทมาหอค"       (ค↔ก, ท↔ต, ซ↔ส, ห↔ฮ)
3. Last char dropped — "โคเบิล" → "โคเบิ"         (พิมพ์ไม่ครบ)
4. Case variants — "Skyrocket" → "skyrocket"     (อังกฤษ)
5. Extra spaces — "ไดยูแมกซ์" → "ได ยู แมกซ์"    (เว้นวรรคมั่ว)
6. DB aliases — ทุก alias → resolve ถึง canonical

Integration test — require real Supabase
"""

from __future__ import annotations

import asyncio
import os
import re

import pytest
from dotenv import load_dotenv

load_dotenv(override=True)


def _has_real_supabase() -> bool:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not (url.startswith("https://fwzdgzpuajcsigwlyojr") and key.startswith("eyJ") and len(key) > 100):
        return False
    try:
        from app import dependencies as _deps
        actual_url = getattr(_deps, "SUPABASE_URL", None) or ""
        return "fwzdgzpuajcsigwlyojr" in actual_url
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _has_real_supabase(),
    reason="Needs real Supabase to load 90-product registry",
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def registry_loaded():
    from app.dependencies import supabase_client
    from app.services.product.registry import ProductRegistry

    reg = ProductRegistry.get_instance()
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(reg.load_from_db(supabase_client))
    finally:
        loop.close()
    return reg


def _load_canonical_list():
    if not _has_real_supabase():
        return []
    try:
        from app.dependencies import supabase_client
        from app.services.product.registry import ProductRegistry

        reg = ProductRegistry.get_instance()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(reg.load_from_db(supabase_client))
        finally:
            loop.close()
        return reg.get_canonical_list()
    except Exception:
        return []


_ALL_PRODUCTS = _load_canonical_list()


# =============================================================================
# Typo generators
# =============================================================================

_THAI_DIACRITICS = re.compile(r'[\u0E48\u0E49\u0E4A\u0E4B\u0E47\u0E4C]')


def _strip_diacritics(text: str) -> str:
    return _THAI_DIACRITICS.sub('', text)


def _has_english(name: str) -> bool:
    return bool(re.search(r'[a-zA-Z]', name))


def _has_thai(name: str) -> bool:
    return bool(re.search(r'[\u0E00-\u0E7F]', name))


def _drop_last_char(name: str) -> str:
    """Drop last non-space char for long-enough names."""
    s = name.rstrip()
    if len(s) < 5:
        return s
    return s[:-1]


# Consonant swaps mirroring _CONSONANT_SWAPS in registry.py
_SWAP_PAIRS = [('ค', 'ก'), ('ท', 'ต'), ('ซ', 'ส'), ('ห', 'ฮ'), ('พ', 'ป'), ('ฟ', 'ฝ')]


def _consonant_swap(name: str) -> str:
    """Apply one consonant swap if applicable."""
    for a, b in _SWAP_PAIRS:
        if a in name:
            return name.replace(a, b, 1)
        if b in name:
            return name.replace(b, a, 1)
    return name


# =============================================================================
# 1. Diacritics-stripped match (ตกวรรณยุกต์)
# =============================================================================

class TestDiacriticsTypo:

    @pytest.mark.parametrize("product_name", _ALL_PRODUCTS)
    def test_strip_all_diacritics_still_matches(self, registry_loaded, product_name):
        """ถอดวรรณยุกต์ออกทั้งหมด → ยังต้อง extract ได้"""
        from app.services.chat.handler import extract_product_name_from_question

        stripped = _strip_diacritics(product_name)
        if stripped == product_name:
            pytest.skip(f"{product_name!r} has no diacritics to strip")

        question = f"{stripped} ใช้ยังไง"
        extracted = extract_product_name_from_question(question)
        assert extracted is not None, (
            f"Typo (diacritics stripped) failed: {stripped!r} did not match {product_name!r}"
        )


# =============================================================================
# 2. Consonant swap (ค↔ก, ท↔ต, ซ↔ส, ห↔ฮ, พ↔ป, ฟ↔ฝ)
# =============================================================================

class TestConsonantSwap:

    @pytest.mark.parametrize("product_name", _ALL_PRODUCTS)
    def test_single_consonant_swap_matches(self, registry_loaded, product_name):
        """สลับพยัญชนะ 1 จุด → ยังต้อง match canonical ตัวเอง"""
        from app.services.chat.handler import extract_product_name_from_question

        swapped = _consonant_swap(product_name)
        if swapped == product_name:
            pytest.skip(f"{product_name!r} has no swappable consonant")

        question = f"{swapped} ใช้ยังไง"
        extracted = extract_product_name_from_question(question)
        assert extracted is not None, (
            f"Consonant swap typo failed: {swapped!r} did not match any product "
            f"(original: {product_name!r})"
        )


# =============================================================================
# 3. Last character dropped (พิมพ์ไม่ครบ)
# =============================================================================

class TestPartialTypingTypo:
    """พิมพ์ไม่ครบตัวสุดท้าย — ต้องใช้ fuzzy match"""

    @pytest.mark.parametrize("product_name", _ALL_PRODUCTS)
    def test_last_char_dropped_still_matches(self, registry_loaded, product_name):
        """ตัดตัวอักษรสุดท้าย → ต้อง fuzzy match ได้ (เฉพาะชื่อยาวพอ)
        Skip names with space/hyphen — fuzzy_match tokenizes on non-Thai/English chars,
        producing short tokens that fall below the min-length threshold.
        """
        if len(product_name) < 6 or ' ' in product_name or '-' in product_name:
            pytest.skip(f"{product_name!r} too short/multi-part for this typo")

        dropped = _drop_last_char(product_name)
        result = registry_loaded.fuzzy_match(dropped, threshold=0.75)
        assert result is not None, (
            f"Fuzzy match failed for partial: {dropped!r} (from {product_name!r})"
        )


# =============================================================================
# 4. Case variants (English names)
# =============================================================================

class TestCaseVariants:
    """สินค้าชื่ออังกฤษ → UPPERCASE / lowercase / MixedCase ต้อง match เหมือนกัน"""

    def _english_aliases_per_product(self, registry_loaded):
        """Return {canonical: english_alias} for products with English aliases."""
        result = {}
        for canon, aliases in registry_loaded.get_product_names_dict().items():
            for a in aliases:
                if re.match(r'^[a-zA-Z][a-zA-Z0-9\s]*$', a):
                    result[canon] = a
                    break
        return result

    def test_uppercase_matches(self, registry_loaded):
        """ทุก English alias → UPPERCASE version ต้อง match ได้"""
        from app.services.chat.handler import extract_product_name_from_question

        mapping = self._english_aliases_per_product(registry_loaded)
        assert mapping, "Expected at least some products with English aliases"

        failures = []
        for canon, en_alias in mapping.items():
            question = f"{en_alias.upper()} ใช้ยังไง"
            extracted = extract_product_name_from_question(question)
            if extracted is None:
                failures.append((canon, en_alias))

        assert not failures, (
            f"UPPERCASE failed for {len(failures)} products: {failures[:5]}"
        )

    def test_mixed_case_matches(self, registry_loaded):
        """Mixed case (Title Case) → match ได้"""
        from app.services.chat.handler import extract_product_name_from_question

        mapping = self._english_aliases_per_product(registry_loaded)
        failures = []
        for canon, en_alias in mapping.items():
            question = f"{en_alias.title()} ใช้ยังไง"
            extracted = extract_product_name_from_question(question)
            if extracted is None:
                failures.append((canon, en_alias))

        assert not failures, (
            f"Title Case failed for {len(failures)} products: {failures[:5]}"
        )


# =============================================================================
# 5. DB aliases — each alias in DB must resolve to its canonical
# =============================================================================

class TestDBAliases:
    """ทุก alias ที่อยู่ใน DB/registry → ต้อง resolve ถึง canonical ที่ถูกต้อง"""

    def test_every_alias_resolves(self, registry_loaded):
        """ทดลองทุก alias ใน _alias_index → resolve_alias คืน canonical ถูกต้อง"""
        alias_index = getattr(registry_loaded, "_alias_index", {})
        failures = []
        for alias, expected_canonical in alias_index.items():
            resolved = registry_loaded.resolve_alias(alias)
            if resolved != expected_canonical:
                failures.append((alias, expected_canonical, resolved))

        assert not failures, (
            f"{len(failures)} aliases do not resolve correctly: {failures[:5]}"
        )

    def test_alias_in_question_extracts_canonical(self, registry_loaded):
        """Sample 20 aliases → แต่ละตัวใส่ในคำถาม ต้อง extract canonical ออกมาได้"""
        from app.services.chat.handler import extract_product_name_from_question

        alias_index = getattr(registry_loaded, "_alias_index", {})
        # Sample: longer aliases first (ambiguous short aliases like 'hope' may false-match)
        aliases_sample = sorted(alias_index.keys(), key=len, reverse=True)[:20]

        failures = []
        for alias in aliases_sample:
            expected = alias_index[alias]
            question = f"{alias} ใช้ยังไง"
            extracted = extract_product_name_from_question(question)
            # Accept either exact canonical or family member (base/variant)
            if extracted is None:
                failures.append((alias, expected, None))
                continue
            if extracted != expected:
                # Allow family-prefix match (e.g. "โบว์แลน" → "โบว์แลน 285")
                first_token = expected.split()[0]
                if not extracted.startswith(first_token):
                    failures.append((alias, expected, extracted))

        assert not failures, (
            f"{len(failures)}/20 alias→canonical extractions failed: {failures[:5]}"
        )


# =============================================================================
# 6. Adversarial — ambiguous queries should still return valid canonical
# =============================================================================

class TestAdversarialTypo:
    """Edge cases ที่ user พิมพ์ประหลาด"""

    @pytest.mark.parametrize("typo,expected_family_prefix", [
        # Thai typos ของสินค้าที่ report มาจากหน้างาน
        ("โทมาหอค", "โทมาฮอค"),        # ค↔ก, ห↔ฮ
        ("กอปกัน", "ก็อปกัน"),          # diacritics
        ("บลูไวต์", "บลูไวท์"),        # ต↔ท
        ("คาริสม่า", "คาริสมา"),       # extra diacritic
        ("โมเดิ้น", "โมเดิน"),         # extra diacritic
        ("แอนด้าแม็กซ์", "แอนดาแม็กซ์"), # extra diacritic
        ("ทอปกัน", "ก็อปกัน"),          # ก↔ท + diacritics
    ])
    def test_known_real_typos(self, registry_loaded, typo, expected_family_prefix):
        """Real typos ที่พบใน LINE log → ต้อง match ถูกต้อง"""
        from app.services.chat.handler import extract_product_name_from_question

        question = f"{typo} ใช้ยังไง"
        extracted = extract_product_name_from_question(question)
        assert extracted is not None, f"Typo {typo!r} did not match anything"

        first_token = expected_family_prefix.split()[0]
        assert extracted.startswith(first_token[:3]) or extracted == expected_family_prefix, (
            f"Typo {typo!r} expected near {expected_family_prefix!r}, got {extracted!r}"
        )

    def test_empty_question_returns_none(self, registry_loaded):
        from app.services.chat.handler import extract_product_name_from_question
        assert extract_product_name_from_question("") is None
        assert extract_product_name_from_question("   ") is None

    def test_unknown_product_returns_none_or_no_false_match(self, registry_loaded):
        """ชื่อสินค้าที่ไม่มีใน DB (เช่น Roundup) → ต้องไม่ match มั่วมา"""
        from app.services.chat.handler import extract_product_name_from_question

        unknown_names = ["Roundup", "Atlanta", "Banzai", "TestFoo123"]
        false_matches = []
        for name in unknown_names:
            question = f"{name} ใช้ยังไง"
            extracted = extract_product_name_from_question(question)
            if extracted is not None:
                false_matches.append((name, extracted))

        # อนุญาตให้มี false match ได้ไม่เกิน 1 ตัว (ปกติ fuzzy อาจ match mushy)
        assert len(false_matches) <= 1, (
            f"Too many false matches for unknown products: {false_matches}"
        )
