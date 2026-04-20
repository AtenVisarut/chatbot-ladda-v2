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


def _tokenize_targets(text: str, min_len: int = 3) -> List[str]:
    """
    Tokenize pest/disease column values but **strip crop prefixes**.
    Format in DB is "<crop> - <pest list>" (e.g. "ทุเรียน - เพลี้ยไฟ เพลี้ยจั๊กจั่น").
    We only want the pest part.
    """
    if not text:
        return []
    tokens = []
    for line in re.split(r"[\n]+", text):
        line = line.strip()
        if not line:
            continue
        # Split "crop - pests" — take only the 2nd half if " - " present
        if " - " in line:
            parts = line.split(" - ", 1)
            if len(parts) == 2:
                line = parts[1]
        tokens.extend(_tokenize_thai(line, min_len=min_len))
    return tokens


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
    """
    if not answer:
        return CapabilityScore(0, "empty answer", {})

    rac = _clean(product.get("chemical_group_rac"))
    if not rac:
        # Product has no rac in DB — skip (full credit)
        return CapabilityScore(
            100, "no rac in DB — full credit", {"rac": 100}
        )

    # Extract group codes from rac (e.g. "กลุ่ม 3A + 4A" → ['3A', '4A'])
    # Also catch "C2", "E", "O + K3" etc.
    codes = re.findall(r"\b[A-Z]?\d+[A-Z]?\b|\b[A-Z]\d?\b", rac)
    # Keep only ones that look like group codes (not random numbers)
    codes = [c for c in codes if re.match(r"^[A-Z]?\d+[A-Z]?$|^[A-Z]\d?$", c)
             and c not in ("I", "A", "D")]  # filter noise

    # Check LLM mentions no-data phrase (bad — this should fail)
    bad_phrases = ["ไม่มีข้อมูล", "ไม่ทราบ", "ไม่ได้ระบุ"]
    # Exception: if LLM says "ไม่ได้ระบุว่าใช้กับ..." (applicability denial, not missing rac)
    # → only penalize if the phrase is about rac/group/moa
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
        # Fallback: check full rac string appears in answer
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

    # Differentiator: product_category, mechanism_of_action, active_ingredient, usage_rate
    cat_a = _clean(product_a.get("product_category"))
    cat_b = _clean(product_b.get("product_category"))
    mechanism_a = _clean(product_a.get("mechanism_of_action"))[:80]
    mechanism_b = _clean(product_b.get("mechanism_of_action"))[:80]

    differentiator_found = False
    # Different categories → answer should show both categories
    if cat_a and cat_b and cat_a.lower() != cat_b.lower():
        if cat_a.lower() in answer.lower() or cat_b.lower() in answer.lower():
            differentiator_found = True
    # Same category → check mechanism or target differences
    if not differentiator_found:
        # Any mechanism word
        mech_tokens = _tokenize_thai(mechanism_a + " " + mechanism_b, min_len=4)
        if any(t in answer for t in mech_tokens[:3]):
            differentiator_found = True
    # Target differences (pest vs disease etc.)
    if not differentiator_found:
        ai_a = _clean(product_a.get("active_ingredient"))
        ai_b = _clean(product_b.get("active_ingredient"))
        if ai_a and ai_b and ai_a != ai_b:
            # Check if any AI-related Thai ingredient name appears
            thai_a = _clean(product_a.get("common_name_th")).split("+")[0].strip()
            thai_b = _clean(product_b.get("common_name_th")).split("+")[0].strip()
            if (thai_a and thai_a in answer) or (thai_b and thai_b in answer):
                differentiator_found = True

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
