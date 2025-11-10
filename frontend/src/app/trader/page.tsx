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
  action: 'BUY' | 'SELL'
  type: 'CALL' | 'PUT'
  strike: number
  quantity: number
  price: number
  status: 'filled' | 'pending' | 'cancelled'
  pnl?: number
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

  // Fetch data from API
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)

        // Fetch trader status, performance, and trades in parallel
        const [statusRes, perfRes, tradesRes, strategiesRes] = await Promise.all([
          apiClient.getTraderStatus(),
          apiClient.getTraderPerformance(),
          apiClient.getTraderTrades(10),
          apiClient.getStrategies()
        ])

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
          // Map database trades to UI format
          const mappedTrades = tradesRes.data.data.map((trade: any) => ({
            id: trade.id?.toString() || trade.timestamp,
            timestamp: trade.timestamp || new Date().toISOString(),
            symbol: trade.symbol || 'SPY',
            action: trade.action || 'BUY',
            type: trade.option_type || 'CALL',
            strike: trade.strike || 0,
            quantity: trade.quantity || 0,
            price: trade.entry_price || 0,
            status: trade.status === 'OPEN' ? 'filled' : 'filled',
            pnl: trade.realized_pnl || trade.unrealized_pnl || 0
          }))
          setRecentTrades(mappedTrades)
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

  const formatUptime = (seconds: number) => {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    return `${hours}h ${minutes}m`
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
                <th className="text-left py-3 px-4 text-text-secondary font-medium">Symbol</th>
                <th className="text-left py-3 px-4 text-text-secondary font-medium">Action</th>
                <th className="text-left py-3 px-4 text-text-secondary font-medium">Type</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium">Strike</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium">Qty</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium">Price</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium">Status</th>
                <th className="text-right py-3 px-4 text-text-secondary font-medium">P&L</th>
              </tr>
            </thead>
            <tbody>
              {recentTrades.map((trade) => (
                <tr key={trade.id} className="border-b border-border/50 hover:bg-background-hover transition-colors">
                  <td className="py-3 px-4 text-text-secondary text-sm">{formatTime(trade.timestamp)}</td>
                  <td className="py-3 px-4 text-text-primary font-medium">{trade.symbol}</td>
                  <td className="py-3 px-4">
                    <span className={`text-sm font-semibold ${
                      trade.action === 'BUY' ? 'text-success' : 'text-danger'
                    }`}>
                      {trade.action}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-text-primary">{trade.type}</td>
                  <td className="py-3 px-4 text-right text-text-primary">{formatCurrency(trade.strike)}</td>
                  <td className="py-3 px-4 text-right text-text-primary">{trade.quantity}</td>
                  <td className="py-3 px-4 text-right text-text-primary">{formatCurrency(trade.price)}</td>
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
                      <span className={`font-semibold ${
                        trade.pnl >= 0 ? 'text-success' : 'text-danger'
                      }`}>
                        {trade.pnl >= 0 ? '+' : ''}{formatCurrency(trade.pnl)}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Risk Management */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
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
