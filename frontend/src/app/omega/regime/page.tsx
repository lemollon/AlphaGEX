'use client'

import React from 'react'
import {
  Activity, BarChart2, TrendingUp, TrendingDown, Minus,
  Clock, RefreshCw, AlertTriangle, CheckCircle, Info,
  Zap, Shield, Target, ArrowRight, ChevronLeft,
  Gauge, Flame, Snowflake, ThermometerSun, AlertOctagon,
  Calendar, BookOpen, ArrowUpDown
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import {
  useOmegaRegime,
  useOmegaRetrainStatus,
} from '@/lib/hooks/useMarketData'

// ==================== HELPERS ====================

const GEX_REGIME_COLORS: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  POSITIVE: { bg: 'bg-green-500/10', text: 'text-green-400', border: 'border-green-500/30', dot: 'bg-green-400' },
  NEGATIVE: { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/30', dot: 'bg-red-400' },
  NEUTRAL: { bg: 'bg-gray-500/10', text: 'text-gray-400', border: 'border-gray-500/30', dot: 'bg-gray-500' },
  UNKNOWN: { bg: 'bg-gray-500/10', text: 'text-gray-500', border: 'border-gray-600', dot: 'bg-gray-600' },
}

const VIX_REGIME_COLORS: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  LOW: { bg: 'bg-green-500/10', text: 'text-green-400', border: 'border-green-500/30', dot: 'bg-green-400' },
  NORMAL: { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/30', dot: 'bg-blue-400' },
  ELEVATED: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30', dot: 'bg-yellow-400' },
  HIGH: { bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/30', dot: 'bg-orange-400' },
  EXTREME: { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/30', dot: 'bg-red-400' },
  UNKNOWN: { bg: 'bg-gray-500/10', text: 'text-gray-500', border: 'border-gray-600', dot: 'bg-gray-600' },
}

const IMPACT_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  HIGH: { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/30' },
  MEDIUM: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30' },
  LOW: { bg: 'bg-green-500/10', text: 'text-green-400', border: 'border-green-500/30' },
}

const TREND_ICONS: Record<string, React.ReactNode> = {
  BULLISH: <TrendingUp className="w-5 h-5 text-green-400" />,
  BEARISH: <TrendingDown className="w-5 h-5 text-red-400" />,
  RANGING: <Minus className="w-5 h-5 text-yellow-400" />,
  UNKNOWN: <Minus className="w-5 h-5 text-gray-500" />,
}

const TREND_COLORS: Record<string, string> = {
  BULLISH: 'text-green-400',
  BEARISH: 'text-red-400',
  RANGING: 'text-yellow-400',
  UNKNOWN: 'text-gray-500',
}

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
      timeZone: 'America/Chicago',
    })
  } catch {
    return ts || '--'
  }
}

function formatTransitionType(type: string): string {
  return type
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

// ==================== CURRENT REGIME CARD ====================

function CurrentRegimeCard({ regimeData }: { regimeData: any }) {
  const currentRegimes = regimeData?.current_regimes || {}
  const gexRegime = currentRegimes.gex_regime || 'UNKNOWN'
  const vixRegime = currentRegimes.vix_regime || 'UNKNOWN'
  const trend = currentRegimes.trend || 'UNKNOWN'

  const observationCount = regimeData?.observation_count || {}

  const gexStyle = GEX_REGIME_COLORS[gexRegime] || GEX_REGIME_COLORS.UNKNOWN
  const vixStyle = VIX_REGIME_COLORS[vixRegime] || VIX_REGIME_COLORS.UNKNOWN

  return (
    <div className="bg-background-card border border-gray-700 rounded-lg p-6 shadow-card">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold text-text-primary flex items-center gap-2">
          <Gauge className="w-5 h-5 text-blue-400" />
          Current Market Regime
        </h2>
        <div className="text-xs text-text-secondary">
          {regimeData?.timestamp ? formatTimestamp(regimeData.timestamp) : '--'}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* GEX Regime */}
        <div className={`rounded-lg border ${gexStyle.border} ${gexStyle.bg} p-5`}>
          <div className="flex items-center gap-2 mb-3">
            <Activity className={`w-4 h-4 ${gexStyle.text}`} />
            <span className="text-sm text-text-secondary font-medium">GEX Regime</span>
          </div>
          <div className="flex items-center gap-3">
            <span className={`w-3 h-3 rounded-full ${gexStyle.dot} animate-pulse`} />
            <span className={`text-3xl font-bold ${gexStyle.text}`}>{gexRegime}</span>
          </div>
          <p className="mt-3 text-xs text-text-secondary">
            {gexRegime === 'POSITIVE'
              ? 'Mean reversion expected. Dealers hedge against moves. Favors Iron Condors.'
              : gexRegime === 'NEGATIVE'
              ? 'Momentum expected. Dealers amplify moves. Favors Directional.'
              : gexRegime === 'NEUTRAL'
              ? 'No strong dealer bias. Mixed signals.'
              : 'Awaiting regime data from observations.'}
          </p>
          <div className="mt-3 flex items-center gap-1.5 text-xs text-text-secondary">
            <BarChart2 className="w-3 h-3" />
            <span>{observationCount.gex || 0} observations</span>
          </div>
        </div>

        {/* VIX Regime */}
        <div className={`rounded-lg border ${vixStyle.border} ${vixStyle.bg} p-5`}>
          <div className="flex items-center gap-2 mb-3">
            <Flame className={`w-4 h-4 ${vixStyle.text}`} />
            <span className="text-sm text-text-secondary font-medium">VIX Regime</span>
          </div>
          <div className="flex items-center gap-3">
            <span className={`w-3 h-3 rounded-full ${vixStyle.dot} animate-pulse`} />
            <span className={`text-3xl font-bold ${vixStyle.text}`}>{vixRegime}</span>
          </div>
          <p className="mt-3 text-xs text-text-secondary">
            {vixRegime === 'LOW'
              ? 'VIX < 15. Thin premiums, favor directional plays.'
              : vixRegime === 'NORMAL'
              ? 'VIX 15-22. Ideal for Iron Condors, balanced premiums.'
              : vixRegime === 'ELEVATED'
              ? 'VIX 22-28. Widen IC strikes, cautious sizing.'
              : vixRegime === 'HIGH'
              ? 'VIX 28-35. Reduce position size 50%. Elevated risk.'
              : vixRegime === 'EXTREME'
              ? 'VIX > 35. Skip ICs entirely. Small directional only.'
              : 'Awaiting VIX data from observations.'}
          </p>
          <div className="mt-3 flex items-center gap-1.5 text-xs text-text-secondary">
            <BarChart2 className="w-3 h-3" />
            <span>{observationCount.vix || 0} observations</span>
          </div>
        </div>

        {/* Trend */}
        <div className="rounded-lg border border-gray-700 bg-gray-800/30 p-5">
          <div className="flex items-center gap-2 mb-3">
            <ArrowUpDown className="w-4 h-4 text-purple-400" />
            <span className="text-sm text-text-secondary font-medium">Market Trend</span>
          </div>
          <div className="flex items-center gap-3">
            {TREND_ICONS[trend] || TREND_ICONS.UNKNOWN}
            <span className={`text-3xl font-bold ${TREND_COLORS[trend] || TREND_COLORS.UNKNOWN}`}>
              {trend}
            </span>
          </div>
          <p className="mt-3 text-xs text-text-secondary">
            {trend === 'BULLISH'
              ? 'Upward price movement detected. Favor call-side exposure.'
              : trend === 'BEARISH'
              ? 'Downward price movement detected. Favor put-side exposure.'
              : trend === 'RANGING'
              ? 'Sideways price action. Range-bound strategies preferred.'
              : 'Awaiting trend data from observations.'}
          </p>
          <div className="mt-3 flex items-center gap-1.5 text-xs text-text-secondary">
            <BarChart2 className="w-3 h-3" />
            <span>{observationCount.trend || 0} observations</span>
          </div>
        </div>
      </div>
    </div>
  )
}

// ==================== REGIME TRANSITION HISTORY ====================

function TransitionHistory({ regimeData }: { regimeData: any }) {
  // Transitions come from either the top-level recent_transitions or nested inside current_regimes
  const topLevelTransitions = regimeData?.recent_transitions || []
  const nestedTransitions = regimeData?.current_regimes?.recent_transitions || []
  const allTransitions = topLevelTransitions.length > 0 ? topLevelTransitions : nestedTransitions

  return (
    <div className="bg-background-card border border-gray-700 rounded-lg p-6 shadow-card">
      <h2 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
        <Clock className="w-5 h-5 text-yellow-400" />
        Regime Transition History
      </h2>

      {allTransitions.length === 0 ? (
        <div className="text-center py-10">
          <CheckCircle className="w-8 h-8 text-green-400/50 mx-auto mb-3" />
          <p className="text-sm text-text-secondary">No regime transitions detected yet</p>
          <p className="text-xs text-text-secondary/70 mt-1">
            Transitions appear when OMEGA detects a confirmed shift in GEX or VIX regime
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {[...allTransitions].reverse().map((entry: any, entryIdx: number) => {
            const transitions = entry.transitions || [entry]
            const timestamp = entry.timestamp

            return transitions.map((t: any, tIdx: number) => {
              const impact = t.impact || 'LOW'
              const impactStyle = IMPACT_COLORS[impact] || IMPACT_COLORS.LOW

              return (
                <div
                  key={`${entryIdx}-${tIdx}`}
                  className={`border ${impactStyle.border} ${impactStyle.bg} rounded-lg p-4`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${impactStyle.text} ${impactStyle.bg} border ${impactStyle.border}`}>
                        {impact} IMPACT
                      </span>
                      <span className="text-sm font-medium text-text-primary">
                        {formatTransitionType(t.type || 'Unknown Transition')}
                      </span>
                    </div>
                    <span className="text-xs text-text-secondary">
                      {timestamp ? formatTimestamp(timestamp) : '--'}
                    </span>
                  </div>

                  <div className="flex items-center gap-3 mb-2">
                    <span className="text-sm text-text-secondary">
                      {t.from || '?'}
                    </span>
                    <ArrowRight className="w-4 h-4 text-text-secondary/50" />
                    <span className="text-sm font-medium text-text-primary">
                      {t.to || '?'}
                    </span>
                  </div>

                  {t.recommendation && (
                    <div className="flex items-start gap-2 mt-2 pt-2 border-t border-gray-700/50">
                      <Info className="w-3.5 h-3.5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <p className="text-xs text-blue-300/80">{t.recommendation}</p>
                    </div>
                  )}

                  {entry.current_state && (
                    <div className="flex gap-3 mt-2 text-xs text-text-secondary/70">
                      {entry.current_state.gex_regime && (
                        <span>GEX: {entry.current_state.gex_regime}</span>
                      )}
                      {entry.current_state.vix_regime && (
                        <span>VIX Regime: {entry.current_state.vix_regime}</span>
                      )}
                      {entry.current_state.vix && (
                        <span>VIX: {Number(entry.current_state.vix).toFixed(2)}</span>
                      )}
                    </div>
                  )}
                </div>
              )
            })
          })}
        </div>
      )}
    </div>
  )
}

// ==================== VIX REGIME THRESHOLDS ====================

function VixThresholdsCard() {
  const thresholds = [
    {
      regime: 'LOW',
      range: 'VIX < 15',
      color: VIX_REGIME_COLORS.LOW,
      icon: Snowflake,
      action: 'Thin premiums, favor directional plays',
      detail: 'IC premiums too thin to be worthwhile. Focus on debit spreads and directional entries.',
      sizing: '100% size',
    },
    {
      regime: 'NORMAL',
      range: 'VIX 15 - 22',
      color: VIX_REGIME_COLORS.NORMAL,
      icon: CheckCircle,
      action: 'Ideal for Iron Condors',
      detail: 'Best balance of premium vs risk. Standard strike width, full sizing.',
      sizing: '100% size',
    },
    {
      regime: 'ELEVATED',
      range: 'VIX 22 - 28',
      color: VIX_REGIME_COLORS.ELEVATED,
      icon: AlertTriangle,
      action: 'Widen IC strikes',
      detail: 'Increase strike width by 20-30%. Premium is rich but tails are fatter.',
      sizing: '75% size',
    },
    {
      regime: 'HIGH',
      range: 'VIX 28 - 35',
      color: VIX_REGIME_COLORS.HIGH,
      icon: Flame,
      action: 'Reduce position size 50%',
      detail: 'High risk environment. Only take highest-conviction setups with wider wings.',
      sizing: '50% size',
    },
    {
      regime: 'EXTREME',
      range: 'VIX > 35',
      color: VIX_REGIME_COLORS.EXTREME,
      icon: AlertOctagon,
      action: 'Skip ICs, small directional only',
      detail: 'Market in crisis mode. Iron Condors are dangerous. Only small directional bets.',
      sizing: '25% size max',
    },
  ]

  return (
    <div className="bg-background-card border border-gray-700 rounded-lg p-6 shadow-card">
      <h2 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
        <ThermometerSun className="w-5 h-5 text-orange-400" />
        VIX Regime Thresholds
      </h2>

      <div className="space-y-2">
        {thresholds.map(({ regime, range, color, icon: Icon, action, detail, sizing }) => (
          <div
            key={regime}
            className={`border ${color.border} ${color.bg} rounded-lg p-4 flex items-start gap-4`}
          >
            <div className="flex-shrink-0 mt-0.5">
              <Icon className={`w-5 h-5 ${color.text}`} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 mb-1">
                <span className={`text-sm font-bold ${color.text}`}>{regime}</span>
                <span className="text-xs text-text-secondary font-mono">{range}</span>
                <span className={`ml-auto text-xs px-2 py-0.5 rounded ${color.bg} ${color.text} border ${color.border}`}>
                  {sizing}
                </span>
              </div>
              <p className="text-sm text-text-primary">{action}</p>
              <p className="text-xs text-text-secondary mt-1">{detail}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ==================== TRAINING SCHEDULE ====================

function TrainingSchedulePanel({ retrainData }: { retrainData: any }) {
  const trainingSchedule = retrainData?.training_schedule || []
  const autoRetrain = retrainData?.auto_retrain || {}
  const config = retrainData?.config || {}
  const evaluation = autoRetrain.evaluation || {}

  const sundayModels = trainingSchedule.filter((s: any) => s.day === 'Sunday')
  const dailyModels = trainingSchedule.filter((s: any) => s.day === 'Daily')

  return (
    <div className="bg-background-card border border-gray-700 rounded-lg p-6 shadow-card">
      <h2 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
        <Calendar className="w-5 h-5 text-green-400" />
        Training Schedule
      </h2>

      {/* Sunday Schedule */}
      <div className="mb-5">
        <h3 className="text-sm font-medium text-text-secondary mb-3 flex items-center gap-2">
          <RefreshCw className="w-4 h-4 text-blue-400" />
          Sunday Retraining Cascade (Central Time)
        </h3>
        <div className="relative">
          {/* Timeline bar */}
          <div className="absolute left-[18px] top-3 bottom-3 w-0.5 bg-gray-700" />

          <div className="space-y-3">
            {sundayModels.map((item: any, i: number) => (
              <div key={i} className="flex items-center gap-4 relative">
                <div className="w-9 h-9 rounded-full bg-blue-500/10 border border-blue-500/30 flex items-center justify-center flex-shrink-0 z-10">
                  <span className="text-xs font-bold text-blue-400">{i + 1}</span>
                </div>
                <div className="flex-1 bg-gray-800/40 border border-gray-700/50 rounded-lg p-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-sm font-medium text-text-primary">{item.model}</span>
                      <span className="ml-2 text-xs text-text-secondary font-mono">({item.type})</span>
                    </div>
                    <span className="text-sm font-mono text-blue-400">{item.time_ct}</span>
                  </div>
                  <p className="text-xs text-text-secondary mt-1">{item.file}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Daily Schedule */}
      {dailyModels.length > 0 && (
        <div className="mb-5">
          <h3 className="text-sm font-medium text-text-secondary mb-3 flex items-center gap-2">
            <Clock className="w-4 h-4 text-yellow-400" />
            Daily Tasks
          </h3>
          <div className="space-y-2">
            {dailyModels.map((item: any, i: number) => (
              <div key={i} className="flex items-center gap-3 bg-gray-800/40 border border-gray-700/50 rounded-lg p-3">
                <div className="w-7 h-7 rounded-full bg-yellow-500/10 border border-yellow-500/30 flex items-center justify-center flex-shrink-0">
                  <Clock className="w-3.5 h-3.5 text-yellow-400" />
                </div>
                <div className="flex-1">
                  <span className="text-sm font-medium text-text-primary">{item.model}</span>
                  <span className="ml-2 text-xs text-text-secondary font-mono">({item.type})</span>
                </div>
                <span className="text-sm font-mono text-yellow-400">{item.time_ct} CT</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Auto-Retrain Config */}
      <div className="border-t border-gray-700 pt-4">
        <h3 className="text-sm font-medium text-text-secondary mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4 text-purple-400" />
          Auto-Retrain Configuration
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-gray-800/40 border border-gray-700/50 rounded-lg p-3">
            <div className="text-xs text-text-secondary mb-1">Win Rate Degradation Threshold</div>
            <div className="text-sm font-mono text-text-primary">
              {config.win_rate_degradation_threshold
                ? `${(config.win_rate_degradation_threshold * 100).toFixed(0)}%`
                : '--'}
            </div>
          </div>
          <div className="bg-gray-800/40 border border-gray-700/50 rounded-lg p-3">
            <div className="text-xs text-text-secondary mb-1">Max Model Age</div>
            <div className="text-sm font-mono text-text-primary">
              {config.max_model_age_days ? `${config.max_model_age_days} days` : '--'}
            </div>
          </div>
          <div className="bg-gray-800/40 border border-gray-700/50 rounded-lg p-3">
            <div className="text-xs text-text-secondary mb-1">Min Trades for Evaluation</div>
            <div className="text-sm font-mono text-text-primary">
              {config.min_trades_for_evaluation ?? '--'}
            </div>
          </div>
          <div className="bg-gray-800/40 border border-gray-700/50 rounded-lg p-3">
            <div className="text-xs text-text-secondary mb-1">Consecutive Loss Trigger</div>
            <div className="text-sm font-mono text-text-primary">
              {config.consecutive_loss_trigger ?? '--'}
            </div>
          </div>
        </div>

        {/* Current Tracking Stats */}
        <div className="mt-3 grid grid-cols-3 gap-3">
          <div className="bg-gray-800/40 border border-gray-700/50 rounded-lg p-3 text-center">
            <div className="text-xs text-text-secondary mb-1">Predictions Tracked</div>
            <div className="text-lg font-bold text-text-primary">{autoRetrain.predictions_tracked ?? 0}</div>
          </div>
          <div className="bg-gray-800/40 border border-gray-700/50 rounded-lg p-3 text-center">
            <div className="text-xs text-text-secondary mb-1">Outcomes Tracked</div>
            <div className="text-lg font-bold text-text-primary">{autoRetrain.outcomes_tracked ?? 0}</div>
          </div>
          <div className="bg-gray-800/40 border border-gray-700/50 rounded-lg p-3 text-center">
            <div className="text-xs text-text-secondary mb-1">Last Retrain</div>
            <div className="text-sm font-medium text-text-primary">
              {autoRetrain.last_retrain_date
                ? formatTimestamp(autoRetrain.last_retrain_date)
                : 'Never'}
            </div>
          </div>
        </div>

        {/* Retrain Evaluation */}
        {evaluation && evaluation.retrain_needed !== undefined && (
          <div className={`mt-3 p-3 rounded-lg border ${
            evaluation.retrain_needed
              ? 'bg-yellow-500/10 border-yellow-500/30'
              : 'bg-green-500/10 border-green-500/30'
          }`}>
            <div className="flex items-center gap-2">
              {evaluation.retrain_needed ? (
                <AlertTriangle className="w-4 h-4 text-yellow-400" />
              ) : (
                <CheckCircle className="w-4 h-4 text-green-400" />
              )}
              <span className={`text-sm font-medium ${
                evaluation.retrain_needed ? 'text-yellow-400' : 'text-green-400'
              }`}>
                {evaluation.retrain_needed ? 'Retrain Recommended' : 'Models Current'}
              </span>
            </div>
            {evaluation.reason && (
              <p className="text-xs text-text-secondary mt-1 ml-6">{evaluation.reason}</p>
            )}
            {evaluation.metrics && (
              <div className="flex gap-4 mt-2 ml-6 text-xs text-text-secondary">
                {evaluation.metrics.actual_win_rate !== undefined && (
                  <span>Actual WR: {(evaluation.metrics.actual_win_rate * 100).toFixed(1)}%</span>
                )}
                {evaluation.metrics.predicted_win_rate !== undefined && (
                  <span>Predicted WR: {(evaluation.metrics.predicted_win_rate * 100).toFixed(1)}%</span>
                )}
                {evaluation.metrics.sample_size !== undefined && (
                  <span>Sample: {evaluation.metrics.sample_size}</span>
                )}
                {evaluation.metrics.status && (
                  <span>{evaluation.metrics.status.replace(/_/g, ' ')}</span>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ==================== REGIME IMPACT ON STRATEGIES ====================

function RegimeImpactCard() {
  const scenarios = [
    {
      gex: 'POSITIVE',
      vix: 'LOW',
      gexColor: GEX_REGIME_COLORS.POSITIVE,
      vixColor: VIX_REGIME_COLORS.LOW,
      label: 'Iron Condor Sweet Spot',
      labelColor: 'text-green-400',
      borderColor: 'border-green-500/30',
      bgColor: 'bg-green-500/5',
      icon: Target,
      description: 'Positive gamma acts as a mean-reversion force while low VIX keeps expected moves tight. Premium is thin but highly likely to expire worthless.',
      strategy: 'Standard Iron Condors with tight wings. Full position sizing.',
      bots: 'FORTRESS, ANCHOR favored',
    },
    {
      gex: 'POSITIVE',
      vix: 'NORMAL',
      gexColor: GEX_REGIME_COLORS.POSITIVE,
      vixColor: VIX_REGIME_COLORS.NORMAL,
      label: 'Optimal Trading Conditions',
      labelColor: 'text-blue-400',
      borderColor: 'border-blue-500/30',
      bgColor: 'bg-blue-500/5',
      icon: CheckCircle,
      description: 'Best of both worlds. Mean reversion with adequate premium. This is where Iron Condors have the highest expected value.',
      strategy: 'Full IC program. Can increase contract count. Tight strikes.',
      bots: 'All IC bots: FORTRESS, ANCHOR, LAZARUS',
    },
    {
      gex: 'NEGATIVE',
      vix: 'LOW',
      gexColor: GEX_REGIME_COLORS.NEGATIVE,
      vixColor: VIX_REGIME_COLORS.LOW,
      label: 'Deceptive Calm',
      labelColor: 'text-yellow-400',
      borderColor: 'border-yellow-500/30',
      bgColor: 'bg-yellow-500/5',
      icon: AlertTriangle,
      description: 'Low VIX masks the risk from negative gamma. Dealers will amplify any move. Breakouts are more likely than vol implies.',
      strategy: 'Directional plays preferred. Avoid tight ICs. Watch for breakouts.',
      bots: 'SOLOMON, CORNERSTONE favored',
    },
    {
      gex: 'NEGATIVE',
      vix: 'HIGH',
      gexColor: GEX_REGIME_COLORS.NEGATIVE,
      vixColor: VIX_REGIME_COLORS.HIGH,
      label: 'Directional Only',
      labelColor: 'text-orange-400',
      borderColor: 'border-orange-500/30',
      bgColor: 'bg-orange-500/5',
      icon: Flame,
      description: 'Highest risk environment. Negative gamma + high VIX = explosive moves. ICs will get run over. Only small, defined-risk directional bets.',
      strategy: 'Small directional debit spreads only. 50% position size max.',
      bots: 'SOLOMON only, reduced size',
    },
    {
      gex: 'NEGATIVE',
      vix: 'EXTREME',
      gexColor: GEX_REGIME_COLORS.NEGATIVE,
      vixColor: VIX_REGIME_COLORS.EXTREME,
      label: 'Crisis Mode',
      labelColor: 'text-red-400',
      borderColor: 'border-red-500/30',
      bgColor: 'bg-red-500/5',
      icon: AlertOctagon,
      description: 'Market in freefall or extreme fear. Any premium sold will get blown out. Protect capital.',
      strategy: 'Minimal activity. Cash is a position. 25% max sizing if any.',
      bots: 'All bots should reduce or halt',
    },
    {
      gex: 'TRANSITION',
      vix: 'ANY',
      gexColor: { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/30', dot: 'bg-purple-400' },
      vixColor: { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/30', dot: 'bg-purple-400' },
      label: 'Transition Period',
      labelColor: 'text-purple-400',
      borderColor: 'border-purple-500/30',
      bgColor: 'bg-purple-500/5',
      icon: ArrowUpDown,
      description: 'Regime is actively shifting. Historical transitions are the highest-risk moments. The new regime is not yet confirmed.',
      strategy: 'Reduce position size by 50%. Wait for confirmation before committing.',
      bots: 'All bots reduce via OMEGA sizing adjustment',
    },
  ]

  return (
    <div className="bg-background-card border border-gray-700 rounded-lg p-6 shadow-card">
      <h2 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
        <BookOpen className="w-5 h-5 text-cyan-400" />
        Regime Impact on Strategies
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {scenarios.map(({ gex, vix, gexColor, vixColor, label, labelColor, borderColor, bgColor, icon: Icon, description, strategy, bots }) => (
          <div key={`${gex}-${vix}`} className={`border ${borderColor} ${bgColor} rounded-lg p-4`}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Icon className={`w-5 h-5 ${labelColor}`} />
                <span className={`text-sm font-bold ${labelColor}`}>{label}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-xs px-2 py-0.5 rounded ${gexColor.bg} ${gexColor.text} border ${gexColor.border}`}>
                  {gex}
                </span>
                <span className="text-xs text-text-secondary">+</span>
                <span className={`text-xs px-2 py-0.5 rounded ${vixColor.bg} ${vixColor.text} border ${vixColor.border}`}>
                  {vix}
                </span>
              </div>
            </div>

            <p className="text-xs text-text-secondary mb-3">{description}</p>

            <div className="space-y-2">
              <div className="flex items-start gap-2">
                <Shield className="w-3.5 h-3.5 text-blue-400 mt-0.5 flex-shrink-0" />
                <p className="text-xs text-text-primary">{strategy}</p>
              </div>
              <div className="flex items-start gap-2">
                <Target className="w-3.5 h-3.5 text-purple-400 mt-0.5 flex-shrink-0" />
                <p className="text-xs text-text-secondary">{bots}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ==================== MAIN PAGE ====================

export default function RegimeMonitorPage() {
  const { data: regimeData, error: regimeError, isLoading: regimeLoading } = useOmegaRegime()
  const { data: retrainData, error: retrainError, isLoading: retrainLoading } = useOmegaRetrainStatus()

  const isLoading = regimeLoading || retrainLoading
  const hasError = regimeError || retrainError

  return (
    <div className="min-h-screen bg-background-deep text-text-primary">
      <Navigation />
      <div className="flex-1 p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <a
                href="/omega"
                className="text-text-secondary hover:text-blue-400 transition-colors"
              >
                <ChevronLeft className="w-5 h-5" />
              </a>
              <TrendingUp className="w-7 h-7 text-blue-400" />
              <h1 className="text-2xl font-bold">Regime Monitor</h1>
            </div>
            <p className="text-sm text-text-secondary ml-9">
              Market regime tracking, transition detection, and strategy impact analysis
            </p>
          </div>
          <div className="text-right">
            <div className="text-xs text-text-secondary">
              {regimeData?.timestamp ? formatTimestamp(regimeData.timestamp) : '--'}
            </div>
            <div className="text-xs text-text-secondary/70 mt-0.5">
              Auto-refresh: 30s
            </div>
          </div>
        </div>

        {/* Loading State */}
        {isLoading && !regimeData && !retrainData && (
          <div className="text-center py-20">
            <RefreshCw className="w-8 h-8 text-blue-400 mx-auto mb-3 animate-spin" />
            <p className="text-sm text-text-secondary">Loading regime data...</p>
          </div>
        )}

        {/* Error State */}
        {hasError && !regimeData && !retrainData && (
          <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg mb-6">
            <div className="flex items-center gap-2 text-red-400 text-sm font-medium">
              <AlertTriangle className="w-4 h-4" />
              Failed to load regime data
            </div>
            <p className="text-xs text-red-300/70 mt-1">
              {regimeError?.message || retrainError?.message || 'OMEGA Orchestrator may not be available.'}
            </p>
          </div>
        )}

        {/* Content */}
        {(!isLoading || regimeData || retrainData) && !hasError && (
          <div className="space-y-6">
            {/* Section 1: Current Regime */}
            <CurrentRegimeCard regimeData={regimeData} />

            {/* Section 2 & 3: Transition History + VIX Thresholds side by side */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <TransitionHistory regimeData={regimeData} />
              <VixThresholdsCard />
            </div>

            {/* Section 4: Training Schedule */}
            <TrainingSchedulePanel retrainData={retrainData} />

            {/* Section 5: Regime Impact on Strategies */}
            <RegimeImpactCard />
          </div>
        )}
      </div>
    </div>
  )
}
