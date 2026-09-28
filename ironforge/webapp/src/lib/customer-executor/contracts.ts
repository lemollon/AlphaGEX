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
 * Ported from `customer_protection_sim.py`'s P3 arm (RESULT_customer_protection.md,
 * section P3, frozen 2026-09-28): a customer's FLINT mirror trades ONLY when its own
 * max loss is fully covered by cushion ALREADY BUILT — `equity - protectLevel >=
 * maxLossCents`. By construction FLINT can never, on its own, be the trade that pushes
 * the account below its protected level. `protectLevel` is `depositCents` under today's
 * live system (no profit-floor/ratchet exists for customers yet — that's the sim's P1/P2
 * arm, not shipped) — pass `depositCents` as `protectLevelCents` until a floor exists.
 *
 * ONE DELIBERATE DIFFERENCE FROM THE SIM, per Leron's explicit instruction (not present
 * in the sim's P3 formula, which has no margin term): `marginCents` pads the required
 * cushion, mirroring the $50/contract margin the sim's OWN post-trigger P1/P2 budget
 * check uses elsewhere (MARGIN=50 in customer_protection_sim.py) — "never size up on
 * missing data" extends here to "never gate exactly on the wire." Pass `marginCents: 0`
 * to reproduce the sim's literal P3 rule (see the parity test against sim fixtures).
 *
 * FAILS CLOSED: a null/unreadable equity or deposit reading is never treated as
 * "cushion covers it" — it skips, the same invariant as sizeContracts/canOpenForCustomer.
 */
export interface FlintCushionInput {
  /** Live account equity read at mirror time, in cents. NULL = broker read failed. */
  equityCents: number | null
  /** The customer's protected level, in cents (today: their captured baseline / "deposit"). NULL = unknown. */
  protectLevelCents: number | null
  /** FLINT's own worst-case max loss for exactly 1 contract, in cents. */
  maxLossCents: number
  /** Extra required cushion beyond raw max loss, in cents (live-only; sim's exact P3 rule uses 0). */
  marginCents: number
}

export interface FlintCushionResult {
  eligible: boolean
  cushionCents: number | null
  reason?: 'bad_inputs' | 'equity_unreadable' | 'deposit_unknown' | 'cushion_insufficient'
}

/**
 * CUSTOMER_DEPOSIT_FLOOR — the deposit-only protection floor, ported from
 * customer_protection_sim.py's ROUND 3 winning arm: K=0, N=3, variant S (frozen
 * 2026-09-28, RESULT_customer_protection.md "ROUND 3"). At K=0 the floor never
 * moves off `deposit` (floor_level = deposit forever, once it exists), so this is
 * simpler than the general P1/P2 arm: "once triggered, cap sizing so the account can
 * never trade itself back below deposit."
 *
 * Trigger (one-way, sticky — `triggered` never resets once true): the FIRST day
 * `equity - deposit >= N * (desired_count(deposit, pct, ml) * ml)` — "3x one day's
 * own max loss AT THE CUSTOMER'S NORMAL SIZING, referenced off the FIXED deposit
 * (never off the moving equity)" — same fixed-yardstick fix as evaluateFlintCushion's
 * sibling logic in the P1/P2 arm (equity-referenced would make the trigger scale with
 * itself and become unreachable for some N/pct combinations).
 *
 * Post-trigger sizing (variant S, "sit out below budget"):
 *   n = max(0, min(desiredContracts, floor((equity - deposit) / (maxLossCentsPerContract + marginCents))))
 * Pre-trigger: `desiredContracts` passes through UNCHANGED — byte-identical to BASE.
 *
 * FAILS OPEN on missing data, unlike every other gate in this file: the spec (Leron,
 * "Missing data -> today's sizing, logged") is deliberate here, because this is a
 * PROTECTIVE cap on the customer's PRIMARY leg — an unreadable equity/deposit means
 * "cannot evaluate the floor," and the least-surprising fallback is today's normal
 * sizing (continuity with the CUSTOMER_DEPOSIT_FLOOR=off behavior for that one day),
 * not blocking the trade. The caller MUST log `dataOk: false` (see the decision log
 * in executor.ts) — silent is not allowed even though the trade proceeds.
 */
export interface DepositFloorInput {
  /** Live equity/buying-power at decision time (reuse the SAME read sizeContracts uses — no extra broker call). */
  equityCents: number | null
  /** Fixed baseline, in cents (today: broker_accounts.buying_power_cents captured at connect — same proxy as FLINT's). */
  depositCents: number | null
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
  /** N in the trigger formula — 3, the frozen ROUND 3 winner. */
  triggerN: number
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
   * (evaluateCalmUpsize) when true — the two are mutually exclusive by construction
   * (customer_protection_final_package.py's if/else), never both on the same day.
   */
  triggeredForSizing: boolean
}

export function evaluateDepositFloorCap(i: DepositFloorInput): DepositFloorResult {
  if (
    i.equityCents == null || !Number.isFinite(i.equityCents) ||
    i.depositCents == null || !Number.isFinite(i.depositCents) ||
    !Number.isFinite(i.maxLossCentsPerContract) || i.maxLossCentsPerContract <= 0 ||
    !Number.isFinite(i.pct) || i.pct <= 0 ||
    !Number.isFinite(i.desiredContracts) || i.desiredContracts < 0
  ) {
    return { contracts: Math.max(0, i.desiredContracts || 0), triggeredNow: false, capped: false, dataOk: false, triggeredForSizing: i.triggered }
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

  if (!triggered) {
    return { contracts: i.desiredContracts, triggeredNow: false, capped: false, dataOk: true, triggeredForSizing: false }
  }

  const budget = i.equityCents - i.depositCents // floor_level === deposit forever at K=0
  const capped = budget > 0 ? Math.floor(budget / (i.maxLossCentsPerContract + i.marginCents)) : 0
  const n = Math.max(0, Math.min(i.desiredContracts, capped))
  return { contracts: n, triggeredNow, capped: n < i.desiredContracts, dataOk: true, triggeredForSizing: true }
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
 * ROUND 4 (frozen 2026-09-28, RESULT_customer_protection.md "ROUND 4"). Deposit >=
 * $4,000 only: Round 4 found FLAME $2,000 nets NEGATIVE on both median and p10 (the
 * thin deposit means calm-day upsizing eats into the same cushion the floor is
 * protecting), while $4,242/$5,000/$7,500 all add money at 0% fallback-after-trigger.
 *
 * Gate (the sim's OWN, exact formula — it shipped with a caught bug, fixed before
 * reporting: the +1 is not an independent bet, it shares the SAME day's per-contract
 * loss as the base position, so its risk is ADDITIVE, not separate):
 *   remainingAfterBase = (equity - deposit) - baseContracts * maxLossCentsPerContract
 *   eligible = remainingAfterBase >= (maxLossCentsPerContract + marginCents)
 * `deposit` here IS `protect_level` in the sim's general form (`floor_level` once
 * triggered else `deposit`) — but the shipping floor is K=0, where `floor_level`
 * never moves off `deposit`, so `protect_level === deposit` unconditionally, exactly
 * like evaluateFlintCushion's own protect_level. One NOTE on the source: the
 * coordinator's own restatement of this rule nets the base contracts at
 * `(maxLoss + margin)` per contract rather than the sim's `maxLoss` per contract —
 * this function follows the SIM's literal code (`customer_protection_calmday.py`
 * lines 74-80), which is the frozen, tested, reported rule; the coordinator's
 * paraphrase was imprecise, not a second intended design. Documented per the
 * standing instruction to resolve ambiguity from the sim, not a restatement of it.
 *
 * `baseContracts` MUST be the count AFTER any deposit-floor cap (evaluateDepositFloorCap)
 * has already run — the sim computes calm-day eligibility using that same day's final
 * (floor-capped) `n`, not the pre-floor desired count.
 */
export interface CalmUpsizeInput {
  equityCents: number | null
  /** The customer's deposit baseline — same proxy as everywhere else in this file. */
  depositCents: number | null
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
    | 'deposit_unknown' | 'deposit_below_threshold' | 'equity_unreadable'
    | 'bad_inputs' | 'insufficient_house_money'
}

export function evaluateCalmUpsize(i: CalmUpsizeInput): CalmUpsizeResult {
  if (!Number.isFinite(i.baseContracts) || i.baseContracts <= 0) return { extraContract: false, reason: 'base_zero' }
  if (i.vixRatio == null || !Number.isFinite(i.vixRatio)) return { extraContract: false, reason: 'vix_unavailable' }
  if (!(i.vixRatio <= i.vixCeiling)) return { extraContract: false, reason: 'not_calm' }
  if (i.depositCents == null || !Number.isFinite(i.depositCents)) return { extraContract: false, reason: 'deposit_unknown' }
  if (i.depositCents < i.minDepositCentsForUpsize) return { extraContract: false, reason: 'deposit_below_threshold' }
  if (i.equityCents == null || !Number.isFinite(i.equityCents)) return { extraContract: false, reason: 'equity_unreadable' }
  if (!Number.isFinite(i.maxLossCentsPerContract) || i.maxLossCentsPerContract <= 0 || !Number.isFinite(i.marginCents) || i.marginCents < 0) {
    return { extraContract: false, reason: 'bad_inputs' }
  }
  const remainingAfterBase = (i.equityCents - i.depositCents) - i.baseContracts * i.maxLossCentsPerContract
  const required = i.maxLossCentsPerContract + i.marginCents
  if (remainingAfterBase >= required) return { extraContract: true, reason: 'added' }
  return { extraContract: false, reason: 'insufficient_house_money' }
}

export function evaluateFlintCushion(i: FlintCushionInput): FlintCushionResult {
  if (!Number.isFinite(i.maxLossCents) || i.maxLossCents <= 0 || !Number.isFinite(i.marginCents) || i.marginCents < 0) {
    return { eligible: false, cushionCents: null, reason: 'bad_inputs' }
  }
  if (i.equityCents == null || !Number.isFinite(i.equityCents)) {
    return { eligible: false, cushionCents: null, reason: 'equity_unreadable' }
  }
  if (i.protectLevelCents == null || !Number.isFinite(i.protectLevelCents)) {
    return { eligible: false, cushionCents: null, reason: 'deposit_unknown' }
  }
  const cushion = i.equityCents - i.protectLevelCents
  const required = i.maxLossCents + i.marginCents
  if (cushion < required) return { eligible: false, cushionCents: cushion, reason: 'cushion_insufficient' }
  return { eligible: true, cushionCents: cushion }
}
