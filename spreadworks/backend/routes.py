"""SpreadWorks API routes.

Endpoints
---------
GET  /api/spreadworks/candles          OHLCV candle data from Tradier
GET  /api/spreadworks/gex              GEX levels (proxied from AlphaGEX)
GET  /api/spreadworks/expirations      Available option expirations
GET  /api/spreadworks/chain            Option chain strikes for an expiration
GET  /api/spreadworks/gex-suggest      Auto-suggest strikes from GEX levels
POST /api/spreadworks/calculate        Spread P&L / Greeks calculation
GET  /api/spreadworks/alerts           Active price alerts
POST /api/spreadworks/alerts/{id}/trigger  Mark alert as triggered
"""

from __future__ import annotations

import math
import os
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/spreadworks", tags=["SpreadWorks"])

TRADIER_TOKEN = os.getenv("TRADIER_TOKEN", "")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID", "")
TRADIER_BASE = "https://api.tradier.com/v1"
ALPHAGEX_BASE_URL = os.getenv("ALPHAGEX_BASE_URL", "http://localhost:8000")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tradier_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}


async def _tradier_get(request: Request, path: str, params: dict | None = None):
    """GET from Tradier API via the shared httpx client."""
    http = request.app.state.http
    resp = await http.get(
        f"{TRADIER_BASE}{path}",
        headers=_tradier_headers(),
        params=params or {},
    )
    if resp.status_code != 200:
        raise HTTPException(502, f"Tradier error {resp.status_code}: {resp.text[:200]}")
    return resp.json()


# ---------------------------------------------------------------------------
# 1. Candles
# ---------------------------------------------------------------------------


@router.get("/candles")
async def get_candles(request: Request, symbol: str = "SPY"):
    """Return intraday 5-min candles for the current session."""
    today = date.today().isoformat()
    data = await _tradier_get(
        request,
        "/markets/history",
        {"symbol": symbol, "interval": "5min", "start": today, "end": today},
    )

    raw = data.get("history", {})
    if raw is None:
        raw = {}
    days = raw.get("day", [])
    if isinstance(days, dict):
        days = [days]

    candles = []
    last_price = None
    for d in days:
        candles.append(
            {
                "time": d.get("date"),
                "open": d.get("open"),
                "high": d.get("high"),
                "low": d.get("low"),
                "close": d.get("close"),
                "volume": d.get("volume"),
            }
        )
        last_price = d.get("close")

    # If no intraday history yet, fetch last quote for spot price
    if not candles:
        quote_data = await _tradier_get(request, "/markets/quotes", {"symbols": symbol})
        quotes = quote_data.get("quotes", {})
        q = quotes.get("quote", {}) if quotes else {}
        if isinstance(q, list):
            q = q[0] if q else {}
        last_price = q.get("last")

    return {"symbol": symbol, "candles": candles, "last_price": last_price}


# ---------------------------------------------------------------------------
# 2. GEX levels (proxy from AlphaGEX)
# ---------------------------------------------------------------------------


@router.get("/gex")
async def get_gex(request: Request, symbol: str = "SPY"):
    """Proxy GEX levels from the main AlphaGEX backend.

    Tries WATCHTOWER /gamma first (richer data), falls back to /gex/{symbol}.
    """
    http = request.app.state.http

    # Try WATCHTOWER first
    try:
        resp = await http.get(
            f"{ALPHAGEX_BASE_URL}/api/watchtower/gamma",
            params={"symbol": symbol, "expiration": "today"},
        )
        if resp.status_code == 200:
            body = resp.json()
            d = body.get("data", {})
            ms = d.get("market_structure", {})
            fp_obj = ms.get("flip_point", {})
            gw = ms.get("gamma_walls", {})
            return {
                "flip_point": fp_obj.get("current") if isinstance(fp_obj, dict) else fp_obj,
                "call_wall": gw.get("call_wall") if isinstance(gw, dict) else None,
                "put_wall": gw.get("put_wall") if isinstance(gw, dict) else None,
                "gamma_regime": d.get("gamma_regime") or ms.get("gamma_regime"),
                "spot_price": d.get("spot_price"),
                "vix": d.get("vix"),
                "source": "watchtower",
            }
    except Exception:
        pass

    # Fallback to simple GEX endpoint
    try:
        resp = await http.get(f"{ALPHAGEX_BASE_URL}/api/gex/{symbol}")
        if resp.status_code == 200:
            body = resp.json()
            d = body.get("data", body)
            return {
                "flip_point": d.get("flip_point"),
                "call_wall": d.get("call_wall"),
                "put_wall": d.get("put_wall"),
                "gamma_regime": d.get("regime") or d.get("gamma_regime"),
                "spot_price": d.get("spot_price"),
                "vix": d.get("vix"),
                "source": "gex",
            }
    except Exception:
        pass

    raise HTTPException(502, "Could not fetch GEX data from AlphaGEX")


# ---------------------------------------------------------------------------
# 3. Expirations
# ---------------------------------------------------------------------------


@router.get("/expirations")
async def get_expirations(request: Request, symbol: str = "SPY"):
    """Return available option expirations from Tradier."""
    data = await _tradier_get(
        request,
        "/markets/options/expirations",
        {"symbol": symbol, "includeAllRoots": "true"},
    )
    exps = data.get("expirations", {})
    if exps is None:
        exps = {}
    date_list = exps.get("date", [])
    if isinstance(date_list, str):
        date_list = [date_list]
    return {"symbol": symbol, "expirations": date_list}


# ---------------------------------------------------------------------------
# 4. Option chain (strikes for a given expiration)
# ---------------------------------------------------------------------------


@router.get("/chain")
async def get_chain(request: Request, symbol: str = "SPY", expiration: str = ""):
    """Return available strikes for a given expiration from Tradier."""
    if not expiration:
        raise HTTPException(400, "expiration query param is required")

    data = await _tradier_get(
        request,
        "/markets/options/chains",
        {"symbol": symbol, "expiration": expiration, "greeks": "true"},
    )

    options = data.get("options", {})
    if options is None:
        options = {}
    option_list = options.get("option", [])
    if isinstance(option_list, dict):
        option_list = [option_list]

    # Deduplicate strikes (calls + puts share the same strikes)
    strikes = sorted({o["strike"] for o in option_list if "strike" in o})
    return {"symbol": symbol, "expiration": expiration, "strikes": strikes}


# ---------------------------------------------------------------------------
# 5. GEX-suggested strikes
# ---------------------------------------------------------------------------


@router.get("/gex-suggest")
async def gex_suggest(
    request: Request,
    symbol: str = "SPY",
    strategy: str = "double_diagonal",
):
    """Auto-generate strike suggestions from GEX levels.

    Uses flip point as center, call/put walls for short strikes,
    and offsets for long strikes to create defined-risk spreads.
    """
    # Fetch GEX data
    gex = await get_gex(request, symbol)
    flip = gex.get("flip_point")
    call_wall = gex.get("call_wall")
    put_wall = gex.get("put_wall")
    spot = gex.get("spot_price")
    regime = gex.get("gamma_regime")

    if not flip or not spot:
        raise HTTPException(
            422,
            "GEX data incomplete — flip_point and spot_price required for suggestions",
        )

    # Default walls if missing
    if not call_wall:
        call_wall = spot + (spot * 0.01)  # +1% above spot
    if not put_wall:
        put_wall = spot - (spot * 0.01)  # -1% below spot

    # Round strikes to nearest 0.5
    def _round_strike(v: float) -> float:
        return round(v * 2) / 2

    # Expiration suggestions: front = nearest Friday, back = 2 Fridays out
    today = date.today()
    days_until_friday = (4 - today.weekday()) % 7
    if days_until_friday == 0:
        days_until_friday = 7
    front_exp = (today + timedelta(days=days_until_friday)).isoformat()
    back_exp = (today + timedelta(days=days_until_friday + 7)).isoformat()

    # Wing width depends on regime
    wing_offset = 3.0 if regime and "POSITIVE" in str(regime).upper() else 5.0

    if strategy == "double_diagonal":
        short_put = _round_strike(put_wall)
        short_call = _round_strike(call_wall)
        long_put = _round_strike(short_put - wing_offset)
        long_call = _round_strike(short_call + wing_offset)

        legs = {
            "long_put_strike": long_put,
            "short_put_strike": short_put,
            "short_call_strike": short_call,
            "long_call_strike": long_call,
            "short_expiration": front_exp,
            "long_expiration": back_exp,
        }
        rationale = (
            f"Short strikes at GEX walls (put wall ${short_put}, call wall ${short_call}). "
            f"Long wings ${wing_offset} wide. "
            f"Front exp {front_exp}, back exp {back_exp}. "
            f"Regime: {regime or 'UNKNOWN'}."
        )
    else:
        # Double calendar: put & call strikes near walls, two expirations
        put_strike = _round_strike(put_wall)
        call_strike = _round_strike(call_wall)

        legs = {
            "put_strike": put_strike,
            "call_strike": call_strike,
            "front_expiration": front_exp,
            "back_expiration": back_exp,
        }
        rationale = (
            f"Calendar strikes at GEX walls (put ${put_strike}, call ${call_strike}). "
            f"Front {front_exp}, back {back_exp}. "
            f"Regime: {regime or 'UNKNOWN'}."
        )

    return {
        "symbol": symbol,
        "strategy": strategy,
        "legs": legs,
        "flip_point": flip,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "gamma_regime": regime,
        "spot_price": spot,
        "rationale": rationale,
    }


# ---------------------------------------------------------------------------
# 6. Calculate spread P&L
# ---------------------------------------------------------------------------

# Black-Scholes helpers for Greeks/pricing
_SQRT2PI = math.sqrt(2 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT2PI


def _bs_price(
    S: float, K: float, T: float, r: float, sigma: float, is_call: bool
) -> float:
    """Black-Scholes option price."""
    if T <= 0 or sigma <= 0:
        # Expired — intrinsic only
        return max(0, S - K) if is_call else max(0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if is_call:
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    else:
        return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def _bs_greeks(
    S: float, K: float, T: float, r: float, sigma: float, is_call: bool
) -> dict:
    if T <= 0 or sigma <= 0:
        intrinsic = max(0, S - K) if is_call else max(0, K - S)
        return {"delta": (1.0 if intrinsic > 0 else 0.0) * (1 if is_call else -1),
                "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    nd1 = _norm_pdf(d1)

    if is_call:
        delta = _norm_cdf(d1)
    else:
        delta = _norm_cdf(d1) - 1.0
    gamma = nd1 / (S * sigma * sqrtT)
    theta = (-(S * nd1 * sigma) / (2 * sqrtT)
             - r * K * math.exp(-r * T) * _norm_cdf(d2 if is_call else -d2)
             * (1 if is_call else -1)) / 365.0
    vega = S * nd1 * sqrtT / 100.0

    return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega}


class CalcRequest(BaseModel):
    symbol: str = "SPY"
    strategy: str  # double_diagonal | double_calendar
    contracts: int = 1
    legs: dict[str, Any]
    spot_price: float | None = None
    input_mode: str = "manual"


@router.post("/calculate")
async def calculate_spread(request: Request, body: CalcRequest):
    """Calculate P&L profile, breakevens, and Greeks for a spread."""
    S = body.spot_price
    if not S:
        # Fetch current spot
        gex = await get_gex(request, body.symbol)
        S = gex.get("spot_price")
        if not S:
            raise HTTPException(422, "spot_price required")

    r = 0.05  # risk-free rate assumption
    sigma = 0.20  # default IV (could be enriched from chain greeks)
    legs = body.legs
    n = body.contracts
    today = date.today()

    def _parse_date(d: str) -> date:
        return datetime.strptime(d, "%Y-%m-%d").date()

    def _tte(d: str) -> float:
        """Time to expiration in years."""
        exp = _parse_date(d)
        days = (exp - today).days
        return max(days, 0) / 365.0

    if body.strategy == "double_diagonal":
        lp = float(legs.get("longPutStrike") or legs.get("long_put_strike", 0))
        sp = float(legs.get("shortPutStrike") or legs.get("short_put_strike", 0))
        sc = float(legs.get("shortCallStrike") or legs.get("short_call_strike", 0))
        lc = float(legs.get("longCallStrike") or legs.get("long_call_strike", 0))
        short_exp = str(legs.get("shortExpiration") or legs.get("short_expiration", ""))
        long_exp = str(legs.get("longExpiration") or legs.get("long_expiration", ""))

        if not all([lp, sp, sc, lc, short_exp, long_exp]):
            raise HTTPException(422, "All 4 strikes and 2 expirations required")

        T_short = _tte(short_exp)
        T_long = _tte(long_exp)

        # Net debit = long options bought - short options sold
        # Longs: long put (back exp), long call (back exp)
        # Shorts: short put (front exp), short call (front exp)
        price_long_put = _bs_price(S, lp, T_long, r, sigma, False)
        price_short_put = _bs_price(S, sp, T_short, r, sigma, False)
        price_short_call = _bs_price(S, sc, T_short, r, sigma, True)
        price_long_call = _bs_price(S, lc, T_long, r, sigma, True)

        net_debit = (price_long_put + price_long_call - price_short_put - price_short_call) * 100 * n

        # Greeks (net position)
        g_lp = _bs_greeks(S, lp, T_long, r, sigma, False)
        g_sp = _bs_greeks(S, sp, T_short, r, sigma, False)
        g_sc = _bs_greeks(S, sc, T_short, r, sigma, True)
        g_lc = _bs_greeks(S, lc, T_long, r, sigma, True)

        greeks = {
            k: round((g_lp[k] - g_sp[k] - g_sc[k] + g_lc[k]) * n, 6)
            for k in ("delta", "gamma", "theta", "vega")
        }

        # Approximate max profit / loss via P&L at expiration scan
        max_profit = 0.0
        max_loss = 0.0
        lower_be = None
        upper_be = None

        scan_lo = min(lp, sp, sc, lc) - 20
        scan_hi = max(lp, sp, sc, lc) + 20
        prev_pnl = None

        for px_int in range(int(scan_lo * 10), int(scan_hi * 10) + 1):
            px = px_int / 10.0
            # At short expiration: short options at intrinsic, long options still have time value
            T_remaining = max(T_long - T_short, 1 / 365.0)
            pnl = (
                _bs_price(px, lp, T_remaining, r, sigma, False)
                - max(0, sp - px)  # short put intrinsic
                - max(0, px - sc)  # short call intrinsic
                + _bs_price(px, lc, T_remaining, r, sigma, True)
                - (price_long_put + price_long_call - price_short_put - price_short_call)
            ) * 100 * n

            if pnl > max_profit:
                max_profit = pnl
            if pnl < max_loss:
                max_loss = pnl

            # Breakeven detection
            if prev_pnl is not None:
                if prev_pnl < 0 <= pnl or prev_pnl >= 0 > pnl:
                    be = px
                    if lower_be is None:
                        lower_be = be
                    else:
                        upper_be = be
            prev_pnl = pnl

    elif body.strategy == "double_calendar":
        ps = float(legs.get("putStrike") or legs.get("put_strike", 0))
        cs = float(legs.get("callStrike") or legs.get("call_strike", 0))
        front_exp = str(legs.get("frontExpiration") or legs.get("front_expiration", ""))
        back_exp = str(legs.get("backExpiration") or legs.get("back_expiration", ""))

        if not all([ps, cs, front_exp, back_exp]):
            raise HTTPException(422, "Both strikes and both expirations required")

        T_front = _tte(front_exp)
        T_back = _tte(back_exp)

        # Net debit: buy back month, sell front month
        price_front_put = _bs_price(S, ps, T_front, r, sigma, False)
        price_back_put = _bs_price(S, ps, T_back, r, sigma, False)
        price_front_call = _bs_price(S, cs, T_front, r, sigma, True)
        price_back_call = _bs_price(S, cs, T_back, r, sigma, True)

        net_debit = (price_back_put + price_back_call - price_front_put - price_front_call) * 100 * n

        g_fp = _bs_greeks(S, ps, T_front, r, sigma, False)
        g_bp = _bs_greeks(S, ps, T_back, r, sigma, False)
        g_fc = _bs_greeks(S, cs, T_front, r, sigma, True)
        g_bc = _bs_greeks(S, cs, T_back, r, sigma, True)

        greeks = {
            k: round((-g_fp[k] + g_bp[k] - g_fc[k] + g_bc[k]) * n, 6)
            for k in ("delta", "gamma", "theta", "vega")
        }

        max_profit = 0.0
        max_loss = 0.0
        lower_be = None
        upper_be = None

        scan_lo = min(ps, cs) - 20
        scan_hi = max(ps, cs) + 20
        prev_pnl = None

        for px_int in range(int(scan_lo * 10), int(scan_hi * 10) + 1):
            px = px_int / 10.0
            T_remaining = max(T_back - T_front, 1 / 365.0)
            pnl = (
                -max(0, ps - px)  # short front put
                + _bs_price(px, ps, T_remaining, r, sigma, False)
                - max(0, px - cs)  # short front call
                + _bs_price(px, cs, T_remaining, r, sigma, True)
                - (price_back_put + price_back_call - price_front_put - price_front_call)
            ) * 100 * n

            if pnl > max_profit:
                max_profit = pnl
            if pnl < max_loss:
                max_loss = pnl

            if prev_pnl is not None:
                if prev_pnl < 0 <= pnl or prev_pnl >= 0 > pnl:
                    be = px
                    if lower_be is None:
                        lower_be = be
                    else:
                        upper_be = be
            prev_pnl = pnl
    else:
        raise HTTPException(400, f"Unknown strategy: {body.strategy}")

    # Simple P(profit) estimate: fraction of scan range that's profitable
    profitable_count = 0
    total_count = 0
    for px_int in range(int(scan_lo * 10), int(scan_hi * 10) + 1):
        px = px_int / 10.0
        T_remaining = max(
            (T_long - T_short if body.strategy == "double_diagonal" else T_back - T_front),
            1 / 365.0,
        )
        if body.strategy == "double_diagonal":
            pnl = (
                _bs_price(px, lp, T_remaining, r, sigma, False)
                - max(0, sp - px)
                - max(0, px - sc)
                + _bs_price(px, lc, T_remaining, r, sigma, True)
                - (price_long_put + price_long_call - price_short_put - price_short_call)
            ) * 100 * n
        else:
            pnl = (
                -max(0, ps - px)
                + _bs_price(px, ps, T_remaining, r, sigma, False)
                - max(0, px - cs)
                + _bs_price(px, cs, T_remaining, r, sigma, True)
                - (price_back_put + price_back_call - price_front_put - price_front_call)
            ) * 100 * n
        if pnl > 0:
            profitable_count += 1
        total_count += 1

    prob_profit = profitable_count / total_count if total_count > 0 else None

    return {
        "symbol": body.symbol,
        "strategy": body.strategy,
        "contracts": n,
        "net_debit": round(net_debit, 2),
        "max_profit": round(max_profit, 2),
        "max_loss": round(max_loss, 2),
        "lower_breakeven": round(lower_be, 2) if lower_be else None,
        "upper_breakeven": round(upper_be, 2) if upper_be else None,
        "probability_of_profit": round(prob_profit, 4) if prob_profit is not None else None,
        "greeks": greeks,
    }


# ---------------------------------------------------------------------------
# 7 & 8. Alerts (in-memory for now; database later)
# ---------------------------------------------------------------------------

_alerts: list[dict] = []
_alert_counter = 0


@router.get("/alerts")
async def get_alerts():
    return {"alerts": _alerts}


@router.post("/alerts/{alert_id}/trigger")
async def trigger_alert(alert_id: int):
    for a in _alerts:
        if a["id"] == alert_id:
            a["triggered"] = True
            return {"ok": True}
    raise HTTPException(404, "Alert not found")
