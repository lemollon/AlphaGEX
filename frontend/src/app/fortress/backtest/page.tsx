'use client'

import React, { useState } from 'react'
import {
  Shield, TrendingUp, AlertTriangle, CheckCircle2, XCircle,
  BarChart3, Activity, Target, DollarSign, RefreshCw,
  ChevronDown, ChevronUp, Zap, Clock, Award
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import { useFortressScorecard, useFortressScorecardHistory } from '@/lib/hooks/useMarketData'
import { apiClient } from '@/lib/api'
import { useToast } from '@/components/ui/Toast'
import {
  BotPageHeader,
  LoadingState,
  BOT_BRANDS,
} from '@/components/trader'

// ==============================================================================
// INTERFACES
// ==============================================================================

interface ScorecardCheck {
  number: number
  name: string
  category: string
  target: string
  result_display: string
  result_value: number
  passed: boolean
}

interface VixRegime {
  label: string
  trade_count: number
  win_rate: number
  profit_factor: number
  total_pnl: number
  max_dd_pct: number
}

interface ScorecardData {
  // Verdict
  verdict: string
  verdict_detail: string
  total_checks: number
  passed_checks: number
  recommended_size_pct: number

  // Stats
  total_pnl: number
  avg_pnl: number
  median_pnl: number
  win_rate: number
  profit_factor: number
  expected_value: number
  annualized_return: number
  total_trades: number
  t_statistic: number
  sharpe_ratio: number
  sortino_ratio: number
  skewness: number
  max_drawdown_dollar: number
  max_drawdown_pct: number
  max_dd_duration_trades: number
  max_consecutive_losses: number
  largest_single_loss: number
  calmar_ratio: number
  var_95: number
  initial_capital: number
  ending_equity: number

  // Checks and breakdowns
  checks: ScorecardCheck[]
  vix_regimes: VixRegime[]
  worst_month: string
  worst_month_pnl: number
  worst_month_pct: number
  worst_month_passed: boolean

  // Equity curve
  equity_curve: number[]
  trade_dates: string[]
}

// ==============================================================================
// HELPERS
// ==============================================================================

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

function formatPct(value: number, decimals: number = 1): string {
  return `${(value * 100).toFixed(decimals)}%`
}

function getVerdictColor(verdict: string): { bg: string; border: string; text: string; icon: React.ReactNode } {
  switch (verdict) {
    case 'GO_LIVE':
      return {
        bg: 'bg-green-900/40',
        border: 'border-green-500/60',
        text: 'text-green-400',
        icon: <CheckCircle2 className="w-8 h-8 text-green-400" />,
      }
    case 'CONDITIONAL_GO':
      return {
        bg: 'bg-yellow-900/40',
        border: 'border-yellow-500/60',
        text: 'text-yellow-400',
        icon: <AlertTriangle className="w-8 h-8 text-yellow-400" />,
      }
    case 'PAPER_TRADE':
      return {
        bg: 'bg-orange-900/40',
        border: 'border-orange-500/60',
        text: 'text-orange-400',
        icon: <Clock className="w-8 h-8 text-orange-400" />,
      }
    default:
      return {
        bg: 'bg-red-900/40',
        border: 'border-red-500/60',
        text: 'text-red-400',
        icon: <XCircle className="w-8 h-8 text-red-400" />,
      }
  }
}

function getVerdictLabel(verdict: string): string {
  switch (verdict) {
    case 'GO_LIVE': return 'GO LIVE'
    case 'CONDITIONAL_GO': return 'CONDITIONAL GO'
    case 'PAPER_TRADE': return 'PAPER TRADE'
    case 'NO_GO': return 'NO GO'
    case 'NO_DATA': return 'NO DATA'
    default: return verdict
  }
}

// ==============================================================================
// VERDICT BANNER COMPONENT
// ==============================================================================

function VerdictBanner({ data }: { data: ScorecardData }) {
  const colors = getVerdictColor(data.verdict)

  return (
    <div className={`${colors.bg} border ${colors.border} rounded-xl p-6`}>
      <div className="flex items-center gap-4">
        {colors.icon}
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h2 className={`text-2xl font-bold ${colors.text}`}>
              {getVerdictLabel(data.verdict)}
            </h2>
            <span className="text-gray-400 text-sm">
              {data.passed_checks}/{data.total_checks} checks passed
            </span>
          </div>
          <p className="text-gray-300 mt-1">{data.verdict_detail}</p>
          {data.recommended_size_pct > 0 && data.recommended_size_pct < 100 && (
            <p className={`${colors.text} text-sm mt-2 font-medium`}>
              Recommended deployment: {data.recommended_size_pct}% of optimal position size
            </p>
          )}
        </div>
        <div className="text-right">
          <div className="text-3xl font-bold text-white">
            {data.passed_checks}<span className="text-gray-500">/{data.total_checks}</span>
          </div>
          <div className="text-gray-400 text-xs">checks passed</div>
        </div>
      </div>
    </div>
  )
}

// ==============================================================================
// SCORE RING COMPONENT
// ==============================================================================

function ScoreRing({ passed, total }: { passed: number; total: number }) {
  const pct = total > 0 ? (passed / total) * 100 : 0
  const circumference = 2 * Math.PI * 40
  const strokeDashoffset = circumference - (pct / 100) * circumference

  let color = 'text-red-400'
  if (pct >= 89) color = 'text-green-400'
  else if (pct >= 72) color = 'text-yellow-400'
  else if (pct >= 56) color = 'text-orange-400'

  return (
    <div className="relative w-24 h-24 mx-auto">
      <svg className="w-24 h-24 transform -rotate-90" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="40" stroke="currentColor" strokeWidth="6"
          fill="none" className="text-gray-800" />
        <circle cx="50" cy="50" r="40" stroke="currentColor" strokeWidth="6"
          fill="none" className={color}
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round" />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-xl font-bold text-white">{passed}/{total}</span>
      </div>
    </div>
  )
}

// ==============================================================================
// CATEGORY CARD COMPONENT
// ==============================================================================

function CategoryCard({
  title,
  icon,
  checks,
  defaultOpen = true,
}: {
  title: string
  icon: React.ReactNode
  checks: ScorecardCheck[]
  defaultOpen?: boolean
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen)
  const passCount = checks.filter(c => c.passed).length

  return (
    <div className="bg-gray-900/50 border border-gray-800 rounded-xl overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 hover:bg-gray-800/30 transition-colors"
      >
        <div className="flex items-center gap-3">
          {icon}
          <h3 className="text-white font-semibold">{title}</h3>
          <span className={`text-sm px-2 py-0.5 rounded-full ${
            passCount === checks.length
              ? 'bg-green-900/50 text-green-400'
              : passCount >= checks.length * 0.7
              ? 'bg-yellow-900/50 text-yellow-400'
              : 'bg-red-900/50 text-red-400'
          }`}>
            {passCount}/{checks.length}
          </span>
        </div>
        {isOpen ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
      </button>

      {isOpen && (
        <div className="border-t border-gray-800">
          <table className="w-full">
            <thead>
              <tr className="text-gray-500 text-xs uppercase">
                <th className="text-left p-3 w-8">#</th>
                <th className="text-left p-3">Stat</th>
                <th className="text-right p-3">Target</th>
                <th className="text-right p-3">Result</th>
                <th className="text-center p-3 w-16">Pass?</th>
              </tr>
            </thead>
            <tbody>
              {checks.map((check) => (
                <tr
                  key={check.number}
                  className={`border-t border-gray-800/50 ${
                    check.passed ? 'hover:bg-green-900/10' : 'hover:bg-red-900/10'
                  }`}
                >
                  <td className="p-3 text-gray-500 text-sm">{check.number}</td>
                  <td className="p-3 text-white text-sm font-medium">{check.name}</td>
                  <td className="p-3 text-gray-400 text-sm text-right font-mono">{check.target}</td>
                  <td className={`p-3 text-sm text-right font-mono font-bold ${
                    check.passed ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {check.result_display}
                  </td>
                  <td className="p-3 text-center">
                    {check.passed ? (
                      <CheckCircle2 className="w-5 h-5 text-green-400 mx-auto" />
                    ) : (
                      <XCircle className="w-5 h-5 text-red-400 mx-auto" />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ==============================================================================
// VIX REGIME TABLE
// ==============================================================================

function VixRegimeTable({ regimes, worstMonth, worstMonthPnl, worstMonthPct, worstMonthPassed }: {
  regimes: VixRegime[]
  worstMonth: string
  worstMonthPnl: number
  worstMonthPct: number
  worstMonthPassed: boolean
}) {
  return (
    <div className="bg-gray-900/50 border border-gray-800 rounded-xl overflow-hidden">
      <div className="flex items-center gap-3 p-4">
        <Activity className="w-5 h-5 text-blue-400" />
        <h3 className="text-white font-semibold">Category 4: Robustness Across Conditions</h3>
      </div>
      <div className="border-t border-gray-800">
        <table className="w-full">
          <thead>
            <tr className="text-gray-500 text-xs uppercase">
              <th className="text-left p-3">VIX Regime</th>
              <th className="text-right p-3">Trades</th>
              <th className="text-right p-3">Win Rate</th>
              <th className="text-right p-3">Profit Factor</th>
              <th className="text-right p-3">Total P&L</th>
              <th className="text-right p-3">Max DD</th>
            </tr>
          </thead>
          <tbody>
            {regimes.map((r) => (
              <tr key={r.label} className="border-t border-gray-800/50 hover:bg-gray-800/20">
                <td className="p-3 text-white font-medium text-sm">{r.label}</td>
                <td className="p-3 text-gray-300 text-sm text-right">{r.trade_count}</td>
                <td className={`p-3 text-sm text-right font-mono ${
                  r.win_rate >= 0.8 ? 'text-green-400' : r.win_rate >= 0.6 ? 'text-yellow-400' : 'text-red-400'
                }`}>
                  {formatPct(r.win_rate)}
                </td>
                <td className={`p-3 text-sm text-right font-mono ${
                  r.profit_factor >= 3 ? 'text-green-400' : r.profit_factor >= 1.5 ? 'text-yellow-400' : 'text-red-400'
                }`}>
                  {r.profit_factor.toFixed(2)}
                </td>
                <td className={`p-3 text-sm text-right font-mono ${
                  r.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'
                }`}>
                  {formatCurrency(r.total_pnl)}
                </td>
                <td className={`p-3 text-sm text-right font-mono ${
                  r.max_dd_pct < 0.15 ? 'text-green-400' : r.max_dd_pct < 0.25 ? 'text-yellow-400' : 'text-red-400'
                }`}>
                  {formatPct(r.max_dd_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {worstMonth && (
        <div className={`border-t ${worstMonthPassed ? 'border-gray-800' : 'border-red-800/50'} p-4`}>
          <div className="flex items-center justify-between">
            <span className="text-gray-400 text-sm">Worst Month</span>
            <div className="flex items-center gap-3">
              <span className="text-white font-mono text-sm">{worstMonth}</span>
              <span className={`font-mono text-sm font-bold ${worstMonthPassed ? 'text-yellow-400' : 'text-red-400'}`}>
                {formatCurrency(worstMonthPnl)} ({worstMonthPct.toFixed(1)}%)
              </span>
              {worstMonthPassed ? (
                <CheckCircle2 className="w-4 h-4 text-green-400" />
              ) : (
                <XCircle className="w-4 h-4 text-red-400" />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ==============================================================================
// KEY METRICS CARDS
// ==============================================================================

function KeyMetricsGrid({ data }: { data: ScorecardData }) {
  const metrics = [
    { label: 'Total P&L', value: formatCurrency(data.total_pnl), color: data.total_pnl >= 0 ? 'text-green-400' : 'text-red-400', icon: <DollarSign className="w-4 h-4" /> },
    { label: 'Win Rate', value: formatPct(data.win_rate), color: data.win_rate >= 0.7 ? 'text-green-400' : 'text-yellow-400', icon: <Target className="w-4 h-4" /> },
    { label: 'Profit Factor', value: data.profit_factor.toFixed(2), color: data.profit_factor >= 2 ? 'text-green-400' : 'text-yellow-400', icon: <TrendingUp className="w-4 h-4" /> },
    { label: 'Sharpe Ratio', value: data.sharpe_ratio.toFixed(2), color: data.sharpe_ratio >= 2 ? 'text-green-400' : 'text-yellow-400', icon: <BarChart3 className="w-4 h-4" /> },
    { label: 'Annualized Return', value: formatPct(data.annualized_return), color: data.annualized_return >= 0.3 ? 'text-green-400' : 'text-yellow-400', icon: <Zap className="w-4 h-4" /> },
    { label: 'Max Drawdown', value: `${formatCurrency(data.max_drawdown_dollar)} (${formatPct(data.max_drawdown_pct)})`, color: data.max_drawdown_pct < 0.15 ? 'text-green-400' : 'text-red-400', icon: <AlertTriangle className="w-4 h-4" /> },
    { label: 'Total Trades', value: data.total_trades.toString(), color: 'text-blue-400', icon: <Activity className="w-4 h-4" /> },
    { label: 'Calmar Ratio', value: data.calmar_ratio.toFixed(2), color: data.calmar_ratio >= 1.5 ? 'text-green-400' : 'text-yellow-400', icon: <Award className="w-4 h-4" /> },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {metrics.map((m) => (
        <div key={m.label} className="bg-gray-900/50 border border-gray-800 rounded-lg p-3">
          <div className="flex items-center gap-2 text-gray-400 text-xs mb-1">
            {m.icon}
            {m.label}
          </div>
          <div className={`text-lg font-bold font-mono ${m.color}`}>
            {m.value}
          </div>
        </div>
      ))}
    </div>
  )
}

// ==============================================================================
// EQUITY CURVE (SIMPLE SVG)
// ==============================================================================

function SimpleEquityCurve({ data }: { data: number[] }) {
  if (!data || data.length < 2) return null

  const width = 800
  const height = 200
  const padding = 20
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1

  const points = data.map((v, i) => {
    const x = padding + (i / (data.length - 1)) * (width - 2 * padding)
    const y = height - padding - ((v - min) / range) * (height - 2 * padding)
    return `${x},${y}`
  }).join(' ')

  // Build fill polygon (area under the curve)
  const startX = padding
  const endX = padding + ((data.length - 1) / (data.length - 1)) * (width - 2 * padding)
  const bottomY = height - padding
  const fillPoints = `${startX},${bottomY} ${points} ${endX},${bottomY}`

  const isPositive = data[data.length - 1] >= data[0]

  return (
    <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
      <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
        <TrendingUp className="w-4 h-4 text-blue-400" />
        Equity Curve
      </h3>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" preserveAspectRatio="none">
        <polygon
          points={fillPoints}
          fill={isPositive ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)'}
        />
        <polyline
          points={points}
          fill="none"
          stroke={isPositive ? '#22c55e' : '#ef4444'}
          strokeWidth="2"
        />
        {/* Start and end labels */}
        <text x={padding} y={height - 3} fill="#6b7280" fontSize="10" textAnchor="start">
          {formatCurrency(data[0])}
        </text>
        <text x={width - padding} y={height - 3} fill="#6b7280" fontSize="10" textAnchor="end">
          {formatCurrency(data[data.length - 1])}
        </text>
      </svg>
    </div>
  )
}

// ==============================================================================
// MAIN PAGE COMPONENT
// ==============================================================================

export default function FortressBacktestScorecardPage() {
  const sidebarPadding = useSidebarPadding()
  const { addToast } = useToast()
  const { data: scorecardResp, error, isLoading, mutate } = useFortressScorecard()
  const [saving, setSaving] = useState(false)

  const brand = BOT_BRANDS.FORTRESS

  const scorecard: ScorecardData | null = scorecardResp?.data || null

  const handleRefresh = async () => {
    await mutate()
    addToast({ type: 'success', title: 'Refreshed', message: 'Scorecard recomputed' })
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/api/fortress/backtest/scorecard/save`, {
        method: 'POST',
      })
      const data = await response.json()
      if (data.success) {
        addToast({ type: 'success', title: 'Saved', message: data.data?.message || 'Scorecard saved to database' })
      } else {
        addToast({ type: 'error', title: 'Save Failed', message: data.error || 'Failed to save scorecard' })
      }
    } catch {
      addToast({ type: 'error', title: 'Save Failed', message: 'Network error saving scorecard' })
    } finally {
      setSaving(false)
    }
  }

  if (isLoading) {
    return (
      <>
        <Navigation />
        <div className="flex items-center justify-center h-screen">
          <LoadingState message="Computing FORTRESS Scorecard..." />
        </div>
      </>
    )
  }

  // Group checks by category
  const cat1Checks = scorecard?.checks?.filter(c => c.category === 'DOES IT MAKE MONEY?') || []
  const cat2Checks = scorecard?.checks?.filter(c => c.category === 'IS THE EDGE REAL?') || []
  const cat3Checks = scorecard?.checks?.filter(c => c.category === 'SURVIVE THE BAD TIMES?') || []

  return (
    <>
      <Navigation />
      <main className={`min-h-screen bg-black text-white px-4 pb-4 md:px-6 md:pb-6 pt-24 transition-all duration-300 ${sidebarPadding}`}>
        <div className="max-w-7xl mx-auto space-y-6">

          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-white flex items-center gap-3">
                <Shield className={`w-7 h-7 ${brand.primaryText}`} />
                FORTRESS 25-Stat Profitability Scorecard
              </h1>
              <p className="text-gray-400 text-sm mt-1">
                Comprehensive backtest analysis from live trade history
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleSave}
                disabled={saving || !scorecard}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm disabled:opacity-50 transition-colors"
              >
                {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Award className="w-4 h-4" />}
                Save Snapshot
              </button>
              <button
                onClick={handleRefresh}
                className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg text-sm transition-colors"
              >
                <RefreshCw className="w-4 h-4" />
                Refresh
              </button>
            </div>
          </div>

          {/* Error state */}
          {error && (
            <div className="bg-red-900/30 border border-red-500/50 rounded-lg p-4 text-red-400">
              Failed to load scorecard: {error.message || 'Unknown error'}
            </div>
          )}

          {/* No data state */}
          {scorecard && scorecard.verdict === 'NO_DATA' && (
            <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-8 text-center">
              <AlertTriangle className="w-12 h-12 text-yellow-400 mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-white mb-2">No Trade History</h2>
              <p className="text-gray-400">
                FORTRESS needs closed trades to compute the scorecard.
                The scorecard will populate as FORTRESS completes trades.
              </p>
            </div>
          )}

          {/* Scorecard content */}
          {scorecard && scorecard.verdict !== 'NO_DATA' && (
            <>
              {/* Verdict Banner */}
              <VerdictBanner data={scorecard} />

              {/* Score Ring + Key Metrics */}
              <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
                <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6 flex flex-col items-center justify-center">
                  <ScoreRing passed={scorecard.passed_checks} total={scorecard.total_checks} />
                  <div className="text-gray-400 text-sm mt-3">Overall Score</div>
                  <div className={`text-sm font-bold mt-1 ${
                    getVerdictColor(scorecard.verdict).text
                  }`}>
                    {getVerdictLabel(scorecard.verdict)}
                  </div>
                </div>
                <div className="lg:col-span-3">
                  <KeyMetricsGrid data={scorecard} />
                </div>
              </div>

              {/* Equity Curve */}
              {scorecard.equity_curve && scorecard.equity_curve.length > 2 && (
                <SimpleEquityCurve data={scorecard.equity_curve} />
              )}

              {/* Category 1: Does It Make Money? */}
              <CategoryCard
                title="Category 1: Does It Make Money?"
                icon={<DollarSign className="w-5 h-5 text-green-400" />}
                checks={cat1Checks}
              />

              {/* Category 2: Is The Edge Real? */}
              <CategoryCard
                title="Category 2: Is The Edge Real?"
                icon={<BarChart3 className="w-5 h-5 text-blue-400" />}
                checks={cat2Checks}
              />

              {/* Category 3: Survive The Bad Times? */}
              <CategoryCard
                title="Category 3: Survive The Bad Times?"
                icon={<Shield className="w-5 h-5 text-red-400" />}
                checks={cat3Checks}
              />

              {/* Category 4: VIX Regime Robustness */}
              {scorecard.vix_regimes && scorecard.vix_regimes.length > 0 && (
                <VixRegimeTable
                  regimes={scorecard.vix_regimes}
                  worstMonth={scorecard.worst_month}
                  worstMonthPnl={scorecard.worst_month_pnl}
                  worstMonthPct={scorecard.worst_month_pct}
                  worstMonthPassed={scorecard.worst_month_passed}
                />
              )}

              {/* Additional Stats */}
              <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
                <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-purple-400" />
                  Detailed Statistics
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <span className="text-gray-500 text-xs block">Starting Capital</span>
                    <span className="text-white font-mono">{formatCurrency(scorecard.initial_capital)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 text-xs block">Ending Equity</span>
                    <span className="text-green-400 font-mono">{formatCurrency(scorecard.ending_equity)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 text-xs block">Avg Win</span>
                    <span className="text-green-400 font-mono">{formatCurrency(scorecard.avg_pnl > 0 ? scorecard.avg_pnl : 0)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 text-xs block">Avg Trade P&L</span>
                    <span className={`font-mono ${scorecard.avg_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {formatCurrency(scorecard.avg_pnl)}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500 text-xs block">t-Statistic</span>
                    <span className="text-white font-mono">{scorecard.t_statistic.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 text-xs block">Sortino Ratio</span>
                    <span className="text-white font-mono">{scorecard.sortino_ratio.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 text-xs block">P&L Skewness</span>
                    <span className={`font-mono ${scorecard.skewness > -0.5 ? 'text-green-400' : 'text-red-400'}`}>
                      {scorecard.skewness.toFixed(2)}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500 text-xs block">95% VaR</span>
                    <span className="text-red-400 font-mono">{formatCurrency(scorecard.var_95)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 text-xs block">Max Consec. Losses</span>
                    <span className="text-white font-mono">{scorecard.max_consecutive_losses}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 text-xs block">Max DD Duration</span>
                    <span className="text-white font-mono">{scorecard.max_dd_duration_trades} trades</span>
                  </div>
                  <div>
                    <span className="text-gray-500 text-xs block">Largest Loss</span>
                    <span className="text-red-400 font-mono">{formatCurrency(scorecard.largest_single_loss)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 text-xs block">Expected Value</span>
                    <span className={`font-mono ${scorecard.expected_value >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {formatCurrency(scorecard.expected_value)}/trade
                    </span>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </main>
    </>
  )
}
