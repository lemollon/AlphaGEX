'use client'

import { useState, useEffect, useCallback } from 'react'
import { Activity, TrendingUp, TrendingDown, BarChart3, RefreshCw, AlertTriangle, Clock, Zap, Target, ArrowUpDown, Database, ExternalLink, CheckCircle, XCircle } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend, ReferenceLine } from 'recharts'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'

// ============ INTERFACES ============

interface GammaStrike {
  strike: number
  call_gamma: number
  put_gamma: number
  total_gamma: number
  net_gex?: number
}

interface GammaSource {
  data_source: string
  spot_price: number
  flip_point: number
  call_wall: number
  put_wall: number
  gamma_array: GammaStrike[]
  strikes_count: number
  expiration?: string
  max_pain?: number
  net_gex?: number
  put_call_ratio?: number
  timestamp?: string
  _debug?: {
    raw_fields?: string[]
    sample_strike?: Record<string, string>
    profile_first_strike_gamma?: {
      call_gamma: number | string
      put_gamma: number | string
      total_gamma: number | string
      call_gamma_type: string
      put_gamma_type: string
    }
    calculated_call_wall?: number
    calculated_put_wall?: number
    max_call_gamma?: number
    max_put_gamma?: number
    sample_gamma_values?: GammaStrike[]
    total_net_gex_calculated?: number
    profile_debug?: {
      used_cache?: boolean
      total_strikes_before_filter?: number
      total_strikes_after_filter?: number
      raw_api_first_strike?: {
        strike: number
        call_gamma: string | number
        put_gamma: string | number
        call_gamma_type: string
        put_gamma_type: string
      }
      processed_first_strike?: Record<string, number>
    }
  }
}

interface ComparisonData {
  success: boolean
  symbol: string
  timestamp: string
  trading_volatility: GammaSource | null      // All expirations from Trading Volatility API
  tradier_all_expirations: GammaSource | null // All expirations from Tradier (apples-to-apples)
  tradier_0dte: GammaSource | null            // 0DTE only from Tradier
  tradier_calculated?: GammaSource | null     // Legacy field for backwards compatibility
  errors: string[]
}

interface TradingVolData {
  symbol: string
  spot_price: number
  net_gex: number
  flip_point: number
  call_wall: number | null
  put_wall: number | null
  put_call_ratio: number
  implied_volatility: number
  collection_date: string
}

interface TraderCalculations {
  vix_spot: number
  vix_m1: number
  vix_m2: number
  term_structure_pct: number
  structure_type: string
  iv_percentile: number
  realized_vol_20d: number
  iv_rv_spread: number
  vol_regime: string
}

interface ComparisonHistory {
  timestamp: string
  trading_vol_iv: number
  trader_realized_vol: number
  vix_level: number
  spread: number
}

// ============ COMPONENT ============

export default function VolatilityComparison() {
  const [loading, setLoading] = useState(true)
  const [symbol, setSymbol] = useState('SPY')

  // New 0DTE comparison data
  const [comparisonData, setComparisonData] = useState<ComparisonData | null>(null)

  // Original data sources
  const [tradingVolData, setTradingVolData] = useState<TradingVolData | null>(null)
  const [traderCalcs, setTraderCalcs] = useState<TraderCalculations | null>(null)
  const [comparisonHistory, setComparisonHistory] = useState<ComparisonHistory[]>([])

  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [usingFallback, setUsingFallback] = useState(false)
  const [tradingVolError, setTradingVolError] = useState<string | null>(null)

  const fetchData = useCallback(async (showLoading = true, forceRefresh = false) => {
    try {
      if (showLoading) setLoading(true)
      setError(null)
      setTradingVolError(null)

      // Fetch all data in parallel
      const [comparisonRes, gexRes, vixRes] = await Promise.all([
        apiClient.get0DTEGammaComparison(symbol, forceRefresh).catch((e) => ({
          data: { success: false, errors: [e.message] }
        })),
        apiClient.getGEX(symbol).catch((e) => ({ data: { success: false, error: e.message } })),
        apiClient.getVIXCurrent().catch((e) => ({ data: { success: false, error: e.message } }))
      ])

      // Process 0DTE comparison data (NEW)
      if (comparisonRes.data?.success) {
        setComparisonData(comparisonRes.data)
      }

      // Check if Trading Volatility API succeeded (ORIGINAL)
      const tradingVolSuccess = gexRes.data?.success && gexRes.data?.data
      const traderCalcsSuccess = vixRes.data?.success && vixRes.data?.data

      // Trading Volatility API data (PRIMARY SOURCE)
      if (tradingVolSuccess) {
        const data = gexRes.data.data
        setTradingVolData({
          symbol: data.symbol || symbol,
          spot_price: data.spot_price || 0,
          net_gex: data.net_gex || 0,
          flip_point: data.flip_point || 0,
          call_wall: data.call_wall,
          put_wall: data.put_wall,
          put_call_ratio: data.put_call_ratio || 0,
          implied_volatility: data.implied_vol || data.implied_volatility || 0,
          collection_date: data.collection_date || new Date().toISOString()
        })
        setUsingFallback(false)
      } else {
        setTradingVolData(null)
        setTradingVolError(gexRes.data?.error || 'Trading Volatility API unavailable')
        setUsingFallback(true)
      }

      // Trader calculations (VIX-based)
      if (traderCalcsSuccess) {
        setTraderCalcs(vixRes.data.data)
      }

      // Build comparison history (ORIGINAL)
      const currentComparison: ComparisonHistory = {
        timestamp: new Date().toISOString(),
        trading_vol_iv: tradingVolSuccess
          ? (gexRes.data.data?.implied_vol || gexRes.data.data?.implied_volatility || 0) * 100
          : 0,
        trader_realized_vol: vixRes.data?.data?.realized_vol_20d || 0,
        vix_level: vixRes.data?.data?.vix_spot || 0,
        spread: vixRes.data?.data?.iv_rv_spread || 0
      }

      setComparisonHistory(prev => {
        const newHistory = [...prev, currentComparison]
        return newHistory.slice(-50) // Keep last 50 data points
      })

      // Only set error if ALL sources failed
      if (!tradingVolSuccess && !traderCalcsSuccess && !comparisonRes.data?.success) {
        setError('All data sources unavailable')
      }

      setLastUpdated(new Date())
    } catch (err: any) {
      setError(err.message || 'Failed to load volatility data')
    } finally {
      setLoading(false)
    }
  }, [symbol])

  // Initial fetch and auto-refresh every 5 minutes
  useEffect(() => {
    fetchData()

    let interval: NodeJS.Timeout | null = null
    if (autoRefresh) {
      interval = setInterval(() => {
        fetchData(false)
      }, 5 * 60 * 1000)
    }

    return () => {
      if (interval) clearInterval(interval)
    }
  }, [fetchData, autoRefresh])

  // ============ HELPER FUNCTIONS ============

  const getVolRegimeColor = (regime: string) => {
    switch (regime) {
      case 'very_low':
      case 'low':
        return 'text-success bg-success/20'
      case 'normal':
        return 'text-primary bg-primary/20'
      case 'elevated':
        return 'text-warning bg-warning/20'
      case 'high':
      case 'extreme':
        return 'text-danger bg-danger/20'
      default:
        return 'text-text-muted bg-background-hover'
    }
  }

  const formatNumber = (num: number | null | undefined, decimals = 2) => {
    if (num === null || num === undefined) return '--'
    return num.toFixed(decimals)
  }

  const formatGamma = (value: number) => {
    if (Math.abs(value) >= 1e9) return `${(value / 1e9).toFixed(2)}B`
    if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(2)}M`
    if (Math.abs(value) >= 1e3) return `${(value / 1e3).toFixed(2)}K`
    return value.toFixed(2)
  }

  // Prepare chart data for 0DTE comparison
  const prepareChartData = (source: GammaSource | null, label: string) => {
    if (!source || !source.gamma_array) return []
    return source.gamma_array.map(item => ({
      strike: item.strike,
      [`${label}_call`]: item.call_gamma,
      [`${label}_put`]: -Math.abs(item.put_gamma),
      [`${label}_net`]: item.total_gamma || item.net_gex || 0
    }))
  }

  // Chart data for all 3 sources
  const tradingVolChartData = prepareChartData(comparisonData?.trading_volatility || null, 'tv')
  const tradierAllExpChartData = prepareChartData(comparisonData?.tradier_all_expirations || null, 'ta')
  const tradier0dteChartData = prepareChartData(comparisonData?.tradier_0dte || null, 'tr')

  // Calculate shared Y-axis domain for the two "all expirations" charts (so they're visually comparable)
  const calculateSharedYDomain = () => {
    const allValues: number[] = []

    // Collect all gamma values from both "all expirations" sources
    if (comparisonData?.trading_volatility?.gamma_array) {
      comparisonData.trading_volatility.gamma_array.forEach(item => {
        allValues.push(item.call_gamma, -Math.abs(item.put_gamma))
      })
    }
    if (comparisonData?.tradier_all_expirations?.gamma_array) {
      comparisonData.tradier_all_expirations.gamma_array.forEach(item => {
        allValues.push(item.call_gamma, -Math.abs(item.put_gamma))
      })
    }

    if (allValues.length === 0) return [-100, 100]

    const maxVal = Math.max(...allValues)
    const minVal = Math.min(...allValues)
    // Add 10% padding
    const padding = Math.max(Math.abs(maxVal), Math.abs(minVal)) * 0.1
    return [minVal - padding, maxVal + padding]
  }

  const sharedYDomain = calculateSharedYDomain()

  // Separate Y domain for 0DTE chart
  const calculate0dteYDomain = () => {
    const allValues: number[] = []
    if (comparisonData?.tradier_0dte?.gamma_array) {
      comparisonData.tradier_0dte.gamma_array.forEach(item => {
        allValues.push(item.call_gamma, -Math.abs(item.put_gamma))
      })
    }
    if (allValues.length === 0) return [-100, 100]
    const maxVal = Math.max(...allValues)
    const minVal = Math.min(...allValues)
    const padding = Math.max(Math.abs(maxVal), Math.abs(minVal)) * 0.1
    return [minVal - padding, maxVal + padding]
  }

  const zerodte_YDomain = calculate0dteYDomain()

  // Calculate IV-RV spread
  const ivRvSpread = tradingVolData && traderCalcs
    ? ((tradingVolData.implied_volatility * 100) - traderCalcs.realized_vol_20d).toFixed(2)
    : '--'

  // ============ RENDER ============

  return (
    <div className="min-h-screen">
      <Navigation />
      <main className="pt-16 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <div className="flex items-center gap-3">
                  <ArrowUpDown className="w-8 h-8 text-primary" />
                  <h1 className="text-3xl font-bold text-text-primary">Volatility Comparison</h1>
                </div>
                <p className="text-text-secondary mt-1">Compare Trading Volatility API data with Trader calculations</p>
              </div>
              <div className="flex items-center gap-4">
                <select
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  className="px-4 py-2 rounded-lg bg-background-hover border border-border text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="SPY">SPY</option>
                  <option value="QQQ">QQQ</option>
                  <option value="IWM">IWM</option>
                  <option value="SPX">SPX</option>
                </select>

                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={autoRefresh}
                    onChange={(e) => setAutoRefresh(e.target.checked)}
                    className="w-4 h-4 rounded border-border text-primary focus:ring-primary"
                  />
                  <span className="text-sm text-text-secondary">Auto-refresh</span>
                </label>

                {lastUpdated && (
                  <div className="text-xs text-text-muted hidden sm:block">
                    Updated: {lastUpdated.toLocaleTimeString()}
                  </div>
                )}
                <button
                  onClick={() => fetchData()}
                  disabled={loading}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg font-semibold bg-primary text-white hover:bg-primary/90 disabled:opacity-50"
                >
                  <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                  Refresh
                </button>
                <button
                  onClick={() => fetchData(true, true)}
                  disabled={loading}
                  title="Force refresh clears cached data and fetches fresh from APIs"
                  className="flex items-center gap-2 px-4 py-2 rounded-lg font-semibold bg-warning/20 text-warning border border-warning/30 hover:bg-warning/30 disabled:opacity-50"
                >
                  <Database className="w-4 h-4" />
                  Force Refresh
                </button>
              </div>
            </div>

            {loading && !tradingVolData && !traderCalcs ? (
              <div className="text-center py-12">
                <Activity className="w-8 h-8 text-primary mx-auto animate-spin" />
                <p className="text-text-secondary mt-2">Loading volatility data...</p>
              </div>
            ) : error ? (
              <div className="card bg-danger/10 border-danger/20">
                <div className="flex items-center gap-3">
                  <AlertTriangle className="w-6 h-6 text-danger" />
                  <div>
                    <p className="text-danger font-semibold">Error Loading Data</p>
                    <p className="text-text-secondary text-sm">{error}</p>
                  </div>
                </div>
              </div>
            ) : (
              <>
                {/* Fallback Warning Banner */}
                {usingFallback && (
                  <div className="card bg-warning/10 border-warning/30 border">
                    <div className="flex items-center gap-3">
                      <AlertTriangle className="w-6 h-6 text-warning flex-shrink-0" />
                      <div className="flex-1">
                        <p className="text-warning font-semibold">Using Fallback Data</p>
                        <p className="text-text-secondary text-sm">
                          Trading Volatility API unavailable ({tradingVolError}). Displaying Trader calculations as fallback.
                        </p>
                      </div>
                      <div className="px-3 py-1 rounded-full bg-warning/20 text-warning text-xs font-semibold">
                        FALLBACK MODE
                      </div>
                    </div>
                  </div>
                )}

                {/* Data Source Status Indicators */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className={`card border-l-4 ${!usingFallback ? 'border-l-blue-500' : 'border-l-gray-500 opacity-60'}`}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <ExternalLink className="w-5 h-5 text-blue-400" />
                        <h3 className="font-semibold text-text-primary">Trading Volatility API</h3>
                      </div>
                      {!usingFallback ? (
                        <span className="flex items-center gap-1 px-2 py-1 rounded bg-success/20 text-success text-xs font-semibold">
                          <CheckCircle className="w-3 h-3" /> ACTIVE
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 px-2 py-1 rounded bg-danger/20 text-danger text-xs font-semibold">
                          <XCircle className="w-3 h-3" /> UNAVAILABLE
                        </span>
                      )}
                    </div>
                    <p className="text-text-secondary text-sm">
                      {!usingFallback ? 'Primary source - GEX, IV, walls, gamma profiles' : tradingVolError}
                    </p>
                  </div>

                  <div className={`card border-l-4 ${usingFallback ? 'border-l-green-500' : 'border-l-green-500/50'}`}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Database className="w-5 h-5 text-green-400" />
                        <h3 className="font-semibold text-text-primary">Trader Calculations</h3>
                      </div>
                      <span className={`px-2 py-1 rounded text-xs font-semibold ${
                        usingFallback ? 'bg-warning/20 text-warning' : 'bg-primary/20 text-primary'
                      }`}>
                        {usingFallback ? 'FALLBACK ACTIVE' : 'STANDBY'}
                      </span>
                    </div>
                    <p className="text-text-secondary text-sm">
                      {usingFallback ? 'Active fallback - VIX, realized vol, IV percentile' : 'Ready as fallback - VIX-based calculations'}
                    </p>
                  </div>
                </div>

                {/* Main Comparison Cards */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  <div className="card border-l-4 border-l-blue-500">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-text-secondary text-sm">Trading Vol IV</p>
                        <p className="text-3xl font-bold text-blue-400 mt-1">
                          {formatNumber((tradingVolData?.implied_volatility || 0) * 100, 1)}%
                        </p>
                      </div>
                      <div className="p-2 rounded-lg bg-blue-500/20">
                        <Activity className="w-5 h-5 text-blue-400" />
                      </div>
                    </div>
                    <p className="text-xs text-text-muted mt-2">From Trading Volatility API</p>
                  </div>

                  <div className="card border-l-4 border-l-green-500">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-text-secondary text-sm">Realized Vol (20d)</p>
                        <p className="text-3xl font-bold text-green-400 mt-1">
                          {formatNumber(traderCalcs?.realized_vol_20d, 1)}%
                        </p>
                      </div>
                      <div className="p-2 rounded-lg bg-green-500/20">
                        <TrendingUp className="w-5 h-5 text-green-400" />
                      </div>
                    </div>
                    <p className="text-xs text-text-muted mt-2">Trader calculation</p>
                  </div>

                  <div className="card border-l-4 border-l-yellow-500">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-text-secondary text-sm">VIX Spot</p>
                        <p className={`text-3xl font-bold mt-1 ${
                          (traderCalcs?.vix_spot || 0) > 25 ? 'text-danger' :
                          (traderCalcs?.vix_spot || 0) > 18 ? 'text-warning' : 'text-success'
                        }`}>
                          {formatNumber(traderCalcs?.vix_spot)}
                        </p>
                      </div>
                      <div className={`px-2 py-1 rounded text-xs font-semibold ${getVolRegimeColor(traderCalcs?.vol_regime || '')}`}>
                        {traderCalcs?.vol_regime?.toUpperCase().replace('_', ' ') || 'N/A'}
                      </div>
                    </div>
                    <p className="text-xs text-text-muted mt-2">IV Percentile: {formatNumber(traderCalcs?.iv_percentile, 0)}th</p>
                  </div>

                  <div className="card border-l-4 border-l-purple-500">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-text-secondary text-sm">IV-RV Spread</p>
                        <p className={`text-3xl font-bold mt-1 ${
                          parseFloat(ivRvSpread) > 5 ? 'text-warning' :
                          parseFloat(ivRvSpread) < 0 ? 'text-success' : 'text-text-primary'
                        }`}>
                          {ivRvSpread} pts
                        </p>
                      </div>
                      <div className="p-2 rounded-lg bg-purple-500/20">
                        <ArrowUpDown className="w-5 h-5 text-purple-400" />
                      </div>
                    </div>
                    <p className="text-xs text-text-muted mt-2">
                      {parseFloat(ivRvSpread) > 5 ? 'IV Premium High' :
                       parseFloat(ivRvSpread) < 0 ? 'IV Discount' : 'Normal Range'}
                    </p>
                  </div>
                </div>

                {/* GEX Data Comparison */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <div className="card">
                    <div className="flex items-center gap-2 mb-4">
                      <BarChart3 className="w-5 h-5 text-blue-400" />
                      <h2 className="text-xl font-semibold text-text-primary">Trading Volatility GEX</h2>
                      <span className="text-xs px-2 py-0.5 rounded bg-blue-500/20 text-blue-400">External</span>
                    </div>

                    <div className="grid grid-cols-2 gap-4 mb-4">
                      <div className="p-3 rounded-lg bg-background-hover">
                        <p className="text-text-muted text-xs">Net GEX</p>
                        <p className={`text-xl font-bold ${(tradingVolData?.net_gex || 0) >= 0 ? 'text-success' : 'text-danger'}`}>
                          {formatNumber(tradingVolData?.net_gex, 2)}B
                        </p>
                      </div>
                      <div className="p-3 rounded-lg bg-background-hover">
                        <p className="text-text-muted text-xs">Flip Point</p>
                        <p className="text-xl font-bold text-text-primary">
                          ${formatNumber(tradingVolData?.flip_point, 2)}
                        </p>
                      </div>
                      <div className="p-3 rounded-lg bg-background-hover">
                        <p className="text-text-muted text-xs">Call Wall</p>
                        <p className="text-xl font-bold text-success">
                          ${formatNumber(tradingVolData?.call_wall)}
                        </p>
                      </div>
                      <div className="p-3 rounded-lg bg-background-hover">
                        <p className="text-text-muted text-xs">Put Wall</p>
                        <p className="text-xl font-bold text-danger">
                          ${formatNumber(tradingVolData?.put_wall)}
                        </p>
                      </div>
                    </div>

                    <div className="p-3 rounded-lg bg-background-hover">
                      <p className="text-text-muted text-xs mb-1">P/C Ratio (OI)</p>
                      <p className={`text-lg font-semibold ${
                        (tradingVolData?.put_call_ratio || 0) > 1.2 ? 'text-danger' :
                        (tradingVolData?.put_call_ratio || 0) < 0.8 ? 'text-success' : 'text-text-primary'
                      }`}>
                        {formatNumber(tradingVolData?.put_call_ratio, 3)}
                      </p>
                    </div>
                  </div>

                  <div className="card">
                    <div className="flex items-center gap-2 mb-4">
                      <TrendingUp className="w-5 h-5 text-green-400" />
                      <h2 className="text-xl font-semibold text-text-primary">Trader VIX Analysis</h2>
                      <span className="text-xs px-2 py-0.5 rounded bg-green-500/20 text-green-400">Internal</span>
                    </div>

                    <div className="space-y-3">
                      <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                        <div>
                          <p className="text-text-muted text-xs">VIX Spot</p>
                          <p className="text-xl font-bold text-text-primary">{formatNumber(traderCalcs?.vix_spot)}</p>
                        </div>
                        <div className={`px-3 py-1 rounded-lg font-semibold ${getVolRegimeColor(traderCalcs?.vol_regime || '')}`}>
                          {traderCalcs?.vol_regime?.toUpperCase().replace('_', ' ') || 'N/A'}
                        </div>
                      </div>

                      <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                        <div>
                          <p className="text-text-muted text-xs">VIX Front Month (M1)</p>
                          <p className="text-xl font-bold text-text-primary">{formatNumber(traderCalcs?.vix_m1)}</p>
                        </div>
                        <div className={`px-2 py-1 rounded font-semibold text-sm ${
                          (traderCalcs?.term_structure_pct || 0) > 0 ? 'bg-success/20 text-success' : 'bg-danger/20 text-danger'
                        }`}>
                          {(traderCalcs?.term_structure_pct || 0) > 0 ? '+' : ''}{formatNumber(traderCalcs?.term_structure_pct, 1)}%
                        </div>
                      </div>

                      <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                        <div>
                          <p className="text-text-muted text-xs">VIX Second Month (M2)</p>
                          <p className="text-xl font-bold text-text-primary">{formatNumber(traderCalcs?.vix_m2)}</p>
                        </div>
                      </div>

                      <div className={`p-3 rounded-lg border ${
                        traderCalcs?.structure_type === 'contango' ? 'bg-success/10 border-success/20' :
                        traderCalcs?.structure_type === 'backwardation' ? 'bg-danger/10 border-danger/20' :
                        'bg-background-hover border-border'
                      }`}>
                        <div className="flex items-center gap-2">
                          <Zap className="w-5 h-5" />
                          <span className="font-semibold">
                            {traderCalcs?.structure_type?.toUpperCase() || 'UNKNOWN'}
                          </span>
                        </div>
                        <p className="text-sm text-text-secondary mt-1">
                          {traderCalcs?.structure_type === 'contango'
                            ? 'Normal market - futures above spot'
                            : traderCalcs?.structure_type === 'backwardation'
                            ? 'Stress signal - spot above futures'
                            : 'Analyzing term structure...'}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* OPEX Net Gamma Charts - All Expirations Comparison */}
                {(comparisonData?.trading_volatility || comparisonData?.tradier_all_expirations) && (
                  <>
                    <div className="card bg-gradient-to-r from-primary/10 to-transparent">
                      <div className="flex items-center gap-2 mb-2">
                        <Target className="w-5 h-5 text-primary" />
                        <h2 className="text-xl font-semibold text-text-primary">OPEX Net Gamma Charts</h2>
                      </div>
                      <p className="text-text-secondary text-sm">
                        All expirations NET gamma comparison. TradingVolatility API (left) vs Tradier calculated (right).
                        Both charts should show similar patterns if calculations are accurate.
                      </p>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                      {/* TradingVolatility API Chart - OPEX Net Gamma */}
                      <div className="card">
                        <div className="flex items-center justify-between mb-4">
                          <div className="flex items-center gap-2">
                            <BarChart3 className="w-5 h-5 text-blue-400" />
                            <h3 className="font-semibold text-text-primary">OPEX Net Gamma (TradingVol API)</h3>
                          </div>
                          {comparisonData?.trading_volatility ? (
                            <span className="text-xs text-text-muted">
                              {comparisonData.trading_volatility.strikes_count} strikes
                            </span>
                          ) : (
                            <span className="text-xs text-danger">No data</span>
                          )}
                        </div>
                        {tradingVolChartData.length > 0 ? (
                          <div className="h-64">
                            <ResponsiveContainer width="100%" height="100%">
                              <BarChart data={tradingVolChartData} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                <XAxis
                                  dataKey="strike"
                                  stroke="#9CA3AF"
                                  tick={{ fill: '#9CA3AF', fontSize: 9 }}
                                  tickFormatter={(v) => `$${v}`}
                                  interval="preserveStartEnd"
                                />
                                <YAxis
                                  stroke="#9CA3AF"
                                  tick={{ fill: '#9CA3AF', fontSize: 9 }}
                                  tickFormatter={formatGamma}
                                  domain={sharedYDomain as [number, number]}
                                />
                                <Tooltip
                                  contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: '8px' }}
                                  formatter={(value: number, name: string) => [formatGamma(value), name.includes('call') ? 'Call' : 'Put']}
                                  labelFormatter={(label) => `Strike: $${label}`}
                                />
                                <Bar dataKey="tv_call" fill="#22C55E" stackId="stack" />
                                <Bar dataKey="tv_put" fill="#EF4444" stackId="stack" />
                                {comparisonData?.trading_volatility?.spot_price && (
                                  <ReferenceLine x={comparisonData.trading_volatility.spot_price} stroke="#3B82F6" strokeWidth={2} />
                                )}
                              </BarChart>
                            </ResponsiveContainer>
                          </div>
                        ) : (
                          <div className="h-64 flex items-center justify-center text-text-muted">No data available</div>
                        )}
                      </div>

                      {/* Tradier OPEX Net Gamma Chart */}
                      <div className="card">
                        <div className="flex items-center justify-between mb-4">
                          <div className="flex items-center gap-2">
                            <BarChart3 className="w-5 h-5 text-green-400" />
                            <h3 className="font-semibold text-text-primary">OPEX Net Gamma (Tradier)</h3>
                          </div>
                          {comparisonData?.tradier_all_expirations ? (
                            <span className="text-xs text-text-muted">
                              {comparisonData.tradier_all_expirations.strikes_count} strikes
                            </span>
                          ) : (
                            <span className="text-xs text-danger">No data</span>
                          )}
                        </div>
                        {tradierAllExpChartData.length > 0 ? (
                          <div className="h-64">
                            <ResponsiveContainer width="100%" height="100%">
                              <BarChart data={tradierAllExpChartData} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                <XAxis
                                  dataKey="strike"
                                  stroke="#9CA3AF"
                                  tick={{ fill: '#9CA3AF', fontSize: 9 }}
                                  tickFormatter={(v) => `$${v}`}
                                  interval="preserveStartEnd"
                                />
                                <YAxis
                                  stroke="#9CA3AF"
                                  tick={{ fill: '#9CA3AF', fontSize: 9 }}
                                  tickFormatter={formatGamma}
                                  domain={sharedYDomain as [number, number]}
                                />
                                <Tooltip
                                  contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: '8px' }}
                                  formatter={(value: number, name: string) => [formatGamma(value), name.includes('call') ? 'Call' : 'Put']}
                                  labelFormatter={(label) => `Strike: $${label}`}
                                />
                                <Bar dataKey="ta_call" fill="#22C55E" stackId="stack" />
                                <Bar dataKey="ta_put" fill="#EF4444" stackId="stack" />
                                {comparisonData?.tradier_all_expirations?.spot_price && (
                                  <ReferenceLine x={comparisonData.tradier_all_expirations.spot_price} stroke="#3B82F6" strokeWidth={2} />
                                )}
                              </BarChart>
                            </ResponsiveContainer>
                          </div>
                        ) : (
                          <div className="h-64 flex items-center justify-center text-text-muted">No data available</div>
                        )}
                      </div>
                    </div>

                    {/* Key Levels Comparison Table - All Expirations */}
                    <div className="card">
                      <div className="flex items-center gap-2 mb-4">
                        <Zap className="w-5 h-5 text-primary" />
                        <h2 className="text-lg font-semibold text-text-primary">All Expirations Key Levels Comparison</h2>
                      </div>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b border-border">
                              <th className="text-left py-3 px-4 text-text-muted font-medium">Metric</th>
                              <th className="text-right py-3 px-4 text-blue-400 font-medium">TradingVol API</th>
                              <th className="text-right py-3 px-4 text-green-400 font-medium">Tradier All Exp</th>
                              <th className="text-right py-3 px-4 text-text-muted font-medium">Diff</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr className="border-b border-border/50">
                              <td className="py-2 px-4">Spot Price</td>
                              <td className="py-2 px-4 text-right font-mono">${formatNumber(comparisonData?.trading_volatility?.spot_price)}</td>
                              <td className="py-2 px-4 text-right font-mono">${formatNumber(comparisonData?.tradier_all_expirations?.spot_price)}</td>
                              <td className="py-2 px-4 text-right font-mono text-text-muted">
                                {comparisonData?.trading_volatility?.spot_price && comparisonData?.tradier_all_expirations?.spot_price
                                  ? `$${formatNumber(Math.abs(comparisonData.trading_volatility.spot_price - comparisonData.tradier_all_expirations.spot_price))}` : '--'}
                              </td>
                            </tr>
                            <tr className="border-b border-border/50">
                              <td className="py-2 px-4">Flip Point</td>
                              <td className="py-2 px-4 text-right font-mono">${formatNumber(comparisonData?.trading_volatility?.flip_point)}</td>
                              <td className="py-2 px-4 text-right font-mono">${formatNumber(comparisonData?.tradier_all_expirations?.flip_point)}</td>
                              <td className="py-2 px-4 text-right font-mono text-text-muted">
                                {comparisonData?.trading_volatility?.flip_point && comparisonData?.tradier_all_expirations?.flip_point
                                  ? `$${formatNumber(Math.abs(comparisonData.trading_volatility.flip_point - comparisonData.tradier_all_expirations.flip_point))}` : '--'}
                              </td>
                            </tr>
                            <tr className="border-b border-border/50">
                              <td className="py-2 px-4">Call Wall</td>
                              <td className="py-2 px-4 text-right font-mono text-success">${formatNumber(comparisonData?.trading_volatility?.call_wall)}</td>
                              <td className="py-2 px-4 text-right font-mono text-success">${formatNumber(comparisonData?.tradier_all_expirations?.call_wall)}</td>
                              <td className="py-2 px-4 text-right font-mono text-text-muted">
                                {comparisonData?.trading_volatility?.call_wall && comparisonData?.tradier_all_expirations?.call_wall
                                  ? `$${formatNumber(Math.abs(comparisonData.trading_volatility.call_wall - comparisonData.tradier_all_expirations.call_wall))}` : '--'}
                              </td>
                            </tr>
                            <tr className="border-b border-border/50">
                              <td className="py-2 px-4">Put Wall</td>
                              <td className="py-2 px-4 text-right font-mono text-danger">${formatNumber(comparisonData?.trading_volatility?.put_wall)}</td>
                              <td className="py-2 px-4 text-right font-mono text-danger">${formatNumber(comparisonData?.tradier_all_expirations?.put_wall)}</td>
                              <td className="py-2 px-4 text-right font-mono text-text-muted">
                                {comparisonData?.trading_volatility?.put_wall && comparisonData?.tradier_all_expirations?.put_wall
                                  ? `$${formatNumber(Math.abs(comparisonData.trading_volatility.put_wall - comparisonData.tradier_all_expirations.put_wall))}` : '--'}
                              </td>
                            </tr>
                            <tr>
                              <td className="py-2 px-4">Net GEX</td>
                              <td className="py-2 px-4 text-right font-mono">
                                <span className={(comparisonData?.trading_volatility?.net_gex || 0) >= 0 ? 'text-success' : 'text-danger'}>
                                  {formatGamma(comparisonData?.trading_volatility?.net_gex || 0)}
                                </span>
                              </td>
                              <td className="py-2 px-4 text-right font-mono">
                                <span className={(comparisonData?.tradier_all_expirations?.net_gex || 0) >= 0 ? 'text-success' : 'text-danger'}>
                                  {formatGamma(comparisonData?.tradier_all_expirations?.net_gex || 0)}
                                </span>
                              </td>
                              <td className="py-2 px-4 text-right font-mono text-text-muted">--</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </>
                )}

                {/* 0DTE NET GEX Chart - Tradier Only */}
                {comparisonData?.tradier_0dte && (
                  <>
                    <div className="card bg-gradient-to-r from-yellow-500/10 to-transparent">
                      <div className="flex items-center gap-2 mb-2">
                        <Clock className="w-5 h-5 text-yellow-400" />
                        <h2 className="text-xl font-semibold text-text-primary">Tradier 0DTE NET GEX</h2>
                      </div>
                      <p className="text-text-secondary text-sm">
                        Zero Days to Expiration NET gamma exposure from Tradier.
                        Expiration: {comparisonData.tradier_0dte.expiration}
                      </p>
                    </div>

                    <div className="card">
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-2">
                          <BarChart3 className="w-5 h-5 text-yellow-400" />
                          <h3 className="font-semibold text-text-primary">Tradier 0DTE NET GEX Chart</h3>
                        </div>
                        <span className="text-xs text-text-muted">
                          {comparisonData.tradier_0dte.expiration} | {comparisonData.tradier_0dte.strikes_count} strikes
                        </span>
                      </div>
                      {tradier0dteChartData.length > 0 ? (
                        <div className="h-64">
                          <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={tradier0dteChartData} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                              <XAxis
                                dataKey="strike"
                                stroke="#9CA3AF"
                                tick={{ fill: '#9CA3AF', fontSize: 9 }}
                                tickFormatter={(v) => `$${v}`}
                                interval="preserveStartEnd"
                              />
                              <YAxis
                                stroke="#9CA3AF"
                                tick={{ fill: '#9CA3AF', fontSize: 9 }}
                                tickFormatter={formatGamma}
                                domain={zerodte_YDomain as [number, number]}
                              />
                              <Tooltip
                                contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: '8px' }}
                                formatter={(value: number, name: string) => [formatGamma(value), name.includes('call') ? 'Call' : 'Put']}
                                labelFormatter={(label) => `Strike: $${label}`}
                              />
                              <Bar dataKey="tr_call" fill="#22C55E" stackId="stack" />
                              <Bar dataKey="tr_put" fill="#EF4444" stackId="stack" />
                              {comparisonData.tradier_0dte.spot_price && (
                                <ReferenceLine x={comparisonData.tradier_0dte.spot_price} stroke="#F59E0B" strokeWidth={2} />
                              )}
                            </BarChart>
                          </ResponsiveContainer>
                        </div>
                      ) : (
                        <div className="h-64 flex items-center justify-center text-text-muted">No 0DTE data available</div>
                      )}

                      {/* 0DTE Key Levels */}
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4 pt-4 border-t border-border">
                        <div className="p-3 rounded-lg bg-background-hover">
                          <p className="text-text-muted text-xs">Flip Point</p>
                          <p className="text-lg font-bold text-text-primary">${formatNumber(comparisonData.tradier_0dte.flip_point)}</p>
                        </div>
                        <div className="p-3 rounded-lg bg-background-hover">
                          <p className="text-text-muted text-xs">Call Wall</p>
                          <p className="text-lg font-bold text-success">${formatNumber(comparisonData.tradier_0dte.call_wall)}</p>
                        </div>
                        <div className="p-3 rounded-lg bg-background-hover">
                          <p className="text-text-muted text-xs">Put Wall</p>
                          <p className="text-lg font-bold text-danger">${formatNumber(comparisonData.tradier_0dte.put_wall)}</p>
                        </div>
                        <div className="p-3 rounded-lg bg-background-hover">
                          <p className="text-text-muted text-xs">Net GEX</p>
                          <p className={`text-lg font-bold ${(comparisonData.tradier_0dte.net_gex || 0) >= 0 ? 'text-success' : 'text-danger'}`}>
                            {formatGamma(comparisonData.tradier_0dte.net_gex || 0)}
                          </p>
                        </div>
                      </div>
                    </div>
                  </>
                )}

                {/* Volatility Comparison Over Time */}
                {comparisonHistory.length > 1 && (
                  <div className="card">
                    <div className="flex items-center gap-2 mb-4">
                      <Clock className="w-5 h-5 text-primary" />
                      <h2 className="text-xl font-semibold text-text-primary">Volatility Comparison (Session)</h2>
                    </div>

                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={comparisonHistory} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                          <XAxis
                            dataKey="timestamp"
                            stroke="#9CA3AF"
                            tick={{ fill: '#9CA3AF', fontSize: 11 }}
                            tickFormatter={(value) => new Date(value).toLocaleTimeString()}
                          />
                          <YAxis stroke="#9CA3AF" tick={{ fill: '#9CA3AF', fontSize: 11 }} domain={['auto', 'auto']} />
                          <Tooltip
                            contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: '8px' }}
                            labelFormatter={(label) => new Date(label).toLocaleString()}
                          />
                          <Legend />
                          <Line type="monotone" dataKey="trading_vol_iv" stroke="#3B82F6" name="Trading Vol IV (%)" strokeWidth={2} dot={false} />
                          <Line type="monotone" dataKey="trader_realized_vol" stroke="#22C55E" name="Realized Vol 20d (%)" strokeWidth={2} dot={false} />
                          <Line type="monotone" dataKey="vix_level" stroke="#F59E0B" name="VIX" strokeWidth={2} dot={false} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                {/* Full Data Comparison Table - All Expirations */}
                <div className="card">
                  <div className="flex items-center gap-2 mb-4">
                    <BarChart3 className="w-5 h-5 text-primary" />
                    <h2 className="text-lg font-semibold text-text-primary">Full Data Comparison (All Expirations)</h2>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border">
                          <th className="text-left py-3 px-4 text-text-muted font-medium">Metric</th>
                          <th className="text-right py-3 px-4 text-blue-400 font-medium">
                            <div className="flex items-center justify-end gap-1">
                              <ExternalLink className="w-3 h-3" />
                              TradingVol API
                            </div>
                          </th>
                          <th className="text-right py-3 px-4 text-green-400 font-medium">
                            <div className="flex items-center justify-end gap-1">
                              <Database className="w-3 h-3" />
                              Tradier All Exp
                            </div>
                          </th>
                          <th className="text-right py-3 px-4 text-text-muted font-medium">Diff</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr className="border-b border-border/50">
                          <td className="py-2 px-4 text-text-primary">Spot Price</td>
                          <td className="py-2 px-4 text-right font-mono">${formatNumber(comparisonData?.trading_volatility?.spot_price)}</td>
                          <td className="py-2 px-4 text-right font-mono">${formatNumber(comparisonData?.tradier_all_expirations?.spot_price)}</td>
                          <td className="py-2 px-4 text-right font-mono text-text-muted">
                            {comparisonData?.trading_volatility?.spot_price && comparisonData?.tradier_all_expirations?.spot_price
                              ? `$${formatNumber(Math.abs(comparisonData.trading_volatility.spot_price - comparisonData.tradier_all_expirations.spot_price))}` : '--'}
                          </td>
                        </tr>
                        <tr className="border-b border-border/50">
                          <td className="py-2 px-4 text-text-primary">Net GEX</td>
                          <td className="py-2 px-4 text-right font-mono">
                            <span className={(comparisonData?.trading_volatility?.net_gex || 0) >= 0 ? 'text-success' : 'text-danger'}>
                              {formatGamma(comparisonData?.trading_volatility?.net_gex || 0)}
                            </span>
                          </td>
                          <td className="py-2 px-4 text-right font-mono">
                            <span className={(comparisonData?.tradier_all_expirations?.net_gex || 0) >= 0 ? 'text-success' : 'text-danger'}>
                              {formatGamma(comparisonData?.tradier_all_expirations?.net_gex || 0)}
                            </span>
                          </td>
                          <td className="py-2 px-4 text-right font-mono text-text-muted">--</td>
                        </tr>
                        <tr className="border-b border-border/50">
                          <td className="py-2 px-4 text-text-primary">Flip Point</td>
                          <td className="py-2 px-4 text-right font-mono">${formatNumber(comparisonData?.trading_volatility?.flip_point)}</td>
                          <td className="py-2 px-4 text-right font-mono">${formatNumber(comparisonData?.tradier_all_expirations?.flip_point)}</td>
                          <td className="py-2 px-4 text-right font-mono text-text-muted">
                            {comparisonData?.trading_volatility?.flip_point && comparisonData?.tradier_all_expirations?.flip_point
                              ? `$${formatNumber(Math.abs(comparisonData.trading_volatility.flip_point - comparisonData.tradier_all_expirations.flip_point))}` : '--'}
                          </td>
                        </tr>
                        <tr className="border-b border-border/50">
                          <td className="py-2 px-4 text-text-primary">Call Wall</td>
                          <td className="py-2 px-4 text-right font-mono text-success">${formatNumber(comparisonData?.trading_volatility?.call_wall)}</td>
                          <td className="py-2 px-4 text-right font-mono text-success">${formatNumber(comparisonData?.tradier_all_expirations?.call_wall)}</td>
                          <td className="py-2 px-4 text-right font-mono text-text-muted">
                            {comparisonData?.trading_volatility?.call_wall && comparisonData?.tradier_all_expirations?.call_wall
                              ? `$${formatNumber(Math.abs(comparisonData.trading_volatility.call_wall - comparisonData.tradier_all_expirations.call_wall))}` : '--'}
                          </td>
                        </tr>
                        <tr className="border-b border-border/50">
                          <td className="py-2 px-4 text-text-primary">Put Wall</td>
                          <td className="py-2 px-4 text-right font-mono text-danger">${formatNumber(comparisonData?.trading_volatility?.put_wall)}</td>
                          <td className="py-2 px-4 text-right font-mono text-danger">${formatNumber(comparisonData?.tradier_all_expirations?.put_wall)}</td>
                          <td className="py-2 px-4 text-right font-mono text-text-muted">
                            {comparisonData?.trading_volatility?.put_wall && comparisonData?.tradier_all_expirations?.put_wall
                              ? `$${formatNumber(Math.abs(comparisonData.trading_volatility.put_wall - comparisonData.tradier_all_expirations.put_wall))}` : '--'}
                          </td>
                        </tr>
                        <tr className="border-b border-border/50">
                          <td className="py-2 px-4 text-text-primary">Max Pain</td>
                          <td className="py-2 px-4 text-right font-mono">--</td>
                          <td className="py-2 px-4 text-right font-mono">${formatNumber(comparisonData?.tradier_all_expirations?.max_pain)}</td>
                          <td className="py-2 px-4 text-right font-mono text-text-muted">--</td>
                        </tr>
                        <tr className="border-b border-border/50">
                          <td className="py-2 px-4 text-text-primary">P/C Ratio</td>
                          <td className="py-2 px-4 text-right font-mono">--</td>
                          <td className="py-2 px-4 text-right font-mono">{formatNumber(comparisonData?.tradier_all_expirations?.put_call_ratio, 3)}</td>
                          <td className="py-2 px-4 text-right font-mono text-text-muted">--</td>
                        </tr>
                        <tr className="border-b border-border/50">
                          <td className="py-2 px-4 text-text-primary">Implied Vol</td>
                          <td className="py-2 px-4 text-right font-mono">--</td>
                          <td className="py-2 px-4 text-right font-mono">--</td>
                          <td className="py-2 px-4 text-right font-mono text-text-muted">--</td>
                        </tr>
                        <tr className="border-b border-border/50">
                          <td className="py-2 px-4 text-text-primary">Expiration</td>
                          <td className="py-2 px-4 text-right font-mono">{comparisonData?.trading_volatility?.expiration || '--'}</td>
                          <td className="py-2 px-4 text-right font-mono">{comparisonData?.tradier_all_expirations?.expiration || '--'}</td>
                          <td className="py-2 px-4 text-right font-mono text-text-muted">--</td>
                        </tr>
                        <tr className="border-b border-border/50">
                          <td className="py-2 px-4 text-text-primary">Strike Count</td>
                          <td className="py-2 px-4 text-right font-mono">{comparisonData?.trading_volatility?.strikes_count || '--'}</td>
                          <td className="py-2 px-4 text-right font-mono">{comparisonData?.tradier_all_expirations?.strikes_count || '--'}</td>
                          <td className="py-2 px-4 text-right font-mono text-text-muted">
                            {comparisonData?.trading_volatility?.strikes_count && comparisonData?.tradier_all_expirations?.strikes_count
                              ? Math.abs(comparisonData.trading_volatility.strikes_count - comparisonData.tradier_all_expirations.strikes_count) : '--'}
                          </td>
                        </tr>
                        <tr>
                          <td className="py-2 px-4 text-text-primary">Last Updated</td>
                          <td className="py-2 px-4 text-right font-mono text-text-muted text-xs">
                            {comparisonData?.trading_volatility?.timestamp
                              ? new Date(comparisonData.trading_volatility.timestamp).toLocaleTimeString()
                              : comparisonData?.timestamp
                              ? new Date(comparisonData.timestamp).toLocaleTimeString()
                              : '--'}
                          </td>
                          <td className="py-2 px-4 text-right font-mono text-text-muted text-xs">
                            {comparisonData?.tradier_all_expirations?.timestamp
                              ? new Date(comparisonData.tradier_all_expirations.timestamp).toLocaleTimeString()
                              : '--'}
                          </td>
                          <td className="py-2 px-4 text-right font-mono text-text-muted">--</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* VIX Context (supplemental) */}
                {traderCalcs && (
                  <div className="card">
                    <div className="flex items-center gap-2 mb-4">
                      <TrendingUp className="w-5 h-5 text-yellow-400" />
                      <h2 className="text-lg font-semibold text-text-primary">VIX Context (Supplemental)</h2>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      <div className="p-3 bg-background-hover rounded-lg">
                        <p className="text-text-muted text-xs">VIX Spot</p>
                        <p className="text-xl font-bold">{formatNumber(traderCalcs.vix_spot)}</p>
                      </div>
                      <div className="p-3 bg-background-hover rounded-lg">
                        <p className="text-text-muted text-xs">IV Percentile</p>
                        <p className="text-xl font-bold">{formatNumber(traderCalcs.iv_percentile, 0)}th</p>
                      </div>
                      <div className="p-3 bg-background-hover rounded-lg">
                        <p className="text-text-muted text-xs">Realized Vol 20d</p>
                        <p className="text-xl font-bold">{formatNumber(traderCalcs.realized_vol_20d, 1)}%</p>
                      </div>
                      <div className="p-3 bg-background-hover rounded-lg">
                        <p className="text-text-muted text-xs">Term Structure</p>
                        <p className={`text-xl font-bold ${traderCalcs.structure_type === 'contango' ? 'text-success' : 'text-danger'}`}>
                          {traderCalcs.structure_type?.toUpperCase() || '--'}
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Debug Panel - Collapsible */}
                {comparisonData?.trading_volatility?._debug && (
                  <details className="card bg-gray-900/50">
                    <summary className="cursor-pointer flex items-center gap-2 text-text-muted hover:text-text-primary">
                      <AlertTriangle className="w-4 h-4 text-warning" />
                      <span className="font-semibold">Debug Info (TradingVol API)</span>
                      <span className="text-xs ml-2">
                        {comparisonData.trading_volatility._debug.profile_debug?.used_cache ? '(cached)' : '(fresh)'}
                      </span>
                    </summary>
                    <div className="mt-4 text-xs font-mono overflow-x-auto">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="p-3 bg-background-hover rounded-lg">
                          <h4 className="text-warning font-semibold mb-2">Raw API First Strike</h4>
                          <pre className="text-text-muted whitespace-pre-wrap">
{JSON.stringify(comparisonData.trading_volatility._debug.profile_debug?.raw_api_first_strike || 'N/A', null, 2)}
                          </pre>
                        </div>
                        <div className="p-3 bg-background-hover rounded-lg">
                          <h4 className="text-warning font-semibold mb-2">Processed First Strike</h4>
                          <pre className="text-text-muted whitespace-pre-wrap">
{JSON.stringify(comparisonData.trading_volatility._debug.profile_debug?.processed_first_strike || 'N/A', null, 2)}
                          </pre>
                        </div>
                        <div className="p-3 bg-background-hover rounded-lg">
                          <h4 className="text-warning font-semibold mb-2">Profile First Strike Gamma</h4>
                          <pre className="text-text-muted whitespace-pre-wrap">
{JSON.stringify(comparisonData.trading_volatility._debug.profile_first_strike_gamma || 'N/A', null, 2)}
                          </pre>
                        </div>
                        <div className="p-3 bg-background-hover rounded-lg">
                          <h4 className="text-warning font-semibold mb-2">Sample Gamma Values (First 3)</h4>
                          <pre className="text-text-muted whitespace-pre-wrap">
{JSON.stringify(comparisonData.trading_volatility._debug.sample_gamma_values || [], null, 2)}
                          </pre>
                        </div>
                      </div>
                      <div className="mt-3 p-3 bg-background-hover rounded-lg">
                        <h4 className="text-warning font-semibold mb-2">Summary</h4>
                        <ul className="text-text-muted space-y-1">
                          <li>Cache used: <span className={comparisonData.trading_volatility._debug.profile_debug?.used_cache ? 'text-warning' : 'text-success'}>{String(comparisonData.trading_volatility._debug.profile_debug?.used_cache)}</span></li>
                          <li>Strikes before filter: {comparisonData.trading_volatility._debug.profile_debug?.total_strikes_before_filter}</li>
                          <li>Strikes after filter: {comparisonData.trading_volatility._debug.profile_debug?.total_strikes_after_filter}</li>
                          <li>Max call gamma: {comparisonData.trading_volatility._debug.max_call_gamma}</li>
                          <li>Max put gamma: {comparisonData.trading_volatility._debug.max_put_gamma}</li>
                          <li>Calculated call wall: ${comparisonData.trading_volatility._debug.calculated_call_wall}</li>
                          <li>Calculated put wall: ${comparisonData.trading_volatility._debug.calculated_put_wall}</li>
                          <li>Total net GEX: {comparisonData.trading_volatility._debug.total_net_gex_calculated}</li>
                        </ul>
                      </div>
                    </div>
                  </details>
                )}

                {/* Info Footer */}
                <div className="text-center text-text-muted text-sm">
                  <Clock className="w-4 h-4 inline mr-1" />
                  Data refreshes every 5 minutes. 0DTE gamma charts validate Tradier fallback accuracy.
                </div>
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
