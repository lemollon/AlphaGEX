'use client'

import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import type { TrackRecord } from '@/lib/live/track-record'

/**
 * Hero "Performance Overview" — the approved mock's top-right card.
 *
 * ── WHAT THE MOCK DRAWS THAT THIS DOES NOT ───────────────────────────────────
 *
 * The mock fills this card with "+18.74% · 128 trades · 74% win rate" over a
 * hand-drawn rising line. Those are the original template's placeholder figures.
 * No IronForge account has ever produced them, and they have now been stripped
 * from this codebase three separate times. They are NOT reproduced here, and if
 * a future change puts them back it is publishing a fabricated performance claim
 * on the public homepage of a real-money trading product.
 *
 * The LAYOUT is the mock's: a title row, three stat tiles, an area chart with a
 * value axis and month ticks. Only the numbers come from somewhere real.
 *
 * ── THE ONE LABEL THAT DIFFERS, AND WHY ──────────────────────────────────────
 *
 * The mock's first tile says "Total Return" as a percentage. There is no honest
 * percentage available: a return needs a capital base, and the public
 * track-record payload carries realised P&L in dollars with no starting capital.
 * Dividing by a number this component invented would be exactly the bug the
 * paragraph above is about. The tile reads "Realised P&L" in dollars instead —
 * the same quantity, correctly named. The other two labels are the mock's.
 *
 * ── TWO RULES ────────────────────────────────────────────────────────────────
 *
 *  1. NOTHING IS INVENTED. Every figure traces to a closed trade. If the ledger
 *     cannot be read the card degrades to a quiet unavailable state — never to a
 *     plausible number, and never to a stale hardcoded one.
 *  2. THE BADGE IS EARNED, NOT ASSERTED. `loadBot` now scopes the query to
 *     sandbox rows only (it previously summed sandbox and production into one
 *     line beneath a hardcoded "Paper account" badge), so "Paper account" is
 *     true by construction. Do not widen that query without changing this badge.
 */

function money(v: number): string {
  const sign = v > 0 ? '+' : v < 0 ? '−' : ''
  return `${sign}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

function pct(v: number | null): string {
  return v == null ? '—' : `${v}%`
}

/** Month ticks under the chart, derived from the curve's own dates. */
function monthTicks(dates: string[]): string[] {
  if (dates.length < 2) return []
  const seen: string[] = []
  for (const d of dates) {
    // `t` is a CT calendar date, 'YYYY-MM-DD'. Parse the parts rather than
    // `new Date(d)`, which reads a bare ISO date as midnight UTC and renders
    // the previous month for anyone west of Greenwich on the 1st.
    const [y, m] = d.split('-')
    const label = new Date(Number(y), Number(m) - 1, 1)
      .toLocaleString('en-US', { month: 'short' })
      .toUpperCase()
    if (label !== seen[seen.length - 1]) seen.push(label)
  }
  return seen.slice(-5)
}

function Chart({ points }: { points: number[] }) {
  if (points.length < 2) return <div className="h-[150px]" />

  const min = Math.min(0, ...points)
  const max = Math.max(0, ...points)
  const span = max - min || 1
  const positive = points[points.length - 1] >= 0
  // The mock's rising line is green. Keep green for a gain, but never paint a
  // loss green — the colour is the first thing read and it must not lie.
  const stroke = positive ? '#22C55E' : '#EE5A24'

  const W = 300
  const H = 100
  const coords = points
    .map((p, i) => `${(i / (points.length - 1)) * W},${H - ((p - min) / span) * H}`)
    .join(' ')

  // Four gridlines, as in the mock.
  const grid = [0, 0.25, 0.5, 0.75].map((f) => H * f)

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-[150px] w-full"
      preserveAspectRatio="none"
      role="img"
      aria-label="Cumulative realised profit and loss across closed paper trades"
    >
      <defs>
        <linearGradient id="hero-perf-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.34" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {grid.map((y) => (
        <line key={y} x1="0" y1={y} x2={W} y2={y} stroke="#242424" strokeWidth="0.6" />
      ))}
      <polygon points={`0,${H} ${coords} ${W},${H}`} fill="url(#hero-perf-fill)" />
      <polyline points={coords} fill="none" stroke={stroke} strokeWidth="1.7" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

export default function PerformanceOverviewCard() {
  const { data, error } = useSWR<TrackRecord>('/api/public/track-record', fetcher, {
    refreshInterval: 300_000,
  })

  const bots = data?.bots ?? []
  // Headline whichever bot has the longer record, so the card is not empty just
  // because the alphabetically-first bot happens to have traded least.
  const lead = [...bots].sort((a, b) => b.allTime.trades - a.allTime.trades)[0] ?? null

  const shell = (children: React.ReactNode) => (
    <div className="rounded-2xl border border-[#2B2B2B] bg-[#141414]/80 p-5 shadow-[0_12px_32px_rgba(0,0,0,.28)]">
      {children}
    </div>
  )

  // Degrade quietly. An unavailable ledger must never become a plausible number.
  if (error || (data && (!lead || lead.allTime.trades === 0))) {
    return shell(
      <>
        <div className="text-[15px] text-gray-200">Performance Overview</div>
        <p className="mt-3 text-sm text-[#B8B8B8]">Performance data is temporarily unavailable.</p>
      </>,
    )
  }

  if (!lead) {
    return shell(
      <>
        <div className="text-[15px] text-gray-200">Performance Overview</div>
        <div className="mt-4 h-[236px] animate-pulse rounded-lg bg-[#0E0F0F]" />
      </>,
    )
  }

  const s = lead.allTime
  const tiles = [
    { label: 'Realised P&L', value: money(s.net_pnl), green: s.net_pnl > 0 },
    { label: 'Trades Executed', value: String(s.trades), green: false },
    { label: 'Win Rate', value: pct(s.win_rate), green: false },
  ]
  const ticks = monthTicks(s.curve.map((p) => p.t))

  return shell(
    <>
      <div className="flex items-center justify-between gap-2">
        <div className="text-[15px] text-gray-200">Performance Overview</div>
        <span className="rounded-full border border-sky-700/50 bg-sky-950/40 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-sky-400">
          Paper account
        </span>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2.5">
        {tiles.map(({ label, value, green }) => (
          <div key={label} className="rounded-lg border border-[#2B2B2B] bg-[#0E0F0F] px-3 py-2.5">
            <div className="text-[11px] leading-tight text-[#B8B8B8]">{label}</div>
            <div
              className={`mt-1 text-[19px] font-bold tabular-nums ${green ? 'text-[#22C55E]' : 'text-white'}`}
            >
              {value}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4">
        <Chart points={s.curve.map((p) => p.pnl)} />
        {ticks.length > 1 ? (
          <div className="mt-1.5 flex justify-between px-0.5 text-[10px] tracking-wide text-[#7C7772]">
            {ticks.map((m) => (
              <span key={m}>{m}</span>
            ))}
          </div>
        ) : null}
      </div>

      <p className="mt-3 border-t border-[#1E1E1E] pt-3 text-[11px] leading-relaxed text-[#B8B8B8]">
        {lead.name} &middot; cumulative realised profit and loss on closed trades
        {lead.first_trade ? ` since ${lead.first_trade}` : ''}. Simulated execution on live market
        data. Past performance does not indicate future results.
      </p>
    </>,
  )
}
