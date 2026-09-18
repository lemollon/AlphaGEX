"""Speculative OTM contract selector.

Read-only advisory endpoint that combines TradingVolatility setup/volatility
context with fresh Tradier chains. It never routes or previews orders.
"""
from __future__ import annotations

import asyncio
import math
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from .intraday_watch import normalize_contract
from .routes import _tradier_get
from .trading_volatility_context import _data as _tv_data, _get as _tv_get

router = APIRouter(
    prefix="/api/spreadworks/speculative-contracts",
    tags=["Speculative Contracts"],
)

UTC = timezone.utc
CATEGORY_BANDS = {
    "best_contract": (0.20, 0.35),
    "aggressive_otm": (0.10, 0.20),
    "lotto": (0.05, 0.12),
}


def _coerce_float(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _walk_for_number(payload: Any, keys: tuple[str, ...]) -> float | None:
    if isinstance(payload, dict):
        for key in keys:
            if key in payload:
                found = _coerce_float(payload.get(key))
                if found is not None:
                    return found
        for value in payload.values():
            found = _walk_for_number(value, keys)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _walk_for_number(value, keys)
            if found is not None:
                return found
    return None


def _trade_setup(payload: dict[str, Any]) -> dict[str, Any]:
    data = _tv_data(payload)
    for key in ("trade_setup", "trade_recommendation", "recommendation"):
        value = data.get(key)
        if isinstance(value, dict):
            merged = dict(data)
            merged.update(value)
            return merged
    return data


def _direction(setup: dict[str, Any]) -> tuple[str | None, str | None]:
    raw = str(
        setup.get("direction")
        or setup.get("recommended_direction")
        or setup.get("trade_direction")
        or ""
    ).lower()
    bias = str(setup.get("trade_bias") or "").lower()
    if raw in {"long", "bullish", "up"} or bias.startswith("long"):
        return "long", "C"
    if raw in {"short", "bearish", "down"} or bias.startswith("short"):
        return "short", "P"
    return None, None


def _expected_move(levels_payload: dict[str, Any], market_structure: dict[str, Any] | None = None) -> dict[str, Any]:
    """Prefer the 1-week surface for next-week contract selection; retain 1-day context."""
    levels = _tv_data(levels_payload).get("levels")
    levels = levels if isinstance(levels, list) else []
    by_name = {
        row.get("name"): _coerce_float(row.get("price"))
        for row in levels
        if isinstance(row, dict) and row.get("name")
    }
    structure = _tv_data(market_structure or {})
    key_levels = structure.get("key_levels") if isinstance(structure.get("key_levels"), dict) else {}

    upper_1w = _coerce_float(key_levels.get("plus_1sigma_1w"))
    lower_1w = _coerce_float(key_levels.get("minus_1sigma_1w"))
    upper_1d = _coerce_float(key_levels.get("plus_1sigma_1d")) or by_name.get("plus_1s_1d")
    lower_1d = _coerce_float(key_levels.get("minus_1sigma_1d")) or by_name.get("minus_1s_1d")

    dollars_1w = round((upper_1w - lower_1w) / 2.0, 4) if upper_1w is not None and lower_1w is not None else None
    dollars_1d = round((upper_1d - lower_1d) / 2.0, 4) if upper_1d is not None and lower_1d is not None else None
    return {
        "preferred_horizon": "1w" if dollars_1w is not None else "1d",
        "dollars": dollars_1w if dollars_1w is not None else dollars_1d,
        "one_week": {"lower": lower_1w, "upper": upper_1w, "dollars": dollars_1w},
        "one_day": {"lower": lower_1d, "upper": upper_1d, "dollars": dollars_1d},
    }


def _gamma_expiration_context(payload: dict[str, Any]) -> dict[str, Any]:
    data = _tv_data(payload)
    points = data.get("points")
    if not isinstance(points, list):
        return {"available": False, "dominant_bucket": None, "bucket_abs_gamma": {}}
    buckets = ("nearest", "first_weekly", "first_monthly", "all_other_expiries")
    totals = {bucket: 0.0 for bucket in buckets}
    seen = False
    for point in points:
        if not isinstance(point, dict):
            continue
        for bucket in buckets:
            value = _coerce_float(point.get(bucket))
            if value is not None:
                totals[bucket] += abs(value)
                seen = True
    if not seen:
        return {"available": False, "dominant_bucket": None, "bucket_abs_gamma": {}}
    dominant = max(totals, key=totals.get)
    return {
        "available": True,
        "dominant_bucket": dominant,
        "bucket_abs_gamma": {key: round(value, 2) for key, value in totals.items()},
    }


def _expiration_dates(payload: dict[str, Any], today: date, min_dte: int, max_dte: int) -> list[str]:
    raw = (payload.get("expirations") or {}).get("date") or []
    if isinstance(raw, str):
        raw = [raw]
    selected: list[str] = []
    for value in raw:
        try:
            exp = date.fromisoformat(str(value))
        except ValueError:
            continue
        dte = (exp - today).days
        if min_dte <= dte <= max_dte:
            selected.append(exp.isoformat())
    return selected[:4]


def _relative_spread(contract: dict[str, Any]) -> float:
    bid, ask = float(contract["bid"]), float(contract["ask"])
    midpoint = (bid + ask) / 2.0
    return (ask - bid) / midpoint if midpoint > 0 else float("inf")


def _liquidity_score(contract: dict[str, Any]) -> float:
    oi = max(0, int(contract.get("open_interest") or 0))
    volume = max(0, int(contract.get("volume") or 0))
    oi_component = min(10.0, math.log10(oi + 1) * 2.5)
    vol_component = min(5.0, math.log10(volume + 1) * 1.5)
    return oi_component + vol_component


def _score_contract(
    contract: dict[str, Any],
    *,
    band: tuple[float, float],
    opportunity_score: float | None,
    iv_rank: float | None,
    expected_move: float | None,
    spot: float,
    dte: int | None = None,
    speculative_interest: float | None = None,
) -> tuple[float, dict[str, float]]:
    delta = abs(float(contract["delta"]))
    midpoint = sum(band) / 2.0
    half_width = max((band[1] - band[0]) / 2.0, 0.01)
    delta_score = max(0.0, 20.0 * (1.0 - abs(delta - midpoint) / half_width))

    rel_spread = _relative_spread(contract)
    spread_score = max(0.0, 20.0 * (1.0 - rel_spread / 0.25))
    liquidity_score = _liquidity_score(contract)

    vendor_score = max(0.0, min(25.0, (opportunity_score or 0.0) * 2.5))

    strike_distance = abs(float(contract["strike"]) - spot)
    if expected_move and expected_move > 0:
        sigma = strike_distance / expected_move
        if sigma <= 0.75:
            move_score = 10.0
        elif sigma <= 1.0:
            move_score = 8.0
        elif sigma <= 1.5:
            move_score = 4.0
        else:
            move_score = 1.0
    else:
        move_score = 0.0

    if iv_rank is None:
        iv_score = 5.0
    elif iv_rank <= 25:
        iv_score = 10.0
    elif iv_rank <= 50:
        iv_score = 7.0
    elif iv_rank <= 70:
        iv_score = 4.0
    else:
        iv_score = 1.0

    # For next-week long premium, 7-12 DTE balances convexity with some theta runway.
    if dte is None:
        expiration_score = 0.0
    elif 7 <= dte <= 12:
        expiration_score = 5.0
    elif 5 <= dte <= 14:
        expiration_score = 3.0
    else:
        expiration_score = 1.0

    speculation_score = 0.0
    if speculative_interest is not None:
        speculation_score = max(0.0, min(5.0, speculative_interest * 5.0))

    parts = {
        "tv_opportunity": round(vendor_score, 2),
        "delta_fit": round(delta_score, 2),
        "spread_quality": round(spread_score, 2),
        "liquidity": round(liquidity_score, 2),
        "expected_move_fit": round(move_score, 2),
        "iv_rank_fit": round(iv_score, 2),
        "expiration_fit": round(expiration_score, 2),
        "speculative_interest": round(speculation_score, 2),
    }
    return round(sum(parts.values()), 2), parts


def _choose_candidate(
    contracts: list[dict[str, Any]],
    *,
    right: str,
    spot: float,
    band: tuple[float, float],
    opportunity_score: float | None,
    iv_rank: float | None,
    expected_move: float | None,
    today: date,
    speculative_interest: float | None = None,
) -> dict[str, Any] | None:
    rows = []
    for contract in contracts:
        if contract.get("right") != right:
            continue
        strike = float(contract["strike"])
        if right == "C" and strike <= spot:
            continue
        if right == "P" and strike >= spot:
            continue
        if not band[0] <= abs(float(contract["delta"])) <= band[1]:
            continue
        if _relative_spread(contract) > 0.25:
            continue
        if int(contract.get("open_interest") or 0) < 50:
            continue
        try:
            dte = (date.fromisoformat(str(contract.get("expiration"))) - today).days
        except (TypeError, ValueError):
            dte = None
        score, parts = _score_contract(
            contract,
            band=band,
            opportunity_score=opportunity_score,
            iv_rank=iv_rank,
            expected_move=expected_move,
            spot=spot,
            dte=dte,
            speculative_interest=speculative_interest,
        )
        rows.append((score, parts, contract))
    if not rows:
        return None
    rows.sort(key=lambda row: row[0], reverse=True)
    score, parts, contract = rows[0]
    result = dict(contract)
    result.update(
        speculative_contract_score=score,
        score_components=parts,
        relative_spread=round(_relative_spread(contract), 4),
        distance_from_spot_pct=round(abs(float(contract["strike"]) - spot) / spot * 100.0, 2),
    )
    return result


@router.get("/{symbol}")
async def get_speculative_contracts(
    request: Request,
    symbol: str,
    min_dte: int = Query(5, ge=1, le=45),
    max_dte: int = Query(14, ge=2, le=60),
):
    """Return ranked OTM long-premium contracts using TV context + fresh Tradier data."""
    symbol = symbol.upper().strip()
    if not symbol.isalnum() or len(symbol) > 8:
        raise HTTPException(400, "invalid symbol")
    if min_dte > max_dte:
        raise HTTPException(400, "min_dte must be <= max_dte")

    now = datetime.now(UTC)
    setup_payload, ticker_payload, levels_payload, market_structure_payload, gamma_exp_payload, expirations_payload = await asyncio.gather(
        _tv_get(request.app.state.http, f"/agent/trade-setup/{symbol}", {}),
        _tv_get(request.app.state.http, f"/tickers/{symbol}", {"trade_recommendation": "true"}),
        _tv_get(request.app.state.http, f"/tickers/{symbol}/levels", {}),
        _tv_get(request.app.state.http, f"/tickers/{symbol}/market-structure", {}),
        _tv_get(request.app.state.http, f"/tickers/{symbol}/curves/gamma/expirations", {}),
        _tradier_get(request, "/markets/options/expirations", {"symbol": symbol, "includeAllRoots": "true"}),
    )

    setup = _trade_setup(setup_payload)
    direction, right = _direction(setup)
    if not right:
        return {
            "symbol": symbol,
            "status": "NO_DIRECTIONAL_LONG_PREMIUM_SETUP",
            "trading_volatility_setup": setup,
            "note": "TradingVolatility did not return a long/short direction suitable for an OTM call/put buy.",
        }

    ticker_state = _tv_data(ticker_payload)
    opportunity_score = _walk_for_number(setup, ("opportunity_score",))
    iv_rank = _walk_for_number(ticker_state, ("iv_rank", "ivRank", "iv_rank_30d"))
    spot = _walk_for_number(ticker_state, ("price", "spot", "spot_price", "underlying_price"))
    market_structure = _tv_data(market_structure_payload)
    expected = _expected_move(levels_payload, market_structure_payload)
    gamma_expiration = _gamma_expiration_context(gamma_exp_payload)
    speculative_interest = _walk_for_number(
        market_structure,
        ("speculative_interest_score", "speculation_score"),
    )
    supporting = market_structure.get("supporting_factors") if isinstance(market_structure.get("supporting_factors"), dict) else {}
    skew_tone = (
        ((market_structure.get("drivers") or {}).get("skew_tone") or {})
        if isinstance(market_structure.get("drivers"), dict)
        else {}
    )
    surface_context = {
        "signal": market_structure.get("signal"),
        "bias": market_structure.get("bias"),
        "structure_regime": market_structure.get("structure_regime"),
        "skew_tone": skew_tone,
        "put_call_25d_iv_premium_pct": supporting.get("put_call_25d_iv_premium_pct"),
        "speculative_interest_score": speculative_interest,
        "pct_gamma_expiring_nearest_expiry": supporting.get("pct_gamma_expiring_nearest_expiry"),
        "expected_move_pct_1w": supporting.get("expected_move_pct_1w"),
    }

    expirations = _expiration_dates(expirations_payload, now.date(), min_dte, max_dte)
    if not expirations:
        return {
            "symbol": symbol,
            "status": "NO_EXPIRATION_IN_WINDOW",
            "direction": direction,
            "trading_volatility_setup": setup,
            "iv_rank": iv_rank,
            "expected_move": expected,
            "gamma_by_expiration": gamma_expiration,
        }

    if spot is None:
        quote_payload = await _tradier_get(request, "/markets/quotes", {"symbols": symbol, "greeks": "false"})
        quote = (quote_payload.get("quotes") or {}).get("quote") or {}
        if isinstance(quote, list):
            quote = quote[0] if quote else {}
        spot = _walk_for_number(quote, ("last", "close", "bid", "ask"))
    if spot is None:
        raise HTTPException(503, "underlying price unavailable")

    all_contracts: list[dict[str, Any]] = []
    expirations_used: list[str] = []
    for expiration in expirations:
        chain = await _tradier_get(
            request,
            "/markets/options/chains",
            {"symbol": symbol, "expiration": expiration, "greeks": "true"},
        )
        raw = (chain.get("options") or {}).get("option") or []
        if isinstance(raw, dict):
            raw = [raw]
        normalized = [
            item for item in
            (normalize_contract(row, now, stale_after_seconds=90.0) for row in raw if isinstance(row, dict))
            if item is not None
        ]
        for item in normalized:
            item["expiration"] = expiration
        if normalized:
            expirations_used.append(expiration)
            all_contracts.extend(normalized)

    if not all_contracts:
        return {
            "symbol": symbol,
            "status": "FRESH_OPTIONS_DATA_UNAVAILABLE",
            "direction": direction,
            "right": right,
            "spot": spot,
            "trading_volatility_setup": setup,
            "iv_rank": iv_rank,
            "expected_move": expected,
            "gamma_by_expiration": gamma_expiration,
            "expiration_window": {"min_dte": min_dte, "max_dte": max_dte, "candidates": expirations},
            "note": "No option contracts passed the 90-second bid/ask/Greeks freshness gate.",
        }

    recommendations = {}
    for label, band in CATEGORY_BANDS.items():
        recommendations[label] = _choose_candidate(
            all_contracts,
            right=right,
            spot=float(spot),
            band=band,
            opportunity_score=opportunity_score,
            iv_rank=iv_rank,
            expected_move=expected.get("dollars"),
            today=now.date(),
            speculative_interest=speculative_interest,
        )

    return {
        "symbol": symbol,
        "status": "OK",
        "generated_at": now.isoformat(),
        "direction": direction,
        "right": right,
        "spot": round(float(spot), 4),
        "source": {
            "ranking_and_volatility": "TradingVolatility v2 API",
            "executable_market_data": "Tradier production option chains",
        },
        "trading_volatility_setup": setup,
        "opportunity_score": opportunity_score,
        "iv_rank": iv_rank,
        "expected_move": expected,
        "gamma_by_expiration": gamma_expiration,
        "volatility_surface_context": surface_context,
        "expiration_window": {
            "min_dte": min_dte,
            "max_dte": max_dte,
            "fresh_expirations_used": expirations_used,
        },
        "recommendations": recommendations,
        "selection_policy": {
            "best_contract_delta": CATEGORY_BANDS["best_contract"],
            "aggressive_otm_delta": CATEGORY_BANDS["aggressive_otm"],
            "lotto_delta": CATEGORY_BANDS["lotto"],
            "minimum_open_interest": 50,
            "maximum_relative_bid_ask_spread": 0.25,
            "options_freshness_seconds": 90,
            "note": "GEX/gamma structure is descriptive context only; it is not used as a standalone directional signal.",
        },
        "advisory_only": True,
        "order_routing": False,
    }
