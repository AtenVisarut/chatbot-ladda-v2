"""
Single source of truth for disease patterns + canonical mapping.

All disease detection across the pipeline imports from here.
Used by: orchestrator.py (Stage 0), retrieval_agent.py, response_generator_agent.py
"""

# Every disease pattern the pipeline recognises — sorted longest-first for matching
DISEASE_PATTERNS = [
    'ไฟท็อปธอร่า', 'ไฟทอปธอร่า', 'ไฟท็อปโทร่า', 'ไฟธอปทอร่า',
    'แอนแทรคโนส', 'แอนแทคโนส', 'แอคแทคโนส',
    'ฟิวซาเรียม', 'ฟิวสาเรียม', 'ฟูซาเรียม', 'ฟอซาเรียม',
    'ใบไหม้แผลใหญ่', 'ใบขีดสีน้ำตาล', 'ใบจุดสีน้ำตาล', 'ใบจุดสีม่วง', 'ใบจุดสนิม',
    'ไฟท็อป', 'ไฟทิป', 'ไฟทอป',
    'ราน้ำค้าง', 'ราสีชมพู', 'ราชมพู', 'ราแป้ง', 'ราสนิม',
    'ราดำ', 'ราเขียว', 'ราขาว', 'ราเทา',
    'ผลเน่า', 'รากเน่า', 'โคนเน่า', 'ลำต้นเน่า', 'เน่าคอรวง',
    'กาบใบแห้ง', 'ขอบใบแห้ง', 'เมล็ดด่าง',
    'หอมเลื้อย', 'ใบติด', 'ใบด่าง', 'ใบหงิก', 'ดอกกระถิน',
    'ใบเหี่ยว', 'ใบขาว',   # เพิ่ม 2026-03-19
    'แบคทีเรีย',            # เพิ่ม 2026-03-19: bacterial diseases
    'ใบไหม้', 'ใบจุด',
    'ใบจุ',  # common typo: ใบจุด ขาด ด
    # เพิ่ม 2026-04-21: word-order variants ของ "ใบจุด*" family
    # (ใบร่วง-family เจตนาไม่เพิ่มที่นี่ — มันอยู่ใน NUTRIENT_KEYWORDS แล้ว
    #  และ SYMPTOM_PATHOGEN_MAP handle "ใบหลุดร่วง" ได้แล้ว)
    'จุดสีน้ำตาล', 'จุดน้ำตาล',
    'จุดที่ใบ', 'จุดบนใบ', 'ใบมีจุด', 'ใบเป็นจุด',
]

# Variant → canonical DB name
DISEASE_CANONICAL = {
    'ไฟทิป': 'ไฟท็อป', 'ไฟทอป': 'ไฟท็อป',
    'ไฟทอปธอร่า': 'ไฟท็อปธอร่า', 'ไฟท็อปโทร่า': 'ไฟท็อปธอร่า',
    'ไฟธอปทอร่า': 'ไฟท็อปธอร่า',
    'แอนแทคโนส': 'แอนแทรคโนส', 'แอคแทคโนส': 'แอนแทรคโนส',
    'ฟิวสาเรียม': 'ฟิวซาเรียม', 'ฟูซาเรียม': 'ฟิวซาเรียม',
    'ฟอซาเรียม': 'ฟิวซาเรียม',
    'ราชมพู': 'ราสีชมพู',
    'ใบจุ': 'ใบจุด',  # typo: ขาด ด
    # เพิ่ม 2026-04-21: word-order variants → existing canonicals
    'จุดสีน้ำตาล': 'ใบจุดสีน้ำตาล',
    'จุดน้ำตาล': 'ใบจุดสีน้ำตาล',
    'จุดที่ใบ': 'ใบจุด',
    'จุดบนใบ': 'ใบจุด',
    'ใบมีจุด': 'ใบจุด',
    'ใบเป็นจุด': 'ใบจุด',
}

# Pre-sorted for matching (longest first)
DISEASE_PATTERNS_SORTED = sorted(DISEASE_PATTERNS, key=len, reverse=True)


def get_canonical(pattern: str) -> str:
    """Return canonical disease name for DB matching."""
    return DISEASE_CANONICAL.get(pattern, pattern)
