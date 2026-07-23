'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import type { LiveSummary } from '@/lib/live/types'
import type { HomeData } from '@/lib/live/home'
import CustomerShell from '@/components/customer/CustomerShell'
import EmptyState from './EmptyState'

/** Customer Home dashboard — hero status banner, wealth snapshot, membership,
 *  daily brief, recent trades, community entry (per the approved design). */

function fmtUsd(v: number | null | undefined, opts: { sign?: boolean } = {}): string {
  if (v == null) return '—'
  const sign = opts.sign && v > 0 ? '+' : v < 0 ? '-' : ''
  return `${sign}$${Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function CardLabel({ children }: { children: React.ReactNode }) {
  return <div className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">{children}</div>
}

function CheckIcon({ className = 'h-4 w-4 shrink-0 text-emerald-500' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><path d="m9 11 3 3L22 4" />
    </svg>
  )
}

function TileIcon({ d }: { d: string }) {
  return (
    <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-amber-500/30 bg-amber-500/5">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
        strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5 text-amber-500">
        <path d={d} />
      </svg>
    </div>
  )
}

function HeroBanner({ summary }: { summary: LiveSummary | undefined }) {
  const state = summary?.state
  const market = summary?.market
  const account = summary?.account
  const paused = state?.paused ?? false
  const statusWord = state ? (paused ? 'Paused' : 'Active') : '—'
  const dotClass = !state ? 'bg-gray-500' : paused ? 'bg-amber-500' : 'bg-emerald-500'
  const outlookGood = market?.condition === 'good'
  const outlookColor = !market ? 'text-gray-400' : outlookGood ? 'text-emerald-500' : market.condition === 'caution' ? 'text-amber-500' : 'text-red-500'

  return (
    <div className="relative overflow-hidden rounded-xl border border-forge-border bg-forge-card">
      <div className="pointer-events-none absolute inset-y-0 right-0 w-1/2 bg-ember-glow opacity-50" />
      <div className="relative grid gap-6 p-5 md:grid-cols-[1.5fr_1fr_1fr_1.3fr] md:divide-x md:divide-forge-border">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-amber-500">Spark Agent Status</div>
          <div className="mt-2 flex items-center gap-2.5">
            <span className={`h-2.5 w-2.5 rounded-full ${dotClass}`} />
            <span className="font-display text-3xl tracking-wide text-white">{statusWord}</span>
          </div>
          <div className="mt-2 text-sm font-semibold text-white">
            {state?.check_line ?? state?.headline ?? ''}
          </div>
          <div className="mt-0.5 text-xs leading-relaxed text-gray-400">
            IronForge is monitoring the market and executing your strategy.
          </div>
        </div>
        <div className="md:pl-6">
          <CardLabel>Account Value</CardLabel>
          <div className="mt-2 font-display text-3xl text-white">{fmtUsd(account?.value)}</div>
          <div className="mt-1 text-xs text-gray-500">All Accounts</div>
        </div>
        <div className="md:pl-6">
          <CardLabel>Today&apos;s P&amp;L</CardLabel>
          <div className={`mt-2 font-display text-3xl ${(account?.today_pnl ?? 0) < 0 ? 'text-red-500' : 'text-emerald-500'}`}>
            {fmtUsd(account?.today_pnl, { sign: true })}
          </div>
          <div className={`text-sm ${(account?.today_pnl ?? 0) < 0 ? 'text-red-500' : 'text-emerald-500'}`}>
            {account?.today_pnl_pct != null ? `(${account.today_pnl_pct >= 0 ? '+' : ''}${account.today_pnl_pct.toFixed(2)}%)` : ''}
          </div>
          <div className="mt-1 text-xs text-gray-500">Since market open</div>
        </div>
        <div className="md:pl-6">
          <CardLabel>Market Outlook</CardLabel>
          <div className="mt-2 flex items-center gap-2.5">
            <div className={`flex h-9 w-9 items-center justify-center rounded-full border ${outlookGood ? 'border-emerald-500/40 bg-emerald-500/10' : 'border-forge-border bg-forge-bg'}`}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                strokeLinecap="round" strokeLinejoin="round" className={`h-4 w-4 ${outlookColor}`}>
                <path d="m3 15 5-5 4 4 8-8" /><path d="M14 6h6v6" />
              </svg>
            </div>
            <span className={`font-display text-2xl ${outlookColor}`}>{market?.outlook ?? '—'}</span>
          </div>
          <div className="mt-1.5 text-xs text-gray-400">{market?.condition_line ?? ''}</div>
        </div>
      </div>
    </div>
  )
}

const WEALTH_ICONS = {
  wallet: 'M21 12V7H5a2 2 0 0 1 0-4h14v4M3 5v14a2 2 0 0 0 2 2h16v-5m-4-3a2 2 0 0 0 0 4h6v-4z',
  coins: 'M8 9a6 3 0 1 0 12 0A6 3 0 1 0 8 9m12 0v6c0 1.66-2.69 3-6 3s-6-1.34-6-3V9M4 5v.01M4 12v.01M4 19v.01',
  calendar: 'M8 2v4m8-4v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z',
  chart: 'm3 17 6-6 4 4 8-8m0 0h-5m5 0v5',
}

function WealthSnapshot({ summary, home }: { summary: LiveSummary | undefined; home: HomeData | undefined }) {
  const tiles = [
    { icon: WEALTH_ICONS.wallet, label: 'Portfolio Value', value: fmtUsd(summary?.account.value), sub: ' ', color: 'text-white' },
    { icon: WEALTH_ICONS.coins, label: 'Weekly Income', value: fmtUsd(home?.wealth.weekly_income), sub: 'This Week', color: 'text-white' },
    { icon: WEALTH_ICONS.calendar, label: 'Monthly Income', value: fmtUsd(home?.wealth.monthly_income), sub: 'This Month', color: 'text-white' },
    {
      icon: WEALTH_ICONS.chart,
      label: 'Lifetime Return',
      value: home?.wealth.lifetime_return_pct != null
        ? `${home.wealth.lifetime_return_pct >= 0 ? '+' : ''}${home.wealth.lifetime_return_pct.toFixed(2)}%`
        : '—',
      sub: 'All Time',
      color: (home?.wealth.lifetime_return_pct ?? 0) < 0 ? 'text-red-500' : 'text-emerald-500',
    },
  ]
  return (
    <div className="rounded-xl border border-forge-border bg-forge-card p-5">
      <div className="text-xs font-semibold uppercase tracking-wider text-white">Wealth Snapshot</div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {tiles.map((t) => (
          <div key={t.label} className="flex flex-col items-center rounded-lg border border-forge-border bg-forge-bg p-4 text-center">
            <TileIcon d={t.icon} />
            <div className="mt-3 text-xs text-gray-400">{t.label}</div>
            <div className={`mt-1 font-display text-xl ${t.color}`}>{t.value}</div>
            <div className="mt-1 text-xs text-gray-500">{t.sub}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function MembershipCard({ summary }: { summary: LiveSummary | undefined }) {
  const membership = summary?.membership
  const features = ['Spark Agent', 'Automated Execution', 'Risk Management', 'Community Access']
  return (
    <div className="rounded-xl border border-forge-border bg-forge-card p-5">
      <div className="text-xs font-semibold uppercase tracking-wider text-white">Your Membership</div>
      <div className="mt-4 flex items-center gap-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/forge-logo-mark.png" alt="" className="h-12 w-12 rounded-full ring-1 ring-amber-500/50" />
        <div>
          <div className="font-display text-lg text-amber-500">{membership?.plan ?? 'Forge Automate'}</div>
          <div className="mt-1 inline-block rounded-full border border-forge-border bg-forge-bg px-2.5 py-0.5 text-[11px] text-gray-200">
            {membership?.trial?.label ?? membership?.badge ?? 'Early Access'}
          </div>
        </div>
      </div>
      <div className="mt-4 space-y-2.5 border-t border-forge-border pt-4">
        {features.map((f) => (
          <div key={f} className="flex items-center gap-2.5">
            <CheckIcon />
            <span className="text-sm text-gray-200">{f}</span>
            <span className="ml-auto text-xs text-emerald-500">Active</span>
          </div>
        ))}
      </div>
      <Link href="/pricing"
        className="mt-4 block w-full rounded-lg border border-amber-500 px-4 py-2 text-center text-sm font-medium text-amber-500 transition-colors hover:bg-amber-500/10">
        Manage Membership
      </Link>
    </div>
  )
}

function DailyBrief({ summary, home }: { summary: LiveSummary | undefined; home: HomeData | undefined }) {
  const state = summary?.state
  const market = summary?.market
  const yesterday = home?.yesterday_trades
  const bullets = [
    state?.check_line ?? (state?.paused ? 'Trading is paused — resume anytime.' : 'Spark is monitoring the market.'),
    market?.condition_line ?? 'Checking market conditions…',
    yesterday != null
      ? `IronForge executed ${yesterday} trade${yesterday === 1 ? '' : 's'} yesterday.`
      : 'Loading trade activity…',
    market?.open
      ? 'The trading window is open now.'
      : `Next execution window: ${market?.next_open_label ?? 'next market open'}`,
  ]
  return (
    <div className="flex flex-col rounded-xl border border-forge-border bg-forge-card p-5">
      <div className="text-xs font-semibold uppercase tracking-wider text-white">Daily Brief</div>
      <div className="mt-4 flex-1 space-y-3">
        {bullets.map((b, i) => (
          <div key={i} className="flex items-start gap-2.5">
            <CheckIcon className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
            <span className="text-xs leading-relaxed text-gray-200">{b}</span>
          </div>
        ))}
      </div>
      <Link href="/live" className="mt-4 flex items-center justify-between border-t border-forge-border pt-3 text-sm font-medium text-amber-500 hover:text-amber-400">
        View Full Brief
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
          <path d="m9 18 6-6-6-6" />
        </svg>
      </Link>
    </div>
  )
}

function RecentTrades({ home, error }: { home: HomeData | undefined; error: boolean }) {
  const trades = home?.recent_trades ?? []
  return (
    <div className="flex flex-col rounded-xl border border-forge-border bg-forge-card p-5">
      <div className="flex items-center justify-between">
        <div className="text-xs font-semibold uppercase tracking-wider text-white">Recent Trades</div>
        <Link href="/account/trades" className="text-xs font-medium text-amber-500 hover:text-amber-400">View All</Link>
      </div>
      <div className="mt-3 flex-1 overflow-x-auto">
        {trades.length === 0 ? (
          <div className="py-6 text-xs text-gray-500">
            {error ? 'Trade history is temporarily unavailable.' : 'No completed trades yet — they’ll appear here.'}
          </div>
        ) : (
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="text-gray-500">
                <th className="pb-2 pr-3 font-normal">Time</th>
                <th className="pb-2 pr-3 font-normal">Strategy</th>
                <th className="pb-2 pr-3 font-normal">Contract</th>
                <th className="pb-2 pr-3 font-normal">Premium</th>
                <th className="pb-2 font-normal">Status</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t, i) => (
                <tr key={i} className="border-t border-forge-border/60">
                  <td className="py-2.5 pr-3 text-gray-300">
                    {t.closed_at
                      ? new Date(t.closed_at).toLocaleString('en-US', {
                          timeZone: 'America/New_York', month: 'short', day: 'numeric',
                          hour: 'numeric', minute: '2-digit',
                        })
                      : '—'}
                  </td>
                  <td className="py-2.5 pr-3 text-gray-300">{t.strategy}</td>
                  <td className="py-2.5 pr-3 text-gray-300">{t.contract}</td>
                  <td className="py-2.5 pr-3 text-white">{fmtUsd(t.premium)}</td>
                  <td className="py-2.5 text-emerald-500">{t.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className="mt-3 border-t border-forge-border pt-3 text-[11px] text-gray-500">
        All times ET. Updates every 60 seconds.
      </div>
    </div>
  )
}

function CommunityCard() {
  return (
    <div className="rounded-xl border border-forge-border bg-forge-card p-5">
      <div className="flex items-center gap-2">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/forge-mascot-sm.png" alt="" className="h-6 w-6 rounded-full" />
        <div className="text-xs font-semibold uppercase tracking-wider text-white">Forge Community</div>
      </div>
      <p className="mt-3 text-xs leading-relaxed text-gray-400">
        Join the conversation with other traders. Access trade ideas, market commentary,
        education, and member discussions.
      </p>
      <Link href="/community"
        className="mt-4 block w-full rounded-lg bg-amber-500 px-4 py-2 text-center text-sm font-semibold text-white transition-colors hover:bg-amber-400">
        Enter Community
      </Link>
    </div>
  )
}

export default function HomeClient() {
  const { data: summary } = useSWR<LiveSummary>('/api/live/summary', fetcher, { refreshInterval: 60_000 })
  const { data: home, error: homeError } = useSWR<HomeData>('/api/live/home', fetcher, { refreshInterval: 60_000 })

  return (
    <CustomerShell membership={summary?.membership ?? null} planVariant="trial">
      {summary?.empty ? (
        <EmptyState />
      ) : (
      <div className="flex flex-col gap-4">
        <HeroBanner summary={summary} />
        <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
          <div className="flex flex-col gap-4">
            <WealthSnapshot summary={summary} home={home} />
            <div className="grid gap-4 xl:grid-cols-[1fr_1.35fr]">
              <DailyBrief summary={summary} home={home} />
              <RecentTrades home={home} error={Boolean(homeError)} />
            </div>
          </div>
          <div className="flex flex-col gap-4">
            <MembershipCard summary={summary} />
            <CommunityCard />
          </div>
        </div>
      </div>
      )}
    </CustomerShell>
  )
}
