'use client'

import { useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import type { TrackRecord, SalesBot, Stats, PublicTrade } from '@/lib/live/track-record'

/* ── format ──────────────────────────────────────────────────────────── */

function money(v: number | null | undefined, signed = true): string {
  if (v == null || Number.isNaN(v)) return '—'
  const sign = signed && v > 0 ? '+' : v < 0 ? '−' : ''
  return `${sign}$${Math.abs(v).toLocaleString('en-US', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })}`
}
function money0(v: number | null | undefined, signed = true): string {
  if (v == null || Number.isNaN(v)) return '—'
  const sign = signed && v > 0 ? '+' : v < 0 ? '−' : ''
  return `${sign}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}
function niceDate(d: string | null): string {
  if (!d) return '—'
  const [y, m, day] = d.split('-')
  const M = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${Number(day)} ${M[Number(m) - 1] ?? ''} ${y?.slice(2) ?? ''}`
}

const ACCENT = {
  spark: { hex: '#3B9EFF', glow: 'rgba(59,158,255,0.55)', ring: 'border-sky-500/40' },
  flame: { hex: '#E8531F', glow: 'rgba(232,83,31,0.55)', ring: 'border-amber-500/40' },
} as const

/* ── curve ───────────────────────────────────────────────────────────── */

function Curve({ points, hex }: { points: Array<{ pnl: number }>; hex: string }) {
  if (points.length < 2) {
    return (
      <div className="flex h-24 items-center justify-center text-xs text-gray-600">
        Not enough closed trades in this window yet
      </div>
    )
  }
  const vals = points.map((p) => p.pnl)
  const min = Math.min(0, ...vals)
  const max = Math.max(0, ...vals)
  const span = max - min || 1
  const W = 320, H = 96
  const xy = points.map((p, i) => {
    const x = (i / (points.length - 1)) * W
    const y = H - ((p.pnl - min) / span) * H
    return [x, y] as const
  })
  const line = xy.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const area = `${line} L${W},${H} L0,${H} Z`
  const zeroY = H - ((0 - min) / span) * H
  const id = `g-${hex.slice(1)}`
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-24 w-full" preserveAspectRatio="none"
      role="img" aria-label="Cumulative realised profit and loss">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={hex} stopOpacity="0.28" />
          <stop offset="100%" stopColor={hex} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <line x1="0" y1={zeroY} x2={W} y2={zeroY} stroke="currentColor" className="text-white/15"
        strokeWidth="1" strokeDasharray="3 3" />
      <path d={area} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={hex} strokeWidth="2.25" strokeLinejoin="round"
        strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      <circle cx={xy[xy.length - 1][0]} cy={xy[xy.length - 1][1]} r="3.2" fill={hex} />
    </svg>
  )
}

/* ── strategy card ───────────────────────────────────────────────────── */

function Stat({ label, value, tone = 'default' }: {
  label: string; value: string; tone?: 'default' | 'good' | 'bad'
}) {
  const c = tone === 'good' ? 'text-emerald-400' : tone === 'bad' ? 'text-red-400' : 'text-gray-100'
  return (
    <div className="flex flex-col">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">{label}</span>
      <span className={`font-mono text-sm tabular-nums ${c}`}>{value}</span>
    </div>
  )
}

function StrategyCard({ b, win }: { b: SalesBot; win: 'd7' | 'd30' }) {
  const a = ACCENT[b.key]
  const s: Stats = b.windows[win]
  const lifeWin = b.allTime.win_rate
  return (
    <div className={`relative overflow-hidden rounded-2xl border ${a.ring} bg-forge-card`}>
      <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full opacity-40 blur-2xl"
        style={{ background: a.glow }} />

      {/* header */}
      <div className="flex items-center gap-3 border-b border-white/5 p-5">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={`/home/${b.key}-mascot-glow.png`} alt="" className="h-14 w-14 shrink-0"
          style={{ filter: `drop-shadow(0 0 12px ${a.glow})` }} />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-display text-2xl leading-none text-white">{b.name}</h3>
            <span className={`rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${
              b.mode === 'live'
                ? 'border-emerald-600/50 bg-emerald-950/40 text-emerald-400'
                : 'border-sky-700/50 bg-sky-950/40 text-sky-400'}`}>
              {b.mode === 'live' ? 'Live account' : 'Simulated'}
            </span>
          </div>
          <p className="mt-1 truncate text-xs text-gray-500">{b.tagline}</p>
        </div>
      </div>

      {/* win-rate hero */}
      <div className="flex items-end justify-between px-5 pt-5">
        <div>
          <div className="font-display text-5xl leading-none text-white">
            {s.win_rate == null ? '—' : `${s.win_rate}%`}
          </div>
          <div className="mt-1 text-[11px] font-semibold uppercase tracking-wider text-gray-500">
            trades closed green · {win === 'd7' ? 'last 7 days' : 'last 30 days'}
          </div>
        </div>
        <div className="text-right">
          <div className={`font-mono text-xl tabular-nums ${
            s.net_pnl > 0 ? 'text-emerald-400' : s.net_pnl < 0 ? 'text-red-400' : 'text-gray-300'}`}>
            {money0(s.net_pnl)}
          </div>
          <div className="text-[11px] text-gray-500">{s.trades} trades</div>
        </div>
      </div>

      {/* curve */}
      <div className="px-3 pt-3" style={{ color: a.hex }}>
        <Curve points={s.curve} hex={a.hex} />
      </div>

      {/* window stat row */}
      <div className="grid grid-cols-4 gap-2 px-5 pb-4 pt-1">
        <Stat label="Green days" value={`${s.green_days}/${s.total_days}`} />
        <Stat label="Best day" value={money0(s.best_day)} tone={s.best_day && s.best_day > 0 ? 'good' : 'default'} />
        <Stat label="Worst day" value={money0(s.worst_day)} tone={s.worst_day && s.worst_day < 0 ? 'bad' : 'default'} />
        <Stat label="Avg win/loss"
          value={s.avg_win != null || s.avg_loss != null ? `${money0(s.avg_win, false)} / ${money0(s.avg_loss, false)}` : '—'} />
      </div>

      {/* lifetime credibility strip */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-white/5 bg-black/20 px-5 py-3 text-xs">
        <span className="text-gray-500">Lifetime:</span>
        <span className="text-gray-200"><b className="text-white">{lifeWin == null ? '—' : `${lifeWin}%`}</b> win rate</span>
        <span className="text-gray-200"><b className="text-white">{b.allTime.trades}</b> trades</span>
        <span className="text-gray-200">profit factor <b className="text-white">{b.allTime.profit_factor ?? '—'}</b></span>
        {b.streak && (
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
            b.streak.endsWith('W') ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'}`}>
            {b.streak.endsWith('W') ? `${b.streak.slice(0, -1)} wins in a row` : `${b.streak.slice(0, -1)} losses`}
          </span>
        )}
      </div>
    </div>
  )
}

/* ── page ────────────────────────────────────────────────────────────── */

function WhyCol({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-forge-card/60 p-5">
      <h3 className="font-display text-lg text-amber-500">{title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-gray-400">{body}</p>
    </div>
  )
}

function Dot() {
  return <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-500" />
}

export default function TrackRecordClient() {
  const [win, setWin] = useState<'d7' | 'd30'>('d30')
  const { data, error, isLoading } = useSWR<TrackRecord>(
    '/api/public/track-record', fetcher, { refreshInterval: 300_000 },
  )
  const bots = data?.bots ?? []
  const trades: PublicTrade[] = data?.trades ?? []

  return (
    <div className="min-h-screen bg-forge-bg bg-ember-glow">
      <div className="mx-auto max-w-5xl px-4 py-12 sm:py-16">

        {/* HERO */}
        <header className="mx-auto max-w-3xl text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-amber-500">
            The real track record
          </p>
          <h1 className="mt-3 font-display text-4xl leading-[1.05] text-white sm:text-5xl">
            The setup was never your problem.
            <br /><span className="text-amber-500">Sticking to it was.</span>
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-[15px] leading-relaxed text-gray-400">
            You know the trade. You just don&apos;t always take it — or you take it, then bail the
            second it dips. IronForge doesn&apos;t blink. It runs the same disciplined rules every
            session and logs every result, win or loss. Here is that record, live.
          </p>
          <div className="mt-7 flex flex-wrap justify-center gap-3">
            <Link href="/signup" className="rounded-md bg-amber-600 px-7 py-3 text-sm font-bold text-white shadow-lg shadow-amber-900/30 transition hover:bg-amber-500">
              Put a bot to work
            </Link>
            <a href="#trades" className="rounded-md border border-white/15 px-7 py-3 text-sm font-semibold text-gray-200 transition hover:border-white/30">
              See every trade
            </a>
          </div>
        </header>

        {/* WINDOW TOGGLE */}
        <div className="mt-12 flex flex-wrap items-center justify-center gap-3">
          <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">Performance over the</span>
          <div className="inline-flex rounded-lg border border-white/10 bg-forge-card p-1">
            {([['d7', 'Last 7 days'], ['d30', 'Last 30 days']] as const).map(([k, label]) => (
              <button key={k} onClick={() => setWin(k)}
                className={`rounded-md px-4 py-1.5 text-sm font-semibold transition ${
                  win === k ? 'bg-amber-600 text-white' : 'text-gray-400 hover:text-white'}`}>
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* STRATEGY CARDS */}
        <div className="mt-6">
          {isLoading && (
            <div className="grid gap-5 sm:grid-cols-2">
              {[0, 1].map((i) => <div key={i} className="h-80 animate-pulse rounded-2xl border border-white/10 bg-forge-card/60" />)}
            </div>
          )}
          {error && (
            <div className="rounded-2xl border border-red-900/50 bg-red-950/20 p-6 text-center text-sm text-red-300">
              We couldn&apos;t load the record just now — please try again shortly.
            </div>
          )}
          {!isLoading && !error && (
            <div className="grid gap-5 sm:grid-cols-2">
              {bots.map((b) => <StrategyCard key={b.bot} b={b} win={win} />)}
            </div>
          )}
          <p className="mt-4 text-center text-xs text-gray-500">
            Win rate leads because it can&apos;t be inflated by position size — a win is a win.
            Net dollars and the curve are shown exactly as they happened, losing days included.
          </p>
        </div>

        {/* WHY AUTOMATION */}
        <section className="mt-16">
          <h2 className="text-center font-display text-2xl text-white">Why the bot beats you at your own strategy</h2>
          <p className="mx-auto mt-2 max-w-2xl text-center text-sm text-gray-400">
            It isn&apos;t smarter than you. It&apos;s just not scared, not bored, and not tired at 2:59 PM.
          </p>
          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            <WhyCol title="It never flinches"
              body="No revenge trades. No 'just one more.' No moving a stop because you have a feeling. The rules that produced the win rate above are the rules it runs — every time, without exception." />
            <WhyCol title="Your worst enemy sits out"
              body="Fear and greed close more accounts than bad setups do. The most expensive trade most people make is the good one they abandoned at the worst possible moment. The bot can't abandon it." />
            <WhyCol title="Nothing is hidden"
              body="Every trade it takes is logged and shown here — the losses too. You are not buying a screenshot. You are watching a system work in the open, in real time." />
          </div>
        </section>

        {/* TRADES */}
        <section id="trades" className="mt-16">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="font-display text-2xl text-white">Every trade. Win or lose.</h2>
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
                {trades.length === 0 && !isLoading && (
                  <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500">No closed trades yet.</td></tr>
                )}
                {trades.map((t, i) => (
                  <tr key={`${t.bot}-${t.date}-${i}`} className="border-b border-white/5 last:border-0">
                    <td className="whitespace-nowrap px-4 py-2 text-gray-400">{niceDate(t.date)}</td>
                    <td className="whitespace-nowrap px-4 py-2">
                      <span style={{ color: ACCENT[t.key].hex }} className="font-semibold">{t.name}</span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-gray-400">{t.structure ?? '—'}</td>
                    <td className="whitespace-nowrap px-4 py-2 text-right font-mono tabular-nums text-gray-400">
                      {t.credit == null ? '—' : `$${t.credit.toFixed(2)}`}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2 text-xs text-gray-500">{t.outcome ?? '—'}</td>
                    <td className={`whitespace-nowrap px-4 py-2 text-right font-mono tabular-nums ${
                      t.pnl > 0 ? 'text-emerald-400' : t.pnl < 0 ? 'text-red-400' : 'text-gray-400'}`}>
                      {money(t.pnl)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* FOUNDING / SCARCITY */}
        <section className="mt-16 overflow-hidden rounded-2xl border border-amber-600/40 bg-gradient-to-br from-amber-950/30 via-forge-card/70 to-amber-950/15 p-7 sm:p-9">
          <div className="flex flex-col items-start gap-6 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-amber-500">Founding members — first 100 only</p>
              <h2 className="mt-2 font-display text-2xl text-white sm:text-3xl">Lock $50/month. For life.</h2>
              <p className="mt-2 max-w-lg text-sm leading-relaxed text-gray-300">
                The first 100 accounts keep founding pricing for as long as they stay — even after
                the price rises for everyone else. Every month on the sidelines is a month of this
                track record you only watched.
              </p>
              <ul className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-xs text-gray-400">
                <li className="flex items-center gap-1.5"><Dot /> $50/mo locked while active</li>
                <li className="flex items-center gap-1.5"><Dot /> Cancel anytime — no lock-in</li>
                <li className="flex items-center gap-1.5"><Dot /> Priority on every new strategy</li>
              </ul>
            </div>
            <div className="shrink-0">
              <Link href="/signup?plan=founder" className="block rounded-md bg-amber-600 px-8 py-4 text-center text-base font-bold text-white shadow-lg shadow-amber-900/30 transition hover:bg-amber-500">
                Claim a founding seat
              </Link>
              <Link href="/pricing" className="mt-2 block text-center text-xs text-amber-500 hover:text-amber-400">
                See all plans →
              </Link>
            </div>
          </div>
        </section>

        {/* FINAL CTA */}
        <section className="mt-14 text-center">
          <h2 className="mx-auto max-w-2xl font-display text-3xl leading-tight text-white">
            Next month&apos;s track record is being written right now.
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-sm text-gray-400">
            The bot takes the trade at 9:41, the notification hits your phone, and you get back to
            your day. Or you keep watching from here. Your call.
          </p>
          <Link href="/signup" className="mt-6 inline-block rounded-md bg-amber-600 px-8 py-3.5 text-sm font-bold text-white shadow-lg shadow-amber-900/30 transition hover:bg-amber-500">
            Create your account
          </Link>
          <p className="mt-3 text-xs text-gray-500">No long-term commitment · Cancel anytime</p>
        </section>

        {/* DISCLOSURE */}
        <p className="mt-12 border-t border-white/5 pt-6 text-[11px] leading-relaxed text-gray-600">
          SPARK and FLAME figures are simulated results — the strategies run on live market data in
          paper accounts, so no real money is at risk. All figures are realised profit and
          loss on closed positions and exclude commissions unless stated. Options trading involves
          substantial risk, including the possible loss of principal, and is not suitable for every
          investor. Past performance is not indicative of future results. Nothing on this page is
          investment, tax, or legal advice.
          {data?.generated_at && (
            <> Updated {new Date(data.generated_at).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })}.</>
          )}
        </p>
      </div>
    </div>
  )
}
