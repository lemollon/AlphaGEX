'use client'

/**
 * ARGUS Enhanced Features Components
 *
 * Additional visualization components for ARGUS (0DTE):
 * - Trade Setup Detector
 * - Optimal Strike Recommendations
 * - Historical Pattern Outcomes
 * - Pin Accuracy Tracker
 * - Intraday Gamma Decay
 */

import { useState, useEffect } from 'react'
import {
  Target,
  TrendingUp,
  TrendingDown,
  History,
  CheckCircle2,
  AlertTriangle,
  BarChart3,
  Activity,
  Zap,
  Shield,
  DollarSign,
  Percent,
  Clock,
  ChevronDown,
  ChevronUp,
  RefreshCw
} from 'lucide-react'
import { apiClient } from '@/lib/api'

// Types
interface TradeSetup {
  setup_type: string
  description: string
  confidence: number
  entry_zones: { call_strikes: number[], put_strikes: number[] }
  current_metrics: {
    gamma_regime: string
    pin_probability: number
    distance_to_flip_pct: number
    distance_to_wall_pct: number
  }
  trade_ideas: string[]
  risk_level: string
}

interface OptimalStrike {
  strike: number
  side: string
  probability: number
  expected_value: number
  risk_reward: number
  gamma_exposure: number
  distance_from_spot_pct: number
}

interface PatternOutcome {
  pattern_type: string
  sample_size: number
  win_rate: number
  avg_return: number
  best_case: number
  worst_case: number
  current_similarity: number
}

interface PinAccuracy {
  period: string
  predictions: number
  accurate_within_1_pct: number
  accurate_within_0_5_pct: number
  accuracy_rate: number
  avg_distance: number
}

interface GammaDecayPoint {
  time_label: string
  gamma_magnitude: number
  regime: string
  trading_implication: string
}

// ============================================================================
// Trade Setup Detector Component
// ============================================================================

export function TradeSetupDetector({ symbol = 'SPY' }: { symbol?: string }) {
  const [setup, setSetup] = useState<TradeSetup | null>(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    const fetchSetup = async () => {
      try {
        const res = await fetch(`/api/argus/trade-setups?symbol=${symbol}`)
        const data = await res.json()
        if (data.success) {
          setSetup(data.data)
        }
      } catch (error) {
        console.error('Error fetching trade setup:', error)
      } finally {
        setLoading(false)
      }
    }
    fetchSetup()
    const interval = setInterval(fetchSetup, 60000) // Refresh every minute
    return () => clearInterval(interval)
  }, [symbol])

  if (loading) {
    return (
      <div className="bg-gray-800/50 rounded-xl p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/3 mb-3"></div>
        <div className="h-8 bg-gray-700 rounded w-1/2"></div>
      </div>
    )
  }

  if (!setup) return null

  const setupColors: Record<string, string> = {
    'IC_SAFE_ZONE': 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
    'BREAKOUT_WARNING': 'bg-rose-500/10 border-rose-500/30 text-rose-400',
    'FADE_THE_MOVE': 'bg-blue-500/10 border-blue-500/30 text-blue-400',
    'PIN_SETUP': 'bg-purple-500/10 border-purple-500/30 text-purple-400'
  }

  const colorClass = setupColors[setup.setup_type] || 'bg-gray-700/50 border-gray-600 text-gray-300'

  return (
    <div className={`rounded-xl p-4 border-2 ${colorClass}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Target className="w-5 h-5" />
          <span className="font-bold text-lg">{setup.setup_type.replace(/_/g, ' ')}</span>
          <span className={`px-2 py-0.5 rounded text-xs ${
            setup.risk_level === 'LOW' ? 'bg-emerald-500/20 text-emerald-400' :
            setup.risk_level === 'HIGH' ? 'bg-rose-500/20 text-rose-400' :
            'bg-yellow-500/20 text-yellow-400'
          }`}>
            {setup.risk_level} RISK
          </span>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-gray-400 hover:text-white"
        >
          {expanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
        </button>
      </div>

      <p className="text-sm text-gray-300 mb-3">{setup.description}</p>

      <div className="flex items-center gap-4 mb-3">
        <div className="flex items-center gap-1">
          <Percent className="w-4 h-4 text-gray-500" />
          <span className="text-sm">{(setup.confidence * 100).toFixed(0)}% confidence</span>
        </div>
        <div className="flex items-center gap-1">
          <Activity className="w-4 h-4 text-gray-500" />
          <span className="text-sm">{setup.current_metrics.gamma_regime} regime</span>
        </div>
      </div>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-gray-700">
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <div className="text-xs text-gray-500 mb-1">Pin Probability</div>
              <div className="text-lg font-bold">{setup.current_metrics.pin_probability.toFixed(0)}%</div>
            </div>
            <div>
              <div className="text-xs text-gray-500 mb-1">Distance to Flip</div>
              <div className="text-lg font-bold">{setup.current_metrics.distance_to_flip_pct.toFixed(2)}%</div>
            </div>
          </div>

          <div className="mb-4">
            <div className="text-xs text-gray-500 mb-2">Entry Zones</div>
            <div className="flex gap-4">
              <div>
                <span className="text-xs text-emerald-400">Call Strikes: </span>
                <span className="text-sm">{setup.entry_zones.call_strikes.join(', ')}</span>
              </div>
              <div>
                <span className="text-xs text-rose-400">Put Strikes: </span>
                <span className="text-sm">{setup.entry_zones.put_strikes.join(', ')}</span>
              </div>
            </div>
          </div>

          <div>
            <div className="text-xs text-gray-500 mb-2">Trade Ideas</div>
            <ul className="text-sm space-y-1">
              {setup.trade_ideas.map((idea, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <Zap className="w-3 h-3 mt-1 text-yellow-400 flex-shrink-0" />
                  {idea}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Optimal Strike Recommendations Component
// ============================================================================

export function OptimalStrikes({ symbol = 'SPY' }: { symbol?: string }) {
  const [strikes, setStrikes] = useState<{ calls: OptimalStrike[], puts: OptimalStrike[] } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchStrikes = async () => {
      try {
        const res = await fetch(`/api/argus/optimal-strikes?symbol=${symbol}`)
        const data = await res.json()
        if (data.success) {
          setStrikes(data.data)
        }
      } catch (error) {
        console.error('Error fetching optimal strikes:', error)
      } finally {
        setLoading(false)
      }
    }
    fetchStrikes()
    const interval = setInterval(fetchStrikes, 60000)
    return () => clearInterval(interval)
  }, [symbol])

  if (loading) {
    return (
      <div className="bg-gray-800/50 rounded-xl p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/3 mb-3"></div>
        <div className="h-20 bg-gray-700 rounded"></div>
      </div>
    )
  }

  if (!strikes) return null

  const StrikeRow = ({ strike, color }: { strike: OptimalStrike, color: string }) => (
    <div className={`flex items-center justify-between p-2 rounded ${color}`}>
      <div className="flex items-center gap-3">
        <span className="font-bold text-lg">${strike.strike}</span>
        <span className={`text-xs px-1.5 py-0.5 rounded ${
          strike.side === 'CALL' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
        }`}>
          {strike.side}
        </span>
      </div>
      <div className="flex items-center gap-4 text-sm">
        <div title="Probability">
          <span className="text-gray-500">P: </span>
          <span className="font-medium">{strike.probability.toFixed(0)}%</span>
        </div>
        <div title="Risk/Reward">
          <span className="text-gray-500">R/R: </span>
          <span className="font-medium">{strike.risk_reward.toFixed(1)}</span>
        </div>
        <div title="Distance from Spot">
          <span className="text-gray-500">{strike.distance_from_spot_pct.toFixed(1)}% away</span>
        </div>
      </div>
    </div>
  )

  return (
    <div className="bg-gray-800/50 rounded-xl p-4 border border-gray-700">
      <div className="flex items-center gap-2 mb-4">
        <DollarSign className="w-5 h-5 text-green-400" />
        <span className="font-bold">Optimal Strikes for Iron Condor</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <div className="text-xs text-emerald-400 mb-2 uppercase tracking-wide">Call Side (Short)</div>
          <div className="space-y-2">
            {strikes.calls.slice(0, 3).map((s, idx) => (
              <StrikeRow key={idx} strike={s} color="bg-emerald-500/5" />
            ))}
          </div>
        </div>
        <div>
          <div className="text-xs text-rose-400 mb-2 uppercase tracking-wide">Put Side (Short)</div>
          <div className="space-y-2">
            {strikes.puts.slice(0, 3).map((s, idx) => (
              <StrikeRow key={idx} strike={s} color="bg-rose-500/5" />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Historical Pattern Outcomes Component
// ============================================================================

export function PatternOutcomes({ symbol = 'SPY' }: { symbol?: string }) {
  const [patterns, setPatterns] = useState<PatternOutcome[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchPatterns = async () => {
      try {
        const res = await fetch(`/api/argus/pattern-outcomes?symbol=${symbol}`)
        const data = await res.json()
        if (data.success && data.data.patterns) {
          setPatterns(data.data.patterns)
        }
      } catch (error) {
        console.error('Error fetching patterns:', error)
      } finally {
        setLoading(false)
      }
    }
    fetchPatterns()
  }, [symbol])

  if (loading) {
    return (
      <div className="bg-gray-800/50 rounded-xl p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/3 mb-3"></div>
        <div className="h-16 bg-gray-700 rounded"></div>
      </div>
    )
  }

  if (patterns.length === 0) {
    return (
      <div className="bg-gray-800/50 rounded-xl p-4 border border-gray-700">
        <div className="flex items-center gap-2 mb-2">
          <History className="w-5 h-5 text-blue-400" />
          <span className="font-bold">Historical Patterns</span>
        </div>
        <p className="text-sm text-gray-500">Collecting pattern data. Check back later.</p>
      </div>
    )
  }

  return (
    <div className="bg-gray-800/50 rounded-xl p-4 border border-gray-700">
      <div className="flex items-center gap-2 mb-4">
        <History className="w-5 h-5 text-blue-400" />
        <span className="font-bold">Historical Pattern Outcomes</span>
      </div>

      <div className="space-y-3">
        {patterns.map((pattern, idx) => (
          <div key={idx} className="p-3 bg-gray-900/50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium">{pattern.pattern_type.replace(/_/g, ' ')}</span>
              <span className={`text-sm px-2 py-0.5 rounded ${
                pattern.win_rate >= 60 ? 'bg-emerald-500/20 text-emerald-400' :
                pattern.win_rate >= 50 ? 'bg-yellow-500/20 text-yellow-400' :
                'bg-rose-500/20 text-rose-400'
              }`}>
                {pattern.win_rate.toFixed(0)}% win rate
              </span>
            </div>
            <div className="grid grid-cols-4 gap-2 text-xs">
              <div>
                <span className="text-gray-500">Samples: </span>
                <span>{pattern.sample_size}</span>
              </div>
              <div>
                <span className="text-gray-500">Avg Return: </span>
                <span className={pattern.avg_return >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                  {pattern.avg_return >= 0 ? '+' : ''}{pattern.avg_return.toFixed(1)}%
                </span>
              </div>
              <div>
                <span className="text-gray-500">Best: </span>
                <span className="text-emerald-400">+{pattern.best_case.toFixed(1)}%</span>
              </div>
              <div>
                <span className="text-gray-500">Worst: </span>
                <span className="text-rose-400">{pattern.worst_case.toFixed(1)}%</span>
              </div>
            </div>
            <div className="mt-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500">Current Match</span>
                <span>{(pattern.current_similarity * 100).toFixed(0)}%</span>
              </div>
              <div className="h-1.5 bg-gray-700 rounded-full mt-1">
                <div
                  className="h-full bg-blue-500 rounded-full"
                  style={{ width: `${pattern.current_similarity * 100}%` }}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ============================================================================
// Pin Accuracy Tracker Component
// ============================================================================

export function PinAccuracyTracker({ symbol = 'SPY' }: { symbol?: string }) {
  const [accuracy, setAccuracy] = useState<PinAccuracy[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchAccuracy = async () => {
      try {
        const res = await fetch(`/api/argus/pin-accuracy?symbol=${symbol}`)
        const data = await res.json()
        if (data.success && data.data.accuracy_by_period) {
          setAccuracy(data.data.accuracy_by_period)
        }
      } catch (error) {
        console.error('Error fetching pin accuracy:', error)
      } finally {
        setLoading(false)
      }
    }
    fetchAccuracy()
  }, [symbol])

  if (loading) {
    return (
      <div className="bg-gray-800/50 rounded-xl p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/3 mb-3"></div>
        <div className="h-12 bg-gray-700 rounded"></div>
      </div>
    )
  }

  return (
    <div className="bg-gray-800/50 rounded-xl p-4 border border-gray-700">
      <div className="flex items-center gap-2 mb-4">
        <CheckCircle2 className="w-5 h-5 text-purple-400" />
        <span className="font-bold">Pin Prediction Accuracy</span>
      </div>

      {accuracy.length === 0 ? (
        <p className="text-sm text-gray-500">Building accuracy metrics over time.</p>
      ) : (
        <div className="grid grid-cols-3 gap-3">
          {accuracy.map((period, idx) => (
            <div key={idx} className="text-center p-3 bg-gray-900/50 rounded-lg">
              <div className="text-xs text-gray-500 mb-1">{period.period}</div>
              <div className={`text-2xl font-bold ${
                period.accuracy_rate >= 70 ? 'text-emerald-400' :
                period.accuracy_rate >= 50 ? 'text-yellow-400' :
                'text-rose-400'
              }`}>
                {period.accuracy_rate.toFixed(0)}%
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {period.predictions} predictions
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Intraday Gamma Decay Component
// ============================================================================

export function GammaDecayVisualization({ symbol = 'SPY' }: { symbol?: string }) {
  const [decay, setDecay] = useState<{ periods: GammaDecayPoint[], current_period: string } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchDecay = async () => {
      try {
        const res = await fetch(`/api/argus/gamma-decay?symbol=${symbol}`)
        const data = await res.json()
        if (data.success) {
          setDecay(data.data)
        }
      } catch (error) {
        console.error('Error fetching gamma decay:', error)
      } finally {
        setLoading(false)
      }
    }
    fetchDecay()
    const interval = setInterval(fetchDecay, 300000) // Refresh every 5 mins
    return () => clearInterval(interval)
  }, [symbol])

  if (loading) {
    return (
      <div className="bg-gray-800/50 rounded-xl p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/3 mb-3"></div>
        <div className="h-24 bg-gray-700 rounded"></div>
      </div>
    )
  }

  if (!decay) return null

  const maxGamma = Math.max(...decay.periods.map(p => p.gamma_magnitude))

  return (
    <div className="bg-gray-800/50 rounded-xl p-4 border border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-cyan-400" />
          <span className="font-bold">Intraday Gamma Decay</span>
        </div>
        <span className="text-xs bg-cyan-500/20 text-cyan-400 px-2 py-0.5 rounded">
          Current: {decay.current_period}
        </span>
      </div>

      <div className="flex items-end gap-1 h-20 mb-3">
        {decay.periods.map((period, idx) => {
          const height = (period.gamma_magnitude / maxGamma) * 100
          const isCurrent = period.time_label === decay.current_period
          return (
            <div
              key={idx}
              className="flex-1 flex flex-col items-center"
            >
              <div
                className={`w-full rounded-t transition-all ${
                  isCurrent ? 'bg-cyan-500' :
                  period.regime === 'POSITIVE' ? 'bg-emerald-500/50' :
                  period.regime === 'NEGATIVE' ? 'bg-rose-500/50' :
                  'bg-gray-600/50'
                }`}
                style={{ height: `${height}%` }}
              />
            </div>
          )
        })}
      </div>

      <div className="flex justify-between text-xs text-gray-500">
        {decay.periods.map((period, idx) => (
          <span key={idx} className={period.time_label === decay.current_period ? 'text-cyan-400 font-bold' : ''}>
            {period.time_label}
          </span>
        ))}
      </div>

      {/* Current period implication */}
      {decay.periods.find(p => p.time_label === decay.current_period) && (
        <div className="mt-4 p-3 bg-gray-900/50 rounded-lg">
          <div className="text-xs text-gray-500 mb-1">Trading Implication</div>
          <div className="text-sm">
            {decay.periods.find(p => p.time_label === decay.current_period)?.trading_implication}
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Combined Panel for ARGUS Page
// ============================================================================

export function ArgusEnhancedPanel({ symbol = 'SPY' }: { symbol?: string }) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div className="bg-gray-900/50 rounded-xl border border-gray-700 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-gray-800/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Shield className="w-5 h-5 text-purple-400" />
          <span className="font-bold text-lg">Enhanced Analysis</span>
          <span className="text-xs bg-purple-500/20 text-purple-400 px-2 py-0.5 rounded">NEW</span>
        </div>
        {expanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
      </button>

      {expanded && (
        <div className="p-4 pt-0 space-y-4">
          <TradeSetupDetector symbol={symbol} />
          <OptimalStrikes symbol={symbol} />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <PatternOutcomes symbol={symbol} />
            <PinAccuracyTracker symbol={symbol} />
          </div>
          <GammaDecayVisualization symbol={symbol} />
        </div>
      )}
    </div>
  )
}
