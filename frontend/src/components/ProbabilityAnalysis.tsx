'use client'

import React from 'react'
import { Target, TrendingUp, Zap, DollarSign, Percent, BarChart3, AlertCircle } from 'lucide-react'

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

interface ProbabilityData {
  best_setup: TradeSetup | null
  strike_probabilities: StrikeProbability[]
  wall_probabilities: WallProbabilities
  regime_edge: RegimeEdge
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
          <p className="text-sm text-text-secondary">Based on {setup.sample_size} historical similar setups</p>
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
            Risk/Reward Ratio: {(Math.abs(setup.avg_win) / Math.abs(setup.avg_loss)).toFixed(2)}:1
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

export default function ProbabilityAnalysis({ data, symbol, spotPrice }: ProbabilityAnalysisProps) {
  return (
    <div className="space-y-6">
      {/* Best Setup - Prominent */}
      {data.best_setup && (
        <BestSetupCard setup={data.best_setup} symbol={symbol} />
      )}

      {/* Regime Edge Calculator */}
      <RegimeEdgeCalculator edge={data.regime_edge} />

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
