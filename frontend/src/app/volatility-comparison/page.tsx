'use client'

import { useState, useEffect, useCallback } from 'react'
import { Activity, TrendingUp, BarChart3, RefreshCw, AlertTriangle, Clock, Zap, ArrowUpDown, Database, ExternalLink, CheckCircle, XCircle } from 'lucide-react'
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend, ReferenceLine } from 'recharts'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'

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
}

interface ComparisonData {
  success: boolean
  symbol: string
  timestamp: string
  trading_volatility: GammaSource | null
  tradier_calculated: GammaSource | null
  errors: string[]
}

interface VIXData {
  vix_spot: number
  vix_m1: number
  vix_m2: number
  term_structure_pct: number
  structure_type: string
  iv_percentile: number
  realized_vol_20d: number
  vol_regime: string
}

export default function VolatilityComparison() {
  const [loading, setLoading] = useState(true)
  const [symbol, setSymbol] = useState('SPY')
  const [comparisonData, setComparisonData] = useState<ComparisonData | null>(null)
  const [vixData, setVixData] = useState<VIXData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)

  const fetchData = useCallback(async (showLoading = true) => {
    try {
      if (showLoading) setLoading(true)
      setError(null)

      // Fetch 0DTE gamma comparison and VIX data in parallel
      const [comparisonRes, vixRes] = await Promise.all([
        apiClient.get0DTEGammaComparison(symbol).catch((e) => ({
          data: { success: false, errors: [e.message] }
        })),
        apiClient.getVIXCurrent().catch((e) => ({
          data: { success: false, error: e.message }
        }))
      ])

      // Process comparison data
      if (comparisonRes.data?.success) {
        setComparisonData(comparisonRes.data)
      } else {
        const errorMsg = comparisonRes.data?.errors?.join('; ') || 'Failed to fetch comparison data'
        setError(errorMsg)
      }

      // Process VIX data
      if (vixRes.data?.success && vixRes.data?.data) {
        setVixData(vixRes.data.data)
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
      }, 5 * 60 * 1000) // 5 minutes
    }

    return () => {
      if (interval) clearInterval(interval)
    }
  }, [fetchData, autoRefresh])

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

  // Prepare chart data - merge both sources for comparison
  const prepareChartData = (source: GammaSource | null, label: string) => {
    if (!source || !source.gamma_array) return []
    return source.gamma_array.map(item => ({
      strike: item.strike,
      [`${label}_call`]: item.call_gamma,
      [`${label}_put`]: -Math.abs(item.put_gamma), // Negative for puts
      [`${label}_net`]: item.total_gamma || item.net_gex || 0
    }))
  }

  const tradingVolChartData = prepareChartData(comparisonData?.trading_volatility || null, 'tv')
  const tradierChartData = prepareChartData(comparisonData?.tradier_calculated || null, 'tr')

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
                  <h1 className="text-3xl font-bold text-text-primary">0DTE Gamma Comparison</h1>
                </div>
                <p className="text-text-secondary mt-1">Compare TradingVolatility API vs Tradier 0DTE NET Gamma</p>
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

            {loading && !comparisonData ? (
              <div className="text-center py-12">
                <Activity className="w-8 h-8 text-primary mx-auto animate-spin" />
                <p className="text-text-secondary mt-2">Loading 0DTE gamma data...</p>
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
                {/* Data Source Status Cards */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* TradingVolatility API Status */}
                  <div className={`card border-l-4 ${comparisonData?.trading_volatility ? 'border-l-blue-500' : 'border-l-gray-500'}`}>
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <ExternalLink className="w-5 h-5 text-blue-400" />
                        <h3 className="font-semibold text-text-primary">TradingVolatility API</h3>
                      </div>
                      {comparisonData?.trading_volatility ? (
                        <span className="flex items-center gap-1 px-2 py-1 rounded bg-success/20 text-success text-xs font-semibold">
                          <CheckCircle className="w-3 h-3" /> ACTIVE
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 px-2 py-1 rounded bg-danger/20 text-danger text-xs font-semibold">
                          <XCircle className="w-3 h-3" /> UNAVAILABLE
                        </span>
                      )}
                    </div>
                    {comparisonData?.trading_volatility && (
                      <div className="grid grid-cols-3 gap-2 text-sm">
                        <div className="p-2 bg-background-hover rounded">
                          <p className="text-text-muted text-xs">Spot</p>
                          <p className="font-semibold">${formatNumber(comparisonData.trading_volatility.spot_price)}</p>
                        </div>
                        <div className="p-2 bg-background-hover rounded">
                          <p className="text-text-muted text-xs">Flip Point</p>
                          <p className="font-semibold">${formatNumber(comparisonData.trading_volatility.flip_point)}</p>
                        </div>
                        <div className="p-2 bg-background-hover rounded">
                          <p className="text-text-muted text-xs">Strikes</p>
                          <p className="font-semibold">{comparisonData.trading_volatility.strikes_count}</p>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Tradier Calculated Status */}
                  <div className={`card border-l-4 ${comparisonData?.tradier_calculated ? 'border-l-green-500' : 'border-l-gray-500'}`}>
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <Database className="w-5 h-5 text-green-400" />
                        <h3 className="font-semibold text-text-primary">Tradier Calculation</h3>
                      </div>
                      {comparisonData?.tradier_calculated ? (
                        <span className="flex items-center gap-1 px-2 py-1 rounded bg-success/20 text-success text-xs font-semibold">
                          <CheckCircle className="w-3 h-3" /> ACTIVE
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 px-2 py-1 rounded bg-danger/20 text-danger text-xs font-semibold">
                          <XCircle className="w-3 h-3" /> UNAVAILABLE
                        </span>
                      )}
                    </div>
                    {comparisonData?.tradier_calculated && (
                      <div className="grid grid-cols-3 gap-2 text-sm">
                        <div className="p-2 bg-background-hover rounded">
                          <p className="text-text-muted text-xs">Spot</p>
                          <p className="font-semibold">${formatNumber(comparisonData.tradier_calculated.spot_price)}</p>
                        </div>
                        <div className="p-2 bg-background-hover rounded">
                          <p className="text-text-muted text-xs">Expiration</p>
                          <p className="font-semibold">{comparisonData.tradier_calculated.expiration || '--'}</p>
                        </div>
                        <div className="p-2 bg-background-hover rounded">
                          <p className="text-text-muted text-xs">Strikes</p>
                          <p className="font-semibold">{comparisonData.tradier_calculated.strikes_count}</p>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Errors Banner */}
                {comparisonData?.errors && comparisonData.errors.length > 0 && (
                  <div className="card bg-warning/10 border-warning/30 border">
                    <div className="flex items-start gap-3">
                      <AlertTriangle className="w-5 h-5 text-warning flex-shrink-0 mt-0.5" />
                      <div>
                        <p className="text-warning font-semibold">Data Source Warnings</p>
                        <ul className="text-text-secondary text-sm mt-1 list-disc list-inside">
                          {comparisonData.errors.map((err, i) => (
                            <li key={i}>{err}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </div>
                )}

                {/* Side-by-Side Gamma Charts */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* TradingVolatility API Chart */}
                  <div className="card">
                    <div className="flex items-center gap-2 mb-4">
                      <BarChart3 className="w-5 h-5 text-blue-400" />
                      <h2 className="text-lg font-semibold text-text-primary">TradingVolatility API - 0DTE Gamma</h2>
                    </div>
                    {tradingVolChartData.length > 0 ? (
                      <div className="h-80">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={tradingVolChartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis
                              dataKey="strike"
                              stroke="#9CA3AF"
                              tick={{ fill: '#9CA3AF', fontSize: 10 }}
                              tickFormatter={(value) => `$${value}`}
                              interval="preserveStartEnd"
                            />
                            <YAxis
                              stroke="#9CA3AF"
                              tick={{ fill: '#9CA3AF', fontSize: 10 }}
                              tickFormatter={(value) => formatGamma(value)}
                            />
                            <Tooltip
                              contentStyle={{
                                backgroundColor: '#1F2937',
                                border: '1px solid #374151',
                                borderRadius: '8px'
                              }}
                              labelStyle={{ color: '#F3F4F6' }}
                              formatter={(value: number, name: string) => [
                                formatGamma(value),
                                name.includes('call') ? 'Call Gamma' : name.includes('put') ? 'Put Gamma' : 'Net Gamma'
                              ]}
                              labelFormatter={(label) => `Strike: $${label}`}
                            />
                            <Bar dataKey="tv_call" fill="#22C55E" name="Call" stackId="stack" />
                            <Bar dataKey="tv_put" fill="#EF4444" name="Put" stackId="stack" />
                            {comparisonData?.trading_volatility?.spot_price && (
                              <ReferenceLine
                                x={comparisonData.trading_volatility.spot_price}
                                stroke="#3B82F6"
                                strokeWidth={2}
                                label={{ value: 'Spot', fill: '#3B82F6', fontSize: 12 }}
                              />
                            )}
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <div className="h-80 flex items-center justify-center text-text-muted">
                        <p>No data available</p>
                      </div>
                    )}
                  </div>

                  {/* Tradier Calculated Chart */}
                  <div className="card">
                    <div className="flex items-center gap-2 mb-4">
                      <BarChart3 className="w-5 h-5 text-green-400" />
                      <h2 className="text-lg font-semibold text-text-primary">Tradier Calculated - 0DTE Gamma</h2>
                    </div>
                    {tradierChartData.length > 0 ? (
                      <div className="h-80">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={tradierChartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis
                              dataKey="strike"
                              stroke="#9CA3AF"
                              tick={{ fill: '#9CA3AF', fontSize: 10 }}
                              tickFormatter={(value) => `$${value}`}
                              interval="preserveStartEnd"
                            />
                            <YAxis
                              stroke="#9CA3AF"
                              tick={{ fill: '#9CA3AF', fontSize: 10 }}
                              tickFormatter={(value) => formatGamma(value)}
                            />
                            <Tooltip
                              contentStyle={{
                                backgroundColor: '#1F2937',
                                border: '1px solid #374151',
                                borderRadius: '8px'
                              }}
                              labelStyle={{ color: '#F3F4F6' }}
                              formatter={(value: number, name: string) => [
                                formatGamma(value),
                                name.includes('call') ? 'Call Gamma' : name.includes('put') ? 'Put Gamma' : 'Net Gamma'
                              ]}
                              labelFormatter={(label) => `Strike: $${label}`}
                            />
                            <Bar dataKey="tr_call" fill="#22C55E" name="Call" stackId="stack" />
                            <Bar dataKey="tr_put" fill="#EF4444" name="Put" stackId="stack" />
                            {comparisonData?.tradier_calculated?.spot_price && (
                              <ReferenceLine
                                x={comparisonData.tradier_calculated.spot_price}
                                stroke="#3B82F6"
                                strokeWidth={2}
                                label={{ value: 'Spot', fill: '#3B82F6', fontSize: 12 }}
                              />
                            )}
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <div className="h-80 flex items-center justify-center text-text-muted">
                        <p>No data available</p>
                      </div>
                    )}
                  </div>
                </div>

                {/* Key Levels Comparison Table */}
                {(comparisonData?.trading_volatility || comparisonData?.tradier_calculated) && (
                  <div className="card">
                    <div className="flex items-center gap-2 mb-4">
                      <Zap className="w-5 h-5 text-primary" />
                      <h2 className="text-lg font-semibold text-text-primary">Key Levels Comparison</h2>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-border">
                            <th className="text-left py-3 px-4 text-text-muted font-medium">Metric</th>
                            <th className="text-right py-3 px-4 text-blue-400 font-medium">TradingVol API</th>
                            <th className="text-right py-3 px-4 text-green-400 font-medium">Tradier Calc</th>
                            <th className="text-right py-3 px-4 text-text-muted font-medium">Difference</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr className="border-b border-border/50">
                            <td className="py-3 px-4 text-text-primary">Spot Price</td>
                            <td className="py-3 px-4 text-right font-mono">
                              ${formatNumber(comparisonData?.trading_volatility?.spot_price)}
                            </td>
                            <td className="py-3 px-4 text-right font-mono">
                              ${formatNumber(comparisonData?.tradier_calculated?.spot_price)}
                            </td>
                            <td className="py-3 px-4 text-right font-mono text-text-muted">
                              {comparisonData?.trading_volatility?.spot_price && comparisonData?.tradier_calculated?.spot_price
                                ? `$${formatNumber(Math.abs(comparisonData.trading_volatility.spot_price - comparisonData.tradier_calculated.spot_price))}`
                                : '--'}
                            </td>
                          </tr>
                          <tr className="border-b border-border/50">
                            <td className="py-3 px-4 text-text-primary">Flip Point</td>
                            <td className="py-3 px-4 text-right font-mono">
                              ${formatNumber(comparisonData?.trading_volatility?.flip_point)}
                            </td>
                            <td className="py-3 px-4 text-right font-mono">
                              ${formatNumber(comparisonData?.tradier_calculated?.flip_point)}
                            </td>
                            <td className="py-3 px-4 text-right font-mono text-text-muted">
                              {comparisonData?.trading_volatility?.flip_point && comparisonData?.tradier_calculated?.flip_point
                                ? `$${formatNumber(Math.abs(comparisonData.trading_volatility.flip_point - comparisonData.tradier_calculated.flip_point))}`
                                : '--'}
                            </td>
                          </tr>
                          <tr className="border-b border-border/50">
                            <td className="py-3 px-4 text-text-primary">Call Wall</td>
                            <td className="py-3 px-4 text-right font-mono text-success">
                              ${formatNumber(comparisonData?.trading_volatility?.call_wall)}
                            </td>
                            <td className="py-3 px-4 text-right font-mono text-success">
                              ${formatNumber(comparisonData?.tradier_calculated?.call_wall)}
                            </td>
                            <td className="py-3 px-4 text-right font-mono text-text-muted">
                              {comparisonData?.trading_volatility?.call_wall && comparisonData?.tradier_calculated?.call_wall
                                ? `$${formatNumber(Math.abs(comparisonData.trading_volatility.call_wall - comparisonData.tradier_calculated.call_wall))}`
                                : '--'}
                            </td>
                          </tr>
                          <tr className="border-b border-border/50">
                            <td className="py-3 px-4 text-text-primary">Put Wall</td>
                            <td className="py-3 px-4 text-right font-mono text-danger">
                              ${formatNumber(comparisonData?.trading_volatility?.put_wall)}
                            </td>
                            <td className="py-3 px-4 text-right font-mono text-danger">
                              ${formatNumber(comparisonData?.tradier_calculated?.put_wall)}
                            </td>
                            <td className="py-3 px-4 text-right font-mono text-text-muted">
                              {comparisonData?.trading_volatility?.put_wall && comparisonData?.tradier_calculated?.put_wall
                                ? `$${formatNumber(Math.abs(comparisonData.trading_volatility.put_wall - comparisonData.tradier_calculated.put_wall))}`
                                : '--'}
                            </td>
                          </tr>
                          <tr>
                            <td className="py-3 px-4 text-text-primary">Strike Count</td>
                            <td className="py-3 px-4 text-right font-mono">
                              {comparisonData?.trading_volatility?.strikes_count || '--'}
                            </td>
                            <td className="py-3 px-4 text-right font-mono">
                              {comparisonData?.tradier_calculated?.strikes_count || '--'}
                            </td>
                            <td className="py-3 px-4 text-right font-mono text-text-muted">
                              {comparisonData?.trading_volatility?.strikes_count && comparisonData?.tradier_calculated?.strikes_count
                                ? Math.abs(comparisonData.trading_volatility.strikes_count - comparisonData.tradier_calculated.strikes_count)
                                : '--'}
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* VIX Context Card */}
                {vixData && (
                  <div className="card">
                    <div className="flex items-center gap-2 mb-4">
                      <TrendingUp className="w-5 h-5 text-yellow-400" />
                      <h2 className="text-lg font-semibold text-text-primary">VIX Context</h2>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div className="p-3 bg-background-hover rounded-lg">
                        <p className="text-text-muted text-xs mb-1">VIX Spot</p>
                        <p className={`text-2xl font-bold ${
                          vixData.vix_spot > 25 ? 'text-danger' :
                          vixData.vix_spot > 18 ? 'text-warning' : 'text-success'
                        }`}>
                          {formatNumber(vixData.vix_spot, 1)}
                        </p>
                      </div>
                      <div className="p-3 bg-background-hover rounded-lg">
                        <p className="text-text-muted text-xs mb-1">Vol Regime</p>
                        <span className={`inline-block px-2 py-1 rounded text-sm font-semibold ${getVolRegimeColor(vixData.vol_regime)}`}>
                          {vixData.vol_regime?.toUpperCase().replace('_', ' ') || 'N/A'}
                        </span>
                      </div>
                      <div className="p-3 bg-background-hover rounded-lg">
                        <p className="text-text-muted text-xs mb-1">Term Structure</p>
                        <p className={`text-xl font-bold ${
                          vixData.structure_type === 'contango' ? 'text-success' : 'text-danger'
                        }`}>
                          {vixData.structure_type?.toUpperCase() || '--'}
                        </p>
                        <p className="text-text-muted text-xs">
                          {vixData.term_structure_pct > 0 ? '+' : ''}{formatNumber(vixData.term_structure_pct, 1)}%
                        </p>
                      </div>
                      <div className="p-3 bg-background-hover rounded-lg">
                        <p className="text-text-muted text-xs mb-1">IV Percentile</p>
                        <p className="text-xl font-bold text-text-primary">
                          {formatNumber(vixData.iv_percentile, 0)}th
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Info Footer */}
                <div className="text-center text-text-muted text-sm">
                  <Clock className="w-4 h-4 inline mr-1" />
                  Data refreshes every 5 minutes. Both charts should show nearly identical patterns if calculations are correct.
                </div>
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
