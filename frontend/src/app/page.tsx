'use client'

import Navigation from '@/components/Navigation'
import IntelligenceDashboard from '@/components/IntelligenceDashboard'
import GammaExpirationWidget from '@/components/GammaExpirationWidget'

export default function Dashboard() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-background-deep">
      <Navigation />

      <main className="pt-16 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

          {/* Header */}
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-text-primary">AlphaGEX Dashboard</h1>
            <p className="text-text-secondary text-sm mt-1">Real-time GEX intelligence & trading signals</p>
          </div>

          {/* Main Content - Two Column Layout */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">

            {/* Left Column - Intelligence Feed (2/3 width on xl) */}
            <div className="xl:col-span-2">
              <IntelligenceDashboard />
            </div>

            {/* Right Column - Gamma Expiration Widget (1/3 width on xl) */}
            <div className="xl:col-span-1">
              <GammaExpirationWidget />
            </div>

          </div>

        </div>
      </main>
    </div>
  )
}
