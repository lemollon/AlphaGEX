'use client'

import { useState, useEffect } from 'react'
import {
  Database, RefreshCw, ChevronDown, ChevronUp, Eye, EyeOff,
  Brain, TrendingUp, Activity, Zap, Target, BarChart3,
  FileText, AlertTriangle, Download, Filter, Clock, Layers
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { api } from '@/lib/api'

interface DataCategory {
  display_name: string
  table: string
  total_records: number
  latest_entry: string | null
  hidden_fields: string[]
  hidden_field_count: number
  error?: string
}

interface TransparencySummary {
  [key: string]: DataCategory
}

type ActiveTab = 'summary' | 'regime' | 'vix' | 'ai' | 'sizing' | 'decisions' | 'options' | 'strike' | 'greeks' | 'dte' | 'psychology' | 'volatility' | 'ml' | 'argus' | 'backtest' | 'walkforward' | 'spreadwidth' | 'patterns' | 'volsnapshots'

export default function DataTransparencyPage() {
  const [summary, setSummary] = useState<TransparencySummary | null>(null)
  const [activeTab, setActiveTab] = useState<ActiveTab>('summary')
  const [loading, setLoading] = useState(true)
  const [dataLoading, setDataLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Data for each tab
  const [regimeData, setRegimeData] = useState<any>(null)
  const [vixData, setVixData] = useState<any>(null)
  const [aiData, setAiData] = useState<any>(null)
  const [sizingData, setSizingData] = useState<any>(null)
  const [decisionsData, setDecisionsData] = useState<any>(null)
  const [optionsFlowData, setOptionsFlowData] = useState<any>(null)
  const [strikeData, setStrikeData] = useState<any>(null)
  const [greeksData, setGreeksData] = useState<any>(null)
  const [dteData, setDteData] = useState<any>(null)
  const [psychologyData, setPsychologyData] = useState<any>(null)
  const [volatilityData, setVolatilityData] = useState<any>(null)
  const [mlData, setMlData] = useState<any>(null)
  const [argusData, setArgusData] = useState<any>(null)
  const [backtestData, setBacktestData] = useState<any>(null)
  const [walkforwardData, setWalkforwardData] = useState<any>(null)
  const [spreadwidthData, setSpreadwidthData] = useState<any>(null)
  const [patternsData, setPatternsData] = useState<any>(null)
  const [volsnapshotsData, setVolsnapshotsData] = useState<any>(null)

  const [expandedRecords, setExpandedRecords] = useState<Set<number>>(new Set())
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    loadSummary()
  }, [])

  useEffect(() => {
    if (activeTab !== 'summary') {
      loadTabData(activeTab)
    }
  }, [activeTab])

  const loadSummary = async () => {
    setLoading(true)
    try {
      const response = await api.get('/api/data-transparency/summary')
      if (response.data?.success) {
        setSummary(response.data.data)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load summary')
    }
    setLoading(false)
  }

  const loadTabData = async (tab: ActiveTab) => {
    setDataLoading(true)
    try {
      let endpoint = ''
      let setter: (data: any) => void = () => {}

      switch (tab) {
        case 'regime':
          endpoint = '/api/data-transparency/regime-signals'
          setter = setRegimeData
          break
        case 'vix':
          endpoint = '/api/data-transparency/vix-term-structure'
          setter = setVixData
          break
        case 'ai':
          endpoint = '/api/data-transparency/ai-analysis-history'
          setter = setAiData
          break
        case 'sizing':
          endpoint = '/api/data-transparency/position-sizing'
          setter = setSizingData
          break
        case 'decisions':
          endpoint = '/api/data-transparency/trading-decisions-full'
          setter = setDecisionsData
          break
        case 'options':
          endpoint = '/api/data-transparency/options-flow'
          setter = setOptionsFlowData
          break
        case 'strike':
          endpoint = '/api/data-transparency/strike-performance'
          setter = setStrikeData
          break
        case 'greeks':
          endpoint = '/api/data-transparency/greeks-performance'
          setter = setGreeksData
          break
        case 'dte':
          endpoint = '/api/data-transparency/dte-performance'
          setter = setDteData
          break
        case 'psychology':
          endpoint = '/api/data-transparency/psychology-patterns'
          setter = setPsychologyData
          break
        case 'volatility':
          endpoint = '/api/data-transparency/volatility-surface-history'
          setter = setVolatilityData
          break
        case 'ml':
          endpoint = '/api/data-transparency/ml-model-details'
          setter = setMlData
          break
        case 'argus':
          endpoint = '/api/data-transparency/argus-gamma-details'
          setter = setArgusData
          break
        case 'backtest':
          endpoint = '/api/data-transparency/backtest-trades-full'
          setter = setBacktestData
          break
        case 'walkforward':
          endpoint = '/api/data-transparency/walk-forward-results'
          setter = setWalkforwardData
          break
        case 'spreadwidth':
          endpoint = '/api/data-transparency/spread-width-performance'
          setter = setSpreadwidthData
          break
        case 'patterns':
          endpoint = '/api/data-transparency/pattern-learning'
          setter = setPatternsData
          break
        case 'volsnapshots':
          endpoint = '/api/data-transparency/volatility-surface-snapshots'
          setter = setVolsnapshotsData
          break
      }

      if (endpoint) {
        const response = await api.get(endpoint)
        if (response.data?.success) {
          setter(response.data.data)
        }
      }
    } catch (err: any) {
      console.error(`Failed to load ${tab} data:`, err)
    }
    setDataLoading(false)
  }

  const toggleRecord = (index: number) => {
    const newExpanded = new Set(expandedRecords)
    if (newExpanded.has(index)) {
      newExpanded.delete(index)
    } else {
      newExpanded.add(index)
    }
    setExpandedRecords(newExpanded)
  }

  const tabs = [
    { id: 'summary', name: 'Summary', icon: Database, color: 'bg-gray-600' },
    { id: 'regime', name: 'Regime Signals', icon: Activity, color: 'bg-blue-600', count: summary?.regime_signals?.total_records },
    { id: 'vix', name: 'VIX Term Structure', icon: TrendingUp, color: 'bg-purple-600', count: summary?.vix_term_structure?.total_records },
    { id: 'ai', name: 'AI Analysis', icon: Brain, color: 'bg-pink-600', count: summary?.ai_analysis_history?.total_records },
    { id: 'sizing', name: 'Position Sizing', icon: Target, color: 'bg-orange-600', count: summary?.position_sizing_history?.total_records },
    { id: 'decisions', name: 'Trading Decisions', icon: FileText, color: 'bg-green-600', count: summary?.autonomous_trader_logs?.total_records },
    { id: 'options', name: 'Options Flow', icon: Layers, color: 'bg-cyan-600', count: summary?.options_flow?.total_records },
    { id: 'strike', name: 'Strike Performance', icon: BarChart3, color: 'bg-yellow-600', count: summary?.strike_performance?.total_records },
    { id: 'greeks', name: 'Greeks Efficiency', icon: Zap, color: 'bg-red-600', count: summary?.greeks_performance?.total_records },
    { id: 'dte', name: 'DTE Performance', icon: Clock, color: 'bg-indigo-600', count: summary?.dte_performance?.total_records },
    { id: 'psychology', name: 'Psychology Patterns', icon: AlertTriangle, color: 'bg-amber-600', count: summary?.sucker_statistics?.total_records },
    { id: 'volatility', name: 'Volatility Surface', icon: Activity, color: 'bg-teal-600' },
    { id: 'volsnapshots', name: 'Vol Surface History', icon: TrendingUp, color: 'bg-emerald-600' },
    { id: 'ml', name: 'ML Models', icon: Brain, color: 'bg-violet-600' },
    { id: 'argus', name: 'ARGUS Gamma', icon: Eye, color: 'bg-rose-600' },
    { id: 'backtest', name: 'Backtest Trades', icon: FileText, color: 'bg-sky-600' },
    { id: 'walkforward', name: 'Walk-Forward', icon: BarChart3, color: 'bg-lime-600' },
    { id: 'spreadwidth', name: 'Spread Width', icon: Layers, color: 'bg-fuchsia-600' },
    { id: 'patterns', name: 'Pattern Learning', icon: Target, color: 'bg-stone-600' },
  ]

  // Export handlers
  const handleExport = async (category: string, format: 'csv' | 'json') => {
    setExporting(true)
    try {
      const response = await api.get(`/api/data-transparency/export/${category}?format=${format}&limit=5000`, {
        responseType: 'blob'
      })
      const blob = new Blob([response.data], {
        type: format === 'csv' ? 'text/csv' : 'application/json'
      })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `alphagex-${category}-${new Date().toISOString().split('T')[0]}.${format}`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err) {
      console.error('Export failed:', err)
    }
    setExporting(false)
  }

  const handleExportAll = async () => {
    setExporting(true)
    try {
      const response = await api.get('/api/data-transparency/export-all?limit_per_table=500', {
        responseType: 'blob'
      })
      const blob = new Blob([response.data], { type: 'application/json' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `alphagex-full-transparency-${new Date().toISOString().split('T')[0]}.json`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err) {
      console.error('Export all failed:', err)
    }
    setExporting(false)
  }

  // Map tab IDs to export categories
  const tabToExportCategory: Record<string, string> = {
    'regime': 'regime',
    'vix': 'vix',
    'ai': 'ai',
    'sizing': 'sizing',
    'decisions': 'decisions',
    'options': 'options',
    'strike': 'strike',
    'greeks': 'greeks',
    'dte': 'dte',
    'psychology': 'psychology',
    'backtest': 'backtest',
    'walkforward': 'walk-forward',
    'spreadwidth': 'spread-width',
    'patterns': 'patterns',
    'volsnapshots': 'vol-surface'
  }

  const renderDataTable = (data: any, title: string) => {
    if (!data?.records || data.records.length === 0) {
      return (
        <div className="p-8 text-center text-gray-400">
          <Database className="w-12 h-12 mx-auto mb-3 text-gray-600" />
          <p>No data available</p>
        </div>
      )
    }

    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-semibold text-white">{title}</h3>
            <p className="text-sm text-gray-400">
              Showing {data.records.length} of {data.total_records?.toLocaleString()} records
              {data.column_count && ` | ${data.column_count} columns`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">
              Columns: {data.columns?.join(', ').substring(0, 100)}...
            </span>
          </div>
        </div>

        <div className="space-y-2 max-h-[600px] overflow-y-auto">
          {data.records.map((record: any, index: number) => (
            <div
              key={index}
              className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden"
            >
              <button
                onClick={() => toggleRecord(index)}
                className="w-full p-4 flex items-center justify-between hover:bg-gray-700/50 transition-colors"
              >
                <div className="flex items-center gap-4 text-left">
                  <span className="text-gray-500 text-xs w-8">#{index + 1}</span>
                  <div>
                    <span className="text-white font-medium">
                      {record.created_at || record.timestamp || record.trade_date || 'N/A'}
                    </span>
                    {record.symbol && (
                      <span className="ml-2 px-2 py-0.5 bg-blue-500/30 text-blue-300 rounded text-xs">
                        {record.symbol}
                      </span>
                    )}
                    {record.bot_name && (
                      <span className="ml-2 px-2 py-0.5 bg-orange-500/30 text-orange-300 rounded text-xs">
                        {record.bot_name}
                      </span>
                    )}
                    {record.regime && (
                      <span className={`ml-2 px-2 py-0.5 rounded text-xs ${
                        record.regime === 'POSITIVE' ? 'bg-green-500/30 text-green-300' :
                        record.regime === 'NEGATIVE' ? 'bg-red-500/30 text-red-300' :
                        'bg-gray-600 text-gray-300'
                      }`}>
                        {record.regime}
                      </span>
                    )}
                  </div>
                </div>
                {expandedRecords.has(index) ? (
                  <ChevronUp className="w-5 h-5 text-gray-400" />
                ) : (
                  <ChevronDown className="w-5 h-5 text-gray-400" />
                )}
              </button>

              {expandedRecords.has(index) && (
                <div className="border-t border-gray-700 p-4 bg-gray-900/50">
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {Object.entries(record).map(([key, value]) => (
                      <div key={key} className="bg-gray-800 rounded p-2">
                        <p className="text-xs text-gray-500 mb-1">{key}</p>
                        <p className="text-sm text-white break-words">
                          {value === null || value === undefined
                            ? <span className="text-gray-600 italic">null</span>
                            : typeof value === 'object'
                              ? <pre className="text-xs overflow-auto max-h-32">{JSON.stringify(value, null, 2)}</pre>
                              : String(value).length > 200
                                ? <span title={String(value)}>{String(value).substring(0, 200)}...</span>
                                : String(value)
                          }
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    )
  }

  const renderVolatilitySurface = () => {
    if (!volatilityData) {
      return (
        <div className="p-8 text-center text-gray-400">
          <Activity className="w-12 h-12 mx-auto mb-3 text-gray-600" />
          <p>Loading volatility surface data...</p>
        </div>
      )
    }

    const analysis = volatilityData.current_analysis

    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-white">Volatility Surface Analysis</h3>
            <p className="text-sm text-gray-400">
              Live analysis as of {volatilityData.timestamp}
            </p>
          </div>
          <span className="text-sm text-gray-400">
            Spot: ${volatilityData.spot_price?.toFixed(2)}
          </span>
        </div>

        {analysis ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {/* ATM IV */}
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <p className="text-gray-400 text-sm">ATM IV</p>
              <p className="text-2xl font-bold text-white">
                {(analysis.atm_iv * 100).toFixed(2)}%
              </p>
            </div>

            {/* IV Rank */}
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <p className="text-gray-400 text-sm">IV Rank</p>
              <p className={`text-2xl font-bold ${
                analysis.iv_rank > 70 ? 'text-red-400' :
                analysis.iv_rank > 40 ? 'text-yellow-400' :
                'text-green-400'
              }`}>
                {analysis.iv_rank?.toFixed(1)}%
              </p>
            </div>

            {/* IV Percentile */}
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <p className="text-gray-400 text-sm">IV Percentile</p>
              <p className="text-2xl font-bold text-white">
                {analysis.iv_percentile?.toFixed(1)}%
              </p>
            </div>

            {/* Skew Regime */}
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <p className="text-gray-400 text-sm">Skew Regime</p>
              <p className={`text-lg font-bold ${
                analysis.skew_regime?.includes('PUT') ? 'text-red-400' :
                analysis.skew_regime?.includes('CALL') ? 'text-green-400' :
                'text-blue-400'
              }`}>
                {analysis.skew_regime}
              </p>
            </div>

            {/* 25-Delta Skew */}
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <p className="text-gray-400 text-sm">25-Delta Skew</p>
              <p className="text-xl font-bold text-white">
                {(analysis.skew_25d * 100).toFixed(2)}%
              </p>
            </div>

            {/* Risk Reversal */}
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <p className="text-gray-400 text-sm">Risk Reversal</p>
              <p className={`text-xl font-bold ${
                analysis.risk_reversal < 0 ? 'text-red-400' : 'text-green-400'
              }`}>
                {(analysis.risk_reversal * 100).toFixed(2)}%
              </p>
            </div>

            {/* Term Regime */}
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <p className="text-gray-400 text-sm">Term Structure</p>
              <p className={`text-lg font-bold ${
                analysis.term_regime?.includes('BACKWARDATION') ? 'text-red-400' :
                'text-green-400'
              }`}>
                {analysis.term_regime}
              </p>
            </div>

            {/* Term Slope */}
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <p className="text-gray-400 text-sm">Term Slope</p>
              <p className="text-xl font-bold text-white">
                {(analysis.term_slope * 1000).toFixed(4)}/day
              </p>
            </div>

            {/* Recommended DTE */}
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <p className="text-gray-400 text-sm">Recommended DTE</p>
              <p className="text-2xl font-bold text-blue-400">
                {analysis.recommended_dte} days
              </p>
            </div>

            {/* Directional Bias */}
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <p className="text-gray-400 text-sm">Directional Bias</p>
              <p className={`text-lg font-bold ${
                analysis.directional_bias === 'bullish' ? 'text-green-400' :
                analysis.directional_bias === 'bearish' ? 'text-red-400' :
                'text-gray-400'
              }`}>
                {analysis.directional_bias?.toUpperCase()}
              </p>
            </div>

            {/* Should Sell Premium */}
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <p className="text-gray-400 text-sm">Sell Premium?</p>
              <p className={`text-lg font-bold ${
                analysis.should_sell_premium ? 'text-green-400' : 'text-red-400'
              }`}>
                {analysis.should_sell_premium ? 'YES' : 'NO'}
              </p>
              {analysis.sell_reasoning && (
                <p className="text-xs text-gray-500 mt-1">{analysis.sell_reasoning}</p>
              )}
            </div>

            {/* Optimal Strategy */}
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <p className="text-gray-400 text-sm">Optimal Strategy</p>
              <p className="text-sm font-medium text-white">
                {analysis.optimal_strategy?.strategy_type || 'N/A'}
              </p>
              {analysis.optimal_strategy?.reasoning?.map((r: string, i: number) => (
                <p key={i} className="text-xs text-gray-500 mt-1">{r}</p>
              ))}
            </div>
          </div>
        ) : (
          <div className="p-8 text-center text-gray-400">
            <p>Volatility surface analysis not available</p>
          </div>
        )}
      </div>
    )
  }

  const renderMLModels = () => {
    if (!mlData) {
      return (
        <div className="p-8 text-center text-gray-400">
          <Brain className="w-12 h-12 mx-auto mb-3 text-gray-600" />
          <p>Loading ML model data...</p>
        </div>
      )
    }

    return (
      <div className="space-y-6">
        {/* Prometheus Training History */}
        {mlData.prometheus_training?.length > 0 && (
          <div>
            <h3 className="text-lg font-semibold text-white mb-4">Prometheus Training History</h3>
            <div className="space-y-3">
              {mlData.prometheus_training.map((training: any, index: number) => (
                <div key={index} className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-white font-medium">{training.training_id}</span>
                    <span className="text-gray-400 text-sm">{training.training_date}</span>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <p className="text-xs text-gray-500">Accuracy</p>
                      <p className="text-lg font-bold text-green-400">
                        {(training.accuracy * 100).toFixed(2)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">F1 Score</p>
                      <p className="text-lg font-bold text-blue-400">
                        {(training.f1_score * 100).toFixed(2)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">Brier Score</p>
                      <p className="text-lg font-bold text-purple-400">
                        {training.brier_score?.toFixed(4)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">Samples</p>
                      <p className="text-lg font-bold text-white">
                        {training.total_samples?.toLocaleString()}
                      </p>
                    </div>
                  </div>
                  {training.honest_assessment && (
                    <div className="mt-3 p-3 bg-gray-900 rounded">
                      <p className="text-xs text-gray-500 mb-1">Honest Assessment</p>
                      <p className="text-sm text-gray-300">{training.honest_assessment}</p>
                    </div>
                  )}
                  {training.feature_importance && (
                    <div className="mt-3">
                      <p className="text-xs text-gray-500 mb-1">Feature Importance</p>
                      <pre className="text-xs text-gray-400 overflow-auto max-h-32 bg-gray-900 p-2 rounded">
                        {JSON.stringify(training.feature_importance, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Calibration History */}
        {mlData.calibration_history?.length > 0 && (
          <div>
            <h3 className="text-lg font-semibold text-white mb-4">Calibration History</h3>
            <div className="space-y-2">
              {mlData.calibration_history.slice(0, 10).map((cal: any, index: number) => (
                <div key={index} className="bg-gray-800 rounded-lg p-3 border border-gray-700">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-300">{cal.created_at}</span>
                    <div className="flex items-center gap-4 text-sm">
                      {Object.entries(cal).filter(([k]) => k !== 'id' && k !== 'created_at').map(([key, value]) => (
                        <span key={key} className="text-gray-400">
                          {key}: <span className="text-white">{typeof value === 'number' ? (value as number).toFixed(4) : String(value)}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ML Predictions */}
        {mlData.predictions?.length > 0 && (
          <div>
            <h3 className="text-lg font-semibold text-white mb-4">Recent ML Predictions ({mlData.predictions.length})</h3>
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {mlData.predictions.slice(0, 20).map((pred: any, index: number) => (
                <div key={index} className="bg-gray-800 rounded-lg p-3 border border-gray-700 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-gray-400 text-sm">{pred.created_at}</span>
                    <span className="text-white">{pred.symbol || 'SPY'}</span>
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      pred.prediction_type === 'WIN' ? 'bg-green-500/30 text-green-300' :
                      'bg-gray-600 text-gray-300'
                    }`}>
                      {pred.prediction_type}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-sm">
                    <span className="text-gray-400">
                      Predicted: <span className="text-white">{pred.predicted_value?.toFixed(2)}</span>
                    </span>
                    <span className="text-gray-400">
                      Confidence: <span className="text-blue-400">{(pred.confidence * 100).toFixed(1)}%</span>
                    </span>
                    {pred.actual_value !== null && (
                      <span className={`${pred.correct ? 'text-green-400' : 'text-red-400'}`}>
                        Actual: {pred.actual_value?.toFixed(2)} {pred.correct ? '(Correct)' : '(Wrong)'}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  const renderPsychologyPatterns = () => {
    if (!psychologyData) {
      return (
        <div className="p-8 text-center text-gray-400">
          <AlertTriangle className="w-12 h-12 mx-auto mb-3 text-gray-600" />
          <p>Loading psychology data...</p>
        </div>
      )
    }

    return (
      <div className="space-y-6">
        {/* Sucker Statistics */}
        {psychologyData.sucker_statistics?.length > 0 && (
          <div>
            <h3 className="text-lg font-semibold text-white mb-4">Sucker Statistics (Hidden Data)</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {psychologyData.sucker_statistics.map((stat: any, index: number) => (
                <div key={index} className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                  <p className="text-white font-medium mb-2">{stat.scenario_type}</p>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <p className="text-gray-500">Occurrences</p>
                      <p className="text-white font-bold">{stat.total_occurrences}</p>
                    </div>
                    <div>
                      <p className="text-gray-500">Failure Rate</p>
                      <p className="text-red-400 font-bold">{(stat.failure_rate * 100).toFixed(1)}%</p>
                    </div>
                    <div className="col-span-2">
                      <p className="text-gray-500">Avg Price Change When Failed</p>
                      <p className="text-yellow-400 font-bold">{stat.avg_price_change_when_failed?.toFixed(2)}%</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Liberation Outcomes */}
        {psychologyData.liberation_outcomes?.length > 0 && (
          <div>
            <h3 className="text-lg font-semibold text-white mb-4">Liberation Outcomes (Hidden Data)</h3>
            <div className="space-y-3">
              {psychologyData.liberation_outcomes.map((outcome: any, index: number) => (
                <div key={index} className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <span className="text-gray-400">{outcome.signal_date}</span>
                      <span className="px-2 py-0.5 bg-blue-500/30 text-blue-300 rounded text-xs">
                        Strike: {outcome.strike}
                      </span>
                    </div>
                    <span className={`px-2 py-1 rounded text-sm font-medium ${
                      outcome.breakout_occurred ? 'bg-green-500/30 text-green-300' : 'bg-red-500/30 text-red-300'
                    }`}>
                      {outcome.breakout_occurred ? 'BREAKOUT' : 'NO BREAKOUT'}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                    <div>
                      <p className="text-gray-500">Price at Signal</p>
                      <p className="text-white">${outcome.price_at_signal?.toFixed(2)}</p>
                    </div>
                    <div>
                      <p className="text-gray-500">Price at Liberation</p>
                      <p className="text-white">${outcome.price_at_liberation?.toFixed(2)}</p>
                    </div>
                    <div>
                      <p className="text-gray-500">Price 1D Later</p>
                      <p className="text-white">${outcome.price_1d_later?.toFixed(2)}</p>
                    </div>
                    <div>
                      <p className="text-gray-500">Max Move %</p>
                      <p className="text-green-400 font-bold">{outcome.max_move_pct?.toFixed(2)}%</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Psychology Analysis */}
        {psychologyData.psychology_analysis?.length > 0 && (
          <div>
            <h3 className="text-lg font-semibold text-white mb-4">Psychology Analysis</h3>
            <div className="space-y-2">
              {psychologyData.psychology_analysis.slice(0, 20).map((analysis: any, index: number) => (
                <div key={index} className="bg-gray-800 rounded-lg p-3 border border-gray-700">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="text-gray-400 text-sm">{analysis.created_at}</span>
                      <span className={`px-2 py-0.5 rounded text-xs ${
                        analysis.regime_type === 'LIBERATION' ? 'bg-green-500/30 text-green-300' :
                        analysis.regime_type === 'FALSE_FLOOR' ? 'bg-red-500/30 text-red-300' :
                        'bg-gray-600 text-gray-300'
                      }`}>
                        {analysis.regime_type}
                      </span>
                      {analysis.psychology_trap && (
                        <span className="px-2 py-0.5 bg-yellow-500/30 text-yellow-300 rounded text-xs">
                          TRAP: {analysis.psychology_trap}
                        </span>
                      )}
                    </div>
                    <div className="text-sm">
                      <span className="text-gray-400">Confidence: </span>
                      <span className="text-white">{(analysis.confidence * 100).toFixed(1)}%</span>
                      {analysis.trap_probability && (
                        <>
                          <span className="text-gray-400 ml-3">Trap Prob: </span>
                          <span className="text-red-400">{(analysis.trap_probability * 100).toFixed(1)}%</span>
                        </>
                      )}
                    </div>
                  </div>
                  {analysis.reasoning && (
                    <p className="text-sm text-gray-400 mt-2">{analysis.reasoning}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-900">
      <Navigation />
      <main className="lg:pl-16 pt-24">
        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Eye className="w-8 h-8 text-purple-500" />
              <div>
                <h1 className="text-2xl font-bold text-white">Data Transparency</h1>
                <p className="text-gray-400">Complete visibility into ALL collected data not shown in main UI</p>
              </div>
            </div>
            <button
              onClick={() => {
                loadSummary()
                if (activeTab !== 'summary') loadTabData(activeTab)
              }}
              disabled={loading || dataLoading}
              className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300 disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${(loading || dataLoading) ? 'animate-spin' : ''}`} />
              Refresh
            </button>

            {/* Export buttons */}
            {activeTab !== 'summary' && tabToExportCategory[activeTab] && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleExport(tabToExportCategory[activeTab], 'csv')}
                  disabled={exporting}
                  className="flex items-center gap-2 px-3 py-2 bg-green-600 hover:bg-green-500 rounded-lg text-white text-sm disabled:opacity-50"
                >
                  <Download className="w-4 h-4" />
                  CSV
                </button>
                <button
                  onClick={() => handleExport(tabToExportCategory[activeTab], 'json')}
                  disabled={exporting}
                  className="flex items-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-white text-sm disabled:opacity-50"
                >
                  <Download className="w-4 h-4" />
                  JSON
                </button>
              </div>
            )}

            {activeTab === 'summary' && (
              <button
                onClick={handleExportAll}
                disabled={exporting}
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded-lg text-white disabled:opacity-50"
              >
                <Download className="w-4 h-4" />
                {exporting ? 'Exporting...' : 'Export All'}
              </button>
            )}
          </div>

          {/* Tab Navigation */}
          <div className="flex flex-wrap gap-2 mb-6 pb-4 border-b border-gray-700 overflow-x-auto">
            {tabs.map((tab) => {
              const Icon = tab.icon
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as ActiveTab)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                    activeTab === tab.id
                      ? `${tab.color} text-white`
                      : 'bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {tab.name}
                  {tab.count !== undefined && tab.count > 0 && (
                    <span className="ml-1 px-2 py-0.5 bg-black/20 rounded text-xs">
                      {tab.count.toLocaleString()}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          {/* Content */}
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
            {loading && activeTab === 'summary' ? (
              <div className="flex items-center justify-center p-12">
                <RefreshCw className="w-8 h-8 animate-spin text-purple-500" />
              </div>
            ) : dataLoading ? (
              <div className="flex items-center justify-center p-12">
                <RefreshCw className="w-8 h-8 animate-spin text-purple-500" />
                <span className="ml-3 text-gray-400">Loading {activeTab} data...</span>
              </div>
            ) : activeTab === 'summary' ? (
              <div className="space-y-6">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-gray-900 rounded-lg p-4">
                    <p className="text-gray-400 text-sm">Data Categories</p>
                    <p className="text-3xl font-bold text-white">
                      {summary ? Object.keys(summary).length : 0}
                    </p>
                  </div>
                  <div className="bg-gray-900 rounded-lg p-4">
                    <p className="text-gray-400 text-sm">Total Hidden Fields</p>
                    <p className="text-3xl font-bold text-purple-400">
                      {summary ? Object.values(summary).reduce((sum, cat) => sum + (cat.hidden_field_count || 0), 0) : 0}
                    </p>
                  </div>
                  <div className="bg-gray-900 rounded-lg p-4">
                    <p className="text-gray-400 text-sm">Total Records</p>
                    <p className="text-3xl font-bold text-blue-400">
                      {summary ? Object.values(summary).reduce((sum, cat) => sum + (cat.total_records || 0), 0).toLocaleString() : 0}
                    </p>
                  </div>
                  <div className="bg-gray-900 rounded-lg p-4">
                    <p className="text-gray-400 text-sm">UI Display Rate</p>
                    <p className="text-3xl font-bold text-red-400">~9%</p>
                  </div>
                </div>

                <div className="space-y-4">
                  <h3 className="text-lg font-semibold text-white">Hidden Data Categories</h3>
                  {summary && Object.entries(summary).map(([key, category]) => (
                    <div key={key} className="bg-gray-900 rounded-lg p-4 border border-gray-700">
                      <div className="flex items-center justify-between mb-3">
                        <div>
                          <h4 className="text-white font-medium">{category.display_name}</h4>
                          <p className="text-gray-500 text-sm">{category.table}</p>
                        </div>
                        <div className="text-right">
                          <p className="text-white font-bold">{category.total_records?.toLocaleString() || 0} records</p>
                          <p className="text-purple-400 text-sm">{category.hidden_field_count} hidden fields</p>
                        </div>
                      </div>
                      {category.hidden_fields && (
                        <div className="flex flex-wrap gap-2">
                          {category.hidden_fields.slice(0, 10).map((field, idx) => (
                            <span key={idx} className="px-2 py-1 bg-gray-800 text-gray-400 rounded text-xs">
                              {field}
                            </span>
                          ))}
                          {category.hidden_fields.length > 10 && (
                            <span className="px-2 py-1 bg-purple-500/30 text-purple-300 rounded text-xs">
                              +{category.hidden_fields.length - 10} more
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ) : activeTab === 'volatility' ? (
              renderVolatilitySurface()
            ) : activeTab === 'ml' ? (
              renderMLModels()
            ) : activeTab === 'psychology' ? (
              renderPsychologyPatterns()
            ) : activeTab === 'regime' ? (
              renderDataTable(regimeData, 'Regime Signals (80+ columns)')
            ) : activeTab === 'vix' ? (
              renderDataTable(vixData, 'VIX Term Structure')
            ) : activeTab === 'ai' ? (
              renderDataTable(aiData, 'AI Analysis History')
            ) : activeTab === 'sizing' ? (
              renderDataTable(sizingData, 'Position Sizing History')
            ) : activeTab === 'decisions' ? (
              renderDataTable(decisionsData, 'Full Trading Decisions (62+ fields)')
            ) : activeTab === 'options' ? (
              renderDataTable(optionsFlowData, 'Options Flow')
            ) : activeTab === 'strike' ? (
              renderDataTable(strikeData, 'Strike Performance')
            ) : activeTab === 'greeks' ? (
              renderDataTable(greeksData, 'Greeks Efficiency')
            ) : activeTab === 'dte' ? (
              renderDataTable(dteData, 'DTE Performance')
            ) : activeTab === 'argus' ? (
              <div className="space-y-6">
                {argusData?.gamma_flips?.length > 0 && (
                  <div>
                    <h3 className="text-lg font-semibold text-white mb-4">Gamma Flips</h3>
                    <div className="space-y-2">
                      {argusData.gamma_flips.slice(0, 20).map((flip: any, index: number) => (
                        <div key={index} className="bg-gray-900 rounded p-3 border border-gray-700">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                              <span className="text-gray-400 text-sm">{flip.flip_time}</span>
                              <span className="px-2 py-0.5 bg-blue-500/30 text-blue-300 rounded text-xs">
                                Strike: {flip.strike}
                              </span>
                              <span className={`px-2 py-0.5 rounded text-xs ${
                                flip.flip_direction === 'POS_TO_NEG' ? 'bg-red-500/30 text-red-300' : 'bg-green-500/30 text-green-300'
                              }`}>
                                {flip.flip_direction}
                              </span>
                            </div>
                            <div className="text-sm">
                              <span className="text-gray-400">Before: {flip.gamma_before?.toFixed(0)}</span>
                              <span className="text-gray-500 mx-2">→</span>
                              <span className="text-white">After: {flip.gamma_after?.toFixed(0)}</span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {argusData?.predictions_with_outcomes?.length > 0 && (
                  <div>
                    <h3 className="text-lg font-semibold text-white mb-4">Predictions with Outcomes</h3>
                    <div className="space-y-2">
                      {argusData.predictions_with_outcomes.slice(0, 20).map((pred: any, index: number) => (
                        <div key={index} className="bg-gray-900 rounded p-3 border border-gray-700">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                              <span className="text-gray-400 text-sm">{pred.prediction_date}</span>
                              <span className="px-2 py-0.5 bg-purple-500/30 text-purple-300 rounded text-xs">
                                Pin: {pred.predicted_pin}
                              </span>
                              <span className="text-gray-400 text-sm">
                                Prob: {(pred.pin_probability * 100).toFixed(0)}%
                              </span>
                            </div>
                            {pred.actual_pin_strike && (
                              <div className="flex items-center gap-3 text-sm">
                                <span className="text-gray-400">Actual: {pred.actual_pin_strike}</span>
                                <span className={`${pred.direction_correct ? 'text-green-400' : 'text-red-400'}`}>
                                  {pred.direction_correct ? 'Direction Correct' : 'Direction Wrong'}
                                </span>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : activeTab === 'backtest' ? (
              renderDataTable(backtestData, 'Backtest Trades (Full Entry Context)')
            ) : activeTab === 'walkforward' ? (
              renderDataTable(walkforwardData, 'Walk-Forward Validation Results')
            ) : activeTab === 'spreadwidth' ? (
              renderDataTable(spreadwidthData, 'Spread Width Performance')
            ) : activeTab === 'patterns' ? (
              renderDataTable(patternsData, 'Pattern Learning (Success Rates)')
            ) : activeTab === 'volsnapshots' ? (
              renderDataTable(volsnapshotsData, 'Volatility Surface Snapshots (Historical)')
            ) : null}
          </div>

          {/* Footer */}
          <div className="mt-6 p-4 bg-gray-800/50 rounded-lg border border-gray-700">
            <h4 className="font-medium text-white mb-2">What This Page Shows:</h4>
            <p className="text-sm text-gray-400">
              This page exposes ALL data that AlphaGEX collects but does not display in the main UI.
              Of the ~1,100 data fields collected across 108 tables, only ~100 fields (~9%) are shown
              in the standard UI. This transparency page gives you complete visibility into the hidden 91%.
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}
