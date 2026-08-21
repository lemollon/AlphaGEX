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
  /**
   * The channel the post was written in. UX-005 tags every post in the aggregate
   * "All" view with where it came from. Optional for the same forward/backward
   * compatibility reason as `mine` below — an installed app may be older or newer
   * than the API it is talking to, and a missing field must not fail the payload.
   */
  channel_slug?: string
  channel_name?: string
  /**
   * The viewer wrote this — report/block are hidden on your own posts.
   *
   * Optional because an installed app can be OLDER than the API it talks to and
   * vice versa: a field the server may not send yet must not make the payload
   * fail to type. Absent is treated as "not mine", so the controls still render.
   */
  mine?: boolean
  /** Author is a real member who can be blocked (false for Forge/system posts). */
  blockable?: boolean
}

/** GET /api/community/blocks — the viewer's own block list. */
export interface BlockedMember {
  user_id: string
  display_name: string
  created_at: string
}

export interface CommunityFeed {
  channels: Array<{ slug: string; name: string }>
  messages: CommunityMessage[]
  online_count: number
  members: Array<{ name: string; you: boolean }>
}

/**
 * GET /api/brokerage/connections (APP-040/041).
 *
 * `broker` is the real institution; `provider` is the aggregator. Label with `broker`
 * and fall back — see brokerLabel(). `mask` is the ONLY account identifier the server
 * ever returns; the full number stays in an encrypted column.
 */
export interface BrokerageAccount {
  id: string
  mask: string | null
  eligibility: string | null
  ineligible_reason: string | null
  buying_power_cents: number | null
}

export interface BrokerageConnection {
  id: string
  provider: string
  /**
   * The handle DELETE /api/brokerage/connection requires. Absent from the payload until
   * the server started returning it, which is why disconnect could not be offered.
   */
  authorization_id: string | null
  broker: string | null
  status: string
  connected_on: string
  last_synced_at: string | null
  accounts: BrokerageAccount[]
}

export interface BrokerageConnections {
  ok: boolean
  /** false when the customers DB isn't wired — an honest "can't tell", not "none". */
  configured?: boolean
  connections: BrokerageConnection[]
}

/**
 * GET /api/live/agents — every agent this viewer owns (UX-002 shows two side by side).
 *
 * Replaces composing /api/live/summary + /api/live/trade, which between them could only
 * ever describe ONE agent. `state` or `trade` may be null for a single agent without the
 * others failing — the server settles each independently — so every field is optional and
 * `error` says which half did not load.
 */
export interface LiveAgent {
  bot: string
  label: string
  paper: boolean
  state: CustomerState | null
  account: LiveSummary['account'] | null
  trade: LiveTrade | null
  error: 'state' | 'trade' | null
}

export interface LiveAgents {
  empty?: boolean
  viewer?: LiveSummary['viewer']
  agents: LiveAgent[]
  as_of?: string
}

/** GET /api/billing/membership — APP-038. `membership` is null when there is none. */
export interface MembershipResponse {
  ok: boolean
  configured?: boolean
  membership: {
    plan: string
    status: string
    badge: string
    price_monthly: number
    /** YYYY-MM-DD, or null when Stripe has not written a period end yet. */
    next_billing_date: string | null
    bots: string[]
  } | null
}

export interface ProfileResponse {
  ok: boolean
  profile: {
    firstName: string
    lastName: string
    displayName: string
    initials: string
  }
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

/**
 * Account deletion (GET /api/account/deletion-request).
 *
 * `pending` is the authority, not the presence of `requestedAt` — a cancelled request
 * still has a timestamp, and treating "has a date" as "is deleting" would show a
 * permanent scare banner to someone who already called it off.
 */
export interface DeletionStatusResponse {
  ok: boolean
  pending: boolean
  requestedAt: string | null
  gracePeriodDays: number
}

/** POST /api/account/deletion-request. */
export interface DeletionRequestResponse {
  ok: boolean
  alreadyRequested?: boolean
  requestedAt: string
  gracePeriodDays: number
  steps?: Record<string, string>
}
