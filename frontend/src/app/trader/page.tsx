'use client'

import { logger } from '@/lib/logger'

import { useState, useEffect, Fragment, useMemo } from 'react'
import { Bot, Play, Pause, Square, Settings, TrendingUp, TrendingDown, Activity, DollarSign, Target, AlertTriangle, CheckCircle, XCircle, Clock, Wifi, WifiOff, Shield, BarChart3, Calendar, Zap, Brain, RefreshCw, Power, PowerOff, History, Cpu, ChevronDown, ChevronUp } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, ReferenceLine } from 'recharts'
import Navigation from '@/components/Navigation'
import ExportButtons from '@/components/trader/ExportButtons'
import { apiClient } from '@/lib/api'
import { useTraderWebSocket } from '@/hooks/useTraderWebSocket'

interface TraderStatus {
  is_active: boolean
  mode: 'paper' | 'live'
  status?: string
  current_action?: string
  market_analysis?: string
  last_decision?: string
  last_check: string
  next_check_time?: string
  strategies_active: number
  total_trades_today: number
  uptime?: number
}

interface Performance {
  total_pnl: number
  today_pnl: number
  win_rate: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  sharpe_ratio: number
  max_drawdown: number
  starting_capital: number
  current_value: number
  realized_pnl: number
  unrealized_pnl: number
  return_pct: number
}

interface Strategy {
  id: string
  name: string
  status: 'active' | 'paused' | 'stopped'
  win_rate: number
  total_trades: number
  pnl: number
  last_trade_date: string
}

interface Trade {
  id: string
  timestamp: string
  symbol: string
  action: 'BUY' | 'SELL' | 'LONG_STRADDLE' | 'IRON_CONDOR' | 'BULL_PUT_SPREAD' | 'BEAR_CALL_SPREAD' | 'CASH_SECURED_PUT' | string
  type: 'CALL' | 'PUT' | 'straddle' | 'iron_condor' | 'bull_put_spread' | 'bear_call_spread' | 'csp' | string
  strike: number
  quantity: number
  price: number
  status: 'filled' | 'pending' | 'cancelled' | 'OPEN' | 'CLOSED'
  pnl?: number
  strategy?: string
  entry_bid?: number
  entry_ask?: number
  entry_spot_price?: number
  current_price?: number
  current_spot_price?: number
  trade_reasoning?: string
  expiration_date?: string
  // Verifiable trade details - for checking against Tradier
  contract_symbol?: string  // e.g., "SPY241206C00595000" - the ACTUAL Tradier symbol
  entry_date?: string       // e.g., "2024-12-06"
  entry_time?: string       // e.g., "09:35:42"
  // Greeks
  entry_iv?: number
  entry_delta?: number
  current_iv?: number
  current_delta?: number
  theta?: number
  gamma?: number
  vega?: number
  gex_regime?: string
  entry_net_gex?: number
}

interface TradeLogEntry {
  date: string
  time: string
  action: string
  details: string
  pnl: number
}

// ML Model interfaces
interface MLModelStatus {
  is_trained: boolean
  accuracy: number
  training_samples: number
  feature_count: number
  last_trained: string | null
  feature_importance: Record<string, number>
}

interface MLPrediction {
  prediction: 'bullish' | 'bearish' | 'neutral'
  predicted_direction: number
  symbol: string
  pattern: string
  timestamp: string
  confidence: number
  probability: number
}

// Risk interfaces
interface RiskStatus {
  daily_loss_limit: number
  current_daily_loss: number
  max_position_size: number
  current_exposure: number
  risk_score: number
  alerts: string[]
  limits?: {
    max_drawdown?: number
    daily_loss?: number
    position_size?: number
    correlation?: number
  }
  status?: {
    max_drawdown?: string
    daily_loss?: string
    position_size?: string
    correlation?: string
  }
  current_drawdown_pct?: number
  daily_loss_pct?: number
  position_size_pct?: number
  correlation_pct?: number
}

interface RiskMetric {
  timestamp: string
  var_95: number
  var_99: number
  expected_shortfall: number
  volatility: number
}

// VIX interfaces
interface VixSignal {
  signal: 'elevated' | 'normal' | 'low'
  signal_type?: string
  current_vix: number
  threshold: number
  recommendation: string
  recommended_action?: string
  confidence?: number
  reasoning?: string
  risk_warning?: string
}

interface VixData {
  current: number
  previous_close: number
  change_pct: number
  ma_20: number
  spike_detected: boolean
  vix_spot?: number
  vol_regime?: 'low' | 'very_low' | 'elevated' | 'high' | 'extreme' | 'normal'
  iv_percentile?: number
  realized_vol_20d?: number
  iv_rv_spread?: number
  term_structure_pct?: number
  structure_type?: string
}

// Closed Trade interface
interface ClosedTrade {
  id: string
  entry_date: string
  entry_time: string
  exit_date: string
  exit_time: string
  symbol: string
  strategy: string
  strike: number
  option_type: string
  contracts: number
  entry_price: number
  exit_price: number
  pnl: number
  pnl_pct: number
  exit_reason: string
  hold_duration_minutes: number
  trade_reasoning?: string
  // Verifiable fields
  contract_symbol?: string
  expiration_date?: string
}

// Backtest interface
interface BacktestResult {
  id: string
  strategy: string
  pattern?: string
  win_rate: number
  total_trades: number
  total_signals?: number
  profit_factor: number
  sharpe_ratio: number
  max_drawdown: number
  timestamp: string
  expectancy?: number
  avg_profit_pct?: number
}

// Diagnostics interface
interface TraderDiagnostics {
  api_latency_ms: number
  last_market_check: string
  websocket_status: 'connected' | 'disconnected'
  data_freshness_seconds: number
  errors_last_hour: number
  recommendations?: string[]
  checks?: {
    market_hours?: {
      current_time_ct: string
      day_of_week: string
      status: 'open' | 'closed'
    }
  }
}

// Equity curve point
interface EquityCurvePoint {
  timestamp: number
  equity: number
  pnl: number
  date: string
}

// AI Log Entry interface for autonomous trader logs
interface AILogEntry {
  id?: number
  timestamp: string
  log_type: string
  symbol?: string
  pattern_detected?: string
  confidence_score?: number
  trade_direction?: string
  ai_thought_process?: string
  action_taken?: string
  reasoning_summary?: string
  // Strike selection fields
  strike_chosen?: number
  strike_selection_reason?: string
  // Position sizing fields
  kelly_pct?: number
  contracts?: number
  sizing_rationale?: string
  // AI evaluation fields
  ai_confidence?: number
}

export default function AutonomousTrader() {
  const [loading, setLoading] = useState(true)
  const [traderStatus, setTraderStatus] = useState<TraderStatus>({
    is_active: false,
    mode: 'paper',
    uptime: 0,
    last_check: new Date().toISOString(),
    strategies_active: 0,
    total_trades_today: 0
  })

  const [performance, setPerformance] = useState<Performance>({
    total_pnl: 0,
    today_pnl: 0,
    win_rate: 0,
    total_trades: 0,
    winning_trades: 0,
    losing_trades: 0,
    sharpe_ratio: 0,
    max_drawdown: 0,
    starting_capital: 1000000,
    current_value: 1000000,
    realized_pnl: 0,
    unrealized_pnl: 0,
    return_pct: 0
  })

  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [strategyConfigs, setStrategyConfigs] = useState<Record<string, boolean>>({})
  const [strategyTogglingId, setStrategyTogglingId] = useState<string | null>(null)

  const [recentTrades, setRecentTrades] = useState<Trade[]>([])
  const [expandedTradeId, setExpandedTradeId] = useState<string | null>(null)

  // Trade filters
  const [tradeFilter, setTradeFilter] = useState<'all' | 'open' | 'closed'>('all')
  const [strategyFilter, setStrategyFilter] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState<string>('')

  // Symbol selector for multi-symbol support (SPY, SPX, or ALL for unified view)
  const [selectedSymbol, setSelectedSymbol] = useState<'SPY' | 'SPX' | 'ALL'>('SPY')

  // Unified portfolio data (when selectedSymbol is 'ALL')
  const [unifiedPortfolio, setUnifiedPortfolio] = useState<{
    spy: { total_trades: number; win_rate: number; total_pnl: number; net_delta: number; net_gamma: number; net_theta: number; net_vega: number };
    spx: { total_trades: number; win_rate: number; total_pnl: number; net_delta: number; net_gamma: number; net_theta: number; net_vega: number };
    combined: { total_trades: number; win_rate: number; total_pnl: number; net_delta: number; net_gamma: number; net_theta: number; net_vega: number };
  } | null>(null)

  // Regime signals and volatility surface for transparency
  const [regimeSignals, setRegimeSignals] = useState<{
    timestamp: string;
    gex_regime: string;
    mm_state: string;
    vix_regime: string;
    net_gex: number;
    flip_point: number;
    spot_price: number;
    action_recommended: string;
    confidence: number;
    key_factors: string[];
  } | null>(null)

  const [volSurfaceData, setVolSurfaceData] = useState<{
    symbol: string;
    skew_type: string;
    term_structure: string;
    atm_iv: number;
    iv_percentile: number;
    trading_signal: string;
    signal_strength: number;
  } | null>(null)

  // Background jobs state
  const [backgroundJobs, setBackgroundJobs] = useState<{
    job_id: string;
    job_type: string;
    status: string;
    progress: number;
    message: string;
  }[]>([])

  // Trade Activity Log
  const [tradeLog, setTradeLog] = useState<TradeLogEntry[]>([])

  // Autonomous trader advanced features state
  const [autonomousLogs, setAutonomousLogs] = useState<AILogEntry[]>([])
  const [competitionLeaderboard, setCompetitionLeaderboard] = useState<{
    rank?: number
    name?: string
    pnl?: number
    strategy_id: string
    strategy_name: string
    current_capital: number
    starting_capital: number
    win_rate: number
    total_trades: number
    sharpe_ratio?: number
  }[]>([])
  const [backtestResults, setBacktestResults] = useState<BacktestResult[]>([])
  const [backtestDataSource, setBacktestDataSource] = useState<string>('none')
  const [backtestRefreshing, setBacktestRefreshing] = useState(false)
  const [riskStatus, setRiskStatus] = useState<RiskStatus | null>(null)

  // Liberation and False Floor accuracy state
  const [liberationAccuracy, setLiberationAccuracy] = useState<{
    total_liberation_signals: number
    successful_liberations: number
    accuracy_pct: number
    avg_move_after_liberation_pct: number
    avg_confidence: number
  } | null>(null)
  const [falseFloorEffectiveness, setFalseFloorEffectiveness] = useState<{
    total_false_floor_detections: number
    avoided_bad_short_trades: number
    avg_price_move_pct: number
    effectiveness: string
  } | null>(null)

  // VIX Hedge Signal state
  const [vixSignal, setVixSignal] = useState<VixSignal | null>(null)
  const [vixData, setVixData] = useState<VixData | null>(null)

  // P&L Chart state
  const [equityCurve, setEquityCurve] = useState<{timestamp: string, equity: number, pnl: number, date: string}[]>([])
  const [chartPeriod, setChartPeriod] = useState<7 | 30 | 90>(30)

  // Closed Trades state
  const [closedTrades, setClosedTrades] = useState<ClosedTrade[]>([])
  const [showClosedTrades, setShowClosedTrades] = useState(true)

  // Data verification timestamps
  const [lastDataFetch, setLastDataFetch] = useState<Date | null>(null)

  // ML Model state
  const [mlModelStatus, setMlModelStatus] = useState<MLModelStatus | null>(null)
  const [mlPredictions, setMlPredictions] = useState<MLPrediction[]>([])

  // Risk Metrics History state
  const [riskMetricsHistory, setRiskMetricsHistory] = useState<RiskMetric[]>([])

  // Trader Control state
  const [executing, setExecuting] = useState(false)
  const [traderControlLoading, setTraderControlLoading] = useState(false)

  // Diagnostics state
  const [diagnostics, setDiagnostics] = useState<TraderDiagnostics | null>(null)

  // Countdown timer state
  const [countdown, setCountdown] = useState<string>('--:--')

  // WebSocket connection for real-time updates
  const { data: wsData, isConnected: wsConnected, error: wsError } = useTraderWebSocket()

  // Update state from WebSocket or REST API data
  useEffect(() => {
    if (wsData && (wsData.type === 'trader_update' || wsData.type === 'rest_update' || wsData.type === 'connected')) {
      // Update performance from WebSocket or REST fallback
      // Handle both field name formats: WebSocket uses net_pnl/total_realized_pnl, REST uses total_pnl/realized_pnl
      if (wsData.performance) {
        const perf = wsData.performance as any  // Allow flexible property access
        const netPnl = perf.net_pnl ?? perf.total_pnl ?? 0
        const realizedPnl = perf.total_realized_pnl ?? perf.realized_pnl ?? 0
        const unrealizedPnl = perf.total_unrealized_pnl ?? perf.unrealized_pnl ?? 0
        const currentEquity = perf.current_equity ?? perf.current_value ?? ((perf.starting_capital || 1000000) + netPnl)

        setPerformance(prev => ({
          ...prev,
          total_pnl: netPnl,
          today_pnl: perf.today_pnl ?? 0,
          win_rate: perf.win_rate ?? 0,
          total_trades: perf.total_trades ?? 0,
          winning_trades: perf.winning_trades ?? 0,
          losing_trades: perf.losing_trades ?? 0,
          starting_capital: perf.starting_capital ?? 1000000,
          current_value: currentEquity,
          realized_pnl: realizedPnl,
          unrealized_pnl: unrealizedPnl,
          return_pct: perf.return_pct ?? 0,
        }))
      }

      // Update status from WebSocket
      if (wsData.status) {
        const status = wsData.status
        setTraderStatus(prev => ({
          ...prev,
          is_active: true,
          status: status.status,
          current_action: status.current_action,
          market_analysis: status.market_analysis,
          last_decision: status.last_decision,
          last_check: status.last_updated || new Date().toISOString(),
          next_check_time: status.next_check_time,
        }))
      }

      // Update positions from WebSocket
      if (wsData.positions && wsData.positions.length > 0) {
        const mappedTrades = wsData.positions.map((trade: any) => ({
          id: trade.id?.toString(),
          timestamp: `${trade.entry_date}T${trade.entry_time || '00:00:00'}`,
          symbol: trade.symbol || 'SPY',
          action: trade.action || 'BUY',
          type: trade.option_type || 'CALL',
          strike: trade.strike || 0,
          quantity: trade.contracts || 0,
          price: Math.abs(trade.entry_price) || 0,
          status: 'OPEN' as const,
          pnl: trade.unrealized_pnl || 0,
          strategy: trade.strategy,
          entry_bid: trade.entry_bid,
          entry_ask: trade.entry_ask,
          entry_spot_price: trade.entry_spot_price,
          current_price: trade.current_price,
          current_spot_price: trade.current_spot_price,
          trade_reasoning: trade.trade_reasoning,
          expiration_date: trade.expiration_date,
          // Verifiable trade details for Tradier
          contract_symbol: trade.contract_symbol,
          entry_date: trade.entry_date,
          entry_time: trade.entry_time,
          // Greeks - Entry values
          entry_iv: trade.entry_iv,
          entry_delta: trade.entry_delta,
          current_iv: trade.current_iv,
          current_delta: trade.current_delta,
          // Greeks - Use entry values, fallback to current if available
          theta: trade.entry_theta || trade.current_theta,
          gamma: trade.entry_gamma || trade.current_gamma,
          vega: trade.entry_vega || trade.current_vega,
          // GEX context
          gex_regime: trade.gex_regime,
          entry_net_gex: trade.entry_net_gex,
        }))
        setRecentTrades(mappedTrades)
      }

      // Update AI logs from WebSocket/REST data
      if (wsData.ai_logs && wsData.ai_logs.length > 0) {
        setAutonomousLogs(wsData.ai_logs)
      }
    }
  }, [wsData])

  // Live countdown timer - updates every second
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

  // Calculate best and worst trades
  const bestTrade = tradeLog.length > 0
    ? Math.max(...tradeLog.map(t => t.pnl))
    : 0
  const worstTrade = tradeLog.length > 0
    ? Math.min(...tradeLog.map(t => t.pnl))
    : 0

  // Memoize chart data to avoid recalculation on every render
  const closedTradesChartData = useMemo(() => {
    if (closedTrades.length === 0) return []
    // Sort trades by exit date and build cumulative P&L
    const sortedTrades = [...closedTrades].sort((a, b) =>
      new Date(a.exit_date || 0).getTime() - new Date(b.exit_date || 0).getTime()
    )
    let cumPnl = 0
    return sortedTrades.map((trade, idx) => {
      cumPnl += (trade.pnl || 0)
      return {
        date: trade.exit_date || `Trade ${idx + 1}`,
        pnl: cumPnl,
        equity: 1000000 + cumPnl,
        dailyPnl: trade.pnl || 0
      }
    })
  }, [closedTrades])

  // Memoize total P&L from closed trades
  const closedTradesTotalPnl = useMemo(() =>
    closedTrades.reduce((sum, t) => sum + (t.pnl || 0), 0)
  , [closedTrades])

  // Fetch data from API
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)

        // Fetch all data in parallel, but handle failures gracefully with Promise.allSettled
        // This ensures one failed endpoint doesn't break the entire page
        const results = await Promise.allSettled([
          apiClient.getTraderStatus(),
          apiClient.getTraderPerformance(),
          apiClient.getTraderTrades(10),
          apiClient.getStrategies(),
          apiClient.getStrategyConfigs().catch(() => ({ data: { success: false, data: {} } })),
          apiClient.getAutonomousLogs({ limit: 20 }).catch(() => ({ data: { success: false, data: [] } })),
          apiClient.getCompetitionLeaderboard().catch(() => ({ data: { success: false, data: [] } })),
          apiClient.getAllPatternBacktests(90).catch(() => ({ data: { success: false, data: [] } })),
          apiClient.getLiberationAccuracy(90).catch(() => ({ data: { success: false, data: null } })),
          apiClient.getFalseFloorEffectiveness(90).catch(() => ({ data: { success: false, data: null } })),
          apiClient.getRiskStatus().catch(() => ({ data: { success: false, data: null } })),
          apiClient.getTradeLog(),
          apiClient.getEquityCurve(chartPeriod).catch(() => ({ data: { success: false, data: [] } })),
          apiClient.getClosedTrades(20).catch(() => ({ data: { success: false, data: [] } })),
          apiClient.getMLModelStatus().catch(() => ({ data: { success: false, data: null } })),
          apiClient.getRecentMLPredictions(10).catch(() => ({ data: { success: false, data: [] } })),
          apiClient.getRiskMetrics(30).catch(() => ({ data: { success: false, data: [] } })),
          apiClient.getTraderDiagnostics().catch(() => ({ data: { success: false, data: null } }))
        ])

        // Extract results (fulfilled promises only)
        const [statusRes, perfRes, tradesRes, strategiesRes, strategyConfigsRes, logsRes, leaderboardRes, backtestsRes, liberationRes, falseFloorRes, riskRes, tradeLogRes, equityCurveRes, closedTradesRes, mlStatusRes, mlPredictionsRes, riskMetricsRes, diagnosticsRes] = results.map(result =>
          result.status === 'fulfilled' ? result.value : { data: { success: false, data: null } }
        )

        if (statusRes.data.success) {
          setTraderStatus(statusRes.data.data)
        }

        if (perfRes.data.success) {
          setPerformance(perfRes.data.data)
        }

        // Load strategy configs first
        const configs = strategyConfigsRes.data.success ? strategyConfigsRes.data.data : {}
        if (Object.keys(configs).length > 0) {
          setStrategyConfigs(configs)
        }

        // Set REAL strategies from database
        if (strategiesRes.data?.success && Array.isArray(strategiesRes.data?.data) && strategiesRes.data.data.length > 0) {
          const mappedStrategies = strategiesRes.data.data.map((strat: any) => {
            // Use ID from backend or generate from name
            const strategyId = strat.id || strat.name.toLowerCase().replace(/\s+/g, '_').replace(/[()]/g, '')
            // Check if strategy is enabled in config
            const isEnabled = configs[strat.name] !== false // Default to enabled
            return {
              id: strategyId,
              name: strat.name,
              status: isEnabled ? (strat.status || 'active') : 'paused',
              win_rate: strat.win_rate || 0,
              total_trades: strat.total_trades || 0,
              pnl: strat.total_pnl || 0,
              last_trade_date: strat.last_trade_date || 'Never'
            }
          })
          setStrategies(mappedStrategies)
        }

        if (tradesRes.data?.success && Array.isArray(tradesRes.data?.data) && tradesRes.data.data.length > 0) {
          // Map database trades to UI format with full transparency
          const mappedTrades = tradesRes.data.data.map((trade: any) => ({
            id: trade.id?.toString() || trade.timestamp,
            timestamp: `${trade.entry_date}T${trade.entry_time}`,
            symbol: trade.symbol || 'SPY',
            action: trade.action || 'BUY',
            type: trade.option_type || 'CALL',
            strike: trade.strike || 0,
            quantity: trade.contracts || 0,
            price: Math.abs(trade.entry_price) || 0,
            status: trade.status || 'OPEN',
            pnl: trade.realized_pnl || trade.unrealized_pnl || 0,
            strategy: trade.strategy,
            entry_bid: trade.entry_bid,
            entry_ask: trade.entry_ask,
            entry_spot_price: trade.entry_spot_price,
            current_price: trade.current_price,
            current_spot_price: trade.current_spot_price,
            trade_reasoning: trade.trade_reasoning,
            expiration_date: trade.expiration_date,
            // Verifiable trade details for Tradier
            contract_symbol: trade.contract_symbol,
            entry_date: trade.entry_date,
            entry_time: trade.entry_time,
            // Greeks - Entry values
            entry_iv: trade.entry_iv,
            entry_delta: trade.entry_delta,
            current_iv: trade.current_iv,
            current_delta: trade.current_delta,
            // Greeks - Use entry values, fallback to current if available
            theta: trade.entry_theta || trade.current_theta,
            gamma: trade.entry_gamma || trade.current_gamma,
            vega: trade.entry_vega || trade.current_vega,
            // GEX context
            gex_regime: trade.gex_regime,
            entry_net_gex: trade.entry_net_gex,
          }))
          setRecentTrades(mappedTrades)
        }

        // Set autonomous trader advanced features data (gracefully handle missing endpoints)
        if (logsRes.data.success) {
          setAutonomousLogs(logsRes.data.data || [])
        }

        if (leaderboardRes.data.success) {
          setCompetitionLeaderboard(leaderboardRes.data.data || [])
        }

        if (backtestsRes.data.success) {
          setBacktestResults(backtestsRes.data.data || [])
          setBacktestDataSource(backtestsRes.data.data_source || 'none')
        }

        // Set liberation accuracy and false floor effectiveness data
        if (liberationRes.data.success && liberationRes.data.data) {
          setLiberationAccuracy(liberationRes.data.data)
        }

        if (falseFloorRes.data.success && falseFloorRes.data.data) {
          setFalseFloorEffectiveness(falseFloorRes.data.data)
        }

        if (riskRes.data.success) {
          setRiskStatus(riskRes.data.data)
        }

        if (tradeLogRes.data.success) {
          setTradeLog(tradeLogRes.data.data || [])
        }

        // Set equity curve data for P&L chart
        if (equityCurveRes.data.success && equityCurveRes.data.data && Array.isArray(equityCurveRes.data.data) && equityCurveRes.data.data.length > 0) {
          const curveData = equityCurveRes.data.data.map((point: any, idx: number, arr: any[]) => {
            // Calculate cumulative P&L from starting equity
            const startingEquity = arr[0]?.equity || 1000000
            const pnl = point.equity - startingEquity
            // Handle both Unix timestamps (seconds) and JavaScript timestamps (milliseconds)
            const timestampMs = point.timestamp < 1e12 ? point.timestamp * 1000 : point.timestamp
            return {
              timestamp: timestampMs,
              equity: point.equity,
              pnl: pnl,
              date: point.date || new Date(timestampMs).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
            }
          })
          setEquityCurve(curveData)
        }

        // Set closed trades
        if (closedTradesRes.data.success && closedTradesRes.data.data) {
          setClosedTrades(closedTradesRes.data.data)
        }

        // Set ML model status
        if (mlStatusRes.data.success && mlStatusRes.data.data) {
          setMlModelStatus(mlStatusRes.data.data)
        }

        // Set ML predictions
        if (mlPredictionsRes.data.success && mlPredictionsRes.data.data) {
          setMlPredictions(mlPredictionsRes.data.data)
        }

        // Set risk metrics history
        if (riskMetricsRes.data.success && riskMetricsRes.data.data) {
          setRiskMetricsHistory(riskMetricsRes.data.data)
        }

        // Set diagnostics for debugging
        if (diagnosticsRes.data.success && diagnosticsRes.data.data) {
          setDiagnostics(diagnosticsRes.data.data)
        }

        // Fetch VIX hedge signal data using Promise.allSettled for graceful failure handling
        const vixResults = await Promise.allSettled([
          apiClient.getVIXHedgeSignal(),
          apiClient.getVIXCurrent()
        ])

        const vixSignalRes = vixResults[0]
        const vixDataRes = vixResults[1]

        if (vixSignalRes.status === 'fulfilled' && vixSignalRes.value?.data?.success) {
          setVixSignal(vixSignalRes.value.data.data)
        }
        if (vixDataRes.status === 'fulfilled' && vixDataRes.value?.data?.success) {
          setVixData(vixDataRes.value.data.data)
        }
      } catch (error) {
        logger.error('Error fetching trader data:', error)
        // Keep default/empty state on error
      } finally {
        setLoading(false)
        setLastDataFetch(new Date())
      }
    }

    fetchData()

    // No auto-refresh - protects API rate limit (20 calls/min shared across all users)
    // Trader background worker updates independently - UI will refresh when user navigates
  }, [chartPeriod])

  // Fetch unified portfolio when selectedSymbol is 'ALL'
  useEffect(() => {
    const fetchUnifiedPortfolio = async () => {
      if (selectedSymbol === 'ALL') {
        try {
          const res = await apiClient.getUnifiedPortfolio()
          if (res.data.success) {
            setUnifiedPortfolio(res.data.data)
          }
        } catch (error) {
          logger.error('Error fetching unified portfolio:', error)
        }
      } else {
        setUnifiedPortfolio(null)
      }
    }

    fetchUnifiedPortfolio()
  }, [selectedSymbol])

  // Fetch regime signals, vol surface, and background jobs for transparency
  useEffect(() => {
    const fetchTransparencyData = async () => {
      try {
        // Fetch regime signals, vol surface, and jobs in parallel
        const [regimeRes, volRes, jobsRes] = await Promise.allSettled([
          apiClient.getRegimeCurrent(),
          apiClient.getVolSurfaceTradingSignal(selectedSymbol === 'ALL' ? 'SPY' : selectedSymbol),
          apiClient.getJobsList()
        ])

        if (regimeRes.status === 'fulfilled' && regimeRes.value?.data?.success) {
          const data = regimeRes.value.data.data
          setRegimeSignals({
            timestamp: data.timestamp || new Date().toISOString(),
            gex_regime: data.gex_regime || data.regime || 'Unknown',
            mm_state: data.mm_state || 'Unknown',
            vix_regime: data.vix_regime || data.vol_regime || 'Normal',
            net_gex: data.net_gex || 0,
            flip_point: data.flip_point || 0,
            spot_price: data.spot_price || 0,
            action_recommended: data.action_recommended || data.action || 'HOLD',
            confidence: data.confidence || 0,
            key_factors: data.key_factors || data.reasoning?.split('.').slice(0, 3) || []
          })
        }

        if (volRes.status === 'fulfilled' && volRes.value?.data?.success) {
          const data = volRes.value.data.data
          setVolSurfaceData({
            symbol: data.symbol || selectedSymbol,
            skew_type: data.skew_type || 'Normal',
            term_structure: data.term_structure || 'Normal',
            atm_iv: data.atm_iv || 0,
            iv_percentile: data.iv_percentile || 0,
            trading_signal: data.trading_signal || data.signal || 'Neutral',
            signal_strength: data.signal_strength || data.confidence || 0
          })
        }

        if (jobsRes.status === 'fulfilled' && jobsRes.value?.data?.success) {
          setBackgroundJobs(jobsRes.value.data.jobs || [])
        }
      } catch (error) {
        logger.error('Error fetching transparency data:', error)
      }
    }

    fetchTransparencyData()

    // Refresh every 30 seconds for live data
    const interval = setInterval(fetchTransparencyData, 30000)
    return () => clearInterval(interval)
  }, [selectedSymbol])

  // Trader runs automatically as a background worker - no manual control needed
  // It checks every 5 minutes ALL DAY during market hours (8:30 AM - 3:00 PM CT)
  // GUARANTEED: MINIMUM one trade per day (multi-level fallback system)
  // State is persisted in database, so it remembers everything across restarts

  // Note: Mode toggle removed - requires backend implementation for safe paper/live switching
  // Mode is controlled via autonomous_config table in the database

  const handleToggleStrategy = async (strategyId: string) => {
    setStrategyTogglingId(strategyId)
    try {
      const strategy = strategies.find(s => s.id === strategyId)
      if (!strategy) return

      const newEnabled = strategy.status !== 'active'
      const res = await apiClient.toggleStrategy(strategyId, newEnabled)

      if (res.data.success) {
        // Update local state
        setStrategies(prev =>
          prev.map(s =>
            s.id === strategyId
              ? { ...s, status: newEnabled ? 'active' : 'paused' }
              : s
          )
        )
        setStrategyConfigs(prev => ({
          ...prev,
          [strategy.name]: newEnabled
        }))
      }
    } catch (error) {
      logger.error('Failed to toggle strategy:', error)
    } finally {
      setStrategyTogglingId(null)
    }
  }

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(value)
  }

  const formatTime = (isoString: string) => {
    try {
      if (!isoString) return 'N/A'
      const date = new Date(isoString)
      if (isNaN(date.getTime())) return 'Invalid'
      return new Intl.DateTimeFormat('en-US', {
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
        timeZone: 'America/Chicago'
      }).format(date)
    } catch {
      return 'N/A'
    }
  }

  const formatTradeTime = (dateStr?: string, timeStr?: string) => {
    try {
      if (dateStr && timeStr) {
        const datetime = `${dateStr}T${timeStr}`
        const date = new Date(datetime)
        if (isNaN(date.getTime())) return timeStr || dateStr || 'N/A'
        return new Intl.DateTimeFormat('en-US', {
          hour: 'numeric',
          minute: '2-digit',
          hour12: true,
          timeZone: 'America/Chicago'
        }).format(date)
      }
      return timeStr || dateStr || 'N/A'
    } catch {
      return timeStr || dateStr || 'N/A'
    }
  }

  const formatUptime = (seconds: number) => {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    return `${hours}h ${minutes}m`
  }

  const downloadTradeHistory = () => {
    // Export comprehensive trade data from recentTrades (includes all fields)
    const exportData = recentTrades.length > 0 ? recentTrades : []

    if (exportData.length === 0 && tradeLog.length === 0) {
      alert('No trade history to export')
      return
    }

    // If we have recentTrades, export comprehensive data
    if (exportData.length > 0) {
      const csvContent = [
        ['Date/Time', 'Symbol', 'Strategy', 'Action', 'Strike', 'Type', 'Contracts', 'Entry Price', 'Current Price', 'P&L ($)', 'P&L (%)', 'Status', 'Entry IV', 'Entry Delta', 'GEX Regime', 'Entry Net GEX', 'Expiration'],
        ...exportData.map(trade => {
          const formattedDateTime = trade.timestamp
            ? new Date(trade.timestamp).toLocaleString('en-US', { timeZone: 'America/Chicago' })
            : 'N/A'
          const pnlPct = trade.price > 0 ? ((trade.pnl || 0) / (trade.price * (trade.quantity || 1) * 100) * 100) : 0

          return [
            formattedDateTime,
            trade.symbol || 'SPY',
            trade.strategy || 'N/A',
            trade.action || 'N/A',
            trade.strike || 0,
            trade.type || 'N/A',
            trade.quantity || 1,
            (trade.price || 0).toFixed(2),
            (trade.current_price || trade.price || 0).toFixed(2),
            (trade.pnl || 0).toFixed(2),
            pnlPct.toFixed(2),
            trade.status || 'N/A',
            trade.entry_iv ? (trade.entry_iv * 100).toFixed(2) + '%' : 'N/A',
            trade.entry_delta ? trade.entry_delta.toFixed(4) : 'N/A',
            trade.gex_regime || 'N/A',
            trade.entry_net_gex ? `$${(trade.entry_net_gex / 1e9).toFixed(2)}B` : 'N/A',
            trade.expiration_date || 'N/A'
          ].map(val => `"${val}"`)  // Quote all values to handle commas
        })
      ]
        .map(row => row.join(','))
        .join('\n')

      const blob = new Blob([csvContent], { type: 'text/csv' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `trades-export-${new Date().toISOString().split('T')[0]}.csv`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      return
    }

    // Fallback to trade activity log if no recentTrades
    const csvContent = [
      ['Date/Time (Central)', 'Action', 'Details', 'P&L'],
      ...tradeLog.map(trade => {
        const datetime = trade.date && trade.time ? `${trade.date}T${trade.time}` : null
        const formattedDateTime = datetime
          ? new Date(datetime).toLocaleString('en-US', { timeZone: 'America/Chicago' })
          : 'N/A'

        return [
          `"${formattedDateTime}"`,
          `"${trade.action}"`,
          `"${trade.details}"`,
          trade.pnl.toFixed(2)
        ]
      })
    ]
      .map(row => row.join(','))
      .join('\n')

    const blob = new Blob([csvContent], { type: 'text/csv' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `trade-activity-${new Date().toISOString().split('T')[0]}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
  }

  // Refresh all page data without full reload
  const refreshPageData = async () => {
    try {
      // Fetch key data in parallel for quick refresh
      const results = await Promise.allSettled([
        apiClient.getTraderStatus(),
        apiClient.getTraderPerformance(),
        apiClient.getTraderTrades(10),
        apiClient.getAutonomousLogs({ limit: 20 }).catch(() => ({ data: { success: false, data: [] } })),
        apiClient.getTradeLog(),
        apiClient.getEquityCurve(chartPeriod).catch(() => ({ data: { success: false, data: [] } })),
        apiClient.getClosedTrades(20).catch(() => ({ data: { success: false, data: [] } }))
      ])

      const [statusRes, perfRes, tradesRes, logsRes, tradeLogRes, equityCurveRes, closedTradesRes] = results.map(result =>
        result.status === 'fulfilled' ? result.value : { data: { success: false, data: null } }
      )

      if (statusRes.data?.success) setTraderStatus(statusRes.data.data)
      if (perfRes.data?.success) setPerformance(perfRes.data.data)

      if (tradesRes.data?.success && Array.isArray(tradesRes.data?.data)) {
        const mappedTrades = tradesRes.data.data.map((trade: any) => ({
          id: trade.id?.toString() || trade.timestamp,
          timestamp: `${trade.entry_date}T${trade.entry_time}`,
          symbol: trade.symbol || 'SPY',
          action: trade.action || 'BUY',
          type: trade.option_type || 'CALL',
          strike: trade.strike || 0,
          quantity: trade.contracts || 0,
          price: Math.abs(trade.entry_price) || 0,
          status: trade.status || 'OPEN',
          pnl: trade.realized_pnl || trade.unrealized_pnl || 0,
          strategy: trade.strategy,
          entry_bid: trade.entry_bid,
          entry_ask: trade.entry_ask,
          entry_spot_price: trade.entry_spot_price,
          current_price: trade.current_price,
          current_spot_price: trade.current_spot_price,
          trade_reasoning: trade.trade_reasoning,
          expiration_date: trade.expiration_date,
          // Verifiable trade details for Tradier
          contract_symbol: trade.contract_symbol,
          entry_date: trade.entry_date,
          entry_time: trade.entry_time,
          // Greeks - Entry values
          entry_iv: trade.entry_iv,
          entry_delta: trade.entry_delta,
          current_iv: trade.current_iv,
          current_delta: trade.current_delta,
          // Greeks - Use entry values, fallback to current if available
          theta: trade.entry_theta || trade.current_theta,
          gamma: trade.entry_gamma || trade.current_gamma,
          vega: trade.entry_vega || trade.current_vega,
          // GEX context
          gex_regime: trade.gex_regime,
          entry_net_gex: trade.entry_net_gex,
        }))
        setRecentTrades(mappedTrades)
      }

      if (logsRes.data?.success && logsRes.data.data) setAutonomousLogs(logsRes.data.data)
      if (tradeLogRes.data?.success && tradeLogRes.data.data) setTradeLog(tradeLogRes.data.data)
      if (closedTradesRes.data?.success && closedTradesRes.data.data) setClosedTrades(closedTradesRes.data.data)

      if (equityCurveRes.data?.success && equityCurveRes.data.data && Array.isArray(equityCurveRes.data.data) && equityCurveRes.data.data.length > 0) {
        const startingEquity = equityCurveRes.data.data[0].equity || 1000000
        const curveData = equityCurveRes.data.data.map((point: any) => {
          // Handle both Unix timestamps (seconds) and JavaScript timestamps (milliseconds)
          const timestampMs = point.timestamp < 1e12 ? point.timestamp * 1000 : point.timestamp
          return {
            timestamp: timestampMs,
            equity: point.equity,
            pnl: point.equity - startingEquity,
            date: point.date || new Date(timestampMs).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
          }
        })
        setEquityCurve(curveData)
      }
      setLastDataFetch(new Date())
    } catch (error) {
      logger.error('Error refreshing data:', error)
    }
  }

  // Execute a single trader cycle manually
  const handleExecuteTraderCycle = async () => {
    setExecuting(true)
    try {
      const res = await apiClient.executeTraderCycle()
      if (res.data.success) {
        alert('Trader cycle executed successfully! Check AI Thought Process for results.')
        // Refresh data after execution (targeted refresh, not full page reload)
        await refreshPageData()
      } else {
        alert(`Execution failed: ${res.data.error || 'Unknown error'}`)
      }
    } catch (error: any) {
      alert(`Error executing trader: ${error.message || 'Network error'}`)
    } finally {
      setExecuting(false)
    }
  }

  // Start the trader
  const handleStartTrader = async () => {
    setTraderControlLoading(true)
    try {
      const res = await apiClient.startTrader()
      if (res.data.success) {
        setTraderStatus(prev => ({ ...prev, is_active: true }))
      } else {
        alert(`Failed to start: ${res.data.error || 'Unknown error'}`)
      }
    } catch (error: any) {
      alert(`Error: ${error.message || 'Network error'}`)
    } finally {
      setTraderControlLoading(false)
    }
  }

  // Stop the trader
  const handleStopTrader = async () => {
    setTraderControlLoading(true)
    try {
      const res = await apiClient.stopTrader()
      if (res.data.success) {
        setTraderStatus(prev => ({ ...prev, is_active: false }))
      } else {
        alert(`Failed to stop: ${res.data.error || 'Unknown error'}`)
      }
    } catch (error: any) {
      alert(`Error: ${error.message || 'Network error'}`)
    } finally {
      setTraderControlLoading(false)
    }
  }

  return (
    <div className="min-h-screen">
      <Navigation />
      <main className="pt-16 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="space-y-6">
            {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-4">
            <h1 className="text-3xl font-bold text-text-primary">
              {selectedSymbol === 'ALL' ? 'Unified Portfolio' : `${selectedSymbol} Autonomous Trader`}
            </h1>
            {/* Symbol Selector */}
            <div className="flex rounded-lg bg-background-secondary p-1">
              {(['SPY', 'SPX', 'ALL'] as const).map((sym) => (
                <button
                  key={sym}
                  onClick={() => setSelectedSymbol(sym)}
                  className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${
                    selectedSymbol === sym
                      ? 'bg-primary text-white shadow-md'
                      : 'text-text-secondary hover:text-text-primary hover:bg-background-primary'
                  }`}
                >
                  {sym === 'ALL' ? '📊 All' : sym}
                </button>
              ))}
            </div>
          </div>
          <p className="text-text-secondary mt-1">
            {selectedSymbol === 'ALL'
              ? 'Combined SPY + SPX portfolio view with net Greeks'
              : '$1M capital management for autonomous trading strategies'}
          </p>
          {lastDataFetch && (
            <p className="text-xs text-text-muted mt-1">
              Data last updated: {lastDataFetch.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          {/* WebSocket Connection Indicator */}
          <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${
            wsConnected
              ? 'bg-success/20 text-success'
              : 'bg-text-muted/20 text-text-muted'
          }`}>
            {wsConnected ? <Wifi className="w-4 h-4" /> : <WifiOff className="w-4 h-4" />}
            {wsConnected ? 'Live' : 'Offline'}
          </div>
          <div className={`px-4 py-2 rounded-lg font-semibold ${
            traderStatus.mode === 'paper'
              ? 'bg-warning/20 text-warning'
              : 'bg-danger/20 text-danger'
          }`}>
            {traderStatus.mode === 'paper' ? 'PAPER TRADING' : 'LIVE TRADING'}
          </div>
          <div className={`flex items-center gap-2 px-4 py-2 rounded-lg font-semibold ${
            traderStatus.is_active
              ? 'bg-success/20 text-success'
              : 'bg-text-muted/20 text-text-muted'
          }`}>
            <div className={`w-2 h-2 rounded-full ${
              traderStatus.is_active ? 'bg-success animate-pulse' : 'bg-text-muted'
            }`} />
            {traderStatus.is_active ? 'ACTIVE' : 'STOPPED'}
          </div>
        </div>
      </div>

      {/* Diagnostics Warning Banner - Shows when there are issues */}
      {diagnostics && diagnostics.recommendations && diagnostics.recommendations.length > 0 && (
        <div className="bg-warning/10 border border-warning/30 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-warning flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="font-semibold text-warning mb-2">Trader Diagnostics</h3>
              <ul className="text-sm text-text-secondary space-y-1">
                {diagnostics.recommendations.map((rec: string, idx: number) => (
                  <li key={idx} className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 bg-warning rounded-full" />
                    {rec}
                  </li>
                ))}
              </ul>
              {diagnostics.checks?.market_hours && (
                <div className="mt-3 text-xs text-text-muted">
                  Current time: {diagnostics.checks.market_hours.current_time_ct} ({diagnostics.checks.market_hours.day_of_week})
                  {' | '}
                  Market: {diagnostics.checks.market_hours.status === 'open' ? '🟢 Open' : '🔴 Closed'}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Unified Portfolio Summary - Shows when 'ALL' is selected */}
      {selectedSymbol === 'ALL' && unifiedPortfolio && (
        <div className="card bg-gradient-to-br from-purple-500/10 via-primary/5 to-success/10 border-purple-500/30">
          <h2 className="text-xl font-bold text-text-primary mb-4 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-purple-400" />
            Unified Portfolio Summary
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* SPY Summary */}
            <div className="p-4 bg-background-primary rounded-lg">
              <h3 className="font-semibold text-primary mb-3">SPY Trader</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-text-secondary">Total P&L</span>
                  <span className={unifiedPortfolio.spy?.total_pnl >= 0 ? 'text-success' : 'text-danger'}>
                    ${unifiedPortfolio.spy?.total_pnl?.toLocaleString() || '0'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Win Rate</span>
                  <span className="text-text-primary">{unifiedPortfolio.spy?.win_rate?.toFixed(1) || '0'}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Net Delta</span>
                  <span className="text-text-primary">{unifiedPortfolio.spy?.net_delta?.toFixed(2) || '0'}</span>
                </div>
              </div>
            </div>

            {/* SPX Summary */}
            <div className="p-4 bg-background-primary rounded-lg">
              <h3 className="font-semibold text-warning mb-3">SPX Trader</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-text-secondary">Total P&L</span>
                  <span className={unifiedPortfolio.spx?.total_pnl >= 0 ? 'text-success' : 'text-danger'}>
                    ${unifiedPortfolio.spx?.total_pnl?.toLocaleString() || '0'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Win Rate</span>
                  <span className="text-text-primary">{unifiedPortfolio.spx?.win_rate?.toFixed(1) || '0'}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Net Delta</span>
                  <span className="text-text-primary">{unifiedPortfolio.spx?.net_delta?.toFixed(2) || '0'}</span>
                </div>
              </div>
            </div>

            {/* Combined Portfolio */}
            <div className="p-4 bg-gradient-to-br from-success/20 to-success/5 rounded-lg border border-success/30">
              <h3 className="font-semibold text-success mb-3">Combined Portfolio</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-text-secondary">Total P&L</span>
                  <span className={`text-lg font-bold ${unifiedPortfolio.combined?.total_pnl >= 0 ? 'text-success' : 'text-danger'}`}>
                    ${unifiedPortfolio.combined?.total_pnl?.toLocaleString() || '0'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Total Trades</span>
                  <span className="text-text-primary">{unifiedPortfolio.combined?.total_trades || 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Win Rate</span>
                  <span className="text-text-primary">{unifiedPortfolio.combined?.win_rate?.toFixed(1) || '0'}%</span>
                </div>
              </div>
            </div>
          </div>

          {/* Net Greeks Section */}
          <div className="mt-4 pt-4 border-t border-border">
            <h3 className="font-semibold text-text-primary mb-3 flex items-center gap-2">
              <Activity className="w-4 h-4" />
              Net Portfolio Greeks
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-3 bg-background-primary rounded-lg text-center">
                <div className="text-xs text-text-secondary mb-1">Net Delta (Δ)</div>
                <div className={`text-xl font-bold ${(unifiedPortfolio.combined?.net_delta || 0) >= 0 ? 'text-success' : 'text-danger'}`}>
                  {unifiedPortfolio.combined?.net_delta?.toFixed(2) || '0'}
                </div>
              </div>
              <div className="p-3 bg-background-primary rounded-lg text-center">
                <div className="text-xs text-text-secondary mb-1">Net Gamma (Γ)</div>
                <div className="text-xl font-bold text-primary">
                  {unifiedPortfolio.combined?.net_gamma?.toFixed(4) || '0'}
                </div>
              </div>
              <div className="p-3 bg-background-primary rounded-lg text-center">
                <div className="text-xs text-text-secondary mb-1">Net Theta (Θ)</div>
                <div className={`text-xl font-bold ${(unifiedPortfolio.combined?.net_theta || 0) >= 0 ? 'text-success' : 'text-danger'}`}>
                  ${unifiedPortfolio.combined?.net_theta?.toFixed(2) || '0'}
                </div>
              </div>
              <div className="p-3 bg-background-primary rounded-lg text-center">
                <div className="text-xs text-text-secondary mb-1">Net Vega (ν)</div>
                <div className="text-xl font-bold text-warning">
                  {unifiedPortfolio.combined?.net_vega?.toFixed(2) || '0'}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* AI Decision Transparency Panel */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Regime Signals */}
        <div className="card bg-gradient-to-br from-blue-500/10 to-blue-500/5 border-blue-500/20">
          <h3 className="font-semibold text-text-primary mb-3 flex items-center gap-2">
            <Brain className="w-4 h-4 text-blue-400" />
            Market Regime
          </h3>
          {regimeSignals ? (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-text-secondary">GEX Regime</span>
                <span className={`font-semibold ${regimeSignals.gex_regime?.toLowerCase().includes('positive') ? 'text-success' : regimeSignals.gex_regime?.toLowerCase().includes('negative') ? 'text-danger' : 'text-warning'}`}>
                  {regimeSignals.gex_regime}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">MM State</span>
                <span className="text-text-primary">{regimeSignals.mm_state}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">VIX Regime</span>
                <span className={`${regimeSignals.vix_regime?.toLowerCase().includes('elevated') || regimeSignals.vix_regime?.toLowerCase().includes('high') ? 'text-danger' : 'text-success'}`}>
                  {regimeSignals.vix_regime}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">AI Action</span>
                <span className={`font-bold ${regimeSignals.action_recommended?.toUpperCase().includes('BUY') || regimeSignals.action_recommended?.toUpperCase().includes('CALL') ? 'text-success' : regimeSignals.action_recommended?.toUpperCase().includes('SELL') || regimeSignals.action_recommended?.toUpperCase().includes('PUT') ? 'text-danger' : 'text-warning'}`}>
                  {regimeSignals.action_recommended}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Confidence</span>
                <span className="text-primary font-semibold">{regimeSignals.confidence?.toFixed(0)}%</span>
              </div>
            </div>
          ) : (
            <div className="text-text-muted text-sm">Loading regime data...</div>
          )}
        </div>

        {/* Volatility Surface */}
        <div className="card bg-gradient-to-br from-purple-500/10 to-purple-500/5 border-purple-500/20">
          <h3 className="font-semibold text-text-primary mb-3 flex items-center gap-2">
            <Activity className="w-4 h-4 text-purple-400" />
            Volatility Surface
          </h3>
          {volSurfaceData ? (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-text-secondary">Skew Type</span>
                <span className="text-text-primary">{volSurfaceData.skew_type}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Term Structure</span>
                <span className="text-text-primary">{volSurfaceData.term_structure}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">ATM IV</span>
                <span className="text-text-primary">{(volSurfaceData.atm_iv * 100).toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">IV Percentile</span>
                <span className={`font-semibold ${volSurfaceData.iv_percentile > 70 ? 'text-danger' : volSurfaceData.iv_percentile < 30 ? 'text-success' : 'text-warning'}`}>
                  {volSurfaceData.iv_percentile?.toFixed(0)}%
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Trading Signal</span>
                <span className={`font-bold ${volSurfaceData.trading_signal?.toLowerCase().includes('buy') ? 'text-success' : volSurfaceData.trading_signal?.toLowerCase().includes('sell') ? 'text-danger' : 'text-warning'}`}>
                  {volSurfaceData.trading_signal}
                </span>
              </div>
            </div>
          ) : (
            <div className="text-text-muted text-sm">Loading vol surface...</div>
          )}
        </div>

        {/* Background Jobs */}
        <div className="card bg-gradient-to-br from-green-500/10 to-green-500/5 border-green-500/20">
          <h3 className="font-semibold text-text-primary mb-3 flex items-center gap-2">
            <RefreshCw className="w-4 h-4 text-green-400" />
            Background Jobs
          </h3>
          {backgroundJobs.length > 0 ? (
            <div className="space-y-2">
              {backgroundJobs.slice(0, 3).map((job) => (
                <div key={job.job_id} className="p-2 bg-background-primary rounded text-sm">
                  <div className="flex justify-between items-center">
                    <span className="text-text-primary font-medium">{job.job_type}</span>
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      job.status === 'completed' ? 'bg-success/20 text-success' :
                      job.status === 'running' ? 'bg-warning/20 text-warning' :
                      job.status === 'failed' ? 'bg-danger/20 text-danger' :
                      'bg-text-muted/20 text-text-muted'
                    }`}>
                      {job.status}
                    </span>
                  </div>
                  {job.status === 'running' && (
                    <div className="mt-1">
                      <div className="w-full bg-background-secondary rounded-full h-1.5">
                        <div className="bg-warning h-1.5 rounded-full transition-all" style={{ width: `${job.progress}%` }} />
                      </div>
                      <div className="text-xs text-text-muted mt-1">{job.message}</div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-text-muted text-sm">No active jobs</div>
          )}
        </div>
      </div>

      {/* Trader Control Panel */}
      <div className="card bg-gradient-to-r from-primary/5 to-primary/10 border-primary/20">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-3">
              <Cpu className="w-6 h-6 text-primary" />
              <div>
                <h3 className="font-semibold text-text-primary">Trader Controls</h3>
                <p className="text-xs text-text-secondary">Manual execution and system controls</p>
              </div>
            </div>

            {/* Live Countdown Timer */}
            <div className="flex items-center gap-3 px-4 py-2 bg-background-primary rounded-lg border border-border">
              <Clock className="w-5 h-5 text-warning animate-pulse" />
              <div>
                <p className="text-xs text-text-muted">Next Scan In</p>
                <p className="text-xl font-bold text-warning font-mono">{countdown}</p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Export Buttons */}
            <ExportButtons symbol="SPY" />

            {/* Manual Execute Button */}
            <button
              onClick={handleExecuteTraderCycle}
              disabled={executing}
              className="flex items-center gap-2 px-4 py-2 rounded-lg font-semibold bg-primary text-white hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {executing ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Zap className="w-4 h-4" />
              )}
              {executing ? 'Executing...' : 'Execute Now'}
            </button>

            {/* Start/Stop Buttons */}
            {traderStatus.is_active ? (
              <button
                onClick={handleStopTrader}
                disabled={traderControlLoading}
                className="flex items-center gap-2 px-4 py-2 rounded-lg font-semibold bg-danger/20 text-danger hover:bg-danger/30 disabled:opacity-50 transition-colors"
              >
                {traderControlLoading ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <PowerOff className="w-4 h-4" />
                )}
                Stop Trader
              </button>
            ) : (
              <button
                onClick={handleStartTrader}
                disabled={traderControlLoading}
                className="flex items-center gap-2 px-4 py-2 rounded-lg font-semibold bg-success/20 text-success hover:bg-success/30 disabled:opacity-50 transition-colors"
              >
                {traderControlLoading ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <Power className="w-4 h-4" />
                )}
                Start Trader
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Auto-Running Info Banner */}
      <div className="p-4 rounded-lg bg-primary/10 border border-primary/30">
        <div className="flex items-start gap-3">
          <Bot className="w-5 h-5 text-primary flex-shrink-0 mt-0.5 animate-pulse" />
          <div>
            <p className="font-semibold text-primary mb-1">⚡ Fully Autonomous - Checks Every 5 Minutes ALL DAY</p>
            <p className="text-sm text-text-secondary">
              This trader operates continuously during market hours (8:30 AM - 3:00 PM CT). It checks for opportunities every 5 minutes and is <strong>GUARANTEED to execute MINIMUM one trade per day</strong> using a multi-level fallback system (GEX → Iron Condor → Straddle). All state is persisted - it remembers everything across restarts.
            </p>
          </div>
        </div>
      </div>

      {/* Live Status - Trader Thinking Out Loud */}
      <div className="card">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-text-primary">SPY Autonomous Trader - Live Status</h2>
          <Bot className="text-primary w-6 h-6 animate-pulse" />
        </div>

        <div className="grid grid-cols-1 gap-4">
          {/* Current Action */}
          <div className="p-6 bg-gradient-to-r from-primary/10 to-primary/5 rounded-lg border border-primary/20">
            <div className="flex items-start gap-4">
              <Activity className="w-8 h-8 text-primary flex-shrink-0 mt-1" />
              <div className="flex-1">
                <p className="text-text-secondary text-sm font-medium mb-1">Current Action</p>
                <p className="text-xl font-bold text-text-primary mb-2">
                  {traderStatus.current_action || 'Initializing...'}
                </p>
                {traderStatus.market_analysis && (
                  <p className="text-text-secondary text-sm">
                    📊 {traderStatus.market_analysis}
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Last Decision */}
          {traderStatus.last_decision && (
            <div className="p-4 bg-background-hover rounded-lg">
              <div className="flex items-start gap-3">
                <Target className="w-5 h-5 text-success flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-text-secondary text-sm font-medium">Last Decision</p>
                  <p className="text-text-primary mt-1">{traderStatus.last_decision}</p>
                </div>
              </div>
            </div>
          )}

          {/* System Info Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="p-3 bg-background-hover rounded-lg">
              <p className="text-text-secondary text-xs">Status</p>
              <p className="text-text-primary font-semibold mt-1">
                {traderStatus.status || 'WORKING'}
              </p>
            </div>
            <div className="p-3 bg-background-hover rounded-lg">
              <p className="text-text-secondary text-xs">Mode</p>
              <p className="text-text-primary font-semibold mt-1 capitalize">
                {traderStatus.mode}
              </p>
            </div>
            <div className="p-3 bg-background-hover rounded-lg">
              <p className="text-text-secondary text-xs">Last Check</p>
              <p className="text-text-primary font-semibold mt-1">
                {formatTime(traderStatus.last_check)}
              </p>
            </div>
            <div className="p-3 bg-background-hover rounded-lg">
              <p className="text-text-secondary text-xs">Next Check</p>
              <p className="text-text-primary font-semibold mt-1">
                {traderStatus.next_check_time ? formatTime(traderStatus.next_check_time) : '~5min'}
              </p>
            </div>
          </div>
        </div>

        {/* Autonomous Operation Notice */}
        <div className="mt-6 p-4 bg-success/10 border border-success/20 rounded-lg flex items-start gap-3">
          <CheckCircle className="w-5 h-5 text-success flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-success font-semibold">✅ Fully Autonomous Trading - MINIMUM One Trade Daily GUARANTEED</p>
            <p className="text-text-secondary text-sm mt-1">
              This trader checks market conditions every 5 minutes ALL DAY during market hours (8:30 AM - 3:00 PM CT). It's <strong>GUARANTEED to execute MINIMUM one trade per day</strong> using a 3-level fallback system: GEX directional trade → Iron Condor → ATM Straddle. Watch this panel to see what it's thinking and doing in real-time.
            </p>
          </div>
        </div>
      </div>

      {/* Trading Account Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Account Balance - Most Important */}
        <div className="card bg-gradient-to-br from-primary/10 to-primary/5 border-primary/30">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-text-secondary text-sm">Trading Account</p>
              <p className="text-2xl font-bold text-text-primary mt-1">
                {formatCurrency(performance.current_value)}
              </p>
              <p className={`text-sm mt-1 ${
                (performance.return_pct ?? 0) >= 0 ? 'text-success' : 'text-danger'
              }`}>
                {(performance.return_pct ?? 0) >= 0 ? '+' : ''}{(performance.return_pct ?? 0).toFixed(2)}% return
              </p>
            </div>
            <DollarSign className="text-primary w-8 h-8" />
          </div>
        </div>

        <div className="card">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-text-secondary text-sm">Today's P&L</p>
              <p className={`text-2xl font-bold mt-1 ${
                performance.today_pnl >= 0 ? 'text-success' : 'text-danger'
              }`}>
                {performance.today_pnl >= 0 ? '+' : ''}{formatCurrency(performance.today_pnl)}
              </p>
            </div>
            <Activity className="text-primary w-8 h-8" />
          </div>
        </div>

        <div className="card">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-text-secondary text-sm">Win Rate</p>
              <p className="text-2xl font-bold text-text-primary mt-1">
                {(performance.win_rate ?? 0).toFixed(1)}%
              </p>
            </div>
            <Target className="text-primary w-8 h-8" />
          </div>
        </div>

        <div className="card">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-text-secondary text-sm">Sharpe Ratio</p>
              <p className="text-2xl font-bold text-text-primary mt-1">
                {(performance.sharpe_ratio ?? 0).toFixed(2)}
              </p>
            </div>
            <TrendingUp className="text-primary w-8 h-8" />
          </div>
        </div>
      </div>

      {/* P&L Breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-text-secondary text-sm">Total P&L</p>
              <p className={`text-2xl font-bold mt-1 ${
                performance.total_pnl >= 0 ? 'text-success' : 'text-danger'
              }`}>
                {performance.total_pnl >= 0 ? '+' : ''}{formatCurrency(performance.total_pnl)}
              </p>
            </div>
            <DollarSign className={`w-8 h-8 ${performance.total_pnl >= 0 ? 'text-success' : 'text-danger'}`} />
          </div>
        </div>

        <div className="card">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-text-secondary text-sm">Realized P&L</p>
              <p className={`text-2xl font-bold mt-1 ${
                performance.realized_pnl >= 0 ? 'text-success' : 'text-danger'
              }`}>
                {performance.realized_pnl >= 0 ? '+' : ''}{formatCurrency(performance.realized_pnl)}
              </p>
              <p className="text-xs text-text-muted mt-1">Closed trades</p>
            </div>
            <CheckCircle className={`w-8 h-8 ${performance.realized_pnl >= 0 ? 'text-success' : 'text-danger'}`} />
          </div>
        </div>

        <div className="card">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-text-secondary text-sm">Unrealized P&L</p>
              <p className={`text-2xl font-bold mt-1 ${
                performance.unrealized_pnl >= 0 ? 'text-success' : 'text-danger'
              }`}>
                {performance.unrealized_pnl >= 0 ? '+' : ''}{formatCurrency(performance.unrealized_pnl)}
              </p>
              <p className="text-xs text-text-muted mt-1">Open positions</p>
            </div>
            <Clock className={`w-8 h-8 ${performance.unrealized_pnl >= 0 ? 'text-success' : 'text-danger'}`} />
          </div>
        </div>

        <div className="card">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-text-secondary text-sm">Max Drawdown</p>
              <p className="text-2xl font-bold text-danger mt-1">
                {(performance.max_drawdown ?? 0).toFixed(1)}%
              </p>
            </div>
            <TrendingDown className="text-danger w-8 h-8" />
          </div>
        </div>
      </div>

      {/* P&L Over Time Chart */}
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
                  <linearGradient id="colorPnl" x1="0" y1="0" x2="0" y2="1">
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
                  tickFormatter={(value) => `$${value >= 0 ? '+' : ''}${value.toLocaleString()}`}
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
                    <span style={{ color: value >= 0 ? '#10b981' : '#ef4444', fontWeight: 'bold' }}>
                      ${value >= 0 ? '+' : ''}{value.toFixed(2)}
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
                  fill="url(#colorPnl)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : closedTradesChartData.length > 0 ? (
          // Build chart from closed trades if equity curve is empty (using memoized data)
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={closedTradesChartData}
                margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="colorPnlAlt" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={closedTradesTotalPnl >= 0 ? "#10b981" : "#ef4444"} stopOpacity={0.3}/>
                    <stop offset="95%" stopColor={closedTradesTotalPnl >= 0 ? "#10b981" : "#ef4444"} stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
                <XAxis
                  dataKey="date"
                  stroke="#6b7280"
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  stroke="#6b7280"
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(value) => `$${(value / 1000).toFixed(0)}K`}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                  labelStyle={{ color: '#9ca3af' }}
                  formatter={(value: number, name: string) => [
                    `$${value.toLocaleString('en-US', { minimumFractionDigits: 2 })}`,
                    name === 'pnl' ? 'Cumulative P&L' : 'Daily P&L'
                  ]}
                />
                <Area
                  type="monotone"
                  dataKey="pnl"
                  stroke={closedTradesTotalPnl >= 0 ? "#10b981" : "#ef4444"}
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#colorPnlAlt)"
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
        {(equityCurve.length > 0 || closedTradesChartData.length > 0) && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-6 border-t border-border">
            <div className="text-center">
              <p className="text-text-muted text-xs mb-1">First Trade</p>
              <p className="text-text-primary font-semibold">
                {equityCurve.length > 0
                  ? equityCurve[0]?.date
                  : closedTradesChartData.length > 0
                    ? closedTradesChartData[0]?.date
                    : 'N/A'
                }
              </p>
            </div>
            <div className="text-center">
              <p className="text-text-muted text-xs mb-1">Last Trade</p>
              <p className="text-text-primary font-semibold">
                {equityCurve.length > 0
                  ? equityCurve[equityCurve.length - 1]?.date
                  : closedTradesChartData.length > 0
                    ? closedTradesChartData[closedTradesChartData.length - 1]?.date
                    : 'N/A'
                }
              </p>
            </div>
            <div className="text-center">
              <p className="text-text-muted text-xs mb-1">Total P&L</p>
              <p className={`font-bold ${
                (equityCurve.length > 0 ? equityCurve[equityCurve.length - 1]?.pnl : closedTradesTotalPnl) >= 0
                  ? 'text-success' : 'text-danger'
              }`}>
                {(equityCurve.length > 0 ? equityCurve[equityCurve.length - 1]?.pnl : closedTradesTotalPnl) >= 0 ? '+' : ''}
                {formatCurrency(equityCurve.length > 0 ? equityCurve[equityCurve.length - 1]?.pnl || 0 : closedTradesTotalPnl)}
              </p>
            </div>
            <div className="text-center">
              <p className="text-text-muted text-xs mb-1">Current Equity</p>
              <p className="text-text-primary font-bold">
                {formatCurrency(
                  equityCurve.length > 0
                    ? equityCurve[equityCurve.length - 1]?.equity || 0
                    : 1000000 + closedTradesTotalPnl
                )}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* ML Model Status & Predictions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* ML Model Status */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <Brain className="w-6 h-6 text-primary" />
              <h2 className="text-lg font-semibold text-text-primary">ML Model Status</h2>
            </div>
            {mlModelStatus?.is_trained && (
              <span className="px-2 py-1 bg-success/20 text-success text-xs font-semibold rounded-full">
                TRAINED
              </span>
            )}
          </div>

          {mlModelStatus ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 bg-background-hover rounded-lg">
                  <p className="text-text-muted text-xs">Model Accuracy</p>
                  <p className="text-text-primary font-bold text-lg">
                    {((mlModelStatus.accuracy || 0) * 100).toFixed(1)}%
                  </p>
                </div>
                <div className="p-3 bg-background-hover rounded-lg">
                  <p className="text-text-muted text-xs">Training Samples</p>
                  <p className="text-text-primary font-bold text-lg">
                    {mlModelStatus.training_samples?.toLocaleString() || 'N/A'}
                  </p>
                </div>
                <div className="p-3 bg-background-hover rounded-lg">
                  <p className="text-text-muted text-xs">Features Used</p>
                  <p className="text-text-primary font-bold text-lg">
                    {mlModelStatus.feature_count || 'N/A'}
                  </p>
                </div>
                <div className="p-3 bg-background-hover rounded-lg">
                  <p className="text-text-muted text-xs">Last Trained</p>
                  <p className="text-text-primary font-semibold text-sm">
                    {mlModelStatus.last_trained ? new Date(mlModelStatus.last_trained).toLocaleDateString() : 'Never'}
                  </p>
                </div>
              </div>

              {mlModelStatus.feature_importance && (
                <div className="mt-4">
                  <p className="text-text-muted text-xs mb-2">Top Features</p>
                  <div className="space-y-2">
                    {Object.entries(mlModelStatus.feature_importance || {}).slice(0, 5).map(([feature, importance]: [string, any]) => (
                      <div key={feature} className="flex items-center gap-2">
                        <span className="text-text-secondary text-xs w-32 truncate">{feature}</span>
                        <div className="flex-1 bg-background-primary rounded-full h-2">
                          <div
                            className="bg-primary h-2 rounded-full"
                            style={{ width: `${(importance * 100).toFixed(0)}%` }}
                          />
                        </div>
                        <span className="text-text-muted text-xs w-12 text-right">{(importance * 100).toFixed(0)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-8 text-text-secondary">
              <Brain className="w-10 h-10 text-text-muted mx-auto mb-2" />
              <p>ML model not trained yet</p>
              <p className="text-xs text-text-muted mt-1">Model will train automatically with trade data</p>
            </div>
          )}
        </div>

        {/* Recent ML Predictions */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <Zap className="w-6 h-6 text-warning" />
              <h2 className="text-lg font-semibold text-text-primary">Recent ML Predictions</h2>
            </div>
            <span className="text-xs text-text-muted">{mlPredictions.length} predictions</span>
          </div>

          {mlPredictions.length > 0 ? (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {mlPredictions.map((pred, idx) => (
                <div key={idx} className="p-3 bg-background-hover rounded-lg flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                      pred.prediction === 'bullish' || pred.predicted_direction > 0
                        ? 'bg-success/20 text-success'
                        : pred.prediction === 'bearish' || pred.predicted_direction < 0
                        ? 'bg-danger/20 text-danger'
                        : 'bg-warning/20 text-warning'
                    }`}>
                      {pred.prediction === 'bullish' || pred.predicted_direction > 0 ? (
                        <TrendingUp className="w-4 h-4" />
                      ) : pred.prediction === 'bearish' || pred.predicted_direction < 0 ? (
                        <TrendingDown className="w-4 h-4" />
                      ) : (
                        <Activity className="w-4 h-4" />
                      )}
                    </div>
                    <div>
                      <p className="text-text-primary font-semibold text-sm">
                        {pred.symbol || 'SPY'} - {pred.pattern || pred.prediction?.toUpperCase() || 'NEUTRAL'}
                      </p>
                      <p className="text-text-muted text-xs">
                        {pred.timestamp ? new Date(pred.timestamp).toLocaleString() : 'N/A'}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className={`font-bold ${
                      (pred.confidence || 0) >= 70 ? 'text-success' :
                      (pred.confidence || 0) >= 50 ? 'text-warning' :
                      'text-text-muted'
                    }`}>
                      {pred.confidence?.toFixed(0) || pred.probability?.toFixed(0) || 0}%
                    </p>
                    <p className="text-text-muted text-xs">confidence</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-text-secondary">
              <Zap className="w-10 h-10 text-text-muted mx-auto mb-2" />
              <p>No predictions yet</p>
              <p className="text-xs text-text-muted mt-1">Predictions appear during market analysis</p>
            </div>
          )}
        </div>
      </div>

      {/* Complete Trade History - Full Transparency */}
      <div className="card">
        <div
          className="flex items-center justify-between cursor-pointer"
          onClick={() => setShowClosedTrades(!showClosedTrades)}
        >
          <div className="flex items-center gap-3">
            <History className="w-6 h-6 text-primary" />
            <h2 className="text-xl font-semibold text-text-primary">Complete Trade History</h2>
            <span className="px-2 py-1 bg-primary/20 text-primary text-xs font-semibold rounded-full">
              {closedTrades.length} closed trades
            </span>
            {closedTrades.length > 0 && (
              <span className={`px-2 py-1 text-xs font-semibold rounded-full ${
                closedTradesTotalPnl >= 0
                  ? 'bg-success/20 text-success'
                  : 'bg-danger/20 text-danger'
              }`}>
                Total: {closedTradesTotalPnl >= 0 ? '+' : ''}
                {formatCurrency(closedTradesTotalPnl)}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {closedTrades.length > 0 && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  // Export trade history to CSV
                  const headers = ['Exit Date', 'Exit Time', 'Entry Date', 'Strategy', 'Symbol', 'Strike', 'Type', 'Contracts', 'Entry Price', 'Exit Price', 'P&L $', 'P&L %', 'Exit Reason', 'Hold Duration (min)']
                  const rows = closedTrades.map(t => [
                    t.exit_date || '',
                    t.exit_time || '',
                    t.entry_date || '',
                    t.strategy || '',
                    t.symbol || 'SPY',
                    t.strike || '',
                    t.option_type || '',
                    t.contracts || 1,
                    t.entry_price || 0,
                    t.exit_price || 0,
                    t.pnl || 0,
                    t.pnl_pct || 0,
                    t.exit_reason || '',
                    t.hold_duration_minutes || ''
                  ])
                  const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
                  const blob = new Blob([csv], { type: 'text/csv' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = `trade_history_${new Date().toISOString().split('T')[0]}.csv`
                  a.click()
                }}
                className="px-3 py-1 bg-primary/20 text-primary hover:bg-primary/30 text-sm rounded-lg transition-colors"
              >
                Export CSV
              </button>
            )}
            <button className="p-2 hover:bg-background-hover rounded-lg transition-colors">
              {showClosedTrades ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {showClosedTrades && (
          <div className="mt-4">
            {closedTrades.length > 0 ? (
              <>
                {/* Summary Stats */}
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4 p-4 bg-background-hover rounded-lg">
                  <div>
                    <p className="text-text-muted text-xs">Total Trades</p>
                    <p className="text-text-primary font-bold text-lg">{closedTrades.length}</p>
                  </div>
                  <div>
                    <p className="text-text-muted text-xs">Winning Trades</p>
                    <p className="text-success font-bold text-lg">
                      {closedTrades.filter(t => (t.pnl || 0) > 0).length}
                    </p>
                  </div>
                  <div>
                    <p className="text-text-muted text-xs">Losing Trades</p>
                    <p className="text-danger font-bold text-lg">
                      {closedTrades.filter(t => (t.pnl || 0) <= 0).length}
                    </p>
                  </div>
                  <div>
                    <p className="text-text-muted text-xs">Win Rate</p>
                    <p className="text-text-primary font-bold text-lg">
                      {((closedTrades.filter(t => (t.pnl || 0) > 0).length / closedTrades.length) * 100).toFixed(1)}%
                    </p>
                  </div>
                  <div>
                    <p className="text-text-muted text-xs">Total P&L</p>
                    <p className={`font-bold text-lg ${
                      closedTradesTotalPnl >= 0 ? 'text-success' : 'text-danger'
                    }`}>
                      {closedTradesTotalPnl >= 0 ? '+' : ''}
                      {formatCurrency(closedTradesTotalPnl)}
                    </p>
                  </div>
                </div>

                {/* Scrollable Trade Table */}
                <div className="overflow-x-auto max-h-96 overflow-y-auto border border-border rounded-lg">
                  <table className="w-full">
                    <thead className="sticky top-0 bg-background-card z-10">
                      <tr className="border-b border-border">
                        <th className="text-left py-3 px-3 text-text-secondary font-medium text-xs">Exit Date</th>
                        <th className="text-left py-3 px-3 text-text-secondary font-medium text-xs">Entry Date</th>
                        <th className="text-left py-3 px-3 text-text-secondary font-medium text-xs">Strategy</th>
                        <th className="text-left py-3 px-3 text-text-secondary font-medium text-xs">Contract</th>
                        <th className="text-center py-3 px-3 text-text-secondary font-medium text-xs">Qty</th>
                        <th className="text-right py-3 px-3 text-text-secondary font-medium text-xs">Entry $</th>
                        <th className="text-right py-3 px-3 text-text-secondary font-medium text-xs">Exit $</th>
                        <th className="text-right py-3 px-3 text-text-secondary font-medium text-xs">P&L $</th>
                        <th className="text-right py-3 px-3 text-text-secondary font-medium text-xs">P&L %</th>
                        <th className="text-left py-3 px-3 text-text-secondary font-medium text-xs">Exit Reason</th>
                        <th className="text-center py-3 px-3 text-text-secondary font-medium text-xs">Result</th>
                      </tr>
                    </thead>
                    <tbody>
                      {closedTrades.map((trade, idx) => {
                        const pnl = trade.pnl || 0
                        const pnlPct = trade.pnl_pct || 0
                        const isWin = pnl > 0
                        return (
                          <tr key={idx} className="border-b border-border/50 hover:bg-background-hover transition-colors">
                            <td className="py-2 px-3 text-text-secondary text-xs">
                              <div>{trade.exit_date || 'N/A'}</div>
                              <div className="text-text-muted">{trade.exit_time || ''}</div>
                            </td>
                            <td className="py-2 px-3 text-text-muted text-xs">
                              <div>{trade.entry_date || 'N/A'}</div>
                              <div>{trade.entry_time || ''}</div>
                            </td>
                            <td className="py-2 px-3 text-text-primary font-semibold text-xs">
                              {trade.strategy || 'Unknown'}
                            </td>
                            <td className="py-2 px-3 text-text-primary text-xs">
                              <div>{trade.symbol || 'SPY'} ${trade.strike}{trade.option_type?.charAt(0) || 'C'}</div>
                              <div className="text-text-muted font-mono text-xs">{trade.contract_symbol || ''}</div>
                            </td>
                            <td className="py-2 px-3 text-center text-text-primary text-xs">
                              {trade.contracts || 1}
                            </td>
                            <td className="py-2 px-3 text-right text-text-primary text-xs">
                              ${Math.abs(trade.entry_price || 0).toFixed(2)}
                            </td>
                            <td className="py-2 px-3 text-right text-text-primary text-xs">
                              ${Math.abs(trade.exit_price || 0).toFixed(2)}
                            </td>
                            <td className={`py-2 px-3 text-right font-bold text-xs ${isWin ? 'text-success' : 'text-danger'}`}>
                              {isWin ? '+' : ''}${pnl.toFixed(2)}
                            </td>
                            <td className={`py-2 px-3 text-right text-xs ${isWin ? 'text-success' : 'text-danger'}`}>
                              {isWin ? '+' : ''}{pnlPct.toFixed(1)}%
                            </td>
                            <td className="py-2 px-3 text-text-muted text-xs max-w-32 truncate" title={trade.exit_reason || ''}>
                              {trade.exit_reason || '-'}
                            </td>
                            <td className="py-2 px-3 text-center">
                              <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                                isWin ? 'bg-success/20 text-success' : 'bg-danger/20 text-danger'
                              }`}>
                                {isWin ? 'WIN' : 'LOSS'}
                              </span>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
                <p className="text-xs text-text-muted mt-2 text-center">
                  Scroll to see all trades • Export CSV for full data analysis
                </p>
              </>
            ) : (
              <div className="text-center py-8 text-text-secondary">
                <History className="w-10 h-10 text-text-muted mx-auto mb-2" />
                <p>No closed trades yet</p>
                <p className="text-xs text-text-muted mt-1">Closed trades will appear here as positions are exited</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* VIX Hedge Signal - Risk Management */}
      {vixSignal && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <Shield className="w-6 h-6 text-primary" />
              <h2 className="text-xl font-semibold text-text-primary">VIX Hedge Signal</h2>
            </div>
            {vixData && (
              <div className="flex items-center gap-4 text-sm">
                <div className="px-3 py-1 bg-background-hover rounded-lg">
                  <span className="text-text-muted">VIX:</span>
                  <span className="text-text-primary font-bold ml-2">{vixData.vix_spot?.toFixed(2)}</span>
                </div>
                <div className={`px-3 py-1 rounded-lg ${
                  vixData.vol_regime === 'low' || vixData.vol_regime === 'very_low' ? 'bg-success/20 text-success' :
                  vixData.vol_regime === 'elevated' || vixData.vol_regime === 'high' ? 'bg-warning/20 text-warning' :
                  vixData.vol_regime === 'extreme' ? 'bg-danger/20 text-danger' :
                  'bg-primary/20 text-primary'
                }`}>
                  {vixData.vol_regime?.toUpperCase()}
                </div>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Signal Card */}
            <div className={`p-4 rounded-lg border ${
              vixSignal.signal_type === 'buy_vix_call_spread' ? 'bg-success/10 border-success/30' :
              vixSignal.signal_type === 'reduce_hedge' ? 'bg-warning/10 border-warning/30' :
              vixSignal.signal_type === 'no_action' ? 'bg-background-hover border-border' :
              'bg-primary/10 border-primary/30'
            }`}>
              <div className="flex items-center gap-2 mb-2">
                <BarChart3 className="w-5 h-5" />
                <span className="font-semibold text-text-primary">
                  {vixSignal.signal_type?.replace(/_/g, ' ').toUpperCase()}
                </span>
                <span className="text-text-muted text-sm ml-auto">
                  Confidence: {vixSignal.confidence?.toFixed(0)}%
                </span>
              </div>
              <p className="text-text-secondary text-sm">{vixSignal.reasoning}</p>
            </div>

            {/* Recommendation Card */}
            <div className="p-4 bg-background-hover rounded-lg">
              <p className="text-text-muted text-xs font-medium mb-2">RECOMMENDED ACTION</p>
              <p className="text-text-primary text-sm">{vixSignal.recommended_action}</p>
              {vixSignal.risk_warning && vixSignal.risk_warning !== 'None' && (
                <div className="mt-3 p-2 bg-danger/10 rounded border border-danger/20">
                  <p className="text-danger text-xs flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" />
                    {vixSignal.risk_warning}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* VIX Metrics */}
          {vixData && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
              <div className="p-3 bg-background-hover rounded-lg">
                <p className="text-text-muted text-xs">IV Percentile</p>
                <p className="text-text-primary font-semibold mt-1">{vixData.iv_percentile?.toFixed(0)}th</p>
              </div>
              <div className="p-3 bg-background-hover rounded-lg">
                <p className="text-text-muted text-xs">Realized Vol (20d)</p>
                <p className="text-text-primary font-semibold mt-1">{vixData.realized_vol_20d?.toFixed(1)}%</p>
              </div>
              <div className="p-3 bg-background-hover rounded-lg">
                <p className="text-text-muted text-xs">IV-RV Spread</p>
                <p className={`font-semibold mt-1 ${(vixData.iv_rv_spread || 0) > 5 ? 'text-warning' : 'text-success'}`}>
                  {vixData.iv_rv_spread?.toFixed(1)} pts
                </p>
              </div>
              <div className="p-3 bg-background-hover rounded-lg">
                <p className="text-text-muted text-xs">Term Structure</p>
                <p className={`font-semibold mt-1 ${(vixData.term_structure_pct || 0) > 0 ? 'text-text-primary' : 'text-warning'}`}>
                  {vixData.term_structure_pct?.toFixed(1)}% ({vixData.structure_type})
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Strategies */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-text-primary">Active Strategies</h2>
          <div className="flex items-center gap-3">
            <span className="text-xs text-text-muted">Click toggle to enable/disable</span>
            <span className="text-xs text-text-muted">|</span>
            <span className="text-xs text-success">✓ Live from database ({strategies.reduce((sum, s) => sum + s.total_trades, 0)} total trades)</span>
          </div>
        </div>
        {strategies.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-3 px-4 text-text-secondary font-medium">Strategy</th>
                  <th className="text-center py-3 px-4 text-text-secondary font-medium">Enabled</th>
                  <th className="text-center py-3 px-4 text-text-secondary font-medium">Total Trades</th>
                  <th className="text-center py-3 px-4 text-text-secondary font-medium">Win Rate</th>
                  <th className="text-right py-3 px-4 text-text-secondary font-medium">Total P&L</th>
                  <th className="text-right py-3 px-4 text-text-secondary font-medium">Last Trade</th>
                </tr>
              </thead>
              <tbody>
                {strategies.map((strategy) => (
                  <tr key={strategy.id} className="border-b border-border/50 hover:bg-background-hover transition-colors">
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-3">
                        <div className={`w-2 h-2 rounded-full ${
                          strategy.status === 'active' ? 'bg-success' : 'bg-text-muted'
                        }`} />
                        <span className="text-text-primary font-semibold">{strategy.name}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-center">
                      <button
                        onClick={() => handleToggleStrategy(strategy.id)}
                        disabled={strategyTogglingId === strategy.id}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                          strategy.status === 'active' ? 'bg-success' : 'bg-text-muted/30'
                        } ${strategyTogglingId === strategy.id ? 'opacity-50 cursor-wait' : 'cursor-pointer'}`}
                      >
                        <span
                          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                            strategy.status === 'active' ? 'translate-x-6' : 'translate-x-1'
                          }`}
                        />
                      </button>
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span className="text-text-primary font-semibold">{strategy.total_trades}</span>
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span className={`font-semibold ${
                        (strategy.win_rate ?? 0) >= 60 ? 'text-success' :
                        (strategy.win_rate ?? 0) >= 40 ? 'text-warning' :
                        'text-danger'
                      }`}>
                        {(strategy.win_rate ?? 0).toFixed(1)}%
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <span className={`font-bold ${
                        strategy.pnl >= 0 ? 'text-success' : 'text-danger'
                      }`}>
                        {strategy.pnl >= 0 ? '+' : ''}{formatCurrency(strategy.pnl)}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <span className="text-text-secondary text-sm">
                        {strategy.last_trade_date && strategy.last_trade_date !== 'Never'
                          ? new Date(strategy.last_trade_date).toLocaleDateString('en-US', {
                              month: 'short',
                              day: 'numeric',
                              year: 'numeric'
                            })
                          : 'Never'
                        }
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-8 text-text-secondary">
            <Target className="w-10 h-10 text-text-muted mx-auto mb-2" />
            <p>No strategies with trades yet</p>
            <p className="text-xs text-text-muted mt-1">Strategies will appear here as trades are executed</p>
          </div>
        )}
      </div>

      {/* Recent Trades */}
      <div className="card">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
          <h2 className="text-xl font-semibold text-text-primary">Recent Trades</h2>
          <div className="flex flex-wrap items-center gap-3">
            {/* Search */}
            <div className="relative">
              <input
                type="text"
                placeholder="Search trades..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 pr-4 py-2 bg-background-hover border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-primary w-40"
              />
              <svg className="absolute left-2.5 top-2.5 w-4 h-4 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>

            {/* Status Filter */}
            <div className="flex items-center gap-1 bg-background-hover rounded-lg p-1">
              {(['all', 'open', 'closed'] as const).map((filter) => (
                <button
                  key={filter}
                  onClick={() => setTradeFilter(filter)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                    tradeFilter === filter
                      ? 'bg-primary text-white'
                      : 'text-text-secondary hover:text-text-primary'
                  }`}
                >
                  {filter.charAt(0).toUpperCase() + filter.slice(1)}
                </button>
              ))}
            </div>

            {/* Strategy Filter */}
            <select
              value={strategyFilter}
              onChange={(e) => setStrategyFilter(e.target.value)}
              className="px-3 py-2 bg-background-hover border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-primary"
            >
              <option value="all">All Strategies</option>
              {strategies.map((s) => (
                <option key={s.id} value={s.name}>{s.name}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-3 px-4 text-text-secondary font-medium">Time</th>
                <th className="text-left py-3 px-4 text-text-secondary font-medium">Strategy</th>
                <th className="text-left py-3 px-4 text-text-secondary font-medium">Contract</th>
                <th className="text-center py-3 px-4 text-text-secondary font-medium">Expiration</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium">Entry $</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium">Current $</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium">Status</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium">P&L</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {recentTrades
                .filter((trade) => {
                  // Status filter
                  if (tradeFilter === 'open' && trade.status !== 'OPEN' && trade.status !== 'filled') return false
                  if (tradeFilter === 'closed' && trade.status !== 'CLOSED') return false

                  // Strategy filter
                  if (strategyFilter !== 'all' && trade.strategy !== strategyFilter) return false

                  // Search filter
                  if (searchQuery) {
                    const query = searchQuery.toLowerCase()
                    const matchesSearch =
                      trade.symbol?.toLowerCase().includes(query) ||
                      trade.strategy?.toLowerCase().includes(query) ||
                      trade.action?.toLowerCase().includes(query) ||
                      String(trade.strike).includes(query)
                    if (!matchesSearch) return false
                  }

                  return true
                })
                .map((trade) => {
                // Calculate real P&L from entry and current prices
                const entryPrice = Math.abs(trade.price || 0);
                const currentPrice = Math.abs(trade.current_price || trade.price || 0);
                const contracts = trade.quantity || 1;
                const entryValue = entryPrice * contracts * 100;
                const currentValue = currentPrice * contracts * 100;
                const dollarChange = currentValue - entryValue;
                const pctChange = entryValue > 0 ? (dollarChange / entryValue) * 100 : 0;
                const displayPnl = trade.pnl !== undefined && trade.pnl !== null ? trade.pnl : dollarChange;

                // Format contract display (e.g., "SPY $595C")
                const optionType = trade.type?.toUpperCase()?.charAt(0) || 'C';
                const strike = trade.strike || 0;
                const contractDisplay = strike > 0 ? `${trade.symbol} $${strike}${optionType}` : trade.symbol;

                // Format expiration - show full date for verification
                const expDate = trade.expiration_date || '-';

                // Format entry date/time for display
                const entryDateTime = trade.entry_date && trade.entry_time
                  ? `${trade.entry_date} ${trade.entry_time}`
                  : formatTime(trade.timestamp);

                return (
                <Fragment key={trade.id}>
                  <tr
                    className="border-b border-border/50 hover:bg-background-hover transition-colors cursor-pointer"
                    onClick={() => setExpandedTradeId(expandedTradeId === trade.id ? null : trade.id)}
                  >
                    <td className="py-3 px-4 text-text-secondary text-sm">
                      <div>{trade.entry_date || 'N/A'}</div>
                      <div className="text-xs">{trade.entry_time || ''}</div>
                    </td>
                    <td className="py-3 px-4">
                      <div className="font-semibold text-text-primary text-sm">{trade.strategy || trade.action}</div>
                      <div className="text-xs text-text-secondary">{contracts}x contracts</div>
                    </td>
                    <td className="py-3 px-4">
                      <div className="text-text-primary font-medium">{contractDisplay}</div>
                      <div className="text-xs text-text-muted font-mono">{trade.contract_symbol || 'N/A'}</div>
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span className="text-text-primary text-sm font-mono">{expDate}</span>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className={`font-semibold ${entryPrice > 0 ? 'text-text-primary' : 'text-danger'}`}>
                        {entryPrice > 0 ? formatCurrency(entryPrice) : '$0.00 ⚠️'}
                      </div>
                      <div className="text-xs text-text-secondary">per contract</div>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="text-text-primary font-semibold">{formatCurrency(currentPrice)}</div>
                      <div className="text-xs text-text-secondary">@ {formatCurrency(trade.current_spot_price || trade.entry_spot_price || 0)}</div>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <span className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full font-medium ${
                        trade.status === 'OPEN' ? 'bg-success/20 text-success' :
                        trade.status === 'CLOSED' ? 'bg-primary/20 text-primary' :
                        trade.status === 'filled' ? 'bg-success/20 text-success' :
                        trade.status === 'pending' ? 'bg-warning/20 text-warning' :
                        'bg-danger/20 text-danger'
                      }`}>
                        {(trade.status === 'filled' || trade.status === 'OPEN') && <CheckCircle className="w-3 h-3" />}
                        {trade.status === 'CLOSED' && <XCircle className="w-3 h-3" />}
                        {trade.status === 'pending' && <Clock className="w-3 h-3" />}
                        {trade.status?.toUpperCase() || 'UNKNOWN'}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right">
                      {entryPrice > 0 ? (
                        <div>
                          <div className={`font-bold text-lg ${
                            displayPnl >= 0 ? 'text-success' : 'text-danger'
                          }`}>
                            {displayPnl >= 0 ? '+' : ''}{formatCurrency(displayPnl)}
                          </div>
                          <div className={`text-xs ${pctChange >= 0 ? 'text-success' : 'text-danger'}`}>
                            {pctChange >= 0 ? '+' : ''}{pctChange.toFixed(1)}%
                          </div>
                        </div>
                      ) : (
                        <div className="text-danger text-sm">No entry price</div>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button className="text-primary hover:text-primary/80">
                        {expandedTradeId === trade.id ? '▼' : '▶'}
                      </button>
                    </td>
                  </tr>
                  {expandedTradeId === trade.id && (
                    <tr className="bg-background-hover">
                      <td colSpan={9} className="py-4 px-6">
                        <div className="space-y-4">
                          {/* Trade Reasoning */}
                          {trade.trade_reasoning && (
                            <>
                              <h4 className="font-semibold text-primary flex items-center gap-2">
                                <Target className="w-4 h-4" />
                                Trade Reasoning
                              </h4>
                              <div className="bg-background-primary p-4 rounded-lg font-mono text-sm whitespace-pre-wrap text-text-secondary">
                                {trade.trade_reasoning}
                              </div>
                            </>
                          )}

                          {/* VERIFIABLE TRADE DETAILS - For checking against Tradier */}
                          <h4 className="font-semibold text-success flex items-center gap-2 mt-4">
                            <CheckCircle className="w-4 h-4" />
                            Verifiable Trade Details (Check on Tradier)
                          </h4>
                          <div className="p-4 bg-success/10 border border-success/30 rounded-lg">
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                              <div>
                                <div className="text-xs text-text-secondary mb-1">Contract Symbol</div>
                                <div className="font-mono text-success font-bold text-sm">
                                  {trade.contract_symbol || `${trade.symbol}${trade.expiration_date?.replace(/-/g, '').slice(2)}${trade.type?.charAt(0).toUpperCase()}${String(Math.round((trade.strike || 0) * 1000)).padStart(8, '0')}`}
                                </div>
                                <div className="text-xs text-text-muted mt-1">Use this to verify on Tradier</div>
                              </div>
                              <div>
                                <div className="text-xs text-text-secondary mb-1">Entry Date</div>
                                <div className="text-text-primary font-semibold">
                                  {trade.entry_date || 'N/A'}
                                </div>
                              </div>
                              <div>
                                <div className="text-xs text-text-secondary mb-1">Entry Time</div>
                                <div className="text-text-primary font-semibold">
                                  {trade.entry_time || 'N/A'}
                                </div>
                              </div>
                              <div>
                                <div className="text-xs text-text-secondary mb-1">Expiration</div>
                                <div className="text-text-primary font-semibold">
                                  {trade.expiration_date || 'N/A'}
                                </div>
                              </div>
                            </div>
                            <div className="mt-3 pt-3 border-t border-success/20 grid grid-cols-3 gap-4">
                              <div>
                                <div className="text-xs text-text-secondary mb-1">Strike Price</div>
                                <div className="text-text-primary font-bold text-lg">${trade.strike || 0}</div>
                              </div>
                              <div>
                                <div className="text-xs text-text-secondary mb-1">Option Type</div>
                                <div className={`font-bold text-lg ${trade.type?.toUpperCase() === 'CALL' || trade.type?.charAt(0).toUpperCase() === 'C' ? 'text-success' : 'text-danger'}`}>
                                  {trade.type?.toUpperCase() || 'N/A'}
                                </div>
                              </div>
                              <div>
                                <div className="text-xs text-text-secondary mb-1">Contracts</div>
                                <div className="text-text-primary font-bold text-lg">{trade.quantity || 0}</div>
                              </div>
                            </div>
                          </div>

                          {/* Position Details Grid */}
                          <h4 className="font-semibold text-text-primary flex items-center gap-2 mt-4">
                            <DollarSign className="w-4 h-4" />
                            Position Details
                          </h4>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                            <div className="p-3 bg-background-primary rounded-lg">
                              <div className="text-xs text-text-secondary mb-1">Entry Price</div>
                              <div className="text-text-primary font-semibold">{formatCurrency(trade.price)}</div>
                              <div className="text-xs text-text-muted mt-1">@ {formatCurrency(trade.entry_spot_price || 0)} spot</div>
                            </div>
                            <div className="p-3 bg-background-primary rounded-lg">
                              <div className="text-xs text-text-secondary mb-1">Current Price</div>
                              <div className="text-text-primary font-semibold">{formatCurrency(trade.current_price || trade.price)}</div>
                              <div className="text-xs text-text-muted mt-1">@ {formatCurrency(trade.current_spot_price || 0)} spot</div>
                            </div>
                            <div className="p-3 bg-background-primary rounded-lg">
                              <div className="text-xs text-text-secondary mb-1">Bid / Ask Spread</div>
                              <div className="text-text-primary font-semibold">${trade.entry_bid?.toFixed(2) || '0.00'} / ${trade.entry_ask?.toFixed(2) || '0.00'}</div>
                              <div className="text-xs text-text-muted mt-1">Spread: ${Math.abs((trade.entry_ask || 0) - (trade.entry_bid || 0)).toFixed(2)}</div>
                            </div>
                            <div className="p-3 bg-background-primary rounded-lg">
                              <div className="text-xs text-text-secondary mb-1">Contracts × Strike</div>
                              <div className="text-text-primary font-semibold">{trade.quantity}x @ ${trade.strike}</div>
                              <div className="text-xs text-text-muted mt-1">Exp: {trade.expiration_date || 'N/A'}</div>
                            </div>
                          </div>

                          {/* Greeks Section */}
                          <h4 className="font-semibold text-text-primary flex items-center gap-2 mt-4">
                            <Activity className="w-4 h-4" />
                            Greeks & Risk Metrics
                          </h4>
                          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                            <div className="p-3 bg-gradient-to-br from-primary/10 to-transparent rounded-lg border border-primary/20">
                              <div className="text-xs text-text-secondary mb-1">Delta (Δ)</div>
                              <div className="text-text-primary font-bold text-lg">
                                {trade.entry_delta ? trade.entry_delta.toFixed(3) : trade.current_delta?.toFixed(3) || '—'}
                              </div>
                              <div className="text-xs text-text-muted mt-1">
                                {trade.current_delta && trade.entry_delta
                                  ? `Change: ${(trade.current_delta - trade.entry_delta).toFixed(3)}`
                                  : 'Price sensitivity'
                                }
                              </div>
                            </div>
                            <div className="p-3 bg-gradient-to-br from-success/10 to-transparent rounded-lg border border-success/20">
                              <div className="text-xs text-text-secondary mb-1">Gamma (Γ)</div>
                              <div className="text-text-primary font-bold text-lg">
                                {trade.gamma?.toFixed(4) || '—'}
                              </div>
                              <div className="text-xs text-text-muted mt-1">Delta acceleration</div>
                            </div>
                            <div className="p-3 bg-gradient-to-br from-danger/10 to-transparent rounded-lg border border-danger/20">
                              <div className="text-xs text-text-secondary mb-1">Theta (Θ)</div>
                              <div className="text-text-primary font-bold text-lg">
                                {trade.theta ? `$${trade.theta.toFixed(2)}` : '—'}
                              </div>
                              <div className="text-xs text-text-muted mt-1">Daily decay</div>
                            </div>
                            <div className="p-3 bg-gradient-to-br from-warning/10 to-transparent rounded-lg border border-warning/20">
                              <div className="text-xs text-text-secondary mb-1">Vega (ν)</div>
                              <div className="text-text-primary font-bold text-lg">
                                {trade.vega?.toFixed(3) || '—'}
                              </div>
                              <div className="text-xs text-text-muted mt-1">IV sensitivity</div>
                            </div>
                            <div className="p-3 bg-gradient-to-br from-purple-500/10 to-transparent rounded-lg border border-purple-500/20">
                              <div className="text-xs text-text-secondary mb-1">IV (Entry → Current)</div>
                              <div className="text-text-primary font-bold text-lg">
                                {trade.entry_iv ? `${(trade.entry_iv * 100).toFixed(1)}%` : '—'}
                                {trade.current_iv && trade.entry_iv && (
                                  <span className={`text-sm ml-1 ${trade.current_iv > trade.entry_iv ? 'text-success' : 'text-danger'}`}>
                                    → {(trade.current_iv * 100).toFixed(1)}%
                                  </span>
                                )}
                              </div>
                              <div className="text-xs text-text-muted mt-1">Implied volatility</div>
                            </div>
                          </div>

                          {/* GEX Context */}
                          {(trade.gex_regime || trade.entry_net_gex) && (
                            <>
                              <h4 className="font-semibold text-text-primary flex items-center gap-2 mt-4">
                                <BarChart3 className="w-4 h-4" />
                                GEX Context at Entry
                              </h4>
                              <div className="grid grid-cols-2 gap-3">
                                <div className="p-3 bg-background-primary rounded-lg">
                                  <div className="text-xs text-text-secondary mb-1">GEX Regime</div>
                                  <div className={`font-semibold ${
                                    trade.gex_regime?.includes('Negative') ? 'text-danger' :
                                    trade.gex_regime?.includes('Positive') ? 'text-success' :
                                    'text-warning'
                                  }`}>
                                    {trade.gex_regime || 'Unknown'}
                                  </div>
                                </div>
                                <div className="p-3 bg-background-primary rounded-lg">
                                  <div className="text-xs text-text-secondary mb-1">Net GEX at Entry</div>
                                  <div className={`font-semibold ${
                                    (trade.entry_net_gex || 0) < 0 ? 'text-danger' : 'text-success'
                                  }`}>
                                    {trade.entry_net_gex
                                      ? `$${(trade.entry_net_gex / 1e9).toFixed(2)}B`
                                      : '—'
                                    }
                                  </div>
                                </div>
                              </div>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Trade Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Trade Log */}
        <div className="lg:col-span-2 card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-text-primary">📋 Trade Activity</h2>
            <button
              onClick={downloadTradeHistory}
              className="btn bg-primary/20 text-primary hover:bg-primary/30 text-sm"
              disabled={tradeLog.length === 0}
            >
              Export CSV
            </button>
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
                          entry.action.includes('BUY') || entry.action.includes('OPEN')
                            ? 'text-success'
                            : entry.action.includes('SELL') || entry.action.includes('CLOSE')
                            ? 'text-danger'
                            : 'text-warning'
                        }`}>
                          {entry.action}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-text-primary text-sm">{entry.details}</td>
                      <td className="py-3 px-4 text-right">
                        <span className={`font-semibold ${
                          entry.pnl >= 0 ? 'text-success' : 'text-danger'
                        }`}>
                          {entry.pnl >= 0 ? '+' : ''}{formatCurrency(entry.pnl)}
                        </span>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="py-8 text-center text-text-secondary">
                      No trade activity yet. Trades will appear here as the autonomous trader executes.
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

      {/* AI Thought Process - Real-Time Logs */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-text-primary">🧠 AI Thought Process - Real-Time</h2>
          <span className="text-xs text-text-secondary">Live updates every scan cycle</span>
        </div>

        <div className="space-y-3 max-h-96 overflow-y-auto">
          {autonomousLogs.length > 0 ? (
            autonomousLogs.map((log, idx) => {
              // Use complete class names to avoid Tailwind purging dynamic classes
              const logTypeConfig: Record<string, { bgClass: string, borderClass: string, textClass: string, icon: string, title: string }> = {
                'PSYCHOLOGY_ANALYSIS': { bgClass: 'from-primary/10', borderClass: 'border-primary', textClass: 'text-primary', icon: '🔍', title: 'Psychology Scan' },
                'STRIKE_SELECTION': { bgClass: 'from-warning/10', borderClass: 'border-warning', textClass: 'text-warning', icon: '🎯', title: 'AI Strike Selection' },
                'POSITION_SIZING': { bgClass: 'from-success/10', borderClass: 'border-success', textClass: 'text-success', icon: '💰', title: 'Position Sizing' },
                'AI_EVALUATION': { bgClass: 'from-blue-500/10', borderClass: 'border-blue-500', textClass: 'text-blue-500', icon: '🤖', title: 'ML Pattern Prediction' },
                'RISK_CHECK': { bgClass: 'from-green-500/10', borderClass: 'border-green-500', textClass: 'text-green-500', icon: '✅', title: 'Risk Manager' },
                'TRADE_DECISION': { bgClass: 'from-purple-500/10', borderClass: 'border-purple-500', textClass: 'text-purple-500', icon: '⚡', title: 'Trade Decision' }
              }
              const config = logTypeConfig[log.log_type] || { bgClass: 'from-primary/10', borderClass: 'border-primary', textClass: 'text-primary', icon: '📝', title: log.log_type }

              return (
                <div key={idx} className={`p-4 bg-gradient-to-r ${config.bgClass} to-transparent rounded-lg border-l-4 ${config.borderClass}`}>
                  <div className="flex items-start gap-3">
                    <span className="text-xs text-text-muted">{formatTime(log.timestamp)}</span>
                    <div className="flex-1">
                      <p className={`text-sm font-semibold ${config.textClass} mb-1`}>{config.icon} {config.title}</p>
                      <p className="text-text-secondary text-sm">
                        {log.log_type === 'PSYCHOLOGY_ANALYSIS' && `Pattern: ${log.pattern_detected || 'N/A'} | Confidence: ${log.confidence_score || 0}% | Symbol: ${log.symbol || 'SPY'}`}
                        {log.log_type === 'STRIKE_SELECTION' && `Strike: $${log.strike_chosen} | ${log.strike_selection_reason || 'Optimizing delta positioning'}`}
                        {log.log_type === 'POSITION_SIZING' && `Kelly: ${log.kelly_pct || 0}% | Contracts: ${log.contracts || 0} | ${log.sizing_rationale || ''}`}
                        {log.log_type === 'AI_EVALUATION' && `AI Confidence: ${log.ai_confidence || 0}% | ${log.ai_thought_process || 'Evaluating market conditions'}`}
                        {log.log_type === 'RISK_CHECK' && (log.reasoning_summary || 'All risk checks passed')}
                        {log.log_type === 'TRADE_DECISION' && `Action: ${log.action_taken || 'EVALUATING'} | ${log.reasoning_summary || ''}`}
                      </p>
                    </div>
                  </div>
                </div>
              )
            })
          ) : (
            <div className="text-center py-8 text-text-secondary">
              <p>No autonomous trader logs yet. Logs will appear here as the trader analyzes markets.</p>
            </div>
          )}
        </div>

        <div className="mt-4 p-3 bg-primary/10 rounded-lg text-center">
          <button
            onClick={() => alert('Full thought process archive feature coming soon. All logs are stored in the database for historical analysis.')}
            className="text-primary text-sm font-medium hover:underline"
          >
            View Full Thought Process Archive →
          </button>
        </div>
      </div>

      {/* Strategy Performance Comparison Chart */}
      {strategies.length > 0 && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-text-primary">📈 Strategy Performance Comparison</h2>
            <span className="text-xs text-text-secondary">P&L and Win Rate by Strategy</span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* P&L Bar Chart */}
            <div className="bg-background-hover rounded-lg p-4">
              <h3 className="text-sm font-semibold text-text-secondary mb-4">Total P&L by Strategy</h3>
              <div className="space-y-3">
                {strategies
                  .sort((a, b) => b.pnl - a.pnl)
                  .slice(0, 8)
                  .map((strategy) => {
                    const maxPnl = Math.max(...strategies.map(s => Math.abs(s.pnl)), 1)
                    const widthPct = Math.min(Math.abs(strategy.pnl) / maxPnl * 100, 100)

                    return (
                      <div key={strategy.id} className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span className="text-text-secondary truncate max-w-[150px]" title={strategy.name}>
                            {strategy.name}
                          </span>
                          <span className={`font-semibold ${strategy.pnl >= 0 ? 'text-success' : 'text-danger'}`}>
                            {strategy.pnl >= 0 ? '+' : ''}{formatCurrency(strategy.pnl)}
                          </span>
                        </div>
                        <div className="h-4 bg-background-primary rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-500 ${
                              strategy.pnl >= 0 ? 'bg-success' : 'bg-danger'
                            }`}
                            style={{ width: `${widthPct}%` }}
                          />
                        </div>
                      </div>
                    )
                  })}
              </div>
            </div>

            {/* Win Rate Comparison */}
            <div className="bg-background-hover rounded-lg p-4">
              <h3 className="text-sm font-semibold text-text-secondary mb-4">Win Rate by Strategy</h3>
              <div className="space-y-3">
                {strategies
                  .sort((a, b) => b.win_rate - a.win_rate)
                  .slice(0, 8)
                  .map((strategy) => (
                    <div key={strategy.id} className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="text-text-secondary truncate max-w-[150px]" title={strategy.name}>
                          {strategy.name}
                        </span>
                        <span className={`font-semibold ${
                          (strategy.win_rate ?? 0) >= 60 ? 'text-success' :
                          (strategy.win_rate ?? 0) >= 40 ? 'text-warning' :
                          'text-danger'
                        }`}>
                          {(strategy.win_rate ?? 0).toFixed(1)}%
                        </span>
                      </div>
                      <div className="h-4 bg-background-primary rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${
                            (strategy.win_rate ?? 0) >= 60 ? 'bg-success' :
                            (strategy.win_rate ?? 0) >= 40 ? 'bg-warning' :
                            'bg-danger'
                          }`}
                          style={{ width: `${strategy.win_rate ?? 0}%` }}
                        />
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          </div>

          {/* Strategy Summary Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
            <div className="p-3 bg-background-primary rounded-lg text-center">
              <div className="text-xs text-text-secondary mb-1">Total Strategies</div>
              <div className="text-2xl font-bold text-text-primary">{strategies.length}</div>
            </div>
            <div className="p-3 bg-background-primary rounded-lg text-center">
              <div className="text-xs text-text-secondary mb-1">Profitable</div>
              <div className="text-2xl font-bold text-success">
                {strategies.filter(s => s.pnl > 0).length}
              </div>
            </div>
            <div className="p-3 bg-background-primary rounded-lg text-center">
              <div className="text-xs text-text-secondary mb-1">Avg Win Rate</div>
              <div className="text-2xl font-bold text-primary">
                {strategies.length > 0 ? (strategies.reduce((acc, s) => acc + s.win_rate, 0) / strategies.length).toFixed(1) : 0}%
              </div>
            </div>
            <div className="p-3 bg-background-primary rounded-lg text-center">
              <div className="text-xs text-text-secondary mb-1">Total P&L</div>
              <div className={`text-2xl font-bold ${strategies.reduce((acc, s) => acc + s.pnl, 0) >= 0 ? 'text-success' : 'text-danger'}`}>
                {formatCurrency(strategies.reduce((acc, s) => acc + s.pnl, 0))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Strategy Competition Leaderboard */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-text-primary">🏆 Strategy Competition Leaderboard</h2>
          <span className="text-xs text-text-secondary">8 strategies competing with equal capital</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-3 px-4 text-text-secondary font-medium">Rank</th>
                <th className="text-left py-3 px-4 text-text-secondary font-medium">Strategy</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium">Return %</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium">Win Rate</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium">Trades</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium">Sharpe</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium">P&L</th>
              </tr>
            </thead>
            <tbody>
              {competitionLeaderboard.length > 0 ? (
                competitionLeaderboard.map((strategy, idx) => {
                  const rankEmoji = idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : (idx + 1).toString()
                  const returnPct = ((strategy.current_capital - strategy.starting_capital) / strategy.starting_capital * 100).toFixed(1)
                  const isPositive = parseFloat(returnPct) >= 0

                  return (
                    <tr key={strategy.strategy_id} className={`border-b border-border/50 hover:bg-background-hover transition-colors ${idx === 0 ? 'bg-warning/5' : ''}`}>
                      <td className={`py-3 px-4 font-bold ${idx === 0 ? 'text-warning' : 'text-text-secondary'}`}>{rankEmoji} {idx + 1}</td>
                      <td className="py-3 px-4 text-text-primary font-semibold">{strategy.strategy_name}</td>
                      <td className={`py-3 px-4 text-right font-bold ${isPositive ? 'text-success' : 'text-danger'}`}>
                        {isPositive ? '+' : ''}{returnPct}%
                      </td>
                      <td className="py-3 px-4 text-right text-text-primary">{(strategy.win_rate * 100).toFixed(0)}%</td>
                      <td className="py-3 px-4 text-right text-text-primary">{strategy.total_trades}</td>
                      <td className="py-3 px-4 text-right text-text-primary">{strategy.sharpe_ratio?.toFixed(2) || '0.00'}</td>
                      <td className={`py-3 px-4 text-right font-semibold ${isPositive ? 'text-success' : 'text-danger'}`}>
                        {isPositive ? '+' : ''}{formatCurrency(strategy.current_capital - strategy.starting_capital)}
                      </td>
                    </tr>
                  )
                })
              ) : (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-text-secondary">
                    No competition data yet. Strategies will appear here as trades execute.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="mt-4 text-center">
          <button
            onClick={() => alert('Full strategy competition leaderboard with detailed analytics coming soon. Track performance over time and compare strategies head-to-head.')}
            className="text-primary text-sm font-medium hover:underline"
          >
            View Full Leaderboard & Strategy Details →
          </button>
        </div>
      </div>

      {/* Backtest Results Dashboard */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-text-primary">📊 Pattern Backtest Results</h2>
          <div className="flex items-center gap-2">
            <span className={`text-xs px-2 py-1 rounded ${
              backtestDataSource === 'backtest' ? 'bg-success/20 text-success' :
              backtestDataSource === 'live_trades' ? 'bg-primary/20 text-primary' :
              'bg-background-hover text-text-secondary'
            }`}>
              {backtestDataSource === 'backtest' ? '✓ Historical Backtest Data' :
               backtestDataSource === 'live_trades' ? '📈 Live Trading Results' :
               'No Data'}
            </span>
            <span className="text-xs text-text-secondary">Last 90 days</span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          {backtestResults.length > 0 ? (
            <>
              {/* Best Pattern by Win Rate */}
              {backtestResults[0] && (
                <div className="p-4 bg-success/10 rounded-lg border border-success/20">
                  <p className="text-text-secondary text-sm mb-1">Best Pattern</p>
                  <p className="text-text-primary font-bold text-lg">{backtestResults[0].pattern}</p>
                  <p className="text-success font-semibold text-sm mt-1">
                    Win Rate: {backtestResults[0].win_rate?.toFixed(0)}% | Expectancy: {(backtestResults[0].expectancy || 0) > 0 ? '+' : ''}{backtestResults[0].expectancy?.toFixed(2)}%
                  </p>
                </div>
              )}

              {/* Most Accurate (highest win rate) */}
              {backtestResults[1] && (
                <div className="p-4 bg-primary/10 rounded-lg border border-primary/20">
                  <p className="text-text-secondary text-sm mb-1">Most Accurate</p>
                  <p className="text-text-primary font-bold text-lg">{backtestResults[1].pattern}</p>
                  <p className="text-primary font-semibold text-sm mt-1">
                    Win Rate: {backtestResults[1].win_rate?.toFixed(0)}% | Signals: {backtestResults[1].total_signals}
                  </p>
                </div>
              )}

              {/* Highest Return (best Sharpe) */}
              {backtestResults[2] && (
                <div className="p-4 bg-warning/10 rounded-lg border border-warning/20">
                  <p className="text-text-secondary text-sm mb-1">Highest Return</p>
                  <p className="text-text-primary font-bold text-lg">{backtestResults[2].pattern}</p>
                  <p className="text-warning font-semibold text-sm mt-1">
                    Avg Win: {(backtestResults[2].avg_profit_pct || 0) > 0 ? '+' : ''}{backtestResults[2].avg_profit_pct?.toFixed(2)}% | Sharpe: {backtestResults[2].sharpe_ratio?.toFixed(2)}
                  </p>
                </div>
              )}
            </>
          ) : (
            <div className="col-span-3 text-center py-8 text-text-secondary">
              <p>No backtest data yet. Run backtests to see pattern performance.</p>
            </div>
          )}
        </div>

        <div className="flex items-center justify-center gap-4">
          <button
            onClick={async () => {
              setBacktestRefreshing(true)
              try {
                const res = await apiClient.runAndSaveBacktests(90)
                if (res.data.success) {
                  // Refresh the backtest data
                  const backtestsRes = await apiClient.getAllPatternBacktests(90)
                  if (backtestsRes.data.success) {
                    setBacktestResults(backtestsRes.data.data || [])
                    setBacktestDataSource(backtestsRes.data.data_source || 'backtest')
                  }
                  alert(`Backtest complete! ${res.data.patterns_with_data} patterns saved to database.`)
                }
              } catch (error) {
                logger.error('Error running backtest:', error)
                alert('Error running backtest. Check console for details.')
              } finally {
                setBacktestRefreshing(false)
              }
            }}
            disabled={backtestRefreshing}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              backtestRefreshing
                ? 'bg-background-hover text-text-secondary cursor-not-allowed'
                : 'bg-primary text-white hover:bg-primary/80'
            }`}
          >
            {backtestRefreshing ? '🔄 Running Backtest...' : '🔄 Run & Save Backtests'}
          </button>
          <button
            onClick={() => alert('Complete backtest analysis with detailed pattern breakdowns coming soon. Analyze win rates, expectancy, and optimal entry conditions.')}
            className="text-primary text-sm font-medium hover:underline"
          >
            View Complete Analysis →
          </button>
        </div>
      </div>

      {/* Liberation & False Floor Analysis */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Liberation Accuracy */}
        <div className="card">
          <h2 className="text-lg font-semibold text-text-primary mb-4">🔓 Liberation Setup Accuracy</h2>
          {liberationAccuracy ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 bg-success/10 rounded-lg border border-success/20">
                  <p className="text-text-secondary text-sm">Accuracy Rate</p>
                  <p className="text-2xl font-bold text-success">{liberationAccuracy.accuracy_pct?.toFixed(1) || 0}%</p>
                </div>
                <div className="p-3 bg-primary/10 rounded-lg border border-primary/20">
                  <p className="text-text-secondary text-sm">Total Signals</p>
                  <p className="text-2xl font-bold text-primary">{liberationAccuracy.total_liberation_signals || 0}</p>
                </div>
              </div>
              <div className="p-3 bg-background-hover rounded-lg">
                <div className="flex justify-between text-sm">
                  <span className="text-text-secondary">Successful Liberations</span>
                  <span className="text-success font-semibold">{liberationAccuracy.successful_liberations || 0}</span>
                </div>
                <div className="flex justify-between text-sm mt-2">
                  <span className="text-text-secondary">Avg Move After Liberation</span>
                  <span className={`font-semibold ${(liberationAccuracy.avg_move_after_liberation_pct || 0) > 0 ? 'text-success' : 'text-danger'}`}>
                    {(liberationAccuracy.avg_move_after_liberation_pct || 0) > 0 ? '+' : ''}{liberationAccuracy.avg_move_after_liberation_pct?.toFixed(2) || 0}%
                  </span>
                </div>
                <div className="flex justify-between text-sm mt-2">
                  <span className="text-text-secondary">Avg Confidence</span>
                  <span className="text-text-primary font-semibold">{liberationAccuracy.avg_confidence?.toFixed(0) || 0}%</span>
                </div>
              </div>
            </div>
          ) : (
            <p className="text-text-secondary text-center py-4">No liberation data available</p>
          )}
        </div>

        {/* False Floor Effectiveness */}
        <div className="card">
          <h2 className="text-lg font-semibold text-text-primary mb-4">🛡️ False Floor Detection</h2>
          {falseFloorEffectiveness ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-4">
                <div className={`p-3 rounded-lg border ${
                  falseFloorEffectiveness.effectiveness === 'GOOD'
                    ? 'bg-success/10 border-success/20'
                    : 'bg-warning/10 border-warning/20'
                }`}>
                  <p className="text-text-secondary text-sm">Effectiveness</p>
                  <p className={`text-2xl font-bold ${
                    falseFloorEffectiveness.effectiveness === 'GOOD' ? 'text-success' : 'text-warning'
                  }`}>
                    {falseFloorEffectiveness.effectiveness || 'N/A'}
                  </p>
                </div>
                <div className="p-3 bg-primary/10 rounded-lg border border-primary/20">
                  <p className="text-text-secondary text-sm">Detections</p>
                  <p className="text-2xl font-bold text-primary">{falseFloorEffectiveness.total_false_floor_detections || 0}</p>
                </div>
              </div>
              <div className="p-3 bg-background-hover rounded-lg">
                <div className="flex justify-between text-sm">
                  <span className="text-text-secondary">Bad Shorts Avoided</span>
                  <span className="text-success font-semibold">{falseFloorEffectiveness.avoided_bad_short_trades || 0}</span>
                </div>
                <div className="flex justify-between text-sm mt-2">
                  <span className="text-text-secondary">Avg Price Move After</span>
                  <span className={`font-semibold ${(falseFloorEffectiveness.avg_price_move_pct || 0) > 0 ? 'text-success' : 'text-danger'}`}>
                    {(falseFloorEffectiveness.avg_price_move_pct || 0) > 0 ? '+' : ''}{falseFloorEffectiveness.avg_price_move_pct?.toFixed(2) || 0}%
                  </span>
                </div>
              </div>
              <p className="text-xs text-text-secondary">
                False floor detection helps avoid shorting into support levels that look like breakdowns but are actually accumulation zones.
              </p>
            </div>
          ) : (
            <p className="text-text-secondary text-center py-4">No false floor data available</p>
          )}
        </div>
      </div>

      {/* Risk Management Dashboard */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <h2 className="text-lg font-semibold text-text-primary mb-4">🛡️ Risk Management Status</h2>
          {riskStatus ? (
            <div className="space-y-3">
              {/* Max Drawdown */}
              <div className="p-3 bg-background-hover rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-text-secondary text-sm">Max Drawdown ({riskStatus.limits?.max_drawdown || 15}% limit)</span>
                  <span className={`font-semibold ${
                    (riskStatus.current_drawdown_pct || 0) < (riskStatus.limits?.max_drawdown || 15) * 0.7 ? 'text-success' :
                    (riskStatus.current_drawdown_pct || 0) < (riskStatus.limits?.max_drawdown || 15) ? 'text-warning' :
                    'text-danger'
                  }`}>
                    {riskStatus.current_drawdown_pct?.toFixed(1) || 0}%
                  </span>
                </div>
                <div className="w-full bg-background-primary rounded-full h-2">
                  <div className={`h-2 rounded-full ${
                    (riskStatus.current_drawdown_pct || 0) < (riskStatus.limits?.max_drawdown || 15) * 0.7 ? 'bg-success' :
                    (riskStatus.current_drawdown_pct || 0) < (riskStatus.limits?.max_drawdown || 15) ? 'bg-warning' :
                    'bg-danger'
                  }`} style={{ width: `${Math.min(((riskStatus.current_drawdown_pct || 0) / (riskStatus.limits?.max_drawdown || 15)) * 100, 100)}%` }}></div>
                </div>
              </div>

              {/* Daily Loss */}
              <div className="p-3 bg-background-hover rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-text-secondary text-sm">Daily Loss Limit ({riskStatus.limits?.daily_loss || 5}% limit)</span>
                  <span className={`font-semibold ${
                    (riskStatus.daily_loss_pct || 0) < (riskStatus.limits?.daily_loss || 5) * 0.7 ? 'text-success' :
                    (riskStatus.daily_loss_pct || 0) < (riskStatus.limits?.daily_loss || 5) ? 'text-warning' :
                    'text-danger'
                  }`}>
                    {riskStatus.daily_loss_pct?.toFixed(1) || 0}%
                  </span>
                </div>
                <div className="w-full bg-background-primary rounded-full h-2">
                  <div className={`h-2 rounded-full ${
                    (riskStatus.daily_loss_pct || 0) < (riskStatus.limits?.daily_loss || 5) * 0.7 ? 'bg-success' :
                    (riskStatus.daily_loss_pct || 0) < (riskStatus.limits?.daily_loss || 5) ? 'bg-warning' :
                    'bg-danger'
                  }`} style={{ width: `${Math.min(((riskStatus.daily_loss_pct || 0) / (riskStatus.limits?.daily_loss || 5)) * 100, 100)}%` }}></div>
                </div>
              </div>

              {/* Position Size */}
              <div className="p-3 bg-background-hover rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-text-secondary text-sm">Position Size ({riskStatus.limits?.position_size || 20}% limit)</span>
                  <span className={`font-semibold ${
                    (riskStatus.position_size_pct || 0) < (riskStatus.limits?.position_size || 20) * 0.7 ? 'text-success' :
                    (riskStatus.position_size_pct || 0) < (riskStatus.limits?.position_size || 20) ? 'text-warning' :
                    'text-danger'
                  }`}>
                    {riskStatus.position_size_pct?.toFixed(1) || 0}%
                  </span>
                </div>
                <div className="w-full bg-background-primary rounded-full h-2">
                  <div className={`h-2 rounded-full ${
                    (riskStatus.position_size_pct || 0) < (riskStatus.limits?.position_size || 20) * 0.7 ? 'bg-success' :
                    (riskStatus.position_size_pct || 0) < (riskStatus.limits?.position_size || 20) ? 'bg-warning' :
                    'bg-danger'
                  }`} style={{ width: `${Math.min(((riskStatus.position_size_pct || 0) / (riskStatus.limits?.position_size || 20)) * 100, 100)}%` }}></div>
                </div>
              </div>

              {/* Correlation */}
              <div className="p-3 bg-background-hover rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-text-secondary text-sm">Correlation Exposure ({riskStatus.limits?.correlation || 50}% limit)</span>
                  <span className={`font-semibold ${
                    (riskStatus.correlation_pct || 0) < (riskStatus.limits?.correlation || 50) * 0.7 ? 'text-success' :
                    (riskStatus.correlation_pct || 0) < (riskStatus.limits?.correlation || 50) ? 'text-warning' :
                    'text-danger'
                  }`}>
                    {riskStatus.correlation_pct?.toFixed(1) || 0}%
                  </span>
                </div>
                <div className="w-full bg-background-primary rounded-full h-2">
                  <div className={`h-2 rounded-full ${
                    (riskStatus.correlation_pct || 0) < (riskStatus.limits?.correlation || 50) * 0.7 ? 'bg-success' :
                    (riskStatus.correlation_pct || 0) < (riskStatus.limits?.correlation || 50) ? 'bg-warning' :
                    'bg-danger'
                  }`} style={{ width: `${Math.min(((riskStatus.correlation_pct || 0) / (riskStatus.limits?.correlation || 50)) * 100, 100)}%` }}></div>
                </div>
              </div>

              {/* Overall Status */}
              <div className={`mt-4 p-3 border rounded-lg text-center ${
                (riskStatus.status?.max_drawdown === 'HEALTHY' &&
                 riskStatus.status?.daily_loss === 'HEALTHY' &&
                 riskStatus.status?.position_size === 'HEALTHY' &&
                 riskStatus.status?.correlation === 'HEALTHY')
                  ? 'bg-success/10 border-success/20'
                  : 'bg-danger/10 border-danger/20'
              }`}>
                <p className={`font-semibold text-sm ${
                  (riskStatus.status?.max_drawdown === 'HEALTHY' &&
                   riskStatus.status?.daily_loss === 'HEALTHY' &&
                   riskStatus.status?.position_size === 'HEALTHY' &&
                   riskStatus.status?.correlation === 'HEALTHY')
                    ? 'text-success'
                    : 'text-danger'
                }`}>
                  {(riskStatus.status?.max_drawdown === 'HEALTHY' &&
                    riskStatus.status?.daily_loss === 'HEALTHY' &&
                    riskStatus.status?.position_size === 'HEALTHY' &&
                    riskStatus.status?.correlation === 'HEALTHY')
                    ? '✅ ALL RISK LIMITS HEALTHY'
                    : '⚠️ RISK LIMIT BREACH DETECTED'}
                </p>
              </div>
            </div>
          ) : (
            <div className="text-center py-8 text-text-secondary">
              <p>Loading risk management data...</p>
            </div>
          )}
        </div>

        <div className="card">
          <h2 className="text-lg font-semibold text-text-primary mb-4">Risk Parameters</h2>
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
              <span className="text-text-secondary">Max Position Size (20%)</span>
              <span className="text-text-primary font-semibold">{formatCurrency((performance.starting_capital || 1000000) * 0.20)}</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
              <span className="text-text-secondary">Daily Loss Limit (5%)</span>
              <span className="text-danger font-semibold">-{formatCurrency((performance.starting_capital || 1000000) * 0.05)}</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
              <span className="text-text-secondary">Max Open Positions</span>
              <span className="text-text-primary font-semibold">10</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
              <span className="text-text-secondary">Stop Loss %</span>
              <span className="text-text-primary font-semibold">-20%</span>
            </div>
          </div>
        </div>

        <div className="card">
          <h2 className="text-lg font-semibold text-text-primary mb-4">Performance Stats</h2>
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
              <span className="text-text-secondary">Total Trades</span>
              <span className="text-text-primary font-semibold">{performance.total_trades}</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
              <span className="text-text-secondary">Winning Trades</span>
              <span className="text-success font-semibold">{performance.winning_trades}</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
              <span className="text-text-secondary">Losing Trades</span>
              <span className="text-danger font-semibold">{performance.losing_trades}</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
              <span className="text-text-secondary">Max Drawdown</span>
              <span className="text-danger font-semibold">{performance.max_drawdown}%</span>
            </div>
          </div>
        </div>
      </div>
          </div>
        </div>
      </main>
    </div>
  )
}
