"""
Guard against leaking internal strategy classification names to users.

Strategy values (Skyrocket / Expand / Cosmic-star / Natural / Standard)
are confidential business classifications. They must never appear in:
  1. Hard-coded user-facing strings in handlers / safety intercepts.
  2. LLM prompt text — the LLM may echo terms it sees in its instructions.

Internal usage is fine: column comparisons (`if strategy in {…}`),
sort keys, log lines, source comments — these don't reach users.

Failure here is a confidentiality breach, not a functional bug.
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest


_STRATEGY_SECRETS = ('Skyrocket', 'Expand', 'Cosmic-star', 'Natural', 'Standard')

# Files that build user-visible reply strings or LLM prompts the model paraphrases.
# (`prompts.py` itself is allowed — rule 15 there names them as forbidden, which
# is the only legitimate user-adjacent mention.)
_AUDIT_FILES = [
    'app/services/chat/handler.py',
    'app/services/rag/response_generator_agent.py',
    'app/services/rag/retrieval_agent.py',
    'app/services/rag/query_understanding_agent.py',
    'app/services/rag/orchestrator.py',
]

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _internal_only_node_ids(tree: ast.AST) -> set[int]:
    """Collect id() of string-literal nodes that are internal-only (docstrings
    or arguments of logger/logging calls). Strategy names here don't reach
    users or the LLM."""
    internal_ids: set[int] = set()

    # Docstrings: first statement of module/class/function body
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, 'body', None) or []
            if (body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                internal_ids.add(id(body[0].value))

    # Logger calls: logger.info("..."), logging.warning("..."), etc.
    def _is_logger_call(call: ast.Call) -> bool:
        func = call.func
        if isinstance(func, ast.Attribute):
            # obj.info / obj.warning / … where obj is logger/logging
            root = func.value
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name) and root.id in ('logger', 'logging', 'log'):
                return True
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_logger_call(node):
            for arg in node.args:
                # Direct string or f-string with string parts
                for sub in ast.walk(arg):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        internal_ids.add(id(sub))
    return internal_ids


def _collect_string_literals(source: str) -> list[tuple[int, str]]:
    """Return [(lineno, value), …] for sentence-length string literals that
    reach users (replies) or the LLM (prompts). Excludes docstrings and
    logger-call arguments. Sentence filter (>12 chars OR whitespace) skips
    bare tokens used in set/dict membership."""
    tree = ast.parse(source)
    internal_ids = _internal_only_node_ids(tree)
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in internal_ids:
            continue
        v = node.value
        if len(v) > 12 or any(c.isspace() for c in v):
            out.append((node.lineno, v))
    return out


@pytest.mark.parametrize("rel_path", _AUDIT_FILES)
def test_no_strategy_in_user_facing_or_prompt_strings(rel_path):
    """No strategy name may appear in any sentence-length string literal in
    these files. Single-word literals (set membership, dict keys) are
    excluded — those are internal data, not user-visible."""
    full = _REPO_ROOT / rel_path
    source = full.read_text(encoding='utf-8')
    leaks: list[str] = []
    for lineno, literal in _collect_string_literals(source):
        for secret in _STRATEGY_SECRETS:
            # Word-boundary match prevents false-hits on substrings like
            # "Standard library" if any future docstring mentions it.
            if re.search(rf'\b{re.escape(secret)}\b', literal):
                snippet = literal[:120].replace('\n', ' ')
                leaks.append(f"  line {lineno}: {secret!r} in: {snippet!r}")
    assert not leaks, (
        f"Strategy classification leaked in {rel_path} — these strings "
        f"reach users (handler reply or LLM prompt body):\n"
        + "\n".join(leaks)
    )


def test_handler_sales_popularity_returns_no_strategy_name():
    """Defensive: even if someone re-introduces strategy text into the
    handler response, this end-to-end check catches it. Uses mocked state
    so we exercise both the success branch (priority match) and the
    admin-handoff branch (no priority match) without touching real DB."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.services.chat import handler

    async def _run(state, db_rows, query):
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value.data = db_rows
        with patch("app.services.chat.handler.get_conversation_state",
                   new_callable=AsyncMock, return_value=state), \
             patch("app.services.chat.handler.supabase_client", mock_sb):
            return await handler._handle_sales_popularity_followup('u', query)

    # Success branch — priority match present
    success = asyncio.run(_run(
        state={'active_products': ['แกนเตอร์']},
        db_rows=[{'product_name': 'แกนเตอร์', 'strategy': 'Skyrocket',
                  'common_name_th': '', 'selling_point': ''}],
        query='ตัวไหนขายดี',
    ))
    # Admin-handoff branch — no priority match
    handoff = asyncio.run(_run(
        state={'active_products': ['ไดนาคลอร์']},
        db_rows=[{'product_name': 'ไดนาคลอร์', 'strategy': 'Standard',
                  'common_name_th': '', 'selling_point': ''}],
        query='ฮิตที่สุด',
    ))
    for label, reply in (('success', success), ('handoff', handoff)):
        assert reply is not None, f"{label} branch must produce a reply"
        for secret in _STRATEGY_SECRETS:
            assert secret not in reply, (
                f"Strategy {secret!r} leaked in {label} branch: {reply!r}"
            )


def test_prompts_module_rule_15_still_present():
    """The defense-in-depth rule that tells the LLM not to leak strategy
    names must remain in prompts.py — without it, an LLM could echo any
    metadata it accidentally sees."""
    from app import prompts
    src = inspect.getsource(prompts)
    assert 'ห้ามพูดถึงกลุ่ม/Strategy' in src, (
        "prompts.py rule 15 (no-strategy-leak) was removed — defense-in-depth gone"
    )
    # Must mention all strategy names so the LLM knows what to suppress
    for secret in _STRATEGY_SECRETS:
        assert secret in src, (
            f"prompts.py rule 15 doesn't list {secret!r} — LLM may not know to suppress it"
        )
