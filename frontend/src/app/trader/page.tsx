'use client'

import { useState, useEffect } from 'react'
import { Bot, Play, Pause, Square, Settings, TrendingUp, TrendingDown, Activity, DollarSign, Target, AlertTriangle, CheckCircle, XCircle, Clock } from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'

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
}

interface Strategy {
  id: string
  name: string
  status: 'active' | 'paused' | 'stopped'
  win_rate: number
  trades_today: number
  pnl: number
  last_signal: string
}

interface Trade {
  id: string
  timestamp: string
  symbol: string
  action: 'BUY' | 'SELL' | 'LONG_STRADDLE' | 'IRON_CONDOR' | string
  type: 'CALL' | 'PUT' | 'straddle' | 'iron_condor' | string
  strike: number
  quantity: number
  price: number
  status: 'filled' | 'pending' | 'cancelled'
  pnl?: number
  strategy?: string
  entry_bid?: number
  entry_ask?: number
  entry_spot_price?: number
  current_price?: number
  current_spot_price?: number
  trade_reasoning?: string
}

interface TradeLogEntry {
  date: string
  time: string
  action: string
  details: string
  pnl: number
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
    max_drawdown: 0
  })

  const [strategies, setStrategies] = useState<Strategy[]>([])

  const [recentTrades, setRecentTrades] = useState<Trade[]>([])
  const [expandedTradeId, setExpandedTradeId] = useState<string | null>(null)

  // Trade Activity Log
  const [tradeLog, setTradeLog] = useState<TradeLogEntry[]>([])

  // Autonomous trader advanced features state
  const [autonomousLogs, setAutonomousLogs] = useState<any[]>([])
  const [competitionLeaderboard, setCompetitionLeaderboard] = useState<any[]>([])
  const [backtestResults, setBacktestResults] = useState<any[]>([])
  const [riskStatus, setRiskStatus] = useState<any>(null)

  // Calculate best and worst trades
  const bestTrade = tradeLog.length > 0
    ? Math.max(...tradeLog.map(t => t.pnl))
    : 0
  const worstTrade = tradeLog.length > 0
    ? Math.min(...tradeLog.map(t => t.pnl))
    : 0

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
          apiClient.getAutonomousLogs({ limit: 20 }).catch(() => ({ data: { success: false, data: [] } })),
          apiClient.getCompetitionLeaderboard().catch(() => ({ data: { success: false, data: [] } })),
          apiClient.getAllPatternBacktests(90).catch(() => ({ data: { success: false, data: [] } })),
          apiClient.getRiskStatus().catch(() => ({ data: { success: false, data: null } })),
          apiClient.getTradeLog()
        ])

        // Extract results (fulfilled promises only)
        const [statusRes, perfRes, tradesRes, strategiesRes, logsRes, leaderboardRes, backtestsRes, riskRes, tradeLogRes] = results.map(result =>
          result.status === 'fulfilled' ? result.value : { data: { success: false, data: null } }
        )

        if (statusRes.data.success) {
          setTraderStatus(statusRes.data.data)
        }

        if (perfRes.data.success) {
          setPerformance(perfRes.data.data)
        }

        // Set REAL strategies from database
        if (strategiesRes.data.success && strategiesRes.data.data.length > 0) {
          const mappedStrategies = strategiesRes.data.data.map((strat: any, idx: number) => ({
            id: idx.toString(),
            name: strat.name,
            status: 'active',
            win_rate: strat.win_rate,
            trades_today: 0,  // TODO: Get from API
            pnl: strat.total_pnl,
            last_signal: strat.last_trade_date
          }))
          setStrategies(mappedStrategies)
        }

        if (tradesRes.data.success && tradesRes.data.data.length > 0) {
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
            status: trade.status === 'OPEN' ? 'filled' : 'filled',
            pnl: trade.realized_pnl || trade.unrealized_pnl || 0,
            strategy: trade.strategy,
            entry_bid: trade.entry_bid,
            entry_ask: trade.entry_ask,
            entry_spot_price: trade.entry_spot_price,
            current_price: trade.current_price,
            current_spot_price: trade.current_spot_price,
            trade_reasoning: trade.trade_reasoning
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
        }

        if (riskRes.data.success) {
          setRiskStatus(riskRes.data.data)
        }

        if (tradeLogRes.data.success) {
          setTradeLog(tradeLogRes.data.data || [])
        }
      } catch (error) {
        console.error('Error fetching trader data:', error)
        // Keep default/empty state on error
      } finally {
        setLoading(false)
      }
    }

    fetchData()

    // No auto-refresh - protects API rate limit (20 calls/min shared across all users)
    // Trader background worker updates independently - UI will refresh when user navigates
  }, [])

  // Trader runs automatically as a background worker - no manual control needed
  // It checks every 5 minutes ALL DAY during market hours (8:30 AM - 3:00 PM CT)
  // GUARANTEED: MINIMUM one trade per day (multi-level fallback system)
  // State is persisted in database, so it remembers everything across restarts

  const handleToggleMode = () => {
    setTraderStatus(prev => ({
      ...prev,
      mode: prev.mode === 'paper' ? 'live' : 'paper'
    }))
  }

  const handleToggleStrategy = (strategyId: string) => {
    setStrategies(prev =>
      prev.map(s =>
        s.id === strategyId
          ? { ...s, status: s.status === 'active' ? 'paused' : 'active' }
          : s
      )
    )
  }

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(value)
  }

  const formatTime = (isoString: string) => {
    return new Intl.DateTimeFormat('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
      timeZone: 'America/Chicago'
    }).format(new Date(isoString))
  }

  const formatTradeTime = (dateStr?: string, timeStr?: string) => {
    if (dateStr && timeStr) {
      const datetime = `${dateStr}T${timeStr}`
      return new Intl.DateTimeFormat('en-US', {
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
        timeZone: 'America/Chicago'
      }).format(new Date(datetime))
    }
    return timeStr || dateStr || 'N/A'
  }

  const formatUptime = (seconds: number) => {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    return `${hours}h ${minutes}m`
  }

  const downloadTradeHistory = () => {
    if (tradeLog.length === 0) {
      alert('No trade history to export')
      return
    }

    const csvContent = [
      ['Date/Time (Central)', 'Action', 'Details', 'P&L'],
      ...tradeLog.map(trade => {
        const datetime = trade.date && trade.time ? `${trade.date}T${trade.time}` : null
        const formattedDateTime = datetime
          ? new Date(datetime).toLocaleString('en-US', { timeZone: 'America/Chicago' })
          : 'Invalid Date'

        return [
          formattedDateTime,
          trade.action,
          trade.details,
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
    a.download = `trade-history-${new Date().toISOString().split('T')[0]}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
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
          <h1 className="text-3xl font-bold text-text-primary">Autonomous Trader</h1>
          <p className="text-text-secondary mt-1">Automated trading based on gamma exposure signals</p>
        </div>
        <div className="flex items-center gap-3">
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
          <h2 className="text-xl font-semibold text-text-primary">🤖 Autonomous Trader - Live Status</h2>
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

      {/* Performance Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-text-secondary text-sm">Total P&L</p>
              <p className={`text-2xl font-bold mt-1 ${
                performance.total_pnl >= 0 ? 'text-success' : 'text-danger'
              }`}>
                {formatCurrency(performance.total_pnl)}
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
                {formatCurrency(performance.today_pnl)}
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
                {performance.win_rate.toFixed(1)}%
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
                {performance.sharpe_ratio.toFixed(2)}
              </p>
            </div>
            <TrendingUp className="text-primary w-8 h-8" />
          </div>
        </div>
      </div>

      {/* Strategies */}
      <div className="card">
        <h2 className="text-xl font-semibold text-text-primary mb-4">Active Strategies</h2>
        <div className="space-y-3">
          {strategies.map((strategy) => (
            <div
              key={strategy.id}
              className="p-4 bg-background-hover rounded-lg flex items-center justify-between"
            >
              <div className="flex items-center gap-4 flex-1">
                <div className={`w-3 h-3 rounded-full ${
                  strategy.status === 'active' ? 'bg-success animate-pulse' :
                  strategy.status === 'paused' ? 'bg-warning' :
                  'bg-text-muted'
                }`} />

                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-text-primary font-semibold">{strategy.name}</h3>
                    <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                      strategy.status === 'active' ? 'bg-success/20 text-success' :
                      strategy.status === 'paused' ? 'bg-warning/20 text-warning' :
                      'bg-text-muted/20 text-text-muted'
                    }`}>
                      {strategy.status.toUpperCase()}
                    </span>
                  </div>

                  <div className="flex items-center gap-6 text-sm">
                    <div>
                      <span className="text-text-muted">Win Rate:</span>
                      <span className="text-text-primary font-semibold ml-2">{strategy.win_rate}%</span>
                    </div>
                    <div>
                      <span className="text-text-muted">Today:</span>
                      <span className="text-text-primary font-semibold ml-2">{strategy.trades_today} trades</span>
                    </div>
                    <div>
                      <span className="text-text-muted">P&L:</span>
                      <span className={`font-semibold ml-2 ${
                        strategy.pnl >= 0 ? 'text-success' : 'text-danger'
                      }`}>
                        {formatCurrency(strategy.pnl)}
                      </span>
                    </div>
                    <div>
                      <span className="text-text-muted">Last Signal:</span>
                      <span className="text-text-primary font-semibold ml-2">{strategy.last_signal}</span>
                    </div>
                  </div>
                </div>
              </div>

              <button
                onClick={() => handleToggleStrategy(strategy.id)}
                disabled={!traderStatus.is_active}
                className={`btn ${
                  strategy.status === 'active' ? 'bg-warning/20 text-warning hover:bg-warning/30' : 'bg-success/20 text-success hover:bg-success/30'
                } disabled:opacity-50 disabled:cursor-not-allowed`}
              >
                {strategy.status === 'active' ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Recent Trades */}
      <div className="card">
        <h2 className="text-xl font-semibold text-text-primary mb-4">Recent Trades</h2>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-3 px-4 text-text-secondary font-medium">Time</th>
                <th className="text-left py-3 px-4 text-text-secondary font-medium">Strategy</th>
                <th className="text-left py-3 px-4 text-text-secondary font-medium">Symbol</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium">Entry</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium">Current</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium">Status</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium">P&L</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {recentTrades.map((trade) => (
                <>
                  <tr
                    key={trade.id}
                    className="border-b border-border/50 hover:bg-background-hover transition-colors cursor-pointer"
                    onClick={() => setExpandedTradeId(expandedTradeId === trade.id ? null : trade.id)}
                  >
                    <td className="py-3 px-4 text-text-secondary text-sm">{formatTime(trade.timestamp)}</td>
                    <td className="py-3 px-4">
                      <div className="font-semibold text-text-primary text-sm">{trade.strategy || trade.action}</div>
                      <div className="text-xs text-text-secondary">{trade.type}</div>
                    </td>
                    <td className="py-3 px-4 text-text-primary font-medium">{trade.symbol}</td>
                    <td className="py-3 px-4 text-right">
                      <div className="text-text-primary font-semibold">{formatCurrency(Math.abs(trade.price))}</div>
                      <div className="text-xs text-text-secondary">@ {formatCurrency(trade.entry_spot_price || 0)}</div>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="text-text-primary font-semibold">{formatCurrency(Math.abs(trade.current_price || trade.price))}</div>
                      <div className="text-xs text-text-secondary">@ {formatCurrency(trade.current_spot_price || trade.entry_spot_price || 0)}</div>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <span className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full font-medium ${
                        trade.status === 'filled' ? 'bg-success/20 text-success' :
                        trade.status === 'pending' ? 'bg-warning/20 text-warning' :
                        'bg-danger/20 text-danger'
                      }`}>
                        {trade.status === 'filled' && <CheckCircle className="w-3 h-3" />}
                        {trade.status === 'pending' && <Clock className="w-3 h-3" />}
                        {trade.status === 'cancelled' && <XCircle className="w-3 h-3" />}
                        {trade.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right">
                      {trade.pnl !== undefined && (
                        <div>
                          <div className={`font-bold text-lg ${
                            trade.pnl >= 0 ? 'text-success' : 'text-danger'
                          }`}>
                            {trade.pnl >= 0 ? '+' : ''}{formatCurrency(trade.pnl)}
                          </div>
                          <div className="text-xs text-text-secondary">
                            {((trade.pnl / Math.abs(trade.price)) * 100).toFixed(1)}%
                          </div>
                        </div>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button className="text-primary hover:text-primary/80">
                        {expandedTradeId === trade.id ? '▼' : '▶'}
                      </button>
                    </td>
                  </tr>
                  {expandedTradeId === trade.id && trade.trade_reasoning && (
                    <tr className="bg-background-hover">
                      <td colSpan={8} className="py-4 px-6">
                        <div className="space-y-3">
                          <h4 className="font-semibold text-primary flex items-center gap-2">
                            <Target className="w-4 h-4" />
                            Multi-Leg Position Details
                          </h4>
                          <div className="bg-background-primary p-4 rounded-lg font-mono text-sm whitespace-pre-wrap text-text-secondary">
                            {trade.trade_reasoning}
                          </div>
                          <div className="grid grid-cols-3 gap-4 mt-4">
                            <div className="p-3 bg-background-primary rounded-lg">
                              <div className="text-xs text-text-secondary mb-1">Entry Bid/Ask</div>
                              <div className="text-text-primary font-semibold">${trade.entry_bid?.toFixed(2)} / ${trade.entry_ask?.toFixed(2)}</div>
                            </div>
                            <div className="p-3 bg-background-primary rounded-lg">
                              <div className="text-xs text-text-secondary mb-1">Strike(s)</div>
                              <div className="text-text-primary font-semibold">{formatCurrency(trade.strike)}</div>
                            </div>
                            <div className="p-3 bg-background-primary rounded-lg">
                              <div className="text-xs text-text-secondary mb-1">Contracts</div>
                              <div className="text-text-primary font-semibold">{trade.quantity}</div>
                            </div>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
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
              const logTypeConfig = {
                'PSYCHOLOGY_ANALYSIS': { color: 'primary', icon: '🔍', title: 'Psychology Scan' },
                'STRIKE_SELECTION': { color: 'warning', icon: '🎯', title: 'AI Strike Selection' },
                'POSITION_SIZING': { color: 'success', icon: '💰', title: 'Position Sizing' },
                'AI_EVALUATION': { color: 'blue-500', icon: '🤖', title: 'ML Pattern Prediction' },
                'RISK_CHECK': { color: 'green-500', icon: '✅', title: 'Risk Manager' },
                'TRADE_DECISION': { color: 'purple-500', icon: '⚡', title: 'Trade Decision' }
              }
              const config = logTypeConfig[log.log_type as keyof typeof logTypeConfig] || { color: 'primary', icon: '📝', title: log.log_type }

              return (
                <div key={idx} className={`p-4 bg-gradient-to-r from-${config.color}/10 to-transparent rounded-lg border-l-4 border-${config.color}`}>
                  <div className="flex items-start gap-3">
                    <span className="text-xs text-text-muted">{formatTime(log.timestamp)}</span>
                    <div className="flex-1">
                      <p className={`text-sm font-semibold text-${config.color} mb-1`}>{config.icon} {config.title}</p>
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
          <button className="text-primary text-sm font-medium hover:underline">
            View Full Thought Process Archive →
          </button>
        </div>
      </div>

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
          <button className="text-primary text-sm font-medium hover:underline">
            View Full Leaderboard & Strategy Details →
          </button>
        </div>
      </div>

      {/* Backtest Results Dashboard */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-text-primary">📊 Pattern Backtest Results</h2>
          <span className="text-xs text-text-secondary">Last 90 days validation</span>
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
                    Win Rate: {backtestResults[0].win_rate?.toFixed(0)}% | Expectancy: {backtestResults[0].expectancy > 0 ? '+' : ''}{backtestResults[0].expectancy?.toFixed(2)}%
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
                    Avg Win: {backtestResults[2].avg_profit_pct > 0 ? '+' : ''}{backtestResults[2].avg_profit_pct?.toFixed(2)}% | Sharpe: {backtestResults[2].sharpe_ratio?.toFixed(2)}
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

        <div className="text-center">
          <button className="text-primary text-sm font-medium hover:underline">
            View Complete Backtest Analysis →
          </button>
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
                    riskStatus.current_drawdown_pct < (riskStatus.limits?.max_drawdown || 15) * 0.7 ? 'text-success' :
                    riskStatus.current_drawdown_pct < (riskStatus.limits?.max_drawdown || 15) ? 'text-warning' :
                    'text-danger'
                  }`}>
                    {riskStatus.current_drawdown_pct?.toFixed(1) || 0}%
                  </span>
                </div>
                <div className="w-full bg-background-primary rounded-full h-2">
                  <div className={`h-2 rounded-full ${
                    riskStatus.current_drawdown_pct < (riskStatus.limits?.max_drawdown || 15) * 0.7 ? 'bg-success' :
                    riskStatus.current_drawdown_pct < (riskStatus.limits?.max_drawdown || 15) ? 'bg-warning' :
                    'bg-danger'
                  }`} style={{ width: `${Math.min((riskStatus.current_drawdown_pct / (riskStatus.limits?.max_drawdown || 15)) * 100, 100)}%` }}></div>
                </div>
              </div>

              {/* Daily Loss */}
              <div className="p-3 bg-background-hover rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-text-secondary text-sm">Daily Loss Limit ({riskStatus.limits?.daily_loss || 5}% limit)</span>
                  <span className={`font-semibold ${
                    riskStatus.daily_loss_pct < (riskStatus.limits?.daily_loss || 5) * 0.7 ? 'text-success' :
                    riskStatus.daily_loss_pct < (riskStatus.limits?.daily_loss || 5) ? 'text-warning' :
                    'text-danger'
                  }`}>
                    {riskStatus.daily_loss_pct?.toFixed(1) || 0}%
                  </span>
                </div>
                <div className="w-full bg-background-primary rounded-full h-2">
                  <div className={`h-2 rounded-full ${
                    riskStatus.daily_loss_pct < (riskStatus.limits?.daily_loss || 5) * 0.7 ? 'bg-success' :
                    riskStatus.daily_loss_pct < (riskStatus.limits?.daily_loss || 5) ? 'bg-warning' :
                    'bg-danger'
                  }`} style={{ width: `${Math.min((riskStatus.daily_loss_pct / (riskStatus.limits?.daily_loss || 5)) * 100, 100)}%` }}></div>
                </div>
              </div>

              {/* Position Size */}
              <div className="p-3 bg-background-hover rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-text-secondary text-sm">Position Size ({riskStatus.limits?.position_size || 20}% limit)</span>
                  <span className={`font-semibold ${
                    riskStatus.position_size_pct < (riskStatus.limits?.position_size || 20) * 0.7 ? 'text-success' :
                    riskStatus.position_size_pct < (riskStatus.limits?.position_size || 20) ? 'text-warning' :
                    'text-danger'
                  }`}>
                    {riskStatus.position_size_pct?.toFixed(1) || 0}%
                  </span>
                </div>
                <div className="w-full bg-background-primary rounded-full h-2">
                  <div className={`h-2 rounded-full ${
                    riskStatus.position_size_pct < (riskStatus.limits?.position_size || 20) * 0.7 ? 'bg-success' :
                    riskStatus.position_size_pct < (riskStatus.limits?.position_size || 20) ? 'bg-warning' :
                    'bg-danger'
                  }`} style={{ width: `${Math.min((riskStatus.position_size_pct / (riskStatus.limits?.position_size || 20)) * 100, 100)}%` }}></div>
                </div>
              </div>

              {/* Correlation */}
              <div className="p-3 bg-background-hover rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-text-secondary text-sm">Correlation Exposure ({riskStatus.limits?.correlation || 50}% limit)</span>
                  <span className={`font-semibold ${
                    riskStatus.correlation_pct < (riskStatus.limits?.correlation || 50) * 0.7 ? 'text-success' :
                    riskStatus.correlation_pct < (riskStatus.limits?.correlation || 50) ? 'text-warning' :
                    'text-danger'
                  }`}>
                    {riskStatus.correlation_pct?.toFixed(1) || 0}%
                  </span>
                </div>
                <div className="w-full bg-background-primary rounded-full h-2">
                  <div className={`h-2 rounded-full ${
                    riskStatus.correlation_pct < (riskStatus.limits?.correlation || 50) * 0.7 ? 'bg-success' :
                    riskStatus.correlation_pct < (riskStatus.limits?.correlation || 50) ? 'bg-warning' :
                    'bg-danger'
                  }`} style={{ width: `${Math.min((riskStatus.correlation_pct / (riskStatus.limits?.correlation || 50)) * 100, 100)}%` }}></div>
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
              <span className="text-text-secondary">Max Position Size</span>
              <span className="text-text-primary font-semibold">$5,000</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
              <span className="text-text-secondary">Daily Loss Limit</span>
              <span className="text-danger font-semibold">-$500</span>
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
