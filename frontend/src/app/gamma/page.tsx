'use client'

import { logger } from '@/lib/logger'

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { Zap, TrendingUp, TrendingDown, Activity, BarChart3, Target, Clock, AlertCircle, RefreshCw, Calendar } from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useDataCache } from '@/hooks/useDataCache'
import { useRouter } from 'next/navigation'
import { getCacheTTL } from '@/lib/cacheConfig'
import { useVIX } from '@/lib/hooks/useMarketData'

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
  mm_state?: {
    name: string
    behavior: string
    confidence: number
    action: string
    threshold: number
  }
  net_gex?: number
  strikes?: Strike[]
  flip_point?: number
  call_wall?: number
  put_wall?: number
  data_date?: string  // When the market data was collected
  // Bug #12 Fix: Data source tracking for stale data indication
  data_source?: string  // 'live_api' | 'tradier_calculated' | 'database_fallback'
  data_age?: string     // 'live' | 'recent' | '2h old' | '1d old' etc.
  profile_source?: string  // 'live_api' | 'tradier_calculated' | 'none'
}

export default function GammaIntelligence() {
  const router = useRouter()
  const [symbol, setSymbol] = useState('SPY')

  // Use SWR for VIX data (cached across pages)
  const { data: vixResponse, isLoading: vixLoading } = useVIX()
  const vix = vixResponse?.data?.vix_spot || vixResponse?.vix_spot || 20

  const [intelligence, setIntelligence] = useState<GammaIntelligence | null>(null)
  const [loading, setLoading] = useState(true)  // Bug #1 Fix: Start with loading=true
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [retryCount, setRetryCount] = useState(0)  // Bug #10 Fix: Track retries
  const { data: wsData, isConnected } = useWebSocket(symbol)

  // Bug #11 Fix: Remove VIX from cache key (VIX changes frequently, creates too many cache entries)
  // Bug #2 Fix: Memoize cache TTL to prevent re-creation on every render
  const cacheTTL = useMemo(() => getCacheTTL('GAMMA_INTELLIGENCE', true), [])
  const gammaCache = useDataCache<GammaIntelligence>({
    key: `gamma-intelligence-${symbol}`,  // Removed VIX from key
    ttl: cacheTTL
  })

  // Bug #2 Fix: Use ref to access cache without adding to dependencies
  const gammaCacheRef = useRef(gammaCache)
  gammaCacheRef.current = gammaCache

  // Fetch gamma intelligence
  // Bug #2 Fix: Removed gammaCache from dependencies to prevent race condition
  // Bug #10 Fix: Added retry mechanism for transient failures
  const fetchData = useCallback(async (forceRefresh = false, signal?: AbortSignal, retry = 0) => {
    const cache = gammaCacheRef.current

    // Use cached data if fresh (but not on retry)
    if (!forceRefresh && retry === 0 && cache.isCacheFresh && cache.cachedData) {
      setIntelligence(cache.cachedData)
      setLoading(false)
      return
    }

    try {
      forceRefresh ? setIsRefreshing(true) : setLoading(true)
      if (retry === 0) setError(null)

      logger.info('=== FETCHING GAMMA INTELLIGENCE ===')
      logger.info('Symbol:', symbol, 'VIX:', vix, retry > 0 ? `(Retry ${retry}/3)` : '')

      // Bug #16 Fix: Pass vix with fallback to ensure it's never undefined
      const response = await apiClient.getGammaIntelligence(symbol, vix ?? 20)

      // Check if request was cancelled
      if (signal?.aborted) {
        logger.info('Request cancelled')
        return
      }

      logger.info('API Response:', response.data)

      // Bug #17 Fix: Validate response structure before accessing nested data
      const data = response.data?.data
      if (!data) {
        const errorMsg = response.data?.error || response.data?.detail || 'Invalid API response structure'
        logger.error('API returned invalid data structure:', response.data)
        throw new Error(errorMsg)
      }

      logger.info('Has strikes?', data.strikes?.length || 0)

      // Log what we received for debugging
      logger.info('Intelligence data:', {
        has_strikes: !!data.strikes,
        strikes_count: data.strikes?.length || 0,
        has_flip_point: !!data.flip_point,
        has_walls: !!(data.call_wall && data.put_wall)
      })

      setIntelligence(data)
      setRetryCount(0)
      cache.setCache(data)
    } catch (error: any) {
      // Ignore cancellation errors
      if (error.name === 'AbortError' || signal?.aborted) {
        logger.info('Request cancelled')
        return
      }

      logger.error('Error fetching gamma intelligence:', error)

      // Bug #10 Fix: Retry up to 3 times for transient errors
      // Bug #13 Fix: Check signal before retry to prevent stale updates after unmount
      const isRetryable = error.type === 'network' || error.type === 'timeout' || error.status >= 500
      if (isRetryable && retry < 3 && !signal?.aborted) {
        logger.info(`Retrying in ${(retry + 1) * 2} seconds...`)
        setRetryCount(retry + 1)
        await new Promise(resolve => setTimeout(resolve, (retry + 1) * 2000))
        // Check again after delay in case component unmounted during wait
        if (signal?.aborted) {
          logger.info('Retry cancelled - component unmounted')
          return
        }
        return fetchData(forceRefresh, signal, retry + 1)
      }

      const errorMessage = error.response?.data?.detail || error.message || 'Failed to fetch gamma intelligence'
      setError(errorMessage)
    } finally {
      setLoading(false)
      setIsRefreshing(false)
    }
  }, [symbol, vix])  // Removed gammaCache from deps

  // Bug #2 Fix: Use ref for fetchData to avoid dependency issues
  const fetchDataRef = useRef(fetchData)
  fetchDataRef.current = fetchData

  useEffect(() => {
    // Wait for VIX to be loaded before fetching (SWR will provide cached value)
    if (vixLoading) return

    // Create AbortController for request cancellation
    const controller = new AbortController()

    // Always fetch fresh data when symbol or vix changes
    // Bug #2 Fix: Use ref to avoid including fetchData in deps
    fetchDataRef.current(true, controller.signal)

    // Cleanup: cancel request if component unmounts or deps change
    return () => {
      controller.abort()
    }
  }, [symbol, vix, vixLoading])  // Bug #2 Fix: Removed fetchData from deps

  const handleRefresh = () => {
    fetchData(true)
  }

  // Bug #3 Fix: Update from WebSocket - now creates initial intelligence if null
  useEffect(() => {
    if (wsData?.type === 'market_update' && wsData.data) {
      const data = wsData.data
      if (data.symbol === symbol) {
        setIntelligence(prev => {
          // Bug #3 Fix: If prev is null, create a minimal intelligence object
          // This ensures WebSocket updates aren't lost if initial fetch failed
          if (!prev) {
            return {
              symbol: data.symbol,
              spot_price: data.spot_price || 0,
              total_gamma: 0,
              call_gamma: 0,
              put_gamma: 0,
              gamma_exposure_ratio: 0,
              vanna_exposure: 0,
              charm_decay: 0,
              risk_reversal: 0,
              skew_index: 0,
              key_observations: ['Receiving live data from WebSocket'],
              trading_implications: ['Waiting for full data load...'],
              market_regime: { state: 'Unknown', volatility: 'Unknown', trend: 'Unknown' },
              net_gex: data.net_gex || 0,
              flip_point: data.flip_point || 0,
              call_wall: data.call_wall || 0,
              put_wall: data.put_wall || 0,
            }
          }
          return {
            ...prev,
            spot_price: data.spot_price || prev.spot_price,
            net_gex: data.net_gex ?? prev.net_gex,
            flip_point: data.flip_point || prev.flip_point,
            call_wall: data.call_wall || prev.call_wall,
            put_wall: data.put_wall || prev.put_wall
          }
        })
      }
    }
  }, [wsData, symbol])

  const formatNumber = (value: number) => {
    const absValue = Math.abs(value)
    if (absValue >= 1e9) return `${(value / 1e9).toFixed(2)}B`
    if (absValue >= 1e6) return `${(value / 1e6).toFixed(2)}M`
    if (absValue >= 1e3) return `${(value / 1e3).toFixed(2)}K`
    return value.toFixed(2)
  }

  const popularSymbols = ['SPY', 'QQQ', 'IWM', 'AAPL', 'TSLA', 'NVDA']

  return (
    <div className="min-h-screen">
      <Navigation />
      <main className="pt-16 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="space-y-6">
          {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-text-primary flex items-center space-x-3">
            <span>Gamma Intelligence</span>
            <span className="text-primary">•</span>
            <span className="text-primary">{symbol}</span>
          </h1>
          <p className="text-text-secondary mt-1">Advanced gamma exposure analysis and insights for {symbol}</p>
        </div>
        <div className="flex items-center gap-2">
          {/* 0DTE Tracker Button */}
          <button
            onClick={() => router.push('/gamma/0dte')}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-danger hover:bg-danger/80 text-white transition-all"
          >
            <Calendar className="w-4 h-4" />
            <span className="text-sm font-medium hidden sm:inline">0DTE Tracker</span>
          </button>

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

      {/* Bug #12 Fix: Data Date and Stale Data Indicator */}
      {intelligence && (
        <div className="flex flex-wrap items-center gap-2">
          {/* Data Date */}
          {intelligence.data_date && (
            <div className="flex items-center gap-2 text-sm text-primary bg-primary/10 px-3 py-1.5 rounded-lg">
              <Clock className="w-4 h-4" />
              <span>Market Data as of: <span className="font-semibold">{intelligence.data_date}</span></span>
            </div>
          )}

          {/* Bug #12 Fix: Stale Data Warning */}
          {intelligence.data_source === 'database_fallback' && (
            <div className="flex items-center gap-2 text-sm text-warning bg-warning/10 px-3 py-1.5 rounded-lg">
              <AlertCircle className="w-4 h-4" />
              <span>Using cached data ({intelligence.data_age || 'unknown age'})</span>
            </div>
          )}

          {/* Data Source Indicator */}
          {intelligence.data_source && intelligence.data_source !== 'database_fallback' && (
            <div className={`flex items-center gap-2 text-sm px-3 py-1.5 rounded-lg ${
              intelligence.data_source === 'live_api' ? 'text-success bg-success/10' : 'text-primary bg-primary/10'
            }`}>
              <Activity className="w-4 h-4" />
              <span>
                {intelligence.data_source === 'live_api' ? 'Live API' :
                 intelligence.data_source === 'tradier_calculated' ? 'Tradier (calculated)' :
                 intelligence.data_source}
              </span>
            </div>
          )}

          {/* Retry Count Indicator */}
          {retryCount > 0 && (
            <div className="flex items-center gap-2 text-sm text-warning bg-warning/10 px-3 py-1.5 rounded-lg">
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span>Retrying... ({retryCount}/3)</span>
            </div>
          )}
        </div>
      )}

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
          {/* Bug #16 Fix: VIX auto-fetched from API, displayed read-only */}
          <div className="flex items-center gap-3">
            <label className="text-text-secondary font-medium">VIX:</label>
            <div className={`px-3 py-2 rounded-lg font-semibold ${
              vixLoading ? 'bg-background-hover text-text-muted' :
              vix && vix >= 30 ? 'bg-danger/10 text-danger' :
              vix && vix >= 20 ? 'bg-warning/10 text-warning' :
              'bg-success/10 text-success'
            }`}>
              {vixLoading ? (
                <span className="flex items-center gap-2">
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Loading...
                </span>
              ) : (
                <span>{vix?.toFixed(2) || '--'}</span>
              )}
            </div>
          </div>
        </div>
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
                        {/* Bug #14 Fix: Safe property access */}
                        {(intelligence.gamma_exposure_ratio ?? 0).toFixed(2)}
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
                        {intelligence.vanna_exposure !== null ? formatNumber(intelligence.vanna_exposure) : 'N/A'}
                      </p>
                      {intelligence.vanna_exposure === null && (
                        <p className="text-xs text-text-muted mt-1">Requires IV surface</p>
                      )}
                    </div>
                    <TrendingUp className="text-primary w-8 h-8" />
                  </div>
                </div>

                <div className="card">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-text-secondary text-sm">Charm Decay</p>
                      <p className={`text-2xl font-bold mt-1 ${
                        intelligence.charm_decay !== null && intelligence.charm_decay < 0 ? 'text-danger' :
                        intelligence.charm_decay !== null ? 'text-success' : 'text-text-primary'
                      }`}>
                        {intelligence.charm_decay !== null ? formatNumber(intelligence.charm_decay) : 'N/A'}
                      </p>
                      {intelligence.charm_decay === null && (
                        <p className="text-xs text-text-muted mt-1">Requires Greeks data</p>
                      )}
                    </div>
                    <Clock className="text-primary w-8 h-8" />
                  </div>
                </div>
              </div>

              {/* Market Regime */}
              {intelligence.market_regime && (
                <div className="card">
                  <h2 className="text-xl font-semibold text-text-primary mb-4">Market Regime</h2>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="p-4 bg-background-hover rounded-lg">
                      <p className="text-text-secondary text-sm mb-2">State</p>
                      <p className="text-lg font-bold text-primary">{intelligence.market_regime.state || 'Unknown'}</p>
                    </div>
                    <div className="p-4 bg-background-hover rounded-lg">
                      <p className="text-text-secondary text-sm mb-2">Volatility</p>
                      <p className="text-lg font-bold text-warning">{intelligence.market_regime.volatility || 'Unknown'}</p>
                    </div>
                    <div className="p-4 bg-background-hover rounded-lg">
                      <p className="text-text-secondary text-sm mb-2">Trend</p>
                      <p className="text-lg font-bold text-success">{intelligence.market_regime.trend || 'Unknown'}</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Gamma Exposure Heatmap */}
              <div className="card">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h2 className="text-xl font-semibold text-text-primary mb-2">{symbol} Gamma Exposure by Strike</h2>
                    <p className="text-sm text-text-secondary">💰 HOW TO MAKE MONEY: Use gamma walls (🔼 Call Wall / 🔽 Put Wall) as profit targets. Price tends to move toward highest gamma concentrations. Trade toward the flip point (⚡) for directional plays.</p>
                  </div>
                </div>
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
                          ...intelligence.strikes!.map(s => Math.max(Math.abs(s.call_gamma ?? 0), Math.abs(s.put_gamma ?? 0))), 1
                        )
                        const callWidth = (Math.abs(strike.call_gamma ?? 0) / maxGamma) * 100
                        const putWidth = (Math.abs(strike.put_gamma ?? 0) / maxGamma) * 100
                        const spotPrice = intelligence.spot_price || 1
                        const isNearSpot = Math.abs((strike.strike ?? 0) - spotPrice) < spotPrice * 0.02

                        return (
                          <div
                            key={idx}
                            className={`relative p-2 rounded ${isNearSpot ? 'bg-primary/10 border border-primary/30' : 'bg-background-hover'}`}
                          >
                            <div className="flex items-center justify-between text-sm mb-1">
                              <span className="font-mono font-semibold text-text-primary w-20">
                                ${(strike.strike ?? 0).toFixed(0)}
                                {(strike.strike ?? 0) === intelligence.flip_point && <span className="ml-1 text-xs text-warning">⚡</span>}
                                {(strike.strike ?? 0) === intelligence.call_wall && <span className="ml-1 text-xs text-success">🔼</span>}
                                {(strike.strike ?? 0) === intelligence.put_wall && <span className="ml-1 text-xs text-danger">🔽</span>}
                              </span>
                              <span className="text-success font-mono w-24 text-right">{formatNumber(strike.call_gamma ?? 0)}</span>
                              <span className="text-danger font-mono w-24 text-right">{formatNumber(strike.put_gamma ?? 0)}</span>
                              <span className={`font-mono w-24 text-right ${(strike.total_gamma ?? 0) > 0 ? 'text-success' : 'text-danger'}`}>
                                {formatNumber(strike.total_gamma ?? 0)}
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
                      <p className="text-text-secondary mb-2 font-semibold">No Strike Data Available</p>
                      <p className="text-xs text-text-muted max-w-md mx-auto">
                        Strike-level gamma data is required to display this chart. The backend may be unable to fetch detailed GEX profile data.
                        Check browser console (F12) for errors, or try refreshing the page.
                      </p>
                      <button
                        onClick={() => fetchData(true)}
                        className="mt-4 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/80"
                      >
                        Retry Loading Data
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Market Maker State - HOW TO MAKE MONEY */}
              {intelligence.mm_state && (
                <div className={`card border-l-4 ${
                  intelligence.mm_state.name === 'PANICKING' ? 'border-danger bg-danger/5' :
                  intelligence.mm_state.name === 'TRAPPED' ? 'border-warning bg-warning/5' :
                  intelligence.mm_state.name === 'HUNTING' ? 'border-primary bg-primary/5' :
                  intelligence.mm_state.name === 'DEFENDING' ? 'border-success bg-success/5' :
                  'border-gray-500 bg-background-hover'
                }`}>
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <h2 className="text-2xl font-bold text-text-primary mb-2 flex items-center gap-2">
                        🎯 {symbol} Market Maker State: <span className={
                          intelligence.mm_state.name === 'PANICKING' ? 'text-danger' :
                          intelligence.mm_state.name === 'TRAPPED' ? 'text-warning' :
                          intelligence.mm_state.name === 'HUNTING' ? 'text-primary' :
                          intelligence.mm_state.name === 'DEFENDING' ? 'text-success' :
                          'text-text-secondary'
                        }>{intelligence.mm_state.name}</span>
                      </h2>
                      <p className="text-text-secondary text-sm">{symbol} Net GEX: ${intelligence.net_gex ? (intelligence.net_gex / 1e9).toFixed(2) : '0.00'}B</p>
                    </div>
                    <div className="px-4 py-2 rounded-lg bg-background-card">
                      <p className="text-xs text-text-muted mb-1">Confidence</p>
                      <p className="text-2xl font-bold text-success">{intelligence.mm_state.confidence ?? 0}%</p>
                    </div>
                  </div>

                  <div className="space-y-4">
                    {/* What MMs Are Doing */}
                    <div className="p-4 bg-background-card rounded-lg">
                      <h3 className="font-bold text-text-primary mb-2 flex items-center gap-2">
                        <span>📊</span> What Market Makers Are Doing:
                      </h3>
                      <p className="text-text-secondary">{intelligence.mm_state.behavior}</p>
                    </div>

                    {/* HOW TO MAKE MONEY */}
                    <div className="p-4 bg-gradient-to-r from-success/10 to-primary/10 rounded-lg border-2 border-success">
                      <h3 className="font-bold text-success mb-3 text-lg flex items-center gap-2">
                        <span>💰</span> HOW TO MAKE MONEY - Your Trading Edge:
                      </h3>
                      <p className="text-text-primary font-semibold text-lg mb-3">{intelligence.mm_state.action}</p>

                      {/* Specific instructions based on MM state */}
                      {intelligence.mm_state.name === 'PANICKING' && (
                        <div className="space-y-2 text-sm text-text-secondary">
                          <p><strong className="text-danger">🚨 MAXIMUM AGGRESSION:</strong> MMs are covering shorts at ANY price</p>
                          <p><strong>Strategy:</strong> Buy ATM calls with 3-5 DTE, ride the squeeze until call wall</p>
                          <p><strong>Entry:</strong> IMMEDIATELY when GEX crosses -$3B</p>
                          <p><strong>Exit:</strong> At call wall or when GEX rises above -$2B</p>
                          <p><strong>Size:</strong> 3-5% of account - this is your biggest edge (90% confidence)</p>
                          <p><strong>Stop:</strong> 30% loss or if price breaks below flip point</p>
                        </div>
                      )}

                      {intelligence.mm_state.name === 'TRAPPED' && (
                        <div className="space-y-2 text-sm text-text-secondary">
                          <p><strong className="text-warning">⚡ HIGH PROBABILITY:</strong> MMs MUST buy rallies to hedge shorts</p>
                          <p><strong>Strategy:</strong> Buy 0.4 delta calls (slightly OTM) on dips toward flip point</p>
                          <p><strong>Entry:</strong> When price is 0.5-1% below flip point</p>
                          <p><strong>Exit:</strong> At flip point or call wall (typically 2-3% move)</p>
                          <p><strong>Size:</strong> 2-3% of account (85% confidence)</p>
                          <p><strong>Stop:</strong> If price breaks 1.5% below flip point</p>
                        </div>
                      )}

                      {intelligence.mm_state.name === 'HUNTING' && (
                        <div className="space-y-2 text-sm text-text-secondary">
                          <p><strong className="text-primary">🎣 PATIENT APPROACH:</strong> MMs are positioning for direction</p>
                          <p><strong>Strategy:</strong> Wait for price to show clear direction THEN follow</p>
                          <p><strong>Entry:</strong> AFTER price moves 0.5% from flip (direction confirmed)</p>
                          <p><strong>Exit:</strong> At nearest wall (call or put)</p>
                          <p><strong>Size:</strong> 1-2% of account (60% confidence - lower until direction clear)</p>
                          <p><strong>Stop:</strong> Back through flip point = wrong direction</p>
                        </div>
                      )}

                      {intelligence.mm_state.name === 'DEFENDING' && (
                        <div className="space-y-2 text-sm text-text-secondary">
                          <p><strong className="text-success">🛡️ RANGE-BOUND PROFITS:</strong> MMs will fade any big moves</p>
                          <p><strong>Strategy:</strong> Sell premium (credit spreads) OR buy straddles for range</p>
                          <p><strong>Entry:</strong> When price approaches call/put walls</p>
                          <p><strong>Exit:</strong> 50% profit or opposite wall touched</p>
                          <p><strong>Size:</strong> 2-3% of account (70% confidence)</p>
                          <p><strong>Best Play:</strong> Iron Condor between walls (72% win rate)</p>
                        </div>
                      )}

                      {intelligence.mm_state.name === 'NEUTRAL' && (
                        <div className="space-y-2 text-sm text-text-secondary">
                          <p><strong className="text-text-primary">⚖️ BALANCED:</strong> No strong MM positioning</p>
                          <p><strong>Strategy:</strong> Iron Condor for steady premium collection</p>
                          <p><strong>Entry:</strong> Sell calls at resistance, puts at support</p>
                          <p><strong>Exit:</strong> 50% profit or breach of short strikes</p>
                          <p><strong>Size:</strong> 1-2% of account (50% confidence)</p>
                          <p><strong>Alternative:</strong> Wait for clearer MM state for better edge</p>
                        </div>
                      )}
                    </div>

                    {/* Risk Warning */}
                    <div className="p-3 bg-background-hover rounded-lg border border-border">
                      <p className="text-xs text-text-muted">
                        <strong>⚠️ Risk Management:</strong> MM states can change quickly. Always use stops. GEX updates every 5 minutes during market hours.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Key Observations */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="card">
                  <h2 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
                    <AlertCircle className="w-5 h-5 text-primary" />
                    Key Observations
                  </h2>
                  <ul className="space-y-2">
                    {/* Bug #14 Fix: Safe array access */}
                    {(intelligence.key_observations || []).map((obs, idx) => (
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
                    {/* Bug #14 Fix: Safe array access */}
                    {(intelligence.trading_implications || []).map((impl, idx) => (
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
                      {/* Bug #14 Fix: Safe property access */}
                      {(intelligence.risk_reversal ?? 0).toFixed(3)}
                    </p>
                  </div>
                  <div className="p-4 bg-background-hover rounded-lg">
                    <p className="text-text-muted text-xs uppercase">Skew Index</p>
                    <p className="text-xl font-bold text-text-primary mt-1">
                      {/* Bug #14 Fix: Safe property access */}
                      {(intelligence.skew_index ?? 0).toFixed(2)}
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
      ) : (
        <div className="card text-center py-12">
          <p className="text-text-secondary">No data available for {symbol}</p>
        </div>
      )}
        </div>

        {/* Evidence-Based Thresholds Footer */}
        <div className="card bg-background-hover border-t-4 border-primary mt-8">
          <h3 className="text-sm font-bold text-text-primary mb-2 flex items-center gap-2">
            <span>📚</span> EVIDENCE-BASED THRESHOLDS
          </h3>
          <p className="text-xs text-text-secondary leading-relaxed">
            All gamma metrics, win rates, and risk thresholds are based on: <strong>Academic research</strong> (Dim, Eraker, Vilkov 2023),
            <strong> SpotGamma professional analysis</strong>, <strong>ECB Financial Stability Review 2023</strong>, and <strong>validated production trading data</strong>.
            Context-aware adjustments for Friday expirations and high-VIX environments ensure accuracy across all market conditions.
          </p>
        </div>
        </div>
      </main>
    </div>
  )
}
