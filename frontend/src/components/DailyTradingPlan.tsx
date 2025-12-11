'use client'

import { logger } from '@/lib/logger'

import { useState, useEffect, useCallback } from 'react'
import { Calendar, ChevronDown, ChevronUp, RefreshCw } from 'lucide-react'
import { apiClient } from '@/lib/api'

const CACHE_KEY = 'alphagex_daily_plan'
const CACHE_DURATION_MS = 30 * 60 * 1000 // 30 minutes (plan updates daily at market open)

interface CachedPlan {
  plan: string
  generatedAt: string
  cachedAt: number
}

export default function DailyTradingPlan() {
  const [plan, setPlan] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(true)
  const [generatedAt, setGeneratedAt] = useState<string>('')

  const formatGeneratedAt = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
      month: 'short',
      day: 'numeric',
      timeZone: 'America/Chicago'
    })
  }

  const loadFromCache = useCallback((): CachedPlan | null => {
    try {
      const cached = localStorage.getItem(CACHE_KEY)
      if (cached) {
        const data: CachedPlan = JSON.parse(cached)
        const isExpired = Date.now() - data.cachedAt > CACHE_DURATION_MS
        if (!isExpired) {
          return data
        }
      }
    } catch (e) {
      logger.error('Failed to load plan from cache:', e)
    }
    return null
  }, [])

  const saveToCache = useCallback((planData: string, generatedAtStr: string) => {
    try {
      const cacheData: CachedPlan = {
        plan: planData,
        generatedAt: generatedAtStr,
        cachedAt: Date.now()
      }
      localStorage.setItem(CACHE_KEY, JSON.stringify(cacheData))
    } catch (e) {
      logger.error('Failed to save plan to cache:', e)
    }
  }, [])

  const fetchPlan = async (forceRefresh = false) => {
    // Check cache first (unless force refresh)
    if (!forceRefresh) {
      const cached = loadFromCache()
      if (cached) {
        setPlan(cached.plan)
        setGeneratedAt(formatGeneratedAt(cached.generatedAt))
        setLoading(false)
        return
      }
    }

    try {
      setLoading(true)
      const response = await apiClient.getDailyTradingPlan()

      if (response.data.success) {
        const planData = response.data.data.plan
        const generatedAtStr = response.data.data.generated_at
        setPlan(planData)
        setGeneratedAt(formatGeneratedAt(generatedAtStr))
        saveToCache(planData, generatedAtStr)
      }
    } catch (err: any) {
      logger.error('Failed to fetch daily plan:', err)

      // Extract error message from backend or use generic message
      const errorMessage = err?.message || 'Daily trading plan temporarily unavailable.'

      // Show helpful fallback message based on error type
      if (errorMessage.includes('API key')) {
        setPlan('⚠️ API key not configured. Please contact your administrator to enable AI-powered trading plans.')
      } else {
        setPlan('Daily trading plan temporarily unavailable. Please try refreshing.')
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchPlan()
  }, [])

  return (
    <div className="card bg-gradient-to-r from-success/5 to-transparent border border-success/20">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Calendar className="w-5 h-5 text-success" />
          <h3 className="text-lg font-semibold text-text-primary">📋 Daily Trading Plan</h3>
        </div>
        <div className="flex items-center gap-2">
          {generatedAt && (
            <span className="text-xs text-text-muted">{generatedAt}</span>
          )}
          <button
            onClick={() => fetchPlan(true)}
            disabled={loading}
            className="p-2 hover:bg-success/10 rounded-lg transition-colors"
            title="Refresh plan"
          >
            <RefreshCw className={`w-4 h-4 text-success ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-2 hover:bg-success/10 rounded-lg transition-colors"
          >
            {expanded ? (
              <ChevronUp className="w-4 h-4 text-success" />
            ) : (
              <ChevronDown className="w-4 h-4 text-success" />
            )}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="space-y-3">
          {loading ? (
            <div className="animate-pulse space-y-2">
              <div className="h-4 bg-background-hover rounded w-full"></div>
              <div className="h-4 bg-background-hover rounded w-5/6"></div>
              <div className="h-4 bg-background-hover rounded w-4/6"></div>
              <div className="h-4 bg-background-hover rounded w-full"></div>
              <div className="h-4 bg-background-hover rounded w-3/4"></div>
            </div>
          ) : (
            <>
              <div className="prose prose-sm max-w-none max-h-96 overflow-y-auto pr-2">
                <div className="text-text-primary whitespace-pre-wrap leading-relaxed">
                  {plan}
                </div>
              </div>

              <div className="mt-4 pt-4 border-t border-border flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs text-text-muted">
                  <div className="w-2 h-2 bg-success rounded-full"></div>
                  <span>Generated by Claude Haiku 4.5 • Updated daily at market open</span>
                </div>
                <button
                  onClick={() => fetchPlan(true)}
                  className="text-xs text-success hover:underline font-medium"
                >
                  Refresh Plan
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {!expanded && (
        <p className="text-sm text-text-secondary">
          Click to expand your personalized daily trading plan...
        </p>
      )}
    </div>
  )
}
