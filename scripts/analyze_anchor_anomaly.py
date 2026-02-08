#!/usr/bin/env python3
"""
ANCHOR ANOMALY DEEP ANALYSIS
=============================

Investigates the suspicious 97.4% win rate and identical P&L amounts in ANCHOR trades.

Checks:
1. P&L distribution - are all winners truly identical?
2. Credit/contracts variance - are these constant?
3. Close price patterns - all zeros (expired worthless)?
4. Calculation verification - stored vs calculated P&L
5. Comparison with SAMSON (should show variance)
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter
import statistics

CT = ZoneInfo("America/Chicago")


def analyze_pnl_distribution(cursor, bot_name: str, table_name: str):
    """Analyze P&L distribution for a bot."""
    print(f"\n{'='*80}")
    print(f"{bot_name} P&L DISTRIBUTION ANALYSIS")
    print(f"{'='*80}")

    # Get all closed trades
    cursor.execute(f'''
        SELECT
            realized_pnl, total_credit, contracts, close_price, close_reason,
            put_short_strike, call_short_strike, underlying_at_entry,
            DATE(close_time AT TIME ZONE 'America/Chicago') as close_date
        FROM {table_name}
        WHERE status IN ('closed', 'expired', 'partial_close')
        AND realized_pnl IS NOT NULL
        ORDER BY close_time DESC
    ''')

    trades = cursor.fetchall()
    if not trades:
        print(f"NO CLOSED TRADES FOUND IN {table_name}")
        return None

    print(f"\nTotal closed trades: {len(trades)}")

    # P&L distribution
    pnl_values = [float(t[0]) for t in trades]
    pnl_counter = Counter([round(p, 2) for p in pnl_values])

    print(f"\n--- P&L Value Distribution (Top 20) ---")
    print(f"{'P&L Amount':<15} {'Count':<10} {'Percentage':<15}")
    print("-" * 40)
    for pnl, count in pnl_counter.most_common(20):
        pct = count / len(trades) * 100
        print(f"${pnl:<14,.2f} {count:<10} {pct:.1f}%")

    # Unique P&L counts
    unique_pnls = len(pnl_counter)
    print(f"\nUnique P&L values: {unique_pnls} out of {len(trades)} trades")
    print(f"P&L diversity ratio: {unique_pnls / len(trades) * 100:.1f}%")

    if unique_pnls < 10:
        print("\n*** ANOMALY: Very few unique P&L values! ***")

    # Win/Loss breakdown
    wins = [t for t in trades if float(t[0]) > 0]
    losses = [t for t in trades if float(t[0]) < 0]
    breakeven = [t for t in trades if float(t[0]) == 0]

    print(f"\n--- Win/Loss Breakdown ---")
    print(f"Wins:      {len(wins)} ({len(wins)/len(trades)*100:.1f}%)")
    print(f"Losses:    {len(losses)} ({len(losses)/len(trades)*100:.1f}%)")
    print(f"Breakeven: {len(breakeven)} ({len(breakeven)/len(trades)*100:.1f}%)")

    if len(wins)/len(trades) > 0.90:
        print("\n*** ANOMALY: Win rate > 90% is statistically improbable! ***")

    # Credit distribution
    credits = [float(t[1]) for t in trades if t[1]]
    credit_counter = Counter([round(c, 2) for c in credits])

    print(f"\n--- Total Credit Distribution (Top 10) ---")
    print(f"{'Credit':<15} {'Count':<10}")
    print("-" * 25)
    for credit, count in credit_counter.most_common(10):
        print(f"${credit:<14,.2f} {count:<10}")

    unique_credits = len(credit_counter)
    print(f"\nUnique credit values: {unique_credits}")

    if unique_credits < 5:
        print("\n*** ANOMALY: Credits are nearly constant - should vary with VIX/market ***")

    # Contract distribution
    contracts = [int(t[2]) for t in trades if t[2]]
    contract_counter = Counter(contracts)

    print(f"\n--- Contract Count Distribution ---")
    print(f"{'Contracts':<15} {'Count':<10}")
    print("-" * 25)
    for contr, count in contract_counter.most_common():
        print(f"{contr:<15} {count:<10}")

    if len(contract_counter) == 1:
        print("\n*** ANOMALY: All trades have identical contracts - position sizing appears frozen ***")

    # Close price distribution
    close_prices = [float(t[3]) for t in trades if t[3] is not None]
    close_counter = Counter([round(c, 4) for c in close_prices])

    print(f"\n--- Close Price Distribution (Top 10) ---")
    print(f"{'Close Price':<15} {'Count':<10}")
    print("-" * 25)
    for cp, count in close_counter.most_common(10):
        print(f"${cp:<14,.4f} {count:<10}")

    zeros = len([c for c in close_prices if c == 0.0])
    print(f"\nTrades closed at $0.00 (expired worthless): {zeros} ({zeros/len(close_prices)*100:.1f}%)")

    if zeros / len(close_prices) > 0.9:
        print("\n*** INFO: Most trades expired worthless - consistent with high win rate ***")
        print("          BUT credits and contracts should still vary!")

    # Calculation verification
    print(f"\n--- P&L CALCULATION VERIFICATION (sample 20) ---")
    print(f"{'Position':<25} {'Credit':<10} {'Close':<12} {'Stored':<12} {'Calculated':<12} {'Match?'}")
    print("-" * 85)

    mismatches = 0
    for trade in trades[:20]:
        pnl, credit, contracts_val, close_price, reason, _, _, _, _ = trade
        pnl = float(pnl or 0)
        credit = float(credit or 0)
        contracts_val = int(contracts_val or 1)
        close_price = float(close_price or 0)

        calculated = (credit - close_price) * 100 * contracts_val
        match = "YES" if abs(pnl - calculated) < 1 else "NO !!!"
        if match == "NO !!!":
            mismatches += 1

        print(f"Trade #{trades.index(trade)+1:<18} ${credit:<9.4f} ${close_price:<11.4f} ${pnl:<11.2f} ${calculated:<11.2f} {match}")

    if mismatches > 0:
        print(f"\n*** CRITICAL: {mismatches} P&L mismatches found! Stored != Calculated ***")

    # Statistical summary
    if len(pnl_values) > 1:
        print(f"\n--- STATISTICAL SUMMARY ---")
        print(f"Mean P&L:     ${statistics.mean(pnl_values):.2f}")
        print(f"Median P&L:   ${statistics.median(pnl_values):.2f}")
        print(f"Std Dev:      ${statistics.stdev(pnl_values):.2f}")
        print(f"Min P&L:      ${min(pnl_values):.2f}")
        print(f"Max P&L:      ${max(pnl_values):.2f}")

        # Check for suspicious low variance
        if len(wins) > 1:
            win_pnls = [float(t[0]) for t in wins]
            win_stdev = statistics.stdev(win_pnls) if len(win_pnls) > 1 else 0
            print(f"\nWinning trades std dev: ${win_stdev:.2f}")
            if win_stdev < 10:
                print("*** CRITICAL ANOMALY: Winning trades have near-zero variance! ***")
                print("    This is statistically impossible with variable market conditions.")

    return {
        'total': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'unique_pnls': unique_pnls,
        'unique_credits': unique_credits,
        'unique_contracts': len(contract_counter),
    }


def analyze_close_reasons(cursor, table_name: str):
    """Analyze how positions were closed."""
    print(f"\n--- CLOSE REASON ANALYSIS ---")

    cursor.execute(f'''
        SELECT close_reason, COUNT(*) as count, AVG(realized_pnl) as avg_pnl
        FROM {table_name}
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY close_reason
        ORDER BY count DESC
    ''')

    print(f"{'Close Reason':<25} {'Count':<10} {'Avg P&L':<15}")
    print("-" * 50)
    for row in cursor.fetchall():
        reason, count, avg_pnl = row
        avg_pnl = float(avg_pnl or 0)
        print(f"{reason or 'NULL':<25} {count:<10} ${avg_pnl:<14.2f}")


def check_dates_and_credits(cursor, table_name: str):
    """Check if credits/contracts vary by date."""
    print(f"\n--- DAILY CREDIT/CONTRACT PATTERNS ---")

    cursor.execute(f'''
        SELECT
            DATE(close_time AT TIME ZONE 'America/Chicago') as trade_date,
            COUNT(*) as trades,
            AVG(total_credit) as avg_credit,
            MIN(total_credit) as min_credit,
            MAX(total_credit) as max_credit,
            AVG(contracts) as avg_contracts,
            AVG(realized_pnl) as avg_pnl
        FROM {table_name}
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY DATE(close_time AT TIME ZONE 'America/Chicago')
        ORDER BY trade_date DESC
        LIMIT 15
    ''')

    print(f"{'Date':<12} {'Trades':<8} {'Avg Credit':<12} {'Min':<10} {'Max':<10} {'Contracts':<10} {'Avg P&L':<12}")
    print("-" * 90)
    for row in cursor.fetchall():
        date, trades, avg_c, min_c, max_c, avg_contr, avg_pnl = row
        avg_c = float(avg_c or 0)
        min_c = float(min_c or 0)
        max_c = float(max_c or 0)
        avg_contr = float(avg_contr or 0)
        avg_pnl = float(avg_pnl or 0)
        print(f"{str(date):<12} {trades:<8} ${avg_c:<11.2f} ${min_c:<9.2f} ${max_c:<9.2f} {avg_contr:<10.1f} ${avg_pnl:<11.2f}")


def check_losing_trades(cursor, table_name: str):
    """Detailed analysis of any losing trades."""
    print(f"\n--- LOSING TRADE DETAILS ---")

    cursor.execute(f'''
        SELECT
            position_id, total_credit, close_price, realized_pnl, contracts,
            close_reason, underlying_at_entry, put_short_strike, call_short_strike,
            DATE(close_time AT TIME ZONE 'America/Chicago') as close_date
        FROM {table_name}
        WHERE status IN ('closed', 'expired', 'partial_close')
        AND realized_pnl < 0
        ORDER BY realized_pnl ASC
        LIMIT 20
    ''')

    rows = cursor.fetchall()
    if not rows:
        print("NO LOSING TRADES FOUND")
        print("\n*** CRITICAL ANOMALY: Zero losses is statistically impossible for IC trading ***")
        return

    print(f"Found {len(rows)} losing trades (showing worst 20):")
    print(f"{'Position':<30} {'Loss':<12} {'Credit':<10} {'Close$':<10} {'Reason':<20}")
    print("-" * 90)
    for row in rows:
        pos_id, credit, close_price, pnl, contracts, reason, entry, put_s, call_s, date = row
        pnl = float(pnl or 0)
        credit = float(credit or 0)
        close_price = float(close_price or 0)
        print(f"{pos_id or 'N/A':<30} ${pnl:<11.2f} ${credit:<9.4f} ${close_price:<9.4f} {reason or 'N/A':<20}")


def main():
    print("=" * 80)
    print("ANCHOR ANOMALY DEEP ANALYSIS")
    print(f"Generated: {datetime.now(CT).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 80)

    conn = get_connection()
    cursor = conn.cursor()

    # Analyze ANCHOR
    anchor_stats = analyze_pnl_distribution(cursor, "ANCHOR", "anchor_positions")
    if anchor_stats:
        analyze_close_reasons(cursor, "anchor_positions")
        check_dates_and_credits(cursor, "anchor_positions")
        check_losing_trades(cursor, "anchor_positions")

    # Compare with SAMSON for sanity check
    print("\n\n")
    print("=" * 80)
    print("COMPARISON: SAMSON (should show normal variance)")
    print("=" * 80)

    titan_stats = analyze_pnl_distribution(cursor, "SAMSON", "samson_positions")
    if titan_stats:
        analyze_close_reasons(cursor, "samson_positions")

    # Final diagnosis
    print("\n\n")
    print("=" * 80)
    print("FINAL DIAGNOSIS")
    print("=" * 80)

    if anchor_stats:
        issues = []

        if anchor_stats['unique_pnls'] < 20 and anchor_stats['total'] > 100:
            issues.append("CRITICAL: Less than 20 unique P&L values across 100+ trades")

        if anchor_stats['unique_credits'] < 5:
            issues.append("CRITICAL: Credits are nearly constant (should vary with VIX)")

        if anchor_stats['unique_contracts'] == 1:
            issues.append("CRITICAL: All trades have identical contracts (sizing frozen)")

        win_rate = anchor_stats['wins'] / anchor_stats['total']
        if win_rate > 0.95:
            issues.append(f"SUSPICIOUS: Win rate of {win_rate:.1%} is statistically improbable")

        if anchor_stats['losses'] == 0:
            issues.append("CRITICAL: Zero losing trades - impossible for real IC trading")

        if issues:
            print("\nISSUES FOUND:")
            for i, issue in enumerate(issues, 1):
                print(f"  {i}. {issue}")

            print("\n" + "-" * 60)
            print("LIKELY ROOT CAUSES:")
            print("-" * 60)
            print("""
1. HARDCODED CREDIT: Signal generation might be using a fixed credit value
   instead of calculating from actual option prices.

2. FROZEN POSITION SIZING: Kelly sizing might always return the same value,
   or it's falling back to a fixed contract count.

3. UNREALISTIC PAPER TRADING: All trades might be expiring "worthless"
   (close_price = 0) because:
   - No actual price checking at expiration
   - Settlement logic always assumes price is between short strikes

4. MISSING STOP-LOSS EXECUTION: Stop losses might not be triggering properly,
   causing trades that should have lost to appear as wins.

5. TEST/FAKE DATA: The data might be from initialization or testing,
   not actual paper trading execution.
""")
        else:
            print("\nNo obvious anomalies detected in statistical distribution.")

    conn.close()
    print("\n" + "=" * 80)
    print("END OF ANALYSIS")
    print("=" * 80)


if __name__ == "__main__":
    main()
