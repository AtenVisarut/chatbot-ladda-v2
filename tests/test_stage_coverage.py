"""
Stage-vocabulary coverage tests.

Background (Railway log 2026-04-21):
  T1: user "เพลี้ยกระโดดข้าวใช้อะไรดี" → bot: 5 insecticides + asks stage
      ("เช่น ต้นกล้า/แตกกอ/ตั้งท้อง/ออกรวง/สุก/เก็บเกี่ยว")
  T2: user "แตกกอ" → bot: "ไม่มีข้อมูลสินค้าที่เหมาะสมในระบบ" ❌

Root causes:
  1. "แตกกอ" missing from orchestrator._STAGE_WORDS → Stage -1 merge missed
  2. "แตกกอ","ออกรวง","ตั้งท้อง" listed in NUTRIENT_KEYWORDS → pure stage reply
     gets classified as nutrient → drops original pest context
  3. _CROP_STAGES references stages (แตกกอ, ตั้งท้อง, ออกรวง, สุก) that the bot
     offers as examples, but downstream lists don't cover them → drift

These tests lock in:
  a) Every stage ever offered in _CROP_STAGES is recognized as a stage word
     (so Stage -1 clarification merge fires on user's reply).
  b) Pure stage words are NOT misclassified as nutrient.
  c) Compound nutrient intents ("เร่งแตกกอ") stay classified as nutrient.
  d) The four stage-related vocabularies (orchestrator._STAGE_WORDS,
     response_generator_agent._known_stage_keywords, _CROP_STAGES,
     tests/test_best_pick_clarify.py) stay in sync.
"""
from __future__ import annotations

import inspect
import re

import pytest

from app.services.chat.handler import (
    NUTRIENT_KEYWORDS,
    detect_problem_type,
    detect_problem_types,
)
from app.services.rag import orchestrator, response_generator_agent


# ── Helpers ─────────────────────────────────────────────────────────

def _extract_crop_stages() -> dict[str, list[str]]:
    """Pull the _CROP_STAGES literal out of response_generator_agent source
    and return {crop: [stage, ...]}. Parsing source keeps this test robust
    if _CROP_STAGES is nested inside a method (not importable).
    """
    src = inspect.getsource(response_generator_agent)
    m = re.search(r"_CROP_STAGES\s*=\s*\{([^}]+)\}", src, re.DOTALL)
    assert m, "Could not locate _CROP_STAGES literal in response_generator_agent.py"
    body = m.group(1)
    crops: dict[str, list[str]] = {}
    for line in body.splitlines():
        row = re.match(r'\s*"([^"]+)"\s*:\s*"([^"]+)"\s*,', line)
        if not row:
            continue
        crop = row.group(1)
        stages = [s.strip() for s in row.group(2).split("/")]
        crops[crop] = [s for s in stages if s]
    assert crops, "Parsed _CROP_STAGES is empty — regex likely broke"
    return crops


def _extract_known_stage_keywords() -> tuple[str, ...]:
    """Pull the _known_stage_keywords literal from response_generator_agent.
    Nested inside _generate_llm_response, so source-parse."""
    src = inspect.getsource(
        response_generator_agent.ResponseGeneratorAgent._generate_llm_response
    )
    m = re.search(r"_known_stage_keywords\s*=\s*\(([^)]+)\)", src, re.DOTALL)
    assert m, "Could not locate _known_stage_keywords literal"
    return tuple(re.findall(r"'([^']+)'", m.group(1)))


def _word_covered(stage: str, vocab: tuple[str, ...]) -> bool:
    """True if any vocab entry is a substring of stage (or vice versa).
    Substring match is how the production code detects stage presence:
      `any(kw in query for kw in _STAGE_WORDS)`.
    """
    return any(w in stage for w in vocab)


# ── 1. Sync between _CROP_STAGES and downstream vocabularies ──────

CROP_STAGES = _extract_crop_stages()


def test_crop_stages_has_expected_crops():
    """Rice must be present — it's the crop that triggered the bug."""
    assert "ข้าว" in CROP_STAGES, "Rice (ข้าว) missing from _CROP_STAGES"
    # Rice stages the bot actually offers in its ask-back
    rice = CROP_STAGES["ข้าว"]
    for stage in ("ต้นกล้า", "แตกกอ", "ตั้งท้อง", "ออกรวง", "สุก", "เก็บเกี่ยว"):
        assert stage in rice, (
            f"Rice stage {stage!r} missing from _CROP_STAGES['ข้าว'] = {rice}. "
            f"If bot offers it as an example, downstream must recognize it."
        )


@pytest.mark.parametrize(
    "crop,stage",
    [(crop, stage) for crop, stages in CROP_STAGES.items() for stage in stages],
)
def test_every_crop_stage_recognized_by_orchestrator(crop: str, stage: str):
    """
    For every stage offered in _CROP_STAGES — when user replies with just
    that stage, the orchestrator's _STAGE_WORDS must match it so Stage -1
    clarification merge triggers.
    """
    assert _word_covered(stage, orchestrator._STAGE_WORDS), (
        f"Stage {stage!r} (offered for {crop!r}) not in orchestrator._STAGE_WORDS. "
        f"User reply {stage!r} would miss Stage -1 merge and get routed as "
        f"a brand-new query — losing the pest/disease context from the prior turn."
    )


@pytest.mark.parametrize(
    "crop,stage",
    [(crop, stage) for crop, stages in CROP_STAGES.items() for stage in stages],
)
def test_every_crop_stage_known_by_response_generator(crop: str, stage: str):
    """
    Every stage in _CROP_STAGES must be recognized by
    response_generator_agent's _known_stage_keywords — otherwise best-pick
    will ask for stage AGAIN even after user has replied with one.
    """
    vocab = _extract_known_stage_keywords()
    assert _word_covered(stage, vocab), (
        f"Stage {stage!r} (offered for {crop!r}) not in _known_stage_keywords. "
        f"Best-pick flow would fail to notice stage was already provided."
    )


# ── 2. Pure stage replies must not route as nutrient ─────────────

# Explicit allowlist of stage replies users realistically send. Derived
# from _CROP_STAGES but pinned here so a future accidental edit to
# _CROP_STAGES doesn't silently narrow this safety test.
PURE_STAGE_REPLIES = [
    # Rice — the bug case
    "แตกกอ", "ตั้งท้อง", "ออกรวง", "สุก", "เก็บเกี่ยว",
    # Corn / beans
    "ก่อนออกดอก", "ติดฝัก", "ฝักแก่",
    # Sugarcane
    "ยืดปล้อง",
    # Cassava
    "สร้างหัว",
    # Onion / garlic / potato
    "ลงหัว",
    # Fruit trees
    "ใบอ่อน", "แตกใบ", "ออกดอก", "ติดผล", "ผลอ่อน", "ผลแก่",
    "หลังเก็บเกี่ยว",
    # Seedling / vegetables
    "ต้นกล้า", "ต้นอ่อน", "ต้นเล็ก", "เพาะกล้า",
    # Rubber
    "ให้น้ำยาง",
]


@pytest.mark.parametrize("stage_reply", PURE_STAGE_REPLIES)
def test_pure_stage_reply_not_classified_as_nutrient(stage_reply: str):
    """
    A user replying with just a stage word (after bot asked for it) must
    NOT be classified as a nutrient topic. If it is, the orchestrator
    drops the previously-identified product and clears conversation state
    — which is the exact bug the Railway log captured.
    """
    problem_type = detect_problem_type(stage_reply)
    assert problem_type != "nutrient", (
        f"Stage reply {stage_reply!r} classified as {problem_type!r}. "
        f"Pure stage words must not match NUTRIENT_KEYWORDS, or Stage -1 "
        f"clarification merge would be overridden by topic-change logic."
    )


@pytest.mark.parametrize("stage_reply", PURE_STAGE_REPLIES)
def test_pure_stage_reply_has_no_problem_type(stage_reply: str):
    """
    Pure stage words are neutral phenology — they describe timing, not
    the user's actual problem. detect_problem_types should return []
    (empty) so Stage -1 merge can decide the route.
    """
    types = detect_problem_types(stage_reply)
    assert types == [], (
        f"Stage reply {stage_reply!r} classified as {types!r}. "
        f"Expected [] (neutral) so clarification-merge can prepend root topic."
    )


# ── 3. Nutrient intent (compound) must still route as nutrient ──

NUTRIENT_COMPOUND_QUERIES = [
    "เร่งแตกกอ",          # nutrient-boost tillering
    "เร่งออกรวง",          # nutrient-boost heading
    "เร่งตั้งท้อง",        # nutrient-boost booting
    "บำรุงข้าวช่วงแตกกอ",   # composed: บำรุง + ช่วง + แตกกอ
    "ปุ๋ยเร่งแตกกอ",
    "ขาดธาตุตอนแตกกอ",
]


@pytest.mark.parametrize("query", NUTRIENT_COMPOUND_QUERIES)
def test_nutrient_compound_still_routes_as_nutrient(query: str):
    """
    Removing bare stage words from NUTRIENT_KEYWORDS must NOT break
    legitimate nutrient-intent queries that compose "เร่ง/บำรุง/ปุ๋ย" with
    a stage word. Those compound phrases are what farmers actually send
    when they want a nutrient recommendation.
    """
    types = detect_problem_types(query)
    assert "nutrient" in types, (
        f"Nutrient compound {query!r} lost nutrient classification. "
        f"Got: {types!r}. Compound phrases like 'เร่ง+stage' must stay routable."
    )


def test_nutrient_keywords_no_bare_phenology():
    """
    Regression guard: NUTRIENT_KEYWORDS must not contain bare stage words.
    They belong to phenology (plant timing), not nutrient deficiency.
    """
    forbidden = {
        # Rice phenology (bug origin 2026-04-21)
        "แตกกอ", "ออกรวง", "ตั้งท้อง", "สุก", "เก็บเกี่ยว",
        # Generic stages that should NOT imply nutrient intent alone
        "ติดดอก", "ติดผล", "ออกดอก", "ผลอ่อน", "ผลแก่",
        # Too-vague verb
        "เร่ง",
    }
    found = forbidden & set(NUTRIENT_KEYWORDS)
    assert not found, (
        f"Bare stage/vague words found in NUTRIENT_KEYWORDS: {found}. "
        f"These cause pure-stage replies to misroute as new nutrient topics. "
        f"Use compound forms like 'เร่งแตกกอ' instead."
    )


# ── 4. Stage -1 merge simulation (orchestrator logic) ──────────

def _simulates_stage_minus_one_merge(query: str, context: str) -> bool:
    """Re-creates the orchestrator Stage -1 condition so we can assert
    it triggers without needing to run the async pipeline."""
    _is_short_stage_reply = (
        len(query.strip()) < 30
        and any(kw in query for kw in orchestrator._STAGE_WORDS)
    )
    _bot_asked = (
        "ขอทราบข้อมูลเพิ่มเติม" in context
        or ("ระยะของ" in context and "ตอนนี้" in context)
        or "ระยะของวัชพืช" in context
        or "ใช้กับพืชอะไร" in context
    )
    return _is_short_stage_reply and _bot_asked


@pytest.mark.parametrize("stage_reply", PURE_STAGE_REPLIES)
def test_stage_minus_one_fires_for_every_pure_stage(stage_reply: str):
    """
    Simulate: bot previously asked "ระยะของข้าวตอนนี้...", user replies
    with a pure stage word. Stage -1 must fire for every single stage
    in our allowlist. If one misses, that crop's users get the buggy flow.
    """
    bot_context = (
        "ผู้ใช้: เพลี้ยกระโดดข้าวใช้อะไรดี\n"
        "น้องลัดดา: เพื่อแนะนำสินค้าที่เหมาะสมที่สุด ขอทราบข้อมูลเพิ่มเติมค่ะ\n"
        "• ระยะของข้าวตอนนี้ (เช่น ต้นกล้า/แตกกอ/ออกรวง)"
    )
    assert _simulates_stage_minus_one_merge(stage_reply, bot_context), (
        f"Stage -1 merge did NOT fire for {stage_reply!r}. "
        f"Pipeline would route this as a standalone query, losing root topic."
    )


def test_stage_minus_one_regression_railway_log_case():
    """
    Exact reproduction of the Railway log 2026-04-21 13:57 bug:
    User replied 'แตกกอ' after bot's rice-stage ask-back.
    """
    query = "แตกกอ"
    context = (
        "ผู้ใช้: เพลี้ยกระโดดข้าวใช้อะไรดี\n"
        "น้องลัดดา: เพื่อแนะนำสินค้าที่เหมาะสมที่สุดสำหรับการกำจัด"
        "เพลี้ยกระโดดในข้าว ขอทราบข้อมูลเพิ่มเติมค่ะ 😊\n"
        "• ระยะของข้าวตอนนี้ "
        "(เช่น ต้นกล้า / แตกกอ / ตั้งท้อง / ออกรวง / สุก / เก็บเกี่ยว)"
    )
    assert _simulates_stage_minus_one_merge(query, context), (
        "The exact case from Railway log 2026-04-21 must now pass Stage -1."
    )
    assert detect_problem_type(query) != "nutrient", (
        "The same case must no longer misclassify as nutrient topic."
    )


# ── 5. Sync guard — test-file mirror must match ───────────────

def test_test_best_pick_clarify_stage_words_in_sync():
    """The _STAGE_WORDS mirror in tests/test_best_pick_clarify.py is meant
    to be kept in sync with orchestrator's. Enforce it."""
    import tests.test_best_pick_clarify as mirror_tests
    src = inspect.getsource(mirror_tests.TestClarificationMerge.test_stage_reply_patterns)
    m = re.search(r"_STAGE_WORDS\s*=\s*\(([^)]+)\)", src, re.DOTALL)
    assert m, "Mirror _STAGE_WORDS tuple not found in test_best_pick_clarify.py"
    mirror_words = set(re.findall(r'"([^"]+)"', m.group(1)))
    prod_words = set(orchestrator._STAGE_WORDS)
    missing_in_mirror = prod_words - mirror_words
    # Mirror may be a subset — but rice stages specifically must be there
    rice_stages = {"แตกกอ", "ตั้งท้อง", "ออกรวง", "สุก"}
    missing_rice_in_mirror = rice_stages - mirror_words
    assert not missing_rice_in_mirror, (
        f"Rice stages missing from test_best_pick_clarify.py mirror: "
        f"{missing_rice_in_mirror}. The mirror explicitly comments "
        f"'Keep in sync with orchestrator Stage -1 _STAGE_WORDS' — update it."
    )
    # Non-fatal informational check
    if missing_in_mirror:
        # Not asserting — mirror is allowed to be a curated subset
        pass
