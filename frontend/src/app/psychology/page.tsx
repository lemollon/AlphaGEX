'use client'

import { useState, useEffect, useCallback } from 'react'
import { Brain, AlertTriangle, TrendingUp, TrendingDown, Target, Clock, Shield, Zap, RefreshCw, Activity, Calendar } from 'lucide-react'
import Navigation from '@/components/Navigation'
import TradingGuide from '@/components/TradingGuide'
import PsychologyNotifications from '@/components/PsychologyNotifications'
import { apiClient } from '@/lib/api'

// Get API URL from environment variable (same as rest of the app)
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface RSIAnalysis {
  score: number
  individual_rsi: {
    '5m': number
    '15m': number
    '1h': number
    '4h': number
    '1d': number
  }
  aligned_count: {
    overbought: number
    oversold: number
    extreme_overbought: number
    extreme_oversold: number
  }
  coiling_detected: boolean
}

interface VIXData {
  current: number
  previous_close: number
  change_pct: number
  intraday_high: number
  intraday_low: number
  ma_20: number
  spike_detected: boolean
}

interface VolatilityRegime {
  regime: string
  risk_level: string
  description: string
  at_flip_point: boolean
  flip_point_distance_pct: number
}

interface RegimeAnalysis {
  timestamp: string
  spy_price: number
  regime: {
    primary_type: string
    secondary_type: string | null
    confidence: number
    description: string
    detailed_explanation: string
    trade_direction: string
    risk_level: string
    timeline: string | null
    price_targets: any
    psychology_trap: string
    supporting_factors: string[]
  }
  rsi_analysis: RSIAnalysis
  current_walls: any
  expiration_analysis: any
  forward_gex: any
  volume_ratio: number
  vix_data?: VIXData
  zero_gamma_level?: number
  volatility_regime?: VolatilityRegime
  alert_level: {
    level: string
    reason: string
  }
}

export default function PsychologyTrapDetection() {
  const [symbol, setSymbol] = useState('SPY')
  const [analysis, setAnalysis] = useState<RegimeAnalysis | null>(null)
  const [tradingGuide, setTradingGuide] = useState<any | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [history, setHistory] = useState<any[]>([])
  const [liberationSetups, setLiberationSetups] = useState<any[]>([])
  const [falseFloors, setFalseFloors] = useState<any[]>([])

  // Fetch current regime analysis
  const fetchAnalysis = useCallback(async (forceRefresh = false) => {
    try {
      forceRefresh ? setIsRefreshing(true) : setLoading(true)
      setError(null)

      const response = await fetch(`${API_URL}/api/psychology/current-regime?symbol=${symbol}`)

      if (!response.ok) {
        // Get detailed error from API
        let errorDetail = `HTTP ${response.status}: ${response.statusText}`
        try {
          const errorData = await response.json()
          errorDetail = errorData.detail?.message || errorData.detail || errorData.message || errorDetail
        } catch {
          // Response not JSON, use status text
        }
        throw new Error(errorDetail)
      }

      const data = await response.json()
      setAnalysis(data.analysis)
      setTradingGuide(data.trading_guide || null)

      // REMOVED: Auto-fetch supporting data to reduce API calls on page load
      // Only fetch these when user explicitly refreshes
      // fetchLiberationSetups()
      // fetchFalseFloors()

    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to fetch analysis'
      console.error('Psychology API Error:', errorMsg, err)
      setError(errorMsg)
    } finally {
      setLoading(false)
      setIsRefreshing(false)
    }
  }, [symbol])

  // Fetch liberation setups
  const fetchLiberationSetups = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/psychology/liberation-setups`)
      if (response.ok) {
        const data = await response.json()
        setLiberationSetups(data.liberation_setups || [])
      }
    } catch (err) {
      console.error('Failed to fetch liberation setups:', err)
    }
  }, [])

  // Fetch false floors
  const fetchFalseFloors = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/psychology/false-floors`)
      if (response.ok) {
        const data = await response.json()
        setFalseFloors(data.false_floors || [])
      }
    } catch (err) {
      console.error('Failed to fetch false floors:', err)
    }
  }, [])

  // Initial load
  useEffect(() => {
    fetchAnalysis()
  }, [fetchAnalysis])

  // Get regime color
  const getRegimeColor = (type: string) => {
    const colors: { [key: string]: string } = {
      'LIBERATION_TRADE': 'text-green-400',
      'FALSE_FLOOR': 'text-red-400',
      'ZERO_DTE_PIN': 'text-yellow-400',
      'DESTINATION_TRADE': 'text-blue-400',
      'PIN_AT_CALL_WALL': 'text-orange-400',
      'EXPLOSIVE_CONTINUATION': 'text-emerald-400',
      'PIN_AT_PUT_WALL': 'text-cyan-400',
      'CAPITULATION_CASCADE': 'text-rose-400',
      'MEAN_REVERSION_ZONE': 'text-purple-400',
      'NEUTRAL': 'text-gray-400'
    }
    return colors[type] || 'text-gray-400'
  }

  // Get risk badge color
  const getRiskColor = (risk: string) => {
    const colors: { [key: string]: string } = {
      'low': 'bg-green-500/20 text-green-400',
      'medium': 'bg-yellow-500/20 text-yellow-400',
      'high': 'bg-orange-500/20 text-orange-400',
      'extreme': 'bg-red-500/20 text-red-400'
    }
    return colors[risk] || 'bg-gray-500/20 text-gray-400'
  }

  // Get alert level color
  const getAlertColor = (level: string) => {
    const colors: { [key: string]: string } = {
      'CRITICAL': 'bg-red-500/20 border-red-500 text-red-400',
      'HIGH': 'bg-orange-500/20 border-orange-500 text-orange-400',
      'MEDIUM': 'bg-yellow-500/20 border-yellow-500 text-yellow-400',
      'LOW': 'bg-blue-500/20 border-blue-500 text-blue-400'
    }
    return colors[level] || 'bg-gray-500/20 border-gray-500 text-gray-400'
  }

  // RSI Heatmap Component
  const RSIHeatmap = ({ rsi }: { rsi: RSIAnalysis }) => {
    const getRSIColor = (value: number) => {
      if (value >= 80) return 'bg-red-600'
      if (value >= 70) return 'bg-red-500'
      if (value >= 60) return 'bg-orange-500'
      if (value >= 40) return 'bg-green-500'
      if (value >= 30) return 'bg-blue-500'
      if (value >= 20) return 'bg-blue-600'
      return 'bg-purple-600'
    }

    return (
      <div className="space-y-2">
        {Object.entries(rsi.individual_rsi).map(([timeframe, value]) => (
          <div key={timeframe} className="flex items-center gap-3">
            <div className="w-12 text-sm font-mono text-gray-400">{timeframe}</div>
            <div className="flex-1 h-6 bg-gray-800 rounded-full overflow-hidden">
              <div
                className={`h-full ${getRSIColor(value)} transition-all duration-300`}
                style={{ width: `${value}%` }}
              />
            </div>
            <div className="w-16 text-sm font-mono text-right">
              {value.toFixed(1)}
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <Navigation />

      <main className="pt-16 transition-all duration-300">
        <div className="container mx-auto px-4 py-8 space-y-6">
          {/* Header */}
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Brain className="w-8 h-8 text-purple-400" />
              <h1 className="text-3xl font-bold">Psychology Trap Detection</h1>
            </div>
            <div className="flex items-center gap-3">
              <p className="text-gray-400">
                Identify when retail traders get trapped by ignoring market structure
              </p>
              {analysis?.timestamp && (
                <>
                  <span className="text-gray-600">|</span>
                  <div className="flex items-center gap-1 text-sm text-gray-500">
                    <Clock className="w-4 h-4" />
                    <span>Updated: {new Date(analysis.timestamp).toLocaleString()}</span>
                  </div>
                </>
              )}
            </div>
          </div>

          <button
            onClick={() => fetchAnalysis(true)}
            disabled={isRefreshing}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg flex items-center gap-2 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        {/* Push Notifications */}
        <PsychologyNotifications />

        {/* Error State */}
        {error && (
          <div className="bg-red-500/10 border border-red-500 rounded-lg p-4">
            <div className="flex items-center gap-2 text-red-400">
              <AlertTriangle className="w-5 h-5" />
              <span>{error}</span>
            </div>
          </div>
        )}

        {/* Loading State */}
        {loading && !analysis && (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-4 border-purple-500 border-t-transparent" />
          </div>
        )}

        {/* Main Analysis */}
        {analysis && (
          <>
            {/* Alert Level Banner */}
            {analysis.alert_level && (
              <div className={`border-2 rounded-lg p-6 ${getAlertColor(analysis.alert_level.level)}`}>
                <div className="flex items-start gap-4">
                  <AlertTriangle className="w-8 h-8 flex-shrink-0 mt-1" />
                  <div className="flex-1">
                    <div className="text-xl font-bold mb-2">
                      {analysis.alert_level.level} ALERT
                    </div>
                    <div className="text-sm opacity-90">
                      {analysis.alert_level.reason}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Main Regime Card */}
            <div className="bg-gradient-to-br from-gray-900 to-gray-800 border-2 border-purple-500/30 rounded-xl p-6 space-y-4">
              <div className="flex items-start justify-between">
                <div className="space-y-2">
                  <div className="flex items-center gap-3">
                    <div className={`text-2xl font-bold ${getRegimeColor(analysis.regime.primary_type)}`}>
                      {analysis.regime.primary_type.replace(/_/g, ' ')}
                    </div>
                    <div className={`px-3 py-1 rounded-full text-xs font-semibold ${getRiskColor(analysis.regime.risk_level)}`}>
                      {analysis.regime.risk_level.toUpperCase()} RISK
                    </div>
                  </div>
                  <div className="text-lg text-gray-300">
                    {analysis.regime.description}
                  </div>
                </div>

                <div className="text-right space-y-1">
                  <div className="text-3xl font-bold text-white">
                    {analysis.regime.confidence.toFixed(0)}%
                  </div>
                  <div className="text-sm text-gray-400">Confidence</div>
                </div>
              </div>

              {/* Detailed Explanation */}
              <div className="bg-gray-950/50 rounded-lg p-4">
                <div className="text-sm text-gray-300 whitespace-pre-line">
                  {analysis.regime.detailed_explanation}
                </div>
              </div>

              {/* Psychology Trap */}
              {analysis.regime.psychology_trap && (
                <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="font-semibold text-red-400 mb-1">Psychology Trap:</div>
                      <div className="text-sm text-gray-300">{analysis.regime.psychology_trap}</div>
                    </div>
                  </div>
                </div>
              )}

              {/* Supporting Factors */}
              {analysis.regime.supporting_factors && analysis.regime.supporting_factors.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {analysis.regime.supporting_factors.map((factor, idx) => (
                    <div key={idx} className="px-3 py-1 bg-purple-500/20 rounded-full text-sm">
                      {factor}
                    </div>
                  ))}
                </div>
              )}

              {/* Price Targets & Timeline */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-gray-950/50 rounded-lg p-4">
                  <div className="flex items-center gap-2 text-gray-400 mb-2">
                    <Target className="w-4 h-4" />
                    <span className="text-sm">Current Price</span>
                  </div>
                  <div className="text-2xl font-bold">${analysis.spy_price.toFixed(2)}</div>
                </div>

                {analysis.regime.trade_direction && (
                  <div className="bg-gray-950/50 rounded-lg p-4">
                    <div className="flex items-center gap-2 text-gray-400 mb-2">
                      <Activity className="w-4 h-4" />
                      <span className="text-sm">Direction</span>
                    </div>
                    <div className="text-xl font-bold capitalize">
                      {analysis.regime.trade_direction.replace(/_/g, ' ')}
                    </div>
                  </div>
                )}

                {analysis.regime.timeline && (
                  <div className="bg-gray-950/50 rounded-lg p-4">
                    <div className="flex items-center gap-2 text-gray-400 mb-2">
                      <Clock className="w-4 h-4" />
                      <span className="text-sm">Timeline</span>
                    </div>
                    <div className="text-lg font-bold">{analysis.regime.timeline}</div>
                  </div>
                )}
              </div>
            </div>

            {/* Grid of Analysis Components */}
            {/* HOW TO MAKE MONEY - Trading Guide */}
            {tradingGuide && (
              <div className="my-8">
                <TradingGuide 
                  guide={tradingGuide} 
                  currentPrice={analysis.spy_price}
                />
              </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* RSI Heatmap */}
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
                <div className="flex items-center gap-2 mb-4">
                  <Activity className="w-5 h-5 text-purple-400" />
                  <h2 className="text-xl font-bold">Multi-Timeframe RSI</h2>
                  {analysis.rsi_analysis.coiling_detected && (
                    <div className="px-2 py-1 bg-yellow-500/20 rounded text-xs font-semibold text-yellow-400">
                      COILING
                    </div>
                  )}
                </div>

                <div className="space-y-4">
                  <RSIHeatmap rsi={analysis.rsi_analysis} />

                  <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-800">
                    <div>
                      <div className="text-sm text-gray-400 mb-1">Overbought</div>
                      <div className="text-2xl font-bold text-red-400">
                        {analysis.rsi_analysis.aligned_count.overbought}/5
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-400 mb-1">Oversold</div>
                      <div className="text-2xl font-bold text-blue-400">
                        {analysis.rsi_analysis.aligned_count.oversold}/5
                      </div>
                    </div>
                  </div>

                  <div className="pt-4 border-t border-gray-800">
                    <div className="text-sm text-gray-400 mb-2">Weighted RSI Score</div>
                    <div className="flex items-center gap-3">
                      <div className="flex-1 h-3 bg-gray-800 rounded-full overflow-hidden">
                        <div
                          className={`h-full ${
                            analysis.rsi_analysis.score > 50 ? 'bg-red-500' :
                            analysis.rsi_analysis.score < -50 ? 'bg-blue-500' :
                            'bg-green-500'
                          }`}
                          style={{
                            width: `${Math.abs(analysis.rsi_analysis.score) / 100 * 100}%`,
                            marginLeft: analysis.rsi_analysis.score < 0 ? 'auto' : '0'
                          }}
                        />
                      </div>
                      <div className="text-lg font-bold w-16 text-right">
                        {analysis.rsi_analysis.score.toFixed(0)}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Gamma Walls */}
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
                <div className="flex items-center gap-2 mb-4">
                  <Shield className="w-5 h-5 text-cyan-400" />
                  <h2 className="text-xl font-bold">Gamma Walls</h2>
                </div>

                <div className="space-y-4">
                  {analysis.current_walls?.call_wall && (
                    <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
                      <div className="flex items-center justify-between mb-2">
                        <div className="text-sm text-gray-400">Call Wall</div>
                        <TrendingUp className="w-4 h-4 text-red-400" />
                      </div>
                      <div className="text-2xl font-bold text-red-400">
                        ${analysis.current_walls.call_wall.strike?.toFixed(2)}
                      </div>
                      <div className="text-sm text-gray-400 mt-1">
                        {analysis.current_walls.call_wall.distance_pct?.toFixed(2)}% away
                      </div>
                      <div className="text-xs text-gray-500 mt-2">
                        Dealers: {analysis.current_walls.call_wall.dealer_position}
                      </div>
                    </div>
                  )}

                  {analysis.current_walls?.put_wall && (
                    <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
                      <div className="flex items-center justify-between mb-2">
                        <div className="text-sm text-gray-400">Put Wall</div>
                        <TrendingDown className="w-4 h-4 text-blue-400" />
                      </div>
                      <div className="text-2xl font-bold text-blue-400">
                        ${analysis.current_walls.put_wall.strike?.toFixed(2)}
                      </div>
                      <div className="text-sm text-gray-400 mt-1">
                        {analysis.current_walls.put_wall.distance_pct?.toFixed(2)}% away
                      </div>
                      <div className="text-xs text-gray-500 mt-2">
                        Dealers: {analysis.current_walls.put_wall.dealer_position}
                      </div>
                    </div>
                  )}

                  <div className="pt-4 border-t border-gray-800">
                    <div className="text-sm text-gray-400 mb-2">Net Gamma Regime</div>
                    <div className={`text-xl font-bold ${
                      analysis.current_walls?.net_gamma_regime === 'short' ? 'text-red-400' : 'text-green-400'
                    }`}>
                      {analysis.current_walls?.net_gamma_regime?.toUpperCase()}
                    </div>
                    <div className="text-sm text-gray-500 mt-1">
                      ${(analysis.current_walls?.net_gamma / 1e9).toFixed(2)}B
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* VIX and Volatility Regime Cards (NEW) */}
            {(analysis.vix_data || analysis.volatility_regime) && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* VIX Card */}
                {analysis.vix_data && (
                  <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
                    <div className="flex items-center gap-2 mb-4">
                      <Zap className="w-5 h-5 text-yellow-400" />
                      <h2 className="text-xl font-bold">VIX Volatility Index</h2>
                      {analysis.vix_data.spike_detected && (
                        <div className="px-2 py-1 bg-red-500/20 rounded text-xs font-semibold text-red-400 animate-pulse">
                          SPIKE!
                        </div>
                      )}
                    </div>

                    <div className="space-y-4">
                      {/* Current VIX */}
                      <div className="bg-gray-950/50 rounded-lg p-4">
                        <div className="text-sm text-gray-400 mb-1">Current VIX</div>
                        <div className="flex items-baseline gap-2">
                          <div className={`text-4xl font-bold ${
                            analysis.vix_data.current > 20 ? 'text-red-400' :
                            analysis.vix_data.current > 15 ? 'text-yellow-400' :
                            'text-green-400'
                          }`}>
                            {analysis.vix_data.current.toFixed(2)}
                          </div>
                          <div className={`text-lg font-semibold ${
                            analysis.vix_data.change_pct > 0 ? 'text-red-400' : 'text-green-400'
                          }`}>
                            {analysis.vix_data.change_pct > 0 ? '+' : ''}
                            {analysis.vix_data.change_pct.toFixed(2)}%
                          </div>
                        </div>
                      </div>

                      {/* VIX Details */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <div className="text-xs text-gray-500 mb-1">Previous Close</div>
                          <div className="text-lg font-semibold">{analysis.vix_data.previous_close.toFixed(2)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-500 mb-1">20-Day MA</div>
                          <div className="text-lg font-semibold">{analysis.vix_data.ma_20.toFixed(2)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-500 mb-1">Intraday High</div>
                          <div className="text-lg font-semibold">{analysis.vix_data.intraday_high.toFixed(2)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-500 mb-1">Intraday Low</div>
                          <div className="text-lg font-semibold">{analysis.vix_data.intraday_low.toFixed(2)}</div>
                        </div>
                      </div>

                      {/* Spike Warning */}
                      {analysis.vix_data.spike_detected && (
                        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3">
                          <div className="flex items-center gap-2">
                            <AlertTriangle className="w-4 h-4 text-red-400" />
                            <div className="text-sm text-red-400 font-semibold">
                              VIX SPIKE DETECTED - Dealer amplification likely active
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Volatility Regime Card */}
                {analysis.volatility_regime && (
                  <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
                    <div className="flex items-center gap-2 mb-4">
                      <Activity className="w-5 h-5 text-cyan-400" />
                      <h2 className="text-xl font-bold">Volatility Regime</h2>
                    </div>

                    <div className="space-y-4">
                      {/* Regime Type */}
                      <div className={`rounded-lg p-4 border-2 ${
                        analysis.volatility_regime.regime === 'EXPLOSIVE_VOLATILITY' ? 'bg-red-500/10 border-red-500/50' :
                        analysis.volatility_regime.regime === 'FLIP_POINT_CRITICAL' ? 'bg-purple-500/10 border-purple-500/50' :
                        analysis.volatility_regime.regime === 'NEGATIVE_GAMMA_RISK' ? 'bg-orange-500/10 border-orange-500/50' :
                        analysis.volatility_regime.regime === 'COMPRESSION_PIN' ? 'bg-blue-500/10 border-blue-500/50' :
                        'bg-green-500/10 border-green-500/50'
                      }`}>
                        <div className="text-sm text-gray-400 mb-2">Current Regime</div>
                        <div className={`text-xl font-bold mb-2 ${
                          analysis.volatility_regime.regime === 'EXPLOSIVE_VOLATILITY' ? 'text-red-400' :
                          analysis.volatility_regime.regime === 'FLIP_POINT_CRITICAL' ? 'text-purple-400' :
                          analysis.volatility_regime.regime === 'NEGATIVE_GAMMA_RISK' ? 'text-orange-400' :
                          analysis.volatility_regime.regime === 'COMPRESSION_PIN' ? 'text-blue-400' :
                          'text-green-400'
                        }`}>
                          {analysis.volatility_regime.regime.replace(/_/g, ' ')}
                        </div>
                        <div className="text-sm text-gray-300">
                          {analysis.volatility_regime.description}
                        </div>
                      </div>

                      {/* Risk Level */}
                      <div className="bg-gray-950/50 rounded-lg p-3">
                        <div className="flex items-center justify-between">
                          <div className="text-sm text-gray-400">Risk Level</div>
                          <div className={`text-lg font-bold ${
                            analysis.volatility_regime.risk_level === 'extreme' ? 'text-red-400' :
                            analysis.volatility_regime.risk_level === 'high' ? 'text-orange-400' :
                            analysis.volatility_regime.risk_level === 'medium' ? 'text-yellow-400' :
                            'text-green-400'
                          }`}>
                            {analysis.volatility_regime.risk_level.toUpperCase()}
                          </div>
                        </div>
                      </div>

                      {/* Flip Point Alert */}
                      {analysis.volatility_regime.at_flip_point && analysis.zero_gamma_level && (
                        <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg p-4">
                          <div className="flex items-center gap-2 mb-2">
                            <Target className="w-5 h-5 text-purple-400" />
                            <div className="text-sm font-semibold text-purple-400">AT FLIP POINT!</div>
                          </div>
                          <div className="text-sm text-gray-300">
                            Price at zero gamma level <span className="font-bold text-purple-400">${analysis.zero_gamma_level.toFixed(2)}</span>
                          </div>
                          <div className="text-xs text-gray-400 mt-1">
                            Distance: {analysis.volatility_regime.flip_point_distance_pct.toFixed(3)}%
                          </div>
                          <div className="text-xs text-yellow-400 mt-2">
                            ⚠️ Explosive breakout imminent - direction unclear but magnitude will be large
                          </div>
                        </div>
                      )}

                      {/* Zero Gamma Level (if not at flip point but has data) */}
                      {!analysis.volatility_regime.at_flip_point && analysis.zero_gamma_level && (
                        <div className="bg-gray-950/50 rounded-lg p-3">
                          <div className="text-xs text-gray-500 mb-1">Zero Gamma Level</div>
                          <div className="flex items-center justify-between">
                            <div className="text-lg font-semibold">${analysis.zero_gamma_level.toFixed(2)}</div>
                            <div className="text-sm text-gray-400">
                              {analysis.volatility_regime.flip_point_distance_pct.toFixed(2)}% away
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Liberation Setups & False Floors */}
            {(liberationSetups.length > 0 || falseFloors.length > 0) && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Liberation Setups */}
                {liberationSetups.length > 0 && (
                  <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
                    <div className="flex items-center gap-2 mb-4">
                      <Zap className="w-5 h-5 text-green-400" />
                      <h2 className="text-xl font-bold">Liberation Setups</h2>
                      <div className="px-2 py-1 bg-green-500/20 rounded-full text-xs font-semibold text-green-400">
                        {liberationSetups.length}
                      </div>
                    </div>

                    <div className="space-y-3">
                      {liberationSetups.slice(0, 3).map((setup, idx) => (
                        <div key={idx} className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
                          <div className="flex items-center justify-between mb-2">
                            <div className="font-semibold">
                              ${setup.liberation_target_strike?.toFixed(2)}
                            </div>
                            <div className="text-sm text-gray-400">
                              {setup.liberation_expiry_date}
                            </div>
                          </div>
                          <div className="text-sm text-gray-300">
                            Wall expires soon - breakout likely
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* False Floors */}
                {falseFloors.length > 0 && (
                  <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
                    <div className="flex items-center gap-2 mb-4">
                      <AlertTriangle className="w-5 h-5 text-orange-400" />
                      <h2 className="text-xl font-bold">False Floor Warnings</h2>
                      <div className="px-2 py-1 bg-orange-500/20 rounded-full text-xs font-semibold text-orange-400">
                        {falseFloors.length}
                      </div>
                    </div>

                    <div className="space-y-3">
                      {falseFloors.slice(0, 3).map((floor, idx) => (
                        <div key={idx} className="bg-orange-500/10 border border-orange-500/30 rounded-lg p-4">
                          <div className="flex items-center justify-between mb-2">
                            <div className="font-semibold">
                              ${floor.false_floor_strike?.toFixed(2)}
                            </div>
                            <div className="text-sm text-gray-400">
                              {floor.false_floor_expiry_date}
                            </div>
                          </div>
                          <div className="text-sm text-gray-300">
                            Temporary support - expires soon
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
        </div>
      </main>
    </div>
  )
}
