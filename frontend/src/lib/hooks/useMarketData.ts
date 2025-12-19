'use client'

import useSWR, { SWRConfiguration, preload } from 'swr'
import { apiClient } from '@/lib/api'

// =============================================================================
// SWR FETCHERS - Wrapped API calls for SWR
// =============================================================================

const fetchers = {
  marketCommentary: async () => {
    const response = await apiClient.getMarketCommentary()
    return response.data
  },
  dailyTradingPlan: async () => {
    const response = await apiClient.getDailyTradingPlan()
    return response.data
  },
  gammaExpiration: async (symbol: string) => {
    const response = await apiClient.getGammaExpiration(symbol)
    return response.data
  },
  gammaIntelligence: async (symbol: string) => {
    const response = await apiClient.getGammaIntelligence(symbol)
    return response.data
  },
  gex: async (symbol: string) => {
    const response = await apiClient.getGEX(symbol)
    return response.data
  },
  psychologyRegime: async (symbol: string) => {
    const response = await apiClient.getPsychologyCurrentRegime(symbol)
    return response.data
  },
  vixCurrent: async () => {
    const response = await apiClient.getVIXCurrent()
    return response.data
  },
  aresStatus: async () => {
    const response = await apiClient.getARESPageStatus()
    return response.data
  },
  athenaStatus: async () => {
    const response = await apiClient.getATHENAStatus()
    return response.data
  },
  traderStatus: async () => {
    const response = await apiClient.getTraderStatus()
    return response.data
  },
}

// =============================================================================
// SWR CONFIG - Global caching settings
// =============================================================================

// Cache data for 5 minutes, revalidate in background
export const swrConfig: SWRConfiguration = {
  revalidateOnFocus: false,        // Don't refetch on window focus
  revalidateOnReconnect: true,     // Refetch on reconnect
  dedupingInterval: 60000,         // Dedupe requests within 1 minute
  errorRetryCount: 3,              // Retry 3 times on error
  errorRetryInterval: 5000,        // Wait 5s between retries
  keepPreviousData: true,          // Keep showing old data while fetching new
}

// =============================================================================
// HOOKS - Use these in components for cached, persistent data
// =============================================================================

/**
 * Market Commentary - AI-generated live analysis
 * Refreshes every 5 minutes, cached across navigation
 */
export function useMarketCommentary(options?: SWRConfiguration) {
  return useSWR(
    'market-commentary',
    fetchers.marketCommentary,
    {
      ...swrConfig,
      refreshInterval: 5 * 60 * 1000, // 5 minutes
      ...options,
    }
  )
}

/**
 * Daily Trading Plan - AI-generated daily plan
 * Refreshes every 30 minutes, cached across navigation
 */
export function useDailyTradingPlan(options?: SWRConfiguration) {
  return useSWR(
    'daily-trading-plan',
    fetchers.dailyTradingPlan,
    {
      ...swrConfig,
      refreshInterval: 30 * 60 * 1000, // 30 minutes
      ...options,
    }
  )
}

/**
 * Gamma Expiration (0DTE) - Weekly gamma decay data
 * Refreshes every 5 minutes, cached per symbol
 */
export function useGammaExpiration(symbol: string = 'SPY', options?: SWRConfiguration) {
  return useSWR(
    symbol ? `gamma-expiration-${symbol}` : null,
    () => fetchers.gammaExpiration(symbol),
    {
      ...swrConfig,
      refreshInterval: 5 * 60 * 1000, // 5 minutes
      ...options,
    }
  )
}

/**
 * Gamma Intelligence - Full gamma analysis with market maker states
 * Refreshes every 2 minutes, cached per symbol
 */
export function useGammaIntelligence(symbol: string = 'SPY', options?: SWRConfiguration) {
  return useSWR(
    symbol ? `gamma-intelligence-${symbol}` : null,
    () => fetchers.gammaIntelligence(symbol),
    {
      ...swrConfig,
      refreshInterval: 2 * 60 * 1000, // 2 minutes
      ...options,
    }
  )
}

/**
 * GEX Data - Core gamma exposure data
 * Refreshes every 2 minutes, cached per symbol
 */
export function useGEX(symbol: string = 'SPY', options?: SWRConfiguration) {
  return useSWR(
    symbol ? `gex-${symbol}` : null,
    () => fetchers.gex(symbol),
    {
      ...swrConfig,
      refreshInterval: 2 * 60 * 1000, // 2 minutes
      ...options,
    }
  )
}

/**
 * Psychology Regime - Current market regime analysis
 * Refreshes every minute, cached per symbol
 */
export function usePsychologyRegime(symbol: string = 'SPY', options?: SWRConfiguration) {
  return useSWR(
    symbol ? `psychology-regime-${symbol}` : null,
    () => fetchers.psychologyRegime(symbol),
    {
      ...swrConfig,
      refreshInterval: 60 * 1000, // 1 minute
      ...options,
    }
  )
}

/**
 * VIX Data - Current volatility index
 * Refreshes every minute
 */
export function useVIX(options?: SWRConfiguration) {
  return useSWR(
    'vix-current',
    fetchers.vixCurrent,
    {
      ...swrConfig,
      refreshInterval: 60 * 1000, // 1 minute
      ...options,
    }
  )
}

/**
 * ARES Bot Status
 * Refreshes every 30 seconds
 */
export function useARESStatus(options?: SWRConfiguration) {
  return useSWR(
    'ares-status',
    fetchers.aresStatus,
    {
      ...swrConfig,
      refreshInterval: 30 * 1000, // 30 seconds
      ...options,
    }
  )
}

/**
 * ATHENA Bot Status
 * Refreshes every 30 seconds
 */
export function useATHENAStatus(options?: SWRConfiguration) {
  return useSWR(
    'athena-status',
    fetchers.athenaStatus,
    {
      ...swrConfig,
      refreshInterval: 30 * 1000, // 30 seconds
      ...options,
    }
  )
}

/**
 * Trader Status (PHOENIX)
 * Refreshes every 30 seconds
 */
export function useTraderStatus(options?: SWRConfiguration) {
  return useSWR(
    'trader-status',
    fetchers.traderStatus,
    {
      ...swrConfig,
      refreshInterval: 30 * 1000, // 30 seconds
      ...options,
    }
  )
}

// =============================================================================
// PREFETCH - Call these to warm the cache before navigation
// =============================================================================

export const prefetchMarketData = {
  commentary: () => preload('market-commentary', fetchers.marketCommentary),
  dailyPlan: () => preload('daily-trading-plan', fetchers.dailyTradingPlan),
  gammaExpiration: (symbol: string = 'SPY') =>
    preload(`gamma-expiration-${symbol}`, () => fetchers.gammaExpiration(symbol)),
  gammaIntelligence: (symbol: string = 'SPY') =>
    preload(`gamma-intelligence-${symbol}`, () => fetchers.gammaIntelligence(symbol)),
  gex: (symbol: string = 'SPY') =>
    preload(`gex-${symbol}`, () => fetchers.gex(symbol)),
  psychologyRegime: (symbol: string = 'SPY') =>
    preload(`psychology-regime-${symbol}`, () => fetchers.psychologyRegime(symbol)),
  vix: () => preload('vix-current', fetchers.vixCurrent),

  // Prefetch all common data at once
  all: (symbol: string = 'SPY') => {
    prefetchMarketData.commentary()
    prefetchMarketData.dailyPlan()
    prefetchMarketData.gammaExpiration(symbol)
    prefetchMarketData.gex(symbol)
    prefetchMarketData.vix()
  },
}
