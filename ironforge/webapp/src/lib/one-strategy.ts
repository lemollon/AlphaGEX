/**
 * ONE_STRATEGY — "one strategy for all the versions of FLAME and SPARK"
 * (Leron, 2026-09-28). The single shared sizing/decision module every
 * account — Leron's production account ('Flame', Tradier 6YB71371), the
 * sandbox mirrors (User/Matt/Logan), and app customers — runs through once
 * this flag is on.
 *
 * This module does NOT duplicate the rule set. It re-exports the exact pure
 * functions already shipped to app customers (#3093 and follow-ups) from
 * customer-executor/contracts.ts — evaluateDepositFloorCap,
 * evaluateFastStartUpsize, evaluateCalmUpsize, evaluateFlintCushion — and
 * adds the ONE piece those functions don't own: persistence of each
 * INTERNAL account's own (deposit, triggered, peak-equity) state, using this
 * codebase's own Postgres client (`lib/db.ts`), parallel to how
 * customer-executor/executor.ts persists the SAME shape of state in
 * customer_deposit_floor_state via customers-db.ts. Two different databases,
 * ONE decision engine.
 *
 * Default OFF (ONE_STRATEGY unset or anything other than the literal string
 * 'on'). Every caller (tradier.ts placeIcOrderAllAccounts /
 * placeCallSpreadOrderAllAccounts) is unaffected byte-for-byte when this
 * reads false — see bot-feature-coverage.ts's ONE_STRATEGY entry and the
 * kill-switch test in one-strategy.test.ts.
 *
 * The app-customer path (customer-executor/executor.ts) is NOT gated by this
 * flag — customers already run this exact package unconditionally (that is
 * what #3093 shipped). ONE_STRATEGY only changes what PRODUCTION and SANDBOX
 * internal accounts do; see the "ONE_STRATEGY" mentions in executor.ts's own
 * header for the cross-reference the bot-feature-coverage guard checks.
 */
import {
  currentFloorLevelCents,
  evaluateCalmUpsize,
  evaluateDepositFloorCap,
  evaluateFastStartUpsize,
  evaluateFlintCushion,
} from './customer-executor/contracts'

/** Master switch. Fails closed: unset or anything but the exact string 'on' reads as off. */
export function isOneStrategyMode(): boolean {
  return String(process.env.ONE_STRATEGY ?? '').trim().toLowerCase() === 'on'
}

/** The customer package's own frozen constants (customer_protection_finalK.py, ROUND 8). */
export const ONE_STRATEGY_PCT = 20
export const ONE_STRATEGY_MARGIN_CENTS = 5_000 // $50, matches MARGIN in the sim / FLINT_CUSHION_MARGIN_CENTS
export const ONE_STRATEGY_TRIGGER_N = 3
export const ONE_STRATEGY_FLOOR_K = 0.1
export const ONE_STRATEGY_CALM_VIX_CEILING = 0.70
export const ONE_STRATEGY_CALM_MIN_DEPOSIT_CENTS = 400_000

export type OneStrategyAccountType = 'production' | 'sandbox'

// ---------------------------------------------------------------------------
// Pure sizing (no I/O) — the exact sequence executor.ts's mirrorOneOpen runs
// for the app-customer main leg: desired count (pct of equity / max loss) ->
// deposit-floor cap -> B1 pre-cushion OR house-money calm-upsize post-cushion.
// ---------------------------------------------------------------------------
export interface OneStrategyHostSizingInput {
  /** Live equity/buying-power read at decision time, in cents. */
  equityCents: number | null
  /** This account's fixed deposit baseline, in cents. */
  depositCents: number | null
  /** This trade's max loss per contract (collateral for a defined-risk credit spread), in cents. */
  maxLossCentsPerContract: number
  /** Today's VIX-decay ratio, or null if unreadable. */
  vixRatio: number | null
  /** Persisted sticky trigger state, pre this evaluation. */
  triggered: boolean
  /** Persisted running peak-equity ratchet, pre this evaluation (null on first sight). */
  peakEquityCents: number | null
}

export interface OneStrategyHostSizingResult {
  /** Final contracts for the host (EBB/SPARK) leg. */
  contracts: number
  /** False = equity/maxLoss unreadable — contracts is 0, caller must skip (never guesses a size). */
  dataOk: boolean
  triggeredNow: boolean
  triggeredForSizing: boolean
  capped: boolean
  floorLevelCents: number
  nextPeakEquityCents: number
  fastStartApplied: boolean
  calmUpsizeApplied: boolean
  reason?: string
}

/**
 * The package's host-leg decision, pure. `desiredContracts` is derived HERE
 * (floor((equity * pct/100) / maxLossPerContract)) rather than taken as an
 * input — this is `customer_protection_finalK.py`'s own `m.desired_count`,
 * the same formula `sizeContracts` in contracts.ts reduces to once buying
 * power is not the binding constraint (see that function's own doc comment).
 */
export function evaluateOneStrategyHostSizing(i: OneStrategyHostSizingInput): OneStrategyHostSizingResult {
  if (
    i.equityCents == null || !Number.isFinite(i.equityCents) || i.equityCents <= 0 ||
    !Number.isFinite(i.maxLossCentsPerContract) || i.maxLossCentsPerContract <= 0
  ) {
    return {
      contracts: 0, dataOk: false, triggeredNow: false, triggeredForSizing: i.triggered, capped: false,
      floorLevelCents: i.depositCents ?? 0, nextPeakEquityCents: i.peakEquityCents ?? i.depositCents ?? 0,
      fastStartApplied: false, calmUpsizeApplied: false, reason: 'equity_or_maxloss_unreadable',
    }
  }
  const desiredContracts = Math.floor((i.equityCents * ONE_STRATEGY_PCT) / 100 / i.maxLossCentsPerContract)

  const floorResult = evaluateDepositFloorCap({
    equityCents: i.equityCents,
    depositCents: i.depositCents,
    peakEquityCents: i.peakEquityCents,
    maxLossCentsPerContract: i.maxLossCentsPerContract,
    marginCents: ONE_STRATEGY_MARGIN_CENTS,
    pct: ONE_STRATEGY_PCT,
    desiredContracts,
    triggered: i.triggered,
    triggerN: ONE_STRATEGY_TRIGGER_N,
    floorK: ONE_STRATEGY_FLOOR_K,
  })

  let contracts = floorResult.contracts
  let fastStartApplied = false
  let calmUpsizeApplied = false

  if (floorResult.dataOk) {
    if (!floorResult.triggeredForSizing) {
      // CUSTOMER_FAST_START (B1) — calm +1, pre-cushion, unconditional on deposit size.
      const b1 = evaluateFastStartUpsize({
        triggeredForSizing: floorResult.triggeredForSizing,
        baseContracts: contracts,
        vixRatio: i.vixRatio,
        vixCeiling: ONE_STRATEGY_CALM_VIX_CEILING,
      })
      if (b1.extraContract) { contracts += 1; fastStartApplied = true }
    } else {
      // CUSTOMER_CALM_UPSIZE — house-money calm +1, post-cushion, deposit >= $4,000.
      const calm = evaluateCalmUpsize({
        equityCents: i.equityCents,
        depositCents: i.depositCents,
        protectLevelCents: floorResult.floorLevelCents,
        baseContracts: contracts,
        maxLossCentsPerContract: i.maxLossCentsPerContract,
        marginCents: ONE_STRATEGY_MARGIN_CENTS,
        vixRatio: i.vixRatio,
        vixCeiling: ONE_STRATEGY_CALM_VIX_CEILING,
        minDepositCentsForUpsize: ONE_STRATEGY_CALM_MIN_DEPOSIT_CENTS,
      })
      if (calm.extraContract) { contracts += 1; calmUpsizeApplied = true }
    }
  }

  return {
    contracts,
    dataOk: floorResult.dataOk,
    triggeredNow: floorResult.triggeredNow,
    triggeredForSizing: floorResult.triggeredForSizing,
    capped: floorResult.capped,
    floorLevelCents: floorResult.floorLevelCents,
    nextPeakEquityCents: floorResult.nextPeakEquityCents,
    fastStartApplied,
    calmUpsizeApplied,
  }
}

export interface OneStrategyFlintInput {
  equityCents: number | null
  protectLevelCents: number | null
  /** The host leg's own contracts committed TODAY on this same account (planned or actual). */
  hostContracts: number
  /** The host leg's max loss per contract, in cents (same units as hostContracts). */
  hostMaxLossCentsPerContract: number
  /** FLINT's OWN worst-case max loss for the contract count being evaluated, in cents. */
  flintMaxLossCents: number
}

export interface OneStrategyFlintResult {
  eligible: boolean
  cushionCents: number | null
  reason?: string
}

/** FLINT's netted cushion check — evaluateFlintCushion with the host leg's committed risk derived here. */
export function evaluateOneStrategyFlint(i: OneStrategyFlintInput): OneStrategyFlintResult {
  const hostCommittedCents = Math.max(0, i.hostContracts) * Math.max(0, i.hostMaxLossCentsPerContract)
  const gate = evaluateFlintCushion({
    equityCents: i.equityCents,
    protectLevelCents: i.protectLevelCents,
    hostCommittedCents,
    maxLossCents: i.flintMaxLossCents,
    marginCents: ONE_STRATEGY_MARGIN_CENTS,
  })
  return { eligible: gate.eligible, cushionCents: gate.cushionCents, reason: gate.reason }
}

export interface OneStrategyFlintDecision {
  contracts: number
  eligible: boolean
  cushionCents: number | null
  reason?: string
}

/**
 * Two-candidate step-down, mirroring flint.ts's decideFlintContractsForCushion:
 * try `desired` (the possibly gamma-upsized target) first, fall back to `base`
 * if only the extra lot breaks the netted cushion — "if cushion covers 1 but
 * not 2, trade 1."
 */
export function decideOneStrategyFlintContracts(args: {
  desired: number
  base: number
  equityCents: number | null
  protectLevelCents: number | null
  hostContracts: number
  hostMaxLossCentsPerContract: number
  shortStrike: number
  longStrike: number
  credit: number
  flintMaxLossFn: (shortStrike: number, longStrike: number, credit: number, contracts: number) => number
}): OneStrategyFlintDecision {
  const candidates = args.desired > args.base ? [args.desired, args.base] : [args.desired]
  let last: OneStrategyFlintResult = { eligible: false, cushionCents: null, reason: 'bad_inputs' }
  for (const c of candidates) {
    if (c < 1) continue
    const flintMaxLossCents = Math.round(args.flintMaxLossFn(args.shortStrike, args.longStrike, args.credit, c) * 100)
    last = evaluateOneStrategyFlint({
      equityCents: args.equityCents, protectLevelCents: args.protectLevelCents,
      hostContracts: args.hostContracts, hostMaxLossCentsPerContract: args.hostMaxLossCentsPerContract,
      flintMaxLossCents,
    })
    if (last.eligible) return { contracts: c, eligible: true, cushionCents: last.cushionCents }
  }
  return { contracts: 0, eligible: false, cushionCents: last.cushionCents, reason: last.reason }
}

// ---------------------------------------------------------------------------
// Persistence for INTERNAL accounts (production 'Flame', sandbox mirrors).
// Parallel to customer_deposit_floor_state (customers-db.ts), but on THIS
// app's own Postgres (lib/db.ts) — internal accounts and app customers are
// two separate databases; the RULE is shared, the storage is not.
// ---------------------------------------------------------------------------
interface OneStrategyFloorStateRow {
  deposit_cents: string | number
  triggered: boolean
  peak_equity_cents: string | number | null
}

async function ensureOneStrategyTable(): Promise<void> {
  const { dbExecute: dbx } = await import('./db')
  await dbx(
    `CREATE TABLE IF NOT EXISTS one_strategy_floor_state (
       person TEXT NOT NULL,
       account_type TEXT NOT NULL,
       bot_name TEXT NOT NULL,
       deposit_cents BIGINT NOT NULL,
       triggered BOOLEAN NOT NULL DEFAULT FALSE,
       trigger_date DATE,
       peak_equity_cents BIGINT,
       last_equity_cents BIGINT,
       updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
       PRIMARY KEY (person, account_type, bot_name)
     )`,
  )
}

/**
 * Read-or-seed the persisted state row, WITHOUT ratcheting peak-equity or
 * evaluating today's trigger — a pure "does a row exist" fetch. Used by
 * `planOneStrategyHostContracts` (FLINT's planning read, which must never
 * mutate the state the host leg's own REAL call will evaluate later in the
 * same scan tick) as well as internally by `applyOneStrategyHostFloor`.
 */
async function getOrSeedOneStrategyFloorState(
  person: string,
  accountType: OneStrategyAccountType,
  botName: string,
  depositCents: number,
): Promise<{ depositCents: number; triggered: boolean; peakEquityCents: number | null } | null> {
  try {
    const { query: dbq, dbExecute: dbx } = await import('./db')
    await ensureOneStrategyTable()
    let rows = await dbq(
      `SELECT deposit_cents, triggered, peak_equity_cents FROM one_strategy_floor_state
        WHERE person = $1 AND account_type = $2 AND bot_name = $3`,
      [person, accountType, botName],
    ) as OneStrategyFloorStateRow[]
    if (rows.length === 0) {
      await dbx(
        `INSERT INTO one_strategy_floor_state (person, account_type, bot_name, deposit_cents, triggered, peak_equity_cents)
         VALUES ($1, $2, $3, $4, FALSE, $4)
         ON CONFLICT (person, account_type, bot_name) DO NOTHING`,
        [person, accountType, botName, Math.round(depositCents)],
      )
      rows = await dbq(
        `SELECT deposit_cents, triggered, peak_equity_cents FROM one_strategy_floor_state
          WHERE person = $1 AND account_type = $2 AND bot_name = $3`,
        [person, accountType, botName],
      ) as OneStrategyFloorStateRow[]
    }
    const row = rows[0]
    if (!row) return null
    return {
      depositCents: Math.floor(Number(row.deposit_cents)),
      triggered: Boolean(row.triggered),
      peakEquityCents: row.peak_equity_cents != null ? Math.floor(Number(row.peak_equity_cents)) : null,
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[one-strategy] getOrSeedOneStrategyFloorState(${person}, ${accountType}, ${botName}) failed: ${msg}`)
    return null
  }
}

export interface ApplyOneStrategyHostFloorArgs {
  person: string
  accountType: OneStrategyAccountType
  botName: string
  /** This account's fixed deposit baseline, in cents — seeds the row on first sight only. */
  depositCents: number
  equityCents: number | null
  maxLossCentsPerContract: number
  vixRatio: number | null
}

/**
 * The REAL, mutating host-leg call: read-or-seed state, run the pure sizing,
 * persist the trigger/peak-equity ratchet. This is what tradier.ts's EBB/SPARK
 * sizing branches call under ONE_STRATEGY=on — the exact counterpart of
 * customer-executor/executor.ts's `applyDepositFloor` + the B1/calm-upsize
 * block in `mirrorOneOpen`, for an internal account instead of a customer's
 * SnapTrade-linked one.
 */
/**
 * KNOWN LIMITATION (documented, not hidden): `customer_protection_finalK.py`'s
 * own simulation ratchets peak-equity EVERY calendar day, whether or not the
 * host leg traded that day (a FLINT-only day still moves equity). This
 * function's ratchet only runs when it is actually CALLED — i.e. only on days
 * the host leg (EBB/SPARK) is itself a candidate and tradier.ts invokes it —
 * because production/sandbox have no day-independent EOD hook the customer
 * package's simulation assumes (unlike fast-start-db.ts's updateFastStartEodState,
 * which IS wired to a real once-daily hook in scanner.ts). A FLINT-only day's
 * equity gain is therefore captured on the NEXT host-candidate day's call
 * instead of same-day. This is the CONSERVATIVE direction — it can only delay
 * the floor triggering or delay a peak-profit-driven floor increase, never
 * advance either early — and only bites on the narrow path where equity rises
 * on a FLINT-only day and then falls back before the next EBB/SPARK candidate
 * day. The underlying decision math (evaluateOneStrategyHostSizing /
 * evaluateOneStrategyFlint) is proven byte-identical to the sim in
 * one-strategy.test.ts; this note is about persistence CADENCE, not the rule
 * itself. Flagged for the coordinator; closing it fully means adding a real
 * EOD hook for ONE_STRATEGY the way fast-start-db.ts already has for
 * FLAME_FAST_START.
 */
export async function applyOneStrategyHostFloor(args: ApplyOneStrategyHostFloorArgs): Promise<OneStrategyHostSizingResult> {
  const state = await getOrSeedOneStrategyFloorState(args.person, args.accountType, args.botName, args.depositCents)
  if (state == null) {
    return {
      contracts: 0, dataOk: false, triggeredNow: false, triggeredForSizing: false,
      capped: false, floorLevelCents: args.depositCents, nextPeakEquityCents: args.depositCents,
      fastStartApplied: false, calmUpsizeApplied: false, reason: 'state_unreadable',
    }
  }
  const result = evaluateOneStrategyHostSizing({
    equityCents: args.equityCents,
    depositCents: state.depositCents,
    maxLossCentsPerContract: args.maxLossCentsPerContract,
    vixRatio: args.vixRatio,
    triggered: state.triggered,
    peakEquityCents: state.peakEquityCents,
  })
  if (!result.dataOk) return result

  try {
    const { dbExecute: dbx } = await import('./db')
    await dbx(
      `UPDATE one_strategy_floor_state
          SET triggered = triggered OR $4,
              trigger_date = COALESCE(trigger_date, CASE WHEN $4 THEN CURRENT_DATE END),
              peak_equity_cents = $5, last_equity_cents = $6, updated_at = now()
        WHERE person = $1 AND account_type = $2 AND bot_name = $3`,
      [args.person, args.accountType, args.botName, result.triggeredNow, result.nextPeakEquityCents, args.equityCents],
    )
  } catch (err: unknown) {
    console.error(`[one-strategy] applyOneStrategyHostFloor persist failed for ${args.person}/${args.accountType}/${args.botName} (result still returned):`, err instanceof Error ? err.message : err)
  }
  return result
}

export interface PlanOneStrategyHostContractsArgs {
  person: string
  accountType: OneStrategyAccountType
  botName: string
  depositCents: number
  equityCents: number | null
  /** A CONSERVATIVE (largest plausible) host max-loss-per-contract estimate, in cents — FLINT's
   *  entry runs before the host leg's own real quote is available this same tick (see
   *  tradier.ts's FLAME_FAST_START planning block for the established pattern this mirrors). */
  maxLossCentsPerContract: number
  vixRatio: number | null
}

/**
 * READ-ONLY plan of what the host leg's ONE_STRATEGY sizing WOULD produce
 * today, for FLINT's netting check. Never mutates persisted state — the
 * host leg's own real call (`applyOneStrategyHostFloor`, which runs later in
 * the same scan tick) is the only writer. Returns null only on a DB read
 * failure (never fabricates a plan); the caller must treat that as "assume
 * zero host contracts committed" is UNSAFE and skip FLINT instead.
 */
export async function planOneStrategyHostContracts(args: PlanOneStrategyHostContractsArgs): Promise<OneStrategyHostSizingResult | null> {
  const state = await getOrSeedOneStrategyFloorState(args.person, args.accountType, args.botName, args.depositCents)
  if (state == null) return null
  return evaluateOneStrategyHostSizing({
    equityCents: args.equityCents,
    depositCents: state.depositCents,
    maxLossCentsPerContract: args.maxLossCentsPerContract,
    vixRatio: args.vixRatio,
    triggered: state.triggered,
    peakEquityCents: state.peakEquityCents,
  })
}

/** Re-export for callers that only need the ratcheted level (e.g. logging), matching contracts.ts's own helper. */
export { currentFloorLevelCents }
