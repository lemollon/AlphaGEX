"""SpreadWorks BOOK risk API: /api/spreadworks/book-risk

This is the *portfolio* risk surface — how much the whole fleet can lose, how
far under water it is, how much of it is really one bet, and whether any bot
has drifted off its validated config. It is deliberately NOT the Risk Advisor
(`/api/spreadworks/risk-advisor`), which grades market regime from VIX/flow and
says nothing about the book.

Design rules this module holds to:

1. **Every block carries its own freshness.** Each section returns a `fresh`
   object with the timestamp the underlying data was written, how old that is
   in seconds, when the next write is due, and what writes it. Staleness is a
   first-class field, not something the reader has to infer from a number that
   "looks stuck".

2. **Ages are computed SERVER-side.** The stored TIMESTAMP columns are naive
   and written from a CT-aware `datetime.now(America/Chicago)`, so they hold CT
   wall-clock. Handing a naive CT string to the browser and letting
   `new Date(str)` parse it as browser-local is exactly the bug that made a
   dead bot read "just now" forever on BotDashboard. So the frontend never does
   date math here — it renders `age_seconds` and the preformatted CT strings.

3. **Nothing is invented.** The validated cell for the config audit is
   `BOT_REGISTRY[bot]["defaults"]` — the same dict the bot seeds from. The
   drawdown kill line is NOT read from config because no such column exists;
   it is a page-level convention and is labelled as such, with
   `enforced: false`, so nobody reads it as a live control.

4. **SQL stays dialect-portable** (SQLite in tests, Postgres in prod):
   aggregation happens in Python, not in date functions.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .bots.db import bot_table, load_config
from .bots.executor import account_equity
from .bots.registry import BOT_REGISTRY, list_bots
from .db import engine as _global_engine

logger = logging.getLogger("spreadworks.routes_book_risk")
router = APIRouter(prefix="/api/spreadworks/book-risk", tags=["SpreadWorks Book Risk"])

# Tests override this via monkeypatch (same convention as routes_bots).
ENGINE: Engine = _global_engine
CT = ZoneInfo("America/Chicago")

# The scan loop that writes marks, scan rows and equity snapshots.
# Registered in backend/__init__.py as job id "scan_bots":
#   cron minute="*", hour="8-14", day_of_week="mon-fri", tz America/Chicago.
SCAN_FIRST_HOUR = 8
SCAN_LAST_HOUR = 14          # inclusive — the loop stops after 14:59 CT
SCAN_CADENCE_SEC = 60

# The post-close settlement pass — job id "settle_bots":
#   cron minute="10-45", hour="15", day_of_week="mon-fri".
SETTLE_START = time(15, 10)
SETTLE_END = time(15, 45)

# Page convention for the drawdown kill line. NOT enforced anywhere and NOT
# stored in {bot}_config — see block 2's `limit` object, which says so.
DD_LIMIT_PCT = 0.25

# Correlation needs a real paired sample before it means anything. Below this
# many shared trading days we report the pair as underpowered rather than
# printing a confident-looking r off 6 observations.
MIN_PAIRED_DAYS = 20

# Config keys that are OPERATOR SWITCHES, not strategy parameters. A bot being
# armed when the registry default ships it disarmed is not drift from a
# validated cell — it is someone having turned it on, which is the whole point
# of the knob. Leaving them in swamped the audit: the first live read flagged
# 24 of 25 bots, 20 of them for `enabled` alone, burying the handful of real
# sizing edits. `enabled` already has its own ARMED column on the page.
OPERATIONAL_KEYS = frozenset({"enabled", "discord_alerts"})

# Underlyings that are the same macro bet in different wrappers. Two bots on
# SPY and XSP are not diversified just because the tickers differ.
CLUSTERS: dict[str, str] = {
    "SPY": "US equity index",
    "SPX": "US equity index",
    "XSP": "US equity index",
    "QQQ": "US equity index",
    "IWM": "US equity index",
}


# ---------------------------------------------------------------------------
# clock / freshness
# ---------------------------------------------------------------------------

def _is_holiday(d: date) -> bool:
    """Best-effort holiday check; never let its absence break the page.

    The helper lives in `.economic_events`, not on the package — the scheduler
    imports it inside `_start_scheduler` and guards on `content_loaded`, so
    `from . import is_market_holiday` raises ImportError. Getting this wrong
    silently returned False for every date, which would have pointed
    `next_scan_ct` at a market holiday the scan loop never fires on.
    """
    try:
        from .economic_events import is_market_holiday
        return bool(is_market_holiday(d))
    except Exception:
        return False


def _next_scan(now_ct: datetime) -> datetime:
    """Next minute the scan loop will actually fire, in CT.

    Inside the window that is simply the top of the next minute. Outside it
    (evening, weekend, holiday) it is 08:00 CT on the next trading day — which
    is the honest answer to "when does this number move again", and the whole
    reason the page can say FROZEN instead of pretending to be live.
    """
    cur = now_ct.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(8 * 24 * 60):  # bounded walk — a week of minutes
        if (cur.weekday() < 5
                and SCAN_FIRST_HOUR <= cur.hour <= SCAN_LAST_HOUR
                and not _is_holiday(cur.date())):
            return cur
        # Jump straight to the next candidate open rather than stepping minutes.
        if cur.weekday() >= 5 or cur.hour > SCAN_LAST_HOUR or _is_holiday(cur.date()):
            cur = (cur + timedelta(days=1)).replace(hour=SCAN_FIRST_HOUR, minute=0)
        else:  # before the open on a trading day
            cur = cur.replace(hour=SCAN_FIRST_HOUR, minute=0)
    return cur


def _in_scan_window(now_ct: datetime) -> bool:
    return (now_ct.weekday() < 5
            and SCAN_FIRST_HOUR <= now_ct.hour <= SCAN_LAST_HOUR
            and not _is_holiday(now_ct.date()))


def _fmt(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _to_ct(dt: datetime | None) -> datetime | None:
    """Convert a stored naive timestamp from UTC to naive CT.

    MEASURED, not assumed. The scan loop passes a CT-AWARE
    `datetime.now(America/Chicago)` into the writers, which reads like the
    columns should hold CT wall-clock — but the DB session timezone is UTC, so
    Postgres converts on the way into `timestamp without time zone` and what
    lands is UTC. First deploy of this page proved it: mtm_updated_at read
    14:52 while the server's CT clock said 09:53, i.e. exactly -5h, and every
    block tripped clock_mismatch. This confirms the older note on
    `last_scan_at` and refutes the CT reading of the writer.

    Consequence worth knowing: a naive value from these tables is UTC, so
    anything comparing one against a CT-derived boundary is off by the offset.
    (routes_bots.get_status does exactly that for today's P&L; it survives only
    because a 15:00 CT close is still 20:00 UTC on the same calendar date.)
    """
    if dt is None:
        return None
    return dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(CT).replace(tzinfo=None)


def _fresh(*, as_of: datetime | None, now_ct: datetime, next_at: datetime | None,
           source: str, cadence: str, stale_after_sec: int | None) -> dict[str, Any]:
    """The freshness contract every block on this page must satisfy.

    `as_of` is a NAIVE CT datetime as stored. Age is computed here, in CT, so
    the browser never parses a naive string and gets it wrong.
    """
    naive_now = now_ct.replace(tzinfo=None)
    age = int((naive_now - as_of).total_seconds()) if as_of else None
    # A timestamp AHEAD of the server clock means the column is not in the
    # timezone we think it is (a UTC write read as CT lands ~5h in the future).
    # Left unhandled that reads as a small negative age and formats to "just
    # now" forever — a dead bot looking freshly alive, which is precisely the
    # failure this page exists to prevent. Surface it instead of absorbing it.
    clock_mismatch = age is not None and age < -60
    stale = None
    if stale_after_sec is not None:
        stale = age is None or age > stale_after_sec or clock_mismatch
    return {
        "as_of_ct": _fmt(as_of),
        "age_seconds": age,
        "clock_mismatch": clock_mismatch,
        "next_update_ct": _fmt(next_at.replace(tzinfo=None) if next_at else None),
        "next_update_in_seconds": (
            int((next_at.replace(tzinfo=None) - naive_now).total_seconds())
            if next_at else None
        ),
        "source": source,
        "cadence": cadence,
        "stale": stale,
        "stale_after_seconds": stale_after_sec,
    }


# ---------------------------------------------------------------------------
# data loading
# ---------------------------------------------------------------------------

def _open_positions(conn, bot: str) -> list[dict[str, Any]]:
    rows = conn.execute(text(
        f"SELECT position_id, ticker, strategy, contracts, max_loss, max_profit, "
        f"       mtm_pnl, mtm_updated_at, entry_time, legs, account_label "
        f"FROM {bot_table(bot, 'positions')} WHERE status = 'OPEN'"
    )).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        m = d.get("mtm_updated_at")
        if isinstance(m, str):
            try:
                m = datetime.fromisoformat(m)
            except ValueError:
                m = None
        d["mtm_updated_at"] = _to_ct(m)   # stored UTC -> CT
        out.append(d)
    return out


def _daily_realized(conn, bot: str) -> dict[date, float]:
    """CT trading date -> realized P&L booked that day.

    Grouped in Python because DATE() semantics differ between SQLite and
    Postgres and this endpoint has to run on both.
    """
    rows = conn.execute(text(
        f"SELECT close_time, realized_pnl FROM {bot_table(bot, 'closed_trades')}"
    )).mappings().all()
    out: dict[date, float] = {}
    for r in rows:
        ct = r["close_time"]
        if ct is None:
            continue
        if isinstance(ct, str):
            try:
                ct = datetime.fromisoformat(ct)
            except ValueError:
                continue
        # Group on the CT session date. For a 15:00 CT close the UTC date
        # happens to match, but grouping on the raw UTC value would silently
        # roll any post-19:00 CT booking into the next session.
        d = _to_ct(ct).date()
        out[d] = out.get(d, 0.0) + float(r["realized_pnl"] or 0)
    return out


def _last_close_time(conn, bot: str) -> datetime | None:
    r = conn.execute(text(
        f"SELECT MAX(close_time) AS t FROM {bot_table(bot, 'closed_trades')}"
    )).mappings().first()
    t = r["t"] if r else None
    if isinstance(t, str):
        try:
            t = datetime.fromisoformat(t)
        except ValueError:
            return None
    return _to_ct(t)


def _config_updated_at(conn, bot: str) -> datetime | None:
    r = conn.execute(text(
        f"SELECT MAX(updated_at) AS t FROM {bot_table(bot, 'config')}"
    )).mappings().first()
    t = r["t"] if r else None
    if isinstance(t, str):
        try:
            t = datetime.fromisoformat(t)
        except ValueError:
            return None
    return _to_ct(t)


# ---------------------------------------------------------------------------
# math
# ---------------------------------------------------------------------------

def _drawdown(curve: list[tuple[date, float]]) -> dict[str, Any]:
    """Peak-to-current and worst-ever drawdown over an equity curve.

    `curve` is [(date, equity)] ascending. Returns dollars (negative when under
    water) and the fraction of the peak given up.
    """
    if not curve:
        return {"current_dd": 0.0, "current_dd_pct": 0.0, "peak": None,
                "peak_date": None, "days_since_high_water": None,
                "max_dd": 0.0, "max_dd_pct": 0.0, "max_dd_date": None}
    peak = curve[0][1]
    peak_date = curve[0][0]
    run_peak, run_peak_date = peak, peak_date
    max_dd, max_dd_pct, max_dd_date = 0.0, 0.0, None
    for d, eq in curve:
        if eq >= run_peak:
            run_peak, run_peak_date = eq, d
        dd = eq - run_peak
        dd_pct = dd / run_peak if run_peak else 0.0
        if dd < max_dd:
            max_dd, max_dd_pct, max_dd_date = dd, dd_pct, d
    last_date, last_eq = curve[-1]
    cur_dd = last_eq - run_peak
    return {
        "current_dd": round(cur_dd, 2),
        "current_dd_pct": round(cur_dd / run_peak, 6) if run_peak else 0.0,
        "peak": round(run_peak, 2),
        "peak_date": run_peak_date.isoformat(),
        "days_since_high_water": (last_date - run_peak_date).days,
        "max_dd": round(max_dd, 2),
        "max_dd_pct": round(max_dd_pct, 6),
        "max_dd_date": max_dd_date.isoformat() if max_dd_date else None,
    }


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:      # a flat series has no correlation to report
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / (sxx * syy) ** 0.5


# ---------------------------------------------------------------------------
# endpoint
# ---------------------------------------------------------------------------

@router.get("")
@router.get("/")
def get_book_risk() -> dict[str, Any]:
    now_ct = datetime.now(CT)
    next_scan = _next_scan(now_ct)
    in_window = _in_scan_window(now_ct)

    bots: list[dict[str, Any]] = []
    daily: dict[str, dict[date, float]] = {}
    newest_mark: datetime | None = None
    newest_close: datetime | None = None
    newest_cfg: datetime | None = None
    unavailable: list[dict[str, str]] = []

    for bot in list_bots():
        meta = BOT_REGISTRY[bot]
        try:
            # load_config opens its own connection — keep it outside the block
            # below so we never hold two connections per bot against the pool.
            cfg = load_config(ENGINE, bot)
            with ENGINE.begin() as conn:
                opens = _open_positions(conn, bot)
                pnl_by_day = _daily_realized(conn, bot)
                last_close = _last_close_time(conn, bot)
                cfg_at = _config_updated_at(conn, bot)
            equity_realized = float(account_equity(ENGINE, bot))
        except Exception as exc:  # a bot whose tables aren't built yet must not 500 the page
            logger.warning("[book-risk] %s unavailable: %r", bot, exc)
            unavailable.append({"bot": bot, "reason": str(exc)})
            continue

        start_cap = float(cfg["starting_capital"])
        bp_pct = float(cfg["bp_pct"])

        # ---- exposure -----------------------------------------------------
        # positions.max_loss is already TOTAL dollars for the position
        # (executor writes `signal.max_loss * signal.contracts`), so it sums
        # directly — do not multiply by contracts again.
        defined_risk = sum(float(p["max_loss"] or 0) for p in opens)
        unrealized = sum(float(p["mtm_pnl"] or 0) for p in opens)
        # What you can still lose from HERE: the distance from today's mark
        # down to the structural floor. max_loss is a positive magnitude and
        # mtm_pnl is signed, so a position already down $80 of a $400 floor
        # has $320 left to give.
        remaining_downside = sum(
            max(0.0, float(p["max_loss"] or 0) + float(p["mtm_pnl"] or 0)) for p in opens
        )
        equity_mtm = equity_realized + unrealized
        marks = [p["mtm_updated_at"] for p in opens if p["mtm_updated_at"]]
        marks = [datetime.fromisoformat(m) if isinstance(m, str) else m for m in marks]
        oldest_mark = min(marks) if marks else None
        if marks:
            m = max(marks)
            newest_mark = m if newest_mark is None or m > newest_mark else newest_mark
        if last_close and (newest_close is None or last_close > newest_close):
            newest_close = last_close
        if cfg_at and (newest_cfg is None or cfg_at > newest_cfg):
            newest_cfg = cfg_at

        # ---- drawdown -----------------------------------------------------
        curve: list[tuple[date, float]] = []
        cum = 0.0
        days = sorted(pnl_by_day)
        # Seed at starting capital the day BEFORE the first trade. Without it
        # the curve begins at day-1's post-loss equity, that becomes the peak,
        # and a bot that bled from its very first session reports a drawdown
        # of zero — the one moment the number most needs to be right.
        if days:
            curve.append((days[0] - timedelta(days=1), start_cap))
        for d in days:
            cum += pnl_by_day[d]
            curve.append((d, start_cap + cum))
        # Pin the live point on the end so the drawdown reflects open marks,
        # not just the last day something closed.
        if curve and curve[-1][0] == now_ct.date():
            curve[-1] = (now_ct.date(), equity_mtm)
        else:
            curve.append((now_ct.date(), equity_mtm))
        dd = _drawdown(curve)
        limit_dollars = start_cap * DD_LIMIT_PCT
        dd["limit_pct"] = DD_LIMIT_PCT
        dd["limit_dollars"] = round(limit_dollars, 2)
        dd["limit_used_pct"] = (
            round(abs(dd["current_dd"]) / limit_dollars, 6) if limit_dollars else None
        )

        daily[bot] = pnl_by_day

        # ---- config audit --------------------------------------------------
        defaults: dict[str, Any] = meta.get("defaults", {}) or {}
        drift = []
        for k, validated in sorted(defaults.items()):
            if k not in cfg or k in OPERATIONAL_KEYS:
                continue
            live = cfg[k]
            try:
                same = (float(live) == float(validated)) if isinstance(
                    validated, (int, float)) and not isinstance(validated, bool) \
                    else (bool(live) == bool(validated)) if isinstance(validated, bool) \
                    else (str(live) == str(validated))
            except (TypeError, ValueError):
                same = str(live) == str(validated)
            if not same:
                drift.append({
                    "key": k,
                    "live": float(live) if isinstance(live, (int, float))
                            and not isinstance(live, bool) else str(live),
                    "validated": float(validated) if isinstance(validated, (int, float))
                                 and not isinstance(validated, bool) else str(validated),
                })

        bots.append({
            "bot": bot,
            "display": meta["display"],
            "strategy": meta["strategy"],
            "ticker": meta.get("ticker"),
            "cluster": CLUSTERS.get(str(meta.get("ticker") or "").upper(), "other"),
            "enabled": bool(cfg["enabled"]),
            "exposure": {
                "open_positions": len(opens),
                "contracts": sum(int(p["contracts"] or 0) for p in opens),
                "defined_risk": round(defined_risk, 2),
                "unrealized_pnl": round(unrealized, 2),
                "remaining_downside": round(remaining_downside, 2),
                "equity_mtm": round(equity_mtm, 2),
                "starting_capital": round(start_cap, 2),
                "risk_pct_of_capital": round(defined_risk / start_cap, 6) if start_cap else None,
                "bp_pct": bp_pct,
                "one_day_budget": round(start_cap * bp_pct, 2),
                "over_budget": defined_risk > start_cap * bp_pct + 0.005,
                "oldest_mark_ct": _fmt(oldest_mark),
                "oldest_mark_age_seconds": (
                    int((now_ct.replace(tzinfo=None) - oldest_mark).total_seconds())
                    if oldest_mark else None
                ),
            },
            "drawdown": dd,
            "config": {
                "drift": drift,
                "clean": not drift,
                "updated_at_ct": _fmt(cfg_at),
                "max_contracts": int(cfg["max_contracts"]),
                "max_concurrent_positions": int(cfg["max_concurrent_positions"]),
                "sl_pct": float(cfg["sl_pct"]),
                "pt_pct": float(cfg["pt_pct"]),
                "eod_close_ct": str(cfg["eod_close_ct"]),
            },
        })

    # ---- book totals -------------------------------------------------------
    live_bots = [b for b in bots if b["enabled"]]
    total_risk = sum(b["exposure"]["defined_risk"] for b in bots)
    total_remaining = sum(b["exposure"]["remaining_downside"] for b in bots)
    total_cap = sum(b["exposure"]["starting_capital"] for b in bots)
    total_equity = sum(b["exposure"]["equity_mtm"] for b in bots)
    total_budget = sum(b["exposure"]["one_day_budget"] for b in bots)

    # ---- fleet drawdown ----------------------------------------------------
    # Summed across bots on the union of dates with each bot's cumulative P&L
    # carried forward. The fleet's worst day is NOT the sum of each bot's worst
    # day — they happen on different dates — so this has to be recomputed on
    # the combined curve rather than added up.
    all_dates = sorted({d for m in daily.values() for d in m})
    fleet_curve: list[tuple[date, float]] = []
    running = {b: 0.0 for b in daily}
    if all_dates:                       # same pre-trade seed as the per-bot curves
        fleet_curve.append((all_dates[0] - timedelta(days=1), total_cap))
    for d in all_dates:
        for b in daily:
            running[b] += daily[b].get(d, 0.0)
        fleet_curve.append((d, total_cap + sum(running.values())))
    if fleet_curve and fleet_curve[-1][0] == now_ct.date():
        fleet_curve[-1] = (now_ct.date(), total_equity)
    else:
        fleet_curve.append((now_ct.date(), total_equity))
    fleet_dd = _drawdown(fleet_curve)
    fleet_limit = total_cap * DD_LIMIT_PCT
    fleet_dd["limit_pct"] = DD_LIMIT_PCT
    fleet_dd["limit_dollars"] = round(fleet_limit, 2)
    fleet_dd["limit_used_pct"] = (
        round(abs(fleet_dd["current_dd"]) / fleet_limit, 6) if fleet_limit else None
    )

    # ---- correlation -------------------------------------------------------
    # Paired on days where BOTH bots actually closed something. Filling absent
    # days with 0 would manufacture agreement out of two bots simply being idle
    # at the same time, which is the exact false-diversification read this
    # block exists to prevent.
    names = [b["bot"] for b in bots if daily.get(b["bot"])]
    pairs: list[dict[str, Any]] = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            shared = sorted(set(daily[a]) & set(daily[b]))
            n = len(shared)
            r = _pearson([daily[a][d] for d in shared],
                         [daily[b][d] for d in shared]) if n >= MIN_PAIRED_DAYS else None
            pairs.append({
                "a": a, "b": b, "n_days": n,
                "r": round(r, 4) if r is not None else None,
                "underpowered": n < MIN_PAIRED_DAYS,
            })
    pairs.sort(key=lambda p: (p["r"] is None, -(p["r"] or 0)))
    # With 25 bots this list is ~300 entries and, on a young fleet, almost all
    # of them are "need 20, have 1". Rendering every one buries the pairs that
    # actually carry a number and pushes the concentration bars off screen, so
    # ship a summary the page can collapse them into.
    measured = [p for p in pairs if p["r"] is not None]
    underpowered = [p for p in pairs if p["r"] is None]
    max_shared = max((p["n_days"] for p in underpowered), default=0)

    # ---- concentration -----------------------------------------------------
    by_cluster: dict[str, float] = {}
    by_ticker: dict[str, float] = {}
    by_strategy: dict[str, float] = {}
    for b in bots:
        risk = b["exposure"]["defined_risk"]
        if risk <= 0:
            continue
        by_cluster[b["cluster"]] = by_cluster.get(b["cluster"], 0.0) + risk
        by_ticker[str(b["ticker"])] = by_ticker.get(str(b["ticker"]), 0.0) + risk
        by_strategy[b["strategy"]] = by_strategy.get(b["strategy"], 0.0) + risk

    def _share(m: dict[str, float]) -> list[dict[str, Any]]:
        return sorted(
            [{"key": k, "risk": round(v, 2),
              "share": round(v / total_risk, 6) if total_risk else None}
             for k, v in m.items()],
            key=lambda x: -x["risk"])

    # Worst single day the book ever had, all bots summed — the empirical
    # answer to "how bad can one day be", which beats any modelled number.
    day_totals = {d: sum(m.get(d, 0.0) for m in daily.values()) for d in all_dates}
    worst_day = min(day_totals.items(), key=lambda kv: kv[1]) if day_totals else None

    return {
        "generated_at_ct": _fmt(now_ct.replace(tzinfo=None)),
        "clock": {
            "now_ct": _fmt(now_ct.replace(tzinfo=None)),
            "in_scan_window": in_window,
            "scan_window_ct": f"{SCAN_FIRST_HOUR:02d}:00–{SCAN_LAST_HOUR:02d}:59 Mon–Fri",
            "scan_cadence_seconds": SCAN_CADENCE_SEC,
            "settle_window_ct": f"{SETTLE_START:%H:%M}–{SETTLE_END:%H:%M} Mon–Fri",
            "next_scan_ct": _fmt(next_scan.replace(tzinfo=None)),
            "next_scan_in_seconds": int(
                (next_scan.replace(tzinfo=None) - now_ct.replace(tzinfo=None)).total_seconds()),
            "frozen": not in_window,
            "frozen_note": (
                None if in_window else
                "Outside the scan window nothing on this page moves — marks, "
                "equity and drawdown are the last values written before the "
                "loop stopped. This is expected, not a fault."
            ),
        },
        "exposure": {
            "bots": [{"bot": b["bot"], "display": b["display"], "enabled": b["enabled"],
                      "ticker": b["ticker"], "cluster": b["cluster"], **b["exposure"]}
                     for b in bots],
            "totals": {
                "bots_total": len(bots),
                "bots_armed": len(live_bots),
                "open_positions": sum(b["exposure"]["open_positions"] for b in bots),
                "defined_risk": round(total_risk, 2),
                "remaining_downside": round(total_remaining, 2),
                "starting_capital": round(total_cap, 2),
                "equity_mtm": round(total_equity, 2),
                "risk_pct_of_capital": round(total_risk / total_cap, 6) if total_cap else None,
                "one_day_budget": round(total_budget, 2),
                "over_budget": total_risk > total_budget + 0.005,
            },
            "fresh": _fresh(
                as_of=newest_mark, now_ct=now_ct,
                next_at=next_scan,
                source="{bot}_positions.mtm_updated_at — written by the scan loop",
                cadence="every 60s, 08:00–14:59 CT Mon–Fri",
                stale_after_sec=180 if in_window else None,
            ),
        },
        "drawdown": {
            "bots": [{"bot": b["bot"], "display": b["display"], "enabled": b["enabled"],
                      **b["drawdown"]} for b in bots],
            "fleet": fleet_dd,
            "limit": {
                "pct": DD_LIMIT_PCT,
                "enforced": False,
                "note": (
                    "PAGE CONVENTION, NOT A LIVE CONTROL. No kill/pause "
                    "threshold column exists in {bot}_config, so nothing "
                    "auto-pauses at this line — it is drawn so you can see who "
                    "is near it. Making it a real enforced knob is a schema "
                    "change and has not been done."
                ),
            },
            "note": (
                "Fleet drawdown is recomputed on the combined daily curve, not "
                "summed from the per-bot numbers — bots bottom out on different "
                "days, so adding their worst days overstates the book's."
            ),
            "fresh": _fresh(
                as_of=newest_close, now_ct=now_ct, next_at=next_scan,
                source="{bot}_closed_trades.close_time + live marks",
                cadence="moves when a position closes; marks refresh every 60s in-window",
                stale_after_sec=None,
            ),
        },
        "concentration": {
            "correlation": {
                "pairs": pairs,
                "measured_pairs": len(measured),
                "underpowered_pairs": len(underpowered),
                "total_pairs": len(pairs),
                "max_shared_days_among_underpowered": max_shared,
                "min_paired_days": MIN_PAIRED_DAYS,
                "note": (
                    "Pearson r on daily REALIZED P&L, paired only on days both "
                    "bots closed a trade. Pairs under "
                    f"{MIN_PAIRED_DAYS} shared days are reported as "
                    "underpowered rather than given a number."
                ),
            },
            "by_cluster": _share(by_cluster),
            "by_ticker": _share(by_ticker),
            "by_strategy": _share(by_strategy),
            "worst_book_day": (
                {"date": worst_day[0].isoformat(), "pnl": round(worst_day[1], 2),
                 "by_bot": sorted(
                     [{"bot": b, "pnl": round(daily[b].get(worst_day[0], 0.0), 2)}
                      for b in daily if daily[b].get(worst_day[0])],
                     key=lambda x: x["pnl"])}
                if worst_day else None
            ),
            "fresh": _fresh(
                as_of=newest_close, now_ct=now_ct, next_at=next_scan,
                source="{bot}_closed_trades — full history",
                cadence="recomputed on every request; inputs change when a trade closes",
                stale_after_sec=None,
            ),
        },
        "config_audit": {
            "bots": [{"bot": b["bot"], "display": b["display"], "enabled": b["enabled"],
                      **b["config"]} for b in bots],
            "drifted": sum(1 for b in bots if b["config"]["drift"]),
            "validated_source": (
                "backend/bots/registry.py BOT_REGISTRY[bot]['defaults'] — the "
                "same dict the bot seeds from. Drift means the live DB row was "
                "edited away from the validated cell; the DB wins at runtime. "
                f"Operator switches ({', '.join(sorted(OPERATIONAL_KEYS))}) are "
                "excluded — arming a bot is not drift, and it swamped the "
                "sizing edits that matter."
            ),
            "ignored_keys": sorted(OPERATIONAL_KEYS),
            "fresh": _fresh(
                as_of=newest_cfg, now_ct=now_ct, next_at=None,
                source="{bot}_config.updated_at",
                cadence="only changes when a knob is edited",
                stale_after_sec=None,
            ),
        },
        "unavailable": unavailable,
    }


# ─────────────────────────────────────────────────────────────────────────────
# THE BOOK'S MONEY. There was no page that answered "am I up or down".
#
# 🚨 THE GAP THIS CLOSES IS NOT COSMETIC. Per-bot views existed and the fleet
# page existed; nothing summed them. On 2026-08-20 the honest 30-day answer was
# +$4,635 across 12 bots - which becomes -$4,049 with one bot removed and
# -$684 with ONE TRADE removed. Eleven of twelve bots were losing and no
# surface in the app said so.
#
# ⛔ CONCENTRATION IS REPORTED, NOT BURIED. A book whose P&L rests on a single
# fill is a different object from one earning it across trades, and the number
# that tells you which is the largest trade's share. This book has already
# produced two phantom-profit bugs (the force-close $0 mark and the credit
# settlement clamp), so an outsized single fill is a reconciliation prompt.
# ─────────────────────────────────────────────────────────────────────────────

def _window_start(now_ct: datetime, window: str) -> date | None:
    d = now_ct.date()
    if window == "day":
        return d
    if window == "week":
        return d - timedelta(days=d.weekday())      # Monday of this CT week
    if window == "month":
        return d.replace(day=1)
    return None                                      # "all"


@router.get("/money")
def book_money(window: str = "month"):
    """Realized P&L for the whole book, per bot, over a CT window.

    Windows: day | week | month | all. Dollars first - percent is secondary and
    only meaningful against each bot's own starting capital.
    """
    if window not in ("day", "week", "month", "all"):
        window = "month"
    now_ct = datetime.now(CT)
    start = _window_start(now_ct, window)

    bots, book_total, book_n, biggest = [], 0.0, 0, None
    with ENGINE.begin() as conn:
        for bot in list_bots():
            try:
                rows = conn.execute(text(
                    f"SELECT close_time, realized_pnl "
                    f"FROM {bot_table(bot, 'closed_trades')}"
                )).mappings().all()
            except Exception:                        # table absent = never traded
                continue
            tot, n, wins = 0.0, 0, 0
            worst = best = None
            last = None
            for r in rows:
                ct = r["close_time"]
                if ct is None:
                    continue
                if isinstance(ct, str):
                    try:
                        ct = datetime.fromisoformat(ct)
                    except ValueError:
                        continue
                ct = _to_ct(ct)
                if last is None or ct > last:
                    last = ct
                if start is not None and ct.date() < start:
                    continue
                p = float(r["realized_pnl"] or 0)
                tot += p; n += 1
                if p > 0:
                    wins += 1
                worst = p if worst is None or p < worst else worst
                best = p if best is None or p > best else best
                # 🚨 Tracked ACROSS bots, not within one - the concentration
                # question is about the book, not about any single strategy.
                if biggest is None or p > biggest["pnl"]:
                    biggest = {"bot": bot, "pnl": round(p, 2), "date": str(ct.date())}
            if n == 0:
                continue
            cap = None
            try:
                cap = float((load_config(bot) or {}).get("starting_capital") or 0) or None
            except Exception:
                cap = None
            bots.append({
                "bot": bot, "n": n, "total": round(tot, 2),
                "per_trade": round(tot / n, 2),
                "win_pct": round(100.0 * wins / n, 1),
                "best": round(best, 2) if best is not None else None,
                "worst": round(worst, 2) if worst is not None else None,
                "starting_capital": cap,
                "pct_of_capital": round(100.0 * tot / cap, 2) if cap else None,
                "last_trade": last.isoformat() if last else None,
            })
            book_total += tot; book_n += n

    bots.sort(key=lambda b: b["total"], reverse=True)
    losers = [b for b in bots if b["total"] < 0]

    # What the book looks like WITHOUT its single best trade and without its
    # best bot. If either flips the sign, the headline is carried by one thing.
    top = bots[0] if bots else None
    return {
        "window": window,
        "asof": now_ct.isoformat(),
        "start": str(start) if start else None,
        "book_total": round(book_total, 2),
        "book_trades": book_n,
        "bots_total": len(bots),
        "bots_losing": len(losers),
        "top_bot": top["bot"] if top else None,
        "without_top_bot": round(book_total - top["total"], 2) if top else None,
        "biggest_trade": biggest,
        "without_biggest_trade": (round(book_total - biggest["pnl"], 2)
                                  if biggest else None),
        # 🚨 SIGN-AGNOSTIC. The first version required book_total > 0, so a
        # book of -$2,940 carrying a single +$5,319 fill reported
        # concentrated=false - the most concentrated state possible, flagged as
        # fine, because the test only understood profitable books. What matters
        # is whether ONE trade moves the answer, not which side it lands on.
        "concentrated": bool(
            biggest and abs(biggest["pnl"]) > 0.40 * max(abs(book_total), 1e-9)),
        # How much removing that single trade moves the book, as a share of the
        # book itself. Above 1.0 means the trade is larger than the result.
        "concentration_ratio": (
            round(abs(biggest["pnl"]) / max(abs(book_total), 1e-9), 2)
            if biggest else None),
        # ⛔ The sharpest form of the question: does one fill decide whether you
        # are up or down at all?
        "sign_flips_without_biggest": bool(
            biggest and book_total != 0
            and (book_total > 0) != ((book_total - biggest["pnl"]) > 0)),
        "bots": bots,
    }
