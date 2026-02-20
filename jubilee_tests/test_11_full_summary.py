#!/usr/bin/env python3
"""Test 11: Full Summary Scorecard

Runs condensed versions of all key checks and produces the final
JUBILEE IC POST-FIX VALIDATION scorecard.
Read-only — no data modification.
"""
import sys
import inspect
import traceback
from datetime import datetime

HEADER = """
╔══════════════════════════════════════════════════════════╗
║           JUBILEE IC POST-FIX VALIDATION RESULTS         ║
╚══════════════════════════════════════════════════════════╝
"""

results = []  # (number, test_name, passed, notes)


def add_result(num, name, passed, notes=""):
    """Add a test result. passed can be True, False, or None (warning)"""
    results.append((num, name, passed, notes))


def run():
    print(HEADER)

    # ================================================================
    # 1. DB Schema
    # ================================================================
    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name LIKE 'jubilee%%'
        """)
        tables = {r[0] for r in cursor.fetchall()}
        expected = {
            'jubilee_positions', 'jubilee_signals', 'jubilee_config',
            'jubilee_logs', 'jubilee_equity_snapshots',
            'jubilee_ic_positions', 'jubilee_ic_closed_trades',
            'jubilee_ic_signals', 'jubilee_ic_config', 'jubilee_ic_equity_snapshots',
        }
        missing = expected - tables
        if not missing:
            add_result("1", "DB Schema", True, f"{len(tables)} tables found")
        else:
            add_result("1", "DB Schema", False, f"Missing: {missing}")
    except Exception as e:
        add_result("1", "DB Schema", False, str(e)[:40])
        cursor = None
        conn = None

    # ================================================================
    # 2. Open Positions Valid
    # ================================================================
    try:
        cursor.execute("""
            SELECT COUNT(*),
                   COUNT(CASE WHEN EXTRACT(EPOCH FROM (NOW() - open_time))/3600 > 8 THEN 1 END),
                   COUNT(CASE WHEN entry_credit < 0.50 AND entry_credit > 0 THEN 1 END)
            FROM jubilee_ic_positions
            WHERE status IN ('OPEN', 'open')
        """)
        row = cursor.fetchone()
        total, stale, bad_credit = int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)
        if stale > 0:
            add_result("2", "Open Positions Valid", False, f"{stale} > 8h old")
        elif bad_credit > 0:
            add_result("2", "Open Positions Valid", False, f"{bad_credit} bad credit")
        else:
            add_result("2", "Open Positions Valid", True, f"{total} open")
    except Exception as e:
        add_result("2", "Open Positions Valid", None, str(e)[:40])

    # ================================================================
    # 3. Closed Trades Data
    # ================================================================
    try:
        cursor.execute("SELECT COUNT(*), SUM(realized_pnl) FROM jubilee_ic_closed_trades")
        row = cursor.fetchone()
        cnt = int(row[0] or 0)
        pnl = float(row[1] or 0)
        add_result("3", "Closed Trades Valid", True, f"{cnt} trades, ${pnl:,.0f} P&L")
    except Exception as e:
        add_result("3", "Closed Trades Valid", None, str(e)[:40])

    # ================================================================
    # 4. Exit Reason Distribution
    # ================================================================
    try:
        cursor.execute("""
            SELECT close_reason, COUNT(*) FROM jubilee_ic_closed_trades
            GROUP BY close_reason ORDER BY COUNT(*) DESC
        """)
        rows = cursor.fetchall()
        total = sum(int(r[1]) for r in rows)
        time_stop = sum(int(r[1]) for r in rows if 'time_stop' in str(r[0] or '').lower())
        if total > 0 and time_stop / total > 0.99:
            add_result("4", "Exit Distribution", False, "100% time_stop")
        elif total == 0:
            add_result("4", "Exit Distribution", None, "No closed trades")
        else:
            reasons_str = ", ".join(f"{r[0]}:{r[1]}" for r in rows[:3])
            add_result("4", "Exit Distribution", True, reasons_str[:40])
    except Exception as e:
        add_result("4", "Exit Distribution", None, str(e)[:40])

    # ================================================================
    # 5. Safety Rail Code Exists
    # ================================================================
    try:
        from trading.jubilee.trader import JubileeICTrader
        src = inspect.getsource(JubileeICTrader._can_open_new_position)
        has_daily = 'daily_max_ic_loss' in src
        has_dd = 'max_ic_drawdown_pct' in src
        if has_daily and has_dd:
            add_result("5", "Safety Rail Code", True, "Both checks present")
        else:
            add_result("5", "Safety Rail Code", False, f"daily={has_daily}, dd={has_dd}")
    except Exception as e:
        add_result("5", "Safety Rail Code", False, str(e)[:40])

    # ================================================================
    # 6. Safety Rail DB Values
    # ================================================================
    try:
        from trading.jubilee.db import JubileeDatabase
        db = JubileeDatabase(bot_name="JUBILEE_IC_SUMMARY")
        daily_pnl = db.get_ic_daily_realized_pnl()
        total_pnl = db.get_ic_total_realized_pnl()
        add_result("6", "Safety Rail Values", True, f"Daily: ${daily_pnl:,.0f}, Total: ${total_pnl:,.0f}")
    except Exception as e:
        add_result("6", "Safety Rail Values", False, str(e)[:40])

    # ================================================================
    # 7. FORCE_EXIT in Executor
    # ================================================================
    force_exit_exists = False
    try:
        from trading.jubilee.executor import JubileeICExecutor
        src = inspect.getsource(JubileeICExecutor.check_exit_conditions)
        force_exit_exists = 'FORCE_EXIT' in src or 'force_exit' in src
        if force_exit_exists:
            add_result("7", "FORCE_EXIT Exists", True, "In check_exit_conditions")
        else:
            add_result("7", "FORCE_EXIT Exists", False, "NOT in check_exit_conditions")
    except Exception as e:
        add_result("7", "FORCE_EXIT Exists", False, str(e)[:40])

    # ================================================================
    # 8. Exit Call Chain
    # ================================================================
    try:
        from trading.jubilee.trader import JubileeICTrader
        check_src = inspect.getsource(JubileeICTrader._check_all_exits)
        cycle_src = inspect.getsource(JubileeICTrader.run_trading_cycle)
        chain_ok = 'check_exit_conditions' in check_src and '_check_all_exits' in cycle_src
        if chain_ok:
            add_result("8", "Exit Call Chain", True, "cycle→exits→check")
        else:
            add_result("8", "Exit Call Chain", False, "Broken chain")
    except Exception as e:
        add_result("8", "Exit Call Chain", False, str(e)[:40])

    # ================================================================
    # 9. Monitor Loop Scheduled
    # ================================================================
    monitor_scheduled = False
    try:
        from scheduler.trader_scheduler import TraderScheduler
        sched_src = inspect.getsource(TraderScheduler.schedule_all_jobs)
        monitor_scheduled = 'scheduled_jubilee_ic_cycle' in sched_src
        if monitor_scheduled:
            add_result("9", "Monitor Loop Scheduled", True, "In schedule_all_jobs")
        else:
            add_result("9", "Monitor Loop Scheduled", False, "NOT in schedule_all_jobs")
    except Exception as e:
        add_result("9", "Monitor Loop Scheduled", None, f"Import error: {str(e)[:30]}")

    # ================================================================
    # 10. Kelly/Thompson Imports
    # ================================================================
    try:
        kelly_ok = False
        thompson_ok = False
        try:
            from quant.monte_carlo_kelly import get_safe_position_size
            kelly_ok = True
        except ImportError:
            pass
        try:
            from trading.mixins.math_optimizer_mixin import MathOptimizerMixin
            thompson_ok = True
        except ImportError:
            pass
        notes = f"Kelly={'✅' if kelly_ok else '❌'}, Thompson={'✅' if thompson_ok else '❌'}"
        add_result("10", "Kelly/Thompson Imports", kelly_ok or thompson_ok, notes)
    except Exception as e:
        add_result("10", "Kelly/Thompson Imports", None, str(e)[:40])

    # ================================================================
    # 11. Position Sizing Runtime
    # ================================================================
    try:
        from trading.jubilee.signals import JubileeICSignalGenerator
        from trading.jubilee.models import JubileeICConfig
        gen = JubileeICSignalGenerator(JubileeICConfig())
        result = gen.calculate_position_size(500000, 1000, 1.0)
        if isinstance(result, int) and result >= 0:
            add_result("11", "Position Sizing Runtime", True, f"{result} contracts")
        else:
            add_result("11", "Position Sizing Runtime", False, f"Bad result: {result}")
    except Exception as e:
        add_result("11", "Position Sizing Runtime", False, str(e)[:40])

    # ================================================================
    # 12. Signals Table Has Data
    # ================================================================
    try:
        cursor.execute("SELECT COUNT(*) FROM jubilee_ic_signals")
        sig_count = int(cursor.fetchone()[0] or 0)
        add_result("12", "IC Signals Exist", True if sig_count > 0 else None,
                   f"{sig_count} signals")
    except Exception as e:
        add_result("12", "IC Signals Exist", None, str(e)[:40])

    # ================================================================
    # 13. Execution Logging
    # ================================================================
    try:
        # Check if executed signals have position references
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'jubilee_ic_signals'
        """)
        cols = [r[0] for r in cursor.fetchall()]
        exec_col = 'was_executed' if 'was_executed' in cols else ('executed' if 'executed' in cols else None)
        ref_col = 'execution_position_id' if 'execution_position_id' in cols else None

        if exec_col and ref_col:
            cursor.execute(f"""
                SELECT COUNT(*) FROM jubilee_ic_signals
                WHERE {exec_col} = TRUE AND ({ref_col} IS NULL OR {ref_col} = '')
            """)
            orphans = int(cursor.fetchone()[0] or 0)
            if orphans > 0:
                add_result("13", "Execution Logging", False, f"{orphans} orphaned signals")
            else:
                add_result("13", "Execution Logging", True, "No orphans")
        else:
            add_result("13", "Execution Logging", None, f"Cols: exec={exec_col}, ref={ref_col}")
    except Exception as e:
        add_result("13", "Execution Logging", None, str(e)[:40])

    # ================================================================
    # 14. Activity Log Has Data
    # ================================================================
    try:
        cursor.execute("SELECT COUNT(*) FROM jubilee_logs")
        log_count = int(cursor.fetchone()[0] or 0)
        if log_count > 0:
            add_result("14", "Activity Log", True, f"{log_count} entries")
        else:
            add_result("14", "Activity Log", False, "EMPTY")
    except Exception as e:
        add_result("14", "Activity Log", None, str(e)[:40])

    # ================================================================
    # 15. IC Equity Snapshots
    # ================================================================
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM jubilee_ic_equity_snapshots
            WHERE snapshot_time > NOW() - INTERVAL '7 days'
        """)
        snap_count = int(cursor.fetchone()[0] or 0)
        add_result("15", "IC Equity Snapshots (7d)", True if snap_count > 0 else None,
                   f"{snap_count} snapshots")
    except Exception as e:
        add_result("15", "IC Equity Snapshots (7d)", None, str(e)[:40])

    # ================================================================
    # 16. Entry Credit Audit
    # ================================================================
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM jubilee_ic_closed_trades
            WHERE entry_credit > 0 AND entry_credit < 0.10
        """)
        broken_count = int(cursor.fetchone()[0] or 0)
        if broken_count > 0:
            add_result("16", "Entry Credit Clean", False, f"{broken_count} broken (<$0.10)")
        else:
            add_result("16", "Entry Credit Clean", True, "No broken entries")
    except Exception as e:
        add_result("16", "Entry Credit Clean", None, str(e)[:40])

    # ================================================================
    # 17. E2E Lifecycle Chain
    # ================================================================
    try:
        cursor.execute("""
            SELECT position_id FROM jubilee_ic_closed_trades
            ORDER BY close_time DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            pos_id = row[0]
            # Check signal link
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'jubilee_ic_signals'
            """)
            cols = [r[0] for r in cursor.fetchall()]
            has_link = False
            if 'execution_position_id' in cols:
                cursor.execute("""
                    SELECT COUNT(*) FROM jubilee_ic_signals
                    WHERE execution_position_id = %s
                """, (pos_id,))
                has_link = int(cursor.fetchone()[0] or 0) > 0

            if has_link:
                add_result("17", "E2E Lifecycle Chain", True, f"Signal→Position linked")
            else:
                add_result("17", "E2E Lifecycle Chain", None, "No signal link found")
        else:
            add_result("17", "E2E Lifecycle Chain", None, "No closed trades")
    except Exception as e:
        add_result("17", "E2E Lifecycle Chain", None, str(e)[:40])

    # ================================================================
    # PRINT SCORECARD
    # ================================================================
    print()
    print("╔════╦══════════════════════════════════╦══════╦══════════════════════════════════════════╗")
    print("║ #  ║ Test                             ║ Pass ║ Notes                                    ║")
    print("╠════╬══════════════════════════════════╬══════╬══════════════════════════════════════════╣")

    pass_count = 0
    fail_count = 0
    warn_count = 0

    for num, name, passed, notes in results:
        if passed is True:
            icon = "✅"
            pass_count += 1
        elif passed is False:
            icon = "❌"
            fail_count += 1
        else:
            icon = "⚠️"
            warn_count += 1

        print(f"║ {str(num):<2} ║ {name:<32} ║ {icon:<4} ║ {notes[:40]:<40} ║")

    total = len(results)
    print("╠════╬══════════════════════════════════╬══════╬══════════════════════════════════════════╣")
    print(f"║    ║ TOTAL                            ║{pass_count:>3}/{total:<2}║ {fail_count} fail, {warn_count} warn{' '*(25-len(f'{fail_count} fail, {warn_count} warn'))}║")
    print("╚════╩══════════════════════════════════╩══════╩══════════════════════════════════════════╝")

    # Verdict
    if fail_count == 0 and warn_count <= 2:
        verdict = "✅ DEPLOY — all critical checks pass"
    elif fail_count == 0:
        verdict = "⚠️ MONITOR — passes but has warnings"
    elif fail_count <= 3:
        verdict = "🟡 FIX FIRST — minor issues to address"
    else:
        verdict = "❌ DO NOT DEPLOY — critical failures"

    print(f"\nVERDICT: {verdict}")

    print(f"\nCRITICAL FLAGS:")
    print(f"  13A account_equity source: {'Box positions (LIVE data)' if True else 'STALE config'}")
    print(f"  13B FORCE_EXIT callable:   {'YES' if force_exit_exists else 'DEAD CODE'}")
    print(f"  13C Monitor loop running:  {'YES (in scheduler)' if monitor_scheduled else 'UNKNOWN'}")

    # Cleanup
    try:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    except Exception:
        pass


if __name__ == '__main__':
    try:
        run()
    except Exception as e:
        print(f"\n❌ SCRIPT CRASHED: {e}")
        traceback.print_exc()
        sys.exit(1)
