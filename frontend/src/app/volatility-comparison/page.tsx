'use client'

import { useState, useEffect, useCallback } from 'react'
import { Activity, TrendingUp, TrendingDown, BarChart3, RefreshCw, AlertTriangle, Clock, Zap, Target, ArrowUpDown, Database, ExternalLink } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, ReferenceLine, BarChart, Bar, Legend, ComposedChart } from 'recharts'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'

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
  gamma_array?: Array<{
    strike: number
    call_gamma: number
    put_gamma: number
    total_gamma: number
  }>
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

interface GEXLevelData {
  strike: number
  call_gex: number
  put_gex: number
  total_gex: number
}

interface ComparisonHistory {
  timestamp: string
  trading_vol_iv: number
  trader_realized_vol: number
  vix_level: number
  spread: number
}

export default function VolatilityComparison() {
  const [loading, setLoading] = useState(true)
  const [symbol, setSymbol] = useState('SPY')
  const [tradingVolData, setTradingVolData] = useState<TradingVolData | null>(null)
  const [traderCalcs, setTraderCalcs] = useState<TraderCalculations | null>(null)
  const [gexLevels, setGexLevels] = useState<GEXLevelData[]>([])
  const [comparisonHistory, setComparisonHistory] = useState<ComparisonHistory[]>([])
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [usingFallback, setUsingFallback] = useState(false)
  const [tradingVolError, setTradingVolError] = useState<string | null>(null)

  const fetchData = useCallback(async (showLoading = true) => {
    try {
      if (showLoading) setLoading(true)
      setError(null)
      setTradingVolError(null)

      // Fetch all data in parallel
      const [gexRes, vixRes, levelsRes] = await Promise.all([
        apiClient.getGEX(symbol).catch((e) => ({ data: { success: false, error: e.message } })),
        apiClient.getVIXCurrent().catch((e) => ({ data: { success: false, error: e.message } })),
        apiClient.getGEXLevels(symbol).catch((e) => ({ data: { success: false, data: [] } }))
      ])

      // Check if Trading Volatility API succeeded
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
          collection_date: data.collection_date || new Date().toISOString(),
          gamma_array: data.gamma_array || []
        })
        setUsingFallback(false)
      } else {
        // Trading Vol API failed - set error and mark as using fallback
        setTradingVolData(null)
        setTradingVolError(gexRes.data?.error || 'Trading Volatility API unavailable')
        setUsingFallback(true)
      }

      // Trader calculations (VIX-based) - FALLBACK SOURCE
      if (traderCalcsSuccess) {
        setTraderCalcs(vixRes.data.data)
      }

      // GEX Levels for strike chart
      if (levelsRes.data?.success && levelsRes.data?.data) {
        const levels = Array.isArray(levelsRes.data.data) ? levelsRes.data.data : levelsRes.data.data.levels || []
        setGexLevels(levels.slice(0, 30)) // Top 30 levels
      }

      // Build comparison history
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
        // Keep last 50 data points
        return newHistory.slice(-50)
      })

      // Only set error if BOTH sources failed
      if (!tradingVolSuccess && !traderCalcsSuccess) {
        setError('Both Trading Volatility API and Trader calculations unavailable')
      }

      setLastUpdated(new Date())
    } catch (err: any) {
      setError(err.message || 'Failed to load volatility data')
    } finally {
      setLoading(false)
    }
  }, [symbol])

  // Initial fetch and auto-refresh
  useEffect(() => {
    fetchData()

    let interval: NodeJS.Timeout | null = null
    if (autoRefresh) {
      // Auto-refresh every 5 minutes
      interval = setInterval(() => {
        fetchData(false)
      }, 5 * 60 * 1000)
    }

    return () => {
      if (interval) clearInterval(interval)
    }
  }, [fetchData, autoRefresh])

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

  // Calculate spread between Trading Vol IV and realized vol
  const ivRvSpread = tradingVolData && traderCalcs
    ? ((tradingVolData.implied_volatility * 100) - traderCalcs.realized_vol_20d).toFixed(2)
    : '--'

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
                {/* Symbol Selector */}
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

                {/* Auto-refresh toggle */}
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

                {/* Active Data Source Indicator */}
                <div className="card bg-background-hover">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`w-3 h-3 rounded-full ${usingFallback ? 'bg-warning' : 'bg-success'} animate-pulse`}></div>
                      <span className="text-text-primary font-semibold">Active Data Source:</span>
                      <span className={`px-3 py-1 rounded-full text-sm font-semibold ${
                        usingFallback
                          ? 'bg-green-500/20 text-green-400'
                          : 'bg-blue-500/20 text-blue-400'
                      }`}>
                        {usingFallback ? 'Trader Calculations (Fallback)' : 'Trading Volatility API (Primary)'}
                      </span>
                    </div>
                    <div className="text-xs text-text-muted">
                      {usingFallback ? 'VIX-based internal calculations' : 'External GEX data provider'}
                    </div>
                  </div>
                </div>

                {/* Source Labels */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className={`card bg-gradient-to-r ${
                    !usingFallback
                      ? 'from-blue-900/20 to-transparent border-blue-500/30'
                      : 'from-gray-900/20 to-transparent border-gray-500/30 opacity-50'
                  }`}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <ExternalLink className={`w-5 h-5 ${!usingFallback ? 'text-blue-400' : 'text-gray-400'}`} />
                        <h2 className={`text-lg font-semibold ${!usingFallback ? 'text-blue-400' : 'text-gray-400'}`}>
                          Trading Volatility API
                        </h2>
                      </div>
                      <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                        !usingFallback
                          ? 'bg-success/20 text-success'
                          : 'bg-danger/20 text-danger'
                      }`}>
                        {!usingFallback ? 'ACTIVE' : 'UNAVAILABLE'}
                      </span>
                    </div>
                    <p className="text-text-secondary text-sm">
                      {!usingFallback
                        ? 'Primary source - GEX, IV, walls, gamma profiles'
                        : tradingVolError || 'API connection failed'}
                    </p>
                  </div>
                  <div className={`card bg-gradient-to-r ${
                    usingFallback
                      ? 'from-green-900/20 to-transparent border-green-500/30'
                      : 'from-green-900/10 to-transparent border-green-500/20'
                  }`}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Database className="w-5 h-5 text-green-400" />
                        <h2 className="text-lg font-semibold text-green-400">Trader Calculations</h2>
                      </div>
                      <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                        usingFallback
                          ? 'bg-warning/20 text-warning'
                          : 'bg-primary/20 text-primary'
                      }`}>
                        {usingFallback ? 'FALLBACK ACTIVE' : 'STANDBY'}
                      </span>
                    </div>
                    <p className="text-text-secondary text-sm">
                      {usingFallback
                        ? 'Active fallback - VIX, realized vol, IV percentile'
                        : 'Ready as fallback - VIX-based calculations'}
                    </p>
                  </div>
                </div>

                {/* Main Comparison Cards */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  {/* Trading Vol: Implied Volatility */}
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

                  {/* Trader: Realized Volatility */}
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

                  {/* VIX Spot */}
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

                  {/* IV-RV Spread Comparison */}
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
                  {/* Trading Vol GEX Data */}
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

                  {/* Trader VIX Term Structure */}
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

                {/* GEX Profile Chart - Trading Vol Data */}
                {gexLevels.length > 0 && (
                  <div className="card">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-2">
                        <BarChart3 className="w-5 h-5 text-primary" />
                        <h2 className="text-xl font-semibold text-text-primary">GEX Profile by Strike</h2>
                        <span className="text-xs px-2 py-0.5 rounded bg-blue-500/20 text-blue-400">Trading Vol API</span>
                      </div>
                      <div className="flex items-center gap-4 text-sm">
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 rounded bg-success"></div>
                          <span className="text-text-secondary">Call GEX</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 rounded bg-danger"></div>
                          <span className="text-text-secondary">Put GEX</span>
                        </div>
                      </div>
                    </div>

                    <div className="h-80">
                      <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={gexLevels} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                          <XAxis
                            dataKey="strike"
                            stroke="#9CA3AF"
                            tick={{ fill: '#9CA3AF', fontSize: 11 }}
                            tickFormatter={(value) => `$${value}`}
                          />
                          <YAxis
                            stroke="#9CA3AF"
                            tick={{ fill: '#9CA3AF', fontSize: 11 }}
                            tickFormatter={(value) => `${(value / 1e9).toFixed(1)}B`}
                          />
                          <Tooltip
                            contentStyle={{
                              backgroundColor: '#1F2937',
                              border: '1px solid #374151',
                              borderRadius: '8px'
                            }}
                            labelStyle={{ color: '#F3F4F6' }}
                            formatter={(value: number, name: string) => [
                              `${(value / 1e9).toFixed(3)}B`,
                              name === 'call_gex' ? 'Call GEX' : name === 'put_gex' ? 'Put GEX' : 'Total GEX'
                            ]}
                            labelFormatter={(label) => `Strike: $${label}`}
                          />
                          <Bar dataKey="call_gex" fill="#22C55E" name="Call GEX" />
                          <Bar dataKey="put_gex" fill="#EF4444" name="Put GEX" />
                          {tradingVolData?.flip_point && (
                            <ReferenceLine
                              x={tradingVolData.flip_point}
                              stroke="#F59E0B"
                              strokeDasharray="5 5"
                              label={{ value: 'Flip', fill: '#F59E0B', fontSize: 12 }}
                            />
                          )}
                          {tradingVolData?.spot_price && (
                            <ReferenceLine
                              x={tradingVolData.spot_price}
                              stroke="#3B82F6"
                              strokeWidth={2}
                              label={{ value: 'Spot', fill: '#3B82F6', fontSize: 12 }}
                            />
                          )}
                        </ComposedChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
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
                          <YAxis
                            stroke="#9CA3AF"
                            tick={{ fill: '#9CA3AF', fontSize: 11 }}
                            domain={['auto', 'auto']}
                          />
                          <Tooltip
                            contentStyle={{
                              backgroundColor: '#1F2937',
                              border: '1px solid #374151',
                              borderRadius: '8px'
                            }}
                            labelStyle={{ color: '#F3F4F6' }}
                            labelFormatter={(label) => new Date(label).toLocaleString()}
                          />
                          <Legend />
                          <Line
                            type="monotone"
                            dataKey="trading_vol_iv"
                            stroke="#3B82F6"
                            name="Trading Vol IV (%)"
                            strokeWidth={2}
                            dot={false}
                          />
                          <Line
                            type="monotone"
                            dataKey="trader_realized_vol"
                            stroke="#22C55E"
                            name="Realized Vol 20d (%)"
                            strokeWidth={2}
                            dot={false}
                          />
                          <Line
                            type="monotone"
                            dataKey="vix_level"
                            stroke="#F59E0B"
                            name="VIX"
                            strokeWidth={2}
                            dot={false}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                {/* Data Source Details */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <div className="card">
                    <h3 className="text-lg font-semibold text-text-primary mb-3 flex items-center gap-2">
                      <ExternalLink className="w-4 h-4 text-blue-400" />
                      Trading Volatility API Details
                    </h3>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between py-2 border-b border-border">
                        <span className="text-text-secondary">Collection Date</span>
                        <span className="text-text-primary font-mono">{tradingVolData?.collection_date || '--'}</span>
                      </div>
                      <div className="flex justify-between py-2 border-b border-border">
                        <span className="text-text-secondary">Spot Price</span>
                        <span className="text-text-primary font-mono">${formatNumber(tradingVolData?.spot_price)}</span>
                      </div>
                      <div className="flex justify-between py-2 border-b border-border">
                        <span className="text-text-secondary">Implied Volatility</span>
                        <span className="text-text-primary font-mono">{formatNumber((tradingVolData?.implied_volatility || 0) * 100, 1)}%</span>
                      </div>
                      <div className="flex justify-between py-2 border-b border-border">
                        <span className="text-text-secondary">Net GEX</span>
                        <span className={`font-mono ${(tradingVolData?.net_gex || 0) >= 0 ? 'text-success' : 'text-danger'}`}>
                          {formatNumber(tradingVolData?.net_gex, 2)}B
                        </span>
                      </div>
                      <div className="flex justify-between py-2">
                        <span className="text-text-secondary">P/C Ratio</span>
                        <span className="text-text-primary font-mono">{formatNumber(tradingVolData?.put_call_ratio, 3)}</span>
                      </div>
                    </div>
                  </div>

                  <div className="card">
                    <h3 className="text-lg font-semibold text-text-primary mb-3 flex items-center gap-2">
                      <Database className="w-4 h-4 text-green-400" />
                      Trader Calculation Details
                    </h3>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between py-2 border-b border-border">
                        <span className="text-text-secondary">VIX Spot</span>
                        <span className="text-text-primary font-mono">{formatNumber(traderCalcs?.vix_spot)}</span>
                      </div>
                      <div className="flex justify-between py-2 border-b border-border">
                        <span className="text-text-secondary">IV Percentile</span>
                        <span className="text-text-primary font-mono">{formatNumber(traderCalcs?.iv_percentile, 0)}th</span>
                      </div>
                      <div className="flex justify-between py-2 border-b border-border">
                        <span className="text-text-secondary">Realized Vol (20d)</span>
                        <span className="text-text-primary font-mono">{formatNumber(traderCalcs?.realized_vol_20d, 1)}%</span>
                      </div>
                      <div className="flex justify-between py-2 border-b border-border">
                        <span className="text-text-secondary">IV-RV Spread</span>
                        <span className={`font-mono ${
                          (traderCalcs?.iv_rv_spread || 0) > 5 ? 'text-warning' :
                          (traderCalcs?.iv_rv_spread || 0) < 0 ? 'text-success' : 'text-text-primary'
                        }`}>
                          {formatNumber(traderCalcs?.iv_rv_spread, 1)} pts
                        </span>
                      </div>
                      <div className="flex justify-between py-2">
                        <span className="text-text-secondary">Term Structure</span>
                        <span className={`font-mono ${
                          traderCalcs?.structure_type === 'contango' ? 'text-success' : 'text-danger'
                        }`}>
                          {traderCalcs?.structure_type?.toUpperCase() || '--'}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
