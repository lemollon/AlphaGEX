'use client'

import useSWR, { mutate } from 'swr'
import { useEffect, useState } from 'react'
import { fetcher } from '@/lib/fetcher'
import type { LiveSummary, LiveTrade } from '@/lib/live/types'
import { LIVE_BOTS, LIVE_BOT_LABEL, type LiveBot } from '@/lib/live/bots'
import { accentFor } from './components/accent'
import LiveSidebar from './components/LiveSidebar'
import LiveHeader from './components/LiveHeader'
import SparkHeroCard from './components/SparkHeroCard'
import LiveTradeCard from './components/LiveTradeCard'
import NowTimelineCard from './components/NowTimelineCard'
import MarketConditionsCard from './components/MarketConditionsCard'
import TodayPerformanceChart from './components/TodayPerformanceChart'
import PauseTradingPanel from './components/PauseTradingPanel'

/** Non-customer /live conversion CTAs — one per strategy, Spark then Flame.
 *  Both link into the existing signup flow with the bot preselected. */
const SIGNUP_CTAS = [
  {
    slug: 'spark',
    name: 'Spark',
    tagline: 'Next-day SPY spreads',
    pill: 'Live',
    mascot: '/home/spark-mascot-glow.png',
    cardClass: 'border-spark/40 bg-spark/5 hover:bg-spark/10',
    pillClass: 'bg-spark/20 text-spark',
    btnClass: 'bg-spark group-hover:brightness-110',
  },
  {
    slug: 'flame',
    name: 'Flame',
    tagline: 'Two-day SPY put credit spreads',
    pill: 'Paper',
    mascot: '/home/flame-mascot-glow.png',
    cardClass: 'border-flame/40 bg-flame/5 hover:bg-flame/10',
    pillClass: 'bg-flame/20 text-flame',
    btnClass: 'bg-flame group-hover:brightness-110',
  },
] as const

export default function LiveClient() {
  // Account-aware view: which live bot's account this page shows. The API
  // authorizes server-side; the header toggle only appears when the viewer
  // may see more than one account (operators; later, multi-account owners).
  const [account, setAccount] = useState<LiveBot>('spark')
  useEffect(() => {
    const a = new URLSearchParams(window.location.search).get('account')
    if (a && a !== 'spark' && (LIVE_BOTS as readonly string[]).includes(a)) {
      setAccount(a as LiveBot)
    }
  }, [])
  const switchAccount = (next: LiveBot) => {
    setAccount(next)
    const url = new URL(window.location.href)
    if (next === 'spark') url.searchParams.delete('account')
    else url.searchParams.set('account', next)
    window.history.replaceState(null, '', url.toString())
  }

  const summaryKey = `/api/live/summary?account=${account}`
  const tradeKey = `/api/live/trade?account=${account}`
  const { data: summary, error: summaryError } = useSWR<LiveSummary>(
    summaryKey, fetcher, { refreshInterval: 60_000 },
  )
  const { data: trade, error: tradeError } = useSWR<LiveTrade>(
    tradeKey, fetcher, { refreshInterval: 30_000 },
  )
  const [pausePending, setPausePending] = useState(false)
  // The whole surface takes the active bot's identity colour (Spark blue / Flame orange).
  const accent = accentFor(account)

  async function handlePauseToggle(nextPaused: boolean) {
    setPausePending(true)
    try {
      const res = await fetch(`/api/${account}/production-pause`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          paused: nextPaused,
          reason: nextPaused ? 'customer_pause' : 'customer_resume',
          by: 'live_page',
        }),
      })
      if (!res.ok) throw new Error(`${res.status}`)
      await Promise.all([mutate(summaryKey), mutate(tradeKey)])
    } finally {
      setPausePending(false)
    }
  }

  return (
    <div className="min-h-screen bg-forge-bg">
      <LiveSidebar
        membership={summary?.membership ?? null}
        bots={(summary?.viewer?.allowedBots ?? []) as LiveBot[]}
        activeBot={account}
        paperBots={summary?.viewer?.paperBots ?? []}
        onSwitch={switchAccount}
      />
      <div className="lg:pl-60">
        <div className="mx-auto max-w-[1200px] px-4 py-5">
          <LiveHeader viewer={summary?.viewer ?? null} onSwitch={switchAccount} />
          {summary?.empty ? (
            /* Non-customer (anonymous / no bot mapped) — this is a conversion
               surface, not a dashboard. Show a signup CTA for each strategy
               (Spark, then Flame). Live paper results live on /track-record.
               Customers with a mapped bot never reach this branch. */
            <div className="mt-4">
              <div className="text-center">
                <h2 className="font-display text-2xl tracking-wide text-white">Put a bot to work</h2>
                <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-gray-400">
                  Start a dedicated account for a strategy and it trades the same disciplined
                  rules every session. Watch the live paper track record on{' '}
                  <a href="/track-record" className="font-semibold text-amber-500 hover:text-amber-400">Track Record</a>.
                </p>
              </div>
              <div className="mx-auto mt-6 grid max-w-xl gap-4">
                {SIGNUP_CTAS.map((c) => (
                  <a
                    key={c.slug}
                    href={`/signup?bot=${c.slug}`}
                    className={`group flex items-center gap-4 rounded-xl border p-5 transition ${c.cardClass}`}
                  >
                    <img src={c.mascot} alt="" className="h-14 w-14 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-base font-bold text-white">{c.name}</span>
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${c.pillClass}`}>
                          {c.pill}
                        </span>
                      </div>
                      <p className="mt-0.5 text-sm text-gray-400">{c.tagline}</p>
                    </div>
                    <span className={`shrink-0 rounded-md px-4 py-2 text-sm font-semibold text-white transition ${c.btnClass}`}>
                      Sign up
                    </span>
                  </a>
                ))}
              </div>
            </div>
          ) : summaryError && !summary ? (
            <div className="mt-4 rounded-xl border border-forge-border bg-forge-card/80 p-6 text-sm text-gray-400">
              Live data is temporarily unavailable. We&apos;re on it — try refreshing in a moment.
            </div>
          ) : (
            <div className="mt-4 flex flex-col gap-4">
              {/* Paper-mode disclosure. Every number below this line (account
                  value, Today's Result, the chart) is simulated for a paper bot,
                  and the page's copy otherwise reads as real money — so this
                  banner is not optional dressing. */}
              {summary?.account.mode === 'paper' && summary.account.disclosure ? (
                <div className="order-0 flex items-start gap-2.5 rounded-xl border border-flame/30 bg-flame/10 px-4 py-3">
                  <span className="mt-px rounded bg-flame/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-flame">
                    Paper
                  </span>
                  <p className="text-sm leading-relaxed text-gray-300">
                    {summary.account.disclosure}
                  </p>
                </div>
              ) : null}
              <div className="order-1">
                <SparkHeroCard state={summary?.state ?? null} market={summary?.market ?? null} bot={account} />
              </div>
              <div className="order-2 grid gap-4 lg:grid-cols-[11fr_9fr]">
                <LiveTradeCard trade={trade ?? null} error={Boolean(tradeError)} state={summary?.state ?? null} accent={accent} />
                <NowTimelineCard state={summary?.state ?? null} openedAt={trade?.opened_at ?? null} accent={accent} />
              </div>
              {/* Mobile stacks Today Performance before Market Conditions; desktop reads Conditions first. */}
              <div className="order-4 lg:order-3">
                <MarketConditionsCard market={summary?.market ?? null} accent={accent} />
              </div>
              <div className="order-3 lg:order-4">
                <TodayPerformanceChart account={summary?.account ?? null} intraday={summary?.intraday ?? null} marketOpen={summary?.market.open ?? false} accent={accent} />
              </div>
              {/* Pause is a PRODUCTION control. /api/{bot}/production-pause answers
                  400 for any paper bot, so rendering this on Flame or Spark paper
                  gave the owner a button whose only outcome was a generic failure.
                  There is nothing to pause on a simulated account. */}
              {summary?.account.mode === 'paper' ? null : (
                <div className="order-5">
                  <PauseTradingPanel
                    state={summary?.state ?? null}
                    pending={pausePending}
                    onToggle={handlePauseToggle}
                    accent={accent}
                    botLabel={LIVE_BOT_LABEL[account]}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
