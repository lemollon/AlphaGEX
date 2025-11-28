#!/usr/bin/env python3
"""
AlphaGEX System Verification Script
Run this to verify all components are working after refactoring.

Usage (on Render or locally with DATABASE_URL set):
    python verify_system.py

Returns exit code 0 if all critical checks pass, 1 otherwise.
"""

import sys
import os

# Results tracking
results = {
    'passed': [],
    'failed': [],
    'warnings': []
}


def check(name, condition, critical=True):
    """Record a check result."""
    if condition:
        results['passed'].append(name)
        print(f"  ✅ {name}")
        return True
    else:
        if critical:
            results['failed'].append(name)
            print(f"  ❌ {name}")
        else:
            results['warnings'].append(name)
            print(f"  ⚠️  {name}")
        return False


def section(title):
    """Print section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


# =============================================================================
# 1. ENVIRONMENT CHECKS
# =============================================================================
section("1. ENVIRONMENT VARIABLES")

check("DATABASE_URL set", os.environ.get('DATABASE_URL'), critical=True)
check("TRADIER_API_KEY set", os.environ.get('TRADIER_API_KEY'), critical=False)
check("POLYGON_API_KEY set", os.environ.get('POLYGON_API_KEY'), critical=False)
check("TRADING_VOL_API_KEY set", os.environ.get('TRADING_VOL_API_KEY'), critical=False)

# =============================================================================
# 2. DATABASE CONNECTION
# =============================================================================
section("2. DATABASE CONNECTION")

try:
    from database_adapter import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    cursor.fetchone()
    cursor.close()
    conn.close()
    check("Database connection works", True)
except Exception as e:
    check(f"Database connection works ({e})", False)

# =============================================================================
# 3. CORE MODULE IMPORTS
# =============================================================================
section("3. CORE MODULE IMPORTS")

# Trading module
try:
    from trading import get_trader, get_spy_trader, get_spx_trader
    from trading.config import SYMBOL_CONFIG, RISK_CONFIG, STRATEGY_CONFIG
    check("trading module imports", True)
except Exception as e:
    check(f"trading module imports ({e})", False)

# Trading mixins
try:
    from trading.mixins import (
        PositionSizerMixin,
        TradeExecutorMixin,
        PositionManagerMixin,
        PerformanceTrackerMixin,
        RiskManagerMixin
    )
    check("trading.mixins imports", True)
except Exception as e:
    check(f"trading.mixins imports ({e})", False)

# Autonomous trader
try:
    from core.autonomous_paper_trader import AutonomousPaperTrader
    import inspect
    sig = inspect.signature(AutonomousPaperTrader.__init__)
    has_symbol = 'symbol' in sig.parameters
    has_capital = 'capital' in sig.parameters
    check(f"AutonomousPaperTrader imports (symbol={has_symbol}, capital={has_capital})",
          has_symbol and has_capital)
except Exception as e:
    check(f"AutonomousPaperTrader imports ({e})", False)

# Market regime classifier
try:
    from core.market_regime_classifier import (
        MarketRegimeClassifier,
        RegimeClassification,
        MarketAction,
        get_classifier
    )
    check("market_regime_classifier imports", True)
except Exception as e:
    check(f"market_regime_classifier imports ({e})", False)

# Strategy stats
try:
    from core.strategy_stats import get_strategy_stats, get_recent_changes
    check("strategy_stats imports", True)
except Exception as e:
    check(f"strategy_stats imports ({e})", False)

# Backtest framework
try:
    from backtest.backtest_framework import BacktestBase, BacktestResults, Trade
    check("backtest_framework imports", True)
except Exception as e:
    check(f"backtest_framework imports ({e})", False)

# Unified data provider
try:
    from data.unified_data_provider import get_data_provider, get_quote, get_price
    check("unified_data_provider imports", True)
except Exception as e:
    check(f"unified_data_provider imports ({e})", False)

# =============================================================================
# 4. TRADER INITIALIZATION
# =============================================================================
section("4. TRADER INITIALIZATION")

try:
    from core.autonomous_paper_trader import AutonomousPaperTrader

    # Test SPY trader
    spy_trader = AutonomousPaperTrader(symbol='SPY', capital=1_000_000)
    check(f"SPY trader initializes (capital=${spy_trader.starting_capital:,})",
          spy_trader.symbol == 'SPY')

    # Test SPX trader
    spx_trader = AutonomousPaperTrader(symbol='SPX', capital=100_000_000)
    check(f"SPX trader initializes (capital=${spx_trader.starting_capital:,})",
          spx_trader.symbol == 'SPX')

    # Check MRO (mixins properly inherited)
    mro = [c.__name__ for c in AutonomousPaperTrader.__mro__[:7]]
    has_mixins = all(m in mro for m in ['PositionSizerMixin', 'TradeExecutorMixin',
                                         'PositionManagerMixin', 'PerformanceTrackerMixin',
                                         'RiskManagerMixin'])
    check(f"Mixins in MRO: {mro[:6]}", has_mixins)

except Exception as e:
    check(f"Trader initialization failed ({e})", False)

# =============================================================================
# 5. CONFIGURATION
# =============================================================================
section("5. CONFIGURATION")

try:
    from trading.config import (
        SYMBOL_CONFIG, RISK_CONFIG, POSITION_SIZING_CONFIG,
        STRATEGY_CONFIG, get_symbol_config, is_strategy_enabled
    )

    check(f"Symbols configured: {list(SYMBOL_CONFIG.keys())}",
          'SPY' in SYMBOL_CONFIG and 'SPX' in SYMBOL_CONFIG)

    check(f"Risk config: max_risk={RISK_CONFIG.get('max_risk_per_trade', 0)*100}%",
          RISK_CONFIG.get('max_risk_per_trade', 0) > 0)

    check(f"Strategies configured: {len(STRATEGY_CONFIG)} strategies",
          len(STRATEGY_CONFIG) > 0)

    spy_config = get_symbol_config('SPY')
    check(f"SPY config: capital=${spy_config.get('default_capital', 0):,}",
          spy_config.get('default_capital', 0) > 0)

    check("Iron Condor enabled", is_strategy_enabled('IRON_CONDOR'))

except Exception as e:
    check(f"Configuration failed ({e})", False)

# =============================================================================
# 6. DATA PROVIDERS
# =============================================================================
section("6. DATA PROVIDERS")

# Tradier
try:
    from data.unified_data_provider import get_data_provider
    provider = get_data_provider()
    quote = provider.get_quote('SPY')
    has_price = quote and quote.last > 0
    check(f"Tradier quote: SPY ${quote.last if quote else 'N/A'}", has_price, critical=False)
except Exception as e:
    check(f"Tradier quote ({e})", False, critical=False)

# Polygon
try:
    from data.polygon_data_fetcher import polygon_fetcher
    price = polygon_fetcher.get_current_price('SPY')
    check(f"Polygon price: SPY ${price if price else 'N/A'}",
          price and price > 0, critical=False)
except Exception as e:
    check(f"Polygon price ({e})", False, critical=False)

# Trading Volatility API
try:
    from core_classes_and_engines import TradingVolatilityAPI
    api = TradingVolatilityAPI()
    gex = api.get_net_gamma('SPY')
    has_gex = gex and gex.get('net_gex') is not None
    check(f"Trading Vol GEX: {gex.get('net_gex', 'N/A') if gex else 'N/A'}",
          has_gex, critical=False)
except Exception as e:
    check(f"Trading Vol GEX ({e})", False, critical=False)

# =============================================================================
# 7. DATABASE TABLES
# =============================================================================
section("7. DATABASE TABLES")

try:
    from database_adapter import get_connection
    conn = get_connection()
    cursor = conn.cursor()

    tables_to_check = [
        'autonomous_config',
        'autonomous_open_positions',
        'autonomous_closed_trades',
        'autonomous_trader_logs',
        'autonomous_equity_snapshots',
    ]

    for table in tables_to_check:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            check(f"Table {table}: {count} rows", True)
        except Exception as e:
            check(f"Table {table} ({e})", False)

    cursor.close()
    conn.close()
except Exception as e:
    check(f"Database tables ({e})", False)

# =============================================================================
# 8. API ROUTES
# =============================================================================
section("8. API ROUTES")

try:
    sys.path.insert(0, 'backend')

    from api.routes import (
        trader_routes,
        gex_routes,
        backtest_routes,
        core_routes,
    )
    check("trader_routes imports", True)
    check("gex_routes imports", True)
    check("backtest_routes imports", True)
    check("core_routes imports", True)
except Exception as e:
    check(f"API routes ({e})", False, critical=False)

# =============================================================================
# 9. STRATEGY STATS
# =============================================================================
section("9. STRATEGY STATS")

try:
    from core.strategy_stats import get_strategy_stats
    stats = get_strategy_stats()

    for strategy, data in stats.items():
        win_rate = data.get('win_rate', 0)
        avg_win = data.get('avg_win', 0)
        avg_loss = data.get('avg_loss', 0)
        source = data.get('source', 'unknown')

        # Calculate expectancy
        if avg_loss > 0:
            expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        else:
            expectancy = 0

        status = "✅" if expectancy > 0 else "⚠️"
        print(f"  {status} {strategy}: win={win_rate:.0%}, expect={expectancy:.1f}%, source={source}")

    check(f"Strategy stats loaded: {len(stats)} strategies", len(stats) > 0)
except Exception as e:
    check(f"Strategy stats ({e})", False, critical=False)

# =============================================================================
# 10. FEEDBACK LOOP
# =============================================================================
section("10. FEEDBACK LOOP VERIFICATION")

try:
    # Check if strategy stats file exists
    import os
    stats_file = '.strategy_stats/strategy_stats.json'
    check(f"Strategy stats file exists", os.path.exists(stats_file), critical=False)

    # Check if change log exists
    log_file = '.strategy_stats/change_log.jsonl'
    check(f"Change log file exists", os.path.exists(log_file), critical=False)

    # Verify update mechanism
    from core.strategy_stats import get_strategy_stats, _update_from_backtest
    check("Update mechanism available", callable(_update_from_backtest), critical=False)

except Exception as e:
    check(f"Feedback loop ({e})", False, critical=False)

# =============================================================================
# SUMMARY
# =============================================================================
section("SUMMARY")

total_passed = len(results['passed'])
total_failed = len(results['failed'])
total_warnings = len(results['warnings'])

print(f"\n  ✅ Passed: {total_passed}")
print(f"  ❌ Failed: {total_failed}")
print(f"  ⚠️  Warnings: {total_warnings}")

if total_failed > 0:
    print(f"\n  CRITICAL FAILURES:")
    for fail in results['failed']:
        print(f"    - {fail}")

if total_warnings > 0:
    print(f"\n  WARNINGS (non-critical):")
    for warn in results['warnings']:
        print(f"    - {warn}")

print("\n" + "="*60)
if total_failed == 0:
    print("  ✅ SYSTEM VERIFICATION PASSED")
    print("="*60 + "\n")
    sys.exit(0)
else:
    print("  ❌ SYSTEM VERIFICATION FAILED")
    print("="*60 + "\n")
    sys.exit(1)
