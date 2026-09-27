/**
 * FLAME_FAST_START persistence — per-account state + decision log.
 *
 * Follows the repo's existing "auto-create on first use" migration style
 * (see getOrSeedFlintAccountFloor / getOrRatchetCustomerHighWater in
 * tradier.ts): CREATE TABLE IF NOT EXISTS on every call, no separate
 * migration runner, safe on every deploy including a fresh one.
 *
 * Kept in its OWN file (not folded into tradier.ts) so the new tables and
 * the new decision log are one small, reviewable diff on a real-money
 * change, and so fast-start-sizing.ts (the pure math) never has to import
 * anything DB-shaped.
 */
import { query, dbExecute } from './db'

export interface FastStartStateRow {
  phase: 1 | 2
  deposit: number
}

async function ensureFastStartStateTable(): Promise<void> {
  await dbExecute(
    `CREATE TABLE IF NOT EXISTS fast_start_state (
       id SERIAL PRIMARY KEY,
       person TEXT NOT NULL,
       account_type TEXT NOT NULL,
       phase SMALLINT NOT NULL DEFAULT 1,
       deposit NUMERIC NOT NULL,
       triggered_at TIMESTAMP,
       created_at TIMESTAMP NOT NULL DEFAULT NOW(),
       updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
       UNIQUE (person, account_type)
     )`,
  )
}

async function ensureFastStartDecisionLogTable(): Promise<void> {
  await dbExecute(
    `CREATE TABLE IF NOT EXISTS fast_start_decision_log (
       id BIGSERIAL PRIMARY KEY,
       person TEXT NOT NULL,
       account_type TEXT NOT NULL,
       trade_date DATE NOT NULL,
       evaluated_at TIMESTAMP NOT NULL DEFAULT NOW(),
       phase SMALLINT NOT NULL,
       triggered_today BOOLEAN NOT NULL DEFAULT FALSE,
       normal_ladder INTEGER,
       ebb_contracts INTEGER NOT NULL,
       flint_contracts INTEGER NOT NULL,
       deposit NUMERIC,
       equity NUMERIC,
       cushion NUMERIC,
       floor_amount NUMERIC,
       budget NUMERIC,
       phase1_cap_budget NUMERIC,
       trigger_level NUMERIC,
       reason TEXT
     )`,
  )
  await dbExecute(
    `CREATE INDEX IF NOT EXISTS fast_start_decision_log_person_date_idx
       ON fast_start_decision_log (person, account_type, trade_date)`,
  )
}

/**
 * Read this account's fast-start state, seeding it (phase=1, this deposit)
 * on first use. `deposit` MUST be the account's own flint_account_floor
 * floor_amount (the SAME seeded-once floor EBB's profit ladder and FLINT's
 * R1 gate already use) — passed in by the caller, never re-derived here.
 *
 * SEEDING BEHAVIOR (existing accounts, first run after FLAME_FAST_START is
 * turned on): every account seeds at phase=1. An account that ALREADY has
 * enough cushion today (equity - deposit >= the Phase-1->2 trigger, using
 * TODAY's own ladder/max-loss numbers) advances to phase 2 within the very
 * same evaluation — decideFastStartSizing's trigger check runs before that
 * day's sizing regardless of whether the state row is brand new or 100
 * days old. So: an account with pre-existing profit large enough to clear
 * the trigger starts trading under Phase 2 (the G floor) on day one; an
 * account at or below its deposit starts in Phase 1 at 2x. Nothing special
 * is coded for "existing account" — it falls out of the same trigger check
 * every day already runs.
 *
 * Returns null on any DB failure — the caller must skip (fail closed),
 * never guess a phase/deposit for real money.
 */
export async function getOrSeedFastStartState(
  person: string,
  accountType: 'sandbox' | 'production',
  deposit: number,
): Promise<FastStartStateRow | null> {
  try {
    await ensureFastStartStateTable()
    const existing = await query(
      `SELECT phase, deposit FROM fast_start_state WHERE person = $1 AND account_type = $2`,
      [person, accountType],
    )
    if (existing.length > 0) {
      const phase = Number(existing[0].phase)
      const dep = Number(existing[0].deposit)
      if ((phase !== 1 && phase !== 2) || !Number.isFinite(dep)) return null
      return { phase: phase as 1 | 2, deposit: dep }
    }
    if (!Number.isFinite(deposit) || deposit <= 0) return null
    await query(
      `INSERT INTO fast_start_state (person, account_type, phase, deposit, created_at, updated_at)
       VALUES ($1, $2, 1, $3, NOW(), NOW())
       ON CONFLICT (person, account_type) DO NOTHING`,
      [person, accountType, deposit],
    )
    // Re-read rather than trust the just-inserted values: a concurrent scan
    // tick may have won the ON CONFLICT DO NOTHING race first.
    const after = await query(
      `SELECT phase, deposit FROM fast_start_state WHERE person = $1 AND account_type = $2`,
      [person, accountType],
    )
    if (after.length === 0) return null
    const phase = Number(after[0].phase)
    const dep = Number(after[0].deposit)
    if ((phase !== 1 && phase !== 2) || !Number.isFinite(dep)) return null
    return { phase: phase as 1 | 2, deposit: dep }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[fast-start-db] getOrSeedFastStartState('${person}','${accountType}') failed: ${msg}`)
    return null
  }
}

/**
 * Persist a phase advance. STICKY — only ever writes phase=2, never writes
 * phase=1 over an existing phase=2 row (one-way, matches
 * fast-start-sizing.ts's own nextState contract). A no-op (and not an
 * error) when the account is already at phase 2 or the write races with
 * another already-phase-2 write.
 */
export async function persistFastStartPhaseAdvance(
  person: string,
  accountType: 'sandbox' | 'production',
): Promise<void> {
  try {
    await ensureFastStartStateTable()
    await query(
      `UPDATE fast_start_state
         SET phase = 2, triggered_at = COALESCE(triggered_at, NOW()), updated_at = NOW()
       WHERE person = $1 AND account_type = $2 AND phase = 1`,
      [person, accountType],
    )
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[fast-start-db] persistFastStartPhaseAdvance('${person}','${accountType}') failed: ${msg}`)
  }
}

export interface FastStartDecisionLogEntry {
  person: string
  accountType: 'sandbox' | 'production'
  tradeDate: string // YYYY-MM-DD
  phase: 1 | 2
  triggeredToday: boolean
  normalLadder: number | null
  ebbContracts: number
  flintContracts: number
  deposit: number | null
  equity: number | null
  cushion: number | null
  floor: number | null
  budget: number | null
  phase1CapBudget: number | null
  triggerLevel: number | null
  reason: string
}

/**
 * One row per account per day per evaluation — so Monday's first live day
 * can be verified (phase, ladder count, multiplier, cap, floor, budget,
 * final contracts, reason). Never throws into the caller; a logging
 * failure must not block or alter a sizing decision that already happened.
 */
export async function logFastStartDecision(entry: FastStartDecisionLogEntry): Promise<void> {
  try {
    await ensureFastStartDecisionLogTable()
    await query(
      `INSERT INTO fast_start_decision_log
         (person, account_type, trade_date, phase, triggered_today, normal_ladder,
          ebb_contracts, flint_contracts, deposit, equity, cushion, floor_amount, budget,
          phase1_cap_budget, trigger_level, reason)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)`,
      [
        entry.person, entry.accountType, entry.tradeDate, entry.phase, entry.triggeredToday, entry.normalLadder,
        entry.ebbContracts, entry.flintContracts, entry.deposit, entry.equity, entry.cushion, entry.floor,
        entry.budget, entry.phase1CapBudget, entry.triggerLevel, entry.reason,
      ],
    )
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[fast-start-db] logFastStartDecision('${entry.person}','${entry.accountType}') failed: ${msg}`)
  }
}
