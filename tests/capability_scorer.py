"""
Capability Scorer — ให้คะแนน 0-100 ต่อคำตอบ bot ในแต่ละ capability

6 capabilities ที่วัด:
1. ข้อมูลสินค้า (active ingredient, %, formulation)
2. โรค/แมลง/วัชพืช + พืช
3. อัตราใช้ + วิธีใช้
4. MoA / IRAC / FRAC / HRAC
5. จุดเด่น (selling point)
6. เปรียบเทียบสินค้า
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# =============================================================================
# Helpers
# =============================================================================

_FORMULATION_CODES = ("EC", "SC", "WG", "WP", "GR", "SL", "EW", "OL", "ME",
                     "OD", "CS", "DP", "DS", "ZW", "ZC", "WS", "FS")
# Thai equivalents
_FORMULATION_TH = ("ดับเบิลยู.พี.", "ดับเบิ้ลยู.พี.", "ดับเบิลยู.จี.",
                   "ดับเบิ้ลยู.จี.", "เอฟ", "อีซี", "เอสซี")


def _clean(text: Optional[str]) -> str:
    return str(text or "").strip()


def _extract_percents(text: str) -> List[str]:
    """Extract all percentages from a string e.g. 'BIFENTHRIN 5% + IMIDACLOPRID 25%' -> ['5%','25%']"""
    return re.findall(r"\d+(?:\.\d+)?\s*%", text or "")


def _extract_formulation(active_ingredient: str) -> Optional[str]:
    """Extract EC/SC/WP/etc. from end of active_ingredient string"""
    text = active_ingredient or ""
    # Uppercase English codes (word boundary)
    for code in _FORMULATION_CODES:
        if re.search(rf"\b{re.escape(code)}\b", text):
            return code
    # Thai equivalents (no word boundary needed for Thai)
    for code in _FORMULATION_TH:
        if code in text:
            return code
    return None


def _has_number_with_unit(text: str) -> bool:
    """Check if text has '<num> <unit>' where unit is ซีซี/มล./กรัม/กก./ลิตร/ไร่"""
    units = r"(?:ซีซี|มล|มิลลิลิตร|กรัม|กก|กิโลกรัม|ลิตร|ไร่|ออนซ์)"
    # number followed by optional space + unit within a few chars
    return bool(re.search(rf"\d+(?:\.\d+)?\s*\.?\s*{units}", text))


def _contains_any(haystack: str, needles: List[str], threshold: int = 1) -> int:
    """Return number of needles found in haystack (case-insensitive)"""
    if not haystack or not needles:
        return 0
    h = haystack.lower()
    hit = 0
    for n in needles:
        if n and str(n).strip().lower() in h:
            hit += 1
    return hit


def _tokenize_thai(text: str, min_len: int = 3) -> List[str]:
    """Naive tokenizer: split on whitespace + punctuation, keep tokens >= min_len"""
    if not text:
        return []
    # Split on whitespace, comma, slash, newline, tab, parens, bullet, hyphen, dash
    parts = re.split(r"[,/\s\n\t()•\-–—]+", text)
    toks = []
    for p in parts:
        p = p.strip()
        if len(p) >= min_len:
            toks.append(p)
    return toks


_CROP_NAMES = (
    "ข้าว", "ทุเรียน", "อ้อย", "มันสำปะหลัง", "ยางพารา", "ปาล์ม",
    "มะม่วง", "ลำไย", "ลำใย", "ลิ้นจี่", "เงาะ", "มังคุด", "พริก",
    "มะเขือเทศ", "ข้าวโพด", "ถั่ว", "ถั่วฝักยาว", "ผัก", "ผักคะน้า",
    "กล้วย", "มะพร้าว", "ส้ม", "มะนาว", "ฝรั่ง", "หอมแดง", "หอม",
    "กระเทียม", "มะเขือ", "นาข้าว",
)


def _tokenize_targets(text: str, min_len: int = 3) -> List[str]:
    """
    Tokenize pest/disease column values and **strip crop prefixes/suffixes**.

    DB has two common formats:
      "<crop> - <pest list>"              (e.g. "ทุเรียน - เพลี้ยไฟ")
      "<pest>ใน<crop>,<pest>ใน<crop>"     (e.g. "เพลี้ยไฟในส้ม,หนอนชอนใบในถั่วฝักยาว")

    We extract only the pest part and also generate crop-less aliases for the
    "ใน<crop>" case so "เพลี้ยไฟในส้ม" produces both
    "เพลี้ยไฟในส้ม" AND "เพลี้ยไฟ" as tokens.
    """
    if not text:
        return []
    tokens = []
    # Split top level by newline OR comma (DB uses both)
    for chunk in re.split(r"[\n,]+", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        # Format 1: "<crop> - <pest>"
        if " - " in chunk:
            parts = chunk.split(" - ", 1)
            if len(parts) == 2:
                chunk = parts[1]
        # Format 2: "<pest>ใน<crop>" → also keep crop-less pest
        # Strip "ใน<crop>" suffix by longest-match
        for crop in sorted(_CROP_NAMES, key=len, reverse=True):
            suffix = f"ใน{crop}"
            if suffix in chunk:
                pest_only = chunk.replace(suffix, "").strip()
                if len(pest_only) >= min_len:
                    tokens.append(pest_only)
                # also keep the whole "pestในcrop" form
                break
        tokens.extend(_tokenize_thai(chunk, min_len=min_len))
    # dedupe while preserving order
    seen = set()
    unique = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


# =============================================================================
# Scored result type
# =============================================================================

@dataclass
class CapabilityScore:
    score: int                  # 0-100
    reason: str                 # human-readable explanation
    breakdown: Dict[str, int]   # sub-scores per check


# =============================================================================
# Capability 1: Product info (ingredient, %, formulation)
# =============================================================================

def score_product_info(answer: str, product: dict) -> CapabilityScore:
    """
    +25 pts  product_name mentioned
    +25 pts  Thai ingredient (common_name_th) OR active_ingredient mentioned
    +25 pts  at least one correct percentage from active_ingredient appears
    +25 pts  formulation code (EC/SC/WP/...) mentioned
    """
    if not answer:
        return CapabilityScore(0, "empty answer", {})

    product_name = _clean(product.get("product_name"))
    ai = _clean(product.get("active_ingredient"))
    thai_name = _clean(product.get("common_name_th"))

    breakdown = {}
    score = 0

    # Name mention — allow small variation (strip diacritics) for matches
    if product_name and product_name in answer:
        score += 25
        breakdown["product_name"] = 25
    elif product_name and product_name.replace("์", "") in answer.replace("์", ""):
        score += 25
        breakdown["product_name"] = 25
    else:
        breakdown["product_name"] = 0

    # Ingredient mention — thai name first, else English ingredient token
    if thai_name:
        # Split "a + b" → check each part
        thai_tokens = [t.strip() for t in thai_name.split("+") if t.strip()]
        if any(tok in answer for tok in thai_tokens):
            score += 25
            breakdown["thai_ingredient"] = 25
        else:
            # Fallback: English active ingredient words
            eng_tokens = [t.strip() for t in re.findall(r"[A-Z][A-Z\-]{3,}", ai)]
            if any(tok.lower() in answer.lower() for tok in eng_tokens):
                score += 15
                breakdown["thai_ingredient"] = 15
            else:
                breakdown["thai_ingredient"] = 0
    else:
        # no thai name in DB → skip requirement (give full)
        score += 25
        breakdown["thai_ingredient"] = 25

    # Percentage
    expected_pcts = _extract_percents(ai)
    if expected_pcts:
        answer_pcts = _extract_percents(answer)
        matched = sum(1 for p in expected_pcts if p.replace(" ", "") in answer.replace(" ", ""))
        if matched >= len(expected_pcts):
            score += 25
            breakdown["percent"] = 25
        elif matched >= 1:
            score += 15
            breakdown["percent"] = 15
        else:
            breakdown["percent"] = 0
    else:
        # no percent in DB → skip
        score += 25
        breakdown["percent"] = 25

    # Formulation
    formulation = _extract_formulation(ai)
    if formulation:
        if formulation in answer.upper() or formulation in answer:
            score += 25
            breakdown["formulation"] = 25
        else:
            breakdown["formulation"] = 0
    else:
        # no formulation in DB → skip
        score += 25
        breakdown["formulation"] = 25

    reason_parts = [f"{k}={v}" for k, v in breakdown.items()]
    return CapabilityScore(score, "; ".join(reason_parts), breakdown)


# =============================================================================
# Capability 2: Target pest/disease/weed + applicable crops
# =============================================================================

def score_pest_crop(answer: str, product: dict) -> CapabilityScore:
    """
    +50 pts  answer mentions at least one target (pest/disease/weed) from DB
    +50 pts  answer mentions at least one applicable crop from DB
    """
    if not answer:
        return CapabilityScore(0, "empty answer", {})

    breakdown = {}
    score = 0

    # Collect all targets from 5 pest columns + fertilizer/biostimulant/pgr
    target_fields = [
        "insecticides", "fungicides", "herbicides",
        "biostimulant", "pgr_hormones", "fertilizer",
    ]
    target_text = "\n".join(_clean(product.get(f)) for f in target_fields if _clean(product.get(f)))
    target_tokens = _tokenize_targets(target_text, min_len=3)

    if target_tokens:
        matched = sum(1 for t in target_tokens if t in answer)
        if matched >= 2:
            score += 50
            breakdown["target"] = 50
        elif matched >= 1:
            score += 35
            breakdown["target"] = 35
        else:
            breakdown["target"] = 0
    else:
        # Product has no target data at all (e.g. pure fertilizer) → skip
        score += 50
        breakdown["target"] = 50

    # Applicable crops
    crops = _clean(product.get("applicable_crops"))
    if crops:
        crop_tokens = _tokenize_thai(crops, min_len=2)
        matched = sum(1 for c in crop_tokens if c in answer)
        if matched >= 1:
            score += 50
            breakdown["crop"] = 50
        else:
            breakdown["crop"] = 0
    else:
        score += 50
        breakdown["crop"] = 50

    reason = f"target={breakdown['target']}/50, crop={breakdown['crop']}/50"
    return CapabilityScore(score, reason, breakdown)


# =============================================================================
# Capability 3: Usage rate + how to use
# =============================================================================

def score_usage_rate(answer: str, product: dict) -> CapabilityScore:
    """
    +50 pts  answer contains a number+unit (from usage_rate)
    +50 pts  answer contains usage verb (ผสม/ฉีด/พ่น/ราด/ใช้)
    """
    if not answer:
        return CapabilityScore(0, "empty answer", {})

    breakdown = {}
    score = 0

    rate = _clean(product.get("usage_rate"))
    how = _clean(product.get("how_to_use"))

    # Rate: check if expected number appears in answer
    if rate:
        # Extract numbers from DB usage_rate
        nums = re.findall(r"\d+(?:[\-–]\d+)?", rate)
        if nums:
            matched = sum(1 for n in nums if n in answer)
            if matched >= 1:
                score += 50
                breakdown["rate"] = 50
            else:
                # At least check if unit is mentioned
                if _has_number_with_unit(answer):
                    score += 25
                    breakdown["rate"] = 25
                else:
                    breakdown["rate"] = 0
        else:
            # No numeric rate in DB → check narrative match
            if _has_number_with_unit(answer):
                score += 50
                breakdown["rate"] = 50
            else:
                score += 25
                breakdown["rate"] = 25  # partial — answer shouldn't be expected to have numbers
    else:
        score += 50
        breakdown["rate"] = 50

    # Usage verb — need specific action verb (not just "ใช้" which is too generic)
    usage_verbs = ["ผสม", "ฉีดพ่น", "ฉีด", "พ่น", "ราด", "หยด", "รด", "หว่าน", "คราด", "คลุก"]
    if any(v in answer for v in usage_verbs):
        score += 50
        breakdown["verb"] = 50
    else:
        breakdown["verb"] = 0

    reason = f"rate={breakdown['rate']}/50, verb={breakdown['verb']}/50"
    return CapabilityScore(score, reason, breakdown)


# =============================================================================
# Capability 4: MoA / IRAC / FRAC / HRAC
# =============================================================================

def score_moa(answer: str, product: dict) -> CapabilityScore:
    """
    +100 pts  answer contains the chemical_group_rac value (or its core group code)

    Special cases:
    - Narrative rac (e.g. "ควบคุมการเจริญเติบโตของพืช" for PGR) — accept if
      answer mentions PGR semantics (ควบคุม/เจริญเติบโต/ฮอร์โมน/PGR)
    """
    if not answer:
        return CapabilityScore(0, "empty answer", {})

    rac = _clean(product.get("chemical_group_rac"))
    if not rac:
        # Product has no rac in DB — skip (full credit)
        return CapabilityScore(
            100, "no rac in DB — full credit", {"rac": 100}
        )

    # Narrative rac: no numeric group code (e.g. "ควบคุมการเจริญเติบโตของพืช")
    # → score based on semantic match instead
    is_narrative = bool(re.search(r"ควบคุมการเจริญเติบโต|กลุ่มจิบเบอเรลลิน|Plant Growth|PGR", rac, re.IGNORECASE))
    if is_narrative:
        narrative_keywords = ["ควบคุม", "เจริญเติบโต", "ฮอร์โมน", "PGR",
                              "Plant Growth Regulator", "จิบเบอเรลลิน",
                              "ยับยั้ง", "ใบอ่อน"]
        matched = sum(1 for k in narrative_keywords if k.lower() in answer.lower())
        if matched >= 2:
            return CapabilityScore(
                100, f"narrative rac — {matched} keywords matched", {"rac": 100}
            )
        elif matched >= 1:
            return CapabilityScore(
                60, f"narrative rac — only {matched} keyword", {"rac": 60}
            )
        return CapabilityScore(
            0, "narrative rac — no semantic match", {"rac": 0}
        )

    # Extract group codes from rac (e.g. "กลุ่ม 3A + 4A" → ['3A', '4A'])
    codes = re.findall(r"\b[A-Z]?\d+[A-Z]?\b|\b[A-Z]\d?\b", rac)
    codes = [c for c in codes if re.match(r"^[A-Z]?\d+[A-Z]?$|^[A-Z]\d?$", c)
             and c not in ("I", "A", "D")]

    # Check LLM mentions no-data phrase
    bad_phrases = ["ไม่มีข้อมูล", "ไม่ทราบ", "ไม่ได้ระบุ"]
    rac_context_near_denial = False
    for bp in bad_phrases:
        if bp in answer:
            idx = answer.find(bp)
            window = answer[max(0, idx-30):idx+60]
            if any(kw in window.lower() for kw in ("irac", "frac", "hrac", "moa", "กลุ่ม", "rac")):
                rac_context_near_denial = True
                break

    if rac_context_near_denial:
        return CapabilityScore(0, "LLM said 'no data' about MoA", {"rac": 0})

    if not codes:
        if rac in answer:
            return CapabilityScore(100, "exact rac match", {"rac": 100})
        return CapabilityScore(0, f"rac {rac!r} not matched", {"rac": 0})

    matched = sum(1 for c in codes if c in answer)
    if matched >= len(codes):
        return CapabilityScore(100, f"all codes matched: {codes}", {"rac": 100})
    elif matched >= 1:
        return CapabilityScore(
            60, f"{matched}/{len(codes)} codes matched: {codes}", {"rac": 60}
        )
    else:
        return CapabilityScore(0, f"no codes matched: {codes}", {"rac": 0})


# =============================================================================
# Capability 5: Selling point
# =============================================================================

def score_selling_point(answer: str, product: dict) -> CapabilityScore:
    """
    +100 pts  answer contains >=50% of key terms from selling_point
    """
    if not answer:
        return CapabilityScore(0, "empty answer", {})

    selling = _clean(product.get("selling_point"))
    if not selling:
        return CapabilityScore(
            100, "no selling_point in DB — full credit", {"selling": 100}
        )

    # Check for bad phrase (LLM said no data)
    bad_phrases = ["ไม่มีข้อมูลจุดเด่น", "ไม่มีข้อมูลเรื่องจุดเด่น"]
    if any(bp in answer for bp in bad_phrases):
        return CapabilityScore(0, "LLM said 'no selling point'", {"selling": 0})

    # Tokenize selling_point into meaningful words (length >=4 Thai, >=3 English)
    tokens = _tokenize_thai(selling, min_len=4)
    if not tokens:
        # Selling point too short — just check the whole string
        if selling[:30] in answer:
            return CapabilityScore(100, "selling matched", {"selling": 100})
        return CapabilityScore(50, "no token match", {"selling": 50})

    matched = sum(1 for t in tokens if t in answer)
    ratio = matched / max(len(tokens), 1)

    if ratio >= 0.5:
        return CapabilityScore(100, f"{matched}/{len(tokens)} tokens", {"selling": 100})
    elif ratio >= 0.25:
        return CapabilityScore(70, f"{matched}/{len(tokens)} tokens", {"selling": 70})
    elif matched >= 1:
        return CapabilityScore(40, f"{matched}/{len(tokens)} tokens", {"selling": 40})
    else:
        return CapabilityScore(0, "no tokens matched", {"selling": 0})


# =============================================================================
# Capability 6: Comparison (both products mentioned + differentiator)
# =============================================================================

def score_comparison(answer: str, product_a: dict, product_b: dict) -> CapabilityScore:
    """
    +50 pts  both product names mentioned
    +50 pts  differentiator present (category / mechanism / target / rate)
    """
    if not answer:
        return CapabilityScore(0, "empty answer", {})

    breakdown = {}
    score = 0

    name_a = _clean(product_a.get("product_name"))
    name_b = _clean(product_b.get("product_name"))

    has_a = name_a in answer or name_a.replace("์", "") in answer.replace("์", "")
    has_b = name_b in answer or name_b.replace("์", "") in answer.replace("์", "")

    if has_a and has_b:
        score += 50
        breakdown["both_names"] = 50
    elif has_a or has_b:
        score += 25
        breakdown["both_names"] = 25
    else:
        breakdown["both_names"] = 0

    # Differentiator: any of category / ingredient / mechanism / rate / pest
    cat_a = _clean(product_a.get("product_category"))
    cat_b = _clean(product_b.get("product_category"))
    thai_a_tokens = [t.strip() for t in _clean(product_a.get("common_name_th")).split("+") if t.strip()]
    thai_b_tokens = [t.strip() for t in _clean(product_b.get("common_name_th")).split("+") if t.strip()]
    mechanism_a = _clean(product_a.get("mechanism_of_action"))
    mechanism_b = _clean(product_b.get("mechanism_of_action"))
    rate_a = _clean(product_a.get("usage_rate"))
    rate_b = _clean(product_b.get("usage_rate"))

    differentiator_found = False
    reason_bits = []

    # 1. Different categories → answer mentions at least one category
    if cat_a and cat_b and cat_a.lower() != cat_b.lower():
        if cat_a.lower() in answer.lower() or cat_b.lower() in answer.lower():
            differentiator_found = True
            reason_bits.append("category")

    # 2. Different ingredients (same or cross category): Thai ingredient names from each
    if not differentiator_found and thai_a_tokens and thai_b_tokens:
        a_found = any(t in answer for t in thai_a_tokens if len(t) >= 3)
        b_found = any(t in answer for t in thai_b_tokens if len(t) >= 3)
        if a_found and b_found:
            differentiator_found = True
            reason_bits.append("both_ingredients")

    # 3. Mechanism of action keywords
    if not differentiator_found:
        mech_tokens = _tokenize_thai(mechanism_a + "\n" + mechanism_b, min_len=5)
        if sum(1 for t in mech_tokens[:5] if t in answer) >= 2:
            differentiator_found = True
            reason_bits.append("mechanism")

    # 4. Different rates mentioned
    if not differentiator_found and rate_a and rate_b and rate_a != rate_b:
        nums_a = set(re.findall(r"\d+", rate_a))
        nums_b = set(re.findall(r"\d+", rate_b))
        a_shown = any(n in answer for n in nums_a)
        b_shown = any(n in answer for n in nums_b)
        if a_shown and b_shown and (nums_a & set(re.findall(r"\d+", answer))) != (nums_b & set(re.findall(r"\d+", answer))):
            differentiator_found = True
            reason_bits.append("rates")

    if differentiator_found:
        score += 50
        breakdown["differentiator"] = 50
    else:
        breakdown["differentiator"] = 0

    reason = f"both_names={breakdown['both_names']}/50, diff={breakdown['differentiator']}/50"
    return CapabilityScore(score, reason, breakdown)


# =============================================================================
# Question builder
# =============================================================================

def build_questions(product: dict, comparison_partner: Optional[dict] = None) -> Dict[int, str]:
    """Return dict {capability_id: question_text} for a given product"""
    name = _clean(product.get("product_name")) or "สินค้า"
    questions = {
        1: f"{name} สารสำคัญคืออะไร formulation แบบไหน",
        2: f"{name} ใช้กับพืชอะไรได้บ้าง กำจัดอะไร",
        3: f"{name} อัตราใช้เท่าไหร่ ผสมยังไง",
        4: f"{name} อยู่กลุ่ม IRAC/FRAC/HRAC อะไร",
        5: f"จุดเด่นของ {name} คืออะไร",
    }
    if comparison_partner:
        partner_name = _clean(comparison_partner.get("product_name")) or "สินค้าอื่น"
        questions[6] = f"{name} กับ {partner_name} ต่างกันยังไง"
    return questions
