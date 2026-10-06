'use client'

import useSWR, { mutate } from 'swr'
import { useState } from 'react'
import Link from 'next/link'
import { fetcher } from '@/lib/fetcher'
import CustomerShell, { type PlanCardData } from '@/components/customer/CustomerShell'
import { EMBER_AGENT } from '@/lib/agents/ember'
import type { EmberStatusRow, EmberTradeRow } from '@/lib/ember-trades'

interface SummaryResp { membership?: PlanCardData | null }
interface EntitlementsResp { bots?: string[] }
interface TradesResp { ok: boolean; trades: EmberTradeRow[] }
interface StatusResp { ok: boolean; status: EmberStatusRow | null }
interface Activation { activation_id: string; agent: string; paused: boolean }
interface PauseResp { ok: boolean; activations: Activation[] }

const PAUSE_KEY = '/api/v1/automation/pause'

/**
 * Ember's Pause control (handoff #178 — "0 'pause' in EmberWorkspaceClient").
 * Wired to the same `/api/v1/automation/pause` flag Settings' Automation
 * section uses for Spark/Flame — see that route's comment on `agent === 'ember'`.
 * This only flips `activations.status`; Ember's actual execution (REFLEX,
 * dev/meltup/ember/run_reflex.py — a separate, already-armed sleeve) does not
 * read this table today, so pausing here is the customer's on-record request,
 * not yet an enforced stop. Never touches REFLEX itself.
 */
function EmberPauseControl() {
  const { data } = useSWR<PauseResp>(PAUSE_KEY, fetcher, { shouldRetryOnError: false })
  const [pending, setPending] = useState(false)
  const activation = data?.activations.find((a) => a.agent === 'ember')
  if (!activation) return null

  async function toggle() {
    setPending(true)
    try {
      await fetch(PAUSE_KEY, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paused: !activation!.paused, agent: 'ember' }),
      })
      await mutate(PAUSE_KEY)
    } finally {
      setPending(false)
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={pending}
      className="rounded-lg border border-[var(--line)] px-3 py-1.5 text-xs font-semibold text-[var(--fg)] transition-colors hover:bg-[var(--bg-2)] disabled:opacity-50"
    >
      {activation.paused ? 'Resume Ember' : 'Pause Ember'}
    </button>
  )
}

function signed(v: number): string {
  const a = Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return v > 0 ? `+$${a}` : v < 0 ? `-$${a}` : '$0.00'
}
function fmtTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

/** closed+profit = up, closed+loss = down, anything still open = neutral accent. */
function statusClass(status: string, pnl: number | null): string {
  if (status === 'closed') return pnl != null && pnl < 0 ? 'text-[var(--bad)]' : 'text-[var(--up)]'
  return 'text-[var(--muted)]'
}

/**
 * Ember's customer workspace. Shows EMBER's OWN trade book and status — not a
 * read of the customer's brokerage account; the agent books its own
 * positions and reports them here. No fabricated trades/P&L, ever: an owner
 * with no synced rows yet sees the honest empty state below, not seeded data.
 *
 * EMBER is a single agent (no sub-agent picker — Leron, 2026-10-04, binding). Internally
 * it runs on REFLEX (dev/meltup/ember/run_reflex.py), a SEPARATE, ALREADY-ARMED
 * live-equities sleeve on a Robinhood "Agentic" account (570892331). REFLEX:
 *   - computes NO signal of its own — it polls a reactive-momentum squeeze signal
 *     computed server-side by AlphaGEX/spreadworks (squeeze_reactive_alerts.py) at
 *     GET https://spreadworks-backend.onrender.com/api/spreadworks/squeeze-reactive/state
 *   - persists its own position/order state to a LOCAL reflex_state.json on whatever
 *     machine runs its scheduled task
 *   - is synced READ-ONLY into this webapp's own ember_trades/ember_status tables by
 *     dev/meltup/ember/reflex_sync.py, via POST /api/internal/ember/sync (shared-secret
 *     auth, never a browser caller) — see lib/ember-trades.ts
 *
 * This file never names REFLEX or shows it to the customer — only "Ember".
 * No order-placing path, no arming change, nothing live-money touched by this file.
 */
export default function EmberWorkspaceClient() {
  const { data: summary } = useSWR<SummaryResp>('/api/live/summary', fetcher, { refreshInterval: 60_000 })
  const { data: entitlements } = useSWR<EntitlementsResp>('/api/billing/entitlements', fetcher, { shouldRetryOnError: false })

  const owned = entitlements?.bots ?? []
  const known = entitlements !== undefined
  const ownsEmber = owned.includes('ember')

  // Only fetched once ownership is confirmed — an unowned customer never even
  // issues the request (the API 403s server-side too, this just skips the
  // round-trip and the SWR error state in the common case).
  const { data: tradesResp } = useSWR<TradesResp>(ownsEmber ? '/api/ember/trades' : null, fetcher, {
    refreshInterval: 60_000,
    shouldRetryOnError: false,
  })
  const { data: statusResp } = useSWR<StatusResp>(ownsEmber ? '/api/ember/status' : null, fetcher, {
    refreshInterval: 60_000,
    shouldRetryOnError: false,
  })
  const trades = tradesResp?.trades ?? []
  const status = statusResp?.status ?? null

  return (
    <CustomerShell membership={summary?.membership ?? null} planVariant="trial">
      <div className="flex items-center gap-3">
        <span
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-bold text-[var(--fg)]"
          style={{ backgroundColor: EMBER_AGENT.accent }}
        >
          E
        </span>
        <div>
          <h1 className="text-2xl font-bold text-[var(--fg)]">{EMBER_AGENT.name}</h1>
          <p className="text-sm text-[var(--muted)]">{EMBER_AGENT.sub}</p>
        </div>
      </div>

      {!known ? (
        <div className="mt-6 h-40 animate-pulse rounded-xl border border-[var(--line)] bg-[var(--bg-2)]" />
      ) : !ownsEmber ? (
        <div className="mt-6 rounded-xl border border-[var(--line)] bg-[var(--bg)]/80 p-6">
          <p className="text-sm text-[var(--muted)]">You don&rsquo;t have an Ember account yet.</p>
          <p className="mt-1 text-xs text-[var(--muted)]">
            Free · one account per person · $500–$2,000 trading capital.
          </p>
          <Link
            href="/enroll"
            className="mt-4 inline-flex items-center justify-center rounded-lg px-4 py-2.5 text-sm font-semibold text-[var(--fg)]"
            style={{ backgroundColor: EMBER_AGENT.accent }}
          >
            Start Ember free
          </Link>
        </div>
      ) : (
        <>
          {/* Status strip */}
          <div
            className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--line)] bg-[var(--bg)]/80 p-4"
            style={{ borderColor: status ? `${EMBER_AGENT.accent}40` : undefined }}
          >
            <div className="flex items-center gap-3">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: status?.state === 'ok' ? 'var(--up)' : status ? EMBER_AGENT.accent : 'var(--muted)' }}
              />
              <span className="text-sm font-semibold text-[var(--fg)]">
                {status ? `Ember is ${status.state ?? 'reporting'}` : 'Waiting on Ember’s first report'}
              </span>
            </div>
            <div className="flex items-center gap-4 text-xs text-[var(--muted)]">
              <span>Last update: {fmtTime(status?.last_heartbeat ?? null)}</span>
              <span>
                Open positions:{' '}
                {Array.isArray(status?.open_positions) ? (status!.open_positions as unknown[]).length : 0}
              </span>
              <EmberPauseControl />
            </div>
          </div>

          {/* Trade book */}
          {trades.length === 0 ? (
            <div className="mt-4 rounded-xl border border-[var(--line)] bg-[var(--bg)]/80 p-6">
              <p className="text-sm font-semibold text-[var(--fg)]">No trades yet.</p>
              <p className="mt-2 text-sm text-[var(--muted)]">
                Ember hasn&rsquo;t opened a position yet. Its trade history and profit/loss will
                show up here, from Ember&rsquo;s own book — not your brokerage account&rsquo;s
                overall activity.
              </p>
            </div>
          ) : (
            <div className="mt-4 overflow-x-auto rounded-xl border border-[var(--line)] bg-[var(--bg)]/80">
              <table className="w-full min-w-[720px] text-sm">
                <thead>
                  <tr className="border-b border-[var(--line)] text-left text-xs uppercase tracking-wider text-[var(--muted)]">
                    <th className="px-4 py-3 font-semibold">Opened</th>
                    <th className="px-4 py-3 font-semibold">Closed</th>
                    <th className="px-4 py-3 font-semibold">Symbol</th>
                    <th className="px-4 py-3 font-semibold">Qty</th>
                    <th className="px-4 py-3 font-semibold">Entry</th>
                    <th className="px-4 py-3 font-semibold">Exit</th>
                    <th className="px-4 py-3 text-right font-semibold">P&amp;L</th>
                    <th className="px-4 py-3 text-right font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t) => {
                    const pnl = t.pnl != null ? Number(t.pnl) : null
                    return (
                      <tr key={t.id} className="border-b border-[var(--line)]/60 last:border-0 hover:bg-[var(--bg-2)]">
                        <td className="whitespace-nowrap px-4 py-3 text-[var(--muted)]">{fmtTime(t.opened_at)}</td>
                        <td className="whitespace-nowrap px-4 py-3 text-[var(--muted)]">{fmtTime(t.closed_at)}</td>
                        <td className="whitespace-nowrap px-4 py-3 font-semibold text-[var(--fg)]">{t.symbol}</td>
                        <td className="whitespace-nowrap px-4 py-3 text-[var(--muted)]">{t.qty ?? '—'}</td>
                        <td className="whitespace-nowrap px-4 py-3 text-[var(--muted)]">{t.entry_price ?? '—'}</td>
                        <td className="whitespace-nowrap px-4 py-3 text-[var(--muted)]">{t.exit_price ?? '—'}</td>
                        <td className={`whitespace-nowrap px-4 py-3 text-right font-mono font-semibold ${pnl != null ? (pnl >= 0 ? 'text-[var(--up)]' : 'text-[var(--bad)]') : 'text-[var(--muted)]'}`}>
                          {pnl != null ? signed(pnl) : '—'}
                        </td>
                        <td className={`whitespace-nowrap px-4 py-3 text-right font-medium capitalize ${statusClass(t.status, pnl)}`}>
                          {t.status}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
          <p className="mt-3 text-xs text-[var(--muted)]">
            These are Ember&rsquo;s own trades — not a summary of every trade in your brokerage
            account.
          </p>
        </>
      )}
    </CustomerShell>
  )
}
