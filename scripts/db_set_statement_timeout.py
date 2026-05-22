#!/usr/bin/env python3
"""One-off admin: set the role-level statement_timeout on alphagex-db.

Replaces the per-connection `options='-c statement_timeout=300000'` GUC that was
removed from the connection pools (for PgBouncer transaction-mode compatibility).
Applies to NEW sessions for alphagex_user. Reversible:

    ALTER ROLE alphagex_user RESET statement_timeout;

Run:  python scripts/db_set_statement_timeout.py
Needs DATABASE_URL in the environment (points at alphagex-db).
"""
import os
import psycopg2

TIMEOUT_MS = "300000"  # 5 minutes, same as the removed session GUC
ROLE = "alphagex_user"


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set")
        return 1

    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"ALTER ROLE {ROLE} SET statement_timeout = '{TIMEOUT_MS}'")
    print(f"ALTER ROLE {ROLE} SET statement_timeout = '{TIMEOUT_MS}'  -> done")
    cur.execute("SELECT rolconfig FROM pg_roles WHERE rolname = %s", (ROLE,))
    print("pg_roles rolconfig:", cur.fetchone()[0])
    conn.close()

    # verify a brand-new session inherits the role default
    v = psycopg2.connect(url)
    vc = v.cursor()
    vc.execute("SHOW statement_timeout")
    print("fresh session statement_timeout ->", vc.fetchone()[0], "(expect 5min)")
    v.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
