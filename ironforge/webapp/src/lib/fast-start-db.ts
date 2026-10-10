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
import { query, dbExecute, botTable } from './db'
import { flintMaxLoss } from './flint'
import { evaluateFastStartTrigger } from './fast-start-sizing'

export interface FastStartStateRow {
  phase: 1 | 2
  deposit: number
  /** EOD-only ratchet (see updateFastStartEodState) — NEVER updated intraday. */
  peakProfit: number
}

async function ensureFastStartStateTable(): Promise<void> {
  await dbExecute(
    `CREATE TABLE IF NOT EXISTS fast_start_state (
       id SERIAL PRIMARY KEY,
       person TEXT NOT NULL,
       account_type TEXT NOT NULL,
       bot TEXT NOT NULL DEFAULT 'flame',
       phase SMALLINT NOT NULL DEFAULT 1,
       deposit NUMERIC NOT NULL,
       peak_profit NUMERIC NOT NULL DEFAULT 0,
       last_eod_date DATE,
       triggered_at TIMESTAMP,
       created_at TIMESTAMP NOT NULL DEFAULT NOW(),
       updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
       UNIQUE (person, account_type)
     )`,
  )
  // ADD COLUMN IF NOT EXISTS for deploys where this table pre-dates the
  // EOD-only peak_profit/last_eod_date ratchet (2026-09-29 correction —
  // peak_profit/phase/floor must update once per day at EOD from closing
  // equity, never intraday from a live unrealized mark).
  await dbExecute(`ALTER TABLE fast_start_state ADD COLUMN IF NOT EXISTS peak_profit NUMERIC NOT NULL DEFAULT 0`)
  await dbExecute(`ALTER TABLE fast_start_state ADD COLUMN IF NOT EXISTS last_eod_date DATE`)
  // Defensive migration (2026-09-27/29, SPARK_FAST_START): a table created
  // by FLAME's original PR has no `bot` column and a UNIQUE(person,
  // account_type) constraint — widen both so SPARK's rows never collide
  // with FLAME's on the same customer sandbox account (a customer can run
  // BOTH bots' fast-start engines independently on one physical account).
  await dbExecute(`ALTER TABLE fast_start_state ADD COLUMN IF NOT EXISTS bot TEXT NOT NULL DEFAULT 'flame'`)
  await dbExecute(
    `DO $$ BEGIN
       ALTER TABLE fast_start_state DROP CONSTRAINT IF EXISTS fast_start_state_person_account_type_key;
       ALTER TABLE fast_start_state DROP CONSTRAINT IF EXISTS fast_start_state_person_account_type_bot_key;
       ALTER TABLE fast_start_state ADD CONSTRAINT fast_start_state_person_account_type_bot_key
         UNIQUE (person, account_type, bot);
     EXCEPTION WHEN duplicate_table THEN NULL; WHEN duplicate_object THEN NULL; END $$`,
  )
}

async function ensureFastStartDecisionLogTable(): Promise<void> {
  await dbExecute(
    `CREATE TABLE IF NOT EXISTS fast_start_decision_log (
       id BIGSERIAL PRIMARY KEY,
       person TEXT NOT NULL,
       account_type TEXT NOT NULL,
       bot TEXT NOT NULL DEFAULT 'flame',
       trade_date DATE NOT NULL,
       leg TEXT NOT NULL DEFAULT 'ebb',
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
  // ADD COLUMN IF NOT EXISTS for deploys where this table pre-dates the
  // `leg` column (one decision-log row per account per LEG per day, per the
  // approved spec) — Postgres 9.6+ supports this directly.
  await dbExecute(`ALTER TABLE fast_start_decision_log ADD COLUMN IF NOT EXISTS leg TEXT NOT NULL DEFAULT 'ebb'`)
  await dbExecute(`ALTER TABLE fast_start_decision_log ADD COLUMN IF NOT EXISTS bot TEXT NOT NULL DEFAULT 'flame'`)
  await dbExecute(
    `CREATE INDEX IF NOT EXISTS fast_start_decision_log_person_date_idx
       ON fast_start_decision_log (person, account_type, bot, trade_date, leg)`,
  )
}

/**
 * Read this account's fast-start state, seeding it (phase=1, this deposit)
 * on first use. `deposit` MUST be the account's own flint_account_floor
 * floor_amount (the SAME seeded-once floor EBB's profit ladder and FLINT's
 * R1 gate already use) — passed in by the caller, never re-derived here.
 *
 * SEEDING BEHAVIOR (existing accounts, first run after FLAME_FAST_START is
 * turned on): every account seeds at phase=1, peak_profit = max(0,
 * `currentEquityForSeed` - deposit) as a one-time bootstrap (never touched
 * again intraday after this single INSERT). An account that already has
 * enough profit to clear the Phase-1->2 trigger does NOT jump to Phase 2
 * on this same call — phase/peak_profit/floor update ONLY at EOD (see
 * updateFastStartEodState), matching the sim's own once-per-day cadence,
 * so an intraday unrealized mark at the moment of seeding can never flip
 * the phase. Such an account sizes its FIRST day under Phase 1 (2x) and
 * transitions to Phase 2 that same evening's EOD update if the trigger
 * clears using that day's CLOSING equity — a one-day bootstrap lag, not an
 * immediate jump, by design.
 *
 * `currentEquityForSeed` may be null (equity unreadable at seed time) —
 * peak_profit then seeds at 0, the conservative (never overstates profit)
 * choice; the first EOD update corrects it from real closing equity.
 *
 * Returns null on any DB failure — the caller must skip (fail closed),
 * never guess a phase/deposit for real money.
 */
export async function getOrSeedFastStartState(
  person: string,
  accountType: 'sandbox' | 'production',
  deposit: number,
  currentEquityForSeed: number | null = null,
  bot: string = 'flame',
): Promise<FastStartStateRow | null> {
  try {
    await ensureFastStartStateTable()
    const existing = await query(
      `SELECT phase, deposit, peak_profit FROM fast_start_state WHERE person = $1 AND account_type = $2 AND bot = $3`,
      [person, accountType, bot],
    )
    if (existing.length > 0) {
      const phase = Number(existing[0].phase)
      const dep = Number(existing[0].deposit)
      const peakProfit = Number(existing[0].peak_profit)
      if ((phase !== 1 && phase !== 2) || !Number.isFinite(dep)) return null
      return { phase: phase as 1 | 2, deposit: dep, peakProfit: Number.isFinite(peakProfit) ? peakProfit : 0 }
    }
    if (!Number.isFinite(deposit) || deposit <= 0) return null
    const seedPeakProfit = currentEquityForSeed != null && Number.isFinite(currentEquityForSeed)
      ? Math.max(0, currentEquityForSeed - deposit)
      : 0
    // `bot` is APPENDED as the last column/param (not inserted mid-list) so
    // every pre-existing positional index (deposit=$3, peak_profit=$4) is
    // byte-for-byte unchanged for FLAME's own tests/callers that index into
    // this INSERT's params array.
    await query(
      `INSERT INTO fast_start_state (person, account_type, phase, deposit, peak_profit, bot, created_at, updated_at)
       VALUES ($1, $2, 1, $3, $4, $5, NOW(), NOW())
       ON CONFLICT (person, account_type, bot) DO NOTHING`,
      [person, accountType, deposit, seedPeakProfit, bot],
    )
    // Re-read rather than trust the just-inserted values: a concurrent scan
    // tick may have won the ON CONFLICT DO NOTHING race first.
    const after = await query(
      `SELECT phase, deposit, peak_profit FROM fast_start_state WHERE person = $1 AND account_type = $2 AND bot = $3`,
      [person, accountType, bot],
    )
    if (after.length === 0) return null
    const phase = Number(after[0].phase)
    const dep = Number(after[0].deposit)
    const peakProfit = Number(after[0].peak_profit)
    if ((phase !== 1 && phase !== 2) || !Number.isFinite(dep)) return null
    return { phase: phase as 1 | 2, deposit: dep, peakProfit: Number.isFinite(peakProfit) ? peakProfit : 0 }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[fast-start-db] getOrSeedFastStartState('${person}','${accountType}',bot=${bot}) failed: ${msg}`)
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
  bot: string = 'flame',
): Promise<void> {
  try {
    await ensureFastStartStateTable()
    await query(
      `UPDATE fast_start_state
         SET phase = 2, triggered_at = COALESCE(triggered_at, NOW()), updated_at = NOW()
       WHERE person = $1 AND account_type = $2 AND bot = $3 AND phase = 1`,
      [person, accountType, bot],
    )
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[fast-start-db] persistFastStartPhaseAdvance('${person}','${accountType}',bot=${bot}) failed: ${msg}`)
  }
}

export interface FastStartEodUpdateResult {
  updated: boolean
  /** false = state row doesn't exist yet (nothing to update — the account will seed on its next intraday evaluation), or already updated today (idempotent no-op), or a DB failure occurred. */
  reason: string
  phase?: 1 | 2
  peakProfit?: number
  triggeredToday?: boolean
}

/**
 * The ONE place phase/peak_profit/floor ever change, and it runs ONCE per
 * account per day, called from FLAME's own EOD hook (scanBot('flame') in
 * scanner.ts, once time >= FLAME's eod_cutoff_hhmm_ct) with that day's
 * CLOSING equity — never from an intraday sizing call. This is the fix for
 * the 2026-09-29 bug where an intraday unrealized mark could ratchet the
 * floor or flip the phase mid-day; intraday callers now pass
 * `{ skipTriggerCheck: true }` to decideFastStartSizing and read
 * peak_profit/phase from the STORED state (this table), never recomputing
 * either live.
 *
 * Idempotent: a second call the SAME trade_date (e.g. a later scan tick
 * after the EOD cutoff) is a no-op — `last_eod_date` guards it. `ebbMaxLoss`/
 * `flintMaxLoss` are that day's REAL (not estimated) per-lot/contract max
 * loss, from each leg's own actual today outcome (readEbbTodayOutcome /
 * readFlintTodayCandidacy) — by EOD both legs' entry windows have long
 * since closed, so "no row" is conclusive non-candidacy, not ambiguity.
 * `normalLadderAsOfStartOfDay` MUST be the ladder computed from the
 * PRE-update (this morning's) peak_profit — matching fast_start_floor_sim.py's
 * own `ladder = base_ladder(peak_equity)` computed BEFORE that day's pnl.
 */
export async function updateFastStartEodState(
  person: string,
  accountType: 'sandbox' | 'production',
  tradeDateCt: string,
  closingEquity: number,
  normalLadderAsOfStartOfDay: number,
  ebbCandidateToday: boolean,
  ebbMaxLossToday: number | null,
  flintCandidateToday: boolean,
  flintMaxLossToday: number | null,
  bot: string = 'flame',
): Promise<FastStartEodUpdateResult> {
  try {
    await ensureFastStartStateTable()
    const rows = await query(
      `SELECT phase, deposit, peak_profit, last_eod_date FROM fast_start_state WHERE person = $1 AND account_type = $2 AND bot = $3`,
      [person, accountType, bot],
    )
    if (rows.length === 0) return { updated: false, reason: 'no_state_row_yet' }
    const phase = Number(rows[0].phase) as 1 | 2
    const deposit = Number(rows[0].deposit)
    const priorPeakProfit = Number(rows[0].peak_profit) || 0
    const lastEodDate = rows[0].last_eod_date ? String(rows[0].last_eod_date).slice(0, 10) : null
    if (lastEodDate === tradeDateCt) {
      return { updated: false, reason: 'already_updated_today', phase, peakProfit: priorPeakProfit }
    }
    if (!Number.isFinite(deposit) || deposit <= 0 || !Number.isFinite(closingEquity)) {
      return { updated: false, reason: 'deposit_or_equity_unreadable' }
    }

    const cushion = closingEquity - deposit
    const newPeakProfit = Math.max(priorPeakProfit, cushion, 0) // ratchet — never decreases

    let nextPhase = phase
    let triggeredToday = false
    if (phase === 1) {
      const check = evaluateFastStartTrigger(
        cushion, normalLadderAsOfStartOfDay, ebbCandidateToday, ebbMaxLossToday, flintCandidateToday, flintMaxLossToday,
      )
      if (check.triggered) {
        nextPhase = 2
        triggeredToday = true
      }
    }

    // 🚨 2026-10-10 fix: reusing $4 both as `phase = $4` (inferred SMALLINT,
    // matching the column) and inside `WHEN $4 = 2` (inferred the literal's
    // default INTEGER) made Postgres reject the whole query every single
    // call with "inconsistent types deduced for parameter $4" — confirmed
    // firing every minute in production logs for Logan's SPARK sandbox
    // state, meaning this UPDATE has never once succeeded. `triggeredToday`
    // is already computed above in JS from the exact same (nextPhase===2 &&
    // phase===1) condition the SQL was trying to re-derive — pass it
    // straight through as its own parameter instead of re-expressing it
    // ambiguously in SQL.
    await query(
      `UPDATE fast_start_state
         SET peak_profit = $3, phase = $4, last_eod_date = $5,
             triggered_at = CASE WHEN $6 THEN NOW() ELSE triggered_at END,
             updated_at = NOW()
       WHERE person = $1 AND account_type = $2 AND bot = $7`,
      [person, accountType, newPeakProfit, nextPhase, tradeDateCt, triggeredToday, bot],
    )
    return { updated: true, reason: 'ok', phase: nextPhase, peakProfit: newPeakProfit, triggeredToday }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[fast-start-db] updateFastStartEodState('${person}','${accountType}',bot=${bot}) failed: ${msg}`)
    return { updated: false, reason: `error:${msg}` }
  }
}

export interface FastStartDecisionLogEntry {
  person: string
  accountType: 'sandbox' | 'production'
  /** Defaults to 'flame' — every pre-existing call site is unaffected. */
  bot?: string
  tradeDate: string // YYYY-MM-DD
  /** Which leg this row's own sizing decision is for — one row per leg per day. */
  leg: 'ebb' | 'flint'
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
  const bot = entry.bot ?? 'flame'
  try {
    await ensureFastStartDecisionLogTable()
    const baseCols =
      `person, account_type, trade_date, leg, phase, triggered_today, normal_ladder,
       ebb_contracts, flint_contracts, deposit, equity, cushion, floor_amount, budget,
       phase1_cap_budget, trigger_level, reason`
    const baseParams = [
      entry.person, entry.accountType, entry.tradeDate, entry.leg, entry.phase, entry.triggeredToday,
      entry.normalLadder, entry.ebbContracts, entry.flintContracts, entry.deposit, entry.equity, entry.cushion,
      entry.floor, entry.budget, entry.phase1CapBudget, entry.triggerLevel, entry.reason,
    ]
    // Default ('flame', or omitted) keeps the ORIGINAL 17-column INSERT text
    // and param order byte-for-byte — FLAME's own wiring tests read this
    // call's params by fixed position (leg=index 3, flint_contracts=index
    // 8, reason=the LAST element), so nothing about that shape may move.
    // A non-default bot (SPARK) gets `bot` appended as an 18th column/param
    // — a brand-new call site with no positional assumptions to preserve.
    if (bot === 'flame') {
      await query(
        `INSERT INTO fast_start_decision_log (${baseCols})
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)`,
        baseParams,
      )
    } else {
      await query(
        `INSERT INTO fast_start_decision_log (${baseCols}, bot)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)`,
        [...baseParams, bot],
      )
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[fast-start-db] logFastStartDecision('${entry.person}','${entry.accountType}',bot=${bot}) failed: ${msg}`)
  }
}

/** decision strings from logFlintDailyContext that mean "no real tradeable setup existed" — never a candidate. */
const FLINT_NON_CANDIDATE_DECISIONS = new Set(['skip:no_quote', 'skip:no_quotes', 'skip:call_credit_too_low'])

export interface FlintTodayCandidacy {
  candidateDay: boolean
  /** Per-contract max loss for today's considered strikes/credit — null when not a candidate. */
  maxLossPerContract: number | null
}

/**
 * FLINT's candidacy + max loss for TODAY, from `flint_daily_context` —
 * logged UNCONDITIONALLY every time tryOpenFlint evaluates (see
 * scanner.ts), regardless of whether FLINT actually traded. Reliable for
 * EBB's own call site because FLINT's entry ALWAYS runs before FLAME's own
 * EBB entry logic within the SAME scan tick (scanBot('flame') calls
 * closeFlintAtRiskBeforeBell/settleFlintExpired/tryOpenFlint BEFORE its own
 * put-side entry code) — so by the time EBB evaluates, today's row (if
 * any) already exists. `candidateDay=false` (with maxLossPerContract=null)
 * on no row / no quote / credit-too-low, matching the original backtest's
 * own definition (flint_maxloss_per_contract present only when candidate).
 */
export async function readFlintTodayCandidacy(tradeDate: string): Promise<FlintTodayCandidacy> {
  try {
    const rows = await query(
      `SELECT decision, call_short_strike_considered, call_long_strike_considered, entry_credit_seen
         FROM flint_daily_context
        WHERE trade_date = $1
        ORDER BY evaluated_at DESC
        LIMIT 1`,
      [tradeDate],
    )
    if (rows.length === 0) return { candidateDay: false, maxLossPerContract: null }
    const decision = String(rows[0].decision ?? '')
    if (FLINT_NON_CANDIDATE_DECISIONS.has(decision)) return { candidateDay: false, maxLossPerContract: null }
    const short = Number(rows[0].call_short_strike_considered)
    const long = Number(rows[0].call_long_strike_considered)
    const credit = Number(rows[0].entry_credit_seen)
    if (!Number.isFinite(short) || !Number.isFinite(long) || !Number.isFinite(credit)) {
      return { candidateDay: false, maxLossPerContract: null }
    }
    return { candidateDay: true, maxLossPerContract: flintMaxLoss(short, long, credit, 1) }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[fast-start-db] readFlintTodayCandidacy failed: ${msg}`)
    return { candidateDay: false, maxLossPerContract: null }
  }
}

export interface EbbTodayOutcome {
  /** false = EBB has not yet decided for today (or its window hasn't closed) — caller MUST defer, never guess. */
  known: boolean
  contracts: number
  maxLossPerLot: number | null
}

/**
 * EBB's ACTUAL outcome for TODAY, for this specific (person, accountType) —
 * read from `{bot}_positions`. FLINT's own entry always runs BEFORE EBB's
 * in the same scan tick, so FLINT can only ever see an EBB decision from an
 * EARLIER tick today (or none yet this tick). `nowIsPastEbbWindow` MUST be
 * supplied by the caller (comparing the current CT clock to EBB's own
 * entry_end/eod_cutoff) — before that time, "no row yet" is ambiguous
 * (EBB might still be about to trade) and this returns known=false so the
 * caller defers FLINT's own sizing rather than guessing; after that time,
 * "no row" is conclusive (EBB decided not to trade today) and this returns
 * known=true, contracts=0.
 */
export async function readEbbTodayOutcome(
  botName: string,
  person: string,
  accountType: 'sandbox' | 'production',
  tradeDate: string,
  nowIsPastEbbWindow: boolean,
): Promise<EbbTodayOutcome> {
  try {
    const rows = await query(
      `SELECT contracts, max_loss FROM ${botTable(botName, 'positions')}
        WHERE person = $1 AND account_type = $2 AND open_date = $3
        ORDER BY open_time DESC LIMIT 1`,
      [person, accountType, tradeDate],
    )
    if (rows.length > 0) {
      const contracts = Number(rows[0].contracts)
      const maxLoss = Number(rows[0].max_loss)
      if (Number.isFinite(contracts) && contracts > 0 && Number.isFinite(maxLoss)) {
        return { known: true, contracts, maxLossPerLot: maxLoss / contracts }
      }
    }
    return nowIsPastEbbWindow
      ? { known: true, contracts: 0, maxLossPerLot: null }
      : { known: false, contracts: 0, maxLossPerLot: null }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[fast-start-db] readEbbTodayOutcome('${person}','${accountType}') failed: ${msg}`)
    return { known: false, contracts: 0, maxLossPerLot: null }
  }
}
