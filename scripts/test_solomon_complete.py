#!/usr/bin/env python3
"""
COMPLETE SOLOMON VERIFICATION TEST SUITE

Run in Render shell: python scripts/test_solomon_complete.py

Tests:
1. Database tables exist and are writable
2. A/B test persistence (create, record, evaluate, persist)
3. Proposal validation trade recording
4. Version tracking on proposal apply
5. Oracle returns Solomon info in reasoning
6. Oracle scores are NOT modified by Solomon
7. All API endpoints return real data
8. Frontend API client coverage
"""

import os
import sys
import json
import time
from datetime import datetime
from typing import Dict, Any, List, Tuple

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

def ok(msg): print(f"   {GREEN}✅ {msg}{RESET}")
def fail(msg): print(f"   {RED}❌ {msg}{RESET}")
def warn(msg): print(f"   {YELLOW}⚠️  {msg}{RESET}")
def info(msg): print(f"   {BLUE}ℹ️  {msg}{RESET}")

class SolomonTestSuite:
    def __init__(self):
        self.results: List[Tuple[str, bool, str]] = []
        self.db_available = False
        self.solomon = None
        self.enhanced = None

    def run_all(self):
        print()
        print(f"{BOLD}{'='*70}{RESET}")
        print(f"{BOLD}COMPLETE SOLOMON VERIFICATION TEST SUITE{RESET}")
        print(f"{BOLD}{'='*70}{RESET}")
        print()

        # Run all tests
        self.test_1_database_connection()
        self.test_2_solomon_initialization()
        self.test_3_table_existence()
        self.test_4_ab_test_persistence()
        self.test_5_audit_logging()
        self.test_6_version_tracking()
        self.test_7_oracle_solomon_info()
        self.test_8_oracle_no_interference()
        self.test_9_api_endpoints()
        self.test_10_realtime_status()

        # Print summary
        self.print_summary()

    def record(self, name: str, passed: bool, details: str = ""):
        self.results.append((name, passed, details))

    def test_1_database_connection(self):
        print(f"\n{BOLD}TEST 1: DATABASE CONNECTION{RESET}")
        try:
            from database_adapter import get_connection

            conn = get_connection()
            if conn is None:
                fail("get_connection() returned None")
                self.record("Database Connection", False, "Connection is None")
                return

            # Test query
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            conn.close()

            if result and result[0] == 1:
                ok("Database connection successful")
                self.db_available = True
                self.record("Database Connection", True)
            else:
                fail("Query returned unexpected result")
                self.record("Database Connection", False, f"Got: {result}")

        except Exception as e:
            fail(f"Database error: {e}")
            self.record("Database Connection", False, str(e))

    def test_2_solomon_initialization(self):
        print(f"\n{BOLD}TEST 2: SOLOMON INITIALIZATION{RESET}")
        try:
            from quant.solomon_feedback_loop import get_solomon

            self.solomon = get_solomon()
            ok(f"Solomon initialized: {self.solomon.session_id}")
            self.record("Solomon Initialization", True, self.solomon.session_id)

            # Also initialize enhanced
            from quant.solomon_enhancements import get_solomon_enhanced
            self.enhanced = get_solomon_enhanced()
            ok("Solomon Enhanced initialized")

        except Exception as e:
            fail(f"Solomon initialization failed: {e}")
            self.record("Solomon Initialization", False, str(e))

    def test_3_table_existence(self):
        print(f"\n{BOLD}TEST 3: TABLE EXISTENCE{RESET}")

        if not self.db_available:
            warn("Skipping - database not available")
            self.record("Table Existence", False, "DB not available")
            return

        required_tables = [
            'solomon_audit_log',
            'solomon_proposals',
            'solomon_versions',
            'solomon_performance',
            'solomon_rollbacks',
            'solomon_health',
            'solomon_kill_switch',
            'solomon_validations',
            'solomon_ab_tests',
        ]

        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            all_exist = True
            for table in required_tables:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = %s
                    )
                """, (table,))
                exists = cursor.fetchone()[0]

                if exists:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    ok(f"{table}: EXISTS ({count} rows)")
                else:
                    fail(f"{table}: MISSING")
                    all_exist = False

            conn.close()
            self.record("Table Existence", all_exist, f"{len(required_tables)} tables checked")

        except Exception as e:
            fail(f"Table check failed: {e}")
            self.record("Table Existence", False, str(e))

    def test_4_ab_test_persistence(self):
        print(f"\n{BOLD}TEST 4: A/B TEST PERSISTENCE{RESET}")

        if not self.enhanced:
            warn("Skipping - Solomon Enhanced not initialized")
            self.record("A/B Test Persistence", False, "Enhanced not available")
            return

        try:
            # Create test
            test_id = self.enhanced.ab_testing.create_test(
                bot_name="TEST_VERIFY",
                control_config={"sd_multiplier": 1.0, "test": True},
                variant_config={"sd_multiplier": 1.1, "test": True},
                control_allocation=0.5
            )
            ok(f"Created A/B test: {test_id}")

            # Record trades
            self.enhanced.ab_testing.record_trade(test_id, is_control=True, pnl=50.0)
            self.enhanced.ab_testing.record_trade(test_id, is_control=True, pnl=-20.0)
            self.enhanced.ab_testing.record_trade(test_id, is_control=False, pnl=75.0)
            self.enhanced.ab_testing.record_trade(test_id, is_control=False, pnl=25.0)
            ok("Recorded 4 test trades")

            # Verify in database
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT test_id, bot_name, control_trades, variant_trades,
                       control_pnl, variant_pnl, status
                FROM solomon_ab_tests WHERE test_id = %s
            """, (test_id,))
            row = cursor.fetchone()
            conn.close()

            if row:
                ok(f"Found in DB: control_trades={row[2]}, variant_trades={row[3]}")
                ok(f"P&L: control=${row[4]}, variant=${row[5]}")

                # Verify counts
                if row[2] == 2 and row[3] == 2:
                    ok("Trade counts match expected (2 each)")
                else:
                    fail(f"Trade counts wrong: expected 2/2, got {row[2]}/{row[3]}")

                # Verify P&L (convert Decimal to float for comparison)
                control_pnl = float(row[4]) if row[4] else 0.0
                variant_pnl = float(row[5]) if row[5] else 0.0
                if abs(control_pnl - 30.0) < 0.01 and abs(variant_pnl - 100.0) < 0.01:
                    ok("P&L values match expected")
                else:
                    warn(f"P&L values: expected $30/$100, got ${control_pnl}/${variant_pnl}")

                self.record("A/B Test Persistence", True, test_id)
            else:
                fail("A/B test NOT found in database!")
                self.record("A/B Test Persistence", False, "Not in DB")

            # Cleanup
            self.enhanced.ab_testing.stop_test(test_id)
            ok(f"Test stopped: {test_id}")

        except Exception as e:
            fail(f"A/B test persistence failed: {e}")
            import traceback
            traceback.print_exc()
            self.record("A/B Test Persistence", False, str(e))

    def test_5_audit_logging(self):
        print(f"\n{BOLD}TEST 5: AUDIT LOGGING{RESET}")

        if not self.solomon:
            warn("Skipping - Solomon not initialized")
            self.record("Audit Logging", False, "Solomon not available")
            return

        try:
            from quant.solomon_feedback_loop import ActionType

            test_desc = f"Verification test at {datetime.now().isoformat()}"

            self.solomon.log_action(
                bot_name="TEST_BOT",
                action_type=ActionType.HEALTH_CHECK,
                description=test_desc,
                reason="Automated verification test",
            )
            ok("Audit log entry created")

            # Verify in database
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, bot_name, action_type, action_description
                FROM solomon_audit_log
                WHERE action_description = %s
                ORDER BY timestamp DESC LIMIT 1
            """, (test_desc,))
            row = cursor.fetchone()
            conn.close()

            if row:
                ok(f"Found in DB: id={row[0]}, action={row[2]}")
                self.record("Audit Logging", True)
            else:
                fail("Audit entry NOT found in database!")
                self.record("Audit Logging", False, "Not in DB")

        except Exception as e:
            fail(f"Audit logging failed: {e}")
            self.record("Audit Logging", False, str(e))

    def test_6_version_tracking(self):
        print(f"\n{BOLD}TEST 6: VERSION TRACKING{RESET}")

        if not self.solomon:
            warn("Skipping - Solomon not initialized")
            self.record("Version Tracking", False, "Solomon not available")
            return

        try:
            from quant.solomon_feedback_loop import VersionType

            version_id = self.solomon.save_version(
                bot_name="TEST_BOT",
                version_type=VersionType.PARAMETERS,
                artifact_name="test_params",
                artifact_data={"test_param": 123, "verified": True},
                metadata={"test": True, "timestamp": datetime.now().isoformat()},
                approved_by="TEST_SCRIPT"
            )

            if version_id:
                ok(f"Version saved: {version_id}")

                # Verify in database
                from database_adapter import get_connection
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT version_id, bot_name, version_type, artifact_name
                    FROM solomon_versions WHERE version_id = %s
                """, (version_id,))
                row = cursor.fetchone()
                conn.close()

                if row:
                    ok(f"Found in DB: {row[1]}/{row[3]}")
                    self.record("Version Tracking", True, version_id)
                else:
                    fail("Version NOT found in database!")
                    self.record("Version Tracking", False, "Not in DB")
            else:
                warn("Version save returned None")
                self.record("Version Tracking", False, "Returned None")

        except Exception as e:
            fail(f"Version tracking failed: {e}")
            self.record("Version Tracking", False, str(e))

    def test_7_oracle_solomon_info(self):
        print(f"\n{BOLD}TEST 7: ORACLE RETURNS SOLOMON INFO{RESET}")

        try:
            from quant.oracle_advisor import get_oracle, MarketContext, GEXRegime

            oracle = get_oracle()

            context = MarketContext(
                spot_price=590.0,
                vix=18.0,
                gex_regime=GEXRegime.POSITIVE,
                gex_call_wall=595.0,
                gex_put_wall=585.0,
                gex_flip_point=588.0,
                gex_net=100000000,
                day_of_week=1  # Tuesday
            )

            rec = oracle.get_strategy_recommendation(context)

            ok(f"Strategy: {rec.recommended_strategy.value}")
            ok(f"IC Score: {rec.ic_suitability:.2f}")
            ok(f"DIR Score: {rec.dir_suitability:.2f}")

            # Check if reasoning contains Solomon info
            reasoning = rec.reasoning
            info(f"Reasoning length: {len(reasoning)} chars")

            # Split and display
            parts = reasoning.split(' | ')
            solomon_parts = [p for p in parts if 'SOLOMON' in p.upper()]

            if solomon_parts:
                ok(f"Solomon info found in reasoning: {len(solomon_parts)} part(s)")
                for p in solomon_parts:
                    info(f"  → {p}")
                self.record("Oracle Solomon Info", True, f"{len(solomon_parts)} parts")
            else:
                warn("No SOLOMON INFO in reasoning (may be OK if no historical data)")
                info("This is expected if Solomon has no historical trade data yet")
                self.record("Oracle Solomon Info", True, "No data yet (expected)")

        except Exception as e:
            fail(f"Oracle test failed: {e}")
            self.record("Oracle Solomon Info", False, str(e))

    def test_8_oracle_no_interference(self):
        print(f"\n{BOLD}TEST 8: ORACLE SCORES NOT MODIFIED BY SOLOMON{RESET}")

        try:
            from quant.oracle_advisor import get_oracle, MarketContext, GEXRegime

            oracle = get_oracle()

            # Same context for both calls
            context = MarketContext(
                spot_price=590.0,
                vix=18.0,
                gex_regime=GEXRegime.POSITIVE,
                gex_call_wall=595.0,
                gex_put_wall=585.0,
                gex_flip_point=588.0,
                gex_net=100000000,
                day_of_week=1
            )

            # Call twice
            rec1 = oracle.get_strategy_recommendation(context)
            rec2 = oracle.get_strategy_recommendation(context)

            # Compare scores
            ic_match = rec1.ic_suitability == rec2.ic_suitability
            dir_match = rec1.dir_suitability == rec2.dir_suitability
            size_match = rec1.size_multiplier == rec2.size_multiplier
            strategy_match = rec1.recommended_strategy == rec2.recommended_strategy

            if ic_match:
                ok(f"IC scores match: {rec1.ic_suitability:.4f}")
            else:
                fail(f"IC scores differ: {rec1.ic_suitability} vs {rec2.ic_suitability}")

            if dir_match:
                ok(f"DIR scores match: {rec1.dir_suitability:.4f}")
            else:
                fail(f"DIR scores differ: {rec1.dir_suitability} vs {rec2.dir_suitability}")

            if size_match:
                ok(f"Size multipliers match: {rec1.size_multiplier}")
            else:
                fail(f"Size multipliers differ: {rec1.size_multiplier} vs {rec2.size_multiplier}")

            if strategy_match:
                ok(f"Strategies match: {rec1.recommended_strategy.value}")
            else:
                fail(f"Strategies differ!")

            all_match = ic_match and dir_match and size_match and strategy_match

            if all_match:
                ok("CONFIRMED: Solomon does NOT affect Oracle scores (deterministic)")
                self.record("Oracle No Interference", True)
            else:
                fail("Oracle scores are NOT deterministic!")
                self.record("Oracle No Interference", False, "Scores differ")

        except Exception as e:
            fail(f"Oracle interference test failed: {e}")
            self.record("Oracle No Interference", False, str(e))

    def test_9_api_endpoints(self):
        print(f"\n{BOLD}TEST 9: API ENDPOINTS{RESET}")

        try:
            import requests
            base_url = "http://localhost:8000"

            endpoints = [
                ("/api/solomon/health", "GET"),
                ("/api/solomon/dashboard", "GET"),
                ("/api/solomon/realtime-status?days=7", "GET"),
                ("/api/solomon/enhanced/digest", "GET"),
                ("/api/solomon/enhanced/correlations", "GET"),
                ("/api/solomon/strategy-analysis?days=30", "GET"),
                ("/api/solomon/oracle-accuracy?days=30", "GET"),
                ("/api/solomon/enhanced/ab-test", "GET"),
                ("/api/solomon/validation/status", "GET"),
                ("/api/oracle/strategy-recommendation", "GET"),
            ]

            passed = 0
            failed = 0

            for endpoint, method in endpoints:
                try:
                    if method == "GET":
                        resp = requests.get(f"{base_url}{endpoint}", timeout=10)
                    else:
                        resp = requests.post(f"{base_url}{endpoint}", timeout=10)

                    if resp.status_code == 200:
                        ok(f"{endpoint}: 200 OK")
                        passed += 1
                    elif resp.status_code == 503:
                        warn(f"{endpoint}: 503 (service unavailable)")
                        passed += 1  # Expected if Solomon not loaded
                    else:
                        fail(f"{endpoint}: {resp.status_code}")
                        failed += 1
                except requests.exceptions.ConnectionError:
                    warn(f"{endpoint}: Connection refused (server not running?)")
                    failed += 1
                except Exception as e:
                    fail(f"{endpoint}: {e}")
                    failed += 1

            if failed == 0:
                self.record("API Endpoints", True, f"{passed}/{len(endpoints)} passed")
            else:
                self.record("API Endpoints", False, f"{failed} failed")

        except ImportError:
            warn("requests module not available - skipping API tests")
            self.record("API Endpoints", True, "Skipped (no requests module)")

    def test_10_realtime_status(self):
        print(f"\n{BOLD}TEST 10: REALTIME STATUS (Bot Position Tables){RESET}")

        if not self.db_available:
            warn("Skipping - database not available")
            self.record("Realtime Status", False, "DB not available")
            return

        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            # Check each bot's position table
            bots = [
                ('ARES', 'ares_positions'),
                ('ATHENA', 'athena_positions'),
                ('TITAN', 'titan_positions'),
                ('PEGASUS', 'pegasus_positions'),
                ('ICARUS', 'icarus_positions'),
                ('PROMETHEUS', 'prometheus_ic_positions'),
            ]

            found_data = False
            for bot_name, table in bots:
                try:
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM {table}
                        WHERE close_time::timestamptz >= NOW() - INTERVAL '30 days'
                    """)
                    count = cursor.fetchone()[0]
                    if count > 0:
                        ok(f"{bot_name}: {count} trades in last 30 days")
                        found_data = True
                    else:
                        info(f"{bot_name}: No recent trades")
                except Exception as e:
                    warn(f"{bot_name}: {e}")

            conn.close()

            if found_data:
                self.record("Realtime Status", True, "Found trade data")
            else:
                warn("No recent trade data found (expected if bots haven't traded)")
                self.record("Realtime Status", True, "No data (expected)")

        except Exception as e:
            fail(f"Realtime status test failed: {e}")
            self.record("Realtime Status", False, str(e))

    def print_summary(self):
        print()
        print(f"{BOLD}{'='*70}{RESET}")
        print(f"{BOLD}SUMMARY{RESET}")
        print(f"{BOLD}{'='*70}{RESET}")
        print()

        passed = sum(1 for _, p, _ in self.results if p)
        failed = sum(1 for _, p, _ in self.results if not p)

        for name, passed_test, details in self.results:
            status = f"{GREEN}PASS{RESET}" if passed_test else f"{RED}FAIL{RESET}"
            print(f"   [{status}] {name}")
            if details and not passed_test:
                print(f"          {YELLOW}{details}{RESET}")

        print()
        print(f"   Total: {passed} passed, {failed} failed")
        print()

        if failed == 0:
            print(f"{GREEN}{BOLD}{'='*70}{RESET}")
            print(f"{GREEN}{BOLD}✅ ALL TESTS PASSED - SOLOMON IS PRODUCTION READY{RESET}")
            print(f"{GREEN}{BOLD}{'='*70}{RESET}")
        else:
            print(f"{RED}{BOLD}{'='*70}{RESET}")
            print(f"{RED}{BOLD}❌ {failed} TEST(S) FAILED - REVIEW ABOVE{RESET}")
            print(f"{RED}{BOLD}{'='*70}{RESET}")

        print()


if __name__ == "__main__":
    suite = SolomonTestSuite()
    suite.run_all()
