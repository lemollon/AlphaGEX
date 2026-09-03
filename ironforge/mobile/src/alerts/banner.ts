import type { LiveAgent, BrokerageConnections } from '@/api/types'
import { health } from '@/api/brokerage'
import { color } from '@/theme/tokens'
import { agentDetailHref } from '@/agents/routes'

/**
 * The ONE banner shown above the Forge tab's agent tiles (APP-016).
 *
 * Only one, ever — a stack of banners is a stack nobody reads. `pickBanner` is the
 * priority list as a pure function so the ordering itself is tested rather than
 * trusted to whatever `if` chain a screen happens to write. Severity order (most to
 * least urgent), per SPEC.md:
 *
 *   brokerage disconnected/auth expired > account restricted (BLOCKED) >
 *   ACTION_REQUIRED > membership payment due > paused > market no_trading > caution
 */
export type BannerSeverity =
  | 'brokerage'
  | 'blocked'
  | 'action_required'
  | 'payment'
  | 'paused'
  | 'no_trading'
  | 'caution'

export type BannerTarget = 'brokerage' | 'billing' | 'agent'

export interface Banner {
  severity: BannerSeverity
  /** Hex colour from theme/tokens — color.neg / color.warn / color.muted. */
  color: string
  text: string
  action: { label: string; target: BannerTarget; bot?: string } | null
  /** Only 'caution' may be dismissed — every more urgent banner persists (SPEC.md). */
  dismissible: boolean
}

export interface BannerInput {
  connections: BrokerageConnections | undefined
  agents: LiveAgent[]
  membershipBadge: string | undefined
  marketCondition: 'good' | 'caution' | 'no_trading' | undefined
  conditionLine: string | undefined
}

export function pickBanner(input: BannerInput): Banner | null {
  const connections = input.connections?.connections ?? []
  const brokenConnection = connections.find((c) => {
    const h = health(c.status)
    return h.key === 'disconnected' || h.key === 'restricted'
  })
  if (brokenConnection) {
    const name = brokenConnection.broker ?? brokenConnection.provider
    return {
      severity: 'brokerage',
      color: color.neg,
      text: `${name} needs attention — reconnect it so your agents can keep trading.`,
      action: { label: 'Fix in Account', target: 'brokerage' },
      dismissible: false,
    }
  }

  const blocked = input.agents.find((a) => a.state?.key === 'BLOCKED')
  if (blocked) {
    return {
      severity: 'blocked',
      color: color.neg,
      text: blocked.state?.check_line ?? `${blocked.label} is blocked from trading.`,
      action: { label: 'View', target: 'agent', bot: blocked.bot },
      dismissible: false,
    }
  }

  const actionRequired = input.agents.find((a) => a.state?.key === 'ACTION_REQUIRED')
  if (actionRequired) {
    return {
      severity: 'action_required',
      color: color.warn,
      text: actionRequired.state?.check_line ?? `${actionRequired.label} needs your attention.`,
      action: { label: 'View', target: 'agent', bot: actionRequired.bot },
      dismissible: false,
    }
  }

  if (input.membershipBadge === 'Payment due') {
    return {
      severity: 'payment',
      color: color.warn,
      text: 'Your payment is past due. Update billing to keep your agents trading.',
      action: { label: 'Manage Billing', target: 'billing' },
      dismissible: false,
    }
  }

  const paused = input.agents.find((a) => a.state?.key === 'PAUSED')
  if (paused) {
    return {
      severity: 'paused',
      color: color.muted,
      text: paused.state?.check_line ?? `${paused.label} is paused — no new trades will open.`,
      action: { label: 'View', target: 'agent', bot: paused.bot },
      dismissible: false,
    }
  }

  if (input.marketCondition === 'no_trading') {
    return {
      severity: 'no_trading',
      color: color.warn,
      text: input.conditionLine ?? 'Trading is currently halted.',
      action: null,
      dismissible: false,
    }
  }

  if (input.marketCondition === 'caution') {
    return {
      severity: 'caution',
      color: color.warn,
      text: input.conditionLine ?? 'Market conditions are elevated right now.',
      action: null,
      dismissible: true,
    }
  }

  return null
}

/** Resolves a banner's action into the href the Forge tab should navigate to. */
export function bannerActionHref(action: NonNullable<Banner['action']>): string | null {
  if (action.target === 'brokerage') return '/account'
  if (action.target === 'billing') return '/account'
  if (action.target === 'agent' && action.bot) return agentDetailHref(action.bot as 'spark' | 'flame')
  return null
}
