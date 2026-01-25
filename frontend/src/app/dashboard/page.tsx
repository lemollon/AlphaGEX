'use client'

import Navigation from '@/components/Navigation'
import IntelligenceDashboard from '@/components/IntelligenceDashboard'
import GammaExpirationWidget from '@/components/GammaExpirationWidget'
import DailyMannaWidget from '@/components/DailyMannaWidget'
import BotStatusOverview from '@/components/BotStatusOverview'
import OracleRecommendationWidget from '@/components/OracleRecommendationWidget'
import ARGUSAlertsWidget from '@/components/ARGUSAlertsWidget'
import DashboardScanFeed from '@/components/DashboardScanFeed'
import SAGEStatusWidget from '@/components/SAGEStatusWidget'
import QuantStatusWidget from '@/components/QuantStatusWidget'
import MathOptimizerWidget from '@/components/MathOptimizerWidget'
import SyncStatusWidget from '@/components/SyncStatusWidget'
import MultiBotEquityCurve from '@/components/charts/MultiBotEquityCurve'
import PortfolioSummaryCard from '@/components/dashboard/PortfolioSummaryCard'
import AllOpenPositionsTable from '@/components/dashboard/AllOpenPositionsTable'
import MarketConditionsBanner from '@/components/dashboard/MarketConditionsBanner'
import TodaysActivityFeed from '@/components/dashboard/TodaysActivityFeed'
import AllBotReportsSummary from '@/components/dashboard/AllBotReportsSummary'

export default function Dashboard() {
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

          {/* Row 4: Open Positions + Trading Reports (Bot data together) */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-4">
            <AllOpenPositionsTable />
            <AllBotReportsSummary />
          </div>

          {/* Row 5: Gamma + Oracle (Market intelligence together) */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-4">
            <GammaExpirationWidget />
            <OracleRecommendationWidget />
          </div>

          {/* Row 6: Activity + ARGUS + Scan Feed (Monitoring together) */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
            <TodaysActivityFeed />
            <ARGUSAlertsWidget />
            <DashboardScanFeed />
          </div>

          {/* Row 7: AI/ML Systems */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <SAGEStatusWidget />
            <QuantStatusWidget />
            <MathOptimizerWidget />
            <SyncStatusWidget />
          </div>

          {/* Row 8: Intelligence Dashboard */}
          <div>
            <IntelligenceDashboard />
          </div>

        </div>
      </main>
    </div>
  )
}
