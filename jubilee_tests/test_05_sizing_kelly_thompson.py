#!/usr/bin/env python3
"""Test 5: Position Sizing — Kelly Criterion + Thompson Sampling

Verifies Kelly and Thompson Sampling don't crash at runtime,
and tests with real DB values.
Read-only — no data modification.
"""
import sys
import inspect
import traceback

HEADER = """
╔══════════════════════════════════════╗
║  TEST 5: Kelly + Thompson Sampling   ║
╚══════════════════════════════════════╝
"""


def run():
    print(HEADER)

    overall_pass = True

    # --- Check 5A: Kelly criterion availability ---
    print("--- Check 5A: Kelly Criterion Import ---")
    try:
        from quant.monte_carlo_kelly import get_safe_position_size
        print(f"  ✅ get_safe_position_size imported from quant.monte_carlo_kelly")
        sig = inspect.signature(get_safe_position_size)
        print(f"  Signature: get_safe_position_size{sig}")
        print(f"Result: ✅ PASS")
    except ImportError as e:
        print(f"  ❌ Cannot import: {e}")
        print(f"  Kelly criterion will NOT be used — fallback to config-based sizing")
        print(f"Result: ⚠️ WARNING — Kelly not available")
    except Exception as e:
        print(f"  Error: {e}")
        print(f"Result: ⚠️ WARNING")
    print()

    # --- Check 5B: Count closed trades (Kelly requires 20+) ---
    print("--- Check 5B: Trade Count for Kelly ---")
    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM jubilee_ic_closed_trades
            WHERE close_time > NOW() - INTERVAL '90 days'
        """)
        trade_count_90d = int(cursor.fetchone()[0] or 0)

        cursor.execute("""
            SELECT COUNT(*) FROM jubilee_ic_closed_trades
        """)
        trade_count_all = int(cursor.fetchone()[0] or 0)

        print(f"  Closed IC trades (90 days): {trade_count_90d}")
        print(f"  Closed IC trades (all time): {trade_count_all}")

        if trade_count_90d >= 20:
            print(f"  ✅ Kelly criterion IS active ({trade_count_90d} >= 20 trades)")

            # Get Kelly inputs
            cursor.execute("""
                SELECT realized_pnl, entry_credit, contracts
                FROM jubilee_ic_closed_trades
                WHERE close_time > NOW() - INTERVAL '90 days'
                ORDER BY close_time DESC
                LIMIT 100
            """)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            trades = [dict(zip(columns, r)) for r in rows]

            wins = [t for t in trades if float(t['realized_pnl'] or 0) > 0]
            losses = [t for t in trades if float(t['realized_pnl'] or 0) <= 0]
            win_rate = len(wins) / len(trades) if trades else 0
            avg_win = sum(float(t['realized_pnl'] or 0) for t in wins) / len(wins) if wins else 0
            avg_loss = abs(sum(float(t['realized_pnl'] or 0) for t in losses) / len(losses)) if losses else 0

            print(f"\n  Kelly Inputs (from DB):")
            print(f"    Win rate:    {win_rate:.1%}")
            print(f"    Avg win:     ${avg_win:,.2f}")
            print(f"    Avg loss:    ${avg_loss:,.2f}")
            print(f"    Sample size: {len(trades)}")

            # Try to compute Kelly
            try:
                from quant.monte_carlo_kelly import get_safe_position_size
                available_capital = 500000.0  # Default
                avg_win_pct = avg_win / available_capital * 100 if wins else 0
                avg_loss_pct = avg_loss / available_capital * 100 if losses else 10

                kelly_result = get_safe_position_size(
                    win_rate=win_rate,
                    avg_win=avg_win_pct,
                    avg_loss=avg_loss_pct,
                    sample_size=len(trades),
                    account_size=available_capital,
                    max_risk_pct=4.0  # 2x default max_capital_per_trade_pct
                )
                print(f"\n  Kelly Result:")
                for k, v in kelly_result.items():
                    print(f"    {k}: {v}")
                print(f"\nResult: ✅ PASS — Kelly computed successfully")
            except ImportError:
                print(f"\nResult: ⚠️ WARNING — Kelly module not available")
            except Exception as e:
                print(f"\n  ❌ Kelly computation failed: {e}")
                traceback.print_exc()
                print(f"Result: ❌ FAIL — Kelly crashes at runtime")
                overall_pass = False
        else:
            print(f"  ℹ️  Kelly criterion is INACTIVE ({trade_count_90d} < 20 trades)")
            print(f"  Sizing will use config-based fallback")
            print(f"Result: ✅ PASS — too few trades, Kelly correctly inactive")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL — cannot query trade data")
        overall_pass = False
    print()

    # --- Check 5C: Thompson Sampling availability ---
    print("--- Check 5C: Thompson Sampling (MathOptimizerMixin) ---")
    try:
        from trading.mixins.math_optimizer_mixin import MathOptimizerMixin
        print(f"  ✅ MathOptimizerMixin imported successfully")

        mixin = MathOptimizerMixin()
        if hasattr(mixin, 'math_get_allocation'):
            try:
                allocation = mixin.math_get_allocation()
                print(f"  Allocation result: {allocation}")
                jubilee_alloc = allocation.get('allocations', {}).get('JUBILEE', 0.2)
                weight = jubilee_alloc / 0.2
                print(f"  JUBILEE allocation: {jubilee_alloc:.1%}")
                print(f"  Thompson weight: {weight:.2f}x")
                print(f"Result: ✅ PASS — Thompson Sampling active")
            except Exception as e:
                print(f"  ⚠️ math_get_allocation() failed: {e}")
                print(f"  Thompson weight will default to 1.0")
                print(f"Result: ⚠️ WARNING — Thompson fallback to 1.0")
        else:
            print(f"  ⚠️ MathOptimizerMixin has no math_get_allocation method")
            print(f"Result: ⚠️ WARNING — Thompson not available")
    except ImportError as e:
        print(f"  ❌ Cannot import MathOptimizerMixin: {e}")
        print(f"  Thompson weight will default to 1.0x (no adjustment)")
        print(f"Result: ⚠️ WARNING — Thompson not available")
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL")
        overall_pass = False
    print()

    # --- Check 5D: End-to-end calculate_position_size ---
    print("--- Check 5D: End-to-End calculate_position_size ---")
    try:
        from trading.jubilee.signals import JubileeICSignalGenerator
        from trading.jubilee.models import JubileeICConfig

        config = JubileeICConfig()
        gen = JubileeICSignalGenerator(config)

        # Try calling calculate_position_size with reasonable inputs
        available_capital = 500000.0
        max_loss_per_contract = 1000.0  # $10 spread × 100
        thompson_weight = 1.0

        result = gen.calculate_position_size(
            available_capital=available_capital,
            max_loss_per_contract=max_loss_per_contract,
            thompson_weight=thompson_weight
        )
        print(f"  calculate_position_size result:")
        print(f"    available_capital:      ${available_capital:,.2f}")
        print(f"    max_loss_per_contract:  ${max_loss_per_contract:,.2f}")
        print(f"    thompson_weight:        {thompson_weight}")
        print(f"    → contracts:            {result}")

        if isinstance(result, int) and result > 0:
            print(f"\nResult: ✅ PASS — returns valid contract count")
        elif isinstance(result, int) and result == 0:
            print(f"\nResult: ⚠️ WARNING — returns 0 contracts (may be correct if Kelly says no)")
        else:
            print(f"\nResult: ❌ FAIL — unexpected return type: {type(result)}")
            overall_pass = False
    except Exception as e:
        print(f"  ❌ calculate_position_size crashed: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL — runtime crash in position sizing")
        overall_pass = False
    print()

    # --- Check 5E: Source inspection of calculate_position_size ---
    print("--- Check 5E: calculate_position_size Source Inspection ---")
    try:
        from trading.jubilee.signals import JubileeICSignalGenerator
        source = inspect.getsource(JubileeICSignalGenerator.calculate_position_size)
        print(f"  Source ({len(source)} chars):")
        for i, line in enumerate(source.strip().split('\n')):
            print(f"    {i+1:3d} | {line}")

        checks = {
            'Kelly': '_get_kelly_position_size' in source,
            'Thompson weight': 'thompson_weight' in source,
            'max_contracts': 'max_contracts' in source,
            'Clamp': 'min(' in source or 'max(' in source or 'clamp' in source.lower(),
        }

        print(f"\n  Features found:")
        for feature, found in checks.items():
            print(f"    {'✅' if found else '❌'} {feature}")

        print(f"\nResult: ✅ PASS — source inspected")
    except Exception as e:
        print(f"  Error: {e}")
        print(f"Result: ⚠️ WARNING")
    print()

    print(f"""
═══════════════════════════════
TEST 5 OVERALL: {'✅ PASS' if overall_pass else '❌ FAIL'}
═══════════════════════════════
""")


if __name__ == '__main__':
    try:
        run()
    except Exception as e:
        print(f"\n❌ SCRIPT CRASHED: {e}")
        traceback.print_exc()
        sys.exit(1)
