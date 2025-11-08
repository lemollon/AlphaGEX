/**
 * Centralized Cache Configuration for AlphaGEX
 *
 * Optimized to minimize API calls while keeping data fresh where needed.
 * Trading Volatility API Limit: 20 calls/minute (shared across ALL deployments)
 */

export const CACHE_DURATIONS = {
  // ========================================================================
  // HIGH FREQUENCY - During Market Hours (5 minutes)
  // ========================================================================

  /** SPY spot price - shown in navigation, needs to be reasonably current */
  SPY_PRICE: 5 * 60 * 1000, // 5 minutes

  /** Open positions P&L - traders want to see current unrealized P&L */
  OPEN_POSITIONS: 5 * 60 * 1000, // 5 minutes

  /** Trader status - autonomous trader's current action and state */
  TRADER_STATUS: 5 * 60 * 1000, // 5 minutes

  // ========================================================================
  // MEDIUM FREQUENCY - Hourly Updates
  // ========================================================================

  /** GEX data - gamma exposure changes gradually throughout the day */
  GEX_DATA: 30 * 60 * 1000, // 30 minutes

  /** Psychology/Regime analysis - market regime shifts take time */
  PSYCHOLOGY_REGIME: 60 * 60 * 1000, // 1 hour

  /** Gamma intelligence - Greeks and exposures update slowly */
  GAMMA_INTELLIGENCE: 60 * 60 * 1000, // 1 hour

  // ========================================================================
  // LOW FREQUENCY - Daily or On-Demand
  // ========================================================================

  /** Strategy comparison - strategies don't change intraday */
  STRATEGY_COMPARISON: 24 * 60 * 60 * 1000, // 1 day (refresh at market open)

  /** Performance metrics - P&L summary updated end of day */
  PERFORMANCE_METRICS: 24 * 60 * 60 * 1000, // 1 day

  /** Trade history - historical trades don't change */
  TRADE_HISTORY: 24 * 60 * 60 * 1000, // 1 day

  /** Alert configuration - user's alert list changes rarely */
  ALERTS_LIST: 24 * 60 * 60 * 1000, // 1 day (or until user modifies)

  /** Alert history - triggered alerts update when alerts fire */
  ALERT_HISTORY: 60 * 60 * 1000, // 1 hour

  // ========================================================================
  // ON-DEMAND ONLY - User Initiates
  // ========================================================================

  /** Scanner results - expensive operation, user triggers manually */
  SCANNER_RESULTS: 60 * 60 * 1000, // 1 hour (but only runs on user click)

  /** Scan history - past scans don't change */
  SCAN_HISTORY: 24 * 60 * 60 * 1000, // 1 day

  // ========================================================================
  // PERSISTENT - Rarely Changes
  // ========================================================================

  /** Market status (open/closed) - changes twice per day */
  MARKET_STATUS: 30 * 60 * 1000, // 30 minutes

  /** VIX data - updated every hour */
  VIX_DATA: 60 * 60 * 1000, // 1 hour
} as const

/**
 * Get cache duration with market hours awareness
 * During market hours (9:30 AM - 4:00 PM ET), use shorter TTLs
 * After hours, extend TTLs by 4x to conserve API quota
 */
export function getAdaptiveCacheDuration(baseDuration: number): number {
  const now = new Date()
  const hours = now.getHours()
  const day = now.getDay()

  // Weekend - extend cache by 10x
  if (day === 0 || day === 6) {
    return baseDuration * 10
  }

  // Weekday market hours (9:30 AM - 4:00 PM ET = 8:30 AM - 3:00 PM CT)
  // Using CT since backend is in Central Time
  const isMarketHours = hours >= 8 && hours < 15

  if (!isMarketHours) {
    // After hours - extend cache by 4x
    return baseDuration * 4
  }

  return baseDuration
}

/**
 * Cache TTL helper with logging
 */
export function getCacheTTL(
  cacheType: keyof typeof CACHE_DURATIONS,
  adaptive: boolean = true
): number {
  const baseDuration = CACHE_DURATIONS[cacheType]
  const ttl = adaptive ? getAdaptiveCacheDuration(baseDuration) : baseDuration

  if (process.env.NODE_ENV === 'development') {
    console.log(`📦 Cache TTL for ${cacheType}: ${ttl / 1000 / 60} minutes`)
  }

  return ttl
}

/**
 * Rate limit protection - minimum time between manual refreshes
 */
export const RATE_LIMIT_COOLDOWNS = {
  /** GEX Analysis - prevent spam refreshing */
  GEX_ANALYSIS: 60 * 1000, // 1 minute

  /** Psychology - expensive endpoint */
  PSYCHOLOGY: 60 * 1000, // 1 minute

  /** Scanner - very expensive batch operation */
  SCANNER: 5 * 60 * 1000, // 5 minutes

  /** Gamma Intelligence */
  GAMMA: 60 * 1000, // 1 minute

  /** Alerts check */
  ALERTS_CHECK: 2 * 60 * 1000, // 2 minutes

  /** Default for any manual refresh */
  DEFAULT: 60 * 1000, // 1 minute
} as const

/**
 * WebSocket reconnection configuration
 */
export const WEBSOCKET_CONFIG = {
  /** Delay before attempting reconnection */
  RECONNECT_DELAY: 5 * 1000, // 5 seconds

  /** Maximum reconnection attempts before giving up */
  MAX_RECONNECT_ATTEMPTS: 5,

  /** Exponential backoff multiplier */
  BACKOFF_MULTIPLIER: 2,
} as const

/**
 * Priority levels for API request queue (future implementation)
 */
export const API_PRIORITY = {
  HIGH: 1,    // Psychology, user-initiated actions
  MEDIUM: 5,  // GEX data, gamma intelligence
  LOW: 10,    // Scanner, historical data
} as const
