'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import { LIVE_BOT_LABEL, type LiveBot } from '@/lib/live/bots'
import type { LiveTrade } from '@/lib/live/types'
import type { HistoryTrade, OutcomeKind } from '@/lib/live/trades-history'

/**
 * Overview open-trade card + recent-trades list (dev-handoff #148/#150): "Dashboard
 * Overview still has no open-trade card and no recent-trades list — you have to drill
 * into an agent page to see either." Both widgets read the SAME customer-scoped APIs
 * the agent page (`/agents/{bot}`) and History tab already use —
 * `/api/live/trade?account=` and `/api/live/trades` — no new trading logic, no new
 * data source, just surfacing what already exists one level higher in the app.
 */

type TradeResp = ({ empty?: false } & LiveTrade) | { empty: true }

function signedFull(v: number): string {
  const a = Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return v > 0 ? `+$${a}` : v < 0 ? `-$${a}` : '$0.00'
}

function OpenTradeTile({ bot }: { bot: LiveBot }) {
  const { data } = useSWR<TradeResp>(`/api/live/trade?account=${bot}`, fetcher, { refreshInterval: 30_000 })
  if (!data || ('empty' in data && data.empty) || !data.active) return null

  const pnl = data.unrealized_pnl
  const accentClass = bot === 'flame' ? 'border-flame/25 bg-flame/5' : 'border-spark/25 bg-spark/5'
  const labelClass = bot === 'flame' ? 'text-flame' : 'text-spark'

  return (
    <Link
      href={`/agents/${bot}`}
      className={`flex items-center justify-between gap-3 rounded-lg border px-4 py-3 transition hover:border-[var(--line-2)] ${accentClass}`}
    >
      <div className="flex items-center gap-2 min-w-0">
        {/* db-dash #151: green dot marks an agent with a live open trade. */}
        <span className="h-2 w-2 shrink-0 rounded-full bg-[var(--up)]" aria-hidden />
        <div className="min-w-0">
          <div className={`text-sm font-semibold ${labelClass}`}>{LIVE_BOT_LABEL[bot]} · Open trade</div>
          <div className="truncate text-xs text-[var(--muted)]">
            {data.expires_label ? `Closes ${data.expires_label}` : 'Managing position'}
          </div>
        </div>
      </div>
      <div className={`shrink-0 font-mono text-sm font-bold ${pnl != null && pnl < 0 ? 'text-[var(--bad)]' : 'text-[var(--up)]'}`}>
        {pnl != null ? signedFull(pnl) : '—'}
      </div>
    </Link>
  )
}

/** One row per live bot the viewer owns; renders nothing (not even the section
 *  heading) when none has an open position — never an empty-state card for
 *  something that simply isn't happening right now. */
export function OpenTradesSection({ bots }: { bots: LiveBot[] }) {
  if (bots.length === 0) return null
  return (
    <section className="grid gap-2">
      {bots.map((b) => <OpenTradeTile key={b} bot={b} />)}
    </section>
  )
}

const OUTCOME_CLASS: Record<OutcomeKind, string> = {
  profit: 'text-[var(--up)]',
  auto: 'text-spark',
  stop: 'text-[var(--bad)]',
  manual: 'text-[var(--accent)]',
  expired: 'text-[var(--muted)]',
  other: 'text-[var(--muted)]',
}
const STRATEGY_CLASS: Record<string, string> = { Spark: 'text-spark', Flame: 'text-flame' }

type TradesResp =
  | { empty?: false; trades: HistoryTrade[] }
  | { empty: true }
  | { error: string }

/** Last 5 closed trades across every strategy the viewer owns — the same rows
 *  `/account/trades` (History tab) shows, just the newest page of them, inline. */
export function RecentTradesSection() {
  const { data } = useSWR<TradesResp>('/api/live/trades?limit=5', fetcher, { refreshInterval: 60_000 })
  if (!data || 'error' in data || ('empty' in data && data.empty)) return null
  const trades = 'trades' in data ? data.trades : []
  if (trades.length === 0) return null

  return (
    <section className="rounded-xl border border-[var(--line)] bg-[var(--bg)]/80 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-[var(--accent)]">Recent Trades</h3>
        <Link href="/dashboard?tab=history" className="text-xs font-semibold text-[var(--muted)] hover:text-[var(--fg)]">
          View all
        </Link>
      </div>
      <div className="mt-3 divide-y divide-[var(--line)]/60">
        {trades.map((t) => (
          <div key={t.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <span className={`text-sm font-semibold ${STRATEGY_CLASS[t.strategy] ?? 'text-[var(--fg)]'}`}>{t.strategy}</span>
                {t.paper && <span className="rounded bg-[var(--bg-2)] px-1 py-px text-[9px] font-bold uppercase tracking-wider text-[var(--muted)]">Paper</span>}
              </div>
              <div className="text-xs text-[var(--muted)]">
                {t.closed_ct ?? t.close_date} · <span className={OUTCOME_CLASS[t.outcome_kind]}>{t.outcome}</span>
              </div>
            </div>
            <div className={`shrink-0 font-mono text-sm font-bold ${t.pnl >= 0 ? 'text-[var(--up)]' : 'text-[var(--bad)]'}`}>
              {signedFull(t.pnl)}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
