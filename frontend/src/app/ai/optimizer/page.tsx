'use client'

import { useState } from 'react'
import Navigation from '@/components/Navigation'
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
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<OptimizationResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [apiKey, setApiKey] = useState<string>('')

  const optimizeStrategy = async () => {
    if (!selectedStrategy || !apiKey) {
      setError('Please enter both strategy name and API key')
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
          api_key: apiKey,
        }),
      })

      const data = await response.json()

      if (data.success) {
        setResult(data.data)
      } else {
        setError(data.error || 'Failed to optimize strategy')
      }
    } catch (err) {
      setError('Failed to connect to API')
    } finally {
      setLoading(false)
    }
  }

  const analyzeAllStrategies = async () => {
    if (!apiKey) {
      setError('Please enter your Anthropic API key')
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/ai/analyze-all-strategies?api_key=${apiKey}`
      )

      const data = await response.json()

      if (data.success) {
        setResult(data.data)
      } else {
        setError(data.error || 'Failed to analyze strategies')
      }
    } catch (err) {
      setError('Failed to connect to API')
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
                  Anthropic API Key
                </label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="sk-ant-..."
                  className="w-full px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary focus:outline-none focus:border-primary"
                />
                <p className="text-xs text-text-muted mt-1">
                  Get your API key from{' '}
                  <a
                    href="https://console.anthropic.com/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline"
                  >
                    console.anthropic.com
                  </a>
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Strategy Name (optional)
                </label>
                <input
                  type="text"
                  value={selectedStrategy}
                  onChange={(e) => setSelectedStrategy(e.target.value)}
                  placeholder="GAMMA_SQUEEZE_CASCADE"
                  className="w-full px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary focus:outline-none focus:border-primary"
                />
                <p className="text-xs text-text-muted mt-1">
                  Leave blank to analyze all strategies
                </p>
              </div>

              <div className="flex space-x-4">
                <button
                  onClick={optimizeStrategy}
                  disabled={loading || !apiKey || !selectedStrategy}
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
                  disabled={loading || !apiKey}
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

          {/* Results */}
          {result && (
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
                        Cost: ~$0.01-0.05 per analysis. Monthly: $5-20 for typical usage.
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
