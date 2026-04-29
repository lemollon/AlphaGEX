#!/usr/bin/env python3
"""GOLIATH v0.3 V03-DATA-1 — daily strike-level snapshot collector.

Pulls /curves/gex_by_strike for each universe underlying via the public
TradingVolatilityAPI.get_gex_profile() method and writes a row per
(ticker, snapshot_date, strike) into goliath_strike_snapshots.

Why this exists (see docs/goliath/goliath-v0.3-todos.md V03-DATA-1):
    Phase 1.5 wall concentration calibration was downgraded to a
    cross-sectional sanity check because TV's v2 API does not expose
    historical strike-level snapshots. This script accumulates our own
    snapshots so V03-WALL-RECAL can recompute proper P25/P75/P90
    distributions after 30+ days of collection.

Schedule (recommended):
    Once daily at 3:00 PM CT (market close). Either via the AlphaGEX
    scheduler (scheduler/trader_scheduler.py) or a Render cron job.

Idempotency:
    UNIQUE constraint on (ticker, snapshot_date, strike). Re-running on
    the same day for the same ticker is a no-op (ON CONFLICT DO NOTHING).
    Safe to run multiple times per day if needed.

Required env:
    TRADING_VOLATILITY_API_TOKEN  — Bearer token (Stripe sub_xxx form)
    DATABASE_URL                   — Postgres connection string

Usage:
    python scripts/goliath_strike_snapshot_collector.py
    python scripts/goliath_strike_snapshot_collector.py --tickers MSTR,TSLA
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from typing import List

# Repo root on sys.path so we can import core_classes_and_engines and database_adapter.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

UNIVERSE = ["MSTR", "TSLA", "NVDA", "COIN", "AMD"]


def _ensure_table(conn) -> None:
    """Create goliath_strike_snapshots if not present. Idempotent."""
    c = conn.cursor()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS goliath_strike_snapshots (
                id SERIAL PRIMARY KEY,
                ticker VARCHAR(10) NOT NULL,
                snapshot_date DATE NOT NULL,
                strike DECIMAL(10, 2) NOT NULL,
                call_gamma DECIMAL(20, 6),
                put_gamma DECIMAL(20, 6),
                total_gamma DECIMAL(20, 6),
                spot_at_snapshot DECIMAL(10, 2),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE (ticker, snapshot_date, strike)
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_goliath_strike_snapshots_lookup
            ON goliath_strike_snapshots(ticker, snapshot_date DESC)
        """)
        conn.commit()
    finally:
        try:
            c.close()
        except Exception:
            pass


def _persist_snapshot(conn, ticker: str, snap_date: date, profile: dict) -> int:
    """Write one underlying's strikes to the table. Returns rows inserted
    (excluding ON CONFLICT skips). Best-effort; never raises."""
    strikes_data = profile.get("strikes") or []
    spot = float(profile.get("spot_price", 0) or 0)
    if not strikes_data or spot <= 0:
        return 0

    c = conn.cursor()
    inserted = 0
    try:
        for s in strikes_data:
            try:
                strike = float(s.get("strike", 0) or 0)
                if not strike:
                    continue
                call_g = float(s.get("call_gamma", 0) or 0)
                put_g = float(s.get("put_gamma", 0) or 0)
                total_g = float(s.get("total_gamma", call_g + put_g) or 0)
                c.execute(
                    """
                    INSERT INTO goliath_strike_snapshots
                        (ticker, snapshot_date, strike, call_gamma, put_gamma,
                         total_gamma, spot_at_snapshot)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker, snapshot_date, strike) DO NOTHING
                    """,
                    (ticker, snap_date, strike, call_g, put_g, total_g, spot),
                )
                if c.rowcount > 0:
                    inserted += 1
            except Exception as exc:
                print(f"  [persist] {ticker} strike={s.get('strike')} skipped: {exc!r}")
                continue
        conn.commit()
    finally:
        try:
            c.close()
        except Exception:
            pass
    return inserted


def collect(tickers: List[str]) -> int:
    """Collect snapshots for the given tickers. Returns total rows inserted
    (across all tickers, excluding ON CONFLICT skips).

    Returns -1 on fatal setup failure (no token, no DB, etc).
    """
    if not os.getenv("TRADING_VOLATILITY_API_TOKEN"):
        print("FATAL: TRADING_VOLATILITY_API_TOKEN not set in env.")
        return -1

    try:
        from core_classes_and_engines import TradingVolatilityAPI  # type: ignore
    except ImportError as exc:
        print(f"FATAL: cannot import TradingVolatilityAPI: {exc!r}")
        return -1

    try:
        from database_adapter import get_connection, is_database_available  # type: ignore
    except ImportError as exc:
        print(f"FATAL: cannot import database_adapter: {exc!r}")
        return -1

    if not is_database_available():
        print("FATAL: DATABASE_URL not set / DB unavailable.")
        return -1

    client = TradingVolatilityAPI()
    snap_date = date.today()
    total_inserted = 0

    conn = get_connection()
    try:
        _ensure_table(conn)
        for ticker in tickers:
            try:
                profile = client.get_gex_profile(ticker, expiration="combined")
                if not profile or "strikes" not in profile:
                    print(f"  [{ticker}] no strikes returned -- skipping")
                    continue
                inserted = _persist_snapshot(conn, ticker, snap_date, profile)
                strikes_count = len(profile.get("strikes") or [])
                spot = profile.get("spot_price", 0)
                print(f"  [{ticker}] spot=${spot}, strikes={strikes_count}, inserted={inserted}")
                total_inserted += inserted
            except Exception as exc:
                print(f"  [{ticker}] fetch/persist failed: {exc!r}")
                continue
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return total_inserted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--tickers",
        type=str,
        default=",".join(UNIVERSE),
        help=f"Comma-separated tickers (default: {','.join(UNIVERSE)})",
    )
    args = parser.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if not tickers:
        print("FATAL: empty ticker list")
        return 1

    print(f"GOLIATH strike snapshot collector -- date={date.today().isoformat()}")
    print(f"  tickers: {tickers}")
    inserted = collect(tickers)
    if inserted < 0:
        return 1
    print(f"DONE. Total rows inserted: {inserted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
