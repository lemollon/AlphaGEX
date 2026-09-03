import type { AgentBot } from '@/agents/routes'

/**
 * The single action a customer can take on an agent card (APP-023) — one verdict,
 * computed the same way for the overview grid and the detail screen, so the two
 * screens can never disagree about what a tap should do.
 *
 * Kept pure and tested here rather than left as inline JSX branching: five states
 * that decide whether a screen offers "manage a live agent" or "authorize trading
 * on real money" is exactly the kind of rule that must not silently drift.
 */
export type AgentActionKind = 'active' | 'paused' | 'add' | 'setup_required' | 'switch'

export interface AgentAction {
  kind: AgentActionKind
  label: string
}

/** The shape of one row from GET /api/v1/automation/pause — only what this rule needs. */
export interface ActivationLike {
  agent: string
  paused: boolean
}

export interface AgentActionInput {
  bot: AgentBot
  /** Bots this customer's membership currently entitles them to (billing/entitlements). */
  entitlements: string[]
  /** Every activation the viewer owns, across both agents. */
  activations: ActivationLike[]
  /** Brokerage accounts connected AND eligible for automated options trading. */
  eligibleAccountCount: number
}

function otherBot(bot: AgentBot): AgentBot {
  return bot === 'spark' ? 'flame' : 'spark'
}

export function agentAction(input: AgentActionInput): AgentAction {
  const mine = input.activations.find((a) => a.agent === input.bot)

  // Owned + an activation already exists — Active or Paused, whichever the server
  // says. Membership state does not matter here: the activation record IS the
  // authority already granted, not something still being requested.
  if (mine) {
    return mine.paused ? { kind: 'paused', label: 'Paused' } : { kind: 'active', label: 'Active' }
  }

  // No activation, and nothing eligible to trade through — the honest next step is
  // "connect an account", not "activate", because activation cannot succeed either
  // way.
  if (input.eligibleAccountCount === 0) {
    return { kind: 'setup_required', label: 'Setup Required' }
  }

  // With exactly one eligible account and the OTHER agent already actively trading
  // it, a second activation cannot describe a second account — it would only ever
  // mean displacing the one that is running. That is a switch, not an add.
  const otherActive = input.activations.some((a) => a.agent === otherBot(input.bot) && !a.paused)
  if (otherActive && input.eligibleAccountCount === 1) {
    return { kind: 'switch', label: 'Switch' }
  }

  // Membership entitlement is not re-checked here: a customer who is not entitled
  // yet still sees "Add" and the activation flow itself surfaces the billing
  // blocker (MEMBERSHIP_NOT_ACTIVE) rather than this screen guessing at billing
  // state ahead of the server.
  return { kind: 'add', label: 'Add' }
}
