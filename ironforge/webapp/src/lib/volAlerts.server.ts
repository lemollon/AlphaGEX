/**
 * Volatility-alerts server-only helpers (DB-bound). Kept separate from the
 * pure `volAlerts.ts` so client components can import the pure logic without
 * pulling `pg` into the browser bundle.
 *
 * `ensureVolAlertsTable()` is the single CREATE-IF-NOT-EXISTS bootstrap,
 * callable from both the API route and the scanner (IronForge convention).
 */

import { dbExecute } from './db'

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
