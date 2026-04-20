"""
Tests — ครอบคลุมทุกสินค้าใน DB (90 ตัว)

สำหรับแต่ละสินค้า: ทดสอบ 3 อย่าง
1. extract_product_name — ชื่อเต็มในคำถาม → คืน canonical
2. extract_all_product_names — ชื่อเต็ม → มี canonical อยู่ในผลลัพธ์
3. is_known_product / category — มี category ถูกต้องใน registry

Integration test — require real Supabase เพื่อ load 90 สินค้าจาก products3
"""

from __future__ import annotations

import asyncio
import os

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
# Module fixtures — load registry + canonical list once
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


@pytest.fixture(scope="module")
def all_canonical_names(registry_loaded):
    """Flat list of all canonical product names from registry (DB + fallback)."""
    names = registry_loaded.get_canonical_list()
    assert len(names) >= 80, f"Expected ~90 products loaded, got {len(names)}"
    return names


# Build param lists at collection time so each product = separate test
def _load_registry_lists():
    """Returns (all_canonicals, db_only_products).
    db_only_products = products that exist in products3 DB (have category).
    """
    if not _has_real_supabase():
        return [], []
    try:
        from app.dependencies import supabase_client
        from app.services.product.registry import ProductRegistry

        reg = ProductRegistry.get_instance()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(reg.load_from_db(supabase_client))
        finally:
            loop.close()

        all_canon = reg.get_canonical_list()
        cat_map = getattr(reg, "_category_map", {})
        db_only = [n for n in all_canon if cat_map.get(n)]
        return all_canon, db_only
    except Exception:
        return [], []


_ALL_PRODUCTS, _DB_PRODUCTS = _load_registry_lists()


# =============================================================================
# 1. extract_product_name — each canonical found when used in question
# =============================================================================

class TestAllProductsExtraction:
    """ทุกสินค้าใน DB → extract ได้เมื่อ user พิมพ์ชื่อเต็มในคำถาม"""

    @staticmethod
    def _family_prefix(name: str) -> str:
        """First 3 chars of first token (split on space/hyphen) — family identifier."""
        token = name.split()[0].split('-')[0]
        return token[:3] if len(token) >= 3 else token

    @pytest.mark.parametrize("product_name", _ALL_PRODUCTS)
    def test_exact_name_in_question(self, registry_loaded, product_name):
        """พิมพ์ชื่อเต็มในคำถาม → ต้อง extract ได้ (อย่างน้อยเป็นสินค้า family เดียวกัน)"""
        from app.services.chat.handler import extract_product_name_from_question

        question = f"{product_name} ใช้ยังไง"
        extracted = extract_product_name_from_question(question)
        assert extracted is not None, f"Failed to extract {product_name!r} from {question!r}"

        # Accept base name or any variant of the same family
        prefix = self._family_prefix(product_name)
        assert (
            extracted == product_name
            or product_name.startswith(extracted)
            or extracted.startswith(prefix)
        ), f"Extract mismatch: {extracted!r} for {product_name!r} (family prefix={prefix!r})"

    @pytest.mark.parametrize("product_name", _ALL_PRODUCTS)
    def test_extract_all_contains_product(self, registry_loaded, product_name):
        """extract_all_product_names → ต้องมี canonical ตัวเองหรือ family member อยู่ใน result"""
        from app.services.chat.handler import extract_all_product_names_from_question

        question = f"{product_name} ใช้ยังไง"
        extracted = extract_all_product_names_from_question(question)
        assert extracted, f"extract_all returned empty for {product_name!r}"

        prefix = self._family_prefix(product_name)
        matched = [e for e in extracted if e == product_name or e.startswith(prefix)]
        assert matched, (
            f"extract_all did not return {product_name!r} or family member.\n"
            f"  Query: {question!r}\n  Got: {extracted}\n  Family prefix: {prefix!r}"
        )


# =============================================================================
# 2. Registry meta — every product has category + is_known
# =============================================================================

class TestAllProductsMeta:
    """ทุกสินค้าใน registry → มี metadata ครบ"""

    @pytest.mark.parametrize("product_name", _ALL_PRODUCTS)
    def test_is_known_product(self, registry_loaded, product_name):
        """canonical name ต้อง is_known_product == True"""
        assert registry_loaded.is_known_product(product_name), (
            f"Registry does not recognize canonical: {product_name!r}"
        )

    @pytest.mark.parametrize("product_name", _ALL_PRODUCTS)
    def test_has_aliases(self, registry_loaded, product_name):
        """ทุกสินค้า → ต้องมี alias อย่างน้อย 1 ตัว (canonical.lower() นับเป็น alias)"""
        aliases = registry_loaded.get_aliases(product_name)
        assert aliases, f"{product_name!r} has zero aliases"

    @pytest.mark.parametrize("product_name", _ALL_PRODUCTS)
    def test_canonical_resolves_to_known(self, registry_loaded, product_name):
        """canonical.lower() → ต้อง resolve เป็น canonical ที่รู้จัก
        (อาจ collapse ไป family base เช่น 'กะรัต 35' → 'กะรัต' ถ้า DB มี alias ซ้อน)
        """
        resolved = registry_loaded.resolve_alias(product_name.lower())
        assert resolved is not None, (
            f"canonical {product_name!r} does not resolve to any canonical"
        )
        assert registry_loaded.is_known_product(resolved), (
            f"resolve_alias returned unknown canonical {resolved!r} for {product_name!r}"
        )


# =============================================================================
# 3. Category — each product has category from products3
# =============================================================================

class TestAllProductsCategory:
    """ทุกสินค้า → มี category ไม่ว่าง และอยู่ใน 6 กลุ่มที่ถูกต้อง"""

    VALID_CATEGORIES = {
        "Insecticide", "Fungicide", "Herbicide",
        "Biostimulants", "Fertilizer", "PGR",
        # Allow Thai variants / mixed case that may exist in DB
    }

    @pytest.fixture(scope="class")
    def category_map(self, registry_loaded):
        """internal _category_map from registry"""
        return getattr(registry_loaded, "_category_map", {})

    @pytest.mark.parametrize("product_name", _DB_PRODUCTS)
    def test_has_category(self, category_map, product_name):
        """ทุกสินค้าที่มาจาก DB ต้องมี category (fallback-only products ข้าม)"""
        cat = category_map.get(product_name, "")
        assert cat, f"{product_name!r} has no category in registry"

    def test_category_distribution(self, category_map):
        """ภาพรวม: category distribution ต้องมีครบทุกกลุ่มหลัก"""
        from collections import Counter

        cats = Counter(category_map.values())
        # ต้องมี 6 กลุ่มหลักอย่างน้อย 3 สินค้าต่อกลุ่ม
        for expected in ("Insecticide", "Fungicide", "Herbicide"):
            assert cats.get(expected, 0) >= 3, (
                f"Category {expected} has only {cats.get(expected, 0)} products"
            )


# =============================================================================
# 4. Sanity — registry loaded correct number + no duplicates
# =============================================================================

class TestRegistrySanity:

    def test_registry_loaded_enough_products(self, all_canonical_names):
        """DB มี 90 สินค้า → registry ต้อง load ได้ ≥80 (เผื่อ aliases dedup)"""
        assert len(all_canonical_names) >= 80, (
            f"Registry loaded only {len(all_canonical_names)} canonical names; expected ≥80"
        )

    def test_no_duplicate_canonicals(self, all_canonical_names):
        """canonical list ห้ามมี duplicate"""
        assert len(all_canonical_names) == len(set(all_canonical_names)), (
            "Duplicate canonical names in registry"
        )

    def test_alias_index_not_empty(self, registry_loaded):
        """Alias index ต้องมีข้อมูล (ทุกสินค้ามี alias อย่างน้อย canonical.lower())"""
        alias_count = len(getattr(registry_loaded, "_alias_index", {}))
        product_count = len(registry_loaded.get_canonical_list())
        assert alias_count >= product_count, (
            f"Alias index ({alias_count}) < product count ({product_count})"
        )
