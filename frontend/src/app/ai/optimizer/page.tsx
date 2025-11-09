'use client'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import LoadingWithTips from '@/components/LoadingWithTips'
import { Sparkles, TrendingUp, AlertCircle, CheckCircle, Loader2, BarChart3 } from 'lucide-react'

interface OptimizationResult {
  strategy_name: string
  current_performance: {
    win_rate: number
    expectancy: number
    total_trades: number
  }
  recommendations: Array<{
    priority: string
    change: string
    expected_impact: string
    reasoning: string
  }>
  verdict: string
  ai_analysis: string
}

export default function AIOptimizerPage() {
  const [selectedStrategy, setSelectedStrategy] = useState<string>('')
  const [availableStrategies, setAvailableStrategies] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingStrategies, setLoadingStrategies] = useState(true)
  const [result, setResult] = useState<OptimizationResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Load available strategies on mount
  useEffect(() => {
    const fetchStrategies = async () => {
      try {
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/backtests/results`)
        const data = await response.json()

        if (data.success) {
          const strategies = [...new Set((data.results || data.data || []).map((r: any) => r.strategy_name))]
          setAvailableStrategies(strategies as string[])
        }
      } catch (err) {
        console.error('Failed to fetch strategies:', err)
      } finally {
        setLoadingStrategies(false)
      }
    }

    fetchStrategies()
  }, [])

  const optimizeStrategy = async () => {
    if (!selectedStrategy) {
      setError('Please select a strategy')
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/ai/optimize-strategy`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          strategy_name: selectedStrategy,
        }),
      })

      const data = await response.json()

      if (data.success) {
        setResult(data.optimization || data.data)
      } else {
        setError(data.error || data.detail || 'Failed to optimize strategy')
      }
    } catch (err: any) {
      setError(err.message || 'Failed to connect to API')
    } finally {
      setLoading(false)
    }
  }

  const analyzeAllStrategies = async () => {
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/ai/analyze-all-strategies`
      )

      const data = await response.json()

      if (data.success) {
        setResult(data.analysis || data.data)
      } else {
        setError(data.error || data.detail || 'Failed to analyze strategies')
      }
    } catch (err: any) {
      setError(err.message || 'Failed to connect to API')
    } finally {
      setLoading(false)
    }
  }

  const getPriorityColor = (priority: string) => {
    switch (priority.toUpperCase()) {
      case 'CRITICAL':
        return 'bg-danger/20 text-danger border-danger'
      case 'HIGH':
        return 'bg-warning/20 text-warning border-warning'
      case 'MEDIUM':
        return 'bg-primary/20 text-primary border-primary'
      default:
        return 'bg-text-secondary/20 text-text-secondary border-text-secondary'
    }
  }

  return (
    <div className="min-h-screen">
      <Navigation />

      <main className="pt-16 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-text-primary flex items-center space-x-3">
              <Sparkles className="w-8 h-8 text-primary" />
              <span>AI Strategy Optimizer</span>
            </h1>
            <p className="text-text-secondary mt-2">
              Claude-powered analysis to improve strategy profitability
            </p>
          </div>

          {/* Input Section */}
          <div className="card mb-8">
            <h2 className="text-xl font-semibold text-text-primary mb-4">Configuration</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Strategy Name (optional)
                </label>
                {loadingStrategies ? (
                  <div className="flex items-center space-x-2 px-4 py-2 bg-background-deep border border-gray-700 rounded-lg">
                    <Loader2 className="w-4 h-4 animate-spin text-primary" />
                    <span className="text-text-muted">Loading strategies...</span>
                  </div>
                ) : availableStrategies.length > 0 ? (
                  <select
                    value={selectedStrategy}
                    onChange={(e) => setSelectedStrategy(e.target.value)}
                    className="w-full px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary focus:outline-none focus:border-primary"
                  >
                    <option value="">-- Select a strategy --</option>
                    {availableStrategies.map((strategy) => (
                      <option key={strategy} value={strategy}>
                        {strategy.replace(/_/g, ' ')}
                      </option>
                    ))}
                  </select>
                ) : (
                  <div className="px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-muted">
                    No strategies found. Run backtests first.
                  </div>
                )}
                <p className="text-xs text-text-muted mt-1">
                  Select a strategy to optimize, or use "Analyze All" button
                </p>
              </div>

              <div className="flex space-x-4">
                <button
                  onClick={optimizeStrategy}
                  disabled={loading || !selectedStrategy}
                  className="btn-primary flex items-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <Sparkles className="w-5 h-5" />
                  )}
                  <span>Optimize Strategy</span>
                </button>

                <button
                  onClick={analyzeAllStrategies}
                  disabled={loading}
                  className="btn-secondary flex items-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <BarChart3 className="w-5 h-5" />
                  )}
                  <span>Analyze All</span>
                </button>
              </div>

              <p className="text-xs text-text-muted">
                Using Anthropic Claude API from backend environment configuration
              </p>
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div className="bg-danger/10 border border-danger rounded-lg p-4 mb-8">
              <div className="flex items-center space-x-2 text-danger">
                <AlertCircle className="w-5 h-5" />
                <span className="font-semibold">{error}</span>
              </div>
            </div>
          )}

          {/* Loading State */}
          {loading && (
            <LoadingWithTips
              message={selectedStrategy ? `AI analyzing ${selectedStrategy.replace(/_/g, ' ')}...` : "AI analyzing all strategies..."}
              showProgress={false}
            />
          )}

          {/* Results */}
          {result && !loading && (
            <div className="space-y-6">
              {/* Performance Overview */}
              <div className="card">
                <h2 className="text-xl font-semibold text-text-primary mb-4 flex items-center space-x-2">
                  <BarChart3 className="w-6 h-6 text-primary" />
                  <span>Current Performance</span>
                </h2>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="bg-background-deep rounded-lg p-4">
                    <p className="text-text-secondary text-sm mb-1">Win Rate</p>
                    <p className="text-2xl font-bold text-text-primary">
                      {result.current_performance.win_rate.toFixed(1)}%
                    </p>
                  </div>

                  <div className="bg-background-deep rounded-lg p-4">
                    <p className="text-text-secondary text-sm mb-1">Expectancy</p>
                    <p className={`text-2xl font-bold ${
                      result.current_performance.expectancy >= 0.5
                        ? 'text-success'
                        : 'text-warning'
                    }`}>
                      {result.current_performance.expectancy.toFixed(2)}%
                    </p>
                  </div>

                  <div className="bg-background-deep rounded-lg p-4">
                    <p className="text-text-secondary text-sm mb-1">Total Trades</p>
                    <p className="text-2xl font-bold text-text-primary">
                      {result.current_performance.total_trades}
                    </p>
                  </div>
                </div>
              </div>

              {/* AI Analysis */}
              <div className="card">
                <h2 className="text-xl font-semibold text-text-primary mb-4 flex items-center space-x-2">
                  <Sparkles className="w-6 h-6 text-primary" />
                  <span>AI Analysis</span>
                </h2>

                <div className="bg-background-deep rounded-lg p-4 mb-4">
                  <p className="text-text-primary whitespace-pre-wrap">{result.ai_analysis}</p>
                </div>

                <div className={`px-4 py-3 rounded-lg font-semibold ${
                  result.verdict.includes('IMPLEMENT')
                    ? 'bg-success/20 text-success'
                    : result.verdict.includes('OPTIMIZE')
                    ? 'bg-warning/20 text-warning'
                    : 'bg-danger/20 text-danger'
                }`}>
                  {result.verdict}
                </div>
              </div>

              {/* Recommendations */}
              {result.recommendations && result.recommendations.length > 0 && (
                <div className="card">
                  <h2 className="text-xl font-semibold text-text-primary mb-4 flex items-center space-x-2">
                    <CheckCircle className="w-6 h-6 text-success" />
                    <span>Optimization Recommendations</span>
                  </h2>

                  <div className="space-y-4">
                    {result.recommendations.map((rec, idx) => (
                      <div
                        key={idx}
                        className="border border-gray-700 rounded-lg p-4 hover:border-primary transition-colors"
                      >
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex-1">
                            <div className="flex items-center space-x-2 mb-2">
                              <span
                                className={`px-2 py-1 rounded text-xs font-semibold border ${getPriorityColor(
                                  rec.priority
                                )}`}
                              >
                                {rec.priority}
                              </span>
                            </div>
                            <p className="text-text-primary font-semibold mb-2">{rec.change}</p>
                            <p className="text-text-secondary text-sm mb-2">{rec.reasoning}</p>
                            <p className="text-success text-sm font-semibold">
                              Expected Impact: {rec.expected_impact}
                            </p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Info Box */}
          {!result && !loading && (
            <div className="card bg-primary/5 border border-primary/20">
              <div className="flex items-start space-x-3">
                <AlertCircle className="w-6 h-6 text-primary flex-shrink-0 mt-1" />
                <div>
                  <h3 className="text-lg font-semibold text-text-primary mb-2">How It Works</h3>
                  <ul className="space-y-2 text-text-secondary">
                    <li className="flex items-start space-x-2">
                      <span className="text-primary">•</span>
                      <span>
                        AI analyzes backtest results to identify what's working and what's not
                      </span>
                    </li>
                    <li className="flex items-start space-x-2">
                      <span className="text-primary">•</span>
                      <span>
                        Provides specific parameter changes with expected profitability improvements
                      </span>
                    </li>
                    <li className="flex items-start space-x-2">
                      <span className="text-primary">•</span>
                      <span>
                        Ranks strategies by expectancy (most critical metric for profitability)
                      </span>
                    </li>
                    <li className="flex items-start space-x-2">
                      <span className="text-primary">•</span>
                      <span>
                        Powered by Anthropic Claude - configured in backend environment
                      </span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
