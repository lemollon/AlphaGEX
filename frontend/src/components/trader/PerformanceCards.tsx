'use client'

import { DollarSign, Target, TrendingUp, TrendingDown, Activity, AlertTriangle } from 'lucide-react'
import { Performance, formatCurrency, formatPercent } from './types'

interface PerformanceCardsProps {
  performance: Performance
  wsConnected: boolean
  lastDataFetch: Date | null
}

export default function PerformanceCards({ performance, wsConnected, lastDataFetch }: PerformanceCardsProps) {
  return (
    <>
      {/* Data Source Indicator */}
      <div className="mb-4 flex items-center justify-between text-xs text-text-muted">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-success animate-pulse' : 'bg-warning'}`} />
          <span>{wsConnected ? 'Live WebSocket' : 'REST API Fallback'}</span>
        </div>
        {lastDataFetch && (
          <span>
            Data last updated: {lastDataFetch.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
        )}
      </div>

      {/* Performance Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {/* Total P&L */}
        <div className="card">
          <div className="flex items-center justify-between mb-2">
            <span className="text-text-secondary text-sm">Total P&L</span>
            <DollarSign className={`w-5 h-5 ${performance.total_pnl >= 0 ? 'text-success' : 'text-danger'}`} />
          </div>
          <p className={`text-2xl font-bold ${performance.total_pnl >= 0 ? 'text-success' : 'text-danger'}`}>
            {performance.total_pnl >= 0 ? '+' : ''}{formatCurrency(performance.total_pnl)}
          </p>
          <p className="text-xs text-text-muted mt-1">
            Realized: {formatCurrency(performance.realized_pnl)} | Unrealized: {formatCurrency(performance.unrealized_pnl)}
          </p>
        </div>

        {/* Today's P&L */}
        <div className="card">
          <div className="flex items-center justify-between mb-2">
            <span className="text-text-secondary text-sm">Today's P&L</span>
            <Activity className={`w-5 h-5 ${performance.today_pnl >= 0 ? 'text-success' : 'text-danger'}`} />
          </div>
          <p className={`text-2xl font-bold ${performance.today_pnl >= 0 ? 'text-success' : 'text-danger'}`}>
            {performance.today_pnl >= 0 ? '+' : ''}{formatCurrency(performance.today_pnl)}
          </p>
        </div>

        {/* Win Rate */}
        <div className="card">
          <div className="flex items-center justify-between mb-2">
            <span className="text-text-secondary text-sm">Win Rate</span>
            <Target className="w-5 h-5 text-primary" />
          </div>
          <p className="text-2xl font-bold text-text-primary">
            {performance.win_rate.toFixed(1)}%
          </p>
          <p className="text-xs text-text-muted mt-1">
            {performance.winning_trades}W / {performance.losing_trades}L
          </p>
        </div>

        {/* Return */}
        <div className="card">
          <div className="flex items-center justify-between mb-2">
            <span className="text-text-secondary text-sm">Return</span>
            {performance.return_pct >= 0 ? (
              <TrendingUp className="w-5 h-5 text-success" />
            ) : (
              <TrendingDown className="w-5 h-5 text-danger" />
            )}
          </div>
          <p className={`text-2xl font-bold ${performance.return_pct >= 0 ? 'text-success' : 'text-danger'}`}>
            {formatPercent(performance.return_pct)}
          </p>
          <p className="text-xs text-text-muted mt-1">
            {formatCurrency(performance.starting_capital)} → {formatCurrency(performance.current_value)}
          </p>
        </div>
      </div>

      {/* Secondary Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div className="card p-4">
          <p className="text-text-muted text-xs mb-1">Sharpe Ratio</p>
          <p className={`text-lg font-bold ${performance.sharpe_ratio >= 1 ? 'text-success' : performance.sharpe_ratio >= 0 ? 'text-warning' : 'text-danger'}`}>
            {performance.sharpe_ratio.toFixed(2)}
          </p>
        </div>
        <div className="card p-4">
          <p className="text-text-muted text-xs mb-1">Max Drawdown</p>
          <p className="text-lg font-bold text-danger">
            {formatPercent(-Math.abs(performance.max_drawdown))}
          </p>
        </div>
        <div className="card p-4">
          <p className="text-text-muted text-xs mb-1">Total Trades</p>
          <p className="text-lg font-bold text-text-primary">
            {performance.total_trades}
          </p>
        </div>
        <div className="card p-4">
          <p className="text-text-muted text-xs mb-1">Account Value</p>
          <p className="text-lg font-bold text-primary">
            {formatCurrency(performance.current_value)}
          </p>
        </div>
      </div>
    </>
  )
}
