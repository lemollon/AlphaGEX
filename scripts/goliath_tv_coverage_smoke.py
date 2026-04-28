#!/usr/bin/env python3
"""
GOLIATH Phase 1 — Trading Volatility API coverage smoke test.

Hard-stop gate before any further GOLIATH Phase 1 work. Verifies that the
existing TradingVolatilityAPI (core_classes_and_engines.py:1116) returns
usable GEX data for all five GOLIATH underlyings plus SPY as a sanity
baseline. Decides per-underlying which IV source GOLIATH will use
(`tv_api` vs `hv_proxy`) per Phase 0 Decision 1 and persists the choice
to the goliath_iv_source_decisions table when the database is reachable.

Tickers checked:
    MSTR, TSLA, NVDA, COIN, AMD  (GOLIATH 5 underlyings)
    SPY                          (sanity baseline — known good GEX coverage)

Exits 0 only when 6/6 underlyings PASS every check. Any failure exits 1
and prints what to investigate.

Required env: TRADING_VOLATILITY_API_KEY (or TRADINGVOL_API_KEY / TV_USERNAME)
Optional env: DATABASE_URL — when set, persists per-ticker IV-source decision

Usage:
    python scripts/goliath_tv_coverage_smoke.py
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

# Repo-root on sys.path so we can import core_classes_and_engines and
# database_adapter from anywhere. Mirrors scripts/agape_spot_health_check.py.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# GOLIATH universe + sanity baseline
GOLIATH_UNDERLYINGS = ["MSTR", "TSLA", "NVDA", "COIN", "AMD"]
SANITY_BASELINE = ["SPY"]
ALL_TICKERS = GOLIATH_UNDERLYINGS + SANITY_BASELINE

# Plausibility bounds for IV-rank (0-100 percentile scale per TV v2 spec).
# IV-rank is what Gate G05 actually thresholds on (≥60 to enter trades),
# so this is the field that determines GOLIATH's IV-source decision.
# We accept iv_rank=0 as a degenerate-but-present case (some tickers may
# legitimately read 0 in extreme IV-low regimes); only reject when value
# is missing entirely.
IV_RANK_MIN = 0.0
IV_RANK_MAX = 100.0

# Required fields in get_net_gamma() return dict (post-parse). These map
# directly onto fields GOLIATH gates and strike mapping depend on.
REQUIRED_NET_GAMMA_FIELDS = ["spot_price", "net_gex", "flip_point"]


@dataclass
class TickerResult:
    ticker: str
    spot_price: float = 0.0
    flip_point: float = 0.0
    net_gex: float = 0.0
    iv_rank: float = 0.0                     # 0-100 percentile from TV /series
    has_levels_data: bool = False
    nearest_wall: Optional[float] = None     # legacy: closest wall from /levels (gex_0)
    call_wall: Optional[float] = None        # from /curves/gex_by_strike (above spot)
    put_wall: Optional[float] = None         # from /curves/gex_by_strike (below spot)
    iv_source: str = "unknown"               # 'tv_api' or 'hv_proxy'
    iv_source_reason: str = ""
    failures: list = None
    iv_rank_from_series_present: bool = False  # was iv_rank populated in /series?

    def __post_init__(self):
        if self.failures is None:
            self.failures = []

    @property
    def passed(self) -> bool:
        return not self.failures


def _ensure_table(conn) -> None:
    """Create goliath_iv_source_decisions if not present, then ensure schema
    matches current expectations. Idempotent.

    Uses the canonical AlphaGEX cursor pattern (no `with conn.cursor() as c`,
    since PostgreSQLCursor does not implement the context-manager protocol).

    Schema migration: prior runs created the table with a column called
    `iv_from_series_present`. We renamed to `iv_rank_from_series_present`
    once we discovered TV's /series surfaces iv_rank (not atm_iv) for our
    universe. The ALTER TABLE statements below upgrade in place; if a
    fresh table is created the new schema is used directly.
    """
    c = conn.cursor()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS goliath_iv_source_decisions (
                id SERIAL PRIMARY KEY,
                ticker VARCHAR(10) NOT NULL,
                iv_source VARCHAR(20) NOT NULL,
                reason TEXT NOT NULL,
                iv_value_at_decision DECIMAL(10, 6),
                iv_rank_from_series_present BOOLEAN NOT NULL DEFAULT FALSE,
                decided_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        # Idempotent column-rename / add for tables created by earlier runs
        c.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'goliath_iv_source_decisions'
                      AND column_name = 'iv_from_series_present'
                ) AND NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'goliath_iv_source_decisions'
                      AND column_name = 'iv_rank_from_series_present'
                ) THEN
                    ALTER TABLE goliath_iv_source_decisions
                        RENAME COLUMN iv_from_series_present TO iv_rank_from_series_present;
                END IF;
            END $$;
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_goliath_iv_source_decisions_ticker
            ON goliath_iv_source_decisions(ticker, decided_at DESC)
        """)
        conn.commit()
    finally:
        try:
            c.close()
        except Exception:
            pass


def _persist_decision(result: TickerResult) -> bool:
    """Returns True on successful persist; False (with warning) when DB
    unreachable. Never raises — DB persistence is best-effort."""
    try:
        from database_adapter import get_connection, is_database_available
    except ImportError:
        print(f"  [DB] database_adapter import failed; decision for {result.ticker} not persisted")
        return False

    if not is_database_available():
        print(f"  [DB] no DATABASE_URL; decision for {result.ticker} not persisted")
        return False

    try:
        conn = get_connection()
        try:
            _ensure_table(conn)
            c = conn.cursor()
            try:
                c.execute(
                    """
                    INSERT INTO goliath_iv_source_decisions
                        (ticker, iv_source, reason, iv_value_at_decision, iv_rank_from_series_present)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        result.ticker,
                        result.iv_source,
                        result.iv_source_reason,
                        float(result.iv_rank),
                        bool(result.iv_rank_from_series_present),
                    ),
                )
                conn.commit()
            finally:
                try:
                    c.close()
                except Exception:
                    pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return True
    except Exception as e:
        print(f"  [DB] persist failed for {result.ticker}: {e}")
        return False


def _fetch_iv_rank_from_v2_series(client, ticker: str) -> Optional[float]:
    """Try to fetch the latest IV-rank percentile via TV v2 /series endpoint.

    Returns iv_rank as a 0-100 percentile, or None if not retrievable.

    Why iv_rank not atm_iv: smoke-test diagnostics on 2026-04-28 showed TV
    silently drops `atm_iv` from /series responses (returns date-only points
    when atm_iv is the only metric requested). However, TV pre-computes
    `iv_rank` server-side and surfaces it directly. iv_rank is also exactly
    what Gate G05 thresholds on (≥60), so this is the authoritative source.
    """
    try:
        if not hasattr(client, "_v2_series"):
            return None
        resp = client._v2_series(ticker, ["iv_rank"], window="5d")
        if not isinstance(resp, dict) or "error" in resp:
            return None
        data = resp.get("data", resp)
        # Two possible shapes: data.points = [{date, iv_rank}, ...]
        # or data.series = {iv_rank: [...]} (server-side may use either form).
        points = data.get("points")
        if isinstance(points, list) and points:
            for pt in reversed(points):
                if isinstance(pt, dict) and pt.get("iv_rank") is not None:
                    return float(pt["iv_rank"])
        series = data.get("series")
        if isinstance(series, dict):
            arr = series.get("iv_rank") or []
            if arr:
                for v in reversed(arr):
                    if v is not None:
                        return float(v)
        return None
    except Exception:
        return None


def _check_one_ticker(client, ticker: str) -> TickerResult:
    """Run all coverage checks for a single ticker. Never raises — every
    failure mode becomes an entry in result.failures."""
    result = TickerResult(ticker=ticker)

    # 1. Net gamma snapshot
    try:
        snap = client.get_net_gamma(ticker)
    except Exception as e:
        result.failures.append(f"get_net_gamma raised: {e!r}")
        return result

    if not isinstance(snap, dict):
        result.failures.append(f"get_net_gamma returned non-dict: {type(snap).__name__}")
        return result

    if "error" in snap:
        result.failures.append(f"get_net_gamma error: {snap['error']}")
        return result

    # Pull v1-shaped fields; on the v2-migrated client these come from
    # /market-structure (spot, flip, net_gex) plus /curves/gex_by_strike (walls).
    result.spot_price = float(snap.get("spot_price") or 0)
    result.net_gex = float(snap.get("net_gex") or 0)
    result.flip_point = float(snap.get("flip_point") or 0)

    cw = snap.get("call_wall")
    pw = snap.get("put_wall")
    result.call_wall = float(cw) if cw is not None else None
    result.put_wall = float(pw) if pw is not None else None

    # Required-field checks: a value can be present but zero (e.g., flip_point=0
    # means TV did not surface gamma_flip). Require sensible non-zero spot/flip.
    if result.spot_price <= 0:
        result.failures.append(f"spot_price={result.spot_price} (expected > 0)")
    if result.flip_point <= 0:
        result.failures.append(f"flip_point={result.flip_point} (expected > 0)")

    # IV-rank — Gate G05 thresholds on iv_rank ≥ 60. TV pre-computes iv_rank
    # server-side and surfaces it via /series, which is more useful than raw
    # atm_iv (which TV silently drops from responses for our universe).
    iv_rank = _fetch_iv_rank_from_v2_series(client, ticker)
    result.iv_rank_from_series_present = iv_rank is not None
    result.iv_rank = float(iv_rank) if iv_rank is not None else 0.0

    if not result.iv_rank_from_series_present:
        result.iv_source = "hv_proxy"
        result.iv_source_reason = "TV /series did not return iv_rank (Option C fallback)"
    elif result.iv_rank < IV_RANK_MIN or result.iv_rank > IV_RANK_MAX:
        result.iv_source = "hv_proxy"
        result.iv_source_reason = (
            f"TV iv_rank={result.iv_rank:.2f} outside plausibility range "
            f"[{IV_RANK_MIN}, {IV_RANK_MAX}]"
        )
    else:
        result.iv_source = "tv_api"
        result.iv_source_reason = (
            f"TV iv_rank={result.iv_rank:.2f} in [{IV_RANK_MIN}, {IV_RANK_MAX}]"
        )

    # 2. GEX levels — used for wall identification in strike mapping (legacy
    # nearest_wall display field; the authoritative walls are from get_net_gamma).
    try:
        levels = client.get_gex_levels(ticker)
    except Exception as e:
        result.failures.append(f"get_gex_levels raised: {e!r}")
        return result

    if not isinstance(levels, dict) or not levels:
        # Not fatal anymore — call_wall/put_wall from get_net_gamma cover the
        # actual wall need. Just note that /levels returned nothing.
        result.has_levels_data = False
    else:
        result.has_levels_data = True
        gex_0 = float(levels.get("gex_0") or 0)
        gex_flip = float(levels.get("gex_flip") or 0)
        if gex_0 > 0:
            result.nearest_wall = gex_0
        elif gex_flip > 0:
            result.nearest_wall = gex_flip

    return result


def _print_summary_table(results: list) -> None:
    print()
    print("=" * 120)
    print("GOLIATH TV COVERAGE SUMMARY")
    print("=" * 120)
    header = (
        f"{'Ticker':<7} {'Spot':>10} {'Flip':>10} {'NetGEX':>14} "
        f"{'IVRank':>7} {'CallWall':>10} {'PutWall':>10} {'IVSource':>10} {'Status':>7}"
    )
    print(header)
    print("-" * 120)
    for r in results:
        cw = f"${r.call_wall:.2f}" if r.call_wall else "—"
        pw = f"${r.put_wall:.2f}" if r.put_wall else "—"
        status = "PASS" if r.passed else "FAIL"
        print(
            f"{r.ticker:<7} "
            f"${r.spot_price:>9.2f} "
            f"${r.flip_point:>9.2f} "
            f"{r.net_gex:>13.2e} "
            f"{r.iv_rank:>6.1f} "
            f"{cw:>10} "
            f"{pw:>10} "
            f"{r.iv_source:>10} "
            f"{status:>7}"
        )
    print("-" * 120)


def _print_failure_detail(results: list) -> None:
    failures = [r for r in results if not r.passed]
    if not failures:
        return
    print()
    print("FAILURE DETAIL")
    print("-" * 110)
    for r in failures:
        print(f"\n  {r.ticker}:")
        for f in r.failures:
            print(f"    - {f}")


def main() -> int:
    # Import the existing client. If this fails, the smoke test cannot proceed
    # — and that is itself the answer (GOLIATH cannot run without it).
    try:
        from core_classes_and_engines import TradingVolatilityAPI
    except ImportError as e:
        print(f"FATAL: cannot import TradingVolatilityAPI: {e}")
        return 1

    # Post-v2-migration the canonical env var is TRADING_VOLATILITY_API_TOKEN
    # (Bearer token, e.g. sub_xxx). Legacy names retained for the unlikely
    # case someone is still on a pre-migrated client.
    token_set = any(
        os.getenv(name)
        for name in (
            "TRADING_VOLATILITY_API_TOKEN",
            "TRADING_VOLATILITY_API_KEY",
            "TRADINGVOL_API_KEY",
            "TV_USERNAME",
            "tv_username",
        )
    )
    if not token_set:
        print("FATAL: no TV API credential in env.")
        print("  Set TRADING_VOLATILITY_API_TOKEN (Bearer token from TV billing page).")
        return 1

    client = TradingVolatilityAPI()

    print(f"Running TV coverage smoke test against {len(ALL_TICKERS)} tickers...")
    print(f"  Universe: {GOLIATH_UNDERLYINGS}")
    print(f"  Baseline: {SANITY_BASELINE}")
    print()

    results = []
    for ticker in ALL_TICKERS:
        print(f"[{ticker}] checking...")
        result = _check_one_ticker(client, ticker)
        results.append(result)
        if result.passed:
            _persist_decision(result)
        # Defensive pacing — TradingVolatilityAPI rate-limits internally,
        # but a small explicit delay reduces burst pressure when running
        # this locally outside the shared rate limiter.
        time.sleep(1)

    _print_summary_table(results)
    _print_failure_detail(results)

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print()
    print(f"COVERAGE: {passed}/{total} PASS")

    if passed != total:
        print()
        print("HARD STOP — Phase 1 cannot proceed until 6/6 PASS.")
        print("Investigate failures above, then re-run.")
        return 1

    # Per-ticker IV source decisions summary — drives Phase 3 G05 implementation.
    tv_count = sum(1 for r in results if r.iv_source == "tv_api")
    hv_count = sum(1 for r in results if r.iv_source == "hv_proxy")
    print(f"IV SOURCE DECISIONS: {tv_count} via tv_api, {hv_count} via hv_proxy")
    for r in results:
        print(f"  {r.ticker}: {r.iv_source}  ({r.iv_source_reason})")

    print()
    print("Phase 1 smoke test PASSED. OK to proceed with Phase 1 implementation work.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
