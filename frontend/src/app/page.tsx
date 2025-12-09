'use client'

import Navigation from '@/components/Navigation'
import MarketCommentary from '@/components/MarketCommentary'
import DailyTradingPlan from '@/components/DailyTradingPlan'
import GammaExpirationWidget from '@/components/GammaExpirationWidget'

export default function Dashboard() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-background-deep">
      <Navigation />

      <main className="pt-16 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-text-primary">AlphaGEX Dashboard</h1>
          <p className="text-text-secondary mt-2">Daily trading intelligence</p>
        </div>

        {/* AI Intelligence - Daily Trading Plan and Market Commentary */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <DailyTradingPlan />
          <MarketCommentary />
        </div>

        {/* 0DTE Gamma Expiration Tracker */}
        <GammaExpirationWidget />

        </div>
      </main>
    </div>
  )
}
