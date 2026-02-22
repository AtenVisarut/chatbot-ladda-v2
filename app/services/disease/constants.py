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
    'ใบไหม้แผลใหญ่', 'ใบขีดสีน้ำตาล', 'ใบจุดสีม่วง',
    'ไฟท็อป', 'ไฟทิป', 'ไฟทอป',
    'ราน้ำค้าง', 'ราสีชมพู', 'ราชมพู', 'ราแป้ง', 'ราสนิม',
    'ราดำ', 'ราเขียว', 'ราขาว', 'ราเทา',
    'ผลเน่า', 'รากเน่า', 'โคนเน่า', 'ลำต้นเน่า', 'เน่าคอรวง',
    'กาบใบแห้ง', 'ขอบใบแห้ง', 'เมล็ดด่าง',
    'หอมเลื้อย', 'ใบติด', 'ใบด่าง', 'ใบหงิก', 'ดอกกระถิน',
    'ใบไหม้', 'ใบจุด',
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
}

# Pre-sorted for matching (longest first)
DISEASE_PATTERNS_SORTED = sorted(DISEASE_PATTERNS, key=len, reverse=True)


def get_canonical(pattern: str) -> str:
    """Return canonical disease name for DB matching."""
    return DISEASE_CANONICAL.get(pattern, pattern)
