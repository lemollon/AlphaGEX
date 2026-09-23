"""Trade The Pool FLEX stock bot V1 -- signal-only, fail-closed.

This service consumes AlphaGEX/TradingVolatility discovery context, validates
long-only intraday opening-range-breakout setups from one-minute market bars,
and produces sized trade proposals for the user's $25K FLEX evaluation.

IMPORTANT:
- This module does NOT place, route, preview, or transmit broker orders.
- Live execution remains intentionally absent while Trade The Pool's published
  automation language is internally inconsistent.
- A future execution adapter must require explicit account-level approval and
  must fail closed by default.
"""
from __future__ import annotations

import asyncio
import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI

ET = ZoneInfo("America/New_York")
UTC = timezone.utc

STATUS_URL = os.getenv(
    "TTP_TV_STATUS_URL",
    "https://spreadworks-backend.onrender.com/api/spreadworks/qqq-retest-watch/status",
).strip()
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

RISK_DOLLARS = float(os.getenv("TTP_RISK_DOLLARS", "50"))
DAILY_STOP_DOLLARS = float(os.getenv("TTP_DAILY_STOP_DOLLARS", "200"))
MAX_TRADES_PER_DAY = int(os.getenv("TTP_MAX_TRADES_PER_DAY", "3"))
MAX_POSITION_VALUE = float(os.getenv("TTP_MAX_POSITION_VALUE", "10000"))
MAX_STOP_PCT = float(os.getenv("TTP_MAX_STOP_PCT", "1.5"))
MIN_SCORE = float(os.getenv("TTP_MIN_TV_SCORE", "0"))
POLL_SECONDS = max(30, int(os.getenv("TTP_POLL_SECONDS", "60")))
ENTRY_START_ET = time(9, 35)
ENTRY_END_ET = time(11, 30)
FORCE_FLAT_ET = time(15, 45)

app = FastAPI(title="TTP FLEX Bot V1", version="1.0")


@dataclass(frozen=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Proposal:
    symbol: str
    side: str
    entry: float
    stop: float
    target1: float
    target2: float
    shares: int
    risk_dollars: float
    position_value: float
    tv_rank: int | None
    tv_score: float | None
    tv_bias: str | None
    bar_time: str
    source: str = "AlphaGEX TV discovery + Yahoo 1m validation"


_STATE: dict[str, Any] = {
    "mode": "SIGNAL_ONLY",
    "live_execution": False,
    "account": "TTP 25K FLEX",
    "risk_dollars": RISK_DOLLARS,
    "daily_stop_dollars": DAILY_STOP_DOLLARS,
    "max_trades_per_day": MAX_TRADES_PER_DAY,
    "max_position_value": MAX_POSITION_VALUE,
    "last_cycle_at": None,
    "last_error": None,
    "tv_available": False,
    "tv_retrieval_timestamp": None,
    "watchlist": [],
    "proposals_today": [],
    "signals": [],
    "note": "No broker order-routing code exists in this service.",
}
_seen_today: set[str] = set()
_seen_date = None
_task: asyncio.Task | None = None


def _reset_day(now_et: datetime) -> None:
    global _seen_date
    if _seen_date != now_et.date():
        _seen_date = now_et.date()
        _seen_today.clear()
        _STATE["proposals_today"] = []
        _STATE["signals"] = []


def _regular_entry_window(now_et: datetime) -> bool:
    return (
        now_et.weekday() < 5
        and ENTRY_START_ET <= now_et.time() <= ENTRY_END_ET
    )


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _bullish_setup(item: dict[str, Any]) -> bool:
    direction = str(item.get("direction") or "").lower()
    bias = str(item.get("trade_bias") or "").lower()
    trade_type = str(item.get("trade_type") or "").lower()
    bearish_words = {"bearish", "short", "down", "put"}
    if any(word in direction for word in bearish_words):
        return False
    if any(word in bias for word in bearish_words):
        return False
    if direction or bias:
        return True
    return "bull" in trade_type or "long" in trade_type


def _select_watchlist(tv: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    items = tv.get("top_setups") or []
    selected: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict) or not raw.get("ticker"):
            continue
        if not _bullish_setup(raw):
            continue
        score = raw.get("opportunity_score")
        try:
            score_value = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_value = None
        if score_value is not None and score_value < MIN_SCORE:
            continue
        selected.append(raw)
        if len(selected) >= limit:
            break
    return selected


async def _fetch_tv(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get(STATUS_URL, timeout=20)
    response.raise_for_status()
    payload = response.json()
    tv = payload.get("trading_volatility") or {}
    if not isinstance(tv, dict):
        raise RuntimeError("Trading Volatility status payload missing")
    if not tv.get("available"):
        raise RuntimeError(tv.get("last_error") or "Trading Volatility unavailable")
    return tv


async def _fetch_yahoo_1m(client: httpx.AsyncClient, symbol: str) -> list[Bar]:
    response = await client.get(
        YAHOO_CHART_URL.format(symbol=symbol),
        params={
            "interval": "1m",
            "range": "1d",
            "includePrePost": "false",
            "events": "div,splits",
        },
        headers={"User-Agent": "Mozilla/5.0 AlphaGEX-TTP-FLEX/1.0"},
        timeout=15,
    )
    response.raise_for_status()
    result = ((response.json().get("chart") or {}).get("result") or [None])[0]
    if not result:
        return []
    stamps = result.get("timestamp") or []
    quote = (((result.get("indicators") or {}).get("quote") or [{}])[0])
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    bars: list[Bar] = []
    for i, stamp in enumerate(stamps):
        try:
            vals = (opens[i], highs[i], lows[i], closes[i], volumes[i])
        except IndexError:
            continue
        if any(v is None for v in vals[:4]):
            continue
        ts = datetime.fromtimestamp(float(stamp), UTC).astimezone(ET)
        if time(9, 30) <= ts.time() < time(16, 0):
            bars.append(Bar(
                ts=ts,
                open=float(vals[0]),
                high=float(vals[1]),
                low=float(vals[2]),
                close=float(vals[3]),
                volume=float(vals[4] or 0),
            ))
    return bars


def _proposal_from_bars(
    symbol: str,
    bars: list[Bar],
    tv_item: dict[str, Any],
    now_et: datetime,
) -> Proposal | None:
    today = [b for b in bars if b.ts.date() == now_et.date()]
    completed = [b for b in today if b.ts < now_et.replace(second=0, microsecond=0)]
    opening = [b for b in completed if time(9, 30) <= b.ts.time() < time(9, 35)]
    if len(opening) < 5:
        return None
    eligible = [b for b in completed if ENTRY_START_ET <= b.ts.time() <= ENTRY_END_ET]
    if not eligible:
        return None

    last = eligible[-1]
    orh = max(b.high for b in opening)

    cum_volume = 0.0
    cum_pv = 0.0
    vwap = None
    for b in completed:
        if b.ts > last.ts:
            break
        cum_volume += b.volume
        cum_pv += b.close * b.volume
        if b is last and cum_volume > 0:
            vwap = cum_pv / cum_volume

    if vwap is None or last.close <= orh or last.close <= vwap:
        return None

    prior = [b for b in completed if b.ts < last.ts][-5:]
    if len(prior) < 5:
        return None
    stop = min(b.low for b in prior)
    entry = last.close
    stop_dist = entry - stop
    if stop_dist <= 0:
        return None
    if (stop_dist / entry) * 100 > MAX_STOP_PCT:
        return None

    shares_by_risk = math.floor(RISK_DOLLARS / stop_dist)
    shares_by_bp = math.floor(MAX_POSITION_VALUE / entry)
    shares = min(shares_by_risk, shares_by_bp)
    if shares < 1:
        return None

    try:
        score = (
            float(tv_item.get("opportunity_score"))
            if tv_item.get("opportunity_score") is not None
            else None
        )
    except (TypeError, ValueError):
        score = None

    return Proposal(
        symbol=symbol,
        side="BUY",
        entry=round(entry, 4),
        stop=round(stop, 4),
        target1=round(entry + stop_dist, 4),
        target2=round(entry + 2 * stop_dist, 4),
        shares=shares,
        risk_dollars=round(shares * stop_dist, 2),
        position_value=round(shares * entry, 2),
        tv_rank=tv_item.get("rank"),
        tv_score=score,
        tv_bias=tv_item.get("trade_bias") or tv_item.get("direction"),
        bar_time=last.ts.isoformat(),
    )


async def _cycle() -> None:
    now_et = datetime.now(ET)
    _reset_day(now_et)
    _STATE["last_cycle_at"] = datetime.now(UTC).isoformat()
    _STATE["last_error"] = None

    if not _regular_entry_window(now_et):
        _STATE["watchlist"] = []
        return
    if len(_STATE["proposals_today"]) >= MAX_TRADES_PER_DAY:
        return

    async with httpx.AsyncClient() as client:
        tv = await _fetch_tv(client)
        _STATE["tv_available"] = True
        _STATE["tv_retrieval_timestamp"] = tv.get("retrieval_timestamp")
        watchlist = _select_watchlist(tv)
        _STATE["watchlist"] = [
            {
                "ticker": i.get("ticker"),
                "rank": i.get("rank"),
                "score": i.get("opportunity_score"),
                "bias": i.get("trade_bias") or i.get("direction"),
            }
            for i in watchlist
        ]

        for item in watchlist:
            if len(_STATE["proposals_today"]) >= MAX_TRADES_PER_DAY:
                break
            symbol = str(item["ticker"]).upper()
            bars = await _fetch_yahoo_1m(client, symbol)
            proposal = _proposal_from_bars(symbol, bars, item, now_et)
            if proposal is None:
                continue
            key = f"{proposal.symbol}:{proposal.bar_time}"
            if key in _seen_today:
                continue
            _seen_today.add(key)
            data = asdict(proposal)
            _STATE["proposals_today"].append(data)
            _STATE["signals"].insert(0, data)
            _STATE["signals"] = _STATE["signals"][:25]


async def _loop() -> None:
    while True:
        try:
            await _cycle()
        except Exception as exc:  # noqa: BLE001
            _STATE["last_error"] = f"{type(exc).__name__}: {exc}"
            _STATE["tv_available"] = False
        await asyncio.sleep(POLL_SECONDS)


@app.on_event("startup")
async def _startup() -> None:
    global _task
    _task = asyncio.create_task(_loop())


@app.on_event("shutdown")
async def _shutdown() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "mode": _STATE["mode"],
        "live_execution": False,
        "last_cycle_at": _STATE["last_cycle_at"],
        "last_error": _STATE["last_error"],
    }


@app.get("/status")
async def status() -> dict[str, Any]:
    now_et = datetime.now(ET)
    return {
        **_STATE,
        "now_et": now_et.isoformat(),
        "entry_window_open": _regular_entry_window(now_et),
        "force_flat_et": FORCE_FLAT_ET.isoformat(timespec="minutes"),
        "policy_gate": {
            "automation_approved": _truthy(os.getenv("TTP_AUTOMATION_APPROVED")),
            "live_execution_requested": _truthy(os.getenv("TTP_LIVE_EXECUTION")),
            "order_routing_implemented": False,
        },
    }


@app.get("/signals")
async def signals() -> dict[str, Any]:
    return {
        "count": len(_STATE["signals"]),
        "signals": list(_STATE["signals"]),
        "mode": "SIGNAL_ONLY",
    }
