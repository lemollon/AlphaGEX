#!/usr/bin/env python3
"""
End-to-End Data Verification Script

This script verifies that:
1. Tables contain actual data (not just exist)
2. Data collection pipelines are working
3. APIs return real data from the database
4. Full data flow: Source → Storage → API → Response

Run in Render shell: python scripts/tests/e2e_data_verification.py
"""

import os
import sys
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_result(check, passed, details=""):
    status = "✓" if passed else "✗"
    color_status = "PASS" if passed else "FAIL"
    print(f"  {status} [{color_status}] {check}")
    if details:
        print(f"           └─ {details}")


def check_table_data(cursor, conn, table_name, time_column=None, hours_back=24):
    """Check if table has data and recent records."""
    try:
        # Total count
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        total = cursor.fetchone()[0]
        conn.commit()

        # Recent count (if time column exists)
        recent = None
        if time_column:
            try:
                cursor.execute(f"""
                    SELECT COUNT(*) FROM {table_name}
                    WHERE {time_column} > NOW() - INTERVAL '{hours_back} hours'
                """)
                recent = cursor.fetchone()[0]
                conn.commit()
            except Exception:
                conn.rollback()  # Reset transaction on column error
                pass

        return total, recent
    except Exception as e:
        conn.rollback()  # Reset transaction on error
        return None, None


def main():
    print("""
╔═══════════════════════════════════════════════════════════╗
║        END-TO-END DATA VERIFICATION                       ║
╚═══════════════════════════════════════════════════════════╝
""")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = {"pass": 0, "fail": 0, "warn": 0}

    try:
        from database_adapter import get_connection, is_database_available

        if not is_database_available():
            print("\n  ❌ Database not available!")
            return 1

        conn = get_connection()
        cursor = conn.cursor()

        # ============================================================
        # SECTION 1: CORE TRADING TABLES
        # ============================================================
        print_header("1. CORE TRADING DATA")

        core_tables = [
            ("fortress_positions", "open_date", "FORTRESS positions (iron condors)"),
            ("fortress_daily_performance", "trade_date", "FORTRESS daily P&L"),
            ("decision_logs", "created_at", "Trading decisions"),
            ("bot_decision_logs", "created_at", "Bot decisions"),
            ("wheel_cycles", "created_at", "Wheel strategy cycles"),
        ]

        for table, time_col, desc in core_tables:
            total, recent = check_table_data(cursor, conn, table, time_col, 168)  # 7 days
            if total is None:
                print_result(f"{desc}", False, f"Table missing or error")
                results["fail"] += 1
            elif total == 0:
                print_result(f"{desc}", False, f"EMPTY - no data collected")
                results["fail"] += 1
            else:
                recent_str = f", {recent} in last 7 days" if recent is not None else ""
                print_result(f"{desc}", True, f"{total} records{recent_str}")
                results["pass"] += 1

        # ============================================================
        # SECTION 2: MARKET DATA TABLES
        # ============================================================
        print_header("2. MARKET DATA COLLECTION")

        market_tables = [
            ("gex_snapshots", "created_at", "GEX snapshots"),
            ("gex_history", "created_at", "GEX history"),
            ("vix_data", "created_at", "VIX data"),
            ("market_data", "created_at", "Market data"),
            ("options_chain_snapshots", "snapshot_time", "Options chain snapshots"),
        ]

        for table, time_col, desc in market_tables:
            total, recent = check_table_data(cursor, conn, table, time_col, 24)
            if total is None:
                print_result(f"{desc}", False, f"Table missing")
                results["fail"] += 1
            elif total == 0:
                print_result(f"{desc}", False, f"EMPTY - data collector not running?")
                results["fail"] += 1
            else:
                recent_str = f", {recent} in last 24h" if recent is not None else ""
                print_result(f"{desc}", True, f"{total} records{recent_str}")
                results["pass"] += 1

        # ============================================================
        # SECTION 3: AI/ML TABLES
        # ============================================================
        print_header("3. AI/ML PREDICTIONS")

        ai_tables = [
            ("prophet_predictions", "created_at", "Prophet predictions"),
            ("probability_weights", "timestamp", "Probability weights"),
            ("ml_predictions", "created_at", "ML predictions"),
            ("regime_classifications", "created_at", "Regime classifications"),
        ]

        for table, time_col, desc in ai_tables:
            total, recent = check_table_data(cursor, conn, table, time_col, 168)
            if total is None:
                print_result(f"{desc}", False, f"Table missing")
                results["fail"] += 1
            elif total == 0:
                print_result(f"{desc}", False, f"EMPTY - AI not generating predictions")
                results["warn"] += 1
            else:
                recent_str = f", {recent} in last 7 days" if recent is not None else ""
                print_result(f"{desc}", True, f"{total} records{recent_str}")
                results["pass"] += 1

        # ============================================================
        # SECTION 4: FORTRESS SPECIFIC VERIFICATION
        # ============================================================
        print_header("4. FORTRESS PIPELINE VERIFICATION")

        # Check FORTRESS has position data
        try:
            cursor.execute("""
                SELECT COUNT(*),
                       SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_count,
                       SUM(CASE WHEN status IN ('closed', 'expired') THEN 1 ELSE 0 END) as closed_count
                FROM fortress_positions
            """)
            row = cursor.fetchone()
            conn.commit()
            if row and row[0] > 0:
                print_result("FORTRESS positions recorded", True,
                            f"Total: {row[0]}, Open: {row[1] or 0}, Closed: {row[2] or 0}")
                results["pass"] += 1
            else:
                print_result("FORTRESS positions recorded", False, "No positions in database")
                results["fail"] += 1
        except Exception as e:
            conn.rollback()
            print_result("FORTRESS positions recorded", False, f"Query error: {str(e)[:40]}")
            results["fail"] += 1

        # Check if FORTRESS daily performance is being tracked
        try:
            cursor.execute("""
                SELECT COUNT(*), MIN(trade_date), MAX(trade_date)
                FROM fortress_daily_performance
            """)
            row = cursor.fetchone()
            conn.commit()
            if row and row[0] > 0:
                print_result("FORTRESS daily P&L tracked", True,
                            f"{row[0]} days from {row[1]} to {row[2]}")
                results["pass"] += 1
            else:
                print_result("FORTRESS daily P&L tracked", False, "No daily performance records")
                results["warn"] += 1
        except Exception as e:
            conn.rollback()
            print_result("FORTRESS daily P&L tracked", False, f"Table may not exist")
            results["warn"] += 1

        # ============================================================
        # SECTION 5: API ENDPOINT DATA FLOW
        # ============================================================
        print_header("5. API DATA FLOW TEST")

        import requests
        api_base = os.getenv('API_URL', 'https://alphagex-api.onrender.com')

        # Test FORTRESS status returns data from DB
        try:
            resp = requests.get(f"{api_base}/api/fortress/status", timeout=10)
            data = resp.json()
            if data.get('success') and data.get('data'):
                fortress_data = data['data']
                print_result("FORTRESS /status returns data", True,
                           f"Capital: ${fortress_data.get('capital', 0):,.0f}, "
                           f"Trades: {fortress_data.get('trade_count', 0)}")
                results["pass"] += 1
            else:
                print_result("FORTRESS /status returns data", False, "No data in response")
                results["fail"] += 1
        except Exception as e:
            print_result("FORTRESS /status returns data", False, str(e)[:50])
            results["fail"] += 1

        # Test FORTRESS positions returns data from DB
        try:
            resp = requests.get(f"{api_base}/api/fortress/positions", timeout=10)
            data = resp.json()
            if data.get('success') and data.get('data'):
                pos_data = data['data']
                open_count = pos_data.get('open_count', 0)
                closed_count = pos_data.get('closed_count', 0)
                print_result("FORTRESS /positions returns data", True,
                           f"Open: {open_count}, Closed: {closed_count}")
                results["pass"] += 1
            else:
                print_result("FORTRESS /positions returns data", False, "No position data")
                results["fail"] += 1
        except Exception as e:
            print_result("FORTRESS /positions returns data", False, str(e)[:50])
            results["fail"] += 1

        # Test market data endpoint
        try:
            resp = requests.get(f"{api_base}/api/fortress/market-data", timeout=10)
            data = resp.json()
            if data.get('success') and data.get('data'):
                md = data['data']
                spx_price = md.get('spx', {}).get('price') or md.get('underlying_price')
                spy_price = md.get('spy', {}).get('price')
                if spx_price and spy_price:
                    print_result("Market data flowing", True,
                               f"SPX: ${spx_price:,.2f}, SPY: ${spy_price:.2f}")
                    results["pass"] += 1
                else:
                    print_result("Market data flowing", False, "Missing price data")
                    results["fail"] += 1
            else:
                print_result("Market data flowing", False, data.get('message', 'No data'))
                results["fail"] += 1
        except Exception as e:
            print_result("Market data flowing", False, str(e)[:50])
            results["fail"] += 1

        # ============================================================
        # SECTION 6: DATA COLLECTION STATUS
        # ============================================================
        print_header("6. DATA COLLECTION SERVICES")

        # Check data_collection_log for recent activity
        try:
            cursor.execute("""
                SELECT source, MAX(collected_at) as last_collection, COUNT(*)
                FROM data_collection_log
                WHERE collected_at > NOW() - INTERVAL '24 hours'
                GROUP BY source
                ORDER BY last_collection DESC
            """)
            rows = cursor.fetchall()
            conn.commit()
            if rows:
                for source, last_time, count in rows:
                    print_result(f"Collector: {source}", True,
                               f"{count} collections, last: {last_time}")
                    results["pass"] += 1
            else:
                print_result("Data collectors active", False,
                           "No collection logs in 24h - collectors may be stopped")
                results["warn"] += 1
        except Exception as e:
            conn.rollback()
            print_result("Data collection logs", False, f"Table may not exist")
            results["warn"] += 1

        # ============================================================
        # SUMMARY
        # ============================================================
        print_header("SUMMARY")

        total_checks = results["pass"] + results["fail"] + results["warn"]
        print(f"""
   ✓ Passed:   {results['pass']}/{total_checks}
   ✗ Failed:   {results['fail']}/{total_checks}
   ⚠ Warnings: {results['warn']}/{total_checks}
""")

        if results["fail"] == 0:
            print("   ✅ All critical data flows verified!")
        else:
            print("   ❌ Some data flows need attention")
            print("\n   RECOMMENDED ACTIONS:")
            if results["fail"] > 0:
                print("   1. Check if data collector worker is running on Render")
                print("   2. Verify FORTRESS trader is scheduled and executing")
                print("   3. Run: python data/automated_data_collector.py --once")

        conn.close()
        return 0 if results["fail"] == 0 else 1

    except Exception as e:
        print(f"\n  ❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
