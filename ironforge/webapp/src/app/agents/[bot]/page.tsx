import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import LiveClient from '@/app/live/LiveClient'
import { LIVE_BOT_LABEL, type LiveBot } from '@/lib/live/bots'

export const dynamic = 'force-dynamic'

/**
 * Customer agent workspace (UAT-008 / IF-NAV-001): each agent — Spark, Flame — is a
 * top-level destination that owns its trades, status, history, and controls. Replaces
 * the generic /live tab. Route is /agents/{bot}, NOT /{bot}: the bare names are the
 * operator console's namespace (surface.ts OPERATOR_PAGES) and must not collide.
 *
 * Only the two customer-purchasable agents resolve here; anything else 404s.
 */
const CUSTOMER_AGENTS = new Set(['spark', 'flame'])

export function generateMetadata({ params }: { params: { bot: string } }): Metadata {
  const label = CUSTOMER_AGENTS.has(params.bot) ? LIVE_BOT_LABEL[params.bot as LiveBot] : 'Agent'
  return {
    title: `${label} — IronForge`,
    description: `Real-time view of what ${label} is doing with your account.`,
  }
}

export default function AgentWorkspacePage({ params }: { params: { bot: string } }) {
  if (!CUSTOMER_AGENTS.has(params.bot)) notFound()
  return <LiveClient account={params.bot as LiveBot} />
}
