/**
 * Response shapes, mirrored from the webapp's src/lib/live/types.ts and
 * lib/live/trades-history.ts. Kept as a hand-written mirror rather than a shared
 * package because the repo has no workspace tooling — every app owns its own tree.
 *
 * If a field here drifts from the server, the screen renders undefined rather than
 * throwing, so treat every optional as genuinely optional.
 */

export type CustomerStateKey =
  | 'WORKING_WAITING'
  | 'TRADE_ACTIVE'
  | 'MONITORING_POSITION'
  | 'TRADE_COMPLETE'
  | 'PAUSED'
  | 'BLOCKED'
  | 'ACTION_REQUIRED'

export interface CustomerState {
  key: CustomerStateKey
  headline: string
  subtitle: string
  check_line: string | null
  dot: 'green' | 'blue' | 'amber' | 'red' | 'gray'
  /** 0..4 — drives the Opened → Monitoring → Target/Stop → Auto Close stepper. */
  timeline_step: 0 | 1 | 2 | 3 | 4 | null
  paused: boolean
  can_resume: boolean
}

export interface LiveSummary {
  empty?: boolean
  viewer?: { bot: string | null; allowedBots: string[]; paperBots?: string[] }
  state: CustomerState
  market: {
    open: boolean
    label: 'Market Open' | 'Market Closed' | 'Market Holiday'
    condition: 'good' | 'caution' | 'no_trading'
    condition_line: string
    spy_price: number | null
    vix: number | null
  }
  account: {
    value: number | null
    today_pnl: number | null
    today_pnl_pct: number | null
    source: 'tradier' | 'paper_account'
    mode: 'production' | 'paper'
    disclosure: string | null
  }
  intraday: Array<{ timestamp: string; equity: number; pnl?: number | null }>
  membership: {
    plan: string
    badge: string
    trial?: { label: string; day: number; total_days: number; ends_label: string } | null
  }
  as_of: string
}

export interface LiveTrade {
  active: boolean
  opened_at: string | null
  expires_label: string | null
  time_in_trade_min: number | null
  unrealized_pnl: number | null
  unrealized_pnl_pct: number | null
  pnl_source: 'live' | 'scanner_snapshot' | 'none'
  /** Today's intraday P&L series — the source for the UX-003 chart. */
  spark_series: Array<{ timestamp: string; pnl: number }>
  today_result: { pnl: number; pct: number | null } | null
}

export interface HomeData {
  week_income?: number | null
  month_income?: number | null
  lifetime_return_pct?: number | null
  lifetime_income?: number | null
}

export type OutcomeKind = 'profit' | 'auto' | 'stop' | 'manual' | 'expired' | 'other'

export interface HistoryTrade {
  id: string
  bot: string
  strategy: string
  paper: boolean
  underlying: string
  close_date: string
  opened_ct: string | null
  closed_ct: string | null
  contracts: number
  credit: number | null
  pnl: number
  pnl_pct: number | null
  outcome: string
  outcome_kind: OutcomeKind
}

export interface CommunityMessage {
  id: string
  sender_name: string
  sender_type: 'USER' | 'FORGE' | 'SYSTEM'
  message: string
  created_at: string
  reactions: Array<{ emoji: string; count: number; mine: boolean }>
}

export interface CommunityFeed {
  channels: Array<{ slug: string; name: string }>
  messages: CommunityMessage[]
  online_count: number
  members: Array<{ name: string; you: boolean }>
}

export interface MobileMe {
  ok: boolean
  ownsStrategy?: boolean
  hasMembership?: boolean
  customer?: {
    id: string
    email: string
    displayName: string
    initials: string
    firstName: string | null
    lastName: string | null
    emailVerified: boolean
    onboardingStep: string | null
    memberSince: string
  }
}
