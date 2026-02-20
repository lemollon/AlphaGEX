#!/usr/bin/env python3
"""Test 3: Box Spread Safety Rail Validation

Verifies the safety rail logic with REAL production values.
Traces where account_equity comes from and tests the daily loss limit.
Read-only — no data modification.
"""
import sys
import inspect
import traceback

HEADER = """
╔══════════════════════════════════════╗
║  TEST 3: Safety Rail Validation      ║
╚══════════════════════════════════════╝
"""


def run():
    print(HEADER)

    overall_pass = True

    # --- Check 3A: Trace account_equity source ---
    print("--- Check 3A: Trace account_equity / borrowed_capital Source ---")
    try:
        from trading.jubilee.trader import JubileeICTrader
        source_code = inspect.getsource(JubileeICTrader._get_borrowed_capital)
        print(f"  _get_borrowed_capital() source:")
        for line in source_code.strip().split('\n'):
            print(f"    {line}")

        # Check what it does
        if 'get_open_positions' in source_code:
            print(f"\n  ✅ Reads from LIVE box spread positions (db.get_open_positions())")
            print(f"  This means borrowed_capital = sum of total_cash_deployed from open boxes")
        if 'starting_capital' in source_code:
            print(f"  ⚠️  Falls back to config.starting_capital for PAPER mode (when no box positions)")
        if 'tradier' in source_code.lower() or 'get_balance' in source_code.lower():
            print(f"  ✅ Uses Tradier API for live balance")
        else:
            print(f"\n  ℹ️  Does NOT use Tradier API — equity comes from box position data + config fallback")
            print(f"  This is EXPECTED for JUBILEE: borrowed capital = box spreads, not account balance")

        print(f"\nResult: ✅ PASS — source traced successfully")
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL — cannot inspect source")
        overall_pass = False
    print()

    # --- Check 3B: _can_open_new_position safety rail source ---
    print("--- Check 3B: Safety Rail Logic in _can_open_new_position ---")
    try:
        from trading.jubilee.trader import JubileeICTrader
        source_code = inspect.getsource(JubileeICTrader._can_open_new_position)
        print(f"  _can_open_new_position() source:")
        for line in source_code.strip().split('\n'):
            print(f"    {line}")

        checks = []
        if 'daily_max_ic_loss' in source_code:
            checks.append("Daily IC loss limit")
        if 'get_ic_daily_realized_pnl' in source_code:
            checks.append("Calls get_ic_daily_realized_pnl()")
        if 'max_ic_drawdown_pct' in source_code:
            checks.append("Max drawdown percentage")
        if 'get_ic_total_realized_pnl' in source_code:
            checks.append("Calls get_ic_total_realized_pnl()")
        if '_get_borrowed_capital' in source_code:
            checks.append("References borrowed capital")

        print(f"\n  Safety checks found: {len(checks)}")
        for c in checks:
            print(f"    ✅ {c}")

        if len(checks) >= 3:
            print(f"\nResult: ✅ PASS — safety rail has {len(checks)} checks")
        else:
            print(f"\nResult: ❌ FAIL — expected ≥3 safety checks, found {len(checks)}")
            overall_pass = False
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL — cannot inspect safety rail")
        overall_pass = False
    print()

    # --- Check 3C: Current Safety Rail Values from DB ---
    print("--- Check 3C: Current Safety Rail Values (Live DB) ---")
    try:
        from trading.jubilee.db import JubileeDatabase
        db = JubileeDatabase(bot_name="JUBILEE_IC_TEST")

        # Get config
        ic_config = db.load_ic_config()
        daily_max = getattr(ic_config, 'daily_max_ic_loss', 25000.0)
        max_dd_pct = getattr(ic_config, 'max_ic_drawdown_pct', 10.0)
        starting_capital = getattr(ic_config, 'starting_capital', 500000.0)

        print(f"  Config Values:")
        print(f"    daily_max_ic_loss:    ${daily_max:,.2f}")
        print(f"    max_ic_drawdown_pct:  {max_dd_pct:.1f}%")
        print(f"    starting_capital:     ${starting_capital:,.2f}")
        print(f"    max_contracts:        {getattr(ic_config, 'max_contracts', 'NOT SET')}")
        print(f"    profit_target_pct:    {getattr(ic_config, 'profit_target_pct', 'NOT SET')}")
        print(f"    stop_loss_pct:        {getattr(ic_config, 'stop_loss_pct', 'NOT SET')}")

        # Get daily realized P&L
        daily_pnl = db.get_ic_daily_realized_pnl()
        print(f"\n  Live Values:")
        print(f"    Today's IC realized P&L: ${daily_pnl:,.2f}")

        # Get total realized P&L
        total_pnl = db.get_ic_total_realized_pnl()
        print(f"    Total IC realized P&L:   ${total_pnl:,.2f}")

        # Get borrowed capital (from open box positions)
        open_boxes = db.get_open_positions()
        total_borrowed = 0
        for box in open_boxes:
            try:
                cash = float(getattr(box, 'total_cash_deployed', 0) or 0)
                total_borrowed += cash
            except (ValueError, TypeError, AttributeError):
                pass
        if total_borrowed <= 0:
            total_borrowed = starting_capital
            print(f"    Borrowed capital:        ${total_borrowed:,.2f} (PAPER fallback — no open box positions)")
        else:
            print(f"    Borrowed capital:        ${total_borrowed:,.2f} (from {len(open_boxes)} open box positions)")

        # Calculate safety rail decisions
        print(f"\n  Safety Rail Evaluation:")

        # Daily loss check
        if daily_max > 0 and daily_pnl < -daily_max:
            print(f"    ❌ DAILY LOSS BREACHED: ${daily_pnl:,.2f} < ${-daily_max:,.2f}")
            print(f"       New trades would be BLOCKED")
        else:
            headroom = daily_max + daily_pnl
            print(f"    ✅ Daily loss OK: ${daily_pnl:,.2f} (headroom: ${headroom:,.2f} before halt)")

        # Drawdown check
        if total_borrowed > 0:
            drawdown_pct = abs(min(0, total_pnl)) / total_borrowed * 100
            print(f"    Drawdown: {drawdown_pct:.2f}% of borrowed capital (limit: {max_dd_pct:.1f}%)")
            if drawdown_pct >= max_dd_pct:
                print(f"    ❌ DRAWDOWN BREACHED: {drawdown_pct:.2f}% >= {max_dd_pct:.1f}%")
                print(f"       New trades would be BLOCKED")
            else:
                print(f"    ✅ Drawdown OK: {drawdown_pct:.2f}% < {max_dd_pct:.1f}%")

        # Hypothetical: would a 100-contract trade be allowed?
        print(f"\n  Hypothetical: Would new 100-contract position be ALLOWED?")
        would_block_daily = (daily_max > 0 and daily_pnl < -daily_max)
        would_block_dd = (total_borrowed > 0 and abs(min(0, total_pnl)) / total_borrowed * 100 >= max_dd_pct)

        if would_block_daily or would_block_dd:
            reasons = []
            if would_block_daily:
                reasons.append("daily loss limit breached")
            if would_block_dd:
                reasons.append("drawdown limit breached")
            print(f"    ❌ BLOCKED — {', '.join(reasons)}")
        else:
            print(f"    ✅ ALLOWED — both safety rails clear")

        print(f"\nResult: ✅ PASS — safety rail values retrieved and evaluated")
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL — cannot evaluate safety rail")
        overall_pass = False
    print()

    # --- Cleanup ---
    print(f"""
═══════════════════════════════
TEST 3 OVERALL: {'✅ PASS' if overall_pass else '❌ FAIL'}
═══════════════════════════════
""")


if __name__ == '__main__':
    try:
        run()
    except Exception as e:
        print(f"\n❌ SCRIPT CRASHED: {e}")
        traceback.print_exc()
        sys.exit(1)
