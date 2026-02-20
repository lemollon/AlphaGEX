#!/usr/bin/env python3
"""Test 1: Database Schema Validation

Verifies all required JUBILEE tables exist and have the expected columns.
Read-only — no data modification.
"""
import sys
import traceback

HEADER = """
╔══════════════════════════════════════╗
║  TEST 1: Database Schema Validation  ║
╚══════════════════════════════════════╝
"""

# Expected tables and their critical columns
EXPECTED_TABLES = {
    # Box Spread tables
    'jubilee_positions': [
        'position_id', 'ticker', 'status', 'entry_credit',
        'open_time', 'close_time', 'contracts',
    ],
    'jubilee_signals': [
        'signal_id', 'signal_time', 'executed',
    ],
    'jubilee_capital_deployments': [
        'deployment_id', 'deployment_time',
    ],
    'jubilee_rate_analysis': [
        'analysis_time', 'box_rate', 'is_favorable',
    ],
    'jubilee_daily_briefings': [
        'briefing_date',
    ],
    'jubilee_roll_decisions': [
        'decision_id', 'position_id', 'should_roll',
    ],
    'jubilee_config': [
        'config_key', 'config_data',
    ],
    'jubilee_logs': [
        'log_id', 'timestamp', 'action', 'message',
    ],
    'jubilee_equity_snapshots': [
        'snapshot_time', 'total_equity',
    ],
    # IC Trading tables
    'jubilee_ic_positions': [
        'position_id', 'ticker', 'status', 'entry_credit',
        'contracts', 'open_time', 'close_time', 'close_reason',
        'unrealized_pnl',
    ],
    'jubilee_ic_closed_trades': [
        'position_id', 'realized_pnl', 'close_reason', 'close_time',
    ],
    'jubilee_ic_signals': [
        'signal_id', 'signal_time', 'oracle_approved',
    ],
    'jubilee_ic_config': [
        'config_key', 'config_data',
    ],
    'jubilee_ic_equity_snapshots': [
        'snapshot_time', 'total_equity',
    ],
}


def run():
    print(HEADER)

    # --- Connect to DB ---
    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        print("--- Check 1A: Database Connection ---")
        print("Result: ✅ PASS")
        print("Reason: Connected to production database via database_adapter\n")
    except Exception as e:
        print("--- Check 1A: Database Connection ---")
        print(f"Result: ❌ FAIL")
        print(f"Reason: Cannot connect to database: {e}")
        traceback.print_exc()
        return

    # --- Check 1B: Table Existence ---
    print("--- Check 1B: Table Existence ---")
    tables_pass = True
    missing_tables = []
    found_tables = []

    try:
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name LIKE 'jubilee%%'
            ORDER BY table_name
        """)
        existing = {row[0] for row in cursor.fetchall()}

        for table_name in sorted(EXPECTED_TABLES.keys()):
            if table_name in existing:
                found_tables.append(table_name)
                print(f"  ✅ {table_name}")
            else:
                missing_tables.append(table_name)
                tables_pass = False
                print(f"  ❌ {table_name}  — MISSING")

        # Show any extra jubilee tables we didn't expect
        extra = existing - set(EXPECTED_TABLES.keys())
        if extra:
            print(f"\n  Extra tables found (not in expected list):")
            for t in sorted(extra):
                print(f"    ℹ️  {t}")

    except Exception as e:
        print(f"  ❌ Error querying information_schema: {e}")
        traceback.print_exc()
        tables_pass = False

    if tables_pass:
        print(f"\nResult: ✅ PASS — all {len(EXPECTED_TABLES)} expected tables exist")
    else:
        print(f"\nResult: ❌ FAIL — missing tables: {missing_tables}")
    print()

    # --- Check 1C: Column Validation ---
    print("--- Check 1C: Column Validation ---")
    columns_pass = True
    column_issues = []

    for table_name in sorted(EXPECTED_TABLES.keys()):
        if table_name in missing_tables:
            continue

        expected_cols = EXPECTED_TABLES[table_name]
        try:
            cursor.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                ORDER BY ordinal_position
            """, (table_name,))
            rows = cursor.fetchall()
            actual_cols = {row[0]: row[1] for row in rows}

            missing_cols = [c for c in expected_cols if c not in actual_cols]
            if missing_cols:
                columns_pass = False
                column_issues.append((table_name, missing_cols))
                print(f"  ❌ {table_name} — missing columns: {missing_cols}")
            else:
                print(f"  ✅ {table_name} — all {len(expected_cols)} critical columns present")

            # Print full column list for reference
            print(f"     All columns ({len(actual_cols)}): {', '.join(sorted(actual_cols.keys()))}")

        except Exception as e:
            columns_pass = False
            print(f"  ❌ {table_name} — query error: {e}")

    print()
    if columns_pass:
        print(f"Result: ✅ PASS — all critical columns present in all tables")
    else:
        print(f"Result: ❌ FAIL — column issues: {column_issues}")

    # --- Check 1D: IC Config fields (daily_max_ic_loss, max_ic_drawdown_pct) ---
    print("\n--- Check 1D: IC Config Key Fields ---")
    try:
        cursor.execute("""
            SELECT config_key, config_data
            FROM jubilee_ic_config
            ORDER BY config_key
            LIMIT 10
        """)
        rows = cursor.fetchall()
        if rows:
            import json
            for row in rows:
                key = row[0]
                try:
                    data = json.loads(row[1]) if isinstance(row[1], str) else row[1]
                except (json.JSONDecodeError, TypeError):
                    data = row[1]
                print(f"  Config key: {key}")
                if isinstance(data, dict):
                    for field in ['daily_max_ic_loss', 'max_ic_drawdown_pct',
                                  'max_contracts', 'profit_target_pct', 'stop_loss_pct',
                                  'exit_by', 'use_thompson_sampling', 'starting_capital']:
                        val = data.get(field, '⚠️ NOT SET')
                        print(f"    {field}: {val}")
                else:
                    print(f"    Raw value: {str(data)[:200]}")
            print(f"\nResult: ✅ PASS — IC config found")
        else:
            # Check autonomous_config fallback
            cursor.execute("""
                SELECT key, config_data
                FROM autonomous_config
                WHERE key LIKE 'jubilee_ic%%'
                ORDER BY key
                LIMIT 10
            """)
            rows2 = cursor.fetchall()
            if rows2:
                import json
                for row in rows2:
                    key = row[0]
                    try:
                        data = json.loads(row[1]) if isinstance(row[1], str) else row[1]
                    except (json.JSONDecodeError, TypeError):
                        data = row[1]
                    print(f"  Config key (autonomous_config): {key}")
                    if isinstance(data, dict):
                        for field in ['daily_max_ic_loss', 'max_ic_drawdown_pct',
                                      'max_contracts', 'profit_target_pct', 'stop_loss_pct',
                                      'exit_by', 'use_thompson_sampling', 'starting_capital']:
                            val = data.get(field, '⚠️ NOT SET')
                            print(f"    {field}: {val}")
                print(f"\nResult: ✅ PASS — IC config found in autonomous_config")
            else:
                print(f"  No IC config found in jubilee_ic_config or autonomous_config")
                print(f"Result: ⚠️ WARNING — will use defaults from JubileeICConfig dataclass")
    except Exception as e:
        print(f"  Error reading config: {e}")
        print(f"Result: ⚠️ WARNING — config query failed (table may not exist yet)")

    # --- Cleanup ---
    try:
        cursor.close()
        conn.close()
    except Exception:
        pass

    print(f"""
═══════════════════════════════
TEST 1 OVERALL: {'✅ PASS' if (tables_pass and columns_pass) else '❌ FAIL'}
═══════════════════════════════
""")


if __name__ == '__main__':
    try:
        run()
    except Exception as e:
        print(f"\n❌ SCRIPT CRASHED: {e}")
        traceback.print_exc()
        sys.exit(1)
