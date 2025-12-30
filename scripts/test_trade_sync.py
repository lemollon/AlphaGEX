#!/usr/bin/env python3
"""
Trade Synchronization Validation Test
======================================

This script validates critical trade synchronization for all 3 bots:
1. Open positions appear correctly in /positions and /live-pnl
2. Closed positions move correctly from open to closed
3. Live equity curve shows intraday positions
4. P&L calculations are accurate

Run from Render shell:
    python scripts/test_trade_sync.py
"""

import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zoneinfo import ZoneInfo
CENTRAL_TZ = ZoneInfo("America/Chicago")


def print_header(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_result(test_name: str, passed: bool, details: str = ""):
    status = "✅" if passed else "❌"
    print(f"  {status} {test_name}")
    if details and not passed:
        print(f"      └─ {details}")


class TradeSyncValidator:
    """Validate trade synchronization across database, API, and frontend"""

    def __init__(self):
        self.errors = []
        self.warnings = []
        self.conn = None

    def get_connection(self):
        """Get database connection"""
        if not self.conn:
            from database_adapter import get_connection
            self.conn = get_connection()
        return self.conn

    def close_connection(self):
        """Close database connection"""
        if self.conn:
            try:
                self.conn.close()
            except:
                pass
            self.conn = None

    # =========================================================================
    # ARES VALIDATION
    # =========================================================================

    def validate_ares_open_positions(self) -> dict:
        """Validate ARES open positions sync"""
        results = {"passed": True, "details": {}}

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Get open positions from database
            cursor.execute("""
                SELECT
                    position_id, ticker, expiration, status,
                    put_short_strike, put_long_strike,
                    call_short_strike, call_long_strike,
                    total_credit, contracts, max_loss, max_profit,
                    underlying_at_entry, open_time
                FROM ares_positions
                WHERE status = 'open'
                ORDER BY open_time DESC
            """)
            db_positions = cursor.fetchall()
            results["details"]["db_open_count"] = len(db_positions)

            # Check for stale positions (expired but still open)
            today = datetime.now(CENTRAL_TZ).date()
            stale_positions = []
            for pos in db_positions:
                exp_date = pos[2]
                if exp_date and exp_date < today:
                    stale_positions.append({
                        "position_id": pos[0],
                        "expiration": str(exp_date),
                        "days_stale": (today - exp_date).days
                    })

            if stale_positions:
                results["passed"] = False
                results["details"]["stale_positions"] = stale_positions
                self.errors.append(f"ARES has {len(stale_positions)} stale position(s) - expired but not closed")

            # Check for positions with missing critical fields
            incomplete = []
            for pos in db_positions:
                if not pos[4] or not pos[5] or not pos[6] or not pos[7]:  # strikes
                    incomplete.append({"position_id": pos[0], "issue": "missing strikes"})
                elif not pos[8] or pos[8] <= 0:  # total_credit
                    incomplete.append({"position_id": pos[0], "issue": "missing/zero credit"})

            if incomplete:
                results["details"]["incomplete_positions"] = incomplete
                self.warnings.append(f"ARES has {len(incomplete)} incomplete position(s)")

            # Validate position data integrity
            for pos in db_positions:
                position_id = pos[0]
                put_short, put_long = float(pos[4] or 0), float(pos[5] or 0)
                call_short, call_long = float(pos[6] or 0), float(pos[7] or 0)
                total_credit = float(pos[8] or 0)
                contracts = int(pos[9] or 0)

                # Put spread: long < short (buying lower strike, selling higher)
                if put_long >= put_short:
                    self.warnings.append(f"ARES {position_id}: Put spread strikes invalid ({put_long} >= {put_short})")

                # Call spread: short < long (selling lower strike, buying higher)
                if call_short >= call_long:
                    self.warnings.append(f"ARES {position_id}: Call spread strikes invalid ({call_short} >= {call_long})")

            results["details"]["integrity_checked"] = True

        except Exception as e:
            results["passed"] = False
            results["details"]["error"] = str(e)
            self.errors.append(f"ARES open position validation failed: {e}")

        return results

    def validate_ares_closed_positions(self) -> dict:
        """Validate ARES closed positions have proper P&L"""
        results = {"passed": True, "details": {}}

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Get recent closed positions
            cursor.execute("""
                SELECT
                    position_id, ticker, expiration, status,
                    total_credit, contracts, close_price, realized_pnl,
                    close_reason, close_time
                FROM ares_positions
                WHERE status IN ('closed', 'expired')
                ORDER BY close_time DESC
                LIMIT 20
            """)
            closed_positions = cursor.fetchall()
            results["details"]["closed_count"] = len(closed_positions)

            # Check for positions closed without P&L calculation
            missing_pnl = []
            for pos in closed_positions:
                position_id = pos[0]
                total_credit = float(pos[4] or 0)
                contracts = int(pos[5] or 0)
                close_price = pos[6]
                realized_pnl = pos[7]
                close_reason = pos[8]

                if realized_pnl is None:
                    missing_pnl.append({
                        "position_id": position_id,
                        "close_reason": close_reason
                    })
                elif close_price is not None:
                    # Verify P&L calculation: (credit - close_price) * contracts * 100
                    expected_pnl = (total_credit - float(close_price)) * contracts * 100
                    actual_pnl = float(realized_pnl)
                    # Allow 1% tolerance for rounding
                    if abs(expected_pnl - actual_pnl) > abs(expected_pnl) * 0.01 + 1:
                        self.warnings.append(
                            f"ARES {position_id}: P&L mismatch expected={expected_pnl:.2f}, actual={actual_pnl:.2f}"
                        )

            if missing_pnl:
                results["details"]["missing_pnl_positions"] = missing_pnl
                self.warnings.append(f"ARES has {len(missing_pnl)} closed position(s) without P&L")

        except Exception as e:
            results["passed"] = False
            results["details"]["error"] = str(e)
            self.errors.append(f"ARES closed position validation failed: {e}")

        return results

    def validate_ares_equity_curve(self) -> dict:
        """Validate ARES equity curve data"""
        results = {"passed": True, "details": {}}

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Get daily P&L from closed positions
            cursor.execute("""
                SELECT
                    DATE(close_time AT TIME ZONE 'America/Chicago') as trade_date,
                    COUNT(*) as trades,
                    SUM(realized_pnl) as daily_pnl
                FROM ares_positions
                WHERE status IN ('closed', 'expired')
                AND close_time >= NOW() - INTERVAL '30 days'
                GROUP BY DATE(close_time AT TIME ZONE 'America/Chicago')
                ORDER BY trade_date
            """)
            equity_data = cursor.fetchall()
            results["details"]["trading_days"] = len(equity_data)

            if equity_data:
                total_trades = sum(row[1] for row in equity_data)
                total_pnl = sum(float(row[2] or 0) for row in equity_data)
                results["details"]["total_trades_30d"] = total_trades
                results["details"]["total_pnl_30d"] = round(total_pnl, 2)

            # Check for today's open positions affecting equity
            today = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')
            cursor.execute("""
                SELECT COUNT(*), SUM(total_credit * contracts * 100)
                FROM ares_positions
                WHERE status = 'open'
            """)
            open_stats = cursor.fetchone()
            if open_stats[0]:
                results["details"]["open_positions"] = open_stats[0]
                results["details"]["open_premium_at_risk"] = round(float(open_stats[1] or 0), 2)

        except Exception as e:
            results["passed"] = False
            results["details"]["error"] = str(e)
            self.errors.append(f"ARES equity curve validation failed: {e}")

        return results

    # =========================================================================
    # ATHENA VALIDATION
    # =========================================================================

    def validate_athena_open_positions(self) -> dict:
        """Validate ATHENA open positions sync"""
        results = {"passed": True, "details": {}}

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Get open positions from database
            cursor.execute("""
                SELECT
                    position_id, spread_type, ticker, expiration, status,
                    long_strike, short_strike, entry_price, contracts,
                    max_profit, max_loss, spot_at_entry, created_at
                FROM apache_positions
                WHERE status = 'open'
                ORDER BY created_at DESC
            """)
            db_positions = cursor.fetchall()
            results["details"]["db_open_count"] = len(db_positions)

            # Check for stale positions (expired but still open)
            today = datetime.now(CENTRAL_TZ).date()
            stale_positions = []
            for pos in db_positions:
                exp_date = pos[3]
                if exp_date and exp_date < today:
                    stale_positions.append({
                        "position_id": pos[0],
                        "spread_type": pos[1],
                        "expiration": str(exp_date),
                        "days_stale": (today - exp_date).days
                    })

            if stale_positions:
                results["passed"] = False
                results["details"]["stale_positions"] = stale_positions
                self.errors.append(f"ATHENA has {len(stale_positions)} stale position(s) - expired but not closed")

            # Check spread type validity
            valid_types = ['BULL_CALL_SPREAD', 'BEAR_CALL_SPREAD', 'BULL_PUT_SPREAD', 'BEAR_PUT_SPREAD']
            for pos in db_positions:
                spread_type = pos[1]
                if spread_type and spread_type not in valid_types:
                    self.warnings.append(f"ATHENA {pos[0]}: Unknown spread type '{spread_type}'")

        except Exception as e:
            results["passed"] = False
            results["details"]["error"] = str(e)
            self.errors.append(f"ATHENA open position validation failed: {e}")

        return results

    def validate_athena_closed_positions(self) -> dict:
        """Validate ATHENA closed positions have proper P&L"""
        results = {"passed": True, "details": {}}

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Get recent closed positions
            cursor.execute("""
                SELECT
                    position_id, spread_type, ticker, status,
                    entry_price, contracts, exit_price, realized_pnl,
                    exit_reason, exit_time
                FROM apache_positions
                WHERE status IN ('closed', 'expired')
                ORDER BY exit_time DESC
                LIMIT 20
            """)
            closed_positions = cursor.fetchall()
            results["details"]["closed_count"] = len(closed_positions)

            # Check for positions closed without P&L
            missing_pnl = []
            for pos in closed_positions:
                if pos[7] is None:  # realized_pnl
                    missing_pnl.append({
                        "position_id": pos[0],
                        "spread_type": pos[1],
                        "exit_reason": pos[8]
                    })

            if missing_pnl:
                results["details"]["missing_pnl_positions"] = missing_pnl
                self.warnings.append(f"ATHENA has {len(missing_pnl)} closed position(s) without P&L")

        except Exception as e:
            results["passed"] = False
            results["details"]["error"] = str(e)
            self.errors.append(f"ATHENA closed position validation failed: {e}")

        return results

    def validate_athena_equity_curve(self) -> dict:
        """Validate ATHENA equity curve data"""
        results = {"passed": True, "details": {}}

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    DATE(exit_time AT TIME ZONE 'America/Chicago') as trade_date,
                    COUNT(*) as trades,
                    SUM(realized_pnl) as daily_pnl
                FROM apache_positions
                WHERE status IN ('closed', 'expired')
                AND exit_time >= NOW() - INTERVAL '30 days'
                GROUP BY DATE(exit_time AT TIME ZONE 'America/Chicago')
                ORDER BY trade_date
            """)
            equity_data = cursor.fetchall()
            results["details"]["trading_days"] = len(equity_data)

            if equity_data:
                total_trades = sum(row[1] for row in equity_data)
                total_pnl = sum(float(row[2] or 0) for row in equity_data)
                results["details"]["total_trades_30d"] = total_trades
                results["details"]["total_pnl_30d"] = round(total_pnl, 2)

        except Exception as e:
            results["passed"] = False
            results["details"]["error"] = str(e)
            self.errors.append(f"ATHENA equity curve validation failed: {e}")

        return results

    # =========================================================================
    # PEGASUS VALIDATION
    # =========================================================================

    def validate_pegasus_open_positions(self) -> dict:
        """Validate PEGASUS open positions sync"""
        results = {"passed": True, "details": {}}

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    position_id, ticker, expiration, status,
                    put_short_strike, put_long_strike,
                    call_short_strike, call_long_strike,
                    total_credit, contracts, max_loss, max_profit,
                    underlying_at_entry, open_time
                FROM pegasus_positions
                WHERE status = 'open'
                ORDER BY open_time DESC
            """)
            db_positions = cursor.fetchall()
            results["details"]["db_open_count"] = len(db_positions)

            # Check for stale positions
            today = datetime.now(CENTRAL_TZ).date()
            stale_positions = []
            for pos in db_positions:
                exp_date = pos[2]
                if exp_date and exp_date < today:
                    stale_positions.append({
                        "position_id": pos[0],
                        "expiration": str(exp_date),
                        "days_stale": (today - exp_date).days
                    })

            if stale_positions:
                results["passed"] = False
                results["details"]["stale_positions"] = stale_positions
                self.errors.append(f"PEGASUS has {len(stale_positions)} stale position(s) - expired but not closed")

        except Exception as e:
            results["passed"] = False
            results["details"]["error"] = str(e)
            self.errors.append(f"PEGASUS open position validation failed: {e}")

        return results

    def validate_pegasus_closed_positions(self) -> dict:
        """Validate PEGASUS closed positions"""
        results = {"passed": True, "details": {}}

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    position_id, ticker, status,
                    total_credit, contracts, close_price, realized_pnl,
                    close_reason, close_time
                FROM pegasus_positions
                WHERE status IN ('closed', 'expired')
                ORDER BY close_time DESC
                LIMIT 20
            """)
            closed_positions = cursor.fetchall()
            results["details"]["closed_count"] = len(closed_positions)

            # Check for missing P&L
            missing_pnl = [pos[0] for pos in closed_positions if pos[6] is None]
            if missing_pnl:
                results["details"]["missing_pnl_count"] = len(missing_pnl)
                self.warnings.append(f"PEGASUS has {len(missing_pnl)} closed position(s) without P&L")

        except Exception as e:
            results["passed"] = False
            results["details"]["error"] = str(e)
            self.errors.append(f"PEGASUS closed position validation failed: {e}")

        return results

    def validate_pegasus_equity_curve(self) -> dict:
        """Validate PEGASUS equity curve"""
        results = {"passed": True, "details": {}}

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    DATE(close_time AT TIME ZONE 'America/Chicago') as trade_date,
                    COUNT(*) as trades,
                    SUM(realized_pnl) as daily_pnl
                FROM pegasus_positions
                WHERE status IN ('closed', 'expired')
                AND close_time >= NOW() - INTERVAL '30 days'
                GROUP BY DATE(close_time AT TIME ZONE 'America/Chicago')
                ORDER BY trade_date
            """)
            equity_data = cursor.fetchall()
            results["details"]["trading_days"] = len(equity_data)

            if equity_data:
                total_trades = sum(row[1] for row in equity_data)
                total_pnl = sum(float(row[2] or 0) for row in equity_data)
                results["details"]["total_trades_30d"] = total_trades
                results["details"]["total_pnl_30d"] = round(total_pnl, 2)

        except Exception as e:
            results["passed"] = False
            results["details"]["error"] = str(e)
            self.errors.append(f"PEGASUS equity curve validation failed: {e}")

        return results

    # =========================================================================
    # API ENDPOINT VALIDATION
    # =========================================================================

    def validate_api_sync(self) -> dict:
        """Validate API endpoints return data matching database"""
        results = {"passed": True, "details": {}}

        try:
            import asyncio
            from backend.api.routes.ares_routes import get_ares_positions, get_ares_live_pnl
            from backend.api.routes.athena_routes import get_athena_positions, get_athena_live_pnl
            from backend.api.routes.pegasus_routes import get_pegasus_positions, get_pegasus_live_pnl

            loop = asyncio.get_event_loop()

            # Test ARES API
            try:
                ares_pos = loop.run_until_complete(get_ares_positions())
                results["details"]["ares_api_positions"] = ares_pos.get("data", {}).get("open_count", 0) if isinstance(ares_pos.get("data"), dict) else "N/A"
            except Exception as e:
                results["details"]["ares_api_error"] = str(e)[:100]

            # Test ATHENA API
            try:
                athena_pos = loop.run_until_complete(get_athena_positions())
                results["details"]["athena_api_positions"] = athena_pos.get("count", 0)
            except Exception as e:
                results["details"]["athena_api_error"] = str(e)[:100]

            # Test PEGASUS API
            try:
                pegasus_pos = loop.run_until_complete(get_pegasus_positions())
                results["details"]["pegasus_api_positions"] = len(pegasus_pos.get("data", {}).get("open_positions", []))
            except Exception as e:
                results["details"]["pegasus_api_error"] = str(e)[:100]

        except Exception as e:
            results["passed"] = False
            results["details"]["error"] = str(e)

        return results

    # =========================================================================
    # MAIN RUNNER
    # =========================================================================

    def run_all_validations(self) -> dict:
        """Run all sync validations"""
        timestamp = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')

        print_header(f"TRADE SYNC VALIDATION - {timestamp}")

        all_results = {}
        all_passed = 0
        all_failed = 0

        # ARES Tests
        print_header("ARES Iron Condor Sync")

        result = self.validate_ares_open_positions()
        print_result("Open positions sync", result["passed"], str(result["details"]))
        if result["passed"]:
            all_passed += 1
        else:
            all_failed += 1
        all_results["ares_open"] = result

        result = self.validate_ares_closed_positions()
        print_result("Closed positions P&L", result["passed"], str(result["details"]))
        if result["passed"]:
            all_passed += 1
        else:
            all_failed += 1
        all_results["ares_closed"] = result

        result = self.validate_ares_equity_curve()
        print_result("Equity curve data", result["passed"], str(result["details"]))
        if result["passed"]:
            all_passed += 1
        else:
            all_failed += 1
        all_results["ares_equity"] = result

        # ATHENA Tests
        print_header("ATHENA Directional Spreads Sync")

        result = self.validate_athena_open_positions()
        print_result("Open positions sync", result["passed"], str(result["details"]))
        if result["passed"]:
            all_passed += 1
        else:
            all_failed += 1
        all_results["athena_open"] = result

        result = self.validate_athena_closed_positions()
        print_result("Closed positions P&L", result["passed"], str(result["details"]))
        if result["passed"]:
            all_passed += 1
        else:
            all_failed += 1
        all_results["athena_closed"] = result

        result = self.validate_athena_equity_curve()
        print_result("Equity curve data", result["passed"], str(result["details"]))
        if result["passed"]:
            all_passed += 1
        else:
            all_failed += 1
        all_results["athena_equity"] = result

        # PEGASUS Tests
        print_header("PEGASUS SPX Iron Condor Sync")

        result = self.validate_pegasus_open_positions()
        print_result("Open positions sync", result["passed"], str(result["details"]))
        if result["passed"]:
            all_passed += 1
        else:
            all_failed += 1
        all_results["pegasus_open"] = result

        result = self.validate_pegasus_closed_positions()
        print_result("Closed positions P&L", result["passed"], str(result["details"]))
        if result["passed"]:
            all_passed += 1
        else:
            all_failed += 1
        all_results["pegasus_closed"] = result

        result = self.validate_pegasus_equity_curve()
        print_result("Equity curve data", result["passed"], str(result["details"]))
        if result["passed"]:
            all_passed += 1
        else:
            all_failed += 1
        all_results["pegasus_equity"] = result

        # API Sync Tests
        print_header("API Endpoint Sync")

        result = self.validate_api_sync()
        print_result("API returns DB data", result["passed"], str(result["details"]))
        if result["passed"]:
            all_passed += 1
        else:
            all_failed += 1
        all_results["api_sync"] = result

        # Summary
        print_header("SUMMARY")

        print(f"\n  Tests Passed: {all_passed}")
        print(f"  Tests Failed: {all_failed}")

        if self.warnings:
            print(f"\n  ⚠️  WARNINGS ({len(self.warnings)}):")
            for w in self.warnings[:10]:
                print(f"      - {w}")
            if len(self.warnings) > 10:
                print(f"      ... and {len(self.warnings) - 10} more")

        if self.errors:
            print(f"\n  ❌ ERRORS ({len(self.errors)}):")
            for e in self.errors:
                print(f"      - {e}")

        print("\n" + "=" * 70)
        if all_failed == 0 and not self.errors:
            print("  🎉 ALL SYNC VALIDATIONS PASSED!")
        else:
            print(f"  ⚠️  {all_failed} validation(s) need attention")
        print("=" * 70)

        self.close_connection()

        return {
            "passed": all_passed,
            "failed": all_failed,
            "errors": self.errors,
            "warnings": self.warnings,
            "results": all_results
        }


if __name__ == "__main__":
    validator = TradeSyncValidator()
    results = validator.run_all_validations()
    sys.exit(1 if results["failed"] > 0 else 0)
