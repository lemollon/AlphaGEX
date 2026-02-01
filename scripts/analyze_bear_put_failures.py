#!/usr/bin/env python3
"""
BEAR_PUT Deep Dive Analysis - Understanding Why Bear Puts Fail

This script analyzes BEAR_PUT trades in detail to understand:
1. Market conditions when they fail vs succeed
2. Price movement direction after entry
3. Flip point relationship
4. Timing patterns
5. Oracle confidence correlation

Run in Render shell by copying sections.
"""

# =============================================================================
# PART 1: BEAR_PUT OVERVIEW AND SUCCESS PATTERNS
# =============================================================================
PART_1 = '''
import psycopg2
import os

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

print("=" * 70)
print("BEAR_PUT DEEP DIVE ANALYSIS")
print("=" * 70)

# Overall BEAR_PUT stats by bot
print("\\n1. BEAR_PUT OVERVIEW BY BOT")
print("-" * 50)
cur.execute("""
    SELECT
        bot_name,
        COUNT(*) as total,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(100.0 * SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
        ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
        ROUND(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END)::numeric, 2) as avg_win,
        ROUND(AVG(CASE WHEN realized_pnl <= 0 THEN realized_pnl END)::numeric, 2) as avg_loss
    FROM unified_trades
    WHERE bot_name IN ('ATHENA', 'ICARUS')
    AND strategy_type = 'BEAR_PUT_SPREAD'
    AND realized_pnl IS NOT NULL
    GROUP BY bot_name
    ORDER BY bot_name
""")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} trades, {row[2]} wins ({row[3]}% WR)")
    print(f"    Total P&L: ${row[4]}, Avg: ${row[5]}")
    print(f"    Avg Win: ${row[6]}, Avg Loss: ${row[7]}")

# BEAR_PUT wins - what made them work?
print("\\n2. BEAR_PUT WINNING TRADES - WHAT WORKED?")
print("-" * 50)
cur.execute("""
    SELECT
        bot_name,
        entry_time::date as trade_date,
        EXTRACT(DOW FROM entry_time) as day_of_week,
        EXTRACT(HOUR FROM entry_time) as entry_hour,
        entry_price,
        exit_price,
        realized_pnl,
        oracle_confidence,
        oracle_advice,
        notes
    FROM unified_trades
    WHERE bot_name IN ('ATHENA', 'ICARUS')
    AND strategy_type = 'BEAR_PUT_SPREAD'
    AND realized_pnl > 0
    ORDER BY realized_pnl DESC
    LIMIT 20
""")
print("  Top 20 BEAR_PUT Winners:")
for row in cur.fetchall():
    dow = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][int(row[2])]
    conf = row[7] if row[7] else 'N/A'
    print(f"    {row[0]} {row[1]} {dow} {int(row[3])}:00 | P&L: ${row[6]:.0f} | Oracle: {conf}")

conn.close()
print("\\nPart 1 complete.")
'''

# =============================================================================
# PART 2: BEAR_PUT FAILURES - TIMING ANALYSIS
# =============================================================================
PART_2 = '''
import psycopg2
import os

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

print("\\n3. BEAR_PUT FAILURES BY DAY OF WEEK")
print("-" * 50)
cur.execute("""
    SELECT
        CASE EXTRACT(DOW FROM entry_time)
            WHEN 0 THEN 'Sunday'
            WHEN 1 THEN 'Monday'
            WHEN 2 THEN 'Tuesday'
            WHEN 3 THEN 'Wednesday'
            WHEN 4 THEN 'Thursday'
            WHEN 5 THEN 'Friday'
            WHEN 6 THEN 'Saturday'
        END as day_name,
        COUNT(*) as total,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(100.0 * SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl
    FROM unified_trades
    WHERE bot_name IN ('ATHENA', 'ICARUS')
    AND strategy_type = 'BEAR_PUT_SPREAD'
    AND realized_pnl IS NOT NULL
    GROUP BY EXTRACT(DOW FROM entry_time),
             CASE EXTRACT(DOW FROM entry_time)
                WHEN 0 THEN 'Sunday'
                WHEN 1 THEN 'Monday'
                WHEN 2 THEN 'Tuesday'
                WHEN 3 THEN 'Wednesday'
                WHEN 4 THEN 'Thursday'
                WHEN 5 THEN 'Friday'
                WHEN 6 THEN 'Saturday'
             END
    ORDER BY EXTRACT(DOW FROM entry_time)
""")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} trades, {row[2]} wins ({row[3]}% WR), P&L: ${row[4]}")

print("\\n4. BEAR_PUT FAILURES BY HOUR")
print("-" * 50)
cur.execute("""
    SELECT
        EXTRACT(HOUR FROM entry_time) as hour,
        COUNT(*) as total,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(100.0 * SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl
    FROM unified_trades
    WHERE bot_name IN ('ATHENA', 'ICARUS')
    AND strategy_type = 'BEAR_PUT_SPREAD'
    AND realized_pnl IS NOT NULL
    GROUP BY EXTRACT(HOUR FROM entry_time)
    ORDER BY EXTRACT(HOUR FROM entry_time)
""")
for row in cur.fetchall():
    print(f"  {int(row[0])}:00 CT: {row[1]} trades, {row[2]} wins ({row[3]}% WR), P&L: ${row[4]}")

conn.close()
print("\\nPart 2 complete.")
'''

# =============================================================================
# PART 3: BEAR_PUT VS FLIP POINT ANALYSIS
# =============================================================================
PART_3 = '''
import psycopg2
import os
import json

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

print("\\n5. BEAR_PUT: POSITION RELATIVE TO FLIP POINT")
print("-" * 50)
print("  (Checking if BEAR_PUT works better ABOVE or BELOW flip)")

# Get trades with position info from notes
cur.execute("""
    SELECT
        bot_name,
        realized_pnl,
        notes,
        entry_price,
        exit_price
    FROM unified_trades
    WHERE bot_name IN ('ATHENA', 'ICARUS')
    AND strategy_type = 'BEAR_PUT_SPREAD'
    AND realized_pnl IS NOT NULL
    AND notes IS NOT NULL
""")

above_flip = {'wins': 0, 'losses': 0, 'pnl': 0}
below_flip = {'wins': 0, 'losses': 0, 'pnl': 0}
unknown = {'wins': 0, 'losses': 0, 'pnl': 0}

for row in cur.fetchall():
    pnl = float(row[1]) if row[1] else 0
    notes = row[2] or ''

    # Check for position relative to flip
    if 'ABOVE_FLIP' in notes.upper() or 'above flip' in notes.lower():
        if pnl > 0:
            above_flip['wins'] += 1
        else:
            above_flip['losses'] += 1
        above_flip['pnl'] += pnl
    elif 'BELOW_FLIP' in notes.upper() or 'below flip' in notes.lower():
        if pnl > 0:
            below_flip['wins'] += 1
        else:
            below_flip['losses'] += 1
        below_flip['pnl'] += pnl
    else:
        if pnl > 0:
            unknown['wins'] += 1
        else:
            unknown['losses'] += 1
        unknown['pnl'] += pnl

print(f"  ABOVE FLIP + BEAR_PUT:")
total = above_flip['wins'] + above_flip['losses']
if total > 0:
    wr = 100 * above_flip['wins'] / total
    print(f"    {total} trades, {above_flip['wins']} wins ({wr:.1f}% WR), P&L: ${above_flip['pnl']:.0f}")
else:
    print(f"    No trades with explicit ABOVE_FLIP tag")

print(f"  BELOW FLIP + BEAR_PUT:")
total = below_flip['wins'] + below_flip['losses']
if total > 0:
    wr = 100 * below_flip['wins'] / total
    print(f"    {total} trades, {below_flip['wins']} wins ({wr:.1f}% WR), P&L: ${below_flip['pnl']:.0f}")
else:
    print(f"    No trades with explicit BELOW_FLIP tag")

print(f"  UNKNOWN POSITION:")
total = unknown['wins'] + unknown['losses']
if total > 0:
    wr = 100 * unknown['wins'] / total
    print(f"    {total} trades, {unknown['wins']} wins ({wr:.1f}% WR), P&L: ${unknown['pnl']:.0f}")

conn.close()
print("\\nPart 3 complete.")
'''

# =============================================================================
# PART 4: BEAR_PUT ORACLE CONFIDENCE ANALYSIS
# =============================================================================
PART_4 = '''
import psycopg2
import os

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

print("\\n6. BEAR_PUT BY ORACLE CONFIDENCE BUCKET")
print("-" * 50)
print("  (Note: values over 100 are likely stored as 6500 instead of 0.65)")

cur.execute("""
    SELECT
        CASE
            WHEN oracle_confidence IS NULL THEN 'NULL'
            WHEN oracle_confidence > 100 THEN 'BUG (>100)'
            WHEN oracle_confidence >= 70 THEN '70-100%'
            WHEN oracle_confidence >= 60 THEN '60-70%'
            WHEN oracle_confidence >= 50 THEN '50-60%'
            ELSE '<50%'
        END as confidence_bucket,
        COUNT(*) as total,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(100.0 * SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
        ROUND(AVG(oracle_confidence)::numeric, 1) as avg_conf
    FROM unified_trades
    WHERE bot_name IN ('ATHENA', 'ICARUS')
    AND strategy_type = 'BEAR_PUT_SPREAD'
    AND realized_pnl IS NOT NULL
    GROUP BY CASE
            WHEN oracle_confidence IS NULL THEN 'NULL'
            WHEN oracle_confidence > 100 THEN 'BUG (>100)'
            WHEN oracle_confidence >= 70 THEN '70-100%'
            WHEN oracle_confidence >= 60 THEN '60-70%'
            WHEN oracle_confidence >= 50 THEN '50-60%'
            ELSE '<50%'
        END
    ORDER BY avg_conf DESC NULLS LAST
""")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} trades, {row[2]} wins ({row[3]}% WR), P&L: ${row[4]}")

print("\\n7. BEAR_PUT BY ORACLE ADVICE TYPE")
print("-" * 50)
cur.execute("""
    SELECT
        COALESCE(oracle_advice, 'NULL') as advice,
        COUNT(*) as total,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(100.0 * SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl
    FROM unified_trades
    WHERE bot_name IN ('ATHENA', 'ICARUS')
    AND strategy_type = 'BEAR_PUT_SPREAD'
    AND realized_pnl IS NOT NULL
    GROUP BY oracle_advice
    ORDER BY total DESC
""")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} trades, {row[2]} wins ({row[3]}% WR), P&L: ${row[4]}")

conn.close()
print("\\nPart 4 complete.")
'''

# =============================================================================
# PART 5: BEAR_PUT PRICE MOVEMENT ANALYSIS
# =============================================================================
PART_5 = '''
import psycopg2
import os

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

print("\\n8. BEAR_PUT ENTRY vs EXIT PRICE ANALYSIS")
print("-" * 50)
print("  (For a BEAR PUT to win, exit_price > entry_price)")

cur.execute("""
    SELECT
        bot_name,
        CASE
            WHEN exit_price > entry_price * 1.5 THEN 'Big Win (>50%)'
            WHEN exit_price > entry_price * 1.2 THEN 'Med Win (20-50%)'
            WHEN exit_price > entry_price THEN 'Small Win (<20%)'
            WHEN exit_price > entry_price * 0.5 THEN 'Med Loss (>50% left)'
            ELSE 'Max Loss (<50% left)'
        END as outcome_type,
        COUNT(*) as trades,
        ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl
    FROM unified_trades
    WHERE bot_name IN ('ATHENA', 'ICARUS')
    AND strategy_type = 'BEAR_PUT_SPREAD'
    AND realized_pnl IS NOT NULL
    AND entry_price > 0
    AND exit_price IS NOT NULL
    GROUP BY bot_name,
             CASE
                WHEN exit_price > entry_price * 1.5 THEN 'Big Win (>50%)'
                WHEN exit_price > entry_price * 1.2 THEN 'Med Win (20-50%)'
                WHEN exit_price > entry_price THEN 'Small Win (<20%)'
                WHEN exit_price > entry_price * 0.5 THEN 'Med Loss (>50% left)'
                ELSE 'Max Loss (<50% left)'
            END
    ORDER BY bot_name, avg_pnl DESC
""")
current_bot = None
for row in cur.fetchall():
    if row[0] != current_bot:
        current_bot = row[0]
        print(f"\\n  {current_bot}:")
    print(f"    {row[1]}: {row[2]} trades, Avg P&L: ${row[3]}, Total: ${row[4]}")

print("\\n9. BEAR_PUT TIME TO EXIT (Winners vs Losers)")
print("-" * 50)
cur.execute("""
    SELECT
        bot_name,
        CASE WHEN realized_pnl > 0 THEN 'Winner' ELSE 'Loser' END as outcome,
        COUNT(*) as trades,
        ROUND(AVG(EXTRACT(EPOCH FROM (exit_time - entry_time))/60)::numeric, 1) as avg_minutes,
        ROUND(MIN(EXTRACT(EPOCH FROM (exit_time - entry_time))/60)::numeric, 1) as min_minutes,
        ROUND(MAX(EXTRACT(EPOCH FROM (exit_time - entry_time))/60)::numeric, 1) as max_minutes
    FROM unified_trades
    WHERE bot_name IN ('ATHENA', 'ICARUS')
    AND strategy_type = 'BEAR_PUT_SPREAD'
    AND realized_pnl IS NOT NULL
    AND exit_time IS NOT NULL
    AND entry_time IS NOT NULL
    GROUP BY bot_name, CASE WHEN realized_pnl > 0 THEN 'Winner' ELSE 'Loser' END
    ORDER BY bot_name, outcome
""")
for row in cur.fetchall():
    print(f"  {row[0]} {row[1]}: {row[2]} trades, Avg: {row[3]} min, Range: {row[4]}-{row[5]} min")

conn.close()
print("\\nPart 5 complete.")
'''

# =============================================================================
# PART 6: BEAR_PUT VS BULL_CALL COMPARISON
# =============================================================================
PART_6 = '''
import psycopg2
import os

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

print("\\n10. BEAR_PUT vs BULL_CALL SIDE-BY-SIDE")
print("-" * 50)
print("  Why does BULL_CALL work better?")

cur.execute("""
    SELECT
        strategy_type,
        COUNT(*) as total,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(100.0 * SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
        ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
        ROUND(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END)::numeric, 2) as avg_win,
        ROUND(AVG(CASE WHEN realized_pnl <= 0 THEN realized_pnl END)::numeric, 2) as avg_loss
    FROM unified_trades
    WHERE bot_name IN ('ATHENA', 'ICARUS')
    AND strategy_type IN ('BEAR_PUT_SPREAD', 'BULL_CALL_SPREAD')
    AND realized_pnl IS NOT NULL
    GROUP BY strategy_type
""")
for row in cur.fetchall():
    print(f"\\n  {row[0]}:")
    print(f"    Trades: {row[1]}, Wins: {row[2]} ({row[3]}% WR)")
    print(f"    Total P&L: ${row[4]}, Avg: ${row[5]}")
    print(f"    Avg Win: ${row[6]}, Avg Loss: ${row[7]}")
    if row[6] and row[7]:
        rr = abs(row[6] / row[7])
        print(f"    Risk/Reward: {rr:.2f}:1")

print("\\n11. SAME DAY COMPARISON: Days with Both BEAR and BULL")
print("-" * 50)
cur.execute("""
    WITH daily_stats AS (
        SELECT
            entry_time::date as trade_date,
            strategy_type,
            SUM(realized_pnl) as daily_pnl,
            COUNT(*) as trades
        FROM unified_trades
        WHERE bot_name IN ('ATHENA', 'ICARUS')
        AND strategy_type IN ('BEAR_PUT_SPREAD', 'BULL_CALL_SPREAD')
        AND realized_pnl IS NOT NULL
        GROUP BY entry_time::date, strategy_type
    )
    SELECT
        b.trade_date,
        b.trades as bear_trades,
        b.daily_pnl as bear_pnl,
        c.trades as bull_trades,
        c.daily_pnl as bull_pnl
    FROM daily_stats b
    JOIN daily_stats c ON b.trade_date = c.trade_date
    WHERE b.strategy_type = 'BEAR_PUT_SPREAD'
    AND c.strategy_type = 'BULL_CALL_SPREAD'
    ORDER BY b.trade_date DESC
    LIMIT 15
""")
print("  Date       | BEAR trades/P&L    | BULL trades/P&L")
print("  " + "-" * 55)
for row in cur.fetchall():
    print(f"  {row[0]} | {row[1]:>3} trades ${row[2]:>8.0f} | {row[3]:>3} trades ${row[4]:>8.0f}")

conn.close()
print("\\nPart 6 complete.")
'''

# =============================================================================
# PART 7: BEAR_PUT MARKET CONDITION ANALYSIS
# =============================================================================
PART_7 = '''
import psycopg2
import os

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

print("\\n12. BEAR_PUT BY VIX LEVEL AT ENTRY")
print("-" * 50)

# First check if we have VIX data in notes or a separate field
cur.execute("""
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = 'unified_trades'
    AND column_name LIKE '%vix%'
""")
vix_cols = cur.fetchall()
print(f"  VIX columns in unified_trades: {[c[0] for c in vix_cols]}")

# Check notes for VIX info
cur.execute("""
    SELECT notes
    FROM unified_trades
    WHERE bot_name IN ('ATHENA', 'ICARUS')
    AND notes LIKE '%VIX%' OR notes LIKE '%vix%'
    LIMIT 5
""")
samples = cur.fetchall()
if samples:
    print(f"  Sample notes with VIX: {samples[0][0][:200] if samples[0][0] else 'None'}...")

print("\\n13. BEAR_PUT BY RECENT MARKET TREND")
print("-" * 50)
print("  (Checking if BEAR_PUT works better in downtrending markets)")

# Look at consecutive days
cur.execute("""
    WITH daily AS (
        SELECT
            entry_time::date as trade_date,
            strategy_type,
            SUM(realized_pnl) as daily_pnl,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COUNT(*) as trades
        FROM unified_trades
        WHERE bot_name IN ('ATHENA', 'ICARUS')
        AND strategy_type = 'BEAR_PUT_SPREAD'
        AND realized_pnl IS NOT NULL
        GROUP BY entry_time::date, strategy_type
    )
    SELECT
        trade_date,
        trades,
        wins,
        daily_pnl,
        LAG(daily_pnl) OVER (ORDER BY trade_date) as prev_day_pnl
    FROM daily
    ORDER BY trade_date DESC
    LIMIT 20
""")
print("  Recent BEAR_PUT daily performance:")
for row in cur.fetchall():
    streak = ""
    if row[4] is not None:
        if row[3] > 0 and row[4] > 0:
            streak = " (2-day winning)"
        elif row[3] < 0 and row[4] < 0:
            streak = " (2-day losing)"
    print(f"  {row[0]}: {row[1]} trades, {row[2]} wins, P&L: ${row[3]:.0f}{streak}")

conn.close()
print("\\nPart 7 complete.")
'''

# =============================================================================
# PART 8: BEAR_PUT EXIT REASON ANALYSIS
# =============================================================================
PART_8 = '''
import psycopg2
import os

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

print("\\n14. BEAR_PUT EXIT REASONS")
print("-" * 50)

# Check for exit reason in various fields
cur.execute("""
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = 'unified_trades'
    AND (column_name LIKE '%exit%' OR column_name LIKE '%close%' OR column_name LIKE '%reason%')
""")
print(f"  Exit-related columns: {[c[0] for c in cur.fetchall()]}")

# Check notes for exit reasons
cur.execute("""
    SELECT
        CASE
            WHEN notes LIKE '%stop%loss%' OR notes LIKE '%STOP%' THEN 'Stop Loss'
            WHEN notes LIKE '%profit%' OR notes LIKE '%target%' THEN 'Profit Target'
            WHEN notes LIKE '%expire%' OR notes LIKE '%expir%' THEN 'Expiration'
            WHEN notes LIKE '%manual%' THEN 'Manual Close'
            ELSE 'Other/Unknown'
        END as exit_reason,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl
    FROM unified_trades
    WHERE bot_name IN ('ATHENA', 'ICARUS')
    AND strategy_type = 'BEAR_PUT_SPREAD'
    AND realized_pnl IS NOT NULL
    GROUP BY CASE
            WHEN notes LIKE '%stop%loss%' OR notes LIKE '%STOP%' THEN 'Stop Loss'
            WHEN notes LIKE '%profit%' OR notes LIKE '%target%' THEN 'Profit Target'
            WHEN notes LIKE '%expire%' OR notes LIKE '%expir%' THEN 'Expiration'
            WHEN notes LIKE '%manual%' THEN 'Manual Close'
            ELSE 'Other/Unknown'
        END
    ORDER BY trades DESC
""")
for row in cur.fetchall():
    wr = 100 * row[2] / row[1] if row[1] > 0 else 0
    print(f"  {row[0]}: {row[1]} trades, {row[2]} wins ({wr:.1f}%), P&L: ${row[3]}")

print("\\n15. BEAR_PUT NOTES SAMPLE (Recent Losses)")
print("-" * 50)
cur.execute("""
    SELECT
        entry_time,
        realized_pnl,
        notes
    FROM unified_trades
    WHERE bot_name IN ('ATHENA', 'ICARUS')
    AND strategy_type = 'BEAR_PUT_SPREAD'
    AND realized_pnl < 0
    ORDER BY entry_time DESC
    LIMIT 10
""")
for row in cur.fetchall():
    notes = (row[2] or 'No notes')[:150]
    print(f"  {row[0]}: P&L ${row[1]:.0f}")
    print(f"    Notes: {notes}...")
    print()

conn.close()
print("\\nPart 8 complete.")
'''

# =============================================================================
# PART 9: BEAR_PUT SIGNAL QUALITY ANALYSIS
# =============================================================================
PART_9 = '''
import psycopg2
import os

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

print("\\n16. BEAR_PUT: WHEN SIGNAL SAYS BEARISH, IS MARKET ACTUALLY BEARISH?")
print("-" * 50)

# Get signal activity for BEAR_PUT signals
cur.execute("""
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name IN ('athena_scan_activity', 'icarus_scan_activity')
    LIMIT 20
""")
cols = [c[0] for c in cur.fetchall()]
print(f"  Scan activity columns: {cols[:15]}...")

# Look at scan activity around BEAR_PUT trades
cur.execute("""
    SELECT
        'ATHENA' as bot,
        COUNT(*) as scans,
        COUNT(DISTINCT scan_time::date) as days
    FROM athena_scan_activity
    WHERE direction_bias = 'BEARISH'
    UNION ALL
    SELECT
        'ICARUS' as bot,
        COUNT(*) as scans,
        COUNT(DISTINCT scan_time::date) as days
    FROM icarus_scan_activity
    WHERE direction_bias = 'BEARISH'
""")
for row in cur.fetchall():
    print(f"  {row[0]} BEARISH signals: {row[1]} scans over {row[2]} days")

print("\\n17. BEAR_PUT: SIGNAL STRENGTH DISTRIBUTION")
print("-" * 50)
cur.execute("""
    SELECT
        bot_name,
        CASE
            WHEN oracle_confidence IS NULL THEN 'No Oracle'
            WHEN oracle_confidence > 100 THEN 'Bug (>100)'
            WHEN oracle_confidence >= 80 THEN 'Strong (80+)'
            WHEN oracle_confidence >= 65 THEN 'Medium (65-80)'
            ELSE 'Weak (<65)'
        END as signal_strength,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl
    FROM unified_trades
    WHERE bot_name IN ('ATHENA', 'ICARUS')
    AND strategy_type = 'BEAR_PUT_SPREAD'
    AND realized_pnl IS NOT NULL
    GROUP BY bot_name, CASE
            WHEN oracle_confidence IS NULL THEN 'No Oracle'
            WHEN oracle_confidence > 100 THEN 'Bug (>100)'
            WHEN oracle_confidence >= 80 THEN 'Strong (80+)'
            WHEN oracle_confidence >= 65 THEN 'Medium (65-80)'
            ELSE 'Weak (<65)'
        END
    ORDER BY bot_name, signal_strength
""")
current_bot = None
for row in cur.fetchall():
    if row[0] != current_bot:
        current_bot = row[0]
        print(f"\\n  {current_bot}:")
    wr = 100 * row[3] / row[2] if row[2] > 0 else 0
    print(f"    {row[1]}: {row[2]} trades, {row[3]} wins ({wr:.1f}%), P&L: ${row[4]}")

conn.close()
print("\\nPart 9 complete.")
'''

# =============================================================================
# PART 10: FLIP POINT DISTANCE FOR SIZING ANALYSIS
# =============================================================================
PART_10 = '''
import psycopg2
import os

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

print("\\n18. FLIP POINT DISTANCE ANALYSIS (For Position Sizing)")
print("-" * 50)
print("  User asked: Can we play bigger near flip points?")

# Check scan activity for flip distance
cur.execute("""
    SELECT
        a.bot_name,
        CASE WHEN a.flip_distance < 0.5 THEN 'Very Close (<0.5%)'
             WHEN a.flip_distance < 1.0 THEN 'Close (0.5-1%)'
             WHEN a.flip_distance < 2.0 THEN 'Medium (1-2%)'
             ELSE 'Far (>2%)'
        END as distance_bucket,
        COUNT(DISTINCT t.id) as trades,
        SUM(CASE WHEN t.realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(100.0 * SUM(CASE WHEN t.realized_pnl > 0 THEN 1 ELSE 0 END) / NULLIF(COUNT(DISTINCT t.id), 0), 1) as win_pct,
        ROUND(SUM(t.realized_pnl)::numeric, 2) as total_pnl
    FROM (
        SELECT bot_name, scan_time, flip_distance
        FROM athena_scan_activity
        WHERE flip_distance IS NOT NULL
        UNION ALL
        SELECT bot_name, scan_time, flip_distance
        FROM icarus_scan_activity
        WHERE flip_distance IS NOT NULL
    ) a
    JOIN unified_trades t ON a.bot_name = t.bot_name
        AND a.scan_time::date = t.entry_time::date
        AND ABS(EXTRACT(EPOCH FROM (a.scan_time - t.entry_time))) < 300
    WHERE t.realized_pnl IS NOT NULL
    GROUP BY a.bot_name,
             CASE WHEN a.flip_distance < 0.5 THEN 'Very Close (<0.5%)'
                  WHEN a.flip_distance < 1.0 THEN 'Close (0.5-1%)'
                  WHEN a.flip_distance < 2.0 THEN 'Medium (1-2%)'
                  ELSE 'Far (>2%)'
             END
    ORDER BY a.bot_name, distance_bucket
""")
results = cur.fetchall()
if results:
    current_bot = None
    for row in results:
        if row[0] != current_bot:
            current_bot = row[0]
            print(f"\\n  {current_bot}:")
        print(f"    {row[1]}: {row[2]} trades, {row[3]} wins ({row[4]}% WR), P&L: ${row[5]}")
else:
    print("  No flip distance data found in scan activity tables.")
    print("  Trying alternative: checking notes for flip mentions...")

    cur.execute("""
        SELECT
            bot_name,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl
        FROM unified_trades
        WHERE bot_name IN ('ATHENA', 'ICARUS')
        AND notes LIKE '%flip%'
        AND realized_pnl IS NOT NULL
        GROUP BY bot_name
    """)
    for row in cur.fetchall():
        wr = 100 * row[2] / row[1] if row[1] > 0 else 0
        print(f"  {row[0]} (trades mentioning flip): {row[1]} trades, {wr:.1f}% WR, Avg P&L: ${row[3]}")

conn.close()
print("\\nPart 10 complete.")
'''

# =============================================================================
# PRINT ALL PARTS
# =============================================================================
if __name__ == '__main__':
    print("BEAR_PUT DEEP DIVE ANALYSIS SCRIPTS")
    print("=" * 70)
    print("\nCopy each PART into Render shell to run.")
    print("\nParts available:")
    print("  PART 1: Overview and Success Patterns")
    print("  PART 2: Timing Analysis (Day/Hour)")
    print("  PART 3: Flip Point Position Analysis")
    print("  PART 4: Oracle Confidence Analysis")
    print("  PART 5: Price Movement & Time to Exit")
    print("  PART 6: BEAR_PUT vs BULL_CALL Comparison")
    print("  PART 7: Market Condition Analysis")
    print("  PART 8: Exit Reason Analysis")
    print("  PART 9: Signal Quality Analysis")
    print("  PART 10: Flip Point Distance for Sizing")

    print("\n" + "=" * 70)
    print("PART 1:")
    print("=" * 70)
    print(PART_1)

    print("\n" + "=" * 70)
    print("PART 2:")
    print("=" * 70)
    print(PART_2)

    print("\n" + "=" * 70)
    print("PART 3:")
    print("=" * 70)
    print(PART_3)

    print("\n" + "=" * 70)
    print("PART 4:")
    print("=" * 70)
    print(PART_4)

    print("\n" + "=" * 70)
    print("PART 5:")
    print("=" * 70)
    print(PART_5)

    print("\n" + "=" * 70)
    print("PART 6:")
    print("=" * 70)
    print(PART_6)

    print("\n" + "=" * 70)
    print("PART 7:")
    print("=" * 70)
    print(PART_7)

    print("\n" + "=" * 70)
    print("PART 8:")
    print("=" * 70)
    print(PART_8)

    print("\n" + "=" * 70)
    print("PART 9:")
    print("=" * 70)
    print(PART_9)

    print("\n" + "=" * 70)
    print("PART 10:")
    print("=" * 70)
    print(PART_10)
