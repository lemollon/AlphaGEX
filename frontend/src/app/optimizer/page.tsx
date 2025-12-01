'use client'

import { logger } from '@/lib/logger'

import { useState, useEffect } from 'react'
import { TrendingUp, Target, Activity, Zap, LineChart, Brain, Trophy, AlertCircle, CheckCircle, BarChart3, PieChart } from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'

interface StrikePerformanceData {
  strategy_name: string
  moneyness: string
  strike_distance: number
  vix_regime: string
  total_trades: number
  win_rate: number
  avg_pnl_pct: number
  avg_delta: number
}

interface DTEPerformanceData {
  strategy_name: string
  dte_bucket: string
  total_trades: number
  win_rate: number
  avg_pnl_pct: number
  avg_holding_hours: number
  theta_decay_efficiency: number
}

interface RegimePerformanceData {
  vix_regime: string
  strategy_name: string
  total_trades: number
  win_rate: number
  avg_pnl_pct: number
  best_moneyness: string
  best_dte_bucket: string
}

interface GreeksPerformanceData {
  strategy_name: string
  avg_entry_delta: number
  avg_entry_gamma: number
  avg_entry_theta: number
  avg_entry_vega: number
  total_trades: number
  win_rate: number
  avg_pnl_pct: number
}

interface BestCombination {
  strategy_name: string
  vix_regime: string
  pattern_type: string
  dte_bucket: string
  moneyness: string
  total_trades: number
  win_rate: number
}

interface LiveRecommendation {
  recommended_strategy: string
  strikes: {
    short_call?: number
    long_call?: number
    short_put?: number
    long_put?: number
  }
  optimal_dte: number
  expected_win_rate: number
  confidence: number
  reasoning: string
}

export default function StrategyOptimizer() {
  const [loading, setLoading] = useState(true)
  const [selectedStrategy, setSelectedStrategy] = useState<string>('all')

  // Data states
  const [strikePerformance, setStrikePerformance] = useState<StrikePerformanceData[]>([])
  const [dtePerformance, setDTEPerformance] = useState<DTEPerformanceData[]>([])
  const [regimePerformance, setRegimePerformance] = useState<RegimePerformanceData[]>([])
  const [greeksPerformance, setGreeksPerformance] = useState<GreeksPerformanceData[]>([])
  const [bestCombinations, setBestCombinations] = useState<BestCombination[]>([])
  const [liveRecommendations, setLiveRecommendations] = useState<LiveRecommendation | null>(null)

  // Current market data for live recommendations
  const [currentSpot, setCurrentSpot] = useState<number>(580.50)
  const [currentVIX, setCurrentVIX] = useState<number>(18.5)
  const [currentPattern, setCurrentPattern] = useState<string>('LIBERATION')

  // Fetch all optimizer data
  useEffect(() => {
    const fetchOptimizerData = async () => {
      try {
        setLoading(true)

        // Fetch all data in parallel using apiClient
        const strategyParam = selectedStrategy === 'all' ? undefined : selectedStrategy
        const results = await Promise.allSettled([
          apiClient.getStrikePerformance(strategyParam),
          apiClient.getDTEPerformance(strategyParam),
          apiClient.getRegimePerformance(strategyParam),
          apiClient.getGreeksPerformance(strategyParam),
          apiClient.getBestCombinations(strategyParam),
        ])

        // Extract successful results
        const [strikeRes, dteRes, regimeRes, greeksRes, combosRes] = results.map(result =>
          result.status === 'fulfilled' ? result.value : { data: { success: false, data: [] } }
        )

        if (strikeRes.data.success && strikeRes.data.strike_performance) {
          setStrikePerformance(strikeRes.data.strike_performance)
        }

        if (dteRes.data.success && dteRes.data.dte_performance) {
          setDTEPerformance(dteRes.data.dte_performance)
        }

        if (regimeRes.data.success && regimeRes.data.regime_performance) {
          setRegimePerformance(regimeRes.data.regime_performance)
        }

        if (greeksRes.data.success && greeksRes.data.greeks_performance) {
          setGreeksPerformance(greeksRes.data.greeks_performance)
        }

        if (combosRes.data.success && combosRes.data.combinations) {
          setBestCombinations(combosRes.data.combinations)
        }
      } catch (error) {
        logger.error('Error fetching optimizer data:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchOptimizerData()
  }, [selectedStrategy])

  // Fetch live recommendations
  const fetchLiveRecommendations = async () => {
    try {
      const response = await apiClient.getLiveStrikeRecommendations({
        spot_price: currentSpot,
        vix_current: currentVIX,
        pattern_type: currentPattern
      })

      if (response.data.success && response.data.recommendations) {
        setLiveRecommendations(response.data.recommendations)
      }
    } catch (error) {
      logger.error('Error fetching live recommendations:', error)
    }
  }

  const formatPercentage = (value: number) => {
    return `${value.toFixed(1)}%`
  }

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(value)
  }

  // Get top performers for summary cards
  const bestStrikeByWinRate = strikePerformance.length > 0
    ? strikePerformance.reduce((prev, current) => (prev.win_rate > current.win_rate) ? prev : current)
    : null

  const bestDTEByWinRate = dtePerformance.length > 0
    ? dtePerformance.reduce((prev, current) => (prev.win_rate > current.win_rate) ? prev : current)
    : null

  const bestRegime = regimePerformance.length > 0
    ? regimePerformance.reduce((prev, current) => (prev.win_rate > current.win_rate) ? prev : current)
    : null

  return (
    <div className="min-h-screen">
      <Navigation />
      <main className="pt-16 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-3xl font-bold text-text-primary">Strategy Optimizer</h1>
                <p className="text-text-secondary mt-1">Strike-level intelligence and performance optimization</p>
              </div>
              <div className="flex items-center gap-3">
                <select
                  value={selectedStrategy}
                  onChange={(e) => setSelectedStrategy(e.target.value)}
                  className="px-4 py-2 bg-background-hover border border-border rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="all">All Strategies</option>
                  <option value="iron_condor">Iron Condor</option>
                  <option value="vertical_call">Vertical Call Spread</option>
                  <option value="vertical_put">Vertical Put Spread</option>
                  <option value="long_straddle">Long Straddle</option>
                  <option value="short_straddle">Short Straddle</option>
                </select>
              </div>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="card">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-text-secondary text-sm">Best Strike Performance</p>
                    {bestStrikeByWinRate ? (
                      <>
                        <p className="text-2xl font-bold text-success mt-1">
                          {formatPercentage(bestStrikeByWinRate.win_rate)}
                        </p>
                        <p className="text-text-secondary text-sm mt-1">
                          {bestStrikeByWinRate.moneyness} • {bestStrikeByWinRate.strike_distance}% {bestStrikeByWinRate.vix_regime} VIX
                        </p>
                      </>
                    ) : (
                      <p className="text-text-muted mt-1">No data yet</p>
                    )}
                  </div>
                  <Target className="text-primary w-8 h-8" />
                </div>
              </div>

              <div className="card">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-text-secondary text-sm">Optimal DTE</p>
                    {bestDTEByWinRate ? (
                      <>
                        <p className="text-2xl font-bold text-success mt-1">
                          {bestDTEByWinRate.dte_bucket}
                        </p>
                        <p className="text-text-secondary text-sm mt-1">
                          {formatPercentage(bestDTEByWinRate.win_rate)} win rate • {bestDTEByWinRate.total_trades} trades
                        </p>
                      </>
                    ) : (
                      <p className="text-text-muted mt-1">No data yet</p>
                    )}
                  </div>
                  <Activity className="text-primary w-8 h-8" />
                </div>
              </div>

              <div className="card">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-text-secondary text-sm">Best Market Regime</p>
                    {bestRegime ? (
                      <>
                        <p className="text-2xl font-bold text-success mt-1">
                          {bestRegime.vix_regime.toUpperCase()}
                        </p>
                        <p className="text-text-secondary text-sm mt-1">
                          {formatPercentage(bestRegime.win_rate)} win rate • VIX {bestRegime.vix_regime}
                        </p>
                      </>
                    ) : (
                      <p className="text-text-muted mt-1">No data yet</p>
                    )}
                  </div>
                  <TrendingUp className="text-primary w-8 h-8" />
                </div>
              </div>
            </div>

            {/* Live Strike Recommendations Panel */}
            <div className="card bg-gradient-to-r from-primary/10 to-primary/5 border-2 border-primary/30">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold text-text-primary flex items-center gap-2">
                  <Zap className="text-primary w-6 h-6 animate-pulse" />
                  Live Strike Recommendations
                </h2>
                <button
                  onClick={fetchLiveRecommendations}
                  className="btn bg-primary text-white hover:bg-primary/90"
                >
                  Get AI Recommendation
                </button>
              </div>

              {/* Input Parameters */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                <div>
                  <label className="block text-text-secondary text-sm mb-2">Current Spot Price</label>
                  <input
                    type="number"
                    value={currentSpot}
                    onChange={(e) => setCurrentSpot(parseFloat(e.target.value))}
                    className="w-full px-4 py-2 bg-background-hover border border-border rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="block text-text-secondary text-sm mb-2">Current VIX</label>
                  <input
                    type="number"
                    value={currentVIX}
                    onChange={(e) => setCurrentVIX(parseFloat(e.target.value))}
                    className="w-full px-4 py-2 bg-background-hover border border-border rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="block text-text-secondary text-sm mb-2">Pattern Detected</label>
                  <select
                    value={currentPattern}
                    onChange={(e) => setCurrentPattern(e.target.value)}
                    className="w-full px-4 py-2 bg-background-hover border border-border rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <option value="LIBERATION">Liberation</option>
                    <option value="FALSE_FLOOR">False Floor</option>
                    <option value="BEAR_FLAG">Bear Flag</option>
                    <option value="BULL_TRAP">Bull Trap</option>
                    <option value="NONE">None</option>
                  </select>
                </div>
              </div>

              {/* Live Recommendations Display */}
              {liveRecommendations && (
                <div className="space-y-4">
                  <div className="p-6 bg-background-primary rounded-lg border border-success/30">
                    <div className="flex items-start gap-4 mb-4">
                      <Brain className="w-8 h-8 text-success flex-shrink-0" />
                      <div className="flex-1">
                        <h3 className="text-lg font-bold text-success mb-2">
                          Recommended: {liveRecommendations.recommended_strategy.replace('_', ' ').toUpperCase()}
                        </h3>
                        <p className="text-text-secondary mb-4">{liveRecommendations.reasoning}</p>

                        {/* Strike Details */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                          {liveRecommendations.strikes.short_call && (
                            <div className="p-3 bg-background-hover rounded-lg">
                              <p className="text-xs text-text-secondary mb-1">Short Call</p>
                              <p className="text-lg font-bold text-danger">{formatCurrency(liveRecommendations.strikes.short_call)}</p>
                            </div>
                          )}
                          {liveRecommendations.strikes.long_call && (
                            <div className="p-3 bg-background-hover rounded-lg">
                              <p className="text-xs text-text-secondary mb-1">Long Call</p>
                              <p className="text-lg font-bold text-success">{formatCurrency(liveRecommendations.strikes.long_call)}</p>
                            </div>
                          )}
                          {liveRecommendations.strikes.short_put && (
                            <div className="p-3 bg-background-hover rounded-lg">
                              <p className="text-xs text-text-secondary mb-1">Short Put</p>
                              <p className="text-lg font-bold text-danger">{formatCurrency(liveRecommendations.strikes.short_put)}</p>
                            </div>
                          )}
                          {liveRecommendations.strikes.long_put && (
                            <div className="p-3 bg-background-hover rounded-lg">
                              <p className="text-xs text-text-secondary mb-1">Long Put</p>
                              <p className="text-lg font-bold text-success">{formatCurrency(liveRecommendations.strikes.long_put)}</p>
                            </div>
                          )}
                        </div>

                        {/* Performance Metrics */}
                        <div className="grid grid-cols-3 gap-3">
                          <div className="p-3 bg-background-hover rounded-lg">
                            <p className="text-xs text-text-secondary mb-1">Optimal DTE</p>
                            <p className="text-lg font-bold text-text-primary">{liveRecommendations.optimal_dte} days</p>
                          </div>
                          <div className="p-3 bg-background-hover rounded-lg">
                            <p className="text-xs text-text-secondary mb-1">Expected Win Rate</p>
                            <p className="text-lg font-bold text-success">{formatPercentage(liveRecommendations.expected_win_rate)}</p>
                          </div>
                          <div className="p-3 bg-background-hover rounded-lg">
                            <p className="text-xs text-text-secondary mb-1">AI Confidence</p>
                            <p className="text-lg font-bold text-primary">{liveRecommendations.confidence}%</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Strike Performance Analysis */}
            <div className="card">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold text-text-primary flex items-center gap-2">
                  <Target className="text-primary w-6 h-6" />
                  Strike Performance Analysis
                </h2>
                <span className="text-sm text-text-secondary">{strikePerformance.length} data points</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-3 px-4 text-text-secondary font-medium">Strategy</th>
                      <th className="text-left py-3 px-4 text-text-secondary font-medium">Moneyness</th>
                      <th className="text-right py-3 px-4 text-text-secondary font-medium">Distance %</th>
                      <th className="text-right py-3 px-4 text-text-secondary font-medium">VIX Regime</th>
                      <th className="text-right py-3 px-4 text-text-secondary font-medium">Trades</th>
                      <th className="text-right py-3 px-4 text-text-secondary font-medium">Win Rate</th>
                      <th className="text-right py-3 px-4 text-text-secondary font-medium">Avg P&L %</th>
                      <th className="text-right py-3 px-4 text-text-secondary font-medium">Avg Delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {strikePerformance.length > 0 ? (
                      strikePerformance.slice(0, 15).map((strike, idx) => (
                        <tr key={idx} className="border-b border-border/50 hover:bg-background-hover transition-colors">
                          <td className="py-3 px-4 text-text-primary font-semibold">{strike.strategy_name}</td>
                          <td className="py-3 px-4">
                            <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                              strike.moneyness === 'ATM' ? 'bg-primary/20 text-primary' :
                              strike.moneyness === 'OTM' ? 'bg-warning/20 text-warning' :
                              'bg-success/20 text-success'
                            }`}>
                              {strike.moneyness}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right text-text-primary">{strike.strike_distance.toFixed(1)}%</td>
                          <td className="py-3 px-4 text-right">
                            <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                              strike.vix_regime === 'low' ? 'bg-success/20 text-success' :
                              strike.vix_regime === 'normal' ? 'bg-primary/20 text-primary' :
                              'bg-danger/20 text-danger'
                            }`}>
                              {strike.vix_regime.toUpperCase()}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right text-text-primary">{strike.total_trades}</td>
                          <td className="py-3 px-4 text-right">
                            <span className={`font-bold ${
                              strike.win_rate >= 60 ? 'text-success' :
                              strike.win_rate >= 50 ? 'text-warning' :
                              'text-danger'
                            }`}>
                              {formatPercentage(strike.win_rate)}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right">
                            <span className={`font-semibold ${
                              strike.avg_pnl_pct >= 0 ? 'text-success' : 'text-danger'
                            }`}>
                              {strike.avg_pnl_pct >= 0 ? '+' : ''}{formatPercentage(strike.avg_pnl_pct)}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right text-text-primary">{strike.avg_delta.toFixed(2)}</td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={8} className="py-8 text-center text-text-secondary">
                          No strike performance data yet. Data will appear as trades execute.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* DTE Optimization Display */}
            <div className="card">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold text-text-primary flex items-center gap-2">
                  <Activity className="text-primary w-6 h-6" />
                  DTE Optimization
                </h2>
                <span className="text-sm text-text-secondary">{dtePerformance.length} buckets analyzed</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {dtePerformance.length > 0 ? (
                  dtePerformance.map((dte, idx) => (
                    <div key={idx} className="p-6 bg-background-hover rounded-lg border border-border hover:border-primary/50 transition-colors">
                      <div className="flex items-center justify-between mb-4">
                        <h3 className="text-lg font-bold text-text-primary">{dte.dte_bucket} DTE</h3>
                        <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                          dte.win_rate >= 60 ? 'bg-success/20 text-success' :
                          dte.win_rate >= 50 ? 'bg-warning/20 text-warning' :
                          'bg-danger/20 text-danger'
                        }`}>
                          {formatPercentage(dte.win_rate)}
                        </span>
                      </div>
                      <div className="space-y-2">
                        <div className="flex justify-between">
                          <span className="text-text-secondary text-sm">Total Trades</span>
                          <span className="text-text-primary font-semibold">{dte.total_trades}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-text-secondary text-sm">Avg P&L</span>
                          <span className={`font-semibold ${dte.avg_pnl_pct >= 0 ? 'text-success' : 'text-danger'}`}>
                            {dte.avg_pnl_pct >= 0 ? '+' : ''}{formatPercentage(dte.avg_pnl_pct)}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-text-secondary text-sm">Avg Hold Time</span>
                          <span className="text-text-primary font-semibold">{dte.avg_holding_hours.toFixed(1)}h</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-text-secondary text-sm">Theta Efficiency</span>
                          <span className="text-primary font-semibold">{dte.theta_decay_efficiency.toFixed(2)}</span>
                        </div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="col-span-3 text-center py-8 text-text-secondary">
                    No DTE performance data yet. Data will appear as trades execute.
                  </div>
                )}
              </div>
            </div>

            {/* Regime-Specific Recommendations */}
            <div className="card">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold text-text-primary flex items-center gap-2">
                  <BarChart3 className="text-primary w-6 h-6" />
                  Regime-Specific Performance
                </h2>
                <span className="text-sm text-text-secondary">VIX-based optimization</span>
              </div>

              <div className="space-y-4">
                {regimePerformance.length > 0 ? (
                  regimePerformance.map((regime, idx) => (
                    <div key={idx} className="p-6 bg-background-hover rounded-lg border border-border">
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                          <div className={`w-3 h-3 rounded-full ${
                            regime.vix_regime === 'low' ? 'bg-success' :
                            regime.vix_regime === 'normal' ? 'bg-primary' :
                            'bg-danger'
                          }`} />
                          <h3 className="text-lg font-bold text-text-primary">
                            VIX {regime.vix_regime.toUpperCase()} Regime
                          </h3>
                        </div>
                        <span className={`font-bold text-lg ${
                          regime.win_rate >= 60 ? 'text-success' :
                          regime.win_rate >= 50 ? 'text-warning' :
                          'text-danger'
                        }`}>
                          {formatPercentage(regime.win_rate)} Win Rate
                        </span>
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                        <div>
                          <p className="text-text-secondary text-sm mb-1">Strategy</p>
                          <p className="text-text-primary font-semibold">{regime.strategy_name}</p>
                        </div>
                        <div>
                          <p className="text-text-secondary text-sm mb-1">Total Trades</p>
                          <p className="text-text-primary font-semibold">{regime.total_trades}</p>
                        </div>
                        <div>
                          <p className="text-text-secondary text-sm mb-1">Avg P&L</p>
                          <p className={`font-semibold ${regime.avg_pnl_pct >= 0 ? 'text-success' : 'text-danger'}`}>
                            {regime.avg_pnl_pct >= 0 ? '+' : ''}{formatPercentage(regime.avg_pnl_pct)}
                          </p>
                        </div>
                        <div>
                          <p className="text-text-secondary text-sm mb-1">Best Moneyness</p>
                          <p className="text-primary font-semibold">{regime.best_moneyness}</p>
                        </div>
                        <div>
                          <p className="text-text-secondary text-sm mb-1">Best DTE</p>
                          <p className="text-primary font-semibold">{regime.best_dte_bucket}</p>
                        </div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-center py-8 text-text-secondary">
                    No regime performance data yet. Data will appear as trades execute.
                  </div>
                )}
              </div>
            </div>

            {/* Best Combinations - High Probability Setups */}
            <div className="card">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold text-text-primary flex items-center gap-2">
                  <Trophy className="text-warning w-6 h-6" />
                  Best Combinations - High Probability Setups
                </h2>
                <span className="text-sm text-text-secondary">{bestCombinations.length} winning combinations</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-3 px-4 text-text-secondary font-medium">Rank</th>
                      <th className="text-left py-3 px-4 text-text-secondary font-medium">Strategy</th>
                      <th className="text-left py-3 px-4 text-text-secondary font-medium">VIX</th>
                      <th className="text-left py-3 px-4 text-text-secondary font-medium">Pattern</th>
                      <th className="text-left py-3 px-4 text-text-secondary font-medium">DTE</th>
                      <th className="text-left py-3 px-4 text-text-secondary font-medium">Moneyness</th>
                      <th className="text-right py-3 px-4 text-text-secondary font-medium">Trades</th>
                      <th className="text-right py-3 px-4 text-text-secondary font-medium">Win Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bestCombinations.length > 0 ? (
                      bestCombinations.map((combo, idx) => {
                        const rankEmoji = idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : (idx + 1).toString()
                        return (
                          <tr key={idx} className={`border-b border-border/50 hover:bg-background-hover transition-colors ${idx === 0 ? 'bg-warning/5' : ''}`}>
                            <td className={`py-3 px-4 font-bold ${idx === 0 ? 'text-warning' : 'text-text-secondary'}`}>
                              {rankEmoji} {idx + 1}
                            </td>
                            <td className="py-3 px-4 text-text-primary font-semibold">{combo.strategy_name}</td>
                            <td className="py-3 px-4">
                              <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                                combo.vix_regime === 'low' ? 'bg-success/20 text-success' :
                                combo.vix_regime === 'normal' ? 'bg-primary/20 text-primary' :
                                'bg-danger/20 text-danger'
                              }`}>
                                {combo.vix_regime.toUpperCase()}
                              </span>
                            </td>
                            <td className="py-3 px-4 text-text-primary">{combo.pattern_type}</td>
                            <td className="py-3 px-4 text-text-primary">{combo.dte_bucket}</td>
                            <td className="py-3 px-4">
                              <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                                combo.moneyness === 'ATM' ? 'bg-primary/20 text-primary' :
                                combo.moneyness === 'OTM' ? 'bg-warning/20 text-warning' :
                                'bg-success/20 text-success'
                              }`}>
                                {combo.moneyness}
                              </span>
                            </td>
                            <td className="py-3 px-4 text-right text-text-primary">{combo.total_trades}</td>
                            <td className="py-3 px-4 text-right">
                              <span className="font-bold text-success text-lg">
                                {formatPercentage(combo.win_rate)}
                              </span>
                            </td>
                          </tr>
                        )
                      })
                    ) : (
                      <tr>
                        <td colSpan={8} className="py-8 text-center text-text-secondary">
                          No combination data yet. Data will appear as trades with multiple conditions execute.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Greeks Performance Analysis */}
            <div className="card">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold text-text-primary flex items-center gap-2">
                  <PieChart className="text-primary w-6 h-6" />
                  Greeks Performance Analysis
                </h2>
                <span className="text-sm text-text-secondary">Delta, Gamma, Theta, Vega efficiency</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-3 px-4 text-text-secondary font-medium">Strategy</th>
                      <th className="text-right py-3 px-4 text-text-secondary font-medium">Avg Delta</th>
                      <th className="text-right py-3 px-4 text-text-secondary font-medium">Avg Gamma</th>
                      <th className="text-right py-3 px-4 text-text-secondary font-medium">Avg Theta</th>
                      <th className="text-right py-3 px-4 text-text-secondary font-medium">Avg Vega</th>
                      <th className="text-right py-3 px-4 text-text-secondary font-medium">Trades</th>
                      <th className="text-right py-3 px-4 text-text-secondary font-medium">Win Rate</th>
                      <th className="text-right py-3 px-4 text-text-secondary font-medium">Avg P&L %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {greeksPerformance.length > 0 ? (
                      greeksPerformance.map((greek, idx) => (
                        <tr key={idx} className="border-b border-border/50 hover:bg-background-hover transition-colors">
                          <td className="py-3 px-4 text-text-primary font-semibold">{greek.strategy_name}</td>
                          <td className="py-3 px-4 text-right text-text-primary">{greek.avg_entry_delta.toFixed(3)}</td>
                          <td className="py-3 px-4 text-right text-text-primary">{greek.avg_entry_gamma.toFixed(3)}</td>
                          <td className="py-3 px-4 text-right text-text-primary">{greek.avg_entry_theta.toFixed(3)}</td>
                          <td className="py-3 px-4 text-right text-text-primary">{greek.avg_entry_vega.toFixed(3)}</td>
                          <td className="py-3 px-4 text-right text-text-primary">{greek.total_trades}</td>
                          <td className="py-3 px-4 text-right">
                            <span className={`font-bold ${
                              greek.win_rate >= 60 ? 'text-success' :
                              greek.win_rate >= 50 ? 'text-warning' :
                              'text-danger'
                            }`}>
                              {formatPercentage(greek.win_rate)}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right">
                            <span className={`font-semibold ${
                              greek.avg_pnl_pct >= 0 ? 'text-success' : 'text-danger'
                            }`}>
                              {greek.avg_pnl_pct >= 0 ? '+' : ''}{formatPercentage(greek.avg_pnl_pct)}
                            </span>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={8} className="py-8 text-center text-text-secondary">
                          No Greeks performance data yet. Data will appear as trades with Greeks tracking execute.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Info Banner */}
            <div className="p-4 rounded-lg bg-primary/10 border border-primary/30">
              <div className="flex items-start gap-3">
                <Brain className="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold text-primary mb-1">AI-Powered Strike Intelligence</p>
                  <p className="text-sm text-text-secondary">
                    This optimizer analyzes historical performance data at the strike level, providing actionable insights on which exact strikes, DTE ranges, and market conditions produce the highest win rates. All recommendations are backed by real backtest data and continuously updated as new trades execute.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
