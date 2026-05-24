#!/usr/bin/env python3
"""Tighten SPARK's LIVE (production) stop-loss to -20% — paper account untouched.

Operator decision 2026-05-24: live SPARK runs a conservative -20% stop while the
paper account tests EMBER's wider 1.5x stop. SPARK's exit math:
  stop fires when cost_to_close >= (stop_loss_pct/100) * credit
so a -20% stop (realized loss = 0.2x credit) = cost_to_close 1.2x credit = stop_loss_pct 120.
(Was 130 = -30%.)

Targets ONLY spark_config where account_type='production'. Rolls back if the
'sandbox' (paper) row's stop_loss_pct would change or if the rowcount is unexpected.

    python scripts/spark_set_live_stop.py
"""
import os
import sys

import psycopg2

NEW_SL_PCT = 120.0  # -20% loss -> (1 + 0.2) * 100


def _rows(cur):
    cur.execute(
        """SELECT dte_mode, COALESCE(account_type,'sandbox') AS acct,
                  profit_target_pct, stop_loss_pct
           FROM spark_config ORDER BY dte_mode, acct"""
    )
    return cur.fetchall()


def _show(label, rows):
    print(f"\n{label}")
    print(f"  {'dte':<6}{'account':<12}{'PT%':>7}{'SL_pct':>8}")
    for r in rows:
        print(f"  {r[0]:<6}{r[1]:<12}{float(r[2]):>7.1f}{float(r[3]):>8.1f}")


def main() -> int:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = False
    cur = conn.cursor()

    before = _rows(cur)
    _show("BEFORE", before)
    sbox_before = {(r[0], r[1]): float(r[3]) for r in before if r[1] == "sandbox"}

    cur.execute(
        """UPDATE spark_config
              SET stop_loss_pct = %s, updated_at = NOW()
            WHERE dte_mode = '1DTE'
              AND account_type = 'production'""",
        (NEW_SL_PCT,),
    )
    affected = cur.rowcount
    print(f"\nrows updated (live/production only): {affected}")

    after = _rows(cur)
    sbox_after = {(r[0], r[1]): float(r[3]) for r in after if r[1] == "sandbox"}

    # Safety: exactly one production row touched; no sandbox row changed.
    if affected != 1:
        conn.rollback()
        print(f"ABORTED (rolled back): expected 1 live row, updated {affected}")
        return 1
    if sbox_before != sbox_after:
        conn.rollback()
        print(f"ABORTED (rolled back): sandbox stop changed {sbox_before} -> {sbox_after}")
        return 1

    conn.commit()
    _show("AFTER (committed)", after)
    print("\nDone: SPARK live stop_loss_pct = 120 (-20% loss). Paper unchanged at 250 (+1.5x).")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
