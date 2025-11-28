#!/usr/bin/env python3
"""
SPX Institutional Trader - Comprehensive Diagnostic Tool
=========================================================

Run this to diagnose issues with the SPX trader, including:
- Data fetching (GEX, price, VIX, options chain)
- Regime classification
- Position sizing and Kelly calculations
- Trade execution flow
- Database status
- API connectivity

Usage:
    python diagnose_spx_trader.py
    python diagnose_spx_trader.py --verbose
    python diagnose_spx_trader.py --test-trade

Or on Render shell:
    python diagnose_spx_trader.py
"""

import os
import sys
import argparse
import traceback
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Ensure we can import from the project
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CENTRAL_TZ = ZoneInfo("America/Chicago")

# ANSI color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(title: str):
    """Print a section header."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}  {title}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.END}")


def print_subheader(title: str):
    """Print a subsection header."""
    print(f"\n{Colors.BOLD}{title}{Colors.END}")
    print("-" * 50)


def print_pass(message: str, detail: str = ""):
    """Print a passing check."""
    detail_str = f" - {detail}" if detail else ""
    print(f"  {Colors.GREEN}✅ PASS:{Colors.END} {message}{detail_str}")


def print_fail(message: str, detail: str = ""):
    """Print a failing check."""
    detail_str = f" - {detail}" if detail else ""
    print(f"  {Colors.RED}❌ FAIL:{Colors.END} {message}{detail_str}")


def print_warn(message: str, detail: str = ""):
    """Print a warning."""
    detail_str = f" - {detail}" if detail else ""
    print(f"  {Colors.YELLOW}⚠️  WARN:{Colors.END} {message}{detail_str}")


def print_info(message: str, detail: str = ""):
    """Print an info message."""
    detail_str = f" - {detail}" if detail else ""
    print(f"  {Colors.BLUE}ℹ️  INFO:{Colors.END} {message}{detail_str}")


def check_environment():
    """Check environment variables required for SPX trader."""
    print_header("1. ENVIRONMENT VARIABLES")

    results = {}

    # Required variables
    required_vars = {
        'DATABASE_URL': 'PostgreSQL database connection',
        'POLYGON_API_KEY': 'Polygon.io market data',
    }

    # Optional but useful
    optional_vars = {
        'ANTHROPIC_API_KEY': 'AI reasoning (Claude)',
        'TRADINGVOLATILITY_API_KEY': 'Trading Volatility GEX data',
        'TRADIER_API_KEY': 'Tradier options data',
    }

    all_required_present = True
    for var, description in required_vars.items():
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            masked = value[:4] + '...' + value[-4:] if len(value) > 10 else '***'
            print_pass(f"{var}", f"Set ({masked})")
            results[var] = True
        else:
            print_fail(f"{var}", f"MISSING - Required for {description}")
            results[var] = False
            all_required_present = False

    print()
    for var, description in optional_vars.items():
        value = os.getenv(var)
        if value:
            masked = value[:4] + '...' + value[-4:] if len(value) > 10 else '***'
            print_pass(f"{var}", f"Set ({masked})")
            results[var] = True
        else:
            print_warn(f"{var}", f"Not set - {description} disabled")
            results[var] = False

    return all_required_present, results


def check_market_hours():
    """Check if market is currently open."""
    print_header("2. MARKET HOURS")

    ct_now = datetime.now(CENTRAL_TZ)
    print_info(f"Current Time (CT)", ct_now.strftime('%I:%M:%S %p, %A %B %d, %Y'))
    print_info(f"Day of Week", f"{ct_now.strftime('%A')} ({ct_now.weekday()})")

    # Check weekend
    if ct_now.weekday() >= 5:
        print_warn("MARKET CLOSED", "It's the weekend")
        return False

    # Check time (8:30 AM - 3:00 PM CT for options)
    from datetime import time as dt_time
    market_open = dt_time(8, 30)
    market_close = dt_time(15, 0)
    current_time = ct_now.time()

    print_info(f"Market Hours", f"{market_open.strftime('%I:%M %p')} - {market_close.strftime('%I:%M %p')} CT")

    if current_time < market_open:
        print_warn("MARKET CLOSED", f"Before open ({current_time.strftime('%I:%M %p')} < {market_open.strftime('%I:%M %p')})")
        return False
    elif current_time > market_close:
        print_warn("MARKET CLOSED", f"After close ({current_time.strftime('%I:%M %p')} > {market_close.strftime('%I:%M %p')})")
        return False
    else:
        print_pass("MARKET OPEN", "Trading should be active")
        return True


def check_database():
    """Check database connection and SPX-specific tables."""
    print_header("3. DATABASE STATUS")

    try:
        from database_adapter import get_connection

        conn = get_connection()
        c = conn.cursor()
        print_pass("Database Connection", "Connected successfully")

        # Check SPX-specific tables
        spx_tables = [
            'spx_institutional_positions',
            'spx_institutional_closed_trades',
            'spx_institutional_config',
            'spx_position_sizing_audit',
            'spx_trade_activity',
            'spx_debug_logs'
        ]

        print_subheader("SPX Database Tables")
        for table in spx_tables:
            try:
                c.execute(f"SELECT COUNT(*) FROM {table}")
                count = c.fetchone()[0]
                print_pass(f"{table}", f"{count} rows")
            except Exception as e:
                if 'does not exist' in str(e):
                    print_warn(f"{table}", "Table doesn't exist - will be created on first run")
                else:
                    print_fail(f"{table}", str(e))

        # Check SPX config
        print_subheader("SPX Configuration")
        try:
            c.execute("SELECT key, value FROM spx_institutional_config")
            configs = c.fetchall()
            if configs:
                for key, value in configs:
                    print_info(f"{key}", value[:50] if value else "null")
            else:
                print_warn("No config found", "Will be initialized on first run")
        except Exception as e:
            print_warn("Config table", str(e))

        # Check recent activity
        print_subheader("Recent SPX Activity (Last 24 Hours)")
        try:
            c.execute("""
                SELECT action_type, COUNT(*) as count
                FROM spx_trade_activity
                WHERE activity_timestamp > NOW() - INTERVAL '24 hours'
                GROUP BY action_type
                ORDER BY count DESC
            """)
            activities = c.fetchall()
            if activities:
                for action_type, count in activities:
                    print_info(f"{action_type}", f"{count} events")
            else:
                print_info("No activity", "No SPX trade activity in last 24 hours")
        except Exception as e:
            print_warn("Activity check", str(e))

        # Check open positions
        print_subheader("Open SPX Positions")
        try:
            c.execute("""
                SELECT id, strategy, strike, option_type, contracts, unrealized_pnl, entry_date
                FROM spx_institutional_positions
                WHERE status = 'OPEN'
                ORDER BY entry_date DESC
            """)
            positions = c.fetchall()
            if positions:
                for pos in positions:
                    print_info(f"Position #{pos[0]}", f"{pos[1]} - ${pos[2]} {pos[3]} x{pos[4]} | P&L: ${pos[5]:+,.2f}")
            else:
                print_info("No open positions", "SPX portfolio is flat")
        except Exception as e:
            print_warn("Positions check", str(e))

        conn.close()
        return True

    except Exception as e:
        print_fail("Database Connection", str(e))
        traceback.print_exc()
        return False


def check_data_providers():
    """Check data provider connectivity."""
    print_header("4. DATA PROVIDERS")

    results = {}

    # Check Polygon
    print_subheader("Polygon.io API")
    try:
        from polygon_data_fetcher import polygon_fetcher

        # Test SPY price
        spy_price = polygon_fetcher.get_current_price('SPY')
        if spy_price and spy_price > 0:
            print_pass("SPY Price", f"${spy_price:.2f}")
            results['polygon_spy'] = True
        else:
            print_fail("SPY Price", "Could not fetch")
            results['polygon_spy'] = False

        # Test VIX
        vix = polygon_fetcher.get_current_price('^VIX')
        if vix and vix > 0:
            print_pass("VIX", f"{vix:.2f}")
            results['polygon_vix'] = True
        else:
            print_warn("VIX", "Could not fetch (may need different symbol)")
            results['polygon_vix'] = False

        # Test SPX (may not be available directly)
        spx = polygon_fetcher.get_current_price('^SPX')
        if spx and spx > 0:
            print_pass("SPX Direct", f"${spx:.2f}")
            results['polygon_spx'] = True
        else:
            print_warn("SPX Direct", "Not available - using SPY*10 approximation")
            results['polygon_spx'] = False

    except Exception as e:
        print_fail("Polygon API", str(e))
        results['polygon'] = False

    # Check Trading Volatility API (for GEX)
    print_subheader("Trading Volatility API (GEX Data)")
    try:
        from core_classes_and_engines import TradingVolatilityAPI

        api = TradingVolatilityAPI()
        gex_data = api.get_net_gamma('SPX')

        if gex_data and not gex_data.get('error'):
            print_pass("SPX GEX Data", f"Net GEX: ${gex_data.get('net_gex', 0)/1e9:.2f}B")
            print_info("Flip Point", f"${gex_data.get('flip_point', 0):.0f}")
            print_info("Call Wall", f"${gex_data.get('call_wall', 0):.0f}")
            print_info("Put Wall", f"${gex_data.get('put_wall', 0):.0f}")
            results['tv_gex'] = True
        else:
            print_fail("SPX GEX Data", gex_data.get('error') if gex_data else "No data")
            results['tv_gex'] = False

    except ImportError:
        print_warn("Trading Volatility API", "Module not available")
        results['tv_gex'] = False
    except Exception as e:
        print_fail("Trading Volatility API", str(e))
        results['tv_gex'] = False

    # Check Tradier (for options chain)
    print_subheader("Tradier API (Options Chain)")
    try:
        from tradier_data_fetcher import TradierDataFetcher

        tradier = TradierDataFetcher()
        quote = tradier.get_quote('SPY')

        if quote and not quote.get('error'):
            print_pass("Tradier Connection", f"SPY: ${quote.get('last', 0):.2f}")
            results['tradier'] = True
        else:
            print_warn("Tradier", "Not available or no API key")
            results['tradier'] = False

    except ImportError:
        print_warn("Tradier", "Module not available")
        results['tradier'] = False
    except Exception as e:
        print_warn("Tradier", str(e))
        results['tradier'] = False

    return results


def check_regime_classifier():
    """Check market regime classification."""
    print_header("5. REGIME CLASSIFICATION")

    try:
        from market_regime_classifier import get_classifier, MarketAction

        classifier = get_classifier('SPX')
        print_pass("Classifier Initialized", "SPX regime classifier ready")

        # Get current regime
        print_subheader("Current Market Regime (Simulated)")

        # We need market data for a real classification
        try:
            from polygon_data_fetcher import polygon_fetcher

            spy_price = polygon_fetcher.get_current_price('SPY')
            spx_price = (spy_price * 10) if spy_price else 5900

            # Try to get GEX data
            try:
                from core_classes_and_engines import TradingVolatilityAPI
                api = TradingVolatilityAPI()
                gex_data = api.get_net_gamma('SPX')
                net_gex = gex_data.get('net_gex', 0) if gex_data else 0
                flip_point = gex_data.get('flip_point', spx_price * 0.98) if gex_data else spx_price * 0.98
            except:
                net_gex = 0
                flip_point = spx_price * 0.98

            # Get VIX
            vix = polygon_fetcher.get_current_price('^VIX') or 17

            # Run classification
            regime = classifier.classify(
                spot_price=spx_price,
                net_gex=net_gex,
                flip_point=flip_point,
                current_iv=vix / 100 * 0.9,
                iv_history=[vix / 100 * 0.9] * 20,
                historical_vol=vix / 100 * 0.85,
                vix=vix,
                vix_term_structure="contango",
                momentum_1h=0,
                momentum_4h=0,
                above_20ma=True,
                above_50ma=True
            )

            print_info("Volatility Regime", regime.volatility_regime.value)
            print_info("Gamma Regime", regime.gamma_regime.value)
            print_info("Trend Regime", regime.trend_regime.value)
            print_info("Recommended Action", f"{regime.recommended_action.value}")
            print_info("Confidence", f"{regime.confidence:.0f}%")
            print_info("Bars in Regime", f"{regime.bars_in_regime}")
            print_info("Reasoning", regime.reasoning[:100] + "..." if len(regime.reasoning) > 100 else regime.reasoning)

            return True

        except Exception as e:
            print_warn("Classification test", f"Could not run: {e}")
            return True  # Classifier is available, just couldn't test

    except ImportError as e:
        print_fail("Regime Classifier", f"Import error: {e}")
        return False
    except Exception as e:
        print_fail("Regime Classifier", str(e))
        return False


def check_position_sizing():
    """Check position sizing and Kelly calculation."""
    print_header("6. POSITION SIZING & KELLY")

    try:
        from spx_institutional_trader import SPXInstitutionalTrader

        trader = SPXInstitutionalTrader(capital=100_000_000)
        print_pass("Trader Initialized", f"Capital: ${trader.starting_capital:,.0f}")

        # Test backtest params lookup
        print_subheader("Strategy Backtest Parameters")

        test_strategies = [
            'BUY_CALLS',
            'BUY_PUTS',
            'SELL_PREMIUM',
            'IRON_CONDOR',
            'PUT_SPREAD'
        ]

        for strategy in test_strategies:
            params = trader.get_backtest_params_for_strategy(strategy)
            is_proven = params.get('is_proven', False)
            status = "PROVEN" if is_proven else "Unproven"
            print_info(f"{strategy}", f"{status} | WR: {params['win_rate']:.0%} | "
                      f"Expectancy: {params['expectancy']:.2f}% | "
                      f"Trades: {params['total_trades']}")

        # Test Kelly calculation
        print_subheader("Kelly Criterion Test")
        for strategy in ['BUY_CALLS', 'SELL_PREMIUM']:
            kelly = trader.calculate_kelly_from_backtest(strategy)
            print_info(f"{strategy} Kelly", f"{kelly:.1%}")

        # Test position sizing
        print_subheader("Position Sizing Test")
        contracts, details = trader.calculate_position_size(
            entry_price=50.0,  # $50 option premium
            confidence=75,
            volatility_regime='normal',
            strategy_name='BUY_CALLS'
        )

        print_info("Test Trade", "$50 premium, 75% confidence, normal vol")
        print_info("Calculated Contracts", f"{contracts}")
        print_info("Kelly %", f"{details.get('kelly_pct', 0):.1f}%")
        print_info("Max Position Value", f"${details.get('max_position_value', 0):,.0f}")
        print_info("Final Position Value", f"${details.get('adjusted_position_value', 0):,.0f}")

        return True

    except Exception as e:
        print_fail("Position Sizing", str(e))
        traceback.print_exc()
        return False


def check_debug_logs():
    """Check debug log status."""
    print_header("7. DEBUG LOG STATUS")

    try:
        from spx_debug_logger import get_spx_debug_logger

        logger = get_spx_debug_logger()
        print_pass("Debug Logger", f"Session: {logger.session_id}")

        # Get error summary
        error_summary = logger.get_error_summary()
        if error_summary.get('total_errors', 0) > 0:
            print_warn("Errors Found", f"{error_summary['total_errors']} errors in session")
            for category, count in error_summary.get('error_counts_by_category', {}).items():
                print_info(f"  {category}", f"{count} errors")
        else:
            print_pass("No Errors", "No errors logged in current session")

        # Get recent logs
        recent = logger.get_recent_logs(limit=5)
        if recent:
            print_subheader("Most Recent Log Entries")
            for log in recent:
                status = "✅" if log['success'] else "❌"
                print(f"    {status} [{log['category']}] {log['message'][:60]}...")

        return True

    except ImportError:
        print_warn("Debug Logger", "Module not available - will be created")
        return True
    except Exception as e:
        print_fail("Debug Logger", str(e))
        return False


def run_test_trade_cycle(verbose: bool = False):
    """Run a complete test trade cycle (without executing)."""
    print_header("8. TEST TRADE CYCLE (DRY RUN)")

    try:
        from spx_institutional_trader import SPXInstitutionalTrader

        trader = SPXInstitutionalTrader(capital=100_000_000)

        print_info("Running simulated trade cycle...")
        print()

        # Step 1: Check risk limits
        print_subheader("Step 1: Risk Limit Check")
        greeks = trader.get_portfolio_greeks()
        print_info("Portfolio Delta", f"${greeks['total_delta']:,.0f}")
        print_info("Position Count", f"{greeks['position_count']}")

        daily_pnl = trader._get_daily_pnl()
        print_info("Daily P&L", f"${daily_pnl:+,.2f}")

        max_dd = trader._get_max_drawdown()
        print_info("Max Drawdown", f"{max_dd:.2f}%")

        trade_count = trader._get_daily_trade_count()
        print_info("Today's Trades", f"{trade_count}/{trader.max_daily_trades}")

        # Step 2: Get regime decision
        print_subheader("Step 2: Regime Classification")
        trade = trader.get_unified_regime_decision()

        if trade:
            print_pass("Trade Signal Generated")
            print_info("Strategy", trade.get('strategy'))
            print_info("Action", f"{trade.get('action')} {trade.get('option_type')}")
            print_info("Strike", f"${trade.get('strike')}")
            print_info("Confidence", f"{trade.get('confidence')}%")

            # Step 3: Position sizing
            print_subheader("Step 3: Position Sizing")
            spot = trade.get('spot_price', 5900)
            entry_price = spot * 0.02  # ~2% of spot

            contracts, sizing = trader.calculate_position_size(
                entry_price=entry_price,
                confidence=trade['confidence'],
                volatility_regime='normal',
                strategy_name=trade.get('strategy', '')
            )

            print_info("Entry Price Estimate", f"${entry_price:.2f}")
            print_info("Calculated Contracts", f"{contracts}")
            print_info("Total Premium", f"${sizing.get('total_premium', 0):,.0f}")

            if contracts > 0:
                print_pass("Trade would be executed", f"{contracts} contracts")
            else:
                print_warn("Trade would NOT execute", f"0 contracts ({sizing.get('error', 'sizing issue')})")

        else:
            print_info("No Trade Signal", "Market conditions suggest STAY_FLAT")

        return True

    except Exception as e:
        print_fail("Test Trade Cycle", str(e))
        traceback.print_exc()
        return False


def print_summary(results: dict):
    """Print summary of all checks."""
    print_header("DIAGNOSTIC SUMMARY")

    total_checks = len(results)
    passed = sum(1 for v in results.values() if v)
    failed = total_checks - passed

    for check, passed_val in results.items():
        status = f"{Colors.GREEN}PASS{Colors.END}" if passed_val else f"{Colors.RED}FAIL{Colors.END}"
        print(f"  {check}: {status}")

    print()
    if failed == 0:
        print(f"{Colors.GREEN}{Colors.BOLD}All {total_checks} checks passed! SPX trader should be operational.{Colors.END}")
    else:
        print(f"{Colors.YELLOW}{passed}/{total_checks} checks passed, {failed} issues found.{Colors.END}")

    # Recommendations
    print_header("RECOMMENDATIONS")

    if not results.get('environment'):
        print("• Set required environment variables (DATABASE_URL, POLYGON_API_KEY)")

    if not results.get('database'):
        print("• Check DATABASE_URL connection string")
        print("• Run: python -c 'from spx_institutional_trader import SPXInstitutionalTrader; SPXInstitutionalTrader()'")

    if not results.get('data_providers'):
        print("• Check POLYGON_API_KEY is valid")
        print("• Check TRADINGVOLATILITY_API_KEY for GEX data")

    if not results.get('market_hours'):
        print("• Market is closed - trader will be active during 8:30 AM - 3:00 PM CT, Mon-Fri")

    print("\nTo manually trigger a trade scan:")
    print("  python -c 'from spx_institutional_trader import get_spx_trader_100m; get_spx_trader_100m().find_and_execute_daily_trade()'")

    print("\nTo view debug logs:")
    print("  SELECT * FROM spx_debug_logs ORDER BY timestamp DESC LIMIT 50;")


def main():
    parser = argparse.ArgumentParser(description='SPX Trader Diagnostic Tool')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--test-trade', '-t', action='store_true', help='Run test trade cycle')
    args = parser.parse_args()

    print(f"\n{Colors.BOLD}{Colors.CYAN}SPX INSTITUTIONAL TRADER - DIAGNOSTIC REPORT{Colors.END}")
    print(f"Generated: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 70)

    results = {}

    # Run all checks
    env_ok, _ = check_environment()
    results['environment'] = env_ok

    results['market_hours'] = check_market_hours()
    results['database'] = check_database()

    data_results = check_data_providers()
    results['data_providers'] = any(data_results.values())

    results['regime_classifier'] = check_regime_classifier()
    results['position_sizing'] = check_position_sizing()
    results['debug_logs'] = check_debug_logs()

    if args.test_trade:
        results['test_trade'] = run_test_trade_cycle(args.verbose)

    # Print summary
    print_summary(results)

    # Return exit code based on critical checks
    critical_ok = results['environment'] and results['database']
    sys.exit(0 if critical_ok else 1)


if __name__ == "__main__":
    main()
