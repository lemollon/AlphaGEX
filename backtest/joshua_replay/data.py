"""Replay data loader.

Reads `watchtower_snapshots` for a date range and produces GexSnapshot
objects. The table already has populated flip_point / call_wall / put_wall
columns. The regime column is 3-level (POSITIVE/NEGATIVE/NEUTRAL) — we
upgrade it to the 7-level scheme that the spec setups gate on.
"""
from __future__ import annotations

import datetime as dt
import math
import os
from typing import List, Optional

import psycopg2
import psycopg2.extras

from trading.helios.gex_client import GexSnapshot

TRADING_DAYS_PER_YEAR = 252.0


# total_net_gamma in watchtower_snapshots ranges roughly -3.1M to +1.4M
# Bin into 7 levels using percentile-derived thresholds, calibrated so
# POSITIVE rows map to MODERATE_POSITIVE/HIGH_POSITIVE/EXTREME_POSITIVE
# and NEGATIVE to the mirror. Symmetric thresholds.
HIGH_THRESHOLD = 500_000.0
EXTREME_THRESHOLD = 1_500_000.0


def regime_from_watchtower(gamma_regime: str, total_net_gamma: float) -> str:
    """Map watchtower's 3-level label + magnitude to spec's 7-level."""
    abs_g = abs(total_net_gamma)
    if gamma_regime == "POSITIVE":
        if abs_g >= EXTREME_THRESHOLD:
            return "EXTREME_POSITIVE"
        if abs_g >= HIGH_THRESHOLD:
            return "HIGH_POSITIVE"
        return "MODERATE_POSITIVE"
    if gamma_regime == "NEGATIVE":
        if abs_g >= EXTREME_THRESHOLD:
            return "EXTREME_NEGATIVE"
        if abs_g >= HIGH_THRESHOLD:
            return "HIGH_NEGATIVE"
        return "MODERATE_NEGATIVE"
    return "NEUTRAL"


def regime_from_net_gex_dollars(net_gex: float) -> str:
    """Map dollar-magnitude net_gex (as in gex_history) to 7-level regime.

    Mirrors the thresholds used in backend/api/routes/gex_routes.py for
    the live /api/gex/SPY endpoint.
    """
    if net_gex <= -3e9:
        return "EXTREME_NEGATIVE"
    if net_gex <= -2e9:
        return "HIGH_NEGATIVE"
    if net_gex <= -1e9:
        return "MODERATE_NEGATIVE"
    if net_gex >= 3e9:
        return "EXTREME_POSITIVE"
    if net_gex >= 2e9:
        return "HIGH_POSITIVE"
    if net_gex >= 1e9:
        return "MODERATE_POSITIVE"
    return "NEUTRAL"


def load_snapshots_from_gex_history(
    start: dt.date,
    end: dt.date,
    *,
    symbol: str = "SPY",
    db_url: Optional[str] = None,
) -> List[GexSnapshot]:
    """Alternate loader using `gex_history` table.

    Useful when watchtower_snapshots has wall_data only for very recent
    rows. gex_history has the same shape as the production /api/gex/SPY
    response and historically populated walls/flip on the Nov-Dec 2025
    window (~5-min cadence).
    """
    url = db_url or os.environ["DATABASE_URL"]
    with psycopg2.connect(url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(
                """
                SELECT timestamp, spot_price, net_gex, flip_point, call_wall, put_wall, regime
                FROM gex_history
                WHERE symbol = %s
                  AND timestamp::date BETWEEN %s AND %s
                  AND call_wall > 0
                  AND flip_point > 0
                ORDER BY timestamp ASC
                """,
                (symbol, start, end),
            )
            rows = c.fetchall()

    out: List[GexSnapshot] = []
    for r in rows:
        spot = float(r["spot_price"] or 0.0)
        net_gex = float(r["net_gex"] or 0.0)
        # gex_history has no vix column — approximate from 7-level regime.
        # For replay we use a fixed VIX-equivalent so sigma_1d != 0.
        vix = 18.0
        import math
        sigma_1d = spot * (vix / 100.0) * math.sqrt(1.0 / TRADING_DAYS_PER_YEAR) if spot > 0 else 0.0
        ts = r["timestamp"]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        out.append(GexSnapshot(
            symbol=symbol,
            spot=spot,
            net_gex=net_gex,
            flip_point=float(r["flip_point"] or 0.0),
            call_wall=float(r["call_wall"] or 0.0),
            put_wall=float(r["put_wall"] or 0.0),
            vix=vix,
            regime=regime_from_net_gex_dollars(net_gex),
            sigma_1d_band_width=sigma_1d,
            snapshot_at=ts,
        ))
    return out


def load_snapshots(
    start: dt.date,
    end: dt.date,
    *,
    symbol: str = "SPY",
    db_url: Optional[str] = None,
) -> List[GexSnapshot]:
    """Load snapshots chronologically. (start, end) inclusive."""
    url = db_url or os.environ["DATABASE_URL"]
    with psycopg2.connect(url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(
                """
                SELECT
                    snapshot_time, spot_price, expected_move, vix,
                    total_net_gamma, gamma_regime,
                    flip_point, call_wall, put_wall
                FROM watchtower_snapshots
                WHERE symbol = %s
                  AND snapshot_time::date BETWEEN %s AND %s
                ORDER BY snapshot_time ASC
                """,
                (symbol, start, end),
            )
            rows = c.fetchall()

    out: List[GexSnapshot] = []
    for r in rows:
        net_gex = float(r["total_net_gamma"] or 0.0)
        spot = float(r["spot_price"] or 0.0)
        vix = float(r["vix"] or 0.0)
        em = float(r["expected_move"] or 0.0)
        sigma_1d = em if em > 0 else (
            spot * (vix / 100.0) * math.sqrt(1.0 / TRADING_DAYS_PER_YEAR) if spot > 0 and vix > 0 else 0.0
        )
        out.append(GexSnapshot(
            symbol=symbol,
            spot=spot,
            net_gex=net_gex,
            flip_point=float(r["flip_point"] or 0.0),
            call_wall=float(r["call_wall"] or 0.0),
            put_wall=float(r["put_wall"] or 0.0),
            vix=vix,
            regime=regime_from_watchtower(r["gamma_regime"] or "NEUTRAL", net_gex),
            sigma_1d_band_width=sigma_1d,
            snapshot_at=r["snapshot_time"],
        ))
    return out
