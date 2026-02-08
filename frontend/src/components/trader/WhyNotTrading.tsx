'use client'

import { useState } from 'react'
import { AlertCircle, Clock, TrendingDown, Brain, Target, ChevronDown, ChevronUp, XCircle } from 'lucide-react'

interface SkipReason {
  id: string
  timestamp: string
  reason: string
  category: 'market' | 'signal' | 'risk' | 'prophet' | 'ml' | 'config' | 'other'
  details?: {
    ml_advice?: string
    ml_confidence?: number
    oracle_advice?: string
    oracle_confidence?: number
    oracle_win_prob?: number
    oracle_reasoning?: string
    oracle_top_factors?: Array<{ factor: string; impact: number }>
    oracle_thresholds?: {
      min_win_probability?: number
      vix_skip?: number
    }
    min_win_probability_threshold?: number
    vix?: number
    spot_price?: number
    gex_regime?: string
    rr_ratio?: number
    min_rr_required?: number
  }
}

interface WhyNotTradingProps {
  skipReasons: SkipReason[]
  isLoading?: boolean
  maxDisplay?: number
}

const getCategoryConfig = (category: SkipReason['category']) => {
  switch (category) {
    case 'market':
      return { icon: Clock, color: 'text-yellow-400', bg: 'bg-yellow-900/20', label: 'Market' }
    case 'signal':
      return { icon: Brain, color: 'text-blue-400', bg: 'bg-blue-900/20', label: 'Signal' }
    case 'risk':
      return { icon: AlertCircle, color: 'text-red-400', bg: 'bg-red-900/20', label: 'Risk' }
    case 'prophet':
      return { icon: Target, color: 'text-purple-400', bg: 'bg-purple-900/20', label: 'Prophet' }
    case 'ml':
      return { icon: Brain, color: 'text-cyan-400', bg: 'bg-cyan-900/20', label: 'ML' }
    case 'config':
      return { icon: XCircle, color: 'text-gray-400', bg: 'bg-gray-900/20', label: 'Config' }
    default:
      return { icon: AlertCircle, color: 'text-gray-400', bg: 'bg-gray-900/20', label: 'Other' }
  }
}

export default function WhyNotTrading({ skipReasons, isLoading = false, maxDisplay = 5 }: WhyNotTradingProps) {
  const [expanded, setExpanded] = useState(false)
  const [expandedItem, setExpandedItem] = useState<string | null>(null)

  if (isLoading) {
    return (
      <div className="bg-gray-900/50 rounded-lg border border-gray-700 p-4">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-700 rounded w-1/3 mb-3"></div>
          <div className="space-y-2">
            <div className="h-10 bg-gray-800 rounded"></div>
            <div className="h-10 bg-gray-800 rounded"></div>
          </div>
        </div>
      </div>
    )
  }

  if (skipReasons.length === 0) {
    return null // Don't show if no skips
  }

  const displayReasons = expanded ? skipReasons : skipReasons.slice(0, maxDisplay)
  const hasMore = skipReasons.length > maxDisplay

  return (
    <div className="bg-gray-900/50 rounded-lg border border-gray-700 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-700 bg-gray-800/50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-yellow-400" />
            <span className="text-sm font-medium text-white">Why Not Trading</span>
            <span className="text-xs text-gray-400">({skipReasons.length} skips today)</span>
          </div>
          {hasMore && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-xs text-gray-400 hover:text-white flex items-center gap-1"
            >
              {expanded ? 'Show less' : `Show all (${skipReasons.length})`}
              {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          )}
        </div>
      </div>

      {/* Skip Reasons List */}
      <div className="divide-y divide-gray-800">
        {displayReasons.map((skip) => {
          const config = getCategoryConfig(skip.category)
          const Icon = config.icon
          const isItemExpanded = expandedItem === skip.id

          return (
            <div key={skip.id} className="px-4 py-2 hover:bg-gray-800/30 transition-colors">
              <div
                className="flex items-start gap-3 cursor-pointer"
                onClick={() => setExpandedItem(isItemExpanded ? null : skip.id)}
              >
                {/* Time */}
                <span className="text-xs text-gray-500 font-mono whitespace-nowrap pt-0.5">
                  {new Date(skip.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'America/Chicago' })} CT
                </span>

                {/* Category Badge */}
                <span className={`px-1.5 py-0.5 rounded text-xs ${config.bg} ${config.color} flex items-center gap-1`}>
                  <Icon className="w-3 h-3" />
                  {config.label}
                </span>

                {/* Reason */}
                <span className="text-sm text-gray-300 flex-1">{typeof skip.reason === 'object' ? JSON.stringify(skip.reason) : skip.reason}</span>

                {/* Expand indicator if has details */}
                {skip.details && (
                  <span className="text-gray-500">
                    {isItemExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </span>
                )}
              </div>

              {/* Expanded Details */}
              {isItemExpanded && skip.details && (
                <div className="mt-2 ml-16 p-2 bg-gray-800/50 rounded text-xs space-y-1">
                  <div className="grid grid-cols-2 gap-2">
                    {skip.details.ml_advice && (
                      <div>
                        <span className="text-gray-500">ML:</span>
                        <span className={`ml-1 ${skip.details.ml_advice === 'STAY_OUT' ? 'text-red-400' : 'text-green-400'}`}>
                          {skip.details.ml_advice}
                        </span>
                        {skip.details.ml_confidence && (
                          <span className="text-gray-400 ml-1">({(skip.details.ml_confidence * 100).toFixed(0)}%)</span>
                        )}
                      </div>
                    )}
                    {skip.details.oracle_advice && (
                      <div className="col-span-2">
                        <span className="text-gray-500">Prophet:</span>
                        <span className={`ml-1 ${skip.details.oracle_advice === 'SKIP_TODAY' ? 'text-red-400' : 'text-green-400'}`}>
                          {skip.details.oracle_advice}
                        </span>
                        {skip.details.oracle_win_prob !== undefined && (
                          <span className={`ml-2 ${
                            skip.details.oracle_win_prob >= (skip.details.min_win_probability_threshold || 0.55)
                              ? 'text-green-400'
                              : 'text-red-400'
                          }`}>
                            Win: {(skip.details.oracle_win_prob * 100).toFixed(0)}%
                            {skip.details.min_win_probability_threshold && (
                              <span className="text-gray-500 ml-1">
                                (min: {(skip.details.min_win_probability_threshold * 100).toFixed(0)}%)
                              </span>
                            )}
                          </span>
                        )}
                        {skip.details.oracle_confidence && (
                          <span className="text-gray-400 ml-2">Conf: {(skip.details.oracle_confidence * 100).toFixed(0)}%</span>
                        )}
                      </div>
                    )}
                    {/* Prophet Top Factors */}
                    {skip.details.oracle_top_factors && skip.details.oracle_top_factors.length > 0 && (
                      <div className="col-span-2">
                        <span className="text-gray-500">Top Factors:</span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {skip.details.oracle_top_factors.slice(0, 3).map((f, i) => (
                            <span key={i} className={`px-1.5 py-0.5 rounded text-xs ${
                              f.impact > 0 ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                            }`}>
                              {f.factor}: {f.impact > 0 ? '+' : ''}{(f.impact * 100).toFixed(1)}%
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    {/* Prophet Reasoning */}
                    {skip.details.oracle_reasoning && (
                      <div className="col-span-2 text-gray-400 italic">
                        {skip.details.oracle_reasoning}
                      </div>
                    )}
                    {skip.details.vix && (
                      <div>
                        <span className="text-gray-500">VIX:</span>
                        <span className="ml-1 text-white">{skip.details.vix.toFixed(1)}</span>
                      </div>
                    )}
                    {skip.details.gex_regime && (
                      <div>
                        <span className="text-gray-500">GEX:</span>
                        <span className="ml-1 text-white">{skip.details.gex_regime}</span>
                      </div>
                    )}
                    {skip.details.rr_ratio !== undefined && skip.details.min_rr_required && (
                      <div className="col-span-2">
                        <span className="text-gray-500">R:R Ratio:</span>
                        <span className={`ml-1 ${skip.details.rr_ratio < skip.details.min_rr_required ? 'text-red-400' : 'text-green-400'}`}>
                          {skip.details.rr_ratio.toFixed(2)}:1
                        </span>
                        <span className="text-gray-400 ml-1">(need {skip.details.min_rr_required}:1)</span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
