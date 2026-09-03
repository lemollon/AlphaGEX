"""The /hunt ACTION BOX — one verdict, computed once, server-side.

🚨 THE PROBLEM THIS EXISTS FOR. /hunt used to make the reader work out what
to do: unfired it just said "no confirm" with no reason or trigger level;
fired it buried the actual trade inside the Playbook. build_action() is the
single function that answers "what do I do right now", reused by both the
/session response (the ACTION BOX) and the confirm Discord/ntfy alert (one
extra line, via _action_suffix), so the page and the push can never
disagree.

HARD RULE THIS FILE ENFORCES: build_action/action_sentence must NEVER raise,
no matter what is missing, and every ACT_NOW/DONE headline must carry the
literal word "PAPER" — this trade is paper, on every surface, always.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from backend import routes_risk as R
from backend import risk_alerts as RA

CT = R.CT


def _paper(**kw):
    base = {
        "id": 1, "d": "2026-09-03", "fired_dir": "UP",
        "fired_at": "2026-09-03T10:40:00", "fired_spot": 583.25,
        "expiry": "2026-09-03", "long_strike": 583.0, "short_strike": 585.0,
        "long_ask": 0.92, "short_bid": 0.13, "quote_at": "2026-09-03T10:41:00",
        "debit": 0.79, "contracts": 1, "skipped_reason": None,
        "settle_spot": None, "settle_value": None, "pnl": None,
        "settled_at": None, "created_at": "2026-09-03T10:41:00",
    }
    base.update(kw)
    return base


CONFIRM_UP = {"fired_dir": "UP", "fired_at": "2026-09-03T10:40:00",
             "fired_spot": 583.25, "ref_spot": 582.67, "putcall_z": 1.64,
             "armed": True, "arm_z": R.CONFIRM_ARM_Z,
             "move_pct": R.CONFIRM_MOVE_PCT}


# ── a: fired, ACT_NOW ─────────────────────────────────────────────────────

def test_a_act_now_with_priced_ticket():
    now = datetime(2026, 9, 3, 11, 0)
    action = R.build_action(now, CONFIRM_UP, None, {}, {}, _paper())
    assert action["state"] == "ACT_NOW"
    assert "PAPER" in action["headline"]
    assert "UP confirmed 10:40 CT at 583.25" in action["headline"]
    assert "Buy 0DTE 2026-09-03 583/585 call vertical" in action["detail"]
    assert "1 contract(s)" in action["detail"]
    assert "debit $0.79" in action["detail"]
    assert "10:41" in action["detail"]
    assert "Exit at the 15:00 close." in action["detail"]
    assert action["trade"] == _paper()
    assert action["mode"] == "PAPER"
    assert "63%" in action["why"]


def test_a_act_now_with_skipped_ticket():
    now = datetime(2026, 9, 3, 11, 0)
    paper = _paper(skipped_reason="missing_quote", long_strike=None,
                   short_strike=None, debit=None)
    action = R.build_action(now, CONFIRM_UP, None, {}, {}, paper)
    assert action["state"] == "ACT_NOW"
    assert "PAPER" in action["headline"]
    assert "Ticket not priced: missing_quote" in action["detail"]
    assert "direction UP" in action["detail"]
    assert "no trade to copy" in action["detail"]


def test_a_act_now_with_no_paper_row_at_all():
    now = datetime(2026, 9, 3, 11, 0)
    action = R.build_action(now, CONFIRM_UP, None, {}, {}, None)
    assert action["state"] == "ACT_NOW"
    assert "PAPER" in action["headline"]
    assert "Ticket not priced: no paper row" in action["detail"]
    assert action["trade"] is None


# ── a: fired, DONE ────────────────────────────────────────────────────────

def test_a_done_with_pnl():
    now = datetime(2026, 9, 3, 15, 30)
    paper = _paper(settled_at="2026-09-03T15:05:00", pnl=39.0)
    confirm = {**CONFIRM_UP, "fired_dir": "DOWN"}
    action = R.build_action(now, confirm, None, {}, {}, paper)
    assert action["state"] == "DONE"
    assert "PAPER" in action["headline"]
    assert "DONE (PAPER) — DOWN fired 10:40 CT" == action["headline"]
    assert "result +39.00" in action["detail"]
    assert action["next_check"] == "tomorrow 10:00 CT"


def test_a_done_unsettled_after_the_close():
    now = datetime(2026, 9, 3, 15, 30)
    action = R.build_action(now, CONFIRM_UP, None, {}, {}, _paper())
    assert action["state"] == "DONE"
    assert "PAPER" in action["headline"]
    assert "settles after the close" in action["detail"]


def test_a_settled_before_1500_is_also_done_not_act_now():
    """settled_at flips the branch even before 15:00 — the ticket already
    has an outcome, so there is nothing left to act on."""
    now = datetime(2026, 9, 3, 12, 0)
    paper = _paper(settled_at="2026-09-03T11:59:00", pnl=-12.5)
    action = R.build_action(now, CONFIRM_UP, None, {}, {}, paper)
    assert action["state"] == "DONE"
    assert "result -12.50" in action["detail"]


# ── b: before the 10:00 read ─────────────────────────────────────────────

def test_b_before_1000():
    now = datetime(2026, 9, 3, 9, 15)
    action = R.build_action(now, {}, None, {}, {}, None)
    assert action["state"] == "NO_ACTION"
    assert action["headline"] == "NO ACTION — before the 10:00 flow read"
    assert action["next_check"] == "10:10 CT"


# ── c: the 10:00 read is missing (a fault) ───────────────────────────────

def test_c_1000_clock_never_captured():
    now = datetime(2026, 9, 3, 10, 30)
    action = R.build_action(now, {}, {"captured": False}, {}, {}, None)
    assert action["state"] == "NO_ACTION"
    assert action["headline"] == "NO ACTION — 10:00 read missing"
    assert "check risk_alerts logs" in action["detail"]


def test_c_1000_clock_is_none():
    now = datetime(2026, 9, 3, 10, 30)
    action = R.build_action(now, {}, None, {}, {}, None)
    assert action["state"] == "NO_ACTION"
    assert action["headline"] == "NO ACTION — 10:00 read missing"


# ── d: not armed ──────────────────────────────────────────────────────────

def test_d_not_flagged():
    now = datetime(2026, 9, 3, 10, 30)
    confirm = {"armed": False, "putcall_z": 0.42, "arm_z": 1.5}
    action = R.build_action(now, confirm, {"captured": True}, {}, {}, None)
    assert action["state"] == "NO_ACTION"
    assert action["headline"] == "NO ACTION — not flagged today"
    assert "+0.42" in action["detail"]
    assert "1.5" in action["detail"]
    assert action["next_check"] == "tomorrow 10:00 CT"


# ── e: armed, waiting for the break ──────────────────────────────────────

def test_e_armed_waiting_with_trigger_levels():
    now = datetime(2026, 9, 3, 11, 30)
    confirm = {"armed": True, "putcall_z": 1.64, "arm_z": 1.5,
              "move_pct": 0.10, "ref_spot": 582.67}
    levels = {"down": 582.09, "up": 583.25}
    to_trigger = {"down_pct": -0.30, "up_pct": 0.20}
    action = R.build_action(now, confirm, {"captured": True}, levels, to_trigger, None)
    assert action["state"] == "NO_ACTION"
    assert action["headline"] == "ARMED — waiting for the break"
    assert "up through 583.25 (+0.20% away)" in action["detail"]
    assert "down through 582.09 (-0.30% away)" in action["detail"]
    assert "session high/low" in action["detail"]
    assert action["next_check"] == "every 10 min until 14:00 CT"


def test_e_armed_waiting_without_trigger_levels():
    now = datetime(2026, 9, 3, 10, 5)
    confirm = {"armed": True, "putcall_z": 1.64, "arm_z": 1.5,
              "move_pct": 0.10, "ref_spot": 582.67}
    action = R.build_action(now, confirm, {"captured": True}, {}, {}, None)
    assert action["state"] == "NO_ACTION"
    assert action["headline"] == "ARMED — waiting for the break"
    assert "away" not in action["detail"]
    assert "up through" in action["detail"] and "down through" in action["detail"]


# ── f: window closed, unfired ────────────────────────────────────────────

def test_f_window_closed():
    now = datetime(2026, 9, 3, 14, 30)
    confirm = {"armed": True, "putcall_z": 1.64, "arm_z": 1.5}
    action = R.build_action(now, confirm, {"captured": True}, {}, {}, None)
    assert action["state"] == "NO_ACTION"
    assert action["headline"] == "NO ACTION — window closed at 14:00"
    assert action["next_check"] == "tomorrow 10:00 CT"


# ── every ACT/DONE headline says PAPER ───────────────────────────────────

@pytest.mark.parametrize("now,confirm,paper", [
    (datetime(2026, 9, 3, 11, 0), CONFIRM_UP, _paper()),
    (datetime(2026, 9, 3, 11, 0), CONFIRM_UP, _paper(skipped_reason="no_0dte")),
    (datetime(2026, 9, 3, 11, 0), CONFIRM_UP, None),
    (datetime(2026, 9, 3, 15, 30), CONFIRM_UP, _paper(settled_at="x", pnl=1.0)),
    (datetime(2026, 9, 3, 15, 30), CONFIRM_UP, _paper()),
])
def test_every_act_or_done_headline_says_paper(now, confirm, paper):
    action = R.build_action(now, confirm, None, {}, {}, paper)
    assert action["state"] in ("ACT_NOW", "DONE")
    assert "PAPER" in action["headline"]


# ── build_action must never raise ────────────────────────────────────────

@pytest.mark.parametrize("hour,minute", [(9, 0), (10, 5), (10, 30), (11, 45),
                                         (13, 59), (14, 30), (15, 30)])
def test_build_action_never_raises_on_all_none_fields(hour, minute):
    now = datetime(2026, 9, 3, hour, minute)
    action = R.build_action(now, None, None, None, None, None)
    assert action["state"] == "NO_ACTION"
    assert isinstance(action["headline"], str) and action["headline"]
    assert action["mode"] == "PAPER"


def test_build_action_never_raises_when_fired_but_paper_fields_are_none():
    now = datetime(2026, 9, 3, 11, 0)
    confirm = {"fired_dir": "DOWN", "fired_at": None, "fired_spot": None}
    action = R.build_action(now, confirm, None, {}, {}, {})
    assert action["state"] == "ACT_NOW"
    assert "PAPER" in action["headline"]


# ── action_sentence ───────────────────────────────────────────────────────

def test_action_sentence_is_one_line():
    action = {"headline": "ARMED — waiting for the break",
             "detail": "Flagged (z +1.64). Fires on a break..."}
    sentence = R.action_sentence(action)
    assert "\n" not in sentence
    assert sentence.startswith(action["headline"])
    assert action["detail"] in sentence


def test_action_sentence_strips_embedded_newlines():
    action = {"headline": "H\nH2", "detail": "D\nD2"}
    sentence = R.action_sentence(action)
    assert "\n" not in sentence


def test_action_sentence_never_raises_on_empty_action():
    assert isinstance(R.action_sentence({}), str)
    assert isinstance(R.action_sentence(None), str)


# ── risk_alerts._action_suffix — the alert-append wrapper ───────────────

HIT = {"dir": "DOWN", "spot": 765.56, "ref": 766.56, "putcall_z": 1.64}


def test_action_suffix_normal_path():
    now = datetime(2026, 9, 3, 11, 55)
    suffix = RA._action_suffix(now, HIT, None)
    assert suffix.startswith("\n\n**Action (PAPER):** ")
    assert "PAPER" in suffix


def test_action_suffix_returns_empty_string_on_any_failure(monkeypatch):
    """⛔ THE WHOLE POINT: a broken addendum must degrade to no addendum, not
    to no alert. build_action raising must not propagate."""
    def _raise(*a, **kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(R, "build_action", _raise)
    now = datetime(2026, 9, 3, 11, 55)
    suffix = RA._action_suffix(now, HIT, None)
    assert suffix == ""


def test_action_suffix_never_raises_on_malformed_hit():
    now = datetime(2026, 9, 3, 11, 55)
    suffix = RA._action_suffix(now, {}, None)
    assert isinstance(suffix, str)
