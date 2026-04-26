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

# Plausibility bounds for annualized implied volatility (decimal form).
# Lower bound rejects unset/zero values; upper bound rejects garbage like
# 9999. SPY typically 0.10-0.40, single-name tech 0.30-1.00, COIN/MSTR
# can run 0.50-1.50 around catalysts.
IV_MIN = 0.05
IV_MAX = 5.00

# Required fields in get_net_gamma() return dict (post-parse). These map
# directly onto fields GOLIATH gates and strike mapping depend on.
REQUIRED_NET_GAMMA_FIELDS = ["spot_price", "net_gex", "flip_point", "implied_volatility"]


@dataclass
class TickerResult:
    ticker: str
    spot_price: float = 0.0
    flip_point: float = 0.0
    net_gex: float = 0.0
    implied_volatility: float = 0.0
    has_levels_data: bool = False
    nearest_wall: Optional[float] = None
    iv_source: str = "unknown"           # 'tv_api' or 'hv_proxy'
    iv_source_reason: str = ""
    failures: list = None
    raw_iv_present: bool = False         # was 'implied_volatility' key present in TV raw_data?

    def __post_init__(self):
        if self.failures is None:
            self.failures = []

    @property
    def passed(self) -> bool:
        return not self.failures


def _ensure_table(conn) -> None:
    """Create goliath_iv_source_decisions if not present. Idempotent."""
    with conn.cursor() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS goliath_iv_source_decisions (
                id SERIAL PRIMARY KEY,
                ticker VARCHAR(10) NOT NULL,
                iv_source VARCHAR(20) NOT NULL,
                reason TEXT NOT NULL,
                iv_value_at_decision DECIMAL(10, 6),
                raw_iv_field_present BOOLEAN NOT NULL,
                decided_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_goliath_iv_source_decisions_ticker
            ON goliath_iv_source_decisions(ticker, decided_at DESC)
        """)
    conn.commit()


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
        with get_connection() as conn:
            _ensure_table(conn)
            with conn.cursor() as c:
                c.execute(
                    """
                    INSERT INTO goliath_iv_source_decisions
                        (ticker, iv_source, reason, iv_value_at_decision, raw_iv_field_present)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        result.ticker,
                        result.iv_source,
                        result.iv_source_reason,
                        float(result.implied_volatility),
                        bool(result.raw_iv_present),
                    ),
                )
            conn.commit()
        return True
    except Exception as e:
        print(f"  [DB] persist failed for {result.ticker}: {e}")
        return False


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

    # Distinguish "field present" from "field missing" by inspecting raw_data.
    raw = snap.get("raw_data") or {}
    result.raw_iv_present = "implied_volatility" in raw

    result.spot_price = float(snap.get("spot_price") or 0)
    result.net_gex = float(snap.get("net_gex") or 0)
    result.flip_point = float(snap.get("flip_point") or 0)
    result.implied_volatility = float(snap.get("implied_volatility") or 0)

    # Required-field checks: a value can be present but zero (e.g., flip_point=0
    # means TV did not provide gex_flip_price). Require sensible non-zero spot
    # and non-zero flip; net_gex may legitimately be near zero in neutral regimes.
    if result.spot_price <= 0:
        result.failures.append(f"spot_price={result.spot_price} (expected > 0)")
    if result.flip_point <= 0:
        result.failures.append(f"flip_point={result.flip_point} (expected > 0)")

    # IV plausibility — drives Decision 1 IV-source choice.
    if not result.raw_iv_present:
        result.iv_source = "hv_proxy"
        result.iv_source_reason = "TV /gex/latest did not return implied_volatility key"
    elif result.implied_volatility < IV_MIN:
        result.iv_source = "hv_proxy"
        result.iv_source_reason = (
            f"TV implied_volatility={result.implied_volatility:.4f} below plausibility floor {IV_MIN}"
        )
    elif result.implied_volatility > IV_MAX:
        result.iv_source = "hv_proxy"
        result.iv_source_reason = (
            f"TV implied_volatility={result.implied_volatility:.4f} above plausibility ceiling {IV_MAX}"
        )
    else:
        result.iv_source = "tv_api"
        result.iv_source_reason = (
            f"TV implied_volatility={result.implied_volatility:.4f} within [{IV_MIN}, {IV_MAX}]"
        )

    # 2. GEX levels — used for wall identification in strike mapping.
    try:
        levels = client.get_gex_levels(ticker)
    except Exception as e:
        result.failures.append(f"get_gex_levels raised: {e!r}")
        return result

    if not isinstance(levels, dict) or not levels:
        result.failures.append("get_gex_levels returned empty (no wall data available)")
        return result

    result.has_levels_data = True

    # GEX_0 is TV's primary key gamma level; treat as the candidate wall.
    gex_0 = float(levels.get("gex_0") or 0)
    gex_flip = float(levels.get("gex_flip") or 0)
    if gex_0 > 0:
        result.nearest_wall = gex_0
    elif gex_flip > 0:
        # Fall back to flip level as a wall proxy if GEX_0 is missing.
        result.nearest_wall = gex_flip
    else:
        result.failures.append("levels response had neither gex_0 nor gex_flip")

    return result


def _print_summary_table(results: list) -> None:
    print()
    print("=" * 110)
    print("GOLIATH TV COVERAGE SUMMARY")
    print("=" * 110)
    header = (
        f"{'Ticker':<7} {'Spot':>10} {'Flip':>10} {'NetGEX':>14} "
        f"{'IV':>8} {'Wall':>10} {'IVSource':>10} {'Status':>8}"
    )
    print(header)
    print("-" * 110)
    for r in results:
        wall_str = f"${r.nearest_wall:.2f}" if r.nearest_wall else "—"
        status = "PASS" if r.passed else "FAIL"
        print(
            f"{r.ticker:<7} "
            f"${r.spot_price:>9.2f} "
            f"${r.flip_point:>9.2f} "
            f"{r.net_gex:>13.2e} "
            f"{r.implied_volatility:>7.4f} "
            f"{wall_str:>10} "
            f"{r.iv_source:>10} "
            f"{status:>8}"
        )
    print("-" * 110)


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

    api_key_set = any(
        os.getenv(name)
        for name in ("TRADING_VOLATILITY_API_KEY", "TRADINGVOL_API_KEY", "TV_USERNAME", "tv_username")
    )
    if not api_key_set:
        print("FATAL: no TV API key in env. Set TRADING_VOLATILITY_API_KEY.")
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
