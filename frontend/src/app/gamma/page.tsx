'use client'

import { useState, useEffect, useCallback } from 'react'
import { Zap, TrendingUp, TrendingDown, Activity, BarChart3, Target, Clock, AlertCircle, RefreshCw } from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useDataCache } from '@/hooks/useDataCache'

type TabType = 'overview' | 'impact' | 'historical'

interface GammaIntelligence {
  symbol: string
  spot_price: number
  total_gamma: number
  call_gamma: number
  put_gamma: number
  gamma_exposure_ratio: number
  vanna_exposure: number
  charm_decay: number
  risk_reversal: number
  skew_index: number
  key_observations: string[]
  trading_implications: string[]
  market_regime: {
    state: string
    volatility: string
    trend: string
  }
}

export default function GammaIntelligence() {
  const [activeTab, setActiveTab] = useState<TabType>('overview')
  const [symbol, setSymbol] = useState('SPY')
  const [vix, setVix] = useState<number>(20)
  const [intelligence, setIntelligence] = useState<GammaIntelligence | null>(null)
  const [loading, setLoading] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { data: wsData, isConnected } = useWebSocket(symbol)

  // Position simulator state
  const [simStrike, setSimStrike] = useState(450)
  const [simQuantity, setSimQuantity] = useState(10)
  const [simOptionType, setSimOptionType] = useState<'call' | 'put'>('call')

  // Cache for gamma intelligence
  const gammaCache = useDataCache<GammaIntelligence>({
    key: `gamma-intelligence-${symbol}-${vix}`,
    ttl: 5 * 60 * 1000 // 5 minutes
  })

  // Fetch gamma intelligence
  const fetchData = useCallback(async (forceRefresh = false) => {
    // Use cached data if fresh
    if (!forceRefresh && gammaCache.isCacheFresh && gammaCache.cachedData) {
      setIntelligence(gammaCache.cachedData)
      return
    }

    try {
      forceRefresh ? setIsRefreshing(true) : setLoading(true)
      setError(null)

      console.log('=== FETCHING GAMMA INTELLIGENCE ===')
      console.log('Symbol:', symbol, 'VIX:', vix)

      const response = await apiClient.getGammaIntelligence(symbol, vix)

      console.log('API Response:', response.data)

      const data = response.data.data
      setIntelligence(data)
      gammaCache.setCache(data)
    } catch (error: any) {
      console.error('Error fetching gamma intelligence:', error)
      const errorMessage = error.response?.data?.detail || error.message || 'Failed to fetch gamma intelligence'
      setError(errorMessage)
    } finally {
      setLoading(false)
      setIsRefreshing(false)
    }
  }, [symbol, vix, gammaCache])

  useEffect(() => {
    fetchData()
  }, [symbol, vix])

  const handleRefresh = () => fetchData(true)

  // Update from WebSocket
  useEffect(() => {
    if (wsData?.type === 'gamma_update' && wsData.data) {
      setIntelligence(wsData.data)
    }
  }, [wsData])

  const formatNumber = (value: number) => {
    const absValue = Math.abs(value)
    if (absValue >= 1e9) return `${(value / 1e9).toFixed(2)}B`
    if (absValue >= 1e6) return `${(value / 1e6).toFixed(2)}M`
    if (absValue >= 1e3) return `${(value / 1e3).toFixed(2)}K`
    return value.toFixed(2)
  }

  const tabs = [
    { id: 'overview' as TabType, label: 'Overview', icon: Zap },
    { id: 'impact' as TabType, label: 'Position Impact', icon: Target },
    { id: 'historical' as TabType, label: 'Historical Analysis', icon: Clock }
  ]

  const popularSymbols = ['SPY', 'QQQ', 'IWM', 'AAPL', 'TSLA', 'NVDA']

  return (
    <div className="min-h-screen">
      <Navigation />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="space-y-6">
          {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-text-primary">Gamma Intelligence</h1>
          <p className="text-text-secondary mt-1">Advanced gamma exposure analysis and insights</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Refresh Button */}
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-background-hover hover:bg-background-hover/70 text-text-primary transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            <span className="text-sm font-medium hidden sm:inline">
              {isRefreshing ? 'Refreshing...' : 'Refresh'}
            </span>
          </button>

          {/* Cache Status */}
          {gammaCache.isCacheFresh && !isRefreshing && (
            <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary/10 text-primary text-sm">
              <Clock className="w-4 h-4" />
              <span>Cached {Math.floor(gammaCache.timeUntilExpiry / 1000 / 60)}m</span>
            </div>
          )}

          {/* Live Status */}
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg ${
            isConnected ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger'
          }`}>
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-success' : 'bg-danger'} animate-pulse`} />
            <span className="text-sm font-medium">{isConnected ? 'Live' : 'Disconnected'}</span>
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="card">
        <div className="flex items-center gap-6 flex-wrap">
          <div className="flex items-center gap-4">
            <label className="text-text-secondary font-medium">Symbol:</label>
            <div className="flex gap-2">
              {popularSymbols.map((sym) => (
                <button
                  key={sym}
                  onClick={() => setSymbol(sym)}
                  className={`px-3 py-1.5 rounded-lg font-medium transition-all text-sm ${
                    symbol === sym
                      ? 'bg-primary text-white'
                      : 'bg-background-hover text-text-secondary hover:bg-background-hover/70'
                  }`}
                >
                  {sym}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <label className="text-text-secondary font-medium">VIX:</label>
            <input
              type="number"
              value={vix}
              onChange={(e) => setVix(Number(e.target.value))}
              className="input w-20"
              min="10"
              max="80"
              step="0.5"
            />
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-border">
        {tabs.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-6 py-3 font-medium transition-all relative ${
                activeTab === tab.id
                  ? 'text-primary'
                  : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
              {activeTab === tab.id && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
              )}
            </button>
          )
        })}
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="card h-32 skeleton" />
          ))}
        </div>
      ) : error ? (
        <div className="card text-center py-12">
          <AlertCircle className="w-16 h-16 text-danger mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-text-primary mb-2">Failed to Load Gamma Intelligence</h3>
          <p className="text-text-secondary mb-4">{error}</p>
          <p className="text-text-muted text-sm mb-4">Check browser console (F12) for details</p>
          <button
            onClick={() => fetchData(true)}
            className="px-6 py-2 bg-primary hover:bg-primary/80 text-white rounded-lg font-medium transition-all"
          >
            Try Again
          </button>
        </div>
      ) : intelligence ? (
        <>
          {/* Overview Tab */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              {/* Key Metrics */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="card">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-text-secondary text-sm">Total Gamma</p>
                      <p className={`text-2xl font-bold mt-1 ${
                        intelligence.total_gamma > 0 ? 'text-success' : 'text-danger'
                      }`}>
                        {formatNumber(intelligence.total_gamma)}
                      </p>
                    </div>
                    <Zap className="text-primary w-8 h-8" />
                  </div>
                </div>

                <div className="card">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-text-secondary text-sm">GEX Ratio</p>
                      <p className="text-2xl font-bold text-text-primary mt-1">
                        {intelligence.gamma_exposure_ratio.toFixed(2)}
                      </p>
                    </div>
                    <Activity className="text-primary w-8 h-8" />
                  </div>
                </div>

                <div className="card">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-text-secondary text-sm">Vanna Exposure</p>
                      <p className="text-2xl font-bold text-text-primary mt-1">
                        {formatNumber(intelligence.vanna_exposure)}
                      </p>
                    </div>
                    <TrendingUp className="text-primary w-8 h-8" />
                  </div>
                </div>

                <div className="card">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-text-secondary text-sm">Charm Decay</p>
                      <p className={`text-2xl font-bold mt-1 ${
                        intelligence.charm_decay < 0 ? 'text-danger' : 'text-success'
                      }`}>
                        {formatNumber(intelligence.charm_decay)}
                      </p>
                    </div>
                    <Clock className="text-primary w-8 h-8" />
                  </div>
                </div>
              </div>

              {/* Market Regime */}
              <div className="card">
                <h2 className="text-xl font-semibold text-text-primary mb-4">Market Regime</h2>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="p-4 bg-background-hover rounded-lg">
                    <p className="text-text-secondary text-sm mb-2">State</p>
                    <p className="text-lg font-bold text-primary">{intelligence.market_regime.state}</p>
                  </div>
                  <div className="p-4 bg-background-hover rounded-lg">
                    <p className="text-text-secondary text-sm mb-2">Volatility</p>
                    <p className="text-lg font-bold text-warning">{intelligence.market_regime.volatility}</p>
                  </div>
                  <div className="p-4 bg-background-hover rounded-lg">
                    <p className="text-text-secondary text-sm mb-2">Trend</p>
                    <p className="text-lg font-bold text-success">{intelligence.market_regime.trend}</p>
                  </div>
                </div>
              </div>

              {/* Gamma Exposure Heatmap */}
              <div className="card">
                <h2 className="text-xl font-semibold text-text-primary mb-4">Gamma Exposure Heatmap</h2>
                <div className="h-80 bg-background-deep rounded-lg flex items-center justify-center border border-border">
                  <div className="text-center">
                    <BarChart3 className="w-16 h-16 text-text-muted mx-auto mb-2" />
                    <p className="text-text-secondary">Heatmap Visualization</p>
                    <p className="text-text-muted text-sm mt-1">Coming soon...</p>
                  </div>
                </div>
              </div>

              {/* Key Observations */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="card">
                  <h2 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
                    <AlertCircle className="w-5 h-5 text-primary" />
                    Key Observations
                  </h2>
                  <ul className="space-y-2">
                    {intelligence.key_observations.map((obs, idx) => (
                      <li key={idx} className="flex items-start gap-2 text-text-secondary">
                        <span className="text-primary mt-1">•</span>
                        <span>{obs}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="card">
                  <h2 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
                    <TrendingUp className="w-5 h-5 text-success" />
                    Trading Implications
                  </h2>
                  <ul className="space-y-2">
                    {intelligence.trading_implications.map((impl, idx) => (
                      <li key={idx} className="flex items-start gap-2 text-text-secondary">
                        <span className="text-success mt-1">•</span>
                        <span>{impl}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Greeks Summary */}
              <div className="card">
                <h2 className="text-xl font-semibold text-text-primary mb-4">Greeks Summary</h2>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="p-4 bg-background-hover rounded-lg">
                    <p className="text-text-muted text-xs uppercase">Risk Reversal</p>
                    <p className="text-xl font-bold text-text-primary mt-1">
                      {intelligence.risk_reversal.toFixed(3)}
                    </p>
                  </div>
                  <div className="p-4 bg-background-hover rounded-lg">
                    <p className="text-text-muted text-xs uppercase">Skew Index</p>
                    <p className="text-xl font-bold text-text-primary mt-1">
                      {intelligence.skew_index.toFixed(2)}
                    </p>
                  </div>
                  <div className="p-4 bg-background-hover rounded-lg">
                    <p className="text-text-muted text-xs uppercase">Call Gamma</p>
                    <p className="text-xl font-bold text-success mt-1">
                      {formatNumber(intelligence.call_gamma)}
                    </p>
                  </div>
                  <div className="p-4 bg-background-hover rounded-lg">
                    <p className="text-text-muted text-xs uppercase">Put Gamma</p>
                    <p className="text-xl font-bold text-danger mt-1">
                      {formatNumber(intelligence.put_gamma)}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Position Impact Tab */}
          {activeTab === 'impact' && (
            <div className="space-y-6">
              <div className="card">
                <h2 className="text-xl font-semibold text-text-primary mb-4">Position Simulator</h2>
                <p className="text-text-secondary mb-6">
                  Simulate how a position would affect your gamma exposure and risk profile
                </p>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                  <div>
                    <label className="text-text-secondary text-sm mb-2 block">Option Type</label>
                    <select
                      value={simOptionType}
                      onChange={(e) => setSimOptionType(e.target.value as 'call' | 'put')}
                      className="input w-full"
                    >
                      <option value="call">Call</option>
                      <option value="put">Put</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-text-secondary text-sm mb-2 block">Strike Price</label>
                    <input
                      type="number"
                      value={simStrike}
                      onChange={(e) => setSimStrike(Number(e.target.value))}
                      className="input w-full"
                      step="1"
                    />
                  </div>
                  <div>
                    <label className="text-text-secondary text-sm mb-2 block">Quantity</label>
                    <input
                      type="number"
                      value={simQuantity}
                      onChange={(e) => setSimQuantity(Number(e.target.value))}
                      className="input w-full"
                      min="1"
                      step="1"
                    />
                  </div>
                  <div className="flex items-end">
                    <button className="btn-primary w-full">Calculate Impact</button>
                  </div>
                </div>

                {/* Simulated Results */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 bg-background-hover rounded-lg">
                  <div>
                    <p className="text-text-muted text-xs uppercase mb-1">Position Gamma</p>
                    <p className="text-xl font-bold text-primary">+$2,450</p>
                  </div>
                  <div>
                    <p className="text-text-muted text-xs uppercase mb-1">Delta Impact</p>
                    <p className="text-xl font-bold text-success">+0.65</p>
                  </div>
                  <div>
                    <p className="text-text-muted text-xs uppercase mb-1">Theta Decay</p>
                    <p className="text-xl font-bold text-danger">-$125/day</p>
                  </div>
                </div>
              </div>

              {/* Impact Chart */}
              <div className="card">
                <h2 className="text-xl font-semibold text-text-primary mb-4">Exposure Impact Over Price Range</h2>
                <div className="h-80 bg-background-deep rounded-lg flex items-center justify-center border border-border">
                  <div className="text-center">
                    <BarChart3 className="w-16 h-16 text-text-muted mx-auto mb-2" />
                    <p className="text-text-secondary">Impact Chart</p>
                    <p className="text-text-muted text-sm mt-1">Coming soon...</p>
                  </div>
                </div>
              </div>

              {/* Risk Analysis */}
              <div className="card">
                <h2 className="text-xl font-semibold text-text-primary mb-4">Risk Analysis</h2>
                <div className="space-y-4">
                  <div className="p-4 bg-success/5 border border-success/20 rounded-lg">
                    <p className="text-success font-semibold mb-2">Max Profit Potential</p>
                    <p className="text-text-secondary">+$4,500 at {simStrike + 10} ({simOptionType})</p>
                  </div>
                  <div className="p-4 bg-danger/5 border border-danger/20 rounded-lg">
                    <p className="text-danger font-semibold mb-2">Max Loss Potential</p>
                    <p className="text-text-secondary">-$1,200 (premium paid)</p>
                  </div>
                  <div className="p-4 bg-warning/5 border border-warning/20 rounded-lg">
                    <p className="text-warning font-semibold mb-2">Break-Even Point</p>
                    <p className="text-text-secondary">${simStrike + 12} by expiration</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Historical Analysis Tab */}
          {activeTab === 'historical' && (
            <div className="space-y-6">
              <div className="card">
                <h2 className="text-xl font-semibold text-text-primary mb-4">Gamma Exposure Trends</h2>
                <div className="h-80 bg-background-deep rounded-lg flex items-center justify-center border border-border">
                  <div className="text-center">
                    <Clock className="w-16 h-16 text-text-muted mx-auto mb-2" />
                    <p className="text-text-secondary">Historical Trend Chart</p>
                    <p className="text-text-muted text-sm mt-1">Coming soon...</p>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="card">
                  <h2 className="text-lg font-semibold text-text-primary mb-4">30-Day Statistics</h2>
                  <div className="space-y-3">
                    <div className="flex justify-between items-center p-3 bg-background-hover rounded-lg">
                      <span className="text-text-secondary">Avg Net GEX</span>
                      <span className="text-text-primary font-semibold">$2.4B</span>
                    </div>
                    <div className="flex justify-between items-center p-3 bg-background-hover rounded-lg">
                      <span className="text-text-secondary">Max GEX</span>
                      <span className="text-success font-semibold">$4.1B</span>
                    </div>
                    <div className="flex justify-between items-center p-3 bg-background-hover rounded-lg">
                      <span className="text-text-secondary">Min GEX</span>
                      <span className="text-danger font-semibold">$0.8B</span>
                    </div>
                    <div className="flex justify-between items-center p-3 bg-background-hover rounded-lg">
                      <span className="text-text-secondary">Volatility</span>
                      <span className="text-warning font-semibold">45%</span>
                    </div>
                  </div>
                </div>

                <div className="card">
                  <h2 className="text-lg font-semibold text-text-primary mb-4">Regime Changes</h2>
                  <div className="space-y-3">
                    <div className="p-3 bg-background-hover rounded-lg">
                      <p className="text-text-muted text-sm">5 days ago</p>
                      <p className="text-text-primary font-medium mt-1">Positive → Negative GEX</p>
                    </div>
                    <div className="p-3 bg-background-hover rounded-lg">
                      <p className="text-text-muted text-sm">12 days ago</p>
                      <p className="text-text-primary font-medium mt-1">Low Vol → High Vol</p>
                    </div>
                    <div className="p-3 bg-background-hover rounded-lg">
                      <p className="text-text-muted text-sm">18 days ago</p>
                      <p className="text-text-primary font-medium mt-1">Negative → Positive GEX</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="card">
                <h2 className="text-xl font-semibold text-text-primary mb-4">Correlation Analysis</h2>
                <div className="h-64 bg-background-deep rounded-lg flex items-center justify-center border border-border">
                  <div className="text-center">
                    <Activity className="w-16 h-16 text-text-muted mx-auto mb-2" />
                    <p className="text-text-secondary">Correlation Matrix</p>
                    <p className="text-text-muted text-sm mt-1">Coming soon...</p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="card text-center py-12">
          <p className="text-text-secondary">No data available for {symbol}</p>
        </div>
      )}
        </div>
      </main>
    </div>
  )
}
