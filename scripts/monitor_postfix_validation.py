#!/usr/bin/env python3
"""
ALPHAGEX POST-FIX MONITORING SCRIPT
====================================
Validates 4-issue bug fix deployment for FORTRESS, FAITH, and GRACE bots.

Fixes being validated:
  Issue #1: FAITH morning execution (stale position blocking)
  Issue #2: FORTRESS balance/buying power check (fail-closed)
  Issue #3: FORTRESS symmetric IC enforcement
  Issue #4: FORTRESS/FAITH/GRACE daily EOD close (no swing trades)

Usage:
  python scripts/monitor_postfix_validation.py                # Auto-detect morning/evening
  python scripts/monitor_postfix_validation.py --morning      # Force morning checks
  python scripts/monitor_postfix_validation.py --evening      # Force evening checks
  python scripts/monitor_postfix_validation.py --all          # Run all checks

Requires:
  DATABASE_URL environment variable
  TRADIER_SANDBOX_API_KEY + TRADIER_SANDBOX_ACCOUNT_ID (for FORTRESS Tradier checks)
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EASTERN_TZ = ZoneInfo("America/New_York")
CENTRAL_TZ = ZoneInfo("America/Chicago")

# ============================================================================
# OUTPUT HELPERS
# ============================================================================

PASS = "\u2705"     # green check
FAIL = "\U0001f534"  # red circle
WARN = "\U0001f7e1"  # yellow circle
NA   = "\u26aa"      # white circle

def header(text):
    print(f"\n{'=' * 70}")
    print(f"  {text}")
    print(f"{'=' * 70}")

def section(text):
    print(f"\n--- {text} ---")

def kv(key, value, indent=2):
    print(f"{' ' * indent}{key:<45} {value}")

def status_line(code, label):
    print(f"\n  STATUS: {code} {label}")


# ============================================================================
# DATABASE HELPERS
# ============================================================================

def get_db_connection():
    """Get database connection or exit with clear error."""
    try:
        from database_adapter import get_connection, is_database_available
        if not is_database_available():
            print(f"{FAIL} DATABASE_URL not set or database unavailable.")
            print("  Set DATABASE_URL and ensure PostgreSQL is reachable.")
            sys.exit(1)
        return get_connection()
    except Exception as e:
        print(f"{FAIL} Database connection failed: {e}")
        sys.exit(1)


def query_one(conn, sql, params=None):
    """Execute query and return one row."""
    c = conn.cursor()
    c.execute(sql, params or ())
    return c.fetchone()


def query_all(conn, sql, params=None):
    """Execute query and return all rows."""
    c = conn.cursor()
    c.execute(sql, params or ())
    return c.fetchall()


def table_exists(conn, table_name):
    """Check if a table exists."""
    row = query_one(conn, """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = %s
        )
    """, (table_name,))
    return row[0] if row else False


# ============================================================================
# TRADIER HELPERS
# ============================================================================

def tradier_sandbox_request(endpoint):
    """Make a request to Tradier sandbox API."""
    import urllib.request
    import json

    api_key = os.getenv('TRADIER_SANDBOX_API_KEY')
    account_id = os.getenv('TRADIER_SANDBOX_ACCOUNT_ID')

    if not api_key or not account_id:
        return None, "TRADIER_SANDBOX_API_KEY or TRADIER_SANDBOX_ACCOUNT_ID not set"

    url = f"https://sandbox.tradier.com/v1/accounts/{account_id}/{endpoint}"
    req = urllib.request.Request(url, headers={
        'Authorization': f'Bearer {api_key}',
        'Accept': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data, None
    except Exception as e:
        return None, str(e)


# ============================================================================
# M1: FAITH Morning Execution
# ============================================================================

def check_m1_faith_morning(conn, today_str):
    section("M1: FAITH Morning Execution")
    now_et = datetime.now(EASTERN_TZ)
    kv("TODAY:", f"{now_et.strftime('%A')}, {today_str}")

    results = {'status': NA, 'label': 'NOT RUN'}

    # FAITH scans (2DTE mode)
    faith_scans = query_all(conn, """
        SELECT timestamp, action, details
        FROM faith_logs
        WHERE dte_mode = '2DTE'
          AND DATE(timestamp AT TIME ZONE 'America/New_York') = %s
          AND action IN ('SCAN', 'HEARTBEAT', 'TRADE', 'SKIP', 'RECOVERY')
        ORDER BY timestamp DESC
        LIMIT 20
    """, (today_str,)) if table_exists(conn, 'faith_logs') else []

    faith_scan_count = len(faith_scans)
    faith_latest = faith_scans[0] if faith_scans else None
    kv("FAITH scan entries today:", f"{faith_scan_count}")
    if faith_latest:
        kv("FAITH latest log:", f"{faith_latest[0].astimezone(EASTERN_TZ).strftime('%H:%M:%S ET')} | {faith_latest[1]} | {str(faith_latest[2])[:80]}")

    # FAITH positions today
    faith_positions = query_all(conn, """
        SELECT position_id, open_time, expiration,
               put_short_strike, put_long_strike,
               call_short_strike, call_long_strike,
               total_credit, status, close_reason
        FROM faith_positions
        WHERE dte_mode = '2DTE'
          AND DATE(open_time AT TIME ZONE 'America/New_York') = %s
        ORDER BY open_time DESC
    """, (today_str,)) if table_exists(conn, 'faith_positions') else []

    faith_traded = len(faith_positions) > 0
    kv("FAITH trade placed:", "YES" if faith_traded else "NO")
    if faith_traded:
        pos = faith_positions[0]
        kv("  Entry time:", pos[1].astimezone(EASTERN_TZ).strftime('%H:%M:%S ET') if pos[1] else 'N/A')
        kv("  Strikes:", f"Put {pos[3]}/{pos[4]} | Call {pos[5]}/{pos[6]}")
        kv("  Expiration:", str(pos[2]))
        kv("  Credit:", f"${pos[7]:.2f}" if pos[7] else 'N/A')

    # GRACE scans
    grace_scans = query_all(conn, """
        SELECT timestamp, action, details
        FROM grace_logs
        WHERE DATE(timestamp AT TIME ZONE 'America/New_York') = %s
          AND action IN ('SCAN', 'HEARTBEAT', 'TRADE', 'SKIP', 'RECOVERY')
        ORDER BY timestamp DESC
        LIMIT 20
    """, (today_str,)) if table_exists(conn, 'grace_logs') else []

    grace_scan_count = len(grace_scans)
    grace_latest = grace_scans[0] if grace_scans else None
    kv("GRACE scan entries today:", f"{grace_scan_count}")
    if grace_latest:
        kv("GRACE latest log:", f"{grace_latest[0].astimezone(EASTERN_TZ).strftime('%H:%M:%S ET')} | {grace_latest[1]} | {str(grace_latest[2])[:80]}")

    # GRACE positions today
    grace_positions = query_all(conn, """
        SELECT position_id, open_time, expiration,
               put_short_strike, put_long_strike,
               call_short_strike, call_long_strike,
               total_credit, status, close_reason
        FROM grace_positions
        WHERE DATE(open_time AT TIME ZONE 'America/New_York') = %s
        ORDER BY open_time DESC
    """, (today_str,)) if table_exists(conn, 'grace_positions') else []

    grace_traded = len(grace_positions) > 0
    kv("GRACE trade placed:", "YES" if grace_traded else "NO")
    if grace_traded:
        pos = grace_positions[0]
        kv("  Entry time:", pos[1].astimezone(EASTERN_TZ).strftime('%H:%M:%S ET') if pos[1] else 'N/A')
        kv("  Strikes:", f"Put {pos[3]}/{pos[4]} | Call {pos[5]}/{pos[6]}")
        kv("  Expiration:", str(pos[2]))

    kv("BOTH TRADED:", "YES" if (faith_traded and grace_traded) else "NO")

    # Determine status
    if faith_traded and grace_traded:
        results = {'status': PASS, 'label': 'PASS — both FAITH and GRACE traded'}
    elif not faith_traded and grace_traded:
        # Check for stale position blocking FAITH
        stale = query_all(conn, """
            SELECT position_id, open_time, expiration, status
            FROM faith_positions
            WHERE dte_mode = '2DTE' AND status = 'open'
        """) if table_exists(conn, 'faith_positions') else []

        if stale:
            kv("STALE POSITIONS FOUND:", f"{len(stale)} open FAITH positions")
            for s in stale:
                kv("  ", f"{s[0]} opened={s[1]} exp={s[2]} status={s[3]}")
            results = {'status': FAIL, 'label': 'REGRESSION — Issue #1 not holding (stale position blocking)'}
        else:
            # Check FAITH skip reasons
            skips = [s for s in faith_scans if s[1] == 'SKIP']
            if skips:
                kv("FAITH skip reasons:", str(skips[0][2])[:120])
            results = {'status': FAIL, 'label': 'REGRESSION — FAITH skipped but GRACE traded (check logs)'}
    elif not faith_traded and not grace_traded:
        if faith_scan_count == 0 and grace_scan_count == 0:
            results = {'status': WARN, 'label': 'NO SCANS — bots may not be running'}
        else:
            results = {'status': WARN, 'label': 'NO SIGNAL — both scanned but found no setup (acceptable)'}
    elif faith_traded and not grace_traded:
        results = {'status': WARN, 'label': 'FAITH traded but GRACE did not (check GRACE logs)'}

    status_line(results['status'], results['label'])
    return results


# ============================================================================
# M2: FORTRESS Balance Check
# ============================================================================

def check_m2_fortress_balance(conn, today_str):
    section("M2: FORTRESS Balance Check")

    results = {'status': NA, 'label': 'NOT RUN'}

    # Check FORTRESS logs for balance check entries
    balance_logs = query_all(conn, """
        SELECT timestamp, action, details
        FROM fortress_logs
        WHERE DATE(timestamp AT TIME ZONE 'America/New_York') = %s
          AND (
              details::text ILIKE '%%buying power%%'
              OR details::text ILIKE '%%balance check%%'
              OR details::text ILIKE '%%BLOCKING trade%%'
              OR action IN ('BALANCE_CHECK', 'ORDER_REJECTED', 'TRADE', 'SKIP')
          )
        ORDER BY timestamp DESC
        LIMIT 20
    """, (today_str,)) if table_exists(conn, 'fortress_logs') else []

    kv("Balance-related log entries:", f"{len(balance_logs)}")
    for log in balance_logs[:5]:
        ts = log[0].astimezone(EASTERN_TZ).strftime('%H:%M:%S ET') if log[0] else '?'
        kv(f"  [{ts}]", f"{log[1]}: {str(log[2])[:80]}")

    # Check for rejected orders
    rejected = [l for l in balance_logs if l[1] == 'ORDER_REJECTED' or 'rejected' in str(l[2]).lower()]
    kv("Orders rejected today:", f"{len(rejected)}")

    # Check Tradier sandbox balance
    tradier_data, tradier_err = tradier_sandbox_request("balances")
    if tradier_err:
        kv("Tradier sandbox balance:", f"UNAVAILABLE ({tradier_err})")
    elif tradier_data:
        balances = tradier_data.get('balances', {})
        kv("Tradier sandbox balance:", f"${balances.get('total_equity', 'N/A')}")
        kv("Tradier sandbox buying power:", f"${balances.get('option_buying_power', 'N/A')}")

    # Check for orders submitted today
    orders_today = query_all(conn, """
        SELECT position_id, open_time, put_order_id, call_order_id, status
        FROM fortress_positions
        WHERE DATE(open_time AT TIME ZONE 'America/New_York') = %s
        ORDER BY open_time DESC
    """, (today_str,)) if table_exists(conn, 'fortress_positions') else []

    kv("Orders submitted today:", f"{len(orders_today)}")

    # Determine status
    if rejected:
        # Check if rejection was due to insufficient funds
        insuf_fund_rejects = [r for r in rejected if 'insufficient' in str(r[2]).lower() or 'buying power' in str(r[2]).lower()]
        if insuf_fund_rejects:
            results = {'status': FAIL, 'label': 'REGRESSION — orders rejected for insufficient funds (balance check bypassed)'}
        else:
            results = {'status': WARN, 'label': f'{len(rejected)} rejected orders — check reasons'}
    elif len(balance_logs) == 0 and len(orders_today) == 0:
        results = {'status': WARN, 'label': 'No balance check logs or trades (bot may not have scanned yet)'}
    elif any('BLOCKING' in str(l[2]) for l in balance_logs):
        results = {'status': PASS, 'label': 'PASS — balance check correctly blocked trade'}
    elif orders_today:
        results = {'status': PASS, 'label': f'PASS — {len(orders_today)} order(s) placed after balance validation'}
    else:
        results = {'status': PASS, 'label': 'PASS — balance check logged, no issues'}

    status_line(results['status'], results['label'])
    return results


# ============================================================================
# M3: FORTRESS Symmetric IC
# ============================================================================

def check_m3_fortress_symmetric(conn, today_str):
    section("M3: FORTRESS Symmetric IC")

    results = {'status': NA, 'label': 'N/A'}

    positions = query_all(conn, """
        SELECT position_id,
               put_short_strike, put_long_strike,
               call_short_strike, call_long_strike,
               spread_width
        FROM fortress_positions
        WHERE DATE(open_time AT TIME ZONE 'America/New_York') = %s
        ORDER BY open_time DESC
    """, (today_str,)) if table_exists(conn, 'fortress_positions') else []

    kv("FORTRESS traded today:", "YES" if positions else "NO")

    if not positions:
        results = {'status': NA, 'label': 'N/A — no trade to validate (check again tomorrow)'}
        status_line(results['status'], results['label'])
        return results

    all_symmetric = True
    for pos in positions:
        pid, ps, pl, cs, cl, sw = pos
        put_width = ps - pl
        call_width = cl - cs
        symmetric = abs(put_width - call_width) < 0.01

        kv(f"  Trade {pid}:", "")
        kv("    Short put:", f"${ps}")
        kv("    Long put:", f"${pl}")
        kv("    Short call:", f"${cs}")
        kv("    Long call:", f"${cl}")
        kv("    Put width:", f"${put_width:.2f}")
        kv("    Call width:", f"${call_width:.2f}")
        kv("    SYMMETRIC:", "YES" if symmetric else f"NO (delta=${abs(put_width - call_width):.2f})")

        if not symmetric:
            all_symmetric = False

    if all_symmetric:
        results = {'status': PASS, 'label': 'PASS — all trades have symmetric wings'}
    else:
        results = {'status': FAIL, 'label': 'REGRESSION — Issue #3 not holding (asymmetric wings found)'}

    status_line(results['status'], results['label'])
    return results


# ============================================================================
# M4: Stale Position Check
# ============================================================================

def check_m4_stale_positions(conn, today_str):
    section("M4: Stale Position Check (previous-day open positions)")

    results = {'status': NA, 'label': 'NOT RUN'}
    any_stale = False

    for bot, table in [('FORTRESS', 'fortress_positions'), ('FAITH', 'faith_positions'), ('GRACE', 'grace_positions')]:
        if not table_exists(conn, table):
            kv(f"{bot} stale positions:", "TABLE NOT FOUND")
            continue

        dte_filter = "AND dte_mode = '2DTE'" if bot == 'FAITH' else ""
        stale = query_all(conn, f"""
            SELECT position_id, open_time, expiration,
                   put_short_strike, call_short_strike, status
            FROM {table}
            WHERE status = 'open'
              AND DATE(open_time AT TIME ZONE 'America/New_York') < %s
              {dte_filter}
            ORDER BY open_time ASC
        """, (today_str,))

        kv(f"{bot} stale open positions:", f"{len(stale)}")
        if stale:
            any_stale = True
            for s in stale:
                open_date = s[1].astimezone(EASTERN_TZ).strftime('%Y-%m-%d %H:%M ET') if s[1] else '?'
                kv(f"  {FAIL}", f"{s[0]} opened={open_date} exp={s[2]} Put={s[3]} Call={s[4]}")

            # Check if stale recovery fired
            log_table = f"{bot.lower()}_logs"
            if table_exists(conn, log_table):
                recovery_logs = query_all(conn, f"""
                    SELECT timestamp, action, details
                    FROM {log_table}
                    WHERE DATE(timestamp AT TIME ZONE 'America/New_York') = %s
                      AND (action = 'RECOVERY' OR details::text ILIKE '%%stale%%' OR details::text ILIKE '%%overnight%%')
                    ORDER BY timestamp DESC
                    LIMIT 5
                """, (today_str,))
                if recovery_logs:
                    kv(f"  Recovery logs found:", f"{len(recovery_logs)}")
                    for rl in recovery_logs:
                        kv(f"    ", f"{rl[1]}: {str(rl[2])[:80]}")
                else:
                    kv(f"  Recovery logs:", "NONE FOUND — stale close logic may not have fired")

    if any_stale:
        results = {'status': FAIL, 'label': 'REGRESSION — stale positions from previous day still open'}
    else:
        results = {'status': PASS, 'label': 'PASS — no stale positions across all bots'}

    status_line(results['status'], results['label'])
    return results


# ============================================================================
# E1: FORTRESS EOD Close
# ============================================================================

def check_e1_fortress_eod(conn, today_str):
    section("E1: FORTRESS EOD Close")

    results = {'status': NA, 'label': 'NOT RUN'}

    # Check open positions (should be 0)
    open_count = query_one(conn, """
        SELECT COUNT(*) FROM fortress_positions WHERE status = 'open'
    """) if table_exists(conn, 'fortress_positions') else (0,)
    open_count = open_count[0] if open_count else 0

    kv("FORTRESS internal open positions:", f"{open_count} {'(MUST be 0)' if open_count > 0 else ''}")

    # Check Tradier sandbox positions
    tradier_data, tradier_err = tradier_sandbox_request("positions")
    if tradier_err:
        kv("Tradier sandbox positions:", f"UNAVAILABLE ({tradier_err})")
    elif tradier_data:
        positions = tradier_data.get('positions', {})
        if positions == 'null' or not positions:
            kv("Tradier sandbox positions:", "0 (clear)")
        else:
            pos_list = positions.get('position', [])
            if not isinstance(pos_list, list):
                pos_list = [pos_list]
            kv("Tradier sandbox positions:", f"{len(pos_list)}")
            for p in pos_list:
                kv(f"  {FAIL}", f"{p.get('symbol', '?')} qty={p.get('quantity', '?')} cost={p.get('cost_basis', '?')}")

    # Check EOD close logs
    eod_logs = query_all(conn, """
        SELECT timestamp, action, details
        FROM fortress_logs
        WHERE DATE(timestamp AT TIME ZONE 'America/New_York') = %s
          AND (
              details::text ILIKE '%%EOD_CLOSE%%'
              OR details::text ILIKE '%%force_close%%'
              OR details::text ILIKE '%%FORTRESS EOD%%'
              OR action IN ('EOD_CLOSE', 'FORCE_CLOSE')
          )
        ORDER BY timestamp DESC
        LIMIT 10
    """, (today_str,)) if table_exists(conn, 'fortress_logs') else []

    kv("EOD close log entries:", f"{len(eod_logs)}")
    for log in eod_logs[:5]:
        ts = log[0].astimezone(EASTERN_TZ).strftime('%H:%M:%S ET') if log[0] else '?'
        kv(f"  [{ts}]", f"{log[1]}: {str(log[2])[:80]}")

    # Check trades closed today with close timestamps
    closed_today = query_all(conn, """
        SELECT position_id, open_time, close_time, close_reason, realized_pnl
        FROM fortress_positions
        WHERE DATE(close_time AT TIME ZONE 'America/New_York') = %s
          AND status IN ('closed', 'expired')
        ORDER BY close_time DESC
    """, (today_str,)) if table_exists(conn, 'fortress_positions') else []

    if closed_today:
        kv("Trades closed today:", f"{len(closed_today)}")
        latest_close = None
        for ct in closed_today:
            close_et = ct[2].astimezone(EASTERN_TZ) if ct[2] else None
            if close_et and (latest_close is None or close_et > latest_close):
                latest_close = close_et
            open_str = ct[1].astimezone(EASTERN_TZ).strftime('%H:%M ET') if ct[1] else '?'
            close_str = close_et.strftime('%H:%M ET') if close_et else '?'
            kv(f"  {ct[0]}:", f"opened {open_str} | closed {close_str} | {ct[3]} | P&L ${ct[4]:.2f}" if ct[4] else f"opened {open_str} | closed {close_str} | {ct[3]}")

        if latest_close:
            kv("LATEST close timestamp:", latest_close.strftime('%H:%M:%S ET'))
            if latest_close.hour >= 16:
                kv(f"  {FAIL}", "AFTER 4:00 PM ET — position held past market close!")

    # Determine status
    if open_count > 0:
        results = {'status': FAIL, 'label': 'CRITICAL — Issue #4 not holding, open positions after market close'}
    elif closed_today:
        latest_et = max(ct[2].astimezone(EASTERN_TZ) for ct in closed_today if ct[2])
        if latest_et.hour >= 16:
            results = {'status': FAIL, 'label': f'CRITICAL — latest close at {latest_et.strftime("%H:%M ET")} (after 4 PM)'}
        else:
            results = {'status': PASS, 'label': f'PASS — all positions closed by {latest_et.strftime("%H:%M ET")}'}
    elif eod_logs:
        results = {'status': PASS, 'label': 'PASS — EOD job fired, no positions to close'}
    else:
        # No trades and no EOD logs
        fortress_any_scans = query_one(conn, """
            SELECT COUNT(*) FROM fortress_logs
            WHERE DATE(timestamp AT TIME ZONE 'America/New_York') = %s
        """, (today_str,)) if table_exists(conn, 'fortress_logs') else (0,)

        if fortress_any_scans and fortress_any_scans[0] > 0:
            results = {'status': WARN, 'label': 'WARN — FORTRESS scanned but no EOD log found'}
        else:
            results = {'status': WARN, 'label': 'WARN — no FORTRESS activity today'}

    status_line(results['status'], results['label'])
    return results


# ============================================================================
# E2: FAITH & GRACE EOD Close
# ============================================================================

def check_e2_faith_grace_eod(conn, today_str):
    section("E2: FAITH & GRACE EOD Close")

    results = {'status': NA, 'label': 'NOT RUN'}
    any_open = False

    for bot, table, log_table, dte_filter in [
        ('FAITH', 'faith_positions', 'faith_logs', "AND dte_mode = '2DTE'"),
        ('GRACE', 'grace_positions', 'grace_logs', ""),
    ]:
        if not table_exists(conn, table):
            kv(f"{bot} open positions:", "TABLE NOT FOUND")
            continue

        open_count = query_one(conn, f"""
            SELECT COUNT(*) FROM {table}
            WHERE status = 'open' {dte_filter}
        """)
        open_count = open_count[0] if open_count else 0
        kv(f"{bot} open positions:", f"{open_count}")

        if open_count > 0:
            any_open = True
            stale = query_all(conn, f"""
                SELECT position_id, open_time, expiration
                FROM {table}
                WHERE status = 'open' {dte_filter}
            """)
            for s in stale:
                open_str = s[1].astimezone(EASTERN_TZ).strftime('%Y-%m-%d %H:%M ET') if s[1] else '?'
                kv(f"  {FAIL}", f"{s[0]} opened={open_str} exp={s[2]}")

        # Check EOD logs
        if table_exists(conn, log_table):
            eod_logs = query_all(conn, f"""
                SELECT timestamp, action, details
                FROM {log_table}
                WHERE DATE(timestamp AT TIME ZONE 'America/New_York') = %s
                  AND (
                      action IN ('EOD_CLOSE', 'FORCE_CLOSE')
                      OR details::text ILIKE '%%eod%%'
                      OR details::text ILIKE '%%force-clos%%'
                  )
                ORDER BY timestamp DESC
                LIMIT 5
            """, (today_str,))
            kv(f"{bot} EOD close fired:", f"{'YES' if eod_logs else 'NO'}")
            if eod_logs:
                ts = eod_logs[0][0].astimezone(EASTERN_TZ).strftime('%H:%M:%S ET')
                kv(f"  Latest EOD log:", f"{ts} | {eod_logs[0][1]}")

    if any_open:
        results = {'status': FAIL, 'label': 'REGRESSION — open positions will block tomorrow (Issue #1 recurrence)'}
    else:
        results = {'status': PASS, 'label': 'PASS — no open positions across FAITH and GRACE'}

    status_line(results['status'], results['label'])
    return results


# ============================================================================
# E3: Entry Cutoff Verification
# ============================================================================

def check_e3_entry_cutoff(conn, today_str):
    section("E3: Entry Cutoff Verification")

    results = {'status': NA, 'label': 'NOT RUN'}
    late_entries = []

    # 3:30 PM ET cutoff
    cutoff_hour = 15
    cutoff_min = 30

    for bot, table, dte_filter in [
        ('FORTRESS', 'fortress_positions', ""),
        ('FAITH', 'faith_positions', "AND dte_mode = '2DTE'"),
        ('GRACE', 'grace_positions', ""),
    ]:
        if not table_exists(conn, table):
            continue

        trades = query_all(conn, f"""
            SELECT position_id, open_time,
                   put_short_strike, call_short_strike
            FROM {table}
            WHERE DATE(open_time AT TIME ZONE 'America/New_York') = %s
              {dte_filter}
            ORDER BY open_time
        """, (today_str,))

        for t in trades:
            if t[1]:
                open_et = t[1].astimezone(EASTERN_TZ)
                if open_et.hour > cutoff_hour or (open_et.hour == cutoff_hour and open_et.minute >= cutoff_min):
                    late_entries.append((bot, t[0], open_et, t[2], t[3]))

    if late_entries:
        kv("Trades opened after 3:30 PM ET:", f"{len(late_entries)}")
        for bot, pid, open_et, ps, cs in late_entries:
            kv(f"  {FAIL}", f"{bot} {pid} at {open_et.strftime('%H:%M:%S ET')} Put={ps} Call={cs}")
        results = {'status': FAIL, 'label': 'REGRESSION — entry cutoff not enforced'}
    else:
        kv("Trades opened after 3:30 PM ET:", "NONE")
        results = {'status': PASS, 'label': 'PASS — all entries within trading window'}

    status_line(results['status'], results['label'])
    return results


# ============================================================================
# E4: Data Integrity Sweep
# ============================================================================

def check_e4_data_integrity(conn, today_str):
    section("E4: Data Integrity Sweep")

    results = {'status': NA, 'label': 'NOT RUN'}
    issues = []

    # Count trades per bot
    for bot, table, dte_filter in [
        ('FORTRESS', 'fortress_positions', ""),
        ('FAITH', 'faith_positions', "AND dte_mode = '2DTE'"),
        ('GRACE', 'grace_positions', ""),
    ]:
        if not table_exists(conn, table):
            kv(f"{bot} trades today:", "TABLE NOT FOUND")
            continue

        count = query_one(conn, f"""
            SELECT COUNT(*) FROM {table}
            WHERE DATE(open_time AT TIME ZONE 'America/New_York') = %s
              {dte_filter}
        """, (today_str,))
        kv(f"{bot} trades today:", count[0] if count else 0)

    # Check for duplicates (same strikes, same 5-min window)
    for bot, table, dte_filter in [
        ('FORTRESS', 'fortress_positions', ""),
        ('FAITH', 'faith_positions', "AND dte_mode = '2DTE'"),
        ('GRACE', 'grace_positions', ""),
    ]:
        if not table_exists(conn, table):
            continue

        dupes = query_all(conn, f"""
            SELECT put_short_strike, call_short_strike, COUNT(*) as cnt
            FROM {table}
            WHERE DATE(open_time AT TIME ZONE 'America/New_York') = %s
              {dte_filter}
            GROUP BY put_short_strike, call_short_strike
            HAVING COUNT(*) > 1
        """, (today_str,))

        if dupes:
            issues.append(f"{bot}: {len(dupes)} duplicate strike combinations")
            for d in dupes:
                kv(f"  {FAIL} {bot} duplicate:", f"Put={d[0]} Call={d[1]} count={d[2]}")

    kv("Duplicate records:", "YES" if issues else "NONE")

    # Check paper account balances
    for bot, table in [('FAITH', 'faith_paper_account'), ('GRACE', 'grace_paper_account')]:
        if not table_exists(conn, table):
            kv(f"{bot} paper balance:", "TABLE NOT FOUND")
            continue

        dte_filter = "WHERE dte_mode = '2DTE'" if bot == 'FAITH' else ""
        account = query_one(conn, f"""
            SELECT current_balance, buying_power
            FROM {table}
            {dte_filter}
            ORDER BY updated_at DESC
            LIMIT 1
        """)

        if account:
            balance, bp = account
            is_ok = balance is not None and bp is not None and balance >= 0
            indicator = "OK" if is_ok else FAIL
            kv(f"{bot} paper balance:", f"${balance:.2f} (BP: ${bp:.2f}) [{indicator}]")
            if not is_ok:
                issues.append(f"{bot} paper balance invalid: ${balance}, BP: ${bp}")
        else:
            kv(f"{bot} paper balance:", "NO ACCOUNT FOUND")

    if issues:
        results = {'status': FAIL, 'label': f'ISSUES FOUND — {"; ".join(issues)}'}
    else:
        results = {'status': PASS, 'label': 'PASS — no data integrity issues'}

    status_line(results['status'], results['label'])
    return results


# ============================================================================
# DAILY SUMMARY
# ============================================================================

def print_summary(today_str, day_name, all_results):
    print(f"\n{'=' * 55}")
    print(f"  ALPHAGEX DAILY MONITORING — {today_str} ({day_name})")
    print(f"{'=' * 55}")

    morning_checks = ['M1', 'M2', 'M3', 'M4']
    evening_checks = ['E1', 'E2', 'E3', 'E4']

    labels = {
        'M1': 'FAITH Morning Execution',
        'M2': 'FORTRESS Balance Check',
        'M3': 'FORTRESS Symmetric IC',
        'M4': 'Stale Position Check',
        'E1': 'FORTRESS EOD Close',
        'E2': 'FAITH & GRACE EOD Close',
        'E3': 'Entry Cutoff',
        'E4': 'Data Integrity',
    }

    print("\n  MORNING CHECKS:")
    for key in morning_checks:
        r = all_results.get(key, {'status': NA, 'label': 'NOT RUN'})
        print(f"    {key}  {labels[key]:<30} {r['status']}")

    print("\n  EVENING CHECKS:")
    for key in evening_checks:
        r = all_results.get(key, {'status': NA, 'label': 'NOT RUN'})
        print(f"    {key}  {labels[key]:<30} {r['status']}")

    # Overall
    has_fail = any(r.get('status') == FAIL for r in all_results.values())
    has_warn = any(r.get('status') == WARN for r in all_results.values())

    if has_fail:
        overall = f"{FAIL} ISSUES FOUND"
    elif has_warn:
        overall = f"{WARN} WARNINGS (review needed)"
    else:
        overall = f"{PASS} ALL CLEAR"

    print(f"\n  OVERALL: {overall}")

    # List issues
    fails = [(k, v) for k, v in all_results.items() if v.get('status') == FAIL]
    if fails:
        print(f"\n  ISSUES REQUIRING ACTION:")
        for key, result in fails:
            print(f"    {FAIL} {key}: {result['label']}")

    print(f"\n{'=' * 55}")
    return not has_fail


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='AlphaGEX Post-Fix Monitoring')
    parser.add_argument('--morning', action='store_true', help='Run morning checks only')
    parser.add_argument('--evening', action='store_true', help='Run evening checks only')
    parser.add_argument('--all', action='store_true', help='Run all checks')
    parser.add_argument('--date', type=str, help='Override date (YYYY-MM-DD format)')
    args = parser.parse_args()

    now_et = datetime.now(EASTERN_TZ)
    today_str = args.date or now_et.strftime('%Y-%m-%d')
    day_name = now_et.strftime('%A')

    # Check for weekend/holiday
    if now_et.weekday() >= 5 and not args.date:
        print(f"\n{WARN} Today is {day_name} — market closed. Skipping checks.")
        print(f"  Use --date YYYY-MM-DD to check a specific trading day.")
        return

    header(f"ALPHAGEX POST-FIX MONITORING — {today_str} ({day_name})")
    print(f"  Current time: {now_et.strftime('%H:%M:%S ET')}")
    print(f"  Branch: claude/fix-trading-bot-issues-ZUAPF")

    # Auto-detect morning vs evening
    run_morning = args.morning or args.all or (not args.evening and now_et.hour < 16)
    run_evening = args.evening or args.all or (not args.morning and now_et.hour >= 16)

    if not run_morning and not run_evening:
        run_morning = True  # Default to morning

    # Connect to database
    conn = get_db_connection()
    all_results = {}

    try:
        if run_morning:
            header("MORNING CHECKS")
            if now_et.hour < 10 and not args.all and not args.morning:
                print(f"  {WARN} Before 10:30 AM ET — morning checks may show incomplete data")

            all_results['M1'] = check_m1_faith_morning(conn, today_str)
            all_results['M2'] = check_m2_fortress_balance(conn, today_str)
            all_results['M3'] = check_m3_fortress_symmetric(conn, today_str)
            all_results['M4'] = check_m4_stale_positions(conn, today_str)

        if run_evening:
            header("EVENING CHECKS")
            if now_et.hour < 16 and not args.all and not args.evening:
                print(f"  {WARN} Before 4:15 PM ET — evening checks may show incomplete data")

            all_results['E1'] = check_e1_fortress_eod(conn, today_str)
            all_results['E2'] = check_e2_faith_grace_eod(conn, today_str)
            all_results['E3'] = check_e3_entry_cutoff(conn, today_str)
            all_results['E4'] = check_e4_data_integrity(conn, today_str)

        # Print summary
        clean = print_summary(today_str, day_name, all_results)

        # Exit code for CI/scripts
        sys.exit(0 if clean else 1)

    finally:
        conn.close()


if __name__ == '__main__':
    main()
