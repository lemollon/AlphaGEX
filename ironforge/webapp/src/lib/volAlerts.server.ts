/**
 * Volatility-alerts server-only helpers (DB-bound). Kept separate from the
 * pure `volAlerts.ts` so client components can import the pure logic without
 * pulling `pg` into the browser bundle.
 *
 * `ensureVolAlertsTable()` is the single CREATE-IF-NOT-EXISTS bootstrap,
 * callable from both the API route and the scanner (IronForge convention).
 */

import { dbExecute, query } from './db'
import type { RegimeSnapshot, HedgeDecision, SignalState, LadderTransition } from './volAlerts'

let _tableEnsured = false

/**
 * Auto-create the shared `vol_alerts` table on first use (IronForge
 * convention). Idempotent and cached per-process after the first success.
 */
export async function ensureVolAlertsTable(): Promise<void> {
  if (_tableEnsured) return
  await dbExecute(`
    CREATE TABLE IF NOT EXISTS vol_alerts (
      id          SERIAL PRIMARY KEY,
      signal_key  TEXT NOT NULL,
      direction   TEXT,
      status      TEXT NOT NULL DEFAULT 'active',
      headline    TEXT,
      message     TEXT,
      regime_label TEXT,
      vix         REAL,
      vvix        REAL,
      fired_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      resolved_at TIMESTAMPTZ
    )
  `)
  _tableEnsured = true
}

let _regimeDailyEnsured = false

/**
 * One persisted row per CT trading day: the latched regime read + the daily
 * hedge decision (sticky once flagged), plus next-day realized move for
 * backtesting. Fixes the empty `/api/volatility/history` (which proxied the
 * AlphaGEX backend) by keeping IronForge's OWN backtestable record.
 */
export async function ensureRegimeDailyTable(): Promise<void> {
  if (_regimeDailyEnsured) return
  await dbExecute(`
    CREATE TABLE IF NOT EXISTS regime_daily (
      ct_date          DATE PRIMARY KEY,
      regime_label     TEXT,
      active_signals   TEXT[],
      vix              REAL,
      vvix             REAL,
      vix3m            REAL,
      hedge_flagged    BOOLEAN NOT NULL DEFAULT FALSE,
      hedge_reasons    TEXT[],
      first_flagged_at TIMESTAMPTZ,
      realized_spy_ret REAL,
      realized_vix_chg REAL,
      updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `)
  _regimeDailyEnsured = true
}

/**
 * Upsert today's (CT) regime_daily row. `hedge_flagged` is STICKY — once any
 * read in the session trips the trigger, the day stays flagged (so a transient
 * morning trip still marks the day for the hedge/backtest). The CT date is
 * computed in-DB so callers don't have to. Best-effort; the scanner wraps it.
 */
export async function upsertRegimeDaily(snap: RegimeSnapshot, decision: HedgeDecision): Promise<void> {
  await ensureRegimeDailyTable()
  await dbExecute(
    `INSERT INTO regime_daily
       (ct_date, regime_label, active_signals, vix, vvix, vix3m,
        hedge_flagged, hedge_reasons, first_flagged_at, updated_at)
     VALUES (
       (NOW() AT TIME ZONE 'America/Chicago')::date,
       $1, $2, $3, $4, $5,
       $6, $7, CASE WHEN $6 THEN NOW() ELSE NULL END, NOW())
     ON CONFLICT (ct_date) DO UPDATE SET
       regime_label   = EXCLUDED.regime_label,
       active_signals = EXCLUDED.active_signals,
       vix            = EXCLUDED.vix,
       vvix           = EXCLUDED.vvix,
       vix3m          = EXCLUDED.vix3m,
       hedge_flagged  = regime_daily.hedge_flagged OR EXCLUDED.hedge_flagged,
       hedge_reasons  = CASE WHEN EXCLUDED.hedge_flagged THEN EXCLUDED.hedge_reasons ELSE regime_daily.hedge_reasons END,
       first_flagged_at = COALESCE(regime_daily.first_flagged_at, CASE WHEN EXCLUDED.hedge_flagged THEN NOW() ELSE NULL END),
       updated_at     = NOW()`,
    [
      snap.regimeLabel ?? null,
      snap.activeSignals ?? [],
      snap.vix ?? null,
      snap.vvix ?? null,
      snap.vix3m ?? null,
      decision.flagged,
      decision.reasons ?? [],
    ],
  )
}

/* ------------------------------------------------------------------ */
/*  Signal escalation ladder — the never-drop observation layer        */
/* ------------------------------------------------------------------ */

let _ladderEnsured = false

/**
 * Auto-create the ladder tables (IronForge convention; idempotent, cached).
 *
 *   `vol_signal_state`  — one row per signal: its CURRENT ladder state + notify
 *                          cooldown bookkeeping. Restart-safe (survives a redeploy,
 *                          unlike the in-memory debounce streaks).
 *   `vol_signal_events` — append-only transition log. A `tripped` read that never
 *                          confirms still leaves a permanent row here, so a real
 *                          market sign is never silently dropped by the debounce.
 */
export async function ensureSignalLadderTables(): Promise<void> {
  if (_ladderEnsured) return
  await dbExecute(`
    CREATE TABLE IF NOT EXISTS vol_signal_state (
      signal_key        TEXT PRIMARY KEY,
      state             TEXT NOT NULL,
      direction         TEXT,
      value             REAL,
      proximity         REAL,
      since             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      last_notify_at    TIMESTAMPTZ,
      last_notify_state TEXT,
      updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `)
  await dbExecute(`
    CREATE TABLE IF NOT EXISTS vol_signal_events (
      id           SERIAL PRIMARY KEY,
      signal_key   TEXT NOT NULL,
      direction    TEXT,
      from_state   TEXT NOT NULL,
      to_state     TEXT NOT NULL,
      value        REAL,
      proximity    REAL,
      vix          REAL,
      vvix         REAL,
      vix3m        REAL,
      regime_label TEXT,
      created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `)
  await dbExecute(
    `CREATE INDEX IF NOT EXISTS vol_signal_events_created_idx ON vol_signal_events (created_at DESC)`,
  )
  _ladderEnsured = true
}

/** One signal's instantaneous read for the ladder this scan cycle. */
export interface SignalRead {
  signalKey: string
  direction: string | null
  state: SignalState
  value: number | null
  proximity: number | null
  vix: number | null
  vvix: number | null
  vix3m: number | null
  regimeLabel: string | null
}

/**
 * Reconcile this cycle's per-signal reads against the persisted ladder state.
 * For each signal whose state CHANGED, append a `vol_signal_events` row and update
 * `vol_signal_state.since`; for unchanged signals just refresh value/proximity.
 * Returns the transitions that occurred (newest reads), for the caller to notify on.
 *
 * Best-effort and idempotent: events fire only on a real state change, so the log
 * never fills with per-cycle noise and a re-run with identical reads writes nothing.
 */
export async function recordLadderTransitions(reads: SignalRead[]): Promise<LadderTransition[]> {
  await ensureSignalLadderTables()
  const transitions: LadderTransition[] = []
  for (const r of reads) {
    const prevRows = await query<{ state: SignalState }>(
      `SELECT state FROM vol_signal_state WHERE signal_key = $1`,
      [r.signalKey],
    )
    const from: SignalState = prevRows[0]?.state ?? 'idle'
    const changed = from !== r.state

    if (changed) {
      await query(
        `INSERT INTO vol_signal_events
           (signal_key, direction, from_state, to_state, value, proximity, vix, vvix, vix3m, regime_label)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
        [r.signalKey, r.direction, from, r.state, r.value, r.proximity, r.vix, r.vvix, r.vix3m, r.regimeLabel],
      )
      transitions.push({ signalKey: r.signalKey, direction: r.direction, from, to: r.state })
    }

    // Upsert current state. `since` advances only when the state actually changed.
    await query(
      `INSERT INTO vol_signal_state (signal_key, state, direction, value, proximity, since, updated_at)
       VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
       ON CONFLICT (signal_key) DO UPDATE SET
         state     = EXCLUDED.state,
         direction = EXCLUDED.direction,
         value     = EXCLUDED.value,
         proximity = EXCLUDED.proximity,
         since     = CASE WHEN vol_signal_state.state = EXCLUDED.state
                          THEN vol_signal_state.since ELSE NOW() END,
         updated_at = NOW()`,
      [r.signalKey, r.state, r.direction, r.value, r.proximity],
    )
  }
  return transitions
}

/**
 * Atomic notify check-and-set against the per-signal cooldown. Returns true when a
 * notification for `(signalKey → toState)` is DUE — i.e. it's a different state than
 * the last one we notified for that signal, or the cooldown has elapsed — and stamps
 * the notify bookkeeping in the same UPDATE so a concurrent/duplicate cycle can't
 * double-send. Returns false (suppress) when within cooldown for the same state.
 * Tames any residual flap on the pre-confirm early-warning ping.
 */
export async function markNotifiedIfDue(
  signalKey: string,
  toState: string,
  cooldownMin: number,
): Promise<boolean> {
  const rows = await query<{ signal_key: string }>(
    `UPDATE vol_signal_state
        SET last_notify_at = NOW(), last_notify_state = $2
      WHERE signal_key = $1
        AND (last_notify_state IS DISTINCT FROM $2
             OR last_notify_at IS NULL
             OR last_notify_at < NOW() - make_interval(mins => $3::int))
      RETURNING signal_key`,
    [signalKey, toState, Math.max(0, Math.floor(cooldownMin))],
  )
  return rows.length > 0
}
