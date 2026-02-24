#!/usr/bin/env python3
"""
JUBILEE IC Trading Diagnostic — Why aren't trades opening?

Checks every gate in the signal-to-execution pipeline to find
exactly what's blocking new IC trades.

Run on Render shell:
    python3 system_audit/diagnose_jubilee_ic.py
"""

import os
import sys
from datetime import datetime, date


def get_connection():
    try:
        import psycopg2
        return psycopg2.connect(os.environ['DATABASE_URL'])
    except Exception as e:
        print(f"Cannot connect to database: {e}")
        sys.exit(1)


def main():
    print("=" * 60)
    print("  JUBILEE IC TRADING DIAGNOSTIC")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    conn = get_connection()
    cur = conn.cursor()

    # ============================================================
    # GATE 1: Is IC trading enabled?
    # ============================================================
    print("\n--- GATE 1: IC Config ---")
    try:
        cur.execute("""
            SELECT config_data FROM jubilee_ic_config
            ORDER BY updated_at DESC LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            import json
            config = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            print(f"  enabled: {config.get('enabled', 'NOT SET')}")
            print(f"  mode: {config.get('mode', 'NOT SET')}")
            print(f"  starting_capital: ${config.get('starting_capital', 0):,.2f}")
            print(f"  prefer_0dte: {config.get('prefer_0dte', 'NOT SET')}")
            print(f"  max_positions: {config.get('max_positions', 'NOT SET')}")
            print(f"  daily_max_ic_loss: ${config.get('daily_max_ic_loss', 25000):,.2f}")
            print(f"  max_ic_drawdown_pct: {config.get('max_ic_drawdown_pct', 10)}%")
            print(f"  entry_start: {config.get('entry_start', 'NOT SET')}")
            print(f"  entry_end: {config.get('entry_end', 'NOT SET')}")
            print(f"  min_credit: {config.get('min_credit', 'NOT SET')}")
        else:
            print("  No config found in jubilee_ic_config table")
            # Try default config
            print("  Using default JubileeICConfig values")
    except Exception as e:
        print(f"  Config table query failed: {e}")
        conn.rollback()
        # Try without the config table
        print("  Table may not exist - using defaults")

    # ============================================================
    # GATE 2: Safety rails — daily loss
    # ============================================================
    print("\n--- GATE 2: Daily IC Loss Safety Rail ---")
    try:
        cur.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0)
            FROM jubilee_ic_closed_trades
            WHERE DATE(close_time AT TIME ZONE 'America/Chicago') = CURRENT_DATE
        """)
        daily_pnl = float(cur.fetchone()[0])
        daily_max = 25000.0  # Default
        print(f"  Today's realized P&L: ${daily_pnl:,.2f}")
        print(f"  Daily max loss: -${daily_max:,.2f}")
        if daily_pnl < -daily_max:
            print(f"  BLOCKED: Daily loss ${daily_pnl:,.2f} exceeds -${daily_max:,.2f}")
        else:
            print(f"  OK (${daily_max + daily_pnl:,.2f} remaining before halt)")
    except Exception as e:
        print(f"  Query failed: {e}")
        conn.rollback()

    # ============================================================
    # GATE 3: Safety rails — cumulative drawdown
    # ============================================================
    print("\n--- GATE 3: Cumulative Drawdown Safety Rail ---")
    try:
        cur.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0)
            FROM jubilee_ic_closed_trades
        """)
        total_pnl = float(cur.fetchone()[0])

        # Get borrowed capital from box spreads
        cur.execute("""
            SELECT COALESCE(SUM(total_cash_deployed), 0)
            FROM jubilee_positions
            WHERE status IN ('open', 'active')
            AND expiration > CURRENT_DATE
        """)
        borrowed = float(cur.fetchone()[0])
        if borrowed <= 0:
            borrowed = 500000.0  # Paper mode fallback
            print(f"  No active box spreads, using paper fallback: ${borrowed:,.0f}")

        drawdown_pnl = min(0, total_pnl)
        drawdown_pct = abs(drawdown_pnl) / borrowed * 100 if borrowed > 0 else 0
        max_dd_pct = 10.0  # Default

        print(f"  Total realized P&L: ${total_pnl:,.2f}")
        print(f"  Borrowed capital: ${borrowed:,.2f}")
        print(f"  Drawdown: {drawdown_pct:.1f}% (max: {max_dd_pct}%)")
        if drawdown_pct >= max_dd_pct:
            print(f"  BLOCKED: Drawdown {drawdown_pct:.1f}% >= {max_dd_pct}%")
        else:
            print(f"  OK ({max_dd_pct - drawdown_pct:.1f}% remaining before halt)")
    except Exception as e:
        print(f"  Query failed: {e}")
        conn.rollback()

    # ============================================================
    # GATE 4: Box spread funding
    # ============================================================
    print("\n--- GATE 4: Box Spread Funding ---")
    try:
        cur.execute("""
            SELECT position_id, status, total_cash_deployed, expiration,
                   (expiration - CURRENT_DATE) as days_remaining
            FROM jubilee_positions
            WHERE status IN ('open', 'active')
            ORDER BY expiration
        """)
        rows = cur.fetchall()
        if rows:
            for row in rows:
                print(f"  Box {row[0]}: ${row[2]:,.2f}, exp={row[3]}, {row[4]} days left")
            total = sum(r[2] for r in rows if r[2])
            print(f"  Total funded: ${total:,.2f}")
        else:
            print(f"  No open box spreads!")
            print(f"  BLOCKED: IC trading needs box spread capital")
    except Exception as e:
        print(f"  Query failed: {e}")
        conn.rollback()

    # ============================================================
    # GATE 5: Recent signals — WHY are they skipped?
    # ============================================================
    print("\n--- GATE 5: Recent Signals & Skip Reasons ---")
    try:
        cur.execute("""
            SELECT signal_time, total_credit, oracle_confidence,
                   oracle_approved, was_executed, skip_reason,
                   contracts, dte, expiration
            FROM jubilee_ic_signals
            ORDER BY signal_time DESC
            LIMIT 20
        """)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]

        executed_count = 0
        skipped_count = 0
        skip_reasons = {}

        for row in rows:
            data = dict(zip(cols, row))
            if data['was_executed']:
                executed_count += 1
            else:
                skipped_count += 1
                reason = data['skip_reason'] or 'UNKNOWN'
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

        print(f"  Last 20 signals: {executed_count} executed, {skipped_count} skipped")
        if skip_reasons:
            print(f"  Skip reasons:")
            for reason, count in sorted(skip_reasons.items(), key=lambda x: -x[1]):
                print(f"    {reason}: {count}")

        # Show most recent 5 signals with details
        print(f"\n  Last 5 signals:")
        for row in rows[:5]:
            data = dict(zip(cols, row))
            status = "EXEC" if data['was_executed'] else "SKIP"
            print(f"    {data['signal_time']} | ${data['total_credit']:.2f} | "
                  f"Prophet={data['oracle_confidence']:.0%} | {data['dte']}DTE | "
                  f"{data['contracts']}ct | {status}: {data['skip_reason'] or 'OK'}")
    except Exception as e:
        print(f"  Query failed: {e}")
        conn.rollback()

    # ============================================================
    # GATE 6: Open positions (capacity check)
    # ============================================================
    print("\n--- GATE 6: Open Positions ---")
    try:
        cur.execute("""
            SELECT COUNT(*), string_agg(position_id, ', ')
            FROM jubilee_ic_positions
            WHERE status IN ('open', 'pending', 'closing')
        """)
        count, ids = cur.fetchone()
        print(f"  Open positions: {count}")
        if count > 0:
            print(f"  IDs: {ids}")
    except Exception as e:
        print(f"  Query failed: {e}")
        conn.rollback()

    # ============================================================
    # GATE 7: Recent closed trades — the $0.02 mystery
    # ============================================================
    print("\n--- GATE 7: Recent Closed Trades (last 20) ---")
    try:
        cur.execute("""
            SELECT close_time, entry_credit, exit_price, realized_pnl,
                   contracts, dte_at_entry, close_reason, hold_duration_minutes
            FROM jubilee_ic_closed_trades
            ORDER BY close_time DESC
            LIMIT 20
        """)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]

        for row in rows:
            data = dict(zip(cols, row))
            print(f"    {data['close_time']} | entry=${data['entry_credit']:.2f} | "
                  f"exit=${data['exit_price']:.2f} | P&L=${data['realized_pnl']:,.2f} | "
                  f"{data['contracts']}ct | {data['dte_at_entry']}DTE | "
                  f"{data['close_reason']} | {data['hold_duration_minutes']}min")

        # Summary of $0.02 entries
        cur.execute("""
            SELECT COUNT(*), AVG(realized_pnl)
            FROM jubilee_ic_closed_trades
            WHERE entry_credit < 0.05
        """)
        low_credit_count, low_credit_avg_pnl = cur.fetchone()
        if low_credit_count and low_credit_count > 0:
            print(f"\n  Low-credit trades (<$0.05): {low_credit_count}, avg P&L=${low_credit_avg_pnl:,.2f}")
    except Exception as e:
        print(f"  Query failed: {e}")
        conn.rollback()

    # ============================================================
    # GATE 8: Heartbeat status
    # ============================================================
    print("\n--- GATE 8: Heartbeat & Trader Status ---")
    try:
        cur.execute("""
            SELECT message, COUNT(*) as cnt, MAX(log_time) as latest
            FROM jubilee_logs
            WHERE action = 'IC_HEARTBEAT'
            AND log_time > NOW() - INTERVAL '4 hours'
            GROUP BY message
            ORDER BY cnt DESC
        """)
        rows = cur.fetchall()
        if rows:
            for msg, cnt, latest in rows:
                print(f"  {msg}: {cnt}x (latest: {latest})")
        else:
            print(f"  No heartbeats in last 4 hours")
    except Exception as e:
        print(f"  Query failed: {e}")
        conn.rollback()

    # ============================================================
    # SUMMARY
    # ============================================================
    print(f"\n{'=' * 60}")
    print("  DIAGNOSTIC COMPLETE")
    print("  Review each gate above for BLOCKED indicators")
    print("  Most common issue: safety rail triggered by cumulative drawdown")
    print(f"{'=' * 60}")

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
