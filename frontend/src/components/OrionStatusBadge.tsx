'use client'

/**
 * ORION ML Status Badge
 *
 * A compact status indicator showing whether ORION ML models are trained
 * and providing quick access to the ORION dashboard.
 *
 * Used on: ARGUS, HYPERION pages
 */

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Brain, CheckCircle, AlertTriangle, XCircle, Loader2 } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface OrionStatus {
  is_trained: boolean
  staleness_hours: number | null
  needs_retraining: boolean
  sub_models: {
    direction: boolean
    flip_gravity: boolean
    magnet_attraction: boolean
    volatility: boolean
    pin_zone: boolean
  }
}

export default function OrionStatusBadge() {
  const [status, setStatus] = useState<OrionStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await apiClient.getGexModelsStatus()
        if (res?.data?.data) {
          setStatus(res.data.data)
        }
        setError(false)
      } catch {
        setError(true)
      } finally {
        setLoading(false)
      }
    }

    fetchStatus()
    // Refresh every 5 minutes
    const interval = setInterval(fetchStatus, 5 * 60 * 1000)
    return () => clearInterval(interval)
  }, [])

  const getStatusColor = () => {
    if (loading) return 'bg-gray-700/50 border-gray-600'
    if (error) return 'bg-red-500/10 border-red-500/30'
    if (!status?.is_trained) return 'bg-yellow-500/10 border-yellow-500/30'
    if (status.needs_retraining) return 'bg-yellow-500/10 border-yellow-500/30'
    return 'bg-emerald-500/10 border-emerald-500/30'
  }

  const getStatusIcon = () => {
    if (loading) return <Loader2 className="w-3 h-3 animate-spin text-gray-400" />
    if (error) return <XCircle className="w-3 h-3 text-red-400" />
    if (!status?.is_trained) return <AlertTriangle className="w-3 h-3 text-yellow-400" />
    if (status.needs_retraining) return <AlertTriangle className="w-3 h-3 text-yellow-400" />
    return <CheckCircle className="w-3 h-3 text-emerald-400" />
  }

  const getStatusText = () => {
    if (loading) return 'Loading...'
    if (error) return 'Error'
    if (!status?.is_trained) return 'Not Trained'
    if (status.needs_retraining) return 'Stale'
    return 'Active'
  }

  const getTooltip = () => {
    if (loading) return 'Checking ORION ML status...'
    if (error) return 'Failed to load ORION status'
    if (!status?.is_trained) return 'ORION ML models not trained. Click to train.'
    if (status.needs_retraining) {
      const hours = status.staleness_hours ?? 0
      return `Models are ${hours.toFixed(0)}h old. Consider retraining.`
    }
    const trainedCount = Object.values(status.sub_models).filter(Boolean).length
    return `${trainedCount}/5 sub-models trained`
  }

  return (
    <Link
      href="/gex-ml"
      title={getTooltip()}
      className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs transition-all hover:opacity-80 ${getStatusColor()}`}
    >
      <Brain className="w-3.5 h-3.5 text-purple-400" />
      <span className="font-medium text-gray-300">ORION</span>
      {getStatusIcon()}
      <span className={`hidden sm:inline ${
        loading ? 'text-gray-400' :
        error ? 'text-red-400' :
        !status?.is_trained ? 'text-yellow-400' :
        status.needs_retraining ? 'text-yellow-400' :
        'text-emerald-400'
      }`}>
        {getStatusText()}
      </span>
    </Link>
  )
}
