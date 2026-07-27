"""Rolling 0DTE order-flow state for the UPDRAFT / BACKDRAFT call book.

WHY THIS EXISTS
---------------
Both legs of the book trigger on `flow_imb_30` — the 30-minute imbalance
between 0DTE call and put volume:

    flow_imb_30 = (calls_30m - puts_30m) / (calls_30m + puts_30m)

Tradier reports option `volume` as a CUMULATIVE session total per contract,
not as an interval. So a 30-minute imbalance cannot be read from a single
chain snapshot — it has to be differenced across two snapshots taken 30
minutes apart. That is what this module stores.

The scanner runs every 5 minutes, so a 30-minute window is 6 snapshots back.
Persisting to the database rather than an in-process buffer matters: Render
restarts on every deploy, and an in-memory ring buffer would leave both bots
blind for the first 30 minutes after each one.

FIDELITY TO THE BACKTEST
------------------------
In the research dataset `call_vol`/`put_vol` are the sum over ALL 0DTE
strikes for that minute (ingest/build_spy_gex_minute.py), with no strike
window. `record_snapshot` therefore totals the entire chain. Narrowing to
near-the-money strikes would compute a different quantity from the one the
edge was measured on.

The spot leg of the signal (`r30_bp`, the 30-minute return in basis points)
is derived from the same snapshots so both halves of the signal are read
from one consistent clock.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

TABLE = "spreadworks_flow_snapshots"

# 30-minute window. Tolerance is generous because APScheduler fires on a
# best-effort schedule and a skipped cycle must not silently shorten the
# window — better to use a 27- or 34-minute lookback than to compute a
# 5-minute imbalance and call it 30.
WINDOW_MIN = 30
WINDOW_TOL_MIN = 8

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id           SERIAL PRIMARY KEY,
    ticker       VARCHAR(16)      NOT NULL,
    expiration   DATE             NOT NULL,
    snapshot_time TIMESTAMP       NOT NULL,
    trade_date   DATE             NOT NULL,
    spot         DOUBLE PRECISION NOT NULL,
    call_volume  BIGINT           NOT NULL,
    put_volume   BIGINT           NOT NULL
)
"""
DDL_IDX = (f"CREATE INDEX IF NOT EXISTS {TABLE}_lookup_idx "
           f"ON {TABLE} (ticker, trade_date, snapshot_time)")


@dataclass(frozen=True)
class FlowState:
    """The two signal inputs, plus enough context to debug a live scan."""
    flow_imb_30: float | None
    r30_bp: float | None
    spot: float
    call_volume_30m: int | None
    put_volume_30m: int | None
    lookback_min: float | None
    reason: str | None = None      # why the signal is unavailable, if it is

    def ready(self) -> bool:
        return self.flow_imb_30 is not None and self.r30_bp is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "flow_imb_30": self.flow_imb_30, "r30_bp": self.r30_bp,
            "spot": self.spot, "call_volume_30m": self.call_volume_30m,
            "put_volume_30m": self.put_volume_30m,
            "lookback_min": self.lookback_min, "reason": self.reason,
        }


def ensure_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(DDL))
        conn.execute(text(DDL_IDX))


def chain_volume_totals(options: list[dict[str, Any]]) -> tuple[int, int]:
    """Total call and put volume across the WHOLE 0DTE chain.

    Matches the research definition: every strike, no window. Contracts that
    have not traded report volume 0 (or None) and contribute nothing.
    """
    calls = puts = 0
    for o in options:
        try:
            v = int(o.get("volume") or 0)
        except (TypeError, ValueError):
            continue
        if v <= 0:
            continue
        if o.get("type") == "call":
            calls += v
        elif o.get("type") == "put":
            puts += v
    return calls, puts


def record_snapshot(engine: Engine, *, ticker: str, expiration: Any,
                    now: datetime, spot: float,
                    options: list[dict[str, Any]]) -> FlowState:
    """Persist this scan's cumulative volumes and return the 30-min state.

    Safe to call on every scan for every bot: writes are cheap and the
    read-back is a single indexed lookup.
    """
    calls, puts = chain_volume_totals(options)
    trade_date = now.date()
    try:
        ensure_table(engine)
        with engine.begin() as conn:
            conn.execute(text(
                f"INSERT INTO {TABLE} (ticker, expiration, snapshot_time, "
                "trade_date, spot, call_volume, put_volume) "
                "VALUES (:tk, :ex, :ts, :td, :sp, :cv, :pv)"
            ), {"tk": ticker, "ex": expiration, "ts": now, "td": trade_date,
                "sp": float(spot), "cv": calls, "pv": puts})
    except Exception as e:                       # never break a scan on this
        logger.warning(f"flow snapshot write failed for {ticker}: {e}")
        return FlowState(None, None, spot, None, None, None,
                         reason=f"snapshot_write_failed: {e}")

    return read_state(engine, ticker=ticker, now=now, spot=spot,
                      calls_now=calls, puts_now=puts)


def read_state(engine: Engine, *, ticker: str, now: datetime, spot: float,
               calls_now: int, puts_now: int) -> FlowState:
    """Difference against the snapshot closest to 30 minutes ago."""
    lo = now - timedelta(minutes=WINDOW_MIN + WINDOW_TOL_MIN)
    hi = now - timedelta(minutes=WINDOW_MIN - WINDOW_TOL_MIN)
    try:
        with engine.begin() as conn:
            row = conn.execute(text(
                f"SELECT snapshot_time, spot, call_volume, put_volume "
                f"FROM {TABLE} "
                "WHERE ticker = :tk AND trade_date = :td "
                "  AND snapshot_time BETWEEN :lo AND :hi "
                # closest to exactly WINDOW_MIN ago
                "ORDER BY ABS(EXTRACT(EPOCH FROM (snapshot_time - :target))) "
                "LIMIT 1"
            ), {"tk": ticker, "td": now.date(), "lo": lo, "hi": hi,
                "target": now - timedelta(minutes=WINDOW_MIN)}).mappings().first()
    except Exception as e:
        logger.warning(f"flow state read failed for {ticker}: {e}")
        return FlowState(None, None, spot, None, None, None,
                         reason=f"state_read_failed: {e}")

    if row is None:
        # Normal for the first ~30 minutes of a session, or after a restart.
        return FlowState(None, None, spot, None, None, None,
                         reason="warming_up: no snapshot ~30m back")

    d_call = int(calls_now) - int(row["call_volume"])
    d_put = int(puts_now) - int(row["put_volume"])
    prior_spot = float(row["spot"])
    lookback = (now - row["snapshot_time"]).total_seconds() / 60.0

    # Cumulative volume must not go backwards within a session. If it does,
    # the chain root changed or the session rolled - do not fabricate a
    # signal from it.
    if d_call < 0 or d_put < 0:
        return FlowState(None, None, spot, None, None, lookback,
                         reason="volume_went_backwards: chain root changed?")
    total = d_call + d_put
    if total <= 0:
        return FlowState(None, None, spot, d_call, d_put, lookback,
                         reason="no_volume_in_window")
    if prior_spot <= 0:
        return FlowState(None, None, spot, d_call, d_put, lookback,
                         reason="bad_prior_spot")

    return FlowState(
        flow_imb_30=(d_call - d_put) / total,
        r30_bp=1e4 * (float(spot) / prior_spot - 1.0),
        spot=float(spot),
        call_volume_30m=d_call, put_volume_30m=d_put,
        lookback_min=lookback,
    )


def purge_old(engine: Engine, keep_days: int = 10) -> None:
    """Housekeeping — the table only needs today to function."""
    try:
        with engine.begin() as conn:
            conn.execute(text(
                f"DELETE FROM {TABLE} WHERE trade_date < "
                "CURRENT_DATE - CAST(:d AS INTEGER)"), {"d": keep_days})
    except Exception as e:
        logger.warning(f"flow snapshot purge failed: {e}")
