'use client'

import { useEffect, useState } from 'react'
import Navigation from '@/components/Navigation'
import LoadingWithTips from '@/components/LoadingWithTips'
import { TestTube, TrendingUp, TrendingDown, DollarSign, Activity, BarChart3 } from 'lucide-react'

interface BacktestResult {
  strategy_name: string
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  total_pnl: number
  avg_win: number
  avg_loss: number
  expectancy: number
  sharpe_ratio: number
  max_drawdown: number
  profit_factor: number
}

export default function BacktestingPage() {
  const [results, setResults] = useState<BacktestResult[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedStrategy, setSelectedStrategy] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [symbol, setSymbol] = useState('SPY')

  useEffect(() => {
    fetchResults()
  }, [])

  const fetchResults = async () => {
    try {
      setLoading(true)
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/backtests/results`)
      const data = await response.json()

      if (data.success) {
        setResults(data.results || data.data || [])
      }
    } catch (error) {
      console.error('Failed to fetch backtest results:', error)
    } finally {
      setLoading(false)
    }
  }

  const runBacktests = async () => {
    setRunning(true)
    setRunError(null)

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/backtests/run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          symbol: symbol,
        }),
      })

      const data = await response.json()

      if (data.success) {
        // Refresh results after successful run
        await fetchResults()
      } else {
        setRunError(data.error || 'Failed to run backtests')
      }
    } catch (err) {
      setRunError('Failed to connect to API')
    } finally {
      setRunning(false)
    }
  }

  const formatCurrency = (value: number) => {
    return value >= 0 ? `+$${value.toFixed(2)}` : `-$${Math.abs(value).toFixed(2)}`
  }

  const formatPercent = (value: number) => {
    return `${value.toFixed(1)}%`
  }

  const getProfitabilityColor = (expectancy: number) => {
    if (expectancy >= 1.0) return 'text-success'
    if (expectancy >= 0.5) return 'text-warning'
    return 'text-danger'
  }

  return (
    <div className="min-h-screen">
      <Navigation />

      <main className="pt-16 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="mb-8">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h1 className="text-3xl font-bold text-text-primary flex items-center space-x-3">
                  <TestTube className="w-8 h-8 text-primary" />
                  <span>Strategy Backtesting</span>
                </h1>
                <p className="text-text-secondary mt-2">
                  Performance analysis of all trading strategies with realistic transaction costs
                </p>
              </div>
              <div className="flex items-center space-x-3">
                <input
                  type="text"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                  placeholder="Symbol"
                  className="px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary focus:outline-none focus:border-primary w-24"
                />
                <button
                  onClick={runBacktests}
                  disabled={running}
                  className="btn-primary flex items-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {running ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                      <span>Running...</span>
                    </>
                  ) : (
                    <>
                      <Activity className="w-5 h-5" />
                      <span>Run Backtests</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {runError && (
              <div className="bg-danger/10 border border-danger rounded-lg p-4 mb-4">
                <div className="flex items-center space-x-2 text-danger">
                  <span className="font-semibold">{runError}</span>
                </div>
              </div>
            )}

            {running && (
              <LoadingWithTips
                message="Running comprehensive strategy backtests..."
                showProgress={false}
              />
            )}
          </div>

          {loading ? (
            <LoadingWithTips
              message="Loading backtest results..."
              showProgress={false}
            />
          ) : results.length === 0 ? (
            <div className="card text-center py-12">
              <TestTube className="w-16 h-16 mx-auto text-text-muted mb-4" />
              <h3 className="text-xl font-semibold text-text-primary mb-2">No Backtest Results</h3>
              <p className="text-text-secondary mb-4">
                Click "Run Backtests" above to analyze all trading strategies with historical data
              </p>
              <p className="text-text-muted text-sm">
                The system will automatically research and test 29+ strategies across Psychology, GEX, and Options
              </p>
            </div>
          ) : (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
                <div className="card">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-text-secondary text-sm">Total Strategies</p>
                      <p className="text-2xl font-bold text-text-primary">{results.length}</p>
                    </div>
                    <BarChart3 className="w-8 h-8 text-primary" />
                  </div>
                </div>

                <div className="card">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-text-secondary text-sm">Profitable</p>
                      <p className="text-2xl font-bold text-success">
                        {results.filter(r => r.expectancy > 0.5).length}
                      </p>
                    </div>
                    <TrendingUp className="w-8 h-8 text-success" />
                  </div>
                </div>

                <div className="card">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-text-secondary text-sm">Marginal</p>
                      <p className="text-2xl font-bold text-warning">
                        {results.filter(r => r.expectancy >= 0 && r.expectancy <= 0.5).length}
                      </p>
                    </div>
                    <Activity className="w-8 h-8 text-warning" />
                  </div>
                </div>

                <div className="card">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-text-secondary text-sm">Unprofitable</p>
                      <p className="text-2xl font-bold text-danger">
                        {results.filter(r => r.expectancy < 0).length}
                      </p>
                    </div>
                    <TrendingDown className="w-8 h-8 text-danger" />
                  </div>
                </div>
              </div>

              {/* Strategy Cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {results
                  .sort((a, b) => b.expectancy - a.expectancy)
                  .map((result) => (
                    <div
                      key={result.strategy_name}
                      className="card hover:shadow-xl transition-shadow cursor-pointer"
                      onClick={() => setSelectedStrategy(result.strategy_name)}
                    >
                      <div className="flex items-start justify-between mb-4">
                        <div>
                          <h3 className="text-lg font-semibold text-text-primary">
                            {result.strategy_name.replace(/_/g, ' ')}
                          </h3>
                          <p className="text-sm text-text-secondary">
                            {result.total_trades} trades
                          </p>
                        </div>
                        <div className={`px-3 py-1 rounded-full text-sm font-semibold ${
                          result.expectancy >= 1.0
                            ? 'bg-success/20 text-success'
                            : result.expectancy >= 0.5
                            ? 'bg-warning/20 text-warning'
                            : 'bg-danger/20 text-danger'
                        }`}>
                          {result.expectancy >= 0.5 ? '✓ Trade' : '✗ Skip'}
                        </div>
                      </div>

                      <div className="space-y-3">
                        <div className="flex justify-between items-center">
                          <span className="text-text-secondary text-sm">Win Rate</span>
                          <span className="text-text-primary font-semibold">
                            {formatPercent(result.win_rate)}
                          </span>
                        </div>

                        <div className="flex justify-between items-center">
                          <span className="text-text-secondary text-sm">Expectancy</span>
                          <span className={`font-semibold ${getProfitabilityColor(result.expectancy)}`}>
                            {formatPercent(result.expectancy)}
                          </span>
                        </div>

                        <div className="flex justify-between items-center">
                          <span className="text-text-secondary text-sm">Total P&L</span>
                          <span className={`font-semibold ${result.total_pnl >= 0 ? 'text-success' : 'text-danger'}`}>
                            {formatCurrency(result.total_pnl)}
                          </span>
                        </div>

                        <div className="flex justify-between items-center">
                          <span className="text-text-secondary text-sm">Sharpe Ratio</span>
                          <span className="text-text-primary font-semibold">
                            {result.sharpe_ratio.toFixed(2)}
                          </span>
                        </div>

                        <div className="flex justify-between items-center">
                          <span className="text-text-secondary text-sm">Max Drawdown</span>
                          <span className="text-danger font-semibold">
                            {formatPercent(result.max_drawdown)}
                          </span>
                        </div>

                        <div className="pt-3 border-t border-gray-700">
                          <div className="flex justify-between text-xs">
                            <div>
                              <div className="text-text-muted">Avg Win</div>
                              <div className="text-success font-semibold">
                                {formatCurrency(result.avg_win)}
                              </div>
                            </div>
                            <div className="text-right">
                              <div className="text-text-muted">Avg Loss</div>
                              <div className="text-danger font-semibold">
                                {formatCurrency(result.avg_loss)}
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  )
}
