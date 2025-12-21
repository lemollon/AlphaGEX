'use client'

import { useState } from 'react'
import { Sword, TrendingUp, TrendingDown, Activity, DollarSign, Target, RefreshCw, BarChart3, ChevronDown, ChevronUp, Server, Play, AlertTriangle, Clock, Zap, Brain, Shield, Crosshair, TrendingUp as TrendUp, FileText } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import Navigation from '@/components/Navigation'
import {
  useARESStatus,
  useARESPerformance,
  useARESEquityCurve,
  useARESPositions,
  useARESMarketData,
  useARESTradierStatus,
  useARESConfig,
  useARESDecisions
} from '@/lib/hooks/useMarketData'

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
  // New: separate SPX/SPY data
  spx?: {
    ticker: string
    price: number
    expected_move: number
  }
  spy?: {
    ticker: string
    price: number
    expected_move: number
  }
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
  spread_width_spy?: number
  risk_per_trade_pct: number
  sd_multiplier: number
  sd_multiplier_spy?: number
  min_credit: number
  profit_target_pct: number
  entry_window: string
  mode?: string
}

interface DecisionLog {
  id: number
  bot_name: string
  symbol: string
  decision_type: string
  action: string
  what: string
  why: string
  how: string
  outcome: string
  timestamp: string
  strike?: number
  expiration?: string
  spot_price?: number
  vix?: number
  actual_pnl?: number
  full_decision?: {
    legs?: Array<{
      leg_id: number
      action: string
      option_type: string
      strike: number
      expiration: string
      entry_price: number
      exit_price: number
      contracts: number
      premium_per_contract: number
      delta: number
      gamma: number
      theta: number
      iv: number
      realized_pnl: number
    }>
    underlying_price_at_entry?: number
    underlying_price_at_exit?: number
    position_size_contracts?: number
    position_size_dollars?: number
    oracle_advice?: {
      should_trade: boolean
      confidence: number
      regime: string
      suggested_sd: number
      risk_level: string
    }
    gex_context?: {
      call_wall?: number
      put_wall?: number
      gamma_exposure?: number
      regime?: string
    }
    risk_checks?: Array<{
      check: string
      passed: boolean
      value?: string
    }>
  }
}

// ==================== COMPONENT ====================

export default function ARESPage() {
  // SWR hooks for data fetching with caching
  const { data: statusRes, error: statusError, isLoading: statusLoading, isValidating: statusValidating, mutate: mutateStatus } = useARESStatus()
  const { data: performanceRes, isValidating: perfValidating, mutate: mutatePerf } = useARESPerformance()
  const { data: equityRes, isValidating: equityValidating, mutate: mutateEquity } = useARESEquityCurve(30)
  const { data: positionsRes, isValidating: posValidating, mutate: mutatePositions } = useARESPositions()
  const { data: marketRes, isValidating: marketValidating, mutate: mutateMarket } = useARESMarketData()
  const { data: tradierRes, isValidating: tradierValidating, mutate: mutateTradier } = useARESTradierStatus()
  const { data: configRes, isValidating: configValidating, mutate: mutateConfig } = useARESConfig()
  const { data: decisionsRes, isValidating: decisionsValidating, mutate: mutateDecisions } = useARESDecisions(100)

  // Extract data from responses
  const status = statusRes?.data as ARESStatus | undefined
  const performance = performanceRes?.data as Performance | undefined
  const equityData = (equityRes?.data?.equity_curve || []) as EquityPoint[]
  const positions = (positionsRes?.data?.open_positions || []) as IronCondorPosition[]
  const closedPositions = (positionsRes?.data?.closed_positions || []) as IronCondorPosition[]
  const marketData = marketRes?.data as MarketData | undefined
  const tradierStatus = tradierRes?.data as TradierStatus | undefined
  const config = configRes?.data as Config | undefined
  const decisions = (decisionsRes?.data?.decisions || []) as DecisionLog[]

  const loading = statusLoading && !status
  const error = statusError?.message || null
  const isRefreshing = statusValidating || perfValidating || equityValidating || posValidating || marketValidating || tradierValidating || configValidating || decisionsValidating

  // UI State
  const [showSpxPositions, setShowSpxPositions] = useState(false)
  const [showSpyPositions, setShowSpyPositions] = useState(false)
  const [expandedDecision, setExpandedDecision] = useState<number | null>(null)

  // Manual refresh function
  const fetchData = () => {
    mutateStatus()
    mutatePerf()
    mutateEquity()
    mutatePositions()
    mutateMarket()
    mutateTradier()
    mutateConfig()
    mutateDecisions()
  }

  // Helper to get action color
  const getActionColor = (action: string) => {
    if (action?.includes('BUY') || action?.includes('OPEN') || action?.includes('ENTRY')) return 'text-green-400'
    if (action?.includes('SELL') || action?.includes('CLOSE') || action?.includes('EXIT')) return 'text-red-400'
    if (action?.includes('SKIP') || action?.includes('NO_TRADE')) return 'text-yellow-400'
    return 'text-gray-400'
  }

  // Helper to get decision type badge
  const getDecisionTypeBadge = (type: string) => {
    const badges: Record<string, { bg: string, text: string }> = {
      'ENTRY_SIGNAL': { bg: 'bg-green-900/50', text: 'text-green-400' },
      'EXIT_SIGNAL': { bg: 'bg-red-900/50', text: 'text-red-400' },
      'STRIKE_SELECTION': { bg: 'bg-purple-900/50', text: 'text-purple-400' },
      'NO_TRADE': { bg: 'bg-yellow-900/50', text: 'text-yellow-400' },
      'RISK_BLOCKED': { bg: 'bg-orange-900/50', text: 'text-orange-400' },
      'POSITION_SIZE': { bg: 'bg-blue-900/50', text: 'text-blue-400' },
      'EXPIRATION': { bg: 'bg-gray-700', text: 'text-gray-300' },
    }
    return badges[type] || { bg: 'bg-gray-700', text: 'text-gray-400' }
  }

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
      <main className="lg:pl-16 pt-24">
        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Sword className="w-8 h-8 text-red-500" />
              <div>
                <h1 className="text-2xl font-bold text-white">ARES - 0DTE Iron Condor Strategy</h1>
                <p className="text-gray-400">SPX Paper Trading (Real Market Data) • SPY Live Paper Trading (Tradier Sandbox)</p>
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
                disabled={isRefreshing}
                className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300 disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
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
            <div className="grid grid-cols-2 md:grid-cols-5 lg:grid-cols-10 gap-3 text-center">
              {/* SPX Data */}
              <div className="bg-purple-900/20 rounded-lg p-2">
                <span className="text-purple-400 text-xs">SPX</span>
                <p className="text-white font-mono text-lg font-bold">
                  ${marketData?.spx?.price?.toLocaleString() || marketData?.underlying_price?.toLocaleString() || '--'}
                </p>
              </div>
              <div className="bg-purple-900/20 rounded-lg p-2">
                <span className="text-purple-400 text-xs">SPX ±Move</span>
                <p className="text-white font-mono text-lg font-bold">
                  ±${marketData?.spx?.expected_move?.toFixed(0) || marketData?.expected_move?.toFixed(0) || '--'}
                </p>
              </div>
              <div className="bg-purple-900/20 rounded-lg p-2">
                <span className="text-purple-400 text-xs">SPX Strike</span>
                <p className="text-purple-300 font-mono text-lg font-bold">
                  {config?.sd_multiplier || 0.5} SD
                </p>
              </div>
              <div className="bg-purple-900/20 rounded-lg p-2">
                <span className="text-purple-400 text-xs">SPX Spread</span>
                <p className="text-purple-300 font-mono text-lg font-bold">
                  ${config?.spread_width || 10}
                </p>
              </div>
              {/* SPY Data */}
              <div className="bg-blue-900/20 rounded-lg p-2">
                <span className="text-blue-400 text-xs">SPY</span>
                <p className="text-white font-mono text-lg font-bold">
                  ${marketData?.spy?.price?.toFixed(2) || '--'}
                </p>
              </div>
              <div className="bg-blue-900/20 rounded-lg p-2">
                <span className="text-blue-400 text-xs">SPY ±Move</span>
                <p className="text-white font-mono text-lg font-bold">
                  ±${marketData?.spy?.expected_move?.toFixed(2) || '--'}
                </p>
              </div>
              <div className="bg-blue-900/20 rounded-lg p-2">
                <span className="text-blue-400 text-xs">SPY Strike</span>
                <p className="text-blue-300 font-mono text-lg font-bold">
                  {config?.sd_multiplier_spy || config?.sd_multiplier || 0.5} SD
                </p>
              </div>
              <div className="bg-blue-900/20 rounded-lg p-2">
                <span className="text-blue-400 text-xs">SPY Spread</span>
                <p className="text-blue-300 font-mono text-lg font-bold">
                  ${config?.spread_width_spy || 2}
                </p>
              </div>
              {/* VIX */}
              <div>
                <span className="text-gray-400 text-xs">VIX</span>
                <p className="text-yellow-400 font-mono text-lg font-bold">{marketData?.vix?.toFixed(2) || '--'}</p>
              </div>
              {/* Monthly Target */}
              <div>
                <span className="text-gray-400 text-xs">Monthly Target</span>
                <p className="text-green-400 font-mono text-lg font-bold">10%</p>
              </div>
            </div>
          </div>

          {/* Two Column Layout: SPX | SPY */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

            {/* ==================== LEFT: SPX (Paper Trading) ==================== */}
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
                      PAPER TRADING
                    </span>
                  </div>
                  <p className="text-xs text-gray-400 mt-1">
                    Real market data • Paper execution tracked locally (Tradier doesn&apos;t support SPX options)
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
                    {performance && (
                      <span className={`text-xs ml-auto ${(performance.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {(performance.total_pnl || 0) >= 0 ? '+' : ''}{formatCurrency(performance.total_pnl || 0)}
                      </span>
                    )}
                  </h4>
                  <div className="h-40 bg-gray-800/40 rounded-lg p-2">
                    {equityData.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={equityData}>
                          <defs>
                            <linearGradient id="spxEquity" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#A855F7" stopOpacity={0.4} />
                              <stop offset="95%" stopColor="#A855F7" stopOpacity={0} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                          <XAxis dataKey="date" stroke="#6B7280" fontSize={10} tickFormatter={(v) => v?.slice(5) || ''} />
                          <YAxis
                            stroke="#6B7280"
                            fontSize={10}
                            tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`}
                            domain={['dataMin - 5000', 'dataMax + 5000']}
                          />
                          <Tooltip
                            contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: '8px' }}
                            formatter={(value: number, name: string) => {
                              if (name === 'equity') return [formatCurrency(value), 'Equity']
                              if (name === 'daily_pnl') return [formatCurrency(value), 'Daily P&L']
                              return [value, name]
                            }}
                            labelFormatter={(label) => `Date: ${label}`}
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

                    {/* Equity Curve - From our own tracking */}
                    <div className="px-4 pb-4">
                      <h4 className="text-sm font-medium text-blue-300 mb-2 flex items-center gap-2">
                        <BarChart3 className="w-4 h-4" />
                        Equity Curve (Tracked Locally)
                        {tradierStatus?.account?.equity && (
                          <span className="text-xs ml-auto text-blue-400">
                            Current: {formatCurrency(tradierStatus.account.equity)}
                          </span>
                        )}
                      </h4>
                      <div className="h-40 bg-gray-800/40 rounded-lg p-2">
                        {equityData.length > 0 ? (
                          <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={equityData}>
                              <defs>
                                <linearGradient id="spyEquity" x1="0" y1="0" x2="0" y2="1">
                                  <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.4} />
                                  <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
                                </linearGradient>
                              </defs>
                              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                              <XAxis dataKey="date" stroke="#6B7280" fontSize={10} tickFormatter={(v) => v?.slice(5) || ''} />
                              <YAxis
                                stroke="#6B7280"
                                fontSize={10}
                                tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`}
                                domain={['dataMin - 5000', 'dataMax + 5000']}
                              />
                              <Tooltip
                                contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: '8px' }}
                                formatter={(value: number) => [formatCurrency(value), 'Equity']}
                                labelFormatter={(label) => `Date: ${label}`}
                              />
                              <Area type="monotone" dataKey="equity" stroke="#3B82F6" strokeWidth={2} fill="url(#spyEquity)" />
                            </AreaChart>
                          </ResponsiveContainer>
                        ) : (
                          <div className="flex flex-col items-center justify-center h-full text-gray-500 text-sm">
                            <p>No trades closed yet</p>
                            <p className="text-xs mt-1">Chart will appear after first SPY trade completes</p>
                          </div>
                        )}
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
                      <code className="text-blue-400 block">TRADIER_API_KEY=your_sandbox_api_key</code>
                      <code className="text-blue-400 block">TRADIER_ACCOUNT_ID=your_account_id</code>
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

            </div>
          </div>

          {/* ==================== UNIFIED DECISION LOG (Always Visible) ==================== */}
          <div className="mt-6 bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
            <div className="p-4 border-b border-gray-700 bg-gradient-to-r from-red-900/20 to-gray-800">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <FileText className="w-5 h-5 text-red-400" />
                  ARES Decision Log
                </h3>
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-gray-400">
                    {decisions.length} decisions
                  </span>
                  <a
                    href="/ares/logs"
                    className="text-red-400 hover:text-red-300 underline"
                  >
                    View Full History
                  </a>
                </div>
              </div>
              <p className="text-xs text-gray-400 mt-1">
                Real-time audit trail: What, Why, How for every trading decision
              </p>
            </div>

            <div className="p-4 space-y-3 max-h-[600px] overflow-y-auto">
              {decisions.length > 0 ? (
                decisions.slice(0, 20).map((decision) => {
                  const badge = getDecisionTypeBadge(decision.decision_type)
                  const isExpanded = expandedDecision === decision.id

                  return (
                    <div
                      key={decision.id}
                      className={`bg-gray-900/50 rounded-lg border transition-all ${
                        isExpanded ? 'border-red-500/50' : 'border-gray-700 hover:border-gray-600'
                      }`}
                    >
                      {/* Decision Header - Always Visible */}
                      <div
                        className="p-3 cursor-pointer"
                        onClick={() => setExpandedDecision(isExpanded ? null : decision.id)}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap mb-1">
                              <span className={`px-2 py-0.5 rounded text-xs font-medium ${badge.bg} ${badge.text}`}>
                                {decision.decision_type?.replace(/_/g, ' ')}
                              </span>
                              <span className={`text-sm font-medium ${getActionColor(decision.action)}`}>
                                {decision.action}
                              </span>
                              {decision.symbol && (
                                <span className="text-xs text-gray-400 font-mono">{decision.symbol}</span>
                              )}
                              {decision.actual_pnl !== undefined && decision.actual_pnl !== 0 && (
                                <span className={`text-xs font-bold ${decision.actual_pnl > 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  {decision.actual_pnl > 0 ? '+' : ''}{formatCurrency(decision.actual_pnl)}
                                </span>
                              )}
                            </div>
                            <p className="text-sm text-white truncate">
                              <span className="text-gray-500">WHAT: </span>
                              {decision.what}
                            </p>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-gray-500 whitespace-nowrap">
                              {new Date(decision.timestamp).toLocaleString('en-US', {
                                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                              })}
                            </span>
                            {isExpanded ? (
                              <ChevronUp className="w-4 h-4 text-gray-400" />
                            ) : (
                              <ChevronDown className="w-4 h-4 text-gray-400" />
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Expanded Details */}
                      {isExpanded && (
                        <div className="px-3 pb-3 space-y-3 border-t border-gray-700/50 pt-3">
                          {/* WHY */}
                          <div>
                            <span className="text-yellow-400 text-xs font-bold">WHY:</span>
                            <p className="text-sm text-gray-300 mt-1">{decision.why || 'Not specified'}</p>
                          </div>

                          {/* HOW */}
                          <div>
                            <span className="text-blue-400 text-xs font-bold">HOW:</span>
                            <p className="text-sm text-gray-300 mt-1">{decision.how || 'Not specified'}</p>
                          </div>

                          {/* Market Context */}
                          {(decision.spot_price || decision.vix || decision.strike) && (
                            <div className="bg-gray-800/50 rounded p-2">
                              <span className="text-cyan-400 text-xs font-bold">MARKET CONTEXT:</span>
                              <div className="grid grid-cols-4 gap-2 mt-2 text-xs">
                                {decision.spot_price && (
                                  <div>
                                    <span className="text-gray-500">Spot:</span>
                                    <span className="text-white ml-1">${decision.spot_price.toLocaleString()}</span>
                                  </div>
                                )}
                                {decision.vix && (
                                  <div>
                                    <span className="text-gray-500">VIX:</span>
                                    <span className="text-yellow-400 ml-1">{decision.vix.toFixed(1)}</span>
                                  </div>
                                )}
                                {decision.strike && (
                                  <div>
                                    <span className="text-gray-500">Strike:</span>
                                    <span className="text-white ml-1">${decision.strike}</span>
                                  </div>
                                )}
                                {decision.expiration && (
                                  <div>
                                    <span className="text-gray-500">Exp:</span>
                                    <span className="text-white ml-1">{decision.expiration}</span>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Oracle AI Advice */}
                          {decision.full_decision?.oracle_advice && (
                            <div className="bg-green-900/20 border border-green-700/30 rounded p-2">
                              <div className="flex items-center gap-2 mb-2">
                                <Brain className="w-4 h-4 text-green-400" />
                                <span className="text-green-400 text-xs font-bold">ORACLE AI ADVICE:</span>
                              </div>
                              <div className="grid grid-cols-3 gap-2 text-xs">
                                <div>
                                  <span className="text-gray-500">Should Trade:</span>
                                  <span className={`ml-1 ${decision.full_decision.oracle_advice.should_trade ? 'text-green-400' : 'text-red-400'}`}>
                                    {decision.full_decision.oracle_advice.should_trade ? 'YES' : 'NO'}
                                  </span>
                                </div>
                                <div>
                                  <span className="text-gray-500">Confidence:</span>
                                  <span className="text-white ml-1">{(decision.full_decision.oracle_advice.confidence * 100).toFixed(0)}%</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">Regime:</span>
                                  <span className="text-white ml-1">{decision.full_decision.oracle_advice.regime}</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">Suggested SD:</span>
                                  <span className="text-white ml-1">{decision.full_decision.oracle_advice.suggested_sd}</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">Risk Level:</span>
                                  <span className={`ml-1 ${
                                    decision.full_decision.oracle_advice.risk_level === 'low' ? 'text-green-400' :
                                    decision.full_decision.oracle_advice.risk_level === 'medium' ? 'text-yellow-400' : 'text-red-400'
                                  }`}>
                                    {decision.full_decision.oracle_advice.risk_level?.toUpperCase()}
                                  </span>
                                </div>
                              </div>
                            </div>
                          )}

                          {/* GEX Context */}
                          {decision.full_decision?.gex_context && (
                            <div className="bg-purple-900/20 border border-purple-700/30 rounded p-2">
                              <div className="flex items-center gap-2 mb-2">
                                <Crosshair className="w-4 h-4 text-purple-400" />
                                <span className="text-purple-400 text-xs font-bold">GEX CONTEXT:</span>
                              </div>
                              <div className="grid grid-cols-4 gap-2 text-xs">
                                {decision.full_decision.gex_context.call_wall && (
                                  <div>
                                    <span className="text-gray-500">Call Wall:</span>
                                    <span className="text-red-400 ml-1">${decision.full_decision.gex_context.call_wall}</span>
                                  </div>
                                )}
                                {decision.full_decision.gex_context.put_wall && (
                                  <div>
                                    <span className="text-gray-500">Put Wall:</span>
                                    <span className="text-green-400 ml-1">${decision.full_decision.gex_context.put_wall}</span>
                                  </div>
                                )}
                                {decision.full_decision.gex_context.gamma_exposure && (
                                  <div>
                                    <span className="text-gray-500">GEX:</span>
                                    <span className="text-white ml-1">{(decision.full_decision.gex_context.gamma_exposure / 1e9).toFixed(1)}B</span>
                                  </div>
                                )}
                                {decision.full_decision.gex_context.regime && (
                                  <div>
                                    <span className="text-gray-500">Regime:</span>
                                    <span className="text-white ml-1">{decision.full_decision.gex_context.regime}</span>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Trade Legs */}
                          {decision.full_decision?.legs && decision.full_decision.legs.length > 0 && (
                            <div className="bg-gray-800/50 rounded p-2">
                              <div className="flex items-center gap-2 mb-2">
                                <Target className="w-4 h-4 text-orange-400" />
                                <span className="text-orange-400 text-xs font-bold">TRADE LEGS ({decision.full_decision.legs.length}):</span>
                              </div>
                              <div className="space-y-2">
                                {decision.full_decision.legs.map((leg, idx) => (
                                  <div key={idx} className="bg-gray-900/50 rounded p-2 text-xs">
                                    <div className="flex justify-between items-center mb-1">
                                      <span className="font-medium text-white">
                                        Leg {leg.leg_id}: {leg.action} {leg.option_type?.toUpperCase()}
                                      </span>
                                      {leg.realized_pnl !== 0 && (
                                        <span className={leg.realized_pnl > 0 ? 'text-green-400' : 'text-red-400'}>
                                          P&L: ${leg.realized_pnl?.toFixed(2)}
                                        </span>
                                      )}
                                    </div>
                                    <div className="grid grid-cols-4 gap-2 text-gray-400">
                                      <div>Strike: <span className="text-white">${leg.strike}</span></div>
                                      <div>Entry: <span className="text-white">${leg.entry_price?.toFixed(2)}</span></div>
                                      <div>Exit: <span className="text-white">${leg.exit_price?.toFixed(2) || '-'}</span></div>
                                      <div>Contracts: <span className="text-white">{leg.contracts}</span></div>
                                      <div>Delta: <span className="text-white">{leg.delta?.toFixed(2)}</span></div>
                                      <div>Theta: <span className="text-white">${leg.theta?.toFixed(2)}</span></div>
                                      <div>IV: <span className="text-white">{(leg.iv * 100)?.toFixed(1)}%</span></div>
                                      <div>Exp: <span className="text-white">{leg.expiration}</span></div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Risk Checks */}
                          {decision.full_decision?.risk_checks && decision.full_decision.risk_checks.length > 0 && (
                            <div className="bg-gray-800/50 rounded p-2">
                              <div className="flex items-center gap-2 mb-2">
                                <Shield className="w-4 h-4 text-blue-400" />
                                <span className="text-blue-400 text-xs font-bold">RISK CHECKS:</span>
                              </div>
                              <div className="flex flex-wrap gap-2">
                                {decision.full_decision.risk_checks.map((check, idx) => (
                                  <span
                                    key={idx}
                                    className={`px-2 py-0.5 rounded text-xs ${
                                      check.passed
                                        ? 'bg-green-900/50 text-green-400'
                                        : 'bg-red-900/50 text-red-400'
                                    }`}
                                  >
                                    {check.passed ? '✓' : '✗'} {check.check}
                                    {check.value && <span className="ml-1 opacity-75">({check.value})</span>}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Position Size */}
                          {(decision.full_decision?.position_size_contracts || decision.full_decision?.position_size_dollars) && (
                            <div className="flex gap-4 text-xs">
                              {decision.full_decision.position_size_contracts && (
                                <div>
                                  <span className="text-gray-500">Contracts:</span>
                                  <span className="text-white ml-1">{decision.full_decision.position_size_contracts}</span>
                                </div>
                              )}
                              {decision.full_decision.position_size_dollars && (
                                <div>
                                  <span className="text-gray-500">Position Size:</span>
                                  <span className="text-white ml-1">${decision.full_decision.position_size_dollars.toLocaleString()}</span>
                                </div>
                              )}
                            </div>
                          )}

                          {/* Outcome */}
                          {decision.outcome && (
                            <div className="pt-2 border-t border-gray-700/50">
                              <span className="text-green-400 text-xs font-bold">OUTCOME: </span>
                              <span className="text-sm text-gray-300">{decision.outcome}</span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })
              ) : (
                <div className="text-center py-8 text-gray-500">
                  <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
                  <p>No decisions recorded yet</p>
                  <p className="text-xs mt-1">Decisions will appear here when ARES makes trading decisions</p>
                </div>
              )}
            </div>
          </div>

          {/* Footer */}
          <div className="mt-6 text-center text-sm text-gray-500">
            Auto-refresh every 30 seconds • Cached across pages
          </div>
        </div>
      </main>
    </div>
  )
}
