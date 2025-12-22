'use client'

import { useState } from 'react'
import { Sword, TrendingUp, TrendingDown, Activity, DollarSign, Target, RefreshCw, BarChart3, ChevronDown, ChevronUp, Server, Play, AlertTriangle, Clock, Zap, Brain, Shield, Crosshair, TrendingUp as TrendUp, FileText, ListChecks } from 'lucide-react'
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

interface Heartbeat {
  last_scan: string | null
  last_scan_iso: string | null
  status: string
  scan_count_today: number
  details: Record<string, any>
}

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
  scan_interval_minutes?: number
  heartbeat?: Heartbeat
  config: {
    risk_per_trade: number
    spread_width: number
    sd_multiplier: number
    ticker: string
  }
}

interface IronCondorPosition {
  position_id: string
  ticker?: string  // SPX or SPY
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
  spread_width?: number
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
  underlying_price_at_entry?: number
  underlying_price_at_exit?: number
  outcome_notes?: string
  // Trade legs with Greeks
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
  // Oracle AI advice
  oracle_advice?: {
    advice: string
    win_probability: number
    confidence: number
    suggested_risk_pct: number
    suggested_sd_multiplier: number
    use_gex_walls: boolean
    suggested_put_strike?: number
    suggested_call_strike?: number
    top_factors: Array<[string, number]>
    reasoning: string
    model_version: string
    claude_analysis?: {
      analysis: string
      confidence_adjustment: number
      risk_factors: string[]
      opportunities: string[]
      recommendation: string
    }
  }
  // GEX context
  gex_context?: {
    net_gex: number
    gex_normalized: number
    call_wall: number
    put_wall: number
    flip_point: number
    distance_to_flip_pct: number
    regime: string
    between_walls: boolean
  }
  // Market context
  market_context?: {
    spot_price: number
    vix: number
    vix_percentile: number
    expected_move: number
    trend: string
    day_of_week: number
    days_to_opex: number
  }
  // Backtest statistics
  backtest_stats?: {
    strategy_name: string
    win_rate: number
    expectancy: number
    avg_win: number
    avg_loss: number
    sharpe_ratio: number
    max_drawdown: number
    total_trades: number
    uses_real_data: boolean
    backtest_period: string
  }
  // Position sizing
  position_sizing?: {
    contracts: number
    position_dollars: number
    max_risk_dollars: number
    sizing_method: string
    target_profit_pct: number
    stop_loss_pct: number
    probability_of_profit: number
  }
  // Alternatives considered
  alternatives?: {
    primary_reason: string
    supporting_factors: string[]
    risk_factors: string[]
    alternatives_considered: string[]
    why_not_alternatives: string[]
  }
  // Risk checks
  risk_checks?: Array<{
    check: string
    passed: boolean
    value?: string
  }>
  passed_risk_checks?: boolean
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

  // Helper to determine if position is SPX or SPY
  const isSPX = (pos: IronCondorPosition) => pos.ticker === 'SPX' || (!pos.ticker && (pos.spread_width || 10) > 5)
  const isSPY = (pos: IronCondorPosition) => pos.ticker === 'SPY' || (!pos.ticker && (pos.spread_width || 10) <= 5)

  // Filter positions by ticker
  const spxOpenPositions = positions.filter(isSPX)
  const spyOpenPositions = positions.filter(isSPY)
  const spxClosedPositions = closedPositions.filter(isSPX)
  const spyClosedPositions = closedPositions.filter(isSPY)

  // Helper to calculate max drawdown from closed positions
  const calcMaxDrawdown = (closedPositions: IronCondorPosition[]) => {
    if (closedPositions.length === 0) return 0
    let peak = 0
    let maxDrawdown = 0
    let cumulative = 0
    closedPositions.forEach(p => {
      cumulative += p.realized_pnl || 0
      if (cumulative > peak) peak = cumulative
      const drawdown = peak - cumulative
      if (drawdown > maxDrawdown) maxDrawdown = drawdown
    })
    return maxDrawdown
  }

  // Calculate SPX stats
  const spxStats = {
    capital: 200000, // Starting capital allocated to SPX
    totalPnl: spxClosedPositions.reduce((sum, p) => sum + (p.realized_pnl || 0), 0),
    totalTrades: spxClosedPositions.length,
    winningTrades: spxClosedPositions.filter(p => (p.realized_pnl || 0) > 0).length,
    losingTrades: spxClosedPositions.filter(p => (p.realized_pnl || 0) <= 0).length,
    winRate: spxClosedPositions.length > 0
      ? (spxClosedPositions.filter(p => (p.realized_pnl || 0) > 0).length / spxClosedPositions.length) * 100
      : 0,
    bestTrade: spxClosedPositions.length > 0 ? Math.max(...spxClosedPositions.map(p => p.realized_pnl || 0)) : 0,
    worstTrade: spxClosedPositions.length > 0 ? Math.min(...spxClosedPositions.map(p => p.realized_pnl || 0)) : 0,
    maxDrawdown: calcMaxDrawdown(spxClosedPositions),
    avgTrade: spxClosedPositions.length > 0
      ? spxClosedPositions.reduce((sum, p) => sum + (p.realized_pnl || 0), 0) / spxClosedPositions.length
      : 0,
  }

  // Calculate SPY stats
  const spyStats = {
    capital: tradierStatus?.account?.equity || 102000, // From Tradier or default
    totalPnl: spyClosedPositions.reduce((sum, p) => sum + (p.realized_pnl || 0), 0),
    totalTrades: spyClosedPositions.length,
    winningTrades: spyClosedPositions.filter(p => (p.realized_pnl || 0) > 0).length,
    losingTrades: spyClosedPositions.filter(p => (p.realized_pnl || 0) <= 0).length,
    winRate: spyClosedPositions.length > 0
      ? (spyClosedPositions.filter(p => (p.realized_pnl || 0) > 0).length / spyClosedPositions.length) * 100
      : 0,
    bestTrade: spyClosedPositions.length > 0 ? Math.max(...spyClosedPositions.map(p => p.realized_pnl || 0)) : 0,
    worstTrade: spyClosedPositions.length > 0 ? Math.min(...spyClosedPositions.map(p => p.realized_pnl || 0)) : 0,
    maxDrawdown: calcMaxDrawdown(spyClosedPositions),
    avgTrade: spyClosedPositions.length > 0
      ? spyClosedPositions.reduce((sum, p) => sum + (p.realized_pnl || 0), 0) / spyClosedPositions.length
      : 0,
  }

  // Build equity curve from closed positions for a specific ticker
  const buildEquityCurve = (positions: IronCondorPosition[], startingCapital: number) => {
    if (positions.length === 0) return []

    // Sort by close date
    const sorted = [...positions].sort((a, b) =>
      (a.close_date || a.expiration || '').localeCompare(b.close_date || b.expiration || '')
    )

    // Group by date
    const byDate: Record<string, number> = {}
    sorted.forEach(p => {
      const date = p.close_date || p.expiration || ''
      if (date) {
        byDate[date] = (byDate[date] || 0) + (p.realized_pnl || 0)
      }
    })

    // Build curve
    let cumPnl = 0
    const dates = Object.keys(byDate).sort()
    return dates.map(date => {
      cumPnl += byDate[date]
      return {
        date,
        equity: startingCapital + cumPnl,
        daily_pnl: byDate[date],
        pnl: cumPnl
      }
    })
  }

  // Separate equity curves for SPX and SPY
  const spxEquityData = buildEquityCurve(spxClosedPositions, spxStats.capital)
  const spyEquityData = buildEquityCurve(spyClosedPositions, spyStats.capital)

  // UI State - default to expanded for better visibility
  const [showSpxPositions, setShowSpxPositions] = useState(true)
  const [showSpyPositions, setShowSpyPositions] = useState(true)
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

          {/* Heartbeat Status Bar */}
          <div className="mb-4 bg-gray-800/50 rounded-lg p-3 border border-gray-700">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${
                    status?.heartbeat?.status === 'TRADED' ? 'bg-green-500 animate-pulse' :
                    status?.heartbeat?.status === 'SCAN_COMPLETE' ? 'bg-blue-500' :
                    status?.heartbeat?.status === 'ERROR' ? 'bg-red-500' :
                    status?.heartbeat?.status === 'MARKET_CLOSED' ? 'bg-yellow-500' :
                    'bg-gray-500'
                  }`} />
                  <span className="text-gray-400 text-sm">Heartbeat</span>
                </div>
                <div className="text-sm">
                  <span className="text-gray-500">Last Scan: </span>
                  <span className={`font-mono ${status?.heartbeat?.last_scan ? 'text-white' : 'text-gray-500'}`}>
                    {status?.heartbeat?.last_scan || 'Never'}
                  </span>
                </div>
                <div className="text-sm">
                  <span className="text-gray-500">Status: </span>
                  <span className={`font-medium ${
                    status?.heartbeat?.status === 'TRADED' ? 'text-green-400' :
                    status?.heartbeat?.status === 'SCAN_COMPLETE' ? 'text-blue-400' :
                    status?.heartbeat?.status === 'ERROR' ? 'text-red-400' :
                    'text-gray-400'
                  }`}>
                    {status?.heartbeat?.status?.replace(/_/g, ' ') || 'Unknown'}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-4 text-sm">
                <div>
                  <span className="text-gray-500">Scans Today: </span>
                  <span className="text-white font-bold">{status?.heartbeat?.scan_count_today || 0}</span>
                </div>
                <div>
                  <span className="text-gray-500">Interval: </span>
                  <span className="text-cyan-400">{status?.scan_interval_minutes || 5} min</span>
                </div>
                <Clock className="w-4 h-4 text-gray-500" />
              </div>
            </div>
          </div>

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
                      {formatCurrency(spxStats.capital + spxStats.totalPnl)}
                    </p>
                  </div>
                  <div className="bg-gray-800/60 rounded-lg p-3 text-center">
                    <span className="text-gray-400 text-xs">Total P&L</span>
                    <p className={`font-bold text-lg ${spxStats.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {formatCurrency(spxStats.totalPnl)}
                    </p>
                    <span className="text-xs text-gray-500">
                      ({formatPercent((spxStats.totalPnl / spxStats.capital) * 100)})
                    </span>
                  </div>
                  <div className="bg-gray-800/60 rounded-lg p-3 text-center">
                    <span className="text-gray-400 text-xs">Win Rate</span>
                    <p className="text-white font-bold text-lg">
                      {spxStats.winRate.toFixed(1)}%
                    </p>
                    <span className="text-xs text-gray-500">
                      {spxStats.winningTrades}W / {spxStats.losingTrades}L
                    </span>
                  </div>
                  <div className="bg-gray-800/60 rounded-lg p-3 text-center">
                    <span className="text-gray-400 text-xs">Trades</span>
                    <p className="text-white font-bold text-lg">
                      {spxStats.totalTrades}
                    </p>
                    <span className="text-xs text-gray-500">
                      {spxOpenPositions.length} open
                    </span>
                  </div>
                </div>

                {/* Additional Metrics */}
                <div className="px-4 pb-4 grid grid-cols-4 gap-3">
                  <div className="bg-gray-800/40 rounded p-2 text-center">
                    <span className="text-gray-500 text-xs">Best Trade</span>
                    <p className="text-green-400 font-medium">{formatCurrency(spxStats.bestTrade)}</p>
                  </div>
                  <div className="bg-gray-800/40 rounded p-2 text-center">
                    <span className="text-gray-500 text-xs">Worst Trade</span>
                    <p className="text-red-400 font-medium">{formatCurrency(spxStats.worstTrade)}</p>
                  </div>
                  <div className="bg-gray-800/40 rounded p-2 text-center">
                    <span className="text-gray-500 text-xs">Max Drawdown</span>
                    <p className="text-orange-400 font-medium">{formatCurrency(spxStats.maxDrawdown)}</p>
                  </div>
                  <div className="bg-gray-800/40 rounded p-2 text-center">
                    <span className="text-gray-500 text-xs">Avg Trade</span>
                    <p className="text-yellow-400 font-medium">{formatCurrency(spxStats.avgTrade)}</p>
                  </div>
                </div>

                {/* Equity Curve - SPX Only */}
                <div className="px-4 pb-4">
                  <h4 className="text-sm font-medium text-purple-300 mb-2 flex items-center gap-2">
                    <BarChart3 className="w-4 h-4" />
                    SPX Equity Curve
                    {spxStats.totalPnl !== 0 && (
                      <span className={`text-xs ml-auto ${spxStats.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {spxStats.totalPnl >= 0 ? '+' : ''}{formatCurrency(spxStats.totalPnl)}
                      </span>
                    )}
                  </h4>
                  <div className="h-40 bg-gray-800/40 rounded-lg p-2">
                    {spxEquityData.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={spxEquityData}>
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

                {/* Recent Trades - SPX only */}
                <div className="px-4 pb-4">
                  <h4 className="text-sm font-medium text-purple-300 mb-2">
                    Recent Closed Trades
                    <span className="text-xs text-gray-500 ml-2">
                      ({closedPositions.filter(p => p.ticker === 'SPX' || (!p.ticker && (p.spread_width || 10) > 5)).length} SPX)
                    </span>
                  </h4>
                  <div className="space-y-1 max-h-40 overflow-y-auto">
                    {closedPositions
                      .filter(p => p.ticker === 'SPX' || (!p.ticker && (p.spread_width || 10) > 5))
                      .slice(0, 10)
                      .map((pos) => (
                      <div key={pos.position_id} className="flex items-center justify-between text-xs bg-gray-800/30 rounded p-2">
                        <div className="flex items-center gap-2">
                          <span className="text-gray-400">{pos.close_date || pos.expiration}</span>
                          <span className="px-1 py-0.5 bg-purple-900/50 text-purple-300 rounded text-[10px]">SPX</span>
                        </div>
                        <span className="text-gray-300 font-mono">
                          {pos.put_short_strike}P / {pos.call_short_strike}C
                        </span>
                        <span className={(pos.realized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}>
                          {formatCurrency(pos.realized_pnl || pos.total_credit * 100 * pos.contracts)}
                        </span>
                      </div>
                    ))}
                    {closedPositions.filter(p => p.ticker === 'SPX' || (!p.ticker && (p.spread_width || 10) > 5)).length === 0 && (
                      <p className="text-xs text-gray-500 text-center py-2">No SPX closed trades yet</p>
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
                    {/* Stats Grid - Matches SPX layout */}
                    <div className="p-4 grid grid-cols-2 md:grid-cols-4 gap-3">
                      <div className="bg-gray-800/60 rounded-lg p-3 text-center">
                        <span className="text-gray-400 text-xs">Capital</span>
                        <p className="text-white font-bold text-lg">
                          {formatCurrency(spyStats.capital + spyStats.totalPnl)}
                        </p>
                      </div>
                      <div className="bg-gray-800/60 rounded-lg p-3 text-center">
                        <span className="text-gray-400 text-xs">Total P&L</span>
                        <p className={`font-bold text-lg ${spyStats.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {formatCurrency(spyStats.totalPnl)}
                        </p>
                        <span className="text-xs text-gray-500">
                          ({formatPercent((spyStats.totalPnl / spyStats.capital) * 100)})
                        </span>
                      </div>
                      <div className="bg-gray-800/60 rounded-lg p-3 text-center">
                        <span className="text-gray-400 text-xs">Win Rate</span>
                        <p className="text-white font-bold text-lg">
                          {spyStats.winRate.toFixed(1)}%
                        </p>
                        <span className="text-xs text-gray-500">
                          {spyStats.winningTrades}W / {spyStats.losingTrades}L
                        </span>
                      </div>
                      <div className="bg-gray-800/60 rounded-lg p-3 text-center">
                        <span className="text-gray-400 text-xs">Trades</span>
                        <p className="text-white font-bold text-lg">
                          {spyStats.totalTrades}
                        </p>
                        <span className="text-xs text-gray-500">
                          {spyOpenPositions.length} open
                        </span>
                      </div>
                    </div>

                    {/* Additional Metrics - Matches SPX layout */}
                    <div className="px-4 pb-4 grid grid-cols-4 gap-3">
                      <div className="bg-gray-800/40 rounded p-2 text-center">
                        <span className="text-gray-500 text-xs">Best Trade</span>
                        <p className="text-green-400 font-medium">{formatCurrency(spyStats.bestTrade)}</p>
                      </div>
                      <div className="bg-gray-800/40 rounded p-2 text-center">
                        <span className="text-gray-500 text-xs">Worst Trade</span>
                        <p className="text-red-400 font-medium">{formatCurrency(spyStats.worstTrade)}</p>
                      </div>
                      <div className="bg-gray-800/40 rounded p-2 text-center">
                        <span className="text-gray-500 text-xs">Max Drawdown</span>
                        <p className="text-orange-400 font-medium">{formatCurrency(spyStats.maxDrawdown)}</p>
                      </div>
                      <div className="bg-gray-800/40 rounded p-2 text-center">
                        <span className="text-gray-500 text-xs">Avg Trade</span>
                        <p className="text-yellow-400 font-medium">{formatCurrency(spyStats.avgTrade)}</p>
                      </div>
                    </div>

                    {/* Equity Curve - SPY Only */}
                    <div className="px-4 pb-4">
                      <h4 className="text-sm font-medium text-blue-300 mb-2 flex items-center gap-2">
                        <BarChart3 className="w-4 h-4" />
                        SPY Equity Curve
                        {spyStats.totalPnl !== 0 && (
                          <span className={`text-xs ml-auto ${spyStats.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {spyStats.totalPnl >= 0 ? '+' : ''}{formatCurrency(spyStats.totalPnl)}
                          </span>
                        )}
                      </h4>
                      <div className="h-40 bg-gray-800/40 rounded-lg p-2">
                        {spyEquityData.length > 0 ? (
                          <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={spyEquityData}>
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

                    {/* Recent Orders from Tradier */}
                    <div className="px-4 pb-4">
                      <h4 className="text-sm font-medium text-blue-300 mb-2">
                        Recent Orders (Tradier)
                        <span className="text-xs text-gray-500 ml-2">
                          ({tradierStatus?.orders?.length || 0} total)
                        </span>
                      </h4>
                      <div className="space-y-1 max-h-32 overflow-y-auto">
                        {tradierStatus?.orders && tradierStatus.orders.length > 0 ? tradierStatus.orders.slice(0, 10).map((order) => (
                          <div key={order.id} className="flex items-center justify-between text-xs bg-gray-800/30 rounded p-2">
                            <span className="text-white font-mono">{order.symbol}</span>
                            <span className={order.side === 'buy' ? 'text-green-400' : 'text-red-400'}>
                              {order.side.toUpperCase()} x{order.quantity}
                            </span>
                            <span className={`px-2 py-0.5 rounded ${
                              order.status === 'filled' ? 'bg-green-900 text-green-300' :
                              order.status === 'pending' ? 'bg-yellow-900 text-yellow-300' :
                              order.status === 'canceled' ? 'bg-gray-700 text-gray-300' :
                              order.status === 'expired' ? 'bg-purple-900 text-purple-300' :
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

                    {/* SPY Closed Trades from AlphaGEX tracking */}
                    <div className="px-4 pb-4">
                      <h4 className="text-sm font-medium text-blue-300 mb-2">
                        Closed SPY Trades
                        <span className="text-xs text-gray-500 ml-2">
                          ({closedPositions.filter(p => p.ticker === 'SPY' || (!p.ticker && (p.spread_width || 10) <= 5)).length} SPY)
                        </span>
                      </h4>
                      <div className="space-y-1 max-h-40 overflow-y-auto">
                        {closedPositions
                          .filter(p => p.ticker === 'SPY' || (!p.ticker && (p.spread_width || 10) <= 5))
                          .slice(0, 10)
                          .map((pos) => (
                          <div key={pos.position_id} className="flex items-center justify-between text-xs bg-gray-800/30 rounded p-2">
                            <div className="flex items-center gap-2">
                              <span className="text-gray-400">{pos.close_date || pos.expiration}</span>
                              <span className="px-1 py-0.5 bg-blue-900/50 text-blue-300 rounded text-[10px]">SPY</span>
                            </div>
                            <span className="text-gray-300 font-mono">
                              {pos.put_short_strike}P / {pos.call_short_strike}C
                            </span>
                            <span className={(pos.realized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}>
                              {formatCurrency(pos.realized_pnl || pos.total_credit * 100 * pos.contracts)}
                            </span>
                          </div>
                        ))}
                        {closedPositions.filter(p => p.ticker === 'SPY' || (!p.ticker && (p.spread_width || 10) <= 5)).length === 0 && (
                          <p className="text-xs text-gray-500 text-center py-2">No SPY closed trades yet</p>
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

            <div className="p-4 space-y-3 max-h-[800px] overflow-y-auto">
              {decisions.length > 0 ? (
                decisions.map((decision) => {
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

                      {/* Expanded Details - Full Audit Trail */}
                      {isExpanded && (
                        <div className="px-3 pb-3 space-y-3 border-t border-gray-700/50 pt-3">
                          {/* WHY Section */}
                          <div className="bg-yellow-900/10 border-l-2 border-yellow-500 pl-3 py-2">
                            <span className="text-yellow-400 text-xs font-bold">WHY:</span>
                            <p className="text-sm text-gray-300 mt-1">{decision.why || 'Not specified'}</p>
                            {decision.alternatives?.supporting_factors && decision.alternatives.supporting_factors.length > 0 && (
                              <div className="mt-2">
                                <span className="text-xs text-gray-500">Supporting Factors:</span>
                                <ul className="list-disc list-inside text-xs text-gray-400 mt-1">
                                  {decision.alternatives.supporting_factors.map((f, i) => (
                                    <li key={i}>{f}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>

                          {/* HOW Section */}
                          {decision.how && (
                            <div className="bg-blue-900/10 border-l-2 border-blue-500 pl-3 py-2">
                              <span className="text-blue-400 text-xs font-bold">HOW:</span>
                              <p className="text-sm text-gray-300 mt-1">{decision.how}</p>
                            </div>
                          )}

                          {/* Market Context & GEX - Side by Side */}
                          <div className="grid grid-cols-2 gap-3">
                            {/* Market Context */}
                            <div className="bg-gray-800/50 rounded p-2">
                              <span className="text-cyan-400 text-xs font-bold">MARKET AT DECISION:</span>
                              <div className="grid grid-cols-2 gap-2 mt-2 text-xs">
                                <div>
                                  <span className="text-gray-500">{decision.symbol}:</span>
                                  <span className="text-white ml-1">${(decision.market_context?.spot_price || decision.underlying_price_at_entry || 0).toLocaleString()}</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">VIX:</span>
                                  <span className="text-yellow-400 ml-1">{(decision.market_context?.vix || decision.vix || 0).toFixed(1)}</span>
                                </div>
                                {decision.market_context?.expected_move && (
                                  <div>
                                    <span className="text-gray-500">Exp Move:</span>
                                    <span className="text-white ml-1">{decision.market_context.expected_move.toFixed(2)}%</span>
                                  </div>
                                )}
                                {decision.market_context?.trend && (
                                  <div>
                                    <span className="text-gray-500">Trend:</span>
                                    <span className="text-white ml-1">{decision.market_context.trend}</span>
                                  </div>
                                )}
                              </div>
                            </div>

                            {/* GEX Context */}
                            <div className="bg-purple-900/20 border border-purple-700/30 rounded p-2">
                              <div className="flex items-center gap-1 mb-2">
                                <Crosshair className="w-3 h-3 text-purple-400" />
                                <span className="text-purple-400 text-xs font-bold">GEX LEVELS:</span>
                              </div>
                              <div className="grid grid-cols-2 gap-2 text-xs">
                                <div>
                                  <span className="text-gray-500">Put Wall:</span>
                                  <span className="text-green-400 ml-1">${decision.gex_context?.put_wall || '-'}</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">Call Wall:</span>
                                  <span className="text-red-400 ml-1">${decision.gex_context?.call_wall || '-'}</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">Flip:</span>
                                  <span className="text-white ml-1">${decision.gex_context?.flip_point || '-'}</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">Regime:</span>
                                  <span className={`ml-1 ${decision.gex_context?.regime === 'POSITIVE' ? 'text-green-400' : decision.gex_context?.regime === 'NEGATIVE' ? 'text-red-400' : 'text-gray-400'}`}>
                                    {decision.gex_context?.regime || '-'}
                                  </span>
                                </div>
                                {decision.gex_context?.net_gex && (
                                  <div className="col-span-2">
                                    <span className="text-gray-500">Net GEX:</span>
                                    <span className="text-white ml-1">{(decision.gex_context.net_gex / 1e9).toFixed(2)}B</span>
                                    {decision.gex_context.between_walls !== undefined && (
                                      <span className={`ml-2 text-xs ${decision.gex_context.between_walls ? 'text-green-400' : 'text-red-400'}`}>
                                        {decision.gex_context.between_walls ? '(In Pin Zone)' : '(Outside Walls)'}
                                      </span>
                                    )}
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>

                          {/* Oracle AI Advice - Enhanced */}
                          {decision.oracle_advice && (
                            <div className="bg-green-900/20 border border-green-700/30 rounded p-2">
                              <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-2">
                                  <Brain className="w-4 h-4 text-green-400" />
                                  <span className="text-green-400 text-xs font-bold">ORACLE AI PREDICTION:</span>
                                </div>
                                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                  decision.oracle_advice.advice === 'TRADE_FULL' ? 'bg-green-900/50 text-green-400' :
                                  decision.oracle_advice.advice === 'TRADE_REDUCED' ? 'bg-yellow-900/50 text-yellow-400' :
                                  'bg-red-900/50 text-red-400'
                                }`}>
                                  {decision.oracle_advice.advice?.replace(/_/g, ' ')}
                                </span>
                              </div>
                              <div className="grid grid-cols-4 gap-2 text-xs mb-2">
                                <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                  <span className="text-gray-500 block">Win Prob</span>
                                  <span className="text-green-400 font-bold">{((decision.oracle_advice.win_probability || 0) * 100).toFixed(0)}%</span>
                                </div>
                                <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                  <span className="text-gray-500 block">Confidence</span>
                                  <span className="text-white font-bold">{((decision.oracle_advice.confidence || 0) * 100).toFixed(0)}%</span>
                                </div>
                                <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                  <span className="text-gray-500 block">Risk %</span>
                                  <span className="text-yellow-400 font-bold">{(decision.oracle_advice.suggested_risk_pct || 0).toFixed(1)}%</span>
                                </div>
                                <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                  <span className="text-gray-500 block">SD Mult</span>
                                  <span className="text-white font-bold">{(decision.oracle_advice.suggested_sd_multiplier || 0).toFixed(2)}</span>
                                </div>
                              </div>
                              {decision.oracle_advice.use_gex_walls && (
                                <div className="text-xs text-purple-400 mb-1">
                                  Using GEX Walls (72% historical win rate)
                                </div>
                              )}
                              {decision.oracle_advice.top_factors && decision.oracle_advice.top_factors.length > 0 && (
                                <div className="mt-2">
                                  <span className="text-xs text-gray-500">Top Factors:</span>
                                  <div className="flex flex-wrap gap-1 mt-1">
                                    {decision.oracle_advice.top_factors.slice(0, 5).map(([factor, weight], i) => (
                                      <span key={i} className="px-1.5 py-0.5 bg-gray-800 rounded text-xs text-gray-300">
                                        {factor}: <span className="text-green-400">{(weight * 100).toFixed(0)}%</span>
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}
                              {decision.oracle_advice.reasoning && (
                                <p className="text-xs text-gray-400 mt-2 italic">{decision.oracle_advice.reasoning}</p>
                              )}
                              {decision.oracle_advice.claude_analysis && (
                                <div className="mt-2 pt-2 border-t border-green-700/30">
                                  <span className="text-xs text-green-300 font-medium">Claude AI Analysis:</span>
                                  <p className="text-xs text-gray-400 mt-1">{decision.oracle_advice.claude_analysis.analysis}</p>
                                  {decision.oracle_advice.claude_analysis.risk_factors?.length > 0 && (
                                    <div className="flex flex-wrap gap-1 mt-1">
                                      {decision.oracle_advice.claude_analysis.risk_factors.map((rf, i) => (
                                        <span key={i} className="px-1.5 py-0.5 bg-red-900/30 rounded text-xs text-red-400">{rf}</span>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          )}

                          {/* Backtest Statistics */}
                          {decision.backtest_stats && decision.backtest_stats.total_trades > 0 && (
                            <div className="bg-blue-900/20 border border-blue-700/30 rounded p-2">
                              <div className="flex items-center gap-2 mb-2">
                                <BarChart3 className="w-4 h-4 text-blue-400" />
                                <span className="text-blue-400 text-xs font-bold">BACKTEST BACKING:</span>
                                {decision.backtest_stats.uses_real_data && (
                                  <span className="px-1.5 py-0.5 bg-green-900/50 rounded text-xs text-green-400">Real Data</span>
                                )}
                              </div>
                              <div className="grid grid-cols-4 gap-2 text-xs">
                                <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                  <span className="text-gray-500 block">Win Rate</span>
                                  <span className="text-green-400 font-bold">{(decision.backtest_stats.win_rate || 0).toFixed(1)}%</span>
                                </div>
                                <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                  <span className="text-gray-500 block">Expectancy</span>
                                  <span className="text-white font-bold">${(decision.backtest_stats.expectancy || 0).toFixed(0)}</span>
                                </div>
                                <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                  <span className="text-gray-500 block">Sharpe</span>
                                  <span className="text-white font-bold">{(decision.backtest_stats.sharpe_ratio || 0).toFixed(2)}</span>
                                </div>
                                <div className="bg-gray-800/50 rounded p-1.5 text-center">
                                  <span className="text-gray-500 block">Trades</span>
                                  <span className="text-white font-bold">{decision.backtest_stats.total_trades}</span>
                                </div>
                              </div>
                              {decision.backtest_stats.backtest_period && (
                                <p className="text-xs text-gray-500 mt-1">Period: {decision.backtest_stats.backtest_period}</p>
                              )}
                            </div>
                          )}

                          {/* Position Sizing */}
                          {decision.position_sizing && (decision.position_sizing.contracts > 0 || decision.position_sizing.position_dollars > 0) && (
                            <div className="bg-gray-800/50 rounded p-2">
                              <div className="flex items-center gap-2 mb-2">
                                <DollarSign className="w-4 h-4 text-yellow-400" />
                                <span className="text-yellow-400 text-xs font-bold">POSITION SIZING:</span>
                              </div>
                              <div className="grid grid-cols-4 gap-2 text-xs">
                                <div>
                                  <span className="text-gray-500">Contracts:</span>
                                  <span className="text-white ml-1 font-bold">{decision.position_sizing.contracts}</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">Premium:</span>
                                  <span className="text-green-400 ml-1">${(decision.position_sizing.position_dollars || 0).toLocaleString()}</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">Max Risk:</span>
                                  <span className="text-red-400 ml-1">${(decision.position_sizing.max_risk_dollars || 0).toLocaleString()}</span>
                                </div>
                                {decision.position_sizing.probability_of_profit > 0 && (
                                  <div>
                                    <span className="text-gray-500">POP:</span>
                                    <span className="text-white ml-1">{(decision.position_sizing.probability_of_profit * 100).toFixed(0)}%</span>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Trade Legs with Greeks */}
                          {decision.legs && decision.legs.length > 0 && (
                            <div className="bg-gray-800/50 rounded p-2">
                              <div className="flex items-center gap-2 mb-2">
                                <Target className="w-4 h-4 text-orange-400" />
                                <span className="text-orange-400 text-xs font-bold">TRADE LEGS ({decision.legs.length}):</span>
                              </div>
                              <div className="overflow-x-auto">
                                <table className="w-full text-xs">
                                  <thead>
                                    <tr className="text-gray-500 border-b border-gray-700">
                                      <th className="text-left py-1 px-1">Leg</th>
                                      <th className="text-left py-1 px-1">Type</th>
                                      <th className="text-right py-1 px-1">Strike</th>
                                      <th className="text-right py-1 px-1">Entry</th>
                                      <th className="text-right py-1 px-1">Exit</th>
                                      <th className="text-right py-1 px-1">Delta</th>
                                      <th className="text-right py-1 px-1">Theta</th>
                                      <th className="text-right py-1 px-1">IV</th>
                                      <th className="text-right py-1 px-1">P&L</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {decision.legs.map((leg, idx) => (
                                      <tr key={idx} className="border-b border-gray-700/50">
                                        <td className="py-1 px-1 text-gray-400">{leg.leg_id}</td>
                                        <td className="py-1 px-1">
                                          <span className={leg.action === 'SELL' ? 'text-red-400' : 'text-green-400'}>
                                            {leg.action} {leg.option_type?.toUpperCase()}
                                          </span>
                                        </td>
                                        <td className="py-1 px-1 text-right text-white">${leg.strike}</td>
                                        <td className="py-1 px-1 text-right text-white">${leg.entry_price?.toFixed(2) || '-'}</td>
                                        <td className="py-1 px-1 text-right text-white">${leg.exit_price?.toFixed(2) || '-'}</td>
                                        <td className="py-1 px-1 text-right text-gray-300">{leg.delta?.toFixed(3) || '-'}</td>
                                        <td className="py-1 px-1 text-right text-green-400">${leg.theta?.toFixed(2) || '-'}</td>
                                        <td className="py-1 px-1 text-right text-gray-300">{leg.iv ? (leg.iv * 100).toFixed(1) + '%' : '-'}</td>
                                        <td className={`py-1 px-1 text-right font-medium ${(leg.realized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                          {leg.realized_pnl ? '$' + leg.realized_pnl.toFixed(2) : '-'}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          )}

                          {/* Alternatives Considered */}
                          {decision.alternatives?.alternatives_considered && decision.alternatives.alternatives_considered.length > 0 && (
                            <div className="bg-gray-800/50 rounded p-2">
                              <div className="flex items-center gap-2 mb-2">
                                <ListChecks className="w-4 h-4 text-gray-400" />
                                <span className="text-gray-400 text-xs font-bold">ALTERNATIVES CONSIDERED:</span>
                              </div>
                              <div className="space-y-1">
                                {decision.alternatives.alternatives_considered.map((alt, idx) => (
                                  <div key={idx} className="flex items-start gap-2 text-xs">
                                    <span className="text-red-400">✗</span>
                                    <span className="text-gray-400">{alt}</span>
                                    {decision.alternatives?.why_not_alternatives?.[idx] && (
                                      <span className="text-gray-500 italic">- {decision.alternatives.why_not_alternatives[idx]}</span>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Risk Checks */}
                          {decision.risk_checks && decision.risk_checks.length > 0 && (
                            <div className="bg-gray-800/50 rounded p-2">
                              <div className="flex items-center gap-2 mb-2">
                                <Shield className="w-4 h-4 text-blue-400" />
                                <span className="text-blue-400 text-xs font-bold">RISK CHECKS:</span>
                                <span className={`ml-auto px-1.5 py-0.5 rounded text-xs ${decision.passed_risk_checks !== false ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'}`}>
                                  {decision.passed_risk_checks !== false ? 'ALL PASSED' : 'FAILED'}
                                </span>
                              </div>
                              <div className="flex flex-wrap gap-1">
                                {decision.risk_checks.map((check, idx) => (
                                  <span
                                    key={idx}
                                    className={`px-2 py-0.5 rounded text-xs ${
                                      check.passed ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'
                                    }`}
                                  >
                                    {check.passed ? '✓' : '✗'} {check.check}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Outcome / Exit Context */}
                          {(decision.outcome || decision.outcome_notes || (decision.underlying_price_at_exit && decision.underlying_price_at_exit > 0)) && (
                            <div className="bg-gray-900/50 rounded p-2 border-t-2 border-gray-600">
                              <span className="text-green-400 text-xs font-bold">OUTCOME:</span>
                              <div className="grid grid-cols-3 gap-2 mt-2 text-xs">
                                {decision.underlying_price_at_exit && decision.underlying_price_at_exit > 0 && (
                                  <div>
                                    <span className="text-gray-500">Exit Price:</span>
                                    <span className="text-white ml-1">${decision.underlying_price_at_exit.toLocaleString()}</span>
                                  </div>
                                )}
                                {decision.actual_pnl !== undefined && (
                                  <div>
                                    <span className="text-gray-500">P&L:</span>
                                    <span className={`ml-1 font-bold ${decision.actual_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                      {decision.actual_pnl >= 0 ? '+' : ''}{formatCurrency(decision.actual_pnl)}
                                    </span>
                                  </div>
                                )}
                              </div>
                              {(decision.outcome || decision.outcome_notes) && (
                                <p className="text-sm text-gray-300 mt-2">{decision.outcome || decision.outcome_notes}</p>
                              )}
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
