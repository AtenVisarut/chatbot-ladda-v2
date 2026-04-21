"""
Crop-specific symptom → disease priors (curated, not LLM-generated).

Problem being solved:
    Generic SYMPTOM_PATHOGEN_MAP gives "ใบจุด" → [เซอโคสปอร่า, แอนแทรคโนส]
    for every crop. But rubber leaf-spot vs. durian leaf-spot vs. corn leaf-spot
    have very different likely causes in Thai agriculture, and recommending
    the wrong fungicide family wastes the farmer's money.

Rules (locked in by tests/test_diagnostic_intent.py):
    1. Every disease canonical listed here MUST already appear in
       DISEASE_PATTERNS or in SYMPTOM_PATHOGEN_MAP's pathogen values.
       No new pathogens are introduced here.
    2. Weights are *relative rank* — used only to order the candidate list
       returned to retrieval. They are NOT probabilities.
    3. Coverage: the 8 crops that account for ~80% of bot traffic.
       Expand only after measuring real query distribution in Railway logs.
    4. No speculation: when a crop-symptom pair is not well-established in
       Thai agronomy references (DOAE, RRIT, ICP product docs), it is OMITTED
       from this table rather than guessed — the generic SYMPTOM_PATHOGEN_MAP
       path handles the fallback.
"""
from __future__ import annotations

# Canonical symptom → word-order variants the user might type.
# Lets the priors table stay readable (keyed by the clean form) while the
# resolver still matches queries like "จุดสีน้ำตาลที่ใบ" (no "ใบจุด" substring).
# Kept in sync with SYMPTOM_PATHOGEN_MAP variants in text_processing.py.
_SYMPTOM_VARIANT_GROUPS: dict[str, list[str]] = {
    "ใบจุด": [
        "ใบจุด", "ใบมีจุด", "ใบเป็นจุด",
        "จุดที่ใบ", "จุดบนใบ",
        "จุดสีน้ำตาล", "จุดน้ำตาล",
    ],
    "ใบร่วง":   ["ใบร่วง", "ใบหลุดร่วง"],
    "ใบไหม้":   ["ใบไหม้", "ใบเป็นแผลไหม้"],
    "ยางไหล":   ["ยางไหล", "น้ำยางไหล"],
    "รากเน่า":  ["รากเน่า"],
    "โคนเน่า":  ["โคนเน่า"],
    "ผลเน่า":   ["ผลเน่า"],
    "ยอดแห้ง":  ["ยอดแห้ง"],
    "เปลือกแตก": ["เปลือกแตก"],
    "หน้ายางเน่า": ["หน้ายางเน่า"],
    "เมล็ดด่าง": ["เมล็ดด่าง"],
    "กาบใบแห้ง": ["กาบใบแห้ง"],
    "ขอบใบแห้ง": ["ขอบใบแห้ง"],
    "เน่าคอรวง": ["เน่าคอรวง"],
    "ใบขีด":    ["ใบขีด"],
    "ราน้ำค้าง": ["ราน้ำค้าง"],
    "ราสนิม":   ["ราสนิม"],
    "ราสีชมพู": ["ราสีชมพู", "ราชมพู"],
    "ลำต้นเน่า": ["ลำต้นเน่า"],
    "ใบขาว":    ["ใบขาว"],
    "แอนแทรคโนส": ["แอนแทรคโนส"],
    "ราแป้ง":   ["ราแป้ง"],
    "ราดำ":     ["ราดำ"],
    "ดอกเน่า":  ["ดอกเน่า"],
    "ทะลายเน่า": ["ทะลายเน่า"],
}


def _symptom_matches_query(canonical_symptom: str, query: str) -> bool:
    """True if any registered variant of `canonical_symptom` appears in query."""
    variants = _SYMPTOM_VARIANT_GROUPS.get(canonical_symptom, [canonical_symptom])
    return any(v in query for v in variants)


# symptom_key → substring matched against the user query
# Each value is a list of (disease_canonical, relative_weight), sorted desc.
CROP_DISEASE_PRIORS: dict[str, dict[str, list[tuple[str, float]]]] = {
    "ยางพารา": {
        "ใบจุด":        [("เซอโคสปอร่า", 0.6), ("แอนแทรคโนส", 0.3), ("ราสนิม", 0.1)],
        "ใบร่วง":       [("ไฟทอปธอร่า", 0.6), ("แอนแทรคโนส", 0.4)],
        "เปลือกแตก":    [("ไฟทอปธอร่า", 1.0)],
        "หน้ายางเน่า":  [("ไฟทอปธอร่า", 1.0)],
        "ยางไหล":       [("ไฟทอปธอร่า", 1.0)],
        "ราสีชมพู":     [("ราสีชมพู", 1.0)],
    },
    "ทุเรียน": {
        "รากเน่า":      [("ไฟทอปธอร่า", 0.9), ("พิเทียม", 0.1)],
        "โคนเน่า":      [("ไฟทอปธอร่า", 0.8), ("ฟิวซาเรียม", 0.2)],
        "ใบจุด":        [("แอนแทรคโนส", 0.6), ("เซอโคสปอร่า", 0.4)],
        "ผลเน่า":       [("แอนแทรคโนส", 0.5), ("ไฟทอปธอร่า", 0.5)],
        "ยอดแห้ง":      [("ไฟทอปธอร่า", 0.6), ("ฟิวซาเรียม", 0.4)],
        "ใบไหม้":       [("ไฟทอปธอร่า", 0.6), ("แอนแทรคโนส", 0.4)],
    },
    "ข้าว": {
        "ใบไหม้":       [("ใบไหม้", 1.0)],
        "เมล็ดด่าง":    [("เมล็ดด่าง", 1.0)],
        "กาบใบแห้ง":    [("กาบใบแห้ง", 1.0)],
        "ขอบใบแห้ง":    [("แบคทีเรีย", 1.0)],
        "เน่าคอรวง":    [("เน่าคอรวง", 1.0)],
        "ใบขีด":        [("ใบขีดสีน้ำตาล", 1.0)],
        "ใบจุด":        [("เซอโคสปอร่า", 0.7), ("แอนแทรคโนส", 0.3)],
    },
    "ข้าวโพด": {
        "ใบไหม้":       [("ใบไหม้แผลใหญ่", 0.7), ("ใบไหม้", 0.3)],
        "ใบจุด":        [("เซอโคสปอร่า", 0.6), ("แอนแทรคโนส", 0.4)],
        "ราน้ำค้าง":    [("ราน้ำค้าง", 1.0)],
        "ราสนิม":       [("ราสนิม", 1.0)],
        "ลำต้นเน่า":    [("ฟิวซาเรียม", 0.7), ("ไฟทอปธอร่า", 0.3)],
        "โคนเน่า":      [("ฟิวซาเรียม", 1.0)],
    },
    "มันสำปะหลัง": {
        "รากเน่า":      [("พิเทียม", 0.5), ("ฟิวซาเรียม", 0.5)],
        "ใบไหม้":       [("แบคทีเรีย", 0.6), ("แอนแทรคโนส", 0.4)],
        "ใบจุด":        [("เซอโคสปอร่า", 0.7), ("แอนแทรคโนส", 0.3)],
        "ลำต้นเน่า":    [("ฟิวซาเรียม", 1.0)],
    },
    "อ้อย": {
        "ราสนิม":       [("ราสนิม", 1.0)],
        "ใบขาว":        [("ใบขาว", 1.0)],
        "ลำต้นเน่า":    [("ฟิวซาเรียม", 1.0)],
        "ใบจุด":        [("เซอโคสปอร่า", 0.7), ("แอนแทรคโนส", 0.3)],
    },
    "มะม่วง": {
        "แอนแทรคโนส":  [("แอนแทรคโนส", 1.0)],
        "ราแป้ง":       [("ราแป้ง", 0.7), ("โอดิอัม", 0.3)],
        "ราดำ":         [("ราดำ", 1.0)],
        "ดอกเน่า":      [("แอนแทรคโนส", 1.0)],
        "ผลเน่า":       [("แอนแทรคโนส", 1.0)],
        "ใบจุด":        [("แอนแทรคโนส", 0.5), ("เซอโคสปอร่า", 0.5)],
    },
    "ปาล์ม": {
        "ทะลายเน่า":    [("แอนแทรคโนส", 1.0)],
        "โคนเน่า":      [("ฟิวซาเรียม", 0.5), ("ไฟทอปธอร่า", 0.5)],
        "ใบจุด":        [("เซอโคสปอร่า", 0.6), ("แอนแทรคโนส", 0.4)],
        "ใบไหม้":       [("แอนแทรคโนส", 1.0)],
    },
}


def resolve_crop_symptom_to_diseases(crop: str, query: str) -> list[str]:
    """
    Look up crop-specific disease candidates ordered by prior weight.

    Returns an empty list when the crop is not in the priors table or when
    no symptom keyword matches — caller must fall back to the generic
    SYMPTOM_PATHOGEN_MAP path.

    Dedupes diseases that appear under multiple symptom keys (the first
    occurrence wins — highest-weight symptom match).
    """
    if not crop or not query:
        return []
    priors = CROP_DISEASE_PRIORS.get(crop)
    if not priors:
        return []

    scored: list[tuple[str, float]] = []
    seen: set[str] = set()
    for symptom_key, ranked in priors.items():
        if _symptom_matches_query(symptom_key, query):
            for disease, weight in ranked:
                if disease not in seen:
                    seen.add(disease)
                    scored.append((disease, weight))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [d for d, _ in scored]
