"""Live flow tape (2026-09-03 blind spot) — DESCRIPTIVE ONLY.

🚨 THE INCIDENT THIS EXISTS FOR. On 2026-09-03 SPY ran +1% starting 10:10 CT.
confirm_check only captures 10:10-14:00 CT, so there was no risk_flow_intraday
record at all before 10:10, and the row written AT 10:10 had nothing earlier
to diff against — it read as NULL. Three things are tested here:

  * flow_burst_label — the pure descriptive classifier. Every label it
    returns must carry FLOW_BURST_NOTE and none may say buy/sell/call/put
    direction; the hard rule is enforced by construction (the label set is
    fixed to "bullish burst"/"bearish burst"/"quiet"/"no data").
  * build_flow_tape — the pure, DB-free assembly /session calls, so the
    slotting/dedup/delta logic is tested without a database.
  * risk_alerts.run_flow_capture — the standalone job's skip/retry decision
    logic, factored out of the register_risk_alerts() closure specifically
    so it is unit-testable (same reasoning as test_confirm_alert_retry.py).
    NEVER modifies confirm_check, CONFIRM_ARM_Z, CONFIRM_WINDOW_CT, the
    alert path, or the paper book — this file does not touch any of those.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from backend import risk_alerts, routes_risk as R

CT = R.CT


# ── flow_burst_label ─────────────────────────────────────────────────────

def test_bullish_burst_at_the_inclusive_boundary():
    assert R.flow_burst_label(0.80, 0.30) == "bullish burst"


def test_just_under_the_call_threshold_is_quiet():
    assert R.flow_burst_label(0.79, 0.30) == "quiet"


def test_just_over_the_put_threshold_is_quiet():
    assert R.flow_burst_label(0.80, 0.31) == "quiet"


def test_bearish_burst_at_the_inclusive_boundary():
    assert R.flow_burst_label(0.30, 0.80) == "bearish burst"


def test_bearish_mirror_just_misses():
    assert R.flow_burst_label(0.31, 0.79) == "quiet"


def test_missing_call_share_is_no_data():
    assert R.flow_burst_label(None, 0.50) == "no data"


def test_missing_put_share_is_no_data():
    assert R.flow_burst_label(0.50, None) == "no data"


def test_both_missing_is_no_data():
    assert R.flow_burst_label(None, None) == "no data"


def test_label_set_never_implies_direction():
    """Hard rule: no label may say call/buy/sell/direction. Enforced by
    checking the whole fixed output set, not just one call."""
    labels = {
        R.flow_burst_label(0.80, 0.30), R.flow_burst_label(0.30, 0.80),
        R.flow_burst_label(0.50, 0.50), R.flow_burst_label(None, None),
    }
    banned = ("call", "put", "buy", "sell")
    for lbl in labels:
        low = lbl.lower()
        assert not any(b in low for b in banned), lbl


# ── build_flow_tape ──────────────────────────────────────────────────────

class _Row:
    def __init__(self, ts, call_vol, put_vol, call_buy_share, put_buy_share, spot):
        self.ts = ts
        self.call_vol = call_vol
        self.put_vol = put_vol
        self.call_buy_share = call_buy_share
        self.put_buy_share = put_buy_share
        self.spot = spot


D = datetime(2026, 9, 3)


def _rows():
    zero = [
        _Row(D.replace(hour=8, minute=40), 100, 50, 0.90, 0.20, 550.0),
        _Row(D.replace(hour=8, minute=50), 150, 80, 0.85, 0.25, 551.0),
        _Row(D.replace(hour=10, minute=10), 300, 100, 0.50, 0.50, 555.0),
        # duplicate write inside the 08:40 slot — a race, must lose to the
        # earlier ts already captured above.
        _Row(D.replace(hour=8, minute=41), 999, 999, 0.01, 0.99, 999.0),
    ]
    fivedte = [
        _Row(D.replace(hour=8, minute=40), 40, 20, 0.60, 0.40, 550.0),
        _Row(D.replace(hour=8, minute=50), 55, 30, 0.65, 0.35, 551.0),
        _Row(D.replace(hour=10, minute=10), 90, 45, 0.55, 0.45, 555.0),
    ]
    return {"0dte": zero, "1_5d": fivedte}


def test_three_slots_assembled_and_sorted():
    tape, meta = R.build_flow_tape(_rows())
    assert [t["minute_ct"] for t in tape] == [520, 530, 610]
    assert tape[0]["minute_ct"] == 520 < 610          # before 10:10
    assert meta["n_slots"] == 3


def test_duplicate_row_in_a_slot_picks_the_earliest():
    tape, _ = R.build_flow_tape(_rows())
    first = tape[0]["tenors"]["0dte"]
    assert first["call_vol"] == 100 and first["put_vol"] == 50
    assert first["call_buy_share"] == 0.90


def test_first_slot_has_no_delta_later_slots_do():
    tape, _ = R.build_flow_tape(_rows())
    assert tape[0]["tenors"]["0dte"]["call_vol_delta"] is None
    assert tape[1]["tenors"]["0dte"]["call_vol_delta"] == 50    # 150-100
    assert tape[1]["tenors"]["0dte"]["put_vol_delta"] == 30     # 80-50
    assert tape[2]["tenors"]["0dte"]["call_vol_delta"] == 150   # 300-150
    assert tape[2]["tenors"]["1_5d"]["call_vol_delta"] == 35    # 90-55


def test_read_is_derived_from_the_0dte_tenor_only():
    tape, _ = R.build_flow_tape(_rows())
    assert tape[0]["read"] == "bullish burst"        # 0.90 / 0.20
    assert tape[2]["read"] == "quiet"                 # 0.50 / 0.50


def test_every_slot_carries_the_descriptive_note():
    tape, meta = R.build_flow_tape(_rows())
    assert all(t["note"] == R.FLOW_BURST_NOTE for t in tape)
    assert meta["note"] == R.FLOW_BURST_NOTE


def test_meta_first_last_capture_and_latest_read():
    tape, meta = R.build_flow_tape(_rows())
    assert meta["first_capture"] == "08:40"
    assert meta["last_capture"] == "10:10"
    assert "quiet" in meta["latest_read"]
    assert "unvalidated" in meta["latest_read"]


def test_latest_read_mentions_the_burst_label_when_flagged():
    rows = {"0dte": [_Row(D.replace(hour=8, minute=40), 100, 50, 0.90, 0.20, 550.0)]}
    _, meta = R.build_flow_tape(rows)
    assert "bullish burst" in meta["latest_read"]
    assert "unvalidated" in meta["latest_read"]


def test_no_data_slot_reads_no_data_not_a_crash():
    rows = {"0dte": [_Row(D.replace(hour=8, minute=40), 0, 0, None, None, 550.0)]}
    tape, meta = R.build_flow_tape(rows)
    assert tape[0]["read"] == "no data"
    assert "no data" in meta["latest_read"]
    assert "unvalidated" in meta["latest_read"]


def test_empty_input_returns_empty_tape_and_null_meta():
    tape, meta = R.build_flow_tape({})
    assert tape == []
    assert meta == {"first_capture": None, "last_capture": None, "n_slots": 0,
                    "note": R.FLOW_BURST_NOTE, "latest_read": None}


def test_a_tenor_missing_from_one_slot_does_not_poison_the_next_delta():
    """0dte present at 08:40 and 10:10 but NOT 08:50 — the 10:10 delta must
    be taken against 08:40 (the tenor's own previous appearance), not
    fabricated against a slot it was never in."""
    rows = {
        "0dte": [
            _Row(D.replace(hour=8, minute=40), 100, 50, 0.9, 0.2, 550.0),
            _Row(D.replace(hour=10, minute=10), 300, 100, 0.5, 0.5, 555.0),
        ],
        "1_5d": [
            _Row(D.replace(hour=8, minute=40), 40, 20, 0.6, 0.4, 550.0),
            _Row(D.replace(hour=8, minute=50), 55, 30, 0.65, 0.35, 551.0),
        ],
    }
    tape, _ = R.build_flow_tape(rows)
    slots = {t["minute_ct"]: t for t in tape}
    assert 520 in slots and 530 in slots and 610 in slots
    assert "0dte" not in slots[530]["tenors"]
    assert slots[610]["tenors"]["0dte"]["call_vol_delta"] == 200   # 300-100


# ── flow_slot_has_rows ───────────────────────────────────────────────────

def test_flow_slot_has_rows_is_false_without_a_database(monkeypatch):
    monkeypatch.setattr(R, "SessionLocal", None)
    assert R.flow_slot_has_rows(D.date(), 520) is False


class _FakeQuery:
    def __init__(self, hit):
        self._hit = hit
    def filter(self, *a, **k):
        return self
    def first(self):
        return self._hit


class _FakeDB:
    def __init__(self, hit):
        self._hit = hit
    def query(self, *a, **k):
        return _FakeQuery(self._hit)
    def close(self):
        pass


def test_flow_slot_has_rows_true_when_a_row_exists(monkeypatch):
    monkeypatch.setattr(R, "SessionLocal", lambda: _FakeDB(object()))
    assert R.flow_slot_has_rows(D.date(), 520) is True


def test_flow_slot_has_rows_false_when_no_row(monkeypatch):
    monkeypatch.setattr(R, "SessionLocal", lambda: _FakeDB(None))
    assert R.flow_slot_has_rows(D.date(), 520) is False


def test_flow_slot_has_rows_never_raises_on_a_db_error(monkeypatch):
    def _boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(R, "SessionLocal", _boom)
    assert R.flow_slot_has_rows(D.date(), 520) is False


# ── risk_alerts.run_flow_capture ─────────────────────────────────────────

APP = SimpleNamespace(state=SimpleNamespace(http=None))


async def test_weekend_is_a_noop(monkeypatch):
    calls = []
    monkeypatch.setattr(R, "flow_slot_has_rows", lambda d, m: calls.append(1) or False)
    saturday = datetime(2026, 9, 5, 9, 0)   # a Saturday
    await risk_alerts.run_flow_capture(APP, saturday)
    assert calls == []


async def test_outside_the_capture_window_is_a_noop(monkeypatch):
    calls = []
    monkeypatch.setattr(R, "flow_slot_has_rows", lambda d, m: calls.append(1) or False)
    too_early = datetime(2026, 9, 3, 8, 30)   # before 08:40
    await risk_alerts.run_flow_capture(APP, too_early)
    assert calls == []


async def test_skips_the_slot_confirm_check_already_captured(monkeypatch):
    captured = []
    monkeypatch.setattr(R, "flow_slot_has_rows", lambda d, m: True)

    async def _fake_capture(request, now):
        captured.append(now)
        return True

    monkeypatch.setattr(R, "capture_flow_intraday", _fake_capture)
    now = datetime(2026, 9, 3, 10, 10)
    await risk_alerts.run_flow_capture(APP, now)
    assert captured == []      # never called — the slot was already written


async def test_retries_once_when_the_first_capture_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(R, "flow_slot_has_rows", lambda d, m: False)

    async def _fake_capture(request, now):
        calls.append(now)
        return False        # fails both times

    monkeypatch.setattr(R, "capture_flow_intraday", _fake_capture)

    async def _no_sleep(_secs):
        pass
    monkeypatch.setattr(risk_alerts.asyncio, "sleep", _no_sleep)

    async def _no_spot(_request):
        return None
    monkeypatch.setattr(R, "_rolling_flow_now", _no_spot)

    now = datetime(2026, 9, 3, 8, 40)
    await risk_alerts.run_flow_capture(APP, now)
    assert len(calls) == 2     # first attempt + exactly one retry


async def test_does_not_retry_when_the_first_capture_succeeds(monkeypatch):
    calls = []
    monkeypatch.setattr(R, "flow_slot_has_rows", lambda d, m: False)

    async def _fake_capture(request, now):
        calls.append(now)
        return True

    monkeypatch.setattr(R, "capture_flow_intraday", _fake_capture)

    slept = []
    async def _track_sleep(_secs):
        slept.append(_secs)
    monkeypatch.setattr(risk_alerts.asyncio, "sleep", _track_sleep)

    async def _no_spot(_request):
        return None
    monkeypatch.setattr(R, "_rolling_flow_now", _no_spot)

    now = datetime(2026, 9, 3, 8, 40)
    await risk_alerts.run_flow_capture(APP, now)
    assert len(calls) == 1
    assert slept == []


async def test_a_capture_success_writes_the_spot_to_the_session_log(monkeypatch):
    monkeypatch.setattr(R, "flow_slot_has_rows", lambda d, m: False)

    async def _fake_capture(request, now):
        return True
    monkeypatch.setattr(R, "capture_flow_intraday", _fake_capture)

    async def _fake_spot(_request):
        return {"putv": 1, "totv": 2, "spot": 543.21}
    monkeypatch.setattr(R, "_rolling_flow_now", _fake_spot)

    writes = []
    monkeypatch.setattr(R, "session_log_write",
                        lambda d, now, **kw: writes.append((d, now, kw)))

    now = datetime(2026, 9, 3, 8, 40)
    await risk_alerts.run_flow_capture(APP, now)
    assert len(writes) == 1
    assert writes[0][2]["spot"] == 543.21


async def test_a_spot_fetch_failure_never_blocks_or_raises(monkeypatch):
    monkeypatch.setattr(R, "flow_slot_has_rows", lambda d, m: False)

    async def _fake_capture(request, now):
        return True
    monkeypatch.setattr(R, "capture_flow_intraday", _fake_capture)

    async def _boom_spot(_request):
        raise RuntimeError("tradier down")
    monkeypatch.setattr(R, "_rolling_flow_now", _boom_spot)

    now = datetime(2026, 9, 3, 8, 40)
    await risk_alerts.run_flow_capture(APP, now)   # must not raise


def test_the_job_never_touches_confirm_step_or_its_thresholds():
    """🚨 GUARDRAIL. run_flow_capture's CODE (not its docstring, which is
    allowed to reference these by name when explaining why it does NOT use
    them) must not import or call anything from the validated confirmation
    watcher — this is a recording job, not a rule."""
    import ast
    import inspect
    src = inspect.getsource(risk_alerts.run_flow_capture)
    tree = ast.parse(src)
    func = tree.body[0]
    body = func.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]                     # drop the docstring node
    code_src = "\n".join(ast.get_source_segment(src, n) or "" for n in body)
    for banned in ("confirm_step", "CONFIRM_ARM_Z", "CONFIRM_WINDOW_CT",
                  "CONFIRM_MOVE_PCT", "paper_record_fire"):
        assert banned not in code_src, banned
