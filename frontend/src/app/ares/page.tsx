'use client'

import { useState, useEffect } from 'react'
import { Sword, TrendingUp, TrendingDown, Activity, DollarSign, Target, CheckCircle, Clock, RefreshCw, BarChart3, ChevronDown, ChevronUp, Server, Play, AlertTriangle } from 'lucide-react'
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
  expiration: string
  put_long_strike: number
  put_short_strike: number
  call_short_strike: number
  call_long_strike: number
  total_credit: number
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

interface MarketData {
  ticker: string
  underlying_price: number
  vix: number
  expected_move: number
  timestamp: string
  source: string
}

interface TradierFullStatus {
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
    created_date?: string
  }>
  errors: string[]
}

export default function ARESPage() {
  const [status, setStatus] = useState<ARESStatus | null>(null)
  const [positions, setPositions] = useState<IronCondorPosition[]>([])
  const [closedPositions, setClosedPositions] = useState<IronCondorPosition[]>([])
  const [performance, setPerformance] = useState<Performance | null>(null)
  const [marketData, setMarketData] = useState<MarketData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date())
  const [tradierStatus, setTradierStatus] = useState<TradierFullStatus | null>(null)
  const [showSpxLog, setShowSpxLog] = useState(false)
  const [showSpyLog, setShowSpyLog] = useState(false)

  const fetchData = async () => {
    try {
      setLoading(true)
      setError(null)

      // Fetch all ARES data
      const [statusRes, performanceRes, positionsRes, marketRes, tradierRes] = await Promise.all([
        apiClient.getARESPageStatus().catch(() => ({ data: null })),
        apiClient.getARESPerformance().catch(() => ({ data: null })),
        apiClient.getARESPositions().catch(() => ({ data: null })),
        apiClient.getARESMarketData().catch(() => ({ data: null })),
        apiClient.getARESTradierStatus().catch(() => ({ data: null }))
      ])

      if (statusRes.data?.data) setStatus(statusRes.data.data)
      if (performanceRes.data?.data) setPerformance(performanceRes.data.data)
      if (positionsRes.data?.data?.open_positions) setPositions(positionsRes.data.data.open_positions)
      if (positionsRes.data?.data?.closed_positions) setClosedPositions(positionsRes.data.data.closed_positions)
      if (marketRes.data?.data) setMarketData(marketRes.data.data)
      if (tradierRes.data?.data) setTradierStatus(tradierRes.data.data)

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
                <h1 className="text-2xl font-bold text-white">ARES - Iron Condor Strategy</h1>
                <p className="text-gray-400">SPX (Simulated) vs SPY (Tradier Paper Trading)</p>
              </div>
            </div>
            <button
              onClick={fetchData}
              className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>

          {error && (
            <div className="mb-6 p-4 bg-red-900/50 border border-red-500 rounded-lg text-red-300">
              {error}
            </div>
          )}

          {/* Market Data Bar */}
          <div className="mb-6 bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-6">
                <div>
                  <span className="text-gray-400 text-sm">SPX</span>
                  <p className="text-white font-mono text-lg">
                    {marketData?.underlying_price ? `$${marketData.underlying_price.toLocaleString()}` : '--'}
                  </p>
                </div>
                <div>
                  <span className="text-gray-400 text-sm">VIX</span>
                  <p className="text-white font-mono text-lg">{marketData?.vix?.toFixed(2) || '--'}</p>
                </div>
                <div>
                  <span className="text-gray-400 text-sm">Expected Move</span>
                  <p className="text-white font-mono text-lg">±${marketData?.expected_move?.toFixed(0) || '--'}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                  status?.in_trading_window ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-300'
                }`}>
                  {status?.in_trading_window ? 'MARKET OPEN' : 'MARKET CLOSED'}
                </span>
              </div>
            </div>
          </div>

          {/* Two Column Layout: SPX | SPY */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

            {/* LEFT SIDE: SPX Performance (Simulated) */}
            <div className="space-y-4">
              <div className="bg-purple-900/20 rounded-lg p-4 border border-purple-700/50">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-bold text-purple-300 flex items-center gap-2">
                    <Play className="w-5 h-5" />
                    SPX Performance
                  </h2>
                  <span className="px-2 py-1 rounded text-xs bg-purple-900 text-purple-300">SIMULATED</span>
                </div>
                <p className="text-xs text-gray-400 mb-4">
                  Uses real Tradier market data • Execution is simulated (Tradier doesn&apos;t support SPX options)
                </p>

                {/* SPX Stats Grid */}
                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div className="bg-gray-800/50 rounded p-3">
                    <span className="text-gray-400 text-xs">Capital</span>
                    <p className="text-white font-bold text-lg">
                      {formatCurrency(performance?.current_capital || 200000)}
                    </p>
                  </div>
                  <div className="bg-gray-800/50 rounded p-3">
                    <span className="text-gray-400 text-xs">Total P&L</span>
                    <p className={`font-bold text-lg ${(performance?.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {formatCurrency(performance?.total_pnl || 0)}
                    </p>
                  </div>
                  <div className="bg-gray-800/50 rounded p-3">
                    <span className="text-gray-400 text-xs">Win Rate</span>
                    <p className="text-white font-bold text-lg">
                      {(performance?.win_rate || 0).toFixed(1)}%
                    </p>
                  </div>
                  <div className="bg-gray-800/50 rounded p-3">
                    <span className="text-gray-400 text-xs">Trades</span>
                    <p className="text-white font-bold text-lg">
                      {performance?.closed_trades || 0}
                    </p>
                  </div>
                </div>

                {/* SPX Open Positions */}
                <div className="mb-4">
                  <h4 className="text-sm font-medium text-purple-300 mb-2">Open Positions ({positions.length})</h4>
                  {positions.length > 0 ? (
                    <div className="space-y-1 max-h-32 overflow-y-auto">
                      {positions.map((pos) => (
                        <div key={pos.position_id} className="flex items-center justify-between text-xs bg-gray-800/30 rounded p-2">
                          <span className="text-gray-400">{pos.expiration}</span>
                          <span className="text-purple-300 font-mono">
                            {pos.put_short_strike}P / {pos.call_short_strike}C
                          </span>
                          <span className="text-green-400">
                            {formatCurrency(pos.total_credit * 100 * pos.contracts)}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-gray-500">No open positions</p>
                  )}
                </div>

                {/* SPX Recent Trades */}
                <div>
                  <h4 className="text-sm font-medium text-purple-300 mb-2">Recent Trades</h4>
                  {closedPositions.length > 0 ? (
                    <div className="space-y-1 max-h-32 overflow-y-auto">
                      {closedPositions.slice(0, 5).map((pos) => (
                        <div key={pos.position_id} className="flex items-center justify-between text-xs bg-gray-800/30 rounded p-2">
                          <span className="text-gray-400">{pos.expiration}</span>
                          <span className="text-gray-300 font-mono">
                            {pos.put_short_strike}P / {pos.call_short_strike}C
                          </span>
                          <span className={pos.total_credit > 0 ? 'text-green-400' : 'text-red-400'}>
                            {formatCurrency(pos.total_credit * 100 * pos.contracts)}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-gray-500">No closed trades yet</p>
                  )}
                </div>
              </div>

              {/* SPX Decision Log */}
              <div className="bg-gray-800 rounded-lg border border-gray-700">
                <button
                  onClick={() => setShowSpxLog(!showSpxLog)}
                  className="w-full flex items-center justify-between p-4"
                >
                  <h3 className="text-sm font-medium text-purple-300">SPX Decision Log</h3>
                  {showSpxLog ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                </button>
                {showSpxLog && (
                  <div className="p-4 pt-0 max-h-64 overflow-y-auto">
                    <DecisionLogViewer defaultBot="ARES" />
                  </div>
                )}
              </div>
            </div>

            {/* RIGHT SIDE: SPY Performance (Tradier) */}
            <div className="space-y-4">
              <div className="bg-blue-900/20 rounded-lg p-4 border border-blue-700/50">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-bold text-blue-300 flex items-center gap-2">
                    <Server className="w-5 h-5" />
                    SPY Performance
                  </h2>
                  <span className={`px-2 py-1 rounded text-xs ${
                    tradierConnected ? 'bg-green-900 text-green-300' : 'bg-yellow-900 text-yellow-300'
                  }`}>
                    {tradierConnected ? 'CONNECTED' : 'NOT CONNECTED'}
                  </span>
                </div>
                <p className="text-xs text-gray-400 mb-4">
                  Real paper trading on Tradier sandbox • Actual order execution
                </p>

                {tradierConnected ? (
                  <>
                    {/* SPY Stats Grid */}
                    <div className="grid grid-cols-2 gap-3 mb-4">
                      <div className="bg-gray-800/50 rounded p-3">
                        <span className="text-gray-400 text-xs">Buying Power</span>
                        <p className="text-white font-bold text-lg">
                          {formatCurrency(tradierStatus?.account?.buying_power || 0)}
                        </p>
                      </div>
                      <div className="bg-gray-800/50 rounded p-3">
                        <span className="text-gray-400 text-xs">Total Equity</span>
                        <p className="text-white font-bold text-lg">
                          {formatCurrency(tradierStatus?.account?.equity || 0)}
                        </p>
                      </div>
                      <div className="bg-gray-800/50 rounded p-3">
                        <span className="text-gray-400 text-xs">Cash</span>
                        <p className="text-white font-bold text-lg">
                          {formatCurrency(tradierStatus?.account?.cash || 0)}
                        </p>
                      </div>
                      <div className="bg-gray-800/50 rounded p-3">
                        <span className="text-gray-400 text-xs">Positions</span>
                        <p className="text-white font-bold text-lg">
                          {tradierStatus?.positions?.length || 0}
                        </p>
                      </div>
                    </div>

                    {/* SPY Positions */}
                    <div className="mb-4">
                      <h4 className="text-sm font-medium text-blue-300 mb-2">
                        Tradier Positions ({tradierStatus?.positions?.length || 0})
                      </h4>
                      {tradierStatus?.positions && tradierStatus.positions.length > 0 ? (
                        <div className="space-y-1 max-h-32 overflow-y-auto">
                          {tradierStatus.positions.map((pos, idx) => (
                            <div key={idx} className="flex items-center justify-between text-xs bg-gray-800/30 rounded p-2">
                              <span className="text-white font-mono">{pos.symbol}</span>
                              <span className="text-gray-400">x{pos.quantity}</span>
                              <span className="text-blue-300">{formatCurrency(pos.cost_basis)}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-gray-500">No open positions</p>
                      )}
                    </div>

                    {/* SPY Recent Orders */}
                    <div>
                      <h4 className="text-sm font-medium text-blue-300 mb-2">Recent Orders</h4>
                      {tradierStatus?.orders && tradierStatus.orders.length > 0 ? (
                        <div className="space-y-1 max-h-32 overflow-y-auto">
                          {tradierStatus.orders.slice(0, 5).map((order) => (
                            <div key={order.id} className="flex items-center justify-between text-xs bg-gray-800/30 rounded p-2">
                              <span className="text-white font-mono">{order.symbol}</span>
                              <span className={order.side === 'buy' ? 'text-green-400' : 'text-red-400'}>
                                {order.side.toUpperCase()}
                              </span>
                              <span className={`px-1 rounded ${
                                order.status === 'filled' ? 'bg-green-900 text-green-300' :
                                order.status === 'pending' ? 'bg-yellow-900 text-yellow-300' :
                                'bg-gray-700 text-gray-300'
                              }`}>
                                {order.status}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-gray-500">No recent orders</p>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="text-center py-8">
                    <AlertTriangle className="w-12 h-12 text-yellow-500 mx-auto mb-3" />
                    <h4 className="text-white font-semibold mb-2">Tradier Not Connected</h4>
                    <p className="text-gray-400 text-sm mb-2">
                      Set TRADIER_ACCESS_TOKEN to enable SPY paper trading
                    </p>
                    {tradierStatus?.errors && tradierStatus.errors.length > 0 && (
                      <p className="text-red-400 text-xs mt-2">
                        Error: {tradierStatus.errors[0]}
                      </p>
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
                  <h3 className="text-sm font-medium text-blue-300">SPY Decision Log</h3>
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

          {/* Strategy Info */}
          <div className="mt-6 bg-gray-800 rounded-lg p-4 border border-gray-700">
            <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
              <Sword className="w-5 h-5 text-red-500" />
              Strategy Configuration
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
              <div>
                <span className="text-gray-400">Strategy</span>
                <p className="text-white font-medium">0DTE Iron Condor</p>
              </div>
              <div>
                <span className="text-gray-400">Spread Width</span>
                <p className="text-white font-medium">${status?.config?.spread_width || 10}</p>
              </div>
              <div>
                <span className="text-gray-400">Risk Per Trade</span>
                <p className="text-white font-medium">{status?.config?.risk_per_trade || 10}%</p>
              </div>
              <div>
                <span className="text-gray-400">Strike Distance</span>
                <p className="text-white font-medium">{status?.config?.sd_multiplier || 1} SD</p>
              </div>
              <div>
                <span className="text-gray-400">Monthly Target</span>
                <p className="text-green-400 font-medium">10%</p>
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
