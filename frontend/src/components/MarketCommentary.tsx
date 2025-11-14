'use client'

import { useState, useEffect } from 'react'
import { MessageSquare, RefreshCw } from 'lucide-react'
import { apiClient } from '@/lib/api'

export default function MarketCommentary() {
  const [commentary, setCommentary] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<string>('')
  const [error, setError] = useState<string>('')

  const fetchCommentary = async () => {
    try {
      setLoading(true)
      setError('')
      const response = await apiClient.getMarketCommentary()

      if (response.data.success) {
        setCommentary(response.data.data.commentary)
        setLastUpdated(new Date(response.data.data.generated_at).toLocaleTimeString('en-US', {
          hour: 'numeric',
          minute: '2-digit',
          hour12: true,
          timeZone: 'America/Chicago'
        }))
      }
    } catch (err: any) {
      console.error('Failed to fetch market commentary:', err)
      setError('Unable to load commentary')
      setCommentary('Market commentary temporarily unavailable. Please refresh.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchCommentary()

    // Auto-refresh every 5 minutes
    const interval = setInterval(fetchCommentary, 5 * 60 * 1000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="card bg-gradient-to-r from-primary/5 to-transparent border border-primary/20">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-5 h-5 text-primary" />
          <h3 className="text-lg font-semibold text-text-primary">🗣️ Live Market Commentary</h3>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-xs text-text-muted">
              Updated {lastUpdated}
            </span>
          )}
          <button
            onClick={fetchCommentary}
            disabled={loading}
            className="p-2 hover:bg-primary/10 rounded-lg transition-colors disabled:opacity-50"
            title="Refresh commentary"
          >
            <RefreshCw className={`w-4 h-4 text-primary ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {loading && !commentary ? (
          <div className="animate-pulse">
            <div className="h-4 bg-background-hover rounded w-full mb-2"></div>
            <div className="h-4 bg-background-hover rounded w-5/6 mb-2"></div>
            <div className="h-4 bg-background-hover rounded w-4/6"></div>
          </div>
        ) : error ? (
          <div className="p-4 bg-danger/10 border border-danger/20 rounded-lg">
            <p className="text-danger text-sm">{error}</p>
          </div>
        ) : (
          <>
            <div className="prose prose-sm max-w-none">
              <p className="text-text-primary leading-relaxed whitespace-pre-wrap">
                {commentary}
              </p>
            </div>

            <div className="mt-4 pt-4 border-t border-border">
              <div className="flex items-center gap-2 text-xs text-text-muted">
                <div className="w-2 h-2 bg-success rounded-full animate-pulse"></div>
                <span>AI-powered live analysis • Updates every 5 minutes</span>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
