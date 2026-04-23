"""
Test weed-name precision: Stage 0 extraction + post-retrieval herbicide filter.

Bug scenario (pre-fix): Query "ข้าวดีดใช้ยาอะไร" returned 6 herbicides but only
#1 (ทูโฟพอส) actually targets ข้าวดีด. #2-6 were generic rice herbicides for
other weeds. Fix: extract weed_name in Stage 0 + prune Herbicide docs whose
herbicides column doesn't mention the specific weed.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.text_processing import diacritics_match


# Mirror _WEED_PATTERNS_STAGE0 from orchestrator.py — kept in sync by whitelist test below
_WEED_PATTERNS_STAGE0 = [
    'หญ้าข้าวนก', 'ข้าวดีด', 'ข้าวตีด', 'ข้าวนก',
    'หญ้าดอกขาว', 'หญ้าหนวดแมว', 'หญ้าแห้วหมู',
    'หญ้าตีนกา', 'หญ้าตีนนก', 'หญ้าปากควาย',
    'หญ้านกสีชมพู', 'หญ้าไม้กวาด', 'หญ้าขจรจบ',
    'กกทราย', 'กกขนาก', 'ผักปราบ', 'ผักบุ้งนา',
    'ใบแคบ', 'ใบกว้าง',
]


def extract_weed(query: str) -> str:
    """Simulate Stage 0 weed-name extraction."""
    for pattern in _WEED_PATTERNS_STAGE0:
        if diacritics_match(query, pattern):
            return pattern
    return ''


class TestWeedExtraction:
    """Stage 0 should extract specific weed names from query."""

    @pytest.mark.parametrize("query,expected_weed", [
        ("ข้าวดีดใช้ยาอะไร", "ข้าวดีด"),
        ("ข้าวดีดตัวไหนจัดการได้", "ข้าวดีด"),
        ("กำจัดข้าวดีดในนาข้าว", "ข้าวดีด"),
        ("ยาฆ่าหญ้าข้าวนกในนา", "หญ้าข้าวนก"),
        ("หญ้าดอกขาว ใช้ยาอะไร", "หญ้าดอกขาว"),
        ("หญ้าหนวดแมวในนา", "หญ้าหนวดแมว"),
        ("หญ้าตีนกาในข้าวโพด", "หญ้าตีนกา"),
        ("กำจัดกกทรายในนา", "กกทราย"),
        ("ใบแคบในนาข้าว", "ใบแคบ"),
        ("ใบกว้างในข้าว", "ใบกว้าง"),
    ])
    def test_extracts_specific_weed(self, query, expected_weed):
        assert extract_weed(query) == expected_weed

    @pytest.mark.parametrize("query", [
        "ยาฆ่าหญ้าในข้าว",        # generic — no specific weed
        "แนะนำยาฆ่าหญ้า",         # generic
        "เพลี้ยไก่แจ้ ใช้อะไร",     # not a weed query
        "ทุเรียนรากเน่า",            # disease query
    ])
    def test_no_extraction_for_generic_or_unrelated(self, query):
        assert extract_weed(query) == ''

    def test_longest_match_wins(self):
        # "หญ้าข้าวนก" listed BEFORE "ข้าวนก" — specific pattern should win
        assert extract_weed("ยากำจัดหญ้าข้าวนก") == "หญ้าข้าวนก"


# ---------------------------------------------------------------------
# Post-retrieval filter simulation (mirrors retrieval_agent Stage 3.545)
# ---------------------------------------------------------------------
class _FakeDoc:
    def __init__(self, product_id, category, herbicides):
        self.id = product_id
        self.metadata = {'category': category, 'herbicides': herbicides}


def simulate_weed_precision_filter(weed_name: str, docs: list) -> list:
    """Mirror retrieval_agent Stage 3.545 logic for tests."""
    if weed_name in {'หญ้า', 'วัชพืช', 'ใบแคบ', 'ใบกว้า'}:
        return docs
    weed_lower = weed_name.lower()

    def _mentions(d):
        return weed_lower in (d.metadata.get('herbicides') or '').lower()

    def _is_herbicide(d):
        return 'herbicide' in str(d.metadata.get('category') or '').lower()

    matching = [d for d in docs if _mentions(d)]
    if not matching:
        return docs  # no prune if zero matches — don't break retrieval
    kept = [d for d in docs if _mentions(d) or not _is_herbicide(d)]
    return matching + [d for d in kept if not _mentions(d)]


class TestWeedPrecisionFilter:
    """Post-retrieval filter should prune herbicides not targeting the specific weed."""

    def test_rice_weedy_prunes_non_matching_herbicides(self):
        """Bug reproduction: ข้าวดีด should only surface ทูโฟพอส."""
        docs = [
            _FakeDoc('1', 'Herbicide', 'ข้าวดีด, ข้าวนก'),           # ทูโฟพอส
            _FakeDoc('2', 'Herbicide', 'ข้าวนก, หญ้าดอกขาว'),        # แกนเตอร์
            _FakeDoc('3', 'Herbicide', 'ใบแคบ, ใบกว้าง'),             # อะนิลการ์ด
            _FakeDoc('4', 'Herbicide', 'ใบแคบ, ใบกว้าง'),             # เลกาซี 10
            _FakeDoc('5', 'Herbicide', 'ข้าวนก, หญ้าดอกขาว'),        # ไซฟอบ
        ]
        result = simulate_weed_precision_filter('ข้าวดีด', docs)
        assert [d.id for d in result] == ['1'], \
            f"Expected only ID 1 (ทูโฟพอส), got {[d.id for d in result]}"

    def test_no_match_returns_original(self):
        """If zero products target the weed, don't prune to empty list."""
        docs = [
            _FakeDoc('1', 'Herbicide', 'หญ้าดอกขาว'),
            _FakeDoc('2', 'Herbicide', 'ข้าวนก'),
        ]
        result = simulate_weed_precision_filter('ข้าวดีด', docs)
        assert len(result) == 2

    def test_non_herbicide_docs_preserved(self):
        """Non-Herbicide docs (adjuvant, fertilizer) should not be pruned."""
        docs = [
            _FakeDoc('1', 'Herbicide', 'ข้าวดีด'),
            _FakeDoc('2', 'Herbicide', 'ข้าวนก'),          # pruned
            _FakeDoc('3', 'Fertilizer', ''),                 # kept (not Herbicide)
            _FakeDoc('4', 'Biostimulants', ''),              # kept
        ]
        result = simulate_weed_precision_filter('ข้าวดีด', docs)
        ids = [d.id for d in result]
        assert '1' in ids
        assert '2' not in ids
        assert '3' in ids
        assert '4' in ids

    def test_matching_docs_moved_to_top(self):
        """Matching docs come first, non-matching non-herbicides stay below."""
        docs = [
            _FakeDoc('1', 'Fertilizer', ''),             # non-herbicide
            _FakeDoc('2', 'Herbicide', 'ข้าวดีด'),      # match
            _FakeDoc('3', 'Herbicide', 'ข้าวนก'),       # pruned
        ]
        result = simulate_weed_precision_filter('ข้าวดีด', docs)
        assert [d.id for d in result] == ['2', '1']


class TestStage0WhitelistParity:
    """Ensure test file's weed pattern list stays in sync with orchestrator."""

    def test_patterns_match_orchestrator(self):
        # Read orchestrator source and check all _WEED_PATTERNS_STAGE0 entries
        # appear there — prevents silent drift between test + prod.
        with open(os.path.join(os.path.dirname(__file__), '..',
                               'app/services/rag/orchestrator.py'),
                  encoding='utf-8') as f:
            source = f.read()
        for pattern in _WEED_PATTERNS_STAGE0:
            assert f"'{pattern}'" in source, \
                f"Pattern '{pattern}' missing from orchestrator.py _WEED_PATTERNS_STAGE0"
