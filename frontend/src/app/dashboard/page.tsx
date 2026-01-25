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

export default function Dashboard() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-background-deep">
      <Navigation />

      <main className="pt-24 transition-all duration-300">
        <div className="max-w-[1800px] mx-auto px-4 sm:px-6 lg:px-8 py-6">

          {/* Daily Manna Widget - Faith meets Finance */}
          <div className="mb-4">
            <DailyMannaWidget />
          </div>

          {/* Header */}
          <div className="mb-4">
            <h1 className="text-2xl font-bold text-text-primary">Live Trading Dashboard</h1>
            <p className="text-text-secondary text-sm mt-1">Real-time portfolio & trading activity</p>
          </div>

          {/* Row 1: Market Conditions Banner - Key context at a glance */}
          <div className="mb-4">
            <MarketConditionsBanner />
          </div>

          {/* Row 2: Portfolio Summary + Bot Status */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-4">
            <div className="xl:col-span-1">
              <PortfolioSummaryCard />
            </div>
            <div className="xl:col-span-2">
              <BotStatusOverview />
            </div>
          </div>

          {/* Row 3: Bot Performance Comparison - Full width equity curve */}
          <div className="mb-4">
            <MultiBotEquityCurve days={30} height={350} showPercentage={true} />
          </div>

          {/* Row 4: All Open Positions - Full width table */}
          <div className="mb-4">
            <AllOpenPositionsTable />
          </div>

          {/* Row 5: Today's Activity + Oracle + Gamma */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
            <TodaysActivityFeed />
            <OracleRecommendationWidget />
            <GammaExpirationWidget />
          </div>

          {/* Row 6: AI/ML Systems - SAGE, QUANT, Math Optimizer, Sync Status */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
            <SAGEStatusWidget />
            <QuantStatusWidget />
            <MathOptimizerWidget />
            <SyncStatusWidget />
          </div>

          {/* Row 7: ARGUS Alerts & Scan Feed - Activity monitoring */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
            <ARGUSAlertsWidget />
            <DashboardScanFeed />
          </div>

          {/* Row 8: Intelligence Dashboard - Full width */}
          <div>
            <IntelligenceDashboard />
          </div>

        </div>
      </main>
    </div>
  )
}
