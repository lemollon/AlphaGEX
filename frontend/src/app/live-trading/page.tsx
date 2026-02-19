'use client'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
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
// PHASED LOADING
// ---------------------------------------------------------------------------
// The /live-trading page was firing 60 API calls simultaneously on mount,
// overwhelming Render's 15-connection DB pool and causing 1.5+ min load times.
//
// Phase 1 (immediate):   Navigation + MarketConditions + Portfolio + BotStatus
//                        → ~22 unique API calls (critical above-the-fold data)
// Phase 2 (after 800ms): MultiBotEquityCurve (16 equity curves) + Positions (5)
//                        + Reports (5) = 26 calls
// Phase 3 (after 1.5s):  ML/System widgets (7 calls)
//
// This spreads ~55 unique calls across 1.5 seconds instead of firing all at once,
// keeping concurrent requests within DB pool limits at any given moment.
// ---------------------------------------------------------------------------

export default function LiveTradingDashboard() {
  const sidebarPadding = useSidebarPadding()
  const [phase, setPhase] = useState(1)

  useEffect(() => {
    const t2 = setTimeout(() => setPhase(2), 800)
    const t3 = setTimeout(() => setPhase(3), 1500)
    return () => {
      clearTimeout(t2)
      clearTimeout(t3)
    }
  }, [])

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-background-deep">
      <Navigation />

      <main className={`pt-24 transition-all duration-300 ${sidebarPadding}`}>
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

          {/* PHASE 1: Above-the-fold — immediate */}

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

          {/* PHASE 2: Below-the-fold — after 800ms */}

          {/* Row 3: Bot Performance Comparison - Full width equity curve */}
          <div className="mb-4">
            {phase >= 2 ? (
              <MultiBotEquityCurve days={30} height={350} showPercentage={true} />
            ) : (
              <div className="bg-[#0a0a0a] rounded-xl border border-gray-800 p-6 h-[350px] animate-pulse">
                <div className="h-4 bg-gray-800 rounded w-48 mb-4" />
                <div className="h-full bg-gray-800/30 rounded-lg" />
              </div>
            )}
          </div>

          {/* Row 4: Open Positions + Trading Reports */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-4">
            {phase >= 2 ? (
              <>
                <AllOpenPositionsTable />
                <AllBotReportsSummary />
              </>
            ) : (
              <>
                <div className="bg-[#0a0a0a] rounded-xl border border-gray-800 p-6 h-64 animate-pulse">
                  <div className="h-4 bg-gray-800 rounded w-40 mb-4" />
                  <div className="space-y-3">
                    {[...Array(4)].map((_, i) => <div key={i} className="h-8 bg-gray-800/30 rounded" />)}
                  </div>
                </div>
                <div className="bg-[#0a0a0a] rounded-xl border border-gray-800 p-6 h-64 animate-pulse">
                  <div className="h-4 bg-gray-800 rounded w-40 mb-4" />
                  <div className="space-y-3">
                    {[...Array(4)].map((_, i) => <div key={i} className="h-8 bg-gray-800/30 rounded" />)}
                  </div>
                </div>
              </>
            )}
          </div>

          {/* PHASE 3: System widgets — after 1.5s */}

          {/* Row 5: AI/ML Systems that advise the bots */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {phase >= 3 ? (
              <>
                <WisdomStatusWidget />
                <QuantStatusWidget />
                <MathOptimizerWidget />
                <SyncStatusWidget />
              </>
            ) : (
              [...Array(4)].map((_, i) => (
                <div key={i} className="card bg-gradient-to-r from-gray-800/10 to-transparent border border-gray-800/30 animate-pulse">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-gray-800/50 rounded-lg" />
                    <div className="flex-1">
                      <div className="h-4 w-32 bg-gray-800/50 rounded mb-2" />
                      <div className="h-3 w-24 bg-gray-800/30 rounded" />
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

        </div>
      </main>
    </div>
  )
}
