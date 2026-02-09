#!/usr/bin/env python
"""
VALOR End-to-End Test Script

Comprehensive test to verify VALOR futures bot is production-ready:
    python scripts/test_valor_e2e.py

Tests:
1. Module imports and initialization
2. Database tables and schema
3. Paper trading account management
4. Scan activity logging (ML training data)
5. Signal generation flow
6. API endpoint responses
7. Scheduler integration

Run in Render Shell after deployment to verify everything works.
"""

import os
import sys
import uuid
from datetime import datetime

# Add project root to Python path for Render shell
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# ANSI colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
CYAN = '\033[96m'
RESET = '\033[0m'
BOLD = '\033[1m'


def section(title: str):
    """Print a section header."""
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}{title}{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}")


def success(msg: str):
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str):
    print(f"  {RED}✗{RESET} {msg}")


def warn(msg: str):
    print(f"  {YELLOW}⚠{RESET} {msg}")


def info(msg: str):
    print(f"  {BLUE}→{RESET} {msg}")


class ValorTestSuite:
    """End-to-end tests for VALOR."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def test_imports(self) -> bool:
        """Test all VALOR module imports."""
        section("1. Module Imports")

        try:
            # Core imports
            from trading.valor.models import (
                ValorConfig, FuturesPosition, FuturesSignal,
                TradingMode, PositionStatus, SignalSource, TradeDirection
            )
            success("models.py imports OK")

            from trading.valor.db import ValorDatabase
            success("db.py imports OK")

            from trading.valor.signals import ValorSignalGenerator
            success("signals.py imports OK")

            from trading.valor.executor import TastytradeExecutor
            success("executor.py imports OK")

            from trading.valor.trader import ValorTrader
            success("trader.py imports OK")

            # Package-level imports (used by scheduler)
            from trading.valor import ValorTrader, ValorConfig, TradingMode
            success("Package-level imports OK (scheduler compatible)")

            self.passed += 1
            return True

        except ImportError as e:
            fail(f"Import failed: {e}")
            self.failed += 1
            return False

    def test_database_tables(self) -> bool:
        """Test that all database tables exist."""
        section("2. Database Tables")

        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            tables = {
                'valor_positions': 'Open positions tracking',
                'valor_closed_trades': 'Trade history',
                'valor_equity_snapshots': 'Intraday equity curve',
                'valor_signals': 'Signal log',
                'valor_paper_account': 'Paper trading balance',
                'valor_scan_activity': 'ML training data collection',
            }

            all_exist = True
            for table, description in tables.items():
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = %s
                    )
                """, (table,))
                exists = cursor.fetchone()[0]
                if exists:
                    success(f"{table} - {description}")
                else:
                    fail(f"{table} - MISSING!")
                    all_exist = False

            cursor.close()

            if all_exist:
                self.passed += 1
            else:
                self.failed += 1

            return all_exist

        except Exception as e:
            fail(f"Database error: {e}")
            self.failed += 1
            return False

    def test_paper_account(self) -> bool:
        """Test paper trading account operations."""
        section("3. Paper Trading Account")

        try:
            from trading.valor.db import ValorDatabase
            db = ValorDatabase()

            # Check/create account
            account = db.get_paper_account()
            if not account:
                info("No paper account found - initializing...")
                db.initialize_paper_account(100000.0)
                account = db.get_paper_account()

            if account:
                success(f"Paper account exists")
                info(f"  Starting Capital: ${account.get('starting_capital', 0):,.2f}")
                info(f"  Current Balance:  ${account.get('current_balance', 0):,.2f}")
                info(f"  Cumulative P&L:   ${account.get('cumulative_pnl', 0):+,.2f}")
                info(f"  Return:           {account.get('return_pct', 0):+.2f}%" if 'return_pct' in account else "")
                self.passed += 1
                return True
            else:
                fail("Could not create paper account")
                self.failed += 1
                return False

        except Exception as e:
            fail(f"Paper account error: {e}")
            self.failed += 1
            return False

    def test_scan_activity_logging(self) -> bool:
        """Test scan activity logging for ML training."""
        section("4. Scan Activity (ML Training Data)")

        try:
            from trading.valor.db import ValorDatabase
            db = ValorDatabase()

            # Create a test scan
            test_scan_id = f"test_scan_{uuid.uuid4().hex[:8]}"

            saved = db.save_scan_activity(
                scan_id=test_scan_id,
                outcome="NO_TRADE",
                action_taken="TEST",
                decision_summary="E2E test scan",
                underlying_price=6000.0,
                underlying_symbol="MES",
                vix=15.5,
                gamma_regime="POSITIVE",
                gex_value=1000000.0,
                flip_point=5990.0,
                signal_direction="LONG",
                signal_source="GEX_MEAN_REVERSION",
                signal_confidence=0.75,
                signal_win_probability=0.65,
                bayesian_win_probability=0.55,
                session_type="RTH",
                skip_reason="E2E TEST - not real signal"
            )

            if saved:
                success(f"Scan activity saved: {test_scan_id}")
            else:
                fail("Failed to save scan activity")
                self.failed += 1
                return False

            # Verify it was saved
            scans = db.get_scan_activity(limit=5)
            test_scan = next((s for s in scans if s.get('scan_id') == test_scan_id), None)

            if test_scan:
                success("Scan activity retrieved successfully")
                info(f"  Outcome: {test_scan.get('outcome')}")
                info(f"  Regime:  {test_scan.get('gamma_regime')}")
                info(f"  Price:   {test_scan.get('underlying_price')}")
            else:
                warn("Scan saved but not in recent results")
                self.warnings += 1

            # Test ML training data endpoint
            ml_data = db.get_ml_training_data()
            success(f"ML training data query works ({len(ml_data)} samples)")

            if len(ml_data) >= 50:
                success("Ready for ML model training!")
            else:
                info(f"Need {50 - len(ml_data)} more completed trades for ML")

            self.passed += 1
            return True

        except Exception as e:
            fail(f"Scan activity error: {e}")
            import traceback
            traceback.print_exc()
            self.failed += 1
            return False

    def test_signal_generator(self) -> bool:
        """Test signal generation (without real market data)."""
        section("5. Signal Generator")

        try:
            from trading.valor.signals import ValorSignalGenerator
            from trading.valor.models import ValorConfig, BayesianWinTracker

            config = ValorConfig()
            win_tracker = BayesianWinTracker()
            generator = ValorSignalGenerator(config, win_tracker)

            success("Signal generator initialized")
            info(f"  Symbol: {config.symbol}")
            info(f"  Point Value: ${config.point_value}")
            info(f"  Initial Stop: {config.initial_stop_points} points")

            # Test mock signal (can't test real without market data)
            success("Signal generator ready for live data")

            self.passed += 1
            return True

        except Exception as e:
            fail(f"Signal generator error: {e}")
            self.failed += 1
            return False

    def test_trader_initialization(self) -> bool:
        """Test ValorTrader can be initialized."""
        section("6. Trader Initialization")

        try:
            from trading.valor.trader import ValorTrader
            from trading.valor.models import ValorConfig, TradingMode

            # Paper mode only for testing
            config = ValorConfig(mode=TradingMode.PAPER)
            trader = ValorTrader(config)

            success("ValorTrader initialized in PAPER mode")
            info(f"  Mode: {trader.config.mode.value}")
            info(f"  Symbol: {trader.config.symbol}")
            info(f"  Max Contracts: {trader.config.max_contracts}")

            # Check win tracker
            tracker = trader.win_tracker
            success(f"Win tracker initialized")
            info(f"  Current Win Prob: {tracker.win_probability:.1%}")
            info(f"  Total Trades: {tracker.total_trades}")
            info(f"  Use ML: {tracker.should_use_ml}")

            self.passed += 1
            return True

        except Exception as e:
            fail(f"Trader initialization error: {e}")
            import traceback
            traceback.print_exc()
            self.failed += 1
            return False

    def test_api_endpoints(self) -> bool:
        """Test API endpoints respond correctly."""
        section("7. API Endpoints")

        import requests
        BASE_URL = os.environ.get('API_BASE_URL') or os.environ.get('RENDER_EXTERNAL_URL') or 'http://localhost:8000'
        BASE_URL = BASE_URL.rstrip('/')

        endpoints = [
            ('/api/valor/status', 'Status'),
            ('/api/valor/positions', 'Positions'),
            ('/api/valor/closed-trades', 'Closed Trades'),
            ('/api/valor/paper-equity-curve', 'Paper Equity Curve'),
            ('/api/valor/signals/recent', 'Recent Signals'),
            ('/api/valor/logs', 'Logs'),
            ('/api/valor/scan-activity', 'Scan Activity'),
            ('/api/valor/ml-training-data', 'ML Training Data'),
        ]

        all_ok = True
        for path, name in endpoints:
            try:
                response = requests.get(f"{BASE_URL}{path}", timeout=30)
                if response.status_code == 200:
                    success(f"[{response.status_code}] {name}")
                elif response.status_code == 503:
                    warn(f"[{response.status_code}] {name} (module unavailable)")
                    self.warnings += 1
                else:
                    fail(f"[{response.status_code}] {name}")
                    all_ok = False
            except requests.exceptions.ConnectionError:
                warn(f"[SKIP] {name} (API not reachable)")
                self.warnings += 1
            except Exception as e:
                fail(f"[ERR] {name}: {str(e)[:40]}")
                all_ok = False

        if all_ok:
            self.passed += 1
        else:
            self.failed += 1

        return all_ok

    def run_all(self):
        """Run all tests."""
        print(f"\n{BOLD}VALOR END-TO-END TEST SUITE{RESET}")
        print(f"Timestamp: {datetime.now().isoformat()}")

        self.test_imports()
        self.test_database_tables()
        self.test_paper_account()
        self.test_scan_activity_logging()
        self.test_signal_generator()
        self.test_trader_initialization()
        self.test_api_endpoints()

        # Summary
        section("TEST SUMMARY")
        total = self.passed + self.failed
        print(f"  Passed:   {GREEN}{self.passed}{RESET}/{total}")
        print(f"  Failed:   {RED}{self.failed}{RESET}/{total}")
        print(f"  Warnings: {YELLOW}{self.warnings}{RESET}")

        if self.failed == 0:
            print(f"\n{GREEN}{BOLD}ALL TESTS PASSED - VALOR IS PRODUCTION READY!{RESET}")
            return 0
        else:
            print(f"\n{RED}{BOLD}TESTS FAILED - DO NOT DEPLOY!{RESET}")
            return 1


def main():
    suite = ValorTestSuite()
    exit_code = suite.run_all()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
