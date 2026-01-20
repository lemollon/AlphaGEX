'use client'

/**
 * HYPERION Enhanced Features Components
 *
 * Additional visualization components for HYPERION (Weekly Gamma):
 * - Weekly Setup Scanner
 * - Multi-Day Gamma Trend
 * - OPEX Week Analysis
 */

import { useState, useEffect } from 'react'
import {
  Calendar,
  TrendingUp,
  TrendingDown,
  BarChart3,
  AlertTriangle,
  CheckCircle2,
  Clock,
  ChevronDown,
  ChevronUp,
  Target,
  Shield,
  Activity,
  Percent,
  DollarSign,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Zap,
  Sun
} from 'lucide-react'
import { api } from '@/lib/api'

// Types
interface WeeklySetup {
  setup_type: string
  expiration: string
  dte: number
  symbol: string
  description: string
  trade_idea: string
  confidence: number
  metrics: Record<string, number | string>
  risk_level: string
}

interface GammaTrendDay {
  date: string
  spot_price: number
  gamma_regime: string
  regime_changed: boolean
  total_net_gamma: number
  net_gamma_direction: string
  top_magnet: number | null
  magnet_migration: string | null
  likely_pin: number | null
  flip_point: number | null
  vix: number | null
  outcome_direction: string | null
  outcome_pct: number | null
}

interface OPEXAnalysis {
  symbol: string
  current_date: string
  monthly_opex: string
  days_to_opex: number
  is_opex_week: boolean
  opex_phase: string
  phase_description: string
  historical_opex_behavior: {
    sample_size: number
    avg_move_pct: number
    up_days: number
    down_days: number
    positive_gamma_days: number
    historical_data: Array<{
      date: string
      spot_price: number
      outcome_direction: string
      outcome_pct: number
    }>
  }
  recommendations: Array<{
    action: string
    priority: string
    reason: string
  }>
  trading_implications: string
}

// ============================================================================
// Weekly Setup Scanner Component
// ============================================================================

export function WeeklySetupScanner({ symbol = 'AAPL' }: { symbol?: string }) {
  const [setups, setSetups] = useState<WeeklySetup[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(true)

  useEffect(() => {
    const fetchSetups = async () => {
      try {
        const response = await api.get(`/api/hyperion/weekly-setups?symbol=${symbol}`)
        if (response.data?.success && response.data?.data?.setups) {
          setSetups(response.data.data.setups)
        }
      } catch (error) {
        console.error('Error fetching weekly setups:', error)
      } finally {
        setLoading(false)
      }
    }
    fetchSetups()
    const interval = setInterval(fetchSetups, 300000) // Refresh every 5 mins
    return () => clearInterval(interval)
  }, [symbol])

  if (loading) {
    return (
      <div className="bg-gray-800/50 rounded-xl p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/3 mb-3"></div>
        <div className="h-32 bg-gray-700 rounded"></div>
      </div>
    )
  }

  const setupColors: Record<string, string> = {
    'PREMIUM_CRUSH': 'border-emerald-500/30 bg-emerald-500/5',
    'DIRECTIONAL_BREAKOUT': 'border-rose-500/30 bg-rose-500/5',
    'CALENDAR_PLAY': 'border-blue-500/30 bg-blue-500/5',
    'EARNINGS_SETUP': 'border-yellow-500/30 bg-yellow-500/5'
  }

  const setupIcons: Record<string, React.ReactNode> = {
    'PREMIUM_CRUSH': <DollarSign className="w-4 h-4 text-emerald-400" />,
    'DIRECTIONAL_BREAKOUT': <Zap className="w-4 h-4 text-rose-400" />,
    'CALENDAR_PLAY': <Calendar className="w-4 h-4 text-blue-400" />,
    'EARNINGS_SETUP': <AlertTriangle className="w-4 h-4 text-yellow-400" />
  }

  return (
    <div className="bg-gray-800/50 rounded-xl border border-gray-700 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-gray-800/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Target className="w-5 h-5 text-purple-400" />
          <span className="font-bold">Weekly Setup Scanner</span>
          {setups.length > 0 && (
            <span className="text-xs bg-purple-500/20 text-purple-400 px-2 py-0.5 rounded">
              {setups.length} setups found
            </span>
          )}
        </div>
        {expanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
      </button>

      {expanded && (
        <div className="p-4 pt-0 space-y-3">
          {setups.length === 0 ? (
            <p className="text-sm text-gray-500">No active setups detected. Market may be in consolidation.</p>
          ) : (
            setups.map((setup, idx) => (
              <div
                key={idx}
                className={`p-3 rounded-lg border ${setupColors[setup.setup_type] || 'border-gray-600 bg-gray-700/30'}`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    {setupIcons[setup.setup_type]}
                    <span className="font-bold">{setup.setup_type.replace(/_/g, ' ')}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-400">{setup.dte} DTE</span>
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      setup.risk_level === 'LOW' ? 'bg-emerald-500/20 text-emerald-400' :
                      setup.risk_level === 'HIGH' ? 'bg-rose-500/20 text-rose-400' :
                      'bg-yellow-500/20 text-yellow-400'
                    }`}>
                      {setup.risk_level}
                    </span>
                  </div>
                </div>

                <p className="text-sm text-gray-300 mb-2">{setup.description}</p>

                <div className="flex items-center justify-between">
                  <div className="text-sm">
                    <span className="text-gray-500">Trade: </span>
                    <span className="text-white">{setup.trade_idea}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Percent className="w-3 h-3 text-gray-500" />
                    <span className="text-sm font-medium">{(setup.confidence * 100).toFixed(0)}%</span>
                  </div>
                </div>

                <div className="mt-2 pt-2 border-t border-gray-700/50 text-xs text-gray-400">
                  Exp: {setup.expiration}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Multi-Day Gamma Trend Component
// ============================================================================

export function GammaTrend({ symbol = 'AAPL', days = 5 }: { symbol?: string, days?: number }) {
  const [trend, setTrend] = useState<{
    trend_data: GammaTrendDay[]
    summary: {
      overall_trend: string
      magnet_trend: string
      regime_changes: number
      positive_gamma_days: number
      negative_gamma_days: number
    }
    implication: string
  } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchTrend = async () => {
      try {
        const response = await api.get(`/api/hyperion/gamma-trend?symbol=${symbol}&days=${days}`)
        if (response.data?.success) {
          setTrend(response.data.data)
        }
      } catch (error) {
        console.error('Error fetching gamma trend:', error)
      } finally {
        setLoading(false)
      }
    }
    fetchTrend()
  }, [symbol, days])

  if (loading) {
    return (
      <div className="bg-gray-800/50 rounded-xl p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/3 mb-3"></div>
        <div className="h-24 bg-gray-700 rounded"></div>
      </div>
    )
  }

  if (!trend || trend.trend_data.length === 0) {
    return (
      <div className="bg-gray-800/50 rounded-xl p-4 border border-gray-700">
        <div className="flex items-center gap-2 mb-2">
          <BarChart3 className="w-5 h-5 text-blue-400" />
          <span className="font-bold">Multi-Day Gamma Trend</span>
        </div>
        <p className="text-sm text-gray-500">Collecting trend data. Check back later.</p>
      </div>
    )
  }

  const trendColors: Record<string, string> = {
    'BULLISH_GAMMA': 'text-emerald-400',
    'BEARISH_GAMMA': 'text-rose-400',
    'MIXED': 'text-yellow-400'
  }

  const magnetColors: Record<string, string> = {
    'MIGRATING_HIGHER': 'text-emerald-400',
    'MIGRATING_LOWER': 'text-rose-400',
    'STABLE': 'text-gray-400'
  }

  return (
    <div className="bg-gray-800/50 rounded-xl p-4 border border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-blue-400" />
          <span className="font-bold">Multi-Day Gamma Trend</span>
        </div>
        <span className="text-xs text-gray-500">{trend.trend_data.length} days</span>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="text-center p-2 bg-gray-900/50 rounded-lg">
          <div className="text-xs text-gray-500 mb-1">Trend</div>
          <div className={`text-sm font-bold ${trendColors[trend.summary.overall_trend] || 'text-gray-300'}`}>
            {trend.summary.overall_trend.replace(/_/g, ' ')}
          </div>
        </div>
        <div className="text-center p-2 bg-gray-900/50 rounded-lg">
          <div className="text-xs text-gray-500 mb-1">Magnets</div>
          <div className={`text-sm font-bold ${magnetColors[trend.summary.magnet_trend] || 'text-gray-300'}`}>
            {trend.summary.magnet_trend.replace(/_/g, ' ')}
          </div>
        </div>
        <div className="text-center p-2 bg-gray-900/50 rounded-lg">
          <div className="text-xs text-gray-500 mb-1">Regime Changes</div>
          <div className={`text-sm font-bold ${
            trend.summary.regime_changes >= 3 ? 'text-rose-400' :
            trend.summary.regime_changes >= 1 ? 'text-yellow-400' :
            'text-emerald-400'
          }`}>
            {trend.summary.regime_changes}
          </div>
        </div>
      </div>

      {/* Daily Trend Bars */}
      <div className="flex items-end gap-1 h-16 mb-2">
        {trend.trend_data.map((day, idx) => {
          const maxGamma = Math.max(...trend.trend_data.map(d => Math.abs(d.total_net_gamma)))
          const height = maxGamma > 0 ? (Math.abs(day.total_net_gamma) / maxGamma) * 100 : 0
          return (
            <div key={idx} className="flex-1 flex flex-col items-center">
              <div
                className={`w-full rounded-t ${
                  day.net_gamma_direction === 'POSITIVE' ? 'bg-emerald-500/60' : 'bg-rose-500/60'
                } ${day.regime_changed ? 'ring-2 ring-yellow-500' : ''}`}
                style={{ height: `${Math.max(height, 10)}%` }}
                title={`${day.date}: ${day.net_gamma_direction}`}
              />
            </div>
          )
        })}
      </div>

      <div className="flex justify-between text-xs text-gray-500 mb-4">
        {trend.trend_data.map((day, idx) => (
          <span key={idx} className="flex-1 text-center">
            {new Date(day.date).toLocaleDateString('en-US', { weekday: 'short' })}
          </span>
        ))}
      </div>

      {/* Implication */}
      <div className="p-3 bg-gray-900/50 rounded-lg">
        <div className="text-xs text-gray-500 mb-1">Trading Implication</div>
        <div className="text-sm text-gray-300">{trend.implication}</div>
      </div>
    </div>
  )
}

// ============================================================================
// OPEX Week Analysis Component
// ============================================================================

export function OPEXAnalysisPanel({ symbol = 'AAPL' }: { symbol?: string }) {
  const [opex, setOpex] = useState<OPEXAnalysis | null>(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(true)

  useEffect(() => {
    const fetchOpex = async () => {
      try {
        const response = await api.get(`/api/hyperion/opex-analysis?symbol=${symbol}`)
        if (response.data?.success) {
          setOpex(response.data.data)
        }
      } catch (error) {
        console.error('Error fetching OPEX analysis:', error)
      } finally {
        setLoading(false)
      }
    }
    fetchOpex()
  }, [symbol])

  if (loading) {
    return (
      <div className="bg-gray-800/50 rounded-xl p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/3 mb-3"></div>
        <div className="h-32 bg-gray-700 rounded"></div>
      </div>
    )
  }

  if (!opex) return null

  const phaseColors: Record<string, string> = {
    'OPEX_DAY': 'bg-rose-500/10 border-rose-500/30',
    'OPEX_WEEK_LATE': 'bg-yellow-500/10 border-yellow-500/30',
    'OPEX_WEEK_EARLY': 'bg-emerald-500/10 border-emerald-500/30',
    'PRE_OPEX': 'bg-blue-500/10 border-blue-500/30',
    'POST_OPEX': 'bg-purple-500/10 border-purple-500/30',
    'MID_CYCLE': 'bg-gray-700/30 border-gray-600/30'
  }

  const priorityColors: Record<string, string> = {
    'HIGH': 'text-rose-400',
    'MEDIUM': 'text-yellow-400',
    'LOW': 'text-gray-400'
  }

  return (
    <div className={`rounded-xl border overflow-hidden ${phaseColors[opex.opex_phase] || 'bg-gray-800/50 border-gray-700'}`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-gray-800/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Calendar className="w-5 h-5 text-orange-400" />
          <span className="font-bold">OPEX Week Analysis</span>
          {opex.is_opex_week && (
            <span className="text-xs bg-orange-500/20 text-orange-400 px-2 py-0.5 rounded animate-pulse">
              OPEX WEEK
            </span>
          )}
        </div>
        {expanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
      </button>

      {expanded && (
        <div className="p-4 pt-0 space-y-4">
          {/* Phase Info */}
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs text-gray-500 mb-1">Current Phase</div>
              <div className="text-lg font-bold">{opex.opex_phase.replace(/_/g, ' ')}</div>
            </div>
            <div className="text-right">
              <div className="text-xs text-gray-500 mb-1">Days to OPEX</div>
              <div className={`text-2xl font-bold ${
                opex.days_to_opex <= 0 ? 'text-rose-400' :
                opex.days_to_opex <= 2 ? 'text-yellow-400' :
                'text-emerald-400'
              }`}>
                {opex.days_to_opex <= 0 ? 'TODAY' : opex.days_to_opex}
              </div>
            </div>
          </div>

          <p className="text-sm text-gray-300">{opex.phase_description}</p>

          {/* Historical Stats */}
          {opex.historical_opex_behavior.sample_size > 0 && (
            <div className="grid grid-cols-4 gap-2 p-3 bg-gray-900/50 rounded-lg">
              <div className="text-center">
                <div className="text-xs text-gray-500">Avg Move</div>
                <div className="text-sm font-bold">{opex.historical_opex_behavior.avg_move_pct}%</div>
              </div>
              <div className="text-center">
                <div className="text-xs text-gray-500">Up Days</div>
                <div className="text-sm font-bold text-emerald-400">{opex.historical_opex_behavior.up_days}</div>
              </div>
              <div className="text-center">
                <div className="text-xs text-gray-500">Down Days</div>
                <div className="text-sm font-bold text-rose-400">{opex.historical_opex_behavior.down_days}</div>
              </div>
              <div className="text-center">
                <div className="text-xs text-gray-500">+γ Days</div>
                <div className="text-sm font-bold">{opex.historical_opex_behavior.positive_gamma_days}</div>
              </div>
            </div>
          )}

          {/* Recommendations */}
          <div>
            <div className="text-xs text-gray-500 mb-2 uppercase tracking-wide">Recommendations</div>
            <div className="space-y-2">
              {opex.recommendations.map((rec, idx) => (
                <div key={idx} className="flex items-start gap-2 p-2 bg-gray-900/30 rounded">
                  <span className={`text-xs font-bold ${priorityColors[rec.priority]}`}>
                    [{rec.priority}]
                  </span>
                  <div>
                    <div className="text-sm font-medium">{rec.action}</div>
                    <div className="text-xs text-gray-500">{rec.reason}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Trading Implication */}
          <div className="p-3 bg-gray-900/50 rounded-lg border border-gray-700/50">
            <div className="flex items-center gap-2 mb-1">
              <Activity className="w-4 h-4 text-gray-500" />
              <span className="text-xs text-gray-500">Trading Implication</span>
            </div>
            <div className="text-sm text-white">{opex.trading_implications}</div>
          </div>

          {/* OPEX Date */}
          <div className="text-xs text-gray-500 text-center">
            Monthly OPEX: {opex.monthly_opex}
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Combined Panel for HYPERION Page
// ============================================================================

export function HyperionEnhancedPanel({ symbol = 'AAPL' }: { symbol?: string }) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div className="bg-gray-900/50 rounded-xl border border-gray-700 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-gray-800/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Sun className="w-5 h-5 text-orange-400" />
          <span className="font-bold text-lg">Enhanced Analysis</span>
          <span className="text-xs bg-orange-500/20 text-orange-400 px-2 py-0.5 rounded">NEW</span>
        </div>
        {expanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
      </button>

      {expanded && (
        <div className="p-4 pt-0 space-y-4">
          <WeeklySetupScanner symbol={symbol} />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <GammaTrend symbol={symbol} />
            <OPEXAnalysisPanel symbol={symbol} />
          </div>
        </div>
      )}
    </div>
  )
}
