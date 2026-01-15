'use client'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import { api, apiClient } from '@/lib/api'
import useSWR from 'swr'
import {
  Brain,
  AlertTriangle,
  CheckCircle,
  XCircle,
  RefreshCw,
  Database,
  Zap,
  Target,
  BarChart3,
  Activity,
  Clock,
  TrendingUp,
  TrendingDown,
  Filter,
  Calendar,
  ArrowUpRight,
  ArrowDownRight,
  Flame,
  Shield,
  Eye,
  FileText,
  Settings,
  ChevronRight,
  Play,
  Pause,
  Calculator,
  Send,
  CheckSquare,
  Square,
  DollarSign,
  Loader2
} from 'lucide-react'

// API fetcher for SWR
const fetcher = (url: string) => api.get(url).then(res => res.data)

interface MLStatus {
  ml_library_available: boolean
  model_trained: boolean
  model_version: string | null
  is_calibrated: boolean
  training_data_available: number
  can_train: boolean
  honest_assessment: string
  what_ml_can_do: string[]
  what_ml_cannot_do: string[]
  training_metrics?: {
    accuracy: number
    precision: number
    recall: number
    cv_accuracy_mean: number
    calibration_error: number | null
  }
  performance?: {
    total_predictions: number
    wins: number
    losses: number
    win_rate: number
    total_pnl: number
  }
}

interface Feature {
  rank: number
  name: string
  importance: number
  importance_pct: number
  meaning: string
}

interface Log {
  id: number
  timestamp: string
  log_type: string
  action: string
  ml_score: number | null
  recommendation: string | null
  reasoning: string | null
  trade_id: string | null
  details: any
}

interface TrainingHistory {
  training_id: string
  training_date: string
  accuracy: number
  precision_score: number
  cv_accuracy_mean: number
  is_calibrated: boolean
  model_version: string
  total_samples: number
}

interface PendingTrade {
  trade_id: string
  trade_date: string
  strike: number
  underlying_price: number
  dte: number
  delta: number
  premium: number
  vix: number
  iv_rank: number
  created_at: string
}

interface MarketData {
  vix: number
  iv_rank: number
  vix_percentile: number
  vix_term_structure: number
  put_wall_distance_pct: number
  call_wall_distance_pct: number
  net_gex: number
  spx_20d_return: number
  spx_5d_return: number
  spx_distance_from_high: number
  iv: number
}

export default function PrometheusPage() {
  const [activeTab, setActiveTab] = useState<'overview' | 'features' | 'performance' | 'logs' | 'training' | 'strategy'>('overview')
  const [training, setTraining] = useState(false)
  const [logFilter, setLogFilter] = useState<string>('')

  // Quick Predict form state
  const [quickPredictForm, setQuickPredictForm] = useState({
    strike: '',
    underlying_price: '',
    dte: '0',
    delta: '-0.15',
    premium: '',
    trade_id: '',
    record_entry: false
  })
  const [quickPredicting, setQuickPredicting] = useState(false)
  const [quickPredictResult, setQuickPredictResult] = useState<any>(null)

  // Outcome recording state
  const [selectedTrade, setSelectedTrade] = useState<PendingTrade | null>(null)
  const [outcomeForm, setOutcomeForm] = useState({
    outcome: 'WIN',
    pnl: ''
  })
  const [recordingOutcome, setRecordingOutcome] = useState(false)

  // SWR hooks for data fetching
  const { data: statusData, isLoading: statusLoading, mutate: mutateStatus } = useSWR<MLStatus>(
    '/api/prometheus/status',
    fetcher,
    { refreshInterval: 30000 }
  )

  // API response wrapper type
  type ApiResponse<T> = { success: boolean; data: T }

  const { data: featuresData, mutate: mutateFeatures } = useSWR<ApiResponse<{ features: Feature[] }>>(
    activeTab === 'features' ? '/api/prometheus/feature-importance' : null,
    fetcher
  )

  const { data: logsData, mutate: mutateLogs } = useSWR<ApiResponse<{ logs: Log[] }>>(
    activeTab === 'logs' ? '/api/prometheus/logs?limit=100' : null,
    fetcher,
    { refreshInterval: 10000 }
  )

  const { data: trainingHistoryData } = useSWR<ApiResponse<{ history: TrainingHistory[] }>>(
    activeTab === 'training' ? '/api/prometheus/training-history' : null,
    fetcher
  )

  const { data: performanceData } = useSWR<ApiResponse<any>>(
    activeTab === 'performance' ? '/api/prometheus/performance' : null,
    fetcher
  )

  const { data: pendingTradesData, mutate: mutatePendingTrades } = useSWR<ApiResponse<{ trades: PendingTrade[] }>>(
    activeTab === 'overview' ? '/api/prometheus/pending-trades' : null,
    fetcher,
    { refreshInterval: 60000 }
  )

  const { data: marketDataRes } = useSWR<ApiResponse<MarketData>>(
    activeTab === 'overview' ? '/api/prometheus/market-data' : null,
    fetcher,
    { refreshInterval: 60000 }
  )

  // Status endpoint returns data at root level (not wrapped)
  const status = statusData
  // Other endpoints wrap data in { success, data: {...} } format
  const features = featuresData?.data?.features || []
  const logs = logsData?.data?.logs || []
  const trainingHistory = trainingHistoryData?.data?.history || []
  const pendingTrades: PendingTrade[] = pendingTradesData?.data?.trades || []
  const marketData: MarketData | null = marketDataRes?.data || null

  const handleTrain = async () => {
    setTraining(true)
    try {
      await api.post('/api/prometheus/train', { min_samples: 30, calibrate: true })
      mutateStatus()
      mutateFeatures()
    } catch (e) {
      console.error('Training failed:', e)
    }
    setTraining(false)
  }

  const handleRefresh = () => {
    mutateStatus()
    if (activeTab === 'logs') mutateLogs()
    if (activeTab === 'features') mutateFeatures()
    if (activeTab === 'overview') {
      mutatePendingTrades()
    }
  }

  const handleQuickPredict = async (e: React.FormEvent) => {
    e.preventDefault()
    setQuickPredicting(true)
    setQuickPredictResult(null)

    try {
      const response = await api.post('/api/prometheus/quick-predict', {
        strike: parseFloat(quickPredictForm.strike),
        underlying_price: parseFloat(quickPredictForm.underlying_price),
        dte: parseInt(quickPredictForm.dte),
        delta: parseFloat(quickPredictForm.delta),
        premium: parseFloat(quickPredictForm.premium),
        trade_id: quickPredictForm.trade_id || undefined,
        record_entry: quickPredictForm.record_entry
      })

      setQuickPredictResult(response.data)

      if (quickPredictForm.record_entry) {
        mutatePendingTrades()
      }
    } catch (error: any) {
      console.error('Quick predict failed:', error)
      setQuickPredictResult({
        success: false,
        error: error.response?.data?.detail || error.message || 'Prediction failed'
      })
    }

    setQuickPredicting(false)
  }

  const handleRecordOutcome = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedTrade) return

    setRecordingOutcome(true)

    try {
      await api.post('/api/prometheus/record-outcome', {
        trade_id: selectedTrade.trade_id,
        outcome: outcomeForm.outcome,
        pnl: parseFloat(outcomeForm.pnl),
        was_traded: true
      })

      setSelectedTrade(null)
      setOutcomeForm({ outcome: 'WIN', pnl: '' })
      mutatePendingTrades()
      mutateStatus()
    } catch (error) {
      console.error('Failed to record outcome:', error)
    }

    setRecordingOutcome(false)
  }

  const getRecommendationStyle = (rec: string) => {
    switch (rec) {
      case 'STRONG_TRADE':
        return 'bg-green-900/50 text-green-300 border-green-700'
      case 'TRADE':
        return 'bg-blue-900/50 text-blue-300 border-blue-700'
      case 'NEUTRAL':
        return 'bg-yellow-900/50 text-yellow-300 border-yellow-700'
      case 'CAUTION':
        return 'bg-orange-900/50 text-orange-300 border-orange-700'
      case 'SKIP':
        return 'bg-red-900/50 text-red-300 border-red-700'
      default:
        return 'bg-gray-800 text-gray-300 border-gray-700'
    }
  }

  const getLogTypeStyle = (type: string) => {
    switch (type) {
      case 'PREDICTION':
        return 'bg-purple-900/50 text-purple-300'
      case 'TRAINING':
        return 'bg-blue-900/50 text-blue-300'
      case 'OUTCOME':
        return 'bg-green-900/50 text-green-300'
      case 'ERROR':
        return 'bg-red-900/50 text-red-300'
      default:
        return 'bg-gray-800 text-gray-300'
    }
  }

  const filteredLogs = logs.filter(log => {
    if (!logFilter) return true
    return (
      log.log_type.toLowerCase().includes(logFilter.toLowerCase()) ||
      log.action.toLowerCase().includes(logFilter.toLowerCase()) ||
      (log.reasoning && log.reasoning.toLowerCase().includes(logFilter.toLowerCase()))
    )
  })

  // Static strategy explanation (since there's no backend endpoint)
  const strategyExplanation = {
    strategy: 'SPX Cash-Secured Put Selling',
    why_it_works: {
      theta_decay: {
        explanation: 'Options lose value as time passes (theta decay). As the seller, you collect this premium.',
        you_benefit: 'Daily theta decay puts money in your pocket'
      },
      volatility_premium: {
        explanation: 'Implied volatility often exceeds realized volatility. Sellers capture this premium.',
        you_benefit: 'Options are typically overpriced, giving sellers an edge'
      },
      market_tendency: {
        explanation: 'Markets trend upward over time, making puts expire worthless more often.',
        you_benefit: '~68% of puts expire OTM historically'
      }
    },
    why_it_can_fail: {
      black_swan: {
        explanation: 'Sudden market crashes can result in massive losses that wipe out months of gains.'
      },
      assignment_risk: {
        explanation: 'If SPX drops below your strike, you may be assigned and face large unrealized losses.'
      },
      vol_expansion: {
        explanation: 'During market stress, VIX spikes can increase option prices against you.'
      }
    },
    realistic_expectations: {
      win_rate: '65-72%',
      avg_win: '$300-600',
      avg_loss: '$1,000-2,500',
      monthly_return: '2-5%',
      max_drawdown: '15-30%'
    },
    bottom_line: 'This strategy works when you consistently sell puts with good premium, manage position size, and accept that occasional large losses are part of the game. ML helps identify favorable conditions but cannot eliminate the inherent risks.'
  }

  return (
    <div className="flex h-screen bg-gray-900">
      <Navigation />

      <div className="flex-1 overflow-auto p-8 pt-20">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="mb-8 flex justify-between items-start">
            <div>
              <h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-3">
                <Flame className="w-8 h-8 text-orange-400" />
                PROMETHEUS
              </h1>
              <p className="text-gray-400">
                Predictive Risk Optimization Through Machine Evaluation & Training for Honest Earnings Utility System
              </p>
              {status?.model_version && (
                <p className="text-sm text-purple-400 mt-1 flex items-center gap-2">
                  <Shield className="w-4 h-4" />
                  Model: {status.model_version}
                  {status.is_calibrated && (
                    <span className="bg-green-900/50 text-green-300 text-xs px-2 py-0.5 rounded">
                      Calibrated
                    </span>
                  )}
                </p>
              )}
            </div>
            <button
              onClick={handleRefresh}
              className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400"
            >
              <RefreshCw className={`w-5 h-5 ${statusLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {/* Tabs */}
          <div className="flex gap-2 mb-6 flex-wrap">
            {[
              { id: 'overview', label: 'Overview', icon: Target },
              { id: 'features', label: 'Features', icon: BarChart3 },
              { id: 'performance', label: 'Performance', icon: Activity },
              { id: 'training', label: 'Training', icon: Zap },
              { id: 'logs', label: 'Logs', icon: FileText },
              { id: 'strategy', label: 'Strategy', icon: Brain }
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2 ${
                  activeTab === tab.id
                    ? 'bg-orange-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </button>
            ))}
          </div>

          {statusLoading && !status ? (
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-orange-500"></div>
            </div>
          ) : (
            <>
              {/* Overview Tab */}
              {activeTab === 'overview' && (
                <div className="space-y-6">
                  {/* Status Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                    {/* ML Status */}
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <div className="flex items-center gap-3 mb-4">
                        {status?.model_trained ? (
                          <CheckCircle className="w-6 h-6 text-green-400" />
                        ) : (
                          <AlertTriangle className="w-6 h-6 text-yellow-400" />
                        )}
                        <h3 className="text-lg font-semibold text-white">Model Status</h3>
                      </div>
                      <p className={status?.model_trained ? 'text-green-400' : 'text-yellow-400'}>
                        {status?.model_trained ? 'Trained & Ready' : 'Not Trained'}
                      </p>
                      {status?.is_calibrated && (
                        <p className="text-sm text-purple-400 mt-1">Probabilities Calibrated</p>
                      )}
                    </div>

                    {/* Training Data */}
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <div className="flex items-center gap-3 mb-4">
                        <Database className="w-6 h-6 text-blue-400" />
                        <h3 className="text-lg font-semibold text-white">Training Data</h3>
                      </div>
                      <p className="text-2xl font-bold text-white">
                        {status?.training_data_available || 0}
                      </p>
                      <p className="text-sm text-gray-400">
                        {status?.can_train ? 'Ready to train' : `Need ${30 - (status?.training_data_available || 0)} more`}
                      </p>
                    </div>

                    {/* Accuracy */}
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <div className="flex items-center gap-3 mb-4">
                        <Target className="w-6 h-6 text-purple-400" />
                        <h3 className="text-lg font-semibold text-white">Accuracy</h3>
                      </div>
                      <p className="text-2xl font-bold text-white">
                        {status?.training_metrics?.accuracy
                          ? `${(status.training_metrics.accuracy * 100).toFixed(1)}%`
                          : 'N/A'}
                      </p>
                      {status?.training_metrics?.cv_accuracy_mean && (
                        <p className="text-sm text-gray-400">
                          CV: {(status.training_metrics.cv_accuracy_mean * 100).toFixed(1)}%
                        </p>
                      )}
                    </div>

                    {/* Win Rate */}
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <div className="flex items-center gap-3 mb-4">
                        <TrendingUp className="w-6 h-6 text-green-400" />
                        <h3 className="text-lg font-semibold text-white">Win Rate</h3>
                      </div>
                      <p className="text-2xl font-bold text-white">
                        {status?.performance?.win_rate
                          ? `${(status.performance.win_rate * 100).toFixed(1)}%`
                          : 'N/A'}
                      </p>
                      <p className="text-sm text-gray-400">
                        {status?.performance?.wins || 0}W / {status?.performance?.losses || 0}L
                      </p>
                    </div>
                  </div>

                  {/* Quick Predict Form */}
                  <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                    <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                      <Calculator className="w-5 h-5 text-orange-400" />
                      Quick Predict
                    </h3>
                    <p className="text-gray-400 text-sm mb-4">
                      Enter trade parameters to get an ML prediction. Market data (VIX, GEX, etc.) is fetched automatically.
                    </p>

                    <form onSubmit={handleQuickPredict} className="space-y-4">
                      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">Strike</label>
                          <input
                            type="number"
                            step="0.01"
                            value={quickPredictForm.strike}
                            onChange={(e) => setQuickPredictForm({...quickPredictForm, strike: e.target.value})}
                            placeholder="5800"
                            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-orange-500"
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">Underlying Price</label>
                          <input
                            type="number"
                            step="0.01"
                            value={quickPredictForm.underlying_price}
                            onChange={(e) => setQuickPredictForm({...quickPredictForm, underlying_price: e.target.value})}
                            placeholder="5950"
                            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-orange-500"
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">DTE</label>
                          <input
                            type="number"
                            value={quickPredictForm.dte}
                            onChange={(e) => setQuickPredictForm({...quickPredictForm, dte: e.target.value})}
                            placeholder="0"
                            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-orange-500"
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">Delta</label>
                          <input
                            type="number"
                            step="0.01"
                            value={quickPredictForm.delta}
                            onChange={(e) => setQuickPredictForm({...quickPredictForm, delta: e.target.value})}
                            placeholder="-0.15"
                            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-orange-500"
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">Premium ($)</label>
                          <input
                            type="number"
                            step="0.01"
                            value={quickPredictForm.premium}
                            onChange={(e) => setQuickPredictForm({...quickPredictForm, premium: e.target.value})}
                            placeholder="5.50"
                            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-orange-500"
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">Trade ID (optional)</label>
                          <input
                            type="text"
                            value={quickPredictForm.trade_id}
                            onChange={(e) => setQuickPredictForm({...quickPredictForm, trade_id: e.target.value})}
                            placeholder="MY-TRADE-001"
                            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-orange-500"
                          />
                        </div>
                      </div>

                      <div className="flex items-center justify-between">
                        <label className="flex items-center gap-2 text-gray-400 cursor-pointer">
                          <button
                            type="button"
                            onClick={() => setQuickPredictForm({...quickPredictForm, record_entry: !quickPredictForm.record_entry})}
                            className="p-0.5"
                          >
                            {quickPredictForm.record_entry ? (
                              <CheckSquare className="w-5 h-5 text-orange-400" />
                            ) : (
                              <Square className="w-5 h-5" />
                            )}
                          </button>
                          Record as trade entry (for outcome tracking)
                        </label>

                        <button
                          type="submit"
                          disabled={quickPredicting}
                          className="px-6 py-2 bg-orange-600 hover:bg-orange-700 disabled:bg-gray-600 text-white font-medium rounded-lg flex items-center gap-2"
                        >
                          {quickPredicting ? (
                            <>
                              <Loader2 className="w-4 h-4 animate-spin" />
                              Predicting...
                            </>
                          ) : (
                            <>
                              <Send className="w-4 h-4" />
                              Get Prediction
                            </>
                          )}
                        </button>
                      </div>
                    </form>

                    {/* Prediction Result */}
                    {quickPredictResult && (
                      <div className={`mt-4 p-4 rounded-lg border ${
                        quickPredictResult.success === false
                          ? 'bg-red-900/30 border-red-700'
                          : 'bg-gray-900 border-gray-700'
                      }`}>
                        {quickPredictResult.success === false ? (
                          <p className="text-red-400">{quickPredictResult.error}</p>
                        ) : (
                          <div className="space-y-3">
                            <div className="flex items-center justify-between">
                              <span className="text-gray-400">Win Probability:</span>
                              <span className={`text-2xl font-bold ${
                                quickPredictResult.data?.win_probability > 0.7 ? 'text-green-400' :
                                quickPredictResult.data?.win_probability > 0.5 ? 'text-yellow-400' : 'text-red-400'
                              }`}>
                                {((quickPredictResult.data?.win_probability || 0) * 100).toFixed(1)}%
                              </span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-gray-400">Recommendation:</span>
                              <span className={`px-3 py-1 rounded text-sm font-medium border ${
                                getRecommendationStyle(quickPredictResult.data?.recommendation || '')
                              }`}>
                                {quickPredictResult.data?.recommendation || 'N/A'}
                              </span>
                            </div>
                            {quickPredictResult.data?.key_factors && quickPredictResult.data.key_factors.length > 0 && (
                              <div>
                                <span className="text-gray-400 text-sm">Key Factors:</span>
                                <ul className="mt-1 space-y-1">
                                  {quickPredictResult.data.key_factors.slice(0, 3).map((factor: string, i: number) => (
                                    <li key={i} className="text-sm text-gray-300 flex items-start gap-2">
                                      <ChevronRight className="w-4 h-4 text-orange-400 mt-0.5 flex-shrink-0" />
                                      {factor}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {quickPredictResult.entry_recorded && (
                              <p className="text-green-400 text-sm flex items-center gap-2">
                                <CheckCircle className="w-4 h-4" />
                                Trade entry recorded for outcome tracking
                              </p>
                            )}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Current Market Data */}
                    {marketData && (
                      <div className="mt-4 p-4 bg-gray-900 rounded-lg">
                        <p className="text-sm text-gray-500 mb-2">Current Market Data (auto-fetched):</p>
                        <div className="grid grid-cols-3 md:grid-cols-6 gap-3 text-sm">
                          <div>
                            <span className="text-gray-500">VIX:</span>
                            <span className={`ml-1 font-medium ${
                              marketData.vix > 25 ? 'text-red-400' : marketData.vix > 18 ? 'text-yellow-400' : 'text-green-400'
                            }`}>
                              {marketData.vix?.toFixed(2) || 'N/A'}
                            </span>
                          </div>
                          <div>
                            <span className="text-gray-500">IV Rank:</span>
                            <span className="ml-1 text-white">{marketData.iv_rank?.toFixed(0) || 'N/A'}%</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Net GEX:</span>
                            <span className={`ml-1 font-medium ${
                              (marketData.net_gex || 0) > 0 ? 'text-green-400' : 'text-red-400'
                            }`}>
                              {marketData.net_gex ? (marketData.net_gex / 1e9).toFixed(1) + 'B' : 'N/A'}
                            </span>
                          </div>
                          <div>
                            <span className="text-gray-500">Put Wall:</span>
                            <span className="ml-1 text-white">{marketData.put_wall_distance_pct?.toFixed(1) || 'N/A'}%</span>
                          </div>
                          <div>
                            <span className="text-gray-500">5D Return:</span>
                            <span className={`ml-1 ${
                              (marketData.spx_5d_return || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                            }`}>
                              {marketData.spx_5d_return?.toFixed(2) || 'N/A'}%
                            </span>
                          </div>
                          <div>
                            <span className="text-gray-500">From High:</span>
                            <span className="ml-1 text-white">{marketData.spx_distance_from_high?.toFixed(1) || 'N/A'}%</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Pending Trades */}
                  <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                        <Clock className="w-5 h-5 text-orange-400" />
                        Pending Trades ({pendingTrades.length})
                      </h3>
                      <button
                        onClick={() => mutatePendingTrades()}
                        className="p-1.5 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-400"
                      >
                        <RefreshCw className="w-4 h-4" />
                      </button>
                    </div>

                    {pendingTrades.length > 0 ? (
                      <div className="space-y-3">
                        {pendingTrades.map((trade) => (
                          <div
                            key={trade.trade_id}
                            className={`p-4 rounded-lg border ${
                              selectedTrade?.trade_id === trade.trade_id
                                ? 'bg-orange-900/30 border-orange-600'
                                : 'bg-gray-900 border-gray-700 hover:border-gray-600'
                            } cursor-pointer transition-colors`}
                            onClick={() => setSelectedTrade(trade)}
                          >
                            <div className="flex items-center justify-between">
                              <div>
                                <p className="text-white font-medium">{trade.trade_id}</p>
                                <p className="text-sm text-gray-400">
                                  Strike: ${trade.strike?.toFixed(0)} | Δ: {trade.delta?.toFixed(2)} | DTE: {trade.dte}
                                </p>
                              </div>
                              <div className="text-right">
                                <p className="text-green-400 font-medium">${trade.premium?.toFixed(2)}</p>
                                <p className="text-xs text-gray-500">
                                  {new Date(trade.created_at).toLocaleDateString()}
                                </p>
                              </div>
                            </div>
                          </div>
                        ))}

                        {/* Outcome Recording Form */}
                        {selectedTrade && (
                          <div className="mt-4 p-4 bg-gray-900 rounded-lg border border-orange-600">
                            <h4 className="text-white font-medium mb-3">
                              Record Outcome for {selectedTrade.trade_id}
                            </h4>
                            <form onSubmit={handleRecordOutcome} className="flex items-end gap-4">
                              <div>
                                <label className="block text-sm text-gray-400 mb-1">Outcome</label>
                                <select
                                  value={outcomeForm.outcome}
                                  onChange={(e) => setOutcomeForm({...outcomeForm, outcome: e.target.value})}
                                  className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-orange-500"
                                >
                                  <option value="WIN">WIN</option>
                                  <option value="LOSS">LOSS</option>
                                </select>
                              </div>
                              <div className="flex-1">
                                <label className="block text-sm text-gray-400 mb-1">P&L ($)</label>
                                <input
                                  type="number"
                                  step="0.01"
                                  value={outcomeForm.pnl}
                                  onChange={(e) => setOutcomeForm({...outcomeForm, pnl: e.target.value})}
                                  placeholder={outcomeForm.outcome === 'WIN' ? '550' : '-1200'}
                                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-orange-500"
                                  required
                                />
                              </div>
                              <button
                                type="submit"
                                disabled={recordingOutcome}
                                className="px-4 py-2 bg-orange-600 hover:bg-orange-700 disabled:bg-gray-600 text-white font-medium rounded-lg flex items-center gap-2"
                              >
                                {recordingOutcome ? (
                                  <Loader2 className="w-4 h-4 animate-spin" />
                                ) : (
                                  <DollarSign className="w-4 h-4" />
                                )}
                                Record
                              </button>
                              <button
                                type="button"
                                onClick={() => setSelectedTrade(null)}
                                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
                              >
                                Cancel
                              </button>
                            </form>
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="text-gray-400 text-sm">
                        No pending trades. Use Quick Predict with "Record as trade entry" checked to add trades.
                      </p>
                    )}
                  </div>

                  {/* Honest Assessment */}
                  <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                    <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                      <Eye className="w-5 h-5 text-orange-400" />
                      Honest Assessment
                    </h3>
                    <p className="text-gray-300 text-lg">{status?.honest_assessment}</p>
                  </div>

                  {/* What ML Can/Cannot Do */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="bg-gray-800 rounded-lg p-6 border border-green-900/50">
                      <h3 className="text-lg font-semibold text-green-400 mb-4 flex items-center gap-2">
                        <CheckCircle className="w-5 h-5" />
                        What Prometheus CAN Do
                      </h3>
                      <ul className="space-y-2">
                        {status?.what_ml_can_do?.map((item, i) => (
                          <li key={i} className="flex items-start gap-2 text-gray-300">
                            <ChevronRight className="w-4 h-4 text-green-400 mt-1 flex-shrink-0" />
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div className="bg-gray-800 rounded-lg p-6 border border-red-900/50">
                      <h3 className="text-lg font-semibold text-red-400 mb-4 flex items-center gap-2">
                        <XCircle className="w-5 h-5" />
                        What Prometheus CANNOT Do
                      </h3>
                      <ul className="space-y-2">
                        {status?.what_ml_cannot_do?.map((item, i) => (
                          <li key={i} className="flex items-start gap-2 text-gray-300">
                            <ChevronRight className="w-4 h-4 text-red-400 mt-1 flex-shrink-0" />
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  {/* Train Button */}
                  {status?.can_train && (
                    <div className="flex justify-center">
                      <button
                        onClick={handleTrain}
                        disabled={training}
                        className="px-8 py-4 bg-orange-600 hover:bg-orange-700 disabled:bg-gray-600 text-white font-medium rounded-lg flex items-center gap-3 text-lg"
                      >
                        {training ? (
                          <>
                            <RefreshCw className="w-6 h-6 animate-spin" />
                            Training Prometheus...
                          </>
                        ) : (
                          <>
                            <Flame className="w-6 h-6" />
                            Train Prometheus Model
                          </>
                        )}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Features Tab */}
              {activeTab === 'features' && (
                <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                  <h3 className="text-lg font-semibold text-white mb-6 flex items-center gap-2">
                    <BarChart3 className="w-5 h-5 text-orange-400" />
                    Feature Importance Analysis
                  </h3>
                  {features.length > 0 ? (
                    <div className="space-y-4">
                      {features.map((feature, i) => (
                        <div key={i} className="space-y-2">
                          <div className="flex justify-between items-center">
                            <div className="flex items-center gap-2">
                              <span className="text-gray-500 text-sm w-6">#{feature.rank}</span>
                              <span className="text-white font-medium">{feature.name}</span>
                            </div>
                            <span className="text-orange-400 font-bold">
                              {feature.importance_pct.toFixed(1)}%
                            </span>
                          </div>
                          <div className="w-full bg-gray-700 rounded-full h-3">
                            <div
                              className="bg-gradient-to-r from-orange-600 to-orange-400 h-3 rounded-full transition-all duration-500"
                              style={{ width: `${Math.min(feature.importance_pct * 2, 100)}%` }}
                            />
                          </div>
                          <p className="text-sm text-gray-400 pl-8">{feature.meaning}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-gray-400">Train the model to see feature importance</p>
                  )}
                </div>
              )}

              {/* Performance Tab */}
              {activeTab === 'performance' && (
                <div className="space-y-6">
                  {/* Performance Summary */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <p className="text-gray-400 text-sm mb-1">Total Predictions</p>
                      <p className="text-3xl font-bold text-white">
                        {performanceData?.data?.total_predictions || status?.performance?.total_predictions || 0}
                      </p>
                    </div>
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <p className="text-gray-400 text-sm mb-1">Prediction Accuracy</p>
                      <p className="text-3xl font-bold text-green-400">
                        {performanceData?.data?.prediction_accuracy
                          ? `${(performanceData.data.prediction_accuracy * 100).toFixed(1)}%`
                          : 'N/A'}
                      </p>
                    </div>
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <p className="text-gray-400 text-sm mb-1">Total P&L</p>
                      <p className={`text-3xl font-bold ${
                        (performanceData?.data?.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                      }`}>
                        ${(performanceData?.data?.total_pnl || status?.performance?.total_pnl || 0).toLocaleString()}
                      </p>
                    </div>
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <p className="text-gray-400 text-sm mb-1">Calibration Error</p>
                      <p className="text-3xl font-bold text-purple-400">
                        {performanceData?.data?.calibration_error
                          ? `${(performanceData.data.calibration_error * 100).toFixed(2)}%`
                          : 'N/A'}
                      </p>
                    </div>
                  </div>

                  {/* Calibration Chart Placeholder */}
                  <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                    <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                      <Activity className="w-5 h-5 text-orange-400" />
                      Probability Calibration
                    </h3>
                    <p className="text-gray-400">
                      Calibration shows how well predicted probabilities match actual outcomes.
                      A well-calibrated model should have predictions close to the diagonal line.
                    </p>
                    <div className="mt-4 p-4 bg-gray-900 rounded-lg">
                      <p className="text-sm text-gray-500">
                        {status?.is_calibrated
                          ? 'Model is calibrated using isotonic regression.'
                          : 'Model uses raw probabilities (not calibrated).'}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Training History Tab */}
              {activeTab === 'training' && (
                <div className="space-y-6">
                  <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
                    <div className="p-4 border-b border-gray-700">
                      <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                        <Zap className="w-5 h-5 text-orange-400" />
                        Training History
                      </h3>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead className="bg-gray-900">
                          <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Date</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Version</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Samples</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Accuracy</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">CV Score</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Calibrated</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-700">
                          {trainingHistory.length > 0 ? (
                            trainingHistory.map((training, i) => (
                              <tr key={i} className="hover:bg-gray-700/50">
                                <td className="px-4 py-3 text-sm text-gray-300">
                                  {new Date(training.training_date).toLocaleDateString()}
                                </td>
                                <td className="px-4 py-3 text-sm text-purple-400">
                                  {training.model_version}
                                </td>
                                <td className="px-4 py-3 text-sm text-white">
                                  {training.total_samples}
                                </td>
                                <td className="px-4 py-3 text-sm text-green-400">
                                  {(training.accuracy * 100).toFixed(1)}%
                                </td>
                                <td className="px-4 py-3 text-sm text-blue-400">
                                  {(training.cv_accuracy_mean * 100).toFixed(1)}%
                                </td>
                                <td className="px-4 py-3">
                                  {training.is_calibrated ? (
                                    <CheckCircle className="w-4 h-4 text-green-400" />
                                  ) : (
                                    <XCircle className="w-4 h-4 text-gray-500" />
                                  )}
                                </td>
                              </tr>
                            ))
                          ) : (
                            <tr>
                              <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                                No training history yet
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Training Metrics Details */}
                  {status?.training_metrics && (
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <h3 className="text-lg font-semibold text-white mb-4">Current Model Metrics</h3>
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                        <div>
                          <p className="text-gray-400 text-sm">Accuracy</p>
                          <p className="text-xl font-bold text-white">
                            {(status.training_metrics.accuracy * 100).toFixed(1)}%
                          </p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">Precision</p>
                          <p className="text-xl font-bold text-white">
                            {(status.training_metrics.precision * 100).toFixed(1)}%
                          </p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">Recall</p>
                          <p className="text-xl font-bold text-white">
                            {(status.training_metrics.recall * 100).toFixed(1)}%
                          </p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">CV Score</p>
                          <p className="text-xl font-bold text-white">
                            {(status.training_metrics.cv_accuracy_mean * 100).toFixed(1)}%
                          </p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">Calibration Error</p>
                          <p className="text-xl font-bold text-white">
                            {status.training_metrics.calibration_error
                              ? `${(status.training_metrics.calibration_error * 100).toFixed(2)}%`
                              : 'N/A'}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Logs Tab */}
              {activeTab === 'logs' && (
                <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
                  <div className="p-4 border-b border-gray-700 flex justify-between items-center">
                    <div>
                      <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                        <FileText className="w-5 h-5 text-orange-400" />
                        Decision Logs
                      </h3>
                      <p className="text-sm text-gray-400">Complete transparency on all ML decisions</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="relative">
                        <Filter className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                        <input
                          type="text"
                          placeholder="Filter logs..."
                          value={logFilter}
                          onChange={(e) => setLogFilter(e.target.value)}
                          className="pl-10 pr-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:border-orange-500"
                        />
                      </div>
                      <button
                        onClick={() => mutateLogs()}
                        className="p-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-400"
                      >
                        <RefreshCw className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                  <div className="max-h-[600px] overflow-y-auto">
                    <table className="w-full">
                      <thead className="bg-gray-900 sticky top-0">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Time</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Type</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Action</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Score</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Recommendation</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Details</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-700">
                        {filteredLogs.length > 0 ? (
                          filteredLogs.map((log) => (
                            <tr key={log.id} className="hover:bg-gray-700/50">
                              <td className="px-4 py-3 text-sm text-gray-400">
                                {new Date(log.timestamp).toLocaleString()}
                              </td>
                              <td className="px-4 py-3">
                                <span className={`px-2 py-1 rounded text-xs font-medium ${getLogTypeStyle(log.log_type)}`}>
                                  {log.log_type}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-sm text-white">
                                {log.action}
                              </td>
                              <td className="px-4 py-3 text-sm">
                                {log.ml_score !== null ? (
                                  <span className={log.ml_score > 0.6 ? 'text-green-400' : 'text-yellow-400'}>
                                    {(log.ml_score * 100).toFixed(1)}%
                                  </span>
                                ) : (
                                  <span className="text-gray-500">-</span>
                                )}
                              </td>
                              <td className="px-4 py-3">
                                {log.recommendation && (
                                  <span className={`px-2 py-1 rounded text-xs font-medium border ${getRecommendationStyle(log.recommendation)}`}>
                                    {log.recommendation}
                                  </span>
                                )}
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-400 max-w-xs truncate">
                                {log.reasoning || '-'}
                              </td>
                            </tr>
                          ))
                        ) : (
                          <tr>
                            <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                              No logs yet. Train the model or run predictions to generate logs.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Strategy Tab */}
              {activeTab === 'strategy' && (
                <div className="space-y-6">
                  <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                    <h3 className="text-xl font-semibold text-white mb-2">{strategyExplanation.strategy}</h3>

                    {/* Why It Works */}
                    <div className="mt-6">
                      <h4 className="text-lg font-medium text-green-400 mb-4 flex items-center gap-2">
                        <TrendingUp className="w-5 h-5" />
                        Why It Works
                      </h4>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {Object.entries(strategyExplanation.why_it_works).map(([key, value]) => (
                          <div key={key} className="bg-gray-900 rounded-lg p-4 border border-green-900/30">
                            <h5 className="text-white font-medium mb-2 capitalize">
                              {key.replace(/_/g, ' ')}
                            </h5>
                            <p className="text-gray-400 text-sm">{value.explanation}</p>
                            <p className="text-green-400 text-sm mt-2">{value.you_benefit}</p>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Why It Can Fail */}
                    <div className="mt-6">
                      <h4 className="text-lg font-medium text-red-400 mb-4 flex items-center gap-2">
                        <TrendingDown className="w-5 h-5" />
                        Why It Can Fail
                      </h4>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {Object.entries(strategyExplanation.why_it_can_fail).map(([key, value]) => (
                          <div key={key} className="bg-gray-900 rounded-lg p-4 border border-red-900/30">
                            <h5 className="text-white font-medium mb-2 capitalize">
                              {key.replace(/_/g, ' ')}
                            </h5>
                            <p className="text-gray-400 text-sm">{value.explanation}</p>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Realistic Expectations */}
                    <div className="mt-6">
                      <h4 className="text-lg font-medium text-blue-400 mb-4 flex items-center gap-2">
                        <Target className="w-5 h-5" />
                        Realistic Expectations
                      </h4>
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                        {Object.entries(strategyExplanation.realistic_expectations).map(([key, value]) => (
                          <div key={key} className="bg-gray-900 rounded-lg p-4 text-center">
                            <p className="text-gray-400 text-sm capitalize">{key.replace(/_/g, ' ')}</p>
                            <p className="text-white font-bold text-lg mt-1">{String(value)}</p>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Bottom Line */}
                    <div className="mt-6 bg-orange-900/30 rounded-lg p-4 border border-orange-700">
                      <p className="text-gray-200">{strategyExplanation.bottom_line}</p>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
