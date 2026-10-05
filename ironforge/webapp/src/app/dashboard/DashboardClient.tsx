'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { useRouter, useSearchParams } from 'next/navigation'
import { fetcher } from '@/lib/fetcher'
import CustomerShell from '@/components/customer/CustomerShell'
import type { LiveSummary } from '@/lib/live/types'
import { LIVE_BOT_LABEL, LIVE_BOTS } from '@/lib/live/bots'
import { EMBER_AGENT } from '@/lib/agents/ember'
import OverviewBody from './OverviewBody'
import { CommunityBody } from '@/app/community/CommunityClient'
import { TradeHistoryBody } from '@/app/account/trades/TradeHistoryClient'
import { SettingsBody } from '@/app/settings/SettingsClient'

/**
 * `/dashboard` — the real member landing page (dev-handoff §6): a single
 * tabbed shell for Overview / [Agent] / Community / History / Settings.
 * Gap audit: `/dashboard` 302'd to `/ops/login` and didn't exist for
 * customers at all; the tab structure was split into five separate routes.
 *
 * Overview, Community, History and Settings render INLINE (same page, no
 * navigation) via the extracted *Body components below — matching the
 * spec's "single page, tabs" structure exactly. Spark/Flame/Ember/+Agent are
 * full-trust trading surfaces with their own SSE streams, pause controls and
 * ledger-switch state (LiveClient/EmberWorkspaceClient); rather than fork that
 * logic into a second inline copy, those tabs navigate to their existing,
 * already-correct `/agents/{bot}` and `/live/{bot}/open` routes — same
 * CustomerShell chrome, so the experience reads as one continuous app.
 */

type TabKey = 'overview' | 'community' | 'history' | 'settings'

const INLINE_TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'overview', label: 'Overview' },
  { key: 'community', label: 'Community' },
  { key: 'history', label: 'History' },
  { key: 'settings', label: 'Settings' },
]

interface Entitlements { bots?: string[] }

export default function DashboardClient() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const tabParam = searchParams.get('tab')
  const tab: TabKey = (INLINE_TABS.some((t) => t.key === tabParam) ? tabParam : 'overview') as TabKey

  const { data: summary } = useSWR<LiveSummary>('/api/live/summary', fetcher)
  const { data: ent } = useSWR<Entitlements>('/api/billing/entitlements', fetcher, { shouldRetryOnError: false })
  const owned = new Set(ent?.bots ?? [])
  const bots = LIVE_BOTS

  function setTab(next: TabKey) {
    router.replace(`/dashboard?tab=${next}`, { scroll: false })
  }

  return (
    <CustomerShell membership={summary?.membership ?? null}>
      {/* Tab bar — Overview/[Agent]/+Agent/Community/History/Settings, in the
          order the dev-handoff table lists them. */}
      <div className="flex flex-wrap items-center gap-1.5 border-b border-[var(--line)] pb-3">
        {INLINE_TABS.map((t) => (
          <button key={t.key} type="button" onClick={() => setTab(t.key)}
            aria-current={tab === t.key ? 'page' : undefined}
            className={`rounded-full px-3.5 py-1.5 text-sm font-semibold transition-colors ${
              tab === t.key
                ? 'bg-[var(--accent)] text-[var(--accent-ink)]'
                : 'text-[var(--muted)] hover:bg-[var(--bg-2)] hover:text-[var(--fg)]'
            }`}>
            {t.label}
          </button>
        ))}
        <span className="mx-1 h-5 w-px bg-[var(--line)]" aria-hidden />
        {bots.map((b) => {
          const isOwned = owned.has(b)
          return (
            <Link key={b} href={isOwned ? `/agents/${b}` : `/live/${b}/open`}
              className={`flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm font-semibold transition-colors ${
                isOwned
                  ? (b === 'flame' ? 'border-flame/30 text-flame hover:bg-flame/10' : 'border-spark/30 text-spark hover:bg-spark/10')
                  : 'border-dashed border-[var(--line-2)] text-[var(--muted)] hover:text-[var(--fg)]'
              }`}>
              {LIVE_BOT_LABEL[b]}
              {!isOwned && <span className="text-xs">+ Add</span>}
            </Link>
          )
        })}
        {owned.has('ember') && (
          <Link href="/agents/ember"
            className="flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm font-semibold transition-colors"
            style={{ borderColor: `${EMBER_AGENT.accent}4d`, color: EMBER_AGENT.accent }}>
            {EMBER_AGENT.name}
          </Link>
        )}
      </div>

      <div className="pt-4">
        {tab === 'overview' && <OverviewBody />}
        {tab === 'community' && <CommunityBody />}
        {tab === 'history' && <TradeHistoryBody />}
        {tab === 'settings' && <SettingsBody />}
      </div>
    </CustomerShell>
  )
}
