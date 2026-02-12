'use client'

import React, { useState } from 'react'
import {
  Zap, Play, Loader2, AlertTriangle, ChevronDown, ChevronUp,
  Shield, CheckCircle, XCircle, Layers, Brain,
  Minus, ArrowLeft, BarChart2, TrendingUp, TrendingDown,
  Activity, Clock, Cpu, Info, Target
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import { apiClient } from '@/lib/api'

// ==================== TYPES ====================

interface ProverbsVerdict {
  can_trade: boolean
  reason: string
  consecutive_losses: number
  daily_loss_pct: number
  is_killed: boolean
  authority: string
}

interface EnsembleContext {
  signal: string
  confidence: number
  bullish_weight: number
  bearish_weight: number
  neutral_weight: number
  component_signals: Record<string, any>
  position_size_multiplier: number
  regime: string
  authority: string
}

interface MLAdvisorDecision {
  advice: string
  win_probability: number
  confidence: number
  suggested_risk_pct: number
  suggested_sd_multiplier: number
  top_factors: [string, number][]
  model_version: string
  needs_retraining: boolean
  authority: string
}

interface ProphetAdaptation {
  bot_name: string
  suggested_put_strike: number | null
  suggested_call_strike: number | null
  use_gex_walls: boolean
  risk_adjustment: number
  reasoning: string
  authority: string
}

interface OmegaDecisionResult {
  timestamp: string
  bot_name: string
  final_decision: string
  final_risk_pct: number
  final_position_size_multiplier: number
  proverbs_verdict: ProverbsVerdict
  ensemble_context: EnsembleContext
  ml_decision: MLAdvisorDecision
  prophet_adaptation: ProphetAdaptation
  capital_allocation: Record<string, number>
  equity_scaled_risk: number
  correlation_check: Record<string, any>
  regime_transition: string | null
  decision_path: string[]
}

interface SimulationResponse {
  status: string
  simulation: boolean
  input: {
    bot_name: string
    market_conditions: Record<string, any>
  }
  decision: OmegaDecisionResult
  timestamp: string
}

// ==================== DECISION BADGE ====================

const DecisionBadge = ({ decision }: { decision: string }) => {
  const config: Record<string, { bg: string; text: string; icon: any }> = {
    TRADE_FULL: { bg: 'bg-green-500/15 border-green-500/30', text: 'text-green-400', icon: CheckCircle },
    TRADE_REDUCED: { bg: 'bg-yellow-500/15 border-yellow-500/30', text: 'text-yellow-400', icon: Minus },
    SKIP_TODAY: { bg: 'bg-gray-500/15 border-gray-500/30', text: 'text-gray-400', icon: XCircle },
    BLOCKED_BY_PROVERBS: { bg: 'bg-red-500/15 border-red-500/30', text: 'text-red-400', icon: Shield },
  }
  const c = config[decision] || config.SKIP_TODAY
  const Icon = c.icon

  return (
    <span className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold border ${c.bg} ${c.text}`}>
      <Icon className="w-4 h-4" />
      {decision.replace(/_/g, ' ')}
    </span>
  )
}

// ==================== LAYER RESULT CARD ====================

const LayerResultCard = ({
  layerNumber,
  name,
  icon: Icon,
  borderColor,
  children,
}: {
  layerNumber: number
  name: string
  icon: any
  borderColor: string
  children: React.ReactNode
}) => (
  <div className={`bg-background-card border ${borderColor} rounded-lg p-4 shadow-card`}>
    <div className="flex items-center gap-2 mb-3">
      <Icon className="w-5 h-5 text-blue-400" />
      <span className="text-xs font-bold text-blue-400">L{layerNumber}</span>
      <span className="text-sm font-semibold text-text-primary">{name}</span>
    </div>
    {children}
  </div>
)

// ==================== MAIN PAGE ====================

export default function OmegaSimulator() {
  const sidebarPadding = useSidebarPadding()
  // Input state
  const [selectedBot, setSelectedBot] = useState('FORTRESS')
  const [vixValue, setVixValue] = useState(20)
  const [spotPrice, setSpotPrice] = useState(585)
  const [gexRegime, setGexRegime] = useState('POSITIVE')
  const [priceTrend, setPriceTrend] = useState('NEUTRAL')
  const [dayOfWeek, setDayOfWeek] = useState(1)
  const [expectedMove, setExpectedMove] = useState(1.0)
  const [netGamma, setNetGamma] = useState(0)
  const [showOptional, setShowOptional] = useState(false)
  const [flipPoint, setFlipPoint] = useState<number | ''>('')
  const [putWall, setPutWall] = useState<number | ''>('')
  const [callWall, setCallWall] = useState<number | ''>('')

  // Output state
  const [result, setResult] = useState<SimulationResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const bots = [
    { value: 'FORTRESS', label: 'FORTRESS', desc: 'SPY 0DTE IC' },
    { value: 'ANCHOR', label: 'ANCHOR', desc: 'SPX Weekly IC' },
    { value: 'SOLOMON', label: 'SOLOMON', desc: 'SPY Directional' },
    { value: 'LAZARUS', label: 'LAZARUS', desc: 'SPY Call Entries' },
    { value: 'CORNERSTONE', label: 'CORNERSTONE', desc: 'SPY Cash-Secured Puts' },
  ]

  const days = [
    { value: 0, label: 'Monday' },
    { value: 1, label: 'Tuesday' },
    { value: 2, label: 'Wednesday' },
    { value: 3, label: 'Thursday' },
    { value: 4, label: 'Friday' },
  ]

  const runSimulation = async () => {
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await apiClient.simulateOmegaDecision({
        bot_name: selectedBot,
        vix: vixValue,
        spot_price: spotPrice,
        gex_regime: gexRegime,
        price_trend: priceTrend,
        day_of_week: dayOfWeek,
        expected_move_pct: expectedMove,
        net_gamma: netGamma,
        flip_point: flipPoint !== '' ? flipPoint : undefined,
        put_wall: putWall !== '' ? putWall : undefined,
        call_wall: callWall !== '' ? callWall : undefined,
      })
      setResult(response.data as SimulationResponse)
    } catch (err: any) {
      const message = err?.response?.data?.detail || err?.message || 'Simulation failed. Check that the backend is running.'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  const decision = result?.decision

  return (
    <div className="min-h-screen bg-background-deep text-text-primary">
      <Navigation />
      <main className={`pt-24 transition-all duration-300 ${sidebarPadding}`}>
        <div className="max-w-[1800px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="flex items-center gap-3">
              <Zap className="w-7 h-7 text-yellow-400" />
              <h1 className="text-2xl font-bold">OMEGA Simulator</h1>
            </div>
            <p className="text-sm text-text-secondary mt-1">
              What-if analysis through the full 4-layer decision pipeline
            </p>
          </div>
          <a
            href="/omega"
            className="flex items-center gap-1.5 px-4 py-2 text-sm bg-gray-700/50 text-text-secondary border border-gray-600 rounded-lg hover:bg-gray-700 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to OMEGA
          </a>
        </div>

        {/* Info Banner */}
        <div className="mb-6 p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg">
          <div className="flex items-center gap-2 text-blue-400 text-xs">
            <Info className="w-4 h-4 flex-shrink-0" />
            <span>
              This simulator runs your inputs through the full OMEGA 4-layer pipeline: PROVERBS safety gate,
              Ensemble context (gutted), WISDOM ML prediction, and Prophet adaptation. No trades are placed.
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* ==================== INPUT PANEL ==================== */}
          <div className="lg:col-span-4">
            <div className="bg-background-card border border-gray-700 rounded-lg p-5 shadow-card sticky top-6">
              <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Activity className="w-5 h-5 text-blue-400" />
                Market Conditions
              </h2>

              {/* Bot Selector */}
              <div className="mb-4">
                <label className="block text-xs text-text-secondary font-medium mb-1.5">Trading Bot</label>
                <select
                  value={selectedBot}
                  onChange={(e) => setSelectedBot(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-sm text-text-primary focus:border-blue-500 focus:outline-none appearance-none cursor-pointer"
                >
                  {bots.map((bot) => (
                    <option key={bot.value} value={bot.value}>
                      {bot.label} - {bot.desc}
                    </option>
                  ))}
                </select>
              </div>

              {/* VIX Slider */}
              <div className="mb-4">
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs text-text-secondary font-medium">VIX</label>
                  <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                    vixValue < 15 ? 'bg-green-500/10 text-green-400' :
                    vixValue < 22 ? 'bg-blue-500/10 text-blue-400' :
                    vixValue < 28 ? 'bg-yellow-500/10 text-yellow-400' :
                    vixValue < 35 ? 'bg-orange-500/10 text-orange-400' :
                    'bg-red-500/10 text-red-400'
                  }`}>
                    {vixValue}
                  </span>
                </div>
                <input
                  type="range"
                  min={10}
                  max={80}
                  step={0.5}
                  value={vixValue}
                  onChange={(e) => setVixValue(parseFloat(e.target.value))}
                  className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                />
                <div className="flex justify-between text-[10px] text-text-secondary mt-0.5">
                  <span>10</span>
                  <span>LOW</span>
                  <span>NORMAL</span>
                  <span>HIGH</span>
                  <span>80</span>
                </div>
              </div>

              {/* SPY Price */}
              <div className="mb-4">
                <label className="block text-xs text-text-secondary font-medium mb-1.5">SPY Price</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary text-sm">$</span>
                  <input
                    type="number"
                    value={spotPrice}
                    onChange={(e) => setSpotPrice(parseFloat(e.target.value) || 0)}
                    step={0.5}
                    className="w-full pl-7 pr-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-sm text-text-primary focus:border-blue-500 focus:outline-none"
                  />
                </div>
              </div>

              {/* GEX Regime */}
              <div className="mb-4">
                <label className="block text-xs text-text-secondary font-medium mb-1.5">GEX Regime</label>
                <div className="grid grid-cols-3 gap-2">
                  {['POSITIVE', 'NEGATIVE', 'NEUTRAL'].map((regime) => (
                    <button
                      key={regime}
                      onClick={() => setGexRegime(regime)}
                      className={`px-3 py-2 text-xs rounded-lg border transition-colors font-medium ${
                        gexRegime === regime
                          ? regime === 'POSITIVE'
                            ? 'bg-green-500/20 border-green-500/40 text-green-400'
                            : regime === 'NEGATIVE'
                            ? 'bg-red-500/20 border-red-500/40 text-red-400'
                            : 'bg-gray-500/20 border-gray-500/40 text-gray-300'
                          : 'bg-gray-800 border-gray-600 text-text-secondary hover:border-gray-500'
                      }`}
                    >
                      {regime}
                    </button>
                  ))}
                </div>
              </div>

              {/* Price Trend */}
              <div className="mb-4">
                <label className="block text-xs text-text-secondary font-medium mb-1.5">Price Trend</label>
                <div className="grid grid-cols-3 gap-2">
                  {['BULLISH', 'BEARISH', 'NEUTRAL'].map((trend) => (
                    <button
                      key={trend}
                      onClick={() => setPriceTrend(trend)}
                      className={`px-3 py-2 text-xs rounded-lg border transition-colors font-medium flex items-center justify-center gap-1 ${
                        priceTrend === trend
                          ? trend === 'BULLISH'
                            ? 'bg-green-500/20 border-green-500/40 text-green-400'
                            : trend === 'BEARISH'
                            ? 'bg-red-500/20 border-red-500/40 text-red-400'
                            : 'bg-gray-500/20 border-gray-500/40 text-gray-300'
                          : 'bg-gray-800 border-gray-600 text-text-secondary hover:border-gray-500'
                      }`}
                    >
                      {trend === 'BULLISH' && <TrendingUp className="w-3 h-3" />}
                      {trend === 'BEARISH' && <TrendingDown className="w-3 h-3" />}
                      {trend === 'NEUTRAL' && <Minus className="w-3 h-3" />}
                      {trend}
                    </button>
                  ))}
                </div>
              </div>

              {/* Day of Week */}
              <div className="mb-4">
                <label className="block text-xs text-text-secondary font-medium mb-1.5">Day of Week</label>
                <div className="grid grid-cols-5 gap-1.5">
                  {days.map((d) => (
                    <button
                      key={d.value}
                      onClick={() => setDayOfWeek(d.value)}
                      className={`px-2 py-2 text-xs rounded-lg border transition-colors font-medium ${
                        dayOfWeek === d.value
                          ? 'bg-blue-500/20 border-blue-500/40 text-blue-400'
                          : 'bg-gray-800 border-gray-600 text-text-secondary hover:border-gray-500'
                      }`}
                    >
                      {d.label.slice(0, 3)}
                    </button>
                  ))}
                </div>
              </div>

              {/* Expected Move */}
              <div className="mb-4">
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs text-text-secondary font-medium">Expected Move %</label>
                  <span className="text-xs font-bold text-text-primary">{expectedMove.toFixed(1)}%</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={5}
                  step={0.1}
                  value={expectedMove}
                  onChange={(e) => setExpectedMove(parseFloat(e.target.value))}
                  className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                />
                <div className="flex justify-between text-[10px] text-text-secondary mt-0.5">
                  <span>0%</span>
                  <span>2.5%</span>
                  <span>5%</span>
                </div>
              </div>

              {/* Net Gamma */}
              <div className="mb-4">
                <label className="block text-xs text-text-secondary font-medium mb-1.5">Net Gamma</label>
                <input
                  type="number"
                  value={netGamma}
                  onChange={(e) => setNetGamma(parseFloat(e.target.value) || 0)}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-sm text-text-primary focus:border-blue-500 focus:outline-none"
                  placeholder="0"
                />
              </div>

              {/* Optional Fields Collapsible */}
              <div className="mb-5">
                <button
                  onClick={() => setShowOptional(!showOptional)}
                  className="flex items-center gap-2 text-xs text-text-secondary hover:text-text-primary transition-colors w-full py-2"
                >
                  {showOptional ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  <span className="font-medium">Optional Fields</span>
                  <span className="text-text-secondary/50">(Flip Point, Put Wall, Call Wall)</span>
                </button>

                {showOptional && (
                  <div className="mt-2 space-y-3 pl-1 border-l-2 border-gray-700 ml-1.5">
                    <div className="pl-3">
                      <label className="block text-xs text-text-secondary font-medium mb-1.5">Flip Point</label>
                      <div className="relative">
                        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary text-sm">$</span>
                        <input
                          type="number"
                          value={flipPoint}
                          onChange={(e) => setFlipPoint(e.target.value ? parseFloat(e.target.value) : '')}
                          step={0.5}
                          placeholder="Auto: spot price"
                          className="w-full pl-7 pr-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-sm text-text-primary focus:border-blue-500 focus:outline-none placeholder:text-gray-600"
                        />
                      </div>
                    </div>
                    <div className="pl-3">
                      <label className="block text-xs text-text-secondary font-medium mb-1.5">Put Wall</label>
                      <div className="relative">
                        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary text-sm">$</span>
                        <input
                          type="number"
                          value={putWall}
                          onChange={(e) => setPutWall(e.target.value ? parseFloat(e.target.value) : '')}
                          step={0.5}
                          placeholder="Auto: spot * 0.98"
                          className="w-full pl-7 pr-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-sm text-text-primary focus:border-blue-500 focus:outline-none placeholder:text-gray-600"
                        />
                      </div>
                    </div>
                    <div className="pl-3">
                      <label className="block text-xs text-text-secondary font-medium mb-1.5">Call Wall</label>
                      <div className="relative">
                        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary text-sm">$</span>
                        <input
                          type="number"
                          value={callWall}
                          onChange={(e) => setCallWall(e.target.value ? parseFloat(e.target.value) : '')}
                          step={0.5}
                          placeholder="Auto: spot * 1.02"
                          className="w-full pl-7 pr-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-sm text-text-primary focus:border-blue-500 focus:outline-none placeholder:text-gray-600"
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Run Button */}
              <button
                onClick={runSimulation}
                disabled={loading}
                className={`w-full py-3 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2 ${
                  loading
                    ? 'bg-gray-700 text-gray-400 cursor-not-allowed'
                    : 'bg-blue-600 text-white hover:bg-blue-500 active:bg-blue-700 shadow-lg shadow-blue-500/20'
                }`}
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Running Pipeline...
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4" />
                    Run Simulation
                  </>
                )}
              </button>
            </div>
          </div>

          {/* ==================== OUTPUT PANEL ==================== */}
          <div className="lg:col-span-8">
            {/* Empty State */}
            {!result && !loading && !error && (
              <div className="bg-background-card border border-gray-700 rounded-lg p-16 shadow-card flex flex-col items-center justify-center text-center">
                <Cpu className="w-16 h-16 text-gray-600 mb-4" />
                <h3 className="text-lg font-semibold text-text-secondary mb-2">No Simulation Results Yet</h3>
                <p className="text-sm text-text-secondary/70 max-w-md">
                  Configure market conditions on the left and click &quot;Run Simulation&quot; to see how
                  OMEGA&apos;s 4-layer pipeline would process a trading decision.
                </p>
              </div>
            )}

            {/* Loading State */}
            {loading && (
              <div className="bg-background-card border border-gray-700 rounded-lg p-16 shadow-card flex flex-col items-center justify-center text-center">
                <Loader2 className="w-12 h-12 text-blue-400 animate-spin mb-4" />
                <h3 className="text-lg font-semibold text-text-primary mb-2">Running 4-Layer Pipeline</h3>
                <div className="space-y-1.5 text-xs text-text-secondary">
                  <p>L1: PROVERBS safety check...</p>
                  <p>L2: Ensemble context (gutted)...</p>
                  <p>L3: WISDOM ML prediction...</p>
                  <p>L4: Prophet bot adaptation...</p>
                </div>
              </div>
            )}

            {/* Error State */}
            {error && !loading && (
              <div className="bg-background-card border border-red-500/30 rounded-lg p-8 shadow-card">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-6 h-6 text-red-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <h3 className="text-lg font-semibold text-red-400 mb-2">Simulation Failed</h3>
                    <p className="text-sm text-text-secondary mb-4">{error}</p>
                    <button
                      onClick={runSimulation}
                      className="px-4 py-2 text-sm bg-red-600/20 text-red-400 border border-red-500/30 rounded-lg hover:bg-red-600/30 transition-colors"
                    >
                      Retry
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Results */}
            {result && decision && !loading && (
              <div className="space-y-5">
                {/* Final Decision Header */}
                <div className="bg-background-card border border-gray-700 rounded-lg p-5 shadow-card">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold flex items-center gap-2">
                      <Zap className="w-5 h-5 text-yellow-400" />
                      Final Decision
                    </h2>
                    <div className="text-xs text-text-secondary flex items-center gap-1.5">
                      <Clock className="w-3 h-3" />
                      {new Date(result.timestamp).toLocaleString()}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {/* Decision */}
                    <div className="flex flex-col items-center p-4 bg-gray-800/50 rounded-lg border border-gray-700">
                      <span className="text-xs text-text-secondary mb-2">Decision for {decision.bot_name}</span>
                      <DecisionBadge decision={decision.final_decision} />
                    </div>

                    {/* Risk % */}
                    <div className="flex flex-col items-center p-4 bg-gray-800/50 rounded-lg border border-gray-700">
                      <span className="text-xs text-text-secondary mb-2">Risk Per Trade</span>
                      <span className={`text-3xl font-bold ${
                        decision.final_risk_pct <= 5 ? 'text-green-400' :
                        decision.final_risk_pct <= 10 ? 'text-yellow-400' :
                        'text-red-400'
                      }`}>
                        {decision.final_risk_pct.toFixed(1)}%
                      </span>
                    </div>

                    {/* Position Size Multiplier */}
                    <div className="flex flex-col items-center p-4 bg-gray-800/50 rounded-lg border border-gray-700">
                      <span className="text-xs text-text-secondary mb-2">Position Size Multiplier</span>
                      <span className={`text-3xl font-bold ${
                        decision.final_position_size_multiplier >= 0.8 ? 'text-green-400' :
                        decision.final_position_size_multiplier >= 0.5 ? 'text-yellow-400' :
                        'text-red-400'
                      }`}>
                        {decision.final_position_size_multiplier.toFixed(2)}x
                      </span>
                    </div>
                  </div>
                </div>

                {/* Layer-by-Layer Breakdown */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* L1: PROVERBS */}
                  <LayerResultCard
                    layerNumber={1}
                    name="PROVERBS Safety Gate"
                    icon={Shield}
                    borderColor={decision.proverbs_verdict.can_trade ? 'border-green-500/30' : 'border-red-500/30'}
                  >
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-secondary">Can Trade</span>
                        {decision.proverbs_verdict.can_trade ? (
                          <span className="flex items-center gap-1 text-xs text-green-400 font-medium">
                            <CheckCircle className="w-3.5 h-3.5" /> YES
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-xs text-red-400 font-medium">
                            <XCircle className="w-3.5 h-3.5" /> NO
                          </span>
                        )}
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-secondary">Reason</span>
                        <span className="text-xs text-text-primary text-right max-w-[60%] truncate" title={decision.proverbs_verdict.reason}>
                          {decision.proverbs_verdict.reason}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-secondary">Consecutive Losses</span>
                        <span className={`text-xs font-medium ${
                          decision.proverbs_verdict.consecutive_losses > 2 ? 'text-red-400' :
                          decision.proverbs_verdict.consecutive_losses > 0 ? 'text-yellow-400' :
                          'text-green-400'
                        }`}>
                          {decision.proverbs_verdict.consecutive_losses}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-secondary">Daily Loss</span>
                        <span className={`text-xs font-medium ${
                          decision.proverbs_verdict.daily_loss_pct > 5 ? 'text-red-400' :
                          decision.proverbs_verdict.daily_loss_pct > 0 ? 'text-yellow-400' :
                          'text-green-400'
                        }`}>
                          {decision.proverbs_verdict.daily_loss_pct.toFixed(1)}%
                        </span>
                      </div>
                      {decision.proverbs_verdict.is_killed && (
                        <div className="mt-1 p-2 bg-red-500/10 border border-red-500/20 rounded text-xs text-red-400">
                          Kill switch is activated in database
                        </div>
                      )}
                    </div>
                  </LayerResultCard>

                  {/* L2: Ensemble */}
                  <LayerResultCard
                    layerNumber={2}
                    name="Ensemble Context"
                    icon={Layers}
                    borderColor="border-gray-600"
                  >
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-secondary">Signal</span>
                        <span className="text-xs text-gray-400 font-medium">{decision.ensemble_context.signal}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-secondary">Confidence</span>
                        <span className="text-xs text-gray-400 font-medium">{decision.ensemble_context.confidence.toFixed(0)}%</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-secondary">Position Multiplier</span>
                        <span className="text-xs text-gray-400 font-medium">{decision.ensemble_context.position_size_multiplier.toFixed(2)}x</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-secondary">Regime</span>
                        <span className="text-xs text-gray-400 font-medium">{decision.ensemble_context.regime}</span>
                      </div>
                      <div className="mt-1 p-2 bg-gray-500/10 border border-gray-600 rounded text-xs text-gray-500 italic">
                        This layer is gutted — always returns NEUTRAL / 50%
                      </div>
                    </div>
                  </LayerResultCard>

                  {/* L3: WISDOM */}
                  <LayerResultCard
                    layerNumber={3}
                    name="WISDOM ML Decision"
                    icon={Brain}
                    borderColor="border-purple-500/30"
                  >
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-secondary">Advice</span>
                        <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                          decision.ml_decision.advice === 'TRADE_FULL'
                            ? 'bg-green-500/10 text-green-400'
                            : decision.ml_decision.advice === 'TRADE_REDUCED'
                            ? 'bg-yellow-500/10 text-yellow-400'
                            : 'bg-gray-500/10 text-gray-400'
                        }`}>
                          {decision.ml_decision.advice}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-secondary">Win Probability</span>
                        <span className={`text-xs font-bold ${
                          decision.ml_decision.win_probability >= 0.65 ? 'text-green-400' :
                          decision.ml_decision.win_probability >= 0.50 ? 'text-yellow-400' :
                          'text-red-400'
                        }`}>
                          {(decision.ml_decision.win_probability * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-secondary">Confidence</span>
                        <span className="text-xs text-text-primary font-medium">
                          {decision.ml_decision.confidence.toFixed(0)}%
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-secondary">Suggested Risk</span>
                        <span className="text-xs text-text-primary font-medium">
                          {decision.ml_decision.suggested_risk_pct.toFixed(1)}%
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-secondary">SD Multiplier</span>
                        <span className="text-xs text-text-primary font-medium">
                          {decision.ml_decision.suggested_sd_multiplier.toFixed(2)}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-secondary">Model Version</span>
                        <span className="text-xs text-text-primary font-mono">{decision.ml_decision.model_version}</span>
                      </div>
                      {decision.ml_decision.needs_retraining && (
                        <div className="mt-1 p-2 bg-yellow-500/10 border border-yellow-500/20 rounded text-xs text-yellow-400">
                          Model needs retraining
                        </div>
                      )}
                      {/* Top Factors */}
                      {decision.ml_decision.top_factors && decision.ml_decision.top_factors.length > 0 && (
                        <div className="mt-2 pt-2 border-t border-gray-700">
                          <span className="text-[10px] text-text-secondary font-medium uppercase tracking-wider">Top Factors</span>
                          <div className="mt-1.5 space-y-1">
                            {decision.ml_decision.top_factors.slice(0, 5).map(([factor, importance], i) => (
                              <div key={i} className="flex items-center gap-2">
                                <span className="text-[11px] text-text-secondary flex-1 truncate">{factor}</span>
                                <div className="w-16 bg-gray-700 rounded-full h-1">
                                  <div
                                    className="bg-purple-500 rounded-full h-1"
                                    style={{ width: `${Math.min(importance * 100, 100)}%` }}
                                  />
                                </div>
                                <span className="text-[10px] text-text-secondary w-8 text-right">
                                  {(importance * 100).toFixed(0)}%
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </LayerResultCard>

                  {/* L4: Prophet */}
                  <LayerResultCard
                    layerNumber={4}
                    name="Prophet Adaptation"
                    icon={Target}
                    borderColor="border-cyan-500/30"
                  >
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-secondary">Bot</span>
                        <span className="text-xs text-text-primary font-bold">{decision.prophet_adaptation.bot_name}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-secondary">Risk Adjustment</span>
                        <span className={`text-xs font-bold ${
                          decision.prophet_adaptation.risk_adjustment >= 1.0 ? 'text-green-400' :
                          decision.prophet_adaptation.risk_adjustment >= 0.7 ? 'text-yellow-400' :
                          'text-red-400'
                        }`}>
                          {decision.prophet_adaptation.risk_adjustment.toFixed(2)}x
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-secondary">Use GEX Walls</span>
                        <span className={`text-xs font-medium ${
                          decision.prophet_adaptation.use_gex_walls ? 'text-green-400' : 'text-gray-400'
                        }`}>
                          {decision.prophet_adaptation.use_gex_walls ? 'YES' : 'NO'}
                        </span>
                      </div>
                      {decision.prophet_adaptation.suggested_put_strike !== null && (
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-text-secondary">Put Strike</span>
                          <span className="text-xs text-red-400 font-mono">
                            ${decision.prophet_adaptation.suggested_put_strike?.toFixed(1)}
                          </span>
                        </div>
                      )}
                      {decision.prophet_adaptation.suggested_call_strike !== null && (
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-text-secondary">Call Strike</span>
                          <span className="text-xs text-green-400 font-mono">
                            ${decision.prophet_adaptation.suggested_call_strike?.toFixed(1)}
                          </span>
                        </div>
                      )}
                      {decision.prophet_adaptation.reasoning && (
                        <div className="mt-2 pt-2 border-t border-gray-700">
                          <span className="text-[10px] text-text-secondary font-medium uppercase tracking-wider">Reasoning</span>
                          <p className="text-xs text-text-secondary mt-1 leading-relaxed">
                            {decision.prophet_adaptation.reasoning}
                          </p>
                        </div>
                      )}
                    </div>
                  </LayerResultCard>
                </div>

                {/* Decision Path */}
                {decision.decision_path && decision.decision_path.length > 0 && (
                  <div className="bg-background-card border border-gray-700 rounded-lg p-5 shadow-card">
                    <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
                      <BarChart2 className="w-4 h-4 text-blue-400" />
                      Decision Path
                    </h3>
                    <ol className="space-y-1.5">
                      {decision.decision_path.map((step, i) => (
                        <li key={i} className="flex items-start gap-2.5 text-xs">
                          <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-500/20 text-blue-400 flex items-center justify-center text-[10px] font-bold mt-0.5">
                            {i + 1}
                          </span>
                          <span className="text-text-secondary leading-relaxed">{step}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}

                {/* Bottom Row: Capital Allocation + Correlation */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Capital Allocation */}
                  <div className="bg-background-card border border-gray-700 rounded-lg p-5 shadow-card">
                    <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
                      <BarChart2 className="w-4 h-4 text-purple-400" />
                      Capital Allocation
                    </h3>
                    {decision.capital_allocation && Object.keys(decision.capital_allocation).length > 0 ? (
                      <div className="space-y-2">
                        {Object.entries(decision.capital_allocation).map(([bot, pct]) => (
                          <div key={bot} className="flex items-center gap-2">
                            <span className="text-xs text-text-secondary w-28 truncate">{bot}</span>
                            <div className="flex-1 bg-gray-700 rounded-full h-2">
                              <div
                                className={`rounded-full h-2 transition-all ${
                                  bot === decision.bot_name ? 'bg-blue-500' : 'bg-gray-500'
                                }`}
                                style={{ width: `${Math.min((pct as number) * 100, 100)}%` }}
                              />
                            </div>
                            <span className="text-xs text-text-primary w-12 text-right font-medium">
                              {((pct as number) * 100).toFixed(0)}%
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-text-secondary italic">No allocation data</p>
                    )}
                    <div className="mt-3 pt-3 border-t border-gray-700 flex items-center justify-between">
                      <span className="text-xs text-text-secondary">Equity-Scaled Risk</span>
                      <span className="text-xs text-text-primary font-medium">
                        {decision.equity_scaled_risk?.toFixed(1) ?? 'N/A'}%
                      </span>
                    </div>
                  </div>

                  {/* Correlation Check */}
                  <div className="bg-background-card border border-gray-700 rounded-lg p-5 shadow-card">
                    <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
                      <Activity className="w-4 h-4 text-cyan-400" />
                      Correlation Check
                    </h3>
                    {decision.correlation_check && Object.keys(decision.correlation_check).length > 0 ? (
                      <div className="space-y-2">
                        {Object.entries(decision.correlation_check).map(([key, value]) => (
                          <div key={key} className="flex items-center justify-between">
                            <span className="text-xs text-text-secondary">{key.replace(/_/g, ' ')}</span>
                            <span className={`text-xs font-medium ${
                              typeof value === 'boolean'
                                ? value ? 'text-green-400' : 'text-red-400'
                                : typeof value === 'number'
                                ? (value as number) > 0.7 ? 'text-red-400' : 'text-green-400'
                                : 'text-text-primary'
                            }`}>
                              {typeof value === 'boolean'
                                ? value ? 'YES' : 'NO'
                                : typeof value === 'number'
                                ? (value as number).toFixed(3)
                                : String(value)
                              }
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-text-secondary italic">No correlation data</p>
                    )}
                    {decision.regime_transition && decision.regime_transition !== 'NO_CHANGE' && (
                      <div className="mt-3 pt-3 border-t border-gray-700">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-text-secondary">Regime Transition</span>
                          <span className="text-xs text-yellow-400 font-medium">
                            {decision.regime_transition.replace(/_/g, ' ')}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Simulation Input Summary (collapsed) */}
                <details className="bg-background-card border border-gray-700 rounded-lg shadow-card">
                  <summary className="px-5 py-3 cursor-pointer text-sm text-text-secondary hover:text-text-primary transition-colors flex items-center gap-2">
                    <ChevronDown className="w-4 h-4" />
                    Simulation Input Summary
                  </summary>
                  <div className="px-5 pb-4 grid grid-cols-2 md:grid-cols-4 gap-3">
                    {result.input?.market_conditions && Object.entries(result.input.market_conditions).map(([key, val]) => (
                      <div key={key} className="text-xs">
                        <span className="text-text-secondary">{key.replace(/_/g, ' ')}: </span>
                        <span className="text-text-primary font-medium">
                          {typeof val === 'number' ? val.toFixed(2) : String(val)}
                        </span>
                      </div>
                    ))}
                  </div>
                </details>
              </div>
            )}
          </div>
        </div>
        </div>
      </main>
    </div>
  )
}
