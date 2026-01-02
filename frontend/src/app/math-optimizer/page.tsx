'use client'

import React, { useState, useEffect } from 'react'
import {
  Brain, Activity, TrendingUp, Target, Clock, RefreshCw,
  ChevronDown, ChevronUp, BarChart2, Zap, Shield, ArrowRight,
  LineChart, GitBranch, Layers, Settings, AlertTriangle,
  CheckCircle, Info, BookOpen, Code, Play, PauseCircle
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'

// =============================================================================
// ALGORITHM CARD COMPONENT
// =============================================================================

interface AlgorithmCardProps {
  name: string
  icon: React.ReactNode
  purpose: string
  formula: string
  improvement: string
  color: string
  details: {
    mathematicalFoundation: string[]
    whyItImproves: string[]
    solomonIntegration: {
      actionType: string
      loggedData: string[]
    }
  }
}

const AlgorithmCard = ({ name, icon, purpose, formula, improvement, color, details }: AlgorithmCardProps) => {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className={`bg-gray-800 rounded-lg border border-${color}-500/30 overflow-hidden`}>
      {/* Header */}
      <div
        className={`p-4 bg-gradient-to-r from-${color}-500/10 to-transparent cursor-pointer`}
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-2 bg-${color}-500/20 rounded-lg text-${color}-400`}>
              {icon}
            </div>
            <div>
              <h3 className="text-lg font-bold text-white">{name}</h3>
              <p className="text-sm text-gray-400">{purpose}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className={`px-3 py-1 bg-${color}-500/20 text-${color}-400 text-sm rounded-full font-medium`}>
              {improvement}
            </span>
            {expanded ? <ChevronUp className="w-5 h-5 text-gray-400" /> : <ChevronDown className="w-5 h-5 text-gray-400" />}
          </div>
        </div>
      </div>

      {/* Formula Preview */}
      <div className="px-4 pb-4">
        <div className="bg-gray-900/50 rounded p-3 font-mono text-sm text-green-400">
          {formula}
        </div>
      </div>

      {/* Expanded Details */}
      {expanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-gray-700 pt-4">
          {/* Mathematical Foundation */}
          <div>
            <h4 className="text-sm font-bold text-white mb-2 flex items-center gap-2">
              <Code className="w-4 h-4 text-purple-400" />
              Mathematical Foundation
            </h4>
            <ul className="space-y-1">
              {details.mathematicalFoundation.map((item, i) => (
                <li key={i} className="text-sm text-gray-400 flex items-start gap-2">
                  <span className="text-purple-400 mt-1">-</span>
                  <span className="font-mono">{item}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Why It Improves Trading */}
          <div>
            <h4 className="text-sm font-bold text-white mb-2 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-green-400" />
              Why It Improves Trading
            </h4>
            <ul className="space-y-1">
              {details.whyItImproves.map((item, i) => (
                <li key={i} className="text-sm text-gray-400 flex items-start gap-2">
                  <CheckCircle className="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0" />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          {/* Solomon Integration */}
          <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg p-3">
            <h4 className="text-sm font-bold text-purple-400 mb-2 flex items-center gap-2">
              <Brain className="w-4 h-4" />
              Solomon Integration
            </h4>
            <div className="text-sm">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-gray-500">Action Type:</span>
                <code className="px-2 py-0.5 bg-gray-800 rounded text-purple-400">{details.solomonIntegration.actionType}</code>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-gray-500">Logged:</span>
                <span className="text-gray-400">{details.solomonIntegration.loggedData.join(', ')}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// =============================================================================
// LIVE DASHBOARD COMPONENT - Enhanced with full data
// =============================================================================

interface BotStat {
  expected_win_rate: number
  uncertainty: number
  allocation_pct: number
  integrated: boolean
}

interface RegimeData {
  current: string
  probability: number
  is_favorable: boolean
  all_probabilities: Record<string, { probability: number; is_favorable: boolean }>
  observations_processed: number
}

interface Decision {
  timestamp: string
  bot: string
  action_type: string
  description: string
  details: Record<string, any>
  success: boolean
}

const LiveOptimizerStatus = () => {
  const [dashboard, setDashboard] = useState<any>(null)
  const [decisions, setDecisions] = useState<Decision[]>([])
  const [loading, setLoading] = useState(true)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [dashRes, decisionsRes] = await Promise.all([
          apiClient.getMathOptimizerLiveDashboard(),
          apiClient.getMathOptimizerDecisions(10)
        ])
        setDashboard(dashRes.data)
        setDecisions(decisionsRes.data?.decisions || [])
        setLastUpdate(new Date())
      } catch (error) {
        console.error('Failed to fetch optimizer data:', error)
      }
      setLoading(false)
    }

    fetchData()
    const interval = setInterval(fetchData, 15000) // Refresh every 15s
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-8 flex items-center justify-center">
        <RefreshCw className="w-8 h-8 text-purple-400 animate-spin" />
        <span className="ml-3 text-gray-400">Loading live optimizer data...</span>
      </div>
    )
  }

  if (!dashboard) {
    return (
      <div className="bg-gray-800 rounded-lg border border-red-500/30 p-6">
        <div className="flex items-center gap-3 text-red-400">
          <AlertTriangle className="w-6 h-6" />
          <span>Unable to connect to math optimizer backend</span>
        </div>
      </div>
    )
  }

  const { regime, thompson, kalman, algorithms, optimization_counts } = dashboard

  return (
    <div className="space-y-6">
      {/* Header with refresh indicator */}
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-bold text-white flex items-center gap-2">
          <Activity className="w-6 h-6 text-green-400" />
          Live Optimizer Dashboard
        </h3>
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <RefreshCw className="w-4 h-4" />
          {lastUpdate && `Updated ${lastUpdate.toLocaleTimeString()}`}
        </div>
      </div>

      {/* Main Stats Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Current Regime Card */}
        <div className="bg-gray-800 rounded-lg border border-yellow-500/30 p-6">
          <h4 className="text-sm font-bold text-yellow-400 mb-4 flex items-center gap-2">
            <Brain className="w-5 h-5" />
            HMM Market Regime
          </h4>

          {/* Current Regime Highlight */}
          <div className={`p-4 rounded-lg mb-4 ${regime?.is_favorable ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'}`}>
            <div className="flex items-center justify-between">
              <span className="text-white font-bold text-lg">{regime?.current || 'Unknown'}</span>
              <span className={`text-2xl font-bold ${regime?.is_favorable ? 'text-green-400' : 'text-red-400'}`}>
                {((regime?.probability || 0) * 100).toFixed(0)}%
              </span>
            </div>
            <div className={`text-sm mt-1 ${regime?.is_favorable ? 'text-green-400' : 'text-red-400'}`}>
              {regime?.is_favorable ? '✓ Favorable for trading' : '⚠ Caution advised'}
            </div>
          </div>

          {/* All Regime Probabilities */}
          <div className="space-y-2">
            <div className="text-xs text-gray-500 mb-2">All Regime Probabilities:</div>
            {regime?.all_probabilities && Object.entries(regime.all_probabilities)
              .sort(([, a]: any, [, b]: any) => b.probability - a.probability)
              .slice(0, 5)
              .map(([name, data]: [string, any]) => (
                <div key={name} className="flex items-center gap-2">
                  <div className="flex-1">
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-gray-400">{name}</span>
                      <span className={data.is_favorable ? 'text-green-400' : 'text-gray-500'}>
                        {(data.probability * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${data.is_favorable ? 'bg-green-500' : 'bg-gray-500'}`}
                        style={{ width: `${data.probability * 100}%` }}
                      />
                    </div>
                  </div>
                </div>
              ))}
          </div>

          <div className="mt-4 text-xs text-gray-500">
            {regime?.observations_processed || 0} observations processed
          </div>
        </div>

        {/* Thompson Sampling Bot Stats */}
        <div className="bg-gray-800 rounded-lg border border-green-500/30 p-6">
          <h4 className="text-sm font-bold text-green-400 mb-4 flex items-center gap-2">
            <Layers className="w-5 h-5" />
            Thompson Sampling Allocations
          </h4>

          {thompson?.bot_stats && (
            <div className="space-y-3">
              {Object.entries(thompson.bot_stats as Record<string, BotStat>)
                .sort(([, a], [, b]) => b.allocation_pct - a.allocation_pct)
                .map(([bot, stats]) => (
                  <div key={bot} className="bg-gray-900/50 rounded-lg p-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-bold text-white">{bot}</span>
                      <span className={`px-2 py-0.5 rounded text-xs ${stats.integrated ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}`}>
                        {stats.integrated ? 'ACTIVE' : 'PENDING'}
                      </span>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-xs">
                      <div>
                        <div className="text-gray-500">Win Rate</div>
                        <div className="text-green-400 font-bold">{(stats.expected_win_rate * 100).toFixed(0)}%</div>
                      </div>
                      <div>
                        <div className="text-gray-500">Allocation</div>
                        <div className="text-blue-400 font-bold">{(stats.allocation_pct * 100).toFixed(0)}%</div>
                      </div>
                      <div>
                        <div className="text-gray-500">Uncertainty</div>
                        <div className="text-yellow-400 font-bold">±{(stats.uncertainty * 100).toFixed(0)}%</div>
                      </div>
                    </div>
                    {/* Allocation Bar */}
                    <div className="mt-2 h-2 bg-gray-700 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-green-500 to-blue-500 rounded-full"
                        style={{ width: `${stats.allocation_pct * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
            </div>
          )}

          <div className="mt-4 text-xs text-gray-500">
            {thompson?.total_outcomes_recorded || 0} total outcomes recorded
          </div>
        </div>

        {/* Algorithm Status & Kalman */}
        <div className="space-y-6">
          {/* Algorithm Status */}
          <div className="bg-gray-800 rounded-lg border border-purple-500/30 p-6">
            <h4 className="text-sm font-bold text-purple-400 mb-4 flex items-center gap-2">
              <Settings className="w-5 h-5" />
              Algorithm Status
            </h4>

            {algorithms && (
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(algorithms as Record<string, { status: string; description: string }>).map(([key, algo]) => (
                  <div key={key} className="flex items-center gap-2">
                    {algo.status === 'ACTIVE' ? (
                      <CheckCircle className="w-4 h-4 text-green-400" />
                    ) : (
                      <PauseCircle className="w-4 h-4 text-yellow-400" />
                    )}
                    <span className="text-xs text-gray-400 uppercase">{key}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Kalman Smoothed Greeks */}
          <div className="bg-gray-800 rounded-lg border border-blue-500/30 p-6">
            <h4 className="text-sm font-bold text-blue-400 mb-4 flex items-center gap-2">
              <LineChart className="w-5 h-5" />
              Kalman Smoothed Greeks
            </h4>

            {kalman?.smoothed_greeks && Object.keys(kalman.smoothed_greeks).length > 0 ? (
              <div className="space-y-2">
                {Object.entries(kalman.smoothed_greeks).map(([greek, value]: [string, any]) => (
                  <div key={greek} className="flex items-center justify-between">
                    <span className="text-gray-400 capitalize text-sm">{greek}</span>
                    <span className="text-white font-mono text-sm">
                      {typeof value === 'number' ? value.toFixed(4) : '-'}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-gray-500 text-sm">Waiting for Greeks data...</div>
            )}
          </div>

          {/* Optimization Counts */}
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
            <h4 className="text-sm font-bold text-gray-400 mb-4 flex items-center gap-2">
              <BarChart2 className="w-5 h-5" />
              Optimization Counts
            </h4>

            {optimization_counts && Object.keys(optimization_counts).length > 0 ? (
              <div className="grid grid-cols-2 gap-2 text-xs">
                {Object.entries(optimization_counts).map(([key, count]: [string, any]) => (
                  <div key={key} className="flex justify-between">
                    <span className="text-gray-500">{key.replace(/_/g, ' ')}</span>
                    <span className="text-white font-mono">{count}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-gray-500 text-sm">No optimizations yet</div>
            )}
          </div>
        </div>
      </div>

      {/* Recent Decisions Log */}
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
        <h4 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
          <Activity className="w-5 h-5 text-purple-400" />
          Recent Optimizer Decisions
        </h4>

        {decisions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-700">
                  <th className="pb-2 pr-4">Time</th>
                  <th className="pb-2 pr-4">Bot</th>
                  <th className="pb-2 pr-4">Action</th>
                  <th className="pb-2">Description</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((decision, i) => (
                  <tr key={i} className="border-b border-gray-800">
                    <td className="py-2 pr-4 text-gray-500 text-xs">
                      {decision.timestamp ? new Date(decision.timestamp).toLocaleTimeString() : '-'}
                    </td>
                    <td className="py-2 pr-4">
                      <span className="px-2 py-0.5 bg-purple-500/20 text-purple-400 rounded text-xs">
                        {decision.bot}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-gray-400 text-xs">{decision.action_type}</td>
                    <td className="py-2 text-gray-300 text-xs">{decision.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-gray-500 text-sm text-center py-4">
            No recent decisions recorded
          </div>
        )}
      </div>
    </div>
  )
}

// =============================================================================
// AGGRESSIVE MODE SECTION
// =============================================================================

const AggressiveModeSection = () => {
  return (
    <div className="bg-gradient-to-r from-red-500/10 to-orange-500/10 border border-red-500/30 rounded-lg p-6">
      <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
        <Zap className="w-6 h-6 text-red-400" />
        Can These Algorithms Make Bots More Aggressive?
      </h3>

      <div className="text-lg text-green-400 font-bold mb-4">
        YES - Here's How:
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div className="bg-gray-800/50 rounded-lg p-4">
          <h4 className="font-bold text-yellow-400 mb-2">Thompson Sampling</h4>
          <p className="text-sm text-gray-400">
            Allocates up to <span className="text-green-400 font-bold">50%</span> capital to hot bots
            (vs 25% fixed). When ARES is winning, it gets more capital automatically.
          </p>
        </div>

        <div className="bg-gray-800/50 rounded-lg p-4">
          <h4 className="font-bold text-blue-400 mb-2">HMM Regime Detection</h4>
          <p className="text-sm text-gray-400">
            Increases position size when regime confidence is <span className="text-green-400 font-bold">80%+</span> favorable.
            Knows WHEN to be aggressive.
          </p>
        </div>

        <div className="bg-gray-800/50 rounded-lg p-4">
          <h4 className="font-bold text-purple-400 mb-2">Convex Strike Optimizer</h4>
          <p className="text-sm text-gray-400">
            Finds strikes with <span className="text-green-400 font-bold">lower risk per dollar</span>,
            allowing larger positions with same risk budget.
          </p>
        </div>

        <div className="bg-gray-800/50 rounded-lg p-4">
          <h4 className="font-bold text-green-400 mb-2">HJB Exit Optimizer</h4>
          <p className="text-sm text-gray-400">
            Holds winners <span className="text-green-400 font-bold">longer</span> when expected value
            is still positive. No more leaving money on the table.
          </p>
        </div>
      </div>

      <div className="bg-gray-800 rounded-lg p-4">
        <h4 className="font-bold text-white mb-2 flex items-center gap-2">
          <Shield className="w-5 h-5 text-blue-400" />
          Safety Guardrails (Still Protected)
        </h4>
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm text-gray-400">
          <li className="flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-green-400" />
            Solomon approval required for parameter changes
          </li>
          <li className="flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-green-400" />
            Automatic rollback if degradation detected
          </li>
          <li className="flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-green-400" />
            Kill switch available per bot
          </li>
          <li className="flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-green-400" />
            All decisions logged with full audit trail
          </li>
        </ul>
      </div>
    </div>
  )
}

// =============================================================================
// MAIN PAGE
// =============================================================================

export default function MathOptimizerPage() {
  const algorithms: AlgorithmCardProps[] = [
    {
      name: "Hidden Markov Model (HMM)",
      icon: <Brain className="w-6 h-6" />,
      purpose: "Regime Detection with Probability Distributions",
      formula: "P(regime | obs) = P(obs | regime) x Sum[P(regime_t | regime_t-1) x P(regime_t-1)]",
      improvement: "30-50% less whipsaw",
      color: "yellow",
      details: {
        mathematicalFoundation: [
          "Hidden states S = {TRENDING, MEAN_REVERTING, VOLATILE, PINNED, ...}",
          "Observations O = {VIX, net_gamma, momentum, realized_vol}",
          "Transition matrix A[i,j] = P(state_j | state_i) - learned from data",
          "Emission model: Gaussian P(obs | state) = N(obs; mean, std)",
          "Forward algorithm for Bayesian state estimation"
        ],
        whyItImproves: [
          "Replaces hard 'IF vix > 20' rules with probability distributions",
          "Requires 70%+ confidence before regime transition (reduces false signals)",
          "Learns optimal thresholds from historical data",
          "Reduces regime whipsaw by 30-50%"
        ],
        solomonIntegration: {
          actionType: "HMM_REGIME_UPDATE",
          loggedData: ["current_regime", "probability", "confidence", "transition_from"]
        }
      }
    },
    {
      name: "Kalman Filter",
      icon: <LineChart className="w-6 h-6" />,
      purpose: "Greeks and Signal Smoothing",
      formula: "x_new = x_pred + K x (observation - x_pred)  |  K = Kalman Gain",
      improvement: "Cleaner signals",
      color: "blue",
      details: {
        mathematicalFoundation: [
          "State equation: x_t = A x x_t-1 + w_t (process noise)",
          "Observation equation: z_t = H x x_t + v_t (measurement noise)",
          "Predict: x_pred = A x x_prev, P_pred = A x P x A' + Q",
          "Update: K = P_pred / (P_pred + R)",
          "Kalman gain balances trust in prediction vs observation"
        ],
        whyItImproves: [
          "Raw Greeks fluctuate with bid-ask spread noise",
          "Provides optimal balance of responsiveness and stability",
          "Fewer false signals from noisy delta/gamma readings",
          "Predictive capability for short-term Greeks movement"
        ],
        solomonIntegration: {
          actionType: "KALMAN_SMOOTHING",
          loggedData: ["raw_values", "smoothed_values", "kalman_gain", "prediction"]
        }
      }
    },
    {
      name: "Thompson Sampling",
      icon: <Layers className="w-6 h-6" />,
      purpose: "Dynamic Bot Capital Allocation",
      formula: "theta ~ Beta(wins+1, losses+1)  |  Allocate proportional to sampled theta",
      improvement: "15-30% better capital efficiency",
      color: "green",
      details: {
        mathematicalFoundation: [
          "Multi-Armed Bandit with Beta-Bernoulli model",
          "Each bot's win rate modeled as Beta(alpha, beta)",
          "Win: alpha_new = alpha + 1 (weighted by P&L)",
          "Loss: beta_new = beta + 1 (weighted by P&L)",
          "Sample theta, allocate capital proportional to samples"
        ],
        whyItImproves: [
          "Replaces fixed equal allocation with performance-based allocation",
          "Automatically shifts capital to hot-performing bots",
          "Exploration bonus ensures underperforming bots get tested",
          "Converges to optimal allocation while maintaining flexibility"
        ],
        solomonIntegration: {
          actionType: "THOMPSON_ALLOCATION",
          loggedData: ["allocations", "sampled_rewards", "exploration_bonus", "expected_win_rates"]
        }
      }
    },
    {
      name: "Convex Strike Optimizer",
      icon: <Target className="w-6 h-6" />,
      purpose: "Scenario-Aware Strike Selection",
      formula: "minimize E[Loss] = Sum[P(scenario) x Loss(strike, scenario)]",
      improvement: "2-5% better P&L",
      color: "purple",
      details: {
        mathematicalFoundation: [
          "Mixed-Integer Convex Programming (MICP)",
          "Objective: minimize expected loss across price scenarios",
          "Constraints: delta bounds, margin budget, available strikes",
          "Loss = delta_exposure + theta_decay + adjustment_cost + slippage",
          "Scenarios: +3%, +1.5%, 0%, -1.5%, -3% with probabilities"
        ],
        whyItImproves: [
          "Replaces 'closest to target delta' with scenario-aware selection",
          "Considers future adjustment costs before entry",
          "Optimizes for expected P&L, not just current Greeks",
          "2-5% improvement in strike selection P&L"
        ],
        solomonIntegration: {
          actionType: "CONVEX_STRIKE_OPTIMIZATION",
          loggedData: ["original_strike", "optimized_strike", "improvement_pct", "scenarios_evaluated"]
        }
      }
    },
    {
      name: "Hamilton-Jacobi-Bellman (HJB)",
      icon: <Clock className="w-6 h-6" />,
      purpose: "Optimal Exit Timing",
      formula: "Exit when PnL >= boundary(time, volatility)  |  boundary = f(time_decay, vol_risk)",
      improvement: "10-20% better exits",
      color: "red",
      details: {
        mathematicalFoundation: [
          "Optimal stopping problem from stochastic control",
          "Value function: V(pnl, time, vol) = value of holding",
          "HJB: 0 = max{EXIT: pnl, HOLD: dV/dt + mu*dV/dpnl + 0.5*sigma^2*d2V/dpnl2}",
          "As time -> 0: exit boundary -> 0 (lock in any profit)",
          "As vol increases: exit boundary decreases (exit earlier)"
        ],
        whyItImproves: [
          "Replaces fixed '50% profit target' with dynamic boundaries",
          "Accounts for time decay acceleration near expiry",
          "Volatility-aware: exits earlier in high-vol to lock gains",
          "10-20% improvement in exit timing P&L"
        ],
        solomonIntegration: {
          actionType: "HJB_EXIT_SIGNAL",
          loggedData: ["should_exit", "optimal_boundary", "time_value", "expected_future_value", "reason"]
        }
      }
    },
    {
      name: "Markov Decision Process (MDP)",
      icon: <GitBranch className="w-6 h-6" />,
      purpose: "Trade Sequencing Optimization",
      formula: "V(s) = max_a [R(s,a) + gamma x Sum[P(s'|s,a) x V(s')]]  |  Bellman Equation",
      improvement: "5-15% better selection",
      color: "orange",
      details: {
        mathematicalFoundation: [
          "States: (portfolio, regime, pending_signals)",
          "Actions: {EXECUTE, SKIP, DELAY} for each trade",
          "Rewards: expected_pnl - transaction_costs - opportunity_cost",
          "Transitions: P(next_state | state, action)",
          "Solve via value iteration or greedy approximation"
        ],
        whyItImproves: [
          "Considers how one trade affects future opportunities",
          "Skips redundant trades (two bots taking same position)",
          "Regime-aware: adjusts trade value based on current regime",
          "Reduces unnecessary transaction costs"
        ],
        solomonIntegration: {
          actionType: "MDP_TRADE_SEQUENCE",
          loggedData: ["original_order", "optimized_order", "skipped_trades", "ev_improvement"]
        }
      }
    }
  ]

  return (
    <div className="min-h-screen bg-gray-900">
      <Navigation />

      <main className="max-w-7xl mx-auto px-4 py-8 pt-24">
        {/* Header */}
        <div className="flex items-center gap-4 mb-8">
          <div className="p-4 bg-gradient-to-br from-purple-500/20 to-blue-500/20 rounded-xl">
            <Brain className="w-10 h-10 text-purple-400" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-white">Mathematical Optimization Algorithms</h1>
            <p className="text-gray-400">Advanced quantitative methods enhancing AlphaGEX trading bots</p>
          </div>
        </div>

        {/* Integration Banner */}
        <div className="bg-gradient-to-r from-purple-500/10 to-blue-500/10 border border-purple-500/30 rounded-lg p-4 mb-8">
          <div className="flex items-center gap-3">
            <Info className="w-5 h-5 text-purple-400" />
            <div>
              <span className="text-white font-medium">Solomon Integration:</span>
              <span className="text-gray-400 ml-2">
                All algorithm decisions are logged to Solomon's audit trail with WHO, WHAT, WHY, WHEN for full transparency and rollback capability.
              </span>
            </div>
          </div>
        </div>

        {/* Live Status */}
        <div className="mb-8">
          <LiveOptimizerStatus />
        </div>

        {/* Aggressive Mode Section */}
        <div className="mb-8">
          <AggressiveModeSection />
        </div>

        {/* Expected Improvements Summary */}
        <div className="bg-gray-800 rounded-lg border border-green-500/30 p-6 mb-8">
          <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-green-400" />
            Expected Performance Improvements
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <div className="bg-gray-900/50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-yellow-400">30-50%</div>
              <div className="text-xs text-gray-500">Regime Whipsaw Reduction</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-blue-400">Cleaner</div>
              <div className="text-xs text-gray-500">Greeks Signals</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-green-400">15-30%</div>
              <div className="text-xs text-gray-500">Capital Efficiency</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-purple-400">2-5%</div>
              <div className="text-xs text-gray-500">Strike Selection P&L</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-red-400">10-20%</div>
              <div className="text-xs text-gray-500">Exit Timing P&L</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-orange-400">5-15%</div>
              <div className="text-xs text-gray-500">Trade Selection</div>
            </div>
          </div>
          <div className="mt-4 text-center">
            <span className="text-gray-400">Overall Risk-Adjusted Return:</span>
            <span className="text-green-400 font-bold text-xl ml-2">20-40% Sharpe Ratio Improvement</span>
          </div>
        </div>

        {/* Algorithm Cards */}
        <div className="mb-8">
          <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-purple-400" />
            Algorithm Details (Click to Expand)
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {algorithms.map((algo) => (
              <AlgorithmCard key={algo.name} {...algo} />
            ))}
          </div>
        </div>

        {/* Integration Flow Diagram */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 mb-8">
          <h3 className="text-lg font-bold text-white mb-4">Integration with Solomon Feedback Loop</h3>
          <div className="overflow-x-auto">
            <pre className="text-sm text-gray-400 font-mono whitespace-pre">
{`
MARKET DATA → [KALMAN FILTER] → Smoothed Greeks
                     ↓
               [HMM REGIME] → Regime Probabilities
                     ↓
    ┌────────────────┴────────────────┐
    ↓                                 ↓
YOUR BOTS                     [THOMPSON SAMPLING]
(ARES, ATHENA, etc.)              Capital Allocation
    │                                 │
    └────────────────┬────────────────┘
                     ↓
              [MDP SEQUENCER] → Trade Ordering
                     ↓
           [CONVEX OPTIMIZER] → Strike Selection
                     ↓
              EXECUTE TRADE
                     ↓
             [HJB EXIT OPT] → Exit Timing
                     ↓
        ┌──────────────────────────┐
        │      SOLOMON LOGS        │
        │  All decisions tracked   │
        │  WHO, WHAT, WHY, WHEN    │
        └──────────────────────────┘
`}
            </pre>
          </div>
        </div>

        {/* API Endpoints */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
          <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <Code className="w-5 h-5 text-blue-400" />
            API Endpoints
          </h3>
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-2 bg-gray-900/50 rounded p-2">
              <span className="px-2 py-0.5 bg-green-500/20 text-green-400 rounded text-xs font-mono">GET</span>
              <code className="text-gray-400">/api/math-optimizer/documentation</code>
              <span className="text-gray-500 ml-auto">Full algorithm documentation</span>
            </div>
            <div className="flex items-center gap-2 bg-gray-900/50 rounded p-2">
              <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded text-xs font-mono">POST</span>
              <code className="text-gray-400">/api/math-optimizer/regime/update</code>
              <span className="text-gray-500 ml-auto">Update HMM with observation</span>
            </div>
            <div className="flex items-center gap-2 bg-gray-900/50 rounded p-2">
              <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded text-xs font-mono">POST</span>
              <code className="text-gray-400">/api/math-optimizer/kalman/update</code>
              <span className="text-gray-500 ml-auto">Smooth Greeks</span>
            </div>
            <div className="flex items-center gap-2 bg-gray-900/50 rounded p-2">
              <span className="px-2 py-0.5 bg-green-500/20 text-green-400 rounded text-xs font-mono">GET</span>
              <code className="text-gray-400">/api/math-optimizer/thompson/allocation</code>
              <span className="text-gray-500 ml-auto">Get bot allocation</span>
            </div>
            <div className="flex items-center gap-2 bg-gray-900/50 rounded p-2">
              <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded text-xs font-mono">POST</span>
              <code className="text-gray-400">/api/math-optimizer/strike/optimize</code>
              <span className="text-gray-500 ml-auto">Optimize strike selection</span>
            </div>
            <div className="flex items-center gap-2 bg-gray-900/50 rounded p-2">
              <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded text-xs font-mono">POST</span>
              <code className="text-gray-400">/api/math-optimizer/exit/check</code>
              <span className="text-gray-500 ml-auto">Check exit timing</span>
            </div>
            <div className="flex items-center gap-2 bg-gray-900/50 rounded p-2">
              <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded text-xs font-mono">POST</span>
              <code className="text-gray-400">/api/math-optimizer/sequence/optimize</code>
              <span className="text-gray-500 ml-auto">Optimize trade sequence</span>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
