'use client'

import { useState } from 'react'
import { Activity, Shield, AlertTriangle, BarChart3, Clock, Zap, Target, RefreshCw, ChevronLeft, ChevronRight, AlertCircle } from 'lucide-react'
import Navigation from '@/components/Navigation'
import { useVIX, useVIXHedgeSignal, useVIXSignalHistory } from '@/lib/hooks/useMarketData'

interface VIXData {
  vix_spot: number
  vix_source: string
  vix_m1: number
  vix_m2: number
  is_estimated: boolean
  term_structure_pct: number
  term_structure_m2_pct: number
  structure_type: string
  vvix: number | null
  vvix_source: string
  iv_percentile: number
  realized_vol_20d: number
  iv_rv_spread: number
  vol_regime: string
  vix_stress_level: string
  position_size_multiplier: number
  data_date?: string  // When the market data was collected
  timestamp: string
  fallback_mode?: boolean  // Indicates if using fallback data sources
}

interface HedgeSignal {
  signal_type: string
  confidence: number
  reasoning: string
  recommended_action: string
  risk_warning?: string
  fallback_mode?: boolean
}

interface SignalHistory {
  timestamp: string
  signal_type: string
  vix_level: number
  confidence?: number
  action_taken?: string
}

// Pagination constants
const ITEMS_PER_PAGE = 10

export default function VIXDashboard() {
  // Pagination state
  const [currentPage, setCurrentPage] = useState(0)

  // SWR hooks for data fetching with caching
  const { data: vixResponse, error: vixError, isLoading: vixLoading, isValidating: vixValidating, mutate: mutateVix } = useVIX()
  const { data: signalResponse, error: signalError, isValidating: signalValidating, mutate: mutateSignal } = useVIXHedgeSignal()
  const { data: historyResponse, isValidating: historyValidating, mutate: mutateHistory } = useVIXSignalHistory()

  // Extract data from responses
  const vixData = vixResponse?.data as VIXData | undefined
  const hedgeSignal = signalResponse?.data as HedgeSignal | undefined
  const signalHistory = (historyResponse?.data || []) as SignalHistory[]

  // Pagination calculations
  const totalPages = Math.ceil(signalHistory.length / ITEMS_PER_PAGE)
  const paginatedHistory = signalHistory.slice(
    currentPage * ITEMS_PER_PAGE,
    (currentPage + 1) * ITEMS_PER_PAGE
  )

  // Check if using fallback mode
  const isUsingFallback = vixData?.fallback_mode || hedgeSignal?.fallback_mode

  const loading = vixLoading && !vixData
  const error = vixError?.message || signalError?.message || null
  const isRefreshing = vixValidating || signalValidating || historyValidating

  // Manual refresh function
  const handleRefresh = () => {
    mutateVix()
    mutateSignal()
    mutateHistory()
  }

  const getVolRegimeColor = (regime: string) => {
    switch (regime) {
      case 'very_low':
      case 'low':
        return 'text-success bg-success/20'
      case 'normal':
        return 'text-primary bg-primary/20'
      case 'elevated':
        return 'text-warning bg-warning/20'
      case 'high':
      case 'extreme':
        return 'text-danger bg-danger/20'
      default:
        return 'text-text-muted bg-background-hover'
    }
  }

  const getSignalColor = (signalType: string) => {
    if (signalType.includes('buy') || signalType.includes('protection')) {
      return 'text-success bg-success/20 border-success/30'
    } else if (signalType.includes('reduce') || signalType.includes('sell')) {
      return 'text-warning bg-warning/20 border-warning/30'
    } else if (signalType === 'no_action') {
      return 'text-text-muted bg-background-hover border-border'
    }
    return 'text-primary bg-primary/20 border-primary/30'
  }

  const formatSignalDate = (timestamp: string | null | undefined) => {
    if (!timestamp) return 'N/A'
    try {
      const date = new Date(timestamp)
      if (isNaN(date.getTime())) return 'N/A'
      return date.toLocaleString()
    } catch {
      return 'N/A'
    }
  }

  return (
    <div className="min-h-screen">
      <Navigation />
      <main className="pt-24 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-3">
                  <Activity className="w-8 h-8 text-primary" />
                  <h1 className="text-3xl font-bold text-text-primary">VIX Dashboard</h1>
                </div>
                <p className="text-text-secondary mt-1">Volatility analysis and hedge signal management</p>
              </div>
              <div className="flex items-center gap-4">
                <div className="text-xs text-text-muted">
                  <span className="text-success">Auto-refresh 1min • Cached across pages</span>
                </div>
                <button
                  onClick={handleRefresh}
                  disabled={isRefreshing}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg font-semibold bg-primary text-white hover:bg-primary/90 disabled:opacity-50"
                >
                  <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
                  Refresh
                </button>
              </div>
            </div>

            {/* Data Date Display */}
            {vixData?.data_date && (
              <div className="flex items-center gap-2 text-sm text-primary bg-primary/10 px-3 py-1.5 rounded-lg w-fit">
                <Clock className="w-4 h-4" />
                <span>Market Data as of: <span className="font-semibold">{vixData.data_date}</span></span>
              </div>
            )}

            {/* Fallback Mode Indicator */}
            {isUsingFallback && (
              <div className="flex items-center gap-2 text-sm text-warning bg-warning/10 border border-warning/20 px-3 py-2 rounded-lg">
                <AlertCircle className="w-4 h-4" />
                <div>
                  <span className="font-semibold">Fallback Mode Active</span>
                  <span className="text-text-secondary ml-2">
                    Primary data source unavailable. Using backup sources (data may be delayed).
                  </span>
                </div>
              </div>
            )}

            {loading && !vixData ? (
              <div className="text-center py-12">
                <Activity className="w-8 h-8 text-primary mx-auto animate-spin" />
                <p className="text-text-secondary mt-2">Loading VIX data...</p>
              </div>
            ) : error ? (
              <div className="card bg-danger/10 border-danger/20">
                <div className="flex items-center gap-3">
                  <AlertTriangle className="w-6 h-6 text-danger" />
                  <div>
                    <p className="text-danger font-semibold">Error Loading Data</p>
                    <p className="text-text-secondary text-sm">{error}</p>
                  </div>
                </div>
              </div>
            ) : (
              <>
                {/* VIX Overview Cards */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  <div className="card">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-text-secondary text-sm">VIX Spot</p>
                        <p className="text-3xl font-bold text-text-primary mt-1">
                          {vixData?.vix_spot?.toFixed(2) || '--'}
                        </p>
                        <p className="text-xs text-text-muted mt-1">
                          Source: {vixData?.vix_source || 'unknown'}
                        </p>
                      </div>
                      <div className={`px-3 py-1 rounded-lg font-semibold text-sm ${getVolRegimeColor(vixData?.vol_regime || '')}`}>
                        {vixData?.vol_regime?.toUpperCase().replace('_', ' ') || 'UNKNOWN'}
                      </div>
                    </div>
                  </div>

                  <div className="card">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-text-secondary text-sm">VVIX (Vol of VIX)</p>
                        <p className={`text-3xl font-bold mt-1 ${
                          (vixData?.vvix || 0) > 120 ? 'text-danger' :
                          (vixData?.vvix || 0) > 90 ? 'text-warning' :
                          'text-success'
                        }`}>
                          {vixData?.vvix?.toFixed(1) || '--'}
                        </p>
                      </div>
                      <Activity className="text-primary w-8 h-8" />
                    </div>
                    <p className="text-xs text-text-muted mt-2">
                      {vixData?.vvix ? (
                        (vixData.vvix > 120) ? 'High VIX volatility - timing uncertain' :
                        (vixData.vvix > 90) ? 'Elevated VIX volatility' :
                        'Normal VVIX - good timing window'
                      ) : 'VVIX data unavailable'}
                    </p>
                  </div>

                  <div className="card">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-text-secondary text-sm">IV Percentile</p>
                        <p className={`text-3xl font-bold mt-1 ${
                          (vixData?.iv_percentile || 0) > 80 ? 'text-danger' :
                          (vixData?.iv_percentile || 0) > 50 ? 'text-warning' :
                          'text-success'
                        }`}>
                          {vixData?.iv_percentile?.toFixed(0) || '--'}%
                        </p>
                      </div>
                      <BarChart3 className="text-primary w-8 h-8" />
                    </div>
                    <p className="text-xs text-text-muted mt-2">
                      {(vixData?.iv_percentile || 0) > 80 ? 'Historically high volatility' :
                       (vixData?.iv_percentile || 0) > 50 ? 'Above average volatility' :
                       'Below average - protection is cheap'}
                    </p>
                  </div>

                  <div className="card">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-text-secondary text-sm">IV-RV Spread</p>
                        <p className={`text-3xl font-bold mt-1 ${
                          (vixData?.iv_rv_spread || 0) > 5 ? 'text-warning' :
                          (vixData?.iv_rv_spread || 0) < 0 ? 'text-success' :
                          'text-text-primary'
                        }`}>
                          {vixData?.iv_rv_spread?.toFixed(1) || '--'} pts
                        </p>
                      </div>
                      <Target className="text-primary w-8 h-8" />
                    </div>
                    <p className="text-xs text-text-muted mt-2">
                      {(vixData?.iv_rv_spread || 0) > 5 ? 'Implied vol premium high' :
                       (vixData?.iv_rv_spread || 0) < 0 ? 'Implied vol discount' :
                       'Normal spread'}
                    </p>
                  </div>
                </div>

                {/* Trading Stress Indicator */}
                <div className={`card border-2 ${
                  vixData?.vix_stress_level === 'extreme' ? 'border-danger bg-danger/10' :
                  vixData?.vix_stress_level === 'high' ? 'border-warning bg-warning/10' :
                  vixData?.vix_stress_level === 'elevated' ? 'border-warning/50 bg-warning/5' :
                  'border-success/50 bg-success/5'
                }`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <AlertTriangle className={`w-6 h-6 ${
                        vixData?.vix_stress_level === 'extreme' ? 'text-danger' :
                        vixData?.vix_stress_level === 'high' ? 'text-warning' :
                        vixData?.vix_stress_level === 'elevated' ? 'text-warning' :
                        'text-success'
                      }`} />
                      <div>
                        <p className="font-semibold text-text-primary">
                          VIX Stress Level: {vixData?.vix_stress_level?.toUpperCase() || 'UNKNOWN'}
                        </p>
                        <p className="text-sm text-text-secondary">
                          Position Size Multiplier: {((vixData?.position_size_multiplier || 1) * 100).toFixed(0)}%
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-2xl font-bold text-text-primary">
                        {vixData?.realized_vol_20d?.toFixed(1) || '--'}%
                      </p>
                      <p className="text-xs text-text-muted">20d Realized Vol</p>
                    </div>
                  </div>
                  <div className="mt-3 text-sm">
                    {vixData?.vix_stress_level === 'extreme' && (
                      <p className="text-danger">⚠️ EXTREME STRESS: Reduce position sizes by 75%. Avoid new trades.</p>
                    )}
                    {vixData?.vix_stress_level === 'high' && (
                      <p className="text-warning">⚠️ HIGH STRESS: Reduce position sizes by 50%. Use caution.</p>
                    )}
                    {vixData?.vix_stress_level === 'elevated' && (
                      <p className="text-warning">⚠️ ELEVATED: Reduce position sizes by 25%. Monitor closely.</p>
                    )}
                    {vixData?.vix_stress_level === 'normal' && (
                      <p className="text-success">✅ Normal conditions. Standard position sizing applies.</p>
                    )}
                  </div>
                </div>

                {/* Term Structure */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <div className="card">
                    <div className="flex items-center justify-between mb-4">
                      <h2 className="text-xl font-semibold text-text-primary">VIX Term Structure</h2>
                      {vixData?.is_estimated && (
                        <span className="px-2 py-1 rounded text-xs bg-warning/20 text-warning font-semibold">
                          ESTIMATED
                        </span>
                      )}
                    </div>
                    <div className="space-y-4">
                      <div className="flex items-center justify-between p-4 bg-background-hover rounded-lg">
                        <div>
                          <p className="text-text-muted text-sm">VIX Spot</p>
                          <p className="text-2xl font-bold text-text-primary">{vixData?.vix_spot?.toFixed(2) || '--'}</p>
                        </div>
                        <div className="text-4xl">📊</div>
                      </div>

                      <div className="flex items-center justify-between p-4 bg-background-hover rounded-lg">
                        <div>
                          <p className="text-text-muted text-sm">VIX Front Month (M1)</p>
                          <p className="text-2xl font-bold text-text-primary">{vixData?.vix_m1?.toFixed(2) || '--'}</p>
                        </div>
                        <div className={`px-3 py-1 rounded-lg font-semibold ${
                          (vixData?.term_structure_pct || 0) > 0 ? 'bg-success/20 text-success' : 'bg-danger/20 text-danger'
                        }`}>
                          {(vixData?.term_structure_pct || 0) > 0 ? '+' : ''}{vixData?.term_structure_pct?.toFixed(1) || '0'}%
                        </div>
                      </div>

                      <div className="flex items-center justify-between p-4 bg-background-hover rounded-lg">
                        <div>
                          <p className="text-text-muted text-sm">VIX Second Month (M2)</p>
                          <p className="text-2xl font-bold text-text-primary">{vixData?.vix_m2?.toFixed(2) || '--'}</p>
                        </div>
                        <div className={`px-3 py-1 rounded-lg font-semibold ${
                          (vixData?.term_structure_m2_pct || 0) > 0 ? 'bg-success/20 text-success' : 'bg-danger/20 text-danger'
                        }`}>
                          {(vixData?.term_structure_m2_pct || 0) > 0 ? '+' : ''}{vixData?.term_structure_m2_pct?.toFixed(1) || '0'}%
                        </div>
                      </div>

                      <div className={`p-4 rounded-lg border ${
                        vixData?.structure_type === 'contango' ? 'bg-success/10 border-success/20' :
                        vixData?.structure_type === 'backwardation' ? 'bg-danger/10 border-danger/20' :
                        'bg-background-hover border-border'
                      }`}>
                        <div className="flex items-center gap-2">
                          <Zap className="w-5 h-5" />
                          <span className="font-semibold">
                            {vixData?.structure_type?.toUpperCase() || 'UNKNOWN'}
                          </span>
                        </div>
                        <p className="text-sm text-text-secondary mt-1">
                          {vixData?.structure_type === 'contango'
                            ? 'Normal market conditions - futures above spot'
                            : vixData?.structure_type === 'backwardation'
                            ? 'Stress signal - spot above futures (fear)'
                            : vixData?.structure_type === 'flat'
                            ? 'Flat structure - transition period'
                            : 'Analyzing term structure...'}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Hedge Signal */}
                  <div className="card">
                    <div className="flex items-center gap-3 mb-4">
                      <Shield className="w-6 h-6 text-primary" />
                      <h2 className="text-xl font-semibold text-text-primary">Current Hedge Signal</h2>
                    </div>

                    {hedgeSignal ? (
                      <div className="space-y-4">
                        <div className={`p-4 rounded-lg border ${getSignalColor(hedgeSignal.signal_type)}`}>
                          <div className="flex items-center justify-between mb-2">
                            <span className="font-bold text-lg">
                              {hedgeSignal.signal_type.replace(/_/g, ' ').toUpperCase()}
                            </span>
                            <span className="text-sm">
                              Confidence: {hedgeSignal.confidence?.toFixed(0)}%
                            </span>
                          </div>
                          <p className="text-sm">{hedgeSignal.reasoning}</p>
                        </div>

                        <div className="p-4 bg-background-hover rounded-lg">
                          <p className="text-text-muted text-xs font-medium mb-2">RECOMMENDED ACTION</p>
                          <p className="text-text-primary">{hedgeSignal.recommended_action}</p>
                        </div>

                        {hedgeSignal.risk_warning && hedgeSignal.risk_warning !== 'None' && (
                          <div className="p-4 bg-danger/10 border border-danger/20 rounded-lg">
                            <div className="flex items-center gap-2">
                              <AlertTriangle className="w-5 h-5 text-danger" />
                              <span className="text-danger font-semibold">Risk Warning</span>
                            </div>
                            <p className="text-sm text-text-secondary mt-1">{hedgeSignal.risk_warning}</p>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="text-center py-8 text-text-secondary">
                        <Shield className="w-10 h-10 text-text-muted mx-auto mb-2" />
                        <p>No hedge signal available</p>
                      </div>
                    )}
                  </div>
                </div>

                {/* Signal History */}
                <div className="card">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <Clock className="w-6 h-6 text-primary" />
                      <h2 className="text-xl font-semibold text-text-primary">Signal History</h2>
                    </div>
                    <span className="text-xs text-text-muted">{signalHistory.length} signals</span>
                  </div>

                  {signalHistory.length > 0 ? (
                    <>
                      <div className="overflow-x-auto">
                        <table className="w-full">
                          <thead>
                            <tr className="border-b border-border">
                              <th className="text-left py-3 px-4 text-text-secondary font-medium">Time</th>
                              <th className="text-left py-3 px-4 text-text-secondary font-medium">Signal</th>
                              <th className="text-center py-3 px-4 text-text-secondary font-medium">VIX Level</th>
                              <th className="text-center py-3 px-4 text-text-secondary font-medium">Confidence</th>
                              <th className="text-left py-3 px-4 text-text-secondary font-medium">Action Taken</th>
                            </tr>
                          </thead>
                          <tbody>
                            {paginatedHistory.map((signal, idx) => (
                              <tr key={idx} className="border-b border-border/50 hover:bg-background-hover">
                                <td className="py-3 px-4 text-text-secondary text-sm">
                                  {formatSignalDate(signal.timestamp)}
                                </td>
                                <td className="py-3 px-4">
                                  <span className={`px-2 py-1 rounded text-xs font-semibold ${getSignalColor(signal.signal_type || 'no_action')}`}>
                                    {(signal.signal_type || 'no_action').replace(/_/g, ' ').toUpperCase()}
                                  </span>
                                </td>
                                <td className="py-3 px-4 text-center font-semibold">
                                  {signal.vix_level?.toFixed(2) || '--'}
                                </td>
                                <td className="py-3 px-4 text-center text-sm">
                                  {signal.confidence != null ? `${signal.confidence.toFixed(0)}%` : '--'}
                                </td>
                                <td className="py-3 px-4 text-text-primary text-sm">
                                  {signal.action_taken || 'Monitored'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      {/* Pagination Controls */}
                      {totalPages > 1 && (
                        <div className="flex items-center justify-between mt-4 pt-4 border-t border-border">
                          <div className="text-sm text-text-muted">
                            Showing {currentPage * ITEMS_PER_PAGE + 1} - {Math.min((currentPage + 1) * ITEMS_PER_PAGE, signalHistory.length)} of {signalHistory.length}
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => setCurrentPage(p => Math.max(0, p - 1))}
                              disabled={currentPage === 0}
                              className="p-2 rounded-lg hover:bg-background-hover disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              <ChevronLeft className="w-5 h-5" />
                            </button>
                            <span className="text-sm text-text-secondary px-2">
                              Page {currentPage + 1} of {totalPages}
                            </span>
                            <button
                              onClick={() => setCurrentPage(p => Math.min(totalPages - 1, p + 1))}
                              disabled={currentPage >= totalPages - 1}
                              className="p-2 rounded-lg hover:bg-background-hover disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              <ChevronRight className="w-5 h-5" />
                            </button>
                          </div>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-center py-8 text-text-secondary">
                      <Clock className="w-10 h-10 text-text-muted mx-auto mb-2" />
                      <p>No signal history yet</p>
                      <p className="text-xs text-text-muted mt-1">Signals will appear as they are generated</p>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
