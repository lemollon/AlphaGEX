/**
 * Customer-facing Live page payload types.
 * Served by /api/live/summary and /api/live/trade — a deliberately narrow,
 * jargon-free projection of SPARK production state. No operator internals
 * (sandbox account IDs, close-reason breakdowns, strikes/legs) ever cross
 * this boundary.
 */

export type CustomerStateKey =
  | 'WORKING_WAITING'
  | 'TRADE_ACTIVE'
  | 'MONITORING_POSITION'
  | 'TRADE_COMPLETE'
  | 'PAUSED'
  | 'BLOCKED'
  | 'ACTION_REQUIRED'

export type StateDot = 'green' | 'blue' | 'amber' | 'red' | 'gray'

export interface CustomerState {
  key: CustomerStateKey
  headline: string
  subtitle: string
  /** e.g. "No action required." — null when the state isn't calm. */
  check_line: string | null
  dot: StateDot
  /** 1..4 = current step on the "what is happening" timeline; 0 = pre-trade
   *  (all steps upcoming); null = timeline not applicable (paused/blocked/closed). */
  timeline_step: 0 | 1 | 2 | 3 | 4 | null
  paused: boolean
  can_resume: boolean
}

export interface MarketSession {
  open: boolean
  label: 'Market Open' | 'Market Closed' | 'Market Holiday'
  /** Minutes-since-midnight CT the session closes (720 early close / 900 normal); null when closed. */
  closes_at_min: number | null
  /** e.g. "Opens Monday 8:30 AM CT" — null while the market is open. */
  next_open_label: string | null
}

export interface LiveSummary {
  state: CustomerState
  market: MarketSession & {
    condition: 'good' | 'caution' | 'no_trading'
    condition_line: string
    spy_price: number | null
    spy_change_pct: number | null
    vix: number | null
    /** ISO timestamp of the heartbeat the SPY/VIX values came from. */
    vix_as_of: string | null
    trend: 'Bullish' | 'Bearish' | 'Holding Steady' | null
    outlook: string | null
    /** Trend/outlook/condition are derived labels (VIX bands + SPY day change), not a data feed. */
    derived: true
  }
  account: {
    value: number | null
    today_pnl: number | null
    today_pnl_pct: number | null
    source: 'tradier' | 'paper_account'
  }
  intraday: Array<{ timestamp: string; equity: number }>
  membership: { plan: string; badge: string }
  as_of: string
}

export interface LiveTrade {
  active: boolean
  /** ISO open time; format client-side in CT. */
  opened_at: string | null
  /** e.g. "Today 2:45 PM CT" or "Mon Jul 6" — plain-English auto-close/expiry. */
  expires_label: string | null
  time_in_trade_min: number | null
  /** null = quotes unavailable → UI must show "—", never $0.00. */
  unrealized_pnl: number | null
  unrealized_pnl_pct: number | null
  pnl_source: 'live' | 'scanner_snapshot' | 'none'
  spark_series: Array<{ timestamp: string; pnl: number }>
  /** Populated when today's trading is complete (realized result). */
  today_result: { pnl: number; pct: number | null } | null
}
