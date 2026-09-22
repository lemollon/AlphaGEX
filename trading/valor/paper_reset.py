"""Atomic paper-only reset, with durable archive and lifecycle serialization."""
import json
import math
import uuid


def _ident(name):
    return '"' + name.replace('"', '""') + '"'

TABLES = ('valor_positions', 'valor_closed_trades', 'valor_equity_snapshots',
          'valor_scan_activity', 'valor_signals', 'valor_daily_perf', 'valor_logs',
          'valor_order_intents', 'valor_ml_shadow', 'valor_paper_fills')
PRESERVE = ('valor_paper_account', 'valor_win_tracker', 'valor_ml_config', 'valor_config')


def reset_paper(starting_capital, full_reset=True):
    from .db import db_connection
    if not full_reset or not math.isfinite(starting_capital) or not 1000 <= starting_capital <= 10000000:
        raise ValueError('Only a full, archived paper reset is supported')
    batch = str(uuid.uuid4())
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("SET LOCAL lock_timeout='15s'")
        c.execute("SET LOCAL statement_timeout='120s'")
        c.execute("SELECT pg_advisory_xact_lock(8675309,42)")
        # Scan/log writers do not all use the lifecycle advisory lock. Lock the
        # source tables too, so no row can arrive between archive and deletion.
        available = []
        for table in TABLES + PRESERVE:
            c.execute('SELECT to_regclass(%s)', (table,))
            if c.fetchone()[0] is not None:
                available.append(table)
        c.execute('LOCK TABLE ' + ','.join(available) + ' IN SHARE ROW EXCLUSIVE MODE')
        c.execute("SELECT config_value FROM valor_config WHERE config_key='mode'")
        mode = c.fetchone()
        if mode and str(mode[0]).strip('"') != 'paper':
            raise ValueError('Reset refused: configured mode is not paper')
        c.execute("SELECT COUNT(*) FROM valor_order_intents WHERE state='pending'")
        if c.fetchone()[0]:
            raise ValueError('Reset refused: pending execution intents require reconciliation')
        c.execute("SELECT COUNT(*) FROM valor_positions WHERE status='open' AND (order_id IS NULL OR order_id NOT LIKE 'PAPER-%')")
        if c.fetchone()[0]:
            raise ValueError('Reset refused: an open position is not verified paper')
        c.execute('''CREATE TABLE IF NOT EXISTS valor_paper_reset_batches (
            batch_id TEXT PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            starting_capital NUMERIC NOT NULL, row_counts JSONB NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS valor_paper_archive_rows (
            batch_id TEXT NOT NULL, source_table TEXT NOT NULL, row_data JSONB NOT NULL)''')
        c.execute('CREATE INDEX IF NOT EXISTS valor_archive_batch_idx ON valor_paper_archive_rows(batch_id,source_table)')
        archive_schema = 'valor_archive_' + batch.replace('-', '')
        c.execute('SELECT current_schema()')
        active_schema = c.fetchone()[0]
        # Table moves preserve history without duplicating millions of rows.
        # Refuse dependencies LIKE cannot safely reproduce.
        for table in TABLES:
            if table not in available:
                continue
            c.execute("SELECT COUNT(*) FROM pg_constraint WHERE contype='f' AND (conrelid=to_regclass(%s) OR confrelid=to_regclass(%s))", (table,table))
            if c.fetchone()[0]:
                raise ValueError('Reset refused: foreign-key dependency requires migration')
            c.execute("SELECT COUNT(*) FROM pg_trigger WHERE tgrelid=to_regclass(%s) AND NOT tgisinternal", (table,))
            if c.fetchone()[0]:
                raise ValueError('Reset refused: table trigger requires migration')
        c.execute("SELECT DISTINCT v.oid,n.nspname,v.relname,v.relkind,pg_get_viewdef(v.oid,true) FROM pg_depend d JOIN pg_rewrite r ON r.oid=d.objid JOIN pg_class v ON v.oid=r.ev_class JOIN pg_namespace n ON n.oid=v.relnamespace WHERE d.refobjid IN (SELECT oid FROM pg_class WHERE relnamespace=current_schema()::regnamespace AND relname=ANY(%s)) AND v.relkind IN ('v','m')", (list(TABLES),))
        views = c.fetchall()
        if any(v[3] != 'v' for v in views):
            raise ValueError('Reset refused: materialized view requires migration')
        c.execute('CREATE SCHEMA ' + _ident(archive_schema))
        c.execute('ALTER TABLE valor_paper_reset_batches ADD COLUMN IF NOT EXISTS archive_schema TEXT')
        counts = {}
        for table in TABLES + PRESERVE:
            # Identifiers come exclusively from this module's fixed allowlist.
            c.execute('SELECT to_regclass(%s)', (table,))
            if c.fetchone()[0] is None:
                continue
            if table in TABLES:
                c.execute('SELECT COUNT(*) FROM ' + _ident(table))
                counts[table] = c.fetchone()[0]
                c.execute('ALTER TABLE ' + _ident(table) + ' SET SCHEMA ' + _ident(archive_schema))
                c.execute('CREATE TABLE ' + _ident(active_schema) + '.' + _ident(table) +
                          ' (LIKE ' + _ident(archive_schema) + '.' + _ident(table) + ' INCLUDING ALL)')
            else:
                c.execute(f'INSERT INTO valor_paper_archive_rows SELECT %s,%s,to_jsonb(t) FROM {table} t', (batch, table))
                counts[table] = c.rowcount
        # Keep view OIDs and permissions, but rebind their stored queries to the
        # new active tables. Definitions were captured before moving history.
        for _, schema, name, _, definition in views:
            c.execute('CREATE OR REPLACE VIEW ' + _ident(schema) + '.' + _ident(name) + ' AS ' + definition)
        c.execute('''UPDATE valor_win_tracker SET alpha=1,beta=1,total_trades=0,
            positive_gamma_wins=0,positive_gamma_losses=0,negative_gamma_wins=0,
            negative_gamma_losses=0,updated_at=NOW()''')
        c.execute('DELETE FROM valor_ml_config')
        c.execute('UPDATE valor_paper_account SET is_active=FALSE')
        c.execute('''INSERT INTO valor_paper_account
            (starting_capital,current_balance,cumulative_pnl,margin_available,high_water_mark)
            VALUES (%s,%s,0,%s,%s)''', (starting_capital,)*4)
        for key, value in {'mode':'paper', 'paper_reset_epoch':batch,
                           'paper_round_trip_fee':3.0, 'paper_slippage_ticks':1,
                           'paper_fee_source':'assumed; verify broker statement'}.items():
            c.execute('''INSERT INTO valor_config(config_key,config_value) VALUES (%s,%s)
                ON CONFLICT(config_key) DO UPDATE SET config_value=EXCLUDED.config_value''', (key,json.dumps(value)))
        c.execute('INSERT INTO valor_paper_reset_batches(batch_id,starting_capital,row_counts,archive_schema) VALUES (%s,%s,%s::jsonb,%s)',
                  (batch,starting_capital,json.dumps(counts),archive_schema))
        conn.commit()
    return batch
