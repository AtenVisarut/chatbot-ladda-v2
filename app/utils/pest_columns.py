"""
Pest columns helper — utilities for the 5 pest group columns in products2.

products2 splits the old `target_pest` into:
  herbicides, fungicides, insecticides, biostimulant, pgr_hormones

This module provides helpers to:
- Display pest info by category
- Build Supabase OR filters across all 5 columns
- Read combined pest text from a product dict
"""

# Column names in products2
PEST_COLUMNS = ['fungicides', 'insecticides', 'herbicides', 'biostimulant', 'pgr_hormones']

# Thai labels for display
PEST_LABELS = {
    'fungicides': 'สารกำจัดเชื้อรา',
    'insecticides': 'สารกำจัดแมลง',
    'herbicides': 'สารกำจัดวัชพืช',
    'biostimulant': 'สารกระตุ้นชีวภาพ',
    'pgr_hormones': 'ฮอร์โมนพืช',
}


def get_pest_display(product: dict, max_len: int = 0) -> str:
    """Build display string showing pest info by category.

    Example output:
        สารกำจัดเชื้อรา: โรคไหม้, โรคใบจุด
        สารกำจัดแมลง: เพลี้ยกระโดดสีน้ำตาล

    Args:
        product: dict with pest column keys
        max_len: truncate each category value (0 = no limit)
    """
    parts = []
    for col in PEST_COLUMNS:
        val = (product.get(col) or '').strip()
        if val:
            if max_len and len(val) > max_len:
                val = val[:max_len] + "..."
            parts.append(f"{PEST_LABELS[col]}: {val}")
    return "\n".join(parts)


def get_pest_text(product: dict) -> str:
    """Combine all 5 pest columns into a single lowercase string for matching/search."""
    parts = []
    for col in PEST_COLUMNS:
        val = (product.get(col) or '').strip()
        if val:
            parts.append(val)
    return ", ".join(parts)


def get_pest_text_lower(product: dict) -> str:
    """Same as get_pest_text but lowercased."""
    return get_pest_text(product).lower()


def has_pest_data(product: dict) -> bool:
    """Check if product has any pest data in the 5 columns."""
    return any((product.get(col) or '').strip() for col in PEST_COLUMNS)


def build_pest_or_filter(keyword: str) -> str:
    """Build Supabase OR filter string to search keyword across all 5 pest columns.

    Returns e.g.:
        "fungicides.ilike.%โรคไหม้%,insecticides.ilike.%โรคไหม้%,..."
    """
    conditions = [f"{col}.ilike.%{keyword}%" for col in PEST_COLUMNS]
    return ",".join(conditions)


def build_pest_or_conditions(keyword: str) -> list:
    """Return list of OR conditions for a keyword across all 5 pest columns."""
    return [f"{col}.ilike.%{keyword}%" for col in PEST_COLUMNS]


def pest_columns_select() -> str:
    """Return comma-separated column names for SQL SELECT."""
    return ", ".join(PEST_COLUMNS)
