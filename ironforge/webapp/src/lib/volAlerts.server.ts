/**
 * Volatility-alerts server-only helpers (DB-bound). Kept separate from the
 * pure `volAlerts.ts` so client components can import the pure logic without
 * pulling `pg` into the browser bundle.
 *
 * `ensureVolAlertsTable()` is the single CREATE-IF-NOT-EXISTS bootstrap,
 * callable from both the API route and the scanner (IronForge convention).
 */

import { dbExecute } from './db'
import type { RegimeSnapshot, HedgeDecision } from './volAlerts'

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
