'use client'

import Navigation from '@/components/Navigation'
import DailyMannaWidget from '@/components/DailyMannaWidget'
import BotStatusOverview from '@/components/BotStatusOverview'
import MultiBotEquityCurve from '@/components/charts/MultiBotEquityCurve'
import PortfolioSummaryCard from '@/components/dashboard/PortfolioSummaryCard'
import AllOpenPositionsTable from '@/components/dashboard/AllOpenPositionsTable'
import MarketConditionsBanner from '@/components/dashboard/MarketConditionsBanner'
import AllBotReportsSummary from '@/components/dashboard/AllBotReportsSummary'
import SAGEStatusWidget from '@/components/SAGEStatusWidget'
import QuantStatusWidget from '@/components/QuantStatusWidget'
import MathOptimizerWidget from '@/components/MathOptimizerWidget'
import SyncStatusWidget from '@/components/SyncStatusWidget'

export default function LiveTradingDashboard() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-background-deep">
      <Navigation />

      <main className="pt-24 transition-all duration-300">
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

          {/* Row 3: Bot Performance Comparison - Full width equity curve */}
          <div className="mb-4">
            <MultiBotEquityCurve days={30} height={350} showPercentage={true} />
          </div>

          {/* Row 4: Open Positions + Trading Reports */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-4">
            <AllOpenPositionsTable />
            <AllBotReportsSummary />
          </div>

          {/* Row 5: AI/ML Systems that advise the bots */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <SAGEStatusWidget />
            <QuantStatusWidget />
            <MathOptimizerWidget />
            <SyncStatusWidget />
          </div>

        </div>
      </main>
    </div>
  )
}
