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
