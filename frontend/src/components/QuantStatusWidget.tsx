'use client'

import { useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import { api } from '@/lib/api'
import {
  BarChart3,
  CheckCircle,
  XCircle,
  AlertTriangle,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Activity,
  Bell
} from 'lucide-react'

const fetcher = (url: string) => api.get(url).then(res => res.data)

interface QuantModule {
  name: string
  available: boolean
  is_trained?: boolean
  model_version?: string
  description?: string
}

interface QuantStatus {
  models: QuantModule[]
  total_predictions_24h: number
  timestamp: string
}

interface QuantAlert {
  id: number
  timestamp: string
  alert_type: string
  severity: string
  title: string
  acknowledged: boolean
}

export default function QuantStatusWidget() {
  const [expanded, setExpanded] = useState(true)

  const { data: status, isLoading, mutate } = useSWR<QuantStatus>(
    '/api/quant/status',
    fetcher,
    { refreshInterval: 30000 }
  )

  const { data: alertsData } = useSWR<{ alerts: QuantAlert[], total: number }>(
    '/api/quant/alerts?limit=5&unacknowledged_only=true',
    fetcher,
    { refreshInterval: 15000 }
  )

  const alerts = alertsData?.alerts || []
  const unackAlerts = alerts.filter(a => !a.acknowledged).length

  // Calculate stats
  const availableModels = status?.models?.filter(m => m.available) || []
  const trainedModels = status?.models?.filter(m => m.is_trained) || []
  const totalModels = status?.models?.length || 0
  const predictions24h = status?.total_predictions_24h || 0

  // Overall health
  const isHealthy = trainedModels.length >= 2
  const needsAttention = unackAlerts > 0

  if (isLoading) {
    return (
      <div className="card bg-gradient-to-r from-cyan-500/5 to-transparent border border-cyan-500/20 animate-pulse">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-background-hover rounded-lg" />
          <div className="flex-1">
            <div className="h-4 w-32 bg-background-hover rounded mb-2" />
            <div className="h-3 w-24 bg-background-hover rounded" />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="card bg-gradient-to-r from-cyan-500/5 to-transparent border border-cyan-500/20">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-cyan-500/10">
            <BarChart3 className="w-5 h-5 text-cyan-500" />
          </div>
          <div className="text-left">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              QUANT ML Models
              {needsAttention && (
                <span className="flex items-center justify-center w-4 h-4 bg-danger text-white text-[10px] rounded-full">
                  {unackAlerts}
                </span>
              )}
            </h3>
            <div className="flex items-center gap-3 text-xs text-text-muted">
              <span className="flex items-center gap-1">
                <Activity className="w-3 h-3 text-cyan-400" />
                {trainedModels.length}/{totalModels} models
              </span>
              <span className="text-cyan-400">
                {predictions24h} predictions/24h
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation()
              mutate()
            }}
            className="p-1.5 rounded-lg hover:bg-cyan-500/10 transition-colors"
          >
            <RefreshCw className="w-4 h-4 text-cyan-500" />
          </button>
          {expanded ? (
            <ChevronUp className="w-5 h-5 text-cyan-500" />
          ) : (
            <ChevronDown className="w-5 h-5 text-cyan-500" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-border/50 animate-fade-in">
          {/* Model Status Grid */}
          <div className="grid grid-cols-2 gap-2 mb-4">
            {status?.models?.slice(0, 4).map((model) => (
              <div
                key={model.name}
                className={`p-2 rounded-lg border ${
                  model.is_trained
                    ? 'bg-success/10 border-success/30'
                    : model.available
                    ? 'bg-warning/10 border-warning/30'
                    : 'bg-background-hover border-border/50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-text-primary truncate">
                    {model.name}
                  </span>
                  {model.is_trained ? (
                    <CheckCircle className="w-3 h-3 text-success" />
                  ) : model.available ? (
                    <AlertTriangle className="w-3 h-3 text-warning" />
                  ) : (
                    <XCircle className="w-3 h-3 text-text-muted" />
                  )}
                </div>
                {model.model_version && (
                  <div className="text-[10px] text-text-muted mt-1">
                    v{model.model_version}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Stats Row */}
          <div className="grid grid-cols-3 gap-2 mb-4">
            <div className="p-2 bg-background-hover rounded text-center">
              <div className="text-[10px] text-text-muted">Available</div>
              <div className="text-sm font-bold text-cyan-400">
                {availableModels.length}
              </div>
            </div>
            <div className="p-2 bg-background-hover rounded text-center">
              <div className="text-[10px] text-text-muted">Trained</div>
              <div className="text-sm font-bold text-success">
                {trainedModels.length}
              </div>
            </div>
            <div className="p-2 bg-background-hover rounded text-center">
              <div className="text-[10px] text-text-muted">Alerts</div>
              <div className={`text-sm font-bold ${unackAlerts > 0 ? 'text-warning' : 'text-text-muted'}`}>
                {unackAlerts}
              </div>
            </div>
          </div>

          {/* Recent Alerts */}
          {alerts.length > 0 && (
            <div className="mb-4 space-y-2">
              <div className="text-xs font-medium text-text-muted flex items-center gap-1">
                <Bell className="w-3 h-3" />
                Recent Alerts
              </div>
              {alerts.slice(0, 2).map((alert) => (
                <div
                  key={alert.id}
                  className={`p-2 rounded text-xs ${
                    alert.severity === 'CRITICAL'
                      ? 'bg-danger/10 border border-danger/30 text-danger'
                      : alert.severity === 'WARNING'
                      ? 'bg-warning/10 border border-warning/30 text-warning'
                      : 'bg-info/10 border border-info/30 text-info'
                  }`}
                >
                  {alert.title}
                </div>
              ))}
            </div>
          )}

          {/* Quick Link */}
          <Link
            href="/quant"
            className="flex items-center justify-center gap-2 w-full px-4 py-2 text-sm font-medium text-cyan-400 bg-cyan-500/10 rounded-lg hover:bg-cyan-500/20 transition-colors"
          >
            <BarChart3 className="w-4 h-4" />
            Open QUANT Dashboard
          </Link>
        </div>
      )}
    </div>
  )
}
