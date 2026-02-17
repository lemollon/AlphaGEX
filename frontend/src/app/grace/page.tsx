'use client'

import React, { useState, useEffect, useCallback } from 'react'
import {
  Heart, TrendingUp, Activity, DollarSign, Target,
  BarChart3, Shield, Clock, AlertTriangle, CheckCircle2,
  XCircle, RefreshCw, Power, FileText
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'

const API_URL = process.env.NEXT_PUBLIC_API_URL || ''

// ============================================================================
// FETCH HELPER
// ============================================================================

async function fetchApi<T>(endpoint: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_URL}${endpoint}`)
    if (!res.ok) return null
    const json = await res.json()
    return 'data' in json ? json.data : json
  } catch {
    return null
  }
}

// ============================================================================
// INTERFACES
// ============================================================================

interface PaperAccount {
  starting_balance: number
  balance: number
  buying_power: number
  collateral_in_use: number
  total_trades: number
  cumulative_pnl: number
  return_pct: number
  high_water_mark: number
  max_drawdown: number
  is_active: boolean
}

interface PDTStatus {
  day_trades_rolling_5: number
  day_trades_remaining: number
  max_day_trades: number
  trades_today: number
  max_trades_per_day: number
  can_trade: boolean
  reason: string
  next_reset: string | null
  pdt_log: any[]
}

interface BotStatus {
  bot_name: string
  is_active: boolean
  is_paper: boolean
  mode: string
  ticker: string
  dte: number
  last_scan: string | null
  last_scan_result: any
  open_positions: number
  trades_today: number
  max_trades_per_day: number
  profit_target_pct: number
  stop_loss_pct: number
  eod_cutoff: string
  sd_multiplier: number
  spread_width: number
  vix_skip: number
  paper_account: PaperAccount
  pdt: PDTStatus
}

interface PositionMonitor {
  position_id: string
  ticker: string
  expiration: string
  put_short_strike: number
  put_long_strike: number
  call_short_strike: number
  call_long_strike: number
  put_width: number
  call_width: number
  wings_symmetric: boolean
  wings_adjusted: boolean
  contracts: number
  entry_credit: number
  current_cost_to_close: number | null
  profit_target_price: number
  stop_loss_price: number
  pnl_per_contract: number | null
  pnl_total: number | null
  pnl_pct: number | null
  profit_target_pct: number
  stop_loss_pct: number
  eod_cutoff: string
  open_time: string
  collateral_required: number
}

interface Trade {
  position_id: string
  ticker: string
  expiration: string
  put_short_strike: number
  put_long_strike: number
  call_short_strike: number
  call_long_strike: number
  contracts: number
  spread_width: number
  total_credit: number
  close_price: number
  close_reason: string
  realized_pnl: number
  open_time: string
  close_time: string
  wings_adjusted: boolean
  wings_symmetric: boolean
  put_width: number
  call_width: number
}

interface Performance {
  total_trades: number
  wins: number
  losses: number
  win_rate: number
  total_pnl: number
  avg_win: number
  avg_loss: number
  best_trade: number
  worst_trade: number
  starting_capital: number
  current_balance: number
  return_pct: number
}

interface LogEntry {
  timestamp: string
  level: string
  message: string
  details: any
}

// ============================================================================
// HELPER COMPONENTS
// ============================================================================

function formatCurrency(val: number | null | undefined): string {
  if (val == null) return '--'
  return `$${val.toFixed(2)}`
}

function formatPct(val: number | null | undefined): string {
  if (val == null) return '--'
  return `${val.toFixed(1)}%`
}

function formatTime(iso: string | null): string {
  if (!iso) return '--'
  try {
    return new Date(iso).toLocaleString('en-US', {
      timeZone: 'America/New_York',
      month: 'short', day: 'numeric',
      hour: 'numeric', minute: '2-digit',
      hour12: true,
    })
  } catch {
    return iso
  }
}

function PnlBadge({ pnl }: { pnl: number | null | undefined }) {
  if (pnl == null) return <span className="text-text-secondary">--</span>
  const color = pnl > 0 ? 'text-green-400' : pnl < 0 ? 'text-red-400' : 'text-text-secondary'
  const prefix = pnl > 0 ? '+' : ''
  return <span className={`font-mono font-semibold ${color}`}>{prefix}${pnl.toFixed(2)}</span>
}

function WingBadge({ adjusted, putWidth, callWidth }: {
  adjusted: boolean
  putWidth: number
  callWidth: number
}) {
  const symmetric = Math.abs(putWidth - callWidth) < 0.01
  if (symmetric && !adjusted) {
    return (
      <span className="text-xs px-2 py-0.5 rounded bg-green-900/30 text-green-400">
        ${putWidth}/${callWidth} Symmetric
      </span>
    )
  }
  if (adjusted) {
    return (
      <span className="text-xs px-2 py-0.5 rounded bg-yellow-900/30 text-yellow-400">
        ${putWidth}/${callWidth} Adjusted
      </span>
    )
  }
  return (
    <span className="text-xs px-2 py-0.5 rounded bg-red-900/30 text-red-400">
      ${putWidth}/${callWidth} Asymmetric
    </span>
  )
}

// ============================================================================
// PAGE COMPONENT
// ============================================================================

export default function GracePage() {
  const paddingClass = useSidebarPadding()

  const [status, setStatus] = useState<BotStatus | null>(null)
  const [monitor, setMonitor] = useState<PositionMonitor | null>(null)
  const [trades, setTrades] = useState<Trade[]>([])
  const [performance, setPerformance] = useState<Performance | null>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'overview' | 'history' | 'activity'>('overview')

  const fetchData = useCallback(async () => {
    try {
      const [statusData, monitorData, tradesData, perfData, logsData] = await Promise.all([
        fetchApi<BotStatus>('/api/grace/status'),
        fetchApi<PositionMonitor>('/api/grace/position-monitor'),
        fetchApi<Trade[]>('/api/grace/trades'),
        fetchApi<Performance>('/api/grace/performance'),
        fetchApi<LogEntry[]>('/api/grace/logs?limit=50'),
      ])
      setStatus(statusData)
      setMonitor(monitorData)
      setTrades(tradesData || [])
      setPerformance(perfData)
      setLogs(logsData || [])
      setError(null)
    } catch (e: any) {
      setError(e.message || 'Failed to fetch data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 15000)
    return () => clearInterval(interval)
  }, [fetchData])

  const handleToggle = async () => {
    if (!status) return
    try {
      await fetch(`${API_URL}/api/grace/toggle?active=${!status.is_active}`, { method: 'POST' })
      fetchData()
    } catch { /* handled by next refresh */ }
  }

  const handleRunCycle = async () => {
    try {
      await fetch(`${API_URL}/api/grace/run-cycle`, { method: 'POST' })
      setTimeout(fetchData, 2000)
    } catch { /* handled by next refresh */ }
  }

  // ---------- LOADING ----------
  if (loading) {
    return (
      <>
        <Navigation />
        <main className={`pt-24 pb-12 min-h-screen bg-background text-text-primary ${paddingClass}`}>
          <div className="max-w-7xl mx-auto px-4">
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" />
              <span className="ml-3 text-text-secondary">Loading GRACE bot...</span>
            </div>
          </div>
        </main>
      </>
    )
  }

  // ---------- ERROR ----------
  if (error && !status) {
    return (
      <>
        <Navigation />
        <main className={`pt-24 pb-12 min-h-screen bg-background text-text-primary ${paddingClass}`}>
          <div className="max-w-7xl mx-auto px-4">
            <div className="bg-red-900/20 border border-red-700 rounded-lg p-6 text-center">
              <AlertTriangle className="w-8 h-8 text-red-400 mx-auto mb-3" />
              <h2 className="text-lg font-semibold text-red-400 mb-2">Failed to Load GRACE</h2>
              <p className="text-text-secondary mb-4">{error}</p>
              <button onClick={fetchData} className="px-4 py-2 bg-red-700 hover:bg-red-600 rounded text-white text-sm">
                Retry
              </button>
            </div>
          </div>
        </main>
      </>
    )
  }

  const account = status?.paper_account
  const pdt = status?.pdt

  return (
    <>
      <Navigation />
      <main className={`pt-24 pb-12 min-h-screen bg-background text-text-primary ${paddingClass}`}>
        <div className="max-w-7xl mx-auto px-4 space-y-6">

          {/* ============================================================ */}
          {/* HEADER */}
          {/* ============================================================ */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold flex items-center gap-3">
                <Heart className="w-7 h-7 text-purple-400" />
                GRACE
                <span className="text-sm font-normal text-text-secondary">1DTE Paper Iron Condor</span>
              </h1>
              <p className="text-sm text-text-secondary mt-1">
                SPY 1DTE IC | {formatPct(status?.profit_target_pct ?? 30)} profit target | Paper trading with real Tradier data
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={handleRunCycle}
                className="flex items-center gap-2 px-3 py-2 text-sm rounded bg-purple-600 hover:bg-purple-500 text-white transition-colors"
              >
                <RefreshCw className="w-4 h-4" /> Run Cycle
              </button>
              <button
                onClick={handleToggle}
                className={`flex items-center gap-2 px-3 py-2 text-sm rounded transition-colors ${
                  status?.is_active
                    ? 'bg-red-600 hover:bg-red-500 text-white'
                    : 'bg-green-600 hover:bg-green-500 text-white'
                }`}
              >
                <Power className="w-4 h-4" /> {status?.is_active ? 'Disable' : 'Enable'}
              </button>
            </div>
          </div>

          {/* ============================================================ */}
          {/* PAPER TRADING BANNER */}
          {/* ============================================================ */}
          <div className="bg-purple-900/20 border border-purple-700/50 rounded-lg p-4">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div className="flex items-center gap-3">
                <FileText className="w-5 h-5 text-purple-400" />
                <span className="text-sm font-medium text-purple-300">PAPER TRADING</span>
                <span className="text-xs text-text-secondary">Real data, simulated fills</span>
              </div>
              <div className="flex items-center gap-6 text-sm">
                <div>
                  <span className="text-text-secondary">Starting: </span>
                  <span className="font-mono font-semibold">{formatCurrency(account?.starting_balance ?? 5000)}</span>
                </div>
                <div>
                  <span className="text-text-secondary">Current: </span>
                  <span className="font-mono font-semibold">{formatCurrency(account?.balance)}</span>
                </div>
                <div>
                  <span className="text-text-secondary">Buying Power: </span>
                  <span className="font-mono font-semibold">{formatCurrency(account?.buying_power)}</span>
                </div>
                <div>
                  <span className="text-text-secondary">Collateral: </span>
                  <span className="font-mono font-semibold">{formatCurrency(account?.collateral_in_use)}</span>
                </div>
              </div>
            </div>
          </div>

          {/* ============================================================ */}
          {/* STATUS + PDT ROW */}
          {/* ============================================================ */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Bot Status Card */}
            <div className="bg-background-card border border-gray-800 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-text-secondary uppercase mb-3">Bot Status</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-text-secondary">Status</span>
                  <span className={status?.is_active ? 'text-green-400' : 'text-red-400'}>
                    {status?.is_active ? 'Active' : 'Disabled'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Mode</span>
                  <span className="text-purple-400">PAPER</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Last Scan</span>
                  <span>{formatTime(status?.last_scan ?? null)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Trades Today</span>
                  <span>{status?.trades_today ?? 0} / {status?.max_trades_per_day ?? 1}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Open Positions</span>
                  <span>{status?.open_positions ?? 0}</span>
                </div>
              </div>
            </div>

            {/* PDT Status Card */}
            <div className="bg-background-card border border-gray-800 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-text-secondary uppercase mb-3">PDT Status</h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-secondary">Day Trades (5-Day Rolling)</span>
                  <span className="text-lg font-mono font-bold">
                    {pdt?.day_trades_rolling_5 ?? 0} / {pdt?.max_day_trades ?? 3}
                  </span>
                </div>
                <div className="w-full bg-gray-800 rounded-full h-3">
                  <div
                    className={`h-3 rounded-full transition-all ${
                      (pdt?.day_trades_rolling_5 ?? 0) >= (pdt?.max_day_trades ?? 3)
                        ? 'bg-red-500'
                        : (pdt?.day_trades_rolling_5 ?? 0) >= 2
                          ? 'bg-yellow-500'
                          : 'bg-green-500'
                    }`}
                    style={{ width: `${Math.min(100, ((pdt?.day_trades_rolling_5 ?? 0) / (pdt?.max_day_trades ?? 3)) * 100)}%` }}
                  />
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-text-secondary">Can Trade</span>
                  {pdt?.can_trade ? (
                    <span className="flex items-center gap-1 text-green-400">
                      <CheckCircle2 className="w-4 h-4" /> YES
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-red-400">
                      <XCircle className="w-4 h-4" /> BLOCKED
                    </span>
                  )}
                </div>
                {pdt?.next_reset && (
                  <div className="flex justify-between text-sm">
                    <span className="text-text-secondary">Next Reset</span>
                    <span>{pdt.next_reset}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Performance Card */}
            <div className="bg-background-card border border-gray-800 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-text-secondary uppercase mb-3">Performance</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-text-secondary">Total Trades</span>
                  <span>{performance?.total_trades ?? 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Win Rate</span>
                  <span className={
                    (performance?.win_rate ?? 0) >= 50 ? 'text-green-400' : 'text-red-400'
                  }>
                    {formatPct(performance?.win_rate)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Total P&L</span>
                  <PnlBadge pnl={performance?.total_pnl} />
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Avg Win</span>
                  <span className="text-green-400 font-mono">{formatCurrency(performance?.avg_win)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Avg Loss</span>
                  <span className="text-red-400 font-mono">{formatCurrency(performance?.avg_loss)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Return</span>
                  <span className={
                    (performance?.return_pct ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'
                  }>
                    {formatPct(performance?.return_pct)}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* ============================================================ */}
          {/* POSITION MONITOR (when trade is open) */}
          {/* ============================================================ */}
          {monitor && (
            <div className="bg-background-card border border-purple-700/50 rounded-lg p-5">
              <h3 className="text-sm font-semibold text-purple-400 uppercase mb-4 flex items-center gap-2">
                <Target className="w-4 h-4" />
                Open Position — Monitoring for {formatPct(monitor.profit_target_pct)} profit target
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div>
                  <span className="text-xs text-text-secondary block">Iron Condor</span>
                  <span className="font-mono text-sm">
                    {monitor.put_long_strike}P/{monitor.put_short_strike}P — {monitor.call_short_strike}C/{monitor.call_long_strike}C
                  </span>
                  <div className="mt-1">
                    <WingBadge
                      adjusted={monitor.wings_adjusted}
                      putWidth={monitor.put_width}
                      callWidth={monitor.call_width}
                    />
                  </div>
                </div>
                <div>
                  <span className="text-xs text-text-secondary block">Entry Credit</span>
                  <span className="font-mono text-sm">${monitor.entry_credit.toFixed(2)}</span>
                  <span className="text-xs text-text-secondary block mt-1">
                    Target Close: ${monitor.profit_target_price.toFixed(2)}
                  </span>
                </div>
                <div>
                  <span className="text-xs text-text-secondary block">Current Cost to Close</span>
                  <span className="font-mono text-sm">
                    {monitor.current_cost_to_close != null ? `$${monitor.current_cost_to_close.toFixed(4)}` : 'Fetching...'}
                  </span>
                  <div className="mt-1">
                    <PnlBadge pnl={monitor.pnl_total} />
                    {monitor.pnl_pct != null && (
                      <span className={`text-xs ml-2 ${monitor.pnl_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        ({monitor.pnl_pct > 0 ? '+' : ''}{monitor.pnl_pct.toFixed(1)}%)
                      </span>
                    )}
                  </div>
                </div>
                <div>
                  <span className="text-xs text-text-secondary block">Progress</span>
                  {monitor.pnl_pct != null ? (
                    <>
                      <div className="w-full bg-gray-800 rounded-full h-3 mt-1">
                        <div
                          className={`h-3 rounded-full transition-all ${
                            monitor.pnl_pct >= 0 ? 'bg-green-500' : 'bg-red-500'
                          }`}
                          style={{ width: `${Math.min(100, Math.max(0, (monitor.pnl_pct / monitor.profit_target_pct) * 100))}%` }}
                        />
                      </div>
                      <span className="text-xs text-text-secondary">
                        {monitor.pnl_pct.toFixed(1)}% / {monitor.profit_target_pct}% target
                      </span>
                    </>
                  ) : (
                    <span className="text-xs text-text-secondary">Calculating...</span>
                  )}
                  <div className="mt-1 text-xs text-text-secondary">
                    Stop: ${monitor.stop_loss_price.toFixed(2)} | EOD: {monitor.eod_cutoff} ET
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ============================================================ */}
          {/* TABS */}
          {/* ============================================================ */}
          <div className="border-b border-gray-800">
            <div className="flex gap-1">
              {[
                { key: 'overview' as const, label: 'Overview', icon: BarChart3 },
                { key: 'history' as const, label: 'Trade History', icon: Activity },
                { key: 'activity' as const, label: 'Activity Log', icon: FileText },
              ].map(tab => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === tab.key
                      ? 'border-primary text-primary'
                      : 'border-transparent text-text-secondary hover:text-text-primary'
                  }`}
                >
                  <tab.icon className="w-4 h-4" />
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* ============================================================ */}
          {/* TAB CONTENT: OVERVIEW */}
          {/* ============================================================ */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              <div className="bg-background-card border border-gray-800 rounded-lg p-5">
                <h3 className="text-sm font-semibold text-text-secondary uppercase mb-3">Strategy Configuration</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div>
                    <span className="text-text-secondary block">Ticker</span>
                    <span className="font-semibold">{status?.ticker ?? 'SPY'}</span>
                  </div>
                  <div>
                    <span className="text-text-secondary block">DTE Target</span>
                    <span className="font-semibold">{status?.dte ?? 1} day</span>
                  </div>
                  <div>
                    <span className="text-text-secondary block">SD Multiplier</span>
                    <span className="font-semibold">{status?.sd_multiplier ?? 1.2}</span>
                  </div>
                  <div>
                    <span className="text-text-secondary block">Spread Width</span>
                    <span className="font-semibold">${status?.spread_width ?? 5}</span>
                  </div>
                  <div>
                    <span className="text-text-secondary block">Profit Target</span>
                    <span className="font-semibold text-green-400">{formatPct(status?.profit_target_pct ?? 30)}</span>
                  </div>
                  <div>
                    <span className="text-text-secondary block">Stop Loss</span>
                    <span className="font-semibold text-red-400">{formatPct(status?.stop_loss_pct ?? 100)}</span>
                  </div>
                  <div>
                    <span className="text-text-secondary block">EOD Cutoff</span>
                    <span className="font-semibold">{status?.eod_cutoff ?? '15:45'} ET</span>
                  </div>
                  <div>
                    <span className="text-text-secondary block">VIX Skip</span>
                    <span className="font-semibold">{'>'} {status?.vix_skip ?? 32}</span>
                  </div>
                </div>
              </div>

              {!performance || performance.total_trades === 0 ? (
                <div className="bg-background-card border border-gray-800 rounded-lg p-12 text-center">
                  <Heart className="w-10 h-10 text-text-secondary mx-auto mb-4 opacity-50" />
                  <h3 className="text-lg font-medium text-text-secondary mb-2">No Closed Trades Yet</h3>
                  <p className="text-sm text-text-secondary">
                    Performance stats will appear here once GRACE closes its first trade.
                    {(status?.open_positions ?? 0) > 0 && ' There is an open position being monitored above.'}
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {[
                    { label: 'Total P&L', value: formatCurrency(performance.total_pnl), color: performance.total_pnl >= 0 ? 'text-green-400' : 'text-red-400' },
                    { label: 'Win Rate', value: formatPct(performance.win_rate), color: performance.win_rate >= 50 ? 'text-green-400' : 'text-red-400' },
                    { label: 'Best Trade', value: formatCurrency(performance.best_trade), color: 'text-green-400' },
                    { label: 'Worst Trade', value: formatCurrency(performance.worst_trade), color: 'text-red-400' },
                  ].map(stat => (
                    <div key={stat.label} className="bg-background-card border border-gray-800 rounded-lg p-4">
                      <span className="text-xs text-text-secondary block">{stat.label}</span>
                      <span className={`text-xl font-mono font-bold ${stat.color}`}>{stat.value}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ============================================================ */}
          {/* TAB CONTENT: TRADE HISTORY */}
          {/* ============================================================ */}
          {activeTab === 'history' && (
            <div>
              {trades.length === 0 ? (
                <div className="bg-background-card border border-gray-800 rounded-lg p-12 text-center">
                  <Activity className="w-10 h-10 text-text-secondary mx-auto mb-4 opacity-50" />
                  <h3 className="text-lg font-medium text-text-secondary mb-2">No Closed Trades Yet</h3>
                  <p className="text-sm text-text-secondary">
                    Closed trades will appear here once an open position hits its profit target, stop loss, or EOD cutoff.
                    {(status?.open_positions ?? 0) > 0 && ' There is an open position being monitored above.'}
                  </p>
                </div>
              ) : (
                <div className="bg-background-card border border-gray-800 rounded-lg overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-gray-800 text-text-secondary text-left">
                          <th className="px-4 py-3">Date</th>
                          <th className="px-4 py-3">Iron Condor</th>
                          <th className="px-4 py-3">Wings</th>
                          <th className="px-4 py-3">Contracts</th>
                          <th className="px-4 py-3">Credit</th>
                          <th className="px-4 py-3">Close</th>
                          <th className="px-4 py-3">P&L</th>
                          <th className="px-4 py-3">Reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {trades.map(trade => (
                          <tr key={trade.position_id} className="border-b border-gray-800/50 hover:bg-background-hover">
                            <td className="px-4 py-3 text-text-secondary whitespace-nowrap">{formatTime(trade.close_time)}</td>
                            <td className="px-4 py-3 font-mono whitespace-nowrap">
                              {trade.put_long_strike}/{trade.put_short_strike}P — {trade.call_short_strike}/{trade.call_long_strike}C
                            </td>
                            <td className="px-4 py-3">
                              <WingBadge
                                adjusted={trade.wings_adjusted}
                                putWidth={trade.put_width}
                                callWidth={trade.call_width}
                              />
                            </td>
                            <td className="px-4 py-3">{trade.contracts}</td>
                            <td className="px-4 py-3 font-mono">${trade.total_credit.toFixed(2)}</td>
                            <td className="px-4 py-3 font-mono">${trade.close_price.toFixed(2)}</td>
                            <td className="px-4 py-3"><PnlBadge pnl={trade.realized_pnl} /></td>
                            <td className="px-4 py-3">
                              <span className={`text-xs px-2 py-0.5 rounded ${
                                trade.close_reason === 'profit_target' ? 'bg-green-900/30 text-green-400' :
                                trade.close_reason === 'stop_loss' ? 'bg-red-900/30 text-red-400' :
                                'bg-yellow-900/30 text-yellow-400'
                              }`}>
                                {trade.close_reason}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ============================================================ */}
          {/* TAB CONTENT: ACTIVITY LOG */}
          {/* ============================================================ */}
          {activeTab === 'activity' && (
            <div>
              {logs.length === 0 ? (
                <div className="bg-background-card border border-gray-800 rounded-lg p-12 text-center">
                  <FileText className="w-10 h-10 text-text-secondary mx-auto mb-4 opacity-50" />
                  <h3 className="text-lg font-medium text-text-secondary mb-2">No Activity Yet</h3>
                  <p className="text-sm text-text-secondary">
                    Activity logs will appear here as GRACE scans for opportunities.
                  </p>
                </div>
              ) : (
                <div className="bg-background-card border border-gray-800 rounded-lg overflow-hidden">
                  <div className="max-h-[600px] overflow-y-auto">
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 bg-background-card">
                        <tr className="border-b border-gray-800 text-text-secondary text-left">
                          <th className="px-4 py-3">Time</th>
                          <th className="px-4 py-3">Level</th>
                          <th className="px-4 py-3">Message</th>
                        </tr>
                      </thead>
                      <tbody>
                        {logs.map((log, i) => (
                          <tr key={i} className="border-b border-gray-800/50 hover:bg-background-hover">
                            <td className="px-4 py-2 text-text-secondary whitespace-nowrap text-xs">
                              {formatTime(log.timestamp)}
                            </td>
                            <td className="px-4 py-2">
                              <span className={`text-xs px-2 py-0.5 rounded ${
                                log.level === 'ERROR' ? 'bg-red-900/30 text-red-400' :
                                log.level === 'TRADE_OPEN' || log.level === 'TRADE_CLOSE' ? 'bg-green-900/30 text-green-400' :
                                log.level === 'SKIP' ? 'bg-yellow-900/30 text-yellow-400' :
                                'bg-gray-800 text-text-secondary'
                              }`}>
                                {log.level}
                              </span>
                            </td>
                            <td className="px-4 py-2 text-text-primary">{log.message}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

        </div>
      </main>
    </>
  )
}
