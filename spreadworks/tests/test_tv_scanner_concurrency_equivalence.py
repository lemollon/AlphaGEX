"""Equivalence test for the 2026-09-28 tv_scanner.py concurrency redesign (see PR after
#3104). PR #3104 measured the old per-candidate loop at ~13s-paced TV calls x ~150 names,
fully sequential -- the dominant cost behind EMBER's tv_book >1500s subprocess timeouts. This
redesign moves candidate evaluation onto a bounded thread pool (SCAN_WORKERS) with two shared,
thread-safe rate limiters gating every TradingVolatility call (see rate_limiter.py / tv_get()
in tv_scanner.py), instead of one name at a time with a flat post-call sleep.

tv_scanner.py has no __main__ guard -- it runs its scan top-level on import by design (see
PR #3104's own test notes). Importing the REAL `backend.ember.legacy.tv_scanner` package here
would also drag in the full FastAPI app via backend/__init__.py (2000+ lines, DB engine,
69 route modules). This test avoids both problems: it copies the OLD (pre-redesign, vendored
as a static fixture file -- see below) and NEW (this worktree's) tv_scanner.py + ember_lock.py
+ rate_limiter.py into two disposable synthetic packages with empty __init__.py files (so
`from . import ember_lock` resolves without touching the real `backend` package), mocks
urllib.request.urlopen to serve IDENTICAL canned TradingVolatility-list / ThetaData-quote
responses to both, runs each with --cached against the same pre-populated per-name cache
fixtures (so neither run touches a real network socket, the real TradingVolatility account,
or the shared local ThetaData Terminal), and asserts the resulting setups/marginal/hidden/
illiquid/nodata/bounce_* rows are IDENTICAL between old and new. That proves the concurrency
refactor changed WHEN the I/O happens, not WHAT gets computed from it -- same candidate list,
same signals, same decisions.

The OLD source is vendored as a static text fixture (fixtures/ember/tv_scanner_97a7aa08.py.txt,
an exact `git show 97a7aa08:...` snapshot) rather than fetched via `git show` at test time --
CI's checkout is shallow (actions/checkout@v4 default fetch-depth), so an ancestor commit SHA
that predates the PR branch's tip is not present locally and `git show <sha>` fails with exit
128 there even though it works in a full local clone. Vendoring removes that CI/local
environment difference (and the subprocess/git dependency) entirely.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]  # .../AlphaGEX-wt-tvbook
LEGACY_DIR = REPO_ROOT / "spreadworks" / "backend" / "ember" / "legacy"
OLD_SCANNER_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ember" / "tv_scanner_97a7aa08.py.txt"
OLD_COMMIT = "97a7aa08"  # main tip immediately before this session's concurrency redesign; provenance only

TODAY = dt.date.today().isoformat()

# Rows returned by process_candidate() / the old loop end up in one of these; comparing every
# bucket (not just SETUPS) proves tier assignment itself -- not just the winners -- is unchanged.
COMPARE_KEYS = ["setups", "marginal", "hidden", "illiquid", "nodata",
                "bounce_rows", "bounce_hidden", "bounce_illiquid", "truncated_n"]

# Fields that legitimately differ run-to-run without reflecting a computational difference
# (wall-clock timestamps). Excluded from the comparison, not from execution.
VOLATILE_FIELDS = {"scan_time"}


def _old_tv_scanner_source() -> str:
    return OLD_SCANNER_FIXTURE.read_text()


def _strip_volatile(obj):
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items() if k not in VOLATILE_FIELDS}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    if isinstance(obj, tuple):
        return [_strip_volatile(v) for v in obj]
    return obj


def _build_pkg(tmp_path: Path, name: str, tv_scanner_src: str) -> str:
    """A throwaway package: <tmp>/<name>/pkgroot/ember/legacy/{tv_scanner,ember_lock,
    rate_limiter}.py with empty __init__.py files at every level, so `from . import
    ember_lock, rate_limiter` resolves without importing the real backend package. Returns
    the dotted module path to import."""
    root = tmp_path / name
    pkg = root / "pkgroot" / "ember" / "legacy"
    pkg.mkdir(parents=True)
    (root / "pkgroot" / "__init__.py").write_text("")
    (root / "pkgroot" / "ember" / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text("")
    (pkg / "tv_scanner.py").write_text(tv_scanner_src)
    (pkg / "ember_lock.py").write_text((LEGACY_DIR / "ember_lock.py").read_text())
    rate_limiter_src = LEGACY_DIR / "rate_limiter.py"
    if rate_limiter_src.exists():
        (pkg / "rate_limiter.py").write_text(rate_limiter_src.read_text())
    sys.path.insert(0, str(root))
    return "pkgroot.ember.legacy.tv_scanner"


# ---- fixture candidates -----------------------------------------------------------------
# Ratios of em_1w_pct/em_1d_pct are chosen to land each ticker's RR tier by a wide, unambiguous
# margin (no gex-curve wall arithmetic to get subtly wrong) except TSTD, whose put_wall is the
# BOUNCE signal itself and is placed directly.
TICKERS = dict(
    TSTA=dict(price=100.0, flip=50.0, em1d=0.5, em1w=5.0, iv_rank=30, direction="long",
              call_oi=8000, put_oi=8000, call_vol=400, put_vol=400,
              curve=[(20.0, -500.0), (500.0, 500.0)]),   # far walls: never win vs. the em bands
    TSTB=dict(price=150.0, flip=140.0, em1d=2.0, em1w=3.0, iv_rank=40, direction="long",
              call_oi=6000, put_oi=6000, call_vol=600, put_vol=600, curve=[]),
    TSTC=dict(price=200.0, flip=210.0, em1d=5.0, em1w=2.0, iv_rank=45, direction="short",
              call_oi=6000, put_oi=6000, call_vol=600, put_vol=600, curve=[]),
    TSTE=dict(price=120.0, flip=100.0, em1d=0.5, em1w=5.0, iv_rank=60, direction=None,
              call_oi=100, put_oi=100, call_vol=50, put_vol=50,   # below LIQ_OI_MIN/VOL_MIN -> illiquid
              curve=[(20.0, -500.0), (500.0, 500.0)], income_only=True),
    TSTH=dict(price=55.0, flip=40.0, em1d=0.5, em1w=5.0, iv_rank=20, direction="long",
              call_oi=8000, put_oi=8000, call_vol=400, put_vol=400,
              curve=[(20.0, -500.0), (500.0, 500.0)]),
)
# TSTD: BOUNCE setup -- put_wall placed within 3% of price, series carries a real downtrend
# (RSI < 30). RR side is deliberately starved (em1d >> em1w) so its own RR row lands HIDDEN,
# exercising "both strategies scored off the same candidate" (section F of the docstring).
TSTD = dict(price=80.0, flip=60.0, em1d=20.0, em1w=5.0, iv_rank=35, direction="short",
            call_oi=8000, put_oi=8000, call_vol=400, put_vol=400,
            curve=[(79.0, -900.0), (100.0, 900.0)])  # put_wall below spot, within 3% -> bounce signal
# TSTF: no /tickers payload at all (earliest nodata exit). TSTG: present but no
# recommended_direction and no income source -> "no direction" nodata.


def _series_points(trend: str) -> list[dict]:
    """40 ascending-date closes; 'down' gives Wilder's RSI(14) comfortably < 30, 'flat' keeps
    it well clear of the bounce threshold."""
    base = dt.date(2026, 1, 1)
    closes = []
    price = 100.0
    for i in range(40):
        if trend == "down":
            price -= 1.0
        else:
            price += (0.1 if i % 2 == 0 else -0.05)
        closes.append({"date": (base + dt.timedelta(days=i)).isoformat(), "price": round(price, 2)})
    return closes


def _write_json(cache_dir: Path, stem: str, payload: dict) -> None:
    (cache_dir / f"{TODAY}_{stem}.json").write_text(json.dumps(payload))


def _ticker_payload(t: str, cfg: dict) -> dict:
    return {"data": {
        "underlying": {"price": cfg["price"], "iv": {"iv_rank": cfg["iv_rank"]}},
        "gamma": {"flip": {"price": cfg["flip"]}, "structure": {"max_gamma_strike": None}},
        "expected_move": {"expected_move_pct_1d": cfg["em1d"], "expected_move_pct_1w": cfg["em1w"]},
        "positioning": {"put_call": {
            "pcr_volume": 0.9, "pcr_oi": 1.1, "pcr_oi_change": {"d30": 0.02},
            "call_oi": cfg["call_oi"], "put_oi": cfg["put_oi"],
            "call_vol": cfg["call_vol"], "put_vol": cfg["put_vol"],
        }},
        "call_flow": {"speculative_interest_score": 0.42},
    }}


def _curve_payload(points: list[tuple]) -> dict:
    return {"data": {"points": [{"strike": k, "net": g} for k, g in points]}}


def _series_payload(trend: str) -> dict:
    return {"data": {"points": _series_points(trend)}}


def _populate_cache(cache_dir: Path) -> None:
    idea_items = []
    income_items = []
    for t, cfg in {**TICKERS, "TSTD": TSTD}.items():
        item = {"ticker": t, "opportunity_score": 50}
        if cfg.get("direction"):
            item["recommended_direction"] = cfg["direction"]
        if cfg.get("income_only"):
            # fetch_income() filters client-side on "price" (section A.3 -- the endpoint has
            # no price params of its own); the real payload carries it on every item.
            income_items.append({**item, "price": cfg["price"], "iv_rank": cfg["iv_rank"], "earnings_date": "2026-11-01"})
        else:
            idea_items.append({**item, "iv_rank": cfg["iv_rank"]})
    idea_items.append({"ticker": "TSTF", "opportunity_score": 40, "recommended_direction": "long"})
    idea_items.append({"ticker": "TSTG", "opportunity_score": 10})  # no recommended_direction

    _write_json(cache_dir, "top_setups", {"data": {"items": idea_items, "asof": "2026-09-28T14:30:00Z"}})
    _write_json(cache_dir, "income_setups", {"data": {"items": income_items}})
    # Presets (7) and TSTF's /tickers, TSTG's curve/series are deliberately left uncached --
    # under --cached a missing file returns None with no network call (section A/B contract).

    for t, cfg in TICKERS.items():
        _write_json(cache_dir, f"ticker_{t}", _ticker_payload(t, cfg))
        _write_json(cache_dir, f"gex_{t}", _curve_payload(cfg["curve"]))
        _write_json(cache_dir, f"series_{t}", _series_payload("flat"))
    _write_json(cache_dir, "ticker_TSTD", _ticker_payload("TSTD", TSTD))
    _write_json(cache_dir, "gex_TSTD", _curve_payload(TSTD["curve"]))
    _write_json(cache_dir, "series_TSTD", _series_payload("down"))
    _write_json(cache_dir, "ticker_TSTG", {"data": {
        "underlying": {"price": 90.0},
        "expected_move": {"expected_move_pct_1d": 1.0, "expected_move_pct_1w": 3.0},
    }})
    # TSTF: no ticker_TSTF fixture at all -> "no /tickers payload" nodata.


# ---- transport mock -----------------------------------------------------------------------
class _FakeResponse(io.BytesIO):
    def __init__(self, data: bytes, status: int = 200):
        super().__init__(data)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


_EXPIRATIONS_CSV = "expiration\r\n" + (dt.date.today() + dt.timedelta(days=32)).strftime("%Y%m%d") + \
    "\r\n" + (dt.date.today() + dt.timedelta(days=40)).strftime("%Y%m%d") + "\r\n"


def _quote_csv() -> str:
    rows = ["right,strike,bid,ask,bid_size,ask_size"]
    for strike in range(10, 505, 5):
        rows.append(f"CALL,{strike}.0,1.50,1.60,50,50")
        rows.append(f"PUT,{strike}.0,1.50,1.60,50,50")
    return "\r\n".join(rows) + "\r\n"


def _fake_urlopen(request, timeout=None, *a, **k):
    url = getattr(request, "full_url", request)
    if "127.0.0.1:25503" in url or "THETA_TEST_HOST" in url:
        if "/health" in url:
            raise urllib.error.HTTPError(url, 410, "Gone", {}, None)
        if "list/expirations" in url:
            return _FakeResponse(_EXPIRATIONS_CSV.encode())
        if "history/quote" in url:
            return _FakeResponse(_quote_csv().encode())
        if "history/eod" in url:
            raise urllib.error.HTTPError(url, 478, "no data outside hours", {}, None)
    raise AssertionError(f"tv_scanner equivalence test: unexpected network call to {url!r}")


# ---- the test -------------------------------------------------------------------------------
def _run(tmp_path: Path, name: str, tv_scanner_src: str, cache_dir: Path, monkeypatch) -> dict:
    module_name = _build_pkg(tmp_path, name, tv_scanner_src)
    monkeypatch.setattr(sys, "argv", ["tv_scanner.py", "--cached"])
    monkeypatch.setenv("EMBER_TVSCAN_DATA_DIR", str(cache_dir.parents[1]))
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    import importlib
    mod = importlib.import_module(module_name)
    return {k: getattr(mod, k) for k in COMPARE_KEYS}


def test_concurrency_redesign_matches_old_sequential_output(tmp_path, monkeypatch):
    cache_root = tmp_path / "cache_root"
    cache_dir = cache_root / "tools" / "ember_cache"
    cache_dir.mkdir(parents=True)
    _populate_cache(cache_dir)

    new_src = (LEGACY_DIR / "tv_scanner.py").read_text()
    old_src = _old_tv_scanner_source()

    old_result = _run(tmp_path, "old_pkg", old_src, cache_dir, monkeypatch)
    new_result = _run(tmp_path, "new_pkg", new_src, cache_dir, monkeypatch)

    assert old_result["truncated_n"] == new_result["truncated_n"] == 0

    for key in COMPARE_KEYS:
        old_rows = _strip_volatile(old_result[key])
        new_rows = _strip_volatile(new_result[key])
        old_sorted = sorted(old_rows, key=lambda r: json.dumps(r, sort_keys=True, default=str)) \
            if isinstance(old_rows, list) else old_rows
        new_sorted = sorted(new_rows, key=lambda r: json.dumps(r, sort_keys=True, default=str)) \
            if isinstance(new_rows, list) else new_rows
        assert old_sorted == new_sorted, f"{key} differs between old sequential and new concurrent scan"

    # Sanity: the fixture actually exercises every bucket + both strategies, not just nodata.
    assert len(new_result["setups"]) >= 1
    assert len(new_result["marginal"]) >= 1
    assert len(new_result["hidden"]) >= 1
    assert len(new_result["illiquid"]) >= 1
    assert len(new_result["nodata"]) >= 2       # TSTF (no payload) + TSTG (no direction)
    assert len(new_result["bounce_rows"]) >= 1  # TSTD's bounce setup
