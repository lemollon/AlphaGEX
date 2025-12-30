'use client'

import Navigation from '@/components/Navigation'
import IntelligenceDashboard from '@/components/IntelligenceDashboard'
import GammaExpirationWidget from '@/components/GammaExpirationWidget'
import DailyMannaWidget from '@/components/DailyMannaWidget'
import BotStatusOverview from '@/components/BotStatusOverview'
import OracleRecommendationWidget from '@/components/OracleRecommendationWidget'
import ARGUSAlertsWidget from '@/components/ARGUSAlertsWidget'
import DashboardScanFeed from '@/components/DashboardScanFeed'

export default function Dashboard() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-background-deep">
      <Navigation />

      <main className="pt-24 transition-all duration-300">
        <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-8">

          {/* Daily Manna Widget - Faith meets Finance */}
          <div className="mb-6">
            <DailyMannaWidget />
          </div>

          {/* Header */}
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-text-primary">AlphaGEX Dashboard</h1>
            <p className="text-text-secondary text-sm mt-1">Real-time GEX intelligence & trading signals</p>
          </div>

          {/* Top Row - Bot Status & Oracle Recommendation */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
            <BotStatusOverview />
            <OracleRecommendationWidget />
          </div>

          {/* Main Content - Three Column Layout */}
          <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">

            {/* Left Column - Intelligence Feed (5/12 width on xl) */}
            <div className="xl:col-span-5">
              <IntelligenceDashboard />
            </div>

            {/* Middle Column - Gamma Expiration Widget (4/12 width on xl) */}
            <div className="xl:col-span-4 xl:sticky xl:top-20 xl:self-start">
              <GammaExpirationWidget />
            </div>

            {/* Right Column - ARGUS Alerts & Scan Activity (3/12 width on xl) */}
            <div className="xl:col-span-3 space-y-4 xl:sticky xl:top-20 xl:self-start">
              <ARGUSAlertsWidget />
              <DashboardScanFeed />
            </div>

          </div>

        </div>
      </main>
    </div>
  )
}
