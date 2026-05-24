#!/usr/bin/env python3
"""Widen SPARK's stop-loss on the PAPER (sandbox) account only — live untouched.

EMBER's faithful-SPARK sweep (2026-05-24) found SPARK's tight stop is the one leak:
on its real trades, widening the stop from ~0.3-0.5x credit to EMBER's 1.5x loss-
multiple roughly doubled the flat-config EV. SPARK's exit math:
  stop fires when cost_to_close >= (stop_loss_pct/100) * credit
so a loss-of-1.5x-credit stop = cost_to_close 2.5x credit = stop_loss_pct 250.

Targets ONLY spark_config where account_type='sandbox' (paper). Rolls back if the
'production' (live) row's stop_loss_pct would change or if the rowcount is unexpected.

    python scripts/spark_set_paper_stop.py
"""
import os
import sys

import psycopg2

NEW_SL_PCT = 250.0  # EMBER 1.5x loss-multiple -> (1 + 1.5) * 100


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
    prod_before = {(r[0], r[1]): float(r[3]) for r in before if r[1] == "production"}

    cur.execute(
        """UPDATE spark_config
              SET stop_loss_pct = %s, updated_at = NOW()
            WHERE dte_mode = '1DTE'
              AND COALESCE(account_type, 'sandbox') = 'sandbox'""",
        (NEW_SL_PCT,),
    )
    affected = cur.rowcount
    print(f"\nrows updated (paper/sandbox only): {affected}")

    after = _rows(cur)
    prod_after = {(r[0], r[1]): float(r[3]) for r in after if r[1] == "production"}

    # Safety: exactly one sandbox row touched; no production row changed.
    if affected != 1:
        conn.rollback()
        print(f"ABORTED (rolled back): expected 1 paper row, updated {affected}")
        return 1
    if prod_before != prod_after:
        conn.rollback()
        print(f"ABORTED (rolled back): production stop changed {prod_before} -> {prod_after}")
        return 1

    conn.commit()
    _show("AFTER (committed)", after)
    print("\nDone: SPARK paper stop_loss_pct = 250 (loss 1.5x credit). Live unchanged at 130.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
