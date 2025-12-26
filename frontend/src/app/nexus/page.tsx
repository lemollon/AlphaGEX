'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import NexusCanvas, { BotStatus } from '@/components/NexusCanvas'
import { apiClient } from '@/lib/api'

const TRADING_TIPS = [
  "GEX flips signal dealer gamma crossing zero - watch for explosive moves",
  "Negative GEX means dealers chase price - expect higher volatility",
  "Call walls act as resistance, put walls as support",
  "ARES hunts Iron Condor opportunities when volatility spikes",
  "ATHENA captures directional momentum with GEX-aligned spreads",
  "PHOENIX targets 0DTE gamma scalps during high-activity periods",
  "ATLAS wheels premium through systematic SPX strategies",
  "ORACLE's ML models predict direction with 65%+ accuracy",
  "Psychology traps catch 90% of traders - we exploit their fear",
  "VIX below 15 = complacency. Above 30 = panic. Both create edge",
]

export default function NexusPage() {
  const router = useRouter()
  const [botStatus, setBotStatus] = useState<BotStatus>({
    gex: 'active',
    oracle: 'active',
    ares: 'idle',
    athena: 'idle',
    phoenix: 'idle',
    atlas: 'idle',
  })
  const [currentTip, setCurrentTip] = useState(0)
  const [tipOpacity, setTipOpacity] = useState(1)
  const [marketData, setMarketData] = useState<{
    spy: number | null
    vix: number | null
    marketOpen: boolean
  }>({ spy: null, vix: null, marketOpen: false })

  // Fetch real bot statuses
  useEffect(() => {
    const fetchBotStatus = async () => {
      try {
        const [aresRes, athenaRes] = await Promise.all([
          apiClient.getARESStatus().catch(() => null),
          apiClient.getATHENAStatus().catch(() => null),
        ])

        setBotStatus(prev => ({
          ...prev,
          ares: aresRes?.data?.status === 'running' ? 'trading' :
                aresRes?.data?.enabled ? 'active' : 'idle',
          athena: athenaRes?.data?.status === 'running' ? 'trading' :
                  athenaRes?.data?.enabled ? 'active' : 'idle',
        }))
      } catch (error) {
        console.error('Failed to fetch bot status:', error)
      }
    }

    fetchBotStatus()
    const interval = setInterval(fetchBotStatus, 30000)
    return () => clearInterval(interval)
  }, [])

  // Fetch market data
  useEffect(() => {
    const fetchMarketData = async () => {
      try {
        const [gexRes, timeRes, vixRes] = await Promise.all([
          apiClient.getGEX('SPY').catch(() => null),
          apiClient.time().catch(() => null),
          apiClient.getVIXCurrent().catch(() => null),
        ])

        setMarketData({
          spy: gexRes?.data?.data?.spot_price || null,
          vix: vixRes?.data?.data?.vix_spot || null,
          marketOpen: timeRes?.data?.market_open || false,
        })
      } catch (error) {
        console.error('Failed to fetch market data:', error)
      }
    }

    fetchMarketData()
    const interval = setInterval(fetchMarketData, 60000)
    return () => clearInterval(interval)
  }, [])

  // Cycle tips
  useEffect(() => {
    const interval = setInterval(() => {
      setTipOpacity(0)
      setTimeout(() => {
        setCurrentTip(prev => (prev + 1) % TRADING_TIPS.length)
        setTipOpacity(1)
      }, 300)
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  // Handle node click - navigate to bot page
  const handleNodeClick = useCallback((nodeId: string) => {
    const routes: Record<string, string> = {
      'gex-core': '/',
      'oracle': '/oracle',
      'ares': '/ares',
      'athena': '/athena',
      'phoenix': '/trader',
      'atlas': '/spx-wheel',
    }
    const route = routes[nodeId]
    if (route) router.push(route)
  }, [router])

  // Handle ESC key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') router.push('/')
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [router])

  return (
    <div className="fixed inset-0 bg-[#050810]">
      {/* Full-screen NEXUS Canvas */}
      <NexusCanvas
        botStatus={botStatus}
        onNodeClick={handleNodeClick}
        showLabels={true}
      />

      {/* Top Overlay - Header */}
      <div className="absolute top-0 left-0 right-0 pointer-events-none">
        <div className="bg-gradient-to-b from-[#050810] via-[#050810]/80 to-transparent pt-6 pb-16 px-6">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            {/* Left - Brand */}
            <div className="flex items-center space-x-4">
              <div className="relative">
                <div className="w-3 h-3 rounded-full bg-primary animate-pulse" />
                <div className="absolute inset-0 w-3 h-3 rounded-full bg-primary animate-ping opacity-50" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-text-primary tracking-wide">
                  ALPHAGEX NEXUS
                </h1>
                <p className="text-xs text-text-muted">Neural Trading Interface</p>
              </div>
            </div>

            {/* Center - Market Status */}
            <div className="hidden md:flex items-center space-x-6">
              <div className="flex items-center space-x-2">
                <span className="text-text-muted text-xs">SPY</span>
                <span className="text-text-primary font-mono text-sm font-semibold">
                  {marketData.spy ? `$${marketData.spy.toFixed(2)}` : '---'}
                </span>
              </div>
              <div className="flex items-center space-x-2">
                <span className="text-text-muted text-xs">VIX</span>
                <span className={`font-mono text-sm font-semibold ${
                  marketData.vix
                    ? marketData.vix > 25 ? 'text-danger' : marketData.vix > 18 ? 'text-warning' : 'text-success'
                    : 'text-text-primary'
                }`}>
                  {marketData.vix ? marketData.vix.toFixed(2) : '---'}
                </span>
              </div>
              <div className="flex items-center space-x-2">
                <div className={`w-2 h-2 rounded-full ${marketData.marketOpen ? 'bg-success animate-pulse' : 'bg-warning'}`} />
                <span className="text-text-muted text-xs">
                  {marketData.marketOpen ? 'MARKET OPEN' : 'MARKET CLOSED'}
                </span>
              </div>
            </div>

            {/* Right - Close */}
            <button
              onClick={() => router.push('/')}
              className="pointer-events-auto text-text-muted hover:text-text-primary transition-colors"
            >
              <span className="text-xs">ESC to exit</span>
            </button>
          </div>
        </div>
      </div>

      {/* Bottom Overlay - Tips & Status */}
      <div className="absolute bottom-0 left-0 right-0 pointer-events-none">
        <div className="bg-gradient-to-t from-[#050810] via-[#050810]/90 to-transparent pt-24 pb-8 px-6">
          <div className="max-w-3xl mx-auto text-center">
            {/* Title */}
            <h2 className="text-2xl md:text-3xl font-bold text-text-primary mb-2">
              AlphaGEX Neural Network
            </h2>
            <p className="text-text-secondary text-sm mb-6">
              Click any node to navigate • Real-time bot status monitoring
            </p>

            {/* Pro Tip */}
            <div className="inline-block bg-background-card/60 backdrop-blur-sm rounded-xl px-6 py-4 border border-gray-700/50 mb-6">
              <div className="flex items-start space-x-3">
                <span className="text-primary text-xs font-bold tracking-wider uppercase flex-shrink-0 mt-0.5">
                  PRO TIP
                </span>
                <p
                  className="text-text-secondary text-sm text-left transition-opacity duration-300"
                  style={{ opacity: tipOpacity }}
                >
                  {TRADING_TIPS[currentTip]}
                </p>
              </div>
            </div>

            {/* Tip indicators */}
            <div className="flex justify-center space-x-1.5 mb-6">
              {TRADING_TIPS.map((_, idx) => (
                <div
                  key={idx}
                  className={`h-1 rounded-full transition-all duration-300 ${
                    idx === currentTip ? 'w-6 bg-primary' : 'w-1.5 bg-gray-600'
                  }`}
                />
              ))}
            </div>

            {/* Bot Status Row */}
            <div className="flex justify-center flex-wrap gap-4">
              {Object.entries(botStatus).map(([bot, status]) => (
                <div key={bot} className="flex items-center space-x-2">
                  <div className={`w-2.5 h-2.5 rounded-full ${
                    status === 'trading' ? 'bg-warning animate-pulse' :
                    status === 'active' ? 'bg-success' :
                    status === 'error' ? 'bg-danger' :
                    'bg-gray-500'
                  }`} />
                  <span className="text-text-muted text-xs uppercase tracking-wider">
                    {bot === 'gex' ? 'GEX CORE' : bot}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
