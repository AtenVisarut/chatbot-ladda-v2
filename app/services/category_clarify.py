"""
Open-category clarification.

When a user asks an open-ended category query without specifying a crop
(e.g. "แนะนำยาฆ่าหญ้าหน่อย", "อยากได้กำจัดแมลง", "มีอาหารพืชไหม"),
ask one follow-up to collect crop (+ symptom for insect/fungus/fert) so the
RAG pipeline can rank products for the right crop instead of category-wide.

Hybrid UX:
  - Herbicide asks crop only (short list + "ทั่วไป" escape hatch).
  - Insecticide/Fungicide/Fertilizer ask crop + symptom/stage with "เช่น"
    hints — herbicide names are usually applied pre-emergent so symptoms
    aren't as relevant, but pest/disease/fert need the target.

Trigger gating is deliberately conservative:
  - Category keyword must appear.
  - No crop detected in the query (via PlantRegistry).
  - Query under 40 chars (long queries usually have enough context already).
  - Query must not already contain an "escape hatch" word like "ทั่วไป".
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from app.services.plant.registry import PlantRegistry

# Key used in conversation_state to carry the pending category between turns.
PENDING_CLARIFY_KEY = "pending_category_clarify"

# Fallback crop list when PlantRegistry isn't loaded yet (rare — startup race
# or DB unreachable). Keeps clarify from over-triggering on cold start.
_FALLBACK_PLANTS = (
    "มะม่วงหิมพานต์", "ปาล์มน้ำมัน", "ข้าวเหนียว",
    "ทุเรียน", "ข้าวโพด", "ข้าว", "มันสำปะหลัง", "อ้อย", "ยางพารา", "ปาล์ม",
    "มะม่วง", "ลำไย", "ลิ้นจี่", "เงาะ", "มังคุด", "พริก", "มะเขือเทศ",
    "ส้มโอ", "ส้ม", "มะนาว", "กล้วย", "มะพร้าว", "ฝรั่ง", "ชมพู่", "สับปะรด",
)


def _extract_crop(question: str) -> Optional[str]:
    reg = PlantRegistry.get_instance()
    if reg.loaded:
        return reg.extract(question)
    q = question.lower()
    for p in _FALLBACK_PLANTS:  # longest-first already
        if p.lower() in q:
            return p
    return None


class CategoryType(str, Enum):
    HERBICIDE = "herbicide"
    INSECTICIDE = "insecticide"
    FUNGICIDE = "fungicide"
    FERTILIZER = "fertilizer"


CATEGORY_KEYWORDS: dict[CategoryType, tuple[str, ...]] = {
    CategoryType.HERBICIDE: (
        "ยาฆ่าหญ้า", "ฆ่าหญ้า", "กำจัดวัชพืช", "ยาคุมหญ้า", "คุมหญ้า",
        "ยาฉีดหญ้า", "สารกำจัดวัชพืช",
    ),
    CategoryType.INSECTICIDE: (
        "ยาฆ่าแมลง", "ฆ่าแมลง", "กำจัดแมลง", "ยาแมลง",
        "สารกำจัดแมลง", "ยาฆ่าหนอน", "กำจัดหนอน", "ยาฆ่าเพลี้ย",
        "กำจัดเพลี้ย",
    ),
    CategoryType.FUNGICIDE: (
        "ยาเชื้อรา", "ยากันรา", "ยาโรคพืช", "กำจัดเชื้อรา",
        "สารกำจัดเชื้อรา", "ยาฆ่าเชื้อรา", "ยารักษาโรคพืช",
    ),
    CategoryType.FERTILIZER: (
        "ปุ๋ย", "อาหารพืช", "สารอาหารพืช", "ธาตุอาหาร",
        "สารอาหาร", "ฮอร์โมน", "ฮอร์โมนพืช", "อาหารเสริมพืช",
    ),
}


CATEGORY_CLARIFY_MESSAGES: dict[CategoryType, str] = {
    CategoryType.HERBICIDE: (
        "น้องลัดดารบกวนถามก่อนนะคะ จะใช้กับพืชชนิดไหนคะ? 🌾\n"
        "เช่น \"ข้าว\" หรือ \"อ้อย\" ก็พอค่ะ"
    ),
    CategoryType.INSECTICIDE: (
        "รบกวนบอกพืชและแมลงที่เจอให้น้องลัดดาหน่อยนะคะ 🌱\n"
        "เช่น \"ข้าวใช้กับหนอน\""
    ),
    CategoryType.FUNGICIDE: (
        "รบกวนบอกพืชและอาการที่เจอให้น้องลัดดาหน่อยนะคะ 🍃\n"
        "เช่น \"ทุเรียนกำจัดไฟทอป\""
    ),
    CategoryType.FERTILIZER: (
        "รบกวนบอกพืชและระยะที่ใช้ให้น้องลัดดาหน่อยนะคะ 🌾\n"
        "เช่น \"ข้าวแตกกอไม่ดี\""
    ),
}


_CATEGORY_LABEL: dict[CategoryType, str] = {
    CategoryType.HERBICIDE: "ยาฆ่าหญ้า",
    CategoryType.INSECTICIDE: "ยาฆ่าแมลง",
    CategoryType.FUNGICIDE: "ยากำจัดเชื้อรา",
    CategoryType.FERTILIZER: "ปุ๋ย",
}

_ESCAPE_WORDS = ("ทั่วไป", "ทุกชนิด", "ทุกพืช", "ทุกอย่าง")
_MAX_TRIGGER_LEN = 40


def detect_open_category_query(query: str) -> Optional[CategoryType]:
    """
    Return the CategoryType if the query is an open category request that
    should be clarified, else None.

    Gating:
      - matches category keyword
      - no crop detected
      - query length < 40 chars (longer queries usually have own context)
      - no escape word ("ทั่วไป" etc.)
    """
    if not query:
        return None
    q = query.strip().lower()
    if len(q) >= _MAX_TRIGGER_LEN:
        return None
    if any(esc in q for esc in _ESCAPE_WORDS):
        return None

    matched: Optional[CategoryType] = None
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            matched = category
            break
    if matched is None:
        return None

    if _extract_crop(query):
        return None

    return matched


def get_clarify_message(category: CategoryType) -> str:
    return CATEGORY_CLARIFY_MESSAGES[category]


def resume_query_from_clarify(category: CategoryType, user_reply: str) -> str:
    """
    Merge the user's clarify reply into a new query for the RAG pipeline.

    - Herbicide: user usually types just a crop (or "ทั่วไป"). Build a
      template like "แนะนำยาฆ่าหญ้าในข้าว" or keep category-only.
    - Other categories: user typically types "crop + symptom/stage" which
      is already a well-formed RAG query; pass through. If the reply is
      short (only a crop), prepend the category label so the pipeline
      still ranks by category.
    """
    reply = (user_reply or "").strip()
    if not reply:
        return _CATEGORY_LABEL[category]

    reply_l = reply.lower()
    if any(esc in reply_l for esc in _ESCAPE_WORDS):
        return f"แนะนำ{_CATEGORY_LABEL[category]}ทั่วไป"

    if category is CategoryType.HERBICIDE:
        if _extract_crop(reply):
            return f"แนะนำยาฆ่าหญ้าใน{reply}"
        return f"แนะนำยาฆ่าหญ้า {reply}"

    label = _CATEGORY_LABEL[category]
    if label in reply:
        return reply
    return f"{label} {reply}"
