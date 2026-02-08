"""
unified_config.py - Centralized Configuration Module
=====================================================

This module consolidates all configuration from across the AlphaGEX codebase.
Import from here for any configuration needs.

Usage:
    from unified_config import Config, TradingConfig, APIConfig

    # Access via class
    max_risk = TradingConfig.MAX_RISK_PER_TRADE

    # Or via unified Config object
    max_risk = Config.trading.max_risk_per_trade

Author: AlphaGEX
Date: 2025-11-27
"""

import os
from typing import Dict, List, Optional, Any, TypedDict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# Load environment variables from .env file BEFORE any os.getenv() calls
from dotenv import load_dotenv
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

# Import existing configs (for backward compatibility)
from config import (
    VIXConfig,
    GammaDecayConfig,
    GEXThresholdConfig,
    DirectionalPredictionConfig,
    RiskLevelConfig,
    TradeSetupConfig,
    RateLimitConfig,
    ImpliedVolatilityConfig,
    SystemConfig,
    get_gex_thresholds,
    get_gamma_decay_pattern,
    get_vix_fallback,
)

# Import MM_STATES and STRATEGIES with fallback
try:
    from db.config_and_database import MM_STATES, STRATEGIES
except ImportError:
    # Fallback if database dependencies not available
    MM_STATES = {
        'TRAPPED': {'threshold': -2e9, 'behavior': 'Forced buying on rallies', 'confidence': 85, 'action': 'BUY'},
        'DEFENDING': {'threshold': 1e9, 'behavior': 'Selling rallies aggressively', 'confidence': 70, 'action': 'FADE'},
        'HUNTING': {'threshold': -1e9, 'behavior': 'Aggressive positioning', 'confidence': 60, 'action': 'WAIT'},
        'PANICKING': {'threshold': -3e9, 'behavior': 'Capitulation', 'confidence': 90, 'action': 'RIDE'},
        'NEUTRAL': {'threshold': 0, 'behavior': 'Balanced positioning', 'confidence': 50, 'action': 'RANGE'},
    }
    # Core strategies with profitability stats
    STRATEGIES = {
        'IRON_CONDOR': {'win_rate': 0.72, 'risk_reward': 0.3, 'dte_range': [5, 14]},
        'BULL_PUT_SPREAD': {'win_rate': 0.70, 'risk_reward': 0.4, 'dte_range': [5, 21]},
        'BEAR_CALL_SPREAD': {'win_rate': 0.68, 'risk_reward': 0.4, 'dte_range': [5, 21]},
        'BULLISH_CALL_SPREAD': {'win_rate': 0.65, 'risk_reward': 2.0, 'dte_range': [3, 14]},
        'BEARISH_PUT_SPREAD': {'win_rate': 0.62, 'risk_reward': 2.0, 'dte_range': [3, 14]},
        'NEGATIVE_GEX_SQUEEZE': {'win_rate': 0.68, 'risk_reward': 3.0, 'dte_range': [0, 5]},
    }


# ============================================================================
# Environment Variable Helpers
# ============================================================================

def env_float(key: str, default: float) -> float:
    """Get float from environment variable with default"""
    try:
        return float(os.getenv(key, default))
    except (ValueError, TypeError):
        return default


def env_int(key: str, default: int) -> int:
    """Get int from environment variable with default"""
    try:
        return int(os.getenv(key, default))
    except (ValueError, TypeError):
        return default


def env_bool(key: str, default: bool) -> bool:
    """Get bool from environment variable with default"""
    val = os.getenv(key, str(default)).lower()
    return val in ('true', '1', 'yes', 'on')


def env_list(key: str, default: List[str], separator: str = ',') -> List[str]:
    """Get list from environment variable with default"""
    val = os.getenv(key)
    if val:
        return [item.strip() for item in val.split(separator)]
    return default


# ============================================================================
# API Configuration
# ============================================================================

class APIConfig:
    """API endpoints and credentials configuration"""

    # Trading Volatility API
    TRADING_VOLATILITY_BASE_URL: str = os.getenv(
        'TRADING_VOLATILITY_BASE_URL',
        'https://stocks.tradingvolatility.net/api'
    )
    TRADING_VOLATILITY_API_KEY: Optional[str] = os.getenv('TRADING_VOLATILITY_API_KEY')

    # Polygon.io
    POLYGON_API_KEY: Optional[str] = os.getenv('POLYGON_API_KEY')
    POLYGON_BASE_URL: str = 'https://api.polygon.io'

    # Tradier - PRODUCTION credentials (for live trading and real market data)
    # TRADIER_PROD_* takes priority, falls back to TRADIER_API_KEY if not sandbox credentials
    TRADIER_PROD_API_KEY: Optional[str] = os.getenv('TRADIER_PROD_API_KEY')
    TRADIER_PROD_ACCOUNT_ID: Optional[str] = os.getenv('TRADIER_PROD_ACCOUNT_ID')
    TRADIER_API_KEY: Optional[str] = os.getenv('TRADIER_API_KEY')
    TRADIER_ACCOUNT_ID: Optional[str] = os.getenv('TRADIER_ACCOUNT_ID')
    TRADIER_SANDBOX: bool = env_bool('TRADIER_SANDBOX', False)  # Default to PRODUCTION

    # Tradier - SANDBOX credentials (for paper trading - separate API key from Tradier)
    # Get sandbox credentials from: https://developer.tradier.com/user/applications
    TRADIER_SANDBOX_API_KEY: Optional[str] = os.getenv('TRADIER_SANDBOX_API_KEY')
    TRADIER_SANDBOX_ACCOUNT_ID: Optional[str] = os.getenv('TRADIER_SANDBOX_ACCOUNT_ID')

    # Tradier - FORTRESS Second Sandbox Account (for mirroring trades to additional account)
    # FORTRESS will execute the same trades on BOTH sandbox accounts
    TRADIER_FORTRESS_SANDBOX_API_KEY_2: Optional[str] = os.getenv('TRADIER_FORTRESS_SANDBOX_API_KEY_2')
    TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_2: Optional[str] = os.getenv('TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_2')

    @classmethod
    def get_tradier_prod_credentials(cls) -> tuple:
        """Get production credentials, checking TRADIER_PROD_* first, then TRADIER_API_KEY"""
        api_key = cls.TRADIER_PROD_API_KEY or cls.TRADIER_API_KEY
        account_id = cls.TRADIER_PROD_ACCOUNT_ID or cls.TRADIER_ACCOUNT_ID
        return api_key, account_id

    # Claude AI
    ANTHROPIC_API_KEY: Optional[str] = os.getenv('ANTHROPIC_API_KEY')
    CLAUDE_MODEL: str = os.getenv('CLAUDE_MODEL', 'claude-sonnet-4-5-latest')

    # Rate Limits
    TRADING_VOL_RATE_LIMIT: int = env_int('TRADING_VOL_RATE_LIMIT', 20)  # calls per minute
    POLYGON_RATE_LIMIT: int = env_int('POLYGON_RATE_LIMIT', 5)  # free tier

    @classmethod
    def is_configured(cls, api: str) -> bool:
        """Check if an API is properly configured"""
        configs = {
            'trading_volatility': cls.TRADING_VOLATILITY_API_KEY,
            'polygon': cls.POLYGON_API_KEY,
            'tradier': cls.TRADIER_API_KEY,
            'anthropic': cls.ANTHROPIC_API_KEY,
        }
        return bool(configs.get(api))


# ============================================================================
# Trading Configuration
# ============================================================================

class TradingConfig:
    """Core trading parameters"""

    # Risk Management
    MAX_RISK_PER_TRADE: float = env_float('MAX_RISK_PER_TRADE', 0.02)  # 2%
    MAX_PORTFOLIO_RISK: float = env_float('MAX_PORTFOLIO_RISK', 0.10)  # 10%
    MAX_POSITION_SIZE: float = env_float('MAX_POSITION_SIZE', 0.25)  # 25% of capital
    DEFAULT_STOP_LOSS: float = env_float('DEFAULT_STOP_LOSS', 0.50)  # 50% of premium
    DEFAULT_PROFIT_TARGET: float = env_float('DEFAULT_PROFIT_TARGET', 1.00)  # 100% of premium

    # Kelly Criterion
    KELLY_FRACTION: float = env_float('KELLY_FRACTION', 0.25)  # Use 25% of full Kelly
    MIN_KELLY_BET: float = env_float('MIN_KELLY_BET', 0.01)  # 1% minimum
    MAX_KELLY_BET: float = env_float('MAX_KELLY_BET', 0.15)  # 15% maximum

    # Position Limits
    MAX_CONTRACTS_PER_TRADE: int = env_int('MAX_CONTRACTS_PER_TRADE', 100)
    MIN_CONTRACTS_PER_TRADE: int = env_int('MIN_CONTRACTS_PER_TRADE', 1)
    MAX_OPEN_POSITIONS: int = env_int('MAX_OPEN_POSITIONS', 10)

    # Time-based Rules
    NO_TRADES_BEFORE_MARKET_MINUTES: int = env_int('NO_TRADES_BEFORE_MARKET_MINUTES', 15)
    NO_TRADES_AFTER_MARKET_MINUTES: int = env_int('NO_TRADES_AFTER_MARKET_MINUTES', 15)

    # Signal Thresholds
    MIN_WIN_RATE: float = env_float('MIN_WIN_RATE', 0.50)  # 50%
    MIN_CONFIDENCE: float = env_float('MIN_CONFIDENCE', 0.65)  # 65%
    MIN_EDGE: float = env_float('MIN_EDGE', 0.05)  # 5% edge required


# ============================================================================
# GEX Configuration
# ============================================================================

class GEXConfig:
    """Gamma Exposure (GEX) thresholds and parameters"""

    # GEX Magnitude Thresholds (in dollars)
    EXTREME_NEGATIVE_GEX: float = env_float('EXTREME_NEGATIVE_GEX', -3e9)
    HIGH_NEGATIVE_GEX: float = env_float('HIGH_NEGATIVE_GEX', -2e9)
    MODERATE_NEGATIVE_GEX: float = env_float('MODERATE_NEGATIVE_GEX', -1e9)
    NEUTRAL_GEX: float = 0.0
    MODERATE_POSITIVE_GEX: float = env_float('MODERATE_POSITIVE_GEX', 1e9)
    HIGH_POSITIVE_GEX: float = env_float('HIGH_POSITIVE_GEX', 2e9)
    EXTREME_POSITIVE_GEX: float = env_float('EXTREME_POSITIVE_GEX', 3e9)

    # Adaptive Thresholds
    USE_ADAPTIVE_THRESHOLDS: bool = env_bool('USE_ADAPTIVE_GEX_THRESHOLDS', True)
    ADAPTIVE_LOOKBACK_DAYS: int = env_int('GEX_ADAPTIVE_LOOKBACK_DAYS', 20)

    # Wall Proximity
    WALL_PROXIMITY_THRESHOLD: float = env_float('WALL_PROXIMITY_THRESHOLD', 1.5)  # 1.5%

    @classmethod
    def get_regime(cls, net_gex: float) -> str:
        """Get GEX regime classification"""
        if net_gex <= cls.EXTREME_NEGATIVE_GEX:
            return 'EXTREME_NEGATIVE'
        elif net_gex <= cls.HIGH_NEGATIVE_GEX:
            return 'HIGH_NEGATIVE'
        elif net_gex <= cls.MODERATE_NEGATIVE_GEX:
            return 'MODERATE_NEGATIVE'
        elif net_gex >= cls.EXTREME_POSITIVE_GEX:
            return 'EXTREME_POSITIVE'
        elif net_gex >= cls.HIGH_POSITIVE_GEX:
            return 'HIGH_POSITIVE'
        elif net_gex >= cls.MODERATE_POSITIVE_GEX:
            return 'MODERATE_POSITIVE'
        else:
            return 'NEUTRAL'


# ============================================================================
# VIX Configuration
# ============================================================================

class VIXConfiguration:
    """VIX thresholds and parameters (renamed to avoid conflict with config.py)"""

    # VIX Thresholds
    LOW: float = env_float('VIX_LOW_THRESHOLD', 15.0)
    ELEVATED: float = env_float('VIX_ELEVATED_THRESHOLD', 20.0)
    HIGH: float = env_float('VIX_HIGH_THRESHOLD', 30.0)
    EXTREME: float = env_float('VIX_EXTREME_THRESHOLD', 40.0)

    # Defaults
    DEFAULT_VALUE: float = env_float('VIX_DEFAULT', 18.0)
    HISTORICAL_AVERAGE: float = 16.5
    RECENT_AVERAGE: float = 18.0

    # VIX Stress Multipliers (for position sizing)
    STRESS_MULTIPLIERS: Dict[str, float] = {
        'low': 1.2,       # VIX < 15: can be more aggressive
        'normal': 1.0,    # VIX 15-20: normal sizing
        'elevated': 0.75, # VIX 20-30: reduce size 25%
        'high': 0.50,     # VIX 30-40: half size
        'extreme': 0.25,  # VIX > 40: quarter size
    }

    @classmethod
    def get_stress_level(cls, vix: float) -> str:
        """Get VIX stress level classification"""
        if vix < cls.LOW:
            return 'low'
        elif vix < cls.ELEVATED:
            return 'normal'
        elif vix < cls.HIGH:
            return 'elevated'
        elif vix < cls.EXTREME:
            return 'high'
        else:
            return 'extreme'

    @classmethod
    def get_position_multiplier(cls, vix: float) -> float:
        """Get position size multiplier based on VIX"""
        stress_level = cls.get_stress_level(vix)
        return cls.STRESS_MULTIPLIERS.get(stress_level, 1.0)


# ============================================================================
# Database Configuration
# ============================================================================

class DatabaseConfig:
    """Database connection configuration"""

    DATABASE_URL: Optional[str] = os.getenv('DATABASE_URL')
    DB_POOL_SIZE: int = env_int('DB_POOL_SIZE', 5)
    DB_MAX_OVERFLOW: int = env_int('DB_MAX_OVERFLOW', 10)
    DB_POOL_TIMEOUT: int = env_int('DB_POOL_TIMEOUT', 30)

    @classmethod
    def is_configured(cls) -> bool:
        """Check if database is configured"""
        return bool(cls.DATABASE_URL)


# ============================================================================
# Feature Flags
# ============================================================================

class FeatureFlags:
    """Feature toggles for enabling/disabling functionality"""

    ENABLE_AUTONOMOUS_TRADING: bool = env_bool('ENABLE_AUTONOMOUS_TRADING', True)
    ENABLE_SPX_TRADER: bool = env_bool('ENABLE_SPX_TRADER', True)
    ENABLE_PSYCHOLOGY_DETECTION: bool = env_bool('ENABLE_PSYCHOLOGY_DETECTION', True)
    ENABLE_AI_RECOMMENDATIONS: bool = env_bool('ENABLE_AI_RECOMMENDATIONS', True)
    ENABLE_BACKTESTING: bool = env_bool('ENABLE_BACKTESTING', True)
    ENABLE_NOTIFICATIONS: bool = env_bool('ENABLE_NOTIFICATIONS', True)
    ENABLE_ADAPTIVE_THRESHOLDS: bool = env_bool('ENABLE_ADAPTIVE_THRESHOLDS', True)
    ENABLE_DEBUG_LOGGING: bool = env_bool('ENABLE_DEBUG_LOGGING', False)

    # Experimental
    ENABLE_ML_PREDICTIONS: bool = env_bool('ENABLE_ML_PREDICTIONS', False)
    ENABLE_LIVE_TRADING: bool = env_bool('ENABLE_LIVE_TRADING', False)


# ============================================================================
# Unified Config Object
# ============================================================================

@dataclass
class UnifiedConfig:
    """
    Unified configuration access point.

    Usage:
        from unified_config import Config

        # Access nested configs
        Config.api.POLYGON_API_KEY
        Config.trading.MAX_RISK_PER_TRADE
        Config.gex.get_regime(-2.5e9)
    """
    api: type = field(default=APIConfig)
    trading: type = field(default=TradingConfig)
    gex: type = field(default=GEXConfig)
    vix: type = field(default=VIXConfiguration)
    database: type = field(default=DatabaseConfig)
    features: type = field(default=FeatureFlags)

    # Legacy configs (for backward compatibility)
    vix_config: type = field(default=VIXConfig)
    gamma_decay: type = field(default=GammaDecayConfig)
    gex_thresholds: type = field(default=GEXThresholdConfig)
    directional: type = field(default=DirectionalPredictionConfig)
    risk_levels: type = field(default=RiskLevelConfig)
    trade_setup: type = field(default=TradeSetupConfig)
    rate_limit: type = field(default=RateLimitConfig)
    iv_config: type = field(default=ImpliedVolatilityConfig)
    system: type = field(default=SystemConfig)

    # Strategy and MM state configs
    mm_states: Dict = field(default_factory=lambda: MM_STATES)
    strategies: Dict = field(default_factory=lambda: STRATEGIES)


# Create singleton instance
Config = UnifiedConfig()


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    # New unified config
    'Config',
    'UnifiedConfig',
    'APIConfig',
    'TradingConfig',
    'GEXConfig',
    'VIXConfiguration',
    'DatabaseConfig',
    'FeatureFlags',

    # Legacy configs (backward compatibility)
    'VIXConfig',
    'GammaDecayConfig',
    'GEXThresholdConfig',
    'DirectionalPredictionConfig',
    'RiskLevelConfig',
    'TradeSetupConfig',
    'RateLimitConfig',
    'ImpliedVolatilityConfig',
    'SystemConfig',
    'MM_STATES',
    'STRATEGIES',

    # Helper functions
    'get_gex_thresholds',
    'get_gamma_decay_pattern',
    'get_vix_fallback',
    'env_float',
    'env_int',
    'env_bool',
    'env_list',
]
