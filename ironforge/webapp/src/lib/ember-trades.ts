/**
 * EMBER's own trade book — a READ-ONLY mirror of its execution sleeves'
 * local state: REFLEX (dev/meltup/ember/run_reflex.py), and — as of the
 * shared-sleeve build (BUILD_SPEC_SHARED_SLEEVE.md) — CINDER and TALON too,
 * synced in by reflex_sync.py and its siblings (POST /api/internal/ember/sync).
 * This is EMBER's own execution record, not a read of the customer's
 * brokerage account: a customer can own more than one position at once, but
 * each row here is one bot's symbol|signal_date slot, same idempotency key
 * the bot itself uses (e.g. reflex_key() in run_reflex.py).
 *
 * The `strategy` column (reflex | cinder | talon) distinguishes which sleeve
 * produced a row — see upsertEmberTrade's doc comment for the default when a
 * caller omits it, and getEmberEquityCurve/getEmberTrades for how reads use it.
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
       strategy TEXT NOT NULL DEFAULT 'reflex',
       source_ref TEXT NOT NULL,
       created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
       updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
       UNIQUE (source_ref)
     )`,
  )
  // Migration for deploys where ember_trades pre-dates the shared-sleeve
  // build (today's reflex-only rows all default to 'reflex' — correct,
  // since reflex was the only writer until CINDER/TALON came online).
  await dbExecute(
    `ALTER TABLE ${TRADES_TABLE} ADD COLUMN IF NOT EXISTS strategy TEXT NOT NULL DEFAULT 'reflex'`,
  )
  await dbExecute(
    `CREATE INDEX IF NOT EXISTS idx_ember_trades_opened_at ON ${TRADES_TABLE} (opened_at DESC)`,
  )
  await dbExecute(
    `CREATE INDEX IF NOT EXISTS idx_ember_trades_strategy ON ${TRADES_TABLE} (strategy)`,
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

/** Which sleeve produced the trade — see BUILD_SPEC_SHARED_SLEEVE.md Part 3. */
export type EmberStrategy = 'reflex' | 'cinder' | 'talon'

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
  /** Defaults to 'reflex' when omitted — REFLEX was ember_trades' only writer
   *  before CINDER/TALON existed, and reflex_sync.py's own payload may not
   *  send this field yet even after this column ships. */
  strategy?: string | null
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
  strategy: string
  source_ref: string
}

/**
 * Upsert ONE trade by its `source_ref` (each sleeve's own symbol|signal_date
 * key). Idempotent by construction — ON CONFLICT (source_ref) DO UPDATE
 * means calling this twice with the same source_ref and payload never
 * creates a second row; it just re-states the same trade (e.g. open -> closed).
 */
export async function upsertEmberTrade(trade: EmberTradeUpsert): Promise<void> {
  await ensureTables()
  await query(
    `INSERT INTO ${TRADES_TABLE}
       (opened_at, closed_at, symbol, legs, qty, entry_price, exit_price, pnl, status, strategy, source_ref)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
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
       strategy = EXCLUDED.strategy,
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
      trade.strategy ?? 'reflex',
      trade.sourceRef,
    ],
  )
}

/** `strategy` filters to one sleeve (reflex | cinder | talon); omitted or
 *  undefined returns the combined book across all three. */
export async function getEmberTrades(limit = 200, strategy?: string): Promise<EmberTradeRow[]> {
  await ensureTables()
  if (strategy) {
    return query<EmberTradeRow>(
      `SELECT id, opened_at::text, closed_at::text, symbol, legs, qty, entry_price, exit_price, pnl, status, strategy, source_ref
         FROM ${TRADES_TABLE}
        WHERE strategy = $1
        ORDER BY opened_at DESC NULLS LAST, id DESC
        LIMIT $2`,
      [strategy, limit],
    )
  }
  return query<EmberTradeRow>(
    `SELECT id, opened_at::text, closed_at::text, symbol, legs, qty, entry_price, exit_price, pnl, status, strategy, source_ref
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

export type EmberEquityPeriod = 'day' | 'week' | 'month' | 'year' | 'all'

export interface EmberEquityPoint {
  timestamp: string
  cumulative_pnl: number
}

export interface EmberEquityCurve {
  points: EmberEquityPoint[]
  period_pnl: number | null
}

/** Same wall-clock-via-toLocaleString trick pt-tiers.ts' getCTNow() uses —
 *  only ever compared for calendar-day equality below, never treated as a
 *  precise UTC instant, so the lack of a timezone library is fine here. */
function ctDateKey(iso: string): string {
  const ct = new Date(new Date(iso).toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  return `${ct.getFullYear()}-${ct.getMonth()}-${ct.getDate()}`
}

/** Rolling cutoff window (week/month/year) or the full history (all) — same
 *  shape as api/live/equity-curve/route.ts's period filter, rebased onto
 *  cumulative realized P&L instead of an account balance (Ember has none —
 *  see this file's header comment and the API route's). Never returns a
 *  single dot: an empty window just returns no points, and the UI shows the
 *  honest "no closed trades yet" state instead of a fabricated flat line. */
function windowedCurve(full: EmberEquityPoint[], cutoffMs: number | null): EmberEquityCurve {
  if (cutoffMs == null) {
    return { points: full, period_pnl: full[full.length - 1].cumulative_pnl }
  }
  const cutoff = Date.now() - cutoffMs
  const before = full.filter((p) => new Date(p.timestamp).getTime() < cutoff)
  const inWindow = full.filter((p) => new Date(p.timestamp).getTime() >= cutoff)
  if (inWindow.length === 0) {
    return { points: [], period_pnl: null }
  }
  const baseline = before.length > 0 ? before[before.length - 1].cumulative_pnl : 0
  const cutoffAnchor = { timestamp: new Date(cutoff).toISOString(), cumulative_pnl: baseline }
  const periodPnl = Math.round((inWindow[inWindow.length - 1].cumulative_pnl - baseline) * 100) / 100
  return { points: [cutoffAnchor, ...inWindow], period_pnl: periodPnl }
}

/**
 * Ember's equity curve — built ENTIRELY from `ember_trades`' own realized
 * `pnl`, because that is the only $ figure this pipeline tracks for Ember.
 * There is no `ember_equity_snapshots` table, no `starting_capital`, and no
 * live-balance read anywhere in this file or the sync route: REFLEX computes
 * its own live Robinhood `total_value` internally (run_reflex.py,
 * `capital_floor_ok()`) but reflex_sync.py never persists or syncs it here
 * (see that script's own documented schema gaps). Wiring that through is a
 * real improvement but touches the already-armed REFLEX sleeve and its sync
 * script — out of scope for this read-only webapp chart; flagged, not fixed.
 *
 * So `cumulative_pnl` below is cumulative REALIZED P&L, not account value —
 * open positions contribute nothing (no field exists to mark them to market
 * either). "Day" always exists as a toggle option (binding, 2026-10-15) even
 * though `closed_at` is date-precision only (reflex_sync.py's own documented
 * gap #2): it anchors on the cumulative total immediately before today's
 * first closed trade (or "1 minute ago" when there were none yet today),
 * then steps through today's own trades in their stored order — the finest
 * resolution the real data actually supports, never a fabricated intraday
 * bucket.
 *
 * `strategy` (reflex | cinder | talon) narrows the curve to one sleeve's own
 * trades; omitted or undefined sums realized P&L across ALL of them, so the
 * existing chart shows COMBINED Ember P&L by default without a rebuild.
 */
export async function getEmberEquityCurve(period: EmberEquityPeriod, strategy?: string): Promise<EmberEquityCurve> {
  await ensureTables()
  const rows = strategy
    ? await query<{ id: number; closed_at: string | null; pnl: string | null }>(
        `SELECT id, closed_at::text, pnl
           FROM ${TRADES_TABLE}
          WHERE status = 'closed' AND pnl IS NOT NULL AND closed_at IS NOT NULL AND strategy = $1
          ORDER BY closed_at, id`,
        [strategy],
      )
    : await query<{ id: number; closed_at: string | null; pnl: string | null }>(
        `SELECT id, closed_at::text, pnl
           FROM ${TRADES_TABLE}
          WHERE status = 'closed' AND pnl IS NOT NULL AND closed_at IS NOT NULL
          ORDER BY closed_at, id`,
      )
  if (rows.length === 0) return { points: [], period_pnl: null }

  let running = 0
  const full: EmberEquityPoint[] = rows.map((r) => {
    running = Math.round((running + Number(r.pnl)) * 100) / 100
    return { timestamp: r.closed_at as string, cumulative_pnl: running }
  })

  if (period === 'day') {
    const todayKey = ctDateKey(new Date().toISOString())
    const todaysPoints = full.filter((p) => ctDateKey(p.timestamp) === todayKey)
    const priorPoints = full.filter((p) => ctDateKey(p.timestamp) !== todayKey)
    const dayOpenPnl = priorPoints.length > 0 ? priorPoints[priorPoints.length - 1].cumulative_pnl : 0
    const now = Date.now()
    const anchorTimestamp = new Date(
      todaysPoints.length > 0 ? new Date(todaysPoints[0].timestamp).getTime() - 60_000 : now - 60_000,
    ).toISOString()
    const points =
      todaysPoints.length > 0
        ? [{ timestamp: anchorTimestamp, cumulative_pnl: dayOpenPnl }, ...todaysPoints]
        : [{ timestamp: anchorTimestamp, cumulative_pnl: dayOpenPnl }, { timestamp: new Date(now).toISOString(), cumulative_pnl: dayOpenPnl }]
    const periodPnl = Math.round((points[points.length - 1].cumulative_pnl - dayOpenPnl) * 100) / 100
    return { points, period_pnl: periodPnl }
  }

  if (period === 'week') return windowedCurve(full, 7 * 86_400_000)
  if (period === 'month') return windowedCurve(full, 30 * 86_400_000)
  if (period === 'year') return windowedCurve(full, 365 * 86_400_000)
  return windowedCurve(full, null) // 'all'
}
