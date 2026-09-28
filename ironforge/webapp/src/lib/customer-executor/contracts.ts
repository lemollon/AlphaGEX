/**
 * Customer order executor — the PURE math and encoding layer (Phase B, 7/31).
 *
 * No I/O, no clock. The executor's networked layer (SnapTrade placement) and the
 * scanner hook build on these; keeping them pure makes the money math testable
 * without a database or a broker.
 */

/** OCC 21-character option symbol: ROOT(6, space-padded) + YYMMDD + C/P + strike*1000 (8 digits). */
export function occSymbol(root: string, expiration: string, right: 'C' | 'P', strike: number): string {
  const r = root.toUpperCase().padEnd(6, ' ')
  const [y, m, d] = expiration.split('-')
  if (!y || !m || !d) throw new Error(`bad expiration: ${expiration}`)
  const yymmdd = `${y.slice(2)}${m}${d}`
  const k = Math.round(strike * 1000)
  if (!Number.isFinite(k) || k <= 0) throw new Error(`bad strike: ${strike}`)
  return `${r}${yymmdd}${right}${String(k).padStart(8, '0')}`
}

export interface CondorLegs {
  ticker: string
  expiration: string // YYYY-MM-DD
  putShort: number
  putLong: number
  callShort: number
  callLong: number
}

export interface SpreadLegs {
  ticker: string
  expiration: string
  short: number
  long: number
  right: 'C' | 'P'
}

export interface MlegLegSpec {
  symbol: string
  action: 'BUY_TO_OPEN' | 'SELL_TO_OPEN' | 'BUY_TO_CLOSE' | 'SELL_TO_CLOSE'
  units: number
}

/** Iron condor OPEN: sell the inner strikes, buy the wings. Net credit. */
export function condorOpenLegs(p: CondorLegs, contracts: number): MlegLegSpec[] {
  return [
    { symbol: occSymbol(p.ticker, p.expiration, 'P', p.putShort), action: 'SELL_TO_OPEN', units: contracts },
    { symbol: occSymbol(p.ticker, p.expiration, 'P', p.putLong), action: 'BUY_TO_OPEN', units: contracts },
    { symbol: occSymbol(p.ticker, p.expiration, 'C', p.callShort), action: 'SELL_TO_OPEN', units: contracts },
    { symbol: occSymbol(p.ticker, p.expiration, 'C', p.callLong), action: 'BUY_TO_OPEN', units: contracts },
  ]
}

/** Iron condor CLOSE: buy back the shorts, sell the wings. Net debit. */
export function condorCloseLegs(p: CondorLegs, contracts: number): MlegLegSpec[] {
  return [
    { symbol: occSymbol(p.ticker, p.expiration, 'P', p.putShort), action: 'BUY_TO_CLOSE', units: contracts },
    { symbol: occSymbol(p.ticker, p.expiration, 'P', p.putLong), action: 'SELL_TO_CLOSE', units: contracts },
    { symbol: occSymbol(p.ticker, p.expiration, 'C', p.callShort), action: 'BUY_TO_CLOSE', units: contracts },
    { symbol: occSymbol(p.ticker, p.expiration, 'C', p.callLong), action: 'SELL_TO_CLOSE', units: contracts },
  ]
}

/** Two-leg credit spread OPEN (e.g. FLAME put credit spread). */
export function spreadOpenLegs(p: SpreadLegs, contracts: number): MlegLegSpec[] {
  return [
    { symbol: occSymbol(p.ticker, p.expiration, p.right, p.short), action: 'SELL_TO_OPEN', units: contracts },
    { symbol: occSymbol(p.ticker, p.expiration, p.right, p.long), action: 'BUY_TO_OPEN', units: contracts },
  ]
}

export function spreadCloseLegs(p: SpreadLegs, contracts: number): MlegLegSpec[] {
  return [
    { symbol: occSymbol(p.ticker, p.expiration, p.right, p.short), action: 'BUY_TO_CLOSE', units: contracts },
    { symbol: occSymbol(p.ticker, p.expiration, p.right, p.long), action: 'SELL_TO_CLOSE', units: contracts },
  ]
}

export interface SizingInput {
  /** Live option buying power at placement time, in cents. NULL/unknown sizes to zero. */
  buyingPowerCents: number | null
  /** The customer's authorized ceiling from their agent config, in cents. */
  maxDeploymentCents: number
  /** Distance between short and long strike, in dollars (per the master position). */
  spreadWidth: number
  /** Net credit per 1-lot in dollars (the master's fill; customer fills may differ). */
  creditPerSpread: number
}

export interface SizingResult {
  contracts: number
  collateralPerSpreadCents: number
  reason?: 'buying_power_unreadable' | 'no_buying_power' | 'below_one_contract' | 'bad_inputs'
}

/**
 * Contracts = floor(deployable / collateral-per-spread).
 *
 * Deployable = min(live buying power, authorized ceiling): the config caps deployment,
 * the account caps reality, and the smaller number always wins. Collateral for a
 * defined-risk spread = width − credit (×100). Fails to ZERO on anything unknown —
 * a sizing error must never round UP into a bigger position.
 */
export function sizeContracts(s: SizingInput): SizingResult {
  const width = Number(s.spreadWidth)
  const credit = Number(s.creditPerSpread)
  if (!Number.isFinite(width) || width <= 0 || !Number.isFinite(credit) || credit < 0 || credit >= width) {
    return { contracts: 0, collateralPerSpreadCents: 0, reason: 'bad_inputs' }
  }
  const collateral = Math.round((width - credit) * 100) * 100 // dollars → cents, per contract (×100 shares)
  // Both cases size to zero, but they are NOT the same event and must not share
  // a reason: null means the broker never told us (retry/alert), <= 0 means the
  // broker answered and the account is genuinely out of room (a real state).
  // Conflating them is what hid the 2026-08-31 FLAME live-order drop.
  if (s.buyingPowerCents == null) {
    return { contracts: 0, collateralPerSpreadCents: collateral, reason: 'buying_power_unreadable' }
  }
  if (s.buyingPowerCents <= 0) {
    return { contracts: 0, collateralPerSpreadCents: collateral, reason: 'no_buying_power' }
  }
  const deployable = Math.min(s.buyingPowerCents, Math.max(0, s.maxDeploymentCents))
  const contracts = Math.floor(deployable / collateral)
  if (contracts < 1) return { contracts: 0, collateralPerSpreadCents: collateral, reason: 'below_one_contract' }
  return { contracts, collateralPerSpreadCents: collateral }
}

/**
 * SAME conservative wing/credit assumption tradier.ts's FLAME_FAST_START
 * planning block uses for the internal path ($2 wing at EBB's own $0.10
 * minimum credit floor — the worst plausible, hence largest, per-contract
 * loss a real quote would produce). Exported here, not just local, so the
 * planning function below and its tests share the exact same numbers the
 * internal path already ships with.
 */
export const HOST_LEG_PLAN_WING_WIDTH_ESTIMATE = 2
export const HOST_LEG_PLAN_MIN_CREDIT_FLOOR_ESTIMATE = 0.10

export interface PlannedHostRiskInputs {
  /** True only when the host leg's OWN VIX-decay gate (the same deterministic,
   *  prior-close-based check the real EBB/SPARK entry uses) has already
   *  passed for today. False (host leg cannot trade today) or the gate
   *  itself being unreadable must both resolve to 0 here, never a guess. */
  vixCandidateDay: boolean
  /** Fresh live balance — the SAME read FLINT's own cushion check already
   *  performs; never a second broker call. */
  equityCents: number | null
  /** This customer's own max_deployment_pct (config_json) — the SAME pct
   *  the real host-leg sizeContracts() call will use today. */
  maxDeploymentPct: number | null
  /** True when EITHER CUSTOMER_FAST_START or CUSTOMER_CALM_UPSIZE is armed.
   *  Deliberately NOT narrowed to which VIX-ratio/trigger regime actually
   *  applies today — FLINT's own inputs don't cleanly expose the host
   *  leg's VIX ratio. Treating the upsize as "always possible" whenever
   *  either flag is on is the safe-direction approximation: it can only
   *  make this an OVERESTIMATE of risk, never an underestimate. */
  possibleUpsize: boolean
}

/**
 * WORST-CASE dollar estimate (in cents) of what the customer's own main leg
 * (EBB/SPARK put spread) could commit TODAY — computed WITHOUT reading
 * customer_positions, because scanner.ts's tryOpenFlint (which leads to
 * FLINT's customer mirror) always runs BEFORE the host leg's own entry
 * (tryOpenTrade) in the same scan tick. A real DB read sees nothing yet on
 * the exact day this estimate matters most: the host leg's first entry of
 * a fresh hold, with no prior-day row to find.
 *
 * Mirrors tradier.ts's FLAME_FAST_START planning block in spirit (same
 * conservative assumption, same "0 when the host leg simply cannot trade
 * today" short-circuit, same never-under-claim philosophy) without sharing
 * its literal code — the internal ladder and this buying-power sizing
 * compute contract count in fundamentally different ways.
 *
 * Deliberately ignores the deposit floor's own downward cap: a cap can
 * only SHRINK the real contract count, so ignoring it keeps this an upper
 * bound, which is the safe direction for a risk-netting check.
 *
 * XSP_SWAP extension point: when the XSP leg-swap lands, the fixed SPY
 * wing/credit assumption above will need an XSP-priced variant. No such
 * input exists on main as of this function; not plumbed here.
 */
export function estimatePlannedHostRiskCents(inputs: PlannedHostRiskInputs): number {
  if (!inputs.vixCandidateDay) return 0
  const { equityCents, maxDeploymentPct } = inputs
  if (equityCents == null || !Number.isFinite(equityCents) || equityCents <= 0) return 0
  if (maxDeploymentPct == null || !Number.isFinite(maxDeploymentPct) || maxDeploymentPct <= 0 || maxDeploymentPct > 100) return 0

  const maxDeploymentCents = Math.floor((equityCents * maxDeploymentPct) / 100)
  const sizing = sizeContracts({
    buyingPowerCents: equityCents,
    maxDeploymentCents,
    spreadWidth: HOST_LEG_PLAN_WING_WIDTH_ESTIMATE,
    creditPerSpread: HOST_LEG_PLAN_MIN_CREDIT_FLOOR_ESTIMATE,
  })
  if (sizing.contracts < 1) return 0
  const contracts = sizing.contracts + (inputs.possibleUpsize ? 1 : 0)
  return contracts * sizing.collateralPerSpreadCents
}

export interface MirrorGateInput {
  /** Executor master switch (env CUSTOMER_EXECUTOR_ENABLED === 'true'). Ships DISARMED. */
  executorArmed: boolean
  /** Platform/agent kill switch (production pause). Unknown reads as engaged. */
  killSwitchEngaged: boolean
  /** Subscription status for this customer+agent ('trialing' | 'active' | 'past_due' | ...). */
  subscriptionStatus: string | null
  /** The customer's own pause (activations.paused_at set). */
  customerPaused: boolean
  /** Latest activation exists and is active. */
  activationActive: boolean
  /** Broker connection healthy. */
  connectionActive: boolean
}

/** Statuses that may receive NEW orders. past_due pauses new orders (§11) but never blocks closes. */
const OPENABLE_STATUSES = new Set(['trialing', 'active'])

export type MirrorGateVerdict =
  | { allow: true }
  | { allow: false; reason: 'disarmed' | 'kill_switch' | 'subscription' | 'customer_paused' | 'not_activated' | 'connection' }

/**
 * May a NEW position be opened for this customer? FAILS CLOSED on every input.
 * CLOSES are deliberately NOT gated by subscription/pause: an open position must
 * always be closeable, or a pause would strand real risk in the account.
 */
export function canOpenForCustomer(g: MirrorGateInput): MirrorGateVerdict {
  if (!g.executorArmed) return { allow: false, reason: 'disarmed' }
  if (g.killSwitchEngaged !== false) return { allow: false, reason: 'kill_switch' }
  if (!g.activationActive) return { allow: false, reason: 'not_activated' }
  if (g.customerPaused) return { allow: false, reason: 'customer_paused' }
  if (!g.subscriptionStatus || !OPENABLE_STATUSES.has(g.subscriptionStatus)) {
    return { allow: false, reason: 'subscription' }
  }
  if (!g.connectionActive) return { allow: false, reason: 'connection' }
  return { allow: true }
}

/**
 * FLINT customer mirroring (CUSTOMER_FLINT) — the "profits-only" cushion gate.
 *
 * Ported from `customer_protection_sim.py`'s P3 arm, then corrected in ROUND 8
 * (`customer_protection_finalK.py`, frozen 2026-09-28 — see the file doc there for the
 * exact bug write-up): a customer's FLINT mirror trades ONLY when its own max loss is
 * fully covered by cushion ALREADY BUILT, NET of what the host leg's own `n` contracts
 * already committed that SAME day —
 *   remaining = equity - protectLevel - hostCommittedCents
 *   eligible  = remaining >= maxLossCents + marginCents
 * By construction FLINT can never, on its own OR combined with the host leg's worst
 * case, be the trade(s) that push the account below its protected level.
 * `hostCommittedCents` = that day's host `n * maxLossPerContract` (0 when the host
 * didn't trade, or when CUSTOMER_DEPOSIT_FLOOR is off and there's no tracked floor —
 * pass 0, never omit it: ROUND 8 found the un-netted check breaches 0.5-1.1% of paths
 * once the floor tightens (K>0), a flaw invisible at K=0's looser budget). This netting
 * runs UNCONDITIONALLY, independent of whether the deposit floor is engaged — see
 * executor.ts's mirrorOneFlintOpen for how `hostCommittedCents` and `protectLevelCents`
 * are sourced when the floor is off vs on.
 *
 * `protectLevel` is `depositCents` when the floor hasn't triggered (or is off), and the
 * floor's own `floorLevelCents` (see evaluateDepositFloorCap) once triggered.
 *
 * ONE DELIBERATE DIFFERENCE FROM THE SIM, per Leron's explicit instruction (not present
 * in the sim's ORIGINAL P3 formula, which had no margin term at all — ROUND 8's finalK.py
 * DOES add a $50 margin to FLINT's own threshold, confirming this instruction converged
 * with the sim's own later correction): `marginCents` pads the required cushion. Pass
 * `marginCents: 0` to reproduce the ORIGINAL P3 rule exactly (see the parity test).
 *
 * FAILS CLOSED: a null/unreadable equity or deposit reading is never treated as
 * "cushion covers it" — it skips, the same invariant as sizeContracts/canOpenForCustomer.
 */
export interface FlintCushionInput {
  /** Live account equity read at mirror time, in cents. NULL = broker read failed. */
  equityCents: number | null
  /** The customer's protected level, in cents (deposit, or floorLevelCents once triggered). NULL = unknown. */
  protectLevelCents: number | null
  /** The host leg's own committed max loss TODAY (n_host * maxLossPerContract), in cents. 0 when none. */
  hostCommittedCents: number
  /** FLINT's own worst-case max loss for exactly 1 contract, in cents. */
  maxLossCents: number
  /** Extra required cushion beyond raw max loss, in cents (live-only; the ORIGINAL P3 rule uses 0). */
  marginCents: number
}

export interface FlintCushionResult {
  eligible: boolean
  cushionCents: number | null
  reason?: 'bad_inputs' | 'equity_unreadable' | 'deposit_unknown' | 'cushion_insufficient'
}

/**
 * CUSTOMER_DEPOSIT_FLOOR (CUSTOMER_PROFIT_FLOOR in spirit — flag name kept for
 * continuity) — the profit-protection floor, ROUND 8's shipped rule:
 * K=0.1, N=3, variant G (`customer_protection_finalK.py`, frozen 2026-09-28,
 * `customer_package_fixtures_K.json`). This REPLACES the ROUND 3/K=0/variant-S rule:
 * Leron's actual requirement, restated precisely in finalK.py's own docstring —
 * "the customer never loses ALL profits after a win streak; they may lose some but
 * not all, keeping them in the green." K=0 only protected the deposit (100% of
 * profit could still be given back); K=0.1 protects 10% of peak profit too.
 *
 * Floor level (ratchets up only, once triggered):
 *   peakProfit = max(peakEquity - deposit, 0)     // peakEquity = the running max of
 *                                                  // ACTUAL equity ever observed,
 *                                                  // ratcheted once per day (the one
 *                                                  // trade-decision point) from a live
 *                                                  // broker read — "EOD only", never
 *                                                  // recomputed from an intraday value
 *   floorLevel = max(deposit, deposit + K * peakProfit)   // = deposit + K*peakProfit, K>=0
 * Trigger (one-way, sticky — `triggered` never resets once true): the FIRST day
 * `equity - deposit >= N * (desired_count(deposit, pct, ml) * ml)` — "3x one day's
 * own max loss AT THE CUSTOMER'S NORMAL SIZING, referenced off the FIXED deposit
 * (never off the moving equity)" — unchanged from ROUND 3.
 *
 * Post-trigger sizing, variant G ("minimum layer gated on DEPOSIT only, extra layer
 * gated on the stricter floor budget" — can give back down to deposit on a thin day,
 * never down to floorLevel, for the FIRST contract only):
 *   mlEff = maxLossCentsPerContract + marginCents
 *   nMin  = 1 if (equity - deposit) >= mlEff else 0
 *   budgetAfterMin = (equity - floorLevel) - nMin*mlEff
 *   extra = clamp(desiredContracts - nMin, 0, floor(max(budgetAfterMin,0) / mlEff))
 *   n = nMin + extra
 * Pre-trigger: `desiredContracts` passes through UNCHANGED — byte-identical to BASE
 * (B1/CUSTOMER_FAST_START may still add +1 on top — see evaluateFastStartUpsize).
 *
 * FAILS OPEN on missing data, unlike every other gate in this file: the spec (Leron,
 * "Missing data -> today's sizing, logged") is deliberate here, because this is a
 * PROTECTIVE cap on the customer's PRIMARY leg — an unreadable equity/deposit means
 * "cannot evaluate the floor," and the least-surprising fallback is today's normal
 * sizing, not blocking the trade. The caller MUST log `dataOk: false`.
 */
export interface DepositFloorInput {
  /** Live equity/buying-power at decision time (reuse the SAME read sizeContracts uses — no extra broker call). */
  equityCents: number | null
  /** Fixed baseline, in cents (today: broker_accounts.buying_power_cents captured at connect — same proxy as FLINT's). */
  depositCents: number | null
  /** Persisted running max of actual equity ever observed for this customer+bot, PRE this call's update. Null/first-sight -> treated as depositCents (no peak yet). */
  peakEquityCents: number | null
  /** Today's max loss per contract, in cents (reuse sizing.collateralPerSpreadCents — a defined-risk credit spread's max loss equals its collateral). */
  maxLossCentsPerContract: number
  /** $50/contract margin in the post-trigger budget check only (matches the sim's MARGIN=50). */
  marginCents: number
  /** Customer's own max_deployment_pct (e.g. 20), NOT a fraction — same units as agent_configs.config_json.max_deployment_pct. */
  pct: number
  /** The count sizeContracts already computed from real buying power — the "normal" count this floor caps. */
  desiredContracts: number
  /** Persisted sticky state from customer_deposit_floor_state. */
  triggered: boolean
  /** N in the trigger formula — 3, frozen since ROUND 3. */
  triggerN: number
  /** K in the floor formula — 0.1, the ROUND 8 shipped winner. */
  floorK: number
}

export interface DepositFloorResult {
  /** Final contracts to place. Equals desiredContracts verbatim when not triggered or when dataOk is false. */
  contracts: number
  /** True iff the trigger condition fires on THIS evaluation (caller persists trigger_date once). */
  triggeredNow: boolean
  /** True iff the floor actually reduced contracts below desiredContracts. */
  capped: boolean
  /** False = the floor could not be evaluated (missing/bad data) — contracts falls back to desiredContracts, caller must log this. */
  dataOk: boolean
  /**
   * True iff THIS evaluation used the post-trigger (capped) branch — i.e. `triggered ||
   * triggeredNow`. Callers use this to decide which calm-day add-on applies: B1
   * (evaluateFastStartUpsize) when false, the house-money calm-upsize
   * (evaluateCalmUpsize) when true — the two are mutually exclusive by construction,
   * never both on the same day.
   */
  triggeredForSizing: boolean
  /**
   * The protect_level to use for FLINT's netted cushion check and for
   * evaluateCalmUpsize THIS day: `depositCents` pre-trigger, `deposit + K*peakProfit`
   * once triggered. Always populated when dataOk (falls back to depositCents, or 0
   * when even that is unknown, when !dataOk — callers must check dataOk first).
   */
  floorLevelCents: number
  /** The updated peak-equity ratchet to persist for NEXT time (max(peakEquityCents, equityCents)). Only meaningful when dataOk. */
  nextPeakEquityCents: number
}

/**
 * The floor level RIGHT NOW, given persisted state — `depositCents` pre-trigger,
 * `depositCents + floorK * max(peakEquityCents - depositCents, 0)` once triggered.
 * Exposed so FLINT's mirror (a separate function, evaluated later in the day than the
 * host leg) can derive today's protect_level from the SAME persisted
 * customer_deposit_floor_state row the host leg's own call already ratcheted, without
 * re-running the full sizing/trigger logic (FLINT doesn't size the host leg).
 */
export function currentFloorLevelCents(depositCents: number, peakEquityCents: number | null, triggered: boolean, floorK: number): number {
  if (!triggered) return depositCents
  const peak = peakEquityCents ?? depositCents
  const peakProfit = Math.max(peak - depositCents, 0)
  return depositCents + floorK * peakProfit
}

export function evaluateDepositFloorCap(i: DepositFloorInput): DepositFloorResult {
  if (
    i.equityCents == null || !Number.isFinite(i.equityCents) ||
    i.depositCents == null || !Number.isFinite(i.depositCents) ||
    !Number.isFinite(i.maxLossCentsPerContract) || i.maxLossCentsPerContract <= 0 ||
    !Number.isFinite(i.pct) || i.pct <= 0 ||
    !Number.isFinite(i.desiredContracts) || i.desiredContracts < 0
  ) {
    return {
      contracts: Math.max(0, i.desiredContracts || 0), triggeredNow: false, capped: false, dataOk: false,
      triggeredForSizing: i.triggered, floorLevelCents: i.depositCents ?? 0, nextPeakEquityCents: i.peakEquityCents ?? i.depositCents ?? 0,
    }
  }

  let triggered = i.triggered
  let triggeredNow = false
  if (!triggered) {
    const dcountRef = Math.floor((i.depositCents * i.pct) / 100 / i.maxLossCentsPerContract)
    const combinedMl = dcountRef * i.maxLossCentsPerContract
    const cushion = i.equityCents - i.depositCents
    if (combinedMl > 0 && cushion >= i.triggerN * combinedMl) {
      triggered = true
      triggeredNow = true
    }
  }

  // Ratchet uses the PRIOR peak (before today's equity) — matches the sim computing
  // peak_profit from `peak_equity` before adding today's pnl. The caller persists
  // nextPeakEquityCents for tomorrow's call.
  const priorPeak = i.peakEquityCents ?? i.depositCents
  const nextPeakEquityCents = Math.max(priorPeak, i.equityCents)

  if (!triggered) {
    return {
      contracts: i.desiredContracts, triggeredNow: false, capped: false, dataOk: true,
      triggeredForSizing: false, floorLevelCents: i.depositCents, nextPeakEquityCents,
    }
  }

  const floorLevelCents = currentFloorLevelCents(i.depositCents, priorPeak, true, i.floorK)
  const mlEff = i.maxLossCentsPerContract + i.marginCents

  const budgetDep = i.equityCents - i.depositCents
  const nMin = budgetDep >= mlEff ? 1 : 0
  const budgetAfterMin = (i.equityCents - floorLevelCents) - nMin * mlEff
  const extra = Math.max(0, Math.min(Math.max(i.desiredContracts - nMin, 0), Math.floor(Math.max(budgetAfterMin, 0) / mlEff)))
  const n = nMin + extra

  return {
    contracts: n, triggeredNow, capped: n < i.desiredContracts, dataOk: true,
    triggeredForSizing: true, floorLevelCents, nextPeakEquityCents,
  }
}

/**
 * CUSTOMER_FAST_START (B1) — calm-day (VIX-decay ratio <= 0.70) +1 contract on the
 * EBB/SPARK host leg, PRE-cushion ONLY, ALL deposits, BOTH bots. Ported exactly from
 * `customer_protection_fastcushion.py`'s "B1 calm+1" arm and confirmed unchanged in
 * `customer_protection_final_package.py` (ROUND 7, "one rule everywhere" — Leron:
 * "ship B1 on SPARK too"). Deliberately NOT house-money-gated: pre-cushion is, by the
 * existing design, the unprotected phase (the deposit floor hasn't engaged yet) — B1
 * trades faster INTO that same unprotected exposure, honestly, not hidden behind a
 * gate that would change what's being measured. Mutually exclusive with the
 * house-money calm-upsize (evaluateCalmUpsize): only one applies per day, decided by
 * `DepositFloorResult.triggeredForSizing` (false -> B1, true -> calm-upsize).
 */
export interface FastStartUpsizeInput {
  /** Must be the PRE-trigger regime (DepositFloorResult.triggeredForSizing === false) — see doc above. */
  triggeredForSizing: boolean
  /** Today's contracts before this add-on (the plain desired_count(equity,pct,ml) result). No add-on if <= 0. */
  baseContracts: number
  vixRatio: number | null
  /** 0.70 — the frozen "calm" threshold, same constant evaluateCalmUpsize uses. */
  vixCeiling: number
}

export interface FastStartUpsizeResult {
  extraContract: boolean
  reason: 'added' | 'post_trigger' | 'base_zero' | 'vix_unavailable' | 'not_calm'
}

export function evaluateFastStartUpsize(i: FastStartUpsizeInput): FastStartUpsizeResult {
  if (i.triggeredForSizing) return { extraContract: false, reason: 'post_trigger' }
  if (!Number.isFinite(i.baseContracts) || i.baseContracts <= 0) return { extraContract: false, reason: 'base_zero' }
  if (i.vixRatio == null || !Number.isFinite(i.vixRatio)) return { extraContract: false, reason: 'vix_unavailable' }
  if (!(i.vixRatio <= i.vixCeiling)) return { extraContract: false, reason: 'not_calm' }
  return { extraContract: true, reason: 'added' }
}

/**
 * CUSTOMER_CALM_UPSIZE — house-money-only +1 contract on the EBB/SPARK host leg on a
 * calm day (VIX-decay ratio <= 0.70), ported from `customer_protection_calmday.py`
 * ROUND 4, still exactly this formula in ROUND 8's `customer_protection_finalK.py`
 * (frozen 2026-09-28). Deposit >= $4,000 only: Round 4 found FLAME $2,000 nets
 * NEGATIVE on both median and p10 (the thin deposit means calm-day upsizing eats into
 * the same cushion the floor is protecting), while $4,242/$5,000/$7,500 all add money.
 *
 * Gate (the sim's OWN, exact formula — it shipped with a caught bug, fixed before
 * reporting: the +1 is not an independent bet, it shares the SAME day's per-contract
 * loss as the base position, so its risk is ADDITIVE, not separate):
 *   remainingAfterBase = (equity - protectLevel) - baseContracts * maxLossCentsPerContract
 *   eligible = remainingAfterBase >= (maxLossCentsPerContract + marginCents)
 * `protectLevel` = `floorLevelCents` from evaluateDepositFloorCap (this arm only runs
 * post-trigger, so the floor has always engaged by the time this is checked) — NOT
 * the raw deposit once K>0 (ROUND 8 raised K from 0 to 0.1, so protectLevel now grows
 * with peak profit; passing raw deposit here after ROUND 8 would UNDER-protect).
 * `depositCents` is used ONLY for the $4,000 eligibility threshold below, a separate
 * concept from protectLevel. One NOTE on the source: the coordinator's own restatement
 * of the netting formula uses `(maxLoss + margin)` per base contract rather than the
 * sim's `maxLoss` per contract — this function follows the SIM's literal code
 * (`customer_protection_calmday.py` lines 74-80, confirmed unchanged in finalK.py),
 * the frozen, tested, reported rule; the coordinator's paraphrase was imprecise.
 *
 * `baseContracts` MUST be the count AFTER the deposit-floor cap (evaluateDepositFloorCap)
 * has already run — the sim computes calm-day eligibility using that same day's final
 * (floor-capped) `n`, not the pre-floor desired count.
 */
export interface CalmUpsizeInput {
  equityCents: number | null
  /** The customer's deposit baseline — used ONLY for the $4,000 threshold check, never the netting formula. */
  depositCents: number | null
  /** protect_level for the netting formula — floorLevelCents from evaluateDepositFloorCap (NOT raw deposit once K>0). */
  protectLevelCents: number | null
  /** Today's FINAL base contract count (post deposit-floor cap). No add-on if <= 0. */
  baseContracts: number
  maxLossCentsPerContract: number
  marginCents: number
  /** Today's VIX-decay ratio (same signal FLINT's day-eligibility reads), or null if unreadable. */
  vixRatio: number | null
  /** 0.70 — the frozen "calm" threshold. */
  vixCeiling: number
  /** $4,000 in cents (400_000) — the frozen minimum deposit for this feature. */
  minDepositCentsForUpsize: number
}

export interface CalmUpsizeResult {
  extraContract: boolean
  reason:
    | 'added' | 'base_zero' | 'vix_unavailable' | 'not_calm'
    | 'deposit_unknown' | 'deposit_below_threshold' | 'protect_level_unknown' | 'equity_unreadable'
    | 'bad_inputs' | 'insufficient_house_money'
}

export function evaluateCalmUpsize(i: CalmUpsizeInput): CalmUpsizeResult {
  if (!Number.isFinite(i.baseContracts) || i.baseContracts <= 0) return { extraContract: false, reason: 'base_zero' }
  if (i.vixRatio == null || !Number.isFinite(i.vixRatio)) return { extraContract: false, reason: 'vix_unavailable' }
  if (!(i.vixRatio <= i.vixCeiling)) return { extraContract: false, reason: 'not_calm' }
  if (i.depositCents == null || !Number.isFinite(i.depositCents)) return { extraContract: false, reason: 'deposit_unknown' }
  if (i.depositCents < i.minDepositCentsForUpsize) return { extraContract: false, reason: 'deposit_below_threshold' }
  if (i.protectLevelCents == null || !Number.isFinite(i.protectLevelCents)) return { extraContract: false, reason: 'protect_level_unknown' }
  if (i.equityCents == null || !Number.isFinite(i.equityCents)) return { extraContract: false, reason: 'equity_unreadable' }
  if (!Number.isFinite(i.maxLossCentsPerContract) || i.maxLossCentsPerContract <= 0 || !Number.isFinite(i.marginCents) || i.marginCents < 0) {
    return { extraContract: false, reason: 'bad_inputs' }
  }
  const remainingAfterBase = (i.equityCents - i.protectLevelCents) - i.baseContracts * i.maxLossCentsPerContract
  const required = i.maxLossCentsPerContract + i.marginCents
  if (remainingAfterBase >= required) return { extraContract: true, reason: 'added' }
  return { extraContract: false, reason: 'insufficient_house_money' }
}

export function evaluateFlintCushion(i: FlintCushionInput): FlintCushionResult {
  if (
    !Number.isFinite(i.maxLossCents) || i.maxLossCents <= 0 ||
    !Number.isFinite(i.marginCents) || i.marginCents < 0 ||
    !Number.isFinite(i.hostCommittedCents) || i.hostCommittedCents < 0
  ) {
    return { eligible: false, cushionCents: null, reason: 'bad_inputs' }
  }
  if (i.equityCents == null || !Number.isFinite(i.equityCents)) {
    return { eligible: false, cushionCents: null, reason: 'equity_unreadable' }
  }
  if (i.protectLevelCents == null || !Number.isFinite(i.protectLevelCents)) {
    return { eligible: false, cushionCents: null, reason: 'deposit_unknown' }
  }
  const cushion = i.equityCents - i.protectLevelCents - i.hostCommittedCents
  const required = i.maxLossCents + i.marginCents
  if (cushion < required) return { eligible: false, cushionCents: cushion, reason: 'cushion_insufficient' }
  return { eligible: true, cushionCents: cushion }
}
