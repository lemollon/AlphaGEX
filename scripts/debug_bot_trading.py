#!/usr/bin/env python3
"""
Debug Script: Why Are Bots Not Trading?

This script analyzes scan_activity data to identify why bots are scanning
but not executing trades.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from database_adapter import get_connection

CENTRAL_TZ = ZoneInfo("America/Chicago")


def analyze_scan_activity():
    """Analyze recent scan activity to identify blocking conditions."""
    conn = get_connection()
    cursor = conn.cursor()

    today = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")

    print("=" * 80)
    print(f"BOT TRADING DIAGNOSTIC REPORT - {today}")
    print("=" * 80)

    # 1. Get scan counts by bot and outcome
    print("\n📊 SCAN SUMMARY (Last 24 Hours)")
    print("-" * 60)
    cursor.execute("""
        SELECT
            bot_name,
            outcome,
            COUNT(*) as count
        FROM scan_activity
        WHERE date = %s
        GROUP BY bot_name, outcome
        ORDER BY bot_name, outcome
    """, (today,))

    for row in cursor.fetchall():
        print(f"  {row[0]:10} | {row[1]:15} | {row[2]:5} scans")

    # 2. Get the most common decision summaries for NO_TRADE
    print("\n🚫 TOP NO_TRADE REASONS (Last 24 Hours)")
    print("-" * 60)
    cursor.execute("""
        SELECT
            bot_name,
            decision_summary,
            COUNT(*) as count
        FROM scan_activity
        WHERE date = %s
        AND outcome = 'NO_TRADE'
        GROUP BY bot_name, decision_summary
        ORDER BY count DESC
        LIMIT 20
    """, (today,))

    for row in cursor.fetchall():
        print(f"  {row[0]:10} | {row[2]:4}x | {row[1][:60]}")

    # 3. Check win probability distribution
    print("\n📈 WIN PROBABILITY ANALYSIS (NO_TRADE Scans)")
    print("-" * 60)
    cursor.execute("""
        SELECT
            bot_name,
            ROUND(AVG(quant_ml_win_probability)::numeric, 2) as avg_ml_win_prob,
            ROUND(AVG(oracle_win_probability)::numeric, 2) as avg_oracle_win_prob,
            ROUND(AVG(min_win_probability_threshold)::numeric, 2) as avg_threshold,
            COUNT(*) as count
        FROM scan_activity
        WHERE date = %s
        AND outcome = 'NO_TRADE'
        AND (quant_ml_win_probability > 0 OR oracle_win_probability > 0)
        GROUP BY bot_name
        ORDER BY bot_name
    """, (today,))

    results = cursor.fetchall()
    if results:
        for row in results:
            bot_name, ml_prob, oracle_prob, threshold, count = row
            ml_prob = float(ml_prob) if ml_prob else 0
            oracle_prob = float(oracle_prob) if oracle_prob else 0
            threshold = float(threshold) if threshold else 0
            print(f"  {bot_name:10}")
            print(f"    ML Win Prob (avg):     {ml_prob:.1%}")
            print(f"    Oracle Win Prob (avg): {oracle_prob:.1%}")
            print(f"    Min Threshold:         {threshold:.1%}")
            print(f"    Sample size: {count} scans")
            if ml_prob > 0 and threshold > 0:
                if ml_prob < threshold:
                    print(f"    ⚠️ ML Win Prob BELOW threshold by {(threshold - ml_prob):.1%}")
                else:
                    print(f"    ✅ ML Win Prob ABOVE threshold")
    else:
        print("  No win probability data found in NO_TRADE scans")

    # 4. Check if there are any open positions blocking trades
    print("\n🔒 POSITION STATUS")
    print("-" * 60)

    try:
        cursor.execute("""
            SELECT
                'FORTRESS' as bot,
                COUNT(*) as open_positions
            FROM fortress_ic_positions
            WHERE status = 'OPEN'
            UNION ALL
            SELECT
                'SOLOMON' as bot,
                COUNT(*) as open_positions
            FROM solomon_directional_positions
            WHERE status = 'OPEN'
        """)

        for row in cursor.fetchall():
            print(f"  {row[0]:10} | {row[1]} open positions")
            if row[1] > 0:
                print(f"    ⚠️ Open position may be blocking new trades")
    except Exception as e:
        print(f"  Error checking positions: {e}")

    # 5. Check latest scan details
    print("\n📝 LATEST 5 SCANS PER BOT (with decision details)")
    print("-" * 80)

    for bot in ['FORTRESS', 'SOLOMON', 'PEGASUS', 'PHOENIX', 'ATLAS', 'ICARUS']:
        cursor.execute("""
            SELECT
                time_ct,
                outcome,
                decision_summary,
                quant_ml_win_probability,
                oracle_win_probability,
                quant_ml_advice,
                oracle_advice,
                vix,
                gex_regime
            FROM scan_activity
            WHERE bot_name = %s
            AND date = %s
            ORDER BY timestamp DESC
            LIMIT 5
        """, (bot, today))

        rows = cursor.fetchall()
        if rows:
            print(f"\n  {bot}:")
            for row in rows:
                time_ct, outcome, decision, ml_prob, oracle_prob, ml_advice, oracle_advice, vix, gex = row
                ml_prob = float(ml_prob) if ml_prob else 0
                oracle_prob = float(oracle_prob) if oracle_prob else 0
                print(f"    {time_ct} | {outcome:10} | ML:{ml_prob:.1%} | Oracle:{oracle_prob:.1%}")
                print(f"                | ML:{ml_advice or 'N/A':15} | Oracle:{oracle_advice or 'N/A'}")
                print(f"                | {decision[:70]}")

    # 6. Check Oracle/ML model status
    print("\n\n🤖 MODEL STATUS CHECK")
    print("-" * 60)

    # Check if ML models are returning predictions
    cursor.execute("""
        SELECT
            bot_name,
            COUNT(CASE WHEN quant_ml_win_probability > 0 THEN 1 END) as ml_predictions,
            COUNT(CASE WHEN oracle_win_probability > 0 THEN 1 END) as oracle_predictions,
            COUNT(*) as total_scans
        FROM scan_activity
        WHERE date = %s
        GROUP BY bot_name
    """, (today,))

    for row in cursor.fetchall():
        bot, ml_count, oracle_count, total = row
        ml_pct = (ml_count / total * 100) if total > 0 else 0
        oracle_pct = (oracle_count / total * 100) if total > 0 else 0
        print(f"  {bot:10} | ML predicting: {ml_pct:5.1f}% | Oracle predicting: {oracle_pct:5.1f}%")
        if ml_pct < 50:
            print(f"    ⚠️ ML model may not be loaded/trained for {bot}")
        if oracle_pct < 50:
            print(f"    ⚠️ Oracle may not be available for {bot}")

    conn.close()

    print("\n" + "=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    analyze_scan_activity()
