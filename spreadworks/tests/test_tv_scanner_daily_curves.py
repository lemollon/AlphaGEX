"""Tests for the 2026-09-28 daily-cache + intraday-shortlist redesign (tv_scanner.py section
B, "DAILY CACHE + INTRADAY SHORTLIST"; see also shortlist.py for the pure selection-rule tests
and fleet_runtime.py's run_tv_book_daily_curves for the scheduled job).

Uses the same synthetic-package harness as test_tv_scanner_concurrency_equivalence.py
(tests/_scanner_harness.py) so importing tv_scanner.py never drags in the real FastAPI app or
touches a real network socket.

Three behaviors under test:
1. `--daily-curves` mode fetches ONLY the per-name GEX curve (no /tickers, no series, no
   ThetaData -- proven by the fake transport raising on any URL it doesn't expect) for every
   candidate, writes each to the normal per-name cache, and writes a completion marker with an
   accurate ok/failed manifest. The 7 preset-screener lists are pre-cached (unrelated to what
   this test checks) so the run stays inside TradingVolatility's real 5-expensive-calls/min
   budget without needing a real 60s wait -- fetch_presets() always makes all 7 calls
   regardless of --daily-curves, so a cold cache here would just be re-proving the rate
   limiter itself (already covered by test_ember_rate_limiter.py), not this feature.
2 & 3. An intraday --live tick's curve-fetch DECISION for a non-shortlist name (skip
   entirely vs. read cache_only) is tested with `--cached` ALSO set -- under --cached every
   tv_get() call resolves from disk with no network attempt regardless of ttl_s/cache_only
   (existing, unchanged contract), so the only way a non-shortlist name's curve differs
   between "daily cache missing" and "daily cache OK" is whether tv_get() is even CALLED for
   it -- proven directly by whether a pre-populated (but, in scenario 2, deliberately
   IGNORED-per fail-closed) cache file actually reaches the row (put_wall/call_wall populated)
   or not. This is deterministic and fast (no real network, no real rate-limiter sleeps) and
   tests the exact production semantic in tv_get(cache_only=...), not a proxy for it.
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tests._scanner_harness import FakeResponse, build_pkg

TODAY = dt.date.today().isoformat()
PRESETS = ["bottoming_reversal", "capitulation_reversal", "highvol_breakdown", "momentum_breakout",
           "range_premium_seller", "topping_reversal", "trend_pullback"]


def _write_json(cache_dir: Path, stem: str, payload: dict) -> None:
    (cache_dir / f"{TODAY}_{stem}.json").write_text(json.dumps(payload))


def _precache_empty_presets(cache_dir: Path) -> None:
    for name in PRESETS:
        _write_json(cache_dir, f"screener_{name}", {"data": {"items": []}})


def _ticker_payload(price: float, em1d: float, em1w: float, flip: float) -> dict:
    return {"data": {
        "underlying": {"price": price, "iv": {"iv_rank": 30}},
        "gamma": {"flip": {"price": flip}, "structure": {"max_gamma_strike": None}},
        "expected_move": {"expected_move_pct_1d": em1d, "expected_move_pct_1w": em1w},
        "positioning": {"put_call": {
            "pcr_volume": 0.9, "pcr_oi": 1.1, "pcr_oi_change": {"d30": 0.0},
            "call_oi": 6000, "put_oi": 6000, "call_vol": 400, "put_vol": 400,
        }},
        "call_flow": {"speculative_interest_score": 0.3},
    }}


def _curve_payload(points: list[tuple] | None = None) -> dict:
    points = points or [(85.0, -100.0), (115.0, 100.0)]  # near a price=100 spot -> real walls
    return {"data": {"points": [{"strike": k, "net": g} for k, g in points]}}


def _top_setups_payload(tickers_and_scores: dict[str, float]) -> dict:
    items = [{"ticker": t, "opportunity_score": s, "recommended_direction": "long"}
              for t, s in tickers_and_scores.items()]
    return {"data": {"items": items, "asof": "2026-09-28T14:30:00Z"}}


def _run_module(tmp_path: Path, name: str, argv: list[str], cache_dir: Path,
                 monkeypatch, fake_urlopen):
    module_name = build_pkg(tmp_path, name)
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setenv("EMBER_TVSCAN_DATA_DIR", str(cache_dir.parents[1]))
    # RENDER=true (set by the real deployment target) makes tv_scanner.py's `sess` equal
    # dt.date.today() unconditionally -- matching TODAY above. Without it, sess follows the
    # local-Terminal "prior session before 16:00, walked back past weekends" rule instead
    # (correct for that different, non-cloud code path, but not what these tests are about,
    # and it would make `sess` land on a different calendar date than TODAY depending on the
    # wall-clock hour/weekday this test happens to run at).
    monkeypatch.setenv("RENDER", "true")
    # theta_probe()/theta_csv() treat RENDER=true with no THETADATA_BASE_URL as "no local
    # Terminal available" and fall through to the Tradier fallback (unrelated to what these
    # tests check) -- setting a dummy URL keeps them on the same ThetaData-Terminal-shaped
    # mock path _cached_mode_fake_urlopen / test 1's fake_urlopen already handle.
    monkeypatch.setenv("THETADATA_BASE_URL", "http://theta-test-host:25503")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return importlib.import_module(module_name)


def _run_module_expecting_exit(tmp_path: Path, name: str, argv: list[str], cache_dir: Path,
                                monkeypatch, fake_urlopen) -> int:
    """--daily-curves always exits via sys.exit() after warming the cache -- a normal,
    successful exit, not a test failure. importlib.import_module() propagates that SystemExit
    uncaught (module execution stops mid-way, same as running the script directly), so
    callers that expect it use this instead of _run_module() and inspect side effects (files
    written) rather than the module object, which never finishes initializing."""
    with pytest.raises(SystemExit) as exc_info:
        _run_module(tmp_path, name, argv, cache_dir, monkeypatch, fake_urlopen)
    return exc_info.value.code


def _no_unexpected_call(url: str) -> None:
    raise AssertionError(f"unexpected network call: {url!r}")


def _cached_mode_fake_urlopen(request, timeout=None, *a, **k):
    """For --cached-mode tests: theta_probe() always runs regardless of --cached (it isn't
    gated on sys.argv) and needs to succeed or the scan exits(3) before ever reaching the
    shortlist logic under test -- so these two HTTPError responses (mirroring the real local
    Terminal's observed behavior) are allowed through. Anything else -- in particular any
    stocks.tradingvolatility.net call -- must never happen under --cached and fails the test."""
    url = getattr(request, "full_url", request)
    if "/health" in url:
        raise urllib.error.HTTPError(url, 410, "Gone", {}, None)
    if "history/eod" in url:
        raise urllib.error.HTTPError(url, 478, "no data", {}, None)
    _no_unexpected_call(url)


# ---------------------------------------------------------------------------------------------
def test_daily_curves_mode_warms_cache_writes_marker_and_touches_no_thetadata(tmp_path, monkeypatch):
    cache_root = tmp_path / "cache_root"
    cache_dir = cache_root / "tools" / "ember_cache"
    cache_dir.mkdir(parents=True)
    _precache_empty_presets(cache_dir)  # see module docstring point 1

    calls: list[str] = []

    def fake_urlopen(request, timeout=None, *a, **k):
        url = getattr(request, "full_url", request)
        calls.append(url)
        if url.startswith("https://stocks.tradingvolatility.net/api/v2/top-setups"):
            return FakeResponse(json.dumps(_top_setups_payload({"AAA": 90, "BBB": 50, "BROKEN": 10})).encode())
        if "income-setups" in url:
            return FakeResponse(json.dumps({"data": {"items": []}}).encode())
        if "curves/gex_by_strike" in url:
            if "BROKEN" in url:
                raise urllib.error.HTTPError(url, 500, "server error", {}, None)
            return FakeResponse(json.dumps(_curve_payload()).encode())
        _no_unexpected_call(url)

    exit_code = _run_module_expecting_exit(
        tmp_path, "daily_pkg", ["tv_scanner.py", "--daily-curves"], cache_dir, monkeypatch, fake_urlopen)

    assert exit_code == 0
    assert not any("/tickers/" in u and "curves" not in u for u in calls), "must never fetch /tickers/{t} in --daily-curves mode"
    assert not any("25503" in u for u in calls), "must never touch ThetaData in --daily-curves mode"

    assert (cache_dir / f"{TODAY}_gex_AAA.json").exists()
    assert (cache_dir / f"{TODAY}_gex_BBB.json").exists()
    assert not (cache_dir / f"{TODAY}_gex_BROKEN.json").exists()

    marker = json.loads((cache_dir / f"{TODAY}_daily_curves_complete.json").read_text())
    assert marker["date"] == TODAY
    assert marker["candidates"] == 3
    assert marker["ok"] == 2
    assert marker["failed"] == ["BROKEN"]


# ---------------------------------------------------------------------------------------------
def test_fail_closed_ignores_a_stray_cached_curve_when_daily_pass_never_completed(tmp_path, monkeypatch, capsys):
    """`--live --cached`: no network is ever reached either way (existing --cached contract),
    so the only observable difference for a non-shortlist name is whether tv_get() is called
    for it at all. BBB (not on the shortlist -- AAA is ledgered as today's only near-setup
    name) has a CURVE FILE SITTING ON DISK, but with no DAILY_MARKER for today (the daily pass
    never completed) that file must be ignored, not read -- proven by BBB's row showing no
    put_wall/call_wall (the walls that file's own points would otherwise produce), exactly as
    if the file didn't exist. AAA (shortlist) has no cached curve either, so its row also has
    no walls -- what matters here is BBB behaving identically to "nothing cached" despite a
    real file being present."""
    cache_root = tmp_path / "cache_root"
    cache_dir = cache_root / "tools" / "ember_cache"
    cache_dir.mkdir(parents=True)
    _write_json(cache_dir, "top_setups", _top_setups_payload({"AAA": 90, "BBB": 10}))
    _write_json(cache_dir, "income_setups", {"data": {"items": []}})
    _write_json(cache_dir, "ticker_AAA", _ticker_payload(100.0, 20.0, 1.0, 50.0))
    _write_json(cache_dir, "ticker_BBB", _ticker_payload(100.0, 20.0, 1.0, 50.0))
    _write_json(cache_dir, "gex_BBB", _curve_payload())  # stray file -- must be ignored (no marker)
    ledger_path = cache_root / "ember_ledger.jsonl"
    ledger_path.write_text(json.dumps({"ticker": "AAA", "scan_date": TODAY, "dir": "long", "strategy": "rr"}) + "\n")
    # No gex_AAA, no daily_curves_complete marker.

    mod = _run_module(tmp_path, "live_missing_pkg", ["tv_scanner.py", "--live", "--cached"], cache_dir,
                       monkeypatch, _cached_mode_fake_urlopen)

    assert mod.SHORTLIST == {"AAA"}      # today's ledger names AAA as the only near-setup ticker
    assert mod.daily_cache_ok is False

    all_rr_rows = mod.setups + mod.marginal + mod.hidden + mod.illiquid
    bbb_row = next(r for r in all_rr_rows if r["ticker"] == "BBB")
    assert bbb_row["put_wall"] is None and bbb_row["call_wall"] is None, \
        "BBB's on-disk curve file must be ignored when the daily pass never completed"

    out = capsys.readouterr().out
    assert "DAILY CACHE MISSING" in out


def test_live_reuses_non_shortlist_curve_regardless_of_cache_age_when_daily_pass_completed(tmp_path, monkeypatch):
    """Same setup as above but WITH a completion marker -- BBB's (deliberately backdated, far
    past the old 60-minute TTL) cached curve must now be USED, proven by its row showing the
    real put_wall/call_wall that curve's points produce."""
    cache_root = tmp_path / "cache_root"
    cache_dir = cache_root / "tools" / "ember_cache"
    cache_dir.mkdir(parents=True)
    _write_json(cache_dir, "top_setups", _top_setups_payload({"AAA": 90, "BBB": 10}))
    _write_json(cache_dir, "income_setups", {"data": {"items": []}})
    _write_json(cache_dir, "ticker_AAA", _ticker_payload(100.0, 20.0, 1.0, 50.0))
    _write_json(cache_dir, "ticker_BBB", _ticker_payload(100.0, 20.0, 1.0, 50.0))
    _write_json(cache_dir, "gex_BBB", _curve_payload())
    bbb_curve_path = cache_dir / f"{TODAY}_gex_BBB.json"
    old_mtime = (dt.datetime.now() - dt.timedelta(hours=6)).timestamp()  # well past the old 60-min TTL
    os.utime(bbb_curve_path, (old_mtime, old_mtime))
    _write_json(cache_dir, "daily_curves_complete", {"date": TODAY, "ok": 2, "failed": []})
    ledger_path = cache_root / "ember_ledger.jsonl"
    ledger_path.write_text(json.dumps({"ticker": "AAA", "scan_date": TODAY, "dir": "long", "strategy": "rr"}) + "\n")

    mod = _run_module(tmp_path, "live_ok_pkg", ["tv_scanner.py", "--live", "--cached"], cache_dir,
                       monkeypatch, _cached_mode_fake_urlopen)

    assert mod.SHORTLIST == {"AAA"}
    assert mod.daily_cache_ok is True

    all_rr_rows = mod.setups + mod.marginal + mod.hidden + mod.illiquid
    bbb_row = next(r for r in all_rr_rows if r["ticker"] == "BBB")
    assert bbb_row["put_wall"] == 85.0 and bbb_row["call_wall"] == 115.0, \
        "BBB's day-old cached curve must still be used once the daily pass has completed"
