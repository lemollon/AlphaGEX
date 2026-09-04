/**
 * Customer-facing Live page payload types.
 * Served by /api/live/summary and /api/live/trade — a deliberately narrow,
 * jargon-free projection of SPARK production state. No operator internals
 * (sandbox account IDs, close-reason breakdowns, strikes/legs) ever cross
 * this boundary.
 */

import type { BacktestAnchor, compareToBacktestAnchor } from './backtestAnchor'
import type { FeedEntry } from './activityFeed'

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
  /**
   * DASH-FIRST-01: present while the newest activation's first-entry confirmation has
   * not been acknowledged. Also present on the `empty` branch — a just-activated
   * customer has no bot mapping yet, and that is exactly when this must render.
   */
  activation_confirmation?: {
    activation_id: string
    agent: string
    account_mask: string | null
    trial_day: number
    trial_total: number
  } | null
  /**
   * "Risky setups skipped this month" — a count of distinct CT calendar days
   * where a genuine protective/risk gate fired and the bot did NOT end up
   * trading that day (see lib/live/riskProtection.ts). NEVER fabricated: null
   * means the underlying queries could not be computed, and the card must
   * render nothing rather than guess. A count of exactly 0 is a real value
   * and must still render.
   */
  risk_protection: { skipped_count: number; period_label: string } | null
  /**
   * "Live gate/health activity feed" — today's scan activity as a short,
   * plain-English list, so the page feels alive even on a 0-trade day. Every
   * `FeedEntry.label` is ALREADY a curated string (see lib/live/activityFeed.ts)
   * — the raw internal `reason` (e.g. "skip:vix_elevated(0.904>0.90)") never
   * reaches this type. NEVER fabricated: null means the underlying query
   * could not be computed. An empty `entries` array (no scans logged yet
   * today) is a real, renderable state and must still render the card.
   */
  activity_feed: { scans_today: number; gates_held_today: number; entries: FeedEntry[] } | null
  /**
   * Last RECENT_TRADES_LIMIT closed trades as win/loss chips, oldest-first,
   * plus the CURRENT streak (win OR losing — never suppressed). See
   * lib/live/winLossStreak.ts. NEVER fabricated: null means the underlying
   * query could not be computed. An empty `trades` array (no trades closed
   * yet) is a real, renderable state.
   */
  win_loss_streak: {
    trades: ('win' | 'loss')[]
    winsCount: number
    lossesCount: number
    currentStreak: { count: number; type: 'win' | 'loss' } | null
  } | null
  /**
   * Non-P&L tenure/system-health badges — days connected, cumulative scans,
   * month number. See lib/live/milestones.ts. Route-populated (needs
   * customerId, which getLiveSummary does not receive) — same pattern as
   * `membership`/`activation_confirmation`: getLiveSummary returns null here
   * as an inert placeholder, and the route merges the real value in. Each
   * inner field is independently nullable (e.g. an operator view may only
   * ever have `scanNumber`).
   */
  milestones: { daysConnected: number | null; scanNumber: number | null; monthNumber: number | null } | null
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
  /**
   * Lifecycle line (UAT round two, mock #1). Dollar profit at the configured
   * profit target and dollar loss at the configured stop, derived from this
   * position's own credit/contracts — not a percentage, so the card can show
   * "$60 / −$120" without the customer doing the math themselves.
   *
   * `stop_dollars` is null when the strategy has no real stop (holds to
   * settlement instead) — the UI must show "hold to close", never $0.
   */
  target_dollars: number | null
  stop_dollars: number | null
  /** ISO instant of today's EOD auto-close cutoff — null when this position
   *  doesn't expire today (a swung leg), which the UI reads as "at close". */
  auto_close_at: string | null
  /** Opened on an earlier CT date — i.e. this is the swung leg. */
  held_overnight: boolean
  /** 1 on the day it opened, 2 the next session, and so on. */
  day_number: number
  /**
   * Gamma regime AT ENTRY, as recorded on the position — not today's reading. It is what
   * decided this trade's strike width and its size, so re-deriving it live would
   * describe a different trade than the one the customer is holding.
   *
   * null when the chain read failed at entry, which the UI must show as unknown rather
   * than guessing positive.
   */
  gex_regime: 'POSITIVE' | 'NEGATIVE' | null
  /**
   * Capital at risk in dollars — the position's stored max loss.
   *
   * Dollars, not a percentage: account value is assembled in getLiveSummary (Tradier
   * equity, with a ledger fallback) and re-deriving it here would mean two definitions
   * of the customer's balance. The client holds both payloads and divides.
   */
  capital_used: number | null
  /**
   * The ceiling this regime authorises, 0–1 (0.50 positive / 0.20 negative or unknown).
   * Shown beside capital_pct so "17% of 20%" is legible as a rule, not a coincidence.
   */
  regime_cap_pct: number | null
  /**
   * THIS position's intraday mark-to-market, minute-bucketed — the per-trade chart in
   * UX-002/003.
   *
   * Distinct from LiveTrade.spark_series, which is the agent's whole day summed across
   * every open position. With a swung leg open beside today's trade those two are
   * different curves, and drawing the aggregate on a single trade's card would
   * attribute one position's move to another.
   *
   * Empty until the scanner has written marks for it: unrealized P&L per position was
   * never recorded before, so there is nothing to backfill. Gaps are real minutes where
   * the mark failed — the writer deliberately skips those rather than recording a zero.
   */
  series: Array<{ timestamp: string; pnl: number }>
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
  /** Mirrors positions[0] — see LiveOpenPosition for the lifecycle-line contract. */
  target_dollars: number | null
  stop_dollars: number | null
  auto_close_at: string | null
  spark_series: Array<{ timestamp: string; pnl: number }>
  /** Populated when today's trading is complete (realized result). */
  today_result: { pnl: number; pct: number | null } | null
  /**
   * OPT-IN, technical-trader-only. Populated only alongside a non-null
   * `today_result` whose underlying position(s) have `contracts > 0` — never
   * fabricated when there was no trade today. Strictly descriptive: compares
   * today's PER-LOT realized result against the strategy's validated
   * backtested range (see `lib/live/backtestAnchor.ts`). Must never be read as
   * a forward projection — the UI's "Advanced" disclosure is the only place
   * this belongs, and it must carry the "not a guarantee of future results"
   * line every time it renders.
   */
  today_result_technical?: {
    perLot: number
    contracts: number
    anchor: BacktestAnchor
    comparison: ReturnType<typeof compareToBacktestAnchor>
  } | null
  /**
   * EVERY open position, newest first. The scalar fields above describe positions[0]
   * and are kept so existing readers are unaffected; anything that must not hide a
   * swung leg should read this instead.
   *
   * Empty when nothing is open.
   */
  positions: LiveOpenPosition[]
}
