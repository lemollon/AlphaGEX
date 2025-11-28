"""
AlphaGEX Trading Configuration

Centralized configuration for all trading parameters.
This is the SINGLE source of truth for trading settings.
"""

# Supported symbols with their default configurations
SYMBOL_CONFIG = {
    'SPY': {
        'multiplier': 100,
        'default_capital': 1_000_000,
        'max_position_pct': 0.05,  # 5% max per position
        'cost_model': 'paper',
        'settlement': 'T+1',  # ETF
    },
    'SPX': {
        'multiplier': 100,
        'default_capital': 100_000_000,
        'max_position_pct': 0.05,  # 5% max per position
        'cost_model': 'institutional',
        'settlement': 'cash',  # Cash settled index
    },
    'QQQ': {
        'multiplier': 100,
        'default_capital': 1_000_000,
        'max_position_pct': 0.05,
        'cost_model': 'paper',
        'settlement': 'T+1',  # ETF
    },
}

# Trading risk parameters
RISK_CONFIG = {
    'max_risk_per_trade': 0.02,  # 2% of capital
    'max_daily_trades': 3,
    'max_daily_loss_pct': 0.05,  # 5% max daily loss
    'max_drawdown_pct': 0.15,  # 15% max drawdown
    'min_kelly_fraction': 0.25,  # Min Kelly to trade
    'kelly_multiplier': 0.5,  # Half-Kelly for safety
}

# Position sizing parameters
POSITION_SIZING_CONFIG = {
    'min_win_rate': 0.45,  # Min 45% win rate
    'min_profit_factor': 1.0,  # Min 1.0 profit factor
    'min_sample_size': 10,  # Min trades for statistics
    'default_position_pct': 0.01,  # 1% if no backtest data
    'max_position_pct': 0.05,  # Never exceed 5%
}

# Strategy configurations
STRATEGY_CONFIG = {
    'IRON_CONDOR': {
        'enabled': True,
        'min_credit': 0.50,
        'max_width': 10,
        'delta_range': (0.15, 0.30),
        'dte_range': (7, 45),
        'regimes': ['negative_gamma', 'pinned'],
    },
    'BULL_PUT_SPREAD': {
        'enabled': True,
        'min_credit': 0.30,
        'max_width': 5,
        'delta_range': (0.20, 0.35),
        'dte_range': (7, 30),
        'regimes': ['positive_gamma', 'trending_up'],
    },
    'BEAR_CALL_SPREAD': {
        'enabled': True,
        'min_credit': 0.30,
        'max_width': 5,
        'delta_range': (0.20, 0.35),
        'dte_range': (7, 30),
        'regimes': ['negative_gamma', 'trending_down'],
    },
    'DIRECTIONAL_PUT': {
        'enabled': True,
        'max_cost': 5.00,
        'delta_range': (0.30, 0.50),
        'dte_range': (7, 21),
        'regimes': ['high_volatility', 'crash_risk'],
    },
    'DIRECTIONAL_CALL': {
        'enabled': True,
        'max_cost': 5.00,
        'delta_range': (0.30, 0.50),
        'dte_range': (7, 21),
        'regimes': ['low_volatility', 'momentum_up'],
    },
    'ATM_STRADDLE': {
        'enabled': True,
        'max_cost_pct': 0.03,  # 3% of spot
        'dte_range': (5, 14),
        'regimes': ['high_volatility', 'breakout_expected'],
    },
}

# Exit strategy parameters
EXIT_CONFIG = {
    'profit_target_pct': 0.50,  # 50% of max profit
    'stop_loss_pct': 2.0,  # 200% of credit received
    'time_exit_dte': 1,  # Close at 1 DTE
    'gamma_risk_exit': True,  # Exit on high gamma risk
}

# Market hours (Central Time)
MARKET_HOURS = {
    'pre_market_start': '07:00',
    'market_open': '08:30',
    'market_close': '15:00',
    'post_market_end': '17:00',
    'timezone': 'America/Chicago',
}

# Data provider configuration
DATA_PROVIDER_CONFIG = {
    'primary': 'tradier',
    'fallback': 'polygon',
    'gex_source': 'trading_volatility',
    'cache_ttl_seconds': 60,
}

# Logging configuration
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    'date_format': '%Y-%m-%d %H:%M:%S',
}


def get_symbol_config(symbol: str) -> dict:
    """Get configuration for a specific symbol."""
    return SYMBOL_CONFIG.get(symbol, SYMBOL_CONFIG['SPY'])


def get_strategy_config(strategy: str) -> dict:
    """Get configuration for a specific strategy."""
    return STRATEGY_CONFIG.get(strategy, {})


def is_strategy_enabled(strategy: str) -> bool:
    """Check if a strategy is enabled."""
    config = get_strategy_config(strategy)
    return config.get('enabled', False)
