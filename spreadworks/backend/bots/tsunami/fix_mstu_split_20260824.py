"""
ONE-SHOT MANUAL REPAIR for the MSTU 1:10 reverse split (2026-08-24).

Supersedes fix_mstu_split_20260824.sql, whose numbers went stale: the engine
sold MSTU again on 2026-09-03 (1.0813 sh @ 36.95, +37.3286 "realized") on
the un-adjusted ghost quantity, so the book was 1.5318 sh @ 2.4206 by the
time anyone ran the repair, not the 2.6131 the SQL expected.

Facts (all read from prod 2026-09-06, alphagex-db):
    2026-08-20  BUY   16.1362 @ 2.4201   (avg_cost 2.4206 after slippage)
    2026-08-24  1:10 reverse split  -> honest holding 1.61362 @ 24.206
    2026-08-25  SELL  13.5231 @ 30.3105  realized +377.0759   (10x too many)
    2026-09-03  SELL   1.0813 @ 36.95    realized  +37.3286   (10x too many)
    book now:   1.5318 sh @ 2.4206;  cash 135.5603;  no SPLIT row for MSTU

Honest values (ratio 0.1, SLIP 0.0002, same formula the engine uses):
    SELL 8/25 -> 1.35231 sh, realized  8.2470
    SELL 9/03 -> 0.10813 sh, realized  1.3772
    book      -> 0.15318 sh @ 24.206
    cash      -> minus 404.7804 phantom proceeds (368.8289 + 35.9514)
                 -> lands at about -269.22. NEGATIVE CASH IS EXPECTED: buys
                 made after 8/24 were funded by the phantom proceeds. The
                 engine's cash gate blocks new BUYs until real proceeds
                 bring it back above zero. No code change needed.
    SPLIT row -> ('MSTU','SPLIT',1.61362,24.206,'split 0.1 on 2026-08-24')
                 timestamped at the split so history reads in order.

Usage (from anywhere, needs psycopg2):
    DATABASE_URL='postgresql://...' python fix_mstu_split_20260824.py           # dry run: checks + plan, no writes
    DATABASE_URL='postgresql://...' python fix_mstu_split_20260824.py --apply   # applies, one transaction

Every precondition must match exactly or the script exits 2 without
touching anything. Every UPDATE must hit exactly one row or it rolls back.
"""
from __future__ import annotations

import os
import sys
from decimal import ROUND_HALF_UP, Decimal as D

import psycopg2

RATIO = D("0.1")
SLIP = D("0.0002")
AVG_PRE = D("2.4206")
AVG_POST = AVG_PRE / RATIO                       # 24.206
SPLIT_TS = "2026-08-24 19:45:00+00"

# what prod must look like right now
EXPECT_BOOK = (D("1.531800"), D("2.4206"))
EXPECT_SELLS = {                                 # date -> (shares, price, realized)
    "2026-08-25": (D("13.523100"), D("30.3105"), D("377.0759")),
    "2026-09-03": (D("1.081300"), D("36.9500"), D("37.3286")),
}


def q4(x: D) -> D:
    return x.quantize(D("0.0001"), ROUND_HALF_UP)


def q6(x: D) -> D:
    return x.quantize(D("0.000001"), ROUND_HALF_UP)


def honest(shares: D, price: D) -> tuple[D, D, D]:
    """(honest shares, honest realized, phantom cash to remove) for a ghost SELL."""
    hs = shares * RATIO
    realized = q4(hs * (price * (1 - SLIP) - AVG_POST))
    phantom_cash = q4((shares - hs) * price * (1 - SLIP))
    return q6(hs), realized, phantom_cash


def main() -> int:
    apply = "--apply" in sys.argv
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL not set", file=sys.stderr)
        return 1

    conn = psycopg2.connect(url)
    conn.autocommit = False
    try:
        cur = conn.cursor()

        # ---- preconditions -------------------------------------------------
        cur.execute("SELECT shares, avg_cost FROM tsunami_trend_book WHERE letf='MSTU'")
        book = cur.fetchone()
        cur.execute(
            "SELECT id, DATE(ts AT TIME ZONE 'America/New_York')::text, shares, price, realized_pnl "
            "FROM tsunami_trend_trades WHERE letf='MSTU' AND side='SELL' AND ts >= '2026-08-24' ORDER BY ts"
        )
        sells = cur.fetchall()
        cur.execute("SELECT count(*) FROM tsunami_trend_trades WHERE letf='MSTU' AND side='SPLIT'")
        split_rows = cur.fetchone()[0]
        cur.execute("SELECT cash FROM tsunami_trend_cash WHERE id=1")
        cash = cur.fetchone()[0]

        problems = []
        if not book or (D(book[0]), D(book[1])) != EXPECT_BOOK:
            problems.append(f"book row is {book}, expected {EXPECT_BOOK}")
        if len(sells) != len(EXPECT_SELLS):
            problems.append(f"{len(sells)} ghost SELL rows, expected {len(EXPECT_SELLS)}: {sells}")
        for _id, d, sh, px, rp in sells:
            exp = EXPECT_SELLS.get(d)
            if not exp or (D(sh), D(px), D(rp)) != exp:
                problems.append(f"SELL {d} is ({sh},{px},{rp}), expected {exp}")
        if split_rows:
            problems.append(f"{split_rows} SPLIT row(s) already exist for MSTU")
        if problems:
            print("PRECONDITIONS FAILED -- nothing written. The engine has traded since this was written; recompute.")
            for p in problems:
                print("  -", p)
            return 2

        # ---- plan ------------------------------------------------------------
        plan = []
        total_phantom = D("0")
        final_shares = q6(D("16.1362") * RATIO)
        for _id, d, sh, px, _rp in sells:
            hs, realized, phantom = honest(D(sh), D(px))
            plan.append((_id, d, hs, realized))
            total_phantom += phantom
            final_shares -= hs
        new_cash = q4(D(cash) - total_phantom)

        print(f"book   : {book[0]} @ {book[1]}  ->  {final_shares} @ {AVG_POST}")
        for _id, d, hs, realized in plan:
            print(f"SELL {d} (id {_id}): shares -> {hs}, realized -> {realized}")
        print(f"cash   : {cash}  ->  {new_cash}   (removing {total_phantom} phantom proceeds)")
        print(f"SPLIT  : insert 1.61362 @ {AVG_POST} at {SPLIT_TS}")
        assert final_shares == q6(D(book[0]) * RATIO), "final shares must equal book/10"

        if not apply:
            print("\nDRY RUN. Re-run with --apply to write.")
            return 0

        # ---- apply -------------------------------------------------------------
        cur.execute(
            "UPDATE tsunami_trend_book SET shares=%s, avg_cost=%s, updated_at=NOW() WHERE letf='MSTU'",
            (final_shares, AVG_POST),
        )
        assert cur.rowcount == 1, f"book update hit {cur.rowcount} rows"
        for _id, d, hs, realized in plan:
            cur.execute(
                "UPDATE tsunami_trend_trades SET shares=%s, realized_pnl=%s WHERE id=%s AND letf='MSTU' AND side='SELL'",
                (hs, realized, _id),
            )
            assert cur.rowcount == 1, f"SELL {d} update hit {cur.rowcount} rows"
        cur.execute("UPDATE tsunami_trend_cash SET cash = cash - %s WHERE id=1", (total_phantom,))
        assert cur.rowcount == 1, f"cash update hit {cur.rowcount} rows"
        cur.execute(
            "INSERT INTO tsunami_trend_trades (ts, letf, side, shares, price, reason, realized_pnl) "
            "VALUES (%s, 'MSTU', 'SPLIT', %s, %s, %s, 0)",
            (SPLIT_TS, q6(D("16.1362") * RATIO), AVG_POST, "split 0.1 on 2026-08-24 (manual repair 2026-09-06)"),
        )
        assert cur.rowcount == 1
        conn.commit()

        cur.execute("SELECT shares, avg_cost FROM tsunami_trend_book WHERE letf='MSTU'")
        print("\nCOMMITTED. book now:", cur.fetchone())
        cur.execute("SELECT cash FROM tsunami_trend_cash WHERE id=1")
        print("cash now:", cur.fetchone()[0])
        return 0
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        print("ROLLED BACK:", e)
        return 3
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
