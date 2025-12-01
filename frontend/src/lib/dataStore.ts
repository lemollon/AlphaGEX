/**
 * Persistent Data Store for AlphaGEX
 *
 * Caches data across page navigation using localStorage
 * Automatically expires stale data based on TTL
 */
import { logger } from '@/lib/logger'

interface CachedData<T> {
  data: T
  timestamp: number
  ttl: number // Time to live in milliseconds
}

class DataStore {
  private storageKey = 'alphagex_cache'
  private cache: Map<string, CachedData<any>>

  constructor() {
    this.cache = new Map()
    this.loadFromStorage()
  }

  /**
   * Get data from cache
   * Returns null if expired or not found
   */
  get<T>(key: string): T | null {
    const cached = this.cache.get(key)

    if (!cached) {
      return null
    }

    // Check if expired
    const now = Date.now()
    if (now - cached.timestamp > cached.ttl) {
      this.cache.delete(key)
      this.saveToStorage()
      return null
    }

    logger.debug(`Cache HIT: ${key} (${Math.round((cached.ttl - (now - cached.timestamp)) / 1000)}s remaining)`)
    return cached.data as T
  }

  /**
   * Set data in cache
   */
  set<T>(key: string, data: T, ttl: number = 5 * 60 * 1000): void {
    this.cache.set(key, {
      data,
      timestamp: Date.now(),
      ttl
    })
    this.saveToStorage()
    logger.debug(`Cache SET: ${key} (TTL: ${ttl / 1000}s)`)
  }

  /**
   * Clear specific key or all cache
   */
  clear(key?: string): void {
    if (key) {
      this.cache.delete(key)
      logger.debug(`Cache CLEAR: ${key}`)
    } else {
      this.cache.clear()
      logger.debug('Cache CLEAR: all')
    }
    this.saveToStorage()
  }

  /**
   * Get cache statistics
   */
  getStats() {
    const now = Date.now()
    const entries = Array.from(this.cache.entries())

    return {
      totalEntries: entries.length,
      validEntries: entries.filter(([_, v]) => now - v.timestamp < v.ttl).length,
      expiredEntries: entries.filter(([_, v]) => now - v.timestamp >= v.ttl).length,
      totalSize: new Blob([JSON.stringify(Array.from(this.cache))]).size,
      entries: entries.map(([key, value]) => ({
        key,
        age: Math.round((now - value.timestamp) / 1000),
        ttl: Math.round(value.ttl / 1000),
        expired: now - value.timestamp >= value.ttl
      }))
    }
  }

  /**
   * Load cache from localStorage
   * Only runs in browser (not during SSR)
   */
  private loadFromStorage(): void {
    // Skip if not in browser (e.g., during Next.js SSR)
    if (typeof window === 'undefined') {
      return
    }

    try {
      const stored = localStorage.getItem(this.storageKey)
      if (stored) {
        const parsed = JSON.parse(stored)
        this.cache = new Map(parsed)

        // Clean expired entries on load
        const now = Date.now()
        let cleanedCount = 0

        for (const [key, value] of this.cache.entries()) {
          if (now - value.timestamp > value.ttl) {
            this.cache.delete(key)
            cleanedCount++
          }
        }

        if (cleanedCount > 0) {
          logger.debug(`Cleaned ${cleanedCount} expired cache entries`)
          this.saveToStorage()
        }

        logger.debug(`Cache loaded: ${this.cache.size} entries`)
      }
    } catch (error) {
      logger.error('Failed to load cache from storage:', error)
      this.cache = new Map()
    }
  }

  /**
   * Save cache to localStorage
   * Only runs in browser (not during SSR)
   */
  private saveToStorage(): void {
    // Skip if not in browser (e.g., during Next.js SSR)
    if (typeof window === 'undefined') {
      return
    }

    try {
      const serialized = JSON.stringify(Array.from(this.cache.entries()))
      localStorage.setItem(this.storageKey, serialized)
    } catch (error) {
      logger.error('Failed to save cache to storage:', error)
      // If storage is full, clear old entries and try again
      if (error instanceof Error && error.name === 'QuotaExceededError') {
        logger.warn('Storage quota exceeded, clearing old cache entries')
        this.clearOldestEntries(5)
        try {
          const serialized = JSON.stringify(Array.from(this.cache.entries()))
          localStorage.setItem(this.storageKey, serialized)
        } catch (e) {
          logger.error('Still failed after clearing old entries')
        }
      }
    }
  }

  /**
   * Clear the N oldest entries
   */
  private clearOldestEntries(count: number): void {
    const entries = Array.from(this.cache.entries())
    entries.sort((a, b) => a[1].timestamp - b[1].timestamp)

    for (let i = 0; i < Math.min(count, entries.length); i++) {
      this.cache.delete(entries[i][0])
    }
  }
}

// Singleton instance
export const dataStore = new DataStore()

// Export for debugging in console
if (typeof window !== 'undefined') {
  (window as any).dataStore = dataStore
}

/**
 * React hook for using persistent cache
 */
export function usePersistentCache<T>(key: string, ttl: number = 5 * 60 * 1000) {
  const get = (): T | null => dataStore.get<T>(key)
  const set = (data: T) => dataStore.set(key, data, ttl)
  const clear = () => dataStore.clear(key)

  return { get, set, clear }
}

export default dataStore
