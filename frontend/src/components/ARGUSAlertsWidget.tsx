'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  Eye,
  AlertTriangle,
  AlertCircle,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Zap,
  Activity,
  Clock
} from 'lucide-react'
import { api } from '@/lib/api'

interface GammaAlert {
  type: 'BUILDING' | 'COLLAPSING' | 'SPIKE' | 'FLIP' | 'DANGER_ZONE'
  strike: number
  message: string
  severity: 'HIGH' | 'MEDIUM' | 'LOW'
  timestamp: string
}

interface ARGUSData {
  alerts: GammaAlert[]
  danger_zones: {
    strike: number
    gamma: number
    roc: number
  }[]
  pin_status?: string
  gamma_flip_direction?: string
  last_updated?: string
}

export default function ARGUSAlertsWidget() {
  const [expanded, setExpanded] = useState(true)
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<ARGUSData | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fetchData = async () => {
    setLoading(true)
    setError(null)
    try {
      // Fetch multiple ARGUS endpoints in parallel
      const [alertsRes, dangerRes, gammaRes] = await Promise.all([
        api.get('/api/argus/alerts').catch(() => ({ data: { data: { alerts: [] } } })),
        api.get('/api/argus/danger-zones/log?limit=5').catch(() => ({ data: { data: { zones: [] } } })),
        api.get('/api/argus/gamma?symbol=SPY').catch(() => ({ data: { data: null } }))
      ])

      const alerts = alertsRes.data?.data?.alerts || alertsRes.data?.alerts || []
      const dangerZones = dangerRes.data?.data?.zones || dangerRes.data?.zones || []
      const gammaData = gammaRes.data?.data || {}

      setData({
        alerts: alerts.slice(0, 5),
        danger_zones: dangerZones,
        pin_status: gammaData.pin_status,
        gamma_flip_direction: gammaData.gamma_flip_direction,
        last_updated: new Date().toISOString()
      })
    } catch (err) {
      setError('Failed to load ARGUS data')
      console.error('ARGUS fetch error:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000) // Refresh every 30 seconds
    return () => clearInterval(interval)
  }, [])

  const getAlertIcon = (type: string) => {
    switch (type) {
      case 'DANGER_ZONE':
        return <AlertTriangle className="w-4 h-4 text-danger" />
      case 'FLIP':
        return <Activity className="w-4 h-4 text-warning" />
      case 'SPIKE':
        return <Zap className="w-4 h-4 text-primary" />
      case 'BUILDING':
        return <TrendingUp className="w-4 h-4 text-success" />
      case 'COLLAPSING':
        return <TrendingDown className="w-4 h-4 text-danger" />
      default:
        return <AlertCircle className="w-4 h-4 text-text-muted" />
    }
  }

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'HIGH':
        return 'bg-danger/10 border-danger/30 text-danger'
      case 'MEDIUM':
        return 'bg-warning/10 border-warning/30 text-warning'
      default:
        return 'bg-primary/10 border-primary/30 text-primary'
    }
  }

  const hasAlerts = data?.alerts && data.alerts.length > 0
  const hasDangerZones = data?.danger_zones && data.danger_zones.length > 0

  return (
    <div className="card bg-gradient-to-r from-danger/5 to-transparent border border-danger/20">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-danger/10">
            <Eye className="w-5 h-5 text-danger" />
          </div>
          <div className="text-left">
            <h3 className="text-sm font-semibold text-text-primary">ARGUS 0DTE Alerts</h3>
            <div className="flex items-center gap-2 text-xs text-text-muted">
              {loading ? (
                <span>Loading...</span>
              ) : hasAlerts ? (
                <>
                  <span className="text-danger">{data?.alerts.length} active alerts</span>
                  {data?.pin_status && (
                    <>
                      <span className="opacity-50">|</span>
                      <span>{data.pin_status}</span>
                    </>
                  )}
                </>
              ) : (
                <span className="text-success">No active alerts</span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation()
              fetchData()
            }}
            className={`p-1.5 rounded-lg hover:bg-danger/10 transition-colors ${loading ? 'animate-spin' : ''}`}
          >
            <RefreshCw className="w-4 h-4 text-danger" />
          </button>
          {expanded ? (
            <ChevronUp className="w-5 h-5 text-danger" />
          ) : (
            <ChevronDown className="w-5 h-5 text-danger" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-border/50 animate-fade-in">
          {loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-12 bg-background-hover animate-pulse rounded-lg" />
              ))}
            </div>
          ) : error ? (
            <div className="p-4 bg-warning/10 border border-warning/20 rounded-lg">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-warning" />
                <span className="text-sm text-warning">{error}</span>
              </div>
              <button
                onClick={fetchData}
                className="mt-2 text-xs text-primary hover:underline"
              >
                Retry
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Gamma Status */}
              <div className="grid grid-cols-2 gap-3">
                <div className={`p-3 rounded-lg ${
                  data?.pin_status?.includes('PINNING') ? 'bg-warning/10 border border-warning/20' :
                  data?.pin_status?.includes('BREAKING') ? 'bg-danger/10 border border-danger/20' :
                  'bg-background-hover'
                }`}>
                  <div className="text-xs text-text-muted mb-1">Pin Status</div>
                  <div className={`text-sm font-semibold ${
                    data?.pin_status?.includes('PINNING') ? 'text-warning' :
                    data?.pin_status?.includes('BREAKING') ? 'text-danger' :
                    'text-text-primary'
                  }`}>
                    {data?.pin_status || 'Neutral'}
                  </div>
                </div>
                <div className={`p-3 rounded-lg ${
                  data?.gamma_flip_direction === 'POSITIVE' ? 'bg-success/10 border border-success/20' :
                  data?.gamma_flip_direction === 'NEGATIVE' ? 'bg-danger/10 border border-danger/20' :
                  'bg-background-hover'
                }`}>
                  <div className="text-xs text-text-muted mb-1">Gamma Flip</div>
                  <div className={`text-sm font-semibold ${
                    data?.gamma_flip_direction === 'POSITIVE' ? 'text-success' :
                    data?.gamma_flip_direction === 'NEGATIVE' ? 'text-danger' :
                    'text-text-primary'
                  }`}>
                    {data?.gamma_flip_direction?.replace(/_/g, ' ') || 'No flip'}
                  </div>
                </div>
              </div>

              {/* Active Alerts */}
              {hasAlerts ? (
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-text-muted uppercase tracking-wide">Active Alerts</div>
                  {data?.alerts.map((alert, idx) => (
                    <div
                      key={idx}
                      className={`p-3 rounded-lg border ${getSeverityColor(alert.severity)}`}
                    >
                      <div className="flex items-start gap-2">
                        {getAlertIcon(alert.type)}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-sm font-medium">{alert.type.replace(/_/g, ' ')}</span>
                            {alert.strike && (
                              <span className="text-xs font-mono">${alert.strike}</span>
                            )}
                          </div>
                          <p className="text-xs text-text-secondary mt-1 break-words">{alert.message}</p>
                          {alert.timestamp && (
                            <div className="flex items-center gap-1 mt-1 text-xs text-text-muted">
                              <Clock className="w-3 h-3" />
                              {new Date(alert.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-4 bg-success/10 border border-success/20 rounded-lg text-center">
                  <div className="text-success text-sm font-medium mb-1">All Clear</div>
                  <p className="text-xs text-text-muted">No gamma alerts or danger zones detected. Normal trading conditions.</p>
                </div>
              )}

              {/* Danger Zones */}
              {hasDangerZones && (
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-text-muted uppercase tracking-wide">Danger Zones</div>
                  <div className="flex flex-wrap gap-2">
                    {data?.danger_zones.map((zone, idx) => (
                      <div
                        key={idx}
                        className="px-3 py-1.5 bg-danger/10 border border-danger/20 rounded-lg"
                      >
                        <span className="text-sm font-mono text-danger">${zone.strike}</span>
                        {zone.roc && (
                          <span className="text-xs text-text-muted ml-2">ROC: {zone.roc.toFixed(1)}%</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Link to ARGUS page */}
              <Link
                href="/argus"
                className="flex items-center justify-center gap-2 px-4 py-2 bg-danger/10 text-danger rounded-lg hover:bg-danger/20 transition-colors text-sm font-medium"
              >
                <Eye className="w-4 h-4" />
                View Full ARGUS Dashboard
              </Link>

              {/* Last updated */}
              {data?.last_updated && (
                <div className="text-center text-xs text-text-muted">
                  Updated: {new Date(data.last_updated).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
