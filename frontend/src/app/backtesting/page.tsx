'use client'

import { useState, useEffect } from 'react'
import { TestTube, TrendingUp, TrendingDown, Activity, BarChart3, PlayCircle, RefreshCw, AlertTriangle, Calendar, Clock } from 'lucide-react'
import Navigation from '@/components/Navigation'
import SmartStrategyPicker from '@/components/SmartStrategyPicker'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface BacktestResult {
  id: number
  timestamp: string
  strategy_name: string
  symbol: string
  start_date: string
  end_date: string
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  avg_win_pct: number
  avg_loss_pct: number
  largest_win_pct: number
  largest_loss_pct: number
  expectancy_pct: number
  total_return_pct: number
  max_drawdown_pct: number
  sharpe_ratio: number
  avg_trade_duration_days: number
}

export default function BacktestingPage() {
  const [results, setResults] = useState<BacktestResult[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  // Filter states
  const [minExpectancy, setMinExpectancy] = useState<number>(0)
  const [showFilters, setShowFilters] = useState(false)

  useEffect(() => {
    fetchResults()
  }, [])

  const fetchResults = async () => {
    try {
      setLoading(true)
      setError(null)

      const response = await fetch(`${API_URL}/api/backtests/results`)

      if (response.ok) {
        const data = await response.json()
        setResults(data.results || [])
      } else {
        setError('Failed to load backtest results')
      }
    } catch (err) {
      console.error('Failed to fetch backtest results:', err)
      setError('Failed to connect to API')
    } finally {
      setLoading(false)
    }
  }

  const runBacktests = async () => {
    setRunning(true)
    setRunError(null)

    try {
      const response = await fetch(`${API_URL}/api/backtests/run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          symbol: 'SPY',
          start_date: '2023-01-01',
          end_date: new Date().toISOString().split('T')[0]
        }),
      })

      const data = await response.json()

      if (response.ok) {
        await fetchResults()
      } else {
        setRunError(data.error || data.message || 'Failed to run backtests')
      }
    } catch (err) {
      console.error('Failed to run backtests:', err)
      setRunError('Failed to connect to API')
    } finally {
      setRunning(false)
    }
  }

  // Filter results
  const filteredResults = results.filter(r => r.expectancy_pct >= minExpectancy)

  // Calculate summary stats
  const summary = {
    total: results.length,
    profitable: results.filter(r => r.expectancy_pct > 0.5).length,
    marginal: results.filter(r => r.expectancy_pct >= 0 && r.expectancy_pct <= 0.5).length,
    unprofitable: results.filter(r => r.expectancy_pct < 0).length,
    bestStrategy: results.length > 0 ? results.reduce((best, r) => r.expectancy_pct > best.expectancy_pct ? r : best) : null,
    worstStrategy: results.length > 0 ? results.reduce((worst, r) => r.expectancy_pct < worst.expectancy_pct ? r : worst) : null,
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 text-white">
        <Navigation />
        <main className="pt-16">
          <div className="container mx-auto px-4 py-8">
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin rounded-full h-12 w-12 border-4 border-purple-500 border-t-transparent" />
            </div>
          </div>
        </main>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-950 text-white">
        <Navigation />
        <main className="pt-16">
          <div className="container mx-auto px-4 py-8">
            <div className="bg-red-500/10 border border-red-500 rounded-lg p-6 text-red-400">
              {error}
            </div>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <Navigation />

      <main className="pt-16">
        <div className="container mx-auto px-4 py-8 space-y-6">

          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold flex items-center gap-3">
                <TestTube className="w-8 h-8 text-purple-400" />
                Strategy Backtesting
              </h1>
              <p className="text-gray-400 mt-1">
                Performance analysis of 29+ trading strategies with realistic transaction costs
              </p>
            </div>
            <button
              onClick={runBacktests}
              disabled={running}
              className="px-6 py-3 bg-purple-600 hover:bg-purple-700 rounded-lg font-semibold disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {running ? (
                <>
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Running Backtests...
                </>
              ) : (
                <>
                  <PlayCircle className="w-5 h-5" />
                  Run Backtests
                </>
              )}
            </button>
          </div>

          {/* Run Error */}
          {runError && (
            <div className="bg-red-500/10 border border-red-500 rounded-lg p-4 flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0" />
              <div className="text-red-400">{runError}</div>
            </div>
          )}

          {/* Running State */}
          {running && (
            <div className="bg-purple-500/10 border border-purple-500 rounded-lg p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-5 h-5 border-2 border-purple-400 border-t-transparent rounded-full animate-spin" />
                <div className="text-lg font-semibold text-purple-400">Running Comprehensive Backtests...</div>
              </div>
              <p className="text-gray-300 text-sm">
                Testing 29+ strategies across Psychology (13), GEX (5), and Options (11) with historical data.
                This may take 2-5 minutes depending on date range.
              </p>
            </div>
          )}

          {/* Smart Strategy Picker - Only show if we have backtest results */}
          {results.length > 0 && !running && (
            <SmartStrategyPicker />
          )}

          {/* Empty State */}
          {results.length === 0 && (
            <div className="bg-gray-900 border-2 border-dashed border-gray-700 rounded-xl p-12 text-center">
              <TestTube className="w-20 h-20 mx-auto mb-6 text-gray-600" />
              <h2 className="text-3xl font-bold mb-4">No Backtest Results Yet</h2>
              <p className="text-gray-400 text-lg mb-8 max-w-2xl mx-auto">
                Click &quot;Run Backtests&quot; above to analyze all 29+ trading strategies with historical data.
                The system will automatically test Psychology Traps, GEX Strategies, and Options Strategies.
              </p>
              <div className="bg-gray-950/50 rounded-lg p-6 max-w-xl mx-auto">
                <h3 className="font-bold mb-3">What gets tested:</h3>
                <div className="grid grid-cols-3 gap-4 text-sm">
                  <div className="bg-purple-500/10 rounded p-3">
                    <div className="text-purple-400 font-bold">13</div>
                    <div className="text-gray-400">Psychology Patterns</div>
                  </div>
                  <div className="bg-blue-500/10 rounded p-3">
                    <div className="text-blue-400 font-bold">5</div>
                    <div className="text-gray-400">GEX Strategies</div>
                  </div>
                  <div className="bg-green-500/10 rounded p-3">
                    <div className="text-green-400 font-bold">11</div>
                    <div className="text-gray-400">Options Strategies</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Has Results */}
          {results.length > 0 && (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-sm text-gray-400">Total Strategies</div>
                    <BarChart3 className="w-5 h-5 text-gray-400" />
                  </div>
                  <div className="text-3xl font-bold">{summary.total}</div>
                </div>

                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-sm text-gray-400">Profitable</div>
                    <TrendingUp className="w-5 h-5 text-green-400" />
                  </div>
                  <div className="text-3xl font-bold text-green-400">{summary.profitable}</div>
                  <div className="text-xs text-gray-500 mt-1">Expectancy &gt; 0.5%</div>
                </div>

                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-sm text-gray-400">Marginal</div>
                    <Activity className="w-5 h-5 text-yellow-400" />
                  </div>
                  <div className="text-3xl font-bold text-yellow-400">{summary.marginal}</div>
                  <div className="text-xs text-gray-500 mt-1">0% - 0.5%</div>
                </div>

                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-sm text-gray-400">Unprofitable</div>
                    <TrendingDown className="w-5 h-5 text-red-400" />
                  </div>
                  <div className="text-3xl font-bold text-red-400">{summary.unprofitable}</div>
                  <div className="text-xs text-gray-500 mt-1">Expectancy &lt; 0%</div>
                </div>
              </div>

              {/* Best/Worst Strategies */}
              {summary.bestStrategy && summary.worstStrategy && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="bg-gradient-to-br from-green-900/20 to-emerald-900/10 border border-green-500/30 rounded-lg p-6">
                    <h3 className="text-lg font-bold text-green-400 mb-3">🏆 Best Performing Strategy</h3>
                    <div className="font-bold text-xl mb-2">{summary.bestStrategy.strategy_name.replace(/_/g, ' ')}</div>
                    <div className="grid grid-cols-3 gap-3 text-sm">
                      <div>
                        <div className="text-gray-400">Win Rate</div>
                        <div className="font-bold text-green-400">{summary.bestStrategy.win_rate.toFixed(1)}%</div>
                      </div>
                      <div>
                        <div className="text-gray-400">Expectancy</div>
                        <div className="font-bold text-green-400">{summary.bestStrategy.expectancy_pct.toFixed(2)}%</div>
                      </div>
                      <div>
                        <div className="text-gray-400">Trades</div>
                        <div className="font-bold">{summary.bestStrategy.total_trades}</div>
                      </div>
                    </div>
                  </div>

                  <div className="bg-gradient-to-br from-red-900/20 to-orange-900/10 border border-red-500/30 rounded-lg p-6">
                    <h3 className="text-lg font-bold text-red-400 mb-3">⚠️ Worst Performing Strategy</h3>
                    <div className="font-bold text-xl mb-2">{summary.worstStrategy.strategy_name.replace(/_/g, ' ')}</div>
                    <div className="grid grid-cols-3 gap-3 text-sm">
                      <div>
                        <div className="text-gray-400">Win Rate</div>
                        <div className="font-bold text-red-400">{summary.worstStrategy.win_rate.toFixed(1)}%</div>
                      </div>
                      <div>
                        <div className="text-gray-400">Expectancy</div>
                        <div className="font-bold text-red-400">{summary.worstStrategy.expectancy_pct.toFixed(2)}%</div>
                      </div>
                      <div>
                        <div className="text-gray-400">Trades</div>
                        <div className="font-bold">{summary.worstStrategy.total_trades}</div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Filters */}
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                <div className="flex items-center justify-between">
                  <div className="text-sm text-gray-400">
                    Showing {filteredResults.length} of {results.length} strategies
                  </div>
                  <div className="flex items-center gap-4">
                    <label className="text-sm text-gray-400">
                      Min Expectancy: {minExpectancy.toFixed(1)}%
                    </label>
                    <input
                      type="range"
                      min="-5"
                      max="5"
                      step="0.1"
                      value={minExpectancy}
                      onChange={(e) => setMinExpectancy(Number(e.target.value))}
                      className="w-48"
                    />
                  </div>
                </div>
              </div>

              {/* Results Table */}
              <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-gray-950 border-b border-gray-800">
                      <tr className="text-left text-sm text-gray-400">
                        <th className="p-4">Strategy</th>
                        <th className="p-4">Test Period</th>
                        <th className="p-4">Freshness</th>
                        <th className="p-4">Trades</th>
                        <th className="p-4">Win Rate</th>
                        <th className="p-4">Expectancy</th>
                        <th className="p-4">Total Return</th>
                        <th className="p-4">Max DD</th>
                        <th className="p-4">Sharpe</th>
                        <th className="p-4">Status</th>
                      </tr>
                    </thead>
                    <tbody className="text-sm">
                      {filteredResults
                        .sort((a, b) => b.expectancy_pct - a.expectancy_pct)
                        .map((result, idx) => {
                          const daysSince = Math.floor(
                            (new Date().getTime() - new Date(result.timestamp).getTime()) / (1000 * 60 * 60 * 24)
                          )
                          const freshnessColor = daysSince <= 7 ? 'text-green-400' : daysSince <= 30 ? 'text-yellow-400' : 'text-red-400'
                          const freshnessLabel = daysSince <= 7 ? 'FRESH' : daysSince <= 30 ? 'RECENT' : 'STALE'
                          const confidenceColor = result.total_trades >= 100 ? 'text-green-400' : result.total_trades >= 50 ? 'text-yellow-400' : 'text-orange-400'

                          return (
                          <tr key={idx} className="border-b border-gray-800 hover:bg-gray-950/50">
                            <td className="p-4">
                              <div className="font-semibold">{result.strategy_name.replace(/_/g, ' ')}</div>
                              <div className="text-xs text-gray-500">{result.symbol}</div>
                            </td>
                            <td className="p-4">
                              <div className="flex items-center gap-1 text-xs text-gray-400">
                                <Calendar className="w-3 h-3" />
                                <div>
                                  <div className="font-mono">{result.start_date}</div>
                                  <div className="font-mono">to {result.end_date}</div>
                                </div>
                              </div>
                            </td>
                            <td className="p-4">
                              <div className="flex items-center gap-1">
                                <Clock className="w-3 h-3 text-gray-400" />
                                <div>
                                  <div className={`text-xs font-bold ${freshnessColor}`}>{freshnessLabel}</div>
                                  <div className="text-xs text-gray-500">{daysSince}d ago</div>
                                </div>
                              </div>
                            </td>
                            <td className="p-4">
                              <div className={`font-bold ${confidenceColor}`}>{result.total_trades}</div>
                              <div className="text-xs text-gray-500">
                                {result.total_trades >= 100 ? 'High conf' : result.total_trades >= 50 ? 'Med conf' : 'Low conf'}
                              </div>
                            </td>
                            <td className={`p-4 font-bold ${result.win_rate >= 55 ? 'text-green-400' : result.win_rate >= 45 ? 'text-yellow-400' : 'text-red-400'}`}>
                              {result.win_rate.toFixed(1)}%
                            </td>
                            <td className={`p-4 font-bold ${result.expectancy_pct >= 0.5 ? 'text-green-400' : result.expectancy_pct >= 0 ? 'text-yellow-400' : 'text-red-400'}`}>
                              {result.expectancy_pct.toFixed(2)}%
                            </td>
                            <td className={`p-4 font-bold ${result.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              {result.total_return_pct >= 0 ? '+' : ''}{result.total_return_pct.toFixed(2)}%
                            </td>
                            <td className="p-4 text-red-400 font-bold">
                              {result.max_drawdown_pct.toFixed(2)}%
                            </td>
                            <td className="p-4">
                              {result.sharpe_ratio.toFixed(2)}
                            </td>
                            <td className="p-4">
                              <span className={`px-3 py-1 rounded-full text-xs font-bold ${
                                result.expectancy_pct >= 0.5
                                  ? 'bg-green-500/20 text-green-400'
                                  : result.expectancy_pct >= 0
                                  ? 'bg-yellow-500/20 text-yellow-400'
                                  : 'bg-red-500/20 text-red-400'
                              }`}>
                                {result.expectancy_pct >= 0.5 ? '✓ TRADE' : result.expectancy_pct >= 0 ? '⚠ MARGINAL' : '✗ SKIP'}
                              </span>
                            </td>
                          </tr>
                        )}
                        )}
                    </tbody>
                  </table>
                </div>
              </div>

            </>
          )}

        </div>
      </main>
    </div>
  )
}
