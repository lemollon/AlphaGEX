'use client'

import { logger } from '@/lib/logger'

import { useState, useEffect, useCallback } from 'react'
import { MessageSquare, RefreshCw } from 'lucide-react'
import { apiClient } from '@/lib/api'

const CACHE_KEY = 'alphagex_market_commentary'
const CACHE_DURATION_MS = 5 * 60 * 1000 // 5 minutes (matches auto-refresh interval)

interface CachedCommentary {
  commentary: string
  generatedAt: string
  cachedAt: number
}

export default function MarketCommentary() {
  const [commentary, setCommentary] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<string>('')
  const [error, setError] = useState<string>('')

  const formatLastUpdated = (dateStr: string) => {
    return new Date(dateStr).toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
      timeZone: 'America/Chicago'
    })
  }

  const loadFromCache = useCallback((): CachedCommentary | null => {
    try {
      const cached = localStorage.getItem(CACHE_KEY)
      if (cached) {
        const data: CachedCommentary = JSON.parse(cached)
        const isExpired = Date.now() - data.cachedAt > CACHE_DURATION_MS
        if (!isExpired) {
          return data
        }
      }
    } catch (e) {
      logger.error('Failed to load commentary from cache:', e)
    }
    return null
  }, [])

  const saveToCache = useCallback((commentaryData: string, generatedAtStr: string) => {
    try {
      const cacheData: CachedCommentary = {
        commentary: commentaryData,
        generatedAt: generatedAtStr,
        cachedAt: Date.now()
      }
      localStorage.setItem(CACHE_KEY, JSON.stringify(cacheData))
    } catch (e) {
      logger.error('Failed to save commentary to cache:', e)
    }
  }, [])

  const fetchCommentary = async (forceRefresh = false) => {
    // Check cache first (unless force refresh)
    if (!forceRefresh) {
      const cached = loadFromCache()
      if (cached) {
        setCommentary(cached.commentary)
        setLastUpdated(formatLastUpdated(cached.generatedAt))
        setLoading(false)
        setError('')
        return
      }
    }

    try {
      setLoading(true)
      setError('')
      const response = await apiClient.getMarketCommentary()

      if (response.data.success) {
        const commentaryData = response.data.data.commentary
        const generatedAtStr = response.data.data.generated_at
        setCommentary(commentaryData)
        setLastUpdated(formatLastUpdated(generatedAtStr))
        saveToCache(commentaryData, generatedAtStr)
      }
    } catch (err: any) {
      logger.error('Failed to fetch market commentary:', err)

      // Extract error message from backend or use generic message
      const errorMessage = err?.message || 'Unable to load commentary'
      setError(errorMessage)

      // Show helpful fallback message
      if (errorMessage.includes('API key')) {
        setCommentary('API key not configured. Please contact your administrator.')
      } else {
        setCommentary('Market commentary temporarily unavailable. Please refresh.')
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchCommentary()

    // Auto-refresh every 5 minutes (bypasses cache)
    const interval = setInterval(() => fetchCommentary(true), 5 * 60 * 1000)
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
            onClick={() => fetchCommentary(true)}
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
