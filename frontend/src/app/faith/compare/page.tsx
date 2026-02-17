'use client'

import React, { useState, useEffect, useCallback } from 'react'
import {
  Sword, Heart, TrendingUp, TrendingDown, BarChart3,
  RefreshCw, AlertTriangle, Minus
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

interface BotStatus {
  bot_name: string
  is_active: boolean
  open_positions: number
  trades_today: number
  last_scan: string | null
  paper_account: PaperAccount
}

interface EquityPoint {
  timestamp: string
  time?: string
  equity: number
  cumulative_pnl: number
  open_positions?: number
  unrealized_pnl?: number
}

interface IntradayResponse {
  success: boolean
  date: string
  bot: string
  data_points: EquityPoint[]
  current_equity: number
  day_pnl: number
  day_realized: number
  day_unrealized: number
  starting_equity: number
}

// ============================================================================
// HELPERS
// ============================================================================

function formatCurrency(val: number | null | undefined): string {
  if (val == null) return '--'
  return `$${val.toFixed(2)}`
}

function formatPct(val: number | null | undefined): string {
  if (val == null) return '--'
  return `${val.toFixed(1)}%`
}

function PnlValue({ value, size = 'text-sm' }: { value: number | null | undefined; size?: string }) {
  if (value == null) return <span className="text-text-secondary">--</span>
  const color = value > 0 ? 'text-green-400' : value < 0 ? 'text-red-400' : 'text-text-secondary'
  const prefix = value > 0 ? '+' : ''
  return <span className={`font-mono font-semibold ${color} ${size}`}>{prefix}${value.toFixed(2)}</span>
}

function CompareArrow({ faith, grace }: { faith: number | null | undefined; grace: number | null | undefined }) {
  if (faith == null || grace == null) return null
  if (Math.abs(faith - grace) < 0.01) return <Minus className="w-3 h-3 text-text-secondary" />
  if (grace > faith) return <TrendingUp className="w-3 h-3 text-purple-400" />
  return <TrendingDown className="w-3 h-3 text-blue-400" />
}

// ============================================================================
// SIMPLE INLINE EQUITY CHART
// ============================================================================

function EquityChart({ faithPoints, gracePoints }: {
  faithPoints: EquityPoint[]
  gracePoints: EquityPoint[]
}) {
  if (faithPoints.length === 0 && gracePoints.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-text-secondary text-sm">
        No equity data available yet
      </div>
    )
  }

  // Merge all points to get time range
  const allEquities = [
    ...faithPoints.map(p => p.equity),
    ...gracePoints.map(p => p.equity),
  ].filter(Boolean)

  if (allEquities.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-text-secondary text-sm">
        No equity data available yet
      </div>
    )
  }

  const minEq = Math.min(...allEquities)
  const maxEq = Math.max(...allEquities)
  const range = maxEq - minEq || 1

  const chartHeight = 180
  const chartWidth = 600

  function toPath(points: EquityPoint[], width: number, height: number): string {
    if (points.length < 2) return ''
    const step = width / (points.length - 1)
    return points.map((p, i) => {
      const x = i * step
      const y = height - ((p.equity - minEq) / range) * (height - 20) - 10
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`
    }).join(' ')
  }

  const faithPath = toPath(faithPoints, chartWidth, chartHeight)
  const gracePath = toPath(gracePoints, chartWidth, chartHeight)

  return (
    <div className="w-full overflow-hidden">
      <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="w-full h-48" preserveAspectRatio="none">
        {/* Grid lines */}
        {[0.25, 0.5, 0.75].map(pct => {
          const y = chartHeight - (pct * (chartHeight - 20)) - 10
          return (
            <line key={pct} x1="0" y1={y} x2={chartWidth} y2={y}
              stroke="#374151" strokeWidth="0.5" strokeDasharray="4 4" />
          )
        })}
        {/* FAITH line (blue) */}
        {faithPath && (
          <path d={faithPath} fill="none" stroke="#3B82F6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        )}
        {/* GRACE line (purple) */}
        {gracePath && (
          <path d={gracePath} fill="none" stroke="#A855F7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        )}
      </svg>
      {/* Legend */}
      <div className="flex items-center justify-center gap-6 mt-2">
        <div className="flex items-center gap-2">
          <div className="w-4 h-0.5 bg-blue-500 rounded" />
          <span className="text-xs text-text-secondary">FAITH (2DTE)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-0.5 bg-purple-500 rounded" />
          <span className="text-xs text-text-secondary">GRACE (1DTE)</span>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// PAGE COMPONENT
// ============================================================================

export default function FaithGraceComparePage() {
  const paddingClass = useSidebarPadding()

  const [faithPerf, setFaithPerf] = useState<Performance | null>(null)
  const [gracePerf, setGracePerf] = useState<Performance | null>(null)
  const [faithStatus, setFaithStatus] = useState<BotStatus | null>(null)
  const [graceStatus, setGraceStatus] = useState<BotStatus | null>(null)
  const [faithIntraday, setFaithIntraday] = useState<IntradayResponse | null>(null)
  const [graceIntraday, setGraceIntraday] = useState<IntradayResponse | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    const [fp, gp, fs, gs, fi, gi] = await Promise.all([
      fetchApi<Performance>('/api/faith/performance?dte_mode=2DTE'),
      fetchApi<Performance>('/api/grace/performance'),
      fetchApi<BotStatus>('/api/faith/status?dte_mode=2DTE'),
      fetchApi<BotStatus>('/api/grace/status'),
      fetch(`${API_URL}/api/faith/equity-curve/intraday?dte_mode=2DTE`).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`${API_URL}/api/grace/equity-curve/intraday`).then(r => r.ok ? r.json() : null).catch(() => null),
    ])
    setFaithPerf(fp)
    setGracePerf(gp)
    setFaithStatus(fs)
    setGraceStatus(gs)
    setFaithIntraday(fi)
    setGraceIntraday(gi)
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [fetchData])

  if (loading) {
    return (
      <>
        <Navigation />
        <main className={`pt-24 pb-12 min-h-screen bg-background text-text-primary ${paddingClass}`}>
          <div className="max-w-7xl mx-auto px-4">
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" />
              <span className="ml-3 text-text-secondary">Loading comparison data...</span>
            </div>
          </div>
        </main>
      </>
    )
  }

  const faithAccount = faithStatus?.paper_account
  const graceAccount = graceStatus?.paper_account

  // Build comparison metrics rows
  const metrics = [
    {
      label: 'Total Trades',
      faith: faithPerf?.total_trades ?? 0,
      grace: gracePerf?.total_trades ?? 0,
      format: (v: number) => v.toString(),
    },
    {
      label: 'Win Rate',
      faith: faithPerf?.win_rate ?? 0,
      grace: gracePerf?.win_rate ?? 0,
      format: (v: number) => formatPct(v),
      higherBetter: true,
    },
    {
      label: 'Total P&L',
      faith: faithPerf?.total_pnl ?? 0,
      grace: gracePerf?.total_pnl ?? 0,
      format: (v: number) => formatCurrency(v),
      higherBetter: true,
      isPnl: true,
    },
    {
      label: 'Avg Win',
      faith: faithPerf?.avg_win ?? 0,
      grace: gracePerf?.avg_win ?? 0,
      format: (v: number) => formatCurrency(v),
      higherBetter: true,
    },
    {
      label: 'Avg Loss',
      faith: faithPerf?.avg_loss ?? 0,
      grace: gracePerf?.avg_loss ?? 0,
      format: (v: number) => formatCurrency(v),
      higherBetter: false, // less negative is better
    },
    {
      label: 'Best Trade',
      faith: faithPerf?.best_trade ?? 0,
      grace: gracePerf?.best_trade ?? 0,
      format: (v: number) => formatCurrency(v),
      higherBetter: true,
    },
    {
      label: 'Worst Trade',
      faith: faithPerf?.worst_trade ?? 0,
      grace: gracePerf?.worst_trade ?? 0,
      format: (v: number) => formatCurrency(v),
      higherBetter: false,
    },
    {
      label: 'Current Balance',
      faith: faithAccount?.balance ?? 0,
      grace: graceAccount?.balance ?? 0,
      format: (v: number) => formatCurrency(v),
      higherBetter: true,
    },
    {
      label: 'Return %',
      faith: faithPerf?.return_pct ?? 0,
      grace: gracePerf?.return_pct ?? 0,
      format: (v: number) => formatPct(v),
      higherBetter: true,
      isPnl: true,
    },
    {
      label: 'Max Drawdown',
      faith: faithAccount?.max_drawdown ?? 0,
      grace: graceAccount?.max_drawdown ?? 0,
      format: (v: number) => formatCurrency(v),
      higherBetter: false,
    },
  ]

  function getWinner(faith: number, grace: number, higherBetter?: boolean): 'faith' | 'grace' | 'tie' {
    if (Math.abs(faith - grace) < 0.01) return 'tie'
    if (higherBetter === undefined) return 'tie'
    if (higherBetter) return grace > faith ? 'grace' : 'faith'
    // For "lower is better" (like avg loss, worst trade), less negative = better
    return grace > faith ? 'grace' : 'faith'
  }

  const faithPoints = faithIntraday?.data_points ?? []
  const gracePoints = graceIntraday?.data_points ?? []

  return (
    <>
      <Navigation />
      <main className={`pt-24 pb-12 min-h-screen bg-background text-text-primary ${paddingClass}`}>
        <div className="max-w-7xl mx-auto px-4 space-y-6">

          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <Sword className="w-6 h-6 text-blue-400" />
                  <span className="text-blue-400">FAITH</span>
                  <span className="text-text-secondary text-lg font-normal">vs</span>
                  <Heart className="w-6 h-6 text-purple-400" />
                  <span className="text-purple-400">GRACE</span>
                </div>
              </h1>
              <p className="text-sm text-text-secondary mt-1">
                2DTE vs 1DTE Paper Iron Condor — Side-by-side performance comparison
              </p>
            </div>
            <button
              onClick={() => { setLoading(true); fetchData() }}
              className="flex items-center gap-2 px-3 py-2 text-sm rounded bg-gray-700 hover:bg-gray-600 text-white transition-colors"
            >
              <RefreshCw className="w-4 h-4" /> Refresh
            </button>
          </div>

          {/* Quick Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* FAITH Summary */}
            <div className="bg-background-card border border-blue-700/50 rounded-lg p-5">
              <div className="flex items-center gap-2 mb-4">
                <Sword className="w-5 h-5 text-blue-400" />
                <h2 className="text-lg font-semibold text-blue-400">FAITH — 2DTE</h2>
                <span className={`text-xs px-2 py-0.5 rounded ${
                  faithStatus?.is_active ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'
                }`}>
                  {faithStatus?.is_active ? 'ACTIVE' : 'DISABLED'}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <span className="text-text-secondary block text-xs">Balance</span>
                  <span className="font-mono font-semibold">{formatCurrency(faithAccount?.balance)}</span>
                </div>
                <div>
                  <span className="text-text-secondary block text-xs">P&L</span>
                  <PnlValue value={faithPerf?.total_pnl} />
                </div>
                <div>
                  <span className="text-text-secondary block text-xs">Win Rate</span>
                  <span className={`font-mono font-semibold ${
                    (faithPerf?.win_rate ?? 0) >= 50 ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {formatPct(faithPerf?.win_rate)}
                  </span>
                </div>
              </div>
            </div>

            {/* GRACE Summary */}
            <div className="bg-background-card border border-purple-700/50 rounded-lg p-5">
              <div className="flex items-center gap-2 mb-4">
                <Heart className="w-5 h-5 text-purple-400" />
                <h2 className="text-lg font-semibold text-purple-400">GRACE — 1DTE</h2>
                <span className={`text-xs px-2 py-0.5 rounded ${
                  graceStatus?.is_active ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'
                }`}>
                  {graceStatus?.is_active ? 'ACTIVE' : 'DISABLED'}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <span className="text-text-secondary block text-xs">Balance</span>
                  <span className="font-mono font-semibold">{formatCurrency(graceAccount?.balance)}</span>
                </div>
                <div>
                  <span className="text-text-secondary block text-xs">P&L</span>
                  <PnlValue value={gracePerf?.total_pnl} />
                </div>
                <div>
                  <span className="text-text-secondary block text-xs">Win Rate</span>
                  <span className={`font-mono font-semibold ${
                    (gracePerf?.win_rate ?? 0) >= 50 ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {formatPct(gracePerf?.win_rate)}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Overlaid Equity Curves */}
          <div className="bg-background-card border border-gray-800 rounded-lg p-5">
            <h3 className="text-sm font-semibold text-text-secondary uppercase mb-4 flex items-center gap-2">
              <BarChart3 className="w-4 h-4" />
              Intraday Equity Curves — Overlaid
            </h3>
            <EquityChart faithPoints={faithPoints} gracePoints={gracePoints} />
            {/* Day P&L summary under chart */}
            <div className="flex items-center justify-center gap-8 mt-4 text-sm">
              <div className="flex items-center gap-2">
                <Sword className="w-4 h-4 text-blue-400" />
                <span className="text-text-secondary">Day P&L:</span>
                <PnlValue value={faithIntraday?.day_pnl} />
              </div>
              <div className="flex items-center gap-2">
                <Heart className="w-4 h-4 text-purple-400" />
                <span className="text-text-secondary">Day P&L:</span>
                <PnlValue value={graceIntraday?.day_pnl} />
              </div>
            </div>
          </div>

          {/* Side-by-Side Metrics Table */}
          <div className="bg-background-card border border-gray-800 rounded-lg overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-800">
              <h3 className="text-sm font-semibold text-text-secondary uppercase">Performance Comparison</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="px-5 py-3 text-left text-text-secondary font-medium">Metric</th>
                    <th className="px-5 py-3 text-right text-blue-400 font-medium">
                      <div className="flex items-center justify-end gap-2">
                        <Sword className="w-4 h-4" /> FAITH (2DTE)
                      </div>
                    </th>
                    <th className="px-5 py-3 text-center text-text-secondary font-medium w-12"></th>
                    <th className="px-5 py-3 text-left text-purple-400 font-medium">
                      <div className="flex items-center gap-2">
                        <Heart className="w-4 h-4" /> GRACE (1DTE)
                      </div>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {metrics.map((m) => {
                    const winner = getWinner(m.faith, m.grace, m.higherBetter)
                    return (
                      <tr key={m.label} className="border-b border-gray-800/50 hover:bg-background-hover">
                        <td className="px-5 py-3 text-text-secondary">{m.label}</td>
                        <td className={`px-5 py-3 text-right font-mono ${
                          winner === 'faith' ? 'text-blue-400 font-semibold' :
                          m.isPnl ? (m.faith >= 0 ? 'text-green-400' : 'text-red-400') :
                          'text-text-primary'
                        }`}>
                          {m.format(m.faith)}
                          {winner === 'faith' && <span className="ml-1 text-xs text-blue-400">&#9650;</span>}
                        </td>
                        <td className="px-5 py-3 text-center">
                          <CompareArrow faith={m.faith} grace={m.grace} />
                        </td>
                        <td className={`px-5 py-3 font-mono ${
                          winner === 'grace' ? 'text-purple-400 font-semibold' :
                          m.isPnl ? (m.grace >= 0 ? 'text-green-400' : 'text-red-400') :
                          'text-text-primary'
                        }`}>
                          {m.format(m.grace)}
                          {winner === 'grace' && <span className="ml-1 text-xs text-purple-400">&#9650;</span>}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Insights / No Data State */}
          {(faithPerf?.total_trades ?? 0) === 0 && (gracePerf?.total_trades ?? 0) === 0 && (
            <div className="bg-background-card border border-gray-800 rounded-lg p-12 text-center">
              <AlertTriangle className="w-10 h-10 text-text-secondary mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium text-text-secondary mb-2">No Trades Yet</h3>
              <p className="text-sm text-text-secondary">
                Comparison data will populate once FAITH and GRACE close their first trades.
                Both bots scan every 5 minutes during market hours.
              </p>
            </div>
          )}

          {/* Navigation Links */}
          <div className="flex items-center justify-center gap-4 text-sm">
            <a href="/faith" className="flex items-center gap-2 px-4 py-2 rounded bg-blue-900/30 border border-blue-700/50 text-blue-400 hover:bg-blue-900/50 transition-colors">
              <Sword className="w-4 h-4" /> FAITH Dashboard
            </a>
            <a href="/grace" className="flex items-center gap-2 px-4 py-2 rounded bg-purple-900/30 border border-purple-700/50 text-purple-400 hover:bg-purple-900/50 transition-colors">
              <Heart className="w-4 h-4" /> GRACE Dashboard
            </a>
          </div>

        </div>
      </main>
    </>
  )
}
