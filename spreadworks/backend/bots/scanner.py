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
)
from .monitor import (
    decide_exit, pt_pct_for_time_of_day, pt_pct_for_iron_condor_tod,
    MULTI_DAY_STRATEGIES,
)
from .registry import BOT_REGISTRY, get_bot
from .strategies.iron_butterfly import build_iron_butterfly_signal
from .strategies.long_butterfly import build_long_butterfly_signal
from .strategies.iron_condor import build_iron_condor_signal
from .strategies.double_calendar import build_double_calendar_signal
from .strategies.double_diagonal import build_double_diagonal_signal
from .strategies.double_diagonal_credit import build_double_diagonal_credit_signal
from .strategies.dip_buy import build_dip_buy_signal, DEFAULT_PARAMS
from .strategies.setups import detect_setup, compute_indicators, DEFAULT_SETUP_PARAMS
from .strategies.vertical_spread import build_vertical_signal, DEFAULT_VERTICAL_PARAMS
from . import ai_rationale

logger = logging.getLogger("spreadworks.bots.scanner")
CT = ZoneInfo("America/Chicago")
SCAN_TIMEOUT_SEC = 15


class ChainProvider(Protocol):
    def get_chain(self, *, ticker: str, dte: int, today: date) -> dict | None: ...
    def get_leg_mids(self, *, ticker: str, legs: list[dict[str, Any]]) -> list[float]: ...
    def get_daily_history(self, *, ticker: str, days: int) -> list[dict[str, Any]]: ...


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


def _build_signal(*, bot: str, strategy: str, chain_provider: ChainProvider,
                  config: dict, equity: float, today: date,
                  ticker: str, front_dte: int, back_dte: int | None,
                  diag: list[str] | None = None,
                  diag_params: dict | None = None):
    """Build a signal. Returns (signal_or_none, chain_or_none).

    `diag` (if provided) collects the rejection reason from the strategy
    builder OR from chain-fetch failure, so scan_activity.reason can
    surface a specific cause instead of bare "no signal".
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
    raise ValueError(f"unknown strategy {strategy}")


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


def ticker_eval_to_row(e: TickerEval) -> dict[str, Any]:
    """Serialize a TickerEval to a JSON-safe watchlist row. Candidate spread is
    present ONLY when a signal is buildable (status SIGNAL)."""
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
    candidates = [e for e in evals if e.signal is not None]
    if not candidates:
        # surface the last non-held rejection reason, mirroring the old loop
        last_reason = next((e.reason for e in reversed(evals) if e.reason and not e.held), None)
        return {"outcome": "NO_TRADE", "reason": last_reason or "no universe signal"}

    candidates.sort(key=lambda e: e.setup.magnitude_pct, reverse=True)  # deepest dip/rip wins
    best = candidates[0]
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
    pid = open_position(engine, bot, signal.kind, signal, now_ct, notes=notes)
    return {"outcome": "TRADE", "reason": "OPENED", "position_id": pid}


def _evaluate_entry(
    *, engine: Engine, bot: str, meta: dict, cfg: dict, now_ct: datetime,
    chain_provider: ChainProvider, event_blackout: bool, allow_stacking: bool,
    open_count: int, opens: list[dict[str, Any]],
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

    equity = account_equity(engine, bot)
    diag: list[str] = []
    signal, _chain = _build_signal(
        bot=bot, strategy=meta["strategy"], chain_provider=chain_provider,
        config=cfg, equity=equity, today=now_ct.date(),
        ticker=meta["ticker"], front_dte=meta["front_dte"],
        back_dte=meta["back_dte"],
        diag=diag,
    )
    if signal is None:
        return {"outcome": "NO_TRADE", "reason": diag[0] if diag else "no signal"}

    pid = open_position(engine, bot, meta["strategy"], signal, now_ct)
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
            mids = chain_provider.get_leg_mids(ticker=pos["ticker"], legs=legs)
            mtm_value, mtm_pnl = compute_mtm(
                strategy=pos["strategy"], legs=legs,
                entry_price=float(pos["entry_price"]),
                contracts=int(pos["contracts"]),
                leg_mids=mids,
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
                if pos["strategy"] in ("iron_butterfly", "long_butterfly"):
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

            d = decide_exit(
                strategy=pos["strategy"], mtm_pnl=mtm_pnl,
                pt_target_pnl=pt_target, sl_target_pnl=float(pos["sl_target_pnl"]),
                now_ct=now_ct, front_expiration=front_exp,
                eod_close_ct=_parse_time(cfg["eod_close_ct"]),
                event_blackout=event_blackout,
                entry_time=dip_entry_time, hold_days=dip_hold_days,
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
