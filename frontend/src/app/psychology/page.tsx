'use client'

import { logger } from '@/lib/logger'

import { useState, useEffect } from 'react'
import { Brain, AlertTriangle, TrendingUp, TrendingDown, Target, Clock, Shield, Zap, RefreshCw, Activity, Calendar, Sparkles, BarChart3, Eye, EyeOff, PlayCircle, TrendingUpIcon } from 'lucide-react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import TradingGuide from '@/components/TradingGuide'
import PsychologyNotifications from '@/components/PsychologyNotifications'
import InfoTooltip from '@/components/InfoTooltip'
import PsychologyTrapSection from '@/components/PsychologyTrapSection'
import YourEdgeSection from '@/components/YourEdgeSection'
import TradingPsychologySection from '@/components/TradingPsychologySection'
import LiveMonitoringSection from '@/components/LiveMonitoringSection'
import AdjustmentStrategiesSection from '@/components/AdjustmentStrategiesSection'
import WhyTheyLoseWhyWeWin from '@/components/WhyTheyLoseWhyWeWin'
import RedFlagsSection from '@/components/RedFlagsSection'
import DealerMechanicsDeepDive from '@/components/DealerMechanicsDeepDive'
import { usePsychologyRegime, useLiberationSetups, useFalseFloors } from '@/lib/hooks/useMarketData'

// API_URL kept for potential direct fetch fallback only

interface RSIAnalysis {
  score: number
  individual_rsi: {
    '5m': number | null
    '15m': number | null
    '1h': number | null
    '4h': number | null
    '1d': number | null
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

interface MarketStatus {
  is_open: boolean
  timestamp: string
  market_time: string
  status_text: string
  data_age_minutes: number
}

interface AIRecommendation {
  narrative: string
  specific_trade: {
    strike: number
    option_type: string
    expiration: string
    entry_price: number
    target: number
    stop: number
  } | null
  entry_triggers: string[]
  exit_triggers: string[]
  probability: number
  risk_reward: string
  time_window: string
  generated_at: string
  regime_type: string
  confidence: number
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

interface HistoricalComparison {
  yesterday_gamma: number | null
  change_since_yesterday: number | null
  change_pct: number | null
  '7d_avg_gamma': number | null
  vs_7d_avg: number | null
  trend: string
  has_historical_data: boolean
}

interface BacktestStats {
  total_signals: number
  wins: number
  losses: number
  win_rate: number
  avg_gain: number
  avg_loss: number
  expectancy: number
  best_trade: number
  worst_trade: number
  avg_hold_days: number
  has_data: boolean
}

export default function PsychologyTrapDetection() {
  const sidebarPadding = useSidebarPadding()
  const [symbol, setSymbol] = useState('SPY')
  const [isAdvancedView, setIsAdvancedView] = useState(false)
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true)
  const [nextRefreshIn, setNextRefreshIn] = useState(60)

  // SWR hooks for data fetching with caching
  const {
    data: regimeResponse,
    error: regimeError,
    isLoading: regimeLoading,
    isValidating: isRefreshing,
    mutate: mutateRegime
  } = usePsychologyRegime(symbol, {
    refreshInterval: autoRefreshEnabled ? 60 * 1000 : 0
  })

  const { data: liberationResponse } = useLiberationSetups()
  const { data: falseFloorsResponse } = useFalseFloors()

  // Extract data from SWR responses
  const regimeData = regimeResponse?.data || regimeResponse
  const analysis = regimeData?.analysis as RegimeAnalysis | null
  const tradingGuide = regimeData?.trading_guide || null
  const aiRecommendation = regimeData?.ai_recommendation as AIRecommendation | null
  const marketStatus = regimeData?.market_status as MarketStatus | null
  const historicalComparison = regimeData?.historical_comparison as HistoricalComparison | null
  const backtestStats = regimeData?.backtest_stats as BacktestStats | null

  const liberationSetups = liberationResponse?.data?.liberation_setups || []
  const falseFloors = falseFloorsResponse?.data?.false_floors || []

  const loading = regimeLoading && !analysis
  const error = regimeError ? regimeError.message || 'Failed to fetch analysis' : null

  // Manual refresh function
  const handleRefresh = () => {
    mutateRegime()
  }

  // Auto-refresh countdown timer (visual only - SWR handles actual refresh)
  useEffect(() => {
    if (!autoRefreshEnabled || !marketStatus?.is_open) {
      setNextRefreshIn(60)
      return
    }

    const interval = setInterval(() => {
      setNextRefreshIn((prev) => {
        if (prev <= 1) {
          return 60
        }
        return prev - 1
      })
    }, 1000)

    return () => clearInterval(interval)
  }, [autoRefreshEnabled, marketStatus])

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
      'SHORT_GAMMA_MOMENTUM': 'text-amber-400',
      'GAMMA_SQUEEZE_CASCADE': 'text-red-600',
      'FLIP_POINT_CRITICAL': 'text-pink-500',
      'POST_OPEX_REGIME_FLIP': 'text-indigo-400',
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
    const getRSIColor = (value: number | null) => {
      if (value === null) return 'bg-gray-700'
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
                style={{ width: value !== null ? `${value}%` : '0%' }}
              />
            </div>
            <div className="w-16 text-sm font-mono text-right">
              {value !== null ? value.toFixed(1) : '---'}
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <Navigation />

      <main className={`pt-24 transition-all duration-300 ${sidebarPadding}`}>
        <div className="container mx-auto px-4 py-8 space-y-6">
          {/* Header */}
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <Brain className="w-8 h-8 text-purple-400" />
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-3xl font-bold">{symbol}</h1>
                  <span className="text-2xl text-gray-500">Psychology Trap Analysis</span>
                </div>
                <p className="text-sm text-gray-400">
                  Identify when retail traders get trapped by ignoring market structure
                </p>
              </div>
            </div>
            <div className="flex items-center gap-4 text-sm">
              {marketStatus && (
                <>
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${marketStatus.is_open ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
                    <span className="font-semibold text-white">MARKET: {marketStatus.status_text}</span>
                  </div>
                  <span className="text-gray-600">|</span>
                  <div className="flex items-center gap-1 text-gray-400">
                    <Clock className="w-4 h-4" />
                    <span>{marketStatus.market_time}</span>
                    {!marketStatus.is_open && marketStatus.data_age_minutes > 0 && (
                      <span className="text-yellow-500 ml-2">(Data {marketStatus.data_age_minutes} min old)</span>
                    )}
                  </div>
                </>
              )}
              {analysis?.timestamp && !marketStatus && (
                <div className="flex items-center gap-1 text-gray-500">
                  <Clock className="w-4 h-4" />
                  <span>Updated: {new Date(analysis.timestamp).toLocaleString()}</span>
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Auto-refresh toggle */}
            {marketStatus?.is_open && (
              <button
                onClick={() => setAutoRefreshEnabled(!autoRefreshEnabled)}
                className={`px-3 py-2 rounded-lg flex items-center gap-2 text-sm ${
                  autoRefreshEnabled ? 'bg-green-600 hover:bg-green-700' : 'bg-gray-600 hover:bg-gray-700'
                }`}
              >
                {autoRefreshEnabled ? (
                  <>
                    <Activity className="w-4 h-4 animate-pulse" />
                    Auto {nextRefreshIn}s
                  </>
                ) : (
                  <>
                    <Clock className="w-4 h-4" />
                    Auto Off
                  </>
                )}
              </button>
            )}

            {/* Simple/Advanced toggle */}
            <button
              onClick={() => setIsAdvancedView(!isAdvancedView)}
              className="px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg flex items-center gap-2 text-sm"
            >
              {isAdvancedView ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              {isAdvancedView ? 'Simple' : 'Advanced'}
            </button>

            {/* Manual refresh */}
            <button
              onClick={handleRefresh}
              disabled={isRefreshing}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg flex items-center gap-2 disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
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
            {/* 1. PSYCHOLOGY TRAP - Top Priority */}
            <PsychologyTrapSection
              regimeType={analysis.regime.primary_type}
              psychologyTrap={analysis.regime.psychology_trap}
              currentPrice={analysis.spy_price}
              callWallStrike={analysis.current_walls?.call_wall?.strike}
              putWallStrike={analysis.current_walls?.put_wall?.strike}
              sentiment={`${Math.round(analysis.rsi_analysis?.score || 50)}% ${(analysis.rsi_analysis?.score || 50) > 50 ? 'bullish' : 'bearish'}`}
            />

            {/* 2. YOUR EDGE - Data Proof */}
            <YourEdgeSection
              netGex={analysis.current_walls?.net_gamma || 0}
              volumeRatio={analysis.volume_ratio || 1.0}
              strikePrice={analysis.current_walls?.call_wall?.strike || analysis.spy_price}
              volumeAtStrike={Math.round((analysis.current_walls?.call_wall?.strength || 0) / 1000)}
              openInterestAtStrike={Math.round((analysis.current_walls?.call_wall?.strength || 0) / 500)}
              historicalWinRate={backtestStats?.win_rate || 73}
              historicalAvgGain={backtestStats?.avg_gain || 180}
              historicalAvgLoss={backtestStats?.avg_loss || 70}
              ivRank={analysis.vix_data ? Math.min(100, Math.round((analysis.vix_data.current / 30) * 100)) : 50}
              thetaDecay={0.08}
              expectedValue={backtestStats?.expectancy || 180}
            />

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

            {/* Strike Levels */}
            {analysis.current_walls && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Call Wall */}
                {analysis.current_walls.call_wall && (
                  <div className="bg-gradient-to-br from-green-900/20 to-green-800/10 border border-green-500/30 rounded-lg p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <TrendingUp className="w-5 h-5 text-green-400" />
                      <span className="text-sm text-gray-400">Call Wall (Resistance)</span>
                    </div>
                    <div className="text-3xl font-bold text-green-400">
                      ${analysis.current_walls.call_wall.strike?.toFixed(2) || 'N/A'}
                    </div>
                    {analysis.current_walls.call_wall.distance_pct !== null && (
                      <div className="text-sm text-gray-400 mt-1">
                        {analysis.current_walls.call_wall.distance_pct > 0 ? '▲' : '▼'} {Math.abs(analysis.current_walls.call_wall.distance_pct).toFixed(2)}% away
                      </div>
                    )}
                  </div>
                )}

                {/* Put Wall */}
                {analysis.current_walls.put_wall && (
                  <div className="bg-gradient-to-br from-red-900/20 to-red-800/10 border border-red-500/30 rounded-lg p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <TrendingDown className="w-5 h-5 text-red-400" />
                      <span className="text-sm text-gray-400">Put Wall (Support)</span>
                    </div>
                    <div className="text-3xl font-bold text-red-400">
                      ${analysis.current_walls.put_wall.strike?.toFixed(2) || 'N/A'}
                    </div>
                    {analysis.current_walls.put_wall.distance_pct !== null && (
                      <div className="text-sm text-gray-400 mt-1">
                        {analysis.current_walls.put_wall.distance_pct > 0 ? '▲' : '▼'} {Math.abs(analysis.current_walls.put_wall.distance_pct).toFixed(2)}% away
                      </div>
                    )}
                  </div>
                )}

                {/* Zero Gamma Level / Flip Point */}
                {analysis.zero_gamma_level && (
                  <div className="bg-gradient-to-br from-purple-900/20 to-purple-800/10 border border-purple-500/30 rounded-lg p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Target className="w-5 h-5 text-purple-400" />
                      <span className="text-sm text-gray-400">Flip Point (Zero Gamma)</span>
                      <InfoTooltip content="The price level where cumulative gamma exposure crosses zero. When price crosses this level, dealer hedging behavior reverses, often creating explosive moves." />
                    </div>
                    <div className="text-3xl font-bold text-purple-400">
                      ${analysis.zero_gamma_level.toFixed(2)}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      Dealer hedging changes direction
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Prominent CTA Section */}
            {aiRecommendation && aiRecommendation.specific_trade && (
              <div className="bg-gradient-to-r from-purple-600 to-pink-600 rounded-xl p-6 shadow-2xl">
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <Sparkles className="w-8 h-8 text-white" />
                      <h2 className="text-2xl font-bold text-white">Ready to Trade This Setup?</h2>
                    </div>
                    <p className="text-purple-100 text-lg">
                      {aiRecommendation.probability}% win probability • {aiRecommendation.risk_reward} R:R
                    </p>
                  </div>
                  <button
                    onClick={() => window.open('/trader', '_blank')}
                    className="px-8 py-4 bg-white text-purple-600 hover:bg-gray-100 rounded-lg font-bold text-lg flex items-center gap-3 shadow-lg transition-all hover:scale-105"
                  >
                    <PlayCircle className="w-6 h-6" />
                    Paper Trade Now
                  </button>
                </div>
              </div>
            )}

            {/* AI Recommendation */}
            {aiRecommendation && aiRecommendation.narrative && (
              <div className="bg-gradient-to-br from-blue-900/20 to-indigo-800/10 border-2 border-blue-500/30 rounded-xl p-6 space-y-4">
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles className="w-6 h-6 text-blue-400" />
                  <h2 className="text-2xl font-bold text-blue-400">AI Trade Recommendation</h2>
                  <span className="text-xs text-gray-400">Powered by Claude Haiku 4.5</span>
                  <InfoTooltip content="AI-generated trade recommendation based on current market regime, gamma positioning, RSI analysis, and historical pattern performance." />
                </div>

                {/* AI Narrative */}
                <div className="bg-gray-950/50 rounded-lg p-4">
                  <p className="text-gray-300 whitespace-pre-line">{aiRecommendation.narrative}</p>
                </div>

                {/* Specific Trade */}
                {aiRecommendation.specific_trade && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="bg-gray-950/50 rounded-lg p-4">
                      <h3 className="text-lg font-semibold text-white mb-3">Specific Trade</h3>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">Strike:</span>
                          <span className="text-white font-mono">${aiRecommendation.specific_trade.strike}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Type:</span>
                          <span className="text-white uppercase">{aiRecommendation.specific_trade.option_type}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Expiration:</span>
                          <span className="text-white">{aiRecommendation.specific_trade.expiration}</span>
                        </div>
                        <div className="flex justify-between border-t border-gray-700 pt-2 mt-2">
                          <span className="text-gray-400">Entry:</span>
                          <span className="text-green-400 font-mono">${aiRecommendation.specific_trade.entry_price.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Target:</span>
                          <span className="text-green-400 font-mono">${aiRecommendation.specific_trade.target.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Stop:</span>
                          <span className="text-red-400 font-mono">${aiRecommendation.specific_trade.stop.toFixed(2)}</span>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <div className="bg-gray-950/50 rounded-lg p-4">
                        <h3 className="text-lg font-semibold text-white mb-2">Win Probability</h3>
                        <div className="flex items-baseline gap-2">
                          <span className="text-4xl font-bold text-green-400">{aiRecommendation.probability}%</span>
                          <span className="text-sm text-gray-400">success rate</span>
                        </div>
                        <div className="mt-2 text-sm text-gray-400">
                          Risk/Reward: <span className="text-white font-semibold">{aiRecommendation.risk_reward}</span>
                        </div>
                      </div>

                      <div className="bg-gray-950/50 rounded-lg p-4">
                        <h3 className="text-sm font-semibold text-gray-400 mb-2">Best Entry Window</h3>
                        <div className="text-white">{aiRecommendation.time_window}</div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Entry/Exit Triggers */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {aiRecommendation.entry_triggers && aiRecommendation.entry_triggers.length > 0 && (
                    <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
                      <h3 className="text-lg font-semibold text-green-400 mb-2">Entry Triggers</h3>
                      <ul className="space-y-1 text-sm text-gray-300">
                        {aiRecommendation.entry_triggers.map((trigger, idx) => (
                          <li key={idx} className="flex items-start gap-2">
                            <span className="text-green-400 mt-1">▸</span>
                            <span>{trigger}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {aiRecommendation.exit_triggers && aiRecommendation.exit_triggers.length > 0 && (
                    <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
                      <h3 className="text-lg font-semibold text-red-400 mb-2">Exit Triggers</h3>
                      <ul className="space-y-1 text-sm text-gray-300">
                        {aiRecommendation.exit_triggers.map((trigger, idx) => (
                          <li key={idx} className="flex items-start gap-2">
                            <span className="text-red-400 mt-1">▸</span>
                            <span>{trigger}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Historical Comparison & Backtest Stats */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Historical Comparison */}
              {historicalComparison && historicalComparison.has_historical_data && (
                <div className="bg-gradient-to-br from-gray-900/50 to-gray-800/50 border border-gray-700 rounded-lg p-6">
                  <div className="flex items-center gap-2 mb-4">
                    <Calendar className="w-5 h-5 text-blue-400" />
                    <h3 className="text-lg font-semibold text-white">Historical Context</h3>
                  </div>

                  <div className="space-y-3">
                    {historicalComparison.change_since_yesterday !== null && (
                      <div>
                        <div className="text-sm text-gray-400 mb-1">Change Since Yesterday</div>
                        <div className="flex items-baseline gap-2">
                          <span className={`text-2xl font-bold ${historicalComparison.change_since_yesterday >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {historicalComparison.change_since_yesterday >= 0 ? '+' : ''}{(historicalComparison.change_since_yesterday / 1e9).toFixed(2)}B
                          </span>
                          {historicalComparison.change_pct !== null && (
                            <span className={`text-sm ${historicalComparison.change_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              ({historicalComparison.change_pct >= 0 ? '+' : ''}{historicalComparison.change_pct.toFixed(1)}%)
                            </span>
                          )}
                        </div>
                      </div>
                    )}

                    {historicalComparison['7d_avg_gamma'] !== null && (
                      <div>
                        <div className="text-sm text-gray-400 mb-1">vs 7-Day Average</div>
                        <div className="flex items-baseline gap-2">
                          <span className="text-lg font-mono text-white">
                            {(historicalComparison['7d_avg_gamma'] / 1e9).toFixed(2)}B
                          </span>
                          {historicalComparison.vs_7d_avg !== null && (
                            <span className={`text-sm ${historicalComparison.vs_7d_avg >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              ({historicalComparison.vs_7d_avg >= 0 ? '+' : ''}{historicalComparison.vs_7d_avg.toFixed(1)}%)
                            </span>
                          )}
                        </div>
                      </div>
                    )}

                    <div>
                      <div className="text-sm text-gray-400 mb-1">Trend</div>
                      <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-semibold ${
                        historicalComparison.trend === 'increasing' ? 'bg-green-500/20 text-green-400' :
                        historicalComparison.trend === 'decreasing' ? 'bg-red-500/20 text-red-400' :
                        'bg-gray-500/20 text-gray-400'
                      }`}>
                        {historicalComparison.trend === 'increasing' && '↗'}
                        {historicalComparison.trend === 'decreasing' && '↘'}
                        {historicalComparison.trend === 'stable' && '→'}
                        <span className="uppercase">{historicalComparison.trend}</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Backtest Statistics */}
              {backtestStats && backtestStats.has_data && (
                <div className="bg-gradient-to-br from-purple-900/20 to-indigo-800/20 border border-purple-500/30 rounded-lg p-6">
                  <div className="flex items-center gap-2 mb-4">
                    <BarChart3 className="w-5 h-5 text-purple-400" />
                    <h3 className="text-lg font-semibold text-white">Backtest Performance</h3>
                    <span className="text-xs text-gray-400">({backtestStats.total_signals} signals)</span>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <div className="text-sm text-gray-400 mb-1">Win Rate</div>
                      <div className="text-3xl font-bold text-green-400">{backtestStats.win_rate}%</div>
                      <div className="text-xs text-gray-500">{backtestStats.wins}W / {backtestStats.losses}L</div>
                    </div>

                    <div>
                      <div className="text-sm text-gray-400 mb-1">Expectancy</div>
                      <div className={`text-3xl font-bold ${backtestStats.expectancy >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {backtestStats.expectancy >= 0 ? '+' : ''}{backtestStats.expectancy.toFixed(2)}%
                      </div>
                      <div className="text-xs text-gray-500">per trade</div>
                    </div>

                    <div>
                      <div className="text-sm text-gray-400 mb-1">Avg Win</div>
                      <div className="text-lg font-mono text-green-400">+{backtestStats.avg_gain.toFixed(2)}%</div>
                    </div>

                    <div>
                      <div className="text-sm text-gray-400 mb-1">Avg Loss</div>
                      <div className="text-lg font-mono text-red-400">{backtestStats.avg_loss.toFixed(2)}%</div>
                    </div>

                    <div>
                      <div className="text-sm text-gray-400 mb-1">Best Trade</div>
                      <div className="text-sm font-mono text-green-400">+{backtestStats.best_trade.toFixed(2)}%</div>
                    </div>

                    <div>
                      <div className="text-sm text-gray-400 mb-1">Worst Trade</div>
                      <div className="text-sm font-mono text-red-400">{backtestStats.worst_trade.toFixed(2)}%</div>
                    </div>
                  </div>

                  <div className="mt-4 pt-4 border-t border-gray-700">
                    <div className="text-xs text-gray-400 text-center">
                      Based on last {backtestStats.total_signals} {analysis.regime.primary_type.replace(/_/g, ' ')} signals
                    </div>
                  </div>
                </div>
              )}
            </div>

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

            {/* 3. TRADING PSYCHOLOGY - Emotional Discipline */}
            <TradingPsychologySection
              winRate={backtestStats?.win_rate || 73}
              strikePrice={analysis.current_walls?.call_wall?.strike || analysis.spy_price}
            />

            {/* 4. IS IT WORKING? - Live Monitoring */}
            <LiveMonitoringSection
              currentPrice={analysis.spy_price}
              wallStrike={analysis.current_walls?.call_wall?.strike || analysis.spy_price}
              volumeRatio={analysis.volume_ratio || 1.0}
              premiumValue={1.20}
              entryPremium={1.85}
              ivRank={analysis.vix_data ? Math.min(100, Math.round((analysis.vix_data.current / 30) * 100)) : 50}
              daysInTrade={2}
            />

            {/* 5. WHAT IF WRONG? - Adjustment Strategies */}
            <AdjustmentStrategiesSection
              wallStrike={analysis.current_walls?.call_wall?.strike || analysis.spy_price}
            />

            {/* 6. WHY THEY LOSE vs WHY WE WIN */}
            <WhyTheyLoseWhyWeWin
              strikePrice={analysis.current_walls?.call_wall?.strike || analysis.spy_price}
              volumeRatio={analysis.volume_ratio || 1.0}
              winRate={backtestStats?.win_rate || 73}
            />

            {/* 7. RED FLAGS - When NOT to Trade */}
            <RedFlagsSection
              netGex={analysis.current_walls?.net_gamma || 0}
              volumeRatio={analysis.volume_ratio || 1.0}
              ivRank={analysis.vix_data ? Math.min(100, Math.round((analysis.vix_data.current / 30) * 100)) : 50}
              currentPrice={analysis.spy_price}
              strikePrice={analysis.current_walls?.call_wall?.strike || analysis.spy_price}
              daysToExpiration={analysis.expiration_analysis?.nearest_expiration_dte || 5}
            />

            {/* 8. DEALER MECHANICS DEEP DIVE - Collapsible */}
            <DealerMechanicsDeepDive
              netGex={analysis.current_walls?.net_gamma || 0}
              volumeRatio={analysis.volume_ratio || 1.0}
              currentPrice={analysis.spy_price}
              strikePrice={analysis.current_walls?.call_wall?.strike || analysis.spy_price}
              openInterest={Math.round((analysis.current_walls?.call_wall?.strength || 0) / 500)}
              volume={Math.round((analysis.current_walls?.call_wall?.strength || 0) / 1000)}
            />

            {/* Advanced View Content - Only show if toggled */}
            {isAdvancedView && (
            <>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* RSI Heatmap */}
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
                <div className="flex items-center gap-2 mb-4">
                  <Activity className="w-5 h-5 text-purple-400" />
                  <h2 className="text-xl font-bold">Multi-Timeframe RSI</h2>
                  <InfoTooltip content="Relative Strength Index across 5 timeframes (5m, 15m, 1h, 4h, 1d). When multiple timeframes align above 70 (overbought) or below 30 (oversold), it signals strong momentum or potential reversal." />
                  {analysis.rsi_analysis.coiling_detected && (
                    <div className="px-2 py-1 bg-yellow-500/20 rounded text-xs font-semibold text-yellow-400">
                      COILING
                      <InfoTooltip content="Coiling occurs when RSI is compressed in the middle range across multiple timeframes, indicating a potential explosive breakout in either direction." />
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
                      {liberationSetups.slice(0, 3).map((setup: { liberation_target_strike?: number; liberation_expiry_date?: string }, idx: number) => (
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
                      {falseFloors.slice(0, 3).map((floor: { false_floor_strike?: number; false_floor_expiry_date?: string }, idx: number) => (
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
            {/* End Advanced View */}
          </>
        )}
        </div>
      </main>
    </div>
  )
}
