/**
 * EMBER's own trade book — a READ-ONLY mirror of REFLEX's reflex_state.json
 * (dev/meltup/ember/run_reflex.py), synced in by reflex_sync.py
 * (POST /api/internal/ember/sync). This is EMBER's own execution record, not
 * a read of the customer's brokerage account: a customer can own more than
 * one reflex position at once, but each row here is one REFLEX
 * symbol|signal_date slot, same idempotency key the bot itself uses
 * (reflex_key() in run_reflex.py).
 *
 * Nothing in this file places, cancels, or closes an order, and nothing here
 * is written by the webapp's own scanner — the only writer is the sync route.
 */
import { query, dbExecute } from './db'

const TRADES_TABLE = 'ember_trades'
const STATUS_TABLE = 'ember_status'

let _tablesReady = false

async function ensureTables(): Promise<void> {
  if (_tablesReady) return
  await dbExecute(
    `CREATE TABLE IF NOT EXISTS ${TRADES_TABLE} (
       id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
       opened_at TIMESTAMPTZ,
       closed_at TIMESTAMPTZ,
       symbol TEXT NOT NULL,
       legs JSONB,
       qty NUMERIC(14,4),
       entry_price NUMERIC(14,4),
       exit_price NUMERIC(14,4),
       pnl NUMERIC(14,2),
       status TEXT NOT NULL DEFAULT 'open',
       source_ref TEXT NOT NULL,
       created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
       updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
       UNIQUE (source_ref)
     )`,
  )
  await dbExecute(
    `CREATE INDEX IF NOT EXISTS idx_ember_trades_opened_at ON ${TRADES_TABLE} (opened_at DESC)`,
  )
  await dbExecute(
    `CREATE TABLE IF NOT EXISTS ${STATUS_TABLE} (
       id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
       state TEXT,
       last_heartbeat TIMESTAMPTZ,
       open_positions JSONB,
       updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
     )`,
  )
  _tablesReady = true
}

export interface EmberTradeUpsert {
  sourceRef: string
  symbol: string
  openedAt?: string | null
  closedAt?: string | null
  legs?: unknown
  qty?: number | null
  entryPrice?: number | null
  exitPrice?: number | null
  pnl?: number | null
  status: string
}

export interface EmberTradeRow {
  id: number
  opened_at: string | null
  closed_at: string | null
  symbol: string
  legs: unknown
  qty: string | null
  entry_price: string | null
  exit_price: string | null
  pnl: string | null
  status: string
  source_ref: string
}

/**
 * Upsert ONE trade by its `source_ref` (REFLEX's own symbol|signal_date key).
 * Idempotent by construction — ON CONFLICT (source_ref) DO UPDATE means
 * calling this twice with the same source_ref and payload never creates a
 * second row; it just re-states the same trade (e.g. open -> closed).
 */
export async function upsertEmberTrade(trade: EmberTradeUpsert): Promise<void> {
  await ensureTables()
  await query(
    `INSERT INTO ${TRADES_TABLE}
       (opened_at, closed_at, symbol, legs, qty, entry_price, exit_price, pnl, status, source_ref)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
     ON CONFLICT (source_ref) DO UPDATE SET
       opened_at = EXCLUDED.opened_at,
       closed_at = EXCLUDED.closed_at,
       symbol = EXCLUDED.symbol,
       legs = EXCLUDED.legs,
       qty = EXCLUDED.qty,
       entry_price = EXCLUDED.entry_price,
       exit_price = EXCLUDED.exit_price,
       pnl = EXCLUDED.pnl,
       status = EXCLUDED.status,
       updated_at = NOW()`,
    [
      trade.openedAt ?? null,
      trade.closedAt ?? null,
      trade.symbol,
      trade.legs !== undefined ? JSON.stringify(trade.legs) : null,
      trade.qty ?? null,
      trade.entryPrice ?? null,
      trade.exitPrice ?? null,
      trade.pnl ?? null,
      trade.status,
      trade.sourceRef,
    ],
  )
}

export async function getEmberTrades(limit = 200): Promise<EmberTradeRow[]> {
  await ensureTables()
  return query<EmberTradeRow>(
    `SELECT id, opened_at::text, closed_at::text, symbol, legs, qty, entry_price, exit_price, pnl, status, source_ref
       FROM ${TRADES_TABLE}
      ORDER BY opened_at DESC NULLS LAST, id DESC
      LIMIT $1`,
    [limit],
  )
}

export interface EmberStatusUpsert {
  state?: string | null
  lastHeartbeat?: string | null
  openPositions?: unknown
}

export interface EmberStatusRow {
  state: string | null
  last_heartbeat: string | null
  open_positions: unknown
}

/** Singleton row (id=1) — REFLEX reports no per-position heartbeat, just its own last sync. */
export async function upsertEmberStatus(status: EmberStatusUpsert): Promise<void> {
  await ensureTables()
  await query(
    `INSERT INTO ${STATUS_TABLE} (id, state, last_heartbeat, open_positions)
     VALUES (1, $1, $2, $3)
     ON CONFLICT (id) DO UPDATE SET
       state = EXCLUDED.state,
       last_heartbeat = EXCLUDED.last_heartbeat,
       open_positions = EXCLUDED.open_positions,
       updated_at = NOW()`,
    [
      status.state ?? null,
      status.lastHeartbeat ?? null,
      status.openPositions !== undefined ? JSON.stringify(status.openPositions) : null,
    ],
  )
}

export async function getEmberStatus(): Promise<EmberStatusRow | null> {
  await ensureTables()
  const rows = await query<EmberStatusRow>(
    `SELECT state, last_heartbeat::text, open_positions FROM ${STATUS_TABLE} WHERE id = 1`,
  )
  return rows[0] ?? null
}
