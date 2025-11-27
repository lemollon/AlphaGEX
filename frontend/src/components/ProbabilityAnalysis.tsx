'use client'

import React from 'react'
import { Target, TrendingUp, Zap, DollarSign, Percent, BarChart3, AlertCircle, Calculator, Shield, Clock, History, Activity } from 'lucide-react'

interface TradeSetup {
  setup_type: string
  mm_state: string
  strike_distance_pct: number
  win_rate: number
  avg_win: number
  avg_loss: number
  expected_value: number
  sample_size: number
  confidence_score: number
  // NEW: Entry/Exit prices
  entry_price_low: number
  entry_price_high: number
  profit_target: number
  stop_loss: number
  optimal_hold_days: number
}

interface StrikeProbability {
  strike: number
  distance_pct: number
  estimated_delta: number
  win_rate: number
  expected_return: number
  expected_value: number
}

interface WallProbabilities {
  call_wall: {
    price: number
    prob_1d: number
    prob_3d: number
    prob_5d: number
  } | null
  put_wall: {
    price: number
    prob_1d: number
    prob_3d: number
    prob_5d: number
  } | null
}

interface RegimeEdge {
  current_win_rate: number
  baseline_win_rate: number
  edge_percentage: number
  regime_stats: Record<string, any>
}

// NEW: Position Sizing
interface PositionSizing {
  kelly_pct: number
  conservative_pct: number
  aggressive_pct: number
  recommended_contracts: number
  max_contracts: number
  account_risk_pct: number
}

// NEW: Risk Analysis
interface RiskAnalysis {
  total_cost: number
  best_case_profit: number
  worst_case_loss: number
  expected_value_dollars: number
  roi_percent: number
  max_account_risk_pct: number
}

// NEW: Holding Period
interface HoldingPeriod {
  day_1_win_rate: number
  day_2_win_rate: number
  day_3_win_rate: number
  day_4_win_rate: number
  day_5_win_rate: number
  optimal_day: number
}

// NEW: Historical Setup
interface HistoricalSetup {
  date: string
  outcome: string
  pnl_dollars: number
  pnl_percent: number
  hold_days: number
}

// NEW: Regime Stability
interface RegimeStability {
  current_state: string
  stay_probability: number
  shift_probabilities: Record<string, number>
  alert_threshold: number
  recommendation: string
}

interface ProbabilityData {
  best_setup: TradeSetup | null
  strike_probabilities: StrikeProbability[]
  wall_probabilities: WallProbabilities
  regime_edge: RegimeEdge
  // NEW fields
  position_sizing: PositionSizing | null
  risk_analysis: RiskAnalysis | null
  holding_period: HoldingPeriod | null
  historical_setups: HistoricalSetup[]
  regime_stability: RegimeStability | null
  spot_price: number
  option_price: number
  account_size: number
}

interface ProbabilityAnalysisProps {
  data: ProbabilityData
  symbol: string
  spotPrice: number
}

export const BestSetupCard: React.FC<{ setup: TradeSetup; symbol: string }> = ({ setup, symbol }) => {
  const winRatePercent = (setup.win_rate * 100).toFixed(1)
  const avgWinPercent = (setup.avg_win * 100).toFixed(1)
  const avgLossPercent = (setup.avg_loss * 100).toFixed(1)
  const expectedValueDollars = (setup.expected_value * 100).toFixed(0) // Assuming $100/contract basis

  return (
    <div className="card border-2 border-success bg-success/5">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h2 className="text-2xl font-bold text-text-primary mb-1 flex items-center gap-2">
            <Target className="w-7 h-7 text-success" />
            🎯 BEST TRADE SETUP NOW
          </h2>
          <p className="text-text-secondary text-sm">Highest probability opportunity based on current market conditions</p>
        </div>
        <div className="px-4 py-2 rounded-lg bg-success/20">
          <p className="text-xs text-success font-semibold uppercase">
            {setup.mm_state} State
          </p>
        </div>
      </div>

      <div className="space-y-4">
        {/* Setup Type */}
        <div className="p-4 bg-background-card rounded-lg border-l-4 border-success">
          <h3 className="text-lg font-bold text-text-primary mb-1">{setup.setup_type}</h3>
          <p className="text-sm text-text-secondary">Based on {setup.sample_size} historical similar setups • Hold for {setup.optimal_hold_days} days</p>
        </div>

        {/* NEW: Entry/Exit Prices */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 bg-primary/10 border-2 border-primary rounded-lg">
            <p className="text-xs text-text-muted uppercase mb-1">Entry Price (Low)</p>
            <p className="text-2xl font-bold text-primary">${setup.entry_price_low.toFixed(2)}</p>
            <p className="text-xs text-text-secondary mt-1">Conservative entry</p>
          </div>
          <div className="p-4 bg-primary/10 border-2 border-primary rounded-lg">
            <p className="text-xs text-text-muted uppercase mb-1">Entry Price (High)</p>
            <p className="text-2xl font-bold text-primary">${setup.entry_price_high.toFixed(2)}</p>
            <p className="text-xs text-text-secondary mt-1">Max entry</p>
          </div>
          <div className="p-4 bg-success/10 border-2 border-success rounded-lg">
            <p className="text-xs text-text-muted uppercase mb-1">Profit Target</p>
            <p className="text-2xl font-bold text-success">${setup.profit_target.toFixed(2)}</p>
            <p className="text-xs text-text-secondary mt-1">Take profit</p>
          </div>
          <div className="p-4 bg-danger/10 border-2 border-danger rounded-lg">
            <p className="text-xs text-text-muted uppercase mb-1">Stop Loss</p>
            <p className="text-2xl font-bold text-danger">${setup.stop_loss.toFixed(2)}</p>
            <p className="text-xs text-text-secondary mt-1">Exit if hit</p>
          </div>
        </div>

        {/* Key Metrics Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 bg-background-hover rounded-lg">
            <p className="text-xs text-text-muted uppercase mb-1">Win Probability</p>
            <p className="text-3xl font-bold text-success">{winRatePercent}%</p>
            <p className="text-xs text-text-secondary mt-1">Historical win rate</p>
          </div>

          <div className="p-4 bg-background-hover rounded-lg">
            <p className="text-xs text-text-muted uppercase mb-1">Expected Value</p>
            <p className="text-3xl font-bold text-primary">+${expectedValueDollars}</p>
            <p className="text-xs text-text-secondary mt-1">Per contract</p>
          </div>

          <div className="p-4 bg-background-hover rounded-lg">
            <p className="text-xs text-text-muted uppercase mb-1">Avg Win</p>
            <p className="text-2xl font-bold text-success">+{avgWinPercent}%</p>
            <p className="text-xs text-text-secondary mt-1">When profitable</p>
          </div>

          <div className="p-4 bg-background-hover rounded-lg">
            <p className="text-xs text-text-muted uppercase mb-1">Avg Loss</p>
            <p className="text-2xl font-bold text-danger">{avgLossPercent}%</p>
            <p className="text-xs text-text-secondary mt-1">When stopped out</p>
          </div>
        </div>

        {/* Risk/Reward Visual */}
        <div className="p-4 bg-gradient-to-r from-success/10 to-primary/10 rounded-lg border border-success/30">
          <h3 className="font-bold text-text-primary mb-3 flex items-center gap-2">
            <DollarSign className="w-5 h-5 text-success" />
            Risk/Reward Profile
          </h3>
          <div className="space-y-2">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-text-secondary">Profit Target</span>
                <span className="text-success font-semibold">+{avgWinPercent}%</span>
              </div>
              <div className="h-3 bg-background-deep rounded-full overflow-hidden">
                <div
                  className="h-full bg-success"
                  style={{ width: `${Math.abs(setup.avg_win) / (Math.abs(setup.avg_win) + Math.abs(setup.avg_loss)) * 100}%` }}
                />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-text-secondary">Stop Loss</span>
                <span className="text-danger font-semibold">{avgLossPercent}%</span>
              </div>
              <div className="h-3 bg-background-deep rounded-full overflow-hidden">
                <div
                  className="h-full bg-danger"
                  style={{ width: `${Math.abs(setup.avg_loss) / (Math.abs(setup.avg_win) + Math.abs(setup.avg_loss)) * 100}%` }}
                />
              </div>
            </div>
          </div>
          <p className="text-xs text-text-muted mt-3">
            Risk/Reward Ratio: {Math.abs(setup.avg_loss) > 0 ? (Math.abs(setup.avg_win) / Math.abs(setup.avg_loss)).toFixed(2) : '∞'}:1
          </p>
        </div>

        {/* Confidence Badge */}
        <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
          <span className="text-sm text-text-secondary">Setup Confidence Score</span>
          <div className="flex items-center gap-2">
            <div className="h-2 w-32 bg-background-deep rounded-full overflow-hidden">
              <div
                className={`h-full ${
                  setup.confidence_score >= 80 ? 'bg-success' :
                  setup.confidence_score >= 60 ? 'bg-warning' : 'bg-danger'
                }`}
                style={{ width: `${setup.confidence_score}%` }}
              />
            </div>
            <span className={`text-xl font-bold ${
              setup.confidence_score >= 80 ? 'text-success' :
              setup.confidence_score >= 60 ? 'text-warning' : 'text-danger'
            }`}>
              {setup.confidence_score}%
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

export const StrikeProbabilityMatrix: React.FC<{
  strikes: StrikeProbability[]
  spotPrice: number
  symbol: string
}> = ({ strikes, spotPrice, symbol }) => {
  return (
    <div className="card">
      <h2 className="text-xl font-semibold text-text-primary mb-4 flex items-center gap-2">
        <BarChart3 className="w-5 h-5 text-primary" />
        Strike-Specific Probability Matrix
      </h2>
      <p className="text-sm text-text-secondary mb-4">
        💰 <strong>HOW TO USE:</strong> Higher win rates = safer plays. Higher expected returns = bigger payouts. Expected value combines both for best risk-adjusted entry.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-3 px-4 text-text-secondary text-sm font-semibold">Strike</th>
              <th className="text-left py-3 px-4 text-text-secondary text-sm font-semibold">Distance</th>
              <th className="text-left py-3 px-4 text-text-secondary text-sm font-semibold">Delta</th>
              <th className="text-left py-3 px-4 text-text-secondary text-sm font-semibold">Win Rate</th>
              <th className="text-left py-3 px-4 text-text-secondary text-sm font-semibold">Avg Return</th>
              <th className="text-left py-3 px-4 text-text-secondary text-sm font-semibold">Expected Value</th>
            </tr>
          </thead>
          <tbody>
            {strikes.map((strike, idx) => {
              const isNearATM = Math.abs(strike.distance_pct) < 0.5
              return (
                <tr
                  key={idx}
                  className={`border-b border-border hover:bg-background-hover transition-colors ${
                    isNearATM ? 'bg-primary/5' : ''
                  }`}
                >
                  <td className="py-3 px-4">
                    <span className="font-mono font-semibold text-text-primary">
                      ${strike.strike.toFixed(0)}
                      {isNearATM && <span className="ml-2 text-xs text-primary">ATM</span>}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <span className={`font-mono ${
                      strike.distance_pct > 0 ? 'text-success' : 'text-danger'
                    }`}>
                      {strike.distance_pct > 0 ? '+' : ''}{strike.distance_pct.toFixed(2)}%
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <span className="font-mono text-text-primary">{strike.estimated_delta.toFixed(2)}</span>
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-16 bg-background-deep rounded-full overflow-hidden">
                        <div
                          className={`h-full ${
                            strike.win_rate >= 0.7 ? 'bg-success' :
                            strike.win_rate >= 0.5 ? 'bg-warning' : 'bg-danger'
                          }`}
                          style={{ width: `${strike.win_rate * 100}%` }}
                        />
                      </div>
                      <span className={`font-semibold ${
                        strike.win_rate >= 0.7 ? 'text-success' :
                        strike.win_rate >= 0.5 ? 'text-warning' : 'text-danger'
                      }`}>
                        {(strike.win_rate * 100).toFixed(0)}%
                      </span>
                    </div>
                  </td>
                  <td className="py-3 px-4">
                    <span className="font-semibold text-success">+{(strike.expected_return * 100).toFixed(0)}%</span>
                  </td>
                  <td className="py-3 px-4">
                    <span className={`font-bold ${
                      strike.expected_value > 0.1 ? 'text-success' :
                      strike.expected_value > 0 ? 'text-warning' : 'text-danger'
                    }`}>
                      {strike.expected_value > 0 ? '+' : ''}{(strike.expected_value * 100).toFixed(1)}%
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-4 p-3 bg-background-hover rounded-lg">
        <p className="text-xs text-text-muted">
          <strong>💡 Reading the Matrix:</strong> Win Rate shows probability of profit. Avg Return shows typical profit when successful.
          Expected Value combines both (higher is better) - this is your true statistical edge.
        </p>
      </div>
    </div>
  )
}

export const WallProbabilityTracker: React.FC<{
  wallProbs: WallProbabilities
  spotPrice: number
}> = ({ wallProbs, spotPrice }) => {
  const { call_wall, put_wall } = wallProbs

  return (
    <div className="card">
      <h2 className="text-xl font-semibold text-text-primary mb-4 flex items-center gap-2">
        <Zap className="w-5 h-5 text-warning" />
        Wall Probability Tracker
      </h2>
      <p className="text-sm text-text-secondary mb-4">
        💰 <strong>HOW TO USE:</strong> Walls act as magnets. Use high probabilities to set profit targets. Trade TOWARD walls for best odds.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Call Wall */}
        {call_wall && (
          <div className="p-4 bg-success/5 border-2 border-success/30 rounded-lg">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-lg font-bold text-success mb-1">🔼 Call Wall</h3>
                <p className="text-2xl font-bold text-text-primary font-mono">${call_wall.price.toFixed(2)}</p>
                <p className="text-sm text-text-secondary">
                  +{((call_wall.price - spotPrice) / spotPrice * 100).toFixed(2)}% from spot
                </p>
              </div>
            </div>

            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-text-secondary">1-Day Probability</span>
                  <span className="font-semibold text-success">{(call_wall.prob_1d * 100).toFixed(0)}%</span>
                </div>
                <div className="h-2 bg-background-deep rounded-full overflow-hidden">
                  <div className="h-full bg-success" style={{ width: `${call_wall.prob_1d * 100}%` }} />
                </div>
              </div>

              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-text-secondary">3-Day Probability</span>
                  <span className="font-semibold text-success">{(call_wall.prob_3d * 100).toFixed(0)}%</span>
                </div>
                <div className="h-2 bg-background-deep rounded-full overflow-hidden">
                  <div className="h-full bg-success" style={{ width: `${call_wall.prob_3d * 100}%` }} />
                </div>
              </div>

              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-text-secondary">5-Day Probability</span>
                  <span className="font-semibold text-success">{(call_wall.prob_5d * 100).toFixed(0)}%</span>
                </div>
                <div className="h-2 bg-background-deep rounded-full overflow-hidden">
                  <div className="h-full bg-success" style={{ width: `${call_wall.prob_5d * 100}%` }} />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Put Wall */}
        {put_wall && (
          <div className="p-4 bg-danger/5 border-2 border-danger/30 rounded-lg">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-lg font-bold text-danger mb-1">🔽 Put Wall</h3>
                <p className="text-2xl font-bold text-text-primary font-mono">${put_wall.price.toFixed(2)}</p>
                <p className="text-sm text-text-secondary">
                  {((put_wall.price - spotPrice) / spotPrice * 100).toFixed(2)}% from spot
                </p>
              </div>
            </div>

            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-text-secondary">1-Day Probability</span>
                  <span className="font-semibold text-danger">{(put_wall.prob_1d * 100).toFixed(0)}%</span>
                </div>
                <div className="h-2 bg-background-deep rounded-full overflow-hidden">
                  <div className="h-full bg-danger" style={{ width: `${put_wall.prob_1d * 100}%` }} />
                </div>
              </div>

              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-text-secondary">3-Day Probability</span>
                  <span className="font-semibold text-danger">{(put_wall.prob_3d * 100).toFixed(0)}%</span>
                </div>
                <div className="h-2 bg-background-deep rounded-full overflow-hidden">
                  <div className="h-full bg-danger" style={{ width: `${put_wall.prob_3d * 100}%` }} />
                </div>
              </div>

              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-text-secondary">5-Day Probability</span>
                  <span className="font-semibold text-danger">{(put_wall.prob_5d * 100).toFixed(0)}%</span>
                </div>
                <div className="h-2 bg-background-deep rounded-full overflow-hidden">
                  <div className="h-full bg-danger" style={{ width: `${put_wall.prob_5d * 100}%` }} />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {!call_wall && !put_wall && (
        <div className="text-center py-8 text-text-muted">
          <AlertCircle className="w-12 h-12 mx-auto mb-2 opacity-50" />
          <p>No gamma walls detected</p>
        </div>
      )}
    </div>
  )
}

export const RegimeEdgeCalculator: React.FC<{ edge: RegimeEdge }> = ({ edge }) => {
  const edgeColor = edge.edge_percentage >= 30 ? 'success' : edge.edge_percentage >= 15 ? 'warning' : 'text-muted'
  const edgeLabel = edge.edge_percentage >= 30 ? 'STRONG EDGE' : edge.edge_percentage >= 15 ? 'MODERATE EDGE' : edge.edge_percentage > 0 ? 'SLIGHT EDGE' : 'NO EDGE'

  return (
    <div className="card border-2 border-primary bg-primary/5">
      <h2 className="text-xl font-semibold text-text-primary mb-4 flex items-center gap-2">
        <Percent className="w-5 h-5 text-primary" />
        Your Statistical Edge Right Now
      </h2>

      <div className="space-y-4">
        {/* Edge Comparison */}
        <div className="grid grid-cols-3 gap-4">
          <div className="p-4 bg-background-hover rounded-lg text-center">
            <p className="text-xs text-text-muted uppercase mb-1">Baseline (Coin Flip)</p>
            <p className="text-3xl font-bold text-text-secondary">{edge.baseline_win_rate.toFixed(0)}%</p>
          </div>

          <div className="p-4 bg-primary/10 rounded-lg text-center border-2 border-primary">
            <p className="text-xs text-text-muted uppercase mb-1">Current Regime</p>
            <p className="text-3xl font-bold text-primary">{edge.current_win_rate.toFixed(1)}%</p>
          </div>

          <div className={`p-4 bg-${edgeColor}/10 rounded-lg text-center border-2 border-${edgeColor}`}>
            <p className="text-xs text-text-muted uppercase mb-1">Your Edge</p>
            <p className={`text-3xl font-bold text-${edgeColor}`}>+{edge.edge_percentage.toFixed(1)}%</p>
          </div>
        </div>

        {/* Edge Label */}
        <div className={`p-4 bg-gradient-to-r from-${edgeColor}/10 to-${edgeColor}/5 rounded-lg border-l-4 border-${edgeColor}`}>
          <div className="flex items-center justify-between">
            <div>
              <h3 className={`text-2xl font-bold text-${edgeColor} mb-1`}>{edgeLabel}</h3>
              <p className="text-sm text-text-secondary">
                {edge.edge_percentage >= 30
                  ? 'Trade aggressively - this is your biggest advantage'
                  : edge.edge_percentage >= 15
                  ? 'Good opportunity - size positions appropriately'
                  : edge.edge_percentage > 0
                  ? 'Small edge - reduce position size'
                  : 'No statistical edge - avoid trading or wait for better setup'
                }
              </p>
            </div>
            <TrendingUp className={`w-12 h-12 text-${edgeColor}`} />
          </div>
        </div>

        {/* Sample Size Badge */}
        {Object.values(edge.regime_stats)[0] && (
          <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
            <span className="text-sm text-text-secondary">Based on historical patterns</span>
            <span className="text-sm font-semibold text-text-primary">
              {Object.values(edge.regime_stats)[0].sample_size} similar setups
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

// NEW: Position Sizing Card
export const PositionSizingCard: React.FC<{ sizing: PositionSizing; accountSize: number }> = ({ sizing, accountSize }) => {
  return (
    <div className="card border-2 border-primary bg-primary/5">
      <h2 className="text-xl font-semibold text-text-primary mb-4 flex items-center gap-2">
        <Calculator className="w-5 h-5 text-primary" />
        Position Sizing (Kelly Criterion)
      </h2>
      <p className="text-sm text-text-secondary mb-4">
        💰 <strong>HOW TO USE:</strong> Conservative sizing balances risk and reward. Never risk more than recommended.
      </p>

      <div className="space-y-4">
        {/* Recommended Position - Prominent */}
        <div className="p-6 bg-gradient-to-r from-primary/20 to-success/20 rounded-lg border-2 border-primary">
          <div className="text-center">
            <p className="text-sm text-text-muted uppercase mb-2">RECOMMENDED POSITION</p>
            <p className="text-5xl font-bold text-primary mb-2">{sizing.recommended_contracts}</p>
            <p className="text-lg text-text-primary">contracts</p>
            <p className="text-sm text-text-secondary mt-2">
              {sizing.conservative_pct.toFixed(1)}% of account (Half Kelly)
            </p>
          </div>
        </div>

        {/* Sizing Options Grid */}
        <div className="grid grid-cols-3 gap-4">
          <div className="p-4 bg-background-hover rounded-lg text-center">
            <p className="text-xs text-text-muted uppercase mb-1">Conservative</p>
            <p className="text-2xl font-bold text-success">{Math.max(1, Math.floor(sizing.recommended_contracts * 0.5))}</p>
            <p className="text-xs text-text-secondary mt-1">Ultra-safe</p>
          </div>
          <div className="p-4 bg-primary/10 rounded-lg text-center border-2 border-primary">
            <p className="text-xs text-text-muted uppercase mb-1">Recommended</p>
            <p className="text-2xl font-bold text-primary">{sizing.recommended_contracts}</p>
            <p className="text-xs text-text-secondary mt-1">Optimal</p>
          </div>
          <div className="p-4 bg-warning/10 rounded-lg text-center border border-warning">
            <p className="text-xs text-text-muted uppercase mb-1">Aggressive</p>
            <p className="text-2xl font-bold text-warning">{sizing.max_contracts}</p>
            <p className="text-xs text-text-secondary mt-1">Max risk</p>
          </div>
        </div>

        {/* Kelly Percentages */}
        <div className="p-4 bg-background-hover rounded-lg">
          <h3 className="text-sm font-semibold text-text-primary mb-3">Kelly Criterion Breakdown</h3>
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-sm text-text-secondary">Full Kelly</span>
              <span className="font-semibold text-text-primary">{sizing.kelly_pct.toFixed(1)}%</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-text-secondary">Half Kelly (Recommended)</span>
              <span className="font-semibold text-primary">{sizing.conservative_pct.toFixed(1)}%</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-text-secondary">Account Risk</span>
              <span className="font-semibold text-text-primary">{sizing.account_risk_pct.toFixed(1)}%</span>
            </div>
          </div>
        </div>

        {/* Warning */}
        <div className="p-3 bg-warning/10 border-l-4 border-warning rounded">
          <p className="text-xs text-text-muted">
            <strong>⚠️ Risk Management:</strong> Never exceed recommended position size. Kelly Criterion maximizes long-term growth while limiting drawdowns.
          </p>
        </div>
      </div>
    </div>
  )
}

// NEW: Risk Analysis Card
export const RiskAnalysisCard: React.FC<{ risk: RiskAnalysis }> = ({ risk }) => {
  const roi = risk.roi_percent

  return (
    <div className="card border-2 border-success bg-success/5">
      <h2 className="text-xl font-semibold text-text-primary mb-4 flex items-center gap-2">
        <Shield className="w-5 h-5 text-success" />
        Risk/Reward in Dollars
      </h2>
      <p className="text-sm text-text-secondary mb-4">
        💰 <strong>HOW TO USE:</strong> Expected value is your average profit per trade. Positive EV = profitable long-term.
      </p>

      <div className="space-y-4">
        {/* Expected Value - Prominent */}
        <div className="p-6 bg-gradient-to-r from-success/20 to-primary/20 rounded-lg border-2 border-success">
          <div className="text-center">
            <p className="text-sm text-text-muted uppercase mb-2">EXPECTED VALUE</p>
            <p className="text-5xl font-bold text-success mb-2">
              ${risk.expected_value_dollars >= 0 ? '+' : ''}{risk.expected_value_dollars.toFixed(0)}
            </p>
            <p className="text-lg text-text-primary">per trade</p>
            <p className="text-sm text-success mt-2">
              {roi >= 0 ? '+' : ''}{roi.toFixed(1)}% ROI
            </p>
          </div>
        </div>

        {/* Scenarios Grid */}
        <div className="grid grid-cols-3 gap-4">
          <div className="p-4 bg-background-hover rounded-lg text-center">
            <p className="text-xs text-text-muted uppercase mb-1">Total Cost</p>
            <p className="text-xl font-bold text-text-primary">${risk.total_cost.toFixed(0)}</p>
            <p className="text-xs text-text-secondary mt-1">Initial investment</p>
          </div>
          <div className="p-4 bg-success/10 rounded-lg text-center border-2 border-success">
            <p className="text-xs text-text-muted uppercase mb-1">Best Case</p>
            <p className="text-xl font-bold text-success">+${risk.best_case_profit.toFixed(0)}</p>
            <p className="text-xs text-text-secondary mt-1">If win</p>
          </div>
          <div className="p-4 bg-danger/10 rounded-lg text-center border-2 border-danger">
            <p className="text-xs text-text-muted uppercase mb-1">Worst Case</p>
            <p className="text-xl font-bold text-danger">-${Math.abs(risk.worst_case_loss).toFixed(0)}</p>
            <p className="text-xs text-text-secondary mt-1">If loss</p>
          </div>
        </div>

        {/* Risk Percentage */}
        <div className="p-4 bg-background-hover rounded-lg">
          <div className="flex justify-between items-center mb-2">
            <span className="text-sm text-text-secondary">Max Account Risk</span>
            <span className={`text-2xl font-bold ${
              risk.max_account_risk_pct <= 2 ? 'text-success' :
              risk.max_account_risk_pct <= 5 ? 'text-warning' : 'text-danger'
            }`}>
              {risk.max_account_risk_pct.toFixed(1)}%
            </span>
          </div>
          <div className="h-3 bg-background-deep rounded-full overflow-hidden">
            <div
              className={`h-full ${
                risk.max_account_risk_pct <= 2 ? 'bg-success' :
                risk.max_account_risk_pct <= 5 ? 'bg-warning' : 'bg-danger'
              }`}
              style={{ width: `${Math.min(risk.max_account_risk_pct, 10) * 10}%` }}
            />
          </div>
          <p className="text-xs text-text-muted mt-2">
            {risk.max_account_risk_pct <= 2 ? '✅ Safe risk level' :
             risk.max_account_risk_pct <= 5 ? '⚠️ Moderate risk' : '🚨 High risk - reduce position'}
          </p>
        </div>
      </div>
    </div>
  )
}

// NEW: Holding Period Chart
export const HoldingPeriodChart: React.FC<{ holding: HoldingPeriod }> = ({ holding }) => {
  const days = [
    { day: 1, rate: holding.day_1_win_rate },
    { day: 2, rate: holding.day_2_win_rate },
    { day: 3, rate: holding.day_3_win_rate },
    { day: 4, rate: holding.day_4_win_rate },
    { day: 5, rate: holding.day_5_win_rate },
  ]

  const maxRate = Math.max(...days.map(d => d.rate))

  return (
    <div className="card">
      <h2 className="text-xl font-semibold text-text-primary mb-4 flex items-center gap-2">
        <Clock className="w-5 h-5 text-primary" />
        Optimal Holding Period
      </h2>
      <p className="text-sm text-text-secondary mb-4">
        💰 <strong>HOW TO USE:</strong> Day {holding.optimal_day} has highest win rate. Exit before theta decay erodes gains.
      </p>

      <div className="space-y-4">
        {/* Optimal Day - Prominent */}
        <div className="p-6 bg-gradient-to-r from-primary/20 to-success/20 rounded-lg border-2 border-primary text-center">
          <p className="text-sm text-text-muted uppercase mb-2">OPTIMAL HOLDING PERIOD</p>
          <p className="text-5xl font-bold text-primary mb-2">{holding.optimal_day}</p>
          <p className="text-lg text-text-primary">days</p>
          <p className="text-sm text-success mt-2">
            {(maxRate * 100).toFixed(1)}% win rate
          </p>
        </div>

        {/* Day-by-Day Chart */}
        <div className="space-y-3">
          {days.map((day) => {
            const isOptimal = day.day === holding.optimal_day
            return (
              <div key={day.day} className={`p-3 rounded-lg ${isOptimal ? 'bg-primary/10 border-2 border-primary' : 'bg-background-hover'}`}>
                <div className="flex justify-between items-center mb-2">
                  <span className={`font-semibold ${isOptimal ? 'text-primary' : 'text-text-primary'}`}>
                    Day {day.day} {isOptimal && '⭐ OPTIMAL'}
                  </span>
                  <span className={`text-xl font-bold ${
                    day.rate >= 0.7 ? 'text-success' :
                    day.rate >= 0.5 ? 'text-warning' : 'text-danger'
                  }`}>
                    {(day.rate * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="h-3 bg-background-deep rounded-full overflow-hidden">
                  <div
                    className={`h-full ${
                      day.rate >= 0.7 ? 'bg-success' :
                      day.rate >= 0.5 ? 'bg-warning' : 'bg-danger'
                    }`}
                    style={{ width: `${day.rate * 100}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>

        <div className="p-3 bg-background-hover rounded-lg">
          <p className="text-xs text-text-muted">
            <strong>💡 Tip:</strong> Win rate typically peaks at Day 3 for gamma plays as option delta increases. Exit before theta decay dominates.
          </p>
        </div>
      </div>
    </div>
  )
}

// NEW: Historical Setups Table
export const HistoricalSetupsTable: React.FC<{ setups: HistoricalSetup[] }> = ({ setups }) => {
  if (!setups || setups.length === 0) {
    return null
  }

  const wins = setups.filter(s => s.outcome === 'WIN').length
  const winRate = (wins / setups.length) * 100

  return (
    <div className="card">
      <h2 className="text-xl font-semibold text-text-primary mb-4 flex items-center gap-2">
        <History className="w-5 h-5 text-primary" />
        Historical Similar Setups
      </h2>
      <p className="text-sm text-text-secondary mb-4">
        💰 <strong>HOW TO USE:</strong> Past setups matching current conditions. See how similar trades performed.
      </p>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-4 mb-4">
        <div className="p-3 bg-background-hover rounded-lg text-center">
          <p className="text-xs text-text-muted uppercase mb-1">Total Setups</p>
          <p className="text-2xl font-bold text-text-primary">{setups.length}</p>
        </div>
        <div className="p-3 bg-success/10 rounded-lg text-center border-2 border-success">
          <p className="text-xs text-text-muted uppercase mb-1">Wins</p>
          <p className="text-2xl font-bold text-success">{wins}</p>
        </div>
        <div className="p-3 bg-background-hover rounded-lg text-center">
          <p className="text-xs text-text-muted uppercase mb-1">Win Rate</p>
          <p className="text-2xl font-bold text-primary">{winRate.toFixed(0)}%</p>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-2 px-3 text-text-secondary text-xs font-semibold">Date</th>
              <th className="text-left py-2 px-3 text-text-secondary text-xs font-semibold">Outcome</th>
              <th className="text-right py-2 px-3 text-text-secondary text-xs font-semibold">P&L $</th>
              <th className="text-right py-2 px-3 text-text-secondary text-xs font-semibold">P&L %</th>
              <th className="text-right py-2 px-3 text-text-secondary text-xs font-semibold">Hold Days</th>
            </tr>
          </thead>
          <tbody>
            {setups.map((setup, idx) => (
              <tr key={idx} className="border-b border-border hover:bg-background-hover transition-colors">
                <td className="py-2 px-3 text-sm text-text-primary">{setup.date}</td>
                <td className="py-2 px-3">
                  <span className={`text-xs font-semibold px-2 py-1 rounded ${
                    setup.outcome === 'WIN' ? 'bg-success/20 text-success' : 'bg-danger/20 text-danger'
                  }`}>
                    {setup.outcome}
                  </span>
                </td>
                <td className={`py-2 px-3 text-right font-semibold ${
                  setup.pnl_dollars >= 0 ? 'text-success' : 'text-danger'
                }`}>
                  {setup.pnl_dollars >= 0 ? '+' : ''}${setup.pnl_dollars.toFixed(0)}
                </td>
                <td className={`py-2 px-3 text-right font-semibold ${
                  setup.pnl_percent >= 0 ? 'text-success' : 'text-danger'
                }`}>
                  {setup.pnl_percent >= 0 ? '+' : ''}{setup.pnl_percent.toFixed(1)}%
                </td>
                <td className="py-2 px-3 text-right text-sm text-text-primary">{setup.hold_days}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// NEW: Regime Stability Indicator
export const RegimeStabilityIndicator: React.FC<{ stability: RegimeStability }> = ({ stability }) => {
  const stayProb = stability.stay_probability * 100
  const isStable = stayProb >= stability.alert_threshold

  return (
    <div className={`card border-2 ${isStable ? 'border-success bg-success/5' : 'border-warning bg-warning/5'}`}>
      <h2 className="text-xl font-semibold text-text-primary mb-4 flex items-center gap-2">
        <Activity className="w-5 h-5 text-primary" />
        Regime Stability Indicator
      </h2>
      <p className="text-sm text-text-secondary mb-4">
        💰 <strong>HOW TO USE:</strong> High stability = regime likely to persist. Low stability = prepare for regime change.
      </p>

      <div className="space-y-4">
        {/* Current State */}
        <div className="p-4 bg-background-hover rounded-lg">
          <div className="flex justify-between items-center">
            <div>
              <p className="text-xs text-text-muted uppercase mb-1">Current Regime</p>
              <p className="text-2xl font-bold text-primary">{stability.current_state}</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-text-muted uppercase mb-1">Stay Probability</p>
              <p className={`text-3xl font-bold ${isStable ? 'text-success' : 'text-warning'}`}>
                {stayProb.toFixed(0)}%
              </p>
            </div>
          </div>
        </div>

        {/* Stability Bar */}
        <div>
          <div className="flex justify-between text-sm mb-2">
            <span className="text-text-secondary">Regime Stability</span>
            <span className={`font-semibold ${isStable ? 'text-success' : 'text-warning'}`}>
              {isStable ? '✅ STABLE' : '⚠️ UNSTABLE'}
            </span>
          </div>
          <div className="h-4 bg-background-deep rounded-full overflow-hidden">
            <div
              className={`h-full ${isStable ? 'bg-success' : 'bg-warning'}`}
              style={{ width: `${stayProb}%` }}
            />
          </div>
        </div>

        {/* Shift Probabilities */}
        {Object.keys(stability.shift_probabilities).length > 0 && (
          <div className="p-4 bg-background-hover rounded-lg">
            <h3 className="text-sm font-semibold text-text-primary mb-3">Regime Shift Probabilities</h3>
            <div className="space-y-2">
              {Object.entries(stability.shift_probabilities).map(([state, prob]) => (
                <div key={state} className="flex justify-between items-center">
                  <span className="text-sm text-text-secondary">→ {state}</span>
                  <span className="font-semibold text-text-primary">{(prob * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recommendation */}
        <div className={`p-4 rounded-lg border-l-4 ${
          isStable ? 'bg-success/10 border-success' : 'bg-warning/10 border-warning'
        }`}>
          <p className="text-sm font-semibold text-text-primary mb-1">
            {isStable ? '✅ RECOMMENDATION' : '⚠️ RECOMMENDATION'}
          </p>
          <p className="text-sm text-text-secondary">{stability.recommendation}</p>
        </div>
      </div>
    </div>
  )
}

export default function ProbabilityAnalysis({ data, symbol, spotPrice }: ProbabilityAnalysisProps) {
  return (
    <div className="space-y-6">
      {/* Best Setup - Prominent */}
      {data.best_setup && (
        <BestSetupCard setup={data.best_setup} symbol={symbol} />
      )}

      {/* NEW: Two-column layout for Position Sizing and Risk Analysis */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {data.position_sizing && (
          <PositionSizingCard sizing={data.position_sizing} accountSize={data.account_size} />
        )}
        {data.risk_analysis && (
          <RiskAnalysisCard risk={data.risk_analysis} />
        )}
      </div>

      {/* Regime Edge Calculator */}
      <RegimeEdgeCalculator edge={data.regime_edge} />

      {/* NEW: Two-column layout for Holding Period and Regime Stability */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {data.holding_period && (
          <HoldingPeriodChart holding={data.holding_period} />
        )}
        {data.regime_stability && (
          <RegimeStabilityIndicator stability={data.regime_stability} />
        )}
      </div>

      {/* NEW: Historical Setups */}
      {data.historical_setups && data.historical_setups.length > 0 && (
        <HistoricalSetupsTable setups={data.historical_setups} />
      )}

      {/* Wall Probability Tracker */}
      <WallProbabilityTracker wallProbs={data.wall_probabilities} spotPrice={spotPrice} />

      {/* Strike Probability Matrix */}
      {data.strike_probabilities.length > 0 && (
        <StrikeProbabilityMatrix
          strikes={data.strike_probabilities}
          spotPrice={spotPrice}
          symbol={symbol}
        />
      )}
    </div>
  )
}
