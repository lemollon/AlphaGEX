'use client'

import { logger } from '@/lib/logger'

import { useState, useEffect } from 'react'
import { Building2, DollarSign, TrendingUp, TrendingDown, Activity, Shield, AlertTriangle, Target, BarChart3, PieChart, Briefcase, Clock, History } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'

interface SPXStatus {
  symbol: string
  starting_capital: number
  available_capital: number
  max_position_pct: number
  max_delta_exposure: number
  max_contracts_per_trade: number
  greeks: {
    delta: number
    gamma: number
    theta: number
    vega: number
  }
}

interface SPXPerformance {
  total_pnl: number
  realized_pnl: number
  unrealized_pnl: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  avg_win: number
  avg_loss: number
  profit_factor: number
  max_drawdown: number
  sharpe_ratio: number
  tax_treatment?: {
    short_term_gains: number
    long_term_gains: number
    section_1256_gains: number
  }
}

interface TradeLogEntry {
  date: string
  time: string
  action: string
  details: string
  pnl: number
}

interface EquityPoint {
  date: string
  timestamp: number
  pnl: number
  equity: number
  daily_pnl: number
}

export default function SPXInstitutionalTrader() {
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState<SPXStatus | null>(null)
  const [performance, setPerformance] = useState<SPXPerformance | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [failedEndpoints, setFailedEndpoints] = useState<string[]>([])
  const [countdown, setCountdown] = useState<string>('--:--')

  // P&L Chart state
  const [equityCurve, setEquityCurve] = useState<EquityPoint[]>([])
  const [chartPeriod, setChartPeriod] = useState<7 | 30 | 90>(30)

  // Trade Activity state
  const [tradeLog, setTradeLog] = useState<TradeLogEntry[]>([])

  // Live countdown timer - updates every second (5-minute scan intervals)
  useEffect(() => {
    const updateCountdown = () => {
      const now = new Date()
      const minutes = now.getMinutes()
      const seconds = now.getSeconds()

      // Calculate minutes until next 5-minute mark (0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55)
      const nextFiveMin = Math.ceil((minutes + 1) / 5) * 5
      const minutesLeft = nextFiveMin - minutes - 1
      const secondsLeft = 60 - seconds

      // Handle edge case when we're at exactly a 5-minute mark
      if (secondsLeft === 60) {
        setCountdown(`${minutesLeft + 1}:00`)
      } else if (minutesLeft < 0 || (minutesLeft === 0 && secondsLeft === 0)) {
        setCountdown('0:00')
      } else {
        setCountdown(`${minutesLeft}:${secondsLeft.toString().padStart(2, '0')}`)
      }
    }

    // Update immediately
    updateCountdown()

    // Update every second
    const interval = setInterval(updateCountdown, 1000)

    return () => clearInterval(interval)
  }, [])

  // Helper for API calls with error logging
  const fetchWithLogging = async (name: string, apiCall: Promise<any>) => {
    try {
      const res = await apiCall
      if (res?.data?.success === false && res?.data?.error) {
        logger.warn(`SPX ${name}: API returned error:`, res.data.error)
      }
      return res
    } catch (err) {
      logger.error(`SPX ${name}: API call failed:`, err)
      return { data: { success: false, data: null, error: String(err) } }
    }
  }

  // Fetch equity curve when period changes
  useEffect(() => {
    const fetchEquityCurve = async () => {
      const res = await fetchWithLogging('Equity Curve', apiClient.getSPXEquityCurve(chartPeriod))
      if (res.data.success && res.data.data) {
        setEquityCurve(res.data.data)
      }
    }
    fetchEquityCurve()
  }, [chartPeriod])

  // Fetch all SPX data
  const fetchData = async (showLoading = true) => {
    try {
      if (showLoading) setLoading(true)
      const failed: string[] = []

      const [statusRes, perfRes, tradeLogRes, equityCurveRes] = await Promise.all([
        fetchWithLogging('Status', apiClient.getSPXStatus()),
        fetchWithLogging('Performance', apiClient.getSPXPerformance()),
        fetchWithLogging('Trade Log', apiClient.getSPXTradeLog()),
        fetchWithLogging('Equity Curve', apiClient.getSPXEquityCurve(chartPeriod))
      ])

      // Track failures
      if (!statusRes.data?.success) failed.push('Status')
      if (!perfRes.data?.success) failed.push('Performance')
      if (!tradeLogRes.data?.success) failed.push('Trade Log')
      if (!equityCurveRes.data?.success) failed.push('Equity Curve')

      setFailedEndpoints(failed)
      if (failed.length > 0) {
        logger.warn(`SPX data fetch had ${failed.length} failures:`, failed)
      }

      if (statusRes.data.success) {
        setStatus(statusRes.data.data)
      }
      if (perfRes.data.success) {
        setPerformance(perfRes.data.data)
      }
      if (tradeLogRes.data.success) {
        setTradeLog(tradeLogRes.data.data || [])
      }
      if (equityCurveRes.data.success && equityCurveRes.data.data) {
        setEquityCurve(equityCurveRes.data.data)
      }
      setError(null)
    } catch (err: any) {
      logger.error('SPX trader data fetch failed:', err)
      setError(err.message || 'Failed to load SPX trader data')
    } finally {
      setLoading(false)
    }
  }

  // Initial fetch and auto-refresh every 30 seconds
  useEffect(() => {
    fetchData()

    // Auto-refresh every 30 seconds for live trading data
    const interval = setInterval(() => {
      fetchData(false) // Don't show loading spinner for auto-refresh
    }, 30 * 1000)

    return () => clearInterval(interval)
  }, [])

  const formatCurrency = (value: number) => {
    if (value >= 1_000_000_000) {
      return `$${(value / 1_000_000_000).toFixed(2)}B`
    } else if (value >= 1_000_000) {
      return `$${(value / 1_000_000).toFixed(2)}M`
    } else if (value >= 1_000) {
      return `$${(value / 1_000).toFixed(2)}K`
    }
    return `$${value.toFixed(2)}`
  }

  const formatPercent = (value: number) => {
    return `${(value * 100).toFixed(2)}%`
  }

  const formatTradeTime = (date: string, time: string) => {
    if (!date) return 'N/A'
    try {
      return `${date} ${time || ''}`
    } catch {
      return date
    }
  }

  // Calculate best and worst trades
  const bestTrade = tradeLog.length > 0
    ? Math.max(...tradeLog.map(t => t.pnl || 0))
    : 0
  const worstTrade = tradeLog.length > 0
    ? Math.min(...tradeLog.map(t => t.pnl || 0))
    : 0

  return (
    <div className="min-h-screen">
      <Navigation />
      <main className="pt-24 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-3">
                  <Building2 className="w-8 h-8 text-primary" />
                  <h1 className="text-3xl font-bold text-text-primary">SPX Autonomous Trader</h1>
                </div>
                <p className="text-text-secondary mt-1">
                  {status?.starting_capital ? `${formatCurrency(status.starting_capital)} capital management` : 'Institutional capital management'} for SPX index options
                </p>
              </div>
              <div className="flex items-center gap-3">
                {/* Live Countdown Timer */}
                <div className="flex items-center gap-3 px-4 py-2 bg-background-primary rounded-lg border border-border">
                  <Clock className="w-5 h-5 text-warning animate-pulse" />
                  <div>
                    <p className="text-xs text-text-muted">Next Scan In</p>
                    <p className="text-xl font-bold text-warning font-mono">{countdown}</p>
                  </div>
                </div>
                <div className="px-4 py-2 rounded-lg font-semibold bg-primary/20 text-primary">
                  INSTITUTIONAL
                </div>
                <div className="px-4 py-2 rounded-lg font-semibold bg-warning/20 text-warning">
                  SPX OPTIONS
                </div>
              </div>
            </div>

            {/* Data fetch failures indicator for transparency */}
            {failedEndpoints.length > 0 && (
              <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-warning/10 border border-warning/30 text-warning">
                <AlertTriangle className="w-4 h-4" />
                <span className="text-sm">Some data unavailable: {failedEndpoints.join(', ')}</span>
              </div>
            )}

            {/* Info Banner */}
            <div className="p-4 rounded-lg bg-primary/10 border border-primary/30">
              <div className="flex items-start gap-3">
                <Briefcase className="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold text-primary mb-1">Institutional-Grade SPX Trading</p>
                  <p className="text-sm text-text-secondary">
                    This trader manages {status?.starting_capital ? formatCurrency(status.starting_capital) : 'institutional capital'} for SPX index options with risk limits:
                    {status?.max_position_pct ? ` ${(status.max_position_pct * 100).toFixed(0)}%` : ' 5%'} max position size,
                    {status?.max_delta_exposure ? ` ${(status.max_delta_exposure * 100).toFixed(0)}%` : ' 15%'} max delta exposure, 2% daily loss limit.
                    Benefits from 60/40 tax treatment (Section 1256 contracts).
                  </p>
                </div>
              </div>
            </div>

            {loading ? (
              <div className="text-center py-12">
                <Activity className="w-8 h-8 text-primary mx-auto animate-spin" />
                <p className="text-text-secondary mt-2">Loading SPX trader data...</p>
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
                {/* Capital Overview */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  <div className="card">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-text-secondary text-sm">Starting Capital</p>
                        <p className="text-2xl font-bold text-text-primary mt-1">
                          {status?.starting_capital ? formatCurrency(status.starting_capital) : '--'}
                        </p>
                      </div>
                      <Briefcase className="text-primary w-8 h-8" />
                    </div>
                  </div>

                  <div className="card">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-text-secondary text-sm">Available Capital</p>
                        <p className="text-2xl font-bold text-success mt-1">
                          {status ? formatCurrency(status.available_capital) : '--'}
                        </p>
                      </div>
                      <DollarSign className="text-success w-8 h-8" />
                    </div>
                  </div>

                  <div className="card">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-text-secondary text-sm">Total P&L</p>
                        <p className={`text-2xl font-bold mt-1 ${
                          (performance?.total_pnl || 0) >= 0 ? 'text-success' : 'text-danger'
                        }`}>
                          {performance ? formatCurrency(performance.total_pnl) : '--'}
                        </p>
                      </div>
                      {(performance?.total_pnl || 0) >= 0 ? (
                        <TrendingUp className="text-success w-8 h-8" />
                      ) : (
                        <TrendingDown className="text-danger w-8 h-8" />
                      )}
                    </div>
                  </div>

                  <div className="card">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-text-secondary text-sm">Win Rate</p>
                        <p className="text-2xl font-bold text-text-primary mt-1">
                          {performance ? `${performance.win_rate.toFixed(1)}%` : '--'}
                        </p>
                      </div>
                      <Target className="text-primary w-8 h-8" />
                    </div>
                  </div>
                </div>

                {/* P&L Chart */}
                <div className="card">
                  <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center gap-3">
                      <TrendingUp className="w-6 h-6 text-primary" />
                      <h2 className="text-xl font-semibold text-text-primary">P&L Over Time</h2>
                    </div>
                    <div className="flex items-center gap-2">
                      {/* Time Period Selector */}
                      <div className="flex bg-background-hover rounded-lg p-1">
                        {[7, 30, 90].map((days) => (
                          <button
                            key={days}
                            onClick={() => setChartPeriod(days as 7 | 30 | 90)}
                            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                              chartPeriod === days
                                ? 'bg-primary text-white'
                                : 'text-text-secondary hover:text-text-primary'
                            }`}
                          >
                            {days}D
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  {equityCurve.length > 0 ? (
                    <div className="h-80">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={equityCurve} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                          <defs>
                            <linearGradient id="colorPnlSpx" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor={equityCurve[equityCurve.length - 1]?.pnl >= 0 ? "#10b981" : "#ef4444"} stopOpacity={0.3}/>
                              <stop offset="95%" stopColor={equityCurve[equityCurve.length - 1]?.pnl >= 0 ? "#10b981" : "#ef4444"} stopOpacity={0}/>
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                          <XAxis
                            dataKey="date"
                            stroke="#9ca3af"
                            tick={{ fontSize: 12 }}
                            tickLine={false}
                          />
                          <YAxis
                            stroke="#9ca3af"
                            tick={{ fontSize: 12 }}
                            tickLine={false}
                            tickFormatter={(value) => `$${value >= 0 ? '+' : ''}${(value / 1000000).toFixed(1)}M`}
                          />
                          <Tooltip
                            contentStyle={{
                              backgroundColor: '#1f2937',
                              border: '1px solid #374151',
                              borderRadius: '8px',
                              padding: '12px'
                            }}
                            labelStyle={{ color: '#9ca3af' }}
                            formatter={(value: number) => [
                              <span key="value" style={{ color: value >= 0 ? '#10b981' : '#ef4444', fontWeight: 'bold' }}>
                                ${value >= 0 ? '+' : ''}{(value / 1000000).toFixed(2)}M
                              </span>,
                              'P&L'
                            ]}
                          />
                          <ReferenceLine y={0} stroke="#6b7280" strokeDasharray="3 3" />
                          <Area
                            type="monotone"
                            dataKey="pnl"
                            stroke={equityCurve[equityCurve.length - 1]?.pnl >= 0 ? "#10b981" : "#ef4444"}
                            strokeWidth={2}
                            fillOpacity={1}
                            fill="url(#colorPnlSpx)"
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <div className="h-80 flex items-center justify-center">
                      <div className="text-center">
                        <BarChart3 className="w-12 h-12 text-text-muted mx-auto mb-3" />
                        <p className="text-text-secondary">No trading data available yet</p>
                        <p className="text-text-muted text-sm mt-1">P&L chart will appear as trades are executed</p>
                      </div>
                    </div>
                  )}

                  {/* Chart Summary Stats */}
                  {equityCurve.length > 0 && (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-6 border-t border-border">
                      <div className="text-center">
                        <p className="text-text-muted text-xs mb-1">Period Start</p>
                        <p className="text-text-primary font-semibold">
                          {equityCurve[0]?.date || 'N/A'}
                        </p>
                      </div>
                      <div className="text-center">
                        <p className="text-text-muted text-xs mb-1">Period End</p>
                        <p className="text-text-primary font-semibold">
                          {equityCurve[equityCurve.length - 1]?.date || 'N/A'}
                        </p>
                      </div>
                      <div className="text-center">
                        <p className="text-text-muted text-xs mb-1">Total P&L</p>
                        <p className={`font-bold ${equityCurve[equityCurve.length - 1]?.pnl >= 0 ? 'text-success' : 'text-danger'}`}>
                          {equityCurve[equityCurve.length - 1]?.pnl >= 0 ? '+' : ''}
                          {formatCurrency(equityCurve[equityCurve.length - 1]?.pnl || 0)}
                        </p>
                      </div>
                      <div className="text-center">
                        <p className="text-text-muted text-xs mb-1">Current Equity</p>
                        <p className="text-text-primary font-bold">
                          {formatCurrency(equityCurve[equityCurve.length - 1]?.equity || 0)}
                        </p>
                      </div>
                    </div>
                  )}
                </div>

                {/* Risk Limits & Greeks */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Risk Limits */}
                  <div className="card">
                    <div className="flex items-center gap-3 mb-4">
                      <Shield className="w-6 h-6 text-primary" />
                      <h2 className="text-xl font-semibold text-text-primary">Institutional Risk Limits</h2>
                    </div>
                    <div className="space-y-4">
                      <div className="p-4 bg-background-hover rounded-lg">
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-text-secondary">Max Position Size</span>
                          <span className="text-text-primary font-bold">
                            {status ? `${(status.max_position_pct * 100).toFixed(0)}%` : '5%'}
                          </span>
                        </div>
                        <div className="w-full bg-background-primary rounded-full h-2">
                          <div className="bg-primary h-2 rounded-full" style={{ width: '30%' }} />
                        </div>
                        <p className="text-xs text-text-muted mt-1">Current: ~30% of limit</p>
                      </div>

                      <div className="p-4 bg-background-hover rounded-lg">
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-text-secondary">Max Delta Exposure</span>
                          <span className="text-text-primary font-bold">
                            {status ? `${(status.max_delta_exposure * 100).toFixed(0)}%` : '15%'}
                          </span>
                        </div>
                        <div className="w-full bg-background-primary rounded-full h-2">
                          <div className="bg-warning h-2 rounded-full" style={{ width: '45%' }} />
                        </div>
                        <p className="text-xs text-text-muted mt-1">Current: ~45% of limit</p>
                      </div>

                      <div className="p-4 bg-background-hover rounded-lg">
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-text-secondary">Max Contracts/Trade</span>
                          <span className="text-text-primary font-bold">
                            {status?.max_contracts_per_trade || 500}
                          </span>
                        </div>
                        <p className="text-xs text-text-muted">Liquidity constraint for SPX options</p>
                      </div>

                      <div className="p-4 bg-background-hover rounded-lg">
                        <div className="flex justify-between items-center">
                          <span className="text-text-secondary">Daily Loss Limit</span>
                          <span className="text-danger font-bold">2%</span>
                        </div>
                        <p className="text-xs text-text-muted mt-1">
                          {status?.starting_capital ? `${formatCurrency(status.starting_capital * 0.02)} max daily loss on ${formatCurrency(status.starting_capital)}` : '2% of starting capital'}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Portfolio Greeks */}
                  <div className="card">
                    <div className="flex items-center gap-3 mb-4">
                      <BarChart3 className="w-6 h-6 text-primary" />
                      <h2 className="text-xl font-semibold text-text-primary">Portfolio Greeks</h2>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="p-4 bg-background-hover rounded-lg text-center">
                        <p className="text-text-muted text-sm">Delta</p>
                        <p className={`text-2xl font-bold mt-1 ${
                          (status?.greeks?.delta || 0) >= 0 ? 'text-success' : 'text-danger'
                        }`}>
                          {status?.greeks?.delta?.toFixed(2) || '0.00'}
                        </p>
                        <p className="text-xs text-text-muted mt-1">Directional exposure</p>
                      </div>

                      <div className="p-4 bg-background-hover rounded-lg text-center">
                        <p className="text-text-muted text-sm">Gamma</p>
                        <p className="text-2xl font-bold text-primary mt-1">
                          {status?.greeks?.gamma?.toFixed(4) || '0.0000'}
                        </p>
                        <p className="text-xs text-text-muted mt-1">Rate of delta change</p>
                      </div>

                      <div className="p-4 bg-background-hover rounded-lg text-center">
                        <p className="text-text-muted text-sm">Theta</p>
                        <p className={`text-2xl font-bold mt-1 ${
                          (status?.greeks?.theta || 0) >= 0 ? 'text-success' : 'text-danger'
                        }`}>
                          {status?.greeks?.theta ? formatCurrency(status.greeks.theta) : '$0'}
                        </p>
                        <p className="text-xs text-text-muted mt-1">Daily time decay</p>
                      </div>

                      <div className="p-4 bg-background-hover rounded-lg text-center">
                        <p className="text-text-muted text-sm">Vega</p>
                        <p className="text-2xl font-bold text-warning mt-1">
                          {status?.greeks?.vega ? formatCurrency(status.greeks.vega) : '$0'}
                        </p>
                        <p className="text-xs text-text-muted mt-1">Vol sensitivity</p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Performance Stats */}
                {performance && (
                  <div className="card">
                    <div className="flex items-center gap-3 mb-4">
                      <PieChart className="w-6 h-6 text-primary" />
                      <h2 className="text-xl font-semibold text-text-primary">Performance Statistics</h2>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                      <div className="p-3 bg-background-hover rounded-lg text-center">
                        <p className="text-text-muted text-xs">Total Trades</p>
                        <p className="text-xl font-bold text-text-primary mt-1">{performance.total_trades}</p>
                      </div>
                      <div className="p-3 bg-background-hover rounded-lg text-center">
                        <p className="text-text-muted text-xs">Winners</p>
                        <p className="text-xl font-bold text-success mt-1">{performance.winning_trades}</p>
                      </div>
                      <div className="p-3 bg-background-hover rounded-lg text-center">
                        <p className="text-text-muted text-xs">Losers</p>
                        <p className="text-xl font-bold text-danger mt-1">{performance.losing_trades}</p>
                      </div>
                      <div className="p-3 bg-background-hover rounded-lg text-center">
                        <p className="text-text-muted text-xs">Avg Win</p>
                        <p className="text-xl font-bold text-success mt-1">{formatCurrency(performance.avg_win)}</p>
                      </div>
                      <div className="p-3 bg-background-hover rounded-lg text-center">
                        <p className="text-text-muted text-xs">Avg Loss</p>
                        <p className="text-xl font-bold text-danger mt-1">{formatCurrency(performance.avg_loss)}</p>
                      </div>
                      <div className="p-3 bg-background-hover rounded-lg text-center">
                        <p className="text-text-muted text-xs">Profit Factor</p>
                        <p className={`text-xl font-bold mt-1 ${
                          performance.profit_factor >= 1.5 ? 'text-success' :
                          performance.profit_factor >= 1 ? 'text-warning' : 'text-danger'
                        }`}>
                          {performance.profit_factor.toFixed(2)}
                        </p>
                      </div>
                      <div className="p-3 bg-background-hover rounded-lg text-center">
                        <p className="text-text-muted text-xs">Max Drawdown</p>
                        <p className="text-xl font-bold text-danger mt-1">{performance.max_drawdown.toFixed(1)}%</p>
                      </div>
                      <div className="p-3 bg-background-hover rounded-lg text-center">
                        <p className="text-text-muted text-xs">Sharpe Ratio</p>
                        <p className={`text-xl font-bold mt-1 ${
                          performance.sharpe_ratio >= 2 ? 'text-success' :
                          performance.sharpe_ratio >= 1 ? 'text-warning' : 'text-text-primary'
                        }`}>
                          {performance.sharpe_ratio.toFixed(2)}
                        </p>
                      </div>
                      <div className="p-3 bg-background-hover rounded-lg text-center">
                        <p className="text-text-muted text-xs">Realized P&L</p>
                        <p className={`text-xl font-bold mt-1 ${
                          performance.realized_pnl >= 0 ? 'text-success' : 'text-danger'
                        }`}>
                          {formatCurrency(performance.realized_pnl)}
                        </p>
                      </div>
                      <div className="p-3 bg-background-hover rounded-lg text-center">
                        <p className="text-text-muted text-xs">Unrealized P&L</p>
                        <p className={`text-xl font-bold mt-1 ${
                          performance.unrealized_pnl >= 0 ? 'text-success' : 'text-danger'
                        }`}>
                          {formatCurrency(performance.unrealized_pnl)}
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Trade Activity */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  {/* Trade Log */}
                  <div className="lg:col-span-2 card">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <History className="w-6 h-6 text-primary" />
                        <h2 className="text-xl font-semibold text-text-primary">Trade Activity</h2>
                      </div>
                    </div>

                    <div className="overflow-x-auto max-h-96">
                      <table className="w-full">
                        <thead className="sticky top-0 bg-background-primary">
                          <tr className="border-b border-border">
                            <th className="text-left py-3 px-4 text-text-secondary font-medium">Time</th>
                            <th className="text-left py-3 px-4 text-text-secondary font-medium">Action</th>
                            <th className="text-left py-3 px-4 text-text-secondary font-medium">Details</th>
                            <th className="text-right py-3 px-4 text-text-secondary font-medium">P&L</th>
                          </tr>
                        </thead>
                        <tbody>
                          {tradeLog.length > 0 ? (
                            tradeLog.map((entry, idx) => (
                              <tr key={idx} className="border-b border-border/50 hover:bg-background-hover transition-colors">
                                <td className="py-3 px-4 text-text-secondary text-sm">
                                  {formatTradeTime(entry.date, entry.time)}
                                </td>
                                <td className="py-3 px-4">
                                  <span className={`text-sm font-semibold ${
                                    entry.action?.includes('OPEN')
                                      ? 'text-success'
                                      : entry.action?.includes('CLOSE')
                                      ? 'text-danger'
                                      : 'text-warning'
                                  }`}>
                                    {entry.action}
                                  </span>
                                </td>
                                <td className="py-3 px-4 text-text-primary text-sm">{entry.details}</td>
                                <td className="py-3 px-4 text-right">
                                  <span className={`font-semibold ${
                                    (entry.pnl || 0) >= 0 ? 'text-success' : 'text-danger'
                                  }`}>
                                    {(entry.pnl || 0) >= 0 ? '+' : ''}{formatCurrency(entry.pnl || 0)}
                                  </span>
                                </td>
                              </tr>
                            ))
                          ) : (
                            <tr>
                              <td colSpan={4} className="py-8 text-center text-text-secondary">
                                No trade activity yet. Trades will appear here as the SPX trader executes.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Best/Worst Trades */}
                  <div className="space-y-4">
                    <div className="card">
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="text-text-secondary text-sm">Best Trade</h3>
                        <TrendingUp className="w-5 h-5 text-success" />
                      </div>
                      <p className="text-2xl font-bold text-success">
                        {bestTrade >= 0 ? '+' : ''}{formatCurrency(bestTrade)}
                      </p>
                    </div>

                    <div className="card">
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="text-text-secondary text-sm">Worst Trade</h3>
                        <TrendingDown className="w-5 h-5 text-danger" />
                      </div>
                      <p className="text-2xl font-bold text-danger">
                        {worstTrade >= 0 ? '+' : ''}{formatCurrency(worstTrade)}
                      </p>
                    </div>

                    <div className="card">
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="text-text-secondary text-sm">Total Trades</h3>
                        <Activity className="w-5 h-5 text-primary" />
                      </div>
                      <p className="text-2xl font-bold text-text-primary">{tradeLog.length}</p>
                    </div>
                  </div>
                </div>

                {/* Tax Treatment */}
                <div className="card">
                  <div className="flex items-center gap-3 mb-4">
                    <DollarSign className="w-6 h-6 text-success" />
                    <h2 className="text-xl font-semibold text-text-primary">60/40 Tax Treatment (Section 1256)</h2>
                  </div>
                  <div className="p-4 bg-success/10 border border-success/20 rounded-lg">
                    <p className="text-text-primary mb-4">
                      SPX options qualify for Section 1256 tax treatment: <strong>60% long-term</strong> and <strong>40% short-term</strong> capital gains, regardless of holding period.
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="p-3 bg-background-primary rounded-lg text-center">
                        <p className="text-text-muted text-sm">Long-Term (60%)</p>
                        <p className="text-xl font-bold text-success mt-1">
                          {performance?.tax_treatment?.long_term_gains
                            ? formatCurrency(performance.tax_treatment.long_term_gains)
                            : formatCurrency((performance?.total_pnl || 0) * 0.6)}
                        </p>
                        <p className="text-xs text-text-muted mt-1">Max 20% tax rate</p>
                      </div>
                      <div className="p-3 bg-background-primary rounded-lg text-center">
                        <p className="text-text-muted text-sm">Short-Term (40%)</p>
                        <p className="text-xl font-bold text-warning mt-1">
                          {performance?.tax_treatment?.short_term_gains
                            ? formatCurrency(performance.tax_treatment.short_term_gains)
                            : formatCurrency((performance?.total_pnl || 0) * 0.4)}
                        </p>
                        <p className="text-xs text-text-muted mt-1">Ordinary income rate</p>
                      </div>
                      <div className="p-3 bg-background-primary rounded-lg text-center">
                        <p className="text-text-muted text-sm">Blended Rate Savings</p>
                        <p className="text-xl font-bold text-success mt-1">~12%</p>
                        <p className="text-xs text-text-muted mt-1">vs. 100% short-term</p>
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
