#!/usr/bin/env python3
"""
Debug script to analyze ANCHOR P&L discrepancy.
Shows all positions, their P&L, and helps identify where losses come from.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
today = datetime.now(CT).strftime('%Y-%m-%d')

def main():
    conn = get_connection()
    cursor = conn.cursor()

    print("=" * 80)
    print("ANCHOR P&L DEBUG REPORT")
    print(f"Generated: {datetime.now(CT).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 80)

    # 1. OPEN POSITIONS
    print("\n" + "=" * 80)
    print("1. OPEN POSITIONS (source of unrealized P&L)")
    print("=" * 80)

    cursor.execute('''
        SELECT position_id, total_credit, contracts, spread_width,
               put_short_strike, call_short_strike, expiration,
               DATE(open_time AT TIME ZONE 'America/Chicago') as open_date
        FROM anchor_positions
        WHERE status = 'open'
        ORDER BY open_time DESC
    ''')
    open_positions = cursor.fetchall()

    if not open_positions:
        print("NO OPEN POSITIONS")
    else:
        print(f"\n{'Position':<20} {'Credit':<10} {'Contracts':<10} {'Put Short':<12} {'Call Short':<12} {'Exp':<12} {'Max Loss':<12}")
        print("-" * 90)
        total_max_loss = 0
        for row in open_positions:
            pos_id, credit, contracts, spread, put_short, call_short, exp, open_date = row
            credit = float(credit or 0)
            contracts = int(contracts or 0)
            spread = float(spread or 10)
            max_loss = (spread - credit) * 100 * contracts
            total_max_loss += max_loss
            print(f"{pos_id:<20} ${credit:<9.2f} {contracts:<10} {float(put_short or 0):<12.0f} {float(call_short or 0):<12.0f} {str(exp):<12} ${max_loss:<11.2f}")
        print("-" * 90)
        print(f"TOTAL POTENTIAL MAX LOSS FROM OPEN POSITIONS: ${total_max_loss:.2f}")

    # 2. TODAY'S CLOSED POSITIONS
    print("\n" + "=" * 80)
    print(f"2. TODAY'S CLOSED POSITIONS ({today})")
    print("=" * 80)

    cursor.execute('''
        SELECT position_id, total_credit, contracts, spread_width,
               realized_pnl, close_reason, close_price,
               close_time AT TIME ZONE 'America/Chicago' as close_time_ct
        FROM anchor_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        AND DATE(close_time AT TIME ZONE 'America/Chicago') = %s
        ORDER BY close_time DESC
    ''', (today,))
    today_closed = cursor.fetchall()

    if not today_closed:
        print("NO POSITIONS CLOSED TODAY")
    else:
        print(f"\n{'Position':<20} {'Credit':<10} {'Contracts':<10} {'REALIZED P&L':<15} {'Close Price':<12} {'Reason':<20}")
        print("-" * 100)
        today_total = 0
        wins = 0
        losses = 0
        for row in today_closed:
            pos_id, credit, contracts, spread, realized, reason, close_price, close_time = row
            credit = float(credit or 0)
            realized = float(realized or 0)
            close_price = float(close_price or 0)
            today_total += realized
            if realized > 0:
                wins += 1
                pnl_str = f"+${realized:.2f}"
            else:
                losses += 1
                pnl_str = f"-${abs(realized):.2f}"
            print(f"{pos_id:<20} ${credit:<9.2f} {contracts:<10} {pnl_str:<15} ${close_price:<11.4f} {reason or '':<20}")
        print("-" * 100)
        print(f"TODAY'S TOTAL: ${today_total:.2f} ({wins} wins, {losses} losses)")

    # 3. ALL TIME SUMMARY
    print("\n" + "=" * 80)
    print("3. ALL TIME SUMMARY")
    print("=" * 80)

    cursor.execute('''
        SELECT
            status,
            COUNT(*) as count,
            COALESCE(SUM(realized_pnl), 0) as total_pnl,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN realized_pnl = 0 OR realized_pnl IS NULL THEN 1 ELSE 0 END) as breakeven
        FROM anchor_positions
        GROUP BY status
    ''')

    print(f"\n{'Status':<15} {'Count':<10} {'Wins':<10} {'Losses':<10} {'Breakeven':<10} {'Total P&L':<15}")
    print("-" * 70)
    for row in cursor.fetchall():
        status, count, total_pnl, wins, losses, be = row
        total_pnl = float(total_pnl or 0)
        print(f"{status:<15} {count:<10} {wins or 0:<10} {losses or 0:<10} {be or 0:<10} ${total_pnl:<14.2f}")

    # 4. CHECK FOR NEGATIVE REALIZED P&L (LOSSES)
    print("\n" + "=" * 80)
    print("4. ALL LOSING TRADES (realized_pnl < 0)")
    print("=" * 80)

    cursor.execute('''
        SELECT position_id, total_credit, contracts, realized_pnl,
               close_reason, DATE(close_time AT TIME ZONE 'America/Chicago') as close_date
        FROM anchor_positions
        WHERE realized_pnl < 0
        ORDER BY close_time DESC
        LIMIT 20
    ''')
    losses = cursor.fetchall()

    if not losses:
        print("NO LOSING TRADES FOUND - All closed positions are wins!")
    else:
        print(f"\n{'Position':<20} {'Credit':<10} {'Contracts':<10} {'LOSS':<15} {'Reason':<20} {'Date':<12}")
        print("-" * 90)
        for row in losses:
            pos_id, credit, contracts, realized, reason, close_date = row
            print(f"{pos_id:<20} ${float(credit or 0):<9.2f} {contracts:<10} -${abs(float(realized or 0)):<14.2f} {reason or '':<20} {str(close_date):<12}")

    # 5. GRAND TOTALS
    print("\n" + "=" * 80)
    print("5. GRAND TOTALS")
    print("=" * 80)

    cursor.execute('''
        SELECT
            COALESCE(SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') THEN realized_pnl ELSE 0 END), 0) as total_realized,
            COUNT(CASE WHEN status = 'open' THEN 1 END) as open_count
        FROM anchor_positions
    ''')
    row = cursor.fetchone()
    total_realized = float(row[0] or 0)
    open_count = row[1] or 0

    print(f"\nTotal Realized P&L (all closed trades): ${total_realized:.2f}")
    print(f"Open Positions: {open_count}")

    if open_positions:
        # Calculate current unrealized using simple estimation
        print(f"\nNote: Unrealized P&L depends on current SPX price.")
        print(f"If SPX has breached a short strike, unrealized could be large negative.")
        print(f"Maximum potential loss from open positions: ${total_max_loss:.2f}")

    # 6. SANITY CHECK - Raw P&L values
    print("\n" + "=" * 80)
    print("6. RAW DATA CHECK - Last 10 closed positions")
    print("=" * 80)

    cursor.execute('''
        SELECT position_id, total_credit, close_price, realized_pnl, contracts,
               (total_credit - close_price) * 100 * contracts as calculated_pnl
        FROM anchor_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        AND close_price IS NOT NULL
        ORDER BY close_time DESC
        LIMIT 10
    ''')

    print(f"\n{'Position':<20} {'Credit':<10} {'Close Val':<12} {'Stored PnL':<15} {'Calc PnL':<15} {'Match?':<8}")
    print("-" * 90)
    for row in cursor.fetchall():
        pos_id, credit, close_price, stored_pnl, contracts, calc_pnl = row
        credit = float(credit or 0)
        close_price = float(close_price or 0)
        stored_pnl = float(stored_pnl or 0)
        calc_pnl = float(calc_pnl or 0)
        match = "YES" if abs(stored_pnl - calc_pnl) < 1 else "NO !!!"
        print(f"{pos_id:<20} ${credit:<9.4f} ${close_price:<11.4f} ${stored_pnl:<14.2f} ${calc_pnl:<14.2f} {match:<8}")

    conn.close()

    print("\n" + "=" * 80)
    print("END OF REPORT")
    print("=" * 80)

if __name__ == "__main__":
    main()


def check_yesterday():
    """Check yesterday's positions in detail"""
    conn = get_connection()
    cursor = conn.cursor()
    
    yesterday = (datetime.now(CT) - timedelta(days=1)).strftime('%Y-%m-%d')
    
    print(f"\n{'='*80}")
    print(f"YESTERDAY'S POSITIONS ({yesterday}) - DETAILED")
    print("="*80)
    
    cursor.execute('''
        SELECT position_id, total_credit, contracts, close_price, realized_pnl,
               close_reason, put_short_strike, call_short_strike, underlying_at_entry
        FROM anchor_positions
        WHERE DATE(close_time AT TIME ZONE 'America/Chicago') = %s
        ORDER BY close_time
    ''', (yesterday,))
    
    rows = cursor.fetchall()
    print(f"\n{'Position':<25} {'Credit':<8} {'Close$':<10} {'PnL':<12} {'Reason':<20} {'Put Short':<10} {'Call Short':<10}")
    print("-" * 110)
    
    for row in rows:
        pos_id, credit, contracts, close_price, pnl, reason, put_short, call_short, underlying = row
        credit = float(credit or 0)
        close_price = float(close_price or 0)
        pnl = float(pnl or 0)
        print(f"{pos_id:<25} ${credit:<7.2f} ${close_price:<9.4f} ${pnl:<11.2f} {reason or 'N/A':<20} {float(put_short or 0):<10.0f} {float(call_short or 0):<10.0f}")
    
    conn.close()

if __name__ == "__main__":
    check_yesterday()
