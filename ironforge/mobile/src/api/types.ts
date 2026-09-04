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

/**
 * ONE open position. Mirrors LiveOpenPosition in webapp/src/lib/live/types.ts.
 *
 * 🚨 There can be more than one. SPARK swings — yesterday's condor is held to expiry
 * rather than stopped out, so on any day it opens a new trade there are TWO open at
 * once. The web page had a bug where it described only the newest, so the older leg
 * with the customer's money in it appeared nowhere; the mobile app inherited that
 * shape by only ever reading the scalar fields.
 */
export interface LiveOpenPosition {
  position_id: string
  opened_at: string | null
  /** "Jul 28", already in CT — do not re-format from opened_at. */
  opened_date_label: string
  expires_label: string | null
  unrealized_pnl: number | null
  unrealized_pnl_pct: number | null
  pnl_source: 'live' | 'scanner_snapshot' | 'none'
  /** Opened on an earlier CT date — this is the swung leg. */
  held_overnight: boolean
  /** 1 on the day it opened, 2 the next session, and so on. */
  day_number: number
  /**
   * THIS trade's intraday P&L, minute-bucketed — the per-trade chart in UX-002/003.
   *
   * Not the same as LiveTrade.spark_series, which sums the agent's whole day across
   * every open position; with a swung leg open beside today's trade those are two
   * different curves. Empty until the scanner has recorded marks for the position —
   * there is nothing to backfill — and gaps are real minutes where the mark failed.
   */
  series?: Array<{ timestamp: string; pnl: number }>
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
  /**
   * EVERY open position, newest first — the source for UX-002's per-trade rails.
   *
   * The scalar fields above describe `positions[0]`. Optional because an installed app
   * can be older than the API and vice versa; when it is absent the tile falls back to
   * the single-trade rendering rather than showing nothing.
   */
  positions?: LiveOpenPosition[]
}

/**
 * Mirrors webapp/src/lib/live/home.ts's getHomeData() return shape exactly —
 * there is no shared package between the two apps, so this is hand-kept in
 * sync. It previously wasn't: this declared flat `week_income` while the
 * route has always returned nested `wealth.weekly_income`, so This
 * Week/Month/Lifetime rendered "—" forever on the Forge tab. See
 * src/live/period-stats.test.ts's `satisfies` fixture, checked by
 * `tsc --noEmit`, for the guard against that drift recurring silently.
 */
export interface HomeData {
  wealth: {
    weekly_income: number | null
    monthly_income: number | null
    lifetime_income: number | null
    lifetime_return_pct: number | null
  }
  recent_trades: Array<{
    closed_at: string
    strategy: string
    contract: string
    premium: number
    status: string
  }>
  yesterday_trades: number
  as_of: string
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
 * Forge agent-card stat row (handoff/ledger-kpis.md PART 2) — Account Capital,
 * Growth, Last 10, Best Trade, all LIFETIME (no filter). Cents/percent so the
 * screen never re-derives money from a float. `null` when the server couldn't
 * compute it (both the starting-capital and closed-trades queries must
 * succeed) — the tile shows "—" in that case, never a fabricated number.
 */
export interface AgentCardStats {
  account_capital_cents: number | null
  growth_pct: number | null
  last10: { wins: number; losses: number }
  best_trade_cents: number | null
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
  stats: AgentCardStats | null
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

// ---- WP-B types ----

/** The Ledger KPI strip (completed trades / win rate), over the same filtered
 *  population as `total` — bot/days/q, ignoring cursor/limit. */
export interface TradesTotals {
  completed_trades: number
  win_rate: number | null
}

/**
 * GET /api/live/trades — now cursor-paginated (APP-020). `trades` is still the
 * top-level array (unchanged shape for anything reading it pre-pagination);
 * `next_cursor` is opaque and only meaningful passed straight back as `cursor`
 * on the next request. `total` counts every row matching the current filters.
 * `totals` is optional for the same forward/backward-compat reason as other
 * additive fields in this file — an installed app can be older than the API.
 */
export interface TradesPageResponse {
  empty?: boolean
  viewer?: LiveSummary['viewer']
  trades: HistoryTrade[]
  next_cursor: string | null
  total: number
  totals?: TradesTotals
}

export type TradeLegSide = 'buy' | 'sell'
export type TradeLegRight = 'put' | 'call'

export interface TradeLeg {
  side: TradeLegSide
  right: TradeLegRight
  strike: number
  expiry: string
  qty: number
}

export interface TradeLifecycleEntry {
  at_ct: string
  event: string
  note: string | null
}

export type ExitReasonCode = 'profit_target' | 'stop_loss' | 'manual_close' | 'expired' | 'auto_close' | 'other'

/**
 * GET /api/live/trades/:id — trade detail (APP-019/022). Every field is
 * independently nullable: the server sources each ONLY from a column that
 * actually exists, so a field with nothing to source it from is null, never
 * fabricated. `legs`/`lifecycle` are whole-array-or-null rather than an empty
 * array, so the screen can tell "nothing happened" apart from "not available".
 */
export interface TradeDetail {
  legs: TradeLeg[] | null
  entry_at_ct: string | null
  credit: number | null
  buying_power_used: number | null
  current_pnl: number | null
  lifecycle: TradeLifecycleEntry[] | null
  exit_reason_code: ExitReasonCode | null
  exit_reason_text: string | null
  monitoring_message: string | null
}

export interface TradeDetailResponse {
  trade: HistoryTrade
  detail: TradeDetail
}

// ---- WP-E types ----

/** GET/PUT /api/notifications/preferences (APP-036). */
export interface NotificationPreferences {
  trade_opened: boolean
  trade_closed: boolean
  trade_approval: boolean
  brokerage_health: boolean
  billing: boolean
  community: boolean
  show_amounts_on_lockscreen: boolean
}

export interface NotificationPreferencesResponse {
  ok: boolean
  preferences: NotificationPreferences
}

/** One batched analytics event, as sent to POST /api/v1/analytics/events (APP-048). */
export interface AnalyticsEvent {
  event: string
  props?: Record<string, string | number | boolean | null>
  ts: number
  app_version: string
  platform: string
}

export interface AnalyticsEventsResponse {
  ok: boolean
  accepted: number
}

// ---- WP-C types ----

/** GET /api/billing/entitlements — bots this customer's membership currently owns. */
export interface EntitlementsResponse {
  ok: boolean
  bots: string[]
}

/** One row from GET/POST /api/v1/automation/pause. */
export interface AutomationActivation {
  activation_id: string
  agent: string
  paused: boolean
  paused_at: string | null
}

export interface AutomationPauseResponse {
  ok: boolean
  updated?: number
  activations: AutomationActivation[]
}

/** POST /api/v1/agent-configs — a new draft/valid configuration for one agent. */
export interface AgentConfigResponse {
  id: string
  agent_code: string
  rule_version: string
  status: 'draft' | 'valid'
  limits: { max_deployment_cents: number | null; buying_power_cents: number | null }
  violations: Array<{ field?: string; message: string }>
  warnings: Array<{ field?: string; message: string }>
}

/** One reason POST /api/v1/activations would refuse — see evaluateActivation server-side. */
export interface ActivationBlocker {
  code: string
  message: string
  field?: string
  remediable: boolean
}

/** POST /api/v1/activations/preview — the immutable review snapshot. */
export interface ActivationPreviewResponse {
  preview_hash: string
  expires_in_seconds: number
  snapshot: {
    agent: string
    rule_version: string
    account_mask: string | null
    max_deployment_cents: number | null
    buying_power_cents: number | null
    legal_versions: Record<string, string> | null
    plan: { name: string; price_monthly: number; interval: string } | null
    trial: { eligible_days_total: number; counts: string }
  }
  can_activate: boolean
  blockers: ActivationBlocker[]
}

/** POST /api/v1/activations — success body. Only ever rendered after a 2xx. */
export interface ActivationResponse {
  ok: boolean
  activation_id: string
  agent: string
  account_mask: string | null
  trial: { status: string; eligible_days_used: number; eligible_days_total: number }
}

// ---- WP-F types ----
// New fields extend the base CommunityMessage/CommunityFeed above rather than editing
// them in place (shared file — see src/api/types.ts ownership note). Both new fields
// are optional for the same forward/backward-compat reason as `mine`/`blockable`
// above: an installed app can be older or newer than the API it's talking to.

/** A Community post carrying thread data (APP-055) — reply count and, on a reply, its parent. */
export interface CommunityMessageV2 extends CommunityMessage {
  /** How many replies this post has. Only meaningful on top-level feed rows. */
  reply_count?: number
  /** The message this is a reply to. Present on rows returned by GET .../replies. */
  parent_id?: string | null
}

/** GET /api/community/messages?channel=… response, with thread-carrying messages. */
export interface CommunityFeedV2 extends Omit<CommunityFeed, 'messages'> {
  messages: CommunityMessageV2[]
}

/** GET /api/community/messages/[id]/replies?cursor&limit — one thread, oldest first. */
export interface ThreadReplies {
  replies: CommunityMessageV2[]
  next_cursor: string | null
}

/** POST /api/community/assist {draft, channel} — AI-assist composer suggestion (APP-031). */
export interface AssistResponse {
  ok: true
  suggestion: string
}
