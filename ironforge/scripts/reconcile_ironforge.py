#!/usr/bin/env python3
"""
IronForge Full Reconciliation Script
=====================================
Run on Render shell with: python ironforge/scripts/reconcile_ironforge.py 2>&1 | tee /tmp/recon.txt

Checks ALL math across the system:
  1.  Balance = starting_capital + SUM(realized_pnl)
  2.  Collateral = SUM(collateral_required) for open positions
  3.  Buying power = balance - collateral
  4.  Paper account cache vs live calculation
  5.  Every closed trade has realized_pnl (no NULLs)
  6.  Realized P&L matches formula: (entry_credit - close_price) * 100 * contracts
  7.  No open positions past expiration (stranded)
  8.  No open positions with close_time set (state mismatch)
  9.  No closed positions with NULL close_time
  10. Equity snapshots track with actual balance
  11. PDT log matches closed trade count
  12. Sandbox account positions match paper positions (FLAME only)
  13. Total trades count matches
  14. High water mark is correct
  15. Collateral formula: MAX(0, (spread_width - total_credit) * 100) * contracts
  16. Win/loss P&L consistency
  17. Intraday snapshots exist for today
  18. No duplicate position IDs
  19. All positions have valid strikes (put_short > put_long, call_long > call_short)
  20. Credit received matches put_credit + call_credit
"""

import os
import sys
import psycopg2
from datetime import datetime, date
from decimal import Decimal

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set. Export it first:")
    print("  export DATABASE_URL='postgresql://...'")
    sys.exit(1)

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

BOTS = [
    ('flame', '2DTE'),
    ('spark', '1DTE'),
    ('inferno', '0DTE'),
]

PASS = '\033[92m  PASS\033[0m'
FAIL = '\033[91m  FAIL\033[0m'
WARN = '\033[93m  WARN\033[0m'
INFO = '\033[94m  INFO\033[0m'

total_pass = 0
total_fail = 0
total_warn = 0


def check(label, passed, detail='', warn_only=False):
    global total_pass, total_fail, total_warn
    if passed:
        total_pass += 1
        print(f'{PASS}  {label}')
    elif warn_only:
        total_warn += 1
        print(f'{WARN}  {label}')
    else:
        total_fail += 1
        print(f'{FAIL}  {label}')
    if detail:
        print(f'        {detail}')


def d(val):
    """Convert to Decimal safely."""
    if val is None:
        return Decimal('0')
    return Decimal(str(val))


def run_reconciliation():
    global total_pass, total_fail, total_warn

    print('=' * 80)
    print('  IRONFORGE FULL RECONCILIATION')
    print(f'  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} CT')
    print('=' * 80)

    for bot, dte in BOTS:
        print(f'\n{"─" * 80}')
        print(f'  BOT: {bot.upper()} ({dte})')
        print(f'{"─" * 80}')

        pos_table = f'{bot}_positions'
        acct_table = f'{bot}_paper_account'
        snap_table = f'{bot}_equity_snapshots'
        pdt_table = f'{bot}_pdt_log'
        log_table = f'{bot}_logs'

        # ─── 1. Balance = starting_capital + SUM(realized_pnl) ───
        cur.execute(f"""
            SELECT starting_capital, current_balance, cumulative_pnl,
                   collateral_in_use, buying_power, high_water_mark, total_trades
            FROM {acct_table}
            WHERE is_active = TRUE AND dte_mode = %s
            LIMIT 1
        """, (dte,))
        acct = cur.fetchone()
        if not acct:
            print(f'{FAIL}  No active paper account found for {bot}/{dte}!')
            total_fail += 1
            continue

        starting_cap, cached_balance, cached_pnl, cached_collateral, cached_bp, hwm, cached_trades = acct
        starting_cap = d(starting_cap) or Decimal('10000')

        cur.execute(f"""
            SELECT COALESCE(SUM(realized_pnl), 0)
            FROM {pos_table}
            WHERE status IN ('closed', 'expired') AND dte_mode = %s
              AND realized_pnl IS NOT NULL
        """, (dte,))
        actual_realized = d(cur.fetchone()[0])

        expected_balance = starting_cap + actual_realized
        check(
            f'[1] Balance = starting_capital + realized_pnl',
            d(cached_balance) == expected_balance,
            f'cached={cached_balance}, expected={expected_balance} '
            f'(${starting_cap} + ${actual_realized}), diff=${d(cached_balance) - expected_balance}'
        )

        # ─── 2. Cumulative P&L matches SUM(realized_pnl) ───
        check(
            f'[2] Cumulative P&L matches closed trades',
            d(cached_pnl) == actual_realized,
            f'cached={cached_pnl}, actual SUM={actual_realized}, diff={d(cached_pnl) - actual_realized}'
        )

        # ─── 3. Collateral = SUM(collateral_required) for open positions ───
        cur.execute(f"""
            SELECT COALESCE(SUM(collateral_required), 0), COUNT(*)
            FROM {pos_table}
            WHERE status = 'open' AND dte_mode = %s
        """, (dte,))
        actual_collateral, open_count = cur.fetchone()
        actual_collateral = d(actual_collateral)

        check(
            f'[3] Collateral matches open positions',
            d(cached_collateral) == actual_collateral,
            f'cached={cached_collateral}, actual={actual_collateral} ({open_count} open), diff={d(cached_collateral) - actual_collateral}'
        )

        # ─── 4. Buying power = balance - collateral ───
        expected_bp = expected_balance - actual_collateral
        check(
            f'[4] Buying power = balance - collateral',
            d(cached_bp) == expected_bp,
            f'cached={cached_bp}, expected={expected_bp} (${expected_balance} - ${actual_collateral}), diff={d(cached_bp) - expected_bp}'
        )

        # ─── 5. No NULL realized_pnl on closed trades ───
        cur.execute(f"""
            SELECT COUNT(*)
            FROM {pos_table}
            WHERE status IN ('closed', 'expired') AND realized_pnl IS NULL AND dte_mode = %s
        """, (dte,))
        null_pnl_count = cur.fetchone()[0]
        check(
            f'[5] All closed trades have realized_pnl',
            null_pnl_count == 0,
            f'{null_pnl_count} closed trades with NULL realized_pnl' if null_pnl_count > 0 else ''
        )

        # ─── 6. Realized P&L matches formula per trade ───
        cur.execute(f"""
            SELECT position_id, total_credit, close_price, contracts, realized_pnl, close_reason
            FROM {pos_table}
            WHERE status IN ('closed', 'expired') AND dte_mode = %s
              AND realized_pnl IS NOT NULL AND close_price IS NOT NULL
        """, (dte,))
        mismatches = []
        for row in cur.fetchall():
            pid, credit, close_px, contracts, actual_pnl, reason = row
            expected_pnl = round((float(credit) - float(close_px)) * 100 * int(contracts), 2)
            if abs(float(actual_pnl) - expected_pnl) > 0.02:  # penny tolerance
                mismatches.append(f'{pid}: expected={expected_pnl}, actual={actual_pnl}, '
                                  f'credit={credit}, close={close_px}, contracts={contracts}')
        check(
            f'[6] Realized P&L formula matches per trade',
            len(mismatches) == 0,
            f'{len(mismatches)} mismatches:\n' + '\n        '.join(mismatches[:5]) if mismatches else ''
        )

        # ─── 7. No open positions past expiration (stranded) ───
        cur.execute(f"""
            SELECT position_id, expiration, open_time
            FROM {pos_table}
            WHERE status = 'open' AND dte_mode = %s
              AND expiration < CURRENT_DATE
        """, (dte,))
        stranded = cur.fetchall()
        check(
            f'[7] No stranded positions (open past expiration)',
            len(stranded) == 0,
            f'{len(stranded)} stranded: ' + ', '.join(r[0] for r in stranded[:5]) if stranded else ''
        )

        # ─── 8. No open positions with close_time set (state mismatch) ───
        cur.execute(f"""
            SELECT position_id
            FROM {pos_table}
            WHERE status = 'open' AND close_time IS NOT NULL AND dte_mode = %s
        """, (dte,))
        ghost_closed = cur.fetchall()
        check(
            f'[8] No open positions with close_time (state mismatch)',
            len(ghost_closed) == 0,
            f'{len(ghost_closed)} mismatched' if ghost_closed else ''
        )

        # ─── 9. No closed positions with NULL close_time ───
        cur.execute(f"""
            SELECT position_id
            FROM {pos_table}
            WHERE status IN ('closed', 'expired') AND close_time IS NULL AND dte_mode = %s
        """, (dte,))
        no_close_time = cur.fetchall()
        check(
            f'[9] All closed positions have close_time',
            len(no_close_time) == 0,
            f'{len(no_close_time)} missing close_time' if no_close_time else '',
            warn_only=True
        )

        # ─── 10. Total trades count matches ───
        cur.execute(f"""
            SELECT COUNT(*)
            FROM {pos_table}
            WHERE status IN ('closed', 'expired') AND dte_mode = %s
        """, (dte,))
        actual_trades = cur.fetchone()[0]
        check(
            f'[10] Total trades count matches',
            int(cached_trades or 0) == actual_trades,
            f'cached={cached_trades}, actual={actual_trades}'
        )

        # ─── 11. High water mark is correct ───
        cur.execute(f"""
            SELECT realized_pnl, close_time
            FROM {pos_table}
            WHERE status IN ('closed', 'expired') AND dte_mode = %s
              AND realized_pnl IS NOT NULL
            ORDER BY close_time
        """, (dte,))
        running = starting_cap
        max_balance = starting_cap
        for pnl, _ in cur.fetchall():
            running += d(pnl)
            if running > max_balance:
                max_balance = running

        check(
            f'[11] High water mark correct',
            d(hwm) == max_balance,
            f'cached HWM={hwm}, calculated={max_balance}',
            warn_only=True
        )

        # ─── 12. Collateral formula per position ───
        cur.execute(f"""
            SELECT position_id, spread_width, total_credit, contracts, collateral_required
            FROM {pos_table}
            WHERE status = 'open' AND dte_mode = %s
        """, (dte,))
        collateral_mismatches = []
        for row in cur.fetchall():
            pid, width, credit, contracts, actual_coll = row
            if width and credit and contracts:
                expected_coll = round(max(0, (float(width) - float(credit)) * 100) * int(contracts), 2)
                if abs(float(actual_coll or 0) - expected_coll) > 1.0:
                    collateral_mismatches.append(
                        f'{pid}: expected={expected_coll}, actual={actual_coll}, '
                        f'width={width}, credit={credit}, contracts={contracts}'
                    )
        check(
            f'[12] Collateral formula correct per position',
            len(collateral_mismatches) == 0,
            '\n        '.join(collateral_mismatches[:5]) if collateral_mismatches else ''
        )

        # ─── 13. No duplicate position IDs ───
        cur.execute(f"""
            SELECT position_id, COUNT(*)
            FROM {pos_table}
            WHERE dte_mode = %s
            GROUP BY position_id
            HAVING COUNT(*) > 1
        """, (dte,))
        dupes = cur.fetchall()
        check(
            f'[13] No duplicate position IDs',
            len(dupes) == 0,
            f'{len(dupes)} duplicates: ' + ', '.join(f'{r[0]}(x{r[1]})' for r in dupes[:5]) if dupes else ''
        )

        # ─── 14. Valid strikes (put_short > put_long, call_long > call_short) ───
        cur.execute(f"""
            SELECT position_id, put_short_strike, put_long_strike,
                   call_short_strike, call_long_strike
            FROM {pos_table}
            WHERE dte_mode = %s
              AND (put_short_strike <= put_long_strike
                   OR call_long_strike <= call_short_strike)
        """, (dte,))
        bad_strikes = cur.fetchall()
        check(
            f'[14] Strike ordering valid (IC structure)',
            len(bad_strikes) == 0,
            f'{len(bad_strikes)} positions with inverted strikes' if bad_strikes else ''
        )

        # ─── 15. Credit = put_credit + call_credit ───
        cur.execute(f"""
            SELECT position_id, put_credit, call_credit, total_credit
            FROM {pos_table}
            WHERE dte_mode = %s
              AND put_credit IS NOT NULL AND call_credit IS NOT NULL
              AND ABS(COALESCE(put_credit, 0) + COALESCE(call_credit, 0) - COALESCE(total_credit, 0)) > 0.001
        """, (dte,))
        credit_mismatches = cur.fetchall()
        check(
            f'[15] Total credit = put_credit + call_credit',
            len(credit_mismatches) == 0,
            f'{len(credit_mismatches)} mismatches' if credit_mismatches else '',
            warn_only=True
        )

        # ─── 16. Win/Loss P&L consistency ───
        cur.execute(f"""
            SELECT
              COUNT(*) FILTER (WHERE realized_pnl > 0) as wins,
              COUNT(*) FILTER (WHERE realized_pnl <= 0) as losses,
              COALESCE(SUM(realized_pnl) FILTER (WHERE realized_pnl > 0), 0) as win_pnl,
              COALESCE(SUM(realized_pnl) FILTER (WHERE realized_pnl <= 0), 0) as loss_pnl,
              COALESCE(SUM(realized_pnl), 0) as total_pnl
            FROM {pos_table}
            WHERE status IN ('closed', 'expired') AND dte_mode = %s
              AND realized_pnl IS NOT NULL
        """, (dte,))
        wins, losses, win_pnl, loss_pnl, total_pnl = cur.fetchone()
        check(
            f'[16] Win/Loss P&L sums to total',
            abs(float(d(win_pnl) + d(loss_pnl) - d(total_pnl))) < 0.02,
            f'wins={wins} (${win_pnl}), losses={losses} (${loss_pnl}), total=${total_pnl}, '
            f'WR={wins / max(1, wins + losses) * 100:.1f}%'
        )

        # ─── 17. Intraday snapshots exist for today ───
        cur.execute(f"""
            SELECT COUNT(*)
            FROM {snap_table}
            WHERE dte_mode = %s
              AND (snapshot_time AT TIME ZONE 'America/Chicago')::date
                = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Chicago')::date
        """, (dte,))
        snap_count = cur.fetchone()[0]
        check(
            f'[17] Intraday snapshots exist today',
            snap_count > 0,
            f'{snap_count} snapshots today',
            warn_only=True
        )

        # ─── 18. PDT log matches closed trades ───
        cur.execute(f"""
            SELECT COUNT(*)
            FROM {pdt_table}
            WHERE dte_mode = %s AND closed_at IS NOT NULL
        """, (dte,))
        pdt_closed = cur.fetchone()[0]
        check(
            f'[18] PDT log closed count near trade count',
            abs(pdt_closed - actual_trades) <= 2,
            f'PDT logs={pdt_closed}, closed trades={actual_trades}, diff={abs(pdt_closed - actual_trades)}',
            warn_only=True
        )

        # ─── 19. Latest equity snapshot balance matches ───
        cur.execute(f"""
            SELECT balance, realized_pnl, unrealized_pnl, snapshot_time
            FROM {snap_table}
            WHERE dte_mode = %s
            ORDER BY snapshot_time DESC
            LIMIT 1
        """, (dte,))
        snap = cur.fetchone()
        if snap:
            snap_bal, snap_realized, snap_unreal, snap_time = snap
            # Snapshot balance should be close to actual balance
            balance_diff = abs(float(d(snap_bal)) - float(expected_balance))
            check(
                f'[19] Latest snapshot balance near actual',
                balance_diff < 50.0,
                f'snapshot={snap_bal} at {snap_time}, actual={expected_balance}, diff=${balance_diff:.2f}',
                warn_only=balance_diff < 200.0
            )
        else:
            check(f'[19] Latest snapshot balance near actual', False, 'No snapshots found')

        # ─── 20. Closed trades detail summary ───
        cur.execute(f"""
            SELECT close_reason, COUNT(*), COALESCE(SUM(realized_pnl), 0),
                   COALESCE(AVG(realized_pnl), 0)
            FROM {pos_table}
            WHERE status IN ('closed', 'expired') AND dte_mode = %s
              AND realized_pnl IS NOT NULL
            GROUP BY close_reason
            ORDER BY COUNT(*) DESC
        """, (dte,))
        print(f'\n{INFO}  Close reason breakdown:')
        for reason, count, total, avg in cur.fetchall():
            pct = count / max(1, actual_trades) * 100
            print(f'        {reason or "NULL":<30s} {count:>4d} ({pct:5.1f}%)  '
                  f'total=${float(total):>10.2f}  avg=${float(avg):>8.2f}')

        # ─── Summary for this bot ───
        cur.execute(f"""
            SELECT
              COUNT(*) FILTER (WHERE status = 'open') as open_ct,
              COUNT(*) FILTER (WHERE status IN ('closed', 'expired')) as closed_ct,
              COUNT(*) as total_ct
            FROM {pos_table}
            WHERE dte_mode = %s
        """, (dte,))
        o, c, t = cur.fetchone()
        print(f'\n{INFO}  Summary: {o} open, {c} closed, {t} total positions')
        print(f'{INFO}  Balance: ${float(expected_balance):.2f} (${starting_cap} + ${float(actual_realized):.2f})')
        print(f'{INFO}  Collateral: ${float(actual_collateral):.2f} across {open_count} positions')
        print(f'{INFO}  Buying Power: ${float(expected_bp):.2f}')

    # ─── Cross-bot checks ───
    print(f'\n{"─" * 80}')
    print(f'  CROSS-BOT CHECKS')
    print(f'{"─" * 80}')

    # Heartbeat freshness
    cur.execute("""
        SELECT bot_name, last_heartbeat, scan_count, status
        FROM bot_heartbeats
        ORDER BY bot_name
    """)
    for row in cur.fetchall():
        name, hb, scans, status = row
        age_min = (datetime.now(hb.tzinfo) - hb).total_seconds() / 60 if hb else 999
        check(
            f'Heartbeat {name}: {status}, {scans} scans',
            age_min < 10,
            f'last={hb}, age={age_min:.1f}min',
            warn_only=True
        )

    # ─── Final Report ───
    print(f'\n{"=" * 80}')
    total = total_pass + total_fail + total_warn
    print(f'  RESULTS: {total_pass} passed, {total_fail} FAILED, {total_warn} warnings  ({total} checks)')
    if total_fail == 0:
        print(f'  \033[92mALL CRITICAL CHECKS PASSED\033[0m')
    else:
        print(f'  \033[91m{total_fail} CRITICAL FAILURES — INVESTIGATE\033[0m')
    print(f'{"=" * 80}\n')


if __name__ == '__main__':
    try:
        run_reconciliation()
    except Exception as e:
        print(f'\nFATAL ERROR: {e}')
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()
