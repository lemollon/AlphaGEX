'use client'

import React from 'react'
import { Shield, AlertTriangle, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { useVIXHedgeSignal } from '@/lib/hooks/useMarketData'

interface HedgeSignal {
  signal_type: string
  confidence: number
  vol_regime: string
  reasoning: string
  recommended_action: string
  risk_warning?: string
  metrics?: {
    vix_spot: number
    vix_source: string
  }
  fallback_mode?: boolean
  timestamp: string
}

function getSignalColor(signalType: string): string {
  if (signalType.includes('hedge') || signalType.includes('recommended')) {
    return 'bg-red-500/20 border-red-500/30 text-red-400'
  } else if (signalType.includes('monitor') || signalType.includes('closely')) {
    return 'bg-yellow-500/20 border-yellow-500/30 text-yellow-400'
  } else if (signalType === 'no_action') {
    return 'bg-green-500/20 border-green-500/30 text-green-400'
  }
  return 'bg-gray-500/20 border-gray-500/30 text-gray-400'
}

function getSignalIcon(signalType: string) {
  if (signalType.includes('hedge') || signalType.includes('recommended')) {
    return <TrendingDown className="w-4 h-4" />
  } else if (signalType.includes('monitor')) {
    return <Minus className="w-4 h-4" />
  }
  return <TrendingUp className="w-4 h-4" />
}

export function HedgeSignalCard({ compact = false }: { compact?: boolean }) {
  const { data, isLoading, error } = useVIXHedgeSignal()

  const hedgeSignal: HedgeSignal | null = data?.data || data || null

  if (isLoading) {
    return (
      <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
        <div className="flex items-center gap-2 mb-3">
          <Shield className="w-5 h-5 text-purple-400" />
          <span className="text-gray-400 font-medium">Current Hedge Signal</span>
        </div>
        <div className="animate-pulse">
          <div className="h-4 bg-gray-700 rounded w-3/4 mb-2"></div>
          <div className="h-3 bg-gray-700 rounded w-1/2"></div>
        </div>
      </div>
    )
  }

  if (error || !hedgeSignal) {
    return (
      <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
        <div className="flex items-center gap-2 mb-3">
          <Shield className="w-5 h-5 text-purple-400" />
          <span className="text-gray-400 font-medium">Current Hedge Signal</span>
        </div>
        <div className="text-center py-2">
          <p className="text-gray-500 text-sm">No hedge signal available</p>
        </div>
      </div>
    )
  }

  const signalDisplay = hedgeSignal.signal_type.replace(/_/g, ' ').toUpperCase()
  const colorClasses = getSignalColor(hedgeSignal.signal_type)

  if (compact) {
    return (
      <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-purple-400" />
            <span className="text-gray-400 text-sm font-medium">Hedge Signal</span>
          </div>
          <div className={`flex items-center gap-2 px-2 py-1 rounded border ${colorClasses}`}>
            {getSignalIcon(hedgeSignal.signal_type)}
            <span className="text-xs font-bold">{signalDisplay}</span>
          </div>
        </div>
        {hedgeSignal.metrics?.vix_spot && (
          <div className="mt-2 text-xs text-gray-500">
            VIX: {hedgeSignal.metrics.vix_spot.toFixed(2)} | {hedgeSignal.confidence?.toFixed(0)}% confidence
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
      <div className="flex items-center gap-2 mb-3">
        <Shield className="w-5 h-5 text-purple-400" />
        <span className="text-gray-400 font-medium">Current Hedge Signal</span>
        {hedgeSignal.metrics?.vix_spot && (
          <span className="ml-auto text-xs text-gray-500">VIX: {hedgeSignal.metrics.vix_spot.toFixed(2)}</span>
        )}
      </div>

      <div className={`p-3 rounded-lg border ${colorClasses}`}>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            {getSignalIcon(hedgeSignal.signal_type)}
            <span className="font-bold">{signalDisplay}</span>
          </div>
          <span className="text-xs">
            {hedgeSignal.confidence?.toFixed(0)}% confidence
          </span>
        </div>
        <p className="text-xs opacity-80">{hedgeSignal.reasoning}</p>
      </div>

      <div className="mt-3 p-3 bg-gray-900/50 rounded-lg">
        <p className="text-gray-500 text-xs font-medium mb-1">RECOMMENDED ACTION</p>
        <p className="text-gray-300 text-sm">{hedgeSignal.recommended_action}</p>
      </div>

      {hedgeSignal.risk_warning && hedgeSignal.risk_warning !== 'None' && (
        <div className="mt-3 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle className="w-4 h-4 text-red-400" />
            <span className="text-red-400 text-xs font-semibold">Risk Warning</span>
          </div>
          <p className="text-xs text-gray-400">{hedgeSignal.risk_warning}</p>
        </div>
      )}

      {hedgeSignal.fallback_mode && (
        <p className="mt-2 text-xs text-gray-600 text-center">Using basic VIX-level analysis</p>
      )}
    </div>
  )
}

export default HedgeSignalCard
