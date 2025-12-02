#!/bin/bash
# ==========================================================================
# SHOW ALL TRADES - Complete Trade Log
# ==========================================================================
#
# Shows EVERY trade with full transparency:
# - Option ticker (e.g., O:SPX241220P05800000)
# - Entry/Exit prices
# - Price source (POLYGON, TRADIER, ESTIMATED)
# - P&L
# - Status
#
# This is your audit trail - verify any trade on Polygon.io
# ==========================================================================

echo "==========================================================================="
echo "SPX WHEEL - COMPLETE TRADE LOG"
echo "==========================================================================="
echo "Time: $(date)"
echo ""

cd /home/user/AlphaGEX

python3 << 'EOF'
import sys
sys.path.insert(0, '/home/user/AlphaGEX')

from database_adapter import get_connection
import json

try:
    conn = get_connection()
    cursor = conn.cursor()

    # Get all trades
    cursor.execute('''
        SELECT
            id, option_ticker, strike, expiration, contracts,
            entry_price, exit_price, premium_received, settlement_pnl, total_pnl,
            status, opened_at, closed_at, parameters_used
        FROM spx_wheel_positions
        ORDER BY opened_at DESC
    ''')

    trades = cursor.fetchall()

    if not trades:
        print("No trades found.")
        print("\nRun calibration first: ./scripts/calibrate_spx_wheel.sh")
        print("Then run daily trading: ./scripts/run_spx_daily.sh")
    else:
        print(f"Total Trades: {len(trades)}")
        print("")

        # Summary
        real_count = 0
        estimated_count = 0
        total_pnl = 0
        winners = 0
        closed = 0

        for trade in trades:
            params = trade[13] or '{}'
            if isinstance(params, str):
                params = json.loads(params)
            source = params.get('price_source', 'ESTIMATED')

            if source in ['POLYGON', 'TRADIER_LIVE', 'POLYGON_HISTORICAL']:
                real_count += 1
            else:
                estimated_count += 1

            if trade[10] == 'CLOSED':
                closed += 1
                pnl = float(trade[9] or 0)
                total_pnl += pnl
                if pnl > 0:
                    winners += 1

        total_points = real_count + estimated_count
        data_quality = (real_count / total_points * 100) if total_points > 0 else 0
        win_rate = (winners / closed * 100) if closed > 0 else 0

        print("=" * 100)
        print("DATA QUALITY SUMMARY")
        print("=" * 100)
        quality_status = "✓ RELIABLE" if data_quality >= 80 else "⚠️ LOW" if data_quality >= 50 else "❌ UNRELIABLE"
        print(f"Data Quality:     {data_quality:.1f}% {quality_status}")
        print(f"Real Data:        {real_count} trades with Polygon/Tradier prices")
        print(f"Estimated Data:   {estimated_count} trades with formula-based prices")
        print("")
        print(f"Total P&L:        ${total_pnl:,.2f}")
        print(f"Win Rate:         {win_rate:.1f}% ({winners}/{closed} closed trades)")
        print("=" * 100)
        print("")

        # Column headers
        print(f"{'ID':<4} {'TICKER':<28} {'STRIKE':>10} {'ENTRY':>8} {'EXIT':>8} {'PREMIUM':>12} {'P&L':>12} {'SOURCE':<12} {'STATUS':<8}")
        print("-" * 110)

        for trade in trades:
            trade_id = trade[0]
            ticker = trade[1] or ''
            strike = float(trade[2] or 0)
            entry = float(trade[5] or 0)
            exit_p = float(trade[6]) if trade[6] else None
            premium = float(trade[7] or 0)
            pnl = float(trade[9]) if trade[9] else None
            status = trade[10]

            params = trade[13] or '{}'
            if isinstance(params, str):
                params = json.loads(params)
            source = params.get('price_source', 'ESTIMATED')

            # Format values
            strike_str = f"${strike:,.0f}"
            entry_str = f"${entry:.2f}"
            exit_str = f"${exit_p:.2f}" if exit_p else "-"
            premium_str = f"${premium:,.2f}"
            pnl_str = f"${pnl:,.2f}" if pnl else "-"

            # Color coding for source
            source_indicator = ""
            if source == 'ESTIMATED':
                source_indicator = "⚠️"
            elif source in ['POLYGON', 'POLYGON_HISTORICAL']:
                source_indicator = "✓"
            elif source == 'TRADIER_LIVE':
                source_indicator = "✓"

            print(f"{trade_id:<4} {ticker:<28} {strike_str:>10} {entry_str:>8} {exit_str:>8} {premium_str:>12} {pnl_str:>12} {source_indicator}{source:<11} {status:<8}")

        print("-" * 110)
        print("")
        print("LEGEND:")
        print("  ✓ = Real price from Polygon or Tradier")
        print("  ⚠️ = Estimated price (formula-based)")
        print("")
        print("VERIFY ANY TRADE:")
        print("  Search the ticker on Polygon.io: https://polygon.io/quote/")
        print("  Example: O:SPX241220P05800000 = SPX Put, Dec 20 2024, Strike $5800")

    # ================================================================
    # BACKTEST TRADES - Show what calibration used
    # ================================================================
    print("")
    print("=" * 100)
    print("BACKTEST TRADES (Historical simulation used for calibration)")
    print("=" * 100)

    cursor.execute('''
        SELECT DISTINCT ON (backtest_id) backtest_id, COUNT(*) as count
        FROM spx_wheel_backtest_trades
        GROUP BY backtest_id
        ORDER BY backtest_id DESC
        LIMIT 1
    ''')
    backtest_info = cursor.fetchone()

    if backtest_info:
        backtest_id = backtest_info[0]
        print(f"Backtest ID: {backtest_id}")

        cursor.execute('''
            SELECT
                trade_id, trade_date, trade_type, option_ticker, strike,
                entry_price, total_pnl, price_source
            FROM spx_wheel_backtest_trades
            WHERE backtest_id = %s
            ORDER BY trade_date DESC
            LIMIT 20
        ''', (backtest_id,))

        bt_trades = cursor.fetchall()
        if bt_trades:
            print(f"Showing latest 20 of {backtest_info[1]} backtest trades:")
            print("")
            print(f"{'#':<4} {'DATE':<12} {'TYPE':<18} {'TICKER':<28} {'STRIKE':>10} {'ENTRY':>8} {'P&L':>12} {'SOURCE':<12}")
            print("-" * 110)

            for t in bt_trades:
                tid = t[0] or 0
                tdate = str(t[1])[:10] if t[1] else ''
                ttype = t[2] or 'SELL_PUT'
                ticker = t[3] or ''
                strike = float(t[4] or 0)
                entry = float(t[5] or 0)
                pnl = float(t[6]) if t[6] else None
                source = t[7] or 'ESTIMATED'

                strike_str = f"${strike:,.0f}"
                entry_str = f"${entry:.2f}"
                pnl_str = f"${pnl:,.2f}" if pnl else "-"

                source_ind = "✓" if source in ['POLYGON_HISTORICAL', 'POLYGON'] else "⚠️"
                print(f"{tid:<4} {tdate:<12} {ttype:<18} {ticker:<28} {strike_str:>10} {entry_str:>8} {pnl_str:>12} {source_ind}{source:<11}")

            print("-" * 110)
    else:
        print("No backtest trades found.")
        print("Run calibration first: ./scripts/calibrate_spx_wheel.sh")

    conn.close()

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
EOF

echo ""
echo "==========================================================================="
