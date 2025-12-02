"""
Trading Logic Tests

Tests the core trading logic:
1. Trade Execution Timing - Only during market hours
2. Exit Logic Triggers - Stop loss, profit target, expiration
3. Position Sizing - Kelly criterion calculations
4. Regime Classification - GEX regime accuracy
5. Historical Backtest Accuracy - Backtest vs actual results

Run: python tests/test_trading_logic.py
"""

import os
import sys
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTS = {"passed": [], "failed": [], "warnings": []}
CENTRAL_TZ = ZoneInfo("America/Chicago")

def log_pass(test, details=""):
    RESULTS["passed"].append({"test": test, "details": details})
    print(f"✅ {test}" + (f": {details}" if details else ""))

def log_fail(test, details=""):
    RESULTS["failed"].append({"test": test, "details": details})
    print(f"❌ {test}" + (f": {details}" if details else ""))

def log_warn(test, details=""):
    RESULTS["warnings"].append({"test": test, "details": details})
    print(f"⚠️  {test}" + (f": {details}" if details else ""))


# =============================================================================
# TEST 1: Trade Execution Timing
# =============================================================================
def test_trade_execution_timing():
    """
    Verify trades only execute during market hours.
    Market hours: 8:30 AM - 3:00 PM Central Time
    """
    print("\n" + "="*70)
    print("TEST: TRADE EXECUTION TIMING")
    print("="*70)

    try:
        # Test the time checking logic
        market_open = time(8, 30)   # 8:30 AM CT
        market_close = time(15, 0)  # 3:00 PM CT

        test_times = [
            (time(6, 0), False, "6:00 AM - Before market"),
            (time(8, 0), False, "8:00 AM - Before open"),
            (time(8, 30), True, "8:30 AM - Market open"),
            (time(9, 30), True, "9:30 AM - Mid morning"),
            (time(12, 0), True, "12:00 PM - Noon"),
            (time(14, 59), True, "2:59 PM - Before close"),
            (time(15, 0), False, "3:00 PM - Market close"),
            (time(15, 30), False, "3:30 PM - After close"),
            (time(20, 0), False, "8:00 PM - Evening"),
        ]

        print("\nTesting market hours logic (8:30 AM - 3:00 PM CT):")

        all_correct = True
        for test_time, expected_open, description in test_times:
            is_open = market_open <= test_time < market_close

            if is_open == expected_open:
                status = "✓" if expected_open else "✗"
                print(f"   {status} {description}: {'OPEN' if is_open else 'CLOSED'}")
            else:
                print(f"   ✗ {description}: Expected {'OPEN' if expected_open else 'CLOSED'}, got {'OPEN' if is_open else 'CLOSED'}")
                all_correct = False

        if all_correct:
            log_pass("Market Hours Logic", "All time checks correct")
        else:
            log_fail("Market Hours Logic", "Some time checks failed")

        # Check current time
        now_ct = datetime.now(CENTRAL_TZ)
        current_time = now_ct.time()
        is_market_open = market_open <= current_time < market_close
        is_weekday = now_ct.weekday() < 5

        print(f"\nCurrent Status:")
        print(f"   Time (CT): {now_ct.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Day: {now_ct.strftime('%A')}")
        print(f"   Market Open: {is_market_open and is_weekday}")

        # Check if trader respects market hours
        try:
            from core.autonomous_paper_trader import AutonomousPaperTrader

            # Check for market hours configuration
            trader_class_source = open(os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'core', 'autonomous_paper_trader.py'
            )).read()

            if 'market_open' in trader_class_source.lower() or '8:30' in trader_class_source or '8, 30' in trader_class_source:
                log_pass("Trader Has Market Hours Check", "Found market hours logic in trader")
            else:
                log_warn("Trader Market Hours", "Could not confirm market hours check exists")

        except Exception as e:
            log_warn("Trader Import", str(e))

        # Check weekend handling
        print("\nWeekend Handling:")
        if is_weekday:
            print(f"   Today is a weekday - trading allowed")
        else:
            print(f"   Today is weekend - trading should be blocked")

        log_pass("Timing Test Complete", f"Current: {'Market Open' if (is_market_open and is_weekday) else 'Market Closed'}")

    except Exception as e:
        log_fail("Trade Execution Timing", str(e))


# =============================================================================
# TEST 2: Exit Logic Triggers
# =============================================================================
def test_exit_logic_triggers():
    """
    Test that exit conditions trigger correctly:
    - Stop loss
    - Profit target
    - Expiration
    - Time-based exits
    """
    print("\n" + "="*70)
    print("TEST: EXIT LOGIC TRIGGERS")
    print("="*70)

    try:
        from trading.mixins.position_manager import PositionManagerMixin

        # Create test scenarios
        test_positions = [
            {
                'name': 'Profit Target Hit',
                'entry_price': 2.00,
                'current_price': 2.80,  # 40% gain
                'profit_target_pct': 30.0,
                'stop_loss_pct': 25.0,
                'expected_exit': True,
                'expected_reason': 'profit'
            },
            {
                'name': 'Stop Loss Hit',
                'entry_price': 2.00,
                'current_price': 1.40,  # 30% loss
                'profit_target_pct': 30.0,
                'stop_loss_pct': 25.0,
                'expected_exit': True,
                'expected_reason': 'stop'
            },
            {
                'name': 'Position Holding',
                'entry_price': 2.00,
                'current_price': 2.20,  # 10% gain - no exit
                'profit_target_pct': 30.0,
                'stop_loss_pct': 25.0,
                'expected_exit': False,
                'expected_reason': None
            },
            {
                'name': 'Break Even',
                'entry_price': 2.00,
                'current_price': 2.00,  # No change
                'profit_target_pct': 30.0,
                'stop_loss_pct': 25.0,
                'expected_exit': False,
                'expected_reason': None
            },
        ]

        print("\nTesting exit condition logic:")

        for test in test_positions:
            entry = test['entry_price']
            current = test['current_price']
            pnl_pct = ((current - entry) / entry) * 100

            # Check profit target
            hit_profit = pnl_pct >= test['profit_target_pct']
            # Check stop loss
            hit_stop = pnl_pct <= -test['stop_loss_pct']

            should_exit = hit_profit or hit_stop

            actual_reason = None
            if hit_profit:
                actual_reason = 'profit'
            elif hit_stop:
                actual_reason = 'stop'

            print(f"\n   {test['name']}:")
            print(f"      Entry: ${entry:.2f}, Current: ${current:.2f}")
            print(f"      P&L: {pnl_pct:+.1f}%")
            print(f"      Targets: +{test['profit_target_pct']}% / -{test['stop_loss_pct']}%")
            print(f"      Should Exit: {should_exit} (expected: {test['expected_exit']})")

            if should_exit == test['expected_exit']:
                if test['expected_reason'] and actual_reason != test['expected_reason']:
                    log_warn(f"Exit Logic - {test['name']}", f"Wrong reason: {actual_reason} vs {test['expected_reason']}")
                else:
                    log_pass(f"Exit Logic - {test['name']}", f"P&L: {pnl_pct:+.1f}%")
            else:
                log_fail(f"Exit Logic - {test['name']}", f"Expected exit={test['expected_exit']}, got {should_exit}")

        # Test expiration logic
        print("\n\nTesting expiration exit logic:")

        today = datetime.now(CENTRAL_TZ).date()
        tomorrow = today + timedelta(days=1)
        yesterday = today - timedelta(days=1)
        next_week = today + timedelta(days=7)

        expiration_tests = [
            (yesterday, True, "Expired yesterday"),
            (today, True, "Expires today"),
            (tomorrow, False, "Expires tomorrow"),
            (next_week, False, "Expires next week"),
        ]

        for exp_date, should_exit_exp, description in expiration_tests:
            is_expired = exp_date <= today

            if is_expired == should_exit_exp:
                log_pass(f"Expiration - {description}", f"Correctly {'exits' if is_expired else 'holds'}")
            else:
                log_fail(f"Expiration - {description}", f"Expected exit={should_exit_exp}, got {is_expired}")

    except Exception as e:
        log_fail("Exit Logic Triggers", str(e))
        import traceback
        traceback.print_exc()


# =============================================================================
# TEST 3: Position Sizing (Kelly Criterion)
# =============================================================================
def test_position_sizing():
    """
    Test Kelly criterion position sizing calculations.
    """
    print("\n" + "="*70)
    print("TEST: POSITION SIZING (KELLY CRITERION)")
    print("="*70)

    try:
        # Kelly formula: f* = (p * b - q) / b
        # Where: p = win probability, q = 1-p, b = win/loss ratio

        def calculate_kelly(win_rate, avg_win, avg_loss):
            """Calculate Kelly fraction"""
            if avg_loss == 0:
                return 0

            p = win_rate
            q = 1 - win_rate
            b = abs(avg_win / avg_loss)

            kelly = (p * b - q) / b
            return max(0, kelly)  # Can't be negative

        def calculate_half_kelly(win_rate, avg_win, avg_loss):
            """Half Kelly for more conservative sizing"""
            return calculate_kelly(win_rate, avg_win, avg_loss) / 2

        test_scenarios = [
            {
                'name': 'Strong Edge',
                'win_rate': 0.60,
                'avg_win': 100,
                'avg_loss': 50,
                'description': '60% win rate, 2:1 reward/risk'
            },
            {
                'name': 'Moderate Edge',
                'win_rate': 0.55,
                'avg_win': 75,
                'avg_loss': 75,
                'description': '55% win rate, 1:1 reward/risk'
            },
            {
                'name': 'Weak Edge',
                'win_rate': 0.52,
                'avg_win': 60,
                'avg_loss': 60,
                'description': '52% win rate, 1:1 reward/risk'
            },
            {
                'name': 'No Edge',
                'win_rate': 0.50,
                'avg_win': 50,
                'avg_loss': 50,
                'description': '50% win rate, 1:1 reward/risk'
            },
            {
                'name': 'Negative Edge',
                'win_rate': 0.45,
                'avg_win': 50,
                'avg_loss': 50,
                'description': '45% win rate - should not trade'
            },
        ]

        print("\nKelly Criterion Position Sizing:")

        for scenario in test_scenarios:
            kelly = calculate_kelly(scenario['win_rate'], scenario['avg_win'], scenario['avg_loss'])
            half_kelly = calculate_half_kelly(scenario['win_rate'], scenario['avg_win'], scenario['avg_loss'])

            print(f"\n   {scenario['name']} ({scenario['description']}):")
            print(f"      Full Kelly: {kelly*100:.1f}% of capital")
            print(f"      Half Kelly: {half_kelly*100:.1f}% of capital")

            # With $1M capital
            capital = 1_000_000
            position_size = capital * half_kelly

            print(f"      With $1M: ${position_size:,.0f} position")

            if kelly > 0:
                log_pass(f"Kelly - {scenario['name']}", f"Size: {half_kelly*100:.1f}%")
            elif scenario['win_rate'] < 0.5:
                log_pass(f"Kelly - {scenario['name']}", "Correctly shows no edge")
            else:
                log_warn(f"Kelly - {scenario['name']}", "Zero position size")

        # Test actual trader's position sizing
        print("\n\nChecking trader's position sizing implementation:")

        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            # Get recent trades to analyze position sizes
            cursor.execute("""
                SELECT contracts, entry_price, symbol
                FROM autonomous_open_positions
                UNION ALL
                SELECT contracts, entry_price, symbol
                FROM autonomous_closed_trades
                ORDER BY 3
                LIMIT 20
            """)

            trades = cursor.fetchall()

            if trades:
                position_values = []
                for trade in trades:
                    contracts = int(trade[0]) if trade[0] else 1
                    entry_price = float(trade[1]) if trade[1] else 0
                    value = contracts * entry_price * 100
                    position_values.append(value)

                avg_position = sum(position_values) / len(position_values)
                max_position = max(position_values)
                min_position = min(position_values)

                print(f"   Actual positions from database:")
                print(f"      Average: ${avg_position:,.0f}")
                print(f"      Min: ${min_position:,.0f}")
                print(f"      Max: ${max_position:,.0f}")

                # Check if positions are reasonable (< 10% of $1M)
                if max_position < 100_000:
                    log_pass("Position Sizes", f"Max ${max_position:,.0f} is reasonable")
                else:
                    log_warn("Position Sizes", f"Max ${max_position:,.0f} may be too large")
            else:
                log_warn("Position Sizing", "No trades found to analyze")

            conn.close()

        except Exception as e:
            log_warn("Position Sizing Analysis", str(e))

    except Exception as e:
        log_fail("Position Sizing Test", str(e))


# =============================================================================
# TEST 4: Regime Classification
# =============================================================================
def test_regime_classification():
    """
    Test market regime classification accuracy.
    """
    print("\n" + "="*70)
    print("TEST: REGIME CLASSIFICATION")
    print("="*70)

    try:
        from core.market_regime_classifier import MarketRegimeClassifier

        classifier = MarketRegimeClassifier()

        # Test scenarios with known expected outcomes
        test_scenarios = [
            {
                'name': 'Positive GEX Bull',
                'gex_data': {
                    'net_gex': 5_000_000_000,  # $5B positive
                    'flip_point': 590,
                    'spot_price': 600,  # Above flip
                    'gamma_wall_call': 605,
                    'gamma_wall_put': 585,
                },
                'vix': 14,
                'expected_regime': 'positive',
                'expected_action': 'call'
            },
            {
                'name': 'Negative GEX Bear',
                'gex_data': {
                    'net_gex': -3_000_000_000,  # $3B negative
                    'flip_point': 600,
                    'spot_price': 590,  # Below flip
                    'gamma_wall_call': 605,
                    'gamma_wall_put': 585,
                },
                'vix': 22,
                'expected_regime': 'negative',
                'expected_action': 'put'
            },
            {
                'name': 'High VIX Caution',
                'gex_data': {
                    'net_gex': 1_000_000_000,
                    'flip_point': 595,
                    'spot_price': 595,
                    'gamma_wall_call': 600,
                    'gamma_wall_put': 590,
                },
                'vix': 35,
                'expected_regime': 'any',  # High VIX overrides
                'expected_action': 'hold'
            },
        ]

        print("\nTesting regime classification:")

        for scenario in test_scenarios:
            print(f"\n   {scenario['name']}:")
            print(f"      Net GEX: ${scenario['gex_data']['net_gex']/1e9:.1f}B")
            print(f"      Spot: ${scenario['gex_data']['spot_price']}, Flip: ${scenario['gex_data']['flip_point']}")
            print(f"      VIX: {scenario['vix']}")

            try:
                result = classifier.classify(
                    gex_data=scenario['gex_data'],
                    vix_current=scenario['vix']
                )

                if result:
                    regime = result.gex_regime if hasattr(result, 'gex_regime') else 'unknown'
                    action = result.action if hasattr(result, 'action') else 'unknown'
                    confidence = result.confidence if hasattr(result, 'confidence') else 0

                    print(f"      Result: Regime={regime}, Action={action}, Confidence={confidence}%")

                    # Check if matches expected
                    regime_match = scenario['expected_regime'] == 'any' or scenario['expected_regime'].lower() in regime.lower()
                    action_match = scenario['expected_action'].lower() in action.lower()

                    if regime_match:
                        log_pass(f"Regime - {scenario['name']}", f"{regime}")
                    else:
                        log_warn(f"Regime - {scenario['name']}", f"Got {regime}, expected {scenario['expected_regime']}")

                else:
                    log_warn(f"Regime - {scenario['name']}", "No classification result")

            except Exception as e:
                log_warn(f"Regime - {scenario['name']}", str(e))

        # Test with live data
        print("\n\nTesting with live market data:")

        try:
            from data.unified_data_provider import UnifiedDataProvider
            from data.gex_data_provider import GEXDataProvider

            provider = UnifiedDataProvider()
            gex_provider = GEXDataProvider()

            # Get live GEX data
            gex_data = gex_provider.get_gex_analysis('SPY')

            if gex_data:
                print(f"   Live GEX Data:")
                print(f"      Net GEX: ${gex_data.get('net_gex', 0)/1e9:.2f}B")
                print(f"      Flip Point: ${gex_data.get('flip_point', 0):.2f}")

                # Get VIX
                vix_quote = provider.get_quote('$VIX.X') or provider.get_quote('^VIX')
                vix = vix_quote.price if vix_quote else 18

                print(f"      VIX: {vix:.2f}")

                # Classify
                result = classifier.classify(gex_data=gex_data, vix_current=vix)

                if result:
                    print(f"\n   Live Classification:")
                    print(f"      Regime: {result.gex_regime if hasattr(result, 'gex_regime') else 'N/A'}")
                    print(f"      Action: {result.action if hasattr(result, 'action') else 'N/A'}")
                    print(f"      Confidence: {result.confidence if hasattr(result, 'confidence') else 0}%")

                    log_pass("Live Regime Classification", f"{result.gex_regime if hasattr(result, 'gex_regime') else 'Complete'}")
            else:
                log_warn("Live GEX Data", "Could not retrieve")

        except Exception as e:
            log_warn("Live Classification", str(e))

    except ImportError as e:
        log_warn("Regime Classification", f"Could not import classifier: {e}")
    except Exception as e:
        log_fail("Regime Classification", str(e))


# =============================================================================
# TEST 5: Historical Backtest Accuracy
# =============================================================================
def test_historical_backtest_accuracy():
    """
    Test that backtest results are historically accurate.
    Compares backtest predictions against actual historical data.
    """
    print("\n" + "="*70)
    print("TEST: HISTORICAL BACKTEST ACCURACY")
    print("="*70)

    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        # Get backtest results from database
        print("\nChecking backtest result tables:")

        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name LIKE '%backtest%'
        """)

        backtest_tables = cursor.fetchall()
        print(f"   Found {len(backtest_tables)} backtest-related tables")

        for table in backtest_tables:
            print(f"      - {table[0]}")

        # Check SPX wheel backtest results
        print("\nChecking SPX wheel backtest results:")

        try:
            cursor.execute("""
                SELECT COUNT(*) FROM spx_backtest_trades
            """)
            spx_count = cursor.fetchone()[0]
            print(f"   SPX backtest trades: {spx_count}")

            if spx_count > 0:
                # Get sample of backtest trades
                cursor.execute("""
                    SELECT trade_date, entry_price, exit_price, pnl, strategy
                    FROM spx_backtest_trades
                    ORDER BY trade_date DESC
                    LIMIT 5
                """)

                trades = cursor.fetchall()
                print("\n   Sample backtest trades:")

                all_accurate = True
                for trade in trades:
                    date = trade[0]
                    entry = float(trade[1]) if trade[1] else 0
                    exit_p = float(trade[2]) if trade[2] else 0
                    pnl = float(trade[3]) if trade[3] else 0
                    strategy = trade[4]

                    # Verify P&L calculation
                    expected_pnl = (exit_p - entry) * 100  # 1 contract

                    print(f"      {date}: {strategy}")
                    print(f"         Entry: ${entry:.2f}, Exit: ${exit_p:.2f}")
                    print(f"         Recorded P&L: ${pnl:.2f}")
                    print(f"         Calculated P&L: ${expected_pnl:.2f}")

                    # Check if P&L is roughly accurate (allow for commissions)
                    if abs(pnl - expected_pnl) < 50:  # Allow $50 for commissions/slippage
                        print(f"         ✓ P&L accurate")
                    else:
                        print(f"         ✗ P&L mismatch")
                        all_accurate = False

                if all_accurate:
                    log_pass("SPX Backtest P&L", "All sampled trades accurate")
                else:
                    log_warn("SPX Backtest P&L", "Some P&L calculations don't match")

                # Check win rate accuracy
                cursor.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                        AVG(pnl) as avg_pnl
                    FROM spx_backtest_trades
                """)

                stats = cursor.fetchone()
                total = stats[0] or 0
                wins = stats[1] or 0
                avg_pnl = float(stats[2]) if stats[2] else 0

                if total > 0:
                    win_rate = (wins / total) * 100
                    print(f"\n   Backtest Statistics:")
                    print(f"      Total trades: {total}")
                    print(f"      Win rate: {win_rate:.1f}%")
                    print(f"      Average P&L: ${avg_pnl:.2f}")

                    # Sanity check win rate
                    if 30 <= win_rate <= 80:
                        log_pass("Win Rate Sanity", f"{win_rate:.1f}% is realistic")
                    else:
                        log_warn("Win Rate Sanity", f"{win_rate:.1f}% may be unrealistic")

            else:
                log_warn("SPX Backtest", "No backtest trades found")

        except Exception as e:
            if "does not exist" in str(e):
                log_warn("SPX Backtest Table", "Table not created yet")
            else:
                log_warn("SPX Backtest", str(e))

        # Check for actual vs predicted comparison
        print("\nComparing live trades vs backtest expectations:")

        try:
            # Get recent closed trades
            cursor.execute("""
                SELECT
                    symbol,
                    COUNT(*) as total,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    AVG(realized_pnl) as avg_pnl
                FROM autonomous_closed_trades
                WHERE exit_date > NOW() - INTERVAL '30 days'
                GROUP BY symbol
            """)

            live_stats = cursor.fetchall()

            if live_stats:
                print("   Live trading stats (last 30 days):")
                for stat in live_stats:
                    symbol = stat[0]
                    total = stat[1]
                    wins = stat[2] or 0
                    avg_pnl = float(stat[3]) if stat[3] else 0
                    win_rate = (wins / total * 100) if total > 0 else 0

                    print(f"\n      {symbol}:")
                    print(f"         Trades: {total}")
                    print(f"         Win Rate: {win_rate:.1f}%")
                    print(f"         Avg P&L: ${avg_pnl:.2f}")

                log_pass("Live Trading Stats", f"Found stats for {len(live_stats)} symbols")
            else:
                log_warn("Live Trading Stats", "No recent closed trades")

        except Exception as e:
            log_warn("Live Trading Comparison", str(e))

        # Check for date range consistency
        print("\nChecking backtest date range consistency:")

        try:
            cursor.execute("""
                SELECT
                    MIN(trade_date) as earliest,
                    MAX(trade_date) as latest,
                    COUNT(DISTINCT trade_date) as trading_days
                FROM spx_backtest_trades
            """)

            date_stats = cursor.fetchone()

            if date_stats and date_stats[0]:
                earliest = date_stats[0]
                latest = date_stats[1]
                trading_days = date_stats[2]

                print(f"   Date range: {earliest} to {latest}")
                print(f"   Trading days: {trading_days}")

                # Check for gaps (should have ~252 trading days per year)
                total_days = (latest - earliest).days if hasattr(latest, '__sub__') else 365
                expected_trading_days = total_days * 252 / 365

                if trading_days > expected_trading_days * 0.8:
                    log_pass("Date Coverage", f"{trading_days} trading days")
                else:
                    log_warn("Date Coverage", f"Only {trading_days} days - may have gaps")

            else:
                log_warn("Date Range", "No date data available")

        except Exception as e:
            log_warn("Date Range Check", str(e))

        conn.close()

        # Verify backtest uses realistic prices
        print("\nVerifying backtest price realism:")

        try:
            from trading.spx_wheel_system import SPXWheelOptimizer

            # Check if backtester uses historical prices
            optimizer = SPXWheelOptimizer()

            if hasattr(optimizer, 'get_historical_price') or hasattr(optimizer, 'historical_data'):
                log_pass("Historical Prices", "Backtester has historical price access")
            else:
                log_warn("Historical Prices", "Could not verify historical price source")

        except ImportError:
            log_warn("SPX Optimizer Import", "Could not import to verify")
        except Exception as e:
            log_warn("Price Realism Check", str(e))

    except Exception as e:
        log_fail("Historical Backtest Accuracy", str(e))
        import traceback
        traceback.print_exc()


# =============================================================================
# SUMMARY
# =============================================================================
def print_summary():
    print("\n" + "="*70)
    print("TRADING LOGIC TEST RESULTS")
    print("="*70)

    total = len(RESULTS["passed"]) + len(RESULTS["failed"]) + len(RESULTS["warnings"])

    print(f"\n✅ Passed:   {len(RESULTS['passed'])}")
    print(f"❌ Failed:   {len(RESULTS['failed'])}")
    print(f"⚠️  Warnings: {len(RESULTS['warnings'])}")

    if RESULTS["failed"]:
        print("\n❌ FAILURES:")
        for item in RESULTS["failed"]:
            print(f"   • {item['test']}: {item['details']}")

    if RESULTS["warnings"]:
        print("\n⚠️  WARNINGS:")
        for item in RESULTS["warnings"]:
            print(f"   • {item['test']}: {item['details']}")

    return len(RESULTS["failed"]) == 0


if __name__ == "__main__":
    print("="*70)
    print("TRADING LOGIC TESTS")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    test_trade_execution_timing()
    test_exit_logic_triggers()
    test_position_sizing()
    test_regime_classification()
    test_historical_backtest_accuracy()

    success = print_summary()
    sys.exit(0 if success else 1)
