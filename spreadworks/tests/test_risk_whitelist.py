"""Corrective Brief v2 §7.3 — schema tests for the risk-advisor layer boundary.

The risk model outputs probability/magnitude/confidence and a whitelist action.
It may NEVER name an instrument or structure. These tests fail the build if:
  * any graded action falls outside the whitelist,
  * the runtime scrub stops blocking prohibited terms,
  * any string literal in the endpoint/alert modules contains a prohibited
    structure term (outside the PROHIBITED_TERMS definition itself).
"""
import ast
from pathlib import Path

import pytest

from backend.routes_risk import (ACTION_WHITELIST, GRADES, PROHIBITED_TERMS,
                                 _scrub)

BACKEND = Path(__file__).resolve().parent.parent / "backend"


def test_grades_are_whitelist_actions():
    for _, action in GRADES:
        assert action in ACTION_WHITELIST, f"{action!r} is not a permitted action"


def test_whitelist_contains_no_structures():
    for action in ACTION_WHITELIST:
        low = action.lower()
        for term in PROHIBITED_TERMS:
            assert term not in low


def test_scrub_blocks_prohibited_terms():
    dirty = {
        "headline": "consider a long STRADDLE here",
        "nested": [{"note": "maybe buy premium tomorrow"}, "plain ok"],
        "n": 3, "p": 0.42,
    }
    clean = _scrub(dirty)
    assert "straddle" not in str(clean).lower()
    assert "buy premium" not in str(clean).lower()
    assert clean["nested"][1] == "plain ok"          # untouched strings survive
    assert clean["n"] == 3 and clean["p"] == 0.42    # non-strings untouched


@pytest.mark.parametrize("module", ["routes_risk.py", "risk_alerts.py"])
def test_no_prohibited_terms_in_module_strings(module):
    """Every string literal in the module must be structure-free — except the
    PROHIBITED_TERMS definition itself (and _scrub's docstring/replacement,
    which reference the concept, not a recommendation)."""
    src = (BACKEND / module).read_text(encoding="utf-8")
    tree = ast.parse(src)
    allowed_spans = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "PROHIBITED_TERMS":
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Constant):
                            allowed_spans.add(id(sub))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in allowed_spans:
                continue
            low = node.value.lower()
            for term in PROHIBITED_TERMS:
                if term in low:
                    offenders.append((node.lineno, term, node.value[:60]))
    assert not offenders, f"prohibited structure terms in {module}: {offenders}"
