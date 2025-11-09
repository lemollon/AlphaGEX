'use client'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
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

// Default tickers to load
const DEFAULT_TICKERS = ['SPY', 'QQQ', 'IWM', 'VIX', 'NVDA', 'AAPL', 'TSLA', 'AMZN']

interface TickerData {
  symbol: string
  spot_price: number
  net_gex: number
  flip_point: number
  call_wall: number
  put_wall: number
  vix: number
  mm_state: string
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
  const [loading, setLoading] = useState(true)
  const [loadingProgress, setLoadingProgress] = useState(0)
  const [newTicker, setNewTicker] = useState('')
  const [expandedTickers, setExpandedTickers] = useState<Set<string>>(new Set(DEFAULT_TICKERS))
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [cacheInfo, setCacheInfo] = useState<Record<string, string>>({})

  useEffect(() => {
    loadAllTickers()
  }, [tickers])

  const loadAllTickers = async () => {
    setLoading(true)
    setError(null)
    setLoadingProgress(0)

    try {
      // Load tickers with staggered delay to avoid rate limits
      const results = await StaggeredLoader.loadWithDelay(
        tickers,
        async (ticker) => {
          const response = await apiClient.getGEX(ticker)
          if (response.data.success) {
            setLoadingProgress((prev) => prev + 1)
            return response.data.data
          }
          throw new Error('Failed to load')
        },
        600 // 600ms delay between calls = safe rate
      )

      setTickerData(results)

      // Update cache info
      const newCacheInfo: Record<string, string> = {}
      tickers.forEach((ticker) => {
        newCacheInfo[ticker] = IntelligentCache.getAgeString(ticker)
      })
      setCacheInfo(newCacheInfo)
    } catch (err) {
      console.error('Failed to load tickers:', err)
      setError('Failed to load some tickers. Check console for details.')
    } finally {
      setLoading(false)
      setLoadingProgress(0)
    }
  }

  const refreshTicker = async (ticker: string) => {
    setRefreshing(true)
    try {
      // Clear cache for this ticker
      IntelligentCache.remove(ticker)

      // Check rate limit
      if (!RateLimiter.canMakeCall()) {
        const waitTime = Math.ceil(RateLimiter.getTimeUntilNextCall() / 1000)
        setError(`Rate limit: please wait ${waitTime}s`)
        setRefreshing(false)
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
      console.error(`Failed to refresh ${ticker}:`, err)
      setError(`Failed to refresh ${ticker}`)
    } finally {
      setRefreshing(false)
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

  const toggleExpanded = (ticker: string) => {
    const newExpanded = new Set(expandedTickers)
    if (newExpanded.has(ticker)) {
      newExpanded.delete(ticker)
    } else {
      newExpanded.add(ticker)
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

          {/* Add Ticker Input */}
          <div className="card mb-8">
            <div className="flex items-center space-x-4">
              <input
                type="text"
                value={newTicker}
                onChange={(e) => setNewTicker(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addTicker()}
                placeholder="Add ticker (e.g., GOOGL)"
                className="flex-1 px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary focus:outline-none focus:border-primary"
              />
              <button
                onClick={addTicker}
                className="btn-primary flex items-center space-x-2"
              >
                <Plus className="w-5 h-5" />
                <span>Add Ticker</span>
              </button>
            </div>
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

          {/* Loading State */}
          {loading && (
            <div className="text-center py-12">
              <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
              <p className="text-text-secondary mt-4">Loading ticker data...</p>
            </div>
          )}

          {/* Ticker Cards */}
          <div className="space-y-6">
            {tickers.map((ticker) => {
              const data = tickerData[ticker]
              const isExpanded = expandedTickers.has(ticker)

              if (!data) {
                return (
                  <div key={ticker} className="card">
                    <div className="flex items-center justify-between">
                      <div className="text-text-primary font-semibold">{ticker}</div>
                      <button
                        onClick={() => removeTicker(ticker)}
                        className="text-text-secondary hover:text-danger"
                      >
                        <X className="w-5 h-5" />
                      </button>
                    </div>
                    <p className="text-text-muted mt-2">Loading data...</p>
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
                      {cacheInfo[ticker] && (
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

                      {/* Multi-Timeframe RSI */}
                      {data.rsi && (
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
                                  <div className={`text-lg font-bold ${getRSIColor(rsiValue)}`}>
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
