"""
Phase 1: Full Data Audit for Iron Condor Backtesting
Discovers schema, data ranges, options data availability, and gaps.
"""

import os
import sys
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("IC_BACKTEST_DATABASE_URL")
if not DB_URL:
    print("ERROR: IC_BACKTEST_DATABASE_URL not set in .env")
    sys.exit(1)


def run_query(conn, sql: str, desc: str = ""):
    """Run a query and return results as list of dicts."""
    if desc:
        print(f"\n{'='*80}")
        print(f"  {desc}")
        print(f"{'='*80}")
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def print_rows(rows, max_rows=50):
    """Print rows in a readable format."""
    if not rows:
        print("  (no results)")
        return
    for i, row in enumerate(rows[:max_rows]):
        print(f"  {row}")
    if len(rows) > max_rows:
        print(f"  ... and {len(rows) - max_rows} more rows")


def main():
    print("Connecting to AlphaGEX database...")
    conn = psycopg2.connect(DB_URL)
    conn.set_session(readonly=True)
    print("Connected successfully.\n")

    # ─── 1A: Schema Discovery ───────────────────────────────────────────

    # All tables
    tables = run_query(conn, """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name;
    """, "1A.1: ALL TABLES")
    print(f"  Total tables: {len(tables)}")
    for t in tables:
        print(f"    {t['table_schema']}.{t['table_name']}")

    # Row counts
    row_counts = run_query(conn, """
        SELECT schemaname, relname, n_live_tup
        FROM pg_stat_user_tables
        ORDER BY n_live_tup DESC;
    """, "1A.2: ROW COUNTS (top 40)")
    for r in row_counts[:40]:
        print(f"    {r['relname']:50s} {r['n_live_tup']:>12,} rows")

    # Identify tables likely relevant to options/market data
    # Look for tables with keywords: option, chain, strike, gex, gamma, price, ohlc, candle, history, backtest
    relevant_keywords = ['option', 'chain', 'strike', 'gex', 'gamma', 'price',
                         'ohlc', 'candle', 'history', 'backtest', 'spx', 'spy',
                         'iv', 'volatil', 'expir', 'greek', 'delta', 'vix',
                         'chronicle', 'orat']

    print(f"\n{'='*80}")
    print("  TABLES LIKELY RELEVANT TO OPTIONS/MARKET DATA")
    print(f"{'='*80}")

    relevant_tables = []
    for t in tables:
        name_lower = t['table_name'].lower()
        if any(kw in name_lower for kw in relevant_keywords):
            relevant_tables.append(t['table_name'])
            # Find row count
            rc = next((r['n_live_tup'] for r in row_counts if r['relname'] == t['table_name']), '?')
            print(f"    {t['table_name']:50s} {rc:>12} rows")

    # Get columns for relevant tables
    if relevant_tables:
        placeholders = ','.join([f"'{t}'" for t in relevant_tables])
        cols = run_query(conn, f"""
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name IN ({placeholders})
            ORDER BY table_name, ordinal_position;
        """, "1A.3: COLUMNS FOR RELEVANT TABLES")

        current_table = None
        for c in cols:
            if c['table_name'] != current_table:
                current_table = c['table_name']
                print(f"\n  TABLE: {current_table}")
                print(f"  {'Column':<40s} {'Type':<25s} {'Nullable'}")
                print(f"  {'-'*40} {'-'*25} {'-'*8}")
            print(f"  {c['column_name']:<40s} {c['data_type']:<25s} {c['is_nullable']}")

    # Views
    views = run_query(conn, """
        SELECT table_name FROM information_schema.views
        WHERE table_schema = 'public';
    """, "1A.4: VIEWS")
    print_rows(views)

    # Functions
    funcs = run_query(conn, """
        SELECT routine_name, routine_type
        FROM information_schema.routines
        WHERE routine_schema = 'public';
    """, "1A.5: STORED PROCEDURES/FUNCTIONS")
    print_rows(funcs)

    # ─── 1B: Data Range & Coverage ──────────────────────────────────────

    print(f"\n{'='*80}")
    print("  1B: DATA RANGE & COVERAGE AUDIT")
    print(f"{'='*80}")

    # For each relevant table, try to find date columns and get ranges
    for tbl in relevant_tables:
        # Get date/timestamp columns
        date_cols = run_query(conn, f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = '{tbl}'
              AND data_type IN ('date', 'timestamp without time zone', 'timestamp with time zone')
            ORDER BY ordinal_position;
        """)

        if not date_cols:
            continue

        print(f"\n  TABLE: {tbl}")
        for dc in date_cols:
            col = dc['column_name']
            try:
                result = run_query(conn, f"""
                    SELECT MIN("{col}") as min_date,
                           MAX("{col}") as max_date,
                           COUNT(*) as total_rows,
                           COUNT(DISTINCT "{col}"::date) as distinct_days
                    FROM {tbl};
                """)
                r = result[0]
                print(f"    {col}: {r['min_date']} → {r['max_date']}  ({r['total_rows']:,} rows, {r['distinct_days']} distinct days)")
            except Exception as e:
                print(f"    {col}: ERROR - {e}")
                conn.rollback()

    # Check for SPX/SPY in relevant tables
    print(f"\n{'='*80}")
    print("  1B.2: SPX/SPY SYMBOL SEARCH")
    print(f"{'='*80}")

    for tbl in relevant_tables:
        # Find text columns that might contain symbol/ticker
        text_cols = run_query(conn, f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = '{tbl}'
              AND data_type IN ('character varying', 'text', 'character')
            ORDER BY ordinal_position;
        """)

        for tc in text_cols:
            col = tc['column_name']
            try:
                result = run_query(conn, f"""
                    SELECT DISTINCT "{col}"
                    FROM {tbl}
                    WHERE "{col}" ILIKE '%SPX%' OR "{col}" ILIKE '%SPY%' OR "{col}" ILIKE '%spx%'
                    LIMIT 20;
                """)
                if result:
                    vals = [r[col] for r in result]
                    print(f"  {tbl}.{col}: {vals}")
            except Exception as e:
                conn.rollback()

    # Also check all distinct values in symbol/ticker columns
    print(f"\n{'='*80}")
    print("  1B.3: ALL DISTINCT SYMBOLS/TICKERS IN RELEVANT TABLES")
    print(f"{'='*80}")

    for tbl in relevant_tables:
        text_cols = run_query(conn, f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = '{tbl}'
              AND column_name IN ('symbol', 'ticker', 'underlying', 'root', 'root_symbol')
            ORDER BY ordinal_position;
        """)

        for tc in text_cols:
            col = tc['column_name']
            try:
                result = run_query(conn, f"""
                    SELECT DISTINCT "{col}", COUNT(*) as cnt
                    FROM {tbl}
                    GROUP BY "{col}"
                    ORDER BY cnt DESC
                    LIMIT 30;
                """)
                if result:
                    print(f"  {tbl}.{col}:")
                    for r in result:
                        print(f"    {r[col]:>15s}: {r['cnt']:>10,} rows")
            except Exception as e:
                conn.rollback()

    # ─── 1C: Options Data Deep Dive ─────────────────────────────────────

    print(f"\n{'='*80}")
    print("  1C: OPTIONS DATA DEEP DIVE")
    print(f"{'='*80}")

    # Look for tables with strike/expiration columns
    option_tables = run_query(conn, f"""
        SELECT DISTINCT table_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND column_name IN ('strike', 'strike_price', 'expiration', 'expiration_date',
                             'option_type', 'call_put', 'put_call')
        ORDER BY table_name;
    """)

    print(f"  Tables with option-like columns: {[t['table_name'] for t in option_tables]}")

    for ot in option_tables:
        tbl = ot['table_name']
        print(f"\n  --- {tbl} ---")

        # Get full schema
        cols_info = run_query(conn, f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = '{tbl}'
            ORDER BY ordinal_position;
        """)
        print(f"  Columns: {[(c['column_name'], c['data_type']) for c in cols_info]}")

        # Sample rows
        try:
            sample = run_query(conn, f"SELECT * FROM {tbl} LIMIT 5;")
            print(f"  Sample ({len(sample)} rows):")
            for s in sample:
                print(f"    {s}")
        except Exception as e:
            print(f"  Sample error: {e}")
            conn.rollback()

    # ─── Also search for GEX-specific tables ────────────────────────────

    print(f"\n{'='*80}")
    print("  1C.2: GEX DATA TABLES")
    print(f"{'='*80}")

    gex_tables = [t['table_name'] for t in tables if 'gex' in t['table_name'].lower()]
    print(f"  GEX tables found: {gex_tables}")

    for tbl in gex_tables:
        print(f"\n  --- {tbl} ---")
        cols_info = run_query(conn, f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = '{tbl}'
            ORDER BY ordinal_position;
        """)
        for c in cols_info:
            print(f"    {c['column_name']:<40s} {c['data_type']}")

        # Row count and date range
        try:
            date_col_candidates = [c['column_name'] for c in cols_info
                                   if c['data_type'] in ('date', 'timestamp without time zone', 'timestamp with time zone')]
            if date_col_candidates:
                dc = date_col_candidates[0]
                result = run_query(conn, f"""
                    SELECT MIN("{dc}") as min_d, MAX("{dc}") as max_d, COUNT(*) as cnt
                    FROM {tbl};
                """)
                print(f"    Date range ({dc}): {result[0]['min_d']} → {result[0]['max_d']}, {result[0]['cnt']:,} rows")
        except Exception as e:
            print(f"    Date range error: {e}")
            conn.rollback()

    # ─── 1D: Config/API tables ──────────────────────────────────────────

    print(f"\n{'='*80}")
    print("  1D: CONFIG / API / METADATA TABLES")
    print(f"{'='*80}")

    config_tables = [t['table_name'] for t in tables
                     if any(kw in t['table_name'].lower() for kw in ['config', 'api', 'setting', 'meta'])]
    print(f"  Config-like tables: {config_tables}")

    for tbl in config_tables:
        try:
            sample = run_query(conn, f"SELECT * FROM {tbl} LIMIT 5;")
            print(f"\n  {tbl} ({len(sample)} sample rows):")
            for s in sample:
                # Truncate long values
                truncated = {k: (str(v)[:80] + '...' if len(str(v)) > 80 else v) for k, v in s.items()}
                print(f"    {truncated}")
        except Exception as e:
            print(f"  {tbl}: ERROR - {e}")
            conn.rollback()

    # ─── Summary: Tables with significant data ──────────────────────────

    print(f"\n{'='*80}")
    print("  SUMMARY: TABLES WITH >1000 ROWS (sorted by size)")
    print(f"{'='*80}")

    for r in row_counts:
        if r['n_live_tup'] > 1000:
            print(f"    {r['relname']:50s} {r['n_live_tup']:>12,} rows")

    conn.close()
    print("\n\nAudit complete.")


if __name__ == "__main__":
    main()
