'use client'

import { useState, useEffect, useCallback } from 'react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import {
  Search,
  TrendingUp,
  TrendingDown,
  Minus,
  Zap,
  Brain,
  Target,
  Activity,
  Clock,
  DollarSign,
  BarChart3,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  CheckCircle,
  Info,
  Loader2,
  X,
  Plus,
  History,
  Settings,
  Sparkles,
  Shield,
  AlertTriangle,
  TrendingUp as ArrowUp,
  TrendingDown as ArrowDown
} from 'lucide-react'

// ============================================================================
// TYPES
// ============================================================================

interface ApolloFeatures {
  symbol: string
  spot_price: number
  net_gex: number
  net_gex_normalized: number
  flip_point: number
  call_wall: number
  put_wall: number
  distance_to_flip_pct: number
  above_flip: boolean
  vix: number
  vix_percentile: number
  market_regime: string
  gex_regime: string
  atm_iv: number
  iv_rank: number
  put_call_ratio: number
  rsi_14: number
  macd_signal: string
}

interface ApolloPrediction {
  direction: string
  direction_confidence: number
  direction_probabilities: Record<string, number>
  magnitude: string
  magnitude_confidence: number
  timing: string
  timing_confidence: number
  ensemble_confidence: number
  is_ml_prediction: boolean
  model_version: string
}

interface ApolloStrategy {
  strategy_type: string
  symbol: string
  direction: string
  long_strike: number | null
  short_strike: number | null
  expiration: string
  dte: number
  entry_cost: number
  max_profit: number
  max_loss: number
  risk_reward_ratio: number
  probability_of_profit: number
  ml_confidence: number
  rule_confidence: number
  combined_confidence: number
  reasoning: string
  entry_trigger: string
  exit_target: string
  stop_loss: string
  position_delta: number
  position_theta: number
}

interface PinFactor {
  name: string
  score: number
  description: string
  is_bullish: boolean | null
}

interface TradingImplication {
  position_type: string
  outlook: string
  reasoning: string
  recommendation: string
}

interface PinRisk {
  score: number
  level: string
  gamma_regime: string
  gamma_regime_description: string
  long_call_outlook: string
  max_pain: number
  call_wall: number
  put_wall: number
  flip_point: number
  expected_range: {
    low: number
    high: number
    pct: number
  }
  days_to_expiry: number
  is_expiration_day: boolean
  pin_factors: PinFactor[]
  trading_implications: TradingImplication[]
  pin_breakers: string[]
  summary: string
}

interface ApolloScanResult {
  symbol: string
  timestamp: string
  scan_id: string
  features: ApolloFeatures | null
  prediction: ApolloPrediction | null
  strategies: ApolloStrategy[]
  market_regime: string
  gex_regime: string
  pin_risk: PinRisk | null
  data_quality_score: number
  warnings: string[]
}

interface ScanResponse {
  success: boolean
  scan_id: string
  results: ApolloScanResult[]
  vix_at_scan: number
  duration_ms: number
}

interface ModelPerformance {
  total_predictions_30d: number
  total_outcomes_30d: number
  direction_accuracy_7d: number
  direction_accuracy_30d: number
  magnitude_accuracy_30d: number
  strategy_win_rate: number
  models_loaded: boolean
  model_version: string
}

// ============================================================================
// HELPER COMPONENTS
// ============================================================================

function DirectionBadge({ direction, confidence }: { direction: string, confidence: number }) {
  const configs: Record<string, { icon: typeof TrendingUp, color: string, bg: string }> = {
    bullish: { icon: TrendingUp, color: 'text-green-400', bg: 'bg-green-500/20' },
    bearish: { icon: TrendingDown, color: 'text-red-400', bg: 'bg-red-500/20' },
    neutral: { icon: Minus, color: 'text-yellow-400', bg: 'bg-yellow-500/20' }
  }

  const config = configs[direction] || configs.neutral
  const Icon = config.icon

  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg ${config.bg}`}>
      <Icon className={`w-4 h-4 ${config.color}`} />
      <span className={`font-semibold capitalize ${config.color}`}>{direction}</span>
      <span className="text-xs text-gray-400">({(confidence * 100).toFixed(0)}%)</span>
    </div>
  )
}

function RegimeBadge({ regime, type }: { regime: string, type: 'market' | 'gex' }) {
  const marketColors: Record<string, string> = {
    low_vol: 'bg-blue-500/20 text-blue-400',
    normal: 'bg-green-500/20 text-green-400',
    elevated: 'bg-yellow-500/20 text-yellow-400',
    high_vol: 'bg-orange-500/20 text-orange-400',
    extreme: 'bg-red-500/20 text-red-400'
  }

  const gexColors: Record<string, string> = {
    strong_positive: 'bg-green-500/20 text-green-400',
    positive: 'bg-emerald-500/20 text-emerald-400',
    neutral: 'bg-gray-500/20 text-gray-400',
    negative: 'bg-orange-500/20 text-orange-400',
    strong_negative: 'bg-red-500/20 text-red-400'
  }

  const colors = type === 'market' ? marketColors : gexColors
  const colorClass = colors[regime] || 'bg-gray-500/20 text-gray-400'

  return (
    <span className={`px-2 py-1 rounded text-xs font-medium ${colorClass}`}>
      {regime.replace(/_/g, ' ').toUpperCase()}
    </span>
  )
}

function ConfidenceMeter({ value, label }: { value: number, label: string }) {
  const getColor = (v: number) => {
    if (v >= 75) return 'bg-green-500'
    if (v >= 60) return 'bg-yellow-500'
    if (v >= 45) return 'bg-orange-500'
    return 'bg-red-500'
  }

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-gray-400">{label}</span>
        <span className="font-mono">{value.toFixed(0)}%</span>
      </div>
      <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full ${getColor(value)} transition-all duration-500`}
          style={{ width: `${Math.min(100, value)}%` }}
        />
      </div>
    </div>
  )
}

// Strategy descriptions and win rate estimates
const strategyInfo: Record<string, { description: string, winRate: string, holdPeriod: string, bestFor: string }> = {
  BULL_CALL_SPREAD: {
    description: 'Limited risk bullish play. Buy lower strike call, sell higher strike call.',
    winRate: '55-65%',
    holdPeriod: '7-21 days',
    bestFor: 'Moderately bullish outlook with capped risk'
  },
  BEAR_PUT_SPREAD: {
    description: 'Limited risk bearish play. Buy higher strike put, sell lower strike put.',
    winRate: '55-65%',
    holdPeriod: '7-21 days',
    bestFor: 'Moderately bearish outlook with capped risk'
  },
  IRON_CONDOR: {
    description: 'Sell OTM call spread + OTM put spread. Profit from low volatility and range-bound price.',
    winRate: '70-80%',
    holdPeriod: '14-30 days',
    bestFor: 'High positive GEX, low VIX, range-bound markets'
  },
  IRON_BUTTERFLY: {
    description: 'ATM straddle sale + OTM wing protection. Maximum profit at the strike price.',
    winRate: '65-75%',
    holdPeriod: '7-14 days',
    bestFor: 'Very low volatility, strong pinning action'
  },
  BULL_PUT_SPREAD: {
    description: 'Credit spread. Sell higher strike put, buy lower strike put. Profit if price stays above short strike.',
    winRate: '65-75%',
    holdPeriod: '14-30 days',
    bestFor: 'Bullish or neutral, want premium income'
  },
  BEAR_CALL_SPREAD: {
    description: 'Credit spread. Sell lower strike call, buy higher strike call. Profit if price stays below short strike.',
    winRate: '65-75%',
    holdPeriod: '14-30 days',
    bestFor: 'Bearish or neutral, want premium income'
  },
  LONG_CALL: {
    description: 'Buy a call option. Unlimited upside potential with limited downside (premium paid).',
    winRate: '40-50%',
    holdPeriod: '3-14 days',
    bestFor: 'Strong bullish conviction, expecting big move up'
  },
  LONG_PUT: {
    description: 'Buy a put option. Large profit potential if price drops significantly.',
    winRate: '40-50%',
    holdPeriod: '3-14 days',
    bestFor: 'Strong bearish conviction, expecting big move down'
  },
  LONG_STRADDLE: {
    description: 'Buy ATM call + ATM put. Profit from big moves in either direction.',
    winRate: '35-45%',
    holdPeriod: '1-7 days',
    bestFor: 'High expected volatility, earnings, events'
  }
}

function StrategyCard({ strategy, expanded, onToggle }: {
  strategy: ApolloStrategy
  expanded: boolean
  onToggle: () => void
}) {
  const strategyColors: Record<string, string> = {
    BULL_CALL_SPREAD: 'border-green-500/50',
    BEAR_PUT_SPREAD: 'border-red-500/50',
    IRON_CONDOR: 'border-blue-500/50',
    IRON_BUTTERFLY: 'border-purple-500/50',
    BULL_PUT_SPREAD: 'border-emerald-500/50',
    BEAR_CALL_SPREAD: 'border-orange-500/50',
    LONG_CALL: 'border-green-400/50',
    LONG_PUT: 'border-red-400/50',
    LONG_STRADDLE: 'border-yellow-500/50'
  }

  const info = strategyInfo[strategy.strategy_type] || {
    description: 'Options strategy',
    winRate: 'N/A',
    holdPeriod: 'Varies',
    bestFor: 'Various market conditions'
  }

  const borderColor = strategyColors[strategy.strategy_type] || 'border-gray-500/50'

  // Calculate potential return
  const potentialReturn = strategy.max_profit > 0 && strategy.max_loss > 0
    ? ((strategy.max_profit / strategy.max_loss) * 100).toFixed(0)
    : 'N/A'

  return (
    <div className={`bg-background-card border-l-4 ${borderColor} rounded-lg overflow-hidden`}>
      <button
        onClick={onToggle}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-background-hover transition-colors"
      >
        <div className="flex items-center gap-3">
          <Target className="w-5 h-5 text-primary" />
          <div className="text-left">
            <div className="font-semibold">{strategy.strategy_type.replace(/_/g, ' ')}</div>
            <div className="text-xs text-gray-400">
              {strategy.long_strike && `Long: $${strategy.long_strike}`}
              {strategy.short_strike && ` / Short: $${strategy.short_strike}`}
              {strategy.dte > 0 && ` • ${strategy.dte} DTE`}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-sm font-mono text-green-400">
              {strategy.combined_confidence.toFixed(0)}% conf
            </div>
            <div className="text-xs text-gray-400">
              R:R {strategy.risk_reward_ratio.toFixed(2)} • WR ~{info.winRate}
            </div>
          </div>
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-gray-800">
          {/* Strategy Description */}
          <div className="pt-4 p-3 bg-primary/10 border border-primary/30 rounded-lg">
            <div className="text-sm text-primary font-medium mb-1">What is this?</div>
            <div className="text-sm text-gray-300">{info.description}</div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              <span className="px-2 py-1 bg-background rounded">Win Rate: {info.winRate}</span>
              <span className="px-2 py-1 bg-background rounded">Hold: {info.holdPeriod}</span>
            </div>
          </div>

          {/* Money Making Plan */}
          <div className="p-3 bg-green-500/10 border border-green-500/30 rounded-lg">
            <div className="text-sm text-green-400 font-semibold mb-2 flex items-center gap-2">
              <DollarSign className="w-4 h-4" />
              Money Making Plan
            </div>
            <div className="text-sm text-gray-300 space-y-1">
              <div>• <span className="text-white">Entry:</span> {strategy.entry_trigger || 'Enter at current market prices'}</div>
              <div>• <span className="text-white">Target:</span> {strategy.exit_target || `Take profit at 50% of max profit ($${(strategy.max_profit * 0.5).toFixed(0)})`}</div>
              <div>• <span className="text-white">Stop:</span> {strategy.stop_loss || `Close if loss exceeds $${(strategy.max_loss * 0.5).toFixed(0)}`}</div>
              <div>• <span className="text-white">Hold:</span> {info.holdPeriod}</div>
            </div>
          </div>

          {/* Key Metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-3 bg-background rounded-lg text-center">
              <div className="text-xs text-gray-400">Entry Cost</div>
              <div className="text-lg font-mono font-bold">${Math.abs(strategy.entry_cost).toFixed(0)}</div>
            </div>
            <div className="p-3 bg-background rounded-lg text-center">
              <div className="text-xs text-gray-400">Max Profit</div>
              <div className="text-lg font-mono font-bold text-green-400">${strategy.max_profit.toFixed(0)}</div>
            </div>
            <div className="p-3 bg-background rounded-lg text-center">
              <div className="text-xs text-gray-400">Max Loss</div>
              <div className="text-lg font-mono font-bold text-red-400">${strategy.max_loss.toFixed(0)}</div>
            </div>
            <div className="p-3 bg-background rounded-lg text-center">
              <div className="text-xs text-gray-400">Prob. Profit</div>
              <div className="text-lg font-mono font-bold">{(strategy.probability_of_profit * 100).toFixed(0)}%</div>
            </div>
          </div>

          {/* Greeks */}
          <div className="grid grid-cols-4 gap-4 text-sm">
            <div>
              <div className="text-xs text-gray-400">Delta</div>
              <div className={`font-mono ${strategy.position_delta > 0 ? 'text-green-400' : strategy.position_delta < 0 ? 'text-red-400' : 'text-gray-400'}`}>
                {strategy.position_delta.toFixed(2)}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-400">Theta</div>
              <div className={`font-mono ${strategy.position_theta > 0 ? 'text-green-400' : 'text-red-400'}`}>
                {strategy.position_theta.toFixed(2)}/day
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-400">ML Confidence</div>
              <div className="font-mono">{strategy.ml_confidence.toFixed(0)}%</div>
            </div>
            <div>
              <div className="text-xs text-gray-400">Rule Confidence</div>
              <div className="font-mono">{strategy.rule_confidence.toFixed(0)}%</div>
            </div>
          </div>

          {/* Reasoning */}
          <div className="p-3 bg-background-hover rounded-lg">
            <div className="text-xs text-gray-400 mb-1">Why this strategy?</div>
            <div className="text-sm">{strategy.reasoning}</div>
          </div>

          {/* Best For */}
          <div className="text-xs text-gray-400">
            <span className="text-primary">Best for:</span> {info.bestFor}
          </div>
        </div>
      )}
    </div>
  )
}

// Pin Risk Score Bar Component
function PinRiskScoreBar({ score, level }: { score: number, level: string }) {
  const getColor = (l: string) => {
    switch (l) {
      case 'high': return { bar: 'bg-red-500', text: 'text-red-400', bg: 'bg-red-500/20' }
      case 'moderate': return { bar: 'bg-orange-500', text: 'text-orange-400', bg: 'bg-orange-500/20' }
      case 'low_moderate': return { bar: 'bg-yellow-500', text: 'text-yellow-400', bg: 'bg-yellow-500/20' }
      default: return { bar: 'bg-green-500', text: 'text-green-400', bg: 'bg-green-500/20' }
    }
  }

  const colors = getColor(level)

  return (
    <div className="space-y-2">
      <div className="flex justify-between items-center">
        <span className="text-sm text-gray-400">Pin Risk Score</span>
        <span className={`font-mono font-bold ${colors.text}`}>{score}/100</span>
      </div>
      <div className="h-3 bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full ${colors.bar} transition-all duration-500`}
          style={{ width: `${score}%` }}
        />
      </div>
      <div className={`text-center text-sm font-semibold px-3 py-1 rounded ${colors.bg} ${colors.text}`}>
        {level.replace(/_/g, ' ').toUpperCase()} RISK
      </div>
    </div>
  )
}

// Pin Risk Card Component
function PinRiskCard({ pinRisk, symbol }: { pinRisk: PinRisk, symbol: string }) {
  const [expanded, setExpanded] = useState(false)

  const outlookConfig: Record<string, { icon: typeof AlertTriangle, color: string, bg: string, text: string }> = {
    dangerous: { icon: AlertTriangle, color: 'text-red-400', bg: 'bg-red-500/20', text: 'DANGEROUS - High pin risk' },
    challenging: { icon: AlertCircle, color: 'text-orange-400', bg: 'bg-orange-500/20', text: 'CHALLENGING - Moderate headwinds' },
    favorable: { icon: CheckCircle, color: 'text-green-400', bg: 'bg-green-500/20', text: 'FAVORABLE - Gamma supports moves' },
    neutral: { icon: Minus, color: 'text-yellow-400', bg: 'bg-yellow-500/20', text: 'NEUTRAL - No strong gamma bias' }
  }

  const outlook = outlookConfig[pinRisk.long_call_outlook] || outlookConfig.neutral
  const OutlookIcon = outlook.icon

  return (
    <div className="bg-background-card border border-gray-800 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full p-4 flex items-center justify-between hover:bg-background-hover transition-colors"
      >
        <div className="flex items-center gap-3">
          <Shield className={`w-5 h-5 ${pinRisk.score >= 60 ? 'text-red-400' : pinRisk.score >= 40 ? 'text-orange-400' : 'text-green-400'}`} />
          <div className="text-left">
            <div className="font-semibold">Pin Risk Analysis</div>
            <div className="text-xs text-gray-400">
              Score: {pinRisk.score}/100 • {pinRisk.gamma_regime.toUpperCase()} gamma
              {pinRisk.is_expiration_day && ' • EXPIRATION DAY'}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className={`flex items-center gap-1 px-2 py-1 rounded ${outlook.bg}`}>
            <OutlookIcon className={`w-4 h-4 ${outlook.color}`} />
            <span className={`text-xs font-medium ${outlook.color}`}>
              {pinRisk.long_call_outlook.toUpperCase()}
            </span>
          </div>
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </button>

      {expanded && (
        <div className="p-4 border-t border-gray-800 space-y-4">
          {/* Score Bar */}
          <PinRiskScoreBar score={pinRisk.score} level={pinRisk.level} />

          {/* Long Call Assessment */}
          <div className={`p-3 rounded-lg ${outlook.bg} border border-opacity-30`}>
            <div className={`font-semibold ${outlook.color} mb-1 flex items-center gap-2`}>
              <OutlookIcon className="w-4 h-4" />
              Long Calls: {outlook.text}
            </div>
            <div className="text-sm text-gray-300">
              {pinRisk.gamma_regime_description}
            </div>
          </div>

          {/* Key Levels */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="p-3 bg-background rounded-lg text-center">
              <div className="text-xs text-gray-400">Max Pain</div>
              <div className="text-lg font-mono font-bold text-yellow-400">${pinRisk.max_pain.toFixed(0)}</div>
            </div>
            <div className="p-3 bg-background rounded-lg text-center">
              <div className="text-xs text-gray-400">Call Wall</div>
              <div className="text-lg font-mono font-bold text-green-400">${pinRisk.call_wall.toFixed(0)}</div>
            </div>
            <div className="p-3 bg-background rounded-lg text-center">
              <div className="text-xs text-gray-400">Put Wall</div>
              <div className="text-lg font-mono font-bold text-red-400">${pinRisk.put_wall.toFixed(0)}</div>
            </div>
            <div className="p-3 bg-background rounded-lg text-center">
              <div className="text-xs text-gray-400">Gamma Flip</div>
              <div className="text-lg font-mono font-bold text-blue-400">${pinRisk.flip_point.toFixed(0)}</div>
            </div>
          </div>

          {/* Expected Range */}
          <div className="p-3 bg-background rounded-lg">
            <div className="text-xs text-gray-400 mb-2">Expected Price Range</div>
            <div className="flex items-center justify-between">
              <span className="font-mono text-red-400">${pinRisk.expected_range.low.toFixed(2)}</span>
              <div className="flex-1 mx-4 h-2 bg-gray-700 rounded-full relative">
                <div className="absolute inset-0 bg-gradient-to-r from-red-500 via-yellow-500 to-green-500 rounded-full opacity-30" />
              </div>
              <span className="font-mono text-green-400">${pinRisk.expected_range.high.toFixed(2)}</span>
            </div>
            <div className="text-center text-xs text-gray-400 mt-1">
              Range Width: {pinRisk.expected_range.pct.toFixed(1)}%
            </div>
          </div>

          {/* Pin Factors */}
          <div>
            <div className="text-sm font-semibold mb-2">Contributing Factors</div>
            <div className="space-y-2">
              {pinRisk.pin_factors.map((factor, i) => (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <span className="text-primary font-mono">+{factor.score}</span>
                  <span className="text-gray-300">{factor.description}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Trading Implications */}
          <div>
            <div className="text-sm font-semibold mb-2">Trading Implications</div>
            <div className="grid md:grid-cols-2 gap-2">
              {pinRisk.trading_implications.slice(0, 4).map((impl, i) => {
                const implColors: Record<string, string> = {
                  favorable: 'border-green-500/50 bg-green-500/10',
                  unfavorable: 'border-red-500/50 bg-red-500/10',
                  neutral: 'border-yellow-500/50 bg-yellow-500/10'
                }
                return (
                  <div key={i} className={`p-2 rounded border ${implColors[impl.outlook] || implColors.neutral}`}>
                    <div className="flex items-center gap-1 text-xs font-semibold mb-1">
                      {impl.outlook === 'favorable' && <CheckCircle className="w-3 h-3 text-green-400" />}
                      {impl.outlook === 'unfavorable' && <X className="w-3 h-3 text-red-400" />}
                      {impl.outlook === 'neutral' && <Minus className="w-3 h-3 text-yellow-400" />}
                      {impl.position_type.replace(/_/g, ' ').toUpperCase()}
                    </div>
                    <div className="text-xs text-gray-400">{impl.recommendation}</div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* What Would Break the Pin */}
          <div className="p-3 bg-primary/10 border border-primary/30 rounded-lg">
            <div className="text-sm font-semibold text-primary mb-2">What Would Break the Pin</div>
            <ul className="space-y-1">
              {pinRisk.pin_breakers.slice(0, 4).map((breaker, i) => (
                <li key={i} className="text-xs text-gray-300 flex items-start gap-2">
                  <span className="text-primary">•</span>
                  {breaker}
                </li>
              ))}
            </ul>
          </div>

          {/* Expiration Context */}
          {(pinRisk.is_expiration_day || pinRisk.days_to_expiry <= 2) && (
            <div className={`p-2 rounded text-center text-sm ${pinRisk.is_expiration_day ? 'bg-red-500/20 text-red-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
              {pinRisk.is_expiration_day
                ? 'TODAY IS EXPIRATION DAY - Maximum gamma effect!'
                : `${pinRisk.days_to_expiry} days to weekly expiry - Pin gravity increasing`
              }
            </div>
          )}

          {/* Summary */}
          <div className="text-sm text-gray-400 italic">
            {pinRisk.summary}
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export default function ApolloPage() {
  // State
  const [symbols, setSymbols] = useState<string[]>(['SPY'])
  const [inputSymbol, setInputSymbol] = useState('')
  const [scanning, setScanning] = useState(false)
  const [scanResults, setScanResults] = useState<ApolloScanResult[]>([])
  const [lastScanId, setLastScanId] = useState<string | null>(null)
  const [vixAtScan, setVixAtScan] = useState<number>(18)
  const [scanDuration, setScanDuration] = useState<number>(0)
  const [expandedStrategies, setExpandedStrategies] = useState<Record<string, boolean>>({})
  const [performance, setPerformance] = useState<ModelPerformance | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [scanProgress, setScanProgress] = useState<{ current: number, total: number, symbol: string } | null>(null)
  const [selectedResult, setSelectedResult] = useState<ApolloScanResult | null>(null)

  // Quick Pin Risk Checker State
  const [quickPinSymbol, setQuickPinSymbol] = useState('')
  const [quickPinLoading, setQuickPinLoading] = useState(false)
  const [quickPinResult, setQuickPinResult] = useState<PinRisk | null>(null)
  const [quickPinError, setQuickPinError] = useState<string | null>(null)
  const [quickPinExpanded, setQuickPinExpanded] = useState(true)

  const popularSymbols = ['SPY', 'QQQ', 'IWM', 'DIA', 'TSLA', 'NVDA', 'AAPL', 'MSFT', 'AMD', 'META']

  // Fetch model performance on mount
  useEffect(() => {
    fetchPerformance()
  }, [])

  const fetchPerformance = async () => {
    try {
      const response = await apiClient.getApolloPerformance()
      if (response.data?.success) {
        setPerformance(response.data.data)
      }
    } catch (e) {
      console.error('Failed to fetch performance:', e)
    }
  }

  // Quick Pin Risk Check
  const checkPinRisk = async (symbol?: string) => {
    const sym = (symbol || quickPinSymbol).toUpperCase().trim()
    if (!sym) return

    setQuickPinLoading(true)
    setQuickPinError(null)
    setQuickPinResult(null)

    try {
      const response = await apiClient.getApolloPinRisk(sym)
      if (response.data?.success) {
        setQuickPinResult(response.data.data)
        setQuickPinExpanded(true)
      } else {
        throw new Error('Pin risk check failed')
      }
    } catch (e: any) {
      let errorMsg = 'Failed to check pin risk'
      if (e.response?.data?.detail) {
        errorMsg = e.response.data.detail
      } else if (e.message) {
        errorMsg = e.message
      }
      setQuickPinError(errorMsg)
    } finally {
      setQuickPinLoading(false)
    }
  }

  // Add symbol
  const addSymbol = (symbol: string) => {
    const s = symbol.toUpperCase().trim()
    if (s && !symbols.includes(s) && symbols.length < 5) {
      setSymbols([...symbols, s])
    }
    setInputSymbol('')
  }

  // Remove symbol
  const removeSymbol = (symbol: string) => {
    setSymbols(symbols.filter(s => s !== symbol))
  }

  // Perform scan
  const performScan = async () => {
    if (symbols.length === 0) return

    setScanning(true)
    setError(null)
    setScanResults([])
    setScanProgress({ current: 0, total: symbols.length, symbol: '' })

    try {
      // Update progress as we scan
      setScanProgress({ current: 0, total: symbols.length, symbol: symbols[0] })

      const response = await apiClient.apolloScan(symbols, true)
      const data: ScanResponse = response.data

      if (data.success) {
        setScanResults(data.results)
        setLastScanId(data.scan_id)
        setVixAtScan(data.vix_at_scan)
        setScanDuration(data.duration_ms)

        // Auto-expand first strategy for each result
        const expanded: Record<string, boolean> = {}
        data.results.forEach(r => {
          if (r.strategies.length > 0) {
            expanded[`${r.symbol}-${r.strategies[0].strategy_type}`] = true
          }
        })
        setExpandedStrategies(expanded)
      } else {
        throw new Error('Scan returned unsuccessful')
      }

    } catch (e: any) {
      // Better error extraction
      let errorMessage = 'Scan failed'
      if (e.response?.data?.detail) {
        errorMessage = e.response.data.detail
      } else if (e.response?.data?.message) {
        errorMessage = e.response.data.message
      } else if (e.message) {
        errorMessage = e.message
      }

      // Network error handling
      if (e.code === 'ECONNREFUSED' || e.message?.includes('Network Error')) {
        errorMessage = 'Cannot connect to backend. Please ensure the API server is running.'
      }

      setError(errorMessage)
    } finally {
      setScanning(false)
      setScanProgress(null)
    }
  }

  // Toggle strategy expansion
  const toggleStrategy = (symbol: string, strategyType: string) => {
    const key = `${symbol}-${strategyType}`
    setExpandedStrategies(prev => ({ ...prev, [key]: !prev[key] }))
  }

  return (
    <div className="min-h-screen bg-background">
      <Navigation />

      <main className="pt-24 md:pl-64 transition-all duration-300">
        <div className="p-6 max-w-7xl mx-auto space-y-6">

          {/* Header */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold flex items-center gap-3">
                <Sparkles className="w-8 h-8 text-yellow-400" />
                APOLLO
                <span className="text-sm font-normal text-gray-400 ml-2">
                  AI-Powered Live Options Scanner
                </span>
              </h1>
              <p className="text-gray-400 mt-1">
                ML predictions + Live Tradier data + GEX analysis
              </p>
            </div>

            {/* Model Status */}
            {performance && (
              <div className="flex items-center gap-4 text-sm">
                <div className="flex items-center gap-2">
                  <Brain className={`w-4 h-4 ${performance.models_loaded ? 'text-green-400' : 'text-yellow-400'}`} />
                  <span className="text-gray-400">
                    {performance.models_loaded ? 'ML Active' : 'Rule-Based'}
                  </span>
                </div>
                <div className="text-gray-400">
                  7d Accuracy: <span className="text-white font-mono">{performance.direction_accuracy_7d}%</span>
                </div>
              </div>
            )}
          </div>

          {/* Symbol Input */}
          <div className="bg-background-card rounded-xl p-6 border border-gray-800">
            <div className="flex flex-col md:flex-row gap-4">
              {/* Selected Symbols */}
              <div className="flex-1">
                <label className="text-sm text-gray-400 mb-2 block">Symbols to Scan (max 5)</label>
                <div className="flex flex-wrap gap-2">
                  {symbols.map(s => (
                    <div
                      key={s}
                      className="flex items-center gap-1 px-3 py-1.5 bg-primary/20 text-primary rounded-lg"
                    >
                      <span className="font-semibold">{s}</span>
                      <button
                        onClick={() => removeSymbol(s)}
                        className="hover:text-red-400 transition-colors"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                  {symbols.length < 5 && (
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={inputSymbol}
                        onChange={e => setInputSymbol(e.target.value.toUpperCase())}
                        onKeyPress={e => e.key === 'Enter' && addSymbol(inputSymbol)}
                        placeholder="Add symbol..."
                        className="w-32 px-3 py-1.5 bg-gray-900 border border-gray-700 rounded-lg text-sm text-white placeholder-gray-400 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary"
                      />
                      <button
                        onClick={() => addSymbol(inputSymbol)}
                        className="p-1.5 bg-primary/20 text-primary rounded-lg hover:bg-primary/30 transition-colors"
                      >
                        <Plus className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </div>

                {/* Popular Symbols */}
                <div className="mt-3 flex flex-wrap gap-1">
                  {popularSymbols.filter(s => !symbols.includes(s)).slice(0, 6).map(s => (
                    <button
                      key={s}
                      onClick={() => addSymbol(s)}
                      disabled={symbols.length >= 5}
                      className="px-2 py-1 text-xs bg-background hover:bg-background-hover rounded transition-colors disabled:opacity-50"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>

              {/* Scan Button */}
              <div className="flex items-end">
                <button
                  onClick={performScan}
                  disabled={scanning || symbols.length === 0}
                  className="flex items-center gap-2 px-6 py-3 bg-primary hover:bg-primary-hover disabled:bg-gray-700 disabled:cursor-not-allowed rounded-xl font-semibold transition-colors"
                >
                  {scanning ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" />
                      Scanning...
                    </>
                  ) : (
                    <>
                      <Search className="w-5 h-5" />
                      Scan with APOLLO
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>

          {/* Quick Pin Risk Checker */}
          <div className="bg-gradient-to-r from-red-500/10 via-orange-500/10 to-yellow-500/10 rounded-xl p-4 border border-orange-500/30">
            <div className="flex flex-col md:flex-row gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <Shield className="w-5 h-5 text-orange-400" />
                  <span className="font-semibold text-orange-400">Quick Pin Risk Check</span>
                  <span className="text-xs text-gray-400">Instant analysis for any symbol</span>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={quickPinSymbol}
                    onChange={e => setQuickPinSymbol(e.target.value.toUpperCase())}
                    onKeyPress={e => e.key === 'Enter' && checkPinRisk()}
                    placeholder="Enter symbol (e.g., NVDA)"
                    className="flex-1 max-w-xs px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500"
                  />
                  <button
                    onClick={() => checkPinRisk()}
                    disabled={quickPinLoading || !quickPinSymbol.trim()}
                    className="flex items-center gap-2 px-4 py-2 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-700 disabled:cursor-not-allowed rounded-lg font-semibold transition-colors"
                  >
                    {quickPinLoading ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Shield className="w-4 h-4" />
                    )}
                    Check
                  </button>
                </div>
                {/* Quick Symbol Buttons */}
                <div className="mt-2 flex flex-wrap gap-1">
                  {['NVDA', 'TSLA', 'AAPL', 'AMD', 'META', 'AMZN', 'GOOGL', 'MSFT'].map(s => (
                    <button
                      key={s}
                      onClick={() => {
                        setQuickPinSymbol(s)
                        checkPinRisk(s)
                      }}
                      disabled={quickPinLoading}
                      className="px-2 py-1 text-xs bg-gray-800 hover:bg-gray-700 rounded transition-colors disabled:opacity-50"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>

              {/* Quick Result Display */}
              {quickPinResult && (
                <div className="md:w-80 p-3 bg-background rounded-lg border border-gray-700">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-bold text-lg">{quickPinSymbol}</span>
                    <button
                      onClick={() => setQuickPinResult(null)}
                      className="text-gray-400 hover:text-white"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-400">Pin Risk</span>
                      <span className={`font-mono font-bold ${
                        quickPinResult.score >= 60 ? 'text-red-400' :
                        quickPinResult.score >= 40 ? 'text-orange-400' : 'text-green-400'
                      }`}>
                        {quickPinResult.score}/100
                      </span>
                    </div>
                    <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all ${
                          quickPinResult.score >= 60 ? 'bg-red-500' :
                          quickPinResult.score >= 40 ? 'bg-orange-500' : 'bg-green-500'
                        }`}
                        style={{ width: `${quickPinResult.score}%` }}
                      />
                    </div>
                    <div className={`text-center text-xs font-semibold py-1 rounded ${
                      quickPinResult.long_call_outlook === 'dangerous' ? 'bg-red-500/20 text-red-400' :
                      quickPinResult.long_call_outlook === 'challenging' ? 'bg-orange-500/20 text-orange-400' :
                      quickPinResult.long_call_outlook === 'favorable' ? 'bg-green-500/20 text-green-400' :
                      'bg-yellow-500/20 text-yellow-400'
                    }`}>
                      Long Calls: {quickPinResult.long_call_outlook.toUpperCase()}
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="text-center p-1 bg-gray-800 rounded">
                        <div className="text-gray-400">Max Pain</div>
                        <div className="font-mono text-yellow-400">${quickPinResult.max_pain.toFixed(0)}</div>
                      </div>
                      <div className="text-center p-1 bg-gray-800 rounded">
                        <div className="text-gray-400">Gamma</div>
                        <div className={`font-mono ${
                          quickPinResult.gamma_regime === 'positive' ? 'text-green-400' :
                          quickPinResult.gamma_regime === 'negative' ? 'text-red-400' : 'text-yellow-400'
                        }`}>
                          {quickPinResult.gamma_regime.toUpperCase()}
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={() => setQuickPinExpanded(!quickPinExpanded)}
                      className="w-full text-xs text-primary hover:underline"
                    >
                      {quickPinExpanded ? 'Hide Details' : 'Show Details'}
                    </button>
                  </div>
                </div>
              )}

              {/* Error Display */}
              {quickPinError && (
                <div className="md:w-80 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                  <div className="flex items-center gap-2 text-red-400">
                    <AlertCircle className="w-4 h-4" />
                    <span className="text-sm">{quickPinError}</span>
                  </div>
                </div>
              )}
            </div>

            {/* Expanded Quick Result */}
            {quickPinResult && quickPinExpanded && (
              <div className="mt-4 pt-4 border-t border-gray-700">
                <PinRiskCard pinRisk={quickPinResult} symbol={quickPinSymbol} />
              </div>
            )}
          </div>

          {/* Scanning Progress */}
          {scanning && scanProgress && (
            <div className="bg-primary/10 border border-primary/50 rounded-xl p-4">
              <div className="flex items-center gap-3 mb-2">
                <Loader2 className="w-5 h-5 text-primary animate-spin" />
                <span className="text-primary font-medium">
                  Scanning {scanProgress.symbol || 'symbols'}...
                </span>
                <span className="text-gray-400 text-sm">
                  ({scanProgress.current}/{scanProgress.total})
                </span>
              </div>
              <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary transition-all duration-500"
                  style={{ width: `${(scanProgress.current / scanProgress.total) * 100}%` }}
                />
              </div>
              <div className="mt-2 text-xs text-gray-400">
                Fetching live data from Tradier, analyzing GEX levels, running ML predictions...
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="bg-red-500/10 border border-red-500/50 rounded-xl p-4 flex items-center gap-3">
              <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
              <div>
                <span className="text-red-400 font-medium">Scan failed: </span>
                <span className="text-red-300">{error}</span>
              </div>
            </div>
          )}

          {/* Scan Metadata */}
          {lastScanId && (
            <div className="flex items-center gap-6 text-sm text-gray-400">
              <div className="flex items-center gap-2">
                <Clock className="w-4 h-4" />
                Scan ID: <span className="font-mono text-white">{lastScanId}</span>
              </div>
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4" />
                VIX: <span className="font-mono text-white">{vixAtScan.toFixed(2)}</span>
              </div>
              <div className="flex items-center gap-2">
                <Zap className="w-4 h-4" />
                Duration: <span className="font-mono text-white">{scanDuration}ms</span>
              </div>
            </div>
          )}

          {/* Welcome/Intro State - shows when no results */}
          {!scanning && scanResults.length === 0 && !error && (
            <div className="bg-gradient-to-br from-primary/10 via-background-card to-yellow-500/5 rounded-xl border border-primary/30 p-8">
              <div className="text-center mb-8">
                <Sparkles className="w-12 h-12 text-yellow-400 mx-auto mb-4" />
                <h2 className="text-2xl font-bold mb-2">Welcome to APOLLO</h2>
                <p className="text-gray-400 max-w-2xl mx-auto">
                  AI-Powered Live Options Scanner that combines Machine Learning predictions,
                  real-time Tradier data, and GEX analysis to find optimal options strategies.
                </p>
              </div>

              <div className="grid md:grid-cols-3 gap-6 mb-8">
                <div className="bg-background/50 rounded-lg p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-2">
                    <Brain className="w-5 h-5 text-primary" />
                    <h3 className="font-semibold">ML Predictions</h3>
                  </div>
                  <p className="text-sm text-gray-400">
                    XGBoost models predict direction, magnitude, and timing with ensemble confidence scoring.
                  </p>
                </div>
                <div className="bg-background/50 rounded-lg p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-2">
                    <TrendingUp className="w-5 h-5 text-green-400" />
                    <h3 className="font-semibold">Live Market Data</h3>
                  </div>
                  <p className="text-sm text-gray-400">
                    Real-time quotes, options chains, and Greeks from Tradier + VIX from Yahoo Finance.
                  </p>
                </div>
                <div className="bg-background/50 rounded-lg p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-2">
                    <BarChart3 className="w-5 h-5 text-yellow-400" />
                    <h3 className="font-semibold">GEX Analysis</h3>
                  </div>
                  <p className="text-sm text-gray-400">
                    Gamma exposure levels, flip points, call/put walls to identify support and resistance.
                  </p>
                </div>
              </div>

              <div className="bg-background/50 rounded-lg p-4 border border-gray-700 mb-6">
                <h3 className="font-semibold mb-3 flex items-center gap-2">
                  <Target className="w-5 h-5 text-primary" />
                  9 Options Strategies Analyzed
                </h3>
                <div className="grid grid-cols-3 md:grid-cols-5 gap-2 text-sm">
                  <span className="px-2 py-1 bg-green-500/20 text-green-400 rounded text-center">Bull Call Spread</span>
                  <span className="px-2 py-1 bg-red-500/20 text-red-400 rounded text-center">Bear Put Spread</span>
                  <span className="px-2 py-1 bg-blue-500/20 text-blue-400 rounded text-center">Iron Condor</span>
                  <span className="px-2 py-1 bg-purple-500/20 text-purple-400 rounded text-center">Iron Butterfly</span>
                  <span className="px-2 py-1 bg-emerald-500/20 text-emerald-400 rounded text-center">Bull Put Spread</span>
                  <span className="px-2 py-1 bg-orange-500/20 text-orange-400 rounded text-center">Bear Call Spread</span>
                  <span className="px-2 py-1 bg-green-400/20 text-green-300 rounded text-center">Long Call</span>
                  <span className="px-2 py-1 bg-red-400/20 text-red-300 rounded text-center">Long Put</span>
                  <span className="px-2 py-1 bg-yellow-500/20 text-yellow-400 rounded text-center">Long Straddle</span>
                </div>
              </div>

              <div className="text-center">
                <div className="inline-flex items-center gap-2 px-4 py-2 bg-primary/20 text-primary rounded-lg mb-2">
                  <Search className="w-4 h-4" />
                  <span className="font-medium">Get Started</span>
                </div>
                <p className="text-sm text-gray-400">
                  Add symbols above (like SPY, QQQ, TSLA) and click "Scan with APOLLO" to analyze
                </p>
              </div>
            </div>
          )}

          {/* Results */}
          {scanResults.length > 0 && (
            <div className="space-y-6">
              {scanResults.map(result => (
                <div
                  key={result.symbol}
                  className="bg-background-card rounded-xl border border-gray-800 overflow-hidden"
                >
                  {/* Symbol Header */}
                  <div className="p-6 border-b border-gray-800">
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                      <div className="flex items-center gap-4">
                        <div className="text-2xl font-bold">{result.symbol}</div>
                        {result.features && (
                          <div className="text-lg font-mono text-gray-300">
                            ${result.features.spot_price.toFixed(2)}
                          </div>
                        )}
                        <RegimeBadge regime={result.market_regime} type="market" />
                        <RegimeBadge regime={result.gex_regime} type="gex" />
                      </div>

                      {result.prediction && (
                        <DirectionBadge
                          direction={result.prediction.direction}
                          confidence={result.prediction.direction_confidence}
                        />
                      )}
                    </div>

                    {/* Warnings */}
                    {result.warnings.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {result.warnings.map((w, i) => (
                          <span key={i} className="text-xs px-2 py-1 bg-yellow-500/20 text-yellow-400 rounded">
                            {w}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Prediction Details */}
                  {result.prediction && (
                    <div className="p-6 border-b border-gray-800 bg-background-hover/30">
                      <div className="flex items-center gap-2 mb-4">
                        <Brain className="w-5 h-5 text-primary" />
                        <h3 className="font-semibold">ML Prediction</h3>
                        {result.prediction.is_ml_prediction ? (
                          <span className="text-xs px-2 py-0.5 bg-green-500/20 text-green-400 rounded">ML Model</span>
                        ) : (
                          <span className="text-xs px-2 py-0.5 bg-yellow-500/20 text-yellow-400 rounded">Rule-Based</span>
                        )}
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div>
                          <div className="text-xs text-gray-400 mb-1">Direction</div>
                          <div className="flex items-center gap-2">
                            <span className="capitalize font-semibold">{result.prediction.direction}</span>
                            <span className="text-xs text-gray-400">
                              ({(result.prediction.direction_confidence * 100).toFixed(0)}%)
                            </span>
                          </div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-400 mb-1">Magnitude</div>
                          <div className="flex items-center gap-2">
                            <span className="capitalize font-semibold">{result.prediction.magnitude}</span>
                            <span className="text-xs text-gray-400">
                              ({(result.prediction.magnitude_confidence * 100).toFixed(0)}%)
                            </span>
                          </div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-400 mb-1">Timing</div>
                          <div className="flex items-center gap-2">
                            <span className="capitalize font-semibold">{result.prediction.timing.replace('_', ' ')}</span>
                            <span className="text-xs text-gray-400">
                              ({(result.prediction.timing_confidence * 100).toFixed(0)}%)
                            </span>
                          </div>
                        </div>
                        <div>
                          <ConfidenceMeter
                            value={result.prediction.ensemble_confidence}
                            label="Ensemble Confidence"
                          />
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Features Summary */}
                  {result.features && (
                    <div className="p-6 border-b border-gray-800">
                      <div className="flex items-center gap-2 mb-4">
                        <BarChart3 className="w-5 h-5 text-primary" />
                        <h3 className="font-semibold">Market Features & GEX Levels</h3>
                      </div>

                      {/* GEX Levels Visual */}
                      <div className="mb-4 p-4 bg-background rounded-lg border border-gray-700">
                        <div className="flex items-center justify-between mb-2 text-xs text-gray-400">
                          <span>Put Wall: ${result.features.put_wall.toFixed(0)}</span>
                          <span>Spot: ${result.features.spot_price.toFixed(2)}</span>
                          <span>Call Wall: ${result.features.call_wall.toFixed(0)}</span>
                        </div>
                        <div className="relative h-4 bg-gray-700 rounded-full overflow-hidden">
                          {/* Range indicator */}
                          <div className="absolute inset-0 flex items-center">
                            {/* Put wall marker */}
                            <div className="absolute left-[10%] w-1 h-full bg-red-500" title="Put Wall" />
                            {/* Flip point marker */}
                            <div
                              className="absolute w-1 h-full bg-yellow-500"
                              style={{ left: `${Math.min(90, Math.max(10, 50 + (result.features.flip_point - result.features.spot_price) / result.features.spot_price * 500))}%` }}
                              title="Flip Point"
                            />
                            {/* Current price marker */}
                            <div className="absolute left-1/2 w-2 h-full bg-blue-500 -translate-x-1/2" title="Current Price" />
                            {/* Call wall marker */}
                            <div className="absolute right-[10%] w-1 h-full bg-green-500" title="Call Wall" />
                          </div>
                        </div>
                        <div className="flex items-center justify-center gap-4 mt-2 text-xs">
                          <span className="flex items-center gap-1">
                            <span className="w-2 h-2 bg-red-500 rounded-full"></span> Put Wall
                          </span>
                          <span className="flex items-center gap-1">
                            <span className="w-2 h-2 bg-yellow-500 rounded-full"></span> Flip ${result.features.flip_point.toFixed(0)}
                          </span>
                          <span className="flex items-center gap-1">
                            <span className="w-2 h-2 bg-blue-500 rounded-full"></span> Price
                          </span>
                          <span className="flex items-center gap-1">
                            <span className="w-2 h-2 bg-green-500 rounded-full"></span> Call Wall
                          </span>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mb-4">
                        <div className="p-3 bg-background rounded-lg">
                          <div className="text-xs text-gray-400">Net GEX</div>
                          <div className={`text-lg font-mono font-bold ${result.features.net_gex >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {(result.features.net_gex / 1e9).toFixed(2)}B
                          </div>
                          <div className="text-xs text-gray-500">
                            {result.features.net_gex >= 0 ? '↑ Dealer Long Gamma (Stabilizing)' : '↓ Dealer Short Gamma (Volatile)'}
                          </div>
                        </div>
                        <div className="p-3 bg-background rounded-lg">
                          <div className="text-xs text-gray-400">Call Wall</div>
                          <div className="text-lg font-mono font-bold text-green-400">${result.features.call_wall.toFixed(0)}</div>
                          <div className="text-xs text-gray-500">
                            {((result.features.call_wall - result.features.spot_price) / result.features.spot_price * 100).toFixed(1)}% above
                          </div>
                        </div>
                        <div className="p-3 bg-background rounded-lg">
                          <div className="text-xs text-gray-400">Put Wall</div>
                          <div className="text-lg font-mono font-bold text-red-400">${result.features.put_wall.toFixed(0)}</div>
                          <div className="text-xs text-gray-500">
                            {((result.features.spot_price - result.features.put_wall) / result.features.spot_price * 100).toFixed(1)}% below
                          </div>
                        </div>
                        <div className="p-3 bg-background rounded-lg">
                          <div className="text-xs text-gray-400">Position vs Flip</div>
                          <div className={`text-lg font-mono font-bold ${result.features.above_flip ? 'text-green-400' : 'text-red-400'}`}>
                            {result.features.above_flip ? 'ABOVE' : 'BELOW'}
                          </div>
                          <div className="text-xs text-gray-500">
                            {Math.abs(result.features.distance_to_flip_pct).toFixed(2)}% from flip
                          </div>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-6 gap-4 text-sm">
                        <div>
                          <div className="text-xs text-gray-400">VIX</div>
                          <div className={`font-mono font-semibold ${
                            result.features.vix > 25 ? 'text-red-400' :
                            result.features.vix > 20 ? 'text-yellow-400' : 'text-green-400'
                          }`}>{result.features.vix.toFixed(2)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-400">VIX %ile</div>
                          <div className="font-mono">{result.features.vix_percentile}%</div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-400">IV Rank</div>
                          <div className="font-mono">{result.features.iv_rank.toFixed(0)}%</div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-400">RSI (14)</div>
                          <div className={`font-mono ${
                            result.features.rsi_14 > 70 ? 'text-red-400' :
                            result.features.rsi_14 < 30 ? 'text-green-400' : 'text-gray-300'
                          }`}>
                            {result.features.rsi_14.toFixed(1)}
                          </div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-400">MACD</div>
                          <div className={`font-mono capitalize ${
                            result.features.macd_signal === 'bullish' ? 'text-green-400' :
                            result.features.macd_signal === 'bearish' ? 'text-red-400' : 'text-gray-400'
                          }`}>{result.features.macd_signal}</div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-400">P/C Ratio</div>
                          <div className="font-mono">{result.features.put_call_ratio.toFixed(2)}</div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Pin Risk Analysis */}
                  {result.pin_risk && (
                    <div className="p-6 border-b border-gray-800">
                      <PinRiskCard pinRisk={result.pin_risk} symbol={result.symbol} />
                    </div>
                  )}

                  {/* Strategies */}
                  {result.strategies.length > 0 && (
                    <div className="p-6">
                      <div className="flex items-center gap-2 mb-4">
                        <Target className="w-5 h-5 text-primary" />
                        <h3 className="font-semibold">Recommended Strategies</h3>
                        <span className="text-xs text-gray-400">({result.strategies.length} strategies)</span>
                      </div>

                      <div className="space-y-3">
                        {result.strategies.map((strategy, i) => (
                          <StrategyCard
                            key={`${strategy.symbol}-${strategy.strategy_type}-${i}`}
                            strategy={strategy}
                            expanded={expandedStrategies[`${result.symbol}-${strategy.strategy_type}`] || false}
                            onToggle={() => toggleStrategy(result.symbol, strategy.strategy_type)}
                          />
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Data Quality */}
                  <div className="px-6 pb-4 flex items-center justify-between text-xs text-gray-400">
                    <div className="flex items-center gap-2">
                      <CheckCircle className={`w-4 h-4 ${result.data_quality_score >= 80 ? 'text-green-400' : 'text-yellow-400'}`} />
                      Data Quality: {result.data_quality_score.toFixed(0)}%
                    </div>
                    <div>
                      {new Date(result.timestamp).toLocaleString()}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Empty State */}
          {!scanning && scanResults.length === 0 && (
            <div className="bg-background-card rounded-xl p-12 text-center border border-gray-800">
              <Sparkles className="w-16 h-16 text-yellow-400 mx-auto mb-4 opacity-50" />
              <h3 className="text-xl font-semibold mb-2">Ready to Scan</h3>
              <p className="text-gray-400 max-w-md mx-auto">
                Add symbols above and click "Scan with APOLLO" to get ML-powered predictions
                and strategy recommendations based on live market data.
              </p>
            </div>
          )}

          {/* Performance Stats */}
          {performance && (
            <div className="bg-background-card rounded-xl p-6 border border-gray-800">
              <div className="flex items-center gap-2 mb-4">
                <BarChart3 className="w-5 h-5 text-primary" />
                <h3 className="font-semibold">Model Performance (30 days)</h3>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div>
                  <div className="text-xs text-gray-400">Direction (7d)</div>
                  <div className="text-2xl font-mono font-bold">
                    {performance.direction_accuracy_7d.toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-400">Direction (30d)</div>
                  <div className="text-2xl font-mono font-bold">
                    {performance.direction_accuracy_30d.toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-400">Magnitude</div>
                  <div className="text-2xl font-mono font-bold">
                    {performance.magnitude_accuracy_30d.toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-400">Strategy Win Rate</div>
                  <div className="text-2xl font-mono font-bold text-green-400">
                    {performance.strategy_win_rate.toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-400">Predictions</div>
                  <div className="text-2xl font-mono font-bold">
                    {performance.total_predictions_30d}
                  </div>
                </div>
              </div>
            </div>
          )}

        </div>
      </main>
    </div>
  )
}
