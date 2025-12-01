'use client'

import { logger } from '@/lib/logger'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import LoadingWithTips from '@/components/LoadingWithTips'
import GEXProfileChart from '@/components/GEXProfileChartPlotly'
import { apiClient } from '@/lib/api'
import { IntelligentCache, StaggeredLoader, RateLimiter } from '@/lib/intelligentCache'
import {
  TrendingUp,
  TrendingDown,
  Activity,
  AlertTriangle,
  Plus,
  X,
  ChevronDown,
  ChevronUp,
  Zap,
  Target,
  Brain,
  BarChart3,
  DollarSign,
  RefreshCw,
  Clock
} from 'lucide-react'

// Default tickers to load - START WITH JUST SPY to avoid rate limits
// Users can manually add more tickers one at a time
const DEFAULT_TICKERS = ['SPY']

interface GEXLevel {
  strike: number
  call_gex: number
  put_gex: number
  total_gex: number
}

interface TickerData {
  symbol: string
  spot_price: number
  net_gex: number
  flip_point: number
  call_wall: number
  put_wall: number
  vix: number
  mm_state: string
  data_date?: string  // When the market data was collected
  psychology?: {
    fomo_level: number
    fear_level: number
    state: string
    rsi: number
  }
  probability?: {
    eod: ProbabilityData
    next_day: ProbabilityData
  }
  rsi?: {
    '5m': number | null
    '15m': number | null
    '1h': number | null
    '4h': number | null
    '1d': number | null
  }
}

interface ProbabilityData {
  confidence: string
  ranges: Array<{
    range: string
    probability: number
  }>
  supporting_factors: string[]
  trading_insights: Array<{
    setup: string
    action: string
    why: string
    risk: string
    expected: string
    color: string
  }>
}

export default function GEXAnalysisPage() {
  const [tickers, setTickers] = useState<string[]>(DEFAULT_TICKERS)
  const [tickerData, setTickerData] = useState<Record<string, TickerData>>({})
  const [gexLevels, setGexLevels] = useState<Record<string, GEXLevel[]>>({})
  const [loading, setLoading] = useState(true)
  const [loadingProgress, setLoadingProgress] = useState(0)
  const [loadingTickers, setLoadingTickers] = useState<Set<string>>(new Set())
  const [newTicker, setNewTicker] = useState('')
  const [expandedTickers, setExpandedTickers] = useState<Set<string>>(new Set(['SPY'])) // Auto-expand SPY to show GEX chart
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [cacheInfo, setCacheInfo] = useState<Record<string, string>>({})
  // Track loading state and errors for GEX levels specifically
  const [loadingGexLevels, setLoadingGexLevels] = useState<Set<string>>(new Set())
  const [gexLevelsErrors, setGexLevelsErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    loadAllTickers()
  }, [tickers])

  // Auto-load GEX levels for tickers that are expanded on page load (like SPY)
  useEffect(() => {
    if (loading) return // Don't load GEX levels while still loading ticker data

    expandedTickers.forEach((ticker) => {
      // Only load if we have ticker data but don't have GEX levels yet
      if (tickerData[ticker] && !gexLevels[ticker] && !loadingGexLevels.has(ticker) && !gexLevelsErrors[ticker]) {
        logger.info(`Auto-loading GEX levels for expanded ticker: ${ticker}`)
        loadGexLevels(ticker)
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tickerData, expandedTickers, loading]) // Run when ticker data loads or expansion changes

  const loadAllTickers = async () => {
    setLoading(true)
    setError(null)
    setLoadingProgress(0)

    // First, load cached data immediately for instant display
    const cachedData: Record<string, TickerData> = {}
    const tickersToLoad: string[] = []

    tickers.forEach((ticker) => {
      const cached = IntelligentCache.get<TickerData>(ticker)
      if (cached) {
        cachedData[ticker] = cached
      } else {
        tickersToLoad.push(ticker)
      }
    })

    // Show cached data immediately
    if (Object.keys(cachedData).length > 0) {
      setTickerData(cachedData)
      logger.info(`Loaded ${Object.keys(cachedData).length} tickers from cache`)

      // DON'T auto-fetch GEX levels - only load when user expands chart
      // This prevents hitting rate limits (gammaOI has 2 calls/min during trading hours)
    }

    // Mark tickers that need loading
    setLoadingTickers(new Set(tickersToLoad))

    // If all data is cached, we're done
    if (tickersToLoad.length === 0) {
      setLoading(false)
      const newCacheInfo: Record<string, string> = {}
      tickers.forEach((ticker) => {
        newCacheInfo[ticker] = IntelligentCache.getAgeString(ticker)
      })
      setCacheInfo(newCacheInfo)
      return
    }

    try {
      // Load fresh data with rate limiting using StaggeredLoader
      const loadFn = async (ticker: string) => {
        const response = await apiClient.getGEX(ticker)
        if (response.data.success) {
          return response.data.data
        }
        throw new Error(`Failed to load ${ticker}`)
      }

      // Use StaggeredLoader for intelligent rate limiting
      // CONSERVATIVE: 5 second delay = max 12 calls/min (well under 20/min API limit)
      const freshResults = await StaggeredLoader.loadWithDelay(
        tickersToLoad,
        loadFn,
        5000 // 5 seconds between calls to avoid backend circuit breaker
      )

      // Update state with fresh data
      setTickerData((prev) => ({ ...prev, ...freshResults }))
      setLoadingProgress(Object.keys(freshResults).length)

      // Update cache info
      const newCacheInfo: Record<string, string> = {}
      tickers.forEach((ticker) => {
        newCacheInfo[ticker] = IntelligentCache.getAgeString(ticker)
      })
      setCacheInfo(newCacheInfo)

      logger.info(`Loaded ${Object.keys(freshResults).length} fresh tickers from API`)

      // DON'T auto-fetch GEX levels - only load when user expands chart
      // This prevents hitting rate limits (gammaOI has 2 calls/min during trading hours)
    } catch (err) {
      logger.error('Failed to load tickers:', err)
      setError('Some tickers failed to load. Using cached data where available.')
    } finally {
      setLoading(false)
      setLoadingProgress(0)
      setLoadingTickers(new Set())
    }
  }

  const refreshTicker = async (ticker: string) => {
    setRefreshing(true)
    setLoadingTickers((prev) => new Set(prev).add(ticker))

    try {
      // Clear cache for this ticker
      IntelligentCache.remove(ticker)

      // Check rate limit
      if (!RateLimiter.canMakeCall()) {
        const waitTime = Math.ceil(RateLimiter.getTimeUntilNextCall() / 1000)
        setError(`Rate limit: please wait ${waitTime}s`)
        setRefreshing(false)
        setLoadingTickers((prev) => {
          const next = new Set(prev)
          next.delete(ticker)
          return next
        })
        return
      }

      RateLimiter.recordCall()
      const response = await apiClient.getGEX(ticker)

      if (response.data.success) {
        setTickerData((prev) => ({
          ...prev,
          [ticker]: response.data.data,
        }))

        IntelligentCache.set(ticker, response.data.data, ticker)

        setCacheInfo((prev) => ({
          ...prev,
          [ticker]: 'Just now',
        }))
      }
    } catch (err) {
      logger.error(`Failed to refresh ${ticker}:`, err)
      setError(`Failed to refresh ${ticker}`)
    } finally {
      setRefreshing(false)
      setLoadingTickers((prev) => {
        const next = new Set(prev)
        next.delete(ticker)
        return next
      })
    }
  }

  const addTicker = () => {
    const ticker = newTicker.trim().toUpperCase()
    if (ticker && !tickers.includes(ticker)) {
      setTickers([...tickers, ticker])
      setExpandedTickers(new Set([...expandedTickers, ticker]))
      setNewTicker('')
    }
  }

  const removeTicker = (ticker: string) => {
    setTickers(tickers.filter((t) => t !== ticker))
    setExpandedTickers(new Set([...expandedTickers].filter((t) => t !== ticker)))
    const newData = { ...tickerData }
    delete newData[ticker]
    setTickerData(newData)
  }

  const loadGexLevels = async (ticker: string) => {
    // Mark as loading
    setLoadingGexLevels(prev => new Set(prev).add(ticker))
    // Clear any previous error for this ticker
    setGexLevelsErrors(prev => {
      const next = { ...prev }
      delete next[ticker]
      return next
    })

    try {
      // Try the dedicated levels endpoint first
      const response = await apiClient.getGEXLevels(ticker)
      if (response.data.success && response.data.data) {
        const levels = response.data.data.levels || []

        // If levels endpoint returns data, use it
        if (levels.length > 0) {
          setGexLevels(prev => ({
            ...prev,
            [ticker]: levels
          }))
          return
        }

        // If levels is empty (rate limited), fall back to gamma intelligence endpoint
        logger.info(`GEX levels empty for ${ticker}, trying gamma intelligence endpoint as fallback...`)
      }

      // FALLBACK: Try gamma intelligence endpoint which has the same strike data
      try {
        const gammaResponse = await apiClient.getGammaIntelligence(ticker)
        if (gammaResponse.data.success && gammaResponse.data.data?.strikes) {
          const strikes = gammaResponse.data.data.strikes

          // Transform gamma strikes to GEX levels format
          // Gamma uses: call_gamma, put_gamma, total_gamma
          // GEX chart expects: call_gex, put_gex, total_gex
          const transformedLevels = strikes.map((strike: any) => ({
            strike: strike.strike,
            call_gex: strike.call_gamma,  // Gamma and GEX are the same data
            put_gex: strike.put_gamma,
            total_gex: strike.total_gamma
          }))

          logger.info(`Loaded ${transformedLevels.length} strikes from gamma intelligence for ${ticker}`)
          setGexLevels(prev => ({
            ...prev,
            [ticker]: transformedLevels
          }))
          return
        }
      } catch (gammaErr) {
        logger.error(`Gamma intelligence fallback also failed for ${ticker}:`, gammaErr)
      }

      // If both endpoints fail or return empty, show error
      setGexLevelsErrors(prev => ({
        ...prev,
        [ticker]: 'No GEX level data available for this ticker. The gammaOI API may be rate limited.'
      }))

    } catch (err: any) {
      logger.error(`Failed to load GEX levels for ${ticker}:`, err)

      // Still try the gamma intelligence fallback even if levels endpoint threw an error
      try {
        const gammaResponse = await apiClient.getGammaIntelligence(ticker)
        if (gammaResponse.data.success && gammaResponse.data.data?.strikes) {
          const strikes = gammaResponse.data.data.strikes
          const transformedLevels = strikes.map((strike: any) => ({
            strike: strike.strike,
            call_gex: strike.call_gamma,
            put_gex: strike.put_gamma,
            total_gex: strike.total_gamma
          }))

          logger.info(`Loaded ${transformedLevels.length} strikes from gamma intelligence fallback for ${ticker}`)
          setGexLevels(prev => ({
            ...prev,
            [ticker]: transformedLevels
          }))
          return
        }
      } catch (gammaErr) {
        logger.error(`Gamma intelligence fallback also failed for ${ticker}:`, gammaErr)
      }

      const errorMessage = err.response?.data?.detail || err.message || 'Failed to load GEX profile chart'
      setGexLevelsErrors(prev => ({
        ...prev,
        [ticker]: errorMessage
      }))
    } finally {
      // Remove from loading set
      setLoadingGexLevels(prev => {
        const next = new Set(prev)
        next.delete(ticker)
        return next
      })
    }
  }

  const toggleExpanded = async (ticker: string) => {
    const newExpanded = new Set(expandedTickers)
    if (newExpanded.has(ticker)) {
      newExpanded.delete(ticker)
    } else {
      newExpanded.add(ticker)

      // Fetch GEX levels if not already loaded
      if (!gexLevels[ticker]) {
        await loadGexLevels(ticker)
      }
    }
    setExpandedTickers(newExpanded)
  }

  const formatCurrency = (value: number) => {
    const absValue = Math.abs(value)
    if (absValue >= 1e9) {
      return `${(value / 1e9).toFixed(1)}B`
    }
    if (absValue >= 1e6) {
      return `${(value / 1e6).toFixed(0)}M`
    }
    return value.toFixed(2)
  }

  const getMMStateColor = (state: string) => {
    const colors: Record<string, string> = {
      'DEFENDING': 'text-warning',
      'SQUEEZING': 'text-primary',
      'PANICKING': 'text-danger',
      'BREAKDOWN': 'text-danger',
      'NEUTRAL': 'text-text-secondary'
    }
    return colors[state] || 'text-text-secondary'
  }

  const getPsychologyColor = (level: number) => {
    if (level > 70) return 'text-danger'
    if (level > 55) return 'text-warning'
    return 'text-success'
  }

  const getConfidenceColor = (confidence: string) => {
    if (confidence === 'HIGH') return 'text-success'
    if (confidence === 'MEDIUM') return 'text-warning'
    return 'text-danger'
  }

  const getInsightColor = (color: string) => {
    if (color === 'success') return 'bg-success/10 border-success text-success'
    if (color === 'warning') return 'bg-warning/10 border-warning text-warning'
    if (color === 'danger') return 'bg-danger/10 border-danger text-danger'
    return 'bg-background-hover border-gray-700 text-text-primary'
  }

  return (
    <div className="min-h-screen">
      <Navigation />

      <main className="pt-16 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-text-primary flex items-center space-x-3">
              <TrendingUp className="w-8 h-8 text-primary" />
              <span>GEX Analysis - Multi-Ticker View</span>
            </h1>
            <p className="text-text-secondary mt-2">
              Comprehensive GEX analysis with EOD & next-day probability predictions for profitable trading insights
            </p>
          </div>

          {/* Rate Limit Warning */}
          <div className="bg-warning/10 border border-warning rounded-lg p-4 mb-6">
            <div className="flex items-start space-x-3">
              <AlertTriangle className="w-5 h-5 text-warning flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <h3 className="text-warning font-semibold mb-2">⚠️ API Rate Limit Protection</h3>
                <p className="text-text-secondary text-sm mb-3">
                  To avoid hitting API limits, we load data with <strong>5-second delays</strong> between tickers.
                  This means each new ticker takes ~5 seconds to load.
                </p>
                <div className="bg-background-deep rounded-lg p-3 border border-gray-700">
                  <p className="text-text-primary text-sm font-semibold mb-2">💡 Recommended Workflow:</p>
                  <ul className="text-text-secondary text-sm space-y-1">
                    <li>• Start with SPY (already loaded)</li>
                    <li>• Add 1-2 tickers at a time</li>
                    <li>• Wait for data to load before adding more</li>
                    <li>• Cached data persists - refreshing the page is instant!</li>
                  </ul>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <span className="text-text-muted text-xs">Popular tickers:</span>
                  {['QQQ', 'IWM', 'NVDA', 'AAPL', 'TSLA', 'MSFT', 'AMZN', 'META'].map(ticker => (
                    <button
                      key={ticker}
                      onClick={() => {
                        if (!tickers.includes(ticker)) {
                          setNewTicker(ticker)
                        }
                      }}
                      className="px-2 py-1 bg-background-hover border border-gray-700 rounded text-xs text-text-primary hover:border-primary transition-colors"
                    >
                      {ticker}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Add Ticker Input */}
          <div className="card mb-8">
            <div className="flex items-center space-x-4">
              <input
                type="text"
                value={newTicker}
                onChange={(e) => setNewTicker(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addTicker()}
                placeholder="Add ticker (e.g., QQQ, NVDA, AAPL)"
                className="flex-1 px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary focus:outline-none focus:border-primary"
              />
              <button
                onClick={addTicker}
                disabled={loading && loadingTickers.size > 0}
                className="btn-primary flex items-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Plus className="w-5 h-5" />
                <span>Add Ticker</span>
              </button>
            </div>
            {loading && loadingTickers.size > 0 && (
              <div className="mt-3 text-sm text-warning">
                ⏱️ Please wait - loading current ticker(s) with 5-second delays to avoid rate limits...
              </div>
            )}
          </div>

          {/* Error Message */}
          {error && (
            <div className="bg-danger/10 border border-danger rounded-lg p-4 mb-8">
              <div className="flex items-center space-x-2 text-danger">
                <AlertTriangle className="w-5 h-5" />
                <span className="font-semibold">{error}</span>
              </div>
            </div>
          )}

          {/* Loading State with Tips */}
          {loading && loadingTickers.size > 0 && (
            <div className="mb-6">
              <LoadingWithTips
                message={`Loading fresh GEX data for ${loadingTickers.size} ticker${loadingTickers.size > 1 ? 's' : ''}... (Est. ${loadingTickers.size * 5}s)`}
                showProgress={true}
                progress={tickers.length - loadingTickers.size}
                total={tickers.length}
              />
            </div>
          )}

          {/* Ticker Cards */}
          <div className="space-y-6">
            {tickers.map((ticker) => {
              const data = tickerData[ticker]
              const isExpanded = expandedTickers.has(ticker)
              const isLoading = loadingTickers.has(ticker)

              if (!data) {
                return (
                  <div key={ticker} className="card">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <div className="text-text-primary font-semibold">{ticker}</div>
                        {isLoading ? (
                          <div className="flex items-center space-x-2">
                            <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
                            <span className="text-sm text-primary">Loading...</span>
                          </div>
                        ) : (
                          <span className="text-sm text-danger">Failed to load</span>
                        )}
                      </div>
                      <button
                        onClick={() => removeTicker(ticker)}
                        className="text-text-secondary hover:text-danger"
                      >
                        <X className="w-5 h-5" />
                      </button>
                    </div>
                  </div>
                )
              }

              return (
                <div key={ticker} className="card border-2 border-gray-800 hover:border-primary/50 transition-colors">
                  {/* Header */}
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center space-x-4">
                      <h2 className="text-2xl font-bold text-text-primary">{ticker}</h2>
                      <span className="text-xl text-text-secondary font-mono">
                        ${data.spot_price?.toFixed(2) || '---'}
                      </span>
                      <span className={`px-3 py-1 rounded-full text-sm font-semibold ${
                        data.net_gex > 0 ? 'bg-success/20 text-success' : 'bg-danger/20 text-danger'
                      }`}>
                        {data.net_gex > 0 ? 'Positive GEX' : 'Negative GEX'}
                      </span>
                      {isLoading ? (
                        <div className="flex items-center space-x-2 px-3 py-1 rounded-full bg-primary/20">
                          <div className="w-3 h-3 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
                          <span className="text-xs text-primary font-semibold">Refreshing...</span>
                        </div>
                      ) : (
                        <div className="flex items-center space-x-2 px-3 py-1 rounded-full bg-success/10">
                          <span className="text-xs text-success font-semibold">✓ Loaded</span>
                        </div>
                      )}
                      {data.data_date && (
                        <div className="flex items-center space-x-2 text-xs text-primary bg-primary/10 px-2 py-1 rounded">
                          <span>Data: {data.data_date}</span>
                        </div>
                      )}
                      {cacheInfo[ticker] && !isLoading && (
                        <div className="flex items-center space-x-2 text-xs text-text-muted">
                          <Clock className="w-3 h-3" />
                          <span>{cacheInfo[ticker]}</span>
                        </div>
                      )}
                    </div>
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => refreshTicker(ticker)}
                        disabled={refreshing}
                        className="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-background-hover disabled:opacity-50"
                        title="Refresh data"
                      >
                        <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
                      </button>
                      <button
                        onClick={() => toggleExpanded(ticker)}
                        className="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-background-hover"
                      >
                        {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                      </button>
                      <button
                        onClick={() => removeTicker(ticker)}
                        className="p-2 rounded-lg text-text-secondary hover:text-danger hover:bg-background-hover"
                      >
                        <X className="w-5 h-5" />
                      </button>
                    </div>
                  </div>

                  {isExpanded && (
                    <>
                      {/* GEX Profile Chart - Loads on expand to respect rate limits */}
                      <div className="mt-6">
                        {loadingGexLevels.has(ticker) ? (
                          // Loading state
                          <div className="bg-background-deep rounded-lg p-6 border-2 border-primary/20">
                            <div className="flex items-center justify-center space-x-3">
                              <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
                              <p className="text-text-secondary">Loading GEX profile chart for {ticker}...</p>
                            </div>
                          </div>
                        ) : gexLevelsErrors[ticker] ? (
                          // Error state
                          <div className="bg-danger/10 border-2 border-danger rounded-lg p-6">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center space-x-3">
                                <AlertTriangle className="w-8 h-8 text-danger" />
                                <div>
                                  <p className="text-danger font-semibold mb-1">Failed to Load GEX Profile Chart</p>
                                  <p className="text-text-secondary text-sm">{gexLevelsErrors[ticker]}</p>
                                  <p className="text-text-muted text-xs mt-2">Check browser console (F12) for details</p>
                                </div>
                              </div>
                              <button
                                onClick={() => loadGexLevels(ticker)}
                                className="px-4 py-2 bg-primary hover:bg-primary/80 text-white rounded-lg font-medium transition-all flex items-center space-x-2"
                              >
                                <RefreshCw className="w-4 h-4" />
                                <span>Retry</span>
                              </button>
                            </div>
                          </div>
                        ) : gexLevels[ticker] && gexLevels[ticker].length > 0 ? (
                          // Success state - show chart
                          <GEXProfileChart
                            data={gexLevels[ticker]}
                            spotPrice={data.spot_price}
                            flipPoint={data.flip_point}
                            callWall={data.call_wall}
                            putWall={data.put_wall}
                            height={600}
                          />
                        ) : (
                          // Empty state - no data available
                          <div className="bg-background-deep rounded-lg p-6 border-2 border-gray-700">
                            <div className="flex items-center justify-center space-x-3">
                              <BarChart3 className="w-8 h-8 text-text-muted" />
                              <p className="text-text-secondary">No GEX profile data available for {ticker}</p>
                            </div>
                          </div>
                        )}
                      </div>

                      {/* GEX Metrics Grid */}
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                        <div className="bg-background-deep rounded-lg p-4">
                          <div className="flex items-center space-x-2 mb-2">
                            <Activity className="w-4 h-4 text-primary" />
                            <span className="text-text-secondary text-sm">Net GEX</span>
                          </div>
                          <p className={`text-2xl font-bold ${data.net_gex > 0 ? 'text-success' : 'text-danger'}`}>
                            ${formatCurrency(data.net_gex)}
                          </p>
                        </div>

                        <div className="bg-background-deep rounded-lg p-4">
                          <div className="flex items-center space-x-2 mb-2">
                            <Target className="w-4 h-4 text-primary" />
                            <span className="text-text-secondary text-sm">Flip Point</span>
                          </div>
                          <p className="text-2xl font-bold text-text-primary">
                            ${data.flip_point?.toFixed(2) || '---'}
                          </p>
                        </div>

                        <div className="bg-background-deep rounded-lg p-4">
                          <div className="flex items-center space-x-2 mb-2">
                            <TrendingUp className="w-4 h-4 text-success" />
                            <span className="text-text-secondary text-sm">Call Wall</span>
                          </div>
                          <p className="text-2xl font-bold text-success">
                            ${data.call_wall?.toFixed(2) || '---'}
                          </p>
                        </div>

                        <div className="bg-background-deep rounded-lg p-4">
                          <div className="flex items-center space-x-2 mb-2">
                            <TrendingDown className="w-4 h-4 text-danger" />
                            <span className="text-text-secondary text-sm">Put Wall</span>
                          </div>
                          <p className="text-2xl font-bold text-danger">
                            ${data.put_wall?.toFixed(2) || '---'}
                          </p>
                        </div>
                      </div>

                      {/* Psychology & MM State */}
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                        <div className="bg-background-deep rounded-lg p-4">
                          <div className="flex items-center space-x-2 mb-2">
                            <Brain className="w-4 h-4 text-primary" />
                            <span className="text-text-secondary text-sm">Psychology</span>
                          </div>
                          {data.psychology && (
                            <div className="space-y-2">
                              <div className="flex justify-between">
                                <span className="text-sm text-text-muted">FOMO:</span>
                                <span className={`font-semibold ${getPsychologyColor(data.psychology.fomo_level)}`}>
                                  {data.psychology.fomo_level.toFixed(0)}%
                                </span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-sm text-text-muted">Fear:</span>
                                <span className={`font-semibold ${getPsychologyColor(data.psychology.fear_level)}`}>
                                  {data.psychology.fear_level.toFixed(0)}%
                                </span>
                              </div>
                              <div className="mt-2 text-sm font-semibold text-text-primary">
                                {data.psychology.state}
                              </div>
                            </div>
                          )}
                        </div>

                        <div className="bg-background-deep rounded-lg p-4">
                          <div className="flex items-center space-x-2 mb-2">
                            <Zap className="w-4 h-4 text-primary" />
                            <span className="text-text-secondary text-sm">Market Maker State</span>
                          </div>
                          <p className={`text-xl font-bold ${getMMStateColor(data.mm_state)}`}>
                            {data.mm_state}
                          </p>
                          <p className="text-xs text-text-muted mt-2">
                            {data.mm_state === 'DEFENDING' && 'MM dampening volatility'}
                            {data.mm_state === 'SQUEEZING' && 'Explosive moves possible'}
                            {data.mm_state === 'PANICKING' && 'High volatility expected'}
                            {data.mm_state === 'NEUTRAL' && 'Balanced positioning'}
                          </p>
                        </div>

                        <div className="bg-background-deep rounded-lg p-4">
                          <div className="flex items-center space-x-2 mb-2">
                            <BarChart3 className="w-4 h-4 text-primary" />
                            <span className="text-text-secondary text-sm">VIX Level</span>
                          </div>
                          <p className="text-2xl font-bold text-text-primary">
                            {data.vix?.toFixed(1) || '---'}
                          </p>
                          <p className="text-xs text-text-muted mt-2">
                            {data.vix < 15 && 'Low volatility'}
                            {data.vix >= 15 && data.vix < 20 && 'Normal volatility'}
                            {data.vix >= 20 && data.vix < 30 && 'Elevated volatility'}
                            {data.vix >= 30 && 'High volatility'}
                          </p>
                        </div>
                      </div>

                      {/* Multi-Timeframe RSI - Only show if we have at least one valid RSI value */}
                      {data.rsi && Object.values(data.rsi).some(v => v !== null && v !== undefined) && (
                        <div className="bg-background-deep rounded-lg p-4 mb-6">
                          <div className="flex items-center space-x-2 mb-3">
                            <BarChart3 className="w-4 h-4 text-primary" />
                            <span className="text-text-secondary text-sm font-semibold">Multi-Timeframe RSI</span>
                          </div>
                          <div className="grid grid-cols-5 gap-3">
                            {['5m', '15m', '1h', '4h', '1d'].map((tf) => {
                              const rsiValue = data.rsi?.[tf as keyof typeof data.rsi]
                              const getRSIColor = (value: number | null) => {
                                if (value === null) return 'text-text-secondary'
                                if (value > 70) return 'text-danger'
                                if (value < 30) return 'text-success'
                                return 'text-text-primary'
                              }
                              return (
                                <div key={tf} className="text-center bg-background-card rounded-lg p-3">
                                  <div className="text-xs text-text-muted mb-1">{tf.toUpperCase()}</div>
                                  <div className={`text-lg font-bold ${getRSIColor(rsiValue ?? null)}`}>
                                    {rsiValue !== null && rsiValue !== undefined ? rsiValue.toFixed(1) : '---'}
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      )}

                      {/* Probability Predictions */}
                      {data.probability && (
                        <div className="space-y-6">
                          {/* EOD Probability */}
                          {data.probability.eod && (
                            <div className="bg-background-deep rounded-lg p-6">
                              <div className="flex items-center justify-between mb-4">
                                <h3 className="text-lg font-semibold text-text-primary flex items-center space-x-2">
                                  <Target className="w-5 h-5 text-primary" />
                                  <span>📊 EOD Probability (Today's Close)</span>
                                </h3>
                                <span className={`px-3 py-1 rounded-full text-sm font-semibold ${
                                  getConfidenceColor(data.probability.eod.confidence)
                                }`}>
                                  {data.probability.eod.confidence} CONFIDENCE
                                </span>
                              </div>

                              {/* Probability Ranges */}
                              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                                {data.probability.eod.ranges.map((range, idx) => (
                                  <div key={idx} className="bg-background-card rounded-lg p-4 border border-gray-700">
                                    <p className="text-text-secondary text-sm mb-1">{range.range}</p>
                                    <p className="text-2xl font-bold text-primary">{range.probability}%</p>
                                  </div>
                                ))}
                              </div>

                              {/* Supporting Factors */}
                              <div className="mb-4">
                                <h4 className="text-sm font-semibold text-text-primary mb-2">Supporting Factors:</h4>
                                <div className="space-y-1">
                                  {data.probability.eod.supporting_factors.map((factor, idx) => (
                                    <p key={idx} className="text-sm text-text-secondary">• {factor}</p>
                                  ))}
                                </div>
                              </div>

                              {/* Trading Insights */}
                              <div>
                                <h4 className="text-sm font-semibold text-text-primary mb-3">💰 Trading Insights:</h4>
                                <div className="space-y-3">
                                  {data.probability.eod.trading_insights.map((insight, idx) => (
                                    <div key={idx} className={`rounded-lg p-4 border ${getInsightColor(insight.color)}`}>
                                      <p className="font-semibold mb-2">{insight.setup}</p>
                                      <div className="space-y-1 text-sm">
                                        <p><span className="font-semibold">Action:</span> {insight.action}</p>
                                        <p><span className="font-semibold">Why:</span> {insight.why}</p>
                                        <p><span className="font-semibold">Risk:</span> {insight.risk}</p>
                                        <p><span className="font-semibold">Expected:</span> {insight.expected}</p>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            </div>
                          )}

                          {/* Next Day Probability */}
                          {data.probability.next_day && (
                            <div className="bg-background-deep rounded-lg p-6">
                              <div className="flex items-center justify-between mb-4">
                                <h3 className="text-lg font-semibold text-text-primary flex items-center space-x-2">
                                  <DollarSign className="w-5 h-5 text-primary" />
                                  <span>📅 Next Day Probability (Next Close)</span>
                                </h3>
                                <span className={`px-3 py-1 rounded-full text-sm font-semibold ${
                                  getConfidenceColor(data.probability.next_day.confidence)
                                }`}>
                                  {data.probability.next_day.confidence} CONFIDENCE
                                </span>
                              </div>

                              {/* Probability Ranges */}
                              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                                {data.probability.next_day.ranges.map((range, idx) => (
                                  <div key={idx} className="bg-background-card rounded-lg p-4 border border-gray-700">
                                    <p className="text-text-secondary text-sm mb-1">{range.range}</p>
                                    <p className="text-2xl font-bold text-primary">{range.probability}%</p>
                                  </div>
                                ))}
                              </div>

                              {/* Supporting Factors */}
                              <div className="mb-4">
                                <h4 className="text-sm font-semibold text-text-primary mb-2">Supporting Factors:</h4>
                                <div className="space-y-1">
                                  {data.probability.next_day.supporting_factors.map((factor, idx) => (
                                    <p key={idx} className="text-sm text-text-secondary">• {factor}</p>
                                  ))}
                                </div>
                              </div>

                              {/* Trading Insights */}
                              <div>
                                <h4 className="text-sm font-semibold text-text-primary mb-3">💰 Trading Insights:</h4>
                                <div className="space-y-3">
                                  {data.probability.next_day.trading_insights.map((insight, idx) => (
                                    <div key={idx} className={`rounded-lg p-4 border ${getInsightColor(insight.color)}`}>
                                      <p className="font-semibold mb-2">{insight.setup}</p>
                                      <div className="space-y-1 text-sm">
                                        <p><span className="font-semibold">Action:</span> {insight.action}</p>
                                        <p><span className="font-semibold">Why:</span> {insight.why}</p>
                                        <p><span className="font-semibold">Risk:</span> {insight.risk}</p>
                                        <p><span className="font-semibold">Expected:</span> {insight.expected}</p>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {!data.probability && (
                        <div className="bg-warning/10 border border-warning rounded-lg p-4 mt-6">
                          <div className="flex items-center space-x-2 text-warning">
                            <AlertTriangle className="w-5 h-5" />
                            <span className="font-semibold">Probability data not available for this ticker</span>
                          </div>
                        </div>
                      )}

                    </>
                  )}
                </div>
              )
            })}
          </div>

          {/* Empty State */}
          {tickers.length === 0 && !loading && (
            <div className="card text-center py-12">
              <TrendingUp className="w-16 h-16 mx-auto text-text-muted mb-4" />
              <h3 className="text-xl font-semibold text-text-primary mb-2">No Tickers Added</h3>
              <p className="text-text-secondary">Add a ticker above to get started</p>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
