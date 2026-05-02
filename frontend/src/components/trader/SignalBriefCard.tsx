'use client'

import { Brain, RefreshCw } from 'lucide-react'

interface BriefData {
  ticker: string
  brief: string
  model?: string
  fetched_at?: number
  cache_age_seconds?: number
}

interface Props {
  data?: BriefData
  loading?: boolean
  reason?: string
}

/**
 * Claude-generated plain-English read on what the perp bot is seeing.
 * Sits at the top of each perp dashboard so the operator gets context
 * before the raw numbers below.
 */
export default function SignalBriefCard({ data, loading, reason }: Props) {
  return (
    <div className="bg-gradient-to-br from-purple-900/20 to-blue-900/20 border border-purple-500/30 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Brain className="w-5 h-5 text-purple-400" />
          <h3 className="text-base font-semibold text-purple-200">Signal Brief</h3>
          <span className="text-xs text-purple-400/60">powered by Claude</span>
        </div>
        {data?.cache_age_seconds !== undefined && (
          <div className="flex items-center gap-1 text-xs text-gray-500">
            <RefreshCw className="w-3 h-3" />
            <span>{data.cache_age_seconds}s ago</span>
          </div>
        )}
      </div>

      {loading && !data && (
        <div className="space-y-2 animate-pulse">
          <div className="h-4 bg-gray-800 rounded w-3/4" />
          <div className="h-4 bg-gray-800 rounded w-full" />
          <div className="h-4 bg-gray-800 rounded w-5/6" />
        </div>
      )}

      {!loading && !data && (
        <div className="text-sm text-gray-400">
          {reason || 'Signal brief unavailable. Set ANTHROPIC_API_KEY to enable Claude-generated briefs.'}
        </div>
      )}

      {data && (
        <div className="text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">
          {data.brief}
        </div>
      )}
    </div>
  )
}
