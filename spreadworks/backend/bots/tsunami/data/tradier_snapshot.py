"""Market snapshot fetcher for TSUNAMI paper trading (SpreadWorks port).

Composes a MarketSnapshot from three sources:
    - Tradier   : LETF spot + option chain (per-strike bid/ask/OI), and
                  underlying per-strike gamma / net GEX derived from the
                  greeks-enabled chain (this was the production-proven
                  fallback path in the AlphaGEX original; here it is the
                  primary and only GEX source)
    - TV /api   : LETF IV rank (gate G05) — optional, needs
                  TRADING_VOLATILITY_API_TOKEN
    - yfinance  : underlying spot + 50d MA + 30d realized vol +
                  next-earnings date

Each fetch is wrapped in try/except so a single source failure doesn't
abort the snapshot. Failed fields default to safe values that downstream
gates reject (e.g. underlying_spot=0 fails G03's spot guard explicitly).

Best-effort by design: the runner skips the instance if the snapshot
fetcher raises or returns None. Monitoring tracks failure rates and posts
Discord alerts.
"""
from __future__ import annotations

import logging
import math
from datetime import date
from typing import Optional

from backend.bots.tsunami.data import tradier_client, tv_client
from backend.bots.tsunami.engine import MarketSnapshot
from backend.bots.tsunami.instance import TsunamiInstance
from backend.bots.tsunami.strike_mapping.engine import OptionLeg
from backend.bots.tsunami.strike_mapping.wall_finder import GammaStrike

logger = logging.getLogger(__name__)

_DEFAULT_DTE_YEARS = 7.0 / 365.0


def _safe_underlying_gex(symbol: str) -> tuple[float, list[GammaStrike]]:
    """Compute (net_gex, per-strike gamma) from the Tradier options chain.

    Same math as AlphaGEX's data.gex_calculator.calculate_gex_from_chain,
    inlined: per contract GEX = gamma * OI * 100 * spot^2 * 0.01 (per-1%-move
    notional), calls positive / puts negative for the net; per-strike gamma
    for wall detection collapses to call_gex + put_gex magnitudes, matching
    TV's "total_gamma" semantics (both call and put concentration count
    toward a wall). Returns (0.0, []) on failure; G02/G03 then fail closed.
    """
    try:
        quote = tradier_client.get_quote(symbol)
        if not isinstance(quote, dict):
            return 0.0, []
        spot = float(quote.get("last") or quote.get("close") or 0)
        if spot <= 0:
            return 0.0, []

        contracts = tradier_client.get_chain_contracts(symbol)
        if not contracts:
            logger.warning("[snapshot] Tradier-derived GEX %s: empty chain", symbol)
            return 0.0, []

        per_strike: dict[float, dict[str, float]] = {}
        net_gex = 0.0
        for c in contracts:
            strike = c["strike"]
            gamma = c["gamma"]
            oi = c["open_interest"]
            if strike <= 0 or gamma <= 0 or oi <= 0:
                continue
            gex_value = gamma * oi * 100 * (spot ** 2) * 0.01
            bucket = per_strike.setdefault(strike, {"call": 0.0, "put": 0.0})
            if c["option_type"] == "call":
                bucket["call"] += gex_value
                net_gex += gex_value
            elif c["option_type"] == "put":
                bucket["put"] += gex_value
                net_gex -= gex_value

        strikes = [
            GammaStrike(strike=k, gamma=v["call"] + v["put"])
            for k, v in per_strike.items()
        ]
        logger.info("[snapshot] Tradier-derived GEX %s: net=%.2e, strikes=%d",
                    symbol, net_gex, len(strikes))
        return net_gex, strikes
    except Exception as exc:  # noqa: BLE001
        logger.warning("[snapshot] Tradier-derived GEX failed for %s: %r", symbol, exc)
        return 0.0, []


def _safe_yfinance_underlying(ticker: str) -> tuple[float, Optional[float], float, Optional[date]]:
    """Fetch (spot, 50d_ma, 30d_realized_vol, next_earnings_date) from yfinance.
    Returns (0, None, 0, None) on failure."""
    try:
        import yfinance as yf  # type: ignore
    except ImportError as exc:
        logger.warning("[snapshot] yfinance unavailable: %r", exc)
        return 0.0, None, 0.0, None

    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="90d", auto_adjust=True, actions=False)
        if hist is None or hist.empty:
            return 0.0, None, 0.0, None

        spot = float(hist["Close"].iloc[-1])

        ma_50 = None
        if len(hist) >= 50:
            ma_50 = float(hist["Close"].tail(50).mean())

        # 30d annualized realized vol from log returns.
        sigma = 0.0
        if len(hist) >= 31:
            import numpy as np
            log_ret = np.log(hist["Close"] / hist["Close"].shift(1)).dropna().tail(30)
            sigma = float(log_ret.std() * math.sqrt(252))

        # Next earnings date.
        next_earnings: Optional[date] = None
        try:
            cal = t.calendar
            if isinstance(cal, dict) and "Earnings Date" in cal:
                ed = cal["Earnings Date"]
                if isinstance(ed, list) and ed:
                    ed = ed[0]
                if hasattr(ed, "date"):
                    next_earnings = ed.date()
                elif isinstance(ed, date):
                    next_earnings = ed
        except Exception:  # noqa: BLE001
            pass

        return spot, ma_50, sigma, next_earnings
    except Exception as exc:  # noqa: BLE001
        logger.warning("[snapshot] yfinance %s failed: %r", ticker, exc)
        return 0.0, None, 0.0, None


def _safe_tradier_letf_spot_and_chain(
    letf_ticker: str,
) -> tuple[float, dict[tuple[float, str], OptionLeg], Optional[float]]:
    """Fetch (letf_spot, letf_chain dict, iv_rank placeholder) from Tradier.

    Chain is the nearest expiration (spec target is 7-DTE; the paper
    executor stamps next-Friday expiry). Returns (0, {}, None) on failure.
    """
    try:
        quote = tradier_client.get_quote(letf_ticker)
        if not isinstance(quote, dict) or not (quote.get("last") or quote.get("close")):
            return 0.0, {}, None
        spot = float(quote.get("last") or quote.get("close") or 0)

        chain: dict[tuple[float, str], OptionLeg] = {}
        for c in tradier_client.get_chain_contracts(letf_ticker):
            kind = "put" if c["option_type"] == "put" else "call"
            chain[(c["strike"], kind)] = OptionLeg(
                strike=c["strike"],
                bid=c["bid"],
                ask=c["ask"],
                open_interest=c["open_interest"],
                contract_type=kind,
            )
        return spot, chain, None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[snapshot] Tradier %s failed: %r", letf_ticker, exc)
        return 0.0, {}, None


def _safe_tv_iv_rank(letf_ticker: str) -> Optional[float]:
    """Fetch IV rank from TV /series for the LETF. Returns None on failure
    -- G05 then marks INSUFFICIENT_HISTORY (cold-start fail-closed)."""
    return tv_client.get_iv_rank(letf_ticker)


def build_market_snapshot(
    instance: TsunamiInstance,
) -> Optional[MarketSnapshot]:
    """Build a MarketSnapshot for the given instance using live data sources.

    Composes:
        underlying GEX + walls  -- Tradier chain (greeks)
        underlying spot + MA    -- yfinance
        underlying realized vol -- yfinance (30d)
        next earnings           -- yfinance
        LETF spot + chain       -- Tradier
        IV rank                 -- TV (optional); None if unavailable

    Returns None ONLY if the LETF chain is empty (no options data -> no
    structure can be built). Other failures degrade gracefully:
    upstream gates fail closed on missing data, which is what we want.
    """
    underlying = instance.underlying_ticker
    letf = instance.letf_ticker

    # Underlying GEX (G02 + G03 walls)
    underlying_net_gex, underlying_strikes = _safe_underlying_gex(underlying)

    # yfinance: spot, MA, sigma, earnings
    underlying_spot, underlying_50d_ma, sigma, next_earnings = _safe_yfinance_underlying(underlying)

    # Tradier: LETF spot + chain
    letf_spot, letf_chain, _ = _safe_tradier_letf_spot_and_chain(letf)
    if not letf_chain:
        # Cannot build trade structure without options chain. Caller skips.
        logger.warning("[snapshot] %s: empty Tradier chain -- skipping cycle", instance.name)
        return None

    # IV rank (G05) -- TV; cold-start path returns None -> G05 fail-closed
    iv_rank = _safe_tv_iv_rank(letf)

    return MarketSnapshot(
        underlying_net_gex=underlying_net_gex,
        underlying_strikes=list(underlying_strikes),
        underlying_spot=underlying_spot,
        letf_spot=letf_spot,
        letf_chain=letf_chain,
        sigma_annualized=sigma,
        t_years=_DEFAULT_DTE_YEARS,
        next_earnings_date=next_earnings,
        iv_rank=iv_rank,
        underlying_50d_ma=underlying_50d_ma,
    )
