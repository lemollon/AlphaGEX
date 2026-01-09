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
            <h1 className="text-2xl font-bold text-text-primary">AlphaGEX Dashboard</h1>
            <p className="text-text-secondary text-sm mt-1">Real-time GEX intelligence & trading signals</p>
          </div>

          {/* Row 1: Bot Status - Full width with all 5 bots */}
          <div className="mb-4">
            <BotStatusOverview />
          </div>

          {/* Row 2: Oracle & Gamma Expiration */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
            <OracleRecommendationWidget />
            <GammaExpirationWidget />
          </div>

          {/* Row 3: AI/ML Systems - SAGE, QUANT, Math Optimizer */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
            <SAGEStatusWidget />
            <QuantStatusWidget />
            <MathOptimizerWidget />
          </div>

          {/* Row 4: ARGUS Alerts & Scan Feed - Activity monitoring */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
            <ARGUSAlertsWidget />
            <DashboardScanFeed />
          </div>

          {/* Row 5: Intelligence Dashboard - Full width */}
          <div>
            <IntelligenceDashboard />
          </div>

        </div>
      </main>
    </div>
  )
}
