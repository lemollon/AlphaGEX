'use client'

import React, { useState, useEffect } from 'react'
import {
  Brain, Activity, TrendingUp, Target, Clock, RefreshCw,
  ChevronDown, ChevronUp, BarChart2, Zap, Shield, ArrowRight,
  LineChart, GitBranch, Layers, Settings, AlertTriangle,
  CheckCircle, Info, BookOpen, Code, Play, PauseCircle
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { api } from '@/lib/api'

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
// LIVE STATUS COMPONENT
// =============================================================================

const LiveOptimizerStatus = () => {
  const [status, setStatus] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await api.get('/api/math-optimizer/status')
        setStatus(response.data)
      } catch (error) {
        console.error('Failed to fetch optimizer status:', error)
      }
      setLoading(false)
    }

    fetchStatus()
    const interval = setInterval(fetchStatus, 30000)
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-6 flex items-center justify-center">
        <RefreshCw className="w-6 h-6 text-purple-400 animate-spin" />
      </div>
    )
  }

  if (!status?.optimizers) {
    return null
  }

  const { hmm_regime, kalman, thompson } = status.optimizers

  return (
    <div className="bg-gray-800 rounded-lg border border-purple-500/30 p-6">
      <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
        <Activity className="w-5 h-5 text-green-400" />
        Live Optimizer Status
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* HMM Regime */}
        <div className="bg-gray-900/50 rounded-lg p-4">
          <h4 className="text-sm font-bold text-yellow-400 mb-2">HMM Regime</h4>
          {hmm_regime?.current_belief && (
            <div className="space-y-1">
              {Object.entries(hmm_regime.current_belief).slice(0, 3).map(([regime, prob]: [string, any]) => (
                <div key={regime} className="flex items-center justify-between text-sm">
                  <span className="text-gray-400">{regime.replace(/_/g, ' ')}</span>
                  <span className={`font-bold ${prob > 0.5 ? 'text-green-400' : 'text-gray-500'}`}>
                    {(prob * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Kalman Smoothed */}
        <div className="bg-gray-900/50 rounded-lg p-4">
          <h4 className="text-sm font-bold text-blue-400 mb-2">Smoothed Greeks</h4>
          {kalman?.smoothed_greeks && (
            <div className="space-y-1">
              {Object.entries(kalman.smoothed_greeks).slice(0, 3).map(([greek, value]: [string, any]) => (
                <div key={greek} className="flex items-center justify-between text-sm">
                  <span className="text-gray-400 capitalize">{greek}</span>
                  <span className="text-white font-mono">{typeof value === 'number' ? value.toFixed(4) : '-'}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Thompson Allocation */}
        <div className="bg-gray-900/50 rounded-lg p-4">
          <h4 className="text-sm font-bold text-green-400 mb-2">Bot Allocation</h4>
          {thompson?.expected_win_rates && (
            <div className="space-y-1">
              {Object.entries(thompson.expected_win_rates).map(([bot, rate]: [string, any]) => (
                <div key={bot} className="flex items-center justify-between text-sm">
                  <span className="text-gray-400">{bot}</span>
                  <span className="text-white font-bold">{(rate * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}
        </div>
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
