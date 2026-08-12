"""Per-bot 1-minute scanner orchestration.

A `ChainProvider` is injected so the live scanner uses Tradier (see
routes.py for the existing chain fetcher), but unit tests can pass fakes.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .db import bot_table, load_config
from .executor import (
    account_equity, list_open_positions, open_position,
    close_position, compute_mtm, update_mtm, count_positions_opened_on,
    configured_slippage_per_leg, configured_fill_mode,
)
from .monitor import (
    decide_exit, pt_pct_for_time_of_day, pt_pct_for_iron_condor_tod,
    MULTI_DAY_STRATEGIES,
)

# Every mode of the updraft module. Position rows now store the MODE as their
# strategy (so the UI can say WHICH leg a position belongs to), and this set
# is what keeps mode-labelled rows on the updraft timer-exit path. Legacy
# rows that still say 'updraft' match too.
UPDRAFT_FAMILY = {"updraft", "backdraft", "reversal", "em_breach", "afterburn",
                  "weekender", "flashpoint", "afterglow", "ember", "tempest"}
from .registry import BOT_REGISTRY, get_bot
from .strategies.iron_butterfly import build_iron_butterfly_signal
from .strategies.long_butterfly import build_long_butterfly_signal
from .strategies.iron_condor import build_iron_condor_signal
from .strategies.double_calendar import build_double_calendar_signal
from .strategies.double_diagonal import build_double_diagonal_signal
from .strategies.double_diagonal_credit import build_double_diagonal_credit_signal
from .strategies.pin_drift_combo import build_pin_drift_combo_signal
from .strategies.dip_buy import build_dip_buy_signal, DEFAULT_PARAMS
from .strategies.updraft import (build_updraft_signal,
                                 DEFAULT_PARAMS as UPDRAFT_PARAMS)
from . import flow_store
from .strategies.setups import detect_setup, compute_indicators, DEFAULT_SETUP_PARAMS
from .strategies.vertical_spread import build_vertical_signal, DEFAULT_VERTICAL_PARAMS
from . import ai_rationale

logger = logging.getLogger("spreadworks.bots.scanner")
CT = ZoneInfo("America/Chicago")
SCAN_TIMEOUT_SEC = 15


class ChainProvider(Protocol):
    def get_chain(self, *, ticker: str, dte: int, today: date) -> dict | None: ...
    # A leg mid is None when its quote was missing from the provider response
    # (treating a missing quote as $0.00 marked debit combos negative and
    # tripped phantom SLs, 2026-07-06..08).
    def get_leg_mids(self, *, ticker: str, legs: list[dict[str, Any]]) -> list[float | None]: ...
    def get_daily_history(self, *, ticker: str, days: int) -> list[dict[str, Any]]: ...
    # Optional: per-leg half-spread for taker-cost grading. Providers that
    # don't implement it fall back to the flat per-leg slippage default.
    def get_leg_spreads(self, *, ticker: str, legs: list[dict[str, Any]]) -> list[float | None]: ...


def _slippage_total(chain_provider: Any, ticker: str,
                    legs: list[dict[str, Any]], cfg: dict[str, Any]) -> float:
    """Total spread-crossing cost ($/share) for one structure, per fill mode.

    taker (default): sum of the REAL per-leg half-spreads from live quotes —
      the cost of crossing to the touch on every leg. Any leg whose quote is
      missing/junk falls back to the flat per-leg default so a stale book
      can't zero out the cost.
    half: flat per-leg default x leg count.  mid: 0.
    """
    mode = configured_fill_mode(cfg)
    if mode == "mid":
        return 0.0
    per_leg = configured_slippage_per_leg(cfg)
    if mode == "half":
        return len(legs) * per_leg
    fn = getattr(chain_provider, "get_leg_spreads", None)
    if fn is None:
        return len(legs) * per_leg  # provider can't measure — conservative flat
    try:
        halves = fn(ticker=ticker, legs=legs)
    except Exception as e:  # noqa: BLE001 — never fail a scan on a quote hiccup
        logger.warning(f"get_leg_spreads failed for {ticker}: {e}; flat fallback")
        return len(legs) * per_leg
    return sum(per_leg if (h is None or h <= 0) else float(h) for h in halves)


def _parse_time(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def should_run_scan_loop(now_ct: datetime, *, is_holiday: bool) -> bool:
    """Market-wide gate for the per-minute scan loop.

    The loop should only run on a regular-trading-hours weekday that is not a
    market holiday. This skips ALL bots at once (no opens, no monitoring) when
    the market is closed — there are no real quotes to act on. Per-bot gates
    (entry window, entry_days) live separately in run_scan_cycle.
    """
    if now_ct.weekday() >= 5:      # Sat / Sun
        return False
    if is_holiday:                 # US market holiday
        return False
    if not (8 <= now_ct.hour < 15):  # 08:00–14:59 CT
        return False
    return True


def _log_scan(engine: Engine, bot: str, *, now: datetime, outcome: str,
              reason: str | None = None, signal: dict | None = None,
              position_id: str | None = None) -> None:
    t = bot_table(bot, "scan_activity")
    with engine.begin() as conn:
        conn.execute(text(
            f"INSERT INTO {t} (scan_time, outcome, reason, signal_data, position_id) "
            "VALUES (:t, :o, :r, :s, :p)"
        ), {"t": now, "o": outcome, "r": reason,
            "s": json.dumps(signal) if signal else None, "p": position_id})


def _write_equity_snapshot(engine: Engine, bot: str, now: datetime) -> None:
    cfg = load_config(engine, bot)
    realized_today_q = text(
        f"SELECT COALESCE(SUM(realized_pnl), 0) AS s "
        f"FROM {bot_table(bot, 'closed_trades')} "
        "WHERE DATE(close_time) = DATE(:n)"
    )
    cumulative_q = text(
        f"SELECT COALESCE(SUM(realized_pnl), 0) AS s "
        f"FROM {bot_table(bot, 'closed_trades')}"
    )
    open_q = text(
        f"SELECT COUNT(*) c, COALESCE(SUM(mtm_pnl), 0) u "
        f"FROM {bot_table(bot, 'positions')} WHERE status='OPEN'"
    )
    with engine.begin() as conn:
        r_today = float(conn.execute(realized_today_q, {"n": now}).mappings().first()["s"])
        cumulative = float(conn.execute(cumulative_q).mappings().first()["s"])
        row = conn.execute(open_q).mappings().first()
        open_n = int(row["c"]); unrealized = float(row["u"] or 0)
        equity = float(cfg["starting_capital"]) + cumulative + unrealized
        conn.execute(text(
            f"INSERT INTO {bot_table(bot, 'equity_snapshots')} ("
            "snapshot_time, equity, unrealized_pnl, realized_pnl_today, "
            "cumulative_pnl, open_positions"
            ") VALUES (:t, :e, :u, :r, :c, :n)"
        ), {"t": now, "e": equity, "u": unrealized, "r": r_today,
            "c": cumulative, "n": open_n})


def _within_window(now_ct: datetime, start: str, end: str) -> bool:
    t = now_ct.timetz().replace(tzinfo=None)
    return _parse_time(start) <= t < _parse_time(end)


def _settlement_value(chain_provider: ChainProvider, ticker: str,
                      legs: list[dict[str, Any]], exp: date) -> float | None:
    """Cash-settlement value of an expired structure: signed intrinsic of each
    leg against the official close of the expiry day. None until that close
    appears in daily history (then the caller retries next scan). Mirrors
    SPX/XSP European cash settlement — including half-days, where the close
    is simply the early official close."""
    def _close_for(sym: str) -> float | None:
        bars = chain_provider.get_daily_history(ticker=sym, days=10)
        for b in bars or []:
            if str(b.get("date")) == exp.isoformat() and b.get("close"):
                return float(b["close"])
        return None

    close = _close_for(ticker)
    if close is None and ticker == "XSP":
        # XSP settles at exactly SPX/10; fall back if Tradier serves no XSP
        # daily history.
        spx = _close_for("SPX")
        if spx is not None:
            close = spx / 10.0
    if not close:
        return None
    val = 0.0
    for leg in legs:
        k = float(leg["strike"])
        intr = max(0.0, close - k) if leg["type"] == "call" else max(0.0, k - close)
        val += intr if leg["side"] == "long" else -intr
    # A net-long defined-risk structure settles >= 0 by construction.
    return round(max(0.0, val), 4)


# Same-day settlement must not read the expiry-day close before the market
# has actually closed and the official close has had a few minutes to
# publish. 15:10 CT = 10 minutes after the 15:00 CT close.
SETTLE_EARLIEST_CT = time(15, 10)


def run_settlement_pass(*, engine: Engine, bot: str, now_ct: datetime,
                        chain_provider: ChainProvider) -> list[str]:
    """Same-day post-close settlement for settle_at_expiry bots.

    The per-minute scan loop stops at 14:59 CT — one minute before the close
    that determines settlement exists — so on its own an expired European fly
    sits OPEN overnight and books SETTLE on the next morning's first scan.
    This pass runs shortly after the close and books intrinsic vs the official
    close as soon as Tradier publishes the expiry-day daily bar. The
    next-morning scan path is unchanged and remains the backstop (e.g. if the
    close never publishes in the pass window). Returns the position_ids booked.
    """
    meta = get_bot(bot)
    if not bool(meta.get("settle_at_expiry")):
        return []
    booked: list[str] = []
    for pos in list_open_positions(engine, bot):
        legs = json.loads(pos["legs"])
        pos_exp = date.fromisoformat(legs[0]["expiration"])
        if now_ct.date() < pos_exp:
            continue
        if (now_ct.date() == pos_exp
                and now_ct.timetz().replace(tzinfo=None) < SETTLE_EARLIEST_CT):
            continue
        settle = _settlement_value(chain_provider, pos["ticker"], legs, pos_exp)
        if settle is None:
            logger.info(
                f"[{bot}] {pos['position_id']}: official close for {pos_exp} "
                "not published yet — settlement pass retries next tick"
            )
            continue
        close_position(engine, bot, pos["position_id"],
                       close_value=settle, close_reason="SETTLE", now=now_ct)
        _log_scan(engine, bot, now=now_ct, outcome="TRADE",
                  reason="CLOSE_SETTLE", position_id=pos["position_id"])
        booked.append(pos["position_id"])
    if booked:
        # End the day's equity curve at the settled equity instead of the
        # last pre-close mark (which can detach from intrinsic in the final
        # minutes as 0DTE quotes go junk).
        _write_equity_snapshot(engine, bot, now_ct)
    return booked


def _build_signal(*, bot: str, strategy: str, chain_provider: ChainProvider,
                  config: dict, equity: float, today: date,
                  ticker: str, front_dte: int, back_dte: int | None,
                  diag: list[str] | None = None,
                  diag_params: dict | None = None,
                  engine=None, now_ct: datetime | None = None,
                  prefetched_chain: dict | None = None):
    """Build a signal. Returns (signal_or_none, chain_or_none).

    `diag` (if provided) collects the rejection reason from the strategy
    builder OR from chain-fetch failure, so scan_activity.reason can
    surface a specific cause instead of bare "no signal".

    `prefetched_chain` lets the caller hand in a chain it already fetched
    this scan (UPDRAFT/BACKDRAFT snapshot the flow tape before the entry
    gates run) so the same minute is not fetched from Tradier twice.
    """
    if strategy == "iron_butterfly":
        chain = chain_provider.get_chain(ticker=ticker, dte=front_dte, today=today)
        if chain is None:
            if diag is not None:
                diag.append(f"chain_unavailable: ticker={ticker} dte={front_dte}")
            return None, None
        sig = build_iron_butterfly_signal(chain=chain, config=config, equity=equity, diag=diag)
        return sig, chain
    if strategy == "long_butterfly":
        chain = chain_provider.get_chain(ticker=ticker, dte=front_dte, today=today)
        if chain is None:
            if diag is not None:
                diag.append(f"chain_unavailable: ticker={ticker} dte={front_dte}")
            return None, None
        sig = build_long_butterfly_signal(chain=chain, config=config, equity=equity, diag=diag)
        return sig, chain
    if strategy == "iron_condor":
        chain = chain_provider.get_chain(ticker=ticker, dte=front_dte, today=today)
        if chain is None:
            if diag is not None:
                diag.append(f"chain_unavailable: ticker={ticker} dte={front_dte}")
            return None, None
        sig = build_iron_condor_signal(chain=chain, config=config, equity=equity, diag=diag)
        return sig, chain
    if strategy == "updraft":
        # UPDRAFT / BACKDRAFT. Both need a 30-MINUTE flow imbalance, and
        # Tradier reports option volume CUMULATIVELY, so the signal cannot
        # be read from a single chain. Snapshots are recorded from 08:00 CT
        # by record_flow_snapshot() below — including before the entry
        # window opens, which is what gives the window a pre-open zero
        # baseline to truncate against at the 08:30 CT open. Only the first
        # scans after a mid-session deploy return "warming_up".
        chain = prefetched_chain
        if chain is None:
            chain = chain_provider.get_chain(ticker=ticker, dte=front_dte,
                                             today=today)
        if chain is None:
            if diag is not None:
                diag.append(f"chain_unavailable: ticker={ticker} dte={front_dte}")
            return None, None
        # The bot_config TABLE has a fixed column set, so the strategy's own
        # knobs (mode, flow_max, r30_min, hold_minutes, ...) never round-trip
        # through it — they live only in the registry. Layer them explicitly:
        # module defaults < registry defaults < any live config override.
        reg_defaults = (BOT_REGISTRY.get(bot, {}).get("defaults") or {})
        tunable = ("mode", "flow_max", "r30_min", "backdraft_flow_max",
                   "require_put_wall", "strike_offset", "hold_minutes",
                   "min_option_price", "max_spread_pct", "cooldown_min",
                   "rsi_threshold", "rsi_period",
                   "em_frac", "max_open_straddle_pct", "afterburn_min_ret_pct",
                   "or_width_min_em")
        params = {**UPDRAFT_PARAMS,
                  **{k: reg_defaults[k] for k in tunable if k in reg_defaults},
                  **{k: config[k] for k in tunable
                     if config.get(k) is not None},
                  **(diag_params or {})}
        if chain.get("flow") is None:
            if engine is not None:
                flow = flow_store.record_snapshot(
                    engine, ticker=ticker, expiration=chain.get("expiration"),
                    now=now_ct or datetime.combine(today, time(0, 0)),
                    spot=float(chain.get("spot") or 0),
                    options=chain.get("options") or [])
                chain["flow"] = flow.as_dict()
            else:
                chain["flow"] = {"flow_imb_30": None, "r30_bp": None,
                                 "reason": "no_engine: cannot read flow history"}
        # REVERSAL reads hourly RSI off the same snapshot history. Attached
        # only for that mode so the other two legs do not pay a query per
        # scan for a value they never read.
        if str(params.get("mode") or "") in ("reversal", "tempest") and chain.get("rsi") is None:
            if engine is not None:
                # Seed the hourly series from Tradier so a cold snapshot table
                # does not sideline this leg for ~2.5 sessions. Best-effort:
                # if the provider cannot supply history the snapshot-only path
                # still works, it just needs to warm up first.
                seed = []
                getter = getattr(chain_provider, "get_hourly_closes", None)
                if callable(getter):
                    try:
                        seed = getter(ticker=ticker) or []
                    except Exception as e:                  # noqa: BLE001
                        logger.debug(f"rsi seed unavailable for {ticker}: {e}")
                chain["rsi"] = flow_store.read_rsi_state(
                    engine, ticker=ticker,
                    now=now_ct or datetime.combine(today, time(0, 0)),
                    period=int(params.get("rsi_period") or 14),
                    threshold=float(params.get("rsi_threshold") or 30.0),
                    seed_closes=seed,
                ).as_dict()
            else:
                chain["rsi"] = {"rsi": None, "recovery_cross": False,
                                "reason": "no_engine: cannot read rsi history"}
        # EM_BREACH reads the day-open anchor and the previous snapshot off
        # the same table. Attached only for that mode, same as rsi above.
        if (str(params.get("mode") or "") in ("em_breach", "afterburn",
                                              "weekender", "tempest")
                and chain.get("em") is None):
            if engine is not None:
                chain["em"] = flow_store.read_em_state(
                    engine, ticker=ticker,
                    now=now_ct or datetime.combine(today, time(0, 0)),
                ).as_dict()
            else:
                chain["em"] = {"day_open": None,
                               "reason": "no_engine: cannot read day state"}
        # AFTERGLOW/EMBER read the day-signal flags off the same snapshots.
        if (str(params.get("mode") or "") in ("afterglow", "ember")
                and chain.get("dayx") is None):
            if engine is not None:
                seed = []
                getter = getattr(chain_provider, "get_hourly_closes", None)
                if callable(getter):
                    try:
                        seed = getter(ticker=ticker) or []
                    except Exception as e:                  # noqa: BLE001
                        logger.debug(f"dayx seed unavailable: {e}")
                chain["dayx"] = flow_store.read_day_signal_state(
                    engine, ticker=ticker,
                    now=now_ct or datetime.combine(today, time(0, 0)),
                    flow_max=float(params.get("flow_max") or -0.1378),
                    r30_min=float(params.get("r30_min") or 19.23),
                    rsi_period=int(params.get("rsi_period") or 14),
                    rsi_threshold=float(params.get("rsi_threshold") or 30.0),
                    seed_closes=seed,
                ).as_dict()
            else:
                chain["dayx"] = {"updraft_fired": False,
                                 "rsi_recovery_fired": False,
                                 "reason": "no_engine: cannot read day state"}
        # FLASHPOINT reads the opening range off the same snapshot table.
        if (str(params.get("mode") or "") in ("flashpoint", "tempest")
                and chain.get("orx") is None):
            if engine is not None:
                chain["orx"] = flow_store.read_or_state(
                    engine, ticker=ticker,
                    now=now_ct or datetime.combine(today, time(0, 0)),
                ).as_dict()
            else:
                chain["orx"] = {"or_high": None,
                                "reason": "no_engine: cannot read day state"}
        sig = build_updraft_signal(
            chain=chain, today=today, params=params,
            mode=str(params.get("mode") or "updraft"),
            config=config, equity=equity, diag=diag)
        return sig, chain
    if strategy == "dip_buy":
        params = {**DEFAULT_PARAMS, **(diag_params or {})}
        chain = chain_provider.get_chain(ticker=ticker, dte=front_dte, today=today)
        if chain is None:
            if diag is not None:
                diag.append(f"chain_unavailable: ticker={ticker} dte={front_dte}")
            return None, None
        lookback_days = max(int(params["sma_period"]), int(params["lookback_n"])) + 25
        history = chain_provider.get_daily_history(ticker=ticker, days=lookback_days)
        if not history:
            if diag is not None:
                diag.append(f"history_unavailable: ticker={ticker}")
            return None, None
        sig = build_dip_buy_signal(
            chain=chain, history=history, today=today, params=params,
            config=config, equity=equity, diag=diag,
        )
        return sig, chain
    front = chain_provider.get_chain(ticker=ticker, dte=front_dte, today=today)
    back = chain_provider.get_chain(ticker=ticker, dte=back_dte, today=today)
    if front is None or back is None:
        if diag is not None:
            diag.append(
                f"chain_unavailable: ticker={ticker} front_dte={front_dte} "
                f"back_dte={back_dte} front_ok={front is not None} back_ok={back is not None}"
            )
        return None, None
    if strategy == "double_calendar":
        sig = build_double_calendar_signal(
            front_chain=front, back_chain=back, config=config, equity=equity, diag=diag
        )
        return sig, front
    if strategy == "double_diagonal":
        sig = build_double_diagonal_signal(
            front_chain=front, back_chain=back, config=config, equity=equity, diag=diag
        )
        return sig, front
    if strategy == "double_diagonal_credit":
        sig = build_double_diagonal_credit_signal(
            front_chain=front, back_chain=back, config=config, equity=equity, diag=diag
        )
        return sig, front
    if strategy == "pin_drift_combo":
        sig = build_pin_drift_combo_signal(
            front_chain=front, back_chain=back, config=config, equity=equity, diag=diag
        )
        return sig, front
    raise ValueError(f"unknown strategy {strategy}")


def record_flow_snapshot(
    *, engine: Engine, meta: dict, now_ct: datetime,
    chain_provider: ChainProvider,
) -> dict | None:
    """Snapshot the 0DTE volume tape for UPDRAFT/BACKDRAFT and return the chain.

    Runs on EVERY scan for a flow bot, ahead of and independent of every
    entry gate. Two reasons it cannot live behind the entry window:

      1. The window opens at 08:31 CT but the signal differences CUMULATIVE
         volume across ~30 minutes, so the first in-window snapshot is only
         usable at ~08:53 CT. Research truncates its window at the session
         open instead (ROWS 29 PRECEDING) and takes BACKDRAFT signals from
         08:31 CT. Snapshotting from 08:00 CT supplies the pre-open zero
         baseline that reproduces that truncation exactly.
      2. Any other blocking gate — max_concurrent, entry_days, blackout —
         used to stop the snapshot too, punching a hole in the series. A
         hole wider than WINDOW_TOL_MIN blinds the bot after the block
         clears, so a bot holding its 3-position cap for 45 minutes came
         back to a dead signal.

    Returns the chain (with its "flow" block populated) so the caller can
    hand it to _build_signal instead of re-fetching. Never raises.
    """
    try:
        ticker = meta["ticker"]
        chain = chain_provider.get_chain(
            ticker=ticker, dte=int(meta.get("front_dte") or 0),
            today=now_ct.date())
        if chain is None:
            return None
        flow = flow_store.record_snapshot(
            engine, ticker=ticker, expiration=chain.get("expiration"),
            now=now_ct, spot=float(chain.get("spot") or 0),
            options=chain.get("options") or [])
        chain["flow"] = flow.as_dict()
        return chain
    except Exception as e:
        logger.warning(f"[{meta.get('display')}] flow snapshot skipped: {e}")
        return None


def _within_earnings_window(ticker: str, now_ct: datetime, exclude_days: int) -> bool:
    """True if `ticker` reports earnings within `exclude_days` of now.

    Uses earnings_calendar.get_upcoming_earnings; matches the ticker as a
    whitespace token inside the event name (names look like
    '📊 NVDA Earnings (Q1)'). Fail-open (returns False) on ANY error so a
    calendar problem never blocks all entries."""
    if exclude_days <= 0:
        return False
    try:
        from .. import earnings_calendar
        events = earnings_calendar.get_upcoming_earnings(from_date=now_ct, days=exclude_days)
        for e in events:
            if ticker in str(e.get("name", "")).split():
                return True
        return False
    except Exception:
        return False


def _vertical_kind(mode: str, direction: str) -> str:
    if mode == "debit":
        return "bull_call_spread" if direction == "bullish" else "bear_put_spread"
    return "bull_put_spread" if direction == "bullish" else "bear_call_spread"


@dataclass
class TickerEval:
    """One universe name's evaluation. `signal is not None` means a spread is
    currently buildable (would be opened if it's the deepest). Shared by the
    live entry path and the read-only watchlist so they cannot drift."""
    ticker: str
    held: bool
    spot: float | None = None
    chain_expiration: str | None = None
    setup: Any = None          # strategies.setups.Setup | None
    signal: Any = None         # strategies.vertical_spread.VerticalSignal | None
    indicators: dict | None = None
    reason: str | None = None


def _evaluate_ticker(*, engine: Engine | None, bot: str, meta: dict, cfg: dict,
                     now_ct: datetime, chain_provider: ChainProvider, ticker: str,
                     held: bool, equity: float) -> TickerEval:
    """Evaluate ONE universe name. Held names short-circuit WITHOUT fetching
    (preserving the live scanner's skip-held behavior and API cost). For
    non-held names: earnings gate -> chain -> history -> detect_setup ->
    build_vertical_signal, capturing the first rejection reason for display.

    `engine` is not used here (equity is resolved by the caller and passed in);
    it is part of the signature for symmetry with the rest of the scanner's
    per-bot helpers and is forwarded by both callers."""
    if held:
        return TickerEval(ticker=ticker, held=True, reason="held")

    params = dict(meta.get("params") or {})
    if _within_earnings_window(ticker, now_ct, int(params.get("earnings_exclude_days", 0) or 0)):
        return TickerEval(ticker=ticker, held=False, reason=f"earnings_excluded: {ticker}")

    chain = chain_provider.get_chain(ticker=ticker, dte=meta["front_dte"], today=now_ct.date())
    if chain is None:
        return TickerEval(ticker=ticker, held=False, reason=f"chain_unavailable: {ticker}")
    spot = float(chain["spot"])
    exp = chain.get("expiration")

    lookback = max(int(params.get("sma_period", 20)), int(params.get("lookback_n", 5))) + 25
    history = chain_provider.get_daily_history(ticker=ticker, days=lookback)
    if not history:
        return TickerEval(ticker=ticker, held=False, spot=spot, chain_expiration=exp,
                          reason=f"history_unavailable: {ticker}")

    merged = {**DEFAULT_SETUP_PARAMS, **params}
    indicators = compute_indicators(spot=spot, history=history, today=now_ct.date(), params=merged)

    sdiag: list[str] = []
    setup = detect_setup(spot=spot, history=history, today=now_ct.date(),
                         params=merged, diag=sdiag)
    if setup is None:
        return TickerEval(ticker=ticker, held=False, spot=spot, chain_expiration=exp,
                          indicators=indicators,
                          reason=sdiag[0] if sdiag else f"no_setup: {ticker}")

    kind = _vertical_kind(meta.get("vertical_mode", "debit"), setup.direction)
    vdiag: list[str] = []
    signal = build_vertical_signal(kind=kind, chain=chain, config=cfg, equity=equity,
                                   params={**DEFAULT_VERTICAL_PARAMS, **params}, diag=vdiag)
    if signal is None:
        return TickerEval(ticker=ticker, held=False, spot=spot, chain_expiration=exp,
                          setup=setup, indicators=indicators,
                          reason=vdiag[0] if vdiag else f"no_signal: {ticker}")

    return TickerEval(ticker=ticker, held=False, spot=spot, chain_expiration=exp,
                      setup=setup, signal=signal, indicators=indicators)


def evaluate_universe_watchlist(*, engine: Engine | None, bot: str, meta: dict,
                                cfg: dict, now_ct: datetime,
                                chain_provider: ChainProvider) -> list[TickerEval]:
    """READ-ONLY evaluation of every universe name. Never opens, never writes
    scan_activity/equity. One TickerEval per name in meta['universe'] order."""
    opens = list_open_positions(engine, bot)
    held = {p["ticker"] for p in opens}
    equity = account_equity(engine, bot)
    return [
        _evaluate_ticker(engine=engine, bot=bot, meta=meta, cfg=cfg, now_ct=now_ct,
                         chain_provider=chain_provider, ticker=t, held=(t in held),
                         equity=equity)
        for t in meta["universe"]
    ]


def pick_would_open(evals: list[TickerEval]) -> TickerEval | None:
    """The single eval the live scanner would open right now: the deepest-
    magnitude SIGNAL among non-held names. Shared by the live entry path and
    the watchlist's would_open marker so the two always agree. Ties resolve to
    the first in universe order (matches the live path's stable sort)."""
    candidates = [e for e in evals if e.signal is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda e: e.setup.magnitude_pct)


def ticker_eval_to_row(e: TickerEval, would_open: bool = False) -> dict[str, Any]:
    """Serialize a TickerEval to a JSON-safe watchlist row. Candidate spread is
    present ONLY when a signal is buildable (status SIGNAL). `would_open` marks
    the one SIGNAL row the live scanner would actually open this scan (deepest
    dip/rip); only ever True for a SIGNAL row."""
    status = "HELD" if e.held else ("SIGNAL" if e.signal is not None else "WATCHING")
    ind = e.indicators or {}
    row: dict[str, Any] = {
        "ticker": e.ticker,
        "status": status,
        "held": e.held,
        "spot": e.spot,
        "expiration": e.chain_expiration,
        "dip_pct": ind.get("dip_pct"),
        "rip_pct": ind.get("rip_pct"),
        "rsi": ind.get("rsi"),
        "sma20": ind.get("sma"),
        "reason": e.reason,
        "would_open": bool(would_open),
        "candidate": None,
    }
    if e.signal is not None and e.setup is not None:
        s = e.signal
        legs = s.legs()
        long_leg = next((l for l in legs if l["side"] == "long"), {})
        short_leg = next((l for l in legs if l["side"] == "short"), {})
        row["candidate"] = {
            "kind": s.kind,
            "direction": e.setup.direction,
            "long_strike": long_leg.get("strike"),
            "short_strike": short_leg.get("strike"),
            "width": s.width,
            "net": s.net,
            "is_credit": s.is_credit,
            "max_profit": s.max_profit,
            "max_loss": s.max_loss,
            "contracts": s.contracts,
            "pt_target_pnl": s.pt_target_pnl,
            "sl_target_pnl": s.sl_target_pnl,
        }
    return row


def _evaluate_universe_entry(
    *, engine: Engine, bot: str, meta: dict, cfg: dict, now_ct: datetime,
    chain_provider: ChainProvider, opens: list[dict[str, Any]],
) -> dict[str, Any]:
    """Scan the universe; open ONE vertical spread on the deepest qualifying
    dip/rip on a non-held name. Debit bots build bull-call/bear-put spreads;
    credit bots build put-credit/call-credit spreads (resolved by vertical_mode
    + setup direction). Window / concurrent-cap gates ran in the caller."""
    held = {p["ticker"] for p in opens}
    equity = account_equity(engine, bot)
    evals = [
        _evaluate_ticker(engine=engine, bot=bot, meta=meta, cfg=cfg, now_ct=now_ct,
                         chain_provider=chain_provider, ticker=t, held=(t in held),
                         equity=equity)
        for t in meta["universe"]
    ]
    best = pick_would_open(evals)  # deepest dip/rip wins — same rule the watchlist marks
    if best is None:
        # surface the last non-held rejection reason, mirroring the old loop
        last_reason = next((e.reason for e in reversed(evals) if e.reason and not e.held), None)
        return {"outcome": "NO_TRADE", "reason": last_reason or "no universe signal"}

    signal, setup = best.signal, best.setup
    rationale = ai_rationale.generate_entry_rationale(
        bot=bot,
        signal_context={
            "ticker": signal.ticker, "kind": signal.kind, "direction": setup.direction,
            "setup": setup.setup, "magnitude_pct": setup.magnitude_pct,
            "reference_level": setup.reference_level, "rsi": setup.rsi_value,
            "width": signal.width, "net": signal.net, "is_credit": signal.is_credit,
            "max_profit": signal.max_profit, "max_loss": signal.max_loss,
            "pt_target_pnl": signal.pt_target_pnl, "sl_target_pnl": signal.sl_target_pnl,
        },
    )
    notes = json.dumps({
        "ticker": signal.ticker, "kind": signal.kind, "direction": setup.direction,
        "setup": setup.setup, "magnitude_pct": setup.magnitude_pct,
        "reference_level": setup.reference_level, "rsi": setup.rsi_value,
        "width": signal.width, "net": signal.net, "is_credit": signal.is_credit,
        "rationale": rationale,
    })
    pid = open_position(
        engine, bot, signal.kind, signal, now_ct, notes=notes,
        slippage_total=_slippage_total(chain_provider, signal.ticker,
                                       signal.legs(), cfg))
    return {"outcome": "TRADE", "reason": "OPENED", "position_id": pid}


def _evaluate_entry(
    *, engine: Engine, bot: str, meta: dict, cfg: dict, now_ct: datetime,
    chain_provider: ChainProvider, event_blackout: bool, allow_stacking: bool,
    open_count: int, opens: list[dict[str, Any]],
    prefetched_chain: dict | None = None,
) -> dict[str, Any]:
    """Evaluate whether to OPEN a new position. Returns a result dict; never
    opens more than the gates allow. Callers decide whether to invoke this
    (legacy bots only when flat; stacking bots on every entry-day)."""
    if event_blackout:
        return {"outcome": "BLOCKED_EVENT"}
    if not _within_window(now_ct, cfg["entry_start_ct"], cfg["entry_end_ct"]):
        return {"outcome": "BLOCKED_OUTSIDE_WINDOW"}

    # Day-of-week entry gate (MEADOW = Mon/Fri only). entry_days is a CSV of
    # lowercase weekday abbreviations; empty string = no restriction. Only
    # gates OPENING — open positions are still managed any day.
    entry_days = str(cfg.get("entry_days") or "").strip()
    if entry_days:
        allowed = {d.strip().lower() for d in entry_days.split(",") if d.strip()}
        today_abbr = now_ct.strftime("%a").lower()  # mon, tue, wed, ...
        if today_abbr not in allowed:
            return {"outcome": "BLOCKED_ENTRY_DAY",
                    "reason": f"entry_day_blocked: today={today_abbr} allowed={sorted(allowed)}"}

    # Concurrent-position cap — never hold more than max_concurrent_positions
    # open at once (0 = unlimited, mirrors max_contracts). Bounds stacked
    # collateral to ~cap x bp_pct of equity.
    max_concurrent = int(cfg.get("max_concurrent_positions") or 0)
    if max_concurrent > 0 and open_count >= max_concurrent:
        return {"outcome": "BLOCKED_MAX_CONCURRENT",
                "reason": f"max_concurrent_reached: open={open_count} cap={max_concurrent}"}

    # Universe bots (UNDERTOW dip-buy / vertical_debit) scan multiple tickers
    # and open the deepest qualifying dip on a non-held name. Window +
    # concurrent-cap gates above already ran; per-ticker skip + earnings
    # exclusion live inside.
    universe = meta.get("universe")
    if universe and meta.get("vertical_mode"):
        return _evaluate_universe_entry(
            engine=engine, bot=bot, meta=meta, cfg=cfg, now_ct=now_ct,
            chain_provider=chain_provider, opens=opens,
        )

    # Stacking bots open at most ONE new position per entry-day. Closed rows
    # stay in {bot}_positions, so an earlier same-day open-then-close counts.
    if allow_stacking and count_positions_opened_on(engine, bot, now_ct) > 0:
        return {"outcome": "BLOCKED_ALREADY_OPENED_TODAY"}

    # one_entry_per_day (registry meta): after ANY entry today — open OR
    # already closed — do not re-enter. The validated backtests are one
    # morning entry/day; without this gate an early close (e.g. a phantom SL)
    # had the scanner re-buying fresh debits all day (SPLASH opened 3x on
    # 2026-07-08, the last at a junk $0.065 quote).
    if bool(meta.get("one_entry_per_day")) and count_positions_opened_on(engine, bot, now_ct) > 0:
        return {"outcome": "BLOCKED_ALREADY_OPENED_TODAY"}

    # PATIENT ENTRY (2026-07-29, UPDRAFT-only research): with
    # limit_entry_frac > 0 a fresh signal ARMS a resting limit
    # (1-frac) x signal mid for 10 minutes instead of buying instantly;
    # later scans FILL it if the ask touches. TEST +7.8% -> +11.9%/trade at
    # -15%. Verified NOT to transfer to EMBREACH (flips negative) — only
    # bots whose registry carries the knob ever enter this path.
    reg_d = ((BOT_REGISTRY.get(bot) or {}).get("defaults") or {})
    limit_frac = float(
        cfg.get("limit_entry_frac")
        if cfg.get("limit_entry_frac") is not None
        else reg_d.get("limit_entry_frac") or 0)
    if limit_frac > 0 and meta["strategy"] == "updraft" and engine is not None:
        pend = flow_store.read_pending(engine, bot, now_ct)
        if pend:
            chain = chain_provider.get_chain(
                ticker=meta["ticker"], dte=meta["front_dte"],
                today=now_ct.date())
            # A waiting limit must not blind the flow window — record the
            # tape exactly as the signal path would (the BLOCKED-entry
            # snapshot rule).
            if chain:
                try:
                    flow_store.record_snapshot(
                        engine, ticker=meta["ticker"],
                        expiration=chain.get("expiration"), now=now_ct,
                        spot=float(chain.get("spot") or 0),
                        options=chain.get("options") or [])
                except Exception as e:                      # noqa: BLE001
                    logger.debug(f"[{bot}] waiting-snapshot failed: {e}")
            opt = None
            for o in (chain or {}).get("options") or []:
                if (float(o.get("strike") or -1) == float(pend["strike"])
                        and str(o.get("type") or "").lower() == str(pend["side"]).lower()):
                    opt = o
                    break
            ask = float((opt or {}).get("ask") or 0)
            if opt and 0 < ask <= float(pend["limit_price"]):
                from .strategies.updraft import UpdraftSignal
                from datetime import date as _date
                debit = round(ask, 4)
                per = debit * 100.0
                equity = account_equity(engine, bot)
                bp = float(cfg.get("bp_pct") or reg_d.get("bp_pct") or 0.02)
                cap = int(cfg.get("max_contracts") or 0)
                raw = int((equity * bp) // per) if per > 0 else 0
                contracts = min(raw, cap) if cap > 0 else raw
                if contracts >= 1:
                    pt_pct = float(cfg.get("pt_pct") or 9.9999)
                    sl_pct = float(cfg.get("sl_pct") or 0.50)
                    reg_mode = str(reg_d.get("mode") or "updraft")
                    fill = UpdraftSignal(
                        ticker=meta["ticker"],
                        expiration=_date.fromisoformat(str(pend["expiration"])),
                        strike=float(pend["strike"]),
                        call_mid=debit, spot=float((chain or {}).get("spot") or 0),
                        mode=reg_mode, flow_imb_30=None, r30_bp=None,
                        put_wall=None,
                        hold_minutes=int(cfg.get("hold_minutes")
                                         or reg_d.get("hold_minutes") or 45),
                        side=str(pend["side"]), debit=debit,
                        contracts=contracts,
                        max_profit=pt_pct * per, max_loss=per,
                        pt_target_pnl=pt_pct * per * contracts,
                        sl_target_pnl=sl_pct * per * contracts)
                    flow_store.clear_pending(engine, bot)
                    # This fill already crossed to the live ask (patient limit
                    # touched) — do NOT charge entry slippage again.
                    pid = open_position(engine, bot, reg_mode, fill, now_ct,
                                        notes="limit_fill", mid_fill=False)
                    if bool(cfg.get("discord_alerts")):
                        try:
                            from . import discord_alerts
                            discord_alerts.post_open(
                                bot=bot, display=meta["display"],
                                strategy=meta["strategy"], position_id=pid,
                                legs=fill.legs(), entry_price=fill.debit,
                                contracts=fill.contracts,
                                max_profit=fill.max_profit * fill.contracts,
                                max_loss=fill.max_loss * fill.contracts)
                        except Exception as e:              # noqa: BLE001
                            logger.warning(f"[{bot}] discord post failed: {e}")
                    return {"outcome": "TRADE",
                            "reason": f"LIMIT_FILLED: ask={ask:.2f} <= "
                                      f"limit={float(pend['limit_price']):.2f} "
                                      f"(signal mid was {float(pend['signal_mid']):.2f})",
                            "position_id": pid}
                flow_store.clear_pending(engine, bot)
                return {"outcome": "NO_TRADE",
                        "reason": f"limit_fill_size_zero: ask={ask:.2f}"}
            return {"outcome": "NO_TRADE",
                    "reason": f"limit_waiting: ask={ask:.2f} need<="
                              f"{float(pend['limit_price']):.2f}"}

    equity = account_equity(engine, bot)
    diag: list[str] = []
    signal, _chain = _build_signal(
        bot=bot, strategy=meta["strategy"], chain_provider=chain_provider,
        engine=engine, now_ct=now_ct,
        config=cfg, equity=equity, today=now_ct.date(),
        ticker=meta["ticker"], front_dte=meta["front_dte"],
        back_dte=meta["back_dte"],
        diag=diag,
        prefetched_chain=prefetched_chain,
    )
    if signal is None:
        return {"outcome": "NO_TRADE", "reason": diag[0] if diag else "no signal"}

    # PATIENT ENTRY arm: a fresh signal rests a limit instead of buying.
    if limit_frac > 0 and meta["strategy"] == "updraft" and engine is not None:
        lim = round(float(signal.call_mid) * (1.0 - limit_frac), 2)
        flow_store.arm_pending(
            engine, bot, strike=float(signal.strike), side=str(signal.side),
            expiration=(signal.expiration.isoformat()
                        if hasattr(signal.expiration, "isoformat")
                        else str(signal.expiration)),
            limit_price=lim, signal_mid=float(signal.call_mid),
            now=now_ct, ttl_min=10)
        return {"outcome": "NO_TRADE",
                "reason": f"limit_armed: mid={float(signal.call_mid):.2f} "
                          f"resting {lim:.2f} for 10min"}

    # Store the MODE (updraft/backdraft/reversal/em_breach/afterburn) as the
    # position's strategy so four bots sharing one module stay tellable apart
    # in the positions UI. bot_config has no mode column, so the registry
    # defaults are the source of truth here.
    reg_mode = str(((BOT_REGISTRY.get(bot) or {}).get("defaults") or {})
                   .get("mode") or "")
    # TEMPEST stores the SUB-mode that actually fired, so its positions are
    # tellable apart leg by leg (and the per-leg exit params travel on the
    # position row as usual).
    store_mode = (getattr(signal, "mode", None)
                  if reg_mode == "tempest" else reg_mode)
    pid = open_position(
        engine, bot, store_mode or meta["strategy"], signal, now_ct,
        slippage_total=_slippage_total(chain_provider, signal.ticker,
                                       signal.legs(), cfg))
    if bool(cfg.get("discord_alerts")):
        try:
            from . import discord_alerts
            discord_alerts.post_open(
                bot=bot, display=meta["display"], strategy=meta["strategy"],
                position_id=pid, legs=signal.legs(),
                entry_price=getattr(signal, "credit", None) if hasattr(signal, "credit") else signal.debit,
                contracts=signal.contracts,
                max_profit=signal.max_profit * signal.contracts,
                max_loss=signal.max_loss * signal.contracts,
            )
        except Exception as e:
            logger.warning(f"[{bot}] discord post_open failed: {e}")
    return {"outcome": "TRADE", "reason": "OPENED", "position_id": pid}


def run_scan_cycle(
    *, engine: Engine, bot: str, now_ct: datetime,
    chain_provider: ChainProvider, event_blackout: bool,
) -> dict[str, Any]:
    """Execute one scan cycle for `bot`. Returns dict with at least 'outcome' key."""
    meta = get_bot(bot)
    cfg = load_config(engine, bot)
    result: dict[str, Any] = {"outcome": "NO_TRADE", "reason": None}

    try:
        if not bool(cfg.get("enabled")):
            result = {"outcome": "BLOCKED_DISABLED"}
            return result

        allow_stacking = bool(cfg.get("allow_stacking"))
        opens = list_open_positions(engine, bot)

        # --- Monitor every open position (runs every scan, on any weekday) ---
        # A held position is managed (PT/SL/EOD) regardless of entry day. A
        # close logged this scan outranks a plain MONITOR for the headline.
        monitor_result: dict[str, Any] | None = None
        for pos in opens:
            legs = json.loads(pos["legs"])
            # --- Cash settlement (settle_at_expiry bots, e.g. RIPPLE) ---
            # European index flies are never bought back; the first scan AFTER
            # expiry books intrinsic vs the official close. Runs before any
            # quote fetch — the contracts no longer trade.
            if bool(meta.get("settle_at_expiry")):
                pos_exp = date.fromisoformat(legs[0]["expiration"])
                if now_ct.date() > pos_exp:
                    settle = _settlement_value(chain_provider, pos["ticker"], legs, pos_exp)
                    if settle is None:
                        logger.warning(
                            f"[{bot}] {pos['position_id']}: no official close "
                            f"for {pos_exp} yet — settlement retries next scan"
                        )
                        if monitor_result is None:
                            monitor_result = {"outcome": "MONITOR",
                                              "position_id": pos["position_id"]}
                        continue
                    close_position(engine, bot, pos["position_id"],
                                   close_value=settle, close_reason="SETTLE",
                                   now=now_ct)
                    monitor_result = {"outcome": "TRADE", "reason": "CLOSE_SETTLE",
                                      "position_id": pos["position_id"]}
                    continue
            mids = chain_provider.get_leg_mids(ticker=pos["ticker"], legs=legs)
            marks_stale = any(m is None for m in mids)
            if marks_stale:
                # One or more leg quotes missing — the fresh mark would be
                # garbage (this is what booked negative combo closes and
                # phantom SLs 2026-07-06..08). Keep the last stored mark and
                # let ONLY time-based exits (EOD / EVENT_HALT / TIME_STOP)
                # fire on it, never PT/SL.
                mtm_value = float(pos["mtm_value"] or 0.0)
                mtm_pnl = float(pos["mtm_pnl"] or 0.0)
                logger.warning(
                    f"[{bot}] {pos['position_id']}: leg quote(s) missing — "
                    "skipping PT/SL this scan, holding last mark"
                )
            else:
                mtm_value, mtm_pnl = compute_mtm(
                    strategy=pos["strategy"], legs=legs,
                    entry_price=float(pos["entry_price"]),
                    contracts=int(pos["contracts"]),
                    leg_mids=mids,
                    slippage_total=_slippage_total(
                        chain_provider, pos["ticker"], legs, cfg),
                )
                update_mtm(engine, bot, pos["position_id"], mtm_value, mtm_pnl, now_ct)

            pt_target = float(pos["pt_target_pnl"])
            # Manual Adjust shipped 2026-05-19 sets pt_override=TRUE on
            # the row. When it's set, the scanner respects the stored
            # value and skips the time-of-day ladder.
            pt_override = bool(pos.get("pt_override")) if hasattr(pos, "get") else False
            if not pt_override:
                try:
                    pt_override = bool(pos["pt_override"])
                except (KeyError, IndexError):
                    pt_override = False
            if not pt_override:
                # pt_ladder=False (registry meta) keeps the signal's static PT
                # instead of the intraday 30/25/20 ladder. SPLASH's validated
                # fly exit is hold-to-EOD; the ladder is unvalidated for it.
                if not bool(meta.get("pt_ladder", True)):
                    pass
                elif pos["strategy"] in ("iron_butterfly", "long_butterfly"):
                    # Single-expiration butterflies (BREEZE iron fly, RIVER long
                    # fly) re-derive PT each scan from the DECREASING time-of-day
                    # ladder × max_profit. RIVER was previously NOT re-derived, so
                    # it sat at a static 30%-of-max-profit target that a 0DTE
                    # debit fly only reaches at pin near expiry — unreachable
                    # intraday (2026-05-29: peaked 23.4% of max profit, never
                    # filled). The ladder makes the target reachable late-day.
                    new_pt_pct = pt_pct_for_time_of_day(now_ct.timetz().replace(tzinfo=None))
                    pt_target = new_pt_pct * float(pos["max_profit"])
                elif pos["strategy"] == "iron_condor":
                    # FLOW uses the SPARK-style DECREASING ladder — take less
                    # profit as expiration approaches to dodge late-day gamma.
                    new_pt_pct = pt_pct_for_iron_condor_tod(now_ct.timetz().replace(tzinfo=None))
                    pt_target = new_pt_pct * float(pos["max_profit"])

            front_exp_str = legs[0]["expiration"]  # legs share front expiration order for IBF; for DC/DD the short legs are first
            # For DC/DD the front expiration is the SHORT side, which we
            # placed first in legs[] in both strategy modules.
            front_exp = date.fromisoformat(front_exp_str)

            dip_hold_days = None
            dip_entry_time = None
            if pos["strategy"] in MULTI_DAY_STRATEGIES:
                dip_hold_days = int((meta.get("params") or {}).get("hold_days", 2))
                dip_entry_time = pos["entry_time"] if isinstance(pos["entry_time"], datetime) \
                    else datetime.fromisoformat(str(pos["entry_time"]))

            # UPDRAFT/BACKDRAFT are intraday TIMER exits (45m / 30m). The
            # timer is the real exit — pt_pct is deliberately unreachable
            # because a profit target cut returns ~6x in research.
            hold_minutes = None
            if pos["strategy"] in UPDRAFT_FAMILY:
                hold_minutes = int(cfg.get("hold_minutes")
                                   or (meta.get("defaults") or {}).get("hold_minutes", 45))
                dip_entry_time = pos["entry_time"] if isinstance(pos["entry_time"], datetime) \
                    else datetime.fromisoformat(str(pos["entry_time"]))

            # On a stale mark, disarm PT/SL entirely (targets pushed to ±inf)
            # so only the time-based exits can fire — the position is never
            # stranded past EOD, but it also never closes on a phantom price.
            d = decide_exit(
                strategy=pos["strategy"], mtm_pnl=mtm_pnl,
                pt_target_pnl=float("inf") if marks_stale else pt_target,
                sl_target_pnl=float("inf") if marks_stale else float(pos["sl_target_pnl"]),
                now_ct=now_ct, front_expiration=front_exp,
                eod_close_ct=_parse_time(cfg["eod_close_ct"]),
                event_blackout=event_blackout,
                entry_time=dip_entry_time, hold_days=dip_hold_days,
                hold_minutes=hold_minutes,
                settle_at_expiry=bool(meta.get("settle_at_expiry")),
            )
            if d.should_close:
                close_position(engine, bot, pos["position_id"],
                               close_value=mtm_value, close_reason=d.reason,
                               now=now_ct)
                if bool(cfg.get("discord_alerts")):
                    try:
                        from . import discord_alerts
                        entry_dt = pos["entry_time"] if isinstance(pos["entry_time"], datetime) \
                            else datetime.fromisoformat(str(pos["entry_time"]))
                        if entry_dt.tzinfo is None:
                            entry_dt = entry_dt.replace(tzinfo=now_ct.tzinfo)
                        mins = int((now_ct - entry_dt).total_seconds() // 60)
                        discord_alerts.post_close(
                            bot=bot, display=meta["display"], strategy=pos["strategy"],
                            position_id=pos["position_id"], close_reason=d.reason,
                            realized_pnl=mtm_pnl,
                            time_in_trade_min=mins,
                        )
                    except Exception as e:
                        logger.warning(f"[{bot}] discord post_close failed: {e}")
                monitor_result = {"outcome": "TRADE", "reason": f"CLOSE_{d.reason}",
                                  "position_id": pos["position_id"]}
            elif monitor_result is None or monitor_result["outcome"] != "TRADE":
                monitor_result = {"outcome": "MONITOR", "position_id": pos["position_id"]}

        # --- 0DTE flow tape (UPDRAFT / BACKDRAFT) ---
        # Recorded before ANY entry gate and on every scan of the 08:00-14:59
        # CT loop, so the 30-minute window has a pre-open zero baseline to
        # truncate against at the open and no gate can punch a hole in the
        # series. See record_flow_snapshot for why both matter. The chain it
        # fetched is reused below rather than fetched twice.
        flow_chain: dict | None = None
        if meta.get("strategy") == "updraft":
            flow_chain = record_flow_snapshot(
                engine=engine, meta=meta, now_ct=now_ct,
                chain_provider=chain_provider)

        # --- Evaluate a NEW entry ---
        # Legacy (one-at-a-time) bots only open when flat. Stacking bots open
        # on every entry-day even while a position is held (capped to one new
        # entry per entry-day inside _evaluate_entry).
        is_universe = bool(meta.get("universe"))
        entry_result: dict[str, Any] | None = None
        if (not opens) or allow_stacking or is_universe:
            entry_result = _evaluate_entry(
                engine=engine, bot=bot, meta=meta, cfg=cfg, now_ct=now_ct,
                chain_provider=chain_provider, event_blackout=event_blackout,
                allow_stacking=allow_stacking, open_count=len(opens), opens=opens,
                prefetched_chain=flow_chain,
            )

        # --- Headline outcome for logging/return ---
        # A fresh OPEN is most salient; otherwise prefer monitor activity
        # (close/MONITOR) over an entry-block reason; fall back to the block.
        if entry_result is not None and entry_result["outcome"] == "TRADE":
            result = entry_result
        elif monitor_result is not None:
            result = monitor_result
        elif entry_result is not None:
            result = entry_result
        return result
    finally:
        _log_scan(engine, bot, now=now_ct, outcome=result["outcome"],
                  reason=result.get("reason"),
                  position_id=result.get("position_id"))
        _write_equity_snapshot(engine, bot, now_ct)


async def run_scan_cycle_with_timeout(
    *, engine: Engine, bot: str, now_ct: datetime,
    chain_provider: ChainProvider, event_blackout: bool,
) -> dict[str, Any]:
    """Wrap one bot's scan in a 15s timeout so one slow bot can't starve
    the others (memory: 5/15 hung-scanner bug)."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                run_scan_cycle,
                engine=engine, bot=bot, now_ct=now_ct,
                chain_provider=chain_provider, event_blackout=event_blackout,
            ),
            timeout=SCAN_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        logger.warning(f"[{bot}] scan timeout after {SCAN_TIMEOUT_SEC}s")
        return {"outcome": "BLOCKED_TIMEOUT"}
    except Exception as e:
        logger.exception(f"[{bot}] scan exception: {e}")
        return {"outcome": "BLOCKED_EXCEPTION", "reason": str(e)[:200]}
