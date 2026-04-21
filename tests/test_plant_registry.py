"""
Tests for PlantRegistry — DB-driven plant name extraction.

Ensures:
1. Longest-match-first prevents substring bugs (ข้าว ⊂ ข้าวโพด, ส้ม ⊂ ส้มโอ, ...)
2. Typo corrections map to canonical (ลำใย → ลำไย, ทุเรีย → ทุเรียน)
3. Synonyms map to canonical (นาข้าว → ข้าว, ไร่ข้าวโพด → ข้าวโพด)
4. Fallback to hardcoded list if DB unavailable
"""

from __future__ import annotations

import inspect
import os
import pytest
from dotenv import load_dotenv

# Ensure .env is loaded before anything else (overrides conftest dummy values)
load_dotenv(override=True)


class TestPlantRegistryInstance:
    """Registry singleton + loaded-state checks"""

    def test_singleton(self):
        from app.services.plant.registry import PlantRegistry
        r1 = PlantRegistry.get_instance()
        r2 = PlantRegistry.get_instance()
        assert r1 is r2

    def test_unloaded_registry_returns_none(self):
        """If registry never loaded, extract returns None — handler falls back"""
        from app.services.plant.registry import PlantRegistry
        r = PlantRegistry()  # fresh instance, NOT loaded
        assert r.extract("ทุเรียน") is None
        assert r.loaded is False


class TestLongestFirstMatching:
    """The core bug this registry solves"""

    def setup_method(self):
        from app.services.plant.registry import PlantRegistry
        self.reg = PlantRegistry()
        # Load from a representative plant set (no DB call)
        self.reg._build_index({
            "ข้าว", "ข้าวโพด", "ข้าวเหนียว", "นาข้าว",
            "ส้ม", "ส้มโอ",
            "ปาล์ม", "ปาล์มน้ำมัน",
            "มะม่วง", "มะม่วงหิมพานต์",
            "หอม", "หอมแดง", "หอมกระเทียม",
            "ผัก", "ผักคะน้า", "ผักกาด", "ผักกาดขาว",
            "มัน", "มันฝรั่ง", "มันสำปะหลัง",
            "ทุเรียน", "ลำไย",
        })
        self.reg._loaded = True

    @pytest.mark.parametrize("query,expected", [
        # The specific bug from LINE
        ("ใช้ยาอะไรฆ่าหญ้าในข้าวโพด", "ข้าวโพด"),
        # Substring pairs: compound MUST win
        ("ข้าวโพดเป็นโรค", "ข้าวโพด"),
        ("ข้าวเหนียวใบไหม้", "ข้าวเหนียว"),
        ("ส้มโอใบเหลือง", "ส้มโอ"),
        ("ปาล์มน้ำมันใบจุด", "ปาล์มน้ำมัน"),
        ("มะม่วงหิมพานต์ใบไหม้", "มะม่วงหิมพานต์"),
        ("หอมกระเทียม", "หอมกระเทียม"),
        ("หอมแดงเน่า", "หอมแดง"),
        ("ผักคะน้าเป็นโรค", "ผักคะน้า"),
        ("ผักกาดขาวเน่า", "ผักกาดขาว"),
        ("มันฝรั่งใบเหลือง", "มันฝรั่ง"),
        ("มันสำปะหลังเป็นเพลี้ย", "มันสำปะหลัง"),
        # Base names still work
        ("ข้าวใบไหม้", "ข้าว"),
        ("ส้มเน่า", "ส้ม"),
        ("ปาล์มใบเหลือง", "ปาล์ม"),
        ("หอมใบจุด", "หอม"),
        ("ผักต่างๆ", "ผัก"),
    ])
    def test_compound_beats_substring(self, query, expected):
        got = self.reg.extract(query)
        assert got == expected, f"Query {query!r} → {got!r}, expected {expected!r}"


class TestTypoAndSynonyms:
    """Typo corrections + regional synonyms → canonical"""

    def setup_method(self):
        from app.services.plant.registry import PlantRegistry
        self.reg = PlantRegistry()
        self.reg._build_index({
            "ทุเรียน", "ข้าว", "ข้าวโพด", "ลำไย", "มันสำปะหลัง", "ยางพารา",
            "มะม่วง", "ส้ม", "ลิ้นจี่", "อ้อย",
        })
        self.reg._loaded = True

    @pytest.mark.parametrize("query,expected", [
        # Typos
        ("ทุเรียน", "ทุเรียน"),
        ("ทุเรีย", "ทุเรียน"),                 # missing น
        ("ทุเรี่ยน", "ทุเรียน"),              # extra diacritic
        ("ทุลเรียน", "ทุเรียน"),              # misheard ร
        ("มันสัมปะหลัง", "มันสำปะหลัง"),      # common typo
        ("มันสำปะหรัง", "มันสำปะหลัง"),       # DB typo
        ("ลำใย", "ลำไย"),                       # DB typo
        ("ลิ้นจี", "ลิ้นจี่"),                  # missing trailing mark
        # Synonyms (regional / colloquial)
        ("นาข้าว", "ข้าว"),
        ("ข้าวนา", "ข้าว"),
        ("ไร่ข้าวโพด", "ข้าวโพด"),
        ("ไร่อ้อย", "อ้อย"),
        ("ต้นทุเรียน", "ทุเรียน"),
        ("สวนทุเรียน", "ทุเรียน"),
        ("สวนลำไย", "ลำไย"),
        ("สวนมะม่วง", "มะม่วง"),
        ("สวนส้ม", "ส้ม"),
    ])
    def test_typo_or_synonym_maps_to_canonical(self, query, expected):
        got = self.reg.extract(query)
        assert got == expected, f"{query!r} → {got!r}, expected {expected!r}"


class TestDBIntegration:
    """Verifies DB loading + refresh (integration — needs real DB)"""

    @pytest.mark.asyncio
    async def test_load_from_db_extracts_known_plants(self):
        import os
        url = os.environ.get("SUPABASE_URL", "")
        if not url.startswith("https://fwzdgzpuajcsigwlyojr"):
            pytest.skip("Needs real Supabase (integration only)")
        from app.dependencies import supabase_client
        from app.services.plant.registry import PlantRegistry
        reg = PlantRegistry()
        ok = await reg.load_from_db(supabase_client)
        assert ok
        assert reg.loaded
        canonicals = reg.get_canonical_list()
        # DB has these 34+
        for p in ("ข้าว", "ข้าวโพด", "ทุเรียน", "ผักคะน้า",
                  "ถั่วฝักยาว", "มันฝรั่ง"):
            assert p in canonicals, f"{p!r} missing from loaded registry"

    @pytest.mark.asyncio
    async def test_auto_refresh_no_op_when_fresh(self):
        import os
        url = os.environ.get("SUPABASE_URL", "")
        if not url.startswith("https://fwzdgzpuajcsigwlyojr"):
            pytest.skip("Needs real Supabase (integration only)")
        from app.dependencies import supabase_client
        from app.services.plant.registry import PlantRegistry
        reg = PlantRegistry()
        await reg.load_from_db(supabase_client)
        # Immediate second refresh should be no-op
        did_refresh = await reg.refresh_if_stale(supabase_client)
        assert did_refresh is False


class TestHandlerIntegration:
    """Verifies extract_plant_type_from_question uses the registry"""

    def test_handler_source_uses_plant_registry(self):
        import inspect
        from app.services.chat import handler
        src = inspect.getsource(handler.extract_plant_type_from_question)
        assert "PlantRegistry" in src, (
            "handler.extract_plant_type_from_question must use PlantRegistry"
        )
        assert "reg.loaded" in src or "registry.loaded" in src

    def test_refresh_wired_in_handle_natural_conversation(self):
        import inspect
        from app.services.chat import handler
        src = inspect.getsource(handler.handle_natural_conversation)
        assert "PlantRegistry" in src, (
            "handle_natural_conversation must call PlantRegistry.refresh_if_stale"
        )


class TestCriticalBug:
    """Regression: the exact query from the LINE log"""

    @pytest.mark.asyncio
    async def test_the_corn_weed_query(self):
        """
        Real bug: "ใช้ยาอะไรฆ่าหญ้าในข้าวโพด" was detecting plant=ข้าว,
        causing bot to recommend rice-only herbicides like ไซฟอบ.
        """
        import os
        url = os.environ.get("SUPABASE_URL", "")
        if not url.startswith("https://fwzdgzpuajcsigwlyojr"):
            pytest.skip("Needs real Supabase (integration only)")
        from app.dependencies import supabase_client
        from app.services.plant.registry import PlantRegistry
        reg = PlantRegistry.get_instance()
        await reg.load_from_db(supabase_client)
        plant = reg.extract("ใช้ยาอะไรฆ่าหญ้าในข้าวโพด")
        assert plant == "ข้าวโพด", (
            f"Critical regression: extracted {plant!r} instead of 'ข้าวโพด' — "
            f"bot may recommend rice-only herbicides for corn fields"
        )
