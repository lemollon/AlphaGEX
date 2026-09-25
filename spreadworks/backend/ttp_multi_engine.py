"""TTP FLEX multi-engine intraday signal scanner.

Signal-only. No broker order routing.
Scans a liquid stock universe every minute during the regular session and
emits qualified manual trade proposals throughout the entry window.
"""
from __future__ import annotations

import asyncio
import math
import os
import statistics
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
SIGNAL_COOLDOWN_MINUTES = max(1, int(os.getenv("TTP_SIGNAL_COOLDOWN_MINUTES", "90")))
GLOBAL_SIGNAL_COOLDOWN_MINUTES = max(1, int(os.getenv("TTP_GLOBAL_SIGNAL_COOLDOWN_MINUTES", "10")))
MIN_STOP_PCT = float(os.getenv("TTP_MIN_STOP_PCT", "0.30"))
QUALITY_FLOOR = float(os.getenv("TTP_QUALITY_FLOOR", "7.5"))
MAX_BAR_AGE_SECONDS = max(60, int(os.getenv("TTP_MAX_BAR_AGE_SECONDS", "180")))
MAX_POSITION_VALUE = float(os.getenv("TTP_MAX_POSITION_VALUE", "10000"))
MAX_STOP_PCT = float(os.getenv("TTP_MAX_STOP_PCT", "1.5"))
POLL_SECONDS = max(30, int(os.getenv("TTP_POLL_SECONDS", "60")))
ENTRY_START_ET = time(9, 35)
ENTRY_END_ET = time(14, 30)
FORCE_FLAT_ET = time(15, 45)

# 60-day screening winners / near-winners. Keep the live alert stream focused
# on the symbols that actually showed positive expectancy in the first pass.
DEFAULT_UNIVERSE = ["AMD","AMZN","BAC","NVDA","RIVN","SOFI"]
STATIC_UNIVERSE = [
    s.strip().upper()
    for s in os.getenv("TTP_STOCK_UNIVERSE", ",".join(DEFAULT_UNIVERSE)).split(",")
    if s.strip()
]
MAX_UNIVERSE = max(10, int(os.getenv("TTP_MAX_UNIVERSE", "40")))

app = FastAPI(title="TTP FLEX Multi-Engine", version="2.0")


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
    engine: str
    quality: float
    entry: float
    stop: float
    target1: float
    target2: float
    shares: int
    risk_dollars: float
    position_value: float
    bar_time: str
    day_change_pct: float
    relative_bar_volume: float
    source: str = "Yahoo 1m validation + Trading Volatility supplemental discovery"


_STATE: dict[str, Any] = {
    "mode": "SIGNAL_ONLY",
    "version": "MULTI_ENGINE_V2",
    "live_execution": False,
    "account": "TTP 25K FLEX",
    "risk_dollars": RISK_DOLLARS,
    "signal_cooldown_minutes": SIGNAL_COOLDOWN_MINUTES,
    "global_signal_cooldown_minutes": GLOBAL_SIGNAL_COOLDOWN_MINUTES,
    "quality_floor": QUALITY_FLOOR,
    "min_stop_pct": MIN_STOP_PCT,
    "last_cycle_at": None,
    "last_error": None,
    "scan_count": 0,
    "universe": [],
    "candidates": [],
    "proposals_today": [],
    "signals": [],
    "engines": ["MOMENTUM_RVOL", "GAP_GO", "ORB", "VWAP_RECLAIM", "HOD_BREAKOUT"],
}
_last_signal: dict[str, datetime] = {}
_last_global_signal: datetime | None = None
_seen_date = None
_task: asyncio.Task | None = None


def _reset_day(now_et: datetime) -> None:
    global _seen_date
    if _seen_date != now_et.date():
        _seen_date = now_et.date()
        _last_signal.clear()
        global _last_global_signal
        _last_global_signal = None
        _STATE["proposals_today"] = []
        _STATE["signals"] = []


def _window_open(now_et: datetime) -> bool:
    return now_et.weekday() < 5 and ENTRY_START_ET <= now_et.time() <= ENTRY_END_ET


async def _fetch_tv_symbols(client: httpx.AsyncClient) -> list[str]:
    try:
        r = await client.get(STATUS_URL, timeout=15)
        r.raise_for_status()
        tv = (r.json().get("trading_volatility") or {})
        if not tv.get("available"):
            return []
        out = []
        for item in tv.get("top_setups") or []:
            if not isinstance(item, dict):
                continue
            sym = str(item.get("ticker") or "").upper().strip()
            direction = str(item.get("direction") or item.get("trade_bias") or "").lower()
            if sym and not any(x in direction for x in ("bear","short","down","put")):
                out.append(sym)
        return out[:12]
    except Exception:
        return []


async def _fetch_symbol(client: httpx.AsyncClient, symbol: str) -> tuple[list[Bar], float | None]:
    r = await client.get(
        YAHOO_CHART_URL.format(symbol=symbol),
        params={"interval":"1m","range":"1d","includePrePost":"false","events":"div,splits"},
        headers={"User-Agent":"Mozilla/5.0 AlphaGEX-TTP/2.0"},
        timeout=12,
    )
    r.raise_for_status()
    result = ((r.json().get("chart") or {}).get("result") or [None])[0]
    if not result:
        return [], None
    meta = result.get("meta") or {}
    prevclose = meta.get("chartPreviousClose") or meta.get("previousClose")
    try:
        prevclose = float(prevclose) if prevclose is not None else None
    except (TypeError, ValueError):
        prevclose = None

    stamps = result.get("timestamp") or []
    q = (((result.get("indicators") or {}).get("quote") or [{}])[0])
    arrays = [q.get(k) or [] for k in ("open","high","low","close","volume")]
    bars: list[Bar] = []
    for i, stamp in enumerate(stamps):
        try:
            vals = [a[i] for a in arrays]
        except IndexError:
            continue
        if any(v is None for v in vals[:4]):
            continue
        ts = datetime.fromtimestamp(float(stamp), UTC).astimezone(ET)
        if time(9,30) <= ts.time() < time(16,0):
            bars.append(Bar(ts, float(vals[0]), float(vals[1]), float(vals[2]), float(vals[3]), float(vals[4] or 0)))
    return bars, prevclose


def _metrics(bars: list[Bar], now_et: datetime, prevclose: float | None) -> dict[str, Any] | None:
    cutoff = now_et.replace(second=0, microsecond=0)
    b = [x for x in bars if x.ts.date() == now_et.date() and x.ts < cutoff]
    if len(b) < 7:
        return None
    opening = [x for x in b if time(9,30) <= x.ts.time() < time(9,35)]
    if len(opening) < 5:
        return None
    last, prev = b[-1], b[-2]
    if not 0 <= (now_et - last.ts).total_seconds() <= MAX_BAR_AGE_SECONDS:
        return None
    cumv = sum(x.volume for x in b)
    if last.close < 2 or cumv < 100_000:
        return None
    pv = sum(x.close * x.volume for x in b)
    vwap = pv / cumv if cumv else last.close
    orh = max(x.high for x in opening)
    prior_high = max(x.high for x in b[:-1])
    vols = [x.volume for x in b[-21:-1] if x.volume > 0]
    median_vol = statistics.median(vols) if vols else 0
    rvol = (last.volume / median_vol) if median_vol else 1.0
    day_change = ((last.close / prevclose) - 1) * 100 if prevclose else 0.0
    gap = ((opening[0].open / prevclose) - 1) * 100 if prevclose else 0.0
    return {
        "bars": b, "last": last, "prev": prev, "vwap": vwap, "orh": orh,
        "prior_high": prior_high, "rvol": rvol, "day_change": day_change,
        "gap": gap, "cumv": cumv,
    }


def _engine(m: dict[str, Any]) -> tuple[str, float, float] | None:
    b = m["bars"]; last = m["last"]; prev = m["prev"]
    vwap = m["vwap"]; orh = m["orh"]; prior_high = m["prior_high"]
    rvol = m["rvol"]; dc = m["day_change"]; gap = m["gap"]

    # Highest-conviction fresh events first. Stop is structural and later capped.
    if abs(gap) >= 2.0 and gap > 0 and last.close > orh and last.close > vwap and prev.close <= orh:
        q = min(9.5, 7.0 + min(abs(gap), 5) * 0.3 + min(rvol, 3) * 0.35)
        return "GAP_GO", q, min(x.low for x in b[-5:])

    if last.close > orh and prev.close <= orh and last.close > vwap:
        q = min(9.2, 6.8 + min(rvol, 3) * 0.5 + min(max(dc,0), 4) * 0.25)
        return "ORB", q, min(x.low for x in b[-5:])

    if last.close > prior_high and prev.close <= prior_high and last.close > vwap and rvol >= 1.2:
        q = min(9.3, 7.0 + min(rvol, 3) * 0.55 + min(max(dc,0), 4) * 0.2)
        return "HOD_BREAKOUT", q, min(x.low for x in b[-5:])

    if prev.close <= vwap * 1.001 and last.close > vwap and last.close > prev.close and rvol >= 1.15:
        q = min(8.8, 6.6 + min(rvol, 3) * 0.55 + min(max(dc,0), 4) * 0.2)
        return "VWAP_RECLAIM", q, min(x.low for x in b[-5:])

    if len(b) >= 4:
        c = [x.close for x in b[-4:]]
        if c[0] < c[1] < c[2] < c[3] and last.close > vwap and rvol >= 1.5 and dc >= 1.0:
            q = min(9.0, 6.8 + min(rvol, 3.5) * 0.5 + min(dc, 5) * 0.2)
            return "MOMENTUM_RVOL", q, min(x.low for x in b[-5:])
    return None


def _proposal(symbol: str, bars: list[Bar], prevclose: float | None, now_et: datetime) -> Proposal | None:
    m = _metrics(bars, now_et, prevclose)
    if not m:
        return None
    found = _engine(m)
    if not found:
        return None
    engine, quality, stop = found
    last = m["last"]
    # Discord and Trader Evolution use cent prices. Size from the exact prices
    # shown on the card, and reject targets too narrow to count under TTP rules.
    entry = round(last.close, 2)
    structural_dist = max(0.0, entry - round(stop, 2))
    recent_ranges = [max(0.0, x.high - x.low) for x in m["bars"][-20:] if x.high >= x.low]
    noise_floor = 1.25 * statistics.median(recent_ranges) if recent_ranges else 0.0
    min_dist = max(entry * (MIN_STOP_PCT / 100.0), noise_floor)
    dist = max(structural_dist, min_dist)
    if dist <= 0 or (dist / entry) * 100 > MAX_STOP_PCT:
        return None
    stop = round(entry - dist, 2)
    dist = entry - stop
    target1 = round(entry + dist, 2)
    # Take profit sooner than the old 2R-only bracket; the card also tells the
    # user to protect the trade once +1R is reached.
    target2 = round(entry + 1.5 * dist, 2)
    if target2 - entry < 0.10 - 1e-9:
        return None
    # TTP limits a new position to 5% of the previous one-minute candle.
    shares = min(math.floor(RISK_DOLLARS / dist), math.floor(MAX_POSITION_VALUE / entry),
                 math.floor(m["prev"].volume * 0.05))
    if shares < 1:
        return None
    return Proposal(
        symbol=symbol, side="BUY", engine=engine, quality=round(quality,1),
        entry=entry, stop=stop,
        target1=target1, target2=target2,
        shares=shares, risk_dollars=round(shares*dist,2),
        position_value=round(shares*entry,2), bar_time=last.ts.isoformat(),
        day_change_pct=round(m["day_change"],2), relative_bar_volume=round(m["rvol"],2),
    )


async def _cycle() -> None:
    global _last_global_signal
    now_et = datetime.now(ET)
    _reset_day(now_et)
    _STATE["last_cycle_at"] = datetime.now(UTC).isoformat()
    _STATE["last_error"] = None
    _STATE["scan_count"] += 1
    if not _window_open(now_et):
        return

    async with httpx.AsyncClient() as client:
        tv_symbols = await _fetch_tv_symbols(client)
        # Trading Volatility is supplemental context only; do not let it expand
        # the live universe beyond the validated profit-cluster whitelist.
        universe = list(dict.fromkeys(STATIC_UNIVERSE))[:MAX_UNIVERSE]
        _STATE["universe"] = universe

        sem = asyncio.Semaphore(8)
        async def scan(sym: str):
            async with sem:
                try:
                    bars, pc = await _fetch_symbol(client, sym)
                    return _proposal(sym, bars, pc, now_et)
                except Exception:
                    return None

        results = await asyncio.gather(*(scan(s) for s in universe))
        candidates = [p for p in results if p]
        candidates.sort(key=lambda p: (p.quality, p.relative_bar_volume), reverse=True)
        _STATE["candidates"] = [asdict(p) for p in candidates[:10]]

        for p in candidates:
            if p.quality < QUALITY_FLOOR:
                continue
            bar_time = datetime.fromisoformat(p.bar_time)
            previous = _last_signal.get(p.symbol)
            if previous is not None and (bar_time - previous).total_seconds() < SIGNAL_COOLDOWN_MINUTES * 60:
                continue
            if _last_global_signal is not None and (bar_time - _last_global_signal).total_seconds() < GLOBAL_SIGNAL_COOLDOWN_MINUTES * 60:
                continue
            _last_signal[p.symbol] = bar_time
            _last_global_signal = bar_time
            data = asdict(p)
            data["profit_protection"] = {
                "at_1R": round(p.target1, 2),
                "action": "Once price reaches +1R, move the stop to at least breakeven; do not let a winner turn into a loser.",
                "hard_target": round(p.target2, 2),
                "day_trade_only": True,
                "no_new_entries_after_et": ENTRY_END_ET.isoformat(timespec="minutes"),
                "force_flat_by_et": FORCE_FLAT_ET.isoformat(timespec="minutes"),
            }
            _STATE["proposals_today"].append(data)
            _STATE["signals"].insert(0, data)
            _STATE["signals"] = _STATE["signals"][:200]
            break


async def _loop() -> None:
    while True:
        try:
            await _cycle()
        except Exception as exc:
            _STATE["last_error"] = f"{type(exc).__name__}: {exc}"
        await asyncio.sleep(POLL_SECONDS)


@app.on_event("startup")
async def _startup() -> None:
    global _task
    _task = asyncio.create_task(_loop())


@app.on_event("shutdown")
async def _shutdown() -> None:
    global _task
    if _task:
        _task.cancel()
        _task = None


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status":"ok", "version":_STATE["version"], "mode":"SIGNAL_ONLY",
        "last_cycle_at":_STATE["last_cycle_at"], "last_error":_STATE["last_error"],
        "scan_count":_STATE["scan_count"],
    }


@app.get("/status")
async def status() -> dict[str, Any]:
    now_et = datetime.now(ET)
    return {**_STATE, "now_et":now_et.isoformat(), "entry_window_open":_window_open(now_et),
            "force_flat_et":FORCE_FLAT_ET.isoformat(timespec="minutes")}


@app.get("/signals")
async def signals() -> dict[str, Any]:
    return {"count":len(_STATE["signals"]), "signals":list(_STATE["signals"]), "mode":"SIGNAL_ONLY"}
