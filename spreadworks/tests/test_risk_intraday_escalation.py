"""/risk must be able to change its mind during the session.

🚨 THE BUG THIS PINS. `action` was computed once from prior closes plus the
single 10:00 CT snapshot and then frozen. Three validated signals - the 12:00
and 13:30 re-checks and the */10 rolling watcher - fired Discord alerts all
afternoon and could never move the page. A 13:30 spike pushed a phone alert
while /risk still read NORMAL.
"""
import ast
import inspect
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "backend" / "routes_risk.py"
TEXT = SRC.read_text(encoding="utf-8")


def _state_src() -> str:
    """The body of the /state endpoint, so assertions cannot drift to another
    function that merely mentions the same names."""
    tree = ast.parse(TEXT)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "state":
            return ast.get_source_segment(TEXT, node) or ""
    raise AssertionError("/state endpoint not found")


def test_risk_off_consumes_the_pm_clocks_and_the_rolling_watcher():
    src = _state_src()
    i = src.index("risk_off =")
    expr = src[i:src.index("\n", src.index("action =", i))]
    assert "intraday_flags" in expr, (
        "risk_off ignores the intraday clocks again - a 13:30 spike will alert "
        "the phone while the page reads NORMAL")


def test_intraday_flags_are_built_from_both_sources():
    src = _state_src()
    assert "flow_pm" in src and "spike" in src
    assert "fired_today" in src, (
        "the rolling watcher must be read via its dedup'd fired_today flag")


def test_escalation_is_named_in_the_headline():
    """A mid-session change the reader cannot see is the same as no change."""
    src = _state_src()
    assert "escalated_by" in src
    assert "escalated intraday" in src


def test_escalated_by_is_only_set_when_the_close_legs_were_quiet():
    """⛔ Must not claim an intraday escalation on a day that was already
    RISK-OFF from the prior close - that would relabel a standing verdict as a
    new event."""
    src = _state_src()
    i = src.index("escalated_by = None")
    guard = src[i:i + 400]
    for leg in ("backwardation", "flag_vix1d"):
        assert leg in guard, f"{leg} must gate escalated_by"


def test_the_payload_exposes_both_fields():
    src = _state_src()
    assert '"escalated_by": escalated_by' in src
    assert '"intraday_flags": intraday_flags' in src


def test_action_stays_inside_the_whitelist():
    """The escalation must not invent a new instruction."""
    assert "assert action in ACTION_WHITELIST" in _state_src()
