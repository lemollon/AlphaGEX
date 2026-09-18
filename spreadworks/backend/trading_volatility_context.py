"""Cached TradingVolatility context for the cloud market watcher.

TradingVolatility is used for two descriptive inputs only:

* its current liquid, optionable ticker roster; and
* timestamped options-positioning context for the actively configured setup.

It is deliberately not used as the one-minute price feed and its GEX fields do
not create or change a directional alert.  Missing, malformed, or stale vendor
data is reported as unavailable rather than inferred.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any


UTC = timezone.utc
DEFAULT_BASE_URL = "https://stocks.tradingvolatility.net/api/v2"

_CACHE: dict[str, Any] = {
    "checked_at": None,
    "last_success_at": None,
    "payload": None,
}


def _token() -> str:
    return (
        os.getenv("TRADING_VOLATILITY_API_TOKEN", "").strip()
        or os.getenv("TRADING_VOLATILITY_API_KEY", "").strip()
    )


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


def _age_seconds(now: datetime, timestamp: datetime) -> float:
    return max(0.0, (now.astimezone(UTC) - timestamp.astimezone(UTC)).total_seconds())


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw > 10_000_000_000:
            raw /= 1000.0
        try:
            return datetime.fromtimestamp(raw, UTC)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.replace(".", "", 1).isdigit():
        return _parse_timestamp(float(text))
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


async def _get(client: Any, path: str, params: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    if not token:
        raise RuntimeError("TradingVolatility credentials are not configured")
    base_url = (
        os.getenv("TRADING_VOLATILITY_V2_BASE_URL", "").strip()
        or DEFAULT_BASE_URL
    )
    response = await client.get(
        f"{base_url.rstrip('/')}{path}",
        params=params,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"TradingVolatility {path} returned {response.status_code}: "
            f"{response.text[:160]}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"TradingVolatility {path} returned a non-object payload")
    return payload


def _data(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("data", payload)
    return value if isinstance(value, dict) else {}


def _normalize_top_setup(item: dict[str, Any]) -> dict[str, Any]:
    """Keep TradingVolatility's trader-facing ranking fields without leaking unrelated payload data."""
    recommendation = item.get("trade_recommendation")
    source = dict(item)
    if isinstance(recommendation, dict):
        source.update(recommendation)

    ticker = source.get("ticker") or source.get("symbol")
    score = source.get("opportunity_score")
    try:
        normalized_score = float(score) if score is not None else None
    except (TypeError, ValueError):
        normalized_score = None

    structures = source.get("structures")
    if structures is None:
        structures = []
    elif not isinstance(structures, list):
        structures = [structures]

    caution_flags = source.get("caution_flags")
    if caution_flags is None:
        caution_flags = []
    elif not isinstance(caution_flags, list):
        caution_flags = [caution_flags]

    return {
        "ticker": str(ticker).upper() if ticker else None,
        "opportunity_score": normalized_score,
        "opportunity_tier": source.get("opportunity_tier"),
        "trade_bias": source.get("trade_bias"),
        "trade_type": source.get("trade_type"),
        "direction": source.get("direction"),
        "structures": structures,
        "entry_trigger": source.get("entry_trigger"),
        "stop_description": source.get("stop_description"),
        "target_description": source.get("target_description"),
        "risk": source.get("risk"),
        "caution_flags": caution_flags,
        "agent_summary": source.get("agent_summary"),
    }


def _walls(points: list[dict[str, Any]], spot: float, side: str) -> list[dict[str, float]]:
    if side == "call":
        candidates = [
            row for row in points
            if row.get("strike") is not None and row.get("net") is not None
            and float(row["strike"]) > spot
        ]
        candidates.sort(key=lambda row: float(row["net"]), reverse=True)
    else:
        candidates = [
            row for row in points
            if row.get("strike") is not None and row.get("net") is not None
            and float(row["strike"]) < spot
        ]
        candidates.sort(key=lambda row: float(row["net"]))
    return [
        {"strike": float(row["strike"]), "net_gex": float(row["net"])}
        for row in candidates[:3]
    ]


def _build_payload(
    universe_payload: dict[str, Any],
    curve_payload: dict[str, Any],
    levels_payload: dict[str, Any],
    *,
    symbol: str,
    retrieved_at: datetime,
    max_age_seconds: float,
) -> dict[str, Any]:
    universe_items = _data(universe_payload).get("items")
    if not isinstance(universe_items, list):
        raise RuntimeError("TradingVolatility /top-setups returned no items list")
    top_setups = [
        _normalize_top_setup(item)
        for item in universe_items
        if isinstance(item, dict)
    ]
    top_setups = [item for item in top_setups if item.get("ticker")]
    # TradingVolatility documents /top-setups as ranked by opportunity_score.
    # Preserve that order when scores are absent, but sort deterministically
    # when scores are present so downstream consumers can use rank directly.
    if any(item.get("opportunity_score") is not None for item in top_setups):
        top_setups.sort(
            key=lambda item: (
                item.get("opportunity_score") is not None,
                item.get("opportunity_score") if item.get("opportunity_score") is not None else float("-inf"),
            ),
            reverse=True,
        )
    for rank, item in enumerate(top_setups, start=1):
        item["rank"] = rank

    symbols = sorted({item["ticker"] for item in top_setups})
    if not symbols:
        raise RuntimeError("TradingVolatility liquid-options universe was empty")

    curve = _data(curve_payload)
    points = curve.get("points")
    spot = curve.get("price")
    if not isinstance(points, list) or spot is None:
        raise RuntimeError(f"TradingVolatility returned no positioning curve for {symbol}")
    spot = float(spot)
    totals = curve.get("totals") if isinstance(curve.get("totals"), dict) else {}
    vendor_at = _parse_timestamp(curve.get("asof"))
    age = _age_seconds(retrieved_at, vendor_at) if vendor_at else None
    context_fresh = age is not None and age <= max_age_seconds

    raw_levels = _data(levels_payload).get("levels")
    raw_levels = raw_levels if isinstance(raw_levels, list) else []
    levels = {
        item.get("name"): item.get("price")
        for item in raw_levels
        if isinstance(item, dict) and item.get("name") and item.get("price") is not None
    }
    plus_one = levels.get("plus_1s_1d")
    minus_one = levels.get("minus_1s_1d")
    expected_move = None
    if plus_one is not None and minus_one is not None:
        expected_move = round((float(plus_one) - float(minus_one)) / 2.0, 2)

    flip = totals.get("gex_flip_price")
    if flip is None:
        regime = None
    elif spot > float(flip):
        regime = "positive"
    elif spot < float(flip):
        regime = "negative"
    else:
        regime = "neutral"

    return {
        "configured": True,
        "available": True,
        "source": "TradingVolatility v2 API",
        "role": (
            "Liquid-options universe and descriptive positioning context; "
            "not the one-minute price source or a directional signal."
        ),
        "retrieval_timestamp": _iso(retrieved_at),
        "last_success_at": _iso(retrieved_at),
        "universe_count": len(symbols),
        "symbols": symbols,
        "top_setups": top_setups,
        "top_setup_count": len(top_setups),
        "symbol_context": {
            "symbol": symbol,
            "covered": symbol in symbols,
            "vendor_timestamp": _iso(vendor_at),
            "age_seconds": round(age, 1) if age is not None else None,
            "fresh": context_fresh,
            "freshness_limit_seconds": max_age_seconds,
            "reference_spot": spot,
            "gamma_regime": regime,
            "gamma_flip_price": float(flip) if flip is not None else None,
            "expected_move_1d_dollars": expected_move,
            "call_walls": _walls(points, spot, "call"),
            "put_walls": _walls(points, spot, "put"),
        },
        "last_error": None,
    }


def _unavailable(
    *,
    configured: bool,
    checked_at: datetime,
    error: str,
) -> dict[str, Any]:
    return {
        "configured": configured,
        "available": False,
        "source": "TradingVolatility v2 API",
        "role": (
            "Liquid-options universe and descriptive positioning context; "
            "not the one-minute price source or a directional signal."
        ),
        "retrieval_timestamp": _iso(checked_at),
        "last_success_at": _iso(_CACHE.get("last_success_at")),
        "universe_count": None,
        "symbols": [],
        "top_setups": [],
        "top_setup_count": 0,
        "symbol_context": None,
        "last_error": error,
    }


async def get_trading_volatility_context(
    client: Any,
    *,
    symbol: str,
    retrieved_at: datetime,
    refresh_seconds: int,
    max_age_seconds: float,
    universe_limit: int,
) -> dict[str, Any]:
    """Return cached current context; refresh failures never reuse stale data."""
    retrieved_at = retrieved_at.astimezone(UTC)
    if not _token():
        return _unavailable(
            configured=False,
            checked_at=retrieved_at,
            error="TradingVolatility credentials are not configured",
        )

    checked_at = _CACHE.get("checked_at")
    cached = _CACHE.get("payload")
    if isinstance(checked_at, datetime) and isinstance(cached, dict):
        if _age_seconds(retrieved_at, checked_at) < refresh_seconds:
            result = dict(cached)
            result["cache_age_seconds"] = round(_age_seconds(retrieved_at, checked_at), 1)
            return result

    _CACHE["checked_at"] = retrieved_at
    symbol = symbol.upper()
    try:
        universe_payload, curve_payload, levels_payload = await asyncio.gather(
            _get(client, "/top-setups", {"limit": universe_limit, "min_score": 0}),
            _get(client, f"/tickers/{symbol}/curves/gex_by_strike", {"exp": "nearest"}),
            _get(client, f"/tickers/{symbol}/levels", {}),
        )
        payload = _build_payload(
            universe_payload,
            curve_payload,
            levels_payload,
            symbol=symbol,
            retrieved_at=retrieved_at,
            max_age_seconds=max_age_seconds,
        )
        _CACHE.update(last_success_at=retrieved_at, payload=payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        failure = _unavailable(
            configured=True,
            checked_at=retrieved_at,
            error=str(exc),
        )
        _CACHE["payload"] = failure
        return failure
