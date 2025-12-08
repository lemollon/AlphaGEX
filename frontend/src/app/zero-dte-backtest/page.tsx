'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  TestTube, TrendingUp, TrendingDown, Activity, BarChart3, PlayCircle,
  RefreshCw, AlertTriangle, Calendar, Clock, Loader2, CheckCircle,
  Settings, DollarSign, Target, Layers, ChevronDown, ChevronUp
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, BarChart, Bar, Cell
} from 'recharts'

interface BacktestConfig {
  start_date: string
  end_date: string
  initial_capital: number
  spread_width: number
  sd_multiplier: number
  risk_per_trade_pct: number
  ticker: string
  strategy: string
}

interface BacktestJob {
  job_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  progress_message: string
  result: any
  error: string | null
  created_at: string
  completed_at: string | null
}

interface Strategy {
  id: string
  name: string
  description: string
  features: string[]
  recommended_settings: {
    risk_per_trade_pct: number
    sd_multiplier: number
    spread_width: number
  }
}

interface Tier {
  name: string
  equity_range: string
  options_dte: string
  sd_days: number
  max_contracts: number
  trades_per_week: number
  description: string
}

interface BacktestResult {
  id: number
  job_id: string
  created_at: string
  strategy: string
  ticker: string
  start_date: string
  end_date: string
  initial_capital: number
  final_equity: number
  total_pnl: number
  total_return_pct: number
  avg_monthly_return_pct: number
  max_drawdown_pct: number
  total_trades: number
  win_rate: number
  profit_factor: number
  total_costs: number
  tier_stats: any
  monthly_returns: any
}

export default function ZeroDTEBacktestPage() {
  // Configuration state
  const [config, setConfig] = useState<BacktestConfig>({
    start_date: '2022-01-01',
    end_date: '2025-12-01',
    initial_capital: 1000000,
    spread_width: 10,
    sd_multiplier: 1.0,
    risk_per_trade_pct: 5.0,
    ticker: 'SPX',
    strategy: 'hybrid_fixed'
  })

  // UI state
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [tiers, setTiers] = useState<Tier[]>([])
  const [results, setResults] = useState<BacktestResult[]>([])
  const [selectedResult, setSelectedResult] = useState<BacktestResult | null>(null)

  // Job state
  const [currentJobId, setCurrentJobId] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<BacktestJob | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // UI toggles
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [showTiers, setShowTiers] = useState(false)

  // Load strategies and tiers on mount
  useEffect(() => {
    loadStrategies()
    loadTiers()
    loadResults()
  }, [])

  // Poll job status
  useEffect(() => {
    if (!currentJobId || !running) return

    const interval = setInterval(async () => {
      try {
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/zero-dte/job/${currentJobId}`)
        const data = await response.json()

        if (data.job) {
          setJobStatus(data.job)

          if (data.job.status === 'completed') {
            setRunning(false)
            setCurrentJobId(null)
            loadResults()
          } else if (data.job.status === 'failed') {
            setRunning(false)
            setCurrentJobId(null)
            setError(data.job.error || 'Backtest failed')
          }
        }
      } catch (err) {
        console.error('Failed to poll job status:', err)
      }
    }, 2000)

    return () => clearInterval(interval)
  }, [currentJobId, running])

  const loadStrategies = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/zero-dte/strategies`)
      const data = await response.json()
      if (data.strategies) {
        setStrategies(data.strategies)
      }
    } catch (err) {
      console.error('Failed to load strategies:', err)
    }
  }

  const loadTiers = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/zero-dte/tiers`)
      const data = await response.json()
      if (data.tiers) {
        setTiers(data.tiers)
      }
    } catch (err) {
      console.error('Failed to load tiers:', err)
    }
  }

  const loadResults = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/zero-dte/results`)
      const data = await response.json()
      if (data.results) {
        setResults(data.results)
        if (data.results.length > 0) {
          setSelectedResult(data.results[0])
        }
      }
    } catch (err) {
      console.error('Failed to load results:', err)
    }
  }

  const runBacktest = async () => {
    setRunning(true)
    setError(null)
    setJobStatus(null)

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/zero-dte/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      })

      const data = await response.json()

      if (data.job_id) {
        setCurrentJobId(data.job_id)
        setJobStatus({
          job_id: data.job_id,
          status: 'pending',
          progress: 0,
          progress_message: 'Job queued...',
          result: null,
          error: null,
          created_at: new Date().toISOString(),
          completed_at: null
        })
      } else {
        setError(data.error || 'Failed to start backtest')
        setRunning(false)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to connect to API')
      setRunning(false)
    }
  }

  const selectStrategy = (strategyId: string) => {
    const strategy = strategies.find(s => s.id === strategyId)
    if (strategy) {
      setConfig(prev => ({
        ...prev,
        strategy: strategyId,
        ...strategy.recommended_settings
      }))
    }
  }

  // Format monthly returns for chart
  const monthlyChartData = selectedResult?.monthly_returns
    ? Object.entries(selectedResult.monthly_returns).map(([month, pct]) => ({
        month,
        return_pct: typeof pct === 'number' ? pct : parseFloat(String(pct))
      }))
    : []

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <Navigation />

      <main className="pt-16">
        <div className="container mx-auto px-4 py-8 space-y-6">

          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold flex items-center gap-3">
                <TestTube className="w-8 h-8 text-blue-400" />
                0DTE Iron Condor Backtest
              </h1>
              <p className="text-gray-400 mt-1">
                Hybrid scaling strategy with automatic tier transitions
              </p>
            </div>
          </div>

          {/* Strategy Selection */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {strategies.map(strategy => (
              <div
                key={strategy.id}
                onClick={() => selectStrategy(strategy.id)}
                className={`bg-gray-900 border rounded-lg p-4 cursor-pointer transition-all ${
                  config.strategy === strategy.id
                    ? 'border-blue-500 ring-2 ring-blue-500/20'
                    : 'border-gray-800 hover:border-gray-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-bold">{strategy.name}</h3>
                  {config.strategy === strategy.id && (
                    <CheckCircle className="w-5 h-5 text-blue-400" />
                  )}
                </div>
                <p className="text-sm text-gray-400 mb-3">{strategy.description}</p>
                <div className="flex flex-wrap gap-1">
                  {strategy.features.slice(0, 2).map((f, i) => (
                    <span key={i} className="px-2 py-0.5 bg-gray-800 rounded text-xs text-gray-300">
                      {f}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Configuration Panel */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold flex items-center gap-2">
                <Settings className="w-5 h-5 text-gray-400" />
                Backtest Configuration
              </h2>
              <button
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1"
              >
                {showAdvanced ? 'Hide' : 'Show'} Advanced
                {showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {/* Date Range */}
              <div>
                <label className="block text-sm text-gray-400 mb-1">Start Date</label>
                <input
                  type="date"
                  value={config.start_date}
                  onChange={e => setConfig(prev => ({ ...prev, start_date: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">End Date</label>
                <input
                  type="date"
                  value={config.end_date}
                  onChange={e => setConfig(prev => ({ ...prev, end_date: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                />
              </div>

              {/* Capital */}
              <div>
                <label className="block text-sm text-gray-400 mb-1">Initial Capital</label>
                <div className="relative">
                  <DollarSign className="absolute left-3 top-2.5 w-4 h-4 text-gray-500" />
                  <input
                    type="number"
                    value={config.initial_capital}
                    onChange={e => setConfig(prev => ({ ...prev, initial_capital: Number(e.target.value) }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded pl-8 pr-3 py-2 text-sm"
                  />
                </div>
              </div>

              {/* Risk */}
              <div>
                <label className="block text-sm text-gray-400 mb-1">Risk Per Trade (%)</label>
                <input
                  type="number"
                  step="0.5"
                  value={config.risk_per_trade_pct}
                  onChange={e => setConfig(prev => ({ ...prev, risk_per_trade_pct: Number(e.target.value) }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                />
              </div>
            </div>

            {/* Advanced Options */}
            {showAdvanced && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4 pt-4 border-t border-gray-800">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">SD Multiplier</label>
                  <input
                    type="number"
                    step="0.1"
                    value={config.sd_multiplier}
                    onChange={e => setConfig(prev => ({ ...prev, sd_multiplier: Number(e.target.value) }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Spread Width ($)</label>
                  <input
                    type="number"
                    value={config.spread_width}
                    onChange={e => setConfig(prev => ({ ...prev, spread_width: Number(e.target.value) }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Ticker</label>
                  <select
                    value={config.ticker}
                    onChange={e => setConfig(prev => ({ ...prev, ticker: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                  >
                    <option value="SPX">SPX</option>
                    <option value="SPXW">SPXW</option>
                  </select>
                </div>
              </div>
            )}

            {/* Run Button */}
            <div className="mt-6 flex items-center gap-4">
              <button
                onClick={runBacktest}
                disabled={running}
                className="px-6 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg font-semibold disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {running ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Running Backtest...
                  </>
                ) : (
                  <>
                    <PlayCircle className="w-5 h-5" />
                    Run Backtest
                  </>
                )}
              </button>

              {error && (
                <div className="flex items-center gap-2 text-red-400">
                  <AlertTriangle className="w-5 h-5" />
                  {error}
                </div>
              )}
            </div>

            {/* Progress Bar */}
            {running && jobStatus && (
              <div className="mt-4 bg-gray-800 rounded-lg p-4">
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-gray-400">{jobStatus.progress_message}</span>
                  <span className="text-blue-400">{jobStatus.progress}%</span>
                </div>
                <div className="w-full bg-gray-700 rounded-full h-2">
                  <div
                    className="bg-blue-500 h-2 rounded-full transition-all duration-500"
                    style={{ width: `${jobStatus.progress}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Scaling Tiers Info */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
            <button
              onClick={() => setShowTiers(!showTiers)}
              className="w-full px-6 py-4 flex items-center justify-between hover:bg-gray-800/50"
            >
              <div className="flex items-center gap-2">
                <Layers className="w-5 h-5 text-purple-400" />
                <span className="font-bold">Scaling Tiers</span>
                <span className="text-sm text-gray-400">- How the strategy adapts as your account grows</span>
              </div>
              {showTiers ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
            </button>

            {showTiers && (
              <div className="px-6 pb-6">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  {tiers.map((tier, i) => (
                    <div key={tier.name} className="bg-gray-800 rounded-lg p-4">
                      <div className="text-purple-400 font-bold mb-2">Tier {i + 1}</div>
                      <div className="text-lg font-bold mb-1">{tier.equity_range}</div>
                      <div className="text-sm text-gray-400 mb-3">{tier.description}</div>
                      <div className="space-y-1 text-xs">
                        <div className="flex justify-between">
                          <span className="text-gray-500">Options:</span>
                          <span>{tier.options_dte}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">SD Days:</span>
                          <span>{tier.sd_days}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">Max Contracts:</span>
                          <span>{tier.max_contracts}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">Trades/Week:</span>
                          <span>{tier.trades_per_week}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Results Section */}
          {results.length > 0 && (
            <>
              {/* Summary Cards */}
              {selectedResult && (
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                  <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                    <div className="text-sm text-gray-400 mb-1">Final Equity</div>
                    <div className="text-2xl font-bold text-green-400">
                      ${selectedResult.final_equity?.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </div>
                  </div>
                  <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                    <div className="text-sm text-gray-400 mb-1">Total Return</div>
                    <div className={`text-2xl font-bold ${selectedResult.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {selectedResult.total_return_pct?.toFixed(1)}%
                    </div>
                  </div>
                  <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                    <div className="text-sm text-gray-400 mb-1">Avg Monthly</div>
                    <div className={`text-2xl font-bold ${selectedResult.avg_monthly_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {selectedResult.avg_monthly_return_pct?.toFixed(2)}%
                    </div>
                  </div>
                  <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                    <div className="text-sm text-gray-400 mb-1">Win Rate</div>
                    <div className="text-2xl font-bold text-blue-400">
                      {selectedResult.win_rate?.toFixed(1)}%
                    </div>
                  </div>
                  <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                    <div className="text-sm text-gray-400 mb-1">Max Drawdown</div>
                    <div className="text-2xl font-bold text-red-400">
                      {selectedResult.max_drawdown_pct?.toFixed(1)}%
                    </div>
                  </div>
                </div>
              )}

              {/* Monthly Returns Chart */}
              {monthlyChartData.length > 0 && (
                <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
                  <h3 className="font-bold mb-4">Monthly Returns</h3>
                  <div className="h-80">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={monthlyChartData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis
                          dataKey="month"
                          stroke="#9CA3AF"
                          fontSize={10}
                          angle={-45}
                          textAnchor="end"
                          height={60}
                        />
                        <YAxis
                          stroke="#9CA3AF"
                          fontSize={12}
                          tickFormatter={(v) => `${v}%`}
                        />
                        <Tooltip
                          contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                          formatter={(value: number) => [`${value.toFixed(2)}%`, 'Return']}
                        />
                        <Bar dataKey="return_pct" name="Return %">
                          {monthlyChartData.map((entry, index) => (
                            <Cell
                              key={`cell-${index}`}
                              fill={entry.return_pct >= 0 ? '#22C55E' : '#EF4444'}
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {/* Results History */}
              <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
                <div className="px-6 py-4 border-b border-gray-800">
                  <h3 className="font-bold">Backtest History</h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-gray-950 text-sm text-gray-400">
                      <tr>
                        <th className="text-left p-4">Date</th>
                        <th className="text-left p-4">Strategy</th>
                        <th className="text-left p-4">Period</th>
                        <th className="text-right p-4">Initial</th>
                        <th className="text-right p-4">Final</th>
                        <th className="text-right p-4">Return</th>
                        <th className="text-right p-4">Monthly Avg</th>
                        <th className="text-right p-4">Win Rate</th>
                        <th className="text-right p-4">Trades</th>
                      </tr>
                    </thead>
                    <tbody>
                      {results.map(result => (
                        <tr
                          key={result.id}
                          onClick={() => setSelectedResult(result)}
                          className={`border-b border-gray-800 cursor-pointer hover:bg-gray-800/50 ${
                            selectedResult?.id === result.id ? 'bg-blue-900/20' : ''
                          }`}
                        >
                          <td className="p-4 text-sm text-gray-400">
                            {new Date(result.created_at).toLocaleDateString()}
                          </td>
                          <td className="p-4 font-medium">{result.strategy}</td>
                          <td className="p-4 text-sm text-gray-400">
                            {result.start_date} - {result.end_date}
                          </td>
                          <td className="p-4 text-right">
                            ${result.initial_capital?.toLocaleString()}
                          </td>
                          <td className="p-4 text-right font-bold text-green-400">
                            ${result.final_equity?.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                          </td>
                          <td className={`p-4 text-right font-bold ${result.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {result.total_return_pct?.toFixed(1)}%
                          </td>
                          <td className={`p-4 text-right ${result.avg_monthly_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {result.avg_monthly_return_pct?.toFixed(2)}%
                          </td>
                          <td className="p-4 text-right text-blue-400">
                            {result.win_rate?.toFixed(1)}%
                          </td>
                          <td className="p-4 text-right">{result.total_trades}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}

          {/* Empty State */}
          {results.length === 0 && !running && (
            <div className="bg-gray-900 border-2 border-dashed border-gray-700 rounded-xl p-12 text-center">
              <TestTube className="w-16 h-16 mx-auto mb-4 text-gray-600" />
              <h2 className="text-2xl font-bold mb-2">No Backtest Results Yet</h2>
              <p className="text-gray-400 mb-6 max-w-lg mx-auto">
                Configure your strategy parameters above and click "Run Backtest" to analyze the
                0DTE Iron Condor hybrid scaling strategy with your ORAT historical data.
              </p>
            </div>
          )}

        </div>
      </main>
    </div>
  )
}
