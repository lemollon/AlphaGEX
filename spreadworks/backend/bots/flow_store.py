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

THE TWO HALVES TRUNCATE DIFFERENTLY AT THE OPEN
-----------------------------------------------
Research builds the two features with different SQL, and they behave
differently in the first half hour (ingest/build_spy_gex_minute.py):

    flow_imb_30  <- SUM(...) OVER (PARTITION BY trade_date ORDER BY ts
                                   ROWS 29 PRECEDING)
    r30_bp       <- 1e4*(spot/LAG(spot,30) OVER (PARTITION BY trade_date) - 1)

A ROWS-PRECEDING window TRUNCATES at the session boundary, so `flow_imb_30`
is defined from the very first bar (09:31 ET) over however many minutes have
elapsed. `LAG(spot,30)` does not — it is NULL until bar 31, so `r30_bp` is
undefined until 10:00 ET. Measured on the warehouse: earliest minute with a
non-null flow_imb_30 = 09:31, with a non-null r30_bp = 10:00.

That asymmetry is why BACKDRAFT (flow only) takes 12 of its 119 backtested
entries between 09:31 and 09:36 ET while UPDRAFT (flow AND momentum) has no
entry before 10:00. To reproduce it live:

  * snapshots are recorded from 08:00 CT, BEFORE the entry window opens, so
    a pre-open baseline with cumulative volume 0 exists. Differencing against
    it yields exactly "volume since the open" — the truncated window.
  * `r30_bp` is withheld whenever the baseline snapshot predates the session
    open, which makes the first live r30 land at 09:00 CT / 10:00 ET, matching
    LAG(spot,30). Without that guard the pre-open spot would leak a synthetic
    30-minute return across the opening gap and let UPDRAFT trade in a window
    the backtest never traded.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
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

# Regular-session open in Central Time (scanner clocks are CT throughout).
# A snapshot taken before this is a valid ZERO baseline for volume — 0DTE
# contracts do not trade pre-open — but never a valid baseline for a return.
SESSION_OPEN_CT = time(8, 30)

# The suite runs SQLite and production runs Postgres, so the DDL has to be
# dialect-aware (SERIAL and DOUBLE PRECISION are Postgres-only spellings).
def _ddl(sqlite: bool) -> str:
    pk = ("INTEGER PRIMARY KEY AUTOINCREMENT" if sqlite
          else "SERIAL PRIMARY KEY")
    dbl = "REAL" if sqlite else "DOUBLE PRECISION"
    return f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id            {pk},
    ticker        VARCHAR(16) NOT NULL,
    expiration    DATE,
    snapshot_time TIMESTAMP   NOT NULL,
    trade_date    DATE        NOT NULL,
    spot          {dbl}       NOT NULL,
    call_volume   BIGINT      NOT NULL,
    put_volume    BIGINT      NOT NULL,
    straddle_pct  {dbl}
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
    reason: str | None = None      # why the flow reading is unavailable
    # Why r30_bp specifically is unavailable while flow_imb_30 is fine. The
    # two truncate differently at the open (see module docstring), so
    # BACKDRAFT can trade on a state that UPDRAFT must decline.
    r30_reason: str | None = None

    def ready(self) -> bool:
        return self.flow_imb_30 is not None and self.r30_bp is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "flow_imb_30": self.flow_imb_30, "r30_bp": self.r30_bp,
            "spot": self.spot, "call_volume_30m": self.call_volume_30m,
            "put_volume_30m": self.put_volume_30m,
            "lookback_min": self.lookback_min, "reason": self.reason,
            "r30_reason": self.r30_reason,
        }


def ensure_table(engine: Engine) -> None:
    sqlite = engine.dialect.name == "sqlite"
    with engine.begin() as conn:
        conn.execute(text(_ddl(sqlite)))
        conn.execute(text(DDL_IDX))
    # Widen tables created before straddle_pct existed. Postgres and SQLite
    # both lack a portable IF NOT EXISTS here, so failure = already present.
    try:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN straddle_pct DOUBLE PRECISION"
                              if engine.dialect.name != "sqlite" else
                              f"ALTER TABLE {TABLE} ADD COLUMN straddle_pct REAL"))
    except Exception:
        pass



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
    read-back is a single indexed lookup. The timestamp is floored to the
    minute and a minute already on file is not rewritten — UPDRAFT and
    BACKDRAFT scan the same ticker in the same cycle, so without that the
    table carries two identical rows per minute.
    """
    calls, puts = chain_volume_totals(options)
    straddle = atm_straddle_pct(options, spot)
    ts = now.replace(second=0, microsecond=0)
    trade_date = now.date()
    try:
        ensure_table(engine)
        with engine.begin() as conn:
            dup = conn.execute(text(
                f"SELECT 1 FROM {TABLE} WHERE ticker = :tk AND trade_date = :td "
                "  AND snapshot_time >= :t0 AND snapshot_time < :t1 LIMIT 1"
            ), {"tk": ticker, "td": trade_date, "t0": ts,
                "t1": ts + timedelta(minutes=1)}).first()
            if dup is None:
                conn.execute(text(
                    f"INSERT INTO {TABLE} (ticker, expiration, snapshot_time, "
                    "trade_date, spot, call_volume, put_volume, straddle_pct) "
                    "VALUES (:tk, :ex, :ts, :td, :sp, :cv, :pv, :st)"
                ), {"tk": ticker, "ex": expiration, "ts": ts, "td": trade_date,
                    "sp": float(spot), "cv": calls, "pv": puts,
                    "st": straddle})
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
    # Candidates are few (one per 5-minute scan inside a 16-minute band), so
    # pick the closest to exactly WINDOW_MIN ago in Python. Doing it in SQL
    # would need EXTRACT(EPOCH ...), which is Postgres-only and breaks the
    # SQLite test suite.
    target = now - timedelta(minutes=WINDOW_MIN)
    try:
        with engine.begin() as conn:
            rows = conn.execute(text(
                f"SELECT snapshot_time, spot, call_volume, put_volume "
                f"FROM {TABLE} "
                "WHERE ticker = :tk AND trade_date = :td "
                "  AND snapshot_time BETWEEN :lo AND :hi "
                "ORDER BY snapshot_time"
            ), {"tk": ticker, "td": now.date(), "lo": lo,
                "hi": hi}).mappings().all()
    except Exception as e:
        logger.warning(f"flow state read failed for {ticker}: {e}")
        return FlowState(None, None, spot, None, None, None,
                         reason=f"state_read_failed: {e}")

    def _aware(t):
        """Normalise a stored timestamp so it can be compared to `target`.

        SQLite round-trips a tz-aware datetime as an ISO STRING and hands
        back naive values for plain TIMESTAMP columns; Postgres returns
        datetimes. Coerce both shapes, then match awareness.
        """
        if isinstance(t, str):
            try:
                t = datetime.fromisoformat(t)
            except ValueError:
                return target          # unparseable: treat as exact match
        if t.tzinfo is None and target.tzinfo is not None:
            return t.replace(tzinfo=target.tzinfo)
        if t.tzinfo is not None and target.tzinfo is None:
            return t.replace(tzinfo=None)
        return t

    row = min(rows, key=lambda r: abs(_aware(r["snapshot_time"]) - target),
              default=None)

    if row is None:
        # Normal for the first ~30 minutes of a session, or after a restart.
        return FlowState(None, None, spot, None, None, None,
                         reason="warming_up: no snapshot ~30m back")

    d_call = int(calls_now) - int(row["call_volume"])
    d_put = int(puts_now) - int(row["put_volume"])
    prior_spot = float(row["spot"])
    base_ts = _aware(row["snapshot_time"])
    lookback = (now - base_ts).total_seconds() / 60.0

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

    # r30_bp is the STRICTER half. Research derives it from LAG(spot,30)
    # partitioned by trade_date, which is NULL until 30 minutes into the
    # session; a pre-open baseline would measure the opening gap instead and
    # hand UPDRAFT a return the backtest never saw. Withhold it — the volume
    # window truncates at the open, the return window does not.
    r30: float | None = None
    r30_reason: str | None = None
    # Same tzinfo as `target`, which is what _aware() normalises rows to.
    session_open = now.replace(hour=SESSION_OPEN_CT.hour,
                               minute=SESSION_OPEN_CT.minute,
                               second=0, microsecond=0)
    if prior_spot <= 0 or float(spot) <= 0:
        r30_reason = "bad_prior_spot"
    elif base_ts < session_open:
        r30_reason = ("pre_open_baseline: r30 undefined until 30m after the "
                      "open (matches LAG(spot,30) in research)")
    else:
        r30 = 1e4 * (float(spot) / prior_spot - 1.0)

    return FlowState(
        flow_imb_30=(d_call - d_put) / total,
        r30_bp=r30,
        spot=float(spot),
        call_volume_30m=d_call, put_volume_30m=d_put,
        lookback_min=lookback,
        r30_reason=r30_reason,
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


# ---------------------------------------------------------------------------
# HOURLY RSI — the REVERSAL leg's trigger
# ---------------------------------------------------------------------------
# The third leg fires when hourly RSI(14) closes back ABOVE 30 after having
# been below it. Direction matters enormously and was measured twice:
#
#   entry on the RECOVERY cross (RSI back above 30)   SPY +10.68%, XSP +12.58%
#   entry on the CROSS DOWN (buying into the fall)    SPY  -3.87%, XSP  -3.74%
#   entry while merely oversold (RSI < 30 as a state) SPY  +1.24%, XSP  +2.66%
#
# So this must never fire on "RSI is low" — only on the bar where it crosses
# back up. Buying into oversold is a losing trade, not a slightly worse one.
#
# The hourly series is rebuilt from the same 5-minute snapshots the flow
# signal uses, so both halves of the book read one clock. `purge_old` keeps
# 10 days ~= 65 hourly bars, comfortably more than RSI(14) needs. A fresh
# deploy has no history and correctly reports unavailable until roughly three
# sessions of snapshots accumulate.

RSI_PERIOD = 14
RSI_THRESHOLD = 30.0


@dataclass(frozen=True)
class RsiState:
    """Hourly RSI(14) and whether THIS bar is the recovery cross."""
    rsi: float | None
    prev_rsi: float | None
    recovery_cross: bool
    bars_used: int
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"rsi": self.rsi, "prev_rsi": self.prev_rsi,
                "recovery_cross": self.recovery_cross,
                "bars_used": self.bars_used, "reason": self.reason}


def _wilder_rsi(closes: list[float], period: int = RSI_PERIOD) -> list[float]:
    """Wilder's RSI. Same recursion as the research pandas ewm(alpha=1/period,
    adjust=False), so live and backtest values agree bar for bar."""
    out: list[float] = []
    avg_gain = avg_loss = None
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        gain, loss = max(ch, 0.0), max(-ch, 0.0)
        if avg_gain is None:
            avg_gain, avg_loss = gain, loss
        else:
            a = 1.0 / period
            avg_gain = avg_gain + a * (gain - avg_gain)
            avg_loss = avg_loss + a * (loss - avg_loss)
        if avg_loss == 0:
            out.append(100.0 if avg_gain > 0 else 50.0)
        else:
            rs = avg_gain / avg_loss
            out.append(100.0 - 100.0 / (1.0 + rs))
    return out


# ---------------------------------------------------------------------------
# PATIENT ENTRY — resting limit orders (2026-07-29)
# ---------------------------------------------------------------------------
# Research: UPDRAFT's signal improves MONOTONICALLY when the entry is a limit
# 10-20% below the signal-time mid, fill-or-skip within 10 minutes (TEST
# +7.8% market -> +17.1% at -20%; chosen -15% on TRAIN). UPDRAFT-ONLY: the
# same reframe FLIPS EMBREACH NEGATIVE (a put pulling back means the breach
# is failing) — do not arm it for other legs without their own evidence.

PENDING_TABLE = "spreadworks_pending_entries"


def _ensure_pending(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(
            f"CREATE TABLE IF NOT EXISTS {PENDING_TABLE} ("
            "bot VARCHAR(32) PRIMARY KEY, created_at TIMESTAMP NOT NULL, "
            "expires_at TIMESTAMP NOT NULL, strike NUMERIC NOT NULL, "
            "side VARCHAR(8) NOT NULL, expiration VARCHAR(16) NOT NULL, "
            "limit_price NUMERIC NOT NULL, signal_mid NUMERIC NOT NULL)"))


def arm_pending(engine: Engine, bot: str, *, strike: float, side: str,
                expiration: str, limit_price: float, signal_mid: float,
                now: datetime, ttl_min: int = 10) -> None:
    _ensure_pending(engine)
    with engine.begin() as conn:
        conn.execute(text(
            f"DELETE FROM {PENDING_TABLE} WHERE bot = :b"), {"b": bot})
        conn.execute(text(
            f"INSERT INTO {PENDING_TABLE} (bot, created_at, expires_at, "
            "strike, side, expiration, limit_price, signal_mid) VALUES "
            "(:b, :c, :e, :k, :s, :x, :l, :m)"),
            {"b": bot, "c": now, "e": now + timedelta(minutes=ttl_min),
             "k": strike, "s": side, "x": expiration,
             "l": limit_price, "m": signal_mid})


def read_pending(engine: Engine, bot: str, now: datetime) -> dict[str, Any] | None:
    """The live pending order, or None. Expired rows are deleted on read."""
    _ensure_pending(engine)
    try:
        with engine.begin() as conn:
            row = conn.execute(text(
                f"SELECT strike, side, expiration, limit_price, signal_mid, "
                f"expires_at FROM {PENDING_TABLE} WHERE bot = :b"),
                {"b": bot}).mappings().first()
            if row is None:
                return None
            exp = row["expires_at"]
            if isinstance(exp, str):
                exp = datetime.fromisoformat(exp)
            if exp is not None and exp.replace(tzinfo=None) <= now.replace(tzinfo=None):
                conn.execute(text(
                    f"DELETE FROM {PENDING_TABLE} WHERE bot = :b"), {"b": bot})
                return None
            return dict(row)
    except Exception as e:                                  # noqa: BLE001
        logger.warning(f"pending read failed for {bot}: {e}")
        return None


def clear_pending(engine: Engine, bot: str) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(text(
                f"DELETE FROM {PENDING_TABLE} WHERE bot = :b"), {"b": bot})
    except Exception as e:                                  # noqa: BLE001
        logger.warning(f"pending clear failed for {bot}: {e}")


@dataclass(frozen=True)
class DaySignalState:
    """Did a proven intraday signal fire at ANY point earlier today?

    AFTERGLOW/EMBER research: the day's signal predicts the NEXT TWO DAYS.
    These flags are read in the last minutes of the session (entry window
    14:50-14:59 CT), so the day is effectively complete when they're read."""
    updraft_fired: bool
    rsi_recovery_fired: bool
    n_snapshots: int
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"updraft_fired": self.updraft_fired,
                "rsi_recovery_fired": self.rsi_recovery_fired,
                "n_snapshots": self.n_snapshots, "reason": self.reason}


def read_day_signal_state(engine: Engine, *, ticker: str, now: datetime,
                          flow_max: float = -0.1378, r30_min: float = 19.23,
                          rsi_period: int = RSI_PERIOD,
                          rsi_threshold: float = RSI_THRESHOLD,
                          seed_closes: list[tuple[str, float]] | None = None
                          ) -> DaySignalState:
    """Walk today's snapshots and flag whether (a) the UPDRAFT gates
    (flow_imb_30 <= flow_max AND r30 >= r30_min) held at any snapshot, and
    (b) an hourly RSI recovery cross happened at any of TODAY's hourly
    closes. Same snapshot clock and the same 30-minute window the live
    scanner trades on."""
    try:
        with engine.begin() as conn:
            rows = conn.execute(text(
                f"SELECT snapshot_time, spot, call_volume, put_volume "
                f"FROM {TABLE} WHERE ticker = :tk AND trade_date = :td "
                "AND snapshot_time < :now ORDER BY snapshot_time"),
                {"tk": ticker, "td": now.date(), "now": now}).mappings().all()
    except Exception as e:                                  # noqa: BLE001
        logger.warning(f"day signal read failed: {e}")
        return DaySignalState(False, False, 0, f"db_error: {e}")

    def _dt(t):
        if isinstance(t, str):
            try:
                return datetime.fromisoformat(t)
            except ValueError:
                return None
        return t

    snaps = []
    for r in rows:
        t = _dt(r["snapshot_time"])
        if t is not None and (t.hour, t.minute) >= (8, 30):
            snaps.append((t.replace(tzinfo=None), float(r["spot"]),
                          int(r["call_volume"] or 0), int(r["put_volume"] or 0)))
    if not snaps:
        return DaySignalState(False, False, 0, "no_rth_snapshots")

    # (a) UPDRAFT gates at any snapshot vs the one ~30 minutes before it
    updraft = False
    for i, (t, spot, cv, pv) in enumerate(snaps):
        target = t - timedelta(minutes=WINDOW_MIN)
        best = None
        for t0, s0, c0, p0 in snaps[:i]:
            off = abs((t0 - target).total_seconds())
            if off <= WINDOW_TOL_MIN * 60 and (best is None or off < best[0]):
                best = (off, s0, c0, p0)
        if best is None:
            continue
        _, s0, c0, p0 = best
        dc, dp = cv - c0, pv - p0
        if dc < 0 or dp < 0 or (dc + dp) <= 0 or s0 <= 0:
            continue
        imb = (dc - dp) / (dc + dp)
        r30 = 1e4 * (spot / s0 - 1.0)
        if imb <= flow_max and r30 >= r30_min:
            updraft = True
            break

    # (b) hourly RSI recovery cross at any of TODAY's closed hourly bars
    buckets: dict[Any, float] = {}
    for iso_hour, close in (seed_closes or []):
        try:
            buckets[datetime.fromisoformat(str(iso_hour) + ":00:00")] = float(close)
        except (ValueError, TypeError):
            continue
    try:
        with engine.begin() as conn:
            allrows = conn.execute(text(
                f"SELECT snapshot_time, spot FROM {TABLE} "
                "WHERE ticker = :tk AND snapshot_time < :now "
                "ORDER BY snapshot_time"), {"tk": ticker, "now": now}
            ).mappings().all()
    except Exception:                                       # noqa: BLE001
        allrows = []
    for r in allrows:
        t = _dt(r["snapshot_time"])
        if t is None:
            continue
        buckets[t.replace(minute=0, second=0, microsecond=0,
                          tzinfo=None)] = float(r["spot"])
    cur = now.replace(minute=0, second=0, microsecond=0, tzinfo=None)
    keys = [k for k in sorted(buckets) if k < cur]
    closes = [buckets[k] for k in keys]
    rsi_fired = False
    if len(closes) >= rsi_period + 2:
        series = _wilder_rsi(closes, rsi_period)
        # series[j] corresponds to keys[len(keys)-len(series)+j]
        off = len(keys) - len(series)
        for j in range(1, len(series)):
            if keys[off + j].date() != now.date():
                continue
            if series[j] >= rsi_threshold and series[j - 1] < rsi_threshold:
                rsi_fired = True
                break

    return DaySignalState(updraft, rsi_fired, len(snaps))


def read_rsi_state(engine: Engine, *, ticker: str, now: datetime,
                   period: int = RSI_PERIOD,
                   threshold: float = RSI_THRESHOLD,
                   seed_closes: list[tuple[str, float]] | None = None
                   ) -> RsiState:
    """Hourly RSI from stored snapshots, and whether we just crossed back up.

    Only bars that have CLOSED are used. The hour containing `now` is still
    forming, and including it would let an in-progress move trigger an entry
    that the backtest could not have taken.

    `seed_closes` is an optional [(ISO hour, close)] history (Tradier
    timesales via ChainProvider.get_hourly_closes). Without it a cold table
    needs ~2.5 SESSIONS of snapshots before RSI(14) is computable, so the leg
    sits out for days after any reset. Snapshots WIN on overlapping hours:
    they are the same clock the flow half of the book reads, so splicing that
    way keeps both halves consistent.
    """
    try:
        with engine.begin() as conn:
            rows = conn.execute(text(
                f"SELECT snapshot_time, spot FROM {TABLE} "
                "WHERE ticker = :tk AND snapshot_time < :now "
                "ORDER BY snapshot_time"), {"tk": ticker, "now": now}
            ).mappings().all()
    except Exception as e:                                  # noqa: BLE001
        logger.warning(f"rsi read failed: {e}")
        return RsiState(None, None, False, 0, f"db_error: {e}")

    if not rows and not seed_closes:
        return RsiState(None, None, False, 0, "no_snapshots")

    def _dt(t):
        """SQLite hands back an ISO STRING for TIMESTAMP columns; Postgres
        returns a datetime. Same split `read_state._aware` exists for — and
        the reason the first version of this crashed only under SQLite."""
        if isinstance(t, str):
            try:
                return datetime.fromisoformat(t)
            except ValueError:
                return None
        return t

    # last spot of each clock hour == the hourly close
    buckets: dict[Any, float] = {}
    # seed first so live snapshots overwrite any hour they also cover
    for iso_hour, close in (seed_closes or []):
        try:
            buckets[datetime.fromisoformat(str(iso_hour) + ":00:00")] = float(close)
        except (ValueError, TypeError):
            continue
    for r in rows:
        t = _dt(r["snapshot_time"])
        if t is None:
            continue
        key = t.replace(minute=0, second=0, microsecond=0, tzinfo=None)
        buckets[key] = float(r["spot"])
    if not buckets:
        return RsiState(None, None, False, 0, "no_parseable_timestamps")

    # drop the in-progress hour — an unfinished bar must never trigger
    cur = now.replace(minute=0, second=0, microsecond=0, tzinfo=None)
    keys = [k for k in sorted(buckets) if k < cur]
    closes = [buckets[k] for k in keys]

    need = period + 2          # +1 for the diff, +1 for a previous RSI value
    if len(closes) < need:
        return RsiState(None, None, False, len(closes),
                        f"insufficient_history: {len(closes)} bars, need {need}")

    series = _wilder_rsi(closes, period)
    if len(series) < 2:
        return RsiState(None, None, False, len(closes), "rsi_too_short")

    rsi, prev = series[-1], series[-2]
    cross = (rsi >= threshold) and (prev < threshold)
    return RsiState(round(rsi, 2), round(prev, 2), cross, len(closes))


# ---------------------------------------------------------------------------
# EM-BREACH — day-open state and the ATM straddle (the day's priced move)
# ---------------------------------------------------------------------------
# The EM_BREACH leg fires when the session's move from open first crosses
# BELOW -em_frac x the ATM straddle %. Research (hf_28/hf_29/em-breach memo):
# continuation, +6-13%/trade, crushes a time-matched placebo by +28-42pts,
# and the edge lives on ORDINARY days — it is NEGATIVE when the open already
# priced a catalyst (top-decile open straddle), so the open straddle is
# stored per snapshot and the first RTH snapshot's value gates the leg.


def atm_straddle_pct(options: list[dict[str, Any]], spot: float) -> float | None:
    """ATM call mid + put mid as % of spot — the day's priced expected move."""
    if not spot or spot <= 0:
        return None
    def mids(side):
        out = {}
        for o in options or []:
            if o.get("type") != side:
                continue
            b, a = float(o.get("bid") or 0), float(o.get("ask") or 0)
            if b > 0 and a >= b:
                out[float(o["strike"])] = (b + a) / 2.0
        return out
    cm, pm = mids("call"), mids("put")
    shared = set(cm) & set(pm)
    if not shared:
        return None
    k = min(shared, key=lambda x: abs(x - spot))
    return 100.0 * (cm[k] + pm[k]) / spot


@dataclass(frozen=True)
class EmState:
    """Day-open anchor plus the PREVIOUS snapshot, for first-touch detection."""
    day_open: float | None
    open_straddle_pct: float | None
    prev_spot: float | None
    prev_straddle_pct: float | None
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"day_open": self.day_open,
                "open_straddle_pct": self.open_straddle_pct,
                "prev_spot": self.prev_spot,
                "prev_straddle_pct": self.prev_straddle_pct,
                "reason": self.reason}


@dataclass(frozen=True)
class OrState:
    """The 08:31-09:00 CT opening range plus the previous snapshot.

    FLASHPOINT fires on the first cross ABOVE the completed range, but only
    when the range itself was WIDE relative to the day's priced move —
    or_width_pct / open_straddle_pct is the gate. prev_spot makes the entry
    an EVENT (same first-touch construction as EM_BREACH)."""
    or_high: float | None
    or_low: float | None
    or_complete: bool
    day_open: float | None
    open_straddle_pct: float | None
    prev_spot: float | None
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"or_high": self.or_high, "or_low": self.or_low,
                "or_complete": self.or_complete, "day_open": self.day_open,
                "open_straddle_pct": self.open_straddle_pct,
                "prev_spot": self.prev_spot, "reason": self.reason}


def read_or_state(engine: Engine, *, ticker: str, now: datetime) -> OrState:
    """Opening range = snapshots 08:30-09:00 CT (inclusive); complete once
    `now` is past 09:01. prev = latest snapshot strictly before `now`."""
    try:
        with engine.begin() as conn:
            rows = conn.execute(text(
                f"SELECT snapshot_time, spot, straddle_pct FROM {TABLE} "
                "WHERE ticker = :tk AND trade_date = :td AND snapshot_time < :now "
                "ORDER BY snapshot_time"),
                {"tk": ticker, "td": now.date(), "now": now}).mappings().all()
    except Exception as e:                                  # noqa: BLE001
        logger.warning(f"or state read failed: {e}")
        return OrState(None, None, False, None, None, None, f"db_error: {e}")

    def _dt(t):
        if isinstance(t, str):
            try:
                return datetime.fromisoformat(t)
            except ValueError:
                return None
        return t

    rth, orr = [], []
    for r in rows:
        t = _dt(r["snapshot_time"])
        if t is None or (t.hour, t.minute) < (8, 30):
            continue
        rth.append((t, r["spot"], r["straddle_pct"]))
        if (t.hour, t.minute) <= (9, 0):
            orr.append(float(r["spot"]))
    if not rth:
        return OrState(None, None, False, None, None, None,
                       "no_rth_snapshots")
    first, last = rth[0], rth[-1]
    complete = (now.hour, now.minute) > (9, 0) and bool(orr)
    return OrState(max(orr) if orr else None,
                   min(orr) if orr else None,
                   complete,
                   float(first[1]),
                   float(first[2]) if first[2] is not None else None,
                   float(last[1]))


def read_em_state(engine: Engine, *, ticker: str, now: datetime) -> EmState:
    """Day open = spot of the first RTH snapshot (>= 08:30 CT); prev = the
    latest snapshot strictly before `now`. Prev is what makes the entry an
    EVENT: the leg only fires on the scan where the breach BEGINS."""
    try:
        with engine.begin() as conn:
            rows = conn.execute(text(
                f"SELECT snapshot_time, spot, straddle_pct FROM {TABLE} "
                "WHERE ticker = :tk AND trade_date = :td AND snapshot_time < :now "
                "ORDER BY snapshot_time"),
                {"tk": ticker, "td": now.date(), "now": now}).mappings().all()
    except Exception as e:                                  # noqa: BLE001
        logger.warning(f"em state read failed: {e}")
        return EmState(None, None, None, None, f"db_error: {e}")
    def _dt(t):
        if isinstance(t, str):
            try:
                return datetime.fromisoformat(t)
            except ValueError:
                return None
        return t
    rth = []
    for r in rows:
        t = _dt(r["snapshot_time"])
        if t is None:
            continue
        if (t.hour, t.minute) >= (8, 30):          # CT session open
            rth.append((t, r["spot"], r["straddle_pct"]))
    if not rth:
        return EmState(None, None, None, None, "no_rth_snapshots")
    first, last = rth[0], rth[-1]
    return EmState(float(first[1]),
                   float(first[2]) if first[2] is not None else None,
                   float(last[1]),
                   float(last[2]) if last[2] is not None else None)
