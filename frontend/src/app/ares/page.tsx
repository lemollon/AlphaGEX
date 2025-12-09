'use client'

import { useState, useEffect } from 'react'
import { Zap, TrendingUp, TrendingDown, Activity, DollarSign, Target, AlertTriangle, CheckCircle, Clock, RefreshCw, BarChart3 } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import Navigation from '@/components/Navigation'
import DecisionLogViewer from '@/components/trader/DecisionLogViewer'
import { apiClient } from '@/lib/api'

interface ARESStatus {
  mode: string
  capital: number
  total_pnl: number
  trade_count: number
  win_rate: number
  open_positions: number
  traded_today: boolean
  in_trading_window: boolean
  current_time: string
  is_active: boolean
  config: {
    risk_per_trade: number
    spread_width: number
    sd_multiplier: number
    ticker: string
  }
}

interface IronCondorPosition {
  position_id: string
  open_date: string
  expiration: string
  put_long_strike: number
  put_short_strike: number
  call_short_strike: number
  call_long_strike: number
  total_credit: number
  max_loss: number
  contracts: number
  underlying_price_at_entry: number
  vix_at_entry: number
}

interface EquityPoint {
  date: string
  equity: number
  pnl: number
}

interface Performance {
  total_pnl: number
  today_pnl: number
  win_rate: number
  total_trades: number
  max_drawdown: number
  starting_capital: number
  current_value: number
  return_pct: number
}

export default function ARESPage() {
  const [status, setStatus] = useState<ARESStatus | null>(null)
  const [positions, setPositions] = useState<IronCondorPosition[]>([])
  const [equityData, setEquityData] = useState<EquityPoint[]>([])
  const [performance, setPerformance] = useState<Performance | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date())

  const fetchData = async () => {
    try {
      setLoading(true)
      setError(null)

      // Fetch ARES status from dedicated ARES API endpoints
      const [statusRes, performanceRes, equityRes, positionsRes] = await Promise.all([
        apiClient.get('/api/ares/status').catch(() => ({ data: null })),
        apiClient.get('/api/ares/performance').catch(() => ({ data: null })),
        apiClient.get('/api/ares/equity-curve?days=30').catch(() => ({ data: null })),
        apiClient.get('/api/ares/positions').catch(() => ({ data: null }))
      ])

      // Extract data from API responses (all use { success: true, data: {...} } format)
      if (statusRes.data?.data) setStatus(statusRes.data.data)
      if (performanceRes.data?.data) setPerformance(performanceRes.data.data)
      if (equityRes.data?.data?.equity_curve) setEquityData(equityRes.data.data.equity_curve)
      if (positionsRes.data?.data?.open_positions) setPositions(positionsRes.data.data.open_positions)

      setLastUpdate(new Date())
    } catch (err) {
      setError('Failed to fetch ARES data')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000) // Refresh every 30s
    return () => clearInterval(interval)
  }, [])

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(value)
  }

  const formatPercent = (value: number) => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
  }

  return (
    <div className="min-h-screen bg-gray-900">
      <Navigation />
      <main className="lg:pl-64 pt-16 lg:pt-0">
        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Zap className="w-8 h-8 text-red-500" />
              <div>
                <h1 className="text-2xl font-bold text-white">ARES - Aggressive Iron Condor</h1>
                <p className="text-gray-400">Targeting 10% Monthly Returns via Daily SPX Iron Condors</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <button
                onClick={fetchData}
                className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
              <span className="text-sm text-gray-500">
                Last update: {lastUpdate.toLocaleTimeString()}
              </span>
            </div>
          </div>

          {error && (
            <div className="mb-6 p-4 bg-red-900/50 border border-red-500 rounded-lg text-red-300">
              {error}
            </div>
          )}

          {/* Status Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            {/* Mode Status */}
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <div className="flex items-center justify-between">
                <span className="text-gray-400">Mode</span>
                <span className={`px-2 py-1 rounded text-sm font-medium ${
                  status?.mode === 'live' ? 'bg-green-900 text-green-300' : 'bg-yellow-900 text-yellow-300'
                }`}>
                  {status?.mode?.toUpperCase() || 'PAPER'}
                </span>
              </div>
              <div className="mt-2 flex items-center gap-2">
                {status?.in_trading_window ? (
                  <CheckCircle className="w-4 h-4 text-green-500" />
                ) : (
                  <Clock className="w-4 h-4 text-gray-500" />
                )}
                <span className="text-sm text-gray-300">
                  {status?.in_trading_window ? 'In Trading Window' : 'Outside Window'}
                </span>
              </div>
            </div>

            {/* Capital */}
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <div className="flex items-center justify-between">
                <span className="text-gray-400">Capital</span>
                <DollarSign className="w-5 h-5 text-blue-500" />
              </div>
              <div className="mt-2">
                <span className="text-2xl font-bold text-white">
                  {formatCurrency(status?.capital || 200000)}
                </span>
              </div>
            </div>

            {/* Total P&L */}
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <div className="flex items-center justify-between">
                <span className="text-gray-400">Total P&L</span>
                {(performance?.total_pnl || 0) >= 0 ? (
                  <TrendingUp className="w-5 h-5 text-green-500" />
                ) : (
                  <TrendingDown className="w-5 h-5 text-red-500" />
                )}
              </div>
              <div className="mt-2">
                <span className={`text-2xl font-bold ${
                  (performance?.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                }`}>
                  {formatCurrency(performance?.total_pnl || status?.total_pnl || 0)}
                </span>
              </div>
            </div>

            {/* Win Rate */}
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <div className="flex items-center justify-between">
                <span className="text-gray-400">Win Rate</span>
                <Target className="w-5 h-5 text-purple-500" />
              </div>
              <div className="mt-2">
                <span className="text-2xl font-bold text-white">
                  {(performance?.win_rate || status?.win_rate || 0).toFixed(1)}%
                </span>
                <span className="text-sm text-gray-500 ml-2">
                  ({performance?.total_trades || status?.trade_count || 0} trades)
                </span>
              </div>
            </div>
          </div>

          {/* Strategy Info */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <h3 className="text-lg font-semibold text-white mb-3">Strategy Parameters</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">Ticker</span>
                  <span className="text-white font-mono">{status?.config?.ticker || 'SPX'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Spread Width</span>
                  <span className="text-white">${status?.config?.spread_width || 10}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Risk Per Trade</span>
                  <span className="text-white">{status?.config?.risk_per_trade || 10}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Target</span>
                  <span className="text-green-400">10% Monthly</span>
                </div>
              </div>
            </div>

            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <h3 className="text-lg font-semibold text-white mb-3">Today&apos;s Status</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">Traded Today</span>
                  <span className={status?.traded_today ? 'text-green-400' : 'text-yellow-400'}>
                    {status?.traded_today ? 'Yes' : 'Not Yet'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Open Positions</span>
                  <span className="text-white">{status?.open_positions || positions.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Current Time (ET)</span>
                  <span className="text-white font-mono">
                    {status?.current_time || new Date().toLocaleTimeString('en-US', { timeZone: 'America/New_York' })}
                  </span>
                </div>
              </div>
            </div>

            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <h3 className="text-lg font-semibold text-white mb-3">Performance Metrics</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">Return</span>
                  <span className={`${(performance?.return_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {formatPercent(performance?.return_pct || 0)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Max Drawdown</span>
                  <span className="text-red-400">
                    {formatPercent(-(performance?.max_drawdown || 0))}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Today P&L</span>
                  <span className={`${(performance?.today_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {formatCurrency(performance?.today_pnl || 0)}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Equity Curve */}
          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700 mb-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-blue-500" />
                Equity Curve (30 Days)
              </h3>
            </div>
            <div className="h-64">
              {equityData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={equityData}>
                    <defs>
                      <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10B981" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#10B981" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis dataKey="date" stroke="#9CA3AF" fontSize={12} />
                    <YAxis stroke="#9CA3AF" fontSize={12} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                      labelStyle={{ color: '#9CA3AF' }}
                      formatter={(value: number) => [formatCurrency(value), 'Equity']}
                    />
                    <Area
                      type="monotone"
                      dataKey="equity"
                      stroke="#10B981"
                      strokeWidth={2}
                      fill="url(#colorEquity)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex items-center justify-center h-full text-gray-500">
                  No equity data available yet
                </div>
              )}
            </div>
          </div>

          {/* Open Positions */}
          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700 mb-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Activity className="w-5 h-5 text-yellow-500" />
              Open Iron Condor Positions
            </h3>
            {positions.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-gray-400 border-b border-gray-700">
                      <th className="text-left py-2 px-3">Position ID</th>
                      <th className="text-left py-2 px-3">Opened</th>
                      <th className="text-left py-2 px-3">Expiration</th>
                      <th className="text-center py-2 px-3">Put Spread</th>
                      <th className="text-center py-2 px-3">Call Spread</th>
                      <th className="text-right py-2 px-3">Credit</th>
                      <th className="text-right py-2 px-3">Max Loss</th>
                      <th className="text-right py-2 px-3">Contracts</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((pos) => (
                      <tr key={pos.position_id} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                        <td className="py-2 px-3 font-mono text-white">{pos.position_id}</td>
                        <td className="py-2 px-3 text-gray-300">{pos.open_date}</td>
                        <td className="py-2 px-3 text-gray-300">{pos.expiration}</td>
                        <td className="py-2 px-3 text-center">
                          <span className="text-red-400">{pos.put_long_strike}</span>
                          <span className="text-gray-500 mx-1">/</span>
                          <span className="text-red-300">{pos.put_short_strike}</span>
                        </td>
                        <td className="py-2 px-3 text-center">
                          <span className="text-green-300">{pos.call_short_strike}</span>
                          <span className="text-gray-500 mx-1">/</span>
                          <span className="text-green-400">{pos.call_long_strike}</span>
                        </td>
                        <td className="py-2 px-3 text-right text-green-400">
                          {formatCurrency(pos.total_credit * 100 * pos.contracts)}
                        </td>
                        <td className="py-2 px-3 text-right text-red-400">
                          {formatCurrency(pos.max_loss * 100 * pos.contracts)}
                        </td>
                        <td className="py-2 px-3 text-right text-white">{pos.contracts}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500">
                No open positions
              </div>
            )}
          </div>

          {/* Decision Log */}
          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Zap className="w-5 h-5 text-red-500" />
              ARES Decision Log
            </h3>
            <DecisionLogViewer defaultBot="ARES" />
          </div>
        </div>
      </main>
    </div>
  )
}
