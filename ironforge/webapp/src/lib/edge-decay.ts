/**
 * EDGE-DECAY ALARM — one-sided CUSUM (Page's test) on each strategy's own
 * closed-trade realized P&L per contract, calibrated against its 2023-24
 * "edge intact" baseline. See:
 *   C:\Users\lemol\dev\meltup\PREREG_edge_decay_alarm.md
 *   C:\Users\lemol\dev\meltup\RESULT_edge_decay_alarm.md
 *
 * Recursion (Page's one-sided CUSUM, decay direction only):
 *   S_n = min(0, S_{n-1} + (pnl_n - mu0) + k)
 *   alarm when S_n <= -h
 * (mu0, k, h) are calibrated per strategy in RESULT_edge_decay_alarm.md's
 * table (a); CallDiag's (mu0, k) additionally re-baseline off a trailing
 * window of its OWN closed trades (see computeCallDiagRollingBaseline)
 * instead of the frozen, near-zero 2023-24 anchor — the RESULT file's
 * explicit recommendation, because that frozen anchor made CallDiag's SPRT
 * degenerate and Bayes over-alarm.
 *
 * Actions per the RESULT file's recommendation:
 *   FLINT, CallDiag — auto-pause new entries on alarm, resume after a
 *     10-trade SHADOW block (zero-capital-risk realized trades scored while
 *     paused) averages > 0.
 *   EBB — notify only. Never pauses (2026's data is EBB's 2nd-best year; the
 *     RESULT file measured auto-pause costing EBB money in its own history).
 *
 * EDGE_DECAY_MODE (unset = 'off', byte-for-byte unchanged behavior):
 *   off    — this module never reads or writes the database. Every exported
 *            function that would otherwise touch SQL short-circuits first.
 *   notify — compute the CUSUM, log/alarm, notify — never pauses, any strategy.
 *   enforce — notify PLUS auto-pause for FLINT/CallDiag (never EBB).
 *
 * Design split, mirroring lib/flame-skip.ts / lib/flint.ts: the actual state
 * transition (`applyClosedTrade`) is a PURE function with no DB/network
 * dependency, so the CUSUM math, alarm threshold, intact-edge sequence,
 * pause/shadow/resume state machine, "EBB never pauses," and mode gating are
 * all unit-testable without mocking Postgres. `recordEdgeDecayClose` is the
 * thin, DB-touching wrapper the trading files call from their close hooks.
 */

import { query, dbExecute } from './db'
import { sendOpsPush } from './sms'

export type Strategy = 'flint' | 'calldiag' | 'ebb'
export type EdgeDecayMode = 'off' | 'notify' | 'enforce'
export type EdgeDecayStatus = 'active' | 'paused' | 'shadow'

const STATE_TABLE = 'edge_decay_state'
const LOG_TABLE = 'edge_decay_alarm_log'
const SHADOW_TABLE = 'edge_decay_shadow_trades'

/**
 * Calibrated (mu0, k, h) per strategy — table (a) in RESULT_edge_decay_alarm.md.
 * `pausable` encodes the RESULT file's recommendation directly: FLINT and
 * CallDiag auto-pause, EBB never does (notify-only, whatever the mode).
 * `rollingBaseline` marks CallDiag's mu0/k as re-baselined live off its own
 * trailing closed trades rather than the frozen anchor below (used only as
 * CallDiag's fallback when it has too little history to re-baseline yet).
 */
export const STRATEGY_PARAMS: Record<Strategy, { mu0: number; k: number; h: number; pausable: boolean; rollingBaseline: boolean }> = {
  flint: { mu0: 6.35, k: 3.17, h: 417.88, pausable: true, rollingBaseline: false },
  ebb: { mu0: 9.15, k: 4.57, h: 316.99, pausable: false, rollingBaseline: false },
  calldiag: { mu0: -0.14, k: -0.07, h: 1317.38, pausable: true, rollingBaseline: true },
}

/** The 10-trade shadow block size, per the RESULT file's resume rule. */
const SHADOW_BLOCK_SIZE = 10

/** Minimum trailing trades CallDiag needs before trusting a rolling re-baseline over the frozen anchor. */
const CALLDIAG_ROLLING_MIN_TRADES = 10
/** CallDiag's rolling baseline window — RESULT file recommends ~500 trades, refreshed quarterly; here refreshed every recompute, which is only ever more current. */
const CALLDIAG_ROLLING_WINDOW = 500

export function getEdgeDecayMode(): EdgeDecayMode {
  const raw = (process.env.EDGE_DECAY_MODE ?? '').trim().toLowerCase()
  if (raw === 'notify' || raw === 'enforce') return raw
  return 'off'
}

/* ------------------------------------------------------------------ */
/*  Pure math — CUSUM step + alarm test. Unit-tested directly.         */
/* ------------------------------------------------------------------ */

/** One step of Page's one-sided CUSUM (decay direction): S_n = min(0, S_{n-1} + (pnl - mu0) + k). */
export function cusumStep(prevS: number, pnl: number, mu0: number, k: number): number {
  return Math.min(0, prevS + (pnl - mu0) + k)
}

/** True once the running statistic has crossed the (negative) alarm threshold. */
export function isAlarmed(s: number, h: number): boolean {
  return s <= -h
}

/* ------------------------------------------------------------------ */
/*  Pure state machine — no DB, no network. Unit-tested directly.      */
/* ------------------------------------------------------------------ */

export interface EdgeDecayState {
  strategy: Strategy
  status: EdgeDecayStatus
  cusumValue: number
  mu0: number
  k: number
  h: number
  shadowCount: number
  shadowSum: number
}

export function initialEdgeDecayState(strategy: Strategy, params = STRATEGY_PARAMS[strategy]): EdgeDecayState {
  return {
    strategy,
    status: 'active',
    cusumValue: 0,
    mu0: params.mu0,
    k: params.k,
    h: params.h,
    shadowCount: 0,
    shadowSum: 0,
  }
}

export type EdgeDecayAction =
  | { type: 'none' }
  | { type: 'progress' }
  | { type: 'alarm'; enforced: boolean }
  | { type: 'shadow_progress' }
  | { type: 'shadow_block_failed'; avg: number }
  | { type: 'resumed'; avg: number }

/**
 * The one function the state machine lives in. `mode==='off'` is handled by
 * the caller (recordEdgeDecayClose short-circuits before this ever runs) —
 * this function assumes it is being asked to actually evaluate a trade.
 *
 * `pausable=false` (EBB) or `mode==='notify'` (any strategy) means an alarm
 * NEVER flips status to paused/shadow — it only resets S and logs. That is
 * the literal RESULT-file rule ("EBB ... notify Leron, not auto-pause") and
 * the literal EDGE_DECAY_MODE contract ("notify = ... never pauses").
 */
export function applyClosedTrade(
  state: EdgeDecayState,
  pnl: number,
  opts: { mode: EdgeDecayMode; pausable: boolean },
): { state: EdgeDecayState; action: EdgeDecayAction } {
  if (state.status === 'active') {
    const nextS = cusumStep(state.cusumValue, pnl, state.mu0, state.k)
    if (isAlarmed(nextS, state.h)) {
      const enforced = opts.mode === 'enforce' && opts.pausable
      return {
        state: {
          ...state,
          cusumValue: 0,
          status: enforced ? 'paused' : 'active',
          shadowCount: 0,
          shadowSum: 0,
        },
        action: { type: 'alarm', enforced },
      }
    }
    return { state: { ...state, cusumValue: nextS }, action: { type: 'progress' } }
  }

  // status is 'paused' or 'shadow' — this trade is a shadow-block trade
  // (RESULT file: "keep scoring the next realized trades ... can be
  // shadow/paper — no capital needs to be at risk to run the test").
  const shadowCount = state.shadowCount + 1
  const shadowSum = state.shadowSum + pnl
  if (shadowCount >= SHADOW_BLOCK_SIZE) {
    const avg = shadowSum / shadowCount
    if (avg > 0) {
      return {
        state: { ...state, status: 'active', cusumValue: 0, shadowCount: 0, shadowSum: 0 },
        action: { type: 'resumed', avg },
      }
    }
    // Block failed — start a fresh 10-trade block, stay paused/blocked.
    return {
      state: { ...state, status: 'shadow', shadowCount: 0, shadowSum: 0 },
      action: { type: 'shadow_block_failed', avg },
    }
  }
  return {
    state: { ...state, status: 'shadow', shadowCount, shadowSum },
    action: { type: 'shadow_progress' },
  }
}

/* ------------------------------------------------------------------ */
/*  Persistence — thin DB-touching glue around the pure state machine. */
/* ------------------------------------------------------------------ */

let _tablesReady = false
export async function ensureEdgeDecayTables(): Promise<void> {
  if (_tablesReady) return
  await dbExecute(
    `CREATE TABLE IF NOT EXISTS ${STATE_TABLE} (
       strategy TEXT PRIMARY KEY,
       status TEXT NOT NULL DEFAULT 'active',
       cusum_value NUMERIC NOT NULL DEFAULT 0,
       mu0 NUMERIC NOT NULL,
       k NUMERIC NOT NULL,
       h NUMERIC NOT NULL,
       shadow_count INTEGER NOT NULL DEFAULT 0,
       shadow_sum NUMERIC NOT NULL DEFAULT 0,
       alarmed_at TIMESTAMPTZ,
       resumed_at TIMESTAMPTZ,
       updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
     )`,
  )
  await dbExecute(
    `CREATE TABLE IF NOT EXISTS ${LOG_TABLE} (
       id SERIAL PRIMARY KEY,
       strategy TEXT NOT NULL,
       event_type TEXT NOT NULL,
       cusum_value NUMERIC,
       detail JSONB,
       created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
     )`,
  )
  // Generic (strategy, trade_date) shadow ledger — used by strategies that have
  // no pre-existing zero-capital-risk trade stream of their own to reuse as the
  // resume test (CallDiag today; every row here is explicitly hypothetical,
  // never a real order). See calldiag-tracker.ts's edge-decay shadow entry/exit.
  await dbExecute(
    `CREATE TABLE IF NOT EXISTS ${SHADOW_TABLE} (
       id SERIAL PRIMARY KEY,
       strategy TEXT NOT NULL,
       trade_date DATE NOT NULL,
       ticker TEXT,
       front_expiry DATE,
       back_expiry DATE,
       short_strike NUMERIC,
       long_strike NUMERIC,
       short_bid_entry NUMERIC,
       long_ask_entry NUMERIC,
       contracts INTEGER NOT NULL DEFAULT 1,
       status TEXT NOT NULL DEFAULT 'open',
       short_ask_exit NUMERIC,
       long_bid_exit NUMERIC,
       realized_pnl NUMERIC,
       created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
       closed_at TIMESTAMPTZ,
       UNIQUE (strategy, trade_date)
     )`,
  )
  _tablesReady = true
}

type StateRow = {
  strategy: string
  status: string
  cusum_value: string | number
  mu0: string | number
  k: string | number
  h: string | number
  shadow_count: string | number
  shadow_sum: string | number
}

function rowToState(row: StateRow): EdgeDecayState {
  return {
    strategy: row.strategy as Strategy,
    status: row.status as EdgeDecayStatus,
    cusumValue: Number(row.cusum_value) || 0,
    mu0: Number(row.mu0),
    k: Number(row.k),
    h: Number(row.h),
    shadowCount: Number(row.shadow_count) || 0,
    shadowSum: Number(row.shadow_sum) || 0,
  }
}

/**
 * Load (or seed, on first use) this strategy's persisted state. CallDiag's
 * mu0/k are refreshed from its own trailing closed trades every call (see
 * computeCallDiagRollingBaseline) — h stays at the calibrated value; the
 * RESULT file's bootstrap-to-target-ARL calibration for h has no live
 * equivalent without re-running that bootstrap, so it is not recomputed here.
 */
export async function getEdgeDecayState(strategy: Strategy): Promise<EdgeDecayState> {
  await ensureEdgeDecayTables()
  const params = STRATEGY_PARAMS[strategy]
  let mu0 = params.mu0
  let k = params.k
  if (params.rollingBaseline) {
    const rolling = await computeCallDiagRollingBaseline()
    if (rolling) { mu0 = rolling.mu0; k = rolling.k }
  }

  const rows = await query<StateRow>(`SELECT * FROM ${STATE_TABLE} WHERE strategy = $1`, [strategy])
  if (rows.length === 0) {
    await query(
      `INSERT INTO ${STATE_TABLE} (strategy, status, cusum_value, mu0, k, h, shadow_count, shadow_sum)
       VALUES ($1, 'active', 0, $2, $3, $4, 0, 0)
       ON CONFLICT (strategy) DO NOTHING`,
      [strategy, mu0, k, params.h],
    )
    return initialEdgeDecayState(strategy, { ...params, mu0, k })
  }
  const state = rowToState(rows[0])
  // Keep CallDiag's live mu0/k current even on an existing row — a fixed h,
  // freshly-recomputed mu0/k, same as getEdgeDecayState's first-seed path.
  if (params.rollingBaseline) { state.mu0 = mu0; state.k = k }
  return state
}

async function persistState(state: EdgeDecayState, action: EdgeDecayAction): Promise<void> {
  const now = new Date()
  const alarmedAtSql = action.type === 'alarm' ? 'NOW()' : 'alarmed_at'
  const resumedAtSql = action.type === 'resumed' ? 'NOW()' : 'resumed_at'
  await query(
    `UPDATE ${STATE_TABLE}
        SET status = $2, cusum_value = $3, mu0 = $4, k = $5, h = $6,
            shadow_count = $7, shadow_sum = $8, updated_at = NOW(),
            alarmed_at = ${alarmedAtSql}, resumed_at = ${resumedAtSql}
      WHERE strategy = $1`,
    [state.strategy, state.status, state.cusumValue, state.mu0, state.k, state.h, state.shadowCount, state.shadowSum],
  )
  void now
}

async function logEvent(strategy: Strategy, eventType: string, cusumValue: number, detail: Record<string, unknown>): Promise<void> {
  try {
    await query(
      `INSERT INTO ${LOG_TABLE} (strategy, event_type, cusum_value, detail) VALUES ($1, $2, $3, $4)`,
      [strategy, eventType, cusumValue, JSON.stringify(detail)],
    )
  } catch (e) {
    console.warn(`[edge-decay] alarm log write failed (non-fatal): ${e instanceof Error ? e.message : String(e)}`)
  }
}

/**
 * CallDiag's rolling re-baseline: mean pnl (mu0) and k=mu0/2 over its own
 * trailing CALLDIAG_ROLLING_WINDOW closed trades — the RESULT file's
 * recommendation, replacing the frozen 2023-24 anchor that made CallDiag's
 * mean look near-zero and its other methods degenerate/over-alarm. Falls
 * back to the frozen anchor (STRATEGY_PARAMS.calldiag) below
 * CALLDIAG_ROLLING_MIN_TRADES of live history, and on any read error — never
 * fabricates a baseline off too little data.
 */
export async function computeCallDiagRollingBaseline(): Promise<{ mu0: number; k: number } | null> {
  try {
    const rows = await query<{ pnl: string | number }>(
      `SELECT realized_pnl / GREATEST(contracts, 1) AS pnl
         FROM calldiag_positions
        WHERE status = 'closed' AND realized_pnl IS NOT NULL
        ORDER BY exit_date DESC, id DESC
        LIMIT ${CALLDIAG_ROLLING_WINDOW}`,
    )
    if (rows.length < CALLDIAG_ROLLING_MIN_TRADES) return null
    const values = rows.map((r) => Number(r.pnl)).filter((n) => Number.isFinite(n))
    if (values.length < CALLDIAG_ROLLING_MIN_TRADES) return null
    const mu0 = values.reduce((a, b) => a + b, 0) / values.length
    return { mu0, k: mu0 / 2 }
  } catch (e) {
    console.warn(`[edge-decay] CallDiag rolling baseline read failed (non-fatal, using frozen anchor): ${e instanceof Error ? e.message : String(e)}`)
    return null
  }
}

/**
 * The hook every strategy's own close/settle path calls with ONE closed
 * trade's realized pnl PER CONTRACT (matching the calibration's per-trade,
 * 1-lot series). No-ops with ZERO database access when EDGE_DECAY_MODE is
 * unset/off — that is the byte-for-byte-unchanged contract.
 *
 * `opts.shadow` marks this pnl as belonging to a strategy's zero-capital
 * shadow stream (FLINT's own paper book while paused; CallDiag's dedicated
 * shadow table) — it is scored identically by the state machine, which
 * already only treats a trade as "shadow-block scoring" once status is
 * paused/shadow. The flag exists for logging/observability, not branching.
 */
export async function recordEdgeDecayClose(
  strategy: Strategy,
  pnlPerContract: number,
  opts?: { shadow?: boolean },
): Promise<EdgeDecayAction> {
  const mode = getEdgeDecayMode()
  if (mode === 'off') return { type: 'none' }
  if (!Number.isFinite(pnlPerContract)) return { type: 'none' }

  const params = STRATEGY_PARAMS[strategy]
  const before = await getEdgeDecayState(strategy)
  const { state: after, action } = applyClosedTrade(before, pnlPerContract, { mode, pausable: params.pausable })
  await persistState(after, action)

  if (action.type === 'alarm') {
    await logEvent(strategy, 'alarm', after.cusumValue, { pnl: pnlPerContract, enforced: action.enforced, shadow: !!opts?.shadow, mu0: after.mu0, k: after.k, h: after.h })
    await notifyEdgeDecayAlarm(strategy, before.cusumValue, action.enforced)
  } else if (action.type === 'resumed') {
    await logEvent(strategy, 'resume', after.cusumValue, { shadow_avg: action.avg })
    await notifyEdgeDecayResume(strategy, action.avg)
  } else if (action.type === 'shadow_block_failed') {
    await logEvent(strategy, 'shadow_block_failed', after.cusumValue, { shadow_avg: action.avg })
  }

  return action
}

/**
 * True only when EDGE_DECAY_MODE=enforce AND this strategy is currently
 * paused/shadow — the entry-gate check FLINT/CallDiag call before placing a
 * new real (non-shadow) trade. Mode !== 'enforce' short-circuits to false
 * with NO database access, same off-by-default contract as recordEdgeDecayClose:
 * flipping EDGE_DECAY_MODE off never leaves a strategy stuck paused.
 */
export async function isEdgeDecayPaused(strategy: Strategy): Promise<boolean> {
  if (getEdgeDecayMode() !== 'enforce') return false
  const state = await getEdgeDecayState(strategy)
  return state.status === 'paused' || state.status === 'shadow'
}

/* ------------------------------------------------------------------ */
/*  Generic shadow-trade ledger — CallDiag's zero-capital resume stream */
/* ------------------------------------------------------------------ */

export interface ShadowEntryFields {
  tradeDate: string
  ticker: string
  frontExpiry: string
  backExpiry: string
  shortStrike: number
  longStrike: number
  shortBidEntry: number
  longAskEntry: number
  contracts: number
}

/** Record one hypothetical trade while paused. Idempotent per (strategy, tradeDate). */
export async function recordEdgeDecayShadowEntry(strategy: Strategy, f: ShadowEntryFields): Promise<void> {
  await ensureEdgeDecayTables()
  await query(
    `INSERT INTO ${SHADOW_TABLE} (
       strategy, trade_date, ticker, front_expiry, back_expiry, short_strike, long_strike,
       short_bid_entry, long_ask_entry, contracts, status
     ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'open')
     ON CONFLICT (strategy, trade_date) DO NOTHING`,
    [strategy, f.tradeDate, f.ticker, f.frontExpiry, f.backExpiry, f.shortStrike, f.longStrike, f.shortBidEntry, f.longAskEntry, f.contracts],
  )
}

export interface ShadowOpenRow {
  id: number
  trade_date: string
  ticker: string
  front_expiry: string
  back_expiry: string
  short_strike: string | number
  long_strike: string | number
  short_bid_entry: string | number
  long_ask_entry: string | number
  contracts: string | number
}

export async function getOpenEdgeDecayShadowTrades(strategy: Strategy): Promise<ShadowOpenRow[]> {
  await ensureEdgeDecayTables()
  return query<ShadowOpenRow>(
    `SELECT id, trade_date::text, ticker, front_expiry::text, back_expiry::text,
            short_strike, long_strike, short_bid_entry, long_ask_entry, contracts
       FROM ${SHADOW_TABLE}
      WHERE strategy = $1 AND status = 'open'`,
    [strategy],
  )
}

/** Close one shadow row AND feed its per-contract pnl into the state machine in one call. */
export async function settleEdgeDecayShadowTrade(
  id: number,
  strategy: Strategy,
  fields: { shortAskExit: number; longBidExit: number; realizedPnl: number; contracts: number },
): Promise<EdgeDecayAction> {
  await ensureEdgeDecayTables()
  await query(
    `UPDATE ${SHADOW_TABLE}
        SET status = 'closed', short_ask_exit = $2, long_bid_exit = $3, realized_pnl = $4, closed_at = NOW()
      WHERE id = $1`,
    [id, fields.shortAskExit, fields.longBidExit, fields.realizedPnl],
  )
  return recordEdgeDecayClose(strategy, fields.realizedPnl / Math.max(1, fields.contracts), { shadow: true })
}

/* ------------------------------------------------------------------ */
/*  Notification — a working channel, not the dead notify-hub webhook. */
/* ------------------------------------------------------------------ */

/**
 * 🚨 vanta-notify-hub-discord-webhook-dead.md: the notify-hub Discord webhook
 * that other IronForge alerts used to route through 404s (Unknown Webhook) —
 * silently. This module never touches it. It uses lib/sms.ts's sendOpsPush,
 * the SAME live, multi-channel (ntfy/SMS-gateway/Twilio/Discord) push path
 * the assignment guard and watchdog already alert through, plus a
 * console.error tag so the alarm is always visible in Render logs even with
 * zero alert channels configured.
 */
export async function notifyEdgeDecayAlarm(strategy: Strategy, cusumValue: number, enforced: boolean): Promise<void> {
  const title = `[edge-decay] ALARM ${strategy.toUpperCase()}`
  const body = enforced
    ? `${strategy.toUpperCase()} paused (CUSUM ${cusumValue.toFixed(2)}) — resumes after a 10-trade shadow block averages > 0.`
    : `${strategy.toUpperCase()} edge-decay alarm (CUSUM ${cusumValue.toFixed(2)}) — notify-only, no pause taken.`
  console.error(`${title}: ${body}`)
  try {
    await sendOpsPush({ title, body, severity: 'critical' })
  } catch (e) {
    console.warn(`[edge-decay] notify failed (non-fatal): ${e instanceof Error ? e.message : String(e)}`)
  }
}

export async function notifyEdgeDecayResume(strategy: Strategy, shadowAvg: number): Promise<void> {
  const title = `[edge-decay] RESUME ${strategy.toUpperCase()}`
  const body = `${strategy.toUpperCase()} resumed live entries — 10-trade shadow block averaged $${shadowAvg.toFixed(2)}/trade.`
  console.log(`${title}: ${body}`)
  try {
    await sendOpsPush({ title, body, severity: 'info' })
  } catch (e) {
    console.warn(`[edge-decay] notify failed (non-fatal): ${e instanceof Error ? e.message : String(e)}`)
  }
}

/* ------------------------------------------------------------------ */
/*  Operator surface read — feeds GET /api/edge-decay.                 */
/* ------------------------------------------------------------------ */

export interface EdgeDecaySnapshotStrategy {
  strategy: Strategy
  status: EdgeDecayStatus
  cusum_value: number
  mu0: number
  k: number
  h: number
  shadow_count: number
  shadow_sum: number
  alarmed_at: string | null
  resumed_at: string | null
}

export interface EdgeDecayAlarmLogRow {
  strategy: string
  event_type: string
  cusum_value: number | null
  detail: unknown
  created_at: string
}

export async function getEdgeDecaySnapshot(): Promise<{
  mode: EdgeDecayMode
  strategies: EdgeDecaySnapshotStrategy[]
  recent_alarms: EdgeDecayAlarmLogRow[]
}> {
  const mode = getEdgeDecayMode()
  await ensureEdgeDecayTables()

  const strategies: EdgeDecaySnapshotStrategy[] = []
  for (const strategy of Object.keys(STRATEGY_PARAMS) as Strategy[]) {
    const rows = await query<StateRow & { alarmed_at: string | null; resumed_at: string | null }>(
      `SELECT * FROM ${STATE_TABLE} WHERE strategy = $1`,
      [strategy],
    )
    if (rows.length === 0) {
      const s = initialEdgeDecayState(strategy)
      strategies.push({
        strategy, status: s.status, cusum_value: s.cusumValue, mu0: s.mu0, k: s.k, h: s.h,
        shadow_count: 0, shadow_sum: 0, alarmed_at: null, resumed_at: null,
      })
      continue
    }
    const r = rows[0]
    strategies.push({
      strategy,
      status: r.status as EdgeDecayStatus,
      cusum_value: Number(r.cusum_value) || 0,
      mu0: Number(r.mu0),
      k: Number(r.k),
      h: Number(r.h),
      shadow_count: Number(r.shadow_count) || 0,
      shadow_sum: Number(r.shadow_sum) || 0,
      alarmed_at: r.alarmed_at ?? null,
      resumed_at: r.resumed_at ?? null,
    })
  }

  const recent_alarms = await query<EdgeDecayAlarmLogRow>(
    `SELECT strategy, event_type, cusum_value, detail, created_at::text
       FROM ${LOG_TABLE}
      ORDER BY created_at DESC, id DESC
      LIMIT 50`,
  )

  return { mode, strategies, recent_alarms }
}
