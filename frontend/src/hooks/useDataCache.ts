import { useState, useEffect, useCallback } from 'react'
import { logger } from '@/lib/logger'

interface CacheOptions {
  key: string
  ttl?: number // Time to live in milliseconds (default: 5 minutes)
}

interface CacheData<T> {
  data: T
  timestamp: number
}

/**
 * Hook for caching data with automatic expiration
 * Persists data across page refreshes using sessionStorage
 */
export function useDataCache<T>(options: CacheOptions) {
  const { key, ttl = 5 * 60 * 1000 } = options // Default 5 minutes
  const [cachedData, setCachedData] = useState<T | null>(null)
  const [lastFetch, setLastFetch] = useState<number>(0)

  // Load cached data on mount
  useEffect(() => {
    try {
      const cached = sessionStorage.getItem(key)
      if (cached) {
        const parsed: CacheData<T> = JSON.parse(cached)
        const age = Date.now() - parsed.timestamp

        if (age < ttl) {
          setCachedData(parsed.data)
          setLastFetch(parsed.timestamp)
        } else {
          // Cache expired
          sessionStorage.removeItem(key)
        }
      }
    } catch (error) {
      logger.error('Error loading cached data:', error)
      sessionStorage.removeItem(key)
    }
  }, [key, ttl])

  // Save data to cache
  const setCache = useCallback((data: T) => {
    const cacheData: CacheData<T> = {
      data,
      timestamp: Date.now()
    }

    try {
      sessionStorage.setItem(key, JSON.stringify(cacheData))
      setCachedData(data)
      setLastFetch(cacheData.timestamp)
    } catch (error) {
      logger.error('Error saving to cache:', error)
    }
  }, [key])

  // Clear cache
  const clearCache = useCallback(() => {
    try {
      sessionStorage.removeItem(key)
      setCachedData(null)
      setLastFetch(0)
    } catch (error) {
      logger.error('Error clearing cache:', error)
    }
  }, [key])

  // Check if cache is fresh
  const isCacheFresh = useCallback(() => {
    if (!lastFetch) return false
    const age = Date.now() - lastFetch
    return age < ttl
  }, [lastFetch, ttl])

  // Get time until cache expires
  const timeUntilExpiry = useCallback(() => {
    if (!lastFetch) return 0
    const age = Date.now() - lastFetch
    const remaining = ttl - age
    return Math.max(0, remaining)
  }, [lastFetch, ttl])

  return {
    cachedData,
    setCache,
    clearCache,
    isCacheFresh: isCacheFresh(),
    timeUntilExpiry: timeUntilExpiry(),
    lastFetch
  }
}
