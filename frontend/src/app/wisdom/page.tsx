'use client'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import { api } from '@/lib/api'
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
  ChevronRight,
  Shield,
  Eye,
  FileText,
  Sparkles,
  Award,
  Percent,
  AlertCircle,
  Info,
  BookOpen,
  Loader2
} from 'lucide-react'

// API fetcher for SWR
const fetcher = (url: string) => api.get(url).then(res => res.data)

interface MLStatus {
  ml_library_available: boolean
  model_trained: boolean
  model_version: string | null
  training_data_available: number
  can_train: boolean
  should_trust_predictions: boolean
  honest_assessment: string
  what_ml_can_do?: string[]
  what_ml_cannot_do?: string[]
  training_metrics?: {
    accuracy: number
    precision: number
    recall: number
    f1: number
    auc_roc: number
    brier_score: number
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
  action: string
  symbol: string
  ml_score: number | null
  recommendation: string | null
  reasoning: string | null
  trade_id: string | null
  details: any
}

interface DataQuality {
  total_trades: number
  wins: number
  losses: number
  win_rate: number
  total_pnl: number
  quality: string
  recommendation: string
}

interface BotMLStatus {
  bot_name: string
  ml_enabled: boolean
  ml_source: string
  min_win_probability: number
  last_prediction?: {
    win_probability: number
    advice: string
    confidence: number
    timestamp: string
  }
}

export default function SagePage() {
  const [activeTab, setActiveTab] = useState<'overview' | 'predictions' | 'features' | 'performance' | 'logs' | 'training'>('overview')
  const [training, setTraining] = useState(false)
  const [logFilter, setLogFilter] = useState('')
  const [predictionForm, setPredictionForm] = useState({
    vix: '',
    day_of_week: new Date().getDay().toString(),
    price: '',
    price_change_1d: '0',
    expected_move_pct: '1.0',
    gex_regime_positive: true
  })
  const [predicting, setPredicting] = useState(false)
  const [predictionResult, setPredictionResult] = useState<any>(null)

  // SWR hooks for data fetching with automatic revalidation
  // Use WISDOM-specific endpoints for ML Advisor data
  const { data: statusData, isLoading: statusLoading, mutate: mutateStatus } = useSWR<MLStatus>(
    '/api/ml/wisdom/status',
    fetcher,
    { refreshInterval: 30000 }
  )

  const { data: qualityData, mutate: mutateQuality } = useSWR<{ data: DataQuality }>(
    '/api/ml/data-quality',
    fetcher,
    { refreshInterval: 60000 }
  )

  const { data: featuresData, isLoading: featuresLoading, mutate: mutateFeatures } = useSWR<{ data: { features: Feature[] } }>(
    activeTab === 'features' ? '/api/ml/wisdom/feature-importance' : null,
    fetcher
  )

  const { data: logsData, isLoading: logsLoading, mutate: mutateLogs } = useSWR<{ data: { logs: Log[] } }>(
    activeTab === 'logs' ? '/api/ml/logs?limit=100' : null,
    fetcher,
    { refreshInterval: 15000 }
  )

  const { data: strategyData } = useSWR<{ data: any }>(
    activeTab === 'training' ? '/api/ml/strategy-explanation' : null,
    fetcher
  )

  const { data: botStatusData } = useSWR<{ data: { bots: BotMLStatus[] } }>(
    '/api/ml/bot-status',
    fetcher,
    { refreshInterval: 30000 }
  )

  // Extract data from responses
  const status = statusData
  const dataQuality = qualityData?.data
  const features = featuresData?.data?.features || []
  const logs = logsData?.data?.logs || []
  const strategy = strategyData?.data
  const botStatuses = botStatusData?.data?.bots || []

  const handleTrain = async () => {
    setTraining(true)
    try {
      await api.post('/api/ml/wisdom/train', { min_samples: 30, use_chronicles: true })
      mutateStatus()
      mutateQuality()
      mutateFeatures()
    } catch (e) {
      console.error('Training failed:', e)
    }
    setTraining(false)
  }

  const handleRefresh = () => {
    mutateStatus()
    mutateQuality()
    if (activeTab === 'logs') mutateLogs()
    if (activeTab === 'features') mutateFeatures()
  }

  const handlePredict = async (e: React.FormEvent) => {
    e.preventDefault()
    setPredicting(true)
    setPredictionResult(null)

    try {
      const response = await api.post('/api/ml/wisdom/predict', {
        vix: parseFloat(predictionForm.vix),
        day_of_week: parseInt(predictionForm.day_of_week),
        price: parseFloat(predictionForm.price),
        price_change_1d: parseFloat(predictionForm.price_change_1d),
        expected_move_pct: parseFloat(predictionForm.expected_move_pct),
        gex_regime_positive: predictionForm.gex_regime_positive
      })
      setPredictionResult(response.data)
    } catch (error: any) {
      setPredictionResult({
        success: false,
        error: error.response?.data?.detail || error.message || 'Prediction failed'
      })
    }

    setPredicting(false)
  }

  const getQualityColor = (quality: string) => {
    switch (quality) {
      case 'EXCELLENT': return 'text-green-400'
      case 'GOOD': return 'text-blue-400'
      case 'ADEQUATE': return 'text-yellow-400'
      case 'MINIMAL': return 'text-orange-400'
      default: return 'text-red-400'
    }
  }

  const getAdviceStyle = (advice: string) => {
    switch (advice) {
      case 'TRADE_FULL':
        return 'bg-green-900/50 text-green-300 border-green-700'
      case 'TRADE_REDUCED':
        return 'bg-blue-900/50 text-blue-300 border-blue-700'
      case 'SKIP_TODAY':
        return 'bg-red-900/50 text-red-300 border-red-700'
      default:
        return 'bg-gray-800 text-gray-300 border-gray-700'
    }
  }

  const getLogTypeStyle = (action: string) => {
    if (action.includes('TRAIN')) return 'bg-purple-900/50 text-purple-300'
    if (action.includes('PREDICT') || action.includes('SCORE')) return 'bg-blue-900/50 text-blue-300'
    if (action.includes('OUTCOME')) return 'bg-green-900/50 text-green-300'
    if (action.includes('ERROR')) return 'bg-red-900/50 text-red-300'
    return 'bg-gray-800 text-gray-300'
  }

  const filteredLogs = logs.filter(log => {
    if (!logFilter) return true
    return (
      log.action.toLowerCase().includes(logFilter.toLowerCase()) ||
      (log.reasoning && log.reasoning.toLowerCase().includes(logFilter.toLowerCase())) ||
      (log.recommendation && log.recommendation.toLowerCase().includes(logFilter.toLowerCase()))
    )
  })

  const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

  return (
    <div className="flex h-screen bg-gray-900">
      <Navigation />

      <div className="flex-1 overflow-auto p-8 pt-24 lg:pl-20">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="mb-8 flex justify-between items-start">
            <div>
              <h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-3">
                <Brain className="w-8 h-8 text-emerald-400" />
                WISDOM
              </h1>
              <p className="text-gray-400">
                Strategic Algorithmic Guidance Engine - ML-Powered Trading Intelligence
              </p>
              {status?.model_version && (
                <p className="text-sm text-emerald-400 mt-1 flex items-center gap-2">
                  <Shield className="w-4 h-4" />
                  Model: {status.model_version}
                  {status.should_trust_predictions && (
                    <span className="bg-green-900/50 text-green-300 text-xs px-2 py-0.5 rounded">
                      Trusted
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
              { id: 'predictions', label: 'Predictions', icon: Sparkles },
              { id: 'features', label: 'Features', icon: BarChart3 },
              { id: 'performance', label: 'Performance', icon: Activity },
              { id: 'logs', label: 'Decision Logs', icon: FileText },
              { id: 'training', label: 'Training', icon: Zap }
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2 ${
                  activeTab === tab.id
                    ? 'bg-emerald-600 text-white'
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
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-500"></div>
            </div>
          ) : (
            <>
              {/* Overview Tab */}
              {activeTab === 'overview' && (
                <div className="space-y-6">
                  {/* Primary Status Banner */}
                  <div className={`rounded-lg p-6 border ${
                    status?.model_trained && status?.should_trust_predictions
                      ? 'bg-emerald-900/20 border-emerald-700'
                      : status?.model_trained
                        ? 'bg-yellow-900/20 border-yellow-700'
                        : 'bg-red-900/20 border-red-700'
                  }`}>
                    <div className="flex items-center gap-4">
                      {status?.model_trained && status?.should_trust_predictions ? (
                        <CheckCircle className="w-10 h-10 text-emerald-400" />
                      ) : status?.model_trained ? (
                        <AlertTriangle className="w-10 h-10 text-yellow-400" />
                      ) : (
                        <XCircle className="w-10 h-10 text-red-400" />
                      )}
                      <div>
                        <h2 className="text-xl font-semibold text-white">
                          {status?.model_trained && status?.should_trust_predictions
                            ? 'WISDOM is Active & Trusted'
                            : status?.model_trained
                              ? 'WISDOM is Active (Limited Trust)'
                              : 'WISDOM Needs Training'}
                        </h2>
                        <p className="text-gray-400 mt-1">{status?.honest_assessment}</p>
                      </div>
                    </div>
                  </div>

                  {/* Status Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                    {/* ML Library */}
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <div className="flex items-center gap-3 mb-4">
                        {status?.ml_library_available ? (
                          <CheckCircle className="w-6 h-6 text-green-400" />
                        ) : (
                          <XCircle className="w-6 h-6 text-red-400" />
                        )}
                        <h3 className="text-lg font-semibold text-white">ML Library</h3>
                      </div>
                      <p className={status?.ml_library_available ? 'text-green-400' : 'text-red-400'}>
                        {status?.ml_library_available ? 'XGBoost Ready' : 'Not Available'}
                      </p>
                    </div>

                    {/* Model Status */}
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
                      {status?.training_metrics?.accuracy && (
                        <p className="text-sm text-gray-400 mt-2">
                          Accuracy: {(status.training_metrics.accuracy * 100).toFixed(1)}%
                        </p>
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

                    {/* Data Quality */}
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <div className="flex items-center gap-3 mb-4">
                        <Award className="w-6 h-6 text-purple-400" />
                        <h3 className="text-lg font-semibold text-white">Data Quality</h3>
                      </div>
                      <p className={`text-2xl font-bold ${getQualityColor(dataQuality?.quality || '')}`}>
                        {dataQuality?.quality || 'N/A'}
                      </p>
                      <p className="text-sm text-gray-400">
                        {dataQuality?.win_rate ? `${dataQuality.win_rate.toFixed(1)}% win rate` : 'No data'}
                      </p>
                    </div>
                  </div>

                  {/* Bot Integration Status */}
                  <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                    <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                      <Zap className="w-5 h-5 text-emerald-400" />
                      Bot Integration Status
                    </h3>
                    <p className="text-gray-400 text-sm mb-4">
                      Prophet is the PRIMARY decision maker for all trading bots.
                      WISDOM ML predictions feed INTO Prophet as one of its signal sources for enhanced accuracy.
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                      {['FORTRESS', 'SOLOMON', 'GIDEON', 'ANCHOR', 'SAMSON'].map(bot => {
                        const botStatus = botStatuses.find(b => b.bot_name === bot)
                        return (
                          <div key={bot} className="bg-gray-900 rounded-lg p-4 border border-gray-700">
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-white font-medium">{bot}</span>
                              {botStatus?.ml_enabled !== false ? (
                                <CheckCircle className="w-4 h-4 text-green-400" />
                              ) : (
                                <XCircle className="w-4 h-4 text-gray-500" />
                              )}
                            </div>
                            <p className="text-xs text-gray-500">
                              Min: {botStatus?.min_win_probability || (bot === 'GIDEON' || bot === 'SAMSON' ? '40' : '50')}%
                            </p>
                            {botStatus?.last_prediction?.win_probability && (
                              <p className="text-xs text-emerald-400 mt-1">
                                Last: {(botStatus.last_prediction.win_probability * 100).toFixed(0)}%
                              </p>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>

                  {/* What WISDOM Can/Cannot Do */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="bg-gray-800 rounded-lg p-6 border border-green-900/50">
                      <h3 className="text-lg font-semibold text-green-400 mb-4 flex items-center gap-2">
                        <CheckCircle className="w-5 h-5" />
                        What WISDOM CAN Do
                      </h3>
                      <ul className="space-y-2">
                        {(status?.what_ml_can_do || [
                          'Identify favorable market conditions from historical patterns',
                          'Adjust position sizing based on win probability',
                          'Learn from CHRONICLES backtest results',
                          'Provide calibrated probability estimates',
                          'Continuously improve with new trade outcomes'
                        ]).map((item, i) => (
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
                        What WISDOM CANNOT Do
                      </h3>
                      <ul className="space-y-2">
                        {(status?.what_ml_cannot_do || [
                          'Predict black swan events or flash crashes',
                          'Guarantee profits on any individual trade',
                          'Eliminate the inherent risks of options trading',
                          'Replace proper risk management',
                          'Foresee unprecedented market conditions'
                        ]).map((item, i) => (
                          <li key={i} className="flex items-start gap-2 text-gray-300">
                            <ChevronRight className="w-4 h-4 text-red-400 mt-1 flex-shrink-0" />
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  {/* Train Button */}
                  {status?.can_train && !status?.model_trained && (
                    <div className="flex justify-center">
                      <button
                        onClick={handleTrain}
                        disabled={training}
                        className="px-8 py-4 bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-600 text-white font-medium rounded-lg flex items-center gap-3 text-lg"
                      >
                        {training ? (
                          <>
                            <RefreshCw className="w-6 h-6 animate-spin" />
                            Training WISDOM...
                          </>
                        ) : (
                          <>
                            <Brain className="w-6 h-6" />
                            Train WISDOM Model
                          </>
                        )}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Predictions Tab */}
              {activeTab === 'predictions' && (
                <div className="space-y-6">
                  {/* Quick Prediction Form */}
                  <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                    <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                      <Sparkles className="w-5 h-5 text-emerald-400" />
                      Get WISDOM Prediction
                    </h3>
                    <p className="text-gray-400 text-sm mb-4">
                      Enter market conditions to get WISDOM's ML prediction for Iron Condor trading.
                    </p>

                    <form onSubmit={handlePredict} className="space-y-4">
                      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">VIX</label>
                          <input
                            type="number"
                            step="0.01"
                            value={predictionForm.vix}
                            onChange={(e) => setPredictionForm({...predictionForm, vix: e.target.value})}
                            placeholder="18.5"
                            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500"
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">Day of Week</label>
                          <select
                            value={predictionForm.day_of_week}
                            onChange={(e) => setPredictionForm({...predictionForm, day_of_week: e.target.value})}
                            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500"
                          >
                            {dayNames.map((day, i) => (
                              <option key={i} value={i}>{day}</option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">SPY Price</label>
                          <input
                            type="number"
                            step="0.01"
                            value={predictionForm.price}
                            onChange={(e) => setPredictionForm({...predictionForm, price: e.target.value})}
                            placeholder="585.00"
                            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500"
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">Price Change 1D (%)</label>
                          <input
                            type="number"
                            step="0.01"
                            value={predictionForm.price_change_1d}
                            onChange={(e) => setPredictionForm({...predictionForm, price_change_1d: e.target.value})}
                            placeholder="0.5"
                            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500"
                          />
                        </div>
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">Expected Move (%)</label>
                          <input
                            type="number"
                            step="0.1"
                            value={predictionForm.expected_move_pct}
                            onChange={(e) => setPredictionForm({...predictionForm, expected_move_pct: e.target.value})}
                            placeholder="1.0"
                            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500"
                          />
                        </div>
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">GEX Regime</label>
                          <select
                            value={predictionForm.gex_regime_positive ? 'positive' : 'negative'}
                            onChange={(e) => setPredictionForm({...predictionForm, gex_regime_positive: e.target.value === 'positive'})}
                            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500"
                          >
                            <option value="positive">Positive (Stable)</option>
                            <option value="negative">Negative (Volatile)</option>
                          </select>
                        </div>
                      </div>

                      <div className="flex justify-end">
                        <button
                          type="submit"
                          disabled={predicting || !status?.model_trained}
                          className="px-6 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-600 text-white font-medium rounded-lg flex items-center gap-2"
                        >
                          {predicting ? (
                            <>
                              <Loader2 className="w-4 h-4 animate-spin" />
                              Predicting...
                            </>
                          ) : (
                            <>
                              <Brain className="w-4 h-4" />
                              Get Prediction
                            </>
                          )}
                        </button>
                      </div>
                    </form>

                    {/* Prediction Result */}
                    {predictionResult && (
                      <div className={`mt-6 p-6 rounded-lg border ${
                        predictionResult.success === false
                          ? 'bg-red-900/30 border-red-700'
                          : 'bg-gray-900 border-gray-700'
                      }`}>
                        {predictionResult.success === false ? (
                          <p className="text-red-400">{predictionResult.error}</p>
                        ) : (
                          <div className="space-y-4">
                            <div className="flex items-center justify-between">
                              <div>
                                <span className="text-gray-400 text-sm">Win Probability</span>
                                <p className={`text-4xl font-bold ${
                                  (predictionResult.data?.prediction?.win_probability || predictionResult.prediction?.win_probability || 0) >= 0.7 ? 'text-green-400' :
                                  (predictionResult.data?.prediction?.win_probability || predictionResult.prediction?.win_probability || 0) >= 0.55 ? 'text-yellow-400' : 'text-red-400'
                                }`}>
                                  {(((predictionResult.data?.prediction?.win_probability || predictionResult.prediction?.win_probability || 0)) * 100).toFixed(1)}%
                                </p>
                              </div>
                              <div className="text-right">
                                <span className="text-gray-400 text-sm">Recommendation</span>
                                <p className={`mt-1 px-4 py-2 rounded text-lg font-medium border ${
                                  getAdviceStyle(predictionResult.data?.prediction?.advice || predictionResult.prediction?.advice || '')
                                }`}>
                                  {(predictionResult.data?.prediction?.advice || predictionResult.prediction?.advice || 'N/A').replace(/_/g, ' ')}
                                </p>
                              </div>
                            </div>

                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t border-gray-700">
                              <div>
                                <span className="text-gray-500 text-sm">Confidence</span>
                                <p className="text-white font-medium">
                                  {(predictionResult.data?.prediction?.confidence || predictionResult.prediction?.confidence || 0).toFixed(0)}%
                                </p>
                              </div>
                              <div>
                                <span className="text-gray-500 text-sm">Suggested Risk</span>
                                <p className="text-white font-medium">
                                  {(predictionResult.data?.prediction?.suggested_risk_pct || predictionResult.prediction?.suggested_risk_pct || 0).toFixed(1)}%
                                </p>
                              </div>
                              <div>
                                <span className="text-gray-500 text-sm">SD Multiplier</span>
                                <p className="text-white font-medium">
                                  {(predictionResult.data?.prediction?.suggested_sd_multiplier || predictionResult.prediction?.suggested_sd_multiplier || 1.0).toFixed(2)}x
                                </p>
                              </div>
                              <div>
                                <span className="text-gray-500 text-sm">Model Version</span>
                                <p className="text-emerald-400 font-medium">
                                  {predictionResult.data?.prediction?.model_version || predictionResult.prediction?.model_version || 'N/A'}
                                </p>
                              </div>
                            </div>

                            {(predictionResult.data?.prediction?.top_factors || predictionResult.prediction?.top_factors) && (
                              <div className="pt-4 border-t border-gray-700">
                                <span className="text-gray-400 text-sm">Top Decision Factors</span>
                                <div className="mt-2 space-y-2">
                                  {(predictionResult.data?.prediction?.top_factors || predictionResult.prediction?.top_factors || []).slice(0, 5).map((factor: [string, number], i: number) => (
                                    <div key={i} className="flex items-center gap-2">
                                      <div className="flex-1 bg-gray-800 rounded-full h-2">
                                        <div
                                          className="bg-emerald-500 h-2 rounded-full"
                                          style={{ width: `${Math.min(factor[1] * 100, 100)}%` }}
                                        />
                                      </div>
                                      <span className="text-gray-300 text-sm w-40 truncate">{factor[0]}</span>
                                      <span className="text-emerald-400 text-sm w-16 text-right">
                                        {(factor[1] * 100).toFixed(1)}%
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}

                    {!status?.model_trained && (
                      <div className="mt-4 p-4 bg-yellow-900/30 border border-yellow-700 rounded-lg flex items-center gap-3">
                        <AlertTriangle className="w-5 h-5 text-yellow-400" />
                        <p className="text-yellow-300">
                          WISDOM model is not trained yet. Train the model first to get predictions.
                        </p>
                      </div>
                    )}
                  </div>

                  {/* How WISDOM Makes Decisions */}
                  <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                    <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                      <BookOpen className="w-5 h-5 text-emerald-400" />
                      How WISDOM Makes Decisions
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="bg-gray-900 rounded-lg p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <div className="w-8 h-8 rounded-full bg-emerald-900/50 flex items-center justify-center">
                            <span className="text-emerald-400 font-bold">1</span>
                          </div>
                          <h4 className="text-white font-medium">Feature Extraction</h4>
                        </div>
                        <p className="text-gray-400 text-sm">
                          Extracts VIX, GEX regime, day of week, price momentum, and historical win rates from market data.
                        </p>
                      </div>
                      <div className="bg-gray-900 rounded-lg p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <div className="w-8 h-8 rounded-full bg-emerald-900/50 flex items-center justify-center">
                            <span className="text-emerald-400 font-bold">2</span>
                          </div>
                          <h4 className="text-white font-medium">XGBoost Prediction</h4>
                        </div>
                        <p className="text-gray-400 text-sm">
                          Trained on CHRONICLES backtest results, the model predicts win probability with calibrated confidence.
                        </p>
                      </div>
                      <div className="bg-gray-900 rounded-lg p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <div className="w-8 h-8 rounded-full bg-emerald-900/50 flex items-center justify-center">
                            <span className="text-emerald-400 font-bold">3</span>
                          </div>
                          <h4 className="text-white font-medium">Position Sizing</h4>
                        </div>
                        <p className="text-gray-400 text-sm">
                          Adjusts risk percentage and strike width based on confidence level and market conditions.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Features Tab */}
              {activeTab === 'features' && (
                <div className="space-y-6">
                  <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                    <h3 className="text-lg font-semibold text-white mb-2 flex items-center gap-2">
                      <BarChart3 className="w-5 h-5 text-emerald-400" />
                      Feature Importance Analysis
                    </h3>
                    <p className="text-gray-400 text-sm mb-6">
                      These are the factors WISDOM uses to predict trade outcomes, ranked by importance.
                    </p>

                    {featuresLoading ? (
                      <div className="flex items-center justify-center py-8">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
                      </div>
                    ) : features.length > 0 ? (
                      <div className="space-y-4">
                        {features.map((feature, i) => (
                          <div key={i} className="space-y-2">
                            <div className="flex justify-between items-center">
                              <div className="flex items-center gap-3">
                                <span className="text-gray-500 text-sm w-8">#{feature.rank}</span>
                                <span className="text-white font-medium">{feature.name}</span>
                              </div>
                              <span className="text-emerald-400 font-bold">
                                {feature.importance_pct.toFixed(1)}%
                              </span>
                            </div>
                            <div className="w-full bg-gray-700 rounded-full h-3">
                              <div
                                className="bg-gradient-to-r from-emerald-600 to-emerald-400 h-3 rounded-full transition-all duration-500"
                                style={{ width: `${Math.min(feature.importance_pct * 2, 100)}%` }}
                              />
                            </div>
                            <p className="text-sm text-gray-400 pl-11">{feature.meaning}</p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-center py-8">
                        <AlertCircle className="w-12 h-12 text-gray-600 mx-auto mb-4" />
                        <p className="text-gray-400">Train the model to see feature importance</p>
                      </div>
                    )}
                  </div>

                  {/* Feature Categories */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <h4 className="text-white font-medium mb-3 flex items-center gap-2">
                        <Activity className="w-4 h-4 text-blue-400" />
                        Volatility Features
                      </h4>
                      <ul className="space-y-2 text-sm text-gray-400">
                        <li>• VIX level</li>
                        <li>• VIX 30-day percentile</li>
                        <li>• VIX 1-day change</li>
                        <li>• Expected move %</li>
                      </ul>
                    </div>
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <h4 className="text-white font-medium mb-3 flex items-center gap-2">
                        <TrendingUp className="w-4 h-4 text-green-400" />
                        GEX Features
                      </h4>
                      <ul className="space-y-2 text-sm text-gray-400">
                        <li>• GEX regime (positive/negative)</li>
                        <li>• Normalized GEX value</li>
                        <li>• Distance to flip point</li>
                        <li>• Between walls indicator</li>
                      </ul>
                    </div>
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <h4 className="text-white font-medium mb-3 flex items-center gap-2">
                        <Clock className="w-4 h-4 text-purple-400" />
                        Timing Features
                      </h4>
                      <ul className="space-y-2 text-sm text-gray-400">
                        <li>• Day of week</li>
                        <li>• Price change 1-day</li>
                        <li>• 30-day win rate</li>
                        <li>• Historical performance</li>
                      </ul>
                    </div>
                  </div>
                </div>
              )}

              {/* Performance Tab */}
              {activeTab === 'performance' && (
                <div className="space-y-6">
                  {/* Performance Metrics */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <div className="flex items-center gap-2 mb-2">
                        <Target className="w-5 h-5 text-emerald-400" />
                        <span className="text-gray-400 text-sm">Accuracy</span>
                      </div>
                      <p className="text-3xl font-bold text-white">
                        {status?.training_metrics?.accuracy
                          ? `${(status.training_metrics.accuracy * 100).toFixed(1)}%`
                          : 'N/A'}
                      </p>
                    </div>
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <div className="flex items-center gap-2 mb-2">
                        <Percent className="w-5 h-5 text-blue-400" />
                        <span className="text-gray-400 text-sm">Precision</span>
                      </div>
                      <p className="text-3xl font-bold text-white">
                        {status?.training_metrics?.precision
                          ? `${(status.training_metrics.precision * 100).toFixed(1)}%`
                          : 'N/A'}
                      </p>
                    </div>
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <div className="flex items-center gap-2 mb-2">
                        <TrendingUp className="w-5 h-5 text-green-400" />
                        <span className="text-gray-400 text-sm">Win Rate</span>
                      </div>
                      <p className="text-3xl font-bold text-green-400">
                        {dataQuality?.win_rate
                          ? `${dataQuality.win_rate.toFixed(1)}%`
                          : 'N/A'}
                      </p>
                    </div>
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <div className="flex items-center gap-2 mb-2">
                        <Activity className="w-5 h-5 text-purple-400" />
                        <span className="text-gray-400 text-sm">AUC-ROC</span>
                      </div>
                      <p className="text-3xl font-bold text-white">
                        {status?.training_metrics?.auc_roc
                          ? status.training_metrics.auc_roc.toFixed(3)
                          : 'N/A'}
                      </p>
                    </div>
                  </div>

                  {/* Data Quality Details */}
                  {dataQuality && (
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                        <Database className="w-5 h-5 text-emerald-400" />
                        Training Data Quality
                      </h3>
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                        <div>
                          <p className="text-gray-400 text-sm">Total Trades</p>
                          <p className="text-2xl font-bold text-white">{dataQuality.total_trades}</p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">Wins</p>
                          <p className="text-2xl font-bold text-green-400">{dataQuality.wins}</p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">Losses</p>
                          <p className="text-2xl font-bold text-red-400">{dataQuality.losses}</p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">Total P&L</p>
                          <p className={`text-2xl font-bold ${dataQuality.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            ${dataQuality.total_pnl?.toLocaleString()}
                          </p>
                        </div>
                        <div>
                          <p className="text-gray-400 text-sm">Quality Rating</p>
                          <p className={`text-2xl font-bold ${getQualityColor(dataQuality.quality)}`}>
                            {dataQuality.quality}
                          </p>
                        </div>
                      </div>
                      {dataQuality.recommendation && (
                        <p className="mt-4 text-gray-400 text-sm bg-gray-900 p-3 rounded-lg">
                          <Info className="w-4 h-4 inline mr-2 text-blue-400" />
                          {dataQuality.recommendation}
                        </p>
                      )}
                    </div>
                  )}

                  {/* Calibration Info */}
                  <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                    <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                      <Shield className="w-5 h-5 text-emerald-400" />
                      Probability Calibration
                    </h3>
                    <p className="text-gray-400 mb-4">
                      WISDOM uses calibrated probabilities to ensure that when it says "70% win probability",
                      approximately 70% of such trades actually win.
                    </p>
                    <div className="bg-gray-900 rounded-lg p-4">
                      <p className="text-sm text-gray-500">
                        Brier Score: {status?.training_metrics?.brier_score?.toFixed(4) || 'N/A'}
                        <span className="text-gray-600 ml-2">(lower is better, 0.25 = random guessing)</span>
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Logs Tab */}
              {activeTab === 'logs' && (
                <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
                  <div className="p-4 border-b border-gray-700 flex justify-between items-center">
                    <div>
                      <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                        <FileText className="w-5 h-5 text-emerald-400" />
                        Decision Logs
                      </h3>
                      <p className="text-sm text-gray-400">Full transparency on all WISDOM decisions</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="relative">
                        <Filter className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                        <input
                          type="text"
                          placeholder="Filter logs..."
                          value={logFilter}
                          onChange={(e) => setLogFilter(e.target.value)}
                          className="pl-10 pr-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:border-emerald-500"
                        />
                      </div>
                      <button
                        onClick={() => mutateLogs()}
                        className="p-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-400"
                      >
                        <RefreshCw className={`w-4 h-4 ${logsLoading ? 'animate-spin' : ''}`} />
                      </button>
                    </div>
                  </div>
                  <div className="max-h-[600px] overflow-y-auto">
                    {logsLoading ? (
                      <div className="flex items-center justify-center py-8">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
                      </div>
                    ) : filteredLogs.length > 0 ? (
                      <table className="w-full">
                        <thead className="bg-gray-900 sticky top-0">
                          <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Time</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Action</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Symbol</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">ML Score</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Recommendation</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Details</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-700">
                          {filteredLogs.map((log) => (
                            <tr key={log.id} className="hover:bg-gray-700/50">
                              <td className="px-4 py-3 text-sm text-gray-400">
                                {new Date(log.timestamp).toLocaleString()}
                              </td>
                              <td className="px-4 py-3">
                                <span className={`px-2 py-1 rounded text-xs font-medium ${getLogTypeStyle(log.action)}`}>
                                  {log.action}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-sm text-white">
                                {log.symbol || 'SPY'}
                              </td>
                              <td className="px-4 py-3 text-sm">
                                {log.ml_score !== null ? (
                                  <span className={log.ml_score > 0.6 ? 'text-green-400' : log.ml_score > 0.5 ? 'text-yellow-400' : 'text-red-400'}>
                                    {(log.ml_score * 100).toFixed(1)}%
                                  </span>
                                ) : (
                                  <span className="text-gray-500">-</span>
                                )}
                              </td>
                              <td className="px-4 py-3">
                                {log.recommendation && (
                                  <span className={`px-2 py-1 rounded text-xs font-medium border ${getAdviceStyle(log.recommendation)}`}>
                                    {log.recommendation.replace(/_/g, ' ')}
                                  </span>
                                )}
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-400 max-w-xs truncate">
                                {log.reasoning || '-'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <div className="p-8 text-center">
                        <FileText className="w-12 h-12 text-gray-600 mx-auto mb-4" />
                        <p className="text-gray-400">No logs yet. Train the model or run predictions to generate logs.</p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Training Tab */}
              {activeTab === 'training' && (
                <div className="space-y-6">
                  {/* Training Status */}
                  <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                    <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                      <Zap className="w-5 h-5 text-emerald-400" />
                      Training Status
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                      <div className="bg-gray-900 rounded-lg p-4">
                        <p className="text-gray-400 text-sm">Training Samples</p>
                        <p className="text-2xl font-bold text-white mt-1">
                          {status?.training_data_available || 0}
                        </p>
                        <p className="text-xs text-gray-500 mt-1">
                          Minimum required: 30
                        </p>
                      </div>
                      <div className="bg-gray-900 rounded-lg p-4">
                        <p className="text-gray-400 text-sm">Model Version</p>
                        <p className="text-2xl font-bold text-emerald-400 mt-1">
                          {status?.model_version || 'Not trained'}
                        </p>
                      </div>
                      <div className="bg-gray-900 rounded-lg p-4">
                        <p className="text-gray-400 text-sm">Can Train</p>
                        <p className={`text-2xl font-bold mt-1 ${status?.can_train ? 'text-green-400' : 'text-red-400'}`}>
                          {status?.can_train ? 'Yes' : 'No'}
                        </p>
                        {!status?.can_train && (
                          <p className="text-xs text-gray-500 mt-1">
                            Need {30 - (status?.training_data_available || 0)} more samples
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Train Button */}
                    <div className="mt-6 flex justify-center">
                      <button
                        onClick={handleTrain}
                        disabled={training || !status?.can_train}
                        className="px-8 py-4 bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-600 text-white font-medium rounded-lg flex items-center gap-3 text-lg"
                      >
                        {training ? (
                          <>
                            <RefreshCw className="w-6 h-6 animate-spin" />
                            Training WISDOM...
                          </>
                        ) : (
                          <>
                            <Brain className="w-6 h-6" />
                            {status?.model_trained ? 'Retrain Model' : 'Train Model'}
                          </>
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Training Data Sources */}
                  <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                    <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                      <Database className="w-5 h-5 text-emerald-400" />
                      Training Data Sources
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="bg-gray-900 rounded-lg p-4 border border-gray-700">
                        <div className="flex items-center gap-2 mb-2">
                          <CheckCircle className={`w-5 h-5 ${(status as any)?.training_data_sources?.chronicles_backtests > 0 ? 'text-green-400' : 'text-gray-500'}`} />
                          <h4 className="text-white font-medium">CHRONICLES Backtests</h4>
                        </div>
                        <p className="text-2xl font-bold text-white mb-1">
                          {(status as any)?.training_data_sources?.chronicles_backtests?.toLocaleString() || 0} trades
                        </p>
                        <p className="text-gray-400 text-sm">
                          Primary training source. Historical Iron Condor backtests with complete outcome data.
                        </p>
                      </div>
                      <div className="bg-gray-900 rounded-lg p-4 border border-gray-700">
                        <div className="flex items-center gap-2 mb-2">
                          <CheckCircle className={`w-5 h-5 ${(status as any)?.training_data_sources?.live_outcomes > 0 ? 'text-green-400' : 'text-gray-500'}`} />
                          <h4 className="text-white font-medium">Live Trade Outcomes</h4>
                        </div>
                        <p className="text-2xl font-bold text-white mb-1">
                          {(status as any)?.training_data_sources?.live_outcomes?.toLocaleString() || 0} trades
                        </p>
                        <p className="text-gray-400 text-sm">
                          Feedback loop from FORTRESS, ANCHOR, and SAMSON live trades for continuous improvement.
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Strategy Explanation */}
                  {strategy && (
                    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                        <BookOpen className="w-5 h-5 text-emerald-400" />
                        Strategy Understanding
                      </h3>
                      <div className="space-y-4">
                        <div>
                          <h4 className="text-emerald-400 font-medium mb-2">What WISDOM Learned</h4>
                          <p className="text-gray-400">{strategy.ml_role || 'Train the model to see learned patterns.'}</p>
                        </div>
                        {strategy.why_it_works && (
                          <div>
                            <h4 className="text-green-400 font-medium mb-2">Why This Strategy Works</h4>
                            <p className="text-gray-400">{JSON.stringify(strategy.why_it_works)}</p>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
