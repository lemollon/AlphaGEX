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
  Sparkles
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

interface ApolloScanResult {
  symbol: string
  timestamp: string
  scan_id: string
  features: ApolloFeatures | null
  prediction: ApolloPrediction | null
  strategies: ApolloStrategy[]
  market_regime: string
  gex_regime: string
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

  const borderColor = strategyColors[strategy.strategy_type] || 'border-gray-500/50'

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
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-sm font-mono text-green-400">
              {strategy.combined_confidence.toFixed(0)}% conf
            </div>
            <div className="text-xs text-gray-400">
              R:R {strategy.risk_reward_ratio.toFixed(2)}
            </div>
          </div>
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-gray-800">
          <div className="pt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-xs text-gray-400">Entry Cost</div>
              <div className="font-mono">${Math.abs(strategy.entry_cost).toFixed(2)}</div>
            </div>
            <div>
              <div className="text-xs text-gray-400">Max Profit</div>
              <div className="font-mono text-green-400">${strategy.max_profit.toFixed(2)}</div>
            </div>
            <div>
              <div className="text-xs text-gray-400">Max Loss</div>
              <div className="font-mono text-red-400">${strategy.max_loss.toFixed(2)}</div>
            </div>
            <div>
              <div className="text-xs text-gray-400">Prob. Profit</div>
              <div className="font-mono">{(strategy.probability_of_profit * 100).toFixed(0)}%</div>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-xs text-gray-400">DTE</div>
              <div className="font-mono">{strategy.dte} days</div>
            </div>
            <div>
              <div className="text-xs text-gray-400">Delta</div>
              <div className="font-mono">{strategy.position_delta.toFixed(2)}</div>
            </div>
            <div>
              <div className="text-xs text-gray-400">Theta</div>
              <div className="font-mono">{strategy.position_theta.toFixed(2)}</div>
            </div>
            <div>
              <div className="text-xs text-gray-400">ML Conf</div>
              <div className="font-mono">{strategy.ml_confidence.toFixed(0)}%</div>
            </div>
          </div>

          <div className="space-y-2 text-sm">
            <div className="p-2 bg-background-hover rounded">
              <span className="text-gray-400">Reasoning:</span> {strategy.reasoning}
            </div>
            <div className="p-2 bg-green-500/10 rounded text-green-400">
              <span className="text-gray-400">Entry:</span> {strategy.entry_trigger}
            </div>
            <div className="p-2 bg-blue-500/10 rounded text-blue-400">
              <span className="text-gray-400">Exit:</span> {strategy.exit_target}
            </div>
            <div className="p-2 bg-red-500/10 rounded text-red-400">
              <span className="text-gray-400">Stop:</span> {strategy.stop_loss}
            </div>
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

    try {
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
      setError(e.message || 'Scan failed')
    } finally {
      setScanning(false)
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

      <main className="pt-16 md:pl-64 transition-all duration-300">
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
                        className="w-32 px-3 py-1.5 bg-background border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-primary"
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

          {/* Error */}
          {error && (
            <div className="bg-red-500/10 border border-red-500/50 rounded-xl p-4 flex items-center gap-3">
              <AlertCircle className="w-5 h-5 text-red-400" />
              <span className="text-red-400">{error}</span>
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
                        <h3 className="font-semibold">Market Features</h3>
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-6 gap-4 text-sm">
                        <div>
                          <div className="text-xs text-gray-400">Net GEX</div>
                          <div className={`font-mono ${result.features.net_gex >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {(result.features.net_gex / 1e9).toFixed(2)}B
                          </div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-400">Flip Point</div>
                          <div className="font-mono">${result.features.flip_point.toFixed(2)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-400">Distance to Flip</div>
                          <div className="font-mono">{result.features.distance_to_flip_pct.toFixed(2)}%</div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-400">VIX</div>
                          <div className="font-mono">{result.features.vix.toFixed(2)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-400">IV Rank</div>
                          <div className="font-mono">{result.features.iv_rank.toFixed(0)}</div>
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
                      </div>
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
