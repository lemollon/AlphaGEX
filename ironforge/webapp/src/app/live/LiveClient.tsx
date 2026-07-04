'use client'

import useSWR, { mutate } from 'swr'
import { useState } from 'react'
import { fetcher } from '@/lib/fetcher'
import type { LiveSummary, LiveTrade } from '@/lib/live/types'
import LiveSidebar from './components/LiveSidebar'
import LiveHeader from './components/LiveHeader'
import SparkHeroCard from './components/SparkHeroCard'
import LiveTradeCard from './components/LiveTradeCard'
import NowTimelineCard from './components/NowTimelineCard'
import MarketConditionsCard from './components/MarketConditionsCard'
import TodayPerformanceChart from './components/TodayPerformanceChart'
import PauseTradingPanel from './components/PauseTradingPanel'

export default function LiveClient() {
  const { data: summary, error: summaryError } = useSWR<LiveSummary>(
    '/api/live/summary', fetcher, { refreshInterval: 60_000 },
  )
  const { data: trade, error: tradeError } = useSWR<LiveTrade>(
    '/api/live/trade', fetcher, { refreshInterval: 30_000 },
  )
  const [pausePending, setPausePending] = useState(false)

  async function handlePauseToggle(nextPaused: boolean, password: string) {
    setPausePending(true)
    try {
      const res = await fetch('/api/spark/production-pause', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          paused: nextPaused,
          reason: nextPaused ? 'customer_pause' : 'customer_resume',
          by: 'live_page',
          password,
        }),
      })
      if (res.status === 403) throw new Error('password_required')
      if (!res.ok) throw new Error(`${res.status}`)
      await Promise.all([mutate('/api/live/summary'), mutate('/api/live/trade')])
    } finally {
      setPausePending(false)
    }
  }

  return (
    <div className="min-h-screen bg-forge-bg">
      <LiveSidebar membership={summary?.membership ?? null} />
      <div className="lg:pl-60">
        <div className="mx-auto max-w-[1200px] px-4 py-5">
          <LiveHeader />
          {summaryError && !summary ? (
            <div className="mt-4 rounded-xl border border-forge-border bg-forge-card/80 p-6 text-sm text-gray-400">
              Live data is temporarily unavailable. We&apos;re on it — try refreshing in a moment.
            </div>
          ) : (
            <div className="mt-4 flex flex-col gap-4">
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
