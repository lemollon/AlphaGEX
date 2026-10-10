import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import LiveClient from '@/app/live/LiveClient'
import EmberWorkspaceClient from './EmberWorkspaceClient'
import { LIVE_BOT_LABEL, type LiveBot } from '@/lib/live/bots'
import { EMBER_AGENT } from '@/lib/agents/ember'

export const dynamic = 'force-dynamic'

/**
 * Customer agent workspace (UAT-008 / IF-NAV-001): each agent — Spark, Flame, Ember — is
 * a top-level destination that owns its trades, status, history, and controls. Replaces
 * the generic /live tab. Route is /agents/{bot}, NOT /{bot}: the bare names are the
 * operator console's namespace (surface.ts OPERATOR_PAGES) and must not collide.
 *
 * Ember is NOT a LiveBot (LiveClient reads `/api/{bot}/...` Postgres tables that exist
 * only for spark/flame — see ironforge/CLAUDE.md). Ember's execution engine is REFLEX
 * (dev/meltup/ember/run_reflex.py — already live-armed on a separate Robinhood account,
 * outside this webapp), which has no API wired into ironforge/webapp yet. Its workspace
 * is a separate, honest-empty-state client — see EmberWorkspaceClient's own comment for
 * the missing endpoint this would need.
 */
const CUSTOMER_AGENTS = new Set(['spark', 'flame', 'ember'])

export function generateMetadata({ params }: { params: { bot: string } }): Metadata {
  const label = params.bot === 'ember'
    ? EMBER_AGENT.name
    : CUSTOMER_AGENTS.has(params.bot)
      ? LIVE_BOT_LABEL[params.bot as LiveBot]
      : 'Agent'
  return {
    title: `${label} — IronForge`,
    description: `Real-time view of what ${label} is doing with your account.`,
  }
}

export default function AgentWorkspacePage({ params }: { params: { bot: string } }) {
  if (!CUSTOMER_AGENTS.has(params.bot)) notFound()
  if (params.bot === 'ember') return <EmberWorkspaceClient />
  return <LiveClient account={params.bot as LiveBot} />
}
