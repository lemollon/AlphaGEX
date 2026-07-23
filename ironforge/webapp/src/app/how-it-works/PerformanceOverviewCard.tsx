'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import type { TrackRecord } from '@/lib/live/track-record'

/**
 * Real performance summary for the How It Works hero.
 *
 * REPLACES a hardcoded card (+18.74% / 128 trades / 74% win rate over a
 * hand-drawn sparkline) that was labelled in-file as "placeholder marketing
 * figures". Those were the first numbers a prospect saw and none of them were
 * real. This reads the same closed-trade ledger the customer pages read.
 *
 * Client-side on purpose: the page is a static server component, so fetching
 * here keeps the marketing page off the database at build time and lets a slow
 * or failing query degrade to a quiet empty state instead of breaking the page.
 */

function pct(v: number | null): string {
  return v == null ? '—' : `${v}%`
}

function money(v: number): string {
  const sign = v > 0 ? '+' : v < 0 ? '−' : ''
  return `${sign}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

function Sparkline({ points, positive }: { points: number[]; positive: boolean }) {
  if (points.length < 2) return <div className="h-36 md:h-44" />
  const min = Math.min(0, ...points)
  const max = Math.max(0, ...points)
  const span = max - min || 1
  const stroke = positive ? '#56C62B' : '#E8531F'
  const coords = points
    .map((p, i) => `${(i / (points.length - 1)) * 280},${100 - ((p - min) / span) * 100}`)
    .join(' ')
  return (
    <svg viewBox="0 0 280 100" className="h-36 w-full md:h-44" preserveAspectRatio="none"
      role="img" aria-label="Cumulative realised profit and loss across closed trades">
      <defs>
        <linearGradient id="hiw-perf-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.32" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {[14, 39, 64, 89].map((y) => (
        <line key={y} x1="0" y1={y} x2="280" y2={y} stroke="#2B2B2B" strokeWidth="0.5" />
      ))}
      <polygon points={`0,100 ${coords} 280,100`} fill="url(#hiw-perf-fill)" />
      <polyline points={coords} fill="none" stroke={stroke} strokeWidth="1.8" />
    </svg>
  )
}

export default function PerformanceOverviewCard() {
  const { data, error } = useSWR<TrackRecord>('/api/public/track-record', fetcher, {
    refreshInterval: 300_000,
  })

  // Headline the live strategy when there is one; otherwise the first bot.
  const bots = data?.bots ?? []
  const leadBot = bots.find((b) => b.mode === 'live') ?? bots[0]
  // Flatten to the fields this card reads (lifetime figures for the hero).
  const lead = leadBot
    ? {
        name: leadBot.name,
        paper: leadBot.mode !== 'live',
        total_pnl: leadBot.allTime.net_pnl,
        trades: leadBot.allTime.trades,
        win_rate: leadBot.allTime.win_rate,
        curve: leadBot.allTime.curve,
        first_trade: leadBot.first_trade,
      }
    : null

  const shell = (children: React.ReactNode) => (
    <div className="rounded-2xl border border-[#2B2B2B] bg-[#141414]/80 p-5 shadow-[0_12px_32px_rgba(0,0,0,.28)]">
      {children}
    </div>
  )

  // Degrade quietly: an unavailable ledger must never show a fabricated number.
  if (error || (data && !lead)) {
    return shell(
      <>
        <div className="text-sm text-gray-200">Performance</div>
        <p className="mt-3 text-sm text-[#B8B8B8]">
          Our full trade-by-trade record is on the{' '}
          <Link href="/track-record" className="text-amber-500 hover:text-amber-400">
            track record page
          </Link>.
        </p>
      </>,
    )
  }

  if (!lead) {
    return shell(
      <>
        <div className="text-sm text-gray-200">Performance</div>
        <div className="mt-3 h-[188px] animate-pulse rounded-lg bg-[#0E0F0F]" />
      </>,
    )
  }

  const stats = [
    { label: 'Realised P&L', value: money(lead.total_pnl), green: lead.total_pnl > 0 },
    { label: 'Trades Closed', value: String(lead.trades), green: false },
    { label: 'Win Rate', value: pct(lead.win_rate), green: false },
  ]

  return shell(
    <>
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm text-gray-200">{lead.name} — performance</div>
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
          lead.paper
            ? 'border border-sky-700/50 bg-sky-950/40 text-sky-400'
            : 'border border-amber-700/50 bg-amber-950/40 text-amber-400'
        }`}>
          {lead.paper ? 'Paper account' : 'Live account'}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-3">
        {stats.map(({ label, value, green }) => (
          <div key={label} className="rounded-lg border border-[#2B2B2B] bg-[#0E0F0F] px-3 py-2.5">
            <div className="text-[11px] text-[#B8B8B8]">{label}</div>
            <div className={`mt-1 text-lg font-bold tabular-nums ${green ? 'text-[#56C62B]' : 'text-white'}`}>
              {value}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4">
        <Sparkline points={lead.curve.map((p) => p.pnl)} positive={lead.total_pnl >= 0} />
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-[#B8B8B8]">
        Cumulative realised profit and loss on closed trades
        {lead.first_trade ? ` since ${lead.first_trade}` : ''}.{' '}
        {lead.paper
          ? 'Simulated execution on live market data.'
          : 'Real money, our own brokerage account.'}{' '}
        <Link href="/track-record" className="text-amber-500 hover:text-amber-400">
          See every trade
        </Link>
        . Past performance does not indicate future results.
      </p>
    </>,
  )
}
