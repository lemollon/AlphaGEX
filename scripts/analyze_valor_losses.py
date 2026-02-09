#!/usr/bin/env python3
"""
VALOR Loss Analysis Script
=============================
Run this on Render shell to analyze why losses are bigger than wins.

Usage: python scripts/analyze_valor_losses.py
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection


def analyze_valor_trades():
    """Comprehensive analysis of VALOR trading performance."""
    conn = get_connection()
    c = conn.cursor()

    print("=" * 70)
    print("VALOR TRADE ANALYSIS")
    print("=" * 70)

    # ============================================================
    # 1. OVERALL STATS
    # ============================================================
    c.execute("""
        SELECT
            COUNT(*) as total_trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
            SUM(realized_pnl) as total_pnl,
            AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) as avg_win,
            AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END) as avg_loss,
            MAX(realized_pnl) as best_trade,
            MIN(realized_pnl) as worst_trade
        FROM valor_closed_trades
    """)
    row = c.fetchone()

    if not row or row[0] == 0:
        print("No closed trades found!")
        return

    total, wins, losses, total_pnl, avg_win, avg_loss, best, worst = row
    win_rate = (wins / total * 100) if total > 0 else 0

    print(f"\n📊 OVERALL PERFORMANCE ({total} trades)")
    print("-" * 50)
    print(f"Wins: {wins} | Losses: {losses} | Win Rate: {win_rate:.1f}%")
    print(f"Total P&L: ${total_pnl:.2f}")
    print(f"Avg Win: ${avg_win:.2f if avg_win else 0:.2f}")
    print(f"Avg Loss: ${avg_loss:.2f if avg_loss else 0:.2f}")
    print(f"Best Trade: ${best:.2f if best else 0:.2f}")
    print(f"Worst Trade: ${worst:.2f if worst else 0:.2f}")

    if avg_win and avg_loss:
        risk_reward = abs(avg_loss / avg_win)
        print(f"Risk/Reward Ratio: {risk_reward:.2f}:1 (losses are {risk_reward:.1f}x bigger than wins)")

    # ============================================================
    # 2. MFE/MAE ANALYSIS (Max Favorable/Adverse Excursion)
    # ============================================================
    print(f"\n📈 MFE/MAE ANALYSIS (Winners That Became Losers?)")
    print("-" * 50)

    c.execute("""
        SELECT
            COUNT(*) as total_losses,
            SUM(CASE WHEN was_profitable_before_loss = TRUE THEN 1 ELSE 0 END) as reversals,
            AVG(mfe_points) as avg_mfe,
            AVG(mae_points) as avg_mae,
            COUNT(CASE WHEN mfe_points > 1.5 THEN 1 END) as had_1_5pt_profit,
            COUNT(CASE WHEN mfe_points > 3.0 THEN 1 END) as had_3pt_profit
        FROM valor_closed_trades
        WHERE realized_pnl < 0
    """)
    row = c.fetchone()

    if row and row[0] > 0:
        total_losses, reversals, avg_mfe, avg_mae, had_1_5, had_3 = row
        print(f"Total Losses: {total_losses}")
        print(f"Reversals (were profitable before loss): {reversals or 0} ({(reversals or 0)/total_losses*100:.1f}%)")
        print(f"Avg MFE for losses: {avg_mfe:.2f if avg_mfe else 0:.2f} pts (profit they had before losing)")
        print(f"Avg MAE for losses: {avg_mae:.2f if avg_mae else 0:.2f} pts (worst drawdown)")
        print(f"Losses that HAD 1.5+ pts profit: {had_1_5 or 0}/{total_losses} ({(had_1_5 or 0)/total_losses*100:.1f}%)")
        print(f"Losses that HAD 3.0+ pts profit: {had_3 or 0}/{total_losses} ({(had_3 or 0)/total_losses*100:.1f}%)")

        if (had_1_5 or 0) > total_losses * 0.3:
            print("\n⚠️  PROBLEM: Many losses had profit before reversing!")
            print("   -> Need to take profits earlier or tighten trailing stops")

    # ============================================================
    # 3. MFE FOR WINS - How much profit do winners typically have?
    # ============================================================
    c.execute("""
        SELECT
            AVG(mfe_points) as avg_mfe,
            MAX(mfe_points) as max_mfe,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mfe_points) as median_mfe,
            PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY mfe_points) as p90_mfe
        FROM valor_closed_trades
        WHERE realized_pnl > 0 AND mfe_points IS NOT NULL
    """)
    row = c.fetchone()
    if row and row[0]:
        avg_mfe, max_mfe, median_mfe, p90_mfe = row
        print(f"\n📊 WINNING TRADES MFE:")
        print(f"   Avg MFE: {avg_mfe:.2f} pts")
        print(f"   Median MFE: {median_mfe:.2f} pts")
        print(f"   90th percentile MFE: {p90_mfe:.2f} pts")
        print(f"   Max MFE: {max_mfe:.2f} pts")

    # ============================================================
    # 4. STOP TYPE ANALYSIS
    # ============================================================
    print(f"\n🛑 STOP TYPE ANALYSIS")
    print("-" * 50)

    c.execute("""
        SELECT
            COALESCE(stop_type, 'UNKNOWN') as stop_type,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(realized_pnl) as total_pnl,
            AVG(realized_pnl) as avg_pnl,
            AVG(stop_points_used) as avg_stop_pts
        FROM valor_closed_trades
        GROUP BY stop_type
        ORDER BY trades DESC
    """)
    rows = c.fetchall()

    for row in rows:
        stop_type, trades, wins, total_pnl, avg_pnl, avg_stop = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"{stop_type}: {trades} trades, Win Rate: {wr:.1f}%, P&L: ${total_pnl:.2f}, Avg: ${avg_pnl:.2f}, Avg Stop: {avg_stop:.1f if avg_stop else 0:.1f}pts")

    # ============================================================
    # 5. CLOSE REASON ANALYSIS
    # ============================================================
    print(f"\n🔍 CLOSE REASON ANALYSIS")
    print("-" * 50)

    c.execute("""
        SELECT
            COALESCE(close_reason, 'UNKNOWN') as close_reason,
            COUNT(*) as count,
            SUM(realized_pnl) as total_pnl,
            AVG(realized_pnl) as avg_pnl
        FROM valor_closed_trades
        GROUP BY close_reason
        ORDER BY count DESC
    """)
    rows = c.fetchall()

    for row in rows:
        reason, count, total_pnl, avg_pnl = row
        print(f"{reason}: {count} trades, P&L: ${total_pnl:.2f}, Avg: ${avg_pnl:.2f}")

    # ============================================================
    # 6. GAMMA REGIME ANALYSIS
    # ============================================================
    print(f"\n🎯 GAMMA REGIME ANALYSIS")
    print("-" * 50)

    c.execute("""
        SELECT
            COALESCE(gamma_regime, 'UNKNOWN') as regime,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(realized_pnl) as total_pnl,
            AVG(realized_pnl) as avg_pnl,
            AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) as avg_win,
            AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END) as avg_loss
        FROM valor_closed_trades
        GROUP BY gamma_regime
        ORDER BY trades DESC
    """)
    rows = c.fetchall()

    for row in rows:
        regime, trades, wins, total_pnl, avg_pnl, avg_win, avg_loss = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"{regime}: {trades} trades, Win Rate: {wr:.1f}%, P&L: ${total_pnl:.2f}")
        print(f"   Avg Win: ${avg_win:.2f if avg_win else 0:.2f}, Avg Loss: ${avg_loss:.2f if avg_loss else 0:.2f}")

    # ============================================================
    # 7. HOLD DURATION ANALYSIS
    # ============================================================
    print(f"\n⏱️  HOLD DURATION ANALYSIS")
    print("-" * 50)

    c.execute("""
        SELECT
            CASE
                WHEN hold_duration_minutes < 5 THEN '< 5 min'
                WHEN hold_duration_minutes < 15 THEN '5-15 min'
                WHEN hold_duration_minutes < 30 THEN '15-30 min'
                WHEN hold_duration_minutes < 60 THEN '30-60 min'
                ELSE '> 60 min'
            END as duration_bucket,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(realized_pnl) as total_pnl
        FROM valor_closed_trades
        WHERE hold_duration_minutes IS NOT NULL
        GROUP BY duration_bucket
        ORDER BY MIN(hold_duration_minutes)
    """)
    rows = c.fetchall()

    for row in rows:
        bucket, trades, wins, total_pnl = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"{bucket}: {trades} trades, Win Rate: {wr:.1f}%, P&L: ${total_pnl:.2f}")

    # ============================================================
    # 8. RECENT LOSING TRADES DETAIL
    # ============================================================
    print(f"\n❌ LAST 15 LOSING TRADES")
    print("-" * 70)

    c.execute("""
        SELECT
            direction,
            gamma_regime,
            realized_pnl,
            mfe_points,
            mae_points,
            close_reason,
            hold_duration_minutes,
            loss_analysis,
            close_time
        FROM valor_closed_trades
        WHERE realized_pnl < 0
        ORDER BY close_time DESC
        LIMIT 15
    """)
    rows = c.fetchall()

    for i, row in enumerate(rows, 1):
        direction, regime, pnl, mfe, mae, reason, duration, analysis, close_time = row
        print(f"{i}. {direction} | {regime} | P&L: ${pnl:.2f} | MFE: {mfe:.1f if mfe else 0:.1f}pts | MAE: {mae:.1f if mae else 0:.1f}pts | {duration or 0}min | {reason}")
        if analysis:
            print(f"   Analysis: {analysis[:100]}...")

    # ============================================================
    # 9. RECOMMENDATIONS
    # ============================================================
    print(f"\n💡 RECOMMENDATIONS")
    print("-" * 50)

    # Calculate key metrics for recommendations
    c.execute("""
        SELECT
            AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) as avg_win,
            AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END) as avg_loss,
            AVG(CASE WHEN realized_pnl < 0 THEN mfe_points END) as loss_mfe,
            COUNT(CASE WHEN realized_pnl < 0 AND mfe_points > 1.5 THEN 1 END) as losses_with_profit
        FROM valor_closed_trades
    """)
    row = c.fetchone()
    avg_win, avg_loss, loss_mfe, losses_with_profit = row

    recommendations = []

    if avg_win and avg_loss and abs(avg_loss) > avg_win * 1.5:
        recommendations.append(f"⚠️  Losses are {abs(avg_loss/avg_win):.1f}x bigger than wins. REDUCE STOP DISTANCE or INCREASE PROFIT TARGET.")

    if loss_mfe and loss_mfe > 1.0:
        recommendations.append(f"⚠️  Losing trades had avg {loss_mfe:.1f}pts profit before reversing. TAKE PROFITS EARLIER (maybe at 1.5pts instead of trailing).")

    if losses_with_profit and losses_with_profit > 5:
        recommendations.append(f"⚠️  {losses_with_profit} losses had 1.5+ pts profit before losing. TRAILING STOP needs to activate sooner.")

    # Get trailing activation data
    c.execute("""
        SELECT
            COUNT(*) as no_trail_losses,
            AVG(mfe_points) as avg_mfe
        FROM valor_closed_trades
        WHERE realized_pnl < 0
        AND stop_type LIKE '%NO_LOSS%'
        AND (mfe_points IS NULL OR mfe_points < 1.5)
    """)
    row = c.fetchone()
    if row and row[0] > 5:
        recommendations.append(f"⚠️  {row[0]} losses never reached trailing activation (1.5pts). Trailing NEVER protected these trades.")

    if not recommendations:
        recommendations.append("✅ No obvious issues detected. May need more data for analysis.")

    for rec in recommendations:
        print(rec)

    conn.close()
    print("\n" + "=" * 70)
    print("Analysis complete!")


if __name__ == "__main__":
    analyze_valor_trades()
