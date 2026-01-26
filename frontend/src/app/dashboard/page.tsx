'use client'

import Navigation from '@/components/Navigation'
import IntelligenceDashboard from '@/components/IntelligenceDashboard'
import GammaExpirationWidget from '@/components/GammaExpirationWidget'
import DailyMannaWidget from '@/components/DailyMannaWidget'
import OracleRecommendationWidget from '@/components/OracleRecommendationWidget'
import ARGUSAlertsWidget from '@/components/ARGUSAlertsWidget'
import DashboardScanFeed from '@/components/DashboardScanFeed'
import SAGEStatusWidget from '@/components/SAGEStatusWidget'
import QuantStatusWidget from '@/components/QuantStatusWidget'
import MathOptimizerWidget from '@/components/MathOptimizerWidget'
import SyncStatusWidget from '@/components/SyncStatusWidget'
import TodaysActivityFeed from '@/components/dashboard/TodaysActivityFeed'

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
            <h1 className="text-2xl font-bold text-text-primary">Dashboard</h1>
            <p className="text-text-secondary text-sm mt-1">Market intelligence & system status</p>
          </div>

          {/* Row 1: Gamma + Oracle (Market intelligence) */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-4">
            <GammaExpirationWidget />
            <OracleRecommendationWidget />
          </div>

          {/* Row 2: Activity + ARGUS + Scan Feed (Monitoring) */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
            <TodaysActivityFeed />
            <ARGUSAlertsWidget />
            <DashboardScanFeed />
          </div>

          {/* Row 3: AI/ML Systems */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <SAGEStatusWidget />
            <QuantStatusWidget />
            <MathOptimizerWidget />
            <SyncStatusWidget />
          </div>

          {/* Row 4: Intelligence Dashboard */}
          <div>
            <IntelligenceDashboard />
          </div>

        </div>
      </main>
    </div>
  )
}
