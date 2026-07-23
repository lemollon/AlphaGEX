'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import type { LiveBot } from '@/lib/live/bots'
import type { HistoryTrade, OutcomeKind } from '@/lib/live/trades-history'
import LiveSidebar from '../../live/components/LiveSidebar'

type Resp =
  | { empty?: false; trades: HistoryTrade[]; viewer: { allowedBots: LiveBot[]; paperBots: LiveBot[] } }
  | { empty: true; viewer: { allowedBots: LiveBot[]; paperBots: LiveBot[] } }
  | { error: string }

const OUTCOME_CLASS: Record<OutcomeKind, string> = {
  profit: 'text-emerald-400',
  auto: 'text-spark',
  stop: 'text-red-400',
  manual: 'text-amber-400',
  expired: 'text-gray-400',
  other: 'text-gray-400',
}
const STRATEGY_CLASS: Record<string, string> = { Spark: 'text-spark', Flame: 'text-flame' }

function fmtDate(d: string): string {
  const dt = new Date(`${d}T12:00:00`)
  if (isNaN(dt.getTime())) return d
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
function signed(v: number): string {
  const r = Math.round(v)
  return r > 0 ? `+$${r.toLocaleString('en-US')}.00` : r < 0 ? `-$${Math.abs(r).toLocaleString('en-US')}.00` : '$0.00'
}
function signedFull(v: number): string {
  const a = Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return v > 0 ? `+$${a}` : v < 0 ? `-$${a}` : '$0.00'
}

const RANGES = [
  { key: '30', label: 'Last 30 Days', days: 30 },
  { key: '7', label: 'Last 7 Days', days: 7 },
  { key: '90', label: 'Last 90 Days', days: 90 },
  { key: 'all', label: 'All Time', days: 0 },
] as const

export default function TradeHistoryClient() {
  const { data, error } = useSWR<Resp>('/api/live/trades', fetcher, { refreshInterval: 60_000, shouldRetryOnError: false })
  const [q, setQ] = useState('')
  const [strategy, setStrategy] = useState<'all' | string>('all')
  const [range, setRange] = useState<(typeof RANGES)[number]['key']>('30')

  const isEmpty = data && 'empty' in data && data.empty
  const isErr = (data && 'error' in data) || (error && !data)
  const trades = data && 'trades' in data ? data.trades : []
  const allowedBots = (data && 'viewer' in data ? data.viewer.allowedBots : []) as LiveBot[]
  const paperBots = (data && 'viewer' in data ? data.viewer.paperBots : []) as LiveBot[]

  const strategies = useMemo(() => Array.from(new Set(trades.map((t) => t.strategy))), [trades])

  const rows = useMemo(() => {
    const days = RANGES.find((r) => r.key === range)?.days ?? 0
    const cutoff = days > 0 ? Date.now() - days * 86_400_000 : 0
    const needle = q.trim().toLowerCase()
    return trades.filter((t) => {
      if (strategy !== 'all' && t.strategy !== strategy) return false
      if (cutoff && new Date(`${t.close_date}T12:00:00`).getTime() < cutoff) return false
      if (needle) {
        const hay = `${t.strategy} ${t.underlying} ${t.outcome} ${t.close_date}`.toLowerCase()
        if (!hay.includes(needle)) return false
      }
      return true
    })
  }, [trades, strategy, range, q])

  return (
    <div className="min-h-screen bg-forge-bg">
      <LiveSidebar membership={null} bots={allowedBots} paperBots={paperBots} />
      <div className="lg:pl-60">
        <div className="mx-auto max-w-[1200px] px-4 py-5">
          {/* breadcrumb */}
          <div className="flex items-center gap-2 text-sm">
            <Link href="/live" className="font-semibold text-amber-500 hover:text-amber-400">Live</Link>
            <span className="text-gray-600">›</span>
            <span className="text-gray-400">Trade History</span>
          </div>

          <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold text-white">Trade History</h1>
                <span className="rounded-md border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-400">All Trades</span>
              </div>
              <p className="mt-1 text-sm text-gray-400">Review recent and historical trades across your strategies.</p>
            </div>
            {/* controls */}
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search trades…"
                className="w-44 rounded-lg border border-forge-border bg-forge-card px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:border-amber-500/50 focus:outline-none"
              />
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
                className="rounded-lg border border-forge-border bg-forge-card px-3 py-2 text-sm text-gray-200 focus:border-amber-500/50 focus:outline-none"
              >
                <option value="all">All Strategies</option>
                {strategies.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              <select
                value={range}
                onChange={(e) => setRange(e.target.value as typeof range)}
                className="rounded-lg border border-forge-border bg-forge-card px-3 py-2 text-sm text-gray-200 focus:border-amber-500/50 focus:outline-none"
              >
                {RANGES.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
              </select>
            </div>
          </div>

          {isEmpty ? (
            <div className="mt-5 rounded-xl border border-forge-border bg-forge-card/80 p-8 text-center">
              <h2 className="text-lg font-bold text-white">Sign in to see your trades</h2>
              <p className="mx-auto mt-2 max-w-md text-sm text-gray-400">Your trade history appears here once a strategy is connected to your membership.</p>
              <Link href="/login?next=/account/trades" className="mt-4 inline-block rounded-md bg-amber-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-amber-500">Sign in</Link>
            </div>
          ) : isErr ? (
            <div className="mt-5 rounded-xl border border-forge-border bg-forge-card/80 p-6 text-sm text-gray-400">Trade history is temporarily unavailable — try refreshing in a moment.</div>
          ) : !data ? (
            <div className="mt-5 h-64 animate-pulse rounded-xl border border-forge-border bg-forge-card/50" />
          ) : (
            <>
              <div className="mt-5 overflow-x-auto rounded-xl border border-forge-border bg-forge-card/80">
                <table className="w-full min-w-[820px] text-sm">
                  <thead>
                    <tr className="border-b border-forge-border text-left text-xs uppercase tracking-wider text-gray-500">
                      <th className="px-4 py-3 font-semibold">Date</th>
                      <th className="px-4 py-3 font-semibold">Strategy</th>
                      <th className="px-4 py-3 font-semibold">Underlying</th>
                      <th className="px-4 py-3 font-semibold">Opened</th>
                      <th className="px-4 py-3 font-semibold">Closed</th>
                      <th className="px-4 py-3 font-semibold">Contracts</th>
                      <th className="px-4 py-3 text-right font-semibold">Result</th>
                      <th className="px-4 py-3 text-right font-semibold">Outcome</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((t) => {
                      const pos = t.pnl >= 0
                      return (
                        <tr key={t.id} className="border-b border-forge-border/60 last:border-0 hover:bg-white/[0.02]">
                          <td className="whitespace-nowrap px-4 py-3 text-gray-300">{fmtDate(t.close_date)}</td>
                          <td className="whitespace-nowrap px-4 py-3">
                            <span className={`font-semibold ${STRATEGY_CLASS[t.strategy] ?? 'text-gray-200'}`}>{t.strategy}</span>
                            {t.paper && <span className="ml-1.5 rounded bg-gray-700 px-1 py-px text-[9px] font-bold uppercase tracking-wider text-gray-300">Paper</span>}
                          </td>
                          <td className="whitespace-nowrap px-4 py-3 text-gray-300">{t.underlying}</td>
                          <td className="whitespace-nowrap px-4 py-3 text-gray-400">{t.opened_ct ?? '—'}</td>
                          <td className="whitespace-nowrap px-4 py-3 text-gray-400">{t.closed_ct ?? '—'}</td>
                          <td className="whitespace-nowrap px-4 py-3 text-gray-300">{t.contracts}</td>
                          <td className={`whitespace-nowrap px-4 py-3 text-right font-mono font-semibold ${pos ? 'text-emerald-400' : 'text-red-400'}`}>
                            {signedFull(t.pnl)}
                            {t.pnl_pct != null && <span className="ml-1 text-xs opacity-80">({t.pnl_pct > 0 ? '+' : ''}{t.pnl_pct.toFixed(2)}%)</span>}
                          </td>
                          <td className={`whitespace-nowrap px-4 py-3 text-right font-medium ${OUTCOME_CLASS[t.outcome_kind]}`}>{t.outcome}</td>
                        </tr>
                      )
                    })}
                    {rows.length === 0 && (
                      <tr><td colSpan={8} className="px-4 py-10 text-center text-sm text-gray-500">No trades match these filters.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 flex items-center justify-center gap-1.5 text-xs text-gray-500">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-3.5 w-3.5"><rect x="3" y="11" width="18" height="10" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
                All trade data is encrypted and securely stored.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
