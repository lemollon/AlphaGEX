"""Always-on Render watcher for the user-defined QQQ retest setup.

This module is advisory and alert-only.  It cannot place, preview, or route an
order.  It runs inside the existing SpreadWorks Render service so a sleeping
desktop cannot interrupt it.

Market-data policy:
* Prefer Tradier's production consolidated feed already configured on Render.
* Fall back to Yahoo one-minute chart data only when Tradier is unavailable or
  stale, and label that source unofficial/not exchange-certified.
* Reject quotes or newest completed bars older than 90 seconds in an active
  session.
* Option bid/ask/IV/Greeks are included only when every required Tradier field
  carries its own timestamp and passes the same freshness gate.  Nothing is
  inferred from Yahoo.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
UTC = timezone.utc
TRADIER_BASE = "https://api.tradier.com/v1"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

router = APIRouter(prefix="/api/spreadworks/qqq-retest-watch",
                   tags=["QQQ Retest Watch"])


@dataclass(frozen=True)
class Settings:
    enabled: bool
    levels_date: date
    support_low: float
    support_high: float
    reclaim_low: float
    reclaim_high: float
    support_hold_bars: int
    reclaim_confirmation_bars: int
    failure_confirmation_bars: int
    stale_after_seconds: float
    poll_seconds: int
    example_spread_width: float
    allow_yahoo_fallback: bool
    sessions: tuple[str, ...]


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int | None = None


@dataclass(frozen=True)
class Classification:
    state: str
    reason: str
    transition_at: datetime | None


_SCHEDULER: dict[str, Any] = {"ref": None}
_STATE: dict[str, Any] = {"last_state": None, "last_event_key": None}
_BAR_CACHE: dict[str, dict[int, Bar]] = {"QQQ": {}, "SPY": {}}
_STATUS: dict[str, Any] = {
    "enabled": False,
    "registered": False,
    "state": "STARTING",
    "reason": "Watcher has not completed a cycle.",
    "source": None,
    "session": "closed",
    "levels": None,
    "qqq": None,
    "spy": None,
    "options": None,
    "last_checked_at": None,
    "last_alert_at": None,
    "last_error": None,
}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    levels_date = date.fromisoformat(
        os.getenv("QQQ_RETEST_LEVELS_DATE", "2026-09-17"))
    sessions = tuple(
        value.strip().lower()
        for value in os.getenv(
            "QQQ_RETEST_SESSIONS", "premarket,regular,postmarket"
        ).split(",")
        if value.strip()
    )
    settings = Settings(
        enabled=_env_bool("QQQ_RETEST_WATCH_ENABLED", True),
        levels_date=levels_date,
        support_low=float(os.getenv("QQQ_RETEST_SUPPORT_LOW", "714")),
        support_high=float(os.getenv("QQQ_RETEST_SUPPORT_HIGH", "715")),
        reclaim_low=float(os.getenv("QQQ_RETEST_RECLAIM_LOW", "717")),
        reclaim_high=float(os.getenv("QQQ_RETEST_RECLAIM_HIGH", "718")),
        support_hold_bars=int(os.getenv("QQQ_RETEST_SUPPORT_HOLD_BARS", "2")),
        reclaim_confirmation_bars=int(os.getenv(
            "QQQ_RETEST_RECLAIM_CONFIRMATION_BARS", "2")),
        failure_confirmation_bars=int(os.getenv(
            "QQQ_RETEST_FAILURE_CONFIRMATION_BARS", "2")),
        stale_after_seconds=float(os.getenv(
            "QQQ_RETEST_STALE_AFTER_SECONDS", "90")),
        poll_seconds=max(5, int(os.getenv("QQQ_RETEST_POLL_SECONDS", "10"))),
        example_spread_width=float(os.getenv(
            "QQQ_RETEST_EXAMPLE_SPREAD_WIDTH", "2")),
        allow_yahoo_fallback=_env_bool(
            "QQQ_RETEST_ALLOW_YAHOO_FALLBACK", True),
        sessions=sessions,
    )
    if not settings.support_low < settings.support_high:
        raise ValueError("QQQ support low must be below support high")
    if not settings.reclaim_low < settings.reclaim_high:
        raise ValueError("QQQ reclaim low must be below reclaim high")
    if not settings.support_high < settings.reclaim_low:
        raise ValueError("QQQ support must be below the reclaim zone")
    if min(settings.support_hold_bars,
           settings.reclaim_confirmation_bars,
           settings.failure_confirmation_bars) < 1:
        raise ValueError("QQQ confirmation bar counts must be positive")
    invalid_sessions = set(settings.sessions) - {
        "premarket", "regular", "postmarket"
    }
    if invalid_sessions or not settings.sessions:
        raise ValueError(
            "QQQ_RETEST_SESSIONS must contain premarket, regular, and/or "
            "postmarket"
        )
    return settings


def _session(now_et: datetime) -> str:
    if now_et.weekday() >= 5:
        return "closed"
    value = now_et.time()
    if time(4, 0) <= value < time(9, 30):
        return "premarket"
    if time(9, 30) <= value < time(16, 0):
        return "regular"
    if time(16, 0) <= value < time(20, 0):
        return "postmarket"
    return "closed"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def classify_bars(bars: list[Bar], settings: Settings) -> Classification:
    """Classify the current state from completed one-minute bars only."""
    if len(bars) < 2:
        return Classification("WAIT", "Need at least two completed one-minute bars.", None)

    touched = False
    held = False
    hold_count = 0
    below_count = 0
    confirm_count = 0
    state = "WAIT"
    reason = "No confirmed retest."
    transition_at: datetime | None = None

    for bar in sorted(bars, key=lambda item: item.timestamp):
        intersects = (bar.low <= settings.support_high
                      and bar.high >= settings.support_low)
        if intersects and not touched:
            touched = True
            held = False
            hold_count = below_count = confirm_count = 0
            reason = "Price entered support; confirmation pending."

        if not touched:
            continue

        previous = state
        if bar.close < settings.support_low:
            below_count += 1
            hold_count = confirm_count = 0
            held = False
            if below_count >= settings.failure_confirmation_bars:
                state = "FAILED_RETEST"
                reason = (f"{below_count} consecutive completed bars closed "
                          "below support without reclaiming it.")
        else:
            below_count = 0
            hold_count += 1
            if hold_count >= settings.support_hold_bars:
                held = True

            if state == "FAILED_RETEST" and bar.close >= settings.support_high:
                state = "WAIT"
                reason = ("Failed retest recovered above support; reclaim "
                          "confirmation pending.")

            if held and bar.close >= settings.reclaim_low:
                confirm_count += 1
            else:
                confirm_count = 0

            if confirm_count >= settings.reclaim_confirmation_bars:
                state = "BULLISH_RETEST"
                reason = (f"{confirm_count} consecutive completed bars closed "
                          "at or above reclaim after support held.")
            elif state == "BULLISH_RETEST" and bar.close < settings.reclaim_low:
                state = "WAIT"
                reason = "Bullish reclaim lost; waiting for renewed confirmation."

        if state != previous:
            transition_at = bar.timestamp + timedelta(minutes=1)

    return Classification(state, reason, transition_at)


def _quote_timestamp(quote: dict[str, Any]) -> datetime:
    raw = quote.get("trade_date")
    if raw is None:
        raise ValueError(f"{quote.get('symbol', 'quote')} has no trade_date")
    return datetime.fromtimestamp(float(raw) / 1000.0, UTC)


def _age_seconds(now: datetime, timestamp: datetime) -> float:
    return max(0.0, (now.astimezone(UTC) - timestamp.astimezone(UTC)).total_seconds())


def _normalize_quotes(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = (payload.get("quotes") or {}).get("quote")
    if isinstance(raw, dict):
        rows = [raw]
    elif isinstance(raw, list):
        rows = raw
    else:
        rows = []
    return {str(row.get("symbol", "")).upper(): row for row in rows}


async def _tradier_get(app, path: str, params: dict[str, Any]) -> dict[str, Any]:
    token = os.getenv("TRADIER_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TRADIER_TOKEN is not configured on Render")
    response = await app.state.http.get(
        f"{TRADIER_BASE}{path}",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/json"},
        params=params,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Tradier {path} returned {response.status_code}: "
            f"{response.text[:160]}")
    return response.json()


def _timesale_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = (payload.get("series") or {}).get("data")
    if isinstance(raw, dict):
        return [raw]
    return raw if isinstance(raw, list) else []


def _bar_from_timesale(row: dict[str, Any]) -> Bar | None:
    required = ("timestamp", "open", "high", "low", "close")
    if any(row.get(name) is None for name in required):
        return None
    timestamp = datetime.fromtimestamp(float(row["timestamp"]), UTC).astimezone(ET)
    return Bar(
        timestamp=timestamp,
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=int(row["volume"]) if row.get("volume") is not None else None,
    )


async def _fetch_tradier_bars(app, symbol: str, now_et: datetime) -> list[Bar]:
    cache = _BAR_CACHE[symbol]
    if cache:
        start = now_et - timedelta(minutes=5)
    else:
        start = datetime.combine(now_et.date(), time(4, 0), ET)
    payload = await _tradier_get(
        app, "/markets/timesales",
        {"symbol": symbol, "interval": "1min",
         "start": start.strftime("%Y-%m-%d %H:%M"),
         "end": now_et.strftime("%Y-%m-%d %H:%M"),
         "session_filter": "all"},
    )
    for row in _timesale_rows(payload):
        bar = _bar_from_timesale(row)
        if bar and bar.timestamp.date() == now_et.date():
            cache[int(bar.timestamp.timestamp())] = bar
    cutoff = now_et - timedelta(days=1)
    for key in [key for key, bar in cache.items() if bar.timestamp < cutoff]:
        cache.pop(key, None)
    return sorted(
        [bar for bar in cache.values()
         if bar.timestamp.date() == now_et.date()
         and bar.timestamp + timedelta(minutes=1) <= now_et],
        key=lambda item: item.timestamp,
    )


async def _fetch_tradier_market(app, settings: Settings,
                                retrieved_at: datetime) -> dict[str, Any]:
    now_et = retrieved_at.astimezone(ET)
    quotes_payload, qqq_bars, spy_bars = await asyncio.gather(
        _tradier_get(app, "/markets/quotes", {"symbols": "QQQ,SPY"}),
        _fetch_tradier_bars(app, "QQQ", now_et),
        _fetch_tradier_bars(app, "SPY", now_et),
    )
    quotes = _normalize_quotes(quotes_payload)
    if not {"QQQ", "SPY"}.issubset(quotes):
        raise RuntimeError("Tradier did not return both QQQ and SPY quotes")
    if not qqq_bars or not spy_bars:
        raise RuntimeError("Tradier returned no completed current-day one-minute bars")

    snapshots: dict[str, dict[str, Any]] = {}
    for symbol in ("QQQ", "SPY"):
        quote = quotes[symbol]
        stamp = _quote_timestamp(quote)
        age = _age_seconds(retrieved_at, stamp)
        if age > settings.stale_after_seconds:
            raise RuntimeError(f"Tradier {symbol} quote is stale ({age:.1f}s)")
        if quote.get("last") is None:
            raise RuntimeError(f"Tradier {symbol} quote has no last price")
        snapshots[symbol.lower()] = {
            "symbol": symbol,
            "price": float(quote["last"]),
            "exchange_timestamp": stamp,
            "retrieval_timestamp": retrieved_at,
            "age_seconds": round(age, 1),
        }

    for symbol, bars in (("QQQ", qqq_bars), ("SPY", spy_bars)):
        bar_end = bars[-1].timestamp + timedelta(minutes=1)
        age = _age_seconds(retrieved_at, bar_end)
        if age > settings.stale_after_seconds:
            raise RuntimeError(
                f"Tradier {symbol} newest completed bar is stale ({age:.1f}s)")

    return {
        "provider": "Tradier",
        "source": "Tradier production consolidated feed",
        "certification": "Brokerage API; real-time account market data",
        "retrieval_timestamp": retrieved_at,
        "qqq": snapshots["qqq"],
        "spy": snapshots["spy"],
        "qqq_bars": qqq_bars,
        "spy_bars": spy_bars,
    }


async def _fetch_yahoo_symbol(app, symbol: str, retrieved_at: datetime,
                              settings: Settings) -> tuple[dict[str, Any], list[Bar]]:
    response = await app.state.http.get(
        YAHOO_CHART.format(symbol=symbol),
        params={"interval": "1m", "range": "1d", "includePrePost": "true"},
        headers={"User-Agent": "QQQ-Retest-Watch/1.0"},
    )
    if response.status_code != 200:
        raise RuntimeError(f"Yahoo {symbol} returned {response.status_code}")
    payload = response.json()
    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise RuntimeError(f"Yahoo {symbol}: {chart['error']}")
    result = (chart.get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo returned no {symbol} result")
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    bars: list[Bar] = []
    latest: Bar | None = None
    now_et = retrieved_at.astimezone(ET)
    for index, raw_timestamp in enumerate(timestamps):
        try:
            values = {name: quote.get(name, [])[index]
                      for name in ("open", "high", "low", "close")}
        except IndexError:
            continue
        if any(value is None for value in values.values()):
            continue
        stamp = datetime.fromtimestamp(float(raw_timestamp), UTC).astimezone(ET)
        volume_values = quote.get("volume") or []
        volume = (volume_values[index]
                  if index < len(volume_values) else None)
        bar = Bar(stamp, float(values["open"]), float(values["high"]),
                  float(values["low"]), float(values["close"]),
                  int(volume) if volume is not None else None)
        latest = bar
        if (stamp.date() == now_et.date()
                and stamp + timedelta(minutes=1) <= now_et):
            bars.append(bar)
    if latest is None or not bars:
        raise RuntimeError(f"Yahoo returned no priced {symbol} bars")
    age = _age_seconds(retrieved_at, latest.timestamp)
    if age > settings.stale_after_seconds:
        raise RuntimeError(f"Yahoo {symbol} newest bar is stale ({age:.1f}s)")
    snapshot = {
        "symbol": symbol,
        "price": latest.close,
        "exchange_timestamp": latest.timestamp,
        "retrieval_timestamp": retrieved_at,
        "age_seconds": round(age, 1),
    }
    return snapshot, bars


async def _fetch_yahoo_market(app, settings: Settings,
                              retrieved_at: datetime) -> dict[str, Any]:
    qqq_data, spy_data = await asyncio.gather(
        _fetch_yahoo_symbol(app, "QQQ", retrieved_at, settings),
        _fetch_yahoo_symbol(app, "SPY", retrieved_at, settings),
    )
    return {
        "provider": "Yahoo",
        "source": "Yahoo Finance chart/quote",
        "certification": "Unofficial; not exchange-certified BBO",
        "retrieval_timestamp": retrieved_at,
        "qqq": qqq_data[0], "spy": spy_data[0],
        "qqq_bars": qqq_data[1], "spy_bars": spy_data[1],
    }


async def _fetch_market(app, settings: Settings,
                        retrieved_at: datetime) -> dict[str, Any]:
    try:
        return await _fetch_tradier_market(app, settings, retrieved_at)
    except Exception as tradier_error:  # noqa: BLE001
        if not settings.allow_yahoo_fallback:
            raise
        try:
            result = await _fetch_yahoo_market(app, settings, retrieved_at)
            result["fallback_reason"] = str(tradier_error)
            return result
        except Exception as yahoo_error:  # noqa: BLE001
            raise RuntimeError(
                f"Tradier unavailable: {tradier_error}; "
                f"Yahoo unavailable: {yahoo_error}") from yahoo_error


def _parse_greeks_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # Tradier/ORATS examples omit a suffix. Treating the value as Eastern
        # is conservative during US option hours; a stale result stays stale.
        parsed = parsed.replace(tzinfo=ET)
    return parsed.astimezone(UTC)


def _option_freshness(option: dict[str, Any], now: datetime,
                      settings: Settings) -> tuple[bool, str, dict[str, float]]:
    stamps: dict[str, datetime] = {}
    for name in ("bid_date", "ask_date"):
        raw = option.get(name)
        if raw is None:
            return False, f"option missing {name}", {}
        stamps[name] = datetime.fromtimestamp(float(raw) / 1000.0, UTC)
    greeks_stamp = _parse_greeks_timestamp(
        (option.get("greeks") or {}).get("updated_at"))
    if greeks_stamp is None:
        return False, "option Greeks have no usable updated_at", {}
    stamps["greeks_updated_at"] = greeks_stamp
    ages = {name: round(_age_seconds(now, stamp), 1)
            for name, stamp in stamps.items()}
    stale = [name for name, age in ages.items()
             if age > settings.stale_after_seconds]
    if stale:
        return False, f"stale option fields: {', '.join(stale)}", ages
    return True, "fresh", ages


async def _fetch_options_example(app, signal: str, spot: float,
                                 settings: Settings,
                                 retrieved_at: datetime) -> tuple[dict[str, Any] | None, str]:
    if _session(retrieved_at.astimezone(ET)) != "regular":
        return None, "options market is closed"
    if signal not in {"BULLISH_RETEST", "FAILED_RETEST"}:
        return None, "state is not actionable"
    expirations = await _tradier_get(
        app, "/markets/options/expirations",
        {"symbol": "QQQ", "includeAllRoots": "true"})
    raw_dates = (expirations.get("expirations") or {}).get("date") or []
    if isinstance(raw_dates, str):
        raw_dates = [raw_dates]
    today = retrieved_at.astimezone(ET).date()
    available: list[date] = []
    for value in raw_dates:
        try:
            parsed = date.fromisoformat(str(value))
        except (TypeError, ValueError):
            continue
        if parsed >= today:
            available.append(parsed)
    available.sort()
    if not available:
        return None, "Tradier returned no current QQQ expiration"
    expiration = available[0]
    chain_payload = await _tradier_get(
        app, "/markets/options/chains",
        {"symbol": "QQQ", "expiration": expiration.isoformat(),
         "greeks": "true"})
    raw_options = (chain_payload.get("options") or {}).get("option") or []
    if isinstance(raw_options, dict):
        raw_options = [raw_options]
    desired_type = "call" if signal == "BULLISH_RETEST" else "put"
    candidates: list[dict[str, Any]] = []
    stale_reasons: set[str] = set()
    for option in raw_options:
        if str(option.get("option_type", "")).lower() != desired_type:
            continue
        fresh, reason, ages = _option_freshness(
            option, retrieved_at, settings)
        if not fresh:
            stale_reasons.add(reason)
            continue
        greeks = option.get("greeks") or {}
        required = ("bid", "ask", "strike")
        greek_names = ("delta", "gamma", "theta", "vega", "rho", "mid_iv")
        if any(option.get(name) is None for name in required):
            continue
        if any(greeks.get(name) is None for name in greek_names):
            continue
        bid, ask = float(option["bid"]), float(option["ask"])
        if bid < 0 or ask <= 0 or ask < bid:
            continue
        candidates.append({
            "symbol": option.get("symbol"),
            "strike": float(option["strike"]),
            "right": "C" if desired_type == "call" else "P",
            "bid": bid, "ask": ask,
            "bid_size": option.get("bidsize"),
            "ask_size": option.get("asksize"),
            "delta": float(greeks["delta"]),
            "gamma": float(greeks["gamma"]),
            "theta": float(greeks["theta"]),
            "vega": float(greeks["vega"]),
            "rho": float(greeks["rho"]),
            "implied_vol": float(greeks["mid_iv"]),
            "ages_seconds": ages,
        })
    if len(candidates) < 2:
        detail = "; ".join(sorted(stale_reasons)) or "no complete fresh contracts"
        return None, f"fresh Tradier option enrichment unavailable: {detail}"

    buy = min(candidates, key=lambda item: abs(item["strike"] - spot))
    if desired_type == "call":
        sells = [item for item in candidates if item["strike"] > buy["strike"]]
        spread_name = "bull call debit spread"
        distance = lambda item: abs((item["strike"] - buy["strike"])
                                    - settings.example_spread_width)
    else:
        sells = [item for item in candidates if item["strike"] < buy["strike"]]
        spread_name = "bear put debit spread"
        distance = lambda item: abs((buy["strike"] - item["strike"])
                                    - settings.example_spread_width)
    if not sells:
        return None, "no fresh defined-risk wing was available"
    sell = min(sells, key=distance)
    width = abs(sell["strike"] - buy["strike"])
    debit = round(buy["ask"] - sell["bid"], 2)
    if not 0 < debit < width:
        return None, "fresh quotes did not produce a valid natural debit"
    return {
        "source": "Tradier production option chain",
        "expiration": expiration.isoformat(),
        "strategy": spread_name,
        "buy": buy, "sell": sell,
        "natural_debit": debit,
        "width": width,
        "max_loss_dollars": round(debit * 100, 2),
        "max_profit_dollars": round((width - debit) * 100, 2),
        "disclaimer": ("One-contract defined-risk example only; no order is "
                       "created, previewed, or submitted."),
    }, "fresh"


def _public_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not snapshot:
        return None
    return {key: (_iso(value) if isinstance(value, datetime) else value)
            for key, value in snapshot.items()}


def _event_key(classification: Classification, now_et: datetime) -> str:
    if classification.transition_at:
        stamp = int(classification.transition_at.timestamp())
        return f"qqq_{classification.state}_{stamp}"
    return f"qqq_{classification.state}_{now_et.date().isoformat()}"


def _build_embed(classification: Classification, market: dict[str, Any] | None,
                 settings: Settings, session: str,
                 options: dict[str, Any] | None,
                 options_reason: str | None,
                 retrieved_at: datetime) -> dict[str, Any]:
    colors = {"BULLISH_RETEST": 0x34D399, "FAILED_RETEST": 0xF87171,
              "WAIT": 0xFBBF24, "DATA_UNAVAILABLE": 0x9CA3AF,
              "LEVELS_EXPIRED": 0x9CA3AF}
    fields: list[dict[str, Any]] = [{
        "name": "Decision",
        "value": classification.reason,
        "inline": False,
    }, {
        "name": "Levels",
        "value": (f"Support {settings.support_low:g}-{settings.support_high:g} | "
                  f"Reclaim {settings.reclaim_low:g}-{settings.reclaim_high:g} | "
                  f"Valid {settings.levels_date.isoformat()}"),
        "inline": False,
    }]
    if market:
        for symbol in ("qqq", "spy"):
            item = market[symbol]
            fields.append({
                "name": item["symbol"],
                "value": (f"${item['price']:.2f} | exchange "
                          f"{item['exchange_timestamp'].astimezone(ET).isoformat()} | "
                          f"retrieved {retrieved_at.isoformat()} | "
                          f"age {item['age_seconds']:.1f}s"),
                "inline": False,
            })
        fields.append({"name": "Source",
                       "value": (f"{market['source']} | {market['certification']} | "
                                 f"session {session}"), "inline": False})
    if options:
        buy, sell = options["buy"], options["sell"]
        fields.append({
            "name": "Fresh defined-risk example",
            "value": (f"{options['strategy']} exp {options['expiration']} | "
                      f"Buy {buy['right']} {buy['strike']:g} @ ask {buy['ask']:.2f}; "
                      f"sell {sell['right']} {sell['strike']:g} @ bid {sell['bid']:.2f} | "
                      f"natural debit {options['natural_debit']:.2f} | "
                      f"max loss ${options['max_loss_dollars']:.0f}; "
                      f"max profit ${options['max_profit_dollars']:.0f}"),
            "inline": False,
        })
        fields.append({
            "name": "Greeks / IV",
            "value": (f"Buy d {buy['delta']:.3f} g {buy['gamma']:.3f} "
                      f"theta {buy['theta']:.3f} vega {buy['vega']:.3f} "
                      f"IV {buy['implied_vol']:.1%}; sell d {sell['delta']:.3f} "
                      f"g {sell['gamma']:.3f} theta {sell['theta']:.3f} "
                      f"vega {sell['vega']:.3f} IV {sell['implied_vol']:.1%}"),
            "inline": False,
        })
        fields.append({"name": "Risk", "value": options["disclaimer"],
                       "inline": False})
    else:
        fields.append({
            "name": "Options",
            "value": ((options_reason or "unavailable")
                      + "; bid/ask, IV, and Greeks were not inferred."),
            "inline": False,
        })
    return {
        "title": f"QQQ RETEST WATCH - {classification.state}",
        "color": colors.get(classification.state, 0x9CA3AF),
        "fields": fields,
        "timestamp": retrieved_at.isoformat(),
        "footer": {"text": "Render cloud watcher | alert-only | no orders"},
    }


async def _send_alert(embed: dict[str, Any], event_key: str,
                      fire_date: date) -> bool:
    from . import _claim_post_slot_db, _release_post_slot_db, _send_webhook_sync
    webhook = (os.getenv("QQQ_RETEST_WEBHOOK_URL", "").strip()
               or os.getenv("DISCORD_WEBHOOK_URL", "").strip())
    if not webhook:
        logger.warning("[QQQWatch] no webhook configured; event retained in status")
        return False
    dedup_key = event_key[:64]
    if not _claim_post_slot_db(dedup_key, fire_date):
        return False
    sent = await asyncio.to_thread(_send_webhook_sync, embed, webhook)
    if not sent:
        _release_post_slot_db(dedup_key, fire_date)
    return sent


def _set_status(**updates: Any) -> None:
    _STATUS.update(updates)


async def run_watch_cycle(app, *, now: datetime | None = None) -> dict[str, Any]:
    """Run one complete cloud watch cycle. Never places or previews orders."""
    settings = load_settings()
    retrieved_at = (now or datetime.now(UTC)).astimezone(UTC)
    now_et = retrieved_at.astimezone(ET)
    session = _session(now_et)
    levels = {
        "valid_date": settings.levels_date.isoformat(),
        "support": [settings.support_low, settings.support_high],
        "reclaim": [settings.reclaim_low, settings.reclaim_high],
    }
    _set_status(enabled=settings.enabled, session=session, levels=levels,
                last_checked_at=retrieved_at.isoformat())
    if not settings.enabled:
        _set_status(state="DISABLED", reason="QQQ_RETEST_WATCH_ENABLED is false")
        return dict(_STATUS)
    if session == "closed" or session not in settings.sessions:
        _set_status(state="OFF_SESSION", reason="Outside selected market sessions",
                    source=None, qqq=None, spy=None, options=None, last_error=None)
        return dict(_STATUS)

    if now_et.date() != settings.levels_date:
        classification = Classification(
            "LEVELS_EXPIRED",
            (f"Configured levels are prior user-defined levels from "
             f"{settings.levels_date.isoformat()}; update them before using "
             f"on {now_et.date().isoformat()}."),
            None,
        )
        await _process_state_change(app, classification, None, settings,
                                    session, None, "levels expired", retrieved_at)
        return dict(_STATUS)

    try:
        market = await _fetch_market(app, settings, retrieved_at)
        classification = classify_bars(market["qqq_bars"], settings)
        options = None
        options_reason = "state is not actionable"
        if classification.state in {"BULLISH_RETEST", "FAILED_RETEST"}:
            try:
                options, options_reason = await _fetch_options_example(
                    app, classification.state, market["qqq"]["price"],
                    settings, retrieved_at)
            except Exception as exc:  # noqa: BLE001
                options_reason = f"Tradier option enrichment failed: {exc}"
        await _process_state_change(app, classification, market, settings,
                                    session, options, options_reason, retrieved_at)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[QQQWatch] market cycle failed: %r", exc)
        classification = Classification("DATA_UNAVAILABLE", str(exc), None)
        await _process_state_change(app, classification, None, settings,
                                    session, None, str(exc), retrieved_at)
        _set_status(last_error=str(exc))
    return dict(_STATUS)


async def _process_state_change(app, classification: Classification,
                                market: dict[str, Any] | None,
                                settings: Settings, session: str,
                                options: dict[str, Any] | None,
                                options_reason: str | None,
                                retrieved_at: datetime) -> None:
    previous = _STATE.get("last_state")
    changed = previous != classification.state
    _set_status(
        state=classification.state,
        reason=classification.reason,
        source=(market.get("source") if market else None),
        certification=(market.get("certification") if market else None),
        qqq=_public_snapshot(market.get("qqq") if market else None),
        spy=_public_snapshot(market.get("spy") if market else None),
        options=options,
        options_unavailable_reason=(None if options else options_reason),
        transition_at=_iso(classification.transition_at),
        last_error=None,
    )
    if not changed:
        return
    _STATE["last_state"] = classification.state
    # Initial WAIT is status, not an alert. Every actionable first state and
    # every later transition is alertable.
    if previous is None and classification.state == "WAIT":
        return
    event_key = _event_key(classification, retrieved_at.astimezone(ET))
    if event_key == _STATE.get("last_event_key"):
        return
    embed = _build_embed(classification, market, settings, session, options,
                         options_reason, retrieved_at)
    posted = await _send_alert(embed, event_key,
                               retrieved_at.astimezone(ET).date())
    _STATE["last_event_key"] = event_key
    if posted:
        _set_status(last_alert_at=retrieved_at.isoformat())
    logger.info("[QQQWatch] %s -> %s (%s; posted=%s)", previous,
                classification.state, classification.reason, posted)


def scheduled_jobs() -> dict[str, Any]:
    scheduler = _SCHEDULER.get("ref")
    if scheduler is None:
        return {"registered": False, "jobs": {},
                "reason": "QQQ watcher scheduler is not attached."}
    job = scheduler.get_job("qqq_retest_watch")
    next_run = getattr(job, "next_run_time", None) if job else None
    return {"registered": bool(job),
            "jobs": {"qqq_retest_watch": _iso(next_run)},
            "reason": None if job else "QQQ watcher job is missing."}


def register_qqq_retest_watch(scheduler, app) -> None:
    settings = load_settings()
    _set_status(enabled=settings.enabled,
                levels={"valid_date": settings.levels_date.isoformat(),
                        "support": [settings.support_low, settings.support_high],
                        "reclaim": [settings.reclaim_low, settings.reclaim_high]})
    if scheduler is None:
        logger.warning("[QQQWatch] no scheduler; watcher disabled")
        return

    async def tick() -> None:
        try:
            await run_watch_cycle(app)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[QQQWatch] uncaught cycle error: %r", exc)

    scheduler.add_job(
        tick, "interval", seconds=settings.poll_seconds,
        id="qqq_retest_watch", replace_existing=True, coalesce=True,
        max_instances=1, next_run_time=datetime.now(UTC),
    )
    _SCHEDULER["ref"] = scheduler
    _set_status(registered=True)
    logger.info("[QQQWatch] registered every %ss; alert-only, no orders",
                settings.poll_seconds)


@router.get("/status")
async def qqq_retest_watch_status() -> dict[str, Any]:
    """Current watcher result, timestamps, freshness, and scheduler proof."""
    return {**_STATUS, "scheduler": scheduled_jobs()}
