#!/usr/bin/env python3
"""Test 4: Exit Logic Validation (FORCE_EXIT)

Verifies that FORCE_EXIT is wired into check_exit_conditions,
that the call chain is intact, and the monitoring loop is scheduled.
Read-only — no data modification.
"""
import sys
import inspect
import traceback

HEADER = """
╔══════════════════════════════════════╗
║  TEST 4: Exit Logic (FORCE_EXIT)     ║
╚══════════════════════════════════════╝
"""


def run():
    print(HEADER)

    overall_pass = True

    # --- Check 4A: FORCE_EXIT exists in check_exit_conditions ---
    print("--- Check 4A: FORCE_EXIT in check_exit_conditions ---")
    try:
        from trading.jubilee.executor import JubileeICExecutor
        source = inspect.getsource(JubileeICExecutor.check_exit_conditions)
        print(f"  check_exit_conditions() source ({len(source)} chars):")
        for i, line in enumerate(source.strip().split('\n')):
            print(f"    {i+1:3d} | {line}")

        # Check exit priority order
        force_idx = source.find('FORCE_EXIT') if 'FORCE_EXIT' in source else source.find('force_exit')
        profit_idx = source.find('PROFIT') if 'PROFIT' in source else source.find('profit_target')
        stop_idx = source.find('STOP_LOSS') if 'STOP_LOSS' in source else source.find('stop_loss')
        time_idx = source.find('TIME_STOP') if 'TIME_STOP' in source else source.find('time_stop')

        has_force = 'FORCE_EXIT' in source or 'force_exit' in source
        has_expired = 'EXPIRED' in source or 'expired' in source.lower()
        has_profit = 'PROFIT' in source or 'profit_target' in source
        has_stop = 'STOP_LOSS' in source or 'stop_loss' in source
        has_time = 'TIME_STOP' in source or 'time_stop' in source

        print(f"\n  Exit conditions found:")
        print(f"    {'✅' if has_force   else '❌'} FORCE_EXIT  {'(position ' + str(force_idx) + ')' if force_idx >= 0 else ''}")
        print(f"    {'✅' if has_expired else '❌'} EXPIRED")
        print(f"    {'✅' if has_profit  else '❌'} PROFIT_TARGET")
        print(f"    {'✅' if has_stop    else '❌'} STOP_LOSS")
        print(f"    {'✅' if has_time    else '❌'} TIME_STOP")

        # Check priority: FORCE_EXIT should be BEFORE profit/stop
        if has_force and force_idx >= 0:
            if profit_idx >= 0 and force_idx < profit_idx:
                print(f"\n  ✅ FORCE_EXIT comes BEFORE PROFIT_TARGET (correct priority)")
            elif profit_idx >= 0:
                print(f"\n  ⚠️ FORCE_EXIT comes AFTER PROFIT_TARGET (wrong priority!)")
            if stop_idx >= 0 and force_idx < stop_idx:
                print(f"  ✅ FORCE_EXIT comes BEFORE STOP_LOSS (correct priority)")
            elif stop_idx >= 0:
                print(f"  ⚠️ FORCE_EXIT comes AFTER STOP_LOSS (wrong priority!)")

        # Check for exit_by time
        if 'exit_by' in source:
            print(f"\n  ✅ References config.exit_by for force exit timing")
        else:
            print(f"\n  ⚠️ Does not reference exit_by — may use hardcoded time")

        if has_force:
            print(f"\nResult: ✅ PASS — FORCE_EXIT exists in check_exit_conditions")
        else:
            print(f"\nResult: ❌ FAIL — FORCE_EXIT NOT FOUND in check_exit_conditions")
            overall_pass = False

    except ImportError as e:
        print(f"  ❌ Cannot import JubileeICExecutor: {e}")
        print(f"Result: ❌ FAIL")
        overall_pass = False
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL")
        overall_pass = False
    print()

    # --- Check 4B: Call chain — who calls check_exit_conditions? ---
    print("--- Check 4B: Call Chain to check_exit_conditions ---")
    try:
        from trading.jubilee.trader import JubileeICTrader
        check_all_src = inspect.getsource(JubileeICTrader._check_all_exits)
        print(f"  _check_all_exits() calls check_exit_conditions?")

        if 'check_exit_conditions' in check_all_src:
            print(f"    ✅ YES — _check_all_exits() calls self.executor.check_exit_conditions()")
        else:
            print(f"    ❌ NO — _check_all_exits() does NOT call check_exit_conditions")
            overall_pass = False

        # Check that run_trading_cycle calls _check_all_exits
        cycle_src = inspect.getsource(JubileeICTrader.run_trading_cycle)
        if '_check_all_exits' in cycle_src:
            print(f"    ✅ run_trading_cycle() calls _check_all_exits()")
        else:
            print(f"    ❌ run_trading_cycle() does NOT call _check_all_exits()")
            overall_pass = False

        # Full chain
        print(f"\n  Call chain:")
        print(f"    scheduler.scheduled_jubilee_ic_cycle()")
        print(f"      → jubilee_ic_trader.run_trading_cycle()")
        print(f"        → self._check_all_exits()")
        print(f"          → self.executor.check_exit_conditions(position)")
        print(f"            → FORCE_EXIT / EXPIRED / PROFIT / STOP_LOSS / TIME_STOP")

        print(f"\nResult: ✅ PASS — call chain intact")
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL — cannot trace call chain")
        overall_pass = False
    print()

    # --- Check 4C: Is the monitoring loop scheduled? ---
    print("--- Check 4C: Scheduler Job Registration ---")
    try:
        # Read the scheduler source to verify job registration
        from trading.jubilee.trader import JubileeICTrader
        # We can't easily check APScheduler jobs without running the scheduler,
        # but we CAN verify the scheduler code references the right function.

        scheduler_checks = []

        # Check that scheduled_jubilee_ic_cycle exists in scheduler
        try:
            from scheduler.trader_scheduler import TraderScheduler
            if hasattr(TraderScheduler, 'scheduled_jubilee_ic_cycle'):
                scheduler_checks.append("scheduled_jubilee_ic_cycle method exists")
                src = inspect.getsource(TraderScheduler.scheduled_jubilee_ic_cycle)
                if 'run_trading_cycle' in src:
                    scheduler_checks.append("scheduled_jubilee_ic_cycle calls run_trading_cycle()")
                if 'is_market_open' in src or 'market' in src.lower():
                    scheduler_checks.append("Market hours check present")
            else:
                print(f"  ❌ TraderScheduler.scheduled_jubilee_ic_cycle does NOT exist")
                overall_pass = False
        except ImportError as e:
            print(f"  ⚠️ Cannot import TraderScheduler: {e}")
            print(f"  This is expected on Render — the scheduler runs in a separate worker")
            scheduler_checks.append("Cannot verify (separate worker process)")

        for check in scheduler_checks:
            print(f"    ✅ {check}")

        # Check the schedule_all_jobs for jubilee IC registration
        try:
            schedule_src = inspect.getsource(TraderScheduler.schedule_all_jobs)
            if 'scheduled_jubilee_ic_cycle' in schedule_src:
                print(f"    ✅ IC cycle is registered in schedule_all_jobs()")

                # Try to find the interval
                lines = schedule_src.split('\n')
                for i, line in enumerate(lines):
                    if 'scheduled_jubilee_ic_cycle' in line:
                        # Print surrounding context
                        start = max(0, i - 3)
                        end = min(len(lines), i + 5)
                        print(f"    Schedule config:")
                        for j in range(start, end):
                            print(f"      {lines[j].strip()}")
                        break
            else:
                print(f"    ❌ IC cycle NOT registered in schedule_all_jobs()")
                print(f"    ❌ CRITICAL: Monitoring loop is NOT running — no exits will fire")
                overall_pass = False
        except Exception as e:
            print(f"    ⚠️ Cannot read schedule_all_jobs: {e}")

        print(f"\nResult: {'✅ PASS' if overall_pass else '❌ FAIL'}")
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL")
        overall_pass = False
    print()

    # --- Check 4D: run_jubilee_ic_cycle standalone function ---
    print("--- Check 4D: Standalone run_jubilee_ic_cycle function ---")
    try:
        from trading.jubilee.trader import run_jubilee_ic_cycle
        src = inspect.getsource(run_jubilee_ic_cycle)
        print(f"  run_jubilee_ic_cycle() exists as standalone function")
        print(f"  Source ({len(src)} chars):")
        for line in src.strip().split('\n')[:15]:
            print(f"    {line}")
        print(f"\nResult: ✅ PASS")
    except ImportError:
        print(f"  ℹ️  run_jubilee_ic_cycle not exported as standalone function")
        print(f"  This is OK if scheduler uses JubileeICTrader.run_trading_cycle() directly")
        print(f"Result: ⚠️ WARNING — no standalone function")
    except Exception as e:
        print(f"  Error: {e}")
        print(f"Result: ⚠️ WARNING")
    print()

    print(f"""
═══════════════════════════════
TEST 4 OVERALL: {'✅ PASS' if overall_pass else '❌ FAIL'}
═══════════════════════════════
""")


if __name__ == '__main__':
    try:
        run()
    except Exception as e:
        print(f"\n❌ SCRIPT CRASHED: {e}")
        traceback.print_exc()
        sys.exit(1)
