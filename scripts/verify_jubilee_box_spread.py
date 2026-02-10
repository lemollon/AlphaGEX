#!/usr/bin/env python3
"""
JUBILEE Box Spread Verification & Recovery Script
Run this directly in Render shell to verify and fix Jubilee's box spread position.

Usage (paste into Render shell):
    python scripts/verify_jubilee_box_spread.py
"""

import sys
import os

# Ensure project root is on the path (Render shell may start in /opt/render/project/src)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from datetime import datetime, date, timedelta

print("=" * 70)
print("JUBILEE BOX SPREAD VERIFICATION & RECOVERY")
print("=" * 70)

# ------------------------------------------------------------------
# Step 1: Verify database connectivity
# ------------------------------------------------------------------
print("\n[1/5] Checking database connection...")
try:
    from database_adapter import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    cursor.close()
    print("  OK - Database connected")
except Exception as e:
    print(f"  FAIL - Cannot connect to database: {e}")
    print("  Aborting. Fix DATABASE_URL and retry.")
    sys.exit(1)

# ------------------------------------------------------------------
# Step 2: Check jubilee_positions table exists
# ------------------------------------------------------------------
print("\n[2/5] Checking jubilee_positions table...")
try:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_name = 'jubilee_positions'
    """)
    exists = cursor.fetchone()[0] > 0
    cursor.close()
    if exists:
        print("  OK - Table exists")
    else:
        print("  WARN - Table does not exist yet (will be created)")
except Exception as e:
    print(f"  WARN - Could not check table: {e}")

# ------------------------------------------------------------------
# Step 3: Query all positions (open and closed)
# ------------------------------------------------------------------
print("\n[3/5] Querying all Jubilee positions...")
try:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT position_id, status, contracts, strike_width,
               total_credit_received, expiration, current_dte,
               open_time, close_time, close_reason
        FROM jubilee_positions
        ORDER BY open_time DESC
        LIMIT 20
    """)
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    cursor.close()

    if not rows:
        print("  NO POSITIONS FOUND - Jubilee has never had a box spread")
    else:
        print(f"  Found {len(rows)} position(s):\n")
        open_count = 0
        for row in rows:
            data = dict(zip(columns, row))
            status = data['status']
            pos_id = data['position_id']
            contracts = data['contracts']
            width = data['strike_width']
            credit = data['total_credit_received']
            exp = data['expiration']
            dte = data['current_dte']
            opened = data['open_time']
            closed = data['close_time']
            reason = data['close_reason'] or ''

            # Calculate real DTE
            try:
                exp_date = exp if isinstance(exp, date) else datetime.strptime(str(exp), '%Y-%m-%d').date()
                real_dte = (exp_date - date.today()).days
            except Exception:
                real_dte = dte

            marker = ""
            if status in ('open', 'pending', 'assignment_risk'):
                open_count += 1
                if real_dte <= 0:
                    marker = " ** EXPIRED (DTE <= 0) **"
                elif real_dte <= 30:
                    marker = " ** NEEDS ROLL (DTE <= 30) **"
            elif status == 'closed':
                marker = f" (closed: {reason})"

            notional = (contracts or 0) * (width or 0) * 100
            print(f"  {pos_id}")
            print(f"    Status: {status}{marker}")
            print(f"    Size: {contracts} contracts x ${width} width = ${notional:,.0f} notional")
            print(f"    Credit received: ${credit:,.2f}" if credit else "    Credit: N/A")
            print(f"    Expiration: {exp} (DTE: {real_dte})")
            print(f"    Opened: {opened}")
            if closed:
                print(f"    Closed: {closed}")
            print()

        print(f"  Summary: {open_count} OPEN, {len(rows) - open_count} CLOSED/OTHER")

except Exception as e:
    print(f"  ERROR querying positions: {e}")
    rows = []

# ------------------------------------------------------------------
# Step 4: Check if IC trading has capital
# ------------------------------------------------------------------
print("\n[4/5] Checking IC trading capital availability...")
try:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT position_id, total_cash_deployed, expiration
        FROM jubilee_positions
        WHERE status IN ('open', 'pending', 'assignment_risk')
    """)
    open_rows = cursor.fetchall()
    cursor.close()

    total_capital = 0.0
    viable_positions = 0
    for row in open_rows:
        pos_id, deployed, exp = row
        try:
            exp_date = exp if isinstance(exp, date) else datetime.strptime(str(exp), '%Y-%m-%d').date()
            real_dte = (exp_date - date.today()).days
        except Exception:
            real_dte = -1

        if real_dte > 0:
            total_capital += float(deployed or 0)
            viable_positions += 1

    if viable_positions > 0:
        print(f"  OK - {viable_positions} viable position(s) with ${total_capital:,.2f} capital")
    else:
        print(f"  BLOCKED - No viable box spreads. IC trading has $0 capital.")

except Exception as e:
    print(f"  ERROR: {e}")
    viable_positions = 0
    total_capital = 0

# ------------------------------------------------------------------
# Step 5: Create box spread if missing
# ------------------------------------------------------------------
print("\n[5/5] Recovery: Creating box spread if needed...")
if viable_positions > 0 and total_capital > 0:
    print("  SKIP - Jubilee already has a viable box spread. No action needed.")
else:
    print("  CREATING paper box spread now...")
    try:
        from trading.jubilee.trader import JubileeTrader
        from trading.jubilee.models import JubileeConfig, TradingMode

        config = JubileeConfig(mode=TradingMode.PAPER)
        trader = JubileeTrader(config=config)
        trader._create_emergency_paper_position()

        # Verify it was created
        positions = trader.get_positions()
        if positions:
            pos = positions[0]
            print(f"  SUCCESS - Created box spread:")
            print(f"    Position ID: {pos.get('position_id', 'unknown')}")
            print(f"    Contracts:   {pos.get('contracts', 'N/A')}")
            print(f"    Strike Width: ${pos.get('strike_width', 'N/A')}")
            notional = (pos.get('contracts', 0) or 0) * (pos.get('strike_width', 0) or 0) * 100
            print(f"    Notional:    ${notional:,.0f}")
            print(f"    Credit:      ${pos.get('total_credit_received', 0):,.2f}")
            print(f"    Expiration:  {pos.get('expiration', 'N/A')}")
            print(f"    DTE:         {pos.get('current_dte', 'N/A')}")
            print(f"\n  IC trading is now funded and can start immediately.")
        else:
            print("  FAIL - Position creation returned no results. Check logs.")

    except Exception as e:
        print(f"  FAIL - Could not create box spread: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 70)
print("VERIFICATION COMPLETE")
print("=" * 70)
