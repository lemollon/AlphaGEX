'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import type { TrackRecord, PublicBotRecord } from '@/lib/live/track-record'

/* ── helpers ─────────────────────────────────────────────────────────── */

function money(v: number | null | undefined, signed = true): string {
  if (v == null || Number.isNaN(v)) return '—'
  const sign = signed && v > 0 ? '+' : v < 0 ? '−' : ''
  return `${sign}$${Math.abs(v).toLocaleString('en-US', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })}`
}

function niceDate(d: string | null): string {
  if (!d) return '—'
  const [y, m, day] = d.split('-')
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${Number(day)} ${months[Number(m) - 1] ?? ''} ${y?.slice(2) ?? ''}`
}

/** Cumulative realised-P&L sparkline. Not an account balance — starts at zero. */
function Curve({ points, accent }: { points: Array<{ pnl: number }>; accent: string }) {
  if (points.length < 2) {
    return (
      <div className="flex h-14 items-center text-xs text-gray-600">
        Not enough closed trades to chart yet
      </div>
    )
  }
  const vals = points.map((p) => p.pnl)
  const min = Math.min(0, ...vals)
  const max = Math.max(0, ...vals)
  const span = max - min || 1
  const W = 240, H = 56
  const d = points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * W
      const y = H - ((p.pnl - min) / span) * H
      return `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  const zeroY = H - ((0 - min) / span) * H
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-14 w-full" preserveAspectRatio="none"
      role="img" aria-label="Cumulative realised profit and loss">
      <line x1="0" y1={zeroY} x2={W} y2={zeroY} stroke="currentColor"
        className="text-white/15" strokeWidth="1" strokeDasharray="3 3" />
      <path d={d} fill="none" stroke={accent} strokeWidth="2"
        strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

function ModeBadge({ paper }: { paper: boolean }) {
  return paper ? (
    <span className="rounded-full border border-sky-700/50 bg-sky-950/40 px-2 py-0.5
      text-[10px] font-bold uppercase tracking-wider text-sky-400">
      Paper account
    </span>
  ) : (
    <span className="rounded-full border border-amber-700/50 bg-amber-950/40 px-2 py-0.5
      text-[10px] font-bold uppercase tracking-wider text-amber-400">
      Live account
    </span>
  )
}

function Stat({ label, value, tone = 'default' }: {
  label: string; value: string; tone?: 'default' | 'good' | 'bad'
}) {
  const tint = tone === 'good' ? 'text-emerald-400'
    : tone === 'bad' ? 'text-red-400' : 'text-gray-200'
  return (
    <div className="flex items-baseline justify-between border-b border-white/5 py-1.5 last:border-0">
      <span className="text-xs text-gray-500">{label}</span>
      <span className={`font-mono text-sm tabular-nums ${tint}`}>{value}</span>
    </div>
  )
}

function BotCard({ b }: { b: PublicBotRecord }) {
  const accent = b.accent === 'flame' ? '#E8531F' : '#3B9EFF'
  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-forge-card p-5">
      <div className="mb-1 flex items-center justify-between gap-3">
        <h3 className="font-display text-lg text-white">{b.label}</h3>
        <ModeBadge paper={b.paper} />
      </div>
      <p className="mb-4 text-xs text-gray-500">{b.tagline}</p>

      <div className="mb-1 flex items-baseline gap-2">
        <span className={`font-mono text-2xl tabular-nums ${
          b.total_pnl > 0 ? 'text-emerald-400' : b.total_pnl < 0 ? 'text-red-400' : 'text-gray-300'
        }`}>
          {money(b.total_pnl)}
        </span>
        <span className="text-xs text-gray-500">
          realised{b.first_trade ? ` since ${niceDate(b.first_trade)}` : ''}
        </span>
      </div>

      <div className="mb-4" style={{ color: accent }}>
        <Curve points={b.curve} accent={accent} />
      </div>

      <Stat label="Win rate" value={b.win_rate == null ? '—' : `${b.win_rate}%`} />
      <Stat label="Trades closed" value={String(b.trades)} />
      <Stat label="Best day" value={money(b.best_day)}
        tone={b.best_day != null && b.best_day > 0 ? 'good' : 'default'} />
      <Stat label="Worst day" value={money(b.worst_day)}
        tone={b.worst_day != null && b.worst_day < 0 ? 'bad' : 'default'} />
      <Stat label="Max drawdown" value={money(b.max_drawdown)}
        tone={b.max_drawdown != null && b.max_drawdown < 0 ? 'bad' : 'default'} />

      <p className="mt-4 text-[11px] leading-relaxed text-gray-500">
        {b.paper
          ? 'Simulated execution on live market data. No money at risk.'
          : 'Real money, traded in our own brokerage account.'}
      </p>
    </div>
  )
}

/* ── page ────────────────────────────────────────────────────────────── */

export default function TrackRecordClient() {
  const { data, error, isLoading } = useSWR<TrackRecord>(
    '/api/public/track-record', fetcher, { refreshInterval: 300_000 },
  )

  const bots = data?.bots ?? []
  const trades = data?.trades ?? []
  const anyLive = bots.some((b) => !b.paper)
  const anyPaper = bots.some((b) => b.paper)

  return (
    <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-10 sm:py-14">
      <div className="mx-auto max-w-5xl">

        <header className="mb-8">
          <p className="text-xs font-semibold uppercase tracking-[0.25em] text-amber-500">
            Track record
          </p>
          <h1 className="mt-2 font-display text-3xl text-white sm:text-4xl">
            Every trade these bots have closed.
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-gray-400">
            Each strategy below runs on live market data. The figures are realised
            profit and loss on closed trades — not projections, not a backtest.
            Each card states whether it traded real money or a simulated account.
          </p>
        </header>

        {isLoading && (
          <div className="rounded-2xl border border-white/10 bg-forge-card p-8 text-sm text-gray-500">
            Loading the record…
          </div>
        )}

        {error && (
          <div className="rounded-2xl border border-red-900/50 bg-red-950/20 p-6 text-sm text-red-300">
            We couldn&apos;t load the track record just now. Please try again shortly.
          </div>
        )}

        {!isLoading && !error && (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              {bots.map((b) => <BotCard key={b.bot} b={b} />)}
            </div>

            {(anyLive && anyPaper) && (
              <p className="mt-4 rounded-xl border border-amber-900/40 bg-amber-950/15 p-3
                text-[11px] leading-relaxed text-amber-200/80">
                These strategies are not on equal footing: one traded real money and one
                traded a simulated account. Compare them with that in mind — a simulated
                record has no slippage risk and no funding constraint.
              </p>
            )}

            <section className="mt-10">
              <div className="mb-3 flex items-baseline justify-between">
                <h2 className="font-display text-lg text-white">Closed trades</h2>
                <span className="text-xs text-gray-500">most recent {trades.length}</span>
              </div>
              <div className="overflow-x-auto rounded-2xl border border-white/10 bg-forge-card">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-[10px] uppercase tracking-wider text-gray-500">
                      <th className="px-4 py-2.5 font-semibold">Date</th>
                      <th className="px-4 py-2.5 font-semibold">Strategy</th>
                      <th className="px-4 py-2.5 font-semibold">Structure</th>
                      <th className="px-4 py-2.5 text-right font-semibold">Credit</th>
                      <th className="px-4 py-2.5 font-semibold">Closed</th>
                      <th className="px-4 py-2.5 text-right font-semibold">Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.length === 0 && (
                      <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                        No closed trades yet.
                      </td></tr>
                    )}
                    {trades.map((t, i) => (
                      <tr key={`${t.bot}-${t.date}-${i}`} className="border-b border-white/5 last:border-0">
                        <td className="whitespace-nowrap px-4 py-2 text-gray-400">{niceDate(t.date)}</td>
                        <td className="whitespace-nowrap px-4 py-2">
                          <span className="text-gray-200">{t.label}</span>
                          {t.paper && <span className="ml-1.5 text-[10px] text-sky-500">paper</span>}
                        </td>
                        <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-gray-400">
                          {t.structure ?? '—'}
                        </td>
                        <td className="whitespace-nowrap px-4 py-2 text-right font-mono tabular-nums text-gray-400">
                          {t.credit == null ? '—' : `$${t.credit.toFixed(2)}`}
                        </td>
                        <td className="whitespace-nowrap px-4 py-2 text-xs text-gray-500">
                          {t.outcome ?? '—'}
                        </td>
                        <td className={`whitespace-nowrap px-4 py-2 text-right font-mono tabular-nums ${
                          t.pnl > 0 ? 'text-emerald-400' : t.pnl < 0 ? 'text-red-400' : 'text-gray-400'
                        }`}>
                          {money(t.pnl)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="mt-10 rounded-2xl border border-amber-600/40
              bg-gradient-to-r from-amber-950/25 via-forge-card/70 to-amber-950/15 p-6 text-center">
              <h2 className="font-display text-xl text-white">
                Run one of these on your own brokerage.
              </h2>
              <p className="mx-auto mt-2 max-w-xl text-sm text-gray-400">
                You connect your account, the bot places the trades, and you can pause it
                at any time.
              </p>
              <div className="mt-5 flex flex-wrap justify-center gap-3">
                <Link href="/signup"
                  className="rounded-md bg-amber-600 px-6 py-3 text-sm font-bold text-white
                    transition hover:bg-amber-500">
                  Create your account
                </Link>
                <Link href="/pricing"
                  className="rounded-md border border-amber-600/60 px-6 py-3 text-sm
                    font-semibold text-amber-500 transition hover:bg-amber-600/10">
                  See pricing
                </Link>
              </div>
            </section>

            <p className="mt-8 text-[11px] leading-relaxed text-gray-600">
              Past performance is not indicative of future results. Options trading
              involves risk, including the possible loss of principal. Figures are
              realised profit and loss on closed positions and exclude commissions
              unless otherwise stated. Nothing here is investment advice.
              {data?.generated_at && (
                <> Updated {new Date(data.generated_at).toLocaleString('en-US', {
                  dateStyle: 'medium', timeStyle: 'short',
                })}.</>
              )}
            </p>
          </>
        )}
      </div>
    </div>
  )
}
