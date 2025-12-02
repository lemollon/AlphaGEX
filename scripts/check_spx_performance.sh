#!/bin/bash
# ==========================================================================
# SPX WHEEL PERFORMANCE MONITOR
# ==========================================================================
#
# Shows EXACTLY how your live trading compares to the backtest.
#
# This is the CRITICAL feedback loop:
# - If live matches backtest → System is working as expected
# - If live diverges > 10% → Consider recalibration
# - If live significantly underperforms → Market regime may have changed
#
# ==========================================================================

echo "==========================================================================="
echo "SPX WHEEL - PERFORMANCE REPORT"
echo "==========================================================================="
echo "Time: $(date)"
echo ""

cd /home/user/AlphaGEX

python3 << 'EOF'
import sys
sys.path.insert(0, '/home/user/AlphaGEX')

from database_adapter import get_connection
from datetime import datetime, timedelta
import json

def get_performance():
    conn = get_connection()
    cursor = conn.cursor()

    # Check if tables exist
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'spx_wheel_positions'
        )
    """)
    if not cursor.fetchone()[0]:
        print("No SPX wheel positions table found. Run calibration first.")
        return

    print("="*70)
    print("CURRENT PARAMETERS")
    print("="*70)

    # Get active parameters
    cursor.execute("""
        SELECT parameters, timestamp
        FROM spx_wheel_parameters
        WHERE is_active = TRUE
        ORDER BY timestamp DESC LIMIT 1
    """)
    result = cursor.fetchone()

    if result:
        params = result[0]
        calibration_date = result[1]
        print(f"""
Calibrated on: {calibration_date}

Parameters in use:
  Put Delta:        {params.get('put_delta', 'N/A')}
  DTE Target:       {params.get('dte_target', 'N/A')}
  Max Margin:       {params.get('max_margin_pct', 0)*100:.0f}%

Backtest Expectations:
  Win Rate:         {params.get('backtest_win_rate', 0):.1f}%
  Total Return:     {params.get('backtest_total_return', 0):+.1f}%
  Max Drawdown:     {params.get('backtest_max_drawdown', 0):.1f}%
""")
    else:
        print("\nNo calibrated parameters found. Run calibrate_spx_wheel.sh first.")
        params = None

    print("="*70)
    print("LIVE TRADING RESULTS")
    print("="*70)

    # Get position statistics
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status = 'OPEN') as open_count,
            COUNT(*) FILTER (WHERE status = 'CLOSED') as closed_count,
            COUNT(*) FILTER (WHERE total_pnl > 0) as winners,
            COUNT(*) FILTER (WHERE total_pnl <= 0 AND status = 'CLOSED') as losers,
            COALESCE(SUM(premium_received), 0) as total_premium,
            COALESCE(SUM(settlement_pnl), 0) as total_settlement,
            COALESCE(SUM(total_pnl), 0) as total_pnl
        FROM spx_wheel_positions
    """)
    stats = cursor.fetchone()

    total, open_count, closed_count, winners, losers, premium, settlement, pnl = stats

    if total == 0:
        print("\nNo positions yet. Run run_spx_daily.sh to start trading.")
    else:
        live_win_rate = (winners / closed_count * 100) if closed_count > 0 else 0

        print(f"""
Positions:
  Total:            {total}
  Open:             {open_count}
  Closed:           {closed_count}
  Winners:          {winners}
  Losers:           {losers}
  Win Rate:         {live_win_rate:.1f}%

P&L:
  Premium Collected:  ${premium:,.2f}
  Settlement P&L:     ${settlement:,.2f}
  Net P&L:            ${pnl:,.2f}
""")

        print("="*70)
        print("BACKTEST COMPARISON")
        print("="*70)

        if params:
            expected_win_rate = params.get('backtest_win_rate', 0)
            win_rate_diff = live_win_rate - expected_win_rate

            print(f"""
Win Rate:
  Live:             {live_win_rate:.1f}%
  Backtest:         {expected_win_rate:.1f}%
  Difference:       {win_rate_diff:+.1f}%
""")

            if abs(win_rate_diff) > 10:
                print("⚠️  ALERT: Win rate divergence > 10%")
                print("   Consider recalibrating with recent data.")
            elif closed_count >= 10:
                print("✓ Performance is tracking within expectations.")
            else:
                print("   Not enough trades yet for meaningful comparison.")

    # Recent trades
    print("\n" + "="*70)
    print("RECENT POSITIONS")
    print("="*70)

    cursor.execute("""
        SELECT
            option_ticker,
            strike,
            expiration,
            status,
            premium_received,
            settlement_pnl,
            total_pnl,
            notes
        FROM spx_wheel_positions
        ORDER BY opened_at DESC
        LIMIT 10
    """)

    positions = cursor.fetchall()

    if positions:
        print(f"\n{'Ticker':<30} {'Strike':>10} {'Status':>10} {'P&L':>12}")
        print("-"*70)
        for pos in positions:
            ticker, strike, exp, status, prem, settle, pnl, notes = pos
            pnl_str = f"${float(pnl or 0):,.2f}"
            print(f"{ticker:<30} ${float(strike or 0):>8,.0f} {status:>10} {pnl_str:>12}")
    else:
        print("\nNo positions to show.")

    conn.close()

get_performance()
EOF

echo ""
echo "==========================================================================="
echo "PERFORMANCE REPORT COMPLETE"
echo "==========================================================================="
echo ""
echo "WORKFLOW REMINDER:"
echo "  1. If divergence > 10%: ./scripts/calibrate_spx_wheel.sh"
echo "  2. Daily trading: ./scripts/run_spx_daily.sh"
echo "  3. This report: ./scripts/check_spx_performance.sh"
echo "==========================================================================="
