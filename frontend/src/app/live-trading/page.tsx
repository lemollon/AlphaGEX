'use client'

import { SWRConfig } from 'swr'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import { useDashboardBatch } from '@/hooks/useDashboardBatch'
import DailyMannaWidget from '@/components/DailyMannaWidget'
import BotStatusOverview from '@/components/BotStatusOverview'
import MultiBotEquityCurve from '@/components/charts/MultiBotEquityCurve'
import PortfolioSummaryCard from '@/components/dashboard/PortfolioSummaryCard'
import AllOpenPositionsTable from '@/components/dashboard/AllOpenPositionsTable'
import MarketConditionsBanner from '@/components/dashboard/MarketConditionsBanner'
import AllBotReportsSummary from '@/components/dashboard/AllBotReportsSummary'
import WisdomStatusWidget from '@/components/WisdomStatusWidget'
import QuantStatusWidget from '@/components/QuantStatusWidget'
import MathOptimizerWidget from '@/components/MathOptimizerWidget'
import SyncStatusWidget from '@/components/SyncStatusWidget'

// ---------------------------------------------------------------------------
// BATCH LOADING  (replaces phased loading)
// ---------------------------------------------------------------------------
// Previously the page made ~55 individual API calls on mount, spread across
// 3 phases (0ms / 800ms / 1500ms) to avoid overwhelming Render's 15-conn
// DB pool. Each call was a separate HTTP round-trip.
//
// Now a SINGLE POST /api/v1/dashboard/batch call fetches ALL data at once.
// The backend runs all DB queries concurrently via asyncio.gather, returning
// everything in one response. The batch data is injected into SWR's cache
// via <SWRConfig fallback={...}> so every child useSWR hook sees pre-fetched
// data immediately — zero individual API calls on mount.
//
// Net effect: 55 HTTP requests → 1.   Render DB pool load → minimal.
// Individual hooks still poll via refreshInterval for subsequent updates.
// ---------------------------------------------------------------------------

// Full-page skeleton shown while batch loads
function DashboardSkeleton() {
  return (
    <div className="max-w-[1800px] mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-4">
      {/* Daily Manna placeholder */}
      <div className="card bg-gradient-to-r from-amber-500/10 to-orange-500/5 border-amber-500/30 animate-pulse h-16" />

      {/* Header */}
      <div>
        <div className="h-8 bg-gray-800 rounded w-64 mb-2" />
        <div className="h-4 bg-gray-800/50 rounded w-48" />
      </div>

      {/* Market Conditions Banner */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 h-20 animate-pulse" />

      {/* Portfolio + Bot Status */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-2 bg-[#0a0a0a] rounded-xl border border-gray-800 p-4 h-72 animate-pulse">
          <div className="h-5 bg-gray-800 rounded w-40 mb-4" />
          <div className="grid grid-cols-2 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-20 bg-gray-800/30 rounded-lg" />
            ))}
          </div>
        </div>
        <div className="lg:col-span-3 bg-[#0a0a0a] rounded-xl border border-gray-800 p-4 h-72 animate-pulse">
          <div className="h-5 bg-gray-800 rounded w-32 mb-4" />
          <div className="grid grid-cols-3 gap-3">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-24 bg-gray-800/30 rounded-lg" />
            ))}
          </div>
        </div>
      </div>

      {/* Equity Curve */}
      <div className="bg-[#0a0a0a] rounded-xl border border-gray-800 p-6 h-[350px] animate-pulse">
        <div className="h-4 bg-gray-800 rounded w-48 mb-4" />
        <div className="h-full bg-gray-800/30 rounded-lg" />
      </div>

      {/* Positions + Reports */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {[...Array(2)].map((_, i) => (
          <div key={i} className="bg-[#0a0a0a] rounded-xl border border-gray-800 p-6 h-64 animate-pulse">
            <div className="h-4 bg-gray-800 rounded w-40 mb-4" />
            <div className="space-y-3">
              {[...Array(4)].map((_, j) => <div key={j} className="h-8 bg-gray-800/30 rounded" />)}
            </div>
          </div>
        ))}
      </div>

      {/* ML Widgets */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="card bg-gradient-to-r from-gray-800/10 to-transparent border border-gray-800/30 animate-pulse">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gray-800/50 rounded-lg" />
              <div className="flex-1">
                <div className="h-4 w-32 bg-gray-800/50 rounded mb-2" />
                <div className="h-3 w-24 bg-gray-800/30 rounded" />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function LiveTradingDashboard() {
  const sidebarPadding = useSidebarPadding()
  const { fallback, isLoading, data: batchData } = useDashboardBatch()
  const hasBatchData = !!batchData && Object.keys(fallback).length > 0

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-background-deep">
      <Navigation />

      <main className={`pt-24 transition-all duration-300 ${sidebarPadding}`}>
        {isLoading ? (
          <DashboardSkeleton />
        ) : (
          // SWRConfig injects batch data into child hook caches.
          // revalidateIfStale:false prevents hooks from re-fetching data that
          // was just batch-loaded.  refreshInterval on each hook still works
          // for subsequent periodic updates.
          // If batch failed, fallback is empty and revalidateIfStale stays true
          // so child hooks fetch individually (graceful degradation).
          <SWRConfig value={{ fallback, ...(hasBatchData ? { revalidateIfStale: false } : {}) }}>
            <div className="max-w-[1800px] mx-auto px-4 sm:px-6 lg:px-8 py-6">

              {/* Daily Manna Widget */}
              <div className="mb-4">
                <DailyMannaWidget />
              </div>

              {/* Header */}
              <div className="mb-4">
                <h1 className="text-2xl font-bold text-text-primary">Live Trading Dashboard</h1>
                <p className="text-text-secondary text-sm mt-1">Real-time portfolio & trading activity</p>
              </div>

              {/* Row 1: Market Conditions Banner */}
              <div className="mb-4">
                <MarketConditionsBanner />
              </div>

              {/* Row 2: Portfolio Summary + Bot Status */}
              <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 mb-4">
                <div className="lg:col-span-2">
                  <PortfolioSummaryCard />
                </div>
                <div className="lg:col-span-3">
                  <BotStatusOverview />
                </div>
              </div>

              {/* Row 3: Bot Performance Comparison */}
              <div className="mb-4">
                <MultiBotEquityCurve days={30} height={350} showPercentage={true} />
              </div>

              {/* Row 4: Open Positions + Trading Reports */}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-4">
                <AllOpenPositionsTable />
                <AllBotReportsSummary />
              </div>

              {/* Row 5: AI/ML Systems */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <WisdomStatusWidget />
                <QuantStatusWidget />
                <MathOptimizerWidget />
                <SyncStatusWidget />
              </div>

            </div>
          </SWRConfig>
        )}
      </main>
    </div>
  )
}
