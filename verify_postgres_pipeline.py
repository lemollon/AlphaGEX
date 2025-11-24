#!/usr/bin/env python3
"""
PostgreSQL Pipeline Health Check
Verifies all data flows, automation, and data quality
"""

from database_adapter import get_connection
from datetime import datetime, timedelta
import sys

def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")

def check_table_status():
    """Check all critical tables for data freshness and append vs replace"""
    print_section("📊 TABLE STATUS & DATA FRESHNESS")

    conn = get_connection()
    c = conn.cursor()

    # Critical tables to check
    checks = {
        'historical_open_interest': {
            'date_column': 'date',
            'expected_behavior': 'APPEND daily (no duplicates)',
            'max_age_hours': 24,
            'min_rows': 20000
        },
        'autonomous_positions': {
            'date_column': 'entry_date',
            'expected_behavior': 'APPEND on new trades',
            'max_age_hours': 168,  # 7 days
            'min_rows': 0
        },
        'autonomous_trader_logs': {
            'date_column': 'timestamp',
            'expected_behavior': 'APPEND every 5 minutes',
            'max_age_hours': 1,
            'min_rows': 0
        },
        'autonomous_live_status': {
            'date_column': 'last_update',
            'expected_behavior': 'UPDATE (single row)',
            'max_age_hours': 1,
            'min_rows': 0
        },
        'gex_history': {
            'date_column': 'timestamp',
            'expected_behavior': 'APPEND on GEX updates',
            'max_age_hours': 24,
            'min_rows': 0
        }
    }

    results = []

    for table, config in checks.items():
        try:
            # Check if table exists
            c.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = '{table}'
                )
            """)
            exists = c.fetchone()[0]

            if not exists:
                results.append({
                    'table': table,
                    'status': '❌',
                    'issue': 'Table does not exist',
                    'rows': 0,
                    'latest': None
                })
                continue

            # Get row count
            c.execute(f"SELECT COUNT(*) FROM {table}")
            row_count = c.fetchone()[0]

            # Try to get latest date
            latest_date = None
            date_col = config['date_column']
            try:
                c.execute(f"SELECT MAX({date_col}) FROM {table}")
                latest_date = c.fetchone()[0]
            except:
                pass

            # Check for duplicates (for append tables)
            duplicates = 0
            if config['expected_behavior'].startswith('APPEND') and date_col == 'date':
                try:
                    c.execute(f"""
                        SELECT COUNT(*) FROM (
                            SELECT {date_col}, symbol, strike, expiration_date, COUNT(*) as cnt
                            FROM {table}
                            GROUP BY {date_col}, symbol, strike, expiration_date
                            HAVING COUNT(*) > 1
                        ) dupes
                    """)
                    duplicates = c.fetchone()[0]
                except:
                    pass

            # Determine status
            status = '✅'
            issues = []

            if row_count < config['min_rows']:
                status = '⚠️'
                issues.append(f"Low rows ({row_count} < {config['min_rows']})")

            if latest_date:
                if isinstance(latest_date, str):
                    try:
                        latest_dt = datetime.fromisoformat(latest_date.replace('Z', '+00:00'))
                    except:
                        latest_dt = datetime.strptime(latest_date.split()[0], '%Y-%m-%d')
                else:
                    latest_dt = latest_date

                age_hours = (datetime.now() - latest_dt.replace(tzinfo=None)).total_seconds() / 3600

                if age_hours > config['max_age_hours']:
                    status = '❌'
                    issues.append(f"Stale data ({age_hours:.1f}h old > {config['max_age_hours']}h)")

            if duplicates > 0:
                status = '⚠️'
                issues.append(f"{duplicates} duplicate rows (should APPEND not REPLACE)")

            results.append({
                'table': table,
                'status': status,
                'rows': row_count,
                'latest': latest_date,
                'duplicates': duplicates,
                'behavior': config['expected_behavior'],
                'issues': issues
            })

        except Exception as e:
            results.append({
                'table': table,
                'status': '❌',
                'issue': str(e),
                'rows': 0,
                'latest': None
            })

    # Print results
    for r in results:
        print(f"{r['status']} {r['table']:<35} {r['rows']:>8} rows")
        if r.get('latest'):
            print(f"   └─ Latest: {r['latest']}")
        if r.get('behavior'):
            print(f"   └─ Expected: {r['behavior']}")
        if r.get('duplicates', 0) > 0:
            print(f"   └─ ⚠️  {r['duplicates']} duplicate rows detected!")
        if r.get('issues'):
            for issue in r['issues']:
                print(f"   └─ ⚠️  {issue}")
        if r.get('issue'):
            print(f"   └─ ❌ {r['issue']}")
        print()

    conn.close()
    return results

def check_automation():
    """Check what's automated and running"""
    print_section("🤖 AUTOMATION & SCHEDULED JOBS")

    conn = get_connection()
    c = conn.cursor()

    # Check autonomous trader status
    try:
        c.execute("SELECT * FROM autonomous_live_status ORDER BY last_update DESC LIMIT 1")
        status = c.fetchone()
        if status:
            print("✅ Autonomous Trader")
            print(f"   └─ Status: {status[1]}")
            print(f"   └─ Action: {status[2]}")
            print(f"   └─ Last Update: {status[4]}")
            print(f"   └─ Next Check: {status[5]}")
        else:
            print("❌ Autonomous Trader - No status found")
    except:
        print("❌ Autonomous Trader - Status table doesn't exist")

    print()

    # Check scheduler state
    try:
        c.execute("SELECT * FROM scheduler_state LIMIT 1")
        state = c.fetchone()
        if state:
            print("✅ Scheduler")
            print(f"   └─ State: {state}")
        else:
            print("⚠️  Scheduler - No state found (may not be scheduled)")
    except:
        print("⚠️  Scheduler - State table doesn't exist")

    print()

    # Check recent logs
    try:
        c.execute("""
            SELECT COUNT(*)
            FROM autonomous_trader_logs
            WHERE timestamp > NOW() - INTERVAL '1 hour'
        """)
        recent_logs = c.fetchone()[0]

        if recent_logs > 0:
            print(f"✅ Recent Activity: {recent_logs} log entries in last hour")
        else:
            print("⚠️  No recent activity in last hour")
    except:
        print("❌ Cannot check recent activity")

    conn.close()

def check_data_pipeline():
    """Check data flow and updates"""
    print_section("🔄 DATA PIPELINE HEALTH")

    conn = get_connection()
    c = conn.cursor()

    checks = []

    # Check 1: Historical OI - Should append daily
    try:
        c.execute("""
            SELECT
                DATE(date) as day,
                COUNT(*) as rows
            FROM historical_open_interest
            WHERE date >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY DATE(date)
            ORDER BY day DESC
        """)
        recent_days = c.fetchall()

        if len(recent_days) >= 5:
            checks.append({
                'name': 'Historical OI Daily Append',
                'status': '✅',
                'detail': f'Last {len(recent_days)} days have data'
            })
        else:
            checks.append({
                'name': 'Historical OI Daily Append',
                'status': '⚠️',
                'detail': f'Only {len(recent_days)} days in last week'
            })
    except Exception as e:
        checks.append({
            'name': 'Historical OI Daily Append',
            'status': '❌',
            'detail': str(e)
        })

    # Check 2: No full refreshes (check for date gaps)
    try:
        c.execute("""
            WITH date_series AS (
                SELECT generate_series(
                    CURRENT_DATE - INTERVAL '30 days',
                    CURRENT_DATE,
                    '1 day'::interval
                )::date as day
            ),
            data_dates AS (
                SELECT DISTINCT DATE(date) as day
                FROM historical_open_interest
                WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            )
            SELECT COUNT(*)
            FROM date_series ds
            LEFT JOIN data_dates dd ON ds.day = dd.day
            WHERE dd.day IS NULL
            AND EXTRACT(DOW FROM ds.day) NOT IN (0, 6)  -- Exclude weekends
        """)
        missing_days = c.fetchone()[0]

        if missing_days == 0:
            checks.append({
                'name': 'No Data Gaps (Last 30 Days)',
                'status': '✅',
                'detail': 'All trading days have data'
            })
        else:
            checks.append({
                'name': 'No Data Gaps (Last 30 Days)',
                'status': '⚠️',
                'detail': f'{missing_days} trading days missing data'
            })
    except Exception as e:
        checks.append({
            'name': 'No Data Gaps',
            'status': '⚠️',
            'detail': 'Could not check (may be normal for new setup)'
        })

    # Check 3: Duplicate prevention
    try:
        c.execute("""
            SELECT COUNT(*) FROM (
                SELECT date, symbol, strike, expiration_date, COUNT(*) as cnt
                FROM historical_open_interest
                GROUP BY date, symbol, strike, expiration_date
                HAVING COUNT(*) > 1
            ) dupes
        """)
        dupes = c.fetchone()[0]

        if dupes == 0:
            checks.append({
                'name': 'Duplicate Prevention',
                'status': '✅',
                'detail': 'No duplicates found (proper APPEND)'
            })
        else:
            checks.append({
                'name': 'Duplicate Prevention',
                'status': '❌',
                'detail': f'{dupes} duplicate entries (may indicate full refresh instead of append)'
            })
    except Exception as e:
        checks.append({
            'name': 'Duplicate Prevention',
            'status': '❌',
            'detail': str(e)
        })

    # Print results
    for check in checks:
        print(f"{check['status']} {check['name']}")
        print(f"   └─ {check['detail']}")
        print()

    conn.close()

def check_indexes():
    """Check database indexes for performance"""
    print_section("⚡ DATABASE INDEXES")

    conn = get_connection()
    c = conn.cursor()

    # Check critical indexes
    critical_indexes = {
        'historical_open_interest': ['date', 'symbol', 'expiration_date'],
        'autonomous_positions': ['entry_date', 'status'],
        'autonomous_trader_logs': ['timestamp', 'session_id']
    }

    for table, columns in critical_indexes.items():
        try:
            # Check if table exists
            c.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = '{table}'
                )
            """)
            if not c.fetchone()[0]:
                print(f"⚠️  {table} - Table doesn't exist yet")
                continue

            # Check indexes on this table
            c.execute(f"""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = '{table}'
            """)
            indexes = c.fetchall()

            print(f"📋 {table}")
            if indexes:
                for idx_name, idx_def in indexes:
                    print(f"   └─ ✅ {idx_name}")
            else:
                print(f"   └─ ⚠️  No indexes (may impact performance)")
            print()

        except Exception as e:
            print(f"❌ {table} - Error: {e}\n")

    conn.close()

def check_connection_health():
    """Check PostgreSQL connection health"""
    print_section("🔗 CONNECTION HEALTH")

    try:
        conn = get_connection()
        c = conn.cursor()

        # Check connection
        c.execute("SELECT version()")
        version = c.fetchone()[0]
        print(f"✅ PostgreSQL Connection")
        print(f"   └─ Version: {version.split(',')[0]}")
        print()

        # Check database size
        c.execute("""
            SELECT pg_size_pretty(pg_database_size(current_database()))
        """)
        size = c.fetchone()[0]
        print(f"💾 Database Size: {size}")
        print()

        # Check active connections
        c.execute("""
            SELECT count(*)
            FROM pg_stat_activity
            WHERE datname = current_database()
        """)
        connections = c.fetchone()[0]
        print(f"🔌 Active Connections: {connections}")
        print()

        conn.close()

    except Exception as e:
        print(f"❌ Connection Error: {e}")

def main():
    """Run all checks"""
    print("=" * 80)
    print("  🏥 ALPHAGEX POSTGRESQL PIPELINE HEALTH CHECK")
    print("=" * 80)
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Run all checks
    check_connection_health()
    check_table_status()
    check_automation()
    check_data_pipeline()
    check_indexes()

    print("\n" + "=" * 80)
    print("  ✅ HEALTH CHECK COMPLETE")
    print("=" * 80)
    print("\nRecommendations:")
    print("  1. Schedule daily snapshot: historical_oi_snapshot_job.py")
    print("  2. Monitor autonomous trader logs for activity")
    print("  3. Check this report weekly for data pipeline health")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
