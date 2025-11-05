'use client'

import { useState, useEffect } from 'react'
import { Bot, Play, Pause, Square, Settings, TrendingUp, TrendingDown, Activity, DollarSign, Target, AlertTriangle, CheckCircle, XCircle, Clock } from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'

interface TraderStatus {
  is_active: boolean
  mode: 'paper' | 'live'
  uptime: number
  last_check: string
  strategies_active: number
  total_trades_today: number
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

  const [strategies, setStrategies] = useState<Strategy[]>([
    {
      id: '1',
      name: 'Gamma Squeeze Scanner',
      status: 'active',
      win_rate: 72.5,
      trades_today: 5,
      pnl: 450.50,
      last_signal: '2 min ago'
    },
    {
      id: '2',
      name: 'GEX Reversal',
      status: 'active',
      win_rate: 65.0,
      trades_today: 3,
      pnl: 399.75,
      last_signal: '15 min ago'
    },
    {
      id: '3',
      name: 'Vanna Flow',
      status: 'paused',
      win_rate: 58.3,
      trades_today: 0,
      pnl: 0,
      last_signal: '2 hours ago'
    }
  ])

  const [recentTrades, setRecentTrades] = useState<Trade[]>([])

  // Fetch data from API
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)

        // Fetch trader status, performance, and trades in parallel
        const [statusRes, perfRes, tradesRes] = await Promise.all([
          apiClient.getTraderStatus(),
          apiClient.getTraderPerformance(),
          apiClient.getTraderTrades(10)
        ])

        if (statusRes.data.success) {
          setTraderStatus(statusRes.data.data)
        }

        if (perfRes.data.success) {
          setPerformance(perfRes.data.data)
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

    // Refresh data every 30 seconds
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [])

  const handleToggleTrader = () => {
    setTraderStatus(prev => ({ ...prev, is_active: !prev.is_active }))
  }

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
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
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

      {/* Control Panel */}
      <div className="card">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-text-primary">Control Panel</h2>
          <Settings className="text-primary w-6 h-6" />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-background-hover rounded-lg">
                <div>
                  <p className="text-text-secondary text-sm">Bot Status</p>
                  <p className="text-lg font-semibold text-text-primary mt-1">
                    {traderStatus.is_active ? 'Running' : 'Stopped'}
                  </p>
                </div>
                <div className="flex gap-2">
                  {!traderStatus.is_active ? (
                    <button
                      onClick={handleToggleTrader}
                      className="btn bg-success text-white hover:bg-success/80 flex items-center gap-2"
                    >
                      <Play className="w-4 h-4" />
                      Start
                    </button>
                  ) : (
                    <>
                      <button
                        onClick={handleToggleTrader}
                        className="btn bg-danger text-white hover:bg-danger/80 flex items-center gap-2"
                      >
                        <Square className="w-4 h-4" />
                        Stop
                      </button>
                    </>
                  )}
                </div>
              </div>

              <div className="flex items-center justify-between p-4 bg-background-hover rounded-lg">
                <div>
                  <p className="text-text-secondary text-sm">Trading Mode</p>
                  <p className="text-lg font-semibold text-text-primary mt-1 capitalize">
                    {traderStatus.mode}
                  </p>
                </div>
                <button
                  onClick={handleToggleMode}
                  disabled={traderStatus.is_active}
                  className="btn btn-secondary disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Switch to {traderStatus.mode === 'paper' ? 'Live' : 'Paper'}
                </button>
              </div>
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
              <span className="text-text-secondary">Uptime</span>
              <span className="text-text-primary font-semibold">{formatUptime(traderStatus.uptime)}</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
              <span className="text-text-secondary">Active Strategies</span>
              <span className="text-text-primary font-semibold">{traderStatus.strategies_active}</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
              <span className="text-text-secondary">Trades Today</span>
              <span className="text-text-primary font-semibold">{traderStatus.total_trades_today}</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
              <span className="text-text-secondary">Last Check</span>
              <span className="text-text-primary font-semibold">{formatTime(traderStatus.last_check)}</span>
            </div>
          </div>
        </div>

        {!traderStatus.is_active && (
          <div className="mt-6 p-4 bg-warning/10 border border-warning/20 rounded-lg flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-warning flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-warning font-semibold">Trader is currently stopped</p>
              <p className="text-text-secondary text-sm mt-1">
                Click "Start" to begin automated trading. Make sure you've configured your strategies and risk parameters.
              </p>
            </div>
          </div>
        )}
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
      </main>
    </div>
  )
}
