/**
 * Intelligent caching system to avoid API rate limit violations
 * Trading Volatility API: 20 calls/min limit
 */

interface CacheEntry<T> {
  data: T
  timestamp: number
  symbol: string
}

const CACHE_PREFIX = 'alphagex_cache_'

// Cache durations (in milliseconds)
export const CACHE_DURATIONS = {
  // Market hours: shorter cache (5 minutes)
  MARKET_OPEN: 5 * 60 * 1000,
  // Market closed: longer cache (30 minutes)
  MARKET_CLOSED: 30 * 60 * 1000,
  // Weekend: very long cache (2 hours)
  WEEKEND: 2 * 60 * 60 * 1000,
}

export class IntelligentCache {
  private static isMarketHours(): boolean {
    const now = new Date()
    const day = now.getDay()
    const hour = now.getHours()

    // Weekend
    if (day === 0 || day === 6) return false

    // Market hours: 9:30 AM - 4:00 PM ET (approx)
    return hour >= 9 && hour < 16
  }

  private static getCacheDuration(): number {
    const now = new Date()
    const day = now.getDay()

    // Weekend
    if (day === 0 || day === 6) {
      return CACHE_DURATIONS.WEEKEND
    }

    // Market hours
    if (this.isMarketHours()) {
      return CACHE_DURATIONS.MARKET_OPEN
    }

    // Market closed
    return CACHE_DURATIONS.MARKET_CLOSED
  }

  static get<T>(key: string): T | null {
    try {
      const cached = localStorage.getItem(CACHE_PREFIX + key)
      if (!cached) return null

      const entry: CacheEntry<T> = JSON.parse(cached)
      const age = Date.now() - entry.timestamp
      const maxAge = this.getCacheDuration()

      if (age > maxAge) {
        // Cache expired
        this.remove(key)
        return null
      }

      console.log(`📦 Cache HIT for ${key} (age: ${Math.floor(age / 1000)}s)`)
      return entry.data
    } catch (error) {
      console.error('Cache read error:', error)
      return null
    }
  }

  static set<T>(key: string, data: T, symbol: string): void {
    try {
      const entry: CacheEntry<T> = {
        data,
        timestamp: Date.now(),
        symbol,
      }
      localStorage.setItem(CACHE_PREFIX + key, JSON.stringify(entry))
      console.log(`💾 Cached ${key} for ${symbol}`)
    } catch (error) {
      console.error('Cache write error:', error)
    }
  }

  static remove(key: string): void {
    localStorage.removeItem(CACHE_PREFIX + key)
  }

  static clear(): void {
    const keys = Object.keys(localStorage)
    keys.forEach((key) => {
      if (key.startsWith(CACHE_PREFIX)) {
        localStorage.removeItem(key)
      }
    })
    console.log('🧹 Cache cleared')
  }

  static getAge(key: string): number | null {
    try {
      const cached = localStorage.getItem(CACHE_PREFIX + key)
      if (!cached) return null

      const entry: CacheEntry<any> = JSON.parse(cached)
      return Date.now() - entry.timestamp
    } catch {
      return null
    }
  }

  static getAgeString(key: string): string {
    const age = this.getAge(key)
    if (age === null) return 'No cache'

    const seconds = Math.floor(age / 1000)
    if (seconds < 60) return `${seconds}s ago`

    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes}m ago`

    const hours = Math.floor(minutes / 60)
    return `${hours}h ago`
  }
}

/**
 * Rate limiter to prevent hitting API limits
 * Ensures we don't exceed 20 calls/min
 */
export class RateLimiter {
  private static callTimestamps: number[] = []
  private static readonly MAX_CALLS_PER_MINUTE = 18 // Conservative limit (leave buffer)
  private static readonly MINUTE_MS = 60 * 1000

  static canMakeCall(): boolean {
    const now = Date.now()
    // Remove timestamps older than 1 minute
    this.callTimestamps = this.callTimestamps.filter(
      (timestamp) => now - timestamp < this.MINUTE_MS
    )

    return this.callTimestamps.length < this.MAX_CALLS_PER_MINUTE
  }

  static recordCall(): void {
    this.callTimestamps.push(Date.now())
  }

  static getCallsInLastMinute(): number {
    const now = Date.now()
    this.callTimestamps = this.callTimestamps.filter(
      (timestamp) => now - timestamp < this.MINUTE_MS
    )
    return this.callTimestamps.length
  }

  static getTimeUntilNextCall(): number {
    if (this.canMakeCall()) return 0

    const now = Date.now()
    const oldestCall = this.callTimestamps[0]
    return Math.max(0, this.MINUTE_MS - (now - oldestCall))
  }

  static async waitForNextCall(): Promise<void> {
    const waitTime = this.getTimeUntilNextCall()
    if (waitTime > 0) {
      console.log(`⏱️ Rate limit: waiting ${Math.ceil(waitTime / 1000)}s`)
      await new Promise((resolve) => setTimeout(resolve, waitTime))
    }
  }
}

/**
 * Staggered loader to load multiple items without hitting rate limits
 */
export class StaggeredLoader {
  static async loadWithDelay<T>(
    items: string[],
    loadFn: (item: string) => Promise<T>,
    delayMs: number = 500 // 500ms between calls = max 120 calls/min (well under limit)
  ): Promise<Record<string, T>> {
    const results: Record<string, T> = {}

    for (let i = 0; i < items.length; i++) {
      const item = items[i]

      // Check cache first
      const cached = IntelligentCache.get<T>(item)
      if (cached) {
        results[item] = cached
        continue
      }

      // Check rate limit
      if (!RateLimiter.canMakeCall()) {
        await RateLimiter.waitForNextCall()
      }

      // Load data
      try {
        RateLimiter.recordCall()
        const data = await loadFn(item)
        results[item] = data
        IntelligentCache.set(item, data, item)
      } catch (error) {
        console.error(`Failed to load ${item}:`, error)
      }

      // Delay before next call (except for last item)
      if (i < items.length - 1) {
        await new Promise((resolve) => setTimeout(resolve, delayMs))
      }
    }

    return results
  }
}
