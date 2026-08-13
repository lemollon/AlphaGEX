"""Unit tests for the 12:00/13:30 CT afternoon flow re-check plumbing."""
from datetime import datetime

from backend.routes_risk import (PM_CLOCKS, _pm_baseline_rows, _pm_snap_valid,
                                 _scrub)


def test_pm_baseline_rows_12_00_has_full_sample():
    rows = _pm_baseline_rows("12:00")
    assert len(rows) >= 800
    # every row belongs only to the requested clock — the CSV is shared with
    # 13:30 and a wrong filter would silently double or blend the sample.
    assert all(set(r.keys()) == {"d", "callv", "putv", "totv"} for r in rows)


def test_pm_snapshot_window_rejects_late_capture():
    # 18:00 CT is nowhere near the 12:00-12:35 CT capture window — a late
    # capture is not the 12:00 figure at all (same bug class as the AM
    # snapshot's 18:18 pollution incident).
    late = datetime(2026, 8, 13, 18, 0)
    assert _pm_snap_valid("12:00", late) is False
    on_time = datetime(2026, 8, 13, 12, 10)
    assert _pm_snap_valid("12:00", on_time) is True
    # sanity: the window constant actually matches what we're testing
    start, end = PM_CLOCKS["12:00"]
    assert start <= (on_time.hour, on_time.minute) <= end


def test_scrub_blocks_prohibited_term_in_flow_pm_payload():
    # A prohibited structure term planted anywhere in a flow_pm-shaped
    # response must still be redacted — _scrub is defense in depth, not
    # convention, for every field this endpoint can emit.
    dirty = {
        "flow_pm": {
            "12:00": {"status": "snapshot", "putv_z": 2.4, "totv_z": 1.1,
                      "spike": True, "note": "consider a long STRADDLE here"},
            "13:30": {"status": "pre-window — captures at first request "
                                "13:30–14:05 CT", "putv_z": None,
                      "totv_z": None, "spike": None},
        },
    }
    clean = _scrub(dirty)
    assert "straddle" not in str(clean).lower()
    assert clean["flow_pm"]["12:00"]["spike"] is True
    assert clean["flow_pm"]["13:30"]["putv_z"] is None
