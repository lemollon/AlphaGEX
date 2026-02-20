"""
Margin configuration for all leveraged instruments.

CME margin requirements are approximate and change based on volatility.
Update the values and last_updated timestamp when CME adjusts margins.

Perpetual margin rates are exchange-specific defaults.
"""

from typing import Dict, Any


# =============================================================================
# CME FUTURES MARGIN SPECS (fixed $ per contract)
# =============================================================================

FUTURES_MARGIN_SPECS: Dict[str, Dict[str, Any]] = {
    # --- Stock Index Micro Futures ---
    # --- Stock Index Micro Futures (CME margin rates - update when CME changes) ---
    "MES": {
        "name": "Micro E-mini S&P 500",
        "exchange": "CME",
        "point_value": 5.0,
        "tick_size": 0.25,
        "tick_value": 1.25,
        "initial_margin": 2300.0,
        "maintenance_margin": 2100.0,
        "last_updated": "2026-02-20",
        "market_type": "stock_futures",
    },
    "MNQ": {
        "name": "Micro E-mini Nasdaq 100",
        "exchange": "CME",
        "point_value": 2.0,
        "tick_size": 0.25,
        "tick_value": 0.50,
        "initial_margin": 3300.0,
        "maintenance_margin": 3000.0,
        "last_updated": "2026-02-20",
        "market_type": "stock_futures",
    },
    "M2K": {
        "name": "Micro E-mini Russell 2000",
        "exchange": "CME",
        "point_value": 5.0,
        "tick_size": 0.10,
        "tick_value": 0.50,
        "initial_margin": 950.0,
        "maintenance_margin": 860.0,
        "last_updated": "2026-02-20",
        "market_type": "stock_futures",
    },
    # RTY is VALOR's alias for M2K (Micro Russell 2000)
    "RTY": {
        "name": "Micro E-mini Russell 2000",
        "exchange": "CME",
        "point_value": 5.0,
        "tick_size": 0.10,
        "tick_value": 0.50,
        "initial_margin": 950.0,
        "maintenance_margin": 860.0,
        "last_updated": "2026-02-20",
        "market_type": "stock_futures",
    },

    # --- Micro Energy Futures ---
    "CL": {
        "name": "Micro WTI Crude Oil (MCL)",
        "exchange": "NYMEX",
        "point_value": 100.0,
        "tick_size": 0.01,
        "tick_value": 1.0,
        "initial_margin": 575.0,
        "maintenance_margin": 520.0,
        "last_updated": "2026-02-20",
        "market_type": "energy_futures",
    },
    "NG": {
        "name": "Micro Natural Gas (MNG)",
        "exchange": "NYMEX",
        "point_value": 100.0,
        "tick_size": 0.001,
        "tick_value": 0.10,
        "initial_margin": 575.0,
        "maintenance_margin": 520.0,
        "last_updated": "2026-02-20",
        "market_type": "energy_futures",
    },

    # --- Micro Metals ---
    "MGC": {
        "name": "Micro Gold",
        "exchange": "COMEX",
        "point_value": 10.0,
        "tick_size": 0.10,
        "tick_value": 1.0,
        "initial_margin": 1870.0,
        "maintenance_margin": 1700.0,
        "last_updated": "2026-02-20",
        "market_type": "metal_futures",
    },

    # --- CME Crypto Futures ---
    "MBT": {
        "name": "Micro Bitcoin (CME)",
        "exchange": "CME",
        "point_value": 0.1,       # 0.1 BTC per contract
        "tick_size": 5.0,
        "tick_value": 0.50,
        "initial_margin": 2500.0,
        "maintenance_margin": 2250.0,
        "last_updated": "2025-02-01",
        "market_type": "crypto_futures",
    },
    "XRP_FUT": {
        "name": "XRP Futures (CME)",
        "exchange": "CME",
        "point_value": 2500.0,    # 2,500 XRP per contract
        "tick_size": 0.0001,
        "tick_value": 0.25,
        "initial_margin": 1800.0,
        "maintenance_margin": 1620.0,
        "last_updated": "2025-02-01",
        "market_type": "crypto_futures",
    },
}


# =============================================================================
# PERPETUAL FUTURES MARGIN SPECS (percentage-based with leverage)
# =============================================================================

PERPETUAL_MARGIN_SPECS: Dict[str, Dict[str, Any]] = {
    "BTC-PERP": {
        "name": "Bitcoin Perpetual",
        "exchange": "PERPETUAL",
        "max_leverage": 50,
        "default_leverage": 10,
        "maintenance_margin_rate": 0.004,   # 0.4%
        "maker_fee": 0.0002,
        "taker_fee": 0.0006,
        "funding_interval_hours": 8,
        "market_type": "crypto_perp",
    },
    "ETH-PERP": {
        "name": "Ethereum Perpetual",
        "exchange": "PERPETUAL",
        "max_leverage": 50,
        "default_leverage": 10,
        "maintenance_margin_rate": 0.004,   # 0.4%
        "maker_fee": 0.0002,
        "taker_fee": 0.0006,
        "funding_interval_hours": 8,
        "market_type": "crypto_perp",
    },
    "XRP-PERP": {
        "name": "XRP Perpetual",
        "exchange": "PERPETUAL",
        "max_leverage": 25,
        "default_leverage": 5,
        "maintenance_margin_rate": 0.008,   # 0.8% (higher for alts)
        "maker_fee": 0.0002,
        "taker_fee": 0.0006,
        "funding_interval_hours": 8,
        "market_type": "crypto_perp",
    },
    "DOGE-PERP": {
        "name": "Dogecoin Perpetual",
        "exchange": "PERPETUAL",
        "max_leverage": 20,
        "default_leverage": 5,
        "maintenance_margin_rate": 0.01,    # 1.0% (higher for meme coins)
        "maker_fee": 0.0002,
        "taker_fee": 0.0006,
        "funding_interval_hours": 8,
        "market_type": "crypto_perp",
    },
    "SHIB-PERP": {
        "name": "Shiba Inu Perpetual",
        "exchange": "PERPETUAL",
        "max_leverage": 15,
        "default_leverage": 3,
        "maintenance_margin_rate": 0.015,   # 1.5% (highest for micro-cap)
        "maker_fee": 0.0002,
        "taker_fee": 0.0006,
        "funding_interval_hours": 8,
        "market_type": "crypto_perp",
    },
}


# =============================================================================
# BOT-TO-SPEC MAPPING
# =============================================================================

BOT_MARGIN_SPEC: Dict[str, str] = {
    # Stock Index Futures
    "VALOR": "MES",
    "PHOENIX": "MES",
    "HERMES": "MNQ",
    # CME Crypto Futures
    "AGAPE_BTC": "MBT",
    "AGAPE_XRP": "XRP_FUT",
    # Crypto Perpetuals
    "AGAPE_BTC_PERP": "BTC-PERP",
    "AGAPE_ETH_PERP": "ETH-PERP",
    "AGAPE_XRP_PERP": "XRP-PERP",
    "AGAPE_DOGE_PERP": "DOGE-PERP",
    "AGAPE_SHIB_PERP": "SHIB-PERP",
}


def get_spec_for_bot(bot_name: str) -> dict:
    """Get the margin spec for a given bot name."""
    spec_key = BOT_MARGIN_SPEC.get(bot_name)
    if not spec_key:
        return {}
    return FUTURES_MARGIN_SPECS.get(spec_key) or PERPETUAL_MARGIN_SPECS.get(spec_key, {})
