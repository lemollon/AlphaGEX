'use client'

/**
 * ORION - GEX Probability Models Dashboard
 *
 * Named after the mighty hunter constellation, ORION provides the ML-powered
 * probability predictions that guide ARGUS (0DTE) and HYPERION (Weekly) gamma
 * visualizations.
 *
 * Features:
 * - Model status (trained/not trained, staleness)
 * - Training data availability check (gex_structure_daily + gex_history fallback)
 * - Sub-model status (5 XGBoost models)
 * - Manual and scheduled training controls
 * - Auto-training: Every Sunday at 6:00 PM CT
 */

import { useState, useEffect, useCallback } from 'react'
import {
  Brain,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
  Database,
  Play,
  RefreshCw,
  TrendingUp,
  Target,
  Activity,
  Zap,
  Eye,
  Sparkles,
  Info
} from 'lucide-react'
import apiClient from '@/lib/api'
import Navigation from '@/components/Navigation'

interface ModelStatus {
  is_trained: boolean
  model_info: {
    version?: number
    metrics?: Record<string, number>
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

export default function GexMLPage() {
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null)
  const [dataStatus, setDataStatus] = useState<DataStatus | null>(null)
  const [diagnostic, setDiagnostic] = useState<Diagnostic | null>(null)
  const [loading, setLoading] = useState(true)
  const [training, setTraining] = useState(false)
  const [populating, setPopulating] = useState(false)
  const [populatingOrat, setPopulatingOrat] = useState(false)
  const [trainingResult, setTrainingResult] = useState<any>(null)
  const [populateResult, setPopulateResult] = useState<any>(null)
  const [oratResult, setOratResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const fetchStatus = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [modelRes, dataRes, diagRes] = await Promise.all([
        apiClient.getGexModelsStatus(),
        apiClient.getGexModelsDataStatus(),
        apiClient.getGexModelsDataDiagnostic()
      ])

      if (modelRes?.data?.data) {
        setModelStatus(modelRes.data.data)
      }
      if (dataRes?.data?.data) {
        setDataStatus(dataRes.data.data)
      }
      if (diagRes?.data?.data) {
        setDiagnostic(diagRes.data.data)
      }
      setLastRefresh(new Date())
    } catch (err: any) {
      setError(err.message || 'Failed to fetch status')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchStatus()
  }, [fetchStatus])

  const handleTrain = async () => {
    setTraining(true)
    setTrainingResult(null)
    setError(null)
    try {
      const res = await apiClient.trainGexModels({
        symbols: ['SPX', 'SPY'],
        start_date: '2020-01-01'
      })
      setTrainingResult(res.data)
      // Refresh status after training
      await fetchStatus()
    } catch (err: any) {
      setError(err.message || 'Training failed')
    } finally {
      setTraining(false)
    }
  }

  const handlePopulate = async () => {
    setPopulating(true)
    setPopulateResult(null)
    setError(null)
    try {
      const res = await apiClient.populateGexFromSnapshots()
      setPopulateResult(res.data)
      // Refresh status after populating
      await fetchStatus()
    } catch (err: any) {
      setError(err.message || 'Population failed')
    } finally {
      setPopulating(false)
    }
  }

  const handlePopulateFromOrat = async () => {
    setPopulatingOrat(true)
    setOratResult(null)
    setError(null)
    try {
      // Populate both SPY and SPX from ORAT
      const spyRes = await apiClient.populateGexFromOrat({ symbol: 'SPY', start_date: '2023-01-01', limit: 600 })
      const spxRes = await apiClient.populateGexFromOrat({ symbol: 'SPX', start_date: '2023-01-01', limit: 600 })

      setOratResult({
        success: spyRes.data?.success && spxRes.data?.success,
        spy: spyRes.data?.data,
        spx: spxRes.data?.data
      })
      // Refresh status after populating
      await fetchStatus()
    } catch (err: any) {
      setError(err.message || 'ORAT population failed')
    } finally {
      setPopulatingOrat(false)
    }
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

  return (
    <>
      <Navigation />
      <main className="min-h-screen bg-background-deep text-text-primary px-4 pb-4 md:px-6 md:pb-6 pt-28">
        <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <Brain className="w-8 h-8 text-info" />
            <div>
              <h1 className="text-2xl font-bold text-text-primary">ORION</h1>
              <p className="text-text-secondary text-sm">
                GEX Probability Models for ARGUS and HYPERION
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {lastRefresh && (
              <span className="text-xs text-text-muted">
                Last refresh: {lastRefresh.toLocaleTimeString()}
              </span>
            )}
            <button
              onClick={fetchStatus}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-background-hover hover:bg-primary/20 rounded-lg transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-6 p-4 bg-danger/10 border border-danger/30 rounded-lg flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-danger" />
            <span className="text-danger">{error}</span>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Model Status Card */}
          <div className="bg-background-card rounded-xl p-6 border border-gray-700/50 shadow-card">
            <div className="flex items-center gap-3 mb-6">
              <div className={`p-2 rounded-lg ${modelStatus?.is_trained ? 'bg-success/20' : 'bg-danger/20'}`}>
                {modelStatus?.is_trained ? (
                  <CheckCircle className="w-6 h-6 text-success" />
                ) : (
                  <XCircle className="w-6 h-6 text-danger" />
                )}
              </div>
              <div>
                <h2 className="text-lg font-bold text-text-primary">Model Status</h2>
                <p className={`text-sm ${modelStatus?.is_trained ? 'text-success' : 'text-danger'}`}>
                  {modelStatus?.is_trained ? 'Trained & Ready' : 'Not Trained'}
                </p>
              </div>
            </div>

            {modelStatus?.model_info && (
              <div className="space-y-3 mb-6">
                <div className="flex justify-between text-sm">
                  <span className="text-text-secondary">Version</span>
                  <span className="font-mono text-text-primary">v{modelStatus.model_info.version}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-text-secondary">Created</span>
                  <span className="font-mono text-text-primary">{formatDate(modelStatus.model_info.created_at)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-text-secondary">Training Records</span>
                  <span className="font-mono text-text-primary">{modelStatus.model_info.training_records?.toLocaleString() || 'N/A'}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-text-secondary">Model Size</span>
                  <span className="font-mono text-text-primary">{modelStatus.model_info.size_kb?.toFixed(1) || 'N/A'} KB</span>
                </div>
              </div>
            )}

            <div className="space-y-3">
              <div className="flex justify-between items-center text-sm">
                <span className="text-text-secondary flex items-center gap-2">
                  <Clock className="w-4 h-4" />
                  Staleness
                </span>
                <span className={`font-mono ${
                  modelStatus?.needs_retraining ? 'text-warning' : 'text-success'
                }`}>
                  {formatHours(modelStatus?.staleness_hours ?? null)}
                </span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-text-secondary">Needs Retraining</span>
                <span className={modelStatus?.needs_retraining ? 'text-warning' : 'text-success'}>
                  {modelStatus?.needs_retraining ? 'Yes' : 'No'}
                </span>
              </div>
            </div>
          </div>

          {/* Training Data Status Card */}
          <div className="bg-background-card rounded-xl p-6 border border-gray-700/50 shadow-card">
            <div className="flex items-center gap-3 mb-6">
              <div className={`p-2 rounded-lg ${dataStatus?.readiness?.is_ready ? 'bg-success/20' : 'bg-warning/20'}`}>
                <Database className={`w-6 h-6 ${dataStatus?.readiness?.is_ready ? 'text-success' : 'text-warning'}`} />
              </div>
              <div>
                <h2 className="text-lg font-bold text-text-primary">Training Data</h2>
                <p className={`text-sm ${dataStatus?.readiness?.is_ready ? 'text-success' : 'text-warning'}`}>
                  {dataStatus?.readiness?.message || 'Checking...'}
                </p>
              </div>
            </div>

            {/* Data Source Indicator */}
            {dataStatus?.readiness?.data_source && (
              <div className={`mb-4 p-2 rounded-lg text-xs flex items-center gap-2 ${
                dataStatus.readiness.data_source === 'gex_structure_daily'
                  ? 'bg-emerald-500/10 text-emerald-400'
                  : dataStatus.readiness.data_source === 'gex_history'
                  ? 'bg-blue-500/10 text-blue-400'
                  : 'bg-gray-700/50 text-gray-400'
              }`}>
                <Database className="w-3 h-3" />
                <span>
                  Will use: <strong>{dataStatus.readiness.data_source}</strong>
                  {dataStatus.readiness.usable_records !== undefined && (
                    <span className="ml-1">({dataStatus.readiness.usable_records.toLocaleString()} records)</span>
                  )}
                </span>
              </div>
            )}

            <div className="space-y-4">
              {/* Primary: gex_structure_daily */}
              <div className={`p-3 rounded-lg ${
                dataStatus?.readiness?.data_source === 'gex_structure_daily'
                  ? 'bg-emerald-500/10 border border-emerald-500/30'
                  : 'bg-gray-700/30'
              }`}>
                <div className="flex justify-between items-center mb-1">
                  <span className="text-sm font-medium flex items-center gap-2">
                    GEX Structure Daily
                    <span className="text-[10px] px-1.5 py-0.5 bg-purple-500/20 text-purple-400 rounded">PRIMARY</span>
                  </span>
                  {dataStatus?.gex_structure_daily?.has_data ? (
                    <CheckCircle className="w-4 h-4 text-emerald-400" />
                  ) : (
                    <XCircle className="w-4 h-4 text-gray-500" />
                  )}
                </div>
                <div className="text-xs text-gray-400">
                  {dataStatus?.gex_structure_daily?.count.toLocaleString() || 0} records
                </div>
                <div className="text-xs text-gray-500">
                  {dataStatus?.gex_structure_daily?.date_range || 'No data'}
                </div>
              </div>

              {/* Fallback: gex_history */}
              <div className={`p-3 rounded-lg ${
                dataStatus?.readiness?.data_source === 'gex_history'
                  ? 'bg-blue-500/10 border border-blue-500/30'
                  : 'bg-gray-700/30'
              }`}>
                <div className="flex justify-between items-center mb-1">
                  <span className="text-sm font-medium flex items-center gap-2">
                    GEX History
                    <span className="text-[10px] px-1.5 py-0.5 bg-blue-500/20 text-blue-400 rounded">FALLBACK</span>
                  </span>
                  {dataStatus?.gex_history?.has_data ? (
                    <CheckCircle className="w-4 h-4 text-emerald-400" />
                  ) : (
                    <XCircle className="w-4 h-4 text-gray-500" />
                  )}
                </div>
                <div className="text-xs text-gray-400">
                  {dataStatus?.gex_history?.unique_days?.toLocaleString() || 0} unique days
                  {dataStatus?.gex_history?.total_snapshots !== undefined && (
                    <span className="text-gray-500"> ({dataStatus.gex_history.total_snapshots.toLocaleString()} snapshots)</span>
                  )}
                </div>
                <div className="text-xs text-gray-500">
                  {dataStatus?.gex_history?.date_range || 'No data'}
                </div>
                {dataStatus?.gex_history?.note && (
                  <div className="text-[10px] text-gray-600 mt-1 italic">
                    {dataStatus.gex_history.note}
                  </div>
                )}
              </div>

              {/* VIX Data */}
              <div className="p-3 bg-gray-700/30 rounded-lg">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-sm font-medium">VIX Data</span>
                  {dataStatus?.vix_daily?.has_data ? (
                    <CheckCircle className="w-4 h-4 text-emerald-400" />
                  ) : (
                    <AlertTriangle className="w-4 h-4 text-yellow-400" />
                  )}
                </div>
                <div className="text-xs text-gray-400">
                  {dataStatus?.vix_daily?.count.toLocaleString() || 0} records
                </div>
                <div className="text-xs text-gray-500">
                  {dataStatus?.vix_daily?.date_range || 'No data'}
                </div>
              </div>

              {/* Diagnostic Recommendations */}
              {diagnostic && diagnostic.recommendations.length > 0 && (
                <div className="mt-4 space-y-2">
                  <h4 className="text-sm font-medium text-gray-300 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-yellow-400" />
                    Recommendations
                  </h4>
                  {diagnostic.recommendations.map((rec, idx) => (
                    <div
                      key={idx}
                      className={`p-2 rounded text-xs ${
                        rec.priority === 'high'
                          ? 'bg-red-500/10 border border-red-500/30 text-red-300'
                          : rec.priority === 'medium'
                          ? 'bg-yellow-500/10 border border-yellow-500/30 text-yellow-300'
                          : rec.priority === 'info'
                          ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-300'
                          : 'bg-gray-700/50 text-gray-400'
                      }`}
                    >
                      <code className="font-mono text-[11px]">{rec.message}</code>
                    </div>
                  ))}

                  {/* Populate from ORAT Database Button - PRIMARY ACTION */}
                  {(!dataStatus?.gex_structure_daily?.has_data || (dataStatus?.gex_structure_daily?.count || 0) < 100) && (
                    <button
                      onClick={handlePopulateFromOrat}
                      disabled={populatingOrat}
                      className={`mt-2 w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                        populatingOrat
                          ? 'bg-gray-700 text-gray-400 cursor-not-allowed'
                          : 'bg-purple-600 hover:bg-purple-500 text-white'
                      }`}
                    >
                      {populatingOrat ? (
                        <>
                          <RefreshCw className="w-4 h-4 animate-spin" />
                          Populating from ORAT (may take 30-60s)...
                        </>
                      ) : (
                        <>
                          <Database className="w-4 h-4" />
                          Populate from ORAT Database (Historical Data)
                        </>
                      )}
                    </button>
                  )}

                  {/* ORAT Populate Result */}
                  {oratResult && (
                    <div className={`p-2 rounded text-xs ${
                      oratResult.success
                        ? 'bg-emerald-500/10 text-emerald-300'
                        : 'bg-red-500/10 text-red-300'
                    }`}>
                      {oratResult.success ? (
                        <>
                          <div>SPY: {oratResult.spy?.inserted || 0} inserted, {oratResult.spy?.skipped || 0} skipped</div>
                          <div>SPX: {oratResult.spx?.inserted || 0} inserted, {oratResult.spx?.skipped || 0} skipped</div>
                          <div className="mt-1 font-medium">Total: {(oratResult.spy?.total_records || 0) + (oratResult.spx?.total_records || 0)} records</div>
                        </>
                      ) : (
                        `Error: ${oratResult.error || 'Population failed'}`
                      )}
                    </div>
                  )}

                  {/* Populate from Snapshots Button - FALLBACK */}
                  {diagnostic.diagnostics?.gex_history?.count > 0 &&
                   diagnostic.diagnostics?.gex_structure_daily?.count === 0 && (
                    <button
                      onClick={handlePopulate}
                      disabled={populating}
                      className={`mt-2 w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                        populating
                          ? 'bg-gray-700 text-gray-400 cursor-not-allowed'
                          : 'bg-blue-600 hover:bg-blue-500 text-white'
                      }`}
                    >
                      {populating ? (
                        <>
                          <RefreshCw className="w-4 h-4 animate-spin" />
                          Building training data...
                        </>
                      ) : (
                        <>
                          <Database className="w-4 h-4" />
                          Build from Live Snapshots (Alternative)
                        </>
                      )}
                    </button>
                  )}

                  {/* Populate Result */}
                  {populateResult && (
                    <div className={`p-2 rounded text-xs ${
                      populateResult.success
                        ? 'bg-emerald-500/10 text-emerald-300'
                        : 'bg-red-500/10 text-red-300'
                    }`}>
                      {populateResult.success
                        ? `Built ${populateResult.data?.rows_inserted_or_updated || 0} training records`
                        : `Error: ${populateResult.error}`}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Sub-Models Status Card */}
          <div className="bg-background-card rounded-xl p-6 border border-gray-700/50 shadow-card">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2 rounded-lg bg-info/20">
                <Zap className="w-6 h-6 text-info" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-text-primary">5 Sub-Models</h2>
                <p className="text-sm text-text-secondary">XGBoost classifiers and regressors</p>
              </div>
            </div>

            <div className="space-y-3">
              {[
                { key: 'direction', label: 'Direction Probability', desc: 'UP/DOWN/FLAT classification', icon: TrendingUp },
                { key: 'flip_gravity', label: 'Flip Gravity', desc: 'Probability of moving toward flip point', icon: Target },
                { key: 'magnet_attraction', label: 'Magnet Attraction', desc: 'Probability of reaching magnets', icon: Activity },
                { key: 'volatility', label: 'Volatility Estimate', desc: 'Expected price range prediction', icon: Zap },
                { key: 'pin_zone', label: 'Pin Zone Behavior', desc: 'Probability of staying pinned', icon: Eye }
              ].map(model => {
                const Icon = model.icon
                const isTrained = modelStatus?.sub_models?.[model.key as keyof typeof modelStatus.sub_models]
                return (
                  <div key={model.key} className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                    <div className="flex items-center gap-3">
                      <Icon className={`w-4 h-4 ${isTrained ? 'text-info' : 'text-text-muted'}`} />
                      <div>
                        <div className="text-sm font-medium text-text-primary">{model.label}</div>
                        <div className="text-xs text-text-muted">{model.desc}</div>
                      </div>
                    </div>
                    {isTrained ? (
                      <CheckCircle className="w-5 h-5 text-success" />
                    ) : (
                      <XCircle className="w-5 h-5 text-text-muted" />
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {/* Usage & Integration Card */}
          <div className="bg-background-card rounded-xl p-6 border border-gray-700/50 shadow-card">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2 rounded-lg bg-primary/20">
                <Info className="w-6 h-6 text-primary" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-text-primary">Integration</h2>
                <p className="text-sm text-text-secondary">How models are used</p>
              </div>
            </div>

            <div className="space-y-4">
              <div className="p-4 bg-gradient-to-r from-info/10 to-transparent border-l-2 border-info rounded-r-lg">
                <div className="flex items-center gap-2 mb-2">
                  <Eye className="w-5 h-5 text-info" />
                  <span className="font-medium text-text-primary">ARGUS (0DTE Gamma)</span>
                </div>
                <p className="text-sm text-text-secondary">
                  {modelStatus?.usage?.argus || '60% ML + 40% distance-weighted probability'}
                </p>
              </div>

              <div className="p-4 bg-gradient-to-r from-primary/10 to-transparent border-l-2 border-primary rounded-r-lg">
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles className="w-5 h-5 text-primary" />
                  <span className="font-medium text-text-primary">HYPERION (Weekly Gamma)</span>
                </div>
                <p className="text-sm text-text-secondary">
                  {modelStatus?.usage?.hyperion || '60% ML + 40% distance-weighted probability'}
                </p>
              </div>

              <div className="mt-4 p-3 bg-background-hover rounded-lg">
                <h4 className="text-sm font-medium text-text-primary mb-2">Probability Calculation</h4>
                <div className="font-mono text-xs text-text-secondary bg-background-deep p-2 rounded">
                  probability = (0.6 × ML_prob) + (0.4 × distance_prob)
                </div>
                <p className="text-xs text-text-muted mt-2">
                  When ML models are not trained, falls back to 100% distance-based calculation.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Training Controls */}
        <div className="mt-6 bg-background-card rounded-xl p-6 border border-gray-700/50 shadow-card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <Play className="w-5 h-5 text-success" />
              <h2 className="text-lg font-bold text-text-primary">Training Controls</h2>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
            <button
              onClick={handleTrain}
              disabled={training || !dataStatus?.readiness?.is_ready}
              className={`flex items-center gap-2 px-6 py-3 rounded-lg font-medium transition-all ${
                training || !dataStatus?.readiness?.is_ready
                  ? 'bg-background-hover text-text-muted cursor-not-allowed'
                  : 'bg-success hover:bg-success-hover text-white'
              }`}
            >
              {training ? (
                <>
                  <RefreshCw className="w-5 h-5 animate-spin" />
                  Training in progress...
                </>
              ) : (
                <>
                  <Play className="w-5 h-5" />
                  Train Models
                </>
              )}
            </button>

            <div className="text-sm text-text-secondary">
              {!dataStatus?.readiness?.is_ready ? (
                <span className="text-warning">
                  Need at least {dataStatus?.readiness?.min_records_needed || 100} GEX records to train
                </span>
              ) : modelStatus?.is_trained ? (
                <span>Models are trained. Retrain to update with latest data.</span>
              ) : (
                <span>Click to train all 5 models on historical GEX data.</span>
              )}
            </div>
          </div>

          {/* Scheduled Training Info */}
          <div className="mt-4 p-3 bg-primary/10 border border-primary/30 rounded-lg">
            <div className="flex items-center gap-2 text-sm">
              <Clock className="w-4 h-4 text-primary" />
              <span className="text-primary font-medium">Auto-Training Schedule:</span>
              <span className="text-text-primary">Every Sunday at 6:00 PM CT</span>
            </div>
            <p className="text-xs text-text-muted mt-1 ml-6">
              Models automatically retrain weekly when older than 7 days. Training uses GEX data from SPX and SPY.
            </p>
          </div>

          {/* Training Result */}
          {trainingResult && (
            <div className="mt-4 p-4 bg-background-hover rounded-lg">
              <h4 className="text-sm font-medium text-text-primary mb-2 flex items-center gap-2">
                {trainingResult.success ? (
                  <>
                    <CheckCircle className="w-4 h-4 text-success" />
                    Training Complete
                  </>
                ) : (
                  <>
                    <XCircle className="w-4 h-4 text-danger" />
                    Training Failed
                  </>
                )}
              </h4>
              {trainingResult.success ? (
                <p className="text-sm text-text-secondary">{trainingResult.message}</p>
              ) : (
                <p className="text-sm text-danger">{trainingResult.error}</p>
              )}
            </div>
          )}
        </div>

        {/* Model Metrics (if trained) */}
        {modelStatus?.model_info?.metrics && Object.keys(modelStatus.model_info.metrics).length > 0 && (
          <div className="mt-6 bg-background-card rounded-xl p-6 border border-gray-700/50 shadow-card">
            <h2 className="text-lg font-bold text-text-primary mb-4 flex items-center gap-2">
              <Activity className="w-5 h-5 text-primary" />
              Training Metrics
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {Object.entries(modelStatus.model_info.metrics).map(([key, value]) => {
                // Handle nested objects by extracting accuracy or first numeric value
                let displayValue: string
                if (typeof value === 'number') {
                  displayValue = value < 1 ? `${(value * 100).toFixed(1)}%` : value.toFixed(2)
                } else if (typeof value === 'object' && value !== null) {
                  // Extract accuracy or cv_mean from nested metrics
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
                    <div className="text-xs text-text-secondary mb-1">
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
      </main>
    </>
  )
}
