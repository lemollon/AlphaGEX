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
  /** No trading account is linked to this viewer. Distinct from PAUSED: the bot
   *  may be running perfectly for everyone else. */
  | 'NOT_LINKED'

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

export interface LiveViewerInfo {
  bot: string | null
  allowedBots: string[]
  /** Bots currently on simulated money — drives the "Paper" badge client-side. */
  paperBots?: string[]
  /**
   * users.id of the signed-in customer; null for anonymous and for operators.
   *
   * Already present in the payload — /api/live/summary returns the resolved viewer
   * verbatim on the empty branch — this only declares it. It is the one signal that
   * separates "anonymous visitor" from "customer who has not added a bot yet", which
   * the Live empty-state CTA needs: the first should be offered signup, the second
   * must never be sent back through account creation.
   *
   * NOT an identifier the client acts on — it only picks copy and a destination.
   */
  customerId?: string | null
}

export interface LiveSummary {
  /** True when the viewer has no live account to show (fresh signup/anonymous). */
  empty?: boolean
  /** Which live account this payload describes + which the viewer may switch to. */
  viewer?: LiveViewerInfo
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
    /**
     * 'paper' = simulated money. The UI MUST render the paper badge/disclosure
     * whenever this is 'paper' — the rest of the page (account value, Today's
     * Result, Pause Trading) reads as real money otherwise.
     */
    mode: 'production' | 'paper'
    /** Non-null only in paper mode; the exact disclosure copy to display. */
    disclosure: string | null
  }
  // pnl = day P&L anchored at day-open BALANCE (includes an overnight hold's carry, so the
  // curve ends where "Today's Result" reads); equity = absolute value for the tooltip.
  intraday: Array<{ timestamp: string; equity: number; pnl?: number | null }>
  membership: {
    plan: string
    badge: string
    /** Static placeholder until billing/trial state is modeled in the DB. */
    trial?: { label: string; day: number; total_days: number; ends_label: string } | null
  }
  as_of: string
}

/**
 * ONE open position.
 *
 * SPARK swings: a 1DTE condor opened yesterday is held to expiry rather than stopped
 * out, so on any day it opens a new trade there are TWO live positions at once. The Live
 * page described only `positionRows[0]` — the newest — so the held-overnight trade, with
 * the customer's money in it, did not appear anywhere on the page.
 *
 * SPARK is the only bot that swings (isSparkStrategy in scanner.ts), so it is the only
 * one that can produce more than one of these.
 */
export interface LiveOpenPosition {
  position_id: string
  opened_at: string | null
  /** "Jul 28" — the card title, in CT. */
  opened_date_label: string
  expires_label: string | null
  time_in_trade_min: number | null
  unrealized_pnl: number | null
  unrealized_pnl_pct: number | null
  pnl_source: 'live' | 'scanner_snapshot' | 'none'
  /** Opened on an earlier CT date — i.e. this is the swung leg. */
  held_overnight: boolean
  /** 1 on the day it opened, 2 the next session, and so on. */
  day_number: number
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
  /**
   * EVERY open position, newest first. The scalar fields above describe positions[0]
   * and are kept so existing readers are unaffected; anything that must not hide a
   * swung leg should read this instead.
   *
   * Empty when nothing is open.
   */
  positions: LiveOpenPosition[]
}
