/**
 * The enrollment state machines (Enrollment spec §4).
 *
 * THE RULE THE WHOLE SPEC EXISTS TO ENFORCE: paid membership is NOT authority to
 * trade. Membership, billing, brokerage, agent configuration, trial and trading are
 * SEPARATE state machines with separate authorities — collapsing any two of them is
 * how a customer ends up with orders placed on an account they never authorised, or a
 * trial burned before they could use it.
 *
 * Pure: no I/O, no clock, no env. Every transition is data, so the rules are testable
 * without a database and cannot drift from the document silently.
 *
 * Deliberately NOT modelled here: `membership`. The spec lists a memberships entity,
 * but `customer_bot_subscriptions` (user_id, bot, status, stripe_subscription_id,
 * price_lookup_key, current_period_end) already IS that table and is written by the
 * verified Stripe webhook — the spec's own authority for membership state. Adding a
 * second one would be the redundancy this review was asked to avoid.
 */

export type EnrollmentState =
  | 'draft' | 'legal_pending' | 'billing_pending' | 'setup_required' | 'complete' | 'abandoned'
export type BrokerageState =
  | 'not_connected' | 'connecting' | 'connected' | 'reauth_required' | 'revoked' | 'error'
export type AgentConfigState = 'not_started' | 'draft' | 'valid' | 'stale' | 'archived'
export type TradingState = 'inactive' | 'activating' | 'active' | 'paused' | 'blocked' | 'revoked'
export type TrialState = 'not_started' | 'active' | 'completed' | 'converted' | 'canceled'

/**
 * Membership states, read from customer_bot_subscriptions.status (Stripe's vocabulary),
 * plus one synthesized value: 'setup_ready' — no subscription row exists YET because the
 * v2 order is card-at-$0 then subscribe-at-activation, but the enrollment is in
 * setup_required with a payment method on file. It is the "setup_required-equivalent"
 * state the activation predicate's contract names; without it v2 activation would be
 * permanently blocked by MEMBERSHIP_NOT_ACTIVE (no sub row can exist before activation
 * creates one).
 */
export type MembershipState = 'pending' | 'setup_ready' | 'active' | 'past_due' | 'paused' | 'canceled'

type Transitions<S extends string> = Readonly<Record<S, readonly S[]>>

export const ENROLLMENT_TRANSITIONS: Transitions<EnrollmentState> = {
  draft: ['legal_pending', 'abandoned'],
  legal_pending: ['billing_pending', 'draft', 'abandoned'],
  // Community completes at billing; Automate lands in setup_required. Both are reachable
  // from billing, which is exactly the plan-specific branch in §1.
  billing_pending: ['setup_required', 'complete', 'legal_pending', 'abandoned'],
  setup_required: ['complete', 'abandoned'],
  complete: [],
  abandoned: ['draft'],
}

export const BROKERAGE_TRANSITIONS: Transitions<BrokerageState> = {
  not_connected: ['connecting'],
  connecting: ['connected', 'error', 'not_connected'],
  connected: ['reauth_required', 'revoked', 'error'],
  // Re-auth returns through `connecting`, never straight to connected: a new OAuth
  // round trip is what proves the grant is live.
  reauth_required: ['connecting', 'revoked'],
  revoked: ['connecting'],
  error: ['connecting', 'not_connected'],
}

export const AGENT_CONFIG_TRANSITIONS: Transitions<AgentConfigState> = {
  not_started: ['draft'],
  draft: ['valid', 'archived'],
  // `stale` is the spec's "any account or agent change invalidates the activation
  // review" — a previously valid config must be re-validated, never silently reused.
  valid: ['stale', 'archived', 'draft'],
  stale: ['draft', 'archived'],
  archived: [],
}

export const TRADING_TRANSITIONS: Transitions<TradingState> = {
  inactive: ['activating'],
  activating: ['active', 'inactive', 'blocked'],
  active: ['paused', 'blocked', 'revoked'],
  paused: ['active', 'blocked', 'revoked'],
  // `blocked` is set by risk/kill-switch/broker-health, so it can only be left by
  // going back through activation checks.
  blocked: ['activating', 'revoked', 'paused'],
  revoked: [],
}

export const TRIAL_TRANSITIONS: Transitions<TrialState> = {
  // Starts ONLY in the activation transaction (§7) — nothing else may open it.
  not_started: ['active'],
  active: ['completed', 'canceled'],
  completed: ['converted', 'canceled'],
  converted: [],
  canceled: [],
}

function can<S extends string>(t: Transitions<S>, from: S, to: S): boolean {
  return (t[from] ?? []).includes(to)
}

export const canTransitionEnrollment = (f: EnrollmentState, t: EnrollmentState) => can(ENROLLMENT_TRANSITIONS, f, t)
export const canTransitionBrokerage = (f: BrokerageState, t: BrokerageState) => can(BROKERAGE_TRANSITIONS, f, t)
export const canTransitionAgentConfig = (f: AgentConfigState, t: AgentConfigState) => can(AGENT_CONFIG_TRANSITIONS, f, t)
export const canTransitionTrading = (f: TradingState, t: TradingState) => can(TRADING_TRANSITIONS, f, t)
export const canTransitionTrial = (f: TrialState, t: TrialState) => can(TRIAL_TRANSITIONS, f, t)

/** Terminal states never transition again — asserted in tests so a future edit can't reopen one. */
export const TERMINAL = {
  enrollment: ['complete'] as EnrollmentState[],
  agentConfig: ['archived'] as AgentConfigState[],
  trading: ['revoked'] as TradingState[],
  trial: ['converted', 'canceled'] as TrialState[],
}
