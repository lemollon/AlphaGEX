#!/usr/bin/env python3
"""
AlphaGEX Complete System Test
Tests all APIs and component integrations
"""

import os
import sys
from datetime import datetime

print("=" * 60)
print("ALPHAGEX COMPLETE SYSTEM TEST")
print(f"Timestamp: {datetime.now()}")
print("=" * 60)

# Track results
results = {}

# ==================== 1. ENVIRONMENT VARIABLES ====================
print("\n" + "=" * 60)
print("1. ENVIRONMENT VARIABLES")
print("=" * 60)

env_vars = {
    'TRADIER_API_KEY': os.getenv('TRADIER_API_KEY'),
    'TRADIER_ACCOUNT_ID': os.getenv('TRADIER_ACCOUNT_ID'),
    'TRADIER_SANDBOX': os.getenv('TRADIER_SANDBOX'),
    'TRADING_VOLATILITY_API_KEY': os.getenv('TRADING_VOLATILITY_API_KEY'),
    'POLYGON_API_KEY': os.getenv('POLYGON_API_KEY'),
    'DATABASE_URL': os.getenv('DATABASE_URL'),
    'ANTHROPIC_API_KEY': os.getenv('ANTHROPIC_API_KEY'),
}

for key, value in env_vars.items():
    if value:
        masked = f"...{value[-4:]}" if len(value) > 4 else "SET"
        print(f"  ✓ {key}: {masked}")
        results[f"env_{key}"] = True
    else:
        print(f"  ✗ {key}: MISSING")
        results[f"env_{key}"] = False

# ==================== 2. DATABASE CONNECTION ====================
print("\n" + "=" * 60)
print("2. DATABASE CONNECTION")
print("=" * 60)

try:
    from database_adapter import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    conn.close()
    print("  ✓ PostgreSQL connection: WORKING")
    results['database'] = True
except Exception as e:
    print(f"  ✗ PostgreSQL connection: FAILED - {e}")
    results['database'] = False

# ==================== 3. TRADIER API ====================
print("\n" + "=" * 60)
print("3. TRADIER API (Live Options Data)")
print("=" * 60)

try:
    from tradier_data_fetcher import TradierDataFetcher
    tradier = TradierDataFetcher()

    mode = "SANDBOX" if tradier.sandbox else "PRODUCTION"
    print(f"  Mode: {mode}")

    # Test quote
    quote = tradier.get_quote('SPY')
    if quote:
        print(f"  ✓ SPY Quote: ${quote.get('last', 'N/A')}")
        results['tradier_quote'] = True
    else:
        print("  ✗ SPY Quote: FAILED")
        results['tradier_quote'] = False

    # Test options chain
    chain = tradier.get_option_chain('SPY', greeks=True)
    if chain and chain.chains:
        contracts = list(chain.chains.values())[0]
        print(f"  ✓ Options Chain: {len(contracts)} contracts")
        results['tradier_chain'] = True
    else:
        print("  ✗ Options Chain: FAILED")
        results['tradier_chain'] = False

    # Test ATM option
    atm = tradier.find_atm_options('SPY', option_type='call')
    if atm:
        print(f"  ✓ ATM Option: ${atm.strike} call, Delta={atm.delta:.2f}")
        results['tradier_atm'] = True
    else:
        print("  ✗ ATM Option: FAILED")
        results['tradier_atm'] = False

    # Test account
    balance = tradier.get_account_balance()
    if balance:
        print(f"  ✓ Account Balance: ${balance.get('total_equity', 0):,.2f}")
        results['tradier_account'] = True
    else:
        print("  ✗ Account Balance: FAILED")
        results['tradier_account'] = False

except Exception as e:
    print(f"  ✗ Tradier API: FAILED - {e}")
    results['tradier'] = False

# ==================== 4. TRADING VOLATILITY API (GEX) ====================
print("\n" + "=" * 60)
print("4. TRADING VOLATILITY API (GEX Data)")
print("=" * 60)

try:
    from core_classes_and_engines import TradingVolatilityAPI
    tv_api = TradingVolatilityAPI()

    # Test SPY GEX
    gex_data = tv_api.get_net_gamma('SPY')
    if gex_data:
        net_gex = gex_data.get('netGamma', gex_data.get('net_gex', 0))
        flip = gex_data.get('flipPoint', gex_data.get('flip_point', 0))
        print(f"  ✓ SPY GEX: Net={net_gex:,.0f}, Flip=${flip:.2f}")
        results['tv_spy_gex'] = True
    else:
        print("  ✗ SPY GEX: No data returned")
        results['tv_spy_gex'] = False

    # Test SPX GEX
    spx_gex = tv_api.get_net_gamma('SPX')
    if spx_gex:
        net_gex = spx_gex.get('netGamma', spx_gex.get('net_gex', 0))
        print(f"  ✓ SPX GEX: Net={net_gex:,.0f}")
        results['tv_spx_gex'] = True
    else:
        print("  ✗ SPX GEX: No data returned")
        results['tv_spx_gex'] = False

except ImportError:
    print("  ✗ Trading Volatility API: Module not found")
    results['tv_api'] = False
except Exception as e:
    print(f"  ✗ Trading Volatility API: FAILED - {e}")
    results['tv_api'] = False

# ==================== 5. POLYGON API ====================
print("\n" + "=" * 60)
print("5. POLYGON API (Historical Data Fallback)")
print("=" * 60)

try:
    from polygon_data_fetcher import polygon_fetcher

    # Test current price
    price = polygon_fetcher.get_current_price('SPY')
    if price:
        print(f"  ✓ SPY Price: ${price:.2f}")
        results['polygon_price'] = True
    else:
        print("  ✗ SPY Price: No data")
        results['polygon_price'] = False

    # Test historical
    history = polygon_fetcher.get_price_history('SPY', days=5)
    if history is not None and len(history) > 0:
        print(f"  ✓ Historical Data: {len(history)} bars")
        results['polygon_history'] = True
    else:
        print("  ✗ Historical Data: No data")
        results['polygon_history'] = False

except ImportError:
    print("  ⚠ Polygon API: Not configured (Tradier is primary)")
    results['polygon'] = 'skipped'
except Exception as e:
    print(f"  ✗ Polygon API: FAILED - {e}")
    results['polygon'] = False

# ==================== 6. UNIFIED DATA PROVIDER ====================
print("\n" + "=" * 60)
print("6. UNIFIED DATA PROVIDER")
print("=" * 60)

try:
    from unified_data_provider import get_data_provider
    provider = get_data_provider()

    # Test quote
    quote = provider.get_quote('SPY')
    if quote:
        print(f"  ✓ Quote: ${quote.price:.2f} (source: {quote.source})")
        results['unified_quote'] = True
    else:
        print("  ✗ Quote: FAILED")
        results['unified_quote'] = False

    # Test options
    chain = provider.get_options_chain('SPY')
    if chain:
        print(f"  ✓ Options: {len(list(chain.chains.values())[0])} contracts")
        results['unified_options'] = True
    else:
        print("  ✗ Options: FAILED")
        results['unified_options'] = False

    # Test GEX
    gex = provider.get_gex('SPY')
    if gex:
        print(f"  ✓ GEX: Net={gex.net_gex:,.0f}, Flip=${gex.flip_point:.2f}")
        results['unified_gex'] = True
    else:
        print("  ⚠ GEX: Unavailable (Trading Volatility down)")
        results['unified_gex'] = 'unavailable'

except Exception as e:
    print(f"  ✗ Unified Data Provider: FAILED - {e}")
    results['unified'] = False

# ==================== 7. MARKET REGIME CLASSIFIER ====================
print("\n" + "=" * 60)
print("7. MARKET REGIME CLASSIFIER")
print("=" * 60)

try:
    from market_regime_classifier import get_classifier, MarketAction

    classifier = get_classifier('SPY')
    print(f"  ✓ SPY Classifier: Initialized")

    spx_classifier = get_classifier('SPX')
    print(f"  ✓ SPX Classifier: Initialized")

    results['classifier'] = True

except Exception as e:
    print(f"  ✗ Classifier: FAILED - {e}")
    results['classifier'] = False

# ==================== 8. AUTONOMOUS TRADERS ====================
print("\n" + "=" * 60)
print("8. AUTONOMOUS TRADERS")
print("=" * 60)

# SPY Trader
try:
    from autonomous_paper_trader import AutonomousPaperTrader
    spy_trader = AutonomousPaperTrader()
    print(f"  ✓ SPY Trader: Initialized (${spy_trader.current_capital:,.2f} capital)")
    results['spy_trader'] = True
except Exception as e:
    print(f"  ✗ SPY Trader: FAILED - {e}")
    results['spy_trader'] = False

# SPX Trader (using unified trader with symbol='SPX')
try:
    from autonomous_paper_trader import AutonomousPaperTrader
    spx_trader = AutonomousPaperTrader(symbol='SPX', capital=100_000_000)
    print(f"  ✓ SPX Trader (Unified): Initialized (${spx_trader.starting_capital:,.0f} capital)")
    results['spx_trader'] = True
except Exception as e:
    print(f"  ✗ SPX Trader: FAILED - {e}")
    results['spx_trader'] = False

# ==================== 9. BACKTESTER ====================
print("\n" + "=" * 60)
print("9. BACKTESTER")
print("=" * 60)

try:
    from backtest_framework import BacktestResults, Trade
    print("  ✓ Backtest Framework: Loaded")
    results['backtest_framework'] = True
except Exception as e:
    print(f"  ✗ Backtest Framework: FAILED - {e}")
    results['backtest_framework'] = False

try:
    from unified_trading_engine import UnifiedTradingEngine, TradingInterval
    engine = UnifiedTradingEngine(symbol='SPY', interval=TradingInterval.DAILY)
    print(f"  ✓ Unified Trading Engine: Initialized ({engine.interval.value})")
    results['trading_engine'] = True
except Exception as e:
    print(f"  ✗ Unified Trading Engine: FAILED - {e}")
    results['trading_engine'] = False

# ==================== 10. AI REASONING (Optional) ====================
print("\n" + "=" * 60)
print("10. AI REASONING ENGINE (Optional)")
print("=" * 60)

try:
    from autonomous_ai_reasoning import get_ai_reasoning
    ai = get_ai_reasoning()
    if ai.llm:
        print("  ✓ LangChain + Claude: Ready")
        results['ai_reasoning'] = True
    else:
        print("  ⚠ AI Reasoning: LLM not configured")
        results['ai_reasoning'] = 'not_configured'
except ImportError:
    print("  ⚠ AI Reasoning: Module not available")
    results['ai_reasoning'] = 'not_available'
except Exception as e:
    print(f"  ⚠ AI Reasoning: {e}")
    results['ai_reasoning'] = 'error'

# ==================== SUMMARY ====================
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

passed = sum(1 for v in results.values() if v == True)
failed = sum(1 for v in results.values() if v == False)
warnings = sum(1 for v in results.values() if v not in [True, False])

print(f"\n  ✓ Passed: {passed}")
print(f"  ✗ Failed: {failed}")
print(f"  ⚠ Warnings: {warnings}")

if failed == 0:
    print("\n  🎉 ALL CRITICAL SYSTEMS OPERATIONAL!")
else:
    print(f"\n  ⚠️ {failed} component(s) need attention")

print("\n" + "=" * 60)
