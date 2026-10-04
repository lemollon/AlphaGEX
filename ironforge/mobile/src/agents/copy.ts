import type { AgentBot } from '@/agents/routes'

/**
 * Factual agent copy for the overview (APP-023) and detail (APP-024) screens.
 *
 * Sourced from the webapp's own product truth rather than invented here:
 *   - structure/cadence: webapp/src/lib/billing/plans.ts (BOT_PLANS) — "same-day (0DTE)
 *     SPY put credit spreads", Spark each morning, Flame each afternoon. This is the
 *     CURRENT product description, current as of the 2026-08-16 note in that file.
 *   - risk shape: webapp/src/app/_home/DefinedRiskCard.tsx — "Both ends are fixed
 *     before the position opens", i.e. a defined-risk credit spread.
 *   - account requirements: webapp/src/lib/enrollment/activation.ts (evaluateActivation)
 *     — the actual predicate the server enforces before trading may activate.
 *
 * 🚨 webapp/src/lib/support/knowledge.ts (Sparky's FAQ) still describes Spark as 1DTE
 * and Flame as 2DTE — that is the OLDER structure, superseded by BOT_PLANS. Flagged in
 * the WP-C report; whoever owns that FAQ should reconcile it, this file does not.
 *
 * No return, win-rate or outcome language anywhere here — describes the mechanism
 * only, never a promise.
 *
 * Ember added for the 10.4 redesign (handoff/ironforge-10.4-design-spec.md §3) — a
 * single free agent for smaller accounts, one per person, $500–$2,000 capital. Its
 * internal strategy name "REFLEX" is Leron-confirmed never customer-facing (2026-
 * 10-04): no mechanism language for Ember beyond what the design doc itself states,
 * since the strategy's real structure/cadence isn't published copy anywhere else in
 * this repo and must not be invented here.
 */

export const AGENT_LABEL: Record<AgentBot, string> = {
  spark: 'Spark',
  flame: 'Flame',
  ember: 'Ember',
}

/** One line for the overview card. */
export const AGENT_BLURB: Record<AgentBot, string> = {
  spark:
    'Same-day (0DTE) SPY put credit spreads, entered each morning — the lower-risk, steadier-paced agent.',
  flame:
    'Same-day (0DTE) SPY put credit spreads, entered each afternoon. Flame uses its standard VIX regime through 0.80 and can add qualifying days through 0.925 when the prior SPY session was up and credit is at least $0.20.',
  ember:
    'Free, built for smaller accounts and first-time investors. One Ember account per person, funded with $500 to $2,000 in trading capital.',
}

/** Longer description for the detail screen. */
export const AGENT_DESCRIPTION: Record<AgentBot, string> = {
  spark:
    'Spark trades same-day (0DTE) SPY put credit spreads, opened each morning while the market is open. It is the lower-risk, steadier-paced of the two agents.',
  flame:
    'Flame trades same-day (0DTE) SPY put credit spreads, opened each afternoon while the market is open. Its standard VIX regime runs through 0.80; added days can run through 0.925 only after an up prior SPY session and with at least $0.20 credit. It is the higher-risk agent, aiming for near-term upside within the same day.',
  ember:
    'Ember is built for smaller accounts and people new to investing, aiming for steady growth. It has no monthly fee, is limited to one account per person, and trades with $500 to $2,000 in capital.',
}

export const ACCOUNT_REQUIREMENTS =
  'To trade live, an agent needs: a connected brokerage account that is funded and eligible for automated options trading, an active IronForge membership with a valid payment method, and the current agreements accepted.'

export const TRADING_SCHEDULE: Record<AgentBot, string> = {
  spark:
    'Looks for a new position each morning while the market is open. It does not enter new trades outside that window. Any position already open continues to be managed by the agent’s risk rules until it closes.',
  flame:
    'Looks for a new position each afternoon while the market is open. It does not enter new trades outside that window. Any position already open continues to be managed by the agent’s risk rules until it closes.',
  // The design doc's own agent-identity table lists Ember's session as "To be
  // confirmed" (one prototype screen contradicts this with a concrete 9–2 CT window
  // that the design handoff itself flags as unresolved) — this stays unresolved
  // rather than guessing a schedule the product hasn't committed to.
  ember: 'Session to be confirmed. Any position already open continues to be managed by the agent’s risk rules until it closes.',
}

/** Ember's account rule (design-spec §3/§4, verbatim quantities) — surfaced
 *  wherever Spark/Flame's $X/month price would otherwise appear. */
export const EMBER_LIMITS = {
  priceLabel: 'Free',
  perPersonLimit: 1,
  minCapitalCents: 50_000,
  maxCapitalCents: 200_000,
} as const

export const RISK_SUMMARY =
  'Each position is a defined-risk credit spread: the maximum possible gain and the maximum possible loss are both fixed before the trade opens. That structure limits how bad a single trade can be — it does not remove the risk of loss, and trading options involves risk on every trade.'
