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

// Section Header Component
function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="flex items-center gap-3 mb-3 mt-6 first:mt-0">
      <div className="h-px flex-1 bg-gradient-to-r from-gray-800 to-transparent" />
      <div className="text-center">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">{title}</h2>
        {subtitle && <p className="text-xs text-gray-600">{subtitle}</p>}
      </div>
      <div className="h-px flex-1 bg-gradient-to-l from-gray-800 to-transparent" />
    </div>
  )
}

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

          {/* ═══════════════════════════════════════════════════════════════════ */}
          {/* SECTION 1: MARKET CONDITIONS                                         */}
          {/* ═══════════════════════════════════════════════════════════════════ */}
          <div className="mb-4">
            <MarketConditionsBanner />
          </div>

          {/* ═══════════════════════════════════════════════════════════════════ */}
          {/* SECTION 2: PORTFOLIO & BOTS                                          */}
          {/* ═══════════════════════════════════════════════════════════════════ */}
          <SectionHeader title="Portfolio & Bots" />

          {/* Portfolio Summary + Bot Status */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-4">
            <div className="xl:col-span-1">
              <PortfolioSummaryCard />
            </div>
            <div className="xl:col-span-2">
              <BotStatusOverview />
            </div>
          </div>

          {/* Bot Performance Comparison - Full width equity curve */}
          <div className="mb-4">
            <MultiBotEquityCurve days={30} height={300} showPercentage={true} />
          </div>

          {/* Open Positions + Trading Reports - Side by side */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-4">
            <AllOpenPositionsTable />
            <AllBotReportsSummary />
          </div>

          {/* ═══════════════════════════════════════════════════════════════════ */}
          {/* SECTION 3: MARKET INTELLIGENCE                                       */}
          {/* ═══════════════════════════════════════════════════════════════════ */}
          <SectionHeader title="Market Intelligence" />

          {/* Oracle + Gamma - 2 column compact layout */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
            <OracleRecommendationWidget />
            <GammaExpirationWidget />
          </div>

          {/* ═══════════════════════════════════════════════════════════════════ */}
          {/* SECTION 4: ACTIVITY MONITORING                                       */}
          {/* ═══════════════════════════════════════════════════════════════════ */}
          <SectionHeader title="Activity Monitoring" />

          {/* Activity Feed + ARGUS Alerts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
            <TodaysActivityFeed />
            <ARGUSAlertsWidget />
          </div>

          {/* Scan Feed - Full width for detailed activity */}
          <div className="mb-4">
            <DashboardScanFeed />
          </div>

          {/* ═══════════════════════════════════════════════════════════════════ */}
          {/* SECTION 5: AI/ML SYSTEMS                                             */}
          {/* ═══════════════════════════════════════════════════════════════════ */}
          <SectionHeader title="AI/ML Systems" />

          {/* AI/ML Status Widgets */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
            <SAGEStatusWidget />
            <QuantStatusWidget />
            <MathOptimizerWidget />
            <SyncStatusWidget />
          </div>

          {/* Intelligence Dashboard - Full width */}
          <div>
            <IntelligenceDashboard />
          </div>

        </div>
      </main>
    </div>
  )
}
