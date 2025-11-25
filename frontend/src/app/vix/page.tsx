'use client'

import { useState, useEffect } from 'react'
import { Activity, TrendingUp, TrendingDown, Shield, AlertTriangle, BarChart3, Clock, Zap, Target, RefreshCw } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, ReferenceLine } from 'recharts'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'

interface VIXData {
  vix_spot: number
  vix_m1: number
  vix_m2: number
  term_structure_pct: number
  structure_type: string
  iv_percentile: number
  realized_vol_20d: number
  iv_rv_spread: number
  vol_regime: string
  timestamp: string
}

interface HedgeSignal {
  signal_type: string
  confidence: number
  reasoning: string
  recommended_action: string
  risk_warning?: string
}

interface SignalHistory {
  timestamp: string
  signal_type: string
  vix_level: number
  action_taken?: string
}

export default function VIXDashboard() {
  const [loading, setLoading] = useState(true)
  const [vixData, setVixData] = useState<VIXData | null>(null)
  const [hedgeSignal, setHedgeSignal] = useState<HedgeSignal | null>(null)
  const [signalHistory, setSignalHistory] = useState<SignalHistory[]>([])
  const [error, setError] = useState<string | null>(null)

  const fetchData = async () => {
    try {
      setLoading(true)
      const [vixRes, signalRes, historyRes] = await Promise.all([
        apiClient.getVIXCurrent().catch(() => ({ data: { success: false } })),
        apiClient.getVIXHedgeSignal().catch(() => ({ data: { success: false } })),
        apiClient.getVIXSignalHistory().catch(() => ({ data: { success: false, data: [] } }))
      ])

      if (vixRes.data.success) {
        setVixData(vixRes.data.data)
      }
      if (signalRes.data.success) {
        setHedgeSignal(signalRes.data.data)
      }
      if (historyRes.data.success) {
        setSignalHistory(historyRes.data.data || [])
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load VIX data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

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

  return (
    <div className="min-h-screen">
      <Navigation />
      <main className="pt-16 transition-all duration-300">
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
              <button
                onClick={fetchData}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 rounded-lg font-semibold bg-primary text-white hover:bg-primary/90 disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>

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
                      </div>
                      <div className={`px-3 py-1 rounded-lg font-semibold text-sm ${getVolRegimeColor(vixData?.vol_regime || '')}`}>
                        {vixData?.vol_regime?.toUpperCase().replace('_', ' ') || 'UNKNOWN'}
                      </div>
                    </div>
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
                        <p className="text-text-secondary text-sm">Realized Vol (20d)</p>
                        <p className="text-3xl font-bold text-text-primary mt-1">
                          {vixData?.realized_vol_20d?.toFixed(1) || '--'}%
                        </p>
                      </div>
                      <TrendingUp className="text-primary w-8 h-8" />
                    </div>
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

                {/* Term Structure */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <div className="card">
                    <h2 className="text-xl font-semibold text-text-primary mb-4">VIX Term Structure</h2>
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
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead>
                          <tr className="border-b border-border">
                            <th className="text-left py-3 px-4 text-text-secondary font-medium">Time</th>
                            <th className="text-left py-3 px-4 text-text-secondary font-medium">Signal</th>
                            <th className="text-center py-3 px-4 text-text-secondary font-medium">VIX Level</th>
                            <th className="text-left py-3 px-4 text-text-secondary font-medium">Action Taken</th>
                          </tr>
                        </thead>
                        <tbody>
                          {signalHistory.slice(0, 10).map((signal, idx) => (
                            <tr key={idx} className="border-b border-border/50 hover:bg-background-hover">
                              <td className="py-3 px-4 text-text-secondary text-sm">
                                {new Date(signal.timestamp).toLocaleString()}
                              </td>
                              <td className="py-3 px-4">
                                <span className={`px-2 py-1 rounded text-xs font-semibold ${getSignalColor(signal.signal_type)}`}>
                                  {signal.signal_type.replace(/_/g, ' ').toUpperCase()}
                                </span>
                              </td>
                              <td className="py-3 px-4 text-center font-semibold">
                                {signal.vix_level?.toFixed(2) || '--'}
                              </td>
                              <td className="py-3 px-4 text-text-primary text-sm">
                                {signal.action_taken || 'Monitored'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
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
