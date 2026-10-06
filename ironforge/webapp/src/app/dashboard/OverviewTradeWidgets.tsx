'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import { Area, AreaChart, ResponsiveContainer } from 'recharts'
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

function isActiveTrade(data: TradeResp | undefined): data is LiveTrade {
  return !!data && !('empty' in data && data.empty) && !!(data as LiveTrade).active
}

function signedFull(v: number): string {
  const a = Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return v > 0 ? `+$${a}` : v < 0 ? `-$${a}` : '$0.00'
}

/** "Updated Xs ago" — ticks once a second off the SWR hook's own fetchedAt,
 *  not a fixed re-render of the 30s refresh interval, so it reads honestly
 *  between polls too (gap audit "'updated a few seconds ago'" MISSING). */
function useUpdatedLabel(fetchedAt: number | null): string {
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    if (fetchedAt == null) return
    const id = setInterval(() => setNowMs(Date.now()), 1000)
    return () => clearInterval(id)
  }, [fetchedAt])
  if (fetchedAt == null) return ''
  const secs = Math.max(0, Math.round((nowMs - fetchedAt) / 1000))
  if (secs < 5) return 'Updated just now'
  if (secs < 60) return `Updated ${secs}s ago`
  return `Updated ${Math.round(secs / 60)}m ago`
}

/** Progress toward the position's target, or toward its stop when underwater —
 *  the "progress bar" the design's full open-trade card calls for. Renders
 *  nothing when either rail is unknown (never a bar with a fabricated range). */
function TargetStopBar({ pnl, target, stop }: { pnl: number | null; target: number | null; stop: number | null }) {
  if (pnl == null || target == null || stop == null || target <= 0 || stop >= 0) return null
  const towardTarget = pnl >= 0
  const pct = Math.min(100, Math.max(0, Math.round((Math.abs(pnl) / Math.abs(towardTarget ? target : stop)) * 100)))
  return (
    <div className="mt-2">
      <div className="h-1.5 overflow-hidden rounded-full bg-[var(--bg-2)]">
        <div
          className={towardTarget ? 'bg-[var(--up)]' : 'bg-[var(--bad)]'}
          style={{ width: `${pct}%`, height: '100%', borderRadius: 'inherit' }}
        />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-[var(--muted)]">
        <span>{signedFull(stop)} stop</span>
        <span>{signedFull(target)} target</span>
      </div>
    </div>
  )
}

/** Tiny sparkline off the same per-position `series` the agent workspace's
 *  LiveTradeCard charts, scaled down for the Overview tile. */
function MiniChart({ series, up }: { series: Array<{ timestamp: string; pnl: number }>; up: boolean }) {
  if (series.length < 2) return null
  const data = series.map((p) => ({ pnl: p.pnl }))
  const color = up ? '#4ade80' : '#f87171'
  return (
    <div className="h-8 w-20 shrink-0">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
          <Area type="monotone" dataKey="pnl" stroke={color} strokeWidth={1.5} fill={color} fillOpacity={0.12} isAnimationActive={false} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

function OpenTradeTile({ bot, onStatus }: { bot: LiveBot; onStatus?: (bot: LiveBot, open: boolean) => void }) {
  const [fetchedAt, setFetchedAt] = useState<number | null>(null)
  const { data } = useSWR<TradeResp>(`/api/live/trade?account=${bot}`, fetcher, {
    refreshInterval: 30_000,
    onSuccess: () => setFetchedAt(Date.now()),
  })
  const updatedLabel = useUpdatedLabel(fetchedAt)
  const isOpen = isActiveTrade(data)
  useEffect(() => {
    if (data !== undefined) onStatus?.(bot, isOpen)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bot, data, isOpen])
  if (!isOpen || !data) return null

  const pnl = data.unrealized_pnl
  const series = data.positions?.[0]?.series ?? []
  const up = pnl == null ? true : pnl >= 0
  const accentClass = bot === 'flame' ? 'border-flame/25 bg-flame/5' : 'border-spark/25 bg-spark/5'
  const labelClass = bot === 'flame' ? 'text-flame' : 'text-spark'

  return (
    <Link
      href={`/agents/${bot}`}
      className={`block rounded-lg border px-4 py-3 transition hover:border-[var(--line-2)] ${accentClass}`}
    >
      <div className="flex items-center justify-between gap-3">
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
        <MiniChart series={series} up={up} />
        <div className={`shrink-0 font-mono text-sm font-bold ${pnl != null && pnl < 0 ? 'text-[var(--bad)]' : 'text-[var(--up)]'}`}>
          {pnl != null ? signedFull(pnl) : '—'}
        </div>
      </div>
      <TargetStopBar pnl={pnl} target={data.target_dollars} stop={data.stop_dollars} />
      {updatedLabel && <div className="mt-2 text-[10px] text-[var(--muted)]">{updatedLabel}</div>}
    </Link>
  )
}

/** One row per live bot the viewer owns. Renders an explicit empty state
 *  (gap audit MISSING — previously rendered nothing at all) rather than
 *  disappearing, so "nothing is open right now" reads as a real answer and
 *  not as a broken widget. Each tile reports its own loaded/open status up
 *  via `onStatus` rather than this section re-fetching the same data in a
 *  hook loop. */
export function OpenTradesSection({ bots }: { bots: LiveBot[] }) {
  const [status, setStatus] = useState<Partial<Record<LiveBot, boolean>>>({})
  if (bots.length === 0) return null

  const onStatus = (bot: LiveBot, open: boolean) => setStatus((s) => (s[bot] === open ? s : { ...s, [bot]: open }))
  const allLoaded = bots.every((b) => status[b] !== undefined)
  const anyOpen = bots.some((b) => status[b])

  return (
    <section className="grid gap-2">
      {bots.map((b) => <OpenTradeTile key={b} bot={b} onStatus={onStatus} />)}
      {allLoaded && !anyOpen && (
        <div className="rounded-lg border border-[var(--line)] bg-[var(--bg)]/60 px-4 py-3 text-sm text-[var(--muted)]">
          No trade open right now.
        </div>
      )}
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
