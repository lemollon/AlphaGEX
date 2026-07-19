'use client'

import useSWR, { mutate } from 'swr'
import { useEffect, useState } from 'react'
import { fetcher } from '@/lib/fetcher'
import type { LiveSummary, LiveTrade } from '@/lib/live/types'
import { LIVE_BOTS, type LiveBot } from '@/lib/live/bots'
import LiveSidebar from './components/LiveSidebar'
import LiveHeader from './components/LiveHeader'
import SparkHeroCard from './components/SparkHeroCard'
import LiveTradeCard from './components/LiveTradeCard'
import NowTimelineCard from './components/NowTimelineCard'
import MarketConditionsCard from './components/MarketConditionsCard'
import TodayPerformanceChart from './components/TodayPerformanceChart'
import PauseTradingPanel from './components/PauseTradingPanel'

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
            <div className="mt-4 rounded-xl border border-forge-border bg-forge-card/80 p-8 text-center">
              <h2 className="text-lg font-bold text-white">No trading account connected yet</h2>
              <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-gray-400">
                Your live dashboard activates once a trading account is connected to your membership.
                Brokerage connection is coming soon — we&apos;ll email you the moment it&apos;s ready.
              </p>
              <a href="/community" className="mt-5 inline-block rounded-md bg-amber-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-amber-500">
                Visit the Forge Community
              </a>
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
                <SparkHeroCard state={summary?.state ?? null} market={summary?.market ?? null} />
              </div>
              <div className="order-2 grid gap-4 lg:grid-cols-[11fr_9fr]">
                <LiveTradeCard trade={trade ?? null} error={Boolean(tradeError)} state={summary?.state ?? null} />
                <NowTimelineCard state={summary?.state ?? null} openedAt={trade?.opened_at ?? null} />
              </div>
              {/* Mobile stacks Today Performance before Market Conditions; desktop reads Conditions first. */}
              <div className="order-4 lg:order-3">
                <MarketConditionsCard market={summary?.market ?? null} />
              </div>
              <div className="order-3 lg:order-4">
                <TodayPerformanceChart account={summary?.account ?? null} intraday={summary?.intraday ?? null} marketOpen={summary?.market.open ?? false} />
              </div>
              <div className="order-5">
                <PauseTradingPanel
                  state={summary?.state ?? null}
                  pending={pausePending}
                  onToggle={handlePauseToggle}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
