'use client'

import { MessageSquare, RefreshCw } from 'lucide-react'
import { useMarketCommentary } from '@/lib/hooks/useMarketData'

export default function MarketCommentary() {
  const { data, error, isLoading, isValidating, mutate } = useMarketCommentary()

  const formatLastUpdated = (dateStr: string) => {
    return new Date(dateStr).toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
      timeZone: 'America/Chicago'
    })
  }

  const commentary = data?.data?.commentary || ''
  const generatedAt = data?.data?.generated_at || ''
  const lastUpdated = generatedAt ? formatLastUpdated(generatedAt) : ''
  const loading = isLoading && !data
  const refreshing = isValidating

  return (
    <div className="card bg-gradient-to-r from-primary/5 to-transparent border border-primary/20">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-5 h-5 text-primary" />
          <h3 className="text-lg font-semibold text-text-primary">Live Market Commentary</h3>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-xs text-text-muted">
              Updated {lastUpdated}
            </span>
          )}
          <button
            onClick={() => mutate()}
            disabled={refreshing}
            className="p-2 hover:bg-primary/10 rounded-lg transition-colors disabled:opacity-50"
            title="Refresh commentary"
          >
            <RefreshCw className={`w-4 h-4 text-primary ${refreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {loading ? (
          <div className="animate-pulse">
            <div className="h-4 bg-background-hover rounded w-full mb-2"></div>
            <div className="h-4 bg-background-hover rounded w-5/6 mb-2"></div>
            <div className="h-4 bg-background-hover rounded w-4/6"></div>
          </div>
        ) : error ? (
          <div className="p-4 bg-danger/10 border border-danger/20 rounded-lg">
            <p className="text-danger text-sm">{error.message || 'Unable to load commentary'}</p>
          </div>
        ) : (
          <>
            <div className="prose prose-sm max-w-none">
              <p className="text-text-primary leading-relaxed whitespace-pre-wrap">
                {commentary || 'Market commentary temporarily unavailable. Please refresh.'}
              </p>
            </div>

            <div className="mt-4 pt-4 border-t border-border">
              <div className="flex items-center gap-2 text-xs text-text-muted">
                <div className="w-2 h-2 bg-success rounded-full animate-pulse"></div>
                <span>AI-powered live analysis • Updates every 5 minutes • Cached across pages</span>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
