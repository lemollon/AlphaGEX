"""A firing whose alert never went out must be recoverable — but only while
the call is still worth making.

🚨 THE INCIDENT THIS EXISTS FOR. On 2026-08-20 the DIRECTION CONFIRMED signal
fired DOWN at 10:40 CT into a webhook that had been broken by a bad deploy.
confirm_step() had already stamped fired_dir, and every subsequent poll skips
on `fired_dir is None` — so the state machine considered the work done, nobody
was ever told, and the alert was lost permanently. Firing and alerting were the
same flag; they are now two.
"""
from datetime import datetime, timedelta

import pytest

from backend import routes_risk as R

CT = R.CT
TODAY = datetime(2026, 8, 20).date()


class _Row:
    def __init__(self, **kw):
        self.fired_dir = kw.get("fired_dir")
        self.fired_at = kw.get("fired_at")
        self.fired_spot = kw.get("fired_spot")
        self.ref_spot = kw.get("ref_spot")
        self.putcall_z = kw.get("putcall_z", 1.64)
        self.alerted_at = kw.get("alerted_at")


class _DB:
    def __init__(self, row): self._row = row; self.committed = False
    def get(self, *a): return self._row
    def commit(self): self.committed = True
    def close(self): pass


def _patch(monkeypatch, row):
    db = _DB(row)
    monkeypatch.setattr(R, "SessionLocal", lambda: db)
    return db


def _fired(minutes_ago, **kw):
    at = datetime(2026, 8, 20, 12, 0) - timedelta(minutes=minutes_ago)
    return _Row(fired_dir="DOWN", fired_at=at, fired_spot=765.56,
                ref_spot=766.56, **kw)


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=CT)


# ── the recovery itself ──────────────────────────────────────────────────────

def test_an_undelivered_firing_is_recovered(monkeypatch):
    _patch(monkeypatch, _fired(40))
    hit = R.undelivered_firing(TODAY, NOW)
    assert hit is not None
    assert hit["dir"] == "DOWN" and hit["delayed"] is True
    assert hit["age_min"] == 40
    assert hit["move_pct"] == pytest.approx(-0.1305, abs=1e-3)


def test_a_firing_already_alerted_is_never_resent(monkeypatch):
    """⛔ The whole point of the new column. Re-sending would be worse than the
    original bug — an alert you have already acted on, arriving again."""
    _patch(monkeypatch, _fired(40, alerted_at=datetime(2026, 8, 20, 10, 41)))
    assert R.undelivered_firing(TODAY, NOW) is None


def test_no_firing_means_nothing_to_recover(monkeypatch):
    _patch(monkeypatch, _Row())
    assert R.undelivered_firing(TODAY, NOW) is None


def test_a_missing_row_is_not_an_error(monkeypatch):
    _patch(monkeypatch, None)
    assert R.undelivered_firing(TODAY, NOW) is None


# ── the time bound: a late alert is worse than none ──────────────────────────

def test_a_stale_firing_is_abandoned_not_sent_late(monkeypatch):
    """A DIRECTION CONFIRMED alert is a claim about the REST of the day. Two
    hours later the runway it promises is already spent."""
    _patch(monkeypatch, _fired(150))
    assert R.undelivered_firing(TODAY, NOW) is None


def test_the_age_bound_is_configurable_and_enforced(monkeypatch):
    _patch(monkeypatch, _fired(40))
    assert R.undelivered_firing(TODAY, NOW, max_age_min=30) is None
    _patch(monkeypatch, _fired(40))
    assert R.undelivered_firing(TODAY, NOW, max_age_min=60) is not None


def test_nothing_is_sent_after_the_confirmation_window_closes(monkeypatch):
    """Past 14:00 CT the signal's own window is shut; recovering into it would
    contradict the thing the window exists to encode."""
    late = datetime(2026, 8, 20, 14, 30, tzinfo=CT)
    _patch(monkeypatch, _Row(fired_dir="DOWN", fired_spot=765.56, ref_spot=766.56,
                             fired_at=datetime(2026, 8, 20, 14, 20)))
    assert R.undelivered_firing(TODAY, late) is None


def test_a_clock_skew_negative_age_is_rejected(monkeypatch):
    """fired_at in the future means something is wrong with the clock; do not
    alert off it."""
    _patch(monkeypatch, _fired(-20))
    assert R.undelivered_firing(TODAY, NOW) is None


# ── incomplete rows ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("missing", ["fired_at", "ref_spot", "fired_spot"])
def test_an_incomplete_firing_row_is_skipped(monkeypatch, missing):
    row = _fired(40)
    setattr(row, missing, None)
    _patch(monkeypatch, row)
    assert R.undelivered_firing(TODAY, NOW) is None


# ── the stamp ────────────────────────────────────────────────────────────────

def test_mark_alerted_stamps_once(monkeypatch):
    row = _fired(40)
    db = _patch(monkeypatch, row)
    R.mark_alerted(TODAY, NOW)
    assert row.alerted_at is not None and db.committed


def test_mark_alerted_does_not_overwrite_an_existing_stamp(monkeypatch):
    first = datetime(2026, 8, 20, 10, 41)
    row = _fired(40, alerted_at=first)
    _patch(monkeypatch, row)
    R.mark_alerted(TODAY, NOW)
    assert row.alerted_at == first


def test_helpers_never_raise_without_a_database(monkeypatch):
    monkeypatch.setattr(R, "SessionLocal", None)
    assert R.undelivered_firing(TODAY, NOW) is None
    R.mark_alerted(TODAY, NOW)          # must be a no-op, not an exception


# ── the wiring: the stamp must be gated on a real send ───────────────────────

def test_the_job_only_stamps_after_a_successful_send():
    """⛔ Stamping unconditionally would recreate the original bug in a new
    place: a firing recorded as told when nobody was told."""
    import inspect

    from backend import risk_alerts

    src = inspect.getsource(risk_alerts.register_risk_alerts)
    i = src.index('delivered = _post("risk_confirm"')
    seg = src[i:i + 1600]
    assert "if delivered:" in seg and "mark_alerted" in seg
    assert seg.index("if delivered:") < seg.index("mark_alerted(")
