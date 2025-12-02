'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Brain, TrendingUp, TrendingDown, AlertTriangle, CheckCircle,
  PlayCircle, RefreshCw, BarChart3, Target, DollarSign,
  Info, Zap, Clock, Database, ChevronDown, ChevronUp,
  FileText, Activity
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { api } from '@/lib/api'

interface MLLog {
  id: number
  timestamp: string
  action: string
  symbol: string
  details: any
  ml_score: number | null
  recommendation: string | null
  reasoning: string | null
  trade_id: string | null
  backtest_id: string | null
}

interface MLStatus {
  ml_library_available: boolean
  model_trained: boolean
  training_data_available: number
  can_train: boolean
  should_trust_predictions: boolean
  honest_assessment: string
  training_metrics: any
  what_ml_can_do: string[]
  what_ml_cannot_do: string[]
}

interface BacktestSummary {
  start_date: string
  end_date: string
  initial_capital: number
  final_equity: number
  total_return_pct: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  max_drawdown_pct: number
  sharpe_ratio: number
}

interface DataQuality {
  real_data_pct: number
  real_data_points: number
  estimated_data_points: number
  quality_verdict: string
}

interface StrategyExplanation {
  strategy: string
  why_it_works: {
    volatility_risk_premium: { explanation: string; why: string; you_benefit: string }
    theta_decay: { explanation: string; why: string; you_benefit: string }
    probability: { explanation: string; why: string; you_benefit: string }
  }
  why_it_can_fail: {
    tail_risk: { explanation: string; examples: string[]; impact: string }
    asymmetric_payoff: { explanation: string; math: string }
    drawdowns: { explanation: string; reality: string }
  }
  what_ml_adds: { helps_with: string[]; cannot_help_with: string[] }
  realistic_expectations: {
    annual_return: string
    max_drawdown: string
    win_rate: string
    key_insight: string
  }
  bottom_line: string
}

export default function SPXWheelPage() {
  const [mlStatus, setMlStatus] = useState<MLStatus | null>(null)
  const [strategyExplanation, setStrategyExplanation] = useState<StrategyExplanation | null>(null)
  const [backtestSummary, setBacktestSummary] = useState<BacktestSummary | null>(null)
  const [dataQuality, setDataQuality] = useState<DataQuality | null>(null)
  const [loading, setLoading] = useState(true)
  const [runningBacktest, setRunningBacktest] = useState(false)
  const [trainingML, setTrainingML] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showWhyItWorks, setShowWhyItWorks] = useState(true)
  const [showRisks, setShowRisks] = useState(false)
  const [showMLDetails, setShowMLDetails] = useState(false)
  const [mlLogs, setMlLogs] = useState<MLLog[]>([])
  const [showLogs, setShowLogs] = useState(true)
  const [logsLoading, setLogsLoading] = useState(false)
  // Backtest configuration (user-configurable)
  const [backtestStartDate, setBacktestStartDate] = useState('2024-01-01')
  const [backtestEndDate, setBacktestEndDate] = useState('')
  const [showBacktestConfig, setShowBacktestConfig] = useState(false)

  const fetchLogs = useCallback(async () => {
    try {
      setLogsLoading(true)
      const res = await api.get('/api/ml/logs?limit=50').catch(() => ({ data: { data: null } }))
      if (res.data?.data?.logs) {
        setMlLogs(res.data.data.logs)
      }
    } catch (err) {
      console.error('Failed to fetch logs:', err)
    } finally {
      setLogsLoading(false)
    }
  }, [])

  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      // Fetch all data in parallel
      const [mlRes, strategyRes] = await Promise.all([
        api.get('/api/ml/status').catch(() => ({ data: { data: null } })),
        api.get('/api/ml/strategy-explanation').catch(() => ({ data: { data: null } }))
      ])

      if (mlRes.data?.data) {
        setMlStatus(mlRes.data.data)
      }
      if (strategyRes.data?.data) {
        setStrategyExplanation(strategyRes.data.data)
      }

      // Also fetch logs
      await fetchLogs()

    } catch (err: any) {
      setError(err.message || 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }, [fetchLogs])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const runBacktest = async () => {
    setRunningBacktest(true)
    setError(null)

    try {
      const res = await api.post('/api/spx-backtest/run', {
        start_date: backtestStartDate,
        end_date: backtestEndDate || undefined,  // Use current date if empty
        initial_capital: 100000,
        put_delta: 0.20,
        dte_target: 45,
        use_ml_scoring: true
      })

      if (res.data?.success) {
        setBacktestSummary(res.data.summary)
        setDataQuality(res.data.data_quality)
      } else {
        setError(res.data?.error || 'Backtest failed')
      }
    } catch (err: any) {
      setError(err.message || 'Failed to run backtest')
    } finally {
      setRunningBacktest(false)
    }
  }

  const trainML = async () => {
    setTrainingML(true)
    setError(null)

    try {
      const res = await api.post('/api/ml/train', { min_samples: 30 })

      if (res.data?.success) {
        await fetchData() // Refresh ML status
      } else {
        setError(res.data?.error || res.data?.detail?.action_required || 'Training failed - need more trade data')
      }
    } catch (err: any) {
      setError(err.message || 'Failed to train ML')
    } finally {
      setTrainingML(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 text-white">
        <Navigation />
        <main className="pt-16">
          <div className="container mx-auto px-4 py-8">
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-500 border-t-transparent" />
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
                <Target className="w-8 h-8 text-blue-400" />
                SPX Wheel Strategy
              </h1>
              <p className="text-gray-400 mt-1">
                Cash-secured put selling on S&P 500 Index with ML optimization
              </p>
            </div>
            <div className="flex gap-3 items-center">
              <button
                onClick={() => setShowBacktestConfig(!showBacktestConfig)}
                className="px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm flex items-center gap-2"
              >
                <Clock className="w-4 h-4" />
                {showBacktestConfig ? 'Hide' : 'Config'}
              </button>
              <button
                onClick={runBacktest}
                disabled={runningBacktest}
                className="px-6 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg font-semibold disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {runningBacktest ? (
                  <>
                    <RefreshCw className="w-5 h-5 animate-spin" />
                    Running...
                  </>
                ) : (
                  <>
                    <PlayCircle className="w-5 h-5" />
                    Run Backtest
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Backtest Date Configuration */}
          {showBacktestConfig && (
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <h3 className="font-semibold mb-3 flex items-center gap-2">
                <Clock className="w-5 h-5 text-blue-400" />
                Backtest Configuration
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Start Date</label>
                  <input
                    type="date"
                    value={backtestStartDate}
                    onChange={(e) => setBacktestStartDate(e.target.value)}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">End Date (empty = today)</label>
                  <input
                    type="date"
                    value={backtestEndDate}
                    onChange={(e) => setBacktestEndDate(e.target.value)}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white"
                  />
                </div>
                <div className="col-span-2 text-xs text-gray-500 flex items-center">
                  <Info className="w-4 h-4 mr-2" />
                  Backtest uses 20-delta puts with 45 DTE, $100K capital
                </div>
              </div>
            </div>
          )}

          {/* Error Display */}
          {error && (
            <div className="bg-red-500/10 border border-red-500 rounded-lg p-4 flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0" />
              <div className="text-red-400">{error}</div>
            </div>
          )}

          {/* HONEST ML STATUS */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <Brain className="w-6 h-6 text-purple-400" />
                <h2 className="text-xl font-bold">ML System Status</h2>
              </div>
              <div className="flex items-center gap-3">
                {mlStatus?.model_trained ? (
                  <span className="px-3 py-1 bg-green-500/20 text-green-400 rounded-full text-sm font-semibold">
                    TRAINED
                  </span>
                ) : (
                  <span className="px-3 py-1 bg-yellow-500/20 text-yellow-400 rounded-full text-sm font-semibold">
                    NOT TRAINED
                  </span>
                )}
                <button
                  onClick={trainML}
                  disabled={trainingML || !mlStatus?.can_train}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg text-sm disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {trainingML ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Training...
                    </>
                  ) : (
                    <>
                      <Zap className="w-4 h-4" />
                      Train ML
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Honest Assessment */}
            <div className="bg-gray-950 rounded-lg p-4 mb-4">
              <p className="text-lg font-semibold text-yellow-400">
                {mlStatus?.honest_assessment || 'ML status unknown'}
              </p>
            </div>

            {/* ML Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <div className="bg-gray-950 rounded-lg p-4">
                <p className="text-gray-400 text-sm">Training Data</p>
                <p className="text-2xl font-bold">{mlStatus?.training_data_available || 0}</p>
                <p className="text-xs text-gray-500">trades recorded</p>
              </div>
              <div className="bg-gray-950 rounded-lg p-4">
                <p className="text-gray-400 text-sm">Can Train</p>
                <p className={`text-2xl font-bold ${mlStatus?.can_train ? 'text-green-400' : 'text-red-400'}`}>
                  {mlStatus?.can_train ? 'YES' : 'NO'}
                </p>
                <p className="text-xs text-gray-500">need 30+ trades</p>
              </div>
              <div className="bg-gray-950 rounded-lg p-4">
                <p className="text-gray-400 text-sm">Model Accuracy</p>
                <p className="text-2xl font-bold">
                  {mlStatus?.training_metrics?.test_accuracy
                    ? `${(mlStatus.training_metrics.test_accuracy * 100).toFixed(1)}%`
                    : 'N/A'}
                </p>
                <p className="text-xs text-gray-500">on test data</p>
              </div>
              <div className="bg-gray-950 rounded-lg p-4">
                <p className="text-gray-400 text-sm">Trust Level</p>
                <p className={`text-2xl font-bold ${mlStatus?.should_trust_predictions ? 'text-green-400' : 'text-yellow-400'}`}>
                  {mlStatus?.should_trust_predictions ? 'HIGH' : 'LOW'}
                </p>
                <p className="text-xs text-gray-500">need 50+ trades</p>
              </div>
            </div>

            {/* What ML Can/Cannot Do */}
            <button
              onClick={() => setShowMLDetails(!showMLDetails)}
              className="flex items-center gap-2 text-gray-400 hover:text-white text-sm"
            >
              {showMLDetails ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              {showMLDetails ? 'Hide' : 'Show'} ML Capabilities
            </button>

            {showMLDetails && (
              <div className="grid md:grid-cols-2 gap-4 mt-4">
                <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
                  <h3 className="font-semibold text-green-400 mb-2">What ML CAN Do</h3>
                  <ul className="space-y-1 text-sm text-gray-300">
                    {mlStatus?.what_ml_can_do?.map((item, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0 mt-0.5" />
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
                  <h3 className="font-semibold text-red-400 mb-2">What ML CANNOT Do</h3>
                  <ul className="space-y-1 text-sm text-gray-300">
                    {mlStatus?.what_ml_cannot_do?.map((item, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>

          {/* WHY THE STRATEGY WORKS */}
          {strategyExplanation && (
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
              <button
                onClick={() => setShowWhyItWorks(!showWhyItWorks)}
                className="flex items-center justify-between w-full"
              >
                <div className="flex items-center gap-3">
                  <TrendingUp className="w-6 h-6 text-green-400" />
                  <h2 className="text-xl font-bold">Why This Strategy Can Make Money</h2>
                </div>
                {showWhyItWorks ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
              </button>

              {showWhyItWorks && (
                <div className="mt-4 space-y-4">
                  {/* Three Edges */}
                  <div className="grid md:grid-cols-3 gap-4">
                    <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
                      <h3 className="font-bold text-green-400 mb-2">Volatility Risk Premium</h3>
                      <p className="text-sm text-gray-300 mb-2">
                        {strategyExplanation.why_it_works.volatility_risk_premium.explanation}
                      </p>
                      <p className="text-xs text-gray-400">
                        <strong>Why:</strong> {strategyExplanation.why_it_works.volatility_risk_premium.why}
                      </p>
                      <p className="text-xs text-green-400 mt-1">
                        <strong>You benefit:</strong> {strategyExplanation.why_it_works.volatility_risk_premium.you_benefit}
                      </p>
                    </div>

                    <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
                      <h3 className="font-bold text-green-400 mb-2">Theta Decay</h3>
                      <p className="text-sm text-gray-300 mb-2">
                        {strategyExplanation.why_it_works.theta_decay.explanation}
                      </p>
                      <p className="text-xs text-gray-400">
                        <strong>Why:</strong> {strategyExplanation.why_it_works.theta_decay.why}
                      </p>
                      <p className="text-xs text-green-400 mt-1">
                        <strong>You benefit:</strong> {strategyExplanation.why_it_works.theta_decay.you_benefit}
                      </p>
                    </div>

                    <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
                      <h3 className="font-bold text-green-400 mb-2">Probability</h3>
                      <p className="text-sm text-gray-300 mb-2">
                        {strategyExplanation.why_it_works.probability.explanation}
                      </p>
                      <p className="text-xs text-gray-400">
                        <strong>Why:</strong> {strategyExplanation.why_it_works.probability.why}
                      </p>
                      <p className="text-xs text-green-400 mt-1">
                        <strong>You benefit:</strong> {strategyExplanation.why_it_works.probability.you_benefit}
                      </p>
                    </div>
                  </div>

                  {/* Realistic Expectations */}
                  <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
                    <h3 className="font-bold text-blue-400 mb-3">Realistic Expectations</h3>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div>
                        <p className="text-gray-400 text-sm">Annual Return</p>
                        <p className="font-bold text-lg">{strategyExplanation.realistic_expectations.annual_return}</p>
                      </div>
                      <div>
                        <p className="text-gray-400 text-sm">Max Drawdown</p>
                        <p className="font-bold text-lg text-red-400">{strategyExplanation.realistic_expectations.max_drawdown}</p>
                      </div>
                      <div>
                        <p className="text-gray-400 text-sm">Win Rate</p>
                        <p className="font-bold text-lg text-green-400">{strategyExplanation.realistic_expectations.win_rate}</p>
                      </div>
                      <div>
                        <p className="text-gray-400 text-sm">Key Insight</p>
                        <p className="font-bold text-sm text-yellow-400">{strategyExplanation.realistic_expectations.key_insight}</p>
                      </div>
                    </div>
                  </div>

                  {/* Bottom Line */}
                  <div className="bg-gray-950 rounded-lg p-4">
                    <p className="text-gray-300 italic">"{strategyExplanation.bottom_line}"</p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* RISKS - HONEST */}
          {strategyExplanation && (
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
              <button
                onClick={() => setShowRisks(!showRisks)}
                className="flex items-center justify-between w-full"
              >
                <div className="flex items-center gap-3">
                  <AlertTriangle className="w-6 h-6 text-red-400" />
                  <h2 className="text-xl font-bold">Why This Strategy Can FAIL</h2>
                </div>
                {showRisks ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
              </button>

              {showRisks && (
                <div className="mt-4 grid md:grid-cols-3 gap-4">
                  <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
                    <h3 className="font-bold text-red-400 mb-2">Tail Risk</h3>
                    <p className="text-sm text-gray-300 mb-2">
                      {strategyExplanation.why_it_can_fail.tail_risk.explanation}
                    </p>
                    <p className="text-xs text-gray-400">
                      <strong>Examples:</strong> {strategyExplanation.why_it_can_fail.tail_risk.examples.join(', ')}
                    </p>
                    <p className="text-xs text-red-400 mt-1">
                      <strong>Impact:</strong> {strategyExplanation.why_it_can_fail.tail_risk.impact}
                    </p>
                  </div>

                  <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
                    <h3 className="font-bold text-red-400 mb-2">Asymmetric Payoff</h3>
                    <p className="text-sm text-gray-300 mb-2">
                      {strategyExplanation.why_it_can_fail.asymmetric_payoff.explanation}
                    </p>
                    <p className="text-xs text-yellow-400">
                      <strong>Math:</strong> {strategyExplanation.why_it_can_fail.asymmetric_payoff.math}
                    </p>
                  </div>

                  <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
                    <h3 className="font-bold text-red-400 mb-2">Drawdowns</h3>
                    <p className="text-sm text-gray-300 mb-2">
                      {strategyExplanation.why_it_can_fail.drawdowns.explanation}
                    </p>
                    <p className="text-xs text-gray-400">
                      <strong>Reality:</strong> {strategyExplanation.why_it_can_fail.drawdowns.reality}
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* BACKTEST RESULTS */}
          {backtestSummary && (
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
              <div className="flex items-center gap-3 mb-4">
                <BarChart3 className="w-6 h-6 text-blue-400" />
                <h2 className="text-xl font-bold">Backtest Results</h2>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div className="bg-gray-950 rounded-lg p-4">
                  <p className="text-gray-400 text-sm">Total Return</p>
                  <p className={`text-2xl font-bold ${backtestSummary.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {backtestSummary.total_return_pct >= 0 ? '+' : ''}{backtestSummary.total_return_pct.toFixed(2)}%
                  </p>
                </div>
                <div className="bg-gray-950 rounded-lg p-4">
                  <p className="text-gray-400 text-sm">Win Rate</p>
                  <p className={`text-2xl font-bold ${backtestSummary.win_rate >= 60 ? 'text-green-400' : 'text-yellow-400'}`}>
                    {backtestSummary.win_rate.toFixed(1)}%
                  </p>
                </div>
                <div className="bg-gray-950 rounded-lg p-4">
                  <p className="text-gray-400 text-sm">Max Drawdown</p>
                  <p className="text-2xl font-bold text-red-400">
                    {backtestSummary.max_drawdown_pct.toFixed(2)}%
                  </p>
                </div>
                <div className="bg-gray-950 rounded-lg p-4">
                  <p className="text-gray-400 text-sm">Sharpe Ratio</p>
                  <p className={`text-2xl font-bold ${backtestSummary.sharpe_ratio >= 1 ? 'text-green-400' : 'text-yellow-400'}`}>
                    {backtestSummary.sharpe_ratio.toFixed(2)}
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-gray-950 rounded-lg p-3">
                  <p className="text-gray-400 text-xs">Period</p>
                  <p className="font-semibold">{backtestSummary.start_date} to {backtestSummary.end_date}</p>
                </div>
                <div className="bg-gray-950 rounded-lg p-3">
                  <p className="text-gray-400 text-xs">Initial Capital</p>
                  <p className="font-semibold">${backtestSummary.initial_capital.toLocaleString()}</p>
                </div>
                <div className="bg-gray-950 rounded-lg p-3">
                  <p className="text-gray-400 text-xs">Final Equity</p>
                  <p className={`font-semibold ${backtestSummary.final_equity >= backtestSummary.initial_capital ? 'text-green-400' : 'text-red-400'}`}>
                    ${backtestSummary.final_equity.toLocaleString()}
                  </p>
                </div>
                <div className="bg-gray-950 rounded-lg p-3">
                  <p className="text-gray-400 text-xs">Total Trades</p>
                  <p className="font-semibold">
                    {backtestSummary.total_trades} ({backtestSummary.winning_trades}W / {backtestSummary.losing_trades}L)
                  </p>
                </div>
              </div>

              {/* Data Quality - HONEST DISCLOSURE */}
              {dataQuality && (
                <div className="mt-4 bg-gray-950 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Database className="w-5 h-5 text-gray-400" />
                    <h3 className="font-semibold">Data Quality & Sources</h3>
                  </div>
                  <div className="flex items-center gap-4 mb-3">
                    <div>
                      <span className={`px-3 py-1 rounded-full text-sm font-semibold ${
                        dataQuality.quality_verdict === 'HIGH' ? 'bg-green-500/20 text-green-400' :
                        dataQuality.quality_verdict === 'MEDIUM' ? 'bg-yellow-500/20 text-yellow-400' :
                        'bg-red-500/20 text-red-400'
                      }`}>
                        {dataQuality.quality_verdict} CONFIDENCE
                      </span>
                    </div>
                    <div className="text-sm text-gray-400">
                      {dataQuality.real_data_pct.toFixed(1)}% real data ({dataQuality.real_data_points} real, {dataQuality.estimated_data_points} estimated)
                    </div>
                  </div>
                  {/* Honest data source disclosure */}
                  <div className="text-xs text-gray-500 space-y-1 border-t border-gray-800 pt-2">
                    <p className="font-semibold text-gray-400">What counts as "real" data:</p>
                    <p>✓ Option prices: From Polygon.io historical data</p>
                    <p>✓ VIX levels: From Polygon.io (historical lookup per trade date)</p>
                    <p>✓ IV Rank: Calculated from VIX history (252-day lookback)</p>
                    <p>✓ SPX returns: Calculated from Polygon.io price data</p>
                    <p className="text-yellow-500/80">⚠ GEX/Dealer Gamma: Not available (requires Trading Volatility subscription)</p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* NO BACKTEST YET */}
          {!backtestSummary && !runningBacktest && (
            <div className="bg-gray-900 border-2 border-dashed border-gray-700 rounded-lg p-12 text-center">
              <BarChart3 className="w-16 h-16 mx-auto mb-4 text-gray-600" />
              <h2 className="text-2xl font-bold mb-2">No Backtest Results Yet</h2>
              <p className="text-gray-400 mb-6">
                Click "Run Backtest" to see how this strategy would have performed on historical data.
              </p>
              <button
                onClick={runBacktest}
                className="px-8 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg font-semibold flex items-center gap-2 mx-auto"
              >
                <PlayCircle className="w-5 h-5" />
                Run Backtest Now
              </button>
            </div>
          )}

          {/* RUNNING STATE */}
          {runningBacktest && (
            <div className="bg-blue-500/10 border border-blue-500 rounded-lg p-6 text-center">
              <RefreshCw className="w-12 h-12 mx-auto mb-4 text-blue-400 animate-spin" />
              <h2 className="text-xl font-bold mb-2">Running SPX Backtest...</h2>
              <p className="text-gray-400">
                Testing 20-delta put selling strategy with 45 DTE on historical SPX data.
                This may take a minute.
              </p>
            </div>
          )}

          {/* ML DECISION LOGS - FULL TRANSPARENCY */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <button
                onClick={() => setShowLogs(!showLogs)}
                className="flex items-center gap-3"
              >
                <FileText className="w-6 h-6 text-cyan-400" />
                <h2 className="text-xl font-bold">ML Decision Logs</h2>
                <span className="text-sm text-gray-400">({mlLogs.length} entries)</span>
                {showLogs ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
              </button>
              <button
                onClick={fetchLogs}
                disabled={logsLoading}
                className="px-3 py-1 bg-gray-800 hover:bg-gray-700 rounded text-sm flex items-center gap-2"
              >
                <RefreshCw className={`w-4 h-4 ${logsLoading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>

            {showLogs && (
              <>
                {mlLogs.length === 0 ? (
                  <div className="text-center py-8 text-gray-400">
                    <FileText className="w-12 h-12 mx-auto mb-3 text-gray-600" />
                    <p>No ML activity logged yet</p>
                    <p className="text-sm mt-1">Run a backtest to see ML decisions here</p>
                  </div>
                ) : (
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {mlLogs.map((log) => (
                      <div
                        key={log.id}
                        className={`p-3 rounded-lg border ${
                          log.action === 'AUTO_TRAIN' ? 'bg-purple-500/10 border-purple-500/30' :
                          log.action === 'SCORE_TRADE' ? 'bg-blue-500/10 border-blue-500/30' :
                          log.action === 'AUTO_RECORD_TRADE' ? 'bg-green-500/10 border-green-500/30' :
                          'bg-gray-800 border-gray-700'
                        }`}
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex items-center gap-2">
                            <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                              log.action === 'AUTO_TRAIN' ? 'bg-purple-500/30 text-purple-300' :
                              log.action === 'SCORE_TRADE' ? 'bg-blue-500/30 text-blue-300' :
                              log.action === 'AUTO_RECORD_TRADE' ? 'bg-green-500/30 text-green-300' :
                              'bg-gray-700 text-gray-300'
                            }`}>
                              {log.action.replace(/_/g, ' ')}
                            </span>
                            {log.recommendation && (
                              <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                                log.recommendation === 'WIN' || log.recommendation === 'TRADE' || log.recommendation === 'TRAINED' ? 'bg-green-500/30 text-green-300' :
                                log.recommendation === 'LOSS' || log.recommendation === 'SKIP' ? 'bg-red-500/30 text-red-300' :
                                'bg-yellow-500/30 text-yellow-300'
                              }`}>
                                {log.recommendation}
                              </span>
                            )}
                            {log.ml_score !== null && (
                              <span className="text-xs text-gray-400">
                                Score: {(log.ml_score * 100).toFixed(1)}%
                              </span>
                            )}
                          </div>
                          <span className="text-xs text-gray-500">
                            {log.timestamp ? new Date(log.timestamp).toLocaleString() : 'N/A'}
                          </span>
                        </div>

                        {log.reasoning && (
                          <p className="text-sm text-gray-300 mt-2">{log.reasoning}</p>
                        )}

                        {log.details && (
                          <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                            {log.details.strike && (
                              <div className="bg-gray-900/50 rounded px-2 py-1">
                                <span className="text-gray-500">Strike:</span>{' '}
                                <span className="text-gray-300">${log.details.strike}</span>
                              </div>
                            )}
                            {log.details.underlying && (
                              <div className="bg-gray-900/50 rounded px-2 py-1">
                                <span className="text-gray-500">SPX:</span>{' '}
                                <span className="text-gray-300">${log.details.underlying}</span>
                              </div>
                            )}
                            {log.details.pnl !== undefined && (
                              <div className="bg-gray-900/50 rounded px-2 py-1">
                                <span className="text-gray-500">P&L:</span>{' '}
                                <span className={log.details.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                                  ${log.details.pnl?.toFixed(2)}
                                </span>
                              </div>
                            )}
                            {log.details.accuracy && (
                              <div className="bg-gray-900/50 rounded px-2 py-1">
                                <span className="text-gray-500">Accuracy:</span>{' '}
                                <span className="text-green-400">{(log.details.accuracy * 100).toFixed(1)}%</span>
                              </div>
                            )}
                            {log.details.samples && (
                              <div className="bg-gray-900/50 rounded px-2 py-1">
                                <span className="text-gray-500">Samples:</span>{' '}
                                <span className="text-gray-300">{log.details.samples}</span>
                              </div>
                            )}
                            {log.details.vix && (
                              <div className="bg-gray-900/50 rounded px-2 py-1">
                                <span className="text-gray-500">VIX:</span>{' '}
                                <span className="text-gray-300">{log.details.vix?.toFixed(1)}</span>
                              </div>
                            )}
                            {log.details.iv_rank && (
                              <div className="bg-gray-900/50 rounded px-2 py-1">
                                <span className="text-gray-500">IV Rank:</span>{' '}
                                <span className="text-gray-300">{log.details.iv_rank?.toFixed(0)}%</span>
                              </div>
                            )}
                            {log.details.data_quality_pct !== undefined && (
                              <div className="bg-gray-900/50 rounded px-2 py-1">
                                <span className="text-gray-500">Data Quality:</span>{' '}
                                <span className={log.details.data_quality_pct >= 70 ? 'text-green-400' : 'text-yellow-400'}>
                                  {log.details.data_quality_pct?.toFixed(0)}%
                                </span>
                              </div>
                            )}
                          </div>
                        )}

                        {log.trade_id && (
                          <div className="mt-1 text-xs text-gray-500">
                            Trade: {log.trade_id}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>

        </div>
      </main>
    </div>
  )
}
