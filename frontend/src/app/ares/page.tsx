'use client'

import { useState } from 'react'
import { Sword, TrendingUp, TrendingDown, Activity, DollarSign, Target, RefreshCw, BarChart3, ChevronDown, ChevronUp, Server, Play, AlertTriangle, Clock, Zap, Brain, Shield, Crosshair, TrendingUp as TrendUp, FileText, ListChecks, Settings } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
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
  ticker?: string
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
  spx?: { ticker: string; price: number; expected_move: number }
  spy?: { ticker: string; price: number; expected_move: number }
  // GEX data
  gex_context?: {
    put_wall: number
    call_wall: number
    net_gex: number
    regime: string
    flip_point: number
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
  positions: Array<{ symbol: string; quantity: number; cost_basis: number; date_acquired?: string }>
  orders: Array<{ id: string; symbol: string; side: string; quantity: number; status: string; type?: string; price?: number; created_date?: string }>
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
  legs?: Array<{
    leg_id: number; action: string; option_type: string; strike: number; expiration: string
    entry_price: number; exit_price: number; contracts: number; premium_per_contract: number
    delta: number; gamma: number; theta: number; iv: number; realized_pnl: number
  }>
  oracle_advice?: {
    advice: string; win_probability: number; confidence: number; suggested_risk_pct: number
    suggested_sd_multiplier: number; use_gex_walls: boolean; suggested_put_strike?: number
    suggested_call_strike?: number; top_factors: Array<[string, number]>; reasoning: string
    model_version: string; claude_analysis?: { analysis: string; confidence_adjustment: number; risk_factors: string[]; opportunities: string[]; recommendation: string }
  }
  gex_context?: { net_gex: number; gex_normalized: number; call_wall: number; put_wall: number; flip_point: number; distance_to_flip_pct: number; regime: string; between_walls: boolean }
  market_context?: { spot_price: number; vix: number; vix_percentile: number; expected_move: number; trend: string; day_of_week: number; days_to_opex: number }
  backtest_stats?: { strategy_name: string; win_rate: number; expectancy: number; avg_win: number; avg_loss: number; sharpe_ratio: number; max_drawdown: number; total_trades: number; uses_real_data: boolean; backtest_period: string }
  position_sizing?: { contracts: number; position_dollars: number; max_risk_dollars: number; sizing_method: string; target_profit_pct: number; stop_loss_pct: number; probability_of_profit: number }
  alternatives?: { primary_reason: string; supporting_factors: string[]; risk_factors: string[]; alternatives_considered: string[]; why_not_alternatives: string[] }
  risk_checks?: Array<{ check: string; passed: boolean; value?: string }>
  passed_risk_checks?: boolean
}

// ==================== COMPONENT ====================

export default function ARESPage() {
  // SWR hooks for data fetching
  const { data: statusRes, error: statusError, isLoading: statusLoading, isValidating: statusValidating, mutate: mutateStatus } = useARESStatus()
  const { data: performanceRes, isValidating: perfValidating, mutate: mutatePerf } = useARESPerformance()
  const { data: equityRes, isValidating: equityValidating, mutate: mutateEquity } = useARESEquityCurve(30)
  const { data: positionsRes, isValidating: posValidating, mutate: mutatePositions } = useARESPositions()
  const { data: marketRes, isValidating: marketValidating, mutate: mutateMarket } = useARESMarketData()
  const { data: tradierRes, isValidating: tradierValidating, mutate: mutateTradier } = useARESTradierStatus()
  const { data: configRes, isValidating: configValidating, mutate: mutateConfig } = useARESConfig()
  const { data: decisionsRes, isValidating: decisionsValidating, mutate: mutateDecisions } = useARESDecisions(100)

  // Extract data
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
  const [activeTab, setActiveTab] = useState<'overview' | 'spx' | 'spy' | 'decisions' | 'config'>('overview')
  const [expandedDecision, setExpandedDecision] = useState<number | null>(null)
  const [runningCycle, setRunningCycle] = useState(false)

  // Helpers
  const isSPX = (pos: IronCondorPosition) => pos.ticker === 'SPX' || (!pos.ticker && (pos.spread_width || 10) > 5)
  const isSPY = (pos: IronCondorPosition) => pos.ticker === 'SPY' || (!pos.ticker && (pos.spread_width || 10) <= 5)
  const spxOpenPositions = positions.filter(isSPX)
  const spyOpenPositions = positions.filter(isSPY)
  const spxClosedPositions = closedPositions.filter(isSPX)
  const spyClosedPositions = closedPositions.filter(isSPY)

  const calcMaxDrawdown = (closed: IronCondorPosition[]) => {
    if (closed.length === 0) return 0
    let peak = 0, maxDD = 0, cum = 0
    closed.forEach(p => {
      cum += p.realized_pnl || 0
      if (cum > peak) peak = cum
      const dd = peak - cum
      if (dd > maxDD) maxDD = dd
    })
    return maxDD
  }

  const spxStats = {
    capital: 200000,
    totalPnl: spxClosedPositions.reduce((s, p) => s + (p.realized_pnl || 0), 0),
    totalTrades: spxClosedPositions.length,
    winningTrades: spxClosedPositions.filter(p => (p.realized_pnl || 0) > 0).length,
    losingTrades: spxClosedPositions.filter(p => (p.realized_pnl || 0) <= 0).length,
    winRate: spxClosedPositions.length > 0 ? (spxClosedPositions.filter(p => (p.realized_pnl || 0) > 0).length / spxClosedPositions.length) * 100 : 0,
    bestTrade: spxClosedPositions.length > 0 ? Math.max(...spxClosedPositions.map(p => p.realized_pnl || 0)) : 0,
    worstTrade: spxClosedPositions.length > 0 ? Math.min(...spxClosedPositions.map(p => p.realized_pnl || 0)) : 0,
    maxDrawdown: calcMaxDrawdown(spxClosedPositions),
    avgTrade: spxClosedPositions.length > 0 ? spxClosedPositions.reduce((s, p) => s + (p.realized_pnl || 0), 0) / spxClosedPositions.length : 0,
  }

  const spyStats = {
    capital: tradierStatus?.account?.equity || 102000,
    totalPnl: spyClosedPositions.reduce((s, p) => s + (p.realized_pnl || 0), 0),
    totalTrades: spyClosedPositions.length,
    winningTrades: spyClosedPositions.filter(p => (p.realized_pnl || 0) > 0).length,
    losingTrades: spyClosedPositions.filter(p => (p.realized_pnl || 0) <= 0).length,
    winRate: spyClosedPositions.length > 0 ? (spyClosedPositions.filter(p => (p.realized_pnl || 0) > 0).length / spyClosedPositions.length) * 100 : 0,
    bestTrade: spyClosedPositions.length > 0 ? Math.max(...spyClosedPositions.map(p => p.realized_pnl || 0)) : 0,
    worstTrade: spyClosedPositions.length > 0 ? Math.min(...spyClosedPositions.map(p => p.realized_pnl || 0)) : 0,
    maxDrawdown: calcMaxDrawdown(spyClosedPositions),
    avgTrade: spyClosedPositions.length > 0 ? spyClosedPositions.reduce((s, p) => s + (p.realized_pnl || 0), 0) / spyClosedPositions.length : 0,
  }

  const buildEquityCurve = (pos: IronCondorPosition[], startCap: number) => {
    if (pos.length === 0) return []
    const sorted = [...pos].sort((a, b) => (a.close_date || a.expiration || '').localeCompare(b.close_date || b.expiration || ''))
    const byDate: Record<string, number> = {}
    sorted.forEach(p => { const d = p.close_date || p.expiration || ''; if (d) byDate[d] = (byDate[d] || 0) + (p.realized_pnl || 0) })
    let cum = 0
    return Object.keys(byDate).sort().map(d => { cum += byDate[d]; return { date: d, equity: startCap + cum, daily_pnl: byDate[d], pnl: cum } })
  }

  const spxEquityData = buildEquityCurve(spxClosedPositions, spxStats.capital)
  const spyEquityData = buildEquityCurve(spyClosedPositions, spyStats.capital)

  const fetchData = () => { mutateStatus(); mutatePerf(); mutateEquity(); mutatePositions(); mutateMarket(); mutateTradier(); mutateConfig(); mutateDecisions() }

  const runCycle = async () => {
    setRunningCycle(true)
    try {
      await apiClient.runARESCycle()
      fetchData()
    } catch (err) {
      console.error('Failed to run cycle:', err)
    } finally {
      setRunningCycle(false)
    }
  }

  const getActionColor = (action: string) => {
    if (action?.includes('BUY') || action?.includes('OPEN') || action?.includes('ENTRY')) return 'text-green-400'
    if (action?.includes('SELL') || action?.includes('CLOSE') || action?.includes('EXIT')) return 'text-red-400'
    if (action?.includes('SKIP') || action?.includes('NO_TRADE')) return 'text-yellow-400'
    return 'text-gray-400'
  }

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

  const formatCurrency = (v: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(v)
  const formatPercent = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
  const tradierConnected = tradierStatus?.success && tradierStatus?.account?.account_number

  // Combined stats
  const totalPnl = spxStats.totalPnl + spyStats.totalPnl
  const totalTrades = spxStats.totalTrades + spyStats.totalTrades
  const totalWins = spxStats.winningTrades + spyStats.winningTrades
  const overallWinRate = totalTrades > 0 ? (totalWins / totalTrades) * 100 : 0

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
                <h1 className="text-2xl font-bold text-white">ARES</h1>
                <p className="text-gray-400 text-sm">0DTE Iron Condor Strategy</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${status?.in_trading_window ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-300'}`}>
                {status?.in_trading_window ? 'MARKET OPEN' : 'MARKET CLOSED'}
              </span>
              <button onClick={fetchData} disabled={isRefreshing} className="p-2 bg-gray-800 rounded-lg hover:bg-gray-700 disabled:opacity-50">
                <RefreshCw className={`w-5 h-5 text-gray-400 ${isRefreshing ? 'animate-spin' : ''}`} />
              </button>
              <button onClick={runCycle} disabled={runningCycle} className="flex items-center gap-2 px-4 py-2 bg-red-600 rounded-lg hover:bg-red-500 disabled:opacity-50">
                <Play className={`w-4 h-4 ${runningCycle ? 'animate-pulse' : ''}`} />
                <span className="text-white text-sm">Run Cycle</span>
              </button>
            </div>
          </div>

          {error && <div className="mb-6 p-4 bg-red-900/50 border border-red-500 rounded-lg text-red-300">{error}</div>}

          {/* Heartbeat Status Bar */}
          <div className="mb-4 bg-gray-800/50 rounded-lg p-3 border border-gray-700">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${
                    status?.heartbeat?.status === 'TRADED' ? 'bg-green-500 animate-pulse' :
                    status?.heartbeat?.status === 'SCAN_COMPLETE' ? 'bg-blue-500' :
                    status?.heartbeat?.status === 'ERROR' ? 'bg-red-500' :
                    status?.heartbeat?.status === 'MARKET_CLOSED' ? 'bg-yellow-500' : 'bg-gray-500'
                  }`} />
                  <span className="text-gray-400 text-sm">Heartbeat</span>
                </div>
                <div className="text-sm">
                  <span className="text-gray-500">Last Scan: </span>
                  <span className={`font-mono ${status?.heartbeat?.last_scan ? 'text-white' : 'text-gray-500'}`}>{status?.heartbeat?.last_scan || 'Never'}</span>
                </div>
                <div className="text-sm">
                  <span className="text-gray-500">Status: </span>
                  <span className={`font-medium ${status?.heartbeat?.status === 'TRADED' ? 'text-green-400' : status?.heartbeat?.status === 'SCAN_COMPLETE' ? 'text-blue-400' : status?.heartbeat?.status === 'ERROR' ? 'text-red-400' : 'text-gray-400'}`}>
                    {status?.heartbeat?.status?.replace(/_/g, ' ') || 'Unknown'}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-4 text-sm">
                <div><span className="text-gray-500">Scans Today: </span><span className="text-white font-bold">{status?.heartbeat?.scan_count_today || 0}</span></div>
                <div><span className="text-gray-500">Interval: </span><span className="text-cyan-400">{status?.scan_interval_minutes || 5} min</span></div>
                <Clock className="w-4 h-4 text-gray-500" />
              </div>
            </div>
          </div>

          {/* Market Data Bar - Condensed */}
          <div className="mb-4 bg-gray-800 rounded-lg p-3 border border-gray-700">
            <div className="grid grid-cols-3 md:grid-cols-6 gap-3 text-center">
              <div className="bg-purple-900/20 rounded-lg p-2">
                <span className="text-purple-400 text-xs">SPX</span>
                <p className="text-white font-mono text-lg font-bold">${marketData?.spx?.price?.toLocaleString() || '--'}</p>
              </div>
              <div className="bg-blue-900/20 rounded-lg p-2">
                <span className="text-blue-400 text-xs">SPY</span>
                <p className="text-white font-mono text-lg font-bold">${marketData?.spy?.price?.toFixed(2) || '--'}</p>
              </div>
              <div className="bg-yellow-900/20 rounded-lg p-2">
                <span className="text-yellow-400 text-xs">VIX</span>
                <p className="text-white font-mono text-lg font-bold">{marketData?.vix?.toFixed(2) || '--'}</p>
              </div>
              <div className="bg-gray-700/50 rounded-lg p-2">
                <span className="text-gray-400 text-xs">SPX ±Move</span>
                <p className="text-white font-mono text-lg font-bold">±${marketData?.spx?.expected_move?.toFixed(0) || '--'}</p>
              </div>
              <div className="bg-gray-700/50 rounded-lg p-2">
                <span className="text-gray-400 text-xs">SD Mult</span>
                <p className="text-white font-mono text-lg font-bold">{config?.sd_multiplier || 0.5}</p>
              </div>
              <div className="bg-green-900/20 rounded-lg p-2">
                <span className="text-green-400 text-xs">Target</span>
                <p className="text-green-400 font-mono text-lg font-bold">10%/mo</p>
              </div>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex gap-2 mb-6 flex-wrap">
            {(['overview', 'spx', 'spy', 'decisions', 'config'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 rounded-lg capitalize transition ${activeTab === tab ? 'bg-red-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}
              >
                {tab === 'spx' ? 'SPX' : tab === 'spy' ? 'SPY' : tab}
              </button>
            ))}
          </div>

          {/* ==================== OVERVIEW TAB ==================== */}
          {activeTab === 'overview' && (
            <>
              {/* Stats Cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-2">
                    <DollarSign className="w-5 h-5 text-green-500" />
                    <span className="text-gray-400 text-sm">Total Capital</span>
                  </div>
                  <p className="text-2xl font-bold text-white">{formatCurrency(spxStats.capital + spyStats.capital + totalPnl)}</p>
                  <p className="text-sm text-gray-500">SPX + SPY Combined</p>
                </div>
                <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-2">
                    <BarChart3 className="w-5 h-5 text-purple-500" />
                    <span className="text-gray-400 text-sm">Total P&L</span>
                  </div>
                  <p className={`text-2xl font-bold ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>{formatCurrency(totalPnl)}</p>
                  <p className="text-sm text-gray-500">{formatPercent((totalPnl / (spxStats.capital + spyStats.capital)) * 100)}</p>
                </div>
                <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-2">
                    <Target className="w-5 h-5 text-blue-500" />
                    <span className="text-gray-400 text-sm">Win Rate</span>
                  </div>
                  <p className="text-2xl font-bold text-white">{overallWinRate.toFixed(1)}%</p>
                  <p className="text-sm text-gray-500">{totalWins}W / {totalTrades - totalWins}L</p>
                </div>
                <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-2">
                    <Activity className="w-5 h-5 text-orange-500" />
                    <span className="text-gray-400 text-sm">Positions</span>
                  </div>
                  <p className="text-2xl font-bold text-white">{positions.length} open</p>
                  <p className="text-sm text-gray-500">{totalTrades} total trades</p>
                </div>
              </div>

              {/* GEX Context Panel */}
              <div className="bg-gray-800 rounded-xl p-6 border border-purple-700/50 mb-6">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <Crosshair className="w-5 h-5 text-purple-500" />
                    <h2 className="text-lg font-semibold text-white">Iron Condor Strike Zones</h2>
                    <span className="px-2 py-0.5 text-xs bg-purple-900/50 text-purple-400 rounded">GEX</span>
                  </div>
                </div>
                {marketData?.gex_context || marketData?.spx?.price ? (
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                    <div className="bg-gray-900/50 rounded-lg p-4 text-center">
                      <p className="text-gray-400 text-xs mb-1">SPX Price</p>
                      <p className="text-2xl font-bold text-white">${marketData?.spx?.price?.toLocaleString() || '--'}</p>
                    </div>
                    <div className="bg-green-900/20 border border-green-700/30 rounded-lg p-4 text-center">
                      <p className="text-gray-400 text-xs mb-1">Put Wall (Support)</p>
                      <p className="text-2xl font-bold text-green-400">${marketData?.gex_context?.put_wall?.toFixed(0) || '--'}</p>
                    </div>
                    <div className="bg-red-900/20 border border-red-700/30 rounded-lg p-4 text-center">
                      <p className="text-gray-400 text-xs mb-1">Call Wall (Resistance)</p>
                      <p className="text-2xl font-bold text-red-400">${marketData?.gex_context?.call_wall?.toFixed(0) || '--'}</p>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-4 text-center">
                      <p className="text-gray-400 text-xs mb-1">GEX Regime</p>
                      <p className={`text-xl font-bold ${marketData?.gex_context?.regime === 'POSITIVE' ? 'text-green-400' : 'text-red-400'}`}>
                        {marketData?.gex_context?.regime || 'N/A'}
                      </p>
                    </div>
                    <div className="bg-purple-900/20 border border-purple-700/30 rounded-lg p-4 text-center">
                      <p className="text-gray-400 text-xs mb-1">Net GEX</p>
                      <p className="text-xl font-bold text-purple-400">
                        {marketData?.gex_context?.net_gex ? `${(marketData.gex_context.net_gex / 1e9).toFixed(2)}B` : '--'}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-4 text-gray-500">
                    <p>GEX data will appear after ARES runs a scan during market hours</p>
                  </div>
                )}

                {/* Condor visualization */}
                {marketData?.spx?.price && marketData?.spx?.expected_move && (
                  <div className="mt-4 pt-4 border-t border-gray-700">
                    <p className="text-xs text-gray-500 mb-2">Expected Range (±{config?.sd_multiplier || 0.5} SD)</p>
                    <div className="relative h-8 bg-gray-700 rounded-lg overflow-hidden">
                      <div className="absolute inset-0 bg-gradient-to-r from-red-600/30 via-green-600/30 to-red-600/30" />
                      {/* Put short strike zone */}
                      <div className="absolute left-[15%] top-0 bottom-0 w-[20%] bg-green-600/40 border-l-2 border-green-500" />
                      {/* Call short strike zone */}
                      <div className="absolute right-[15%] top-0 bottom-0 w-[20%] bg-green-600/40 border-r-2 border-green-500" />
                      {/* Center marker */}
                      <div className="absolute left-1/2 top-0 bottom-0 w-0.5 bg-white" />
                    </div>
                    <div className="flex justify-between text-xs mt-1">
                      <span className="text-red-400">Put Wing</span>
                      <span className="text-green-400">Put Short</span>
                      <span className="text-white">SPX</span>
                      <span className="text-green-400">Call Short</span>
                      <span className="text-red-400">Call Wing</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Two Column: SPX Summary | SPY Summary */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                {/* SPX Summary */}
                <div className="bg-gradient-to-br from-purple-900/30 to-gray-800 rounded-lg border border-purple-700/50 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-lg font-bold text-purple-300 flex items-center gap-2">
                      <Play className="w-5 h-5" /> SPX Performance
                    </h3>
                    <span className="px-2 py-1 rounded text-xs bg-purple-900 text-purple-300">PAPER</span>
                  </div>
                  <div className="grid grid-cols-4 gap-2 text-center">
                    <div className="bg-gray-800/60 rounded p-2">
                      <p className="text-gray-400 text-xs">P&L</p>
                      <p className={`font-bold ${spxStats.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>{formatCurrency(spxStats.totalPnl)}</p>
                    </div>
                    <div className="bg-gray-800/60 rounded p-2">
                      <p className="text-gray-400 text-xs">Win Rate</p>
                      <p className="text-white font-bold">{spxStats.winRate.toFixed(1)}%</p>
                    </div>
                    <div className="bg-gray-800/60 rounded p-2">
                      <p className="text-gray-400 text-xs">Trades</p>
                      <p className="text-white font-bold">{spxStats.totalTrades}</p>
                    </div>
                    <div className="bg-gray-800/60 rounded p-2">
                      <p className="text-gray-400 text-xs">Open</p>
                      <p className="text-white font-bold">{spxOpenPositions.length}</p>
                    </div>
                  </div>
                </div>

                {/* SPY Summary */}
                <div className="bg-gradient-to-br from-blue-900/30 to-gray-800 rounded-lg border border-blue-700/50 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-lg font-bold text-blue-300 flex items-center gap-2">
                      <Server className="w-5 h-5" /> SPY Performance
                    </h3>
                    <span className={`px-2 py-1 rounded text-xs ${tradierConnected ? 'bg-green-900 text-green-300' : 'bg-yellow-900 text-yellow-300'}`}>
                      {tradierConnected ? 'TRADIER' : 'DISCONNECTED'}
                    </span>
                  </div>
                  <div className="grid grid-cols-4 gap-2 text-center">
                    <div className="bg-gray-800/60 rounded p-2">
                      <p className="text-gray-400 text-xs">P&L</p>
                      <p className={`font-bold ${spyStats.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>{formatCurrency(spyStats.totalPnl)}</p>
                    </div>
                    <div className="bg-gray-800/60 rounded p-2">
                      <p className="text-gray-400 text-xs">Win Rate</p>
                      <p className="text-white font-bold">{spyStats.winRate.toFixed(1)}%</p>
                    </div>
                    <div className="bg-gray-800/60 rounded p-2">
                      <p className="text-gray-400 text-xs">Trades</p>
                      <p className="text-white font-bold">{spyStats.totalTrades}</p>
                    </div>
                    <div className="bg-gray-800/60 rounded p-2">
                      <p className="text-gray-400 text-xs">Open</p>
                      <p className="text-white font-bold">{spyOpenPositions.length}</p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Recent Decisions Summary */}
              <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                    <FileText className="w-5 h-5 text-red-400" /> Recent Decisions
                  </h3>
                  <button onClick={() => setActiveTab('decisions')} className="text-sm text-red-400 hover:underline">View All →</button>
                </div>
                <div className="space-y-2">
                  {decisions.slice(0, 5).map((d) => (
                    <div key={d.id} className="flex items-center justify-between bg-gray-900/50 rounded p-2">
                      <div className="flex items-center gap-2">
                        <span className={`px-2 py-0.5 rounded text-xs ${getDecisionTypeBadge(d.decision_type).bg} ${getDecisionTypeBadge(d.decision_type).text}`}>
                          {d.decision_type?.replace(/_/g, ' ')}
                        </span>
                        <span className="text-gray-300 text-sm truncate max-w-xs">{d.what}</span>
                      </div>
                      <span className="text-xs text-gray-500">{new Date(d.timestamp).toLocaleTimeString()}</span>
                    </div>
                  ))}
                  {decisions.length === 0 && <p className="text-center text-gray-500 py-4">No decisions yet</p>}
                </div>
              </div>
            </>
          )}

          {/* ==================== SPX TAB ==================== */}
          {activeTab === 'spx' && (
            <div className="space-y-6">
              <div className="bg-gradient-to-br from-purple-900/30 to-gray-800 rounded-lg border border-purple-700/50 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-xl font-bold text-purple-300">SPX Iron Condors</h2>
                  <span className="px-3 py-1 rounded text-xs bg-purple-900 text-purple-300">PAPER TRADING</span>
                </div>

                {/* Stats Grid */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                  <div className="bg-gray-800/60 rounded-lg p-4 text-center">
                    <span className="text-gray-400 text-xs">Capital</span>
                    <p className="text-white font-bold text-xl">{formatCurrency(spxStats.capital + spxStats.totalPnl)}</p>
                  </div>
                  <div className="bg-gray-800/60 rounded-lg p-4 text-center">
                    <span className="text-gray-400 text-xs">Total P&L</span>
                    <p className={`font-bold text-xl ${spxStats.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>{formatCurrency(spxStats.totalPnl)}</p>
                  </div>
                  <div className="bg-gray-800/60 rounded-lg p-4 text-center">
                    <span className="text-gray-400 text-xs">Win Rate</span>
                    <p className="text-white font-bold text-xl">{spxStats.winRate.toFixed(1)}%</p>
                  </div>
                  <div className="bg-gray-800/60 rounded-lg p-4 text-center">
                    <span className="text-gray-400 text-xs">Trades</span>
                    <p className="text-white font-bold text-xl">{spxStats.totalTrades}</p>
                  </div>
                </div>

                {/* Equity Curve */}
                <div className="h-48 bg-gray-800/40 rounded-lg p-2 mb-6">
                  {spxEquityData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={spxEquityData}>
                        <defs>
                          <linearGradient id="spxEq" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#A855F7" stopOpacity={0.4} />
                            <stop offset="95%" stopColor="#A855F7" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis dataKey="date" stroke="#6B7280" fontSize={10} />
                        <YAxis stroke="#6B7280" fontSize={10} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
                        <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }} />
                        <Area type="monotone" dataKey="equity" stroke="#A855F7" fill="url(#spxEq)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex items-center justify-center h-full text-gray-500">No equity data yet</div>
                  )}
                </div>

                {/* Open Positions */}
                <h3 className="text-lg font-semibold text-purple-300 mb-3">Open Positions ({spxOpenPositions.length})</h3>
                <div className="space-y-2 mb-6">
                  {spxOpenPositions.map((pos) => (
                    <div key={pos.position_id} className="flex items-center justify-between bg-gray-800/50 rounded p-3">
                      <div>
                        <span className="text-gray-400 text-sm">{pos.expiration}</span>
                        <span className="text-purple-300 font-mono ml-2">{pos.put_short_strike}P / {pos.call_short_strike}C</span>
                      </div>
                      <div className="text-right">
                        <span className="text-green-400">{formatCurrency(pos.total_credit * 100 * pos.contracts)}</span>
                        <span className="text-gray-500 ml-2">x{pos.contracts}</span>
                      </div>
                    </div>
                  ))}
                  {spxOpenPositions.length === 0 && <p className="text-center text-gray-500 py-4">No open SPX positions</p>}
                </div>

                {/* Closed Positions */}
                <h3 className="text-lg font-semibold text-purple-300 mb-3">Closed Trades ({spxClosedPositions.length})</h3>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {spxClosedPositions.slice(0, 20).map((pos) => (
                    <div key={pos.position_id} className="flex items-center justify-between bg-gray-800/30 rounded p-2 text-sm">
                      <span className="text-gray-400">{pos.close_date || pos.expiration}</span>
                      <span className="text-gray-300 font-mono">{pos.put_short_strike}P / {pos.call_short_strike}C</span>
                      <span className={(pos.realized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}>{formatCurrency(pos.realized_pnl || 0)}</span>
                    </div>
                  ))}
                  {spxClosedPositions.length === 0 && <p className="text-center text-gray-500 py-4">No closed SPX trades</p>}
                </div>
              </div>
            </div>
          )}

          {/* ==================== SPY TAB ==================== */}
          {activeTab === 'spy' && (
            <div className="space-y-6">
              <div className="bg-gradient-to-br from-blue-900/30 to-gray-800 rounded-lg border border-blue-700/50 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-xl font-bold text-blue-300">SPY Iron Condors</h2>
                  <span className={`px-3 py-1 rounded text-xs ${tradierConnected ? 'bg-green-900 text-green-300' : 'bg-yellow-900 text-yellow-300'}`}>
                    {tradierConnected ? 'TRADIER CONNECTED' : 'NOT CONNECTED'}
                  </span>
                </div>

                {tradierConnected ? (
                  <>
                    {/* Stats Grid */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                      <div className="bg-gray-800/60 rounded-lg p-4 text-center">
                        <span className="text-gray-400 text-xs">Capital</span>
                        <p className="text-white font-bold text-xl">{formatCurrency(spyStats.capital + spyStats.totalPnl)}</p>
                      </div>
                      <div className="bg-gray-800/60 rounded-lg p-4 text-center">
                        <span className="text-gray-400 text-xs">Total P&L</span>
                        <p className={`font-bold text-xl ${spyStats.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>{formatCurrency(spyStats.totalPnl)}</p>
                      </div>
                      <div className="bg-gray-800/60 rounded-lg p-4 text-center">
                        <span className="text-gray-400 text-xs">Win Rate</span>
                        <p className="text-white font-bold text-xl">{spyStats.winRate.toFixed(1)}%</p>
                      </div>
                      <div className="bg-gray-800/60 rounded-lg p-4 text-center">
                        <span className="text-gray-400 text-xs">Trades</span>
                        <p className="text-white font-bold text-xl">{spyStats.totalTrades}</p>
                      </div>
                    </div>

                    {/* Equity Curve */}
                    <div className="h-48 bg-gray-800/40 rounded-lg p-2 mb-6">
                      {spyEquityData.length > 0 ? (
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={spyEquityData}>
                            <defs>
                              <linearGradient id="spyEq" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.4} />
                                <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
                              </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis dataKey="date" stroke="#6B7280" fontSize={10} />
                            <YAxis stroke="#6B7280" fontSize={10} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
                            <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }} />
                            <Area type="monotone" dataKey="equity" stroke="#3B82F6" fill="url(#spyEq)" />
                          </AreaChart>
                        </ResponsiveContainer>
                      ) : (
                        <div className="flex items-center justify-center h-full text-gray-500">No equity data yet</div>
                      )}
                    </div>

                    {/* Tradier Positions */}
                    <h3 className="text-lg font-semibold text-blue-300 mb-3">Tradier Positions ({tradierStatus?.positions?.length || 0})</h3>
                    <div className="space-y-2 mb-6">
                      {tradierStatus?.positions?.map((pos, idx) => (
                        <div key={idx} className="flex items-center justify-between bg-gray-800/50 rounded p-3">
                          <span className="text-white font-mono">{pos.symbol}</span>
                          <span className="text-gray-400">x{pos.quantity}</span>
                          <span className="text-blue-300">{formatCurrency(pos.cost_basis)}</span>
                        </div>
                      ))}
                      {(!tradierStatus?.positions || tradierStatus.positions.length === 0) && <p className="text-center text-gray-500 py-4">No open positions</p>}
                    </div>

                    {/* Recent Orders */}
                    <h3 className="text-lg font-semibold text-blue-300 mb-3">Recent Orders</h3>
                    <div className="space-y-2 max-h-48 overflow-y-auto">
                      {tradierStatus?.orders?.slice(0, 10).map((order) => (
                        <div key={order.id} className="flex items-center justify-between bg-gray-800/30 rounded p-2 text-sm">
                          <span className="text-white font-mono">{order.symbol}</span>
                          <span className={order.side === 'buy' ? 'text-green-400' : 'text-red-400'}>{order.side.toUpperCase()} x{order.quantity}</span>
                          <span className={`px-2 py-0.5 rounded text-xs ${order.status === 'filled' ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-300'}`}>{order.status}</span>
                        </div>
                      ))}
                      {(!tradierStatus?.orders || tradierStatus.orders.length === 0) && <p className="text-center text-gray-500 py-4">No recent orders</p>}
                    </div>
                  </>
                ) : (
                  <div className="text-center py-8">
                    <AlertTriangle className="w-16 h-16 text-yellow-500 mx-auto mb-4" />
                    <h4 className="text-white font-semibold text-lg mb-2">Tradier Sandbox Not Connected</h4>
                    <p className="text-gray-400 text-sm mb-4">Configure Tradier sandbox credentials to enable real SPY paper trading</p>
                    <div className="bg-gray-800/50 rounded-lg p-4 text-left text-sm max-w-md mx-auto">
                      <code className="text-blue-400 block">TRADIER_API_KEY=your_sandbox_api_key</code>
                      <code className="text-blue-400 block">TRADIER_ACCOUNT_ID=your_account_id</code>
                      <code className="text-blue-400 block">TRADIER_SANDBOX=true</code>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ==================== DECISIONS TAB ==================== */}
          {activeTab === 'decisions' && (
            <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
              <div className="p-4 border-b border-gray-700">
                <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                  <FileText className="w-5 h-5 text-red-400" /> Decision Log
                </h2>
                <p className="text-xs text-gray-400 mt-1">Full audit trail: What, Why, How for every trading decision</p>
              </div>
              <div className="p-4 space-y-3 max-h-[800px] overflow-y-auto">
                {decisions.length > 0 ? decisions.map((decision) => {
                  const badge = getDecisionTypeBadge(decision.decision_type)
                  const isExpanded = expandedDecision === decision.id

                  return (
                    <div key={decision.id} className={`bg-gray-900/50 rounded-lg border transition-all ${isExpanded ? 'border-red-500/50' : 'border-gray-700 hover:border-gray-600'}`}>
                      <div className="p-3 cursor-pointer" onClick={() => setExpandedDecision(isExpanded ? null : decision.id)}>
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap mb-1">
                              <span className={`px-2 py-0.5 rounded text-xs font-medium ${badge.bg} ${badge.text}`}>{decision.decision_type?.replace(/_/g, ' ')}</span>
                              <span className={`text-sm font-medium ${getActionColor(decision.action)}`}>{decision.action}</span>
                              {decision.symbol && <span className="text-xs text-gray-400 font-mono">{decision.symbol}</span>}
                              {decision.actual_pnl !== undefined && decision.actual_pnl !== 0 && (
                                <span className={`text-xs font-bold ${decision.actual_pnl > 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  {decision.actual_pnl > 0 ? '+' : ''}{formatCurrency(decision.actual_pnl)}
                                </span>
                              )}
                            </div>
                            <p className="text-sm text-white truncate"><span className="text-gray-500">WHAT: </span>{decision.what}</p>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-gray-500 whitespace-nowrap">{new Date(decision.timestamp).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                            {isExpanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                          </div>
                        </div>
                      </div>

                      {isExpanded && (
                        <div className="px-3 pb-3 space-y-3 border-t border-gray-700/50 pt-3">
                          <div className="bg-yellow-900/10 border-l-2 border-yellow-500 pl-3 py-2">
                            <span className="text-yellow-400 text-xs font-bold">WHY:</span>
                            <p className="text-sm text-gray-300 mt-1">{decision.why || 'Not specified'}</p>
                          </div>
                          {decision.how && (
                            <div className="bg-blue-900/10 border-l-2 border-blue-500 pl-3 py-2">
                              <span className="text-blue-400 text-xs font-bold">HOW:</span>
                              <p className="text-sm text-gray-300 mt-1">{decision.how}</p>
                            </div>
                          )}
                          {decision.gex_context && (
                            <div className="bg-purple-900/20 border border-purple-700/30 rounded p-2">
                              <span className="text-purple-400 text-xs font-bold">GEX LEVELS:</span>
                              <div className="grid grid-cols-4 gap-2 mt-2 text-xs">
                                <div><span className="text-gray-500">Put Wall:</span><span className="text-green-400 ml-1">${decision.gex_context.put_wall}</span></div>
                                <div><span className="text-gray-500">Call Wall:</span><span className="text-red-400 ml-1">${decision.gex_context.call_wall}</span></div>
                                <div><span className="text-gray-500">Regime:</span><span className="text-white ml-1">{decision.gex_context.regime}</span></div>
                                <div><span className="text-gray-500">Net GEX:</span><span className="text-white ml-1">{(decision.gex_context.net_gex / 1e9).toFixed(2)}B</span></div>
                              </div>
                            </div>
                          )}
                          {decision.oracle_advice && (
                            <div className="bg-green-900/20 border border-green-700/30 rounded p-2">
                              <div className="flex items-center justify-between mb-2">
                                <span className="text-green-400 text-xs font-bold">ORACLE ADVICE:</span>
                                <span className={`px-2 py-0.5 rounded text-xs ${decision.oracle_advice.advice === 'TRADE_FULL' ? 'bg-green-900/50 text-green-400' : 'bg-yellow-900/50 text-yellow-400'}`}>
                                  {decision.oracle_advice.advice?.replace(/_/g, ' ')}
                                </span>
                              </div>
                              <div className="grid grid-cols-3 gap-2 text-xs">
                                <div><span className="text-gray-500">Win Prob:</span><span className="text-green-400 ml-1">{((decision.oracle_advice.win_probability || 0) * 100).toFixed(0)}%</span></div>
                                <div><span className="text-gray-500">Confidence:</span><span className="text-white ml-1">{((decision.oracle_advice.confidence || 0) * 100).toFixed(0)}%</span></div>
                                <div><span className="text-gray-500">Risk:</span><span className="text-yellow-400 ml-1">{(decision.oracle_advice.suggested_risk_pct || 0).toFixed(1)}%</span></div>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                }) : (
                  <div className="text-center py-8 text-gray-500">
                    <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
                    <p>No decisions recorded yet</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ==================== CONFIG TAB ==================== */}
          {activeTab === 'config' && (
            <div className="bg-gray-800 rounded-xl border border-gray-700 p-6">
              <div className="flex items-center gap-2 mb-6">
                <Settings className="w-5 h-5 text-gray-400" />
                <h2 className="text-lg font-semibold text-white">ARES Configuration</h2>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* SPX Config */}
                <div className="bg-purple-900/20 border border-purple-700/30 rounded-lg p-4">
                  <h3 className="text-purple-300 font-semibold mb-4">SPX Settings</h3>
                  <div className="space-y-3">
                    <div className="flex justify-between"><span className="text-gray-400">Spread Width:</span><span className="text-white font-mono">${config?.spread_width || 10}</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">SD Multiplier:</span><span className="text-white font-mono">{config?.sd_multiplier || 0.5}</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">Risk per Trade:</span><span className="text-white font-mono">{config?.risk_per_trade_pct || 10}%</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">Min Credit:</span><span className="text-white font-mono">${config?.min_credit || 0.50}</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">Profit Target:</span><span className="text-white font-mono">{config?.profit_target_pct || 50}%</span></div>
                  </div>
                </div>

                {/* SPY Config */}
                <div className="bg-blue-900/20 border border-blue-700/30 rounded-lg p-4">
                  <h3 className="text-blue-300 font-semibold mb-4">SPY Settings</h3>
                  <div className="space-y-3">
                    <div className="flex justify-between"><span className="text-gray-400">Spread Width:</span><span className="text-white font-mono">${config?.spread_width_spy || 2}</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">SD Multiplier:</span><span className="text-white font-mono">{config?.sd_multiplier_spy || config?.sd_multiplier || 0.5}</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">Tradier Mode:</span><span className="text-white font-mono">{tradierStatus?.mode || 'sandbox'}</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">Account:</span><span className="text-white font-mono">{tradierStatus?.account?.account_number || 'Not Connected'}</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">Buying Power:</span><span className="text-white font-mono">{tradierStatus?.account?.buying_power ? formatCurrency(tradierStatus.account.buying_power) : '--'}</span></div>
                  </div>
                </div>

                {/* General Config */}
                <div className="md:col-span-2 bg-gray-700/30 border border-gray-600 rounded-lg p-4">
                  <h3 className="text-gray-300 font-semibold mb-4">General Settings</h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="flex flex-col"><span className="text-gray-400 text-sm">Entry Window:</span><span className="text-white font-mono">{config?.entry_window || '9:35 AM - 2:55 PM CT'}</span></div>
                    <div className="flex flex-col"><span className="text-gray-400 text-sm">Scan Interval:</span><span className="text-white font-mono">{status?.scan_interval_minutes || 5} min</span></div>
                    <div className="flex flex-col"><span className="text-gray-400 text-sm">Mode:</span><span className="text-white font-mono">{status?.mode || 'paper'}</span></div>
                    <div className="flex flex-col"><span className="text-gray-400 text-sm">Monthly Target:</span><span className="text-green-400 font-mono">10%</span></div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Footer */}
          <div className="mt-6 text-center text-sm text-gray-500">
            Auto-refresh every 30 seconds • Cached across pages
          </div>
        </div>
      </main>
    </div>
  )
}
