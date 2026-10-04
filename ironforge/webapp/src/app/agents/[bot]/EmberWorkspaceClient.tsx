'use client'

import useSWR from 'swr'
import Link from 'next/link'
import { fetcher } from '@/lib/fetcher'
import CustomerShell, { type PlanCardData } from '@/components/customer/CustomerShell'
import { EMBER_AGENT } from '@/lib/agents/ember'

interface SummaryResp { membership?: PlanCardData | null }
interface EntitlementsResp { bots?: string[] }

/**
 * Ember's customer workspace — honest empty state, no fabricated trades/P&L.
 *
 * EMBER is a single agent (no sub-agent picker — Leron, 2026-10-04, binding). Internally
 * it runs on REFLEX (dev/meltup/ember/run_reflex.py), a SEPARATE, ALREADY-ARMED
 * live-equities sleeve on a Robinhood "Agentic" account (570892331). REFLEX:
 *   - computes NO signal of its own — it polls a reactive-momentum squeeze signal
 *     computed server-side by AlphaGEX/spreadworks (squeeze_reactive_alerts.py) at
 *     GET https://spreadworks-backend.onrender.com/api/spreadworks/squeeze-reactive/state
 *   - persists its own position/order state to a LOCAL reflex_state.json on whatever
 *     machine runs its scheduled task — not a shared database this webapp can read
 *   - is NOT wired to any ironforge/webapp API today
 *
 * MISSING ENDPOINT (what would make this real): a read-only
 * `GET /api/ember/positions` (or similar) backed by either (a) REFLEX's own
 * reflex_state.json synced somewhere queryable, or (b) a new read-only route added to
 * the SpreadWorks backend that reads the Robinhood account directly. Until one of those
 * exists, this page can only show real ENROLLMENT state (does the customer own Ember,
 * and since when) — never trades, P&L, or "Trading now", which would be fabricated.
 *
 * No order-placing path, no arming change, nothing live-money touched by this file.
 */
export default function EmberWorkspaceClient() {
  const { data: summary } = useSWR<SummaryResp>('/api/live/summary', fetcher, { refreshInterval: 60_000 })
  const { data: entitlements } = useSWR<EntitlementsResp>('/api/billing/entitlements', fetcher, { shouldRetryOnError: false })

  const owned = entitlements?.bots ?? []
  const known = entitlements !== undefined
  const ownsEmber = owned.includes('ember')

  return (
    <CustomerShell membership={summary?.membership ?? null} planVariant="trial">
      <div className="flex items-center gap-3">
        <span
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-bold text-white"
          style={{ backgroundColor: EMBER_AGENT.accent }}
        >
          E
        </span>
        <div>
          <h1 className="text-2xl font-bold text-white">{EMBER_AGENT.name}</h1>
          <p className="text-sm text-gray-400">{EMBER_AGENT.sub}</p>
        </div>
      </div>

      {!known ? (
        <div className="mt-6 h-40 animate-pulse rounded-xl border border-forge-border bg-forge-card/40" />
      ) : !ownsEmber ? (
        <div className="mt-6 rounded-xl border border-forge-border bg-forge-card/80 p-6">
          <p className="text-sm text-gray-300">You don&rsquo;t have an Ember account yet.</p>
          <p className="mt-1 text-xs text-gray-500">
            Free · one account per person · $500–$2,000 trading capital.
          </p>
          <Link
            href="/enroll"
            className="mt-4 inline-flex items-center justify-center rounded-lg px-4 py-2.5 text-sm font-semibold text-white"
            style={{ backgroundColor: EMBER_AGENT.accent }}
          >
            Start Ember free
          </Link>
        </div>
      ) : (
        <div className="mt-6 rounded-xl border border-forge-border bg-forge-card/80 p-6">
          <p className="text-sm font-semibold text-white">Ember is enrolled on this account.</p>
          <p className="mt-2 text-sm text-gray-400">
            Trade history, open positions and profit/loss aren&rsquo;t shown here yet — IronForge
            has no live data connection to Ember&rsquo;s execution engine (REFLEX) today. Nothing
            fabricated is shown in its place.
          </p>
          <p className="mt-3 text-xs text-gray-500">
            Missing endpoint: a read-only positions/trades API for this agent. See this file&rsquo;s
            own comment for what that would require.
          </p>
        </div>
      )}
    </CustomerShell>
  )
}
