"""
Secure configuration management for AlphaGEX.

This module provides:
- Secure secrets handling (never exposed in logs or errors)
- Validated configuration with Pydantic
- Centralized access to all configuration values
- Environment-based configuration loading
"""

import os
import re
from typing import Any, Dict, Optional, List
from decimal import Decimal
from functools import lru_cache

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings


# =============================================================================
# CONSTANTS - Centralized hardcoded values that should be configurable
# =============================================================================

# Trading Capital
DEFAULT_STARTING_CAPITAL = Decimal('1000000.00')
DEFAULT_MAX_POSITION_SIZE_PCT = Decimal('0.10')  # 10% of capital
DEFAULT_RISK_PER_TRADE_PCT = Decimal('0.02')     # 2% risk per trade

# GEX Thresholds (in dollars)
GEX_THRESHOLDS = {
    'SPY': {
        'negative_squeeze': -1e9,
        'positive_breakdown': 2e9,
        'high_positive': 3e9,
        'extreme_negative': -3e9,
        'extreme_positive': 5e9
    },
    'QQQ': {
        'negative_squeeze': -5e8,
        'positive_breakdown': 1e9,
        'high_positive': 1.5e9,
        'extreme_negative': -1.5e9,
        'extreme_positive': 2.5e9
    },
    'IWM': {
        'negative_squeeze': -2e8,
        'positive_breakdown': 5e8,
        'high_positive': 8e8,
        'extreme_negative': -8e8,
        'extreme_positive': 1.5e9
    },
    'DEFAULT': {
        'negative_squeeze': -5e8,
        'positive_breakdown': 1e9,
        'high_positive': 1.5e9,
        'extreme_negative': -1.5e9,
        'extreme_positive': 3e9
    }
}

# Regime Thresholds
REGIME_THRESHOLDS = {
    'positive_gamma_pinning': 3e9,
    'moderate_positive': 1e9,
    'neutral_high': 0,
    'neutral_low': 0,
    'moderate_negative': -1e9,
    'extreme_negative': -3e9
}

# Market Hours (US/Central)
MARKET_HOURS = {
    'open_hour': 8,
    'open_minute': 30,
    'close_hour': 15,
    'close_minute': 0
}

# Risk Management
RISK_LIMITS = {
    'max_daily_loss_pct': Decimal('0.05'),      # 5% max daily loss
    'max_drawdown_pct': Decimal('0.20'),        # 20% max drawdown
    'max_position_count': 10,
    'max_exposure_pct': Decimal('0.50')         # 50% max exposure
}

# Cache Settings
CACHE_TTL = {
    'rsi': 300,           # 5 minutes
    'gex': 60,            # 1 minute
    'market_data': 30,    # 30 seconds
    'options_chain': 60   # 1 minute
}

# API Rate Limits
RATE_LIMITS = {
    'tradier': {'requests_per_minute': 60, 'burst': 10},
    'polygon': {'requests_per_minute': 5, 'burst': 1},
    'trading_volatility': {'requests_per_minute': 30, 'burst': 5}
}


# =============================================================================
# SECURE SETTINGS
# =============================================================================

class SecureSettings(BaseSettings):
    """
    Secure configuration with environment variable loading.

    IMPORTANT: This class handles secrets securely:
    - Never logs or prints secret values
    - Masks secrets in __str__ and __repr__
    - Validates format without exposing values
    """

    # Database
    database_url: str = Field(default='', description="PostgreSQL connection URL")

    # API Keys
    trading_volatility_api_key: str = Field(default='', description="TradingVolatility API key")
    tradier_api_key: str = Field(default='', description="Tradier API key")
    polygon_api_key: str = Field(default='', description="Polygon.io API key")
    anthropic_api_key: str = Field(default='', description="Anthropic Claude API key")

    # Trading Configuration
    starting_capital: Decimal = Field(default=DEFAULT_STARTING_CAPITAL)
    trading_mode: str = Field(default='paper', description="Trading mode: paper or live")
    auto_execute: bool = Field(default=False, description="Auto-execute trades")

    # Feature Flags
    enable_ai_analysis: bool = Field(default=True)
    enable_autonomous_trading: bool = Field(default=True)
    signal_only_mode: bool = Field(default=False)

    # Environment
    environment: str = Field(default='development')
    debug: bool = Field(default=False)

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        case_sensitive = False

    @field_validator('database_url')
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate database URL format without exposing credentials."""
        if not v:
            return v
        if not v.startswith(('postgresql://', 'postgres://')):
            raise ValueError("DATABASE_URL must use postgresql:// scheme")
        return v

    @field_validator('trading_volatility_api_key', 'tradier_api_key', 'polygon_api_key')
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Validate API key format without exposing the key."""
        if not v:
            return v
        # Basic format validation - alphanumeric with dashes/underscores
        if not re.match(r'^[a-zA-Z0-9\-_]{10,}$', v):
            raise ValueError("Invalid API key format")
        return v

    @field_validator('trading_mode')
    @classmethod
    def validate_trading_mode(cls, v: str) -> str:
        """Validate trading mode."""
        v = v.lower()
        if v not in ('paper', 'live'):
            raise ValueError("trading_mode must be 'paper' or 'live'")
        return v

    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment."""
        v = v.lower()
        if v not in ('development', 'staging', 'production'):
            raise ValueError("environment must be 'development', 'staging', or 'production'")
        return v

    def __str__(self) -> str:
        """String representation that hides secrets."""
        return (
            f"SecureSettings("
            f"database=***configured***, "
            f"trading_mode={self.trading_mode}, "
            f"environment={self.environment})"
        )

    def __repr__(self) -> str:
        return self.__str__()

    def is_configured(self) -> bool:
        """Check if minimum configuration is present."""
        return bool(self.database_url)

    def get_masked_database_url(self) -> str:
        """Get database URL with password masked."""
        if not self.database_url:
            return "NOT_CONFIGURED"
        # Mask the password in the URL
        masked = re.sub(r':([^:@]+)@', ':***@', self.database_url)
        return masked

    def has_api_key(self, key_name: str) -> bool:
        """Check if an API key is configured without exposing it."""
        key_map = {
            'trading_volatility': self.trading_volatility_api_key,
            'tradier': self.tradier_api_key,
            'polygon': self.polygon_api_key,
            'anthropic': self.anthropic_api_key
        }
        key = key_map.get(key_name.lower())
        return bool(key and len(key) > 10)


# =============================================================================
# CONFIGURATION ACCESS
# =============================================================================

@lru_cache(maxsize=1)
def get_settings() -> SecureSettings:
    """
    Get application settings (cached).

    Returns:
        SecureSettings instance loaded from environment
    """
    return SecureSettings()


def get_gex_thresholds(symbol: str = 'SPY') -> Dict[str, float]:
    """
    Get GEX thresholds for a symbol.

    Args:
        symbol: Trading symbol (SPY, QQQ, IWM, etc.)

    Returns:
        Dictionary of GEX threshold values
    """
    symbol = symbol.upper()
    return GEX_THRESHOLDS.get(symbol, GEX_THRESHOLDS['DEFAULT']).copy()


def get_regime_thresholds() -> Dict[str, float]:
    """Get market regime thresholds."""
    return REGIME_THRESHOLDS.copy()


def get_risk_limits() -> Dict[str, Any]:
    """Get risk management limits."""
    return {
        'max_daily_loss_pct': float(RISK_LIMITS['max_daily_loss_pct']),
        'max_drawdown_pct': float(RISK_LIMITS['max_drawdown_pct']),
        'max_position_count': RISK_LIMITS['max_position_count'],
        'max_exposure_pct': float(RISK_LIMITS['max_exposure_pct'])
    }


def get_cache_ttl(cache_type: str) -> int:
    """Get cache TTL in seconds for a cache type."""
    return CACHE_TTL.get(cache_type, 60)


def get_rate_limit(api_name: str) -> Dict[str, int]:
    """Get rate limit settings for an API."""
    return RATE_LIMITS.get(api_name.lower(), {'requests_per_minute': 10, 'burst': 1})


# =============================================================================
# CONFIGURATION VALIDATION
# =============================================================================

def validate_configuration() -> Dict[str, Any]:
    """
    Validate all configuration and return status report.

    Returns:
        Dictionary with validation results for each component
    """
    settings = get_settings()
    results = {
        'valid': True,
        'components': {},
        'warnings': [],
        'errors': []
    }

    # Check database
    if settings.database_url:
        results['components']['database'] = {
            'configured': True,
            'url_masked': settings.get_masked_database_url()
        }
    else:
        results['components']['database'] = {'configured': False}
        results['errors'].append("DATABASE_URL not configured")
        results['valid'] = False

    # Check API keys
    api_keys = [
        ('trading_volatility', 'TradingVolatility API'),
        ('tradier', 'Tradier API'),
        ('polygon', 'Polygon API'),
        ('anthropic', 'Anthropic Claude API')
    ]

    for key_id, key_name in api_keys:
        is_configured = settings.has_api_key(key_id)
        results['components'][key_id] = {'configured': is_configured}
        if not is_configured:
            results['warnings'].append(f"{key_name} key not configured")

    # Check trading settings
    results['components']['trading'] = {
        'mode': settings.trading_mode,
        'auto_execute': settings.auto_execute,
        'signal_only': settings.signal_only_mode,
        'starting_capital': float(settings.starting_capital)
    }

    if settings.trading_mode == 'live' and settings.auto_execute:
        results['warnings'].append("LIVE trading with auto_execute enabled - use with caution!")

    # Environment check
    results['components']['environment'] = {
        'name': settings.environment,
        'debug': settings.debug
    }

    if settings.environment == 'production' and settings.debug:
        results['warnings'].append("Debug mode enabled in production")

    return results


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_config_for_logging() -> Dict[str, Any]:
    """
    Get configuration summary safe for logging (no secrets).

    Returns:
        Dictionary of non-sensitive configuration values
    """
    settings = get_settings()
    return {
        'environment': settings.environment,
        'trading_mode': settings.trading_mode,
        'auto_execute': settings.auto_execute,
        'signal_only_mode': settings.signal_only_mode,
        'starting_capital': float(settings.starting_capital),
        'database_configured': bool(settings.database_url),
        'api_keys_configured': {
            'trading_volatility': settings.has_api_key('trading_volatility'),
            'tradier': settings.has_api_key('tradier'),
            'polygon': settings.has_api_key('polygon'),
            'anthropic': settings.has_api_key('anthropic')
        }
    }


def get_starting_capital() -> Decimal:
    """Get starting capital from configuration."""
    settings = get_settings()
    return settings.starting_capital


def is_production() -> bool:
    """Check if running in production environment."""
    settings = get_settings()
    return settings.environment == 'production'


def is_live_trading() -> bool:
    """Check if live trading is enabled."""
    settings = get_settings()
    return settings.trading_mode == 'live'
