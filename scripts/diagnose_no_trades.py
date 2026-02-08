#!/usr/bin/env python3
"""
URGENT DIAGNOSTIC: Why aren't bots trading?
Run this on production to see EXACTLY what's blocking trades.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")

def diagnose():
    print("=" * 80)
    print("TRADE BLOCKING DIAGNOSTIC - LIVE")
    print(f"Time: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 80)

    # 1. Check database connection
    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        print("\n✅ Database connected")
    except Exception as e:
        print(f"\n❌ Database connection failed: {e}")
        return

    today = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")

    # 2. Check OPEN POSITIONS (this blocks new trades!)
    print("\n" + "=" * 60)
    print("🔒 OPEN POSITIONS (blocks new trades if > 0)")
    print("=" * 60)

    for table, bot in [
        ('fortress_ic_positions', 'FORTRESS'),
        ('solomon_directional_positions', 'SOLOMON'),
        ('anchor_ic_positions', 'ANCHOR'),
        ('icarus_directional_positions', 'GIDEON'),
    ]:
        try:
            cursor.execute(f"""
                SELECT position_id, status, entry_time, entry_credit
                FROM {table}
                WHERE status = 'OPEN'
            """)
            rows = cursor.fetchall()
            if rows:
                print(f"\n⚠️  {bot}: {len(rows)} OPEN POSITION(S) - BLOCKING NEW TRADES!")
                for row in rows:
                    print(f"    Position: {row[0]}, Entry: {row[2]}, Credit: ${row[3]:.2f}")
            else:
                print(f"\n✅ {bot}: No open positions")
        except Exception as e:
            print(f"\n❓ {bot}: Could not check ({e})")

    # 3. Check today's trade count
    print("\n" + "=" * 60)
    print("📊 TODAY'S TRADE COUNT")
    print("=" * 60)

    for table, bot, max_trades in [
        ('fortress_ic_positions', 'FORTRESS', 3),
        ('solomon_directional_positions', 'SOLOMON', 5),
        ('anchor_ic_positions', 'ANCHOR', 5),
        ('icarus_directional_positions', 'GIDEON', 8),
    ]:
        try:
            cursor.execute(f"""
                SELECT COUNT(*) FROM {table}
                WHERE DATE(entry_time) = %s
            """, (today,))
            count = cursor.fetchone()[0]
            status = "⚠️ LIMIT REACHED" if count >= max_trades else "✅"
            print(f"  {bot}: {count}/{max_trades} trades today {status}")
        except Exception as e:
            print(f"  {bot}: Could not check ({e})")

    # 4. Check recent scan activity decisions
    print("\n" + "=" * 60)
    print("📋 RECENT SCAN DECISIONS (last 10 per bot)")
    print("=" * 60)

    try:
        cursor.execute("""
            SELECT
                bot_name,
                time_ct,
                outcome,
                decision_summary,
                oracle_win_probability,
                quant_ml_win_probability,
                min_win_probability_threshold
            FROM scan_activity
            WHERE date = %s
            ORDER BY timestamp DESC
            LIMIT 50
        """, (today,))

        rows = cursor.fetchall()
        if rows:
            by_bot = {}
            for row in rows:
                bot = row[0]
                if bot not in by_bot:
                    by_bot[bot] = []
                if len(by_bot[bot]) < 5:
                    by_bot[bot].append(row)

            for bot, scans in by_bot.items():
                print(f"\n  {bot}:")
                for scan in scans:
                    time_ct, outcome, decision, oracle_wp, ml_wp, threshold = scan[1:7]
                    oracle_wp = float(oracle_wp) if oracle_wp else 0
                    ml_wp = float(ml_wp) if ml_wp else 0
                    threshold = float(threshold) if threshold else 0
                    print(f"    {time_ct} | {outcome:10} | Prophet:{oracle_wp:.0%} ML:{ml_wp:.0%} Thresh:{threshold:.0%}")
                    print(f"      → {decision[:70]}")
        else:
            print("  No scan activity found for today")
    except Exception as e:
        print(f"  Could not fetch scan activity: {e}")

    # 5. Check Prophet predictions
    print("\n" + "=" * 60)
    print("🔮 PROPHET PREDICTIONS TODAY")
    print("=" * 60)

    try:
        cursor.execute("""
            SELECT
                bot_name,
                prediction_time,
                advice,
                win_probability,
                confidence,
                reasoning
            FROM prophet_predictions
            WHERE trade_date = %s
            ORDER BY prediction_time DESC
            LIMIT 20
        """, (today,))

        rows = cursor.fetchall()
        if rows:
            for row in rows:
                bot, time, advice, wp, conf, reason = row
                wp = float(wp) if wp else 0
                conf = float(conf) if conf else 0
                print(f"  {bot} @ {time}: {advice} (WinProb:{wp:.0%}, Conf:{conf:.0%})")
                if reason:
                    print(f"    → {reason[:80]}")
        else:
            print("  ⚠️ NO PROPHET PREDICTIONS STORED TODAY")
            print("  This confirms the visibility issue - predictions only stored on trade execution")
    except Exception as e:
        print(f"  Could not fetch prophet predictions: {e}")

    # 6. Summary
    print("\n" + "=" * 80)
    print("DIAGNOSIS COMPLETE")
    print("=" * 80)

    conn.close()

if __name__ == "__main__":
    diagnose()
