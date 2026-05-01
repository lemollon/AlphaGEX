"""Tradier-based snapshot fetcher for GOLIATH paper trading.

Per Q4 + paper-trading direction (2026-05-01): GOLIATH co-hosts on
alphagex-trader and uses Tradier as the option-chain data source. Real
Tradier *execution* is NOT enabled in v0.2 -- only data fetching.

Composes a MarketSnapshot from three sources:
    - Tradier   : LETF spot + option chain (per-strike bid/ask/OI)
    - TV /api   : underlying GEX (gamma-by-strike, net_gex, walls)
    - yfinance  : underlying spot + 50d MA + 30d realized vol +
                  next-earnings date

Each fetch is wrapped in try/except so a single source failure doesn't
abort the snapshot. Failed fields default to safe values that downstream
gates will reject (e.g. spy_net_gex=0 fails G01 if SPY GEX is unreachable).

Best-effort by design: the runner skips the instance if the snapshot
fetcher raises or returns None. Phase 7 monitoring tracks failure rates
and posts Discord alerts.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta
from typing import Optional

from trading.goliath.engine import MarketSnapshot
from trading.goliath.instance import GoliathInstance
from trading.goliath.strike_mapping.engine import OptionLeg
from trading.goliath.strike_mapping.wall_finder import GammaStrike

logger = logging.getLogger(__name__)

_DEFAULT_DTE_YEARS = 7.0 / 365.0


def _safe_get_tv_gex(symbol: str) -> tuple[float, list[GammaStrike]]:
    """Fetch (net_gex, strike-level gamma list) from TV. Returns (0, []) on
    failure -- downstream G01/G02/G03 will fail closed."""
    try:
        from core_classes_and_engines import TradingVolatilityAPI  # type: ignore
    except ImportError as exc:
        logger.warning("[snapshot] TradingVolatilityAPI unavailable: %r", exc)
        return 0.0, []

    try:
        client = TradingVolatilityAPI()
        net = client.get_net_gamma(symbol)
        if not isinstance(net, dict) or "error" in net:
            logger.warning("[snapshot] TV net_gamma %s error: %r", symbol, net)
            return 0.0, []
        net_gex = float(net.get("net_gex") or 0)

        # Per-strike gamma -- prefer get_gex_levels (curves/gex_by_strike).
        levels = client.get_gex_levels(symbol)
        strikes: list[GammaStrike] = []
        if isinstance(levels, dict):
            curves = levels.get("strikes") or levels.get("curves") or {}
            if isinstance(curves, dict):
                # Tolerate both dict-of-strike and list-of-strike shapes.
                gby = curves.get("gex_by_strike") or curves
                if isinstance(gby, list):
                    for row in gby:
                        try:
                            strike = float(row.get("strike"))
                            gamma = float(row.get("total_gamma") or row.get("gamma") or 0)
                            strikes.append(GammaStrike(strike=strike, gamma=gamma))
                        except (TypeError, ValueError, AttributeError):
                            continue
                elif isinstance(gby, dict):
                    for k, v in gby.items():
                        try:
                            strike = float(k)
                            gamma = float(v.get("total_gamma") or v.get("gamma") or 0)
                            strikes.append(GammaStrike(strike=strike, gamma=gamma))
                        except (TypeError, ValueError, AttributeError):
                            continue
        return net_gex, strikes
    except Exception as exc:  # noqa: BLE001
        logger.warning("[snapshot] TV fetch failed for %s: %r", symbol, exc)
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
    """Fetch (letf_spot, letf_chain dict, iv_rank) from Tradier.

    iv_rank is approximated from get_atm_iv() -- v0.2 uses the spec
    fallback path (TV iv_rank is preferred per Phase 1 smoke test).
    Returns (0, {}, None) on failure.
    """
    try:
        from data.tradier_data_fetcher import TradierDataFetcher  # type: ignore
    except ImportError as exc:
        logger.warning("[snapshot] TradierDataFetcher unavailable: %r", exc)
        return 0.0, {}, None

    try:
        client = TradierDataFetcher(sandbox=False)
        quote = client.get_quote(letf_ticker)
        if not isinstance(quote, dict) or not (quote.get("last") or quote.get("close")):
            return 0.0, {}, None
        spot = float(quote.get("last") or quote.get("close") or 0)

        # Use nearest expiration (Tradier returns first in get_option_expirations
        # which is the nearest valid expiry; per spec target is 7-DTE).
        chain_obj = client.get_option_chain(letf_ticker, greeks=True)
        chain: dict[tuple[float, str], OptionLeg] = {}
        for c in getattr(chain_obj, "contracts", []) or []:
            try:
                kind = "put" if c.option_type == "put" else "call"
                chain[(float(c.strike), kind)] = OptionLeg(
                    strike=float(c.strike),
                    bid=float(c.bid),
                    ask=float(c.ask),
                    open_interest=int(c.open_interest),
                    contract_type=kind,
                )
            except (TypeError, ValueError, AttributeError):
                continue

        # iv_rank approximation: not authoritative; G05 should prefer TV.
        # v0.3 V3-1 builds the proper rolling-percentile module.
        iv_rank: Optional[float] = None

        return spot, chain, iv_rank
    except Exception as exc:  # noqa: BLE001
        logger.warning("[snapshot] Tradier %s failed: %r", letf_ticker, exc)
        return 0.0, {}, None


def _safe_tv_iv_rank(letf_ticker: str) -> Optional[float]:
    """Fetch IV rank from TV /series for the LETF. Returns None on failure
    -- G05 will then mark INSUFFICIENT_HISTORY (cold-start fail-closed)."""
    try:
        from core_classes_and_engines import TradingVolatilityAPI  # type: ignore
        client = TradingVolatilityAPI()
        if not hasattr(client, "_v2_series"):
            return None
        resp = client._v2_series(letf_ticker, ["iv_rank"], window="5d")
        if not isinstance(resp, dict) or "error" in resp:
            return None
        data = resp.get("data", resp)
        points = data.get("points") if isinstance(data, dict) else None
        if isinstance(points, list):
            for pt in reversed(points):
                if isinstance(pt, dict) and pt.get("iv_rank") is not None:
                    return float(pt["iv_rank"])
        series = data.get("series") if isinstance(data, dict) else None
        if isinstance(series, dict):
            arr = series.get("iv_rank") or []
            for v in reversed(arr):
                if v is not None:
                    return float(v)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[snapshot] TV iv_rank %s failed: %r", letf_ticker, exc)
        return None


def build_market_snapshot(
    instance: GoliathInstance,
    spy_net_gex_override: Optional[float] = None,
) -> Optional[MarketSnapshot]:
    """Build a MarketSnapshot for the given instance using live data sources.

    Composes:
        SPY GEX                 -- TV
        underlying GEX + walls  -- TV
        underlying spot + MA    -- yfinance
        underlying realized vol -- yfinance (30d)
        next earnings           -- yfinance
        LETF spot + chain       -- Tradier
        IV rank                 -- TV (preferred); None if unavailable

    Returns None ONLY if the LETF chain is empty (no options data -> no
    structure can be built). Other failures degrade gracefully:
    upstream gates fail closed on missing data, which is what we want.

    spy_net_gex_override lets the runner fetch SPY GEX once per cycle and
    reuse across all 5 instances (avoids 5 TV calls for the same number).
    """
    underlying = instance.underlying_ticker
    letf = instance.letf_ticker

    # SPY GEX (G01)
    if spy_net_gex_override is not None:
        spy_net_gex = spy_net_gex_override
    else:
        spy_net_gex, _ = _safe_get_tv_gex("SPY")

    # Underlying GEX (G02 + G03 walls)
    underlying_net_gex, underlying_strikes = _safe_get_tv_gex(underlying)

    # yfinance: spot, MA, sigma, earnings
    underlying_spot, underlying_50d_ma, sigma, next_earnings = _safe_yfinance_underlying(underlying)

    # Tradier: LETF spot + chain
    letf_spot, letf_chain, _ = _safe_tradier_letf_spot_and_chain(letf)
    if not letf_chain:
        # Cannot build trade structure without options chain. Caller skips.
        logger.warning("[snapshot] %s: empty Tradier chain -- skipping cycle", instance.name)
        return None

    # IV rank (G05) -- prefer TV; cold-start path returns None -> G05 fail-closed
    iv_rank = _safe_tv_iv_rank(letf)

    return MarketSnapshot(
        spy_net_gex=spy_net_gex,
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
