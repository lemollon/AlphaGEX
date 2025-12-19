'use client'

import { useState, useEffect } from 'react'
import { Sword, TrendingUp, TrendingDown, Activity, DollarSign, Target, RefreshCw, BarChart3, ChevronDown, ChevronUp, Server, Play, AlertTriangle, Clock, Zap } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import Navigation from '@/components/Navigation'
import DecisionLogViewer from '@/components/trader/DecisionLogViewer'
import { apiClient } from '@/lib/api'

// ==================== INTERFACES ====================

interface ARESStatus {
  mode: string
  capital: number
  total_pnl: number
  trade_count: number
  win_rate: number
  open_positions: number
  closed_positions: number
  traded_today: boolean
  in_trading_window: boolean
  current_time: string
  is_active: boolean
  high_water_mark: number
  sandbox_connected?: boolean
  paper_mode_type?: 'sandbox' | 'simulated'
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
  close_date?: string
  expiration: string
  put_long_strike: number
  put_short_strike: number
  call_short_strike: number
  call_long_strike: number
  total_credit: number
  close_price?: number
  realized_pnl?: number
  max_loss: number
  contracts: number
  underlying_at_entry: number
  vix_at_entry: number
  status: string
}

interface Performance {
  total_trades: number
  closed_trades: number
  open_positions: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  total_pnl: number
  avg_pnl_per_trade: number
  best_trade: number
  worst_trade: number
  current_capital: number
  return_pct: number
  high_water_mark: number
  max_drawdown_pct: number
}

interface EquityPoint {
  date: string
  equity: number
  pnl: number
  daily_pnl: number
  return_pct: number
}

interface MarketData {
  ticker: string
  underlying_price: number
  vix: number
  expected_move: number
  timestamp: string
  source: string
}

interface TradierStatus {
  mode: string
  success?: boolean
  account: {
    account_number?: string
    type?: string
    cash?: number
    equity?: number
    buying_power?: number
  }
  positions: Array<{
    symbol: string
    quantity: number
    cost_basis: number
    date_acquired?: string
  }>
  orders: Array<{
    id: string
    symbol: string
    side: string
    quantity: number
    status: string
    type?: string
    price?: number
    created_date?: string
  }>
  errors: string[]
}

interface Config {
  ticker: string
  spread_width: number
  risk_per_trade_pct: number
  sd_multiplier: number
  min_credit: number
  profit_target_pct: number
  entry_window: string
  mode?: string
}

// ==================== COMPONENT ====================

export default function ARESPage() {
  // State
  const [status, setStatus] = useState<ARESStatus | null>(null)
  const [positions, setPositions] = useState<IronCondorPosition[]>([])
  const [closedPositions, setClosedPositions] = useState<IronCondorPosition[]>([])
  const [performance, setPerformance] = useState<Performance | null>(null)
  const [equityData, setEquityData] = useState<EquityPoint[]>([])
  const [marketData, setMarketData] = useState<MarketData | null>(null)
  const [tradierStatus, setTradierStatus] = useState<TradierStatus | null>(null)
  const [config, setConfig] = useState<Config | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date())

  // UI State
  const [showSpxPositions, setShowSpxPositions] = useState(false)
  const [showSpyPositions, setShowSpyPositions] = useState(false)
  const [showSpxLog, setShowSpxLog] = useState(false)
  const [showSpyLog, setShowSpyLog] = useState(false)

  // Fetch all data
  const fetchData = async () => {
    try {
      setLoading(true)
      setError(null)

      const [statusRes, performanceRes, equityRes, positionsRes, marketRes, tradierRes, configRes] = await Promise.all([
        apiClient.getARESPageStatus().catch(() => ({ data: null })),
        apiClient.getARESPerformance().catch(() => ({ data: null })),
        apiClient.getARESEquityCurve(30).catch(() => ({ data: null })),
        apiClient.getARESPositions().catch(() => ({ data: null })),
        apiClient.getARESMarketData().catch(() => ({ data: null })),
        apiClient.getARESTradierStatus().catch(() => ({ data: null })),
        apiClient.getARESConfig ? apiClient.getARESConfig().catch(() => ({ data: null })) : Promise.resolve({ data: null })
      ])

      if (statusRes.data?.data) setStatus(statusRes.data.data)
      if (performanceRes.data?.data) setPerformance(performanceRes.data.data)
      if (equityRes.data?.data?.equity_curve) setEquityData(equityRes.data.data.equity_curve)
      if (positionsRes.data?.data?.open_positions) setPositions(positionsRes.data.data.open_positions)
      if (positionsRes.data?.data?.closed_positions) setClosedPositions(positionsRes.data.data.closed_positions)
      if (marketRes.data?.data) setMarketData(marketRes.data.data)
      if (tradierRes.data?.data) setTradierStatus(tradierRes.data.data)
      if (configRes.data?.data) setConfig(configRes.data.data)

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
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [])

  // Formatters
  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(value)
  }

  const formatPercent = (value: number) => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
  }

  const tradierConnected = tradierStatus?.success && tradierStatus?.account?.account_number

  // ==================== RENDER ====================

  return (
    <div className="min-h-screen bg-gray-900">
      <Navigation />
      <main className="lg:pl-64 pt-16 lg:pt-0">
        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Sword className="w-8 h-8 text-red-500" />
              <div>
                <h1 className="text-2xl font-bold text-white">ARES - 0DTE Iron Condor Strategy</h1>
                <p className="text-gray-400">Comparing SPX (Simulated) vs SPY (Tradier Paper Trading)</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                status?.in_trading_window ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-300'
              }`}>
                {status?.in_trading_window ? 'MARKET OPEN' : 'MARKET CLOSED'}
              </span>
              <button
                onClick={fetchData}
                className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>
          </div>

          {error && (
            <div className="mb-6 p-4 bg-red-900/50 border border-red-500 rounded-lg text-red-300">
              {error}
            </div>
          )}

          {/* Market Data Bar */}
          <div className="mb-6 bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="grid grid-cols-2 md:grid-cols-6 gap-4 text-center">
              <div>
                <span className="text-gray-400 text-xs">SPX Price</span>
                <p className="text-white font-mono text-lg font-bold">
                  {marketData?.underlying_price ? `$${marketData.underlying_price.toLocaleString()}` : '--'}
                </p>
              </div>
              <div>
                <span className="text-gray-400 text-xs">VIX</span>
                <p className="text-white font-mono text-lg font-bold">{marketData?.vix?.toFixed(2) || '--'}</p>
              </div>
              <div>
                <span className="text-gray-400 text-xs">Expected Move (1σ)</span>
                <p className="text-white font-mono text-lg font-bold">±${marketData?.expected_move?.toFixed(0) || '--'}</p>
              </div>
              <div>
                <span className="text-gray-400 text-xs">Spread Width</span>
                <p className="text-white font-mono text-lg font-bold">${config?.spread_width || status?.config?.spread_width || 10}</p>
              </div>
              <div>
                <span className="text-gray-400 text-xs">Strike Distance</span>
                <p className="text-white font-mono text-lg font-bold">{config?.sd_multiplier || status?.config?.sd_multiplier || 1} SD</p>
              </div>
              <div>
                <span className="text-gray-400 text-xs">Monthly Target</span>
                <p className="text-green-400 font-mono text-lg font-bold">10%</p>
              </div>
            </div>
          </div>

          {/* Two Column Layout: SPX | SPY */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

            {/* ==================== LEFT: SPX (Simulated) ==================== */}
            <div className="space-y-4">
              <div className="bg-gradient-to-br from-purple-900/30 to-gray-800 rounded-lg border border-purple-700/50 overflow-hidden">
                {/* Header */}
                <div className="p-4 border-b border-purple-700/30">
                  <div className="flex items-center justify-between">
                    <h2 className="text-xl font-bold text-purple-300 flex items-center gap-2">
                      <Play className="w-6 h-6" />
                      SPX Performance
                    </h2>
                    <span className="px-3 py-1 rounded text-xs font-medium bg-purple-900 text-purple-300">
                      SIMULATED
                    </span>
                  </div>
                  <p className="text-xs text-gray-400 mt-1">
                    Real market data from Tradier • Simulated execution (Tradier doesn&apos;t support SPX options)
                  </p>
                </div>

                {/* Stats Grid */}
                <div className="p-4 grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="bg-gray-800/60 rounded-lg p-3 text-center">
                    <span className="text-gray-400 text-xs">Capital</span>
                    <p className="text-white font-bold text-lg">
                      {formatCurrency(performance?.current_capital || 200000)}
                    </p>
                  </div>
                  <div className="bg-gray-800/60 rounded-lg p-3 text-center">
                    <span className="text-gray-400 text-xs">Total P&L</span>
                    <p className={`font-bold text-lg ${(performance?.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {formatCurrency(performance?.total_pnl || 0)}
                    </p>
                    <span className="text-xs text-gray-500">
                      ({formatPercent(performance?.return_pct || 0)})
                    </span>
                  </div>
                  <div className="bg-gray-800/60 rounded-lg p-3 text-center">
                    <span className="text-gray-400 text-xs">Win Rate</span>
                    <p className="text-white font-bold text-lg">
                      {(performance?.win_rate || 0).toFixed(1)}%
                    </p>
                    <span className="text-xs text-gray-500">
                      {performance?.winning_trades || 0}W / {performance?.losing_trades || 0}L
                    </span>
                  </div>
                  <div className="bg-gray-800/60 rounded-lg p-3 text-center">
                    <span className="text-gray-400 text-xs">Trades</span>
                    <p className="text-white font-bold text-lg">
                      {performance?.closed_trades || 0}
                    </p>
                    <span className="text-xs text-gray-500">
                      {performance?.open_positions || 0} open
                    </span>
                  </div>
                </div>

                {/* Additional Metrics */}
                <div className="px-4 pb-4 grid grid-cols-3 gap-3">
                  <div className="bg-gray-800/40 rounded p-2 text-center">
                    <span className="text-gray-500 text-xs">Best Trade</span>
                    <p className="text-green-400 font-medium">{formatCurrency(performance?.best_trade || 0)}</p>
                  </div>
                  <div className="bg-gray-800/40 rounded p-2 text-center">
                    <span className="text-gray-500 text-xs">Worst Trade</span>
                    <p className="text-red-400 font-medium">{formatCurrency(performance?.worst_trade || 0)}</p>
                  </div>
                  <div className="bg-gray-800/40 rounded p-2 text-center">
                    <span className="text-gray-500 text-xs">Max Drawdown</span>
                    <p className="text-yellow-400 font-medium">-{(performance?.max_drawdown_pct || 0).toFixed(1)}%</p>
                  </div>
                </div>

                {/* Equity Curve */}
                <div className="px-4 pb-4">
                  <h4 className="text-sm font-medium text-purple-300 mb-2 flex items-center gap-2">
                    <BarChart3 className="w-4 h-4" />
                    Equity Curve (30 Days)
                  </h4>
                  <div className="h-40 bg-gray-800/40 rounded-lg p-2">
                    {equityData.length > 1 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={equityData}>
                          <defs>
                            <linearGradient id="spxEquity" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#A855F7" stopOpacity={0.4} />
                              <stop offset="95%" stopColor="#A855F7" stopOpacity={0} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                          <XAxis dataKey="date" stroke="#6B7280" fontSize={10} tickFormatter={(v) => v.slice(5)} />
                          <YAxis stroke="#6B7280" fontSize={10} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
                          <Tooltip
                            contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: '8px' }}
                            formatter={(value: number) => [formatCurrency(value), 'Equity']}
                          />
                          <Area type="monotone" dataKey="equity" stroke="#A855F7" strokeWidth={2} fill="url(#spxEquity)" />
                        </AreaChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="flex items-center justify-center h-full text-gray-500 text-sm">
                        No equity data yet - chart appears after first trade
                      </div>
                    )}
                  </div>
                </div>

                {/* Open Positions */}
                <div className="px-4 pb-4">
                  <button
                    onClick={() => setShowSpxPositions(!showSpxPositions)}
                    className="w-full flex items-center justify-between text-sm font-medium text-purple-300 mb-2"
                  >
                    <span className="flex items-center gap-2">
                      <Activity className="w-4 h-4" />
                      Open Positions ({positions.length})
                    </span>
                    {showSpxPositions ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>
                  {showSpxPositions && (
                    <div className="space-y-1 max-h-48 overflow-y-auto">
                      {positions.length > 0 ? positions.map((pos) => (
                        <div key={pos.position_id} className="flex items-center justify-between text-xs bg-gray-800/50 rounded p-2">
                          <div>
                            <span className="text-gray-400">{pos.expiration}</span>
                            <span className="text-purple-300 font-mono ml-2">
                              {pos.put_short_strike}P / {pos.call_short_strike}C
                            </span>
                          </div>
                          <div className="text-right">
                            <span className="text-green-400">{formatCurrency(pos.total_credit * 100 * pos.contracts)}</span>
                            <span className="text-gray-500 ml-2">x{pos.contracts}</span>
                          </div>
                        </div>
                      )) : (
                        <p className="text-xs text-gray-500 text-center py-2">No open positions</p>
                      )}
                    </div>
                  )}
                </div>

                {/* Recent Trades */}
                <div className="px-4 pb-4">
                  <h4 className="text-sm font-medium text-purple-300 mb-2">Recent Closed Trades</h4>
                  <div className="space-y-1 max-h-32 overflow-y-auto">
                    {closedPositions.length > 0 ? closedPositions.slice(0, 5).map((pos) => (
                      <div key={pos.position_id} className="flex items-center justify-between text-xs bg-gray-800/30 rounded p-2">
                        <span className="text-gray-400">{pos.close_date || pos.expiration}</span>
                        <span className="text-gray-300 font-mono">
                          {pos.put_short_strike}P / {pos.call_short_strike}C
                        </span>
                        <span className={(pos.realized_pnl || pos.total_credit) > 0 ? 'text-green-400' : 'text-red-400'}>
                          {formatCurrency((pos.realized_pnl || pos.total_credit * 100 * pos.contracts))}
                        </span>
                      </div>
                    )) : (
                      <p className="text-xs text-gray-500 text-center py-2">No closed trades yet</p>
                    )}
                  </div>
                </div>
              </div>

              {/* SPX Decision Log */}
              <div className="bg-gray-800 rounded-lg border border-gray-700">
                <button
                  onClick={() => setShowSpxLog(!showSpxLog)}
                  className="w-full flex items-center justify-between p-4"
                >
                  <h3 className="text-sm font-medium text-purple-300 flex items-center gap-2">
                    <Zap className="w-4 h-4" />
                    SPX Decision Log
                  </h3>
                  {showSpxLog ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                </button>
                {showSpxLog && (
                  <div className="p-4 pt-0 max-h-64 overflow-y-auto">
                    <DecisionLogViewer defaultBot="ARES" />
                  </div>
                )}
              </div>
            </div>

            {/* ==================== RIGHT: SPY (Tradier) ==================== */}
            <div className="space-y-4">
              <div className="bg-gradient-to-br from-blue-900/30 to-gray-800 rounded-lg border border-blue-700/50 overflow-hidden">
                {/* Header */}
                <div className="p-4 border-b border-blue-700/30">
                  <div className="flex items-center justify-between">
                    <h2 className="text-xl font-bold text-blue-300 flex items-center gap-2">
                      <Server className="w-6 h-6" />
                      SPY Performance
                    </h2>
                    <span className={`px-3 py-1 rounded text-xs font-medium ${
                      tradierConnected ? 'bg-green-900 text-green-300' : 'bg-yellow-900 text-yellow-300'
                    }`}>
                      {tradierConnected ? 'CONNECTED' : 'NOT CONNECTED'}
                    </span>
                  </div>
                  <p className="text-xs text-gray-400 mt-1">
                    Real paper trading on Tradier sandbox • Actual order execution with SPY options
                  </p>
                </div>

                {tradierConnected ? (
                  <>
                    {/* Stats Grid */}
                    <div className="p-4 grid grid-cols-2 md:grid-cols-4 gap-3">
                      <div className="bg-gray-800/60 rounded-lg p-3 text-center">
                        <span className="text-gray-400 text-xs">Buying Power</span>
                        <p className="text-white font-bold text-lg">
                          {formatCurrency(tradierStatus?.account?.buying_power || 0)}
                        </p>
                      </div>
                      <div className="bg-gray-800/60 rounded-lg p-3 text-center">
                        <span className="text-gray-400 text-xs">Total Equity</span>
                        <p className="text-white font-bold text-lg">
                          {formatCurrency(tradierStatus?.account?.equity || 0)}
                        </p>
                      </div>
                      <div className="bg-gray-800/60 rounded-lg p-3 text-center">
                        <span className="text-gray-400 text-xs">Cash</span>
                        <p className="text-white font-bold text-lg">
                          {formatCurrency(tradierStatus?.account?.cash || 0)}
                        </p>
                      </div>
                      <div className="bg-gray-800/60 rounded-lg p-3 text-center">
                        <span className="text-gray-400 text-xs">Positions</span>
                        <p className="text-white font-bold text-lg">
                          {tradierStatus?.positions?.length || 0}
                        </p>
                        <span className="text-xs text-gray-500">
                          {tradierStatus?.orders?.filter(o => o.status === 'pending').length || 0} pending
                        </span>
                      </div>
                    </div>

                    {/* P&L Placeholder (Tradier doesn't provide historical P&L) */}
                    <div className="px-4 pb-4 grid grid-cols-3 gap-3">
                      <div className="bg-gray-800/40 rounded p-2 text-center">
                        <span className="text-gray-500 text-xs">Day P&L</span>
                        <p className="text-gray-400 font-medium">--</p>
                      </div>
                      <div className="bg-gray-800/40 rounded p-2 text-center">
                        <span className="text-gray-500 text-xs">Account Type</span>
                        <p className="text-blue-400 font-medium">{tradierStatus?.account?.type || 'Sandbox'}</p>
                      </div>
                      <div className="bg-gray-800/40 rounded p-2 text-center">
                        <span className="text-gray-500 text-xs">Mode</span>
                        <p className="text-blue-400 font-medium">{tradierStatus?.mode || 'Paper'}</p>
                      </div>
                    </div>

                    {/* Equity Curve Placeholder */}
                    <div className="px-4 pb-4">
                      <h4 className="text-sm font-medium text-blue-300 mb-2 flex items-center gap-2">
                        <BarChart3 className="w-4 h-4" />
                        Equity Curve (30 Days)
                      </h4>
                      <div className="h-40 bg-gray-800/40 rounded-lg flex items-center justify-center">
                        <p className="text-gray-500 text-sm">
                          Historical equity data not available from Tradier sandbox
                        </p>
                      </div>
                    </div>

                    {/* Tradier Positions */}
                    <div className="px-4 pb-4">
                      <button
                        onClick={() => setShowSpyPositions(!showSpyPositions)}
                        className="w-full flex items-center justify-between text-sm font-medium text-blue-300 mb-2"
                      >
                        <span className="flex items-center gap-2">
                          <Activity className="w-4 h-4" />
                          Open Positions ({tradierStatus?.positions?.length || 0})
                        </span>
                        {showSpyPositions ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </button>
                      {showSpyPositions && (
                        <div className="space-y-1 max-h-48 overflow-y-auto">
                          {tradierStatus?.positions && tradierStatus.positions.length > 0 ? tradierStatus.positions.map((pos, idx) => (
                            <div key={idx} className="flex items-center justify-between text-xs bg-gray-800/50 rounded p-2">
                              <span className="text-white font-mono">{pos.symbol}</span>
                              <span className="text-gray-400">x{pos.quantity}</span>
                              <span className="text-blue-300">{formatCurrency(pos.cost_basis)}</span>
                            </div>
                          )) : (
                            <p className="text-xs text-gray-500 text-center py-2">No open positions</p>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Recent Orders */}
                    <div className="px-4 pb-4">
                      <h4 className="text-sm font-medium text-blue-300 mb-2">Recent Orders</h4>
                      <div className="space-y-1 max-h-32 overflow-y-auto">
                        {tradierStatus?.orders && tradierStatus.orders.length > 0 ? tradierStatus.orders.slice(0, 5).map((order) => (
                          <div key={order.id} className="flex items-center justify-between text-xs bg-gray-800/30 rounded p-2">
                            <span className="text-white font-mono">{order.symbol}</span>
                            <span className={order.side === 'buy' ? 'text-green-400' : 'text-red-400'}>
                              {order.side.toUpperCase()} x{order.quantity}
                            </span>
                            <span className={`px-2 py-0.5 rounded ${
                              order.status === 'filled' ? 'bg-green-900 text-green-300' :
                              order.status === 'pending' ? 'bg-yellow-900 text-yellow-300' :
                              order.status === 'canceled' ? 'bg-gray-700 text-gray-300' :
                              'bg-gray-700 text-gray-300'
                            }`}>
                              {order.status}
                            </span>
                          </div>
                        )) : (
                          <p className="text-xs text-gray-500 text-center py-2">No recent orders</p>
                        )}
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="p-8 text-center">
                    <AlertTriangle className="w-16 h-16 text-yellow-500 mx-auto mb-4" />
                    <h4 className="text-white font-semibold text-lg mb-2">Tradier Sandbox Not Connected</h4>
                    <p className="text-gray-400 text-sm mb-4">
                      Configure Tradier sandbox credentials to enable real SPY paper trading
                    </p>
                    <div className="bg-gray-800/50 rounded-lg p-4 text-left text-sm">
                      <p className="text-gray-500 mb-2">Required environment variables:</p>
                      <code className="text-blue-400 block">TRADIER_ACCESS_TOKEN=your_sandbox_token</code>
                      <code className="text-blue-400 block">TRADIER_SANDBOX=true</code>
                    </div>
                    {tradierStatus?.errors && tradierStatus.errors.length > 0 && (
                      <div className="mt-4 text-red-400 text-xs">
                        Error: {tradierStatus.errors[0]}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* SPY Decision Log */}
              <div className="bg-gray-800 rounded-lg border border-gray-700">
                <button
                  onClick={() => setShowSpyLog(!showSpyLog)}
                  className="w-full flex items-center justify-between p-4"
                >
                  <h3 className="text-sm font-medium text-blue-300 flex items-center gap-2">
                    <Zap className="w-4 h-4" />
                    SPY Decision Log
                  </h3>
                  {showSpyLog ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                </button>
                {showSpyLog && (
                  <div className="p-4 pt-0 max-h-64 overflow-y-auto">
                    <DecisionLogViewer defaultBot="ARES" />
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="mt-6 text-center text-sm text-gray-500">
            Last updated: {lastUpdate.toLocaleTimeString()} | Auto-refresh every 30 seconds
          </div>
        </div>
      </main>
    </div>
  )
}
