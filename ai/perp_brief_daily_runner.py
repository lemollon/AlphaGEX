"""
Daily runner that generates AGAPE perp signal briefs for all 11 tickers
once per day after equity close. Wired to APScheduler in
`scheduler/trader_scheduler.py` (3:30 PM CT, Mon-Fri).

Replaces the old on-demand path where every dashboard SWR refresh would
hit Claude. Routes now read from `agape_perp_signal_briefs` instead.
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

# Provider symbols passed to crypto_data_provider.get_snapshot(). These
# match the per-route arguments in backend/api/routes/agape_*_routes.py.
# SHIB-PERP and SHIB-FUTURES both consume the "SHIB" snapshot, so we only
# generate one brief for SHIB and let both routes read from the same row.
PERP_TICKERS: List[str] = [
    "BTC", "ETH", "XRP", "DOGE", "SHIB",
    "SOL", "AVAX",
    "BCH", "LINK", "LTC",
]


def _serialize_snapshot(snap) -> Dict:
    """Serialize a CryptoMarketSnapshot to the dict shape expected by
    perp_signal_brief.get_signal_brief(). Mirrors the per-route inline
    code in agape_*_routes.py."""
    return {
        "symbol": snap.symbol,
        "spot_price": snap.spot_price,
        "funding": {
            "rate": snap.funding_rate.rate if snap.funding_rate else None,
            "regime": snap.funding_regime,
            "annualized": snap.funding_rate.annualized_rate if snap.funding_rate else None,
        },
        "long_short": {
            "ratio": snap.ls_ratio.ratio if snap.ls_ratio else None,
            "long_pct": snap.ls_ratio.long_pct if snap.ls_ratio else None,
            "short_pct": snap.ls_ratio.short_pct if snap.ls_ratio else None,
            "bias": snap.ls_ratio.bias if snap.ls_ratio else None,
        },
        "open_interest": {
            "total_usd": snap.oi_snapshot.total_usd if snap.oi_snapshot else None,
        },
        "crypto_gex": {
            "regime": snap.crypto_gex.gamma_regime if snap.crypto_gex else None,
            "net_gex": snap.crypto_gex.net_gex if snap.crypto_gex else None,
            "flip_point": snap.crypto_gex.flip_point if snap.crypto_gex else None,
        },
        "signals": {
            "combined_signal": snap.combined_signal,
            "combined_confidence": snap.combined_confidence,
            "directional_bias": snap.directional_bias,
            "volatility_regime": snap.volatility_regime,
        },
    }


def run_daily_briefs() -> Dict[str, int]:
    """Generate a fresh signal brief for every perp ticker and store it.

    Returns a small summary dict for the scheduler log.
    """
    summary = {"generated": 0, "snapshot_missing": 0, "claude_failed": 0, "errors": 0}

    try:
        from data.crypto_data_provider import get_crypto_data_provider  # type: ignore
    except Exception as e:
        logger.error(f"perp_brief_daily_runner: crypto provider unavailable: {e}")
        return summary

    try:
        from ai.perp_signal_brief import get_signal_brief
        from ai.perp_brief_storage import store_brief
    except Exception as e:
        logger.error(f"perp_brief_daily_runner: brief modules unavailable: {e}")
        return summary

    provider = get_crypto_data_provider()

    for ticker in PERP_TICKERS:
        try:
            snap = provider.get_snapshot(ticker)
            if not snap:
                summary["snapshot_missing"] += 1
                logger.warning(f"perp_brief_daily_runner: snapshot missing for {ticker}")
                continue

            payload = get_signal_brief(_serialize_snapshot(snap))
            if payload is None:
                summary["claude_failed"] += 1
                logger.warning(f"perp_brief_daily_runner: Claude returned None for {ticker}")
                continue

            store_brief(ticker, payload)
            summary["generated"] += 1
            logger.info(f"perp_brief_daily_runner: stored brief for {ticker}")

        except Exception as e:
            summary["errors"] += 1
            logger.error(f"perp_brief_daily_runner: {ticker} failed: {e}")

    logger.info(f"perp_brief_daily_runner: done — {summary}")
    return summary
