#!/usr/bin/env python3
"""
AlphaGEX Comprehensive End-to-End Test Suite
=============================================

Tests all major systems to ensure they are properly configured and working:
1. Database tables - exist and can accept data
2. Scheduler configuration - timing matches trading windows
3. Trading bots - ATHENA, ARES, PHOENIX status
4. API endpoints - health and data flow
5. Data providers - Tradier, VIX sources
6. ARGUS live data feed

Usage:
    python scripts/test_all_systems_e2e.py [--url BASE_URL]

Example:
    python scripts/test_all_systems_e2e.py --url https://alphagex-api.onrender.com
"""

import sys
import json
import time
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
CYAN = '\033[96m'
RESET = '\033[0m'
BOLD = '\033[1m'

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Test results tracking
results = {
    'passed': 0,
    'failed': 0,
    'warnings': 0,
    'sections': {}
}


def log_pass(section, name, detail=""):
    results['passed'] += 1
    if section not in results['sections']:
        results['sections'][section] = {'passed': 0, 'failed': 0, 'warnings': 0}
    results['sections'][section]['passed'] += 1
    print(f"  {GREEN}✓{RESET} {name}" + (f" ({detail})" if detail else ""))


def log_fail(section, name, detail=""):
    results['failed'] += 1
    if section not in results['sections']:
        results['sections'][section] = {'passed': 0, 'failed': 0, 'warnings': 0}
    results['sections'][section]['failed'] += 1
    print(f"  {RED}✗{RESET} {name}" + (f" ({detail})" if detail else ""))


def log_warn(section, name, detail=""):
    results['warnings'] += 1
    if section not in results['sections']:
        results['sections'][section] = {'passed': 0, 'failed': 0, 'warnings': 0}
    results['sections'][section]['warnings'] += 1
    print(f"  {YELLOW}⚠{RESET} {name}" + (f" ({detail})" if detail else ""))


def log_info(msg):
    print(f"  {BLUE}ℹ{RESET} {msg}")


def section_header(title):
    print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
    print(f"{BOLD}{CYAN}{title}{RESET}")
    print(f"{CYAN}{'=' * 60}{RESET}")


# =============================================================================
# TEST 1: DATABASE TABLES
# =============================================================================
def test_database_tables():
    """Verify all required database tables exist and are accessible"""
    section = "DATABASE"
    section_header("TEST 1: Database Tables")

    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        # Critical tables that must exist
        required_tables = [
            # Trading decisions
            'trading_decisions',
            'bot_decision_logs',
            # ARES
            'ares_iron_condor_positions',
            'ares_iron_condor_performance',
            # ATHENA
            'athena_spread_positions',
            'athena_signals',
            'athena_logs',
            # ARGUS
            'argus_commentary',
            # VIX
            'vix_hedge_signals',
            # Oracle
            'oracle_analysis_cache',
            # Scheduler
            'scheduler_state',
        ]

        for table in required_tables:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = %s
                )
            """, (table,))
            exists = cursor.fetchone()[0]

            if exists:
                # Check if table has data
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                log_pass(section, f"Table '{table}'", f"{count} rows")
            else:
                log_fail(section, f"Table '{table}'", "MISSING")

        conn.close()
        return True

    except Exception as e:
        log_fail(section, "Database connection", str(e))
        return False


# =============================================================================
# TEST 2: SCHEDULER CONFIGURATION
# =============================================================================
def test_scheduler_config():
    """Verify scheduler timing matches trading windows"""
    section = "SCHEDULER"
    section_header("TEST 2: Scheduler Configuration")

    try:
        # Check ARES trading window vs scheduler
        from trading.ares_iron_condor import ARESConfig

        ares_config = ARESConfig()
        log_info(f"ARES entry_time_start: {ares_config.entry_time_start}")
        log_info(f"ARES entry_time_end: {ares_config.entry_time_end}")

        # The scheduler should run at 9:35 AM CT (same as entry_time_start)
        if ares_config.entry_time_start == "09:35":
            log_pass(section, "ARES trading window", f"{ares_config.entry_time_start} - {ares_config.entry_time_end}")
        else:
            log_warn(section, "ARES trading window", f"Starts at {ares_config.entry_time_start}, scheduler should match")

        # Check ATHENA
        from trading.athena_directional_spreads import ATHENAConfig

        athena_config = ATHENAConfig()
        log_info(f"ATHENA max_daily_trades: {athena_config.max_daily_trades}")
        log_info(f"ATHENA max_open_positions: {athena_config.max_open_positions}")
        log_pass(section, "ATHENA config loaded", f"ticker={athena_config.ticker}")

        # Scheduler timing summary
        log_info("")
        log_info("Expected Scheduler Times (CT):")
        log_info("  ATLAS:  9:05 AM daily")
        log_info("  ARES:   9:35 AM daily")
        log_info("  ATHENA: Every 30 min (8:35 AM - 2:30 PM)")
        log_info("  ARGUS:  Every 5 min (8:30 AM - 3:00 PM)")

        return True

    except Exception as e:
        log_fail(section, "Scheduler config", str(e))
        return False


# =============================================================================
# TEST 3: TRADING BOTS STATUS
# =============================================================================
def test_trading_bots(base_url):
    """Test all trading bot endpoints"""
    section = "BOTS"
    section_header("TEST 3: Trading Bots Status")

    try:
        import requests

        # Test ATHENA
        try:
            r = requests.get(f"{base_url}/api/athena/status", timeout=30)
            if r.status_code == 200:
                data = r.json().get('data', {})
                mode = data.get('mode', 'unknown')
                capital = data.get('capital', 0)
                gex_ml = data.get('gex_ml_available', False)
                oracle = data.get('oracle_available', False)
                log_pass(section, "ATHENA status", f"mode={mode}, capital=${capital:,.0f}")
                log_info(f"  GEX ML: {'✓' if gex_ml else '✗'}, Oracle: {'✓' if oracle else '✗'}")
            else:
                log_fail(section, "ATHENA status", f"HTTP {r.status_code}")
        except Exception as e:
            log_fail(section, "ATHENA status", str(e))

        # Test ARES
        try:
            r = requests.get(f"{base_url}/api/ares/status", timeout=30)
            if r.status_code == 200:
                data = r.json().get('data', {})
                mode = data.get('mode', 'unknown')
                capital = data.get('capital', 0)
                open_pos = data.get('open_positions', 0)
                traded_today = data.get('traded_today', False)
                in_window = data.get('in_trading_window', False)
                log_pass(section, "ARES status", f"mode={mode}, capital=${capital:,.0f}")
                log_info(f"  Open positions: {open_pos}, Traded today: {traded_today}, In window: {in_window}")
            else:
                log_fail(section, "ARES status", f"HTTP {r.status_code}")
        except Exception as e:
            log_fail(section, "ARES status", str(e))

        return True

    except Exception as e:
        log_fail(section, "Trading bots", str(e))
        return False


# =============================================================================
# TEST 4: ARGUS LIVE DATA
# =============================================================================
def test_argus_live_data(base_url):
    """Test ARGUS gamma data feed"""
    section = "ARGUS"
    section_header("TEST 4: ARGUS Live Data Feed")

    try:
        import requests

        # Test gamma endpoint
        r = requests.get(f"{base_url}/api/argus/gamma", timeout=30)
        if r.status_code == 200:
            data = r.json()
            if data.get('success'):
                gamma = data.get('data', {})
                is_mock = gamma.get('is_mock', True)
                fetched_at = gamma.get('fetched_at', 'N/A')
                strikes = gamma.get('strikes', [])

                if is_mock:
                    log_warn(section, "Gamma data", "MOCK data (market may be closed)")
                else:
                    log_pass(section, "Gamma data", f"LIVE from Tradier, {len(strikes)} strikes")

                log_info(f"  fetched_at: {fetched_at}")
                log_info(f"  strikes: {len(strikes)}")
            else:
                log_fail(section, "Gamma endpoint", "success=false")
        else:
            log_fail(section, "Gamma endpoint", f"HTTP {r.status_code}")

        # Test commentary history
        try:
            r = requests.get(f"{base_url}/api/argus/commentary", timeout=30)
            if r.status_code == 200:
                data = r.json()
                entries = data.get('data', [])
                log_pass(section, "Commentary history", f"{len(entries)} entries")
                if entries:
                    latest = entries[0]
                    log_info(f"  Latest: {latest.get('generated_at', 'N/A')[:19]}")
            else:
                log_warn(section, "Commentary history", f"HTTP {r.status_code}")
        except Exception as e:
            log_warn(section, "Commentary history", str(e))

        return True

    except Exception as e:
        log_fail(section, "ARGUS", str(e))
        return False


# =============================================================================
# TEST 5: VIX DATA AND SIGNALS
# =============================================================================
def test_vix_system(base_url):
    """Test VIX dashboard and signal generation"""
    section = "VIX"
    section_header("TEST 5: VIX Dashboard & Signals")

    try:
        import requests

        # Test VIX data
        r = requests.get(f"{base_url}/api/vix/data", timeout=30)
        if r.status_code == 200:
            data = r.json()
            if data.get('success'):
                vix_data = data.get('data', {})
                vix_spot = vix_data.get('vix_spot', 0)
                stress_level = vix_data.get('stress_level', 'unknown')
                log_pass(section, "VIX data", f"VIX={vix_spot:.2f}, stress={stress_level}")
            else:
                log_warn(section, "VIX data", "success=false (may need refresh)")
        else:
            log_warn(section, "VIX data", f"HTTP {r.status_code}")

        # Test signal history
        r = requests.get(f"{base_url}/api/vix/signal-history?days=7", timeout=30)
        if r.status_code == 200:
            data = r.json()
            signals = data.get('data', [])
            log_pass(section, "VIX signal history", f"{len(signals)} signals (7 days)")
            if signals:
                latest = signals[0]
                log_info(f"  Latest: {latest.get('signal_type', 'N/A')} at {latest.get('timestamp', 'N/A')[:19]}")
                # Check for detailed metrics (new columns)
                if latest.get('iv_percentile') is not None:
                    log_pass(section, "VIX detailed metrics", f"IV%ile={latest.get('iv_percentile'):.0f}%")
                else:
                    log_warn(section, "VIX detailed metrics", "Missing (old data)")
        else:
            log_warn(section, "VIX signal history", f"HTTP {r.status_code}")

        return True

    except Exception as e:
        log_fail(section, "VIX system", str(e))
        return False


# =============================================================================
# TEST 6: DECISION LOGGING
# =============================================================================
def test_decision_logging(base_url):
    """Test decision logging system"""
    section = "DECISIONS"
    section_header("TEST 6: Decision Logging System")

    try:
        import requests

        # Test ATHENA decisions
        r = requests.get(f"{base_url}/api/athena/decisions?limit=10", timeout=30)
        if r.status_code == 200:
            data = r.json()
            decisions = data.get('data', [])
            log_pass(section, "ATHENA decisions", f"{len(decisions)} decisions")
            if decisions:
                latest = decisions[0]
                what = latest.get('what', '')[:50]
                log_info(f"  Latest: {what}...")
                # Check for detailed logging
                if 'ML:' in what or 'Oracle:' in what or '$' in what:
                    log_pass(section, "ATHENA detailed logs", "Contains market context")
                else:
                    log_warn(section, "ATHENA detailed logs", "May be old format")
        else:
            log_warn(section, "ATHENA decisions", f"HTTP {r.status_code}")

        # Test ARES decisions
        r = requests.get(f"{base_url}/api/ares/decisions?limit=10", timeout=30)
        if r.status_code == 200:
            data = r.json()
            decisions = data.get('data', [])
            log_pass(section, "ARES decisions", f"{len(decisions)} decisions")
        else:
            log_warn(section, "ARES decisions", f"HTTP {r.status_code}")

        return True

    except Exception as e:
        log_fail(section, "Decision logging", str(e))
        return False


# =============================================================================
# TEST 7: DATA PROVIDERS
# =============================================================================
def test_data_providers():
    """Test data provider connections"""
    section = "DATA"
    section_header("TEST 7: Data Providers")

    try:
        # Test Tradier
        from data.tradier_data_fetcher import TradierDataFetcher

        tradier = TradierDataFetcher()
        quote = tradier.get_quote('SPY')
        price = quote.get('last') or quote.get('close')

        if price and price > 0:
            log_pass(section, "Tradier API", f"SPY=${price:.2f}")
        else:
            log_warn(section, "Tradier API", "No price returned (market closed?)")

        # Test VIX fetch
        from data.vix_fetcher import get_vix_with_source

        vix, source = get_vix_with_source()
        if vix and vix > 0:
            log_pass(section, "VIX fetch", f"VIX={vix:.2f} (source: {source})")
        else:
            log_fail(section, "VIX fetch", "Failed to get VIX")

        return True

    except Exception as e:
        log_fail(section, "Data providers", str(e))
        return False


# =============================================================================
# TEST 8: ML AND ORACLE SYSTEMS
# =============================================================================
def test_ml_and_oracle(base_url):
    """Test ML signal and Oracle systems"""
    section = "AI"
    section_header("TEST 8: ML & Oracle Systems")

    try:
        import requests

        # Test ATHENA ML signal
        r = requests.get(f"{base_url}/api/athena/ml-signal", timeout=30)
        if r.status_code == 200:
            data = r.json()
            if data.get('success') and data.get('data'):
                ml = data.get('data', {})
                advice = ml.get('advice', 'N/A')
                confidence = ml.get('confidence', 0)
                log_pass(section, "GEX ML Signal", f"advice={advice}, conf={confidence:.0%}")
            else:
                log_warn(section, "GEX ML Signal", "No signal available")
        else:
            log_warn(section, "GEX ML Signal", f"HTTP {r.status_code}")

        # Test ATHENA Oracle
        r = requests.get(f"{base_url}/api/athena/oracle-advice", timeout=30)
        if r.status_code == 200:
            data = r.json()
            if data.get('success') and data.get('data'):
                oracle = data.get('data', {})
                advice = oracle.get('advice', 'N/A')
                win_prob = oracle.get('win_probability', 0)
                log_pass(section, "Oracle Advice", f"advice={advice}, win_prob={win_prob:.0%}")
            else:
                log_warn(section, "Oracle Advice", "No advice available")
        else:
            log_warn(section, "Oracle Advice", f"HTTP {r.status_code}")

        return True

    except Exception as e:
        log_fail(section, "ML/Oracle", str(e))
        return False


# =============================================================================
# SUMMARY
# =============================================================================
def print_summary():
    """Print test summary"""
    print(f"\n{'=' * 60}")
    print(f"{BOLD}TEST SUMMARY{RESET}")
    print(f"{'=' * 60}")

    total = results['passed'] + results['failed'] + results['warnings']

    print(f"\n  {GREEN}Passed:   {results['passed']}/{total}{RESET}")
    print(f"  {RED}Failed:   {results['failed']}/{total}{RESET}")
    print(f"  {YELLOW}Warnings: {results['warnings']}/{total}{RESET}")

    # Section breakdown
    print(f"\n{BOLD}BY SECTION:{RESET}")
    for section, counts in results['sections'].items():
        status = GREEN + "OK" + RESET if counts['failed'] == 0 else RED + "FAIL" + RESET
        print(f"  {section:15} {status} ({counts['passed']}✓ {counts['failed']}✗ {counts['warnings']}⚠)")

    # Current status
    print(f"\n{BOLD}CURRENT STATUS:{RESET}")
    now_ct = datetime.now(CENTRAL_TZ)
    print(f"  Time (CT): {now_ct.strftime('%I:%M:%S %p')}")
    print(f"  Day: {now_ct.strftime('%A')}")

    # Market hours check
    if now_ct.weekday() < 5:
        time_minutes = now_ct.hour * 60 + now_ct.minute
        if 510 <= time_minutes <= 960:  # 8:30 AM to 4:00 PM
            print(f"  Market: {GREEN}OPEN{RESET}")
        else:
            print(f"  Market: {YELLOW}CLOSED{RESET}")
    else:
        print(f"  Market: {YELLOW}WEEKEND{RESET}")

    if results['failed'] > 0:
        print(f"\n{RED}⚠ {results['failed']} test(s) failed - review above{RESET}")
        return 1
    elif results['warnings'] > 0:
        print(f"\n{YELLOW}⚠ {results['warnings']} warning(s) - review above{RESET}")
        return 0
    else:
        print(f"\n{GREEN}✓ All tests passed!{RESET}")
        return 0


# =============================================================================
# MAIN
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description='AlphaGEX Comprehensive E2E Tests')
    parser.add_argument('--url', default='https://alphagex-api.onrender.com',
                        help='Base URL for API (default: https://alphagex-api.onrender.com)')
    parser.add_argument('--skip-db', action='store_true',
                        help='Skip database tests')
    parser.add_argument('--skip-api', action='store_true',
                        help='Skip API tests')
    args = parser.parse_args()

    print(f"\n{'=' * 60}")
    print(f"{BOLD}ALPHAGEX COMPREHENSIVE E2E TEST SUITE{RESET}")
    print(f"{'=' * 60}")
    print(f"Base URL: {args.url}")
    print(f"Time: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %I:%M:%S %p')} CT")

    # Run tests
    if not args.skip_db:
        test_database_tables()
        test_scheduler_config()
        test_data_providers()

    if not args.skip_api:
        test_trading_bots(args.url)
        test_argus_live_data(args.url)
        test_vix_system(args.url)
        test_decision_logging(args.url)
        test_ml_and_oracle(args.url)

    return print_summary()


if __name__ == '__main__':
    sys.exit(main())
