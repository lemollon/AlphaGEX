'use client'

import { useState, useEffect, useCallback } from 'react'
import { Zap, TrendingUp, TrendingDown, Activity, BarChart3, Target, Clock, AlertCircle, RefreshCw } from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useDataCache } from '@/hooks/useDataCache'

type TabType = 'overview' | 'impact' | 'historical'

interface Strike {
  strike: number
  call_gamma: number
  put_gamma: number
  total_gamma: number
  call_oi: number
  put_oi: number
  put_call_ratio: number
}

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
  strikes?: Strike[]
  flip_point?: number
  call_wall?: number
  put_wall?: number
}

interface HistoricalData {
  date: string
  price: number
  net_gex: number
  flip_point: number
  implied_volatility: number
  put_call_ratio: number
}

export default function GammaIntelligence() {
  const [activeTab, setActiveTab] = useState<TabType>('overview')
  const [symbol, setSymbol] = useState('SPY')
  const [vix, setVix] = useState<number>(20)
  const [intelligence, setIntelligence] = useState<GammaIntelligence | null>(null)
  const [loading, setLoading] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [historicalData, setHistoricalData] = useState<HistoricalData[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)
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

  // Fetch historical data
  const fetchHistoricalData = useCallback(async () => {
    try {
      setLoadingHistory(true)
      const response = await apiClient.getGammaHistory(symbol, 30)
      const data = response.data.data
      setHistoricalData(data || [])
    } catch (error: any) {
      console.error('Error fetching historical data:', error)
    } finally {
      setLoadingHistory(false)
    }
  }, [symbol])

  useEffect(() => {
    fetchData()
  }, [symbol, vix])

  useEffect(() => {
    // Fetch historical data when switching to historical tab
    if (activeTab === 'historical' && historicalData.length === 0) {
      fetchHistoricalData()
    }
  }, [activeTab, historicalData.length, fetchHistoricalData])

  const handleRefresh = () => {
    fetchData(true)
    if (activeTab === 'historical') {
      fetchHistoricalData()
    }
  }

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
                <h2 className="text-xl font-semibold text-text-primary mb-4">Gamma Exposure by Strike</h2>
                {intelligence.strikes && intelligence.strikes.length > 0 ? (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-sm text-text-muted mb-2">
                      <span>Strike</span>
                      <span>Call Gamma</span>
                      <span>Put Gamma</span>
                      <span>Net Gamma</span>
                    </div>
                    <div className="max-h-80 overflow-y-auto space-y-1">
                      {intelligence.strikes.slice(0, 20).map((strike, idx) => {
                        const maxGamma = Math.max(
                          ...intelligence.strikes!.map(s => Math.max(Math.abs(s.call_gamma), Math.abs(s.put_gamma)))
                        )
                        const callWidth = (Math.abs(strike.call_gamma) / maxGamma) * 100
                        const putWidth = (Math.abs(strike.put_gamma) / maxGamma) * 100
                        const isNearSpot = Math.abs(strike.strike - intelligence.spot_price) < intelligence.spot_price * 0.02

                        return (
                          <div
                            key={idx}
                            className={`relative p-2 rounded ${isNearSpot ? 'bg-primary/10 border border-primary/30' : 'bg-background-hover'}`}
                          >
                            <div className="flex items-center justify-between text-sm mb-1">
                              <span className="font-mono font-semibold text-text-primary w-20">
                                ${strike.strike.toFixed(0)}
                                {strike.strike === intelligence.flip_point && <span className="ml-1 text-xs text-warning">⚡</span>}
                                {strike.strike === intelligence.call_wall && <span className="ml-1 text-xs text-success">🔼</span>}
                                {strike.strike === intelligence.put_wall && <span className="ml-1 text-xs text-danger">🔽</span>}
                              </span>
                              <span className="text-success font-mono w-24 text-right">{formatNumber(strike.call_gamma)}</span>
                              <span className="text-danger font-mono w-24 text-right">{formatNumber(strike.put_gamma)}</span>
                              <span className={`font-mono w-24 text-right ${strike.total_gamma > 0 ? 'text-success' : 'text-danger'}`}>
                                {formatNumber(strike.total_gamma)}
                              </span>
                            </div>
                            <div className="flex gap-1">
                              <div className="flex-1 h-1 bg-background-deep rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-success"
                                  style={{ width: `${callWidth}%` }}
                                />
                              </div>
                              <div className="flex-1 h-1 bg-background-deep rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-danger"
                                  style={{ width: `${putWidth}%` }}
                                />
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                    <div className="text-xs text-text-muted mt-2 space-y-1">
                      <div>⚡ = GEX Flip Point</div>
                      <div>🔼 = Call Wall | 🔽 = Put Wall</div>
                    </div>
                  </div>
                ) : (
                  <div className="h-80 bg-background-deep rounded-lg flex items-center justify-center border border-border">
                    <div className="text-center">
                      <BarChart3 className="w-16 h-16 text-text-muted mx-auto mb-2" />
                      <p className="text-text-secondary">No strike data available</p>
                    </div>
                  </div>
                )}
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
                {intelligence && intelligence.strikes && intelligence.strikes.length > 0 ? (
                  <div className="space-y-4">
                    <div className="h-64 relative">
                      {/* Price range visualization */}
                      <div className="space-y-2">
                        {intelligence.strikes.slice(0, 15).map((strike, idx) => {
                          const distance = ((strike.strike - intelligence.spot_price) / intelligence.spot_price) * 100
                          const netGamma = strike.total_gamma
                          const maxAbsGamma = Math.max(...intelligence.strikes!.map(s => Math.abs(s.total_gamma)))
                          const barWidth = (Math.abs(netGamma) / maxAbsGamma) * 100

                          return (
                            <div key={idx} className="flex items-center gap-2">
                              <span className="text-xs font-mono w-16 text-text-secondary">
                                ${strike.strike.toFixed(0)}
                              </span>
                              <span className={`text-xs w-12 ${distance > 0 ? 'text-success' : 'text-danger'}`}>
                                {distance > 0 ? '+' : ''}{distance.toFixed(1)}%
                              </span>
                              <div className="flex-1 h-6 bg-background-deep rounded relative overflow-hidden">
                                <div
                                  className={`h-full ${netGamma > 0 ? 'bg-success' : 'bg-danger'} transition-all`}
                                  style={{ width: `${barWidth}%` }}
                                />
                                <span className="absolute inset-0 flex items-center justify-center text-xs font-mono text-white">
                                  {formatNumber(netGamma)}
                                </span>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-4 p-4 bg-background-hover rounded-lg">
                      <div>
                        <p className="text-text-muted text-xs uppercase mb-1">Current Spot</p>
                        <p className="text-xl font-bold text-primary">${intelligence.spot_price.toFixed(2)}</p>
                      </div>
                      <div>
                        <p className="text-text-muted text-xs uppercase mb-1">Flip Point</p>
                        <p className="text-xl font-bold text-warning">${intelligence.flip_point?.toFixed(2) || 'N/A'}</p>
                      </div>
                      <div>
                        <p className="text-text-muted text-xs uppercase mb-1">Distance to Flip</p>
                        <p className={`text-xl font-bold ${(intelligence.flip_point || 0) > intelligence.spot_price ? 'text-success' : 'text-danger'}`}>
                          {intelligence.flip_point ? ((intelligence.flip_point - intelligence.spot_price) / intelligence.spot_price * 100).toFixed(2) : 'N/A'}%
                        </p>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="h-80 bg-background-deep rounded-lg flex items-center justify-center border border-border">
                    <div className="text-center">
                      <BarChart3 className="w-16 h-16 text-text-muted mx-auto mb-2" />
                      <p className="text-text-secondary">No strike data available</p>
                    </div>
                  </div>
                )}
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
                <h2 className="text-xl font-semibold text-text-primary mb-4">Gamma Exposure Trends (30 Days)</h2>
                {loadingHistory ? (
                  <div className="h-80 bg-background-deep rounded-lg flex items-center justify-center border border-border">
                    <div className="text-center">
                      <RefreshCw className="w-8 h-8 text-primary mx-auto mb-2 animate-spin" />
                      <p className="text-text-secondary">Loading historical data...</p>
                    </div>
                  </div>
                ) : historicalData.length > 0 ? (
                  <div className="space-y-4">
                    {/* Net GEX Trend */}
                    <div>
                      <h3 className="text-sm font-semibold text-text-secondary mb-2">Net GEX Over Time</h3>
                      <div className="h-48 relative">
                        <div className="space-y-1">
                          {historicalData.slice(0, 20).map((point, idx) => {
                            const maxAbsGex = Math.max(...historicalData.map(p => Math.abs(p.net_gex)))
                            const barWidth = (Math.abs(point.net_gex) / maxAbsGex) * 100
                            const date = new Date(point.date.replace('_', ' '))

                            return (
                              <div key={idx} className="flex items-center gap-2">
                                <span className="text-xs font-mono w-24 text-text-muted">
                                  {date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                                </span>
                                <span className="text-xs font-mono w-16 text-text-secondary">
                                  ${point.price.toFixed(2)}
                                </span>
                                <div className="flex-1 h-5 bg-background-deep rounded relative overflow-hidden">
                                  <div
                                    className={`h-full ${point.net_gex > 0 ? 'bg-success' : 'bg-danger'} transition-all`}
                                    style={{ width: `${barWidth}%` }}
                                  />
                                  <span className="absolute inset-0 flex items-center justify-center text-xs font-mono text-white">
                                    {(point.net_gex / 1e9).toFixed(2)}B
                                  </span>
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    </div>

                    {/* IV Trend */}
                    <div>
                      <h3 className="text-sm font-semibold text-text-secondary mb-2">Implied Volatility Trend</h3>
                      <div className="h-32 relative">
                        <div className="space-y-1">
                          {historicalData.slice(0, 15).map((point, idx) => {
                            const maxIV = Math.max(...historicalData.map(p => p.implied_volatility))
                            const barWidth = (point.implied_volatility / maxIV) * 100
                            const date = new Date(point.date.replace('_', ' '))

                            return (
                              <div key={idx} className="flex items-center gap-2">
                                <span className="text-xs font-mono w-24 text-text-muted">
                                  {date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                                </span>
                                <div className="flex-1 h-4 bg-background-deep rounded relative overflow-hidden">
                                  <div
                                    className="h-full bg-warning transition-all"
                                    style={{ width: `${barWidth}%` }}
                                  />
                                  <span className="absolute inset-0 flex items-center justify-center text-xs font-mono text-white">
                                    {(point.implied_volatility * 100).toFixed(1)}%
                                  </span>
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="h-80 bg-background-deep rounded-lg flex items-center justify-center border border-border">
                    <div className="text-center">
                      <Clock className="w-16 h-16 text-text-muted mx-auto mb-2" />
                      <p className="text-text-secondary">No historical data available</p>
                    </div>
                  </div>
                )}
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="card">
                  <h2 className="text-lg font-semibold text-text-primary mb-4">30-Day Statistics</h2>
                  {historicalData.length > 0 ? (
                    <div className="space-y-3">
                      <div className="flex justify-between items-center p-3 bg-background-hover rounded-lg">
                        <span className="text-text-secondary">Avg Net GEX</span>
                        <span className="text-text-primary font-semibold">
                          ${(historicalData.reduce((sum, p) => sum + p.net_gex, 0) / historicalData.length / 1e9).toFixed(2)}B
                        </span>
                      </div>
                      <div className="flex justify-between items-center p-3 bg-background-hover rounded-lg">
                        <span className="text-text-secondary">Max GEX</span>
                        <span className="text-success font-semibold">
                          ${(Math.max(...historicalData.map(p => p.net_gex)) / 1e9).toFixed(2)}B
                        </span>
                      </div>
                      <div className="flex justify-between items-center p-3 bg-background-hover rounded-lg">
                        <span className="text-text-secondary">Min GEX</span>
                        <span className="text-danger font-semibold">
                          ${(Math.min(...historicalData.map(p => p.net_gex)) / 1e9).toFixed(2)}B
                        </span>
                      </div>
                      <div className="flex justify-between items-center p-3 bg-background-hover rounded-lg">
                        <span className="text-text-secondary">Avg IV</span>
                        <span className="text-warning font-semibold">
                          {(historicalData.reduce((sum, p) => sum + p.implied_volatility, 0) / historicalData.length * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="flex justify-between items-center p-3 bg-background-hover rounded-lg">
                        <span className="text-text-secondary">Avg Put/Call Ratio</span>
                        <span className="text-text-primary font-semibold">
                          {(historicalData.reduce((sum, p) => sum + p.put_call_ratio, 0) / historicalData.length).toFixed(2)}
                        </span>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-8 text-text-muted">
                      No data available
                    </div>
                  )}
                </div>

                <div className="card">
                  <h2 className="text-lg font-semibold text-text-primary mb-4">Regime Changes</h2>
                  {historicalData.length > 1 ? (
                    <div className="space-y-3">
                      {(() => {
                        const regimeChanges = []
                        for (let i = 1; i < historicalData.length && regimeChanges.length < 5; i++) {
                          const curr = historicalData[i]
                          const prev = historicalData[i - 1]

                          // Detect GEX flip
                          if ((prev.net_gex > 0 && curr.net_gex < 0) || (prev.net_gex < 0 && curr.net_gex > 0)) {
                            const daysAgo = i
                            regimeChanges.push({
                              daysAgo,
                              type: curr.net_gex > 0 ? 'Negative → Positive GEX' : 'Positive → Negative GEX',
                              color: curr.net_gex > 0 ? 'text-success' : 'text-danger'
                            })
                          }

                          // Detect major IV changes (>10% change)
                          const ivChange = Math.abs((curr.implied_volatility - prev.implied_volatility) / prev.implied_volatility)
                          if (ivChange > 0.1) {
                            const daysAgo = i
                            regimeChanges.push({
                              daysAgo,
                              type: curr.implied_volatility > prev.implied_volatility ? 'IV Spike +' + (ivChange * 100).toFixed(0) + '%' : 'IV Drop -' + (ivChange * 100).toFixed(0) + '%',
                              color: curr.implied_volatility > prev.implied_volatility ? 'text-warning' : 'text-primary'
                            })
                          }
                        }

                        return regimeChanges.length > 0 ? regimeChanges.slice(0, 5).map((change, idx) => (
                          <div key={idx} className="p-3 bg-background-hover rounded-lg">
                            <p className="text-text-muted text-sm">{change.daysAgo} day{change.daysAgo > 1 ? 's' : ''} ago</p>
                            <p className={`${change.color} font-medium mt-1`}>{change.type}</p>
                          </div>
                        )) : (
                          <div className="text-center py-8 text-text-muted">
                            No major regime changes detected
                          </div>
                        )
                      })()}
                    </div>
                  ) : (
                    <div className="text-center py-8 text-text-muted">
                      No data available
                    </div>
                  )}
                </div>
              </div>

              <div className="card">
                <h2 className="text-xl font-semibold text-text-primary mb-4">Correlation Analysis</h2>
                {historicalData.length > 5 ? (
                  <div className="space-y-4">
                    {(() => {
                      // Calculate correlation between price and net_gex
                      const prices = historicalData.map(d => d.price)
                      const gexes = historicalData.map(d => d.net_gex)
                      const ivs = historicalData.map(d => d.implied_volatility)
                      const pcrs = historicalData.map(d => d.put_call_ratio)

                      const correlation = (x: number[], y: number[]) => {
                        const n = x.length
                        const sum_x = x.reduce((a, b) => a + b, 0)
                        const sum_y = y.reduce((a, b) => a + b, 0)
                        const sum_xy = x.reduce((sum, xi, i) => sum + xi * y[i], 0)
                        const sum_x2 = x.reduce((sum, xi) => sum + xi * xi, 0)
                        const sum_y2 = y.reduce((sum, yi) => sum + yi * yi, 0)

                        return (n * sum_xy - sum_x * sum_y) / Math.sqrt((n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y))
                      }

                      const correlations = [
                        { label: 'Price vs Net GEX', value: correlation(prices, gexes) },
                        { label: 'Price vs IV', value: correlation(prices, ivs) },
                        { label: 'Net GEX vs IV', value: correlation(gexes, ivs) },
                        { label: 'Put/Call Ratio vs IV', value: correlation(pcrs, ivs) }
                      ]

                      return (
                        <div className="space-y-3">
                          {correlations.map((corr, idx) => {
                            const absValue = Math.abs(corr.value)
                            const color = absValue > 0.7 ? 'text-success' : absValue > 0.4 ? 'text-warning' : 'text-text-muted'
                            const barColor = corr.value > 0 ? 'bg-success' : 'bg-danger'
                            const barWidth = Math.abs(corr.value) * 100

                            return (
                              <div key={idx} className="space-y-1">
                                <div className="flex justify-between items-center">
                                  <span className="text-sm text-text-secondary">{corr.label}</span>
                                  <span className={`text-sm font-semibold ${color}`}>
                                    {corr.value.toFixed(3)}
                                  </span>
                                </div>
                                <div className="h-2 bg-background-deep rounded-full overflow-hidden">
                                  <div
                                    className={`h-full ${barColor}`}
                                    style={{ width: `${barWidth}%` }}
                                  />
                                </div>
                                <p className="text-xs text-text-muted">
                                  {absValue > 0.7 ? 'Strong' : absValue > 0.4 ? 'Moderate' : 'Weak'} {corr.value > 0 ? 'positive' : 'negative'} correlation
                                </p>
                              </div>
                            )
                          })}
                        </div>
                      )
                    })()}
                  </div>
                ) : (
                  <div className="h-64 bg-background-deep rounded-lg flex items-center justify-center border border-border">
                    <div className="text-center">
                      <Activity className="w-16 h-16 text-text-muted mx-auto mb-2" />
                      <p className="text-text-secondary">Not enough data for correlation analysis</p>
                      <p className="text-text-muted text-sm mt-1">Need at least 5 days of history</p>
                    </div>
                  </div>
                )}
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
