#!/bin/bash
#
# COMPREHENSIVE TEST SUITE FOR SPX WHEEL TRADING SYSTEM
#
# This script tests ALL components to verify:
# 1. API connectivity (Polygon, Tradier)
# 2. Real data vs estimated data
# 3. All system components work
#
# USAGE:
#   ./scripts/test_all.sh           # Run all tests
#   ./scripts/test_all.sh polygon   # Test Polygon only
#   ./scripts/test_all.sh tradier   # Test Tradier only
#   ./scripts/test_all.sh backtest  # Test backtester
#   ./scripts/test_all.sh system    # Test trading system
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project root
PROJECT_ROOT="$(dirname "$(dirname "$(realpath "$0")")")"
cd "$PROJECT_ROOT"

echo ""
echo "========================================================================"
echo "       SPX WHEEL TRADING SYSTEM - COMPREHENSIVE TEST SUITE"
echo "========================================================================"
echo "Project Root: $PROJECT_ROOT"
echo "Timestamp: $(date)"
echo "========================================================================"

# Track test results
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# Function to run a test
run_test() {
    local test_name="$1"
    local test_cmd="$2"

    echo ""
    echo "------------------------------------------------------------------------"
    echo -e "${BLUE}TEST: $test_name${NC}"
    echo "------------------------------------------------------------------------"

    if eval "$test_cmd"; then
        echo -e "${GREEN}✓ PASSED: $test_name${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAILED: $test_name${NC}"
        ((TESTS_FAILED++))
    fi
}

# Function to skip a test
skip_test() {
    local test_name="$1"
    local reason="$2"

    echo ""
    echo -e "${YELLOW}⚠ SKIPPED: $test_name${NC}"
    echo "  Reason: $reason"
    ((TESTS_SKIPPED++))
}

# =============================================================================
# TEST 1: ENVIRONMENT
# =============================================================================
test_environment() {
    echo ""
    echo "========================================================================"
    echo "1. ENVIRONMENT CHECK"
    echo "========================================================================"

    # Check Python
    if command -v python3 &> /dev/null; then
        echo -e "${GREEN}✓ Python3: $(python3 --version)${NC}"
    else
        echo -e "${RED}✗ Python3 not found${NC}"
        return 1
    fi

    # Check required packages
    python3 -c "import pandas, numpy, requests" 2>/dev/null && \
        echo -e "${GREEN}✓ Core packages installed${NC}" || \
        echo -e "${YELLOW}⚠ Some packages missing${NC}"

    # Check API keys
    echo ""
    echo "API Keys:"
    if [ -n "$POLYGON_API_KEY" ]; then
        echo -e "${GREEN}✓ POLYGON_API_KEY is set (${POLYGON_API_KEY:0:8}...)${NC}"
    else
        echo -e "${RED}✗ POLYGON_API_KEY not set${NC}"
        echo "  Export it: export POLYGON_API_KEY=your_key"
    fi

    if [ -n "$TRADIER_API_KEY" ]; then
        echo -e "${GREEN}✓ TRADIER_API_KEY is set${NC}"
    else
        echo -e "${YELLOW}⚠ TRADIER_API_KEY not set (optional for paper trading)${NC}"
    fi

    if [ -n "$DATABASE_URL" ]; then
        echo -e "${GREEN}✓ DATABASE_URL is set${NC}"
    else
        echo -e "${YELLOW}⚠ DATABASE_URL not set${NC}"
    fi

    return 0
}

# =============================================================================
# TEST 2: POLYGON API
# =============================================================================
test_polygon() {
    echo ""
    echo "========================================================================"
    echo "2. POLYGON API TEST"
    echo "========================================================================"

    python3 << 'PYTHON_EOF'
import os
import sys
sys.path.insert(0, os.getcwd())

from data.polygon_data_fetcher import polygon_fetcher

print("\n--- Polygon API Connectivity ---")

# Check API key
if not polygon_fetcher.api_key:
    print("❌ POLYGON_API_KEY not configured")
    sys.exit(1)

print(f"✓ API Key: {polygon_fetcher.api_key[:8]}...")

# Test 1: Current price
print("\n--- Testing Current Price ---")
price = polygon_fetcher.get_current_price('SPX')
if price and price > 4000:
    print(f"✓ SPX Current Price: ${price:,.2f} [REAL DATA]")
else:
    print(f"✗ Could not get SPX price (got: {price})")
    print("  This may fail outside market hours or with proxy issues")

# Test 2: Historical price data
print("\n--- Testing Historical Data ---")
df = polygon_fetcher.get_price_history('SPX', days=30, timeframe='day')
if df is not None and len(df) > 10:
    print(f"✓ Historical Data: {len(df)} days")
    print(f"  Date Range: {df.index[0]} to {df.index[-1]}")
    print(f"  Latest Close: ${df['Close'].iloc[-1]:,.2f}")
    print(f"  Data Source: POLYGON_HISTORICAL [REAL DATA]")
else:
    print(f"✗ Insufficient historical data")
    sys.exit(1)

# Test 3: Option quote
print("\n--- Testing Option Quote ---")
from datetime import datetime, timedelta
exp_date = (datetime.now() + timedelta(days=45)).strftime('%Y-%m-%d')
quote = polygon_fetcher.get_option_quote('SPX', 5800, exp_date, 'put')
if quote:
    bid = quote.get('bid', 0)
    ask = quote.get('ask', 0)
    is_delayed = quote.get('is_delayed', False)

    if bid > 0:
        print(f"✓ Option Quote Retrieved [{'DELAYED' if is_delayed else 'REAL-TIME'}]")
        print(f"  Strike: $5800P")
        print(f"  Expiration: {exp_date}")
        print(f"  Bid: ${bid:.2f}")
        print(f"  Ask: ${ask:.2f}")
        print(f"  Delta: {quote.get('delta', 'N/A')}")
        print(f"  IV: {quote.get('implied_volatility', 0) * 100:.1f}%")
    else:
        print(f"⚠ Option quote has no bid (may be after hours)")
        print(f"  Data status: {quote.get('data_status', 'unknown')}")
else:
    print(f"⚠ Could not get option quote (may require Options tier)")

# Test 4: Historical option prices (for backtesting)
print("\n--- Testing Historical Option Prices (CRITICAL for backtest) ---")
test_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
hist_opt = polygon_fetcher.get_historical_option_prices(
    'SPX', 5800, exp_date, 'put',
    start_date=test_date,
    end_date=datetime.now().strftime('%Y-%m-%d')
)
if hist_opt is not None and len(hist_opt) > 0:
    print(f"✓ Historical Option Data: {len(hist_opt)} days")
    print(f"  This is REAL historical data for backtesting!")
    print(f"  Source: POLYGON_HISTORICAL")
else:
    print(f"⚠ No historical option data")
    print(f"  Backtests will use ESTIMATED prices (less accurate)")

# Test 5: Subscription tier
print("\n--- Detecting Subscription Tier ---")
tier = polygon_fetcher.detect_subscription_tier()
print(f"  Tier: {tier.get('tier', 'Unknown')}")
print(f"  Real-time Stocks: {'✓' if tier.get('has_realtime_stocks') else '✗'}")
print(f"  Real-time Options: {'✓' if tier.get('has_realtime_options') else '✗'}")
print(f"  Intraday Data: {'✓' if tier.get('has_intraday') else '✗'}")

print("\n" + "=" * 60)
print("POLYGON API TEST COMPLETE")
print("=" * 60)
PYTHON_EOF
}

# =============================================================================
# TEST 3: TRADIER API
# =============================================================================
test_tradier() {
    echo ""
    echo "========================================================================"
    echo "3. TRADIER API TEST"
    echo "========================================================================"

    python3 << 'PYTHON_EOF'
import os
import sys
sys.path.insert(0, os.getcwd())

print("\n--- Tradier API Connectivity ---")

# Try to import Tradier
try:
    from data.tradier_data_fetcher import TradierDataFetcher
    print("✓ Tradier module imported")
except ImportError as e:
    print(f"⚠ Tradier module not available: {e}")
    print("  Tradier integration is optional")
    sys.exit(0)  # Exit successfully - Tradier is optional

# Check API key
api_key = os.getenv('TRADIER_API_KEY')
if not api_key:
    print("⚠ TRADIER_API_KEY not set")
    print("  Set it to enable live trading features")
    sys.exit(0)

print(f"✓ API Key: {api_key[:8]}...")

try:
    broker = TradierDataFetcher()

    # Check if sandbox mode
    if broker.sandbox:
        print("⚠ Running in SANDBOX mode")
    else:
        print("🔴 Running in LIVE mode")

    # Test account balance
    print("\n--- Testing Account Balance ---")
    balance = broker.get_account_balance()
    if balance:
        print(f"✓ Account Balance Retrieved")
        print(f"  Total Equity: ${balance.get('total_equity', 0):,.2f}")
        print(f"  Buying Power: ${balance.get('option_buying_power', 0):,.2f}")
        print(f"  Source: TRADIER_LIVE")
    else:
        print(f"⚠ Could not get account balance")

    # Test positions
    print("\n--- Testing Positions Query ---")
    positions = broker.get_positions()
    print(f"✓ Positions Retrieved: {len(positions)} positions")
    for pos in positions[:5]:
        print(f"  - {pos.get('symbol')}: {pos.get('quantity')} @ ${pos.get('cost_basis', 0):.2f}")

    # Test option quote
    print("\n--- Testing Live Option Quote ---")
    from datetime import datetime, timedelta
    exp_date = (datetime.now() + timedelta(days=45)).strftime('%Y-%m-%d')
    # Note: Tradier uses different symbol format
    exp_fmt = exp_date.replace('-', '')[2:]
    symbol = f"SPXW{exp_fmt}P05800000"

    try:
        quote = broker.get_quote(symbol)
        if quote:
            print(f"✓ Live Quote: {symbol}")
            print(f"  Bid: ${quote.get('bid', 0):.2f}")
            print(f"  Ask: ${quote.get('ask', 0):.2f}")
            print(f"  Source: TRADIER_LIVE [REAL-TIME]")
        else:
            print(f"⚠ No quote for {symbol}")
    except Exception as e:
        print(f"⚠ Quote error: {e}")

    print("\n" + "=" * 60)
    print("TRADIER API TEST COMPLETE")
    print("=" * 60)

except Exception as e:
    print(f"✗ Tradier test failed: {e}")
    import traceback
    traceback.print_exc()
PYTHON_EOF
}

# =============================================================================
# TEST 4: DATA SOURCE VERIFICATION
# =============================================================================
test_data_sources() {
    echo ""
    echo "========================================================================"
    echo "4. DATA SOURCE VERIFICATION (REAL vs ESTIMATED)"
    echo "========================================================================"

    python3 << 'PYTHON_EOF'
import os
import sys
sys.path.insert(0, os.getcwd())

from data.polygon_data_fetcher import polygon_fetcher
from datetime import datetime, timedelta

print("\n" + "=" * 60)
print("DATA SOURCE ANALYSIS")
print("=" * 60)
print("\nThis test verifies you are getting REAL data, not estimates.")
print("")

results = {
    'polygon_price': False,
    'polygon_history': False,
    'polygon_options': False,
    'polygon_historical_options': False,
}

# 1. Current Price
print("1. SPX Current Price:")
price = polygon_fetcher.get_current_price('SPX')
if price and price > 4000:
    results['polygon_price'] = True
    print(f"   ✓ ${price:,.2f} [REAL DATA from Polygon]")
else:
    print(f"   ✗ Failed or estimated [price={price}]")

# 2. Historical Prices
print("\n2. SPX Historical Prices (30 days):")
df = polygon_fetcher.get_price_history('SPX', days=30)
if df is not None and len(df) > 15:
    results['polygon_history'] = True
    print(f"   ✓ {len(df)} days [REAL DATA from Polygon]")
    print(f"   Range: {df.index.min()} to {df.index.max()}")
else:
    print(f"   ✗ Failed or insufficient data")

# 3. Option Quote (live)
print("\n3. Option Quote (Live):")
exp = (datetime.now() + timedelta(days=45)).strftime('%Y-%m-%d')
quote = polygon_fetcher.get_option_quote('SPX', 5800, exp, 'put')
if quote and quote.get('bid', 0) > 0:
    results['polygon_options'] = True
    status = "DELAYED" if quote.get('is_delayed') else "REAL-TIME"
    print(f"   ✓ Bid=${quote['bid']:.2f} [{status} from Polygon]")
else:
    print(f"   ⚠ No live quote (may be after hours)")

# 4. Historical Option Prices (MOST IMPORTANT for backtest)
print("\n4. Historical Option Prices (CRITICAL):")
start = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
end = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
hist = polygon_fetcher.get_historical_option_prices(
    'SPX', 5700, exp, 'put', start_date=start, end_date=end
)
if hist is not None and len(hist) > 0:
    results['polygon_historical_options'] = True
    print(f"   ✓ {len(hist)} days of option prices [REAL DATA]")
    print(f"   This means backtests use REAL historical option prices!")
else:
    print(f"   ✗ No historical option data")
    print(f"   ⚠ Backtests will use ESTIMATED prices (less accurate)")

# Summary
print("\n" + "=" * 60)
print("SUMMARY: DATA SOURCES")
print("=" * 60)

real_count = sum(results.values())
total_count = len(results)

print(f"\n{'Source':<35} {'Status':<15}")
print("-" * 50)
print(f"{'SPX Current Price':<35} {'REAL' if results['polygon_price'] else 'UNAVAILABLE':<15}")
print(f"{'SPX Historical Prices':<35} {'REAL' if results['polygon_history'] else 'UNAVAILABLE':<15}")
print(f"{'Live Option Quotes':<35} {'REAL' if results['polygon_options'] else 'UNAVAILABLE':<15}")
print(f"{'Historical Option Prices':<35} {'REAL' if results['polygon_historical_options'] else 'ESTIMATED':<15}")

print(f"\nReal Data Sources: {real_count}/{total_count}")

if results['polygon_historical_options']:
    print(f"\n✓ BACKTESTS WILL USE REAL DATA")
else:
    print(f"\n⚠ BACKTESTS MAY USE ESTIMATED DATA")
    print(f"  Consider upgrading Polygon subscription for historical options")

print("=" * 60)
PYTHON_EOF
}

# =============================================================================
# TEST 5: BACKTESTER
# =============================================================================
test_backtester() {
    echo ""
    echo "========================================================================"
    echo "5. BACKTESTER TEST"
    echo "========================================================================"

    python3 << 'PYTHON_EOF'
import os
import sys
sys.path.insert(0, os.getcwd())

print("\n--- Testing Backtester ---")

try:
    from backtest.spx_premium_backtest import SPXPremiumBacktester

    print("✓ Backtester module imported")

    # Run a short backtest (just a few months)
    print("\nRunning short backtest (2024-01-01 to 2024-03-01)...")
    print("This tests if we can fetch real historical data.\n")

    backtester = SPXPremiumBacktester(
        start_date="2024-01-01",
        end_date="2024-03-01",
        initial_capital=100000,
        put_delta=0.20,
        dte_target=45
    )

    results = backtester.run(save_to_db=False)

    if results:
        summary = results.get('summary', {})
        dq = results.get('data_quality', {})

        print("\n" + "=" * 50)
        print("BACKTEST RESULTS")
        print("=" * 50)
        print(f"Total Trades:    {summary.get('total_trades', 0)}")
        print(f"Win Rate:        {summary.get('win_rate', 0):.1f}%")
        print(f"Total Return:    {summary.get('total_return_pct', 0):.2f}%")
        print(f"\nDATA QUALITY:")
        print(f"  Real Data:     {dq.get('real_data_points', 0)} ({dq.get('real_data_pct', 0):.1f}%)")
        print(f"  Estimated:     {dq.get('estimated_data_points', 0)}")

        if dq.get('real_data_pct', 0) > 50:
            print(f"\n✓ BACKTEST USES MOSTLY REAL DATA ({dq.get('real_data_pct', 0):.1f}%)")
        else:
            print(f"\n⚠ BACKTEST USES MOSTLY ESTIMATED DATA")
            print(f"  Consider Polygon Options tier for better accuracy")

        print("=" * 50)
    else:
        print("✗ Backtest returned no results")
        sys.exit(1)

except Exception as e:
    print(f"✗ Backtester test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYTHON_EOF
}

# =============================================================================
# TEST 6: TRADING SYSTEM
# =============================================================================
test_trading_system() {
    echo ""
    echo "========================================================================"
    echo "6. TRADING SYSTEM COMPONENTS TEST"
    echo "========================================================================"

    python3 << 'PYTHON_EOF'
import os
import sys
sys.path.insert(0, os.getcwd())

print("\n--- Testing Trading System Components ---")

components = []

# 1. Market Calendar
print("\n1. Market Calendar & Earnings:")
try:
    from trading.market_calendar import MarketCalendar, should_trade_today
    cal = MarketCalendar()
    should_trade, reason = should_trade_today()
    print(f"   ✓ Market Calendar: {'Can trade' if should_trade else 'Cannot trade'}")
    print(f"   Reason: {reason}")

    has_earnings, symbols = cal.has_major_earnings_soon(days_ahead=7)
    print(f"   Earnings in 7 days: {'Yes - ' + ', '.join(symbols[:3]) if has_earnings else 'None'}")
    components.append(('Market Calendar', True))
except Exception as e:
    print(f"   ✗ Failed: {e}")
    components.append(('Market Calendar', False))

# 2. Circuit Breaker
print("\n2. Circuit Breaker:")
try:
    from trading.circuit_breaker import CircuitBreaker, is_trading_enabled
    cb = CircuitBreaker()
    status = cb.get_status()
    print(f"   ✓ Circuit Breaker: {status['state']}")
    print(f"   Daily P&L: ${status['daily_pnl']:,.2f}")
    print(f"   Max Daily Loss: {status['limits']['max_daily_loss_pct']}%")
    components.append(('Circuit Breaker', True))
except Exception as e:
    print(f"   ✗ Failed: {e}")
    components.append(('Circuit Breaker', False))

# 3. Alerts System
print("\n3. Alerts System:")
try:
    from trading.alerts import get_alerts, AlertLevel
    alerts = get_alerts()
    print(f"   ✓ Alerts System initialized")
    print(f"   Recipient: {alerts.recipient}")
    print(f"   SMTP: {'Configured' if alerts.smtp_user else 'Not configured (will log to console)'}")
    components.append(('Alerts', True))
except Exception as e:
    print(f"   ✗ Failed: {e}")
    components.append(('Alerts', False))

# 4. Position Monitor
print("\n4. Position Monitor:")
try:
    from trading.position_monitor import PositionMonitor
    monitor = PositionMonitor(mode="paper")
    print(f"   ✓ Position Monitor initialized")
    print(f"   Mode: PAPER")
    print(f"   Stop Loss: {monitor.params.get('stop_loss_pct', 200)}%")
    components.append(('Position Monitor', True))
except Exception as e:
    print(f"   ✗ Failed: {e}")
    components.append(('Position Monitor', False))

# 5. Risk Management
print("\n5. Risk Management:")
try:
    from trading.risk_management import calculate_spx_put_margin
    margin = calculate_spx_put_margin(5800, 6000, 15.0, 1)
    print(f"   ✓ Margin Calculator: ${margin['total_margin']:,.2f} for 1 contract")
    components.append(('Risk Management', True))
except Exception as e:
    print(f"   ✗ Failed: {e}")
    components.append(('Risk Management', False))

# 6. Multi-Leg Strategies
print("\n6. Multi-Leg Strategies:")
try:
    from trading.multi_leg_strategies import PutCreditSpread, IronCondor
    print(f"   ✓ Put Credit Spread available")
    print(f"   ✓ Iron Condor available")
    components.append(('Multi-Leg Strategies', True))
except Exception as e:
    print(f"   ✗ Failed: {e}")
    components.append(('Multi-Leg Strategies', False))

# Summary
print("\n" + "=" * 50)
print("COMPONENT TEST SUMMARY")
print("=" * 50)
for name, passed in components:
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  {name:<25} {status}")

passed = sum(1 for _, p in components if p)
total = len(components)
print(f"\nComponents Working: {passed}/{total}")
print("=" * 50)
PYTHON_EOF
}

# =============================================================================
# MAIN
# =============================================================================

# Parse arguments
TEST_TYPE="${1:-all}"

case "$TEST_TYPE" in
    "env"|"environment")
        test_environment
        ;;
    "polygon")
        test_environment
        test_polygon
        ;;
    "tradier")
        test_environment
        test_tradier
        ;;
    "data")
        test_environment
        test_data_sources
        ;;
    "backtest")
        test_environment
        test_backtester
        ;;
    "system")
        test_environment
        test_trading_system
        ;;
    "all")
        test_environment
        test_polygon
        test_tradier
        test_data_sources
        test_backtester
        test_trading_system
        ;;
    *)
        echo "Unknown test type: $TEST_TYPE"
        echo "Usage: $0 [env|polygon|tradier|data|backtest|system|all]"
        exit 1
        ;;
esac

# Final Summary
echo ""
echo "========================================================================"
echo "                         TEST SUITE COMPLETE"
echo "========================================================================"
echo ""
echo "Run individual tests:"
echo "  ./scripts/test_all.sh polygon   - Test Polygon API"
echo "  ./scripts/test_all.sh tradier   - Test Tradier API"
echo "  ./scripts/test_all.sh data      - Test data sources (real vs estimated)"
echo "  ./scripts/test_all.sh backtest  - Test backtester"
echo "  ./scripts/test_all.sh system    - Test trading system components"
echo ""
echo "========================================================================"
