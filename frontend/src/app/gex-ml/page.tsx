'use client'

/**
 * ORION - GEX Probability Models Dashboard
 *
 * Named after the mighty hunter constellation, ORION provides the ML-powered
 * probability predictions that guide ARGUS (0DTE) and HYPERION (Weekly) gamma
 * visualizations.
 *
 * Features:
 * - Model status with SWR auto-refresh
 * - Tab navigation (Overview, Predictions, Training)
 * - Training data availability check
 * - Sub-model status (5 XGBoost models)
 * - Manual and scheduled training controls
 * - Auto-training: Every Sunday at 6:00 PM CT
 */

import { useState } from 'react'
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
  Activity,
  Clock,
  TrendingUp,
  TrendingDown,
  ChevronRight,
  Eye,
  Sparkles,
  Info,
  BookOpen,
  Loader2,
  Play,
  Shield
} from 'lucide-react'

// API fetcher for SWR
const fetcher = (url: string) => api.get(url).then(res => res.data)

interface ModelStatus {
  is_trained: boolean
  model_info: {
    version?: number
    metrics?: Record<string, any>
    training_records?: number
    created_at?: string
    size_kb?: number
  } | null
  staleness_hours: number | null
  needs_retraining: boolean
  sub_models: {
    direction: boolean
    flip_gravity: boolean
    magnet_attraction: boolean
    volatility: boolean
    pin_zone: boolean
  }
  usage: {
    argus: string
    hyperion: string
  }
}

interface DataStatus {
  gex_structure_daily: {
    count: number
    date_range: string
    has_data: boolean
    is_primary?: boolean
  }
  gex_history?: {
    unique_days: number
    total_snapshots: number
    date_range: string
    has_data: boolean
    is_fallback?: boolean
    note?: string
  }
  vix_daily: {
    count: number
    date_range: string
    has_data: boolean
  }
  readiness: {
    is_ready: boolean
    data_source?: string
    usable_records?: number
    min_records_needed: number
    message: string
  }
}

interface Diagnostic {
  diagnostics: Record<string, { exists: boolean; count: number; status: string }>
  can_train: boolean
  recommendations: Array<{ priority: string; message: string }>
  summary: string
}

interface PredictionResult {
  direction: string
  direction_confidence: number
  flip_gravity_prob: number
  magnet_attraction_prob: number
  expected_volatility_pct: number
  pin_zone_prob: number
  overall_conviction: number
  trade_recommendation: string
}

export default function GexMLPage() {
  const [activeTab, setActiveTab] = useState<'overview' | 'predictions' | 'training'>('overview')
  const [training, setTraining] = useState(false)
  const [populating, setPopulating] = useState(false)
  const [populatingOrat, setPopulatingOrat] = useState(false)
  const [trainingResult, setTrainingResult] = useState<any>(null)
  const [populateResult, setPopulateResult] = useState<any>(null)
  const [oratResult, setOratResult] = useState<any>(null)

  // Prediction form state
  const [predictionForm, setPredictionForm] = useState({
    spot_price: '',
    net_gamma: '',
    total_gamma: '',
    flip_point: '',
    vix: '20'
  })
  const [predicting, setPredicting] = useState(false)
  const [predictionResult, setPredictionResult] = useState<{ success: boolean; data?: PredictionResult; error?: string } | null>(null)

  // SWR hooks for data fetching with automatic revalidation
  const { data: statusRes, isLoading: statusLoading, mutate: mutateStatus } = useSWR<{ success: boolean; data: ModelStatus }>(
    '/api/ml/gex-models/status',
    fetcher,
    { refreshInterval: 30000 }
  )

  const { data: dataRes, mutate: mutateData } = useSWR<{ success: boolean; data: DataStatus }>(
    '/api/ml/gex-models/data-status',
    fetcher,
    { refreshInterval: 60000 }
  )

  const { data: diagRes, mutate: mutateDiag } = useSWR<{ success: boolean; data: Diagnostic }>(
    activeTab === 'training' ? '/api/ml/gex-models/data-diagnostic' : null,
    fetcher
  )

  // Extract data from responses
  const modelStatus = statusRes?.data
  const dataStatus = dataRes?.data
  const diagnostic = diagRes?.data

  const handleTrain = async () => {
    setTraining(true)
    setTrainingResult(null)
    try {
      const res = await api.post('/api/ml/gex-models/train', null, {
        params: { symbols: ['SPX', 'SPY'], start_date: '2020-01-01' }
      })
      setTrainingResult(res.data)
      mutateStatus()
      mutateData()
    } catch (err: any) {
      setTrainingResult({ success: false, error: err.message || 'Training failed' })
    } finally {
      setTraining(false)
    }
  }

  const handlePopulate = async () => {
    setPopulating(true)
    setPopulateResult(null)
    try {
      const res = await api.post('/api/ml/gex-models/populate-from-snapshots')
      setPopulateResult(res.data)
      mutateData()
      mutateDiag()
    } catch (err: any) {
      setPopulateResult({ success: false, error: err.message })
    } finally {
      setPopulating(false)
    }
  }

  const handlePopulateFromOrat = async () => {
    setPopulatingOrat(true)
    setOratResult(null)
    try {
      // Populate both SPY and SPX from ORAT
      const spyRes = await api.post('/api/ml/gex-models/populate-from-orat', null, {
        params: { symbol: 'SPY', start_date: '2023-01-01', limit: 600 }
      })
      const spxRes = await api.post('/api/ml/gex-models/populate-from-orat', null, {
        params: { symbol: 'SPX', start_date: '2023-01-01', limit: 600 }
      })

      setOratResult({
        success: spyRes.data?.success && spxRes.data?.success,
        spy: spyRes.data?.data,
        spx: spxRes.data?.data
      })
      mutateData()
      mutateDiag()
    } catch (err: any) {
      setOratResult({ success: false, error: err.message || 'ORAT population failed' })
    } finally {
      setPopulatingOrat(false)
    }
  }

  const handlePredict = async (e: React.FormEvent) => {
    e.preventDefault()
    setPredicting(true)
    setPredictionResult(null)

    try {
      const response = await api.post('/api/ml/gex-models/predict', null, {
        params: {
          spot_price: parseFloat(predictionForm.spot_price),
          net_gamma: parseFloat(predictionForm.net_gamma),
          total_gamma: parseFloat(predictionForm.total_gamma),
          flip_point: predictionForm.flip_point ? parseFloat(predictionForm.flip_point) : undefined,
          vix: parseFloat(predictionForm.vix)
        }
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

  const handleRefresh = () => {
    mutateStatus()
    mutateData()
    if (activeTab === 'training') mutateDiag()
  }

  const formatDate = (dateStr: string | undefined) => {
    if (!dateStr) return 'N/A'
    try {
      return new Date(dateStr).toLocaleString('en-US', {
        timeZone: 'America/Chicago',
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      })
    } catch {
      return dateStr
    }
  }

  const formatHours = (hours: number | null) => {
    if (hours === null) return 'N/A'
    if (hours < 1) return `${Math.round(hours * 60)} minutes`
    if (hours < 24) return `${hours.toFixed(1)} hours`
    return `${(hours / 24).toFixed(1)} days`
  }

  const getDirectionColor = (direction: string) => {
    switch (direction) {
      case 'UP': return 'text-green-400'
      case 'DOWN': return 'text-red-400'
      default: return 'text-yellow-400'
    }
  }

  const getRecommendationStyle = (rec: string) => {
    if (rec.includes('BULLISH')) return 'bg-green-900/50 text-green-300 border-green-700'
    if (rec.includes('BEARISH')) return 'bg-red-900/50 text-red-300 border-red-700'
    return 'bg-yellow-900/50 text-yellow-300 border-yellow-700'
  }

  return (
    <div className="flex h-screen bg-background-deep">
      <Navigation />

      <div className="flex-1 overflow-auto p-8 pt-24 lg:pl-20">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="mb-8 flex justify-between items-start">
            <div>
              <h1 className="text-3xl font-bold text-text-primary mb-2 flex items-center gap-3">
                <Brain className="w-8 h-8 text-info" />
                ORION
              </h1>
              <p className="text-text-secondary">
                GEX Probability Models - ML-Powered Gamma Intelligence for ARGUS & HYPERION
              </p>
              {modelStatus?.model_info?.version && (
                <p className="text-sm text-info mt-1 flex items-center gap-2">
                  <Shield className="w-4 h-4" />
                  Model v{modelStatus.model_info.version}
                  {modelStatus.is_trained && !modelStatus.needs_retraining && (
                    <span className="bg-success/20 text-success text-xs px-2 py-0.5 rounded">
                      Active
                    </span>
                  )}
                </p>
              )}
            </div>
            <button
              onClick={handleRefresh}
              className="p-2 rounded-lg bg-background-card hover:bg-background-hover text-text-secondary"
            >
              <RefreshCw className={`w-5 h-5 ${statusLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {/* Primary Status Banner */}
          <div className={`rounded-lg p-6 border mb-6 ${
            modelStatus?.is_trained && !modelStatus?.needs_retraining
              ? 'bg-success/10 border-success/30'
              : modelStatus?.is_trained
                ? 'bg-warning/10 border-warning/30'
                : 'bg-danger/10 border-danger/30'
          }`}>
            <div className="flex items-center gap-4">
              {modelStatus?.is_trained && !modelStatus?.needs_retraining ? (
                <CheckCircle className="w-10 h-10 text-success" />
              ) : modelStatus?.is_trained ? (
                <AlertTriangle className="w-10 h-10 text-warning" />
              ) : (
                <XCircle className="w-10 h-10 text-danger" />
              )}
              <div>
                <h2 className="text-xl font-semibold text-text-primary">
                  {modelStatus?.is_trained && !modelStatus?.needs_retraining
                    ? 'ORION is Active & Providing ML Predictions'
                    : modelStatus?.is_trained
                      ? 'ORION is Active (Retraining Recommended)'
                      : 'ORION Needs Training'}
                </h2>
                <p className="text-text-secondary mt-1">
                  {modelStatus?.is_trained
                    ? `Last trained ${formatHours(modelStatus.staleness_hours)} ago with ${modelStatus.model_info?.training_records?.toLocaleString() || 'N/A'} records`
                    : 'Train the models to enable ML-enhanced probability predictions'}
                </p>
              </div>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex gap-2 mb-6 flex-wrap">
            {[
              { id: 'overview', label: 'Overview', icon: Target },
              { id: 'predictions', label: 'Predictions', icon: Sparkles },
              { id: 'training', label: 'Training', icon: Zap }
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2 ${
                  activeTab === tab.id
                    ? 'bg-info text-white'
                    : 'bg-background-card text-text-secondary hover:bg-background-hover'
                }`}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </button>
            ))}
          </div>

          {statusLoading && !modelStatus ? (
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-info"></div>
            </div>
          ) : (
            <>
              {/* Overview Tab */}
              {activeTab === 'overview' && (
                <div className="space-y-6">
                  {/* Status Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                    {/* Model Status */}
                    <div className="bg-background-card rounded-lg p-6 border border-gray-700/50">
                      <div className="flex items-center gap-3 mb-4">
                        {modelStatus?.is_trained ? (
                          <CheckCircle className="w-6 h-6 text-success" />
                        ) : (
                          <AlertTriangle className="w-6 h-6 text-warning" />
                        )}
                        <h3 className="text-lg font-semibold text-text-primary">Model Status</h3>
                      </div>
                      <p className={modelStatus?.is_trained ? 'text-success' : 'text-warning'}>
                        {modelStatus?.is_trained ? 'Trained & Ready' : 'Not Trained'}
                      </p>
                      {modelStatus?.staleness_hours !== null && modelStatus?.staleness_hours !== undefined && (
                        <p className="text-sm text-text-muted mt-2">
                          Age: {formatHours(modelStatus?.staleness_hours ?? null)}
                        </p>
                      )}
                    </div>

                    {/* Sub-Models */}
                    <div className="bg-background-card rounded-lg p-6 border border-gray-700/50">
                      <div className="flex items-center gap-3 mb-4">
                        <Zap className="w-6 h-6 text-info" />
                        <h3 className="text-lg font-semibold text-text-primary">Sub-Models</h3>
                      </div>
                      <p className="text-2xl font-bold text-text-primary">
                        {modelStatus?.sub_models
                          ? Object.values(modelStatus.sub_models).filter(Boolean).length
                          : 0} / 5
                      </p>
                      <p className="text-sm text-text-muted">XGBoost models trained</p>
                    </div>

                    {/* Training Data */}
                    <div className="bg-background-card rounded-lg p-6 border border-gray-700/50">
                      <div className="flex items-center gap-3 mb-4">
                        <Database className="w-6 h-6 text-primary" />
                        <h3 className="text-lg font-semibold text-text-primary">Training Data</h3>
                      </div>
                      <p className="text-2xl font-bold text-text-primary">
                        {dataStatus?.gex_structure_daily?.count?.toLocaleString() || 0}
                      </p>
                      <p className="text-sm text-text-muted">
                        {dataStatus?.readiness?.is_ready ? 'Ready to train' : 'Need more data'}
                      </p>
                    </div>

                    {/* Data Readiness */}
                    <div className="bg-background-card rounded-lg p-6 border border-gray-700/50">
                      <div className="flex items-center gap-3 mb-4">
                        {dataStatus?.readiness?.is_ready ? (
                          <CheckCircle className="w-6 h-6 text-success" />
                        ) : (
                          <AlertTriangle className="w-6 h-6 text-warning" />
                        )}
                        <h3 className="text-lg font-semibold text-text-primary">Data Ready</h3>
                      </div>
                      <p className={dataStatus?.readiness?.is_ready ? 'text-success' : 'text-warning'}>
                        {dataStatus?.readiness?.is_ready ? 'Yes' : 'No'}
                      </p>
                      <p className="text-sm text-text-muted">
                        Min: {dataStatus?.readiness?.min_records_needed || 100} records
                      </p>
                    </div>
                  </div>

                  {/* Bot Integration Status */}
                  <div className="bg-background-card rounded-lg p-6 border border-gray-700/50">
                    <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
                      <Eye className="w-5 h-5 text-info" />
                      Integration with Gamma Visualizers
                    </h3>
                    <p className="text-text-secondary text-sm mb-4">
                      ORION's ML predictions enhance ARGUS and HYPERION gamma visualizations with probability-weighted analysis.
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="bg-background-hover rounded-lg p-4 border border-gray-700/50">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-text-primary font-medium flex items-center gap-2">
                            <Eye className="w-4 h-4 text-info" />
                            ARGUS (0DTE Gamma)
                          </span>
                          {modelStatus?.is_trained ? (
                            <CheckCircle className="w-4 h-4 text-success" />
                          ) : (
                            <XCircle className="w-4 h-4 text-text-muted" />
                          )}
                        </div>
                        <p className="text-xs text-text-muted">
                          {modelStatus?.usage?.argus || '60% ML + 40% distance-weighted'}
                        </p>
                        <p className="text-xs text-info mt-1">
                          {modelStatus?.is_trained ? 'ML predictions active' : 'Using distance-only fallback'}
                        </p>
                      </div>
                      <div className="bg-background-hover rounded-lg p-4 border border-gray-700/50">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-text-primary font-medium flex items-center gap-2">
                            <Sparkles className="w-4 h-4 text-primary" />
                            HYPERION (Weekly Gamma)
                          </span>
                          {modelStatus?.is_trained ? (
                            <CheckCircle className="w-4 h-4 text-success" />
                          ) : (
                            <XCircle className="w-4 h-4 text-text-muted" />
                          )}
                        </div>
                        <p className="text-xs text-text-muted">
                          {modelStatus?.usage?.hyperion || '60% ML + 40% distance-weighted'}
                        </p>
                        <p className="text-xs text-primary mt-1">
                          {modelStatus?.is_trained ? 'ML predictions active' : 'Using distance-only fallback'}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* 5 Sub-Models Detail */}
                  <div className="bg-background-card rounded-lg p-6 border border-gray-700/50">
                    <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
                      <Zap className="w-5 h-5 text-info" />
                      5 XGBoost Sub-Models
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                      {[
                        { key: 'direction', label: 'Direction', desc: 'UP/DOWN/FLAT', icon: TrendingUp },
                        { key: 'flip_gravity', label: 'Flip Gravity', desc: 'Toward flip point', icon: Target },
                        { key: 'magnet_attraction', label: 'Magnet', desc: 'Strike attraction', icon: Activity },
                        { key: 'volatility', label: 'Volatility', desc: 'Expected range', icon: Zap },
                        { key: 'pin_zone', label: 'Pin Zone', desc: 'Stay pinned', icon: Eye }
                      ].map(model => {
                        const Icon = model.icon
                        const isTrained = modelStatus?.sub_models?.[model.key as keyof typeof modelStatus.sub_models]
                        return (
                          <div key={model.key} className="bg-background-hover rounded-lg p-4 text-center">
                            <Icon className={`w-6 h-6 mx-auto mb-2 ${isTrained ? 'text-info' : 'text-text-muted'}`} />
                            <div className="text-sm font-medium text-text-primary">{model.label}</div>
                            <div className="text-xs text-text-muted">{model.desc}</div>
                            <div className={`mt-2 text-xs font-medium ${isTrained ? 'text-success' : 'text-text-muted'}`}>
                              {isTrained ? 'Trained' : 'Not Trained'}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>

                  {/* What ORION Can/Cannot Do */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="bg-background-card rounded-lg p-6 border border-success/30">
                      <h3 className="text-lg font-semibold text-success mb-4 flex items-center gap-2">
                        <CheckCircle className="w-5 h-5" />
                        What ORION CAN Do
                      </h3>
                      <ul className="space-y-2">
                        {[
                          'Predict directional bias from gamma structure patterns',
                          'Estimate probability of price moving to flip point',
                          'Calculate strike-level pin probabilities for ARGUS',
                          'Estimate expected volatility from GEX regime',
                          'Enhance ARGUS/HYPERION with ML-weighted probabilities'
                        ].map((item, i) => (
                          <li key={i} className="flex items-start gap-2 text-text-secondary">
                            <ChevronRight className="w-4 h-4 text-success mt-1 flex-shrink-0" />
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div className="bg-background-card rounded-lg p-6 border border-danger/30">
                      <h3 className="text-lg font-semibold text-danger mb-4 flex items-center gap-2">
                        <XCircle className="w-5 h-5" />
                        What ORION CANNOT Do
                      </h3>
                      <ul className="space-y-2">
                        {[
                          'Predict flash crashes or black swan events',
                          'Guarantee price will reach predicted targets',
                          'Override fundamental market dynamics',
                          'Account for breaking news or sudden events',
                          'Replace proper position sizing and risk management'
                        ].map((item, i) => (
                          <li key={i} className="flex items-start gap-2 text-text-secondary">
                            <ChevronRight className="w-4 h-4 text-danger mt-1 flex-shrink-0" />
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  {/* Probability Calculation */}
                  <div className="bg-background-card rounded-lg p-6 border border-gray-700/50">
                    <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
                      <BookOpen className="w-5 h-5 text-info" />
                      How ORION Calculates Probabilities
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="bg-background-hover rounded-lg p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <div className="w-8 h-8 rounded-full bg-info/20 flex items-center justify-center">
                            <span className="text-info font-bold">1</span>
                          </div>
                          <h4 className="text-text-primary font-medium">ML Prediction</h4>
                        </div>
                        <p className="text-text-muted text-sm">
                          5 XGBoost models analyze gamma structure, VIX, and historical patterns.
                        </p>
                      </div>
                      <div className="bg-background-hover rounded-lg p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <div className="w-8 h-8 rounded-full bg-info/20 flex items-center justify-center">
                            <span className="text-info font-bold">2</span>
                          </div>
                          <h4 className="text-text-primary font-medium">Distance Weighting</h4>
                        </div>
                        <p className="text-text-muted text-sm">
                          Classic distance-based probability using price-to-level relationships.
                        </p>
                      </div>
                      <div className="bg-background-hover rounded-lg p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <div className="w-8 h-8 rounded-full bg-info/20 flex items-center justify-center">
                            <span className="text-info font-bold">3</span>
                          </div>
                          <h4 className="text-text-primary font-medium">Hybrid Blend</h4>
                        </div>
                        <p className="text-text-muted text-sm">
                          Combined: <code className="bg-background-deep px-1 rounded">60% ML + 40% distance</code>
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Quick Train Button if not trained */}
                  {!modelStatus?.is_trained && dataStatus?.readiness?.is_ready && (
                    <div className="flex justify-center">
                      <button
                        onClick={handleTrain}
                        disabled={training}
                        className="px-8 py-4 bg-info hover:bg-info/80 disabled:bg-background-hover disabled:text-text-muted text-white font-medium rounded-lg flex items-center gap-3 text-lg"
                      >
                        {training ? (
                          <>
                            <RefreshCw className="w-6 h-6 animate-spin" />
                            Training ORION...
                          </>
                        ) : (
                          <>
                            <Brain className="w-6 h-6" />
                            Train ORION Models
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
                  {/* Prediction Form */}
                  <div className="bg-background-card rounded-lg p-6 border border-gray-700/50">
                    <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
                      <Sparkles className="w-5 h-5 text-info" />
                      Get ORION Prediction
                    </h3>
                    <p className="text-text-secondary text-sm mb-4">
                      Enter gamma structure data to get ORION's ML prediction for market direction and pin probabilities.
                    </p>

                    <form onSubmit={handlePredict} className="space-y-4">
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                        <div>
                          <label className="block text-sm text-text-secondary mb-1">Spot Price *</label>
                          <input
                            type="number"
                            step="0.01"
                            value={predictionForm.spot_price}
                            onChange={(e) => setPredictionForm({...predictionForm, spot_price: e.target.value})}
                            placeholder="585.00"
                            className="w-full px-3 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary focus:outline-none focus:border-info"
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-sm text-text-secondary mb-1">Net Gamma *</label>
                          <input
                            type="number"
                            step="0.01"
                            value={predictionForm.net_gamma}
                            onChange={(e) => setPredictionForm({...predictionForm, net_gamma: e.target.value})}
                            placeholder="500000"
                            className="w-full px-3 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary focus:outline-none focus:border-info"
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-sm text-text-secondary mb-1">Total Gamma *</label>
                          <input
                            type="number"
                            step="0.01"
                            value={predictionForm.total_gamma}
                            onChange={(e) => setPredictionForm({...predictionForm, total_gamma: e.target.value})}
                            placeholder="1000000"
                            className="w-full px-3 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary focus:outline-none focus:border-info"
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-sm text-text-secondary mb-1">Flip Point</label>
                          <input
                            type="number"
                            step="0.01"
                            value={predictionForm.flip_point}
                            onChange={(e) => setPredictionForm({...predictionForm, flip_point: e.target.value})}
                            placeholder="580.00"
                            className="w-full px-3 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary focus:outline-none focus:border-info"
                          />
                        </div>
                        <div>
                          <label className="block text-sm text-text-secondary mb-1">VIX</label>
                          <input
                            type="number"
                            step="0.1"
                            value={predictionForm.vix}
                            onChange={(e) => setPredictionForm({...predictionForm, vix: e.target.value})}
                            placeholder="20"
                            className="w-full px-3 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary focus:outline-none focus:border-info"
                          />
                        </div>
                      </div>

                      <div className="flex justify-end">
                        <button
                          type="submit"
                          disabled={predicting || !modelStatus?.is_trained}
                          className="px-6 py-2 bg-info hover:bg-info/80 disabled:bg-background-hover disabled:text-text-muted text-white font-medium rounded-lg flex items-center gap-2"
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
                          ? 'bg-danger/10 border-danger/30'
                          : 'bg-background-hover border-gray-700/50'
                      }`}>
                        {predictionResult.success === false ? (
                          <p className="text-danger">{predictionResult.error}</p>
                        ) : predictionResult.data ? (
                          <div className="space-y-4">
                            <div className="flex items-center justify-between">
                              <div>
                                <span className="text-text-secondary text-sm">Direction Prediction</span>
                                <p className={`text-4xl font-bold ${getDirectionColor(predictionResult.data.direction)}`}>
                                  {predictionResult.data.direction}
                                </p>
                              </div>
                              <div className="text-right">
                                <span className="text-text-secondary text-sm">Trade Recommendation</span>
                                <p className={`mt-1 px-4 py-2 rounded text-lg font-medium border ${
                                  getRecommendationStyle(predictionResult.data.trade_recommendation)
                                }`}>
                                  {predictionResult.data.trade_recommendation?.replace(/_/g, ' ') || 'N/A'}
                                </p>
                              </div>
                            </div>

                            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 pt-4 border-t border-gray-700/50">
                              <div>
                                <span className="text-text-muted text-sm">Direction Confidence</span>
                                <p className="text-text-primary font-medium">
                                  {((predictionResult.data.direction_confidence || 0) * 100).toFixed(1)}%
                                </p>
                              </div>
                              <div>
                                <span className="text-text-muted text-sm">Flip Gravity</span>
                                <p className="text-text-primary font-medium">
                                  {((predictionResult.data.flip_gravity_prob || 0) * 100).toFixed(1)}%
                                </p>
                              </div>
                              <div>
                                <span className="text-text-muted text-sm">Magnet Attraction</span>
                                <p className="text-text-primary font-medium">
                                  {((predictionResult.data.magnet_attraction_prob || 0) * 100).toFixed(1)}%
                                </p>
                              </div>
                              <div>
                                <span className="text-text-muted text-sm">Expected Vol</span>
                                <p className="text-text-primary font-medium">
                                  {(predictionResult.data.expected_volatility_pct || 0).toFixed(2)}%
                                </p>
                              </div>
                              <div>
                                <span className="text-text-muted text-sm">Overall Conviction</span>
                                <p className="text-info font-medium">
                                  {((predictionResult.data.overall_conviction || 0) * 100).toFixed(0)}%
                                </p>
                              </div>
                            </div>
                          </div>
                        ) : null}
                      </div>
                    )}

                    {!modelStatus?.is_trained && (
                      <div className="mt-4 p-4 bg-warning/10 border border-warning/30 rounded-lg flex items-center gap-3">
                        <AlertTriangle className="w-5 h-5 text-warning" />
                        <p className="text-warning">
                          ORION models are not trained yet. Train the models first to get predictions.
                        </p>
                      </div>
                    )}
                  </div>

                  {/* How ORION Makes Predictions */}
                  <div className="bg-background-card rounded-lg p-6 border border-gray-700/50">
                    <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
                      <BookOpen className="w-5 h-5 text-info" />
                      Understanding ORION Predictions
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div>
                        <h4 className="text-text-primary font-medium mb-3">Prediction Outputs</h4>
                        <div className="space-y-2 text-sm">
                          <div className="flex items-start gap-2">
                            <TrendingUp className="w-4 h-4 text-success mt-0.5" />
                            <div>
                              <span className="text-text-primary font-medium">Direction:</span>
                              <span className="text-text-secondary ml-1">UP, DOWN, or FLAT prediction with confidence</span>
                            </div>
                          </div>
                          <div className="flex items-start gap-2">
                            <Target className="w-4 h-4 text-info mt-0.5" />
                            <div>
                              <span className="text-text-primary font-medium">Flip Gravity:</span>
                              <span className="text-text-secondary ml-1">Probability price moves toward the flip point</span>
                            </div>
                          </div>
                          <div className="flex items-start gap-2">
                            <Activity className="w-4 h-4 text-primary mt-0.5" />
                            <div>
                              <span className="text-text-primary font-medium">Magnet Attraction:</span>
                              <span className="text-text-secondary ml-1">Probability price reaches nearest gamma magnet</span>
                            </div>
                          </div>
                          <div className="flex items-start gap-2">
                            <Zap className="w-4 h-4 text-warning mt-0.5" />
                            <div>
                              <span className="text-text-primary font-medium">Expected Volatility:</span>
                              <span className="text-text-secondary ml-1">Predicted price range as percentage</span>
                            </div>
                          </div>
                        </div>
                      </div>
                      <div>
                        <h4 className="text-text-primary font-medium mb-3">Trade Recommendations</h4>
                        <div className="space-y-2 text-sm">
                          <div className="p-2 bg-success/10 border border-success/30 rounded">
                            <span className="text-success font-medium">BULLISH_BREAKOUT / BULLISH_GRIND:</span>
                            <span className="text-text-secondary ml-1">Consider call spreads or long directional</span>
                          </div>
                          <div className="p-2 bg-danger/10 border border-danger/30 rounded">
                            <span className="text-danger font-medium">BEARISH_BREAKOUT / BEARISH_GRIND:</span>
                            <span className="text-text-secondary ml-1">Consider put spreads or short directional</span>
                          </div>
                          <div className="p-2 bg-warning/10 border border-warning/30 rounded">
                            <span className="text-warning font-medium">NEUTRAL / SELL_PREMIUM:</span>
                            <span className="text-text-secondary ml-1">Favor Iron Condors or credit spreads</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Training Tab */}
              {activeTab === 'training' && (
                <div className="space-y-6">
                  {/* Training Status */}
                  <div className="bg-background-card rounded-lg p-6 border border-gray-700/50">
                    <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
                      <Zap className="w-5 h-5 text-info" />
                      Training Status
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                      <div className="bg-background-hover rounded-lg p-4">
                        <p className="text-text-secondary text-sm">Training Records</p>
                        <p className="text-2xl font-bold text-text-primary mt-1">
                          {modelStatus?.model_info?.training_records?.toLocaleString() || 0}
                        </p>
                      </div>
                      <div className="bg-background-hover rounded-lg p-4">
                        <p className="text-text-secondary text-sm">Model Version</p>
                        <p className="text-2xl font-bold text-info mt-1">
                          {modelStatus?.model_info?.version ? `v${modelStatus.model_info.version}` : 'Not trained'}
                        </p>
                      </div>
                      <div className="bg-background-hover rounded-lg p-4">
                        <p className="text-text-secondary text-sm">Model Age</p>
                        <p className={`text-2xl font-bold mt-1 ${modelStatus?.needs_retraining ? 'text-warning' : 'text-success'}`}>
                          {formatHours(modelStatus?.staleness_hours ?? null)}
                        </p>
                      </div>
                      <div className="bg-background-hover rounded-lg p-4">
                        <p className="text-text-secondary text-sm">Model Size</p>
                        <p className="text-2xl font-bold text-text-primary mt-1">
                          {modelStatus?.model_info?.size_kb?.toFixed(1) || '0'} KB
                        </p>
                      </div>
                    </div>

                    {/* Train Button */}
                    <div className="mt-6 flex justify-center">
                      <button
                        onClick={handleTrain}
                        disabled={training || !dataStatus?.readiness?.is_ready}
                        className="px-8 py-4 bg-info hover:bg-info/80 disabled:bg-background-hover disabled:text-text-muted text-white font-medium rounded-lg flex items-center gap-3 text-lg"
                      >
                        {training ? (
                          <>
                            <RefreshCw className="w-6 h-6 animate-spin" />
                            Training ORION...
                          </>
                        ) : (
                          <>
                            <Brain className="w-6 h-6" />
                            {modelStatus?.is_trained ? 'Retrain Models' : 'Train Models'}
                          </>
                        )}
                      </button>
                    </div>

                    {/* Scheduled Training Info */}
                    <div className="mt-4 p-3 bg-info/10 border border-info/30 rounded-lg">
                      <div className="flex items-center gap-2 text-sm">
                        <Clock className="w-4 h-4 text-info" />
                        <span className="text-info font-medium">Auto-Training Schedule:</span>
                        <span className="text-text-primary">Every Sunday at 6:00 PM CT</span>
                      </div>
                      <p className="text-xs text-text-muted mt-1 ml-6">
                        Models automatically retrain weekly when older than 7 days. Training uses GEX data from SPX and SPY.
                      </p>
                    </div>

                    {/* Training Result */}
                    {trainingResult && (
                      <div className={`mt-4 p-4 rounded-lg ${
                        trainingResult.success
                          ? 'bg-success/10 border border-success/30'
                          : 'bg-danger/10 border border-danger/30'
                      }`}>
                        <div className="flex items-center gap-2">
                          {trainingResult.success ? (
                            <CheckCircle className="w-5 h-5 text-success" />
                          ) : (
                            <XCircle className="w-5 h-5 text-danger" />
                          )}
                          <span className={trainingResult.success ? 'text-success' : 'text-danger'}>
                            {trainingResult.success ? 'Training Complete' : 'Training Failed'}
                          </span>
                        </div>
                        <p className="text-text-secondary text-sm mt-1">
                          {trainingResult.message || trainingResult.error}
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Training Data Sources */}
                  <div className="bg-background-card rounded-lg p-6 border border-gray-700/50">
                    <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
                      <Database className="w-5 h-5 text-info" />
                      Training Data Sources
                    </h3>

                    <div className="space-y-4">
                      {/* Primary: gex_structure_daily */}
                      <div className={`p-4 rounded-lg ${
                        dataStatus?.readiness?.data_source === 'gex_structure_daily'
                          ? 'bg-success/10 border border-success/30'
                          : 'bg-background-hover border border-gray-700/50'
                      }`}>
                        <div className="flex justify-between items-center mb-2">
                          <span className="font-medium text-text-primary flex items-center gap-2">
                            GEX Structure Daily
                            <span className="text-[10px] px-1.5 py-0.5 bg-purple-500/20 text-purple-400 rounded">PRIMARY</span>
                          </span>
                          {dataStatus?.gex_structure_daily?.has_data ? (
                            <CheckCircle className="w-5 h-5 text-success" />
                          ) : (
                            <XCircle className="w-5 h-5 text-text-muted" />
                          )}
                        </div>
                        <div className="text-sm text-text-secondary">
                          {dataStatus?.gex_structure_daily?.count?.toLocaleString() || 0} records
                        </div>
                        <div className="text-xs text-text-muted">
                          {dataStatus?.gex_structure_daily?.date_range || 'No data'}
                        </div>
                      </div>

                      {/* Fallback: gex_history */}
                      <div className={`p-4 rounded-lg ${
                        dataStatus?.readiness?.data_source === 'gex_history'
                          ? 'bg-info/10 border border-info/30'
                          : 'bg-background-hover border border-gray-700/50'
                      }`}>
                        <div className="flex justify-between items-center mb-2">
                          <span className="font-medium text-text-primary flex items-center gap-2">
                            GEX History (Snapshots)
                            <span className="text-[10px] px-1.5 py-0.5 bg-blue-500/20 text-blue-400 rounded">FALLBACK</span>
                          </span>
                          {dataStatus?.gex_history?.has_data ? (
                            <CheckCircle className="w-5 h-5 text-success" />
                          ) : (
                            <XCircle className="w-5 h-5 text-text-muted" />
                          )}
                        </div>
                        <div className="text-sm text-text-secondary">
                          {dataStatus?.gex_history?.unique_days?.toLocaleString() || 0} unique days
                          {dataStatus?.gex_history?.total_snapshots && (
                            <span className="text-text-muted"> ({dataStatus.gex_history.total_snapshots.toLocaleString()} snapshots)</span>
                          )}
                        </div>
                        <div className="text-xs text-text-muted">
                          {dataStatus?.gex_history?.date_range || 'No data'}
                        </div>
                      </div>

                      {/* VIX Data */}
                      <div className="p-4 bg-background-hover rounded-lg border border-gray-700/50">
                        <div className="flex justify-between items-center mb-2">
                          <span className="font-medium text-text-primary">VIX Data</span>
                          {dataStatus?.vix_daily?.has_data ? (
                            <CheckCircle className="w-5 h-5 text-success" />
                          ) : (
                            <AlertTriangle className="w-5 h-5 text-warning" />
                          )}
                        </div>
                        <div className="text-sm text-text-secondary">
                          {dataStatus?.vix_daily?.count?.toLocaleString() || 0} records
                        </div>
                        <div className="text-xs text-text-muted">
                          {dataStatus?.vix_daily?.date_range || 'No data'}
                        </div>
                      </div>
                    </div>

                    {/* Population Buttons */}
                    {(!dataStatus?.gex_structure_daily?.has_data || (dataStatus?.gex_structure_daily?.count || 0) < 100) && (
                      <div className="mt-4 space-y-3">
                        <h4 className="text-sm font-medium text-text-secondary flex items-center gap-2">
                          <AlertTriangle className="w-4 h-4 text-warning" />
                          Need Training Data?
                        </h4>

                        {/* ORAT Population - Primary */}
                        <button
                          onClick={handlePopulateFromOrat}
                          disabled={populatingOrat}
                          className={`w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg font-medium transition-all ${
                            populatingOrat
                              ? 'bg-background-hover text-text-muted cursor-not-allowed'
                              : 'bg-purple-600 hover:bg-purple-500 text-white'
                          }`}
                        >
                          {populatingOrat ? (
                            <>
                              <RefreshCw className="w-4 h-4 animate-spin" />
                              Populating from ORAT (30-60s)...
                            </>
                          ) : (
                            <>
                              <Database className="w-4 h-4" />
                              Populate from ORAT Database (Historical)
                            </>
                          )}
                        </button>

                        {/* ORAT Result */}
                        {oratResult && (
                          <div className={`p-3 rounded text-sm ${
                            oratResult.success
                              ? 'bg-success/10 text-success'
                              : 'bg-danger/10 text-danger'
                          }`}>
                            {oratResult.success ? (
                              <>
                                <div>SPY: {oratResult.spy?.inserted || 0} inserted, {oratResult.spy?.skipped || 0} skipped</div>
                                <div>SPX: {oratResult.spx?.inserted || 0} inserted, {oratResult.spx?.skipped || 0} skipped</div>
                              </>
                            ) : (
                              `Error: ${oratResult.error || 'Population failed'}`
                            )}
                          </div>
                        )}

                        {/* Snapshots Population - Fallback */}
                        {(diagnostic?.diagnostics?.gex_history?.count ?? 0) > 0 && (
                          <button
                            onClick={handlePopulate}
                            disabled={populating}
                            className={`w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                              populating
                                ? 'bg-background-hover text-text-muted cursor-not-allowed'
                                : 'bg-background-hover hover:bg-info/20 text-text-secondary'
                            }`}
                          >
                            {populating ? (
                              <>
                                <RefreshCw className="w-4 h-4 animate-spin" />
                                Building from snapshots...
                              </>
                            ) : (
                              <>
                                <Database className="w-4 h-4" />
                                Build from Live Snapshots (Alternative)
                              </>
                            )}
                          </button>
                        )}

                        {/* Snapshots Result */}
                        {populateResult && (
                          <div className={`p-3 rounded text-sm ${
                            populateResult.success
                              ? 'bg-success/10 text-success'
                              : 'bg-danger/10 text-danger'
                          }`}>
                            {populateResult.success
                              ? `Built ${populateResult.data?.rows_inserted_or_updated || 0} training records`
                              : `Error: ${populateResult.error}`}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Diagnostic Recommendations */}
                    {diagnostic && diagnostic.recommendations.length > 0 && (
                      <div className="mt-4 space-y-2">
                        <h4 className="text-sm font-medium text-text-secondary flex items-center gap-2">
                          <Info className="w-4 h-4 text-info" />
                          Recommendations
                        </h4>
                        {diagnostic.recommendations.map((rec, idx) => (
                          <div
                            key={idx}
                            className={`p-2 rounded text-xs ${
                              rec.priority === 'high'
                                ? 'bg-danger/10 border border-danger/30 text-danger'
                                : rec.priority === 'medium'
                                ? 'bg-warning/10 border border-warning/30 text-warning'
                                : rec.priority === 'info'
                                ? 'bg-success/10 border border-success/30 text-success'
                                : 'bg-background-hover text-text-muted'
                            }`}
                          >
                            <code className="font-mono text-[11px]">{rec.message}</code>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Model Metrics */}
                  {modelStatus?.model_info?.metrics && Object.keys(modelStatus.model_info.metrics).length > 0 && (
                    <div className="bg-background-card rounded-lg p-6 border border-gray-700/50">
                      <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
                        <Activity className="w-5 h-5 text-info" />
                        Training Metrics
                      </h3>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                        {Object.entries(modelStatus.model_info.metrics).map(([key, value]) => {
                          // Handle nested objects
                          let displayValue: string
                          if (typeof value === 'number') {
                            displayValue = value < 1 ? `${(value * 100).toFixed(1)}%` : value.toFixed(2)
                          } else if (typeof value === 'object' && value !== null) {
                            const obj = value as Record<string, unknown>
                            const numericValue = obj.accuracy ?? obj.cv_mean ?? obj.cv_mae ?? obj.value
                            if (typeof numericValue === 'number') {
                              displayValue = numericValue < 1 ? `${(numericValue * 100).toFixed(1)}%` : numericValue.toFixed(2)
                            } else {
                              displayValue = JSON.stringify(value).slice(0, 20) + '...'
                            }
                          } else {
                            displayValue = String(value)
                          }
                          return (
                            <div key={key} className="p-3 bg-background-hover rounded-lg">
                              <div className="text-xs text-text-muted mb-1">
                                {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                              </div>
                              <div className="text-lg font-mono font-bold text-text-primary">
                                {displayValue}
                              </div>
                            </div>
                          )
                        })}
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
