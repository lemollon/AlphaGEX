"""
Trading Configuration Module

Centralized configuration for AlphaGEX trading system.
"""

from .settings import (
    SYMBOL_CONFIG,
    RISK_CONFIG,
    POSITION_SIZING_CONFIG,
    STRATEGY_CONFIG,
    EXIT_CONFIG,
    MARKET_HOURS,
    DATA_PROVIDER_CONFIG,
    LOGGING_CONFIG,
    get_symbol_config,
    get_strategy_config,
    is_strategy_enabled,
)

__all__ = [
    'SYMBOL_CONFIG',
    'RISK_CONFIG',
    'POSITION_SIZING_CONFIG',
    'STRATEGY_CONFIG',
    'EXIT_CONFIG',
    'MARKET_HOURS',
    'DATA_PROVIDER_CONFIG',
    'LOGGING_CONFIG',
    'get_symbol_config',
    'get_strategy_config',
    'is_strategy_enabled',
]
