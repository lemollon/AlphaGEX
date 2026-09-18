"""Generalized, durable intraday options-entry watcher.

This module is deliberately advisory.  It imports no broker execution code and
only reads market data, persists date-bound setup state, and emits deduplicated
Discord notifications for meaningful transitions.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from itertools import product
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from .db import SessionLocal
from .models import (
    IntradayAlertDedup,
    IntradaySelectedWatchlist,
    IntradaySetup,
    IntradayTradePlan,
    IntradayWatchRuntimeStatus,
    QQQWatchRuntimeStatus,
)

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
UTC = timezone.utc
TRADIER_BASE = "https://api.tradier.com/v1"
CORE_SYMBOLS = ("SPY", "QQQ", "XSP", "IWM")
CONFIRMATION_SYMBOLS = ("VIX",)
STATES = {
    "WAIT", "NEAR_TRIGGER", "ENTRY_READY", "ACTIVE", "INVALIDATED",
    "EXPIRED", "DATA_UNAVAILABLE", "LIQUIDITY_BLOCKED",
}
STRATEGIES = {
    "long_call", "long_put", "call_debit_spread", "put_debit_spread",
    "put_credit_spread", "call_credit_spread", "iron_condor", "calendar",
    "double_calendar",
}
ENTRY_TYPES = {
    "breakout_hold", "breakout_retest", "support_hold", "failed_reclaim",
    "vwap_reclaim", "opening_range_breakout", "opening_range_rejection",
    "opening_range_hold",
}
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
router = APIRouter(prefix="/api/spreadworks/intraday-watch",
                   tags=["Intraday Options Watch"])


@dataclass(frozen=True)
class MarketBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int | None = None
    vwap: float | None = None


@dataclass(frozen=True)
class RuleResult:
    state: str
    reason: str
    evidence: tuple[str, ...] = ()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _parse_date(value: Any, field: str = "trading_date") -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field} must be YYYY-MM-DD") from exc


def _normalize_symbol(value: Any) -> str:
    symbol = str(value or "").strip().upper()
    if not SYMBOL_RE.fullmatch(symbol):
        raise HTTPException(status_code=422, detail=f"invalid symbol: {value!r}")
    return symbol


def _require_write_token(
    x_intraday_watch_token: str | None,
    authorization: str | None,
) -> None:
    expected = os.getenv("INTRADAY_WATCH_API_TOKEN", "").strip()
    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    if not expected or (x_intraday_watch_token != expected and bearer != expected):
        raise HTTPException(status_code=401, detail="invalid or missing intraday watch token")


def validate_watchlist(payload: dict[str, Any]) -> tuple[date, list[str]]:
    trading_date = _parse_date(payload.get("trading_date"))
    raw = payload.get("symbols")
    if not isinstance(raw, list):
        raise HTTPException(status_code=422, detail="symbols must be a list")
    symbols = [_normalize_symbol(item) for item in raw]
    if len(symbols) > 8:
        raise HTTPException(status_code=422, detail="at most 8 selected symbols are allowed")
    if len(set(symbols)) != len(symbols):
        raise HTTPException(status_code=422, detail="symbols must not contain duplicates")
    core = set(CORE_SYMBOLS) | set(CONFIRMATION_SYMBOLS)
    if any(symbol in core for symbol in symbols):
        raise HTTPException(status_code=422, detail="selected list must contain non-core symbols only")
    return trading_date, symbols


def validate_setup(raw: dict[str, Any], trading_date: date) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="each setup must be an object")
    setup = dict(raw)
    setup["symbol"] = _normalize_symbol(setup.get("symbol"))
    strategy = str(setup.get("strategy") or "").strip().lower().replace(" ", "_")
    disposition = str(
        setup.get("action") or setup.get("recommendation")
        or setup.get("trade_status") or ""
    ).strip().lower().replace(" ", "_")
    if strategy in {"watch_only", "no_trade"} or disposition in {"watch_only", "no_trade"}:
        raise HTTPException(status_code=422, detail="Watch Only / No Trade ideas are not actionable setups")
    if strategy not in STRATEGIES:
        raise HTTPException(status_code=422, detail=f"unsupported strategy: {strategy}")
    thesis = str(setup.get("thesis") or "").strip().lower()
    if thesis not in {"bullish", "bearish", "neutral"}:
        raise HTTPException(status_code=422, detail="thesis must be bullish, bearish, or neutral")
    entry = setup.get("entry") or setup.get("entry_trigger")
    invalidation = setup.get("invalidation") or setup.get("invalidation_rule")
    if not isinstance(entry, dict) or entry.get("type") not in ENTRY_TYPES:
        raise HTTPException(status_code=422, detail="entry requires a supported rule type")
    if not isinstance(invalidation, dict) or invalidation.get("type") not in {
        "close_below", "close_above", "time", "none",
    }:
        raise HTTPException(status_code=422, detail="invalidation requires a supported rule type")
    numeric_keys = {
        "breakout_hold": ("breakout_level",),
        "breakout_retest": ("breakout_level",),
        "support_hold": ("support_low", "support_high"),
        "failed_reclaim": ("reclaim_level",),
        "vwap_reclaim": (),
        "opening_range_breakout": ("range_high",),
        "opening_range_rejection": ("range_low", "range_high"),
        "opening_range_hold": ("range_low", "range_high"),
    }[entry["type"]]
    for key in numeric_keys:
        try:
            entry[key] = float(entry[key])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"entry.{key} must be numeric") from exc
    if entry["type"] == "support_hold" and entry["support_low"] > entry["support_high"]:
        raise HTTPException(status_code=422, detail="support_low must not exceed support_high")
    if entry["type"] == "opening_range_hold":
        if entry["range_low"] >= entry["range_high"]:
            raise HTTPException(status_code=422, detail="range_low must be below range_high")
        if thesis != "neutral" or strategy not in {"iron_condor", "calendar", "double_calendar"}:
            raise HTTPException(
                status_code=422,
                detail="opening_range_hold requires a neutral iron condor or calendar strategy",
            )
    if invalidation["type"] in {"close_below", "close_above"}:
        try:
            invalidation["level"] = float(invalidation["level"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="invalidation.level must be numeric") from exc
    confirmation_bars = int(entry.get("confirmation_bars", 2))
    if not 1 <= confirmation_bars <= 10:
        raise HTTPException(status_code=422, detail="confirmation_bars must be between 1 and 10")
    entry["confirmation_bars"] = confirmation_bars
    if strategy in {"calendar", "double_calendar"}:
        for key, default in (
            ("maximum_relative_leg_spread", 0.15),
            ("maximum_natural_midpoint_gap_ratio", 0.125),
        ):
            try:
                value = float(setup.get(key, default))
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=422, detail=f"{key} must be numeric") from exc
            if not 0 < value <= 1:
                raise HTTPException(status_code=422, detail=f"{key} must be in (0, 1]")
            setup[key] = value
        for key, default in (
            ("minimum_calendar_open_interest", 50),
            ("minimum_calendar_volume", 10),
        ):
            raw_value = setup.get(key, default)
            if isinstance(raw_value, bool):
                raise HTTPException(status_code=422, detail=f"{key} must be a nonnegative integer")
            try:
                value = int(raw_value)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=422, detail=f"{key} must be a nonnegative integer") from exc
            if value < 0 or str(raw_value).strip() not in {str(value), f"{value}.0"}:
                raise HTTPException(status_code=422, detail=f"{key} must be a nonnegative integer")
            setup[key] = value
    sessions = setup.get("sessions", ["regular"])
    if not isinstance(sessions, list) or not sessions or any(
        item not in {"premarket", "regular", "postmarket"} for item in sessions
    ):
        raise HTTPException(status_code=422, detail="sessions contains an unsupported market session")
    state = str(setup.get("setup_state", "WAIT")).upper()
    if state not in STATES:
        raise HTTPException(status_code=422, detail=f"unsupported setup_state: {state}")
    expires_at = setup.get("expires_at")
    if expires_at:
        try:
            parsed = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="expires_at must be ISO-8601") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ET)
        setup["expires_at"] = parsed.astimezone(UTC).isoformat()
    setup.update(
        strategy=strategy, thesis=thesis, entry=entry,
        invalidation=invalidation, sessions=sessions, setup_state=state,
        trading_date=trading_date.isoformat(),
    )
    setup.pop("entry_trigger", None)
    setup.pop("invalidation_rule", None)
    raw_id = setup.get("setup_id")
    if raw_id:
        suffix = re.sub(r"[^A-Za-z0-9_.-]", "-", str(raw_id))
        setup["setup_id"] = f"{trading_date.isoformat()}:{suffix}"[:64]
    else:
        identity = _json({
            "date": trading_date.isoformat(), "symbol": setup["symbol"],
            "strategy": strategy, "entry": entry,
        })
        setup["setup_id"] = hashlib.sha256(identity.encode()).hexdigest()[:24]
    return setup


def validate_setups_payload(payload: dict[str, Any]) -> tuple[date, list[dict[str, Any]]]:
    trading_date = _parse_date(payload.get("trading_date"))
    raw = payload.get("setups")
    if not isinstance(raw, list) or not raw:
        raise HTTPException(status_code=422, detail="setups must be a non-empty list")
    setups = [validate_setup(item, trading_date) for item in raw]
    ids = [item["setup_id"] for item in setups]
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=422, detail="setup IDs must be unique")
    return trading_date, setups


def validate_plan_parity(symbols: list[str], setups: list[dict[str, Any]]) -> dict[str, Any]:
    selected = set(symbols)
    non_core_setups = {
        item["symbol"] for item in setups if item["symbol"] not in set(CORE_SYMBOLS)
    }
    missing = sorted(selected - non_core_setups)
    outside = sorted(non_core_setups - selected)
    if missing or outside:
        details = []
        if missing:
            details.append(f"selected symbols without actionable setups: {', '.join(missing)}")
        if outside:
            details.append(f"non-core setup symbols outside selected watchlist: {', '.join(outside)}")
        raise HTTPException(status_code=422, detail="; ".join(details))
    return {
        "valid": True,
        "selected_non_core_symbols": sorted(selected),
        "non_core_setup_symbols": sorted(non_core_setups),
        "selected_symbol_count": len(symbols),
        "setup_count": len(setups),
    }


def plan_hash(trading_date: date, symbols: list[str],
              setups: list[dict[str, Any]]) -> str:
    canonical = {
        "trading_date": trading_date.isoformat(),
        "symbols": sorted(symbols),
        "setups": sorted(setups, key=lambda item: item["setup_id"]),
    }
    return hashlib.sha256(_json(canonical).encode("utf-8")).hexdigest()


def market_session(now: datetime) -> str:
    now_et = now.astimezone(ET)
    current = now_et.time().replace(tzinfo=None)
    if now_et.weekday() >= 5:
        return "closed"
    if time(4, 0) <= current < time(9, 30):
        return "premarket"
    if time(9, 30) <= current < time(16, 0):
        return "regular"
    if time(16, 0) <= current < time(20, 0):
        return "postmarket"
    return "closed"


def freshness(timestamp: datetime, retrieved_at: datetime, limit: float = 90.0) -> dict[str, Any]:
    age = max(0.0, (retrieved_at.astimezone(UTC) - timestamp.astimezone(UTC)).total_seconds())
    return {
        "exchange_timestamp": timestamp.astimezone(UTC).isoformat(),
        "retrieval_timestamp": retrieved_at.astimezone(UTC).isoformat(),
        "age_seconds": round(age, 3),
        "fresh": age <= limit,
    }


def _closed_bars(bars: Iterable[MarketBar], now: datetime) -> list[MarketBar]:
    return sorted(
        [bar for bar in bars if bar.timestamp + timedelta(minutes=1) <= now],
        key=lambda item: item.timestamp,
    )


def _relative_strength_ok(setup: dict[str, Any], context: dict[str, Any] | None) -> tuple[bool, str]:
    rule = setup.get("relative_strength") or (setup.get("confirmation_rule") or {}).get("relative_strength")
    if not rule:
        return True, "not required"
    if not context:
        return False, "relative-strength confirmation unavailable"
    symbol_return = context.get("symbol_return")
    reference_return = context.get("reference_return")
    if symbol_return is None or reference_return is None:
        return False, "relative-strength confirmation unavailable"
    spread = float(symbol_return) - float(reference_return)
    minimum = float(rule.get("minimum_outperformance", 0.0))
    return spread >= minimum, f"relative outperformance {spread:.4f} vs minimum {minimum:.4f}"


def _confirmation_inputs_ok(setup: dict[str, Any], context: dict[str, float] | None) -> tuple[bool, list[str]]:
    conditions = (setup.get("confirmation_rule") or {}).get("inputs") or []
    if not conditions:
        return True, []
    context = context or {}
    messages: list[str] = []
    for condition in conditions:
        symbol = str(condition.get("symbol") or "").upper()
        actual = context.get(symbol)
        required = bool(condition.get("required", True))
        if actual is None:
            messages.append(f"{symbol or 'confirmation input'} unavailable")
            if required:
                return False, messages
            continue
        operator = condition.get("operator")
        target = float(condition.get("value"))
        passed = ((operator == "above" and actual > target)
                  or (operator == "below" and actual < target)
                  or (operator == "at_or_above" and actual >= target)
                  or (operator == "at_or_below" and actual <= target))
        messages.append(f"{symbol} {actual:g} {operator} {target:g}: {'confirmed' if passed else 'not confirmed'}")
        if not passed:
            return False, messages
    return True, messages


def evaluate_setup(
    setup: dict[str, Any], bars: Iterable[MarketBar], now: datetime,
    *, quote_timestamp: datetime | None = None,
    quote_price: float | None = None,
    relative_context: dict[str, Any] | None = None,
    confirmation_context: dict[str, float] | None = None,
    stale_after_seconds: float = 90.0,
) -> RuleResult:
    """Evaluate one setup using completed one-minute bars only."""
    now = now.astimezone(UTC)
    trading_date = date.fromisoformat(setup["trading_date"])
    if now.astimezone(ET).date() != trading_date:
        return RuleResult("EXPIRED", "Setup is date-bound to a different trading day.")
    expires_at = setup.get("expires_at")
    if expires_at and now >= datetime.fromisoformat(expires_at).astimezone(UTC):
        return RuleResult("EXPIRED", "Setup expiration time has passed.")
    if market_session(now) not in setup.get("sessions", ["regular"]):
        return RuleResult("WAIT", "Setup is outside its selected market session.")
    completed = _closed_bars(bars, now)
    if quote_timestamp is None or quote_price is None:
        return RuleResult("DATA_UNAVAILABLE", "A fresh underlying quote is unavailable.")
    qfresh = freshness(quote_timestamp, now, stale_after_seconds)
    if not qfresh["fresh"]:
        return RuleResult("DATA_UNAVAILABLE", f"Underlying quote is stale ({qfresh['age_seconds']:.1f}s).")
    if not completed:
        return RuleResult("DATA_UNAVAILABLE", "No completed one-minute bar is available.")
    bar_end = completed[-1].timestamp.astimezone(UTC) + timedelta(minutes=1)
    bfresh = freshness(bar_end, now, stale_after_seconds)
    if not bfresh["fresh"]:
        return RuleResult("DATA_UNAVAILABLE", f"Newest completed bar is stale ({bfresh['age_seconds']:.1f}s).")

    previous_state = str(setup.get("setup_state", "WAIT")).upper()
    invalidation = setup["invalidation"]
    if invalidation["type"] == "close_below" and completed[-1].close < invalidation["level"]:
        if previous_state in {"ENTRY_READY", "ACTIVE"}:
            return RuleResult("INVALIDATED", f"Completed close {completed[-1].close:g} is below {invalidation['level']:g}.")
    if invalidation["type"] == "close_above" and completed[-1].close > invalidation["level"]:
        if previous_state in {"ENTRY_READY", "ACTIVE"}:
            return RuleResult("INVALIDATED", f"Completed close {completed[-1].close:g} is above {invalidation['level']:g}.")

    entry = setup["entry"]
    needed = int(entry.get("confirmation_bars", 2))
    recent = completed[-needed:]
    if len(recent) < needed:
        return RuleResult("WAIT", f"Need {needed} completed confirmation bars.")
    kind = entry["type"]
    ready = False
    near = False
    evidence: list[str] = []
    level: float | None = None
    if kind == "breakout_hold":
        level = entry["breakout_level"]
        ready = all(bar.close > level for bar in recent)
        near = quote_price >= level * 0.997
        evidence.append(f"{needed} completed closes above {level:g}" if ready else f"waiting for closes above {level:g}")
    elif kind == "breakout_retest":
        level = entry["breakout_level"]
        breakout_indices = [i for i, bar in enumerate(completed[:-needed]) if bar.close > level]
        if breakout_indices:
            after = completed[breakout_indices[-1] + 1:]
            retested = any(bar.low <= level and bar.close >= level for bar in after)
            ready = retested and all(bar.close >= level for bar in recent)
        near = quote_price >= level * 0.997
        evidence.append(f"breakout, retest, and {needed}-bar hold at {level:g}" if ready else f"waiting for completed breakout/retest at {level:g}")
    elif kind == "support_hold":
        low, high = entry["support_low"], entry["support_high"]
        touched = any(bar.low <= high and bar.high >= low for bar in completed)
        ready = touched and all(bar.close >= low for bar in recent)
        near = quote_price <= high * 1.003 and quote_price >= low * 0.997
        evidence.append(f"support {low:g}-{high:g} held for {needed} closes" if ready else f"waiting for support hold at {low:g}-{high:g}")
    elif kind == "failed_reclaim":
        level = entry["reclaim_level"]
        failed = any(bar.high >= level and bar.close < level for bar in completed[-max(needed + 3, 5):])
        ready = failed and all(bar.close < level for bar in recent)
        near = quote_price <= level * 1.003
        evidence.append(f"failed reclaim and {needed} closes below {level:g}" if ready else f"waiting for failed reclaim of {level:g}")
    elif kind == "vwap_reclaim":
        valid = [bar for bar in completed if bar.vwap is not None]
        if len(valid) >= needed + 1:
            crossed = valid[-needed - 1].close <= float(valid[-needed - 1].vwap)
            ready = crossed and all(bar.close > float(bar.vwap) for bar in valid[-needed:])
            near = abs(valid[-1].close - float(valid[-1].vwap)) / valid[-1].close <= 0.003
        evidence.append("VWAP reclaimed with completed-bar confirmation" if ready else "waiting for fresh VWAP reclaim")
    elif kind == "opening_range_breakout":
        level = entry["range_high"]
        ready = all(bar.close > level for bar in recent)
        near = quote_price >= level * 0.997
        evidence.append(f"opening range {level:g} cleared for {needed} closes" if ready else f"waiting for opening-range breakout above {level:g}")
    elif kind == "opening_range_rejection":
        low, high = entry["range_low"], entry["range_high"]
        rejected = any(bar.high >= low and bar.high <= high * 1.002 and bar.close < low for bar in completed[-max(needed + 3, 5):])
        ready = rejected and all(bar.close < low for bar in recent)
        near = quote_price <= high * 1.003 and quote_price >= low * 0.997
        evidence.append(f"opening range rejected with {needed} closes below {low:g}" if ready else "waiting for opening-range rejection")
    elif kind == "opening_range_hold":
        low, high = entry["range_low"], entry["range_high"]
        quote_in_range = low <= quote_price <= high
        lower_touched = any(bar.low <= low for bar in completed)
        upper_touched = any(bar.high >= high for bar in completed)
        closes_held = all(low <= bar.close <= high for bar in recent)
        ready = quote_in_range and lower_touched and upper_touched and closes_held
        near = quote_in_range
        if ready:
            evidence.append(
                f"both sides of opening range {low:g}-{high:g} were tested and "
                f"the latest {needed} completed closes held inside"
            )
        else:
            missing = []
            if not lower_touched:
                missing.append("lower-side test")
            if not upper_touched:
                missing.append("upper-side test")
            if not closes_held:
                missing.append(f"{needed} in-range closes")
            if not quote_in_range:
                missing.append("quote back inside range")
            evidence.append(
                f"waiting for two-sided hold in {low:g}-{high:g}: "
                + ", ".join(missing)
            )

    rs_ok, rs_reason = _relative_strength_ok(setup, relative_context)
    if setup.get("relative_strength") or (setup.get("confirmation_rule") or {}).get("relative_strength"):
        evidence.append(rs_reason)
    inputs_ok, input_evidence = _confirmation_inputs_ok(setup, confirmation_context)
    evidence.extend(input_evidence)
    ready = ready and rs_ok and inputs_ok
    if ready:
        return RuleResult("ENTRY_READY", "; ".join(evidence), tuple(evidence))
    if near:
        return RuleResult("NEAR_TRIGGER", "; ".join(evidence), tuple(evidence))
    return RuleResult("WAIT", "; ".join(evidence), tuple(evidence))


def _option_time(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return datetime.fromtimestamp(float(value) / 1000.0, UTC)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ET)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError, OSError):
        return None


def normalize_contract(raw: dict[str, Any], retrieved_at: datetime,
                       stale_after_seconds: float = 90.0) -> dict[str, Any] | None:
    greeks = raw.get("greeks") or {}
    option_type = str(raw.get("option_type", "")).lower()
    if option_type not in {"call", "put"}:
        return None
    bid_at = _option_time(raw.get("bid_date"))
    ask_at = _option_time(raw.get("ask_date"))
    greek_at = _option_time(greeks.get("updated_at"))
    required = (raw.get("bid"), raw.get("ask"), raw.get("strike"),
                greeks.get("delta"), greeks.get("gamma"), greeks.get("theta"),
                greeks.get("vega"), greeks.get("mid_iv"))
    if any(value is None for value in required) or not bid_at or not ask_at or not greek_at:
        return None
    if any(not freshness(stamp, retrieved_at, stale_after_seconds)["fresh"] for stamp in (bid_at, ask_at, greek_at)):
        return None
    bid, ask = float(raw["bid"]), float(raw["ask"])
    if bid < 0 or ask <= 0 or bid > ask:
        return None
    return {
        "symbol": raw.get("symbol"), "strike": float(raw["strike"]),
        "right": "C" if option_type == "call" else "P",
        "bid": bid, "ask": ask, "delta": float(greeks["delta"]),
        "gamma": greeks.get("gamma"), "theta": greeks.get("theta"),
        "vega": greeks.get("vega"), "iv": greeks.get("mid_iv"),
        "open_interest": raw.get("open_interest"), "volume": raw.get("volume"),
        "bid_size": raw.get("bidsize"), "ask_size": raw.get("asksize"),
        "exchange_timestamp": min(bid_at, ask_at, greek_at).isoformat(),
        "retrieval_timestamp": retrieved_at.astimezone(UTC).isoformat(),
        "age_seconds": max(freshness(stamp, retrieved_at)["age_seconds"] for stamp in (bid_at, ask_at, greek_at)),
    }


def _delta_candidate(contracts: Iterable[dict[str, Any]], right: str,
                     band: tuple[float, float], *, min_oi: int = 0,
                     min_volume: int = 0) -> list[dict[str, Any]]:
    low, high = band
    midpoint = (low + high) / 2
    rows = [item for item in contracts if item["right"] == right
            and low <= abs(float(item["delta"])) <= high
            and int(item.get("open_interest") or 0) >= min_oi
            and int(item.get("volume") or 0) >= min_volume]
    return sorted(rows, key=lambda item: (abs(abs(float(item["delta"])) - midpoint), item["strike"]))


def select_option_structure(
    strategy: str, contracts: list[dict[str, Any]], setup: dict[str, Any],
    expiration: str,
) -> dict[str, Any] | None:
    """Deterministically select fresh contracts by delta and structure."""
    profile = setup.get("target_delta_profile") or {}
    is_credit = strategy in {"put_credit_spread", "call_credit_spread", "iron_condor"}
    min_oi = int(setup.get("minimum_open_interest", 50 if is_credit else 0))
    min_volume = int(setup.get("minimum_volume", 1 if is_credit else 0))
    constraints = {"min_oi": min_oi, "min_volume": min_volume}

    def band(name: str, default: tuple[float, float]) -> tuple[float, float]:
        value = profile.get(name, default)
        return float(value[0]), float(value[1])

    def first(right: str, delta_band: tuple[float, float], predicate=lambda _: True):
        return next((row for row in _delta_candidate(contracts, right, delta_band, **constraints) if predicate(row)), None)

    result: dict[str, Any] = {"strategy": strategy, "expiration": expiration, "source": "Tradier production option chain"}
    if strategy in {"long_call", "long_put"}:
        right = "C" if strategy == "long_call" else "P"
        leg = first(right, band("long", (0.50, 0.65)))
        if not leg:
            return None
        result.update(legs=[{"action": "buy", **leg}], natural_debit=leg["ask"],
                      max_risk=round(leg["ask"] * 100, 2),
                      selection_reason="delta closest to midpoint of requested long-option band")
        return result
    if strategy in {"calendar", "double_calendar"}:
        return None  # one expiration cannot safely construct a calendar

    if strategy == "iron_condor":
        put_setup = dict(setup, strategy="put_credit_spread")
        call_setup = dict(setup, strategy="call_credit_spread")
        put_side = select_option_structure("put_credit_spread", contracts, put_setup, expiration)
        call_side = select_option_structure("call_credit_spread", contracts, call_setup, expiration)
        if not put_side or not call_side:
            return None
        legs = put_side["legs"] + call_side["legs"]
        credit = round(put_side["natural_credit"] + call_side["natural_credit"], 2)
        width = max(put_side["width"], call_side["width"])
        if not 0 < credit < width:
            return None
        result.update(legs=legs, natural_credit=credit, width=width,
                      max_risk=round((width - credit) * 100, 2),
                      selection_reason="both short legs closest to 0.175 absolute delta with farther OTM defined-risk wings")
        return result

    debit = strategy in {"call_debit_spread", "put_debit_spread"}
    put = strategy in {"put_debit_spread", "put_credit_spread"}
    right = "P" if put else "C"
    if debit:
        long_leg = first(right, band("long", (0.50, 0.65)))
        if not long_leg:
            return None
        if right == "C":
            short_leg = first(right, band("short", (0.25, 0.40)), lambda row: row["strike"] > long_leg["strike"])
        else:
            short_leg = first(right, band("short", (0.25, 0.40)), lambda row: row["strike"] < long_leg["strike"])
        if not short_leg:
            return None
        width = abs(short_leg["strike"] - long_leg["strike"])
        natural = round(long_leg["ask"] - short_leg["bid"], 2)
        if not 0 < natural < width:
            return None
        result.update(legs=[{"action": "buy", **long_leg}, {"action": "sell", **short_leg}],
                      natural_debit=natural, width=width,
                      max_risk=round(natural * 100, 2),
                      selection_reason="legs closest to requested delta midpoints with a valid natural debit")
        return result

    support = (setup.get("support_levels") or [None])[0]
    resistance = (setup.get("resistance_levels") or [None])[-1]
    expected = setup.get("expected_move_reference")
    spot = setup.get("current_price")
    def structural_short(row: dict[str, Any]) -> bool:
        if right == "P" and support is not None and row["strike"] >= float(support):
            return False
        if right == "C" and resistance is not None and row["strike"] <= float(resistance):
            return False
        if expected is not None and spot is not None:
            outside = float(spot) - float(expected) if right == "P" else float(spot) + float(expected)
            if right == "P" and row["strike"] > outside:
                return False
            if right == "C" and row["strike"] < outside:
                return False
        return True
    short_leg = first(right, band("short", (0.15, 0.25)), structural_short)
    if not short_leg:
        return None
    if right == "P":
        long_leg = first(right, band("long", (0.05, 0.15)), lambda row: row["strike"] < short_leg["strike"])
    else:
        long_leg = first(right, band("long", (0.05, 0.15)), lambda row: row["strike"] > short_leg["strike"])
    if not long_leg:
        return None
    width = abs(short_leg["strike"] - long_leg["strike"])
    credit = round(short_leg["bid"] - long_leg["ask"], 2)
    min_ratio = float(setup.get("minimum_credit_to_width", 0.20))
    max_leg_spread = float(setup.get("maximum_leg_spread", 1.0))
    if (not 0 < credit < width or credit / width < min_ratio
            or short_leg["ask"] - short_leg["bid"] > max_leg_spread
            or long_leg["ask"] - long_leg["bid"] > max_leg_spread):
        return None
    result.update(legs=[{"action": "sell", **short_leg}, {"action": "buy", **long_leg}],
                  natural_credit=credit, width=width,
                  max_risk=round((width - credit) * 100, 2),
                  selection_reason="short strike satisfies delta and level constraints; wing is farther OTM; credit passes configured width ratio")
    return result


def select_calendar_structure(strategy: str, front: list[dict[str, Any]],
                              back: list[dict[str, Any]], setup: dict[str, Any],
                              front_expiration: str, back_expiration: str) -> dict[str, Any] | None:
    """Select the closest liquid same-strike structure, or diagnose the closest."""
    thesis = setup.get("thesis")
    rights = ["C" if thesis == "bullish" else "P"]
    if strategy == "double_calendar":
        rights = ["P", "C"]
    anchors = {
        "P": (setup.get("support_levels") or [setup.get("current_price")])[-1],
        "C": (setup.get("resistance_levels") or [setup.get("current_price")])[0],
    }
    pair_groups: list[list[tuple[dict[str, Any], dict[str, Any], tuple[float, float, float]]]] = []
    for right in rights:
        front_candidates = _delta_candidate(front, right, (0.30, 0.50))
        back_candidates = _delta_candidate(back, right, (0.30, 0.50))
        pairs = [(near, far) for near in front_candidates for far in back_candidates
                 if near["strike"] == far["strike"]]
        if not pairs:
            return None
        anchor = anchors[right]
        ranked = []
        for near, far in pairs:
            rank = (
                abs(near["strike"] - float(anchor)) if anchor is not None else 0.0,
                abs(abs(near["delta"]) - .40) + abs(abs(far["delta"]) - .40),
                near["strike"],
            )
            ranked.append((near, far, rank))
        pair_groups.append(ranked)

    thresholds = {
        "maximum_relative_leg_spread": float(setup.get("maximum_relative_leg_spread", 0.15)),
        "maximum_natural_midpoint_gap_ratio": float(setup.get("maximum_natural_midpoint_gap_ratio", 0.125)),
        "minimum_calendar_open_interest": int(setup.get("minimum_calendar_open_interest", 50)),
        "minimum_calendar_volume": int(setup.get("minimum_calendar_volume", 10)),
    }

    def snapshot(combo) -> tuple[dict[str, Any], tuple[Any, ...]]:
        legs: list[dict[str, Any]] = []
        failures: list[str] = []
        midpoint_debit = 0.0
        natural_debit = 0.0
        for near, far, _pair_rank in combo:
            observed = (
                {"action": "sell", "expiration": front_expiration, **near},
                {"action": "buy", "expiration": back_expiration, **far},
            )
            pair_midpoints = []
            for leg in observed:
                midpoint = (float(leg["bid"]) + float(leg["ask"])) / 2.0
                relative_spread = ((float(leg["ask"]) - float(leg["bid"])) / midpoint
                                   if midpoint > 0 else None)
                oi = leg.get("open_interest")
                volume = leg.get("volume")
                activity_pass = (
                    int(oi or 0) >= thresholds["minimum_calendar_open_interest"]
                    or int(volume or 0) >= thresholds["minimum_calendar_volume"]
                )
                enriched = dict(leg, midpoint=round(midpoint, 4),
                                relative_spread=(round(relative_spread, 6)
                                                 if relative_spread is not None else None),
                                activity_pass=activity_pass)
                legs.append(enriched)
                pair_midpoints.append(midpoint)
                label = f"{leg['action']} {leg['right']} {leg['strike']:g} {leg['expiration']}"
                if (relative_spread is None
                        or relative_spread - thresholds["maximum_relative_leg_spread"] > 1e-12):
                    spread_text = (f"{relative_spread:.1%}" if relative_spread is not None
                                   else "unavailable")
                    failures.append(
                        f"{label} spread {spread_text} exceeds "
                        f"{thresholds['maximum_relative_leg_spread']:.1%}"
                    )
                if not activity_pass:
                    failures.append(
                        f"{label} activity OI {int(oi or 0)} / volume {int(volume or 0)} "
                        f"is below OI {thresholds['minimum_calendar_open_interest']} "
                        f"OR volume {thresholds['minimum_calendar_volume']}"
                    )
            midpoint_debit += pair_midpoints[1] - pair_midpoints[0]
            natural_debit += float(far["ask"]) - float(near["bid"])
        if midpoint_debit <= 0:
            gap_ratio = None
            failures.append("composite midpoint debit is not positive")
        else:
            gap_ratio = (natural_debit - midpoint_debit) / midpoint_debit
            if gap_ratio - thresholds["maximum_natural_midpoint_gap_ratio"] > 1e-12:
                failures.append(
                    f"natural-to-midpoint debit gap {gap_ratio:.1%} exceeds "
                    f"{thresholds['maximum_natural_midpoint_gap_ratio']:.1%}"
                )
        if natural_debit <= 0:
            failures.append("natural debit is not positive")
        liquidity_status = "PASS" if not failures else "BLOCKED"
        result = {
            "strategy": strategy, "front_expiration": front_expiration,
            "back_expiration": back_expiration, "legs": legs,
            "natural_debit": round(natural_debit, 4),
            "composite_midpoint_debit": round(midpoint_debit, 4),
            "natural_midpoint_gap_ratio": (round(gap_ratio, 6) if gap_ratio is not None else None),
            "liquidity_status": liquidity_status,
            "failed_checks": failures,
            "liquidity_thresholds": thresholds,
            "source": "Tradier production option chains",
            "selection_reason": (
                "liquid same-strike front/back contracts nearest the configured range anchor "
                "and 0.40 absolute delta" if liquidity_status == "PASS" else
                "closest intended same-strike structure shown for liquidity diagnostics only"
            ),
            "observed_only": liquidity_status == "BLOCKED",
        }
        if liquidity_status == "PASS":
            result["max_risk"] = round(natural_debit * 100, 2)
        combo_rank = (
            sum(pair[2][0] for pair in combo),
            sum(pair[2][1] for pair in combo),
            tuple(pair[2][2] for pair in combo),
        )
        return result, combo_rank

    evaluated = [snapshot(combo) for combo in product(*pair_groups)]
    passing = [item for item in evaluated if item[0]["liquidity_status"] == "PASS"]
    candidates = passing or evaluated
    selected, _rank = min(candidates, key=lambda item: item[1])
    return selected


def apply_option_liquidity_state(
    result: RuleResult, option_selection: dict[str, Any] | None,
) -> RuleResult:
    """Turn a confirmed underlying trigger into a no-trade liquidity state."""
    if result.state != "ENTRY_READY" or not option_selection:
        return result
    if option_selection.get("liquidity_status") != "BLOCKED":
        return result
    failures = option_selection.get("failed_checks") or ["calendar liquidity checks failed"]
    return RuleResult(
        "LIQUIDITY_BLOCKED",
        "Underlying entry trigger confirmed, but no trade: " + "; ".join(failures),
        result.evidence,
    )


def _db_required():
    if SessionLocal is None:
        raise HTTPException(status_code=503, detail="database is not configured")
    return SessionLocal()


def store_watchlist(trading_date: date, symbols: list[str]) -> None:
    db = _db_required()
    try:
        row = db.get(IntradaySelectedWatchlist, trading_date)
        if row is None:
            db.add(IntradaySelectedWatchlist(trading_date=trading_date, symbols_json=_json(symbols)))
        else:
            row.symbols_json = _json(symbols)
        db.commit()
    finally:
        db.close()


def store_setups(trading_date: date, setups: list[dict[str, Any]]) -> None:
    db = _db_required()
    try:
        db.query(IntradaySetup).filter(IntradaySetup.trading_date < trading_date).update({"active": 0})
        incoming = {item["setup_id"] for item in setups}
        for row in db.query(IntradaySetup).filter(IntradaySetup.trading_date == trading_date).all():
            if row.setup_id not in incoming:
                row.active = 0
        for item in setups:
            row = db.get(IntradaySetup, item["setup_id"])
            if row is None:
                row = IntradaySetup(setup_id=item["setup_id"], trading_date=trading_date,
                                    symbol=item["symbol"], strategy=item["strategy"],
                                    thesis=item["thesis"], state=item["setup_state"],
                                    payload_json=_json(item), active=1)
                db.add(row)
            else:
                row.trading_date = trading_date
                row.symbol = item["symbol"]
                row.strategy = item["strategy"]
                row.thesis = item["thesis"]
                row.payload_json = _json(item)
                row.active = 1
        db.commit()
    finally:
        db.close()


def store_plan(trading_date: date, payload: dict[str, Any]) -> None:
    db = _db_required()
    try:
        db.query(IntradayTradePlan).filter(IntradayTradePlan.trading_date < trading_date).update({"active": 0})
        row = db.get(IntradayTradePlan, trading_date)
        if row is None:
            db.add(IntradayTradePlan(trading_date=trading_date, payload_json=_json(payload), active=1))
        else:
            row.payload_json = _json(payload)
            row.active = 1
        db.commit()
    finally:
        db.close()


def store_morning_plan_atomic(trading_date: date, symbols: list[str],
                              setups: list[dict[str, Any]],
                              payload: dict[str, Any],
                              *, ingested_at: datetime | None = None) -> dict[str, Any]:
    """Persist the plan, exact watchlist, and setups in one transaction."""
    parity = validate_plan_parity(symbols, setups)
    digest = plan_hash(trading_date, symbols, setups)
    ingested = (ingested_at or datetime.now(UTC)).astimezone(UTC)
    normalized = dict(payload)
    normalized.update(
        trading_date=trading_date.isoformat(), symbols=symbols, setups=setups,
        plan_hash=digest, ingested_at=ingested.isoformat(), parity=parity,
    )
    db = _db_required()
    try:
        db.query(IntradayTradePlan).filter(
            IntradayTradePlan.trading_date < trading_date
        ).update({"active": 0})
        db.query(IntradaySetup).filter(
            IntradaySetup.trading_date < trading_date
        ).update({"active": 0, "state": "EXPIRED"})

        watchlist = db.get(IntradaySelectedWatchlist, trading_date)
        if watchlist is None:
            db.add(IntradaySelectedWatchlist(
                trading_date=trading_date, symbols_json=_json(symbols)
            ))
        else:
            watchlist.symbols_json = _json(symbols)

        incoming = {item["setup_id"] for item in setups}
        for row in db.query(IntradaySetup).filter(
            IntradaySetup.trading_date == trading_date
        ).all():
            if row.setup_id not in incoming:
                row.active = 0
        for item in setups:
            row = db.get(IntradaySetup, item["setup_id"])
            if row is None:
                db.add(IntradaySetup(
                    setup_id=item["setup_id"], trading_date=trading_date,
                    symbol=item["symbol"], strategy=item["strategy"],
                    thesis=item["thesis"], state=item["setup_state"],
                    payload_json=_json(item), active=1,
                ))
            else:
                row.trading_date = trading_date
                row.symbol = item["symbol"]
                row.strategy = item["strategy"]
                row.thesis = item["thesis"]
                row.state = item["setup_state"]
                row.payload_json = _json(item)
                row.active = 1

        plan = db.get(IntradayTradePlan, trading_date)
        if plan is None:
            db.add(IntradayTradePlan(
                trading_date=trading_date, payload_json=_json(normalized), active=1
            ))
        else:
            plan.payload_json = _json(normalized)
            plan.active = 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {
        "trading_date": trading_date.isoformat(), "persisted": True,
        "registered_symbol_count": len(symbols),
        "registered_setup_count": len(setups),
        "registered_total_symbol_count": len(set(CORE_SYMBOLS) | set(symbols)),
        "plan_hash": digest, "ingested_at": ingested.isoformat(),
        "parity": parity,
    }


def claim_alert(db, setup_id: str, trading_date: date, state: str,
                transition_at: datetime, payload: dict[str, Any] | None = None) -> str | None:
    bucket = transition_at.astimezone(UTC).replace(second=0, microsecond=0)
    event_key = f"{trading_date.isoformat()}:{setup_id}:{state}:{bucket.isoformat()}"
    existing = db.get(IntradayAlertDedup, event_key)
    if existing is not None:
        return event_key if existing.posted_at is None else None
    db.add(IntradayAlertDedup(event_key=event_key, trading_date=trading_date,
                              setup_id=setup_id, state=state, transition_at=transition_at,
                              payload_json=_json(payload) if payload else None))
    try:
        db.commit()
        return event_key
    except IntegrityError:
        db.rollback()
        return None


def _public_setup(row: IntradaySetup) -> dict[str, Any]:
    payload = json.loads(row.payload_json)
    return {
        "setup_id": row.setup_id, "trading_date": row.trading_date.isoformat(),
        "symbol": row.symbol, "strategy": row.strategy, "thesis": row.thesis,
        "state": row.state, "active": bool(row.active),
        "last_market_timestamp": _iso(row.last_market_timestamp),
        "last_options_timestamp": _iso(row.last_options_timestamp),
        "last_transition_at": _iso(row.last_transition_at),
        "trigger_status": payload.get("entry"),
        "option_strike_selection": json.loads(row.option_selection_json) if row.option_selection_json else None,
    }


def _load_runtime_status() -> dict[str, Any]:
    if SessionLocal is None:
        return {"worker_healthy": False, "errors": ["database is not configured"]}
    db = SessionLocal()
    try:
        row = db.get(IntradayWatchRuntimeStatus, "intraday-watch")
        if row is None:
            return {"worker_healthy": False, "errors": ["worker has not written a heartbeat"]}
        payload = json.loads(row.payload_json)
        heartbeat = row.heartbeat_at
        if heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=UTC)
        age = max(0.0, (datetime.now(UTC) - heartbeat.astimezone(UTC)).total_seconds())
        poll = int(payload.get("poll_interval_seconds", 60))
        payload.update(worker_heartbeat=heartbeat.isoformat(), worker_heartbeat_age_seconds=round(age, 1),
                       worker_healthy=age <= poll + max(30, poll // 2))
        return payload
    finally:
        db.close()


@router.post("/watchlist")
async def post_watchlist(request: Request,
                         x_intraday_watch_token: str | None = Header(default=None),
                         authorization: str | None = Header(default=None)):
    _require_write_token(x_intraday_watch_token, authorization)
    payload = await request.json()
    trading_date, symbols = validate_watchlist(payload)
    await asyncio.to_thread(store_watchlist, trading_date, symbols)
    return {"trading_date": trading_date.isoformat(), "symbols": symbols, "persisted": True}


@router.post("/setups")
async def post_setups(request: Request,
                      x_intraday_watch_token: str | None = Header(default=None),
                      authorization: str | None = Header(default=None)):
    _require_write_token(x_intraday_watch_token, authorization)
    payload = await request.json()
    trading_date, setups = validate_setups_payload(payload)
    await asyncio.to_thread(store_setups, trading_date, setups)
    return {"trading_date": trading_date.isoformat(), "setup_ids": [item["setup_id"] for item in setups], "persisted": True}


@router.post("/plan")
async def post_plan(request: Request,
                    x_intraday_watch_token: str | None = Header(default=None),
                    authorization: str | None = Header(default=None)):
    _require_write_token(x_intraday_watch_token, authorization)
    payload = await request.json()
    trading_date = _parse_date(payload.get("trading_date"))
    if "symbols" not in payload or "setups" not in payload:
        raise HTTPException(
            status_code=422,
            detail="morning plan requires both symbols and setups",
        )
    _, symbols = validate_watchlist({
        "trading_date": trading_date.isoformat(), "symbols": payload["symbols"]
    })
    _, setups = validate_setups_payload({
        "trading_date": trading_date.isoformat(), "setups": payload["setups"]
    })
    validate_plan_parity(symbols, setups)
    return await asyncio.to_thread(
        store_morning_plan_atomic, trading_date, symbols, setups, payload
    )


@router.get("/plan")
async def get_plan(trading_date: str | None = None):
    requested = _parse_date(trading_date) if trading_date else datetime.now(ET).date()
    db = _db_required()
    try:
        row = db.get(IntradayTradePlan, requested)
        if row is None:
            raise HTTPException(status_code=404, detail="no plan for requested trading date")
        payload = json.loads(row.payload_json)
        payload["active"] = bool(row.active)
        return payload
    finally:
        db.close()


@router.get("/status")
async def get_status():
    return await asyncio.to_thread(_load_runtime_status)


async def _tradier_get(app, path: str, params: dict[str, Any]) -> dict[str, Any]:
    token = os.getenv("TRADIER_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TRADIER_TOKEN is not configured")
    response = await app.state.http.get(
        f"{TRADIER_BASE}{path}", params=params,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if response.status_code != 200:
        raise RuntimeError(f"Tradier {path} returned HTTP {response.status_code}")
    return response.json()


def _quote_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = (payload.get("quotes") or {}).get("quote") or []
    return [rows] if isinstance(rows, dict) else rows


def _bar_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = (payload.get("series") or {}).get("data") or []
    return [rows] if isinstance(rows, dict) else rows


async def fetch_symbol_market(app, symbol: str, now: datetime) -> dict[str, Any]:
    """Fetch a legitimate symbol quote and its completed one-minute bars.

    XSP follows this exact index-symbol path. SPY is never substituted.
    """
    now_et = now.astimezone(ET)
    quote_payload, bars_payload = await asyncio.gather(
        _tradier_get(app, "/markets/quotes", {"symbols": symbol, "greeks": "false"}),
        _tradier_get(app, "/markets/timesales", {
            "symbol": symbol, "interval": "1min",
            "start": datetime.combine(now_et.date(), time(4, 0), ET).strftime("%Y-%m-%d %H:%M"),
            "end": now_et.strftime("%Y-%m-%d %H:%M"), "session_filter": "all",
        }),
    )
    quotes = _quote_rows(quote_payload)
    if not quotes:
        raise RuntimeError(f"Tradier returned no usable {symbol} quote")
    quote = quotes[0]
    last_price = quote.get("last")
    trade_at = _option_time(quote.get("trade_date"))
    try:
        last_value = float(last_price) if last_price is not None else None
        if last_value is not None and last_value <= 0:
            last_value = None
    except (TypeError, ValueError):
        last_value = None
    bid, ask = quote.get("bid"), quote.get("ask")
    bid_at = _option_time(quote.get("bid_date"))
    ask_at = _option_time(quote.get("ask_date"))
    last_fresh = (
        last_value is not None and trade_at is not None
        and freshness(trade_at, now)["fresh"]
    )
    bbo_fresh = False
    if bid is not None and ask is not None and bid_at and ask_at:
        try:
            bid_value, ask_value = float(bid), float(ask)
            bbo_fresh = (
                bid_value > 0 and ask_value >= bid_value
                and freshness(bid_at, now)["fresh"]
                and freshness(ask_at, now)["fresh"]
            )
        except (TypeError, ValueError):
            bbo_fresh = False
    if last_fresh:
        price = last_value
        quote_at = trade_at
        price_basis = "last trade"
    elif bbo_fresh:
        price = (bid_value + ask_value) / 2.0
        quote_at = min(bid_at, ask_at)
        price_basis = "bid/ask midpoint"
    elif last_value is not None and trade_at is not None:
        # Preserve the stale last and its real timestamp. The rule evaluator
        # will reject it through the unchanged 90-second freshness gate.
        price = last_value
        quote_at = trade_at
        price_basis = "last trade"
    else:
        raise RuntimeError(f"Tradier returned no timestamped {symbol} last trade or fresh valid BBO")
    bars: list[MarketBar] = []
    for raw in _bar_rows(bars_payload):
        if any(raw.get(key) is None for key in ("timestamp", "open", "high", "low", "close")):
            continue
        bars.append(MarketBar(
            timestamp=datetime.fromtimestamp(float(raw["timestamp"]), UTC),
            open=float(raw["open"]), high=float(raw["high"]), low=float(raw["low"]),
            close=float(raw["close"]), volume=int(raw["volume"]) if raw.get("volume") is not None else None,
            vwap=float(raw["vwap"]) if raw.get("vwap") is not None else None,
        ))
    return {"symbol": symbol, "price": price, "price_basis": price_basis,
            "quote_timestamp": quote_at,
            "bars": bars, "source": "Tradier production consolidated feed",
            "session": market_session(now), **freshness(quote_at, now)}


async def fetch_option_selection(app, setup: dict[str, Any], now: datetime) -> tuple[dict[str, Any] | None, str]:
    if market_session(now) != "regular":
        return None, "options market is closed"
    symbol = setup["symbol"]
    expirations = await _tradier_get(app, "/markets/options/expirations", {"symbol": symbol, "includeAllRoots": "true"})
    raw_dates = (expirations.get("expirations") or {}).get("date") or []
    if isinstance(raw_dates, str):
        raw_dates = [raw_dates]
    dates = sorted(_parse_date(value, "expiration") for value in raw_dates)
    today = now.astimezone(ET).date()
    valid = [value for value in dates if value >= today]
    if not valid:
        return None, "no current expiration is available"
    expiration = _choose_expiration(valid, setup, today)
    if expiration is None:
        return None, "no expiration matched the setup preference"
    chain = await _tradier_get(app, "/markets/options/chains", {
        "symbol": symbol, "expiration": expiration.isoformat(), "greeks": "true",
    })
    rows = (chain.get("options") or {}).get("option") or []
    if isinstance(rows, dict):
        rows = [rows]
    contracts = [item for raw in rows if (item := normalize_contract(raw, now)) is not None]
    if setup["strategy"] in {"calendar", "double_calendar"}:
        later = [item for item in valid if item > expiration]
        if not later:
            return None, "ENTRY TRIGGER HIT — STRIKES PENDING OPTIONS DATA"
        back_expiration = later[0]
        back_chain = await _tradier_get(app, "/markets/options/chains", {
            "symbol": symbol, "expiration": back_expiration.isoformat(), "greeks": "true",
        })
        back_rows = (back_chain.get("options") or {}).get("option") or []
        if isinstance(back_rows, dict):
            back_rows = [back_rows]
        back_contracts = [item for raw in back_rows if (item := normalize_contract(raw, now)) is not None]
        selected = select_calendar_structure(
            setup["strategy"], contracts, back_contracts, setup,
            expiration.isoformat(), back_expiration.isoformat(),
        )
    else:
        selected = select_option_structure(setup["strategy"], contracts, setup, expiration.isoformat())
    if selected is None:
        return None, "ENTRY TRIGGER HIT — STRIKES PENDING OPTIONS DATA"
    if symbol == "XSP":
        selected["settlement_note"] = "XSP is cash-settled; verify AM/PM settlement and last-trading-time for this expiration."
    if selected.get("liquidity_status") == "BLOCKED":
        return selected, "LIQUIDITY BLOCKED — no complete calendar passed execution-quality checks"
    return selected, "fresh"


def _choose_expiration(available: list[date], setup: dict[str, Any], today: date) -> date | None:
    exact = setup.get("target_expiration")
    if exact:
        try:
            requested = date.fromisoformat(str(exact))
        except ValueError:
            return None
        return requested if requested in available else None
    preference = str(setup.get("expiration_preference") or "").strip().upper()
    match = re.fullmatch(r"(\d+)\s*-\s*(\d+)\s*DTE", preference)
    if match:
        low, high = int(match.group(1)), int(match.group(2))
        candidates = [item for item in available if low <= (item - today).days <= high]
        if not candidates:
            return None
        midpoint = (low + high) / 2
        return min(candidates, key=lambda item: (abs((item - today).days - midpoint), item))
    return available[0] if available else None


def _display_et(value: Any) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return "unavailable"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(ET).strftime("%Y-%m-%d %I:%M:%S %p ET")


def _human_trigger(entry: dict[str, Any]) -> str:
    kind = entry.get("type")
    bars = int(entry.get("confirmation_bars", 2))
    if kind == "breakout_hold":
        return f"Break and hold above ${entry['breakout_level']:g} for {bars} completed 1-minute bar(s)."
    if kind == "breakout_retest":
        return f"Break above ${entry['breakout_level']:g}, retest it, then hold for {bars} completed 1-minute bar(s)."
    if kind == "support_hold":
        return f"Test support ${entry['support_low']:g}-${entry['support_high']:g} and hold it for {bars} completed 1-minute bar(s)."
    if kind == "failed_reclaim":
        return f"Fail to reclaim ${entry['reclaim_level']:g}, confirmed by {bars} completed 1-minute close(s) below it."
    if kind == "vwap_reclaim":
        return f"Reclaim VWAP and hold above it for {bars} completed 1-minute bar(s)."
    if kind == "opening_range_breakout":
        return f"Close above the ${entry['range_high']:g} opening-range high for {bars} completed 1-minute bar(s)."
    if kind == "opening_range_rejection":
        return f"Reject the ${entry['range_low']:g}-${entry['range_high']:g} opening range and close below it for {bars} bar(s)."
    if kind == "opening_range_hold":
        return f"Test both sides of ${entry['range_low']:g}-${entry['range_high']:g}, then hold inside for {bars} completed 1-minute bar(s)."
    return "NOT DEFINED — plan did not provide a supported entry trigger."


def _human_invalidation(rule: dict[str, Any] | None) -> str:
    rule = rule or {}
    if rule.get("type") == "close_below" and rule.get("level") is not None:
        return f"Invalid on a completed 1-minute close below ${float(rule['level']):g}."
    if rule.get("type") == "close_above" and rule.get("level") is not None:
        return f"Invalid on a completed 1-minute close above ${float(rule['level']):g}."
    if rule.get("type") == "time" and rule.get("time"):
        return f"Invalid after {rule['time']}."
    return "NOT DEFINED — plan did not provide an actionable invalidation."


def _defined_or_warning(value: Any, label: str) -> str:
    if value is None or value == "" or value == []:
        return f"NOT DEFINED — plan did not provide {label}."
    if isinstance(value, dict):
        return "; ".join(
            f"{str(key).replace('_', ' ')}: {_defined_or_warning(item, label)}"
            for key, item in value.items()
        )
    if isinstance(value, list):
        return "; ".join(_defined_or_warning(item, label) for item in value)
    return str(value)


def build_alert_embed(setup: dict[str, Any], prior_state: str, result: RuleResult,
                      market: dict[str, Any], option_selection: dict[str, Any] | None,
                      options_reason: str | None, now: datetime) -> dict[str, Any]:
    strategy = setup["strategy"].replace("_", " ").upper()
    unavailable = result.state == "DATA_UNAVAILABLE"
    liquidity_blocked = result.state == "LIQUIDITY_BLOCKED"
    if unavailable:
        title = f"NO TRADE — {setup['symbol']} DATA UNAVAILABLE"
        action = (
            f"NO TRADE. {result.reason} Market data must be 90 seconds old or less. "
            "Monitoring resumes automatically when fresh data returns."
        )
    elif liquidity_blocked:
        title = f"NO TRADE — {setup['symbol']} LIQUIDITY BLOCKED"
        action = f"NO TRADE. The underlying trigger passed, but the observed option structure failed liquidity checks: {result.reason}"
    elif result.state == "ENTRY_READY":
        title = f"ENTRY READY — {setup['symbol']} {strategy}"
        action = "Review the qualified alert and defined risk; advisory only—no order was routed."
    elif result.state == "INVALIDATED":
        title = f"INVALIDATED — {setup['symbol']} {strategy}"
        action = f"NO TRADE / EXIT REVIEW. {result.reason}"
    else:
        title = f"{result.state.replace('_', ' ')} — {setup['symbol']} {strategy}"
        action = result.reason

    price = f"${market['price']:.2f}" if market.get("price") is not None else "unavailable"
    basis = market.get("price_basis") or "price basis unavailable"
    fields = [
        {"name": "Action", "value": action[:1024], "inline": False},
        {"name": "Setup", "value": (
            f"{setup['symbol']} | {strategy} | {setup['thesis'].upper()} | "
            f"{prior_state} → {result.state} | underlying {price} ({basis})"
        )[:1024], "inline": False},
        {"name": "Entry rule", "value": _human_trigger(setup.get("entry") or {}), "inline": False},
        {"name": "Decision evidence", "value": result.reason[:1024], "inline": False},
        {"name": "Invalidation", "value": _human_invalidation(setup.get("invalidation")), "inline": False},
        {"name": "Profit target", "value": _defined_or_warning(
            setup.get("profit_taking_framework"), "a profit target or framework"
        )[:1024], "inline": False},
        {"name": "Main risk", "value": _defined_or_warning(
            setup.get("main_risks"), "the main setup risk"
        )[:1024], "inline": False},
        {"name": "Underlying data", "value": (
            f"{market.get('source') or 'source unavailable'} | session {market.get('session') or 'unavailable'} | "
            f"exchange {_display_et(market.get('exchange_timestamp'))} | "
            f"retrieved {_display_et(market.get('retrieval_timestamp'))} | "
            f"age {market.get('age_seconds') if market.get('age_seconds') is not None else 'unavailable'}s"
        )[:1024], "inline": False},
    ]
    if option_selection:
        leg_lines, greek_lines, provenance = [], [], []
        for leg in option_selection.get("legs", []):
            expiration = leg.get("expiration") or option_selection.get("expiration")
            leg_lines.append(
                f"{leg['action'].upper()} {leg['right']} ${leg['strike']:g} exp {expiration} | "
                f"bid/ask {leg['bid']:.2f}/{leg['ask']:.2f} | Δ {leg['delta']:.3f}"
            )
            if leg.get("relative_spread") is not None:
                leg_lines[-1] += (
                    f" | midpoint {leg['midpoint']:.2f} | spread {leg['relative_spread']:.1%} | "
                    f"OI {leg.get('open_interest', 'unavailable')} | vol {leg.get('volume', 'unavailable')}"
                )
            greek_lines.append(
                f"{leg['right']} ${leg['strike']:g}: Γ {float(leg['gamma']):.4f}, "
                f"Θ {float(leg['theta']):.4f}, Vega {float(leg['vega']):.4f}, IV {float(leg['iv']):.1%}"
            )
            provenance.append(
                f"{leg['right']} ${leg['strike']:g}: exchange {_display_et(leg.get('exchange_timestamp'))}, "
                f"retrieved {_display_et(leg.get('retrieval_timestamp'))}, age {leg.get('age_seconds')}s"
            )
        price_name = "Natural credit" if "natural_credit" in option_selection else "Natural debit"
        option_price = option_selection.get("natural_credit", option_selection.get("natural_debit"))
        width = option_selection.get("width")
        max_risk = option_selection.get("max_risk")
        cost_text = f"{price_name} ${option_price:.2f}"
        if width is not None:
            cost_text += f" | width ${float(width):g}"
        cost_text += (f" | max risk ${float(max_risk):.2f}" if max_risk is not None
                      else " | max risk NOT DEFINED")
        leg_heading = ("Observed option legs — NOT EXECUTABLE"
                       if liquidity_blocked else "Option legs")
        fields.extend([
            {"name": leg_heading, "value": "\n".join(leg_lines)[:1024], "inline": False},
            {"name": "Greeks / IV", "value": "\n".join(greek_lines)[:1024], "inline": False},
            {"name": "Options data", "value": (
                f"{option_selection.get('source') or 'source unavailable'} | session regular | "
                + "; ".join(provenance)
            )[:1024], "inline": False},
        ])
        if liquidity_blocked:
            midpoint = option_selection.get("composite_midpoint_debit")
            natural = option_selection.get("natural_debit")
            gap = option_selection.get("natural_midpoint_gap_ratio")
            thresholds = option_selection.get("liquidity_thresholds") or {}
            failures = option_selection.get("failed_checks") or []
            fields.extend([
                {"name": "Observed pricing — NOT EXECUTABLE", "value": (
                    f"composite midpoint debit ${midpoint:.2f} | natural debit ${natural:.2f} | "
                    f"natural-vs-mid gap {gap:.1%}" if gap is not None
                    else f"composite midpoint debit ${midpoint:.2f} | natural debit ${natural:.2f} | gap unavailable"
                ), "inline": False},
                {"name": "Liquidity failures", "value": "; ".join(failures)[:1024], "inline": False},
                {"name": "Liquidity thresholds", "value": (
                    f"max leg spread {thresholds.get('maximum_relative_leg_spread', 0):.1%} | "
                    f"max natural-mid gap {thresholds.get('maximum_natural_midpoint_gap_ratio', 0):.1%} | "
                    f"activity per leg OI ≥ {thresholds.get('minimum_calendar_open_interest')} "
                    f"OR volume ≥ {thresholds.get('minimum_calendar_volume')}"
                ), "inline": False},
            ])
        else:
            fields.append({"name": "Defined cost / risk", "value": cost_text, "inline": False})
        if option_selection.get("settlement_note"):
            fields.append({"name": "Settlement", "value": option_selection["settlement_note"][:1024], "inline": False})
    elif result.state == "ENTRY_READY":
        fields.append({
            "name": "Options",
            "value": (options_reason or "ENTRY TRIGGER HIT — STRIKES PENDING OPTIONS DATA")[:1024],
            "inline": False,
        })
    return {
        "title": title,
        "description": "Alert only. No order preview, routing, modification, or cancellation.",
        "color": 0x9CA3AF if (unavailable or liquidity_blocked) else (0x34D399 if result.state == "ENTRY_READY" else 0xF87171),
        "fields": fields, "timestamp": now.isoformat(),
        "footer": {"text": "Render Intraday Options Watch | alert only | no order routing"},
    }


def _return_from_bars(market: dict[str, Any]) -> float | None:
    bars = market.get("bars") or []
    if len(bars) < 2 or not bars[0].close:
        return None
    return bars[-1].close / bars[0].close - 1.0


def _setup_contexts(setup: dict[str, Any], market: dict[str, Any],
                    cache: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, float]]:
    relative_rule = setup.get("relative_strength") or (setup.get("confirmation_rule") or {}).get("relative_strength")
    relative = None
    if relative_rule:
        reference = str(relative_rule.get("reference_symbol") or "SPY").upper()
        reference_market = cache.get(reference)
        relative = {
            "symbol_return": _return_from_bars(market),
            "reference_return": _return_from_bars(reference_market) if reference_market else None,
        }
    confirmations = {
        symbol: float(item["price"]) for symbol, item in cache.items()
        if item.get("price") is not None
    }
    return relative, confirmations


async def run_intraday_cycle(app, *, now: datetime | None = None) -> dict[str, Any]:
    """Evaluate persisted setups once. Called only by the dedicated worker."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    today = now.astimezone(ET).date()
    poll = max(30, int(os.getenv("INTRADAY_WATCH_POLL_SECONDS", "60")))
    status: dict[str, Any] = {
        "worker_heartbeat": now.isoformat(), "worker_healthy": True,
        "poll_interval_seconds": poll, "current_trading_date": today.isoformat(),
        "core_symbols": list(CORE_SYMBOLS), "confirmation_symbols": list(CONFIRMATION_SYMBOLS),
        "trading_volatility_universe_count": None, "selected_daily_symbols": [],
        "active_setup_count": 0, "per_symbol_state": {}, "last_market_data_timestamp": None,
        "last_options_data_timestamp": None, "last_alert": None,
        "data_source": "Tradier production consolidated feed", "data_freshness": {},
        "discord_configured": bool(os.getenv("DISCORD_WEBHOOK_URL", "").strip()),
        "plan_ingestion_timestamp": None, "plan_hash": None,
        "plan_parity": {"valid": False, "reason": "no plan ingested"},
        "errors": [],
    }
    if SessionLocal is None:
        status.update(worker_healthy=False, errors=["DATABASE_URL is not configured"])
        return status
    db = SessionLocal()
    try:
        db.query(IntradaySetup).filter(IntradaySetup.trading_date < today).update({"active": 0, "state": "EXPIRED"})
        watchlist = db.get(IntradaySelectedWatchlist, today)
        if watchlist:
            status["selected_daily_symbols"] = json.loads(watchlist.symbols_json)
        else:
            status["errors"].append("No selected morning watchlist; core symbols only. Trading Volatility is discovery-only and no random fallback was chosen.")
        legacy = db.get(QQQWatchRuntimeStatus, "qqq-retest")
        if legacy:
            try:
                tv = json.loads(legacy.payload_json).get("trading_volatility") or {}
                status["trading_volatility_universe_count"] = tv.get("universe_count")
            except (json.JSONDecodeError, TypeError):
                pass
        rows = db.query(IntradaySetup).filter(IntradaySetup.trading_date == today, IntradaySetup.active == 1).all()
        status["active_setup_count"] = len(rows)
        plan_row = db.get(IntradayTradePlan, today)
        if plan_row:
            try:
                plan_payload = json.loads(plan_row.payload_json)
                expected_symbols = set(plan_payload.get("symbols") or [])
                expected_ids = {
                    item.get("setup_id") for item in plan_payload.get("setups") or []
                }
                actual_symbols = set(status["selected_daily_symbols"])
                actual_ids = {row.setup_id for row in rows}
                symbols_match = actual_symbols == expected_symbols
                setups_match = actual_ids == expected_ids
                status["plan_ingestion_timestamp"] = plan_payload.get("ingested_at")
                status["plan_hash"] = plan_payload.get("plan_hash")
                status["plan_parity"] = {
                    "valid": symbols_match and setups_match,
                    "selected_symbols_match": symbols_match,
                    "active_setups_match": setups_match,
                    "expected_symbol_count": len(expected_symbols),
                    "registered_symbol_count": len(actual_symbols),
                    "expected_setup_count": len(expected_ids),
                    "registered_setup_count": len(actual_ids),
                }
            except (json.JSONDecodeError, TypeError) as exc:
                status["errors"].append(f"morning plan metadata: {exc}")
        market_cache: dict[str, dict[str, Any]] = {}
        extra_confirmations: set[str] = set()
        for row in rows:
            raw_setup = json.loads(row.payload_json)
            relative_rule = raw_setup.get("relative_strength") or (raw_setup.get("confirmation_rule") or {}).get("relative_strength")
            if relative_rule:
                extra_confirmations.add(_normalize_symbol(relative_rule.get("reference_symbol") or "SPY"))
            for condition in (raw_setup.get("confirmation_rule") or {}).get("inputs") or []:
                extra_confirmations.add(_normalize_symbol(condition.get("symbol")))
        selected_symbols = tuple(status["selected_daily_symbols"])
        symbols_to_fetch = list(dict.fromkeys(
            CORE_SYMBOLS + CONFIRMATION_SYMBOLS + selected_symbols
            + tuple(sorted(extra_confirmations))
        ))
        for symbol in symbols_to_fetch if market_session(now) != "closed" else []:
            try:
                market_cache[symbol] = await fetch_symbol_market(app, symbol, now)
                item = market_cache[symbol]
                status["data_freshness"][symbol] = {
                    "source": item["source"], "session": item["session"],
                    "exchange_timestamp": item["exchange_timestamp"],
                    "retrieval_timestamp": item["retrieval_timestamp"],
                    "age_seconds": item["age_seconds"], "fresh": item["fresh"],
                }
            except Exception as exc:  # noqa: BLE001
                status["errors"].append(f"{symbol}: {exc}")
                status["data_freshness"][symbol] = {
                    "source": "Tradier production consolidated feed",
                    "session": market_session(now), "exchange_timestamp": None,
                    "retrieval_timestamp": now.isoformat(), "age_seconds": None,
                    "fresh": False, "error": str(exc),
                }
        setup_symbols = {row.symbol for row in rows}
        attempted_alerts: set[str] = set()
        for symbol in symbols_to_fetch:
            if symbol not in setup_symbols:
                available = symbol in market_cache
                status["per_symbol_state"][symbol] = [{
                    "setup_id": None,
                    "state": "NO_ACTIVE_SETUP" if available else "DATA_UNAVAILABLE",
                    "reason": ("Fresh market data monitored; no date-bound setup was supplied."
                               if available else "Fresh market data unavailable."),
                    "option_strike_selection": None,
                }]
        for row in rows:
            setup = json.loads(row.payload_json)
            setup["setup_state"] = row.state
            prior = row.state
            if market_session(now) not in setup.get("sessions", ["regular"]):
                result = RuleResult("WAIT", "Setup is outside its selected market session.")
                market = {"symbol": row.symbol, "price": None, "source": "Tradier",
                          "session": market_session(now), "exchange_timestamp": None,
                          "retrieval_timestamp": now.isoformat(), "age_seconds": None}
            else:
                result = None
            try:
                if result is None:
                    market = market_cache.get(row.symbol)
                    if market is None:
                        market = await fetch_symbol_market(app, row.symbol, now)
                        market_cache[row.symbol] = market
                    relative_context, confirmation_context = _setup_contexts(
                        setup, market, market_cache
                    )
                    result = evaluate_setup(setup, market["bars"], now,
                                            quote_timestamp=market["quote_timestamp"],
                                            quote_price=market["price"],
                                            relative_context=relative_context,
                                            confirmation_context=confirmation_context)
                    row.last_market_timestamp = market["quote_timestamp"]
                    status["last_market_data_timestamp"] = market["exchange_timestamp"]
                    status["data_freshness"][row.symbol] = {
                        "source": market["source"], "session": market["session"],
                        "exchange_timestamp": market["exchange_timestamp"],
                        "retrieval_timestamp": market["retrieval_timestamp"],
                        "age_seconds": market["age_seconds"], "fresh": market["fresh"],
                    }
            except Exception as exc:  # noqa: BLE001
                market = {"symbol": row.symbol, "price": None, "source": "Tradier",
                          "session": market_session(now), "exchange_timestamp": None,
                          "retrieval_timestamp": now.isoformat(), "age_seconds": None}
                result = RuleResult("DATA_UNAVAILABLE", str(exc))
                status["errors"].append(f"{row.symbol}: {exc}")
            option_selection = None
            options_reason = None
            if result.state == "ENTRY_READY":
                try:
                    enriched = dict(setup, current_price=market["price"])
                    option_selection, options_reason = await fetch_option_selection(app, enriched, now)
                    if option_selection:
                        row.option_selection_json = _json(option_selection)
                        row.last_options_timestamp = now
                        status["last_options_data_timestamp"] = now.isoformat()
                        result = apply_option_liquidity_state(result, option_selection)
                except Exception as exc:  # noqa: BLE001
                    options_reason = f"ENTRY TRIGGER HIT — STRIKES PENDING OPTIONS DATA ({exc})"
            meaningful = (
                result.state != prior and (
                    result.state in {"ENTRY_READY", "INVALIDATED", "LIQUIDITY_BLOCKED"}
                    or (result.state == "DATA_UNAVAILABLE" and prior == "NEAR_TRIGGER")
                )
            )
            if result.state != prior:
                row.state = result.state
                row.last_transition_at = now
                setup["setup_state"] = result.state
                row.payload_json = _json(setup)
                logger.info("[IntradayWatch] %s %s -> %s", row.symbol, prior, result.state)
            status["per_symbol_state"].setdefault(row.symbol, []).append({
                "setup_id": row.setup_id, "state": result.state,
                "reason": result.reason, "option_strike_selection": option_selection,
            })
            if meaningful:
                embed = build_alert_embed(setup, prior, result, market, option_selection, options_reason, now)
                event_key = claim_alert(db, row.setup_id, today, result.state, now, embed)
                if event_key:
                    attempted_alerts.add(event_key)
                    from . import _send_webhook_sync
                    webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
                    posted = bool(webhook) and await asyncio.to_thread(_send_webhook_sync, embed, webhook)
                    if posted:
                        alert_row = db.get(IntradayAlertDedup, event_key)
                        if alert_row:
                            alert_row.posted_at = now
                        logger.info("[IntradayWatch] Discord posted setup_id=%s", row.setup_id)
                    status["last_alert"] = {"setup_id": row.setup_id, "state": result.state,
                                            "transition_at": now.isoformat(), "posted": posted}
        # A failed webhook stays durable and is retried after restarts. Posted
        # transitions are never sent again.
        webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
        pending = db.query(IntradayAlertDedup).filter(
            IntradayAlertDedup.posted_at.is_(None),
            IntradayAlertDedup.trading_date == today,
        ).all()
        if webhook:
            from . import _send_webhook_sync
            for alert in pending:
                if alert.event_key in attempted_alerts or not alert.payload_json:
                    continue
                try:
                    embed = json.loads(alert.payload_json)
                    posted = await asyncio.to_thread(_send_webhook_sync, embed, webhook)
                except (json.JSONDecodeError, TypeError) as exc:
                    status["errors"].append(f"pending alert {alert.event_key}: {exc}")
                    continue
                if posted:
                    alert.posted_at = now
                    status["last_alert"] = {
                        "setup_id": alert.setup_id, "state": alert.state,
                        "transition_at": alert.transition_at.isoformat(),
                        "posted": True, "retried": True,
                    }
                    logger.info("[IntradayWatch] Discord retry posted setup_id=%s", alert.setup_id)
        db.commit()
        runtime = db.get(IntradayWatchRuntimeStatus, "intraday-watch")
        if runtime is None:
            runtime = IntradayWatchRuntimeStatus(watcher_id="intraday-watch",
                                                 payload_json=_json(status), heartbeat_at=now)
            db.add(runtime)
        else:
            runtime.payload_json = _json(status)
            runtime.heartbeat_at = now
        db.commit()
        logger.info("[IntradayWatch] cycle completed setups=%d", len(rows))
        return status
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
