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
import ProbabilityAnalysis from '@/components/ProbabilityAnalysis'

type TabType = 'overview' | 'probabilities' | 'impact' | 'historical'

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

interface HistoricalData {
  date: string
  price: number
  net_gex: number
  flip_point: number
  implied_volatility: number
  put_call_ratio: number
}

export default function GammaIntelligence() {
  const router = useRouter()
  const [activeTab, setActiveTab] = useState<TabType>('overview')
  const [symbol, setSymbol] = useState('SPY')
  const [vix, setVix] = useState<number>(20)
  const [intelligence, setIntelligence] = useState<GammaIntelligence | null>(null)
  const [loading, setLoading] = useState(true)  // Bug #1 Fix: Start with loading=true
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [historicalData, setHistoricalData] = useState<HistoricalData[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [probabilityData, setProbabilityData] = useState<any | null>(null)
  const [loadingProbabilities, setLoadingProbabilities] = useState(false)
  const [retryCount, setRetryCount] = useState(0)  // Bug #10 Fix: Track retries
  const { data: wsData, isConnected } = useWebSocket(symbol)

  // Position simulator state
  const [simStrike, setSimStrike] = useState(450)
  const [simQuantity, setSimQuantity] = useState(10)
  const [simOptionType, setSimOptionType] = useState<'call' | 'put'>('call')
  const [simResults, setSimResults] = useState<{
    positionGamma: number
    deltaImpact: number
    thetaDecay: number
  } | null>(null)

  // Calculate position impact based on inputs
  const calculatePositionImpact = useCallback(() => {
    if (!intelligence || !intelligence.strikes || intelligence.strikes.length === 0) {
      setSimResults(null)
      return
    }

    // Find closest strike in the data
    const closestStrike = intelligence.strikes.reduce((prev, curr) =>
      Math.abs(curr.strike - simStrike) < Math.abs(prev.strike - simStrike) ? curr : prev
    )

    // Get gamma for the option type
    const gammaPerContract = simOptionType === 'call'
      ? closestStrike.call_gamma
      : closestStrike.put_gamma

    // Calculate position gamma (gamma * contracts * 100 shares per contract)
    const positionGamma = gammaPerContract * simQuantity * 100

    // Calculate approximate delta based on moneyness
    // ATM options have ~0.5 delta, ITM closer to 1, OTM closer to 0
    const moneyness = (intelligence.spot_price - simStrike) / intelligence.spot_price
    let baseDelta: number
    if (simOptionType === 'call') {
      // Call delta: ITM > 0.5, ATM = 0.5, OTM < 0.5
      baseDelta = 0.5 + (moneyness * 2) // Rough approximation
      baseDelta = Math.max(0.05, Math.min(0.95, baseDelta))
    } else {
      // Put delta: negative, ITM closer to -1, OTM closer to 0
      baseDelta = -0.5 + (moneyness * 2)
      baseDelta = Math.max(-0.95, Math.min(-0.05, baseDelta))
    }
    const deltaImpact = baseDelta * simQuantity

    // Calculate approximate theta decay
    // Theta is typically -0.01 to -0.05 per contract per day for ATM options
    // Higher for ATM, lower for deep ITM/OTM
    const atmDistance = Math.abs(simStrike - intelligence.spot_price) / intelligence.spot_price
    const thetaMultiplier = Math.max(0.3, 1 - atmDistance * 5) // ATM = 1, 20% OTM = 0.3
    const baseTheta = -0.03 * thetaMultiplier * intelligence.spot_price // Rough theta estimate
    const thetaDecay = baseTheta * simQuantity

    setSimResults({
      positionGamma,
      deltaImpact,
      thetaDecay
    })
  }, [intelligence, simStrike, simQuantity, simOptionType])

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

      const response = await apiClient.getGammaIntelligence(symbol, vix)

      // Check if request was cancelled
      if (signal?.aborted) {
        logger.info('Request cancelled')
        return
      }

      logger.info('API Response:', response.data)
      logger.info('Has strikes?', response.data.data?.strikes?.length || 0)

      const data = response.data.data

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

  // Fetch historical data
  const fetchHistoricalData = useCallback(async () => {
    try {
      setLoadingHistory(true)
      logger.info('=== FETCHING HISTORICAL DATA ===')
      logger.info('Symbol:', symbol)

      const response = await apiClient.getGammaHistory(symbol, 30)
      const data = response.data.data

      logger.info('Historical data received:', {
        count: data?.length || 0,
        sample: data?.[0] || null
      })

      setHistoricalData(data || [])
    } catch (error: any) {
      logger.error('Error fetching historical data:', error)
      logger.error('Error details:', error.response?.data || error.message)
    } finally {
      setLoadingHistory(false)
    }
  }, [symbol])

  // Fetch probability data
  const fetchProbabilityData = useCallback(async () => {
    try {
      setLoadingProbabilities(true)
      logger.info('=== FETCHING PROBABILITY DATA ===')
      logger.info('Symbol:', symbol, 'VIX:', vix)

      const response = await apiClient.getGammaProbabilities(symbol, vix)

      // Validate response structure
      if (!response?.data) {
        setError('Invalid response from probability API')
        setProbabilityData(null)
        return
      }

      const data = response.data.data

      // Validate required fields
      if (!data) {
        setError('No probability data available for current conditions')
        setProbabilityData(null)
        return
      }

      logger.info('Probability data received:', {
        has_setup: !!data?.best_setup,
        strike_count: data?.strike_probabilities?.length || 0,
        has_position_sizing: !!data?.position_sizing,
        has_risk_analysis: !!data?.risk_analysis
      })

      // Check if there's no trading edge
      if (!data.best_setup) {
        logger.warn('No trading setup available - insufficient edge in current conditions')
        // Still set the data so components can show "no edge" message
      }

      setProbabilityData(data)
      setError(null) // Clear any previous errors
    } catch (error: any) {
      logger.error('Error fetching probability data:', error)
      logger.error('Error details:', error.response?.data || error.message)

      // Set user-friendly error message
      if (error.status === 422) {
        setError('Invalid market data - unable to calculate probabilities')
      } else if (error.status === 404) {
        setError(`No probability data available for ${symbol}`)
      } else if (error.type === 'network') {
        setError('Network error - please check your connection')
      } else if (error.type === 'timeout') {
        setError('Request timed out - please try again')
      } else {
        setError(error.message || 'Failed to load probability data')
      }

      setProbabilityData(null)
    } finally {
      setLoadingProbabilities(false)
    }
  }, [symbol, vix])

  // Bug #2 Fix: Use ref for fetchData to avoid dependency issues
  const fetchDataRef = useRef(fetchData)
  fetchDataRef.current = fetchData

  useEffect(() => {
    // Create AbortController for request cancellation
    const controller = new AbortController()

    // Always fetch fresh data when symbol or vix changes
    // Bug #2 Fix: Use ref to avoid including fetchData in deps
    fetchDataRef.current(true, controller.signal)

    // Cleanup: cancel request if component unmounts or deps change
    return () => {
      controller.abort()
    }
  }, [symbol, vix])  // Bug #2 Fix: Removed fetchData from deps

  // Update simulator strike to spot price when intelligence loads
  useEffect(() => {
    if (intelligence?.spot_price && simStrike === 450) {
      setSimStrike(Math.round(intelligence.spot_price))
    }
  }, [intelligence?.spot_price, simStrike])

  // Bug #9 Fix: Use refs for fetch functions to avoid unnecessary re-fetches
  const fetchHistoricalDataRef = useRef(fetchHistoricalData)
  fetchHistoricalDataRef.current = fetchHistoricalData
  const fetchProbabilityDataRef = useRef(fetchProbabilityData)
  fetchProbabilityDataRef.current = fetchProbabilityData

  useEffect(() => {
    // Fetch historical data when switching to historical tab
    if (activeTab === 'historical' && historicalData.length === 0) {
      fetchHistoricalDataRef.current()
    }
  }, [activeTab, historicalData.length])  // Bug #9 Fix: Removed fetchHistoricalData from deps

  useEffect(() => {
    // Fetch probability data when switching to probabilities tab
    if (activeTab === 'probabilities' && !probabilityData) {
      fetchProbabilityDataRef.current()
    }
  }, [activeTab, probabilityData])  // Bug #9 Fix: Removed fetchProbabilityData from deps

  const handleRefresh = () => {
    fetchData(true)
    if (activeTab === 'historical') {
      fetchHistoricalData()
    }
    if (activeTab === 'probabilities') {
      fetchProbabilityData()
    }
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

  const tabs = [
    { id: 'overview' as TabType, label: 'Overview', icon: Zap },
    { id: 'probabilities' as TabType, label: 'Probabilities & Edge', icon: Target },
    { id: 'impact' as TabType, label: 'Position Impact', icon: BarChart3 },
    { id: 'historical' as TabType, label: 'Historical Analysis', icon: Clock }
  ]

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
                      <p className="text-2xl font-bold text-success">{intelligence.mm_state.confidence}%</p>
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
          )}

          {/* Probabilities & Edge Tab */}
          {activeTab === 'probabilities' && (
            <div className="space-y-6">
              {loadingProbabilities ? (
                <div className="grid grid-cols-1 gap-6">
                  {[...Array(4)].map((_, i) => (
                    <div key={i} className="card h-64 skeleton" />
                  ))}
                </div>
              ) : probabilityData && intelligence ? (
                <ProbabilityAnalysis
                  data={probabilityData}
                  symbol={symbol}
                  spotPrice={intelligence.spot_price}
                />
              ) : (
                <div className="card text-center py-12">
                  <AlertCircle className="w-16 h-16 text-text-muted mx-auto mb-4" />
                  <h3 className="text-xl font-semibold text-text-primary mb-2">No Probability Data Available</h3>
                  <p className="text-text-secondary mb-4">Unable to load probability analysis</p>
                  <button
                    onClick={fetchProbabilityData}
                    className="px-6 py-2 bg-primary hover:bg-primary/80 text-white rounded-lg font-medium transition-all"
                  >
                    Retry
                  </button>
                </div>
              )}
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
                    <button onClick={calculatePositionImpact} className="btn-primary w-full">Calculate Impact</button>
                  </div>
                </div>

                {/* Simulated Results */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 bg-background-hover rounded-lg">
                  <div>
                    <p className="text-text-muted text-xs uppercase mb-1">Position Gamma</p>
                    <p className={`text-xl font-bold ${simResults && simResults.positionGamma >= 0 ? 'text-success' : 'text-danger'}`}>
                      {simResults ? (simResults.positionGamma >= 0 ? '+' : '') + simResults.positionGamma.toFixed(2) : 'Click Calculate'}
                    </p>
                  </div>
                  <div>
                    <p className="text-text-muted text-xs uppercase mb-1">Delta Impact</p>
                    <p className={`text-xl font-bold ${simResults && simResults.deltaImpact >= 0 ? 'text-success' : 'text-danger'}`}>
                      {simResults ? (simResults.deltaImpact >= 0 ? '+' : '') + simResults.deltaImpact.toFixed(2) : 'Click Calculate'}
                    </p>
                  </div>
                  <div>
                    <p className="text-text-muted text-xs uppercase mb-1">Theta Decay</p>
                    <p className="text-xl font-bold text-danger">
                      {simResults ? '$' + simResults.thetaDecay.toFixed(2) + '/day' : 'Click Calculate'}
                    </p>
                  </div>
                </div>
              </div>

              {/* Impact Chart */}
              <div className="card">
                <div className="mb-4">
                  <h2 className="text-xl font-semibold text-text-primary mb-2">Exposure Impact Over Price Range</h2>
                  <p className="text-sm text-text-secondary">💰 HOW TO MAKE MONEY: Identify where net gamma changes sign. Positive gamma (green) = range-bound, sell premium. Negative gamma (red) = trending, buy directional options. Use flip point as key decision level.</p>
                </div>
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
                        {/* Bug #14 Fix: Safe property access */}
                        <p className="text-xl font-bold text-primary">${(intelligence.spot_price ?? 0).toFixed(2)}</p>
                      </div>
                      <div>
                        <p className="text-text-muted text-xs uppercase mb-1">Flip Point</p>
                        <p className="text-xl font-bold text-warning">${intelligence.flip_point?.toFixed(2) || 'N/A'}</p>
                      </div>
                      <div>
                        <p className="text-text-muted text-xs uppercase mb-1">Distance to Flip</p>
                        {/* Bug #14 Fix: Safe division (prevent divide by zero) */}
                        <p className={`text-xl font-bold ${(intelligence.flip_point || 0) > (intelligence.spot_price || 0) ? 'text-success' : 'text-danger'}`}>
                          {intelligence.flip_point && intelligence.spot_price ? ((intelligence.flip_point - intelligence.spot_price) / intelligence.spot_price * 100).toFixed(2) : 'N/A'}%
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

              {/* Risk Analysis section removed - was showing placeholder demo values */}
            </div>
          )}

          {/* Historical Analysis Tab */}
          {activeTab === 'historical' && (
            <div className="space-y-6">
              <div className="card">
                <div className="mb-4">
                  <h2 className="text-xl font-semibold text-text-primary mb-2">{symbol} Gamma Exposure Trends (30 Days)</h2>
                  <p className="text-sm text-text-secondary">💰 HOW TO MAKE MONEY: Identify trend changes in GEX. When GEX flips from positive to negative = buy calls on dips. When GEX flips from negative to positive = sell premium. Rising IV = buy straddles, falling IV = sell spreads.</p>
                </div>
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
