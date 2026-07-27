/**
 * Bot Ledger — wire and internal types.
 *
 * Every decimal crosses the wire as a STRING. Returning them as JSON numbers
 * would hand the client a binary float of a value we computed exactly, and the
 * client is forbidden from recomputing official KPIs anyway.
 */

import type { LedgerBot, LedgerPeriod } from './constants'

export type Outcome = 'WIN' | 'LOSS' | 'SCRATCH'
export type PublicOutcome = 'win' | 'loss' | 'scratch'

/** A decimal rendered as a fixed-point string, e.g. '73.68' or '-5.20'. */
export type DecimalString = string

/** One row as it comes back from `{bot}_positions`. All NUMERICs are strings. */
export interface RawLedgerRow {
  id: unknown
  position_id: unknown
  ticker: unknown
  contracts: unknown
  realized_pnl: unknown
  bp: unknown
  put_short_strike: unknown
  put_long_strike: unknown
  call_short_strike: unknown
  call_long_strike: unknown
  status: unknown
  close_time: unknown
  et_date: unknown
  ct_date: unknown
}

/**
 * A projected trade, in exact integer units. This is the internal currency of
 * the whole module — `summarize()` never sees a float.
 */
export interface LedgerTrade {
  publicId: string
  bot: LedgerBot
  /** Market date (ET), YYYY-MM-DD. */
  closedDate: string
  /** Sort key only — never published. */
  closedAtMs: number
  /** Deterministic tie-break for equal close times — never published. */
  rowId: number
  setup: string
  legs: number
  /** Buying power for ONE contract, in cents. */
  bpCents: number
  /** Net result for ONE contract, in cents. */
  netCents: number
  /** Return on buying power, in integer hundredths of a percent. */
  returnOnBpHpct: number
  outcome: Outcome
  /** True when the ET and CT calendar dates disagree (monitoring only). */
  tzDivergent: boolean
}

export type ProjectionRejectReason =
  | 'INVALID_CONTRACTS'
  | 'INVALID_BUYING_POWER'
  | 'INVALID_NUMERIC'
  | 'ZERO_LEGS'
  | 'MISSING_CLOSE_TIME'

export interface ProjectionReject {
  ok: false
  reason: ProjectionRejectReason
}

export interface ProjectionOk {
  ok: true
  trade: LedgerTrade
}

export type ProjectionResult = ProjectionOk | ProjectionReject

/** KPI block for one bot over one set of trades. */
export interface PeriodStats {
  closed_trades: number
  wins: number
  losses: number
  scratches: number
  win_rate_pct: DecimalString | null
  avg_return_on_bp_pct: DecimalString | null
  profit_factor: DecimalString | null
  avg_winner_pct: DecimalString | null
  avg_loser_pct: DecimalString | null
}

export interface BotSummary extends PeriodStats {
  bot: LedgerBot
  name: string
  tagline: string
  execution_mode: 'paper'
  mascot: string
  lifetime_closed_trades: number
  lifetime_wins: number
  lifetime_win_rate_pct: DecimalString | null
  current_win_streak: number
  /** First eligible close date (ET). Disclosed on the card as the ledger start. */
  inception_date: string | null
  /** Trade counts per public setup label — makes a strategy change visible. */
  setups: Record<string, number>
}

export interface DataQuality {
  tz_date_divergences: number
  dedupe_dropped: number
  excluded_no_bp: number
  excluded_zero_legs: number
  excluded_invalid_contracts: number
  excluded_missing_close_time: number
  excluded_invalid_numeric: number
}

export interface SummaryResponse {
  snapshot_id: string
  as_of: string
  period: LedgerPeriod
  calculation_version: number
  net_basis: string
  data_freshness_seconds: number | null
  generated_at: string
  /**
   * Whether the aggregate reconciled against the trade set.
   *
   * This server only ever emits `true` — a failed invariant throws and the
   * route returns 500 rather than serving a payload. It is typed `boolean`
   * anyway because it is a WIRE contract: the client must be able to suppress
   * the cards on `false` without depending on the current server's behaviour.
   */
  reconciled: boolean
  bots: BotSummary[]
  data_quality: DataQuality
}

export interface PublicLedgerTrade {
  public_id: string
  closed_date: string
  bot: LedgerBot
  setup: string
  buying_power_used: DecimalString
  net_result: DecimalString
  return_on_bp_pct: DecimalString
  outcome: PublicOutcome
}

export interface TradesResponse {
  snapshot_id: string
  as_of: string
  calculation_version: number
  net_basis: string
  generated_at: string
  filter: { bot: 'all' | LedgerBot }
  items: PublicLedgerTrade[]
  total: number
  next_cursor: string | null
  previous_cursor: string | null
}

export type LedgerErrorCode =
  | 'INVALID_PERIOD'
  | 'INVALID_BOT_FILTER'
  | 'INVALID_LIMIT'
  | 'INVALID_CURSOR'
  | 'INVALID_SNAPSHOT'
  | 'SNAPSHOT_EXPIRED'
  | 'LEDGER_INVARIANT_VIOLATION'
  | 'LEDGER_UNAVAILABLE'
