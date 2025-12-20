'use client'

import useSWR, { SWRConfiguration, preload } from 'swr'
import { apiClient, api } from '@/lib/api'

// =============================================================================
// SWR FETCHERS - Wrapped API calls for SWR
// =============================================================================

const fetchers = {
  // Dashboard
  marketCommentary: async () => {
    const response = await apiClient.getMarketCommentary()
    return response.data
  },
  dailyTradingPlan: async () => {
    const response = await apiClient.getDailyTradingPlan()
    return response.data
  },
  intelligenceFeed: async () => {
    const response = await apiClient.getIntelligenceFeed()
    return response.data
  },

  // GEX & Gamma
  gex: async (symbol: string) => {
    const response = await apiClient.getGEX(symbol)
    return response.data
  },
  gexLevels: async (symbol: string) => {
    const response = await apiClient.getGEXLevels(symbol)
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
  gammaProbabilities: async (symbol: string) => {
    const response = await apiClient.getGammaProbabilities(symbol)
    return response.data
  },
  gexHistory: async (symbol: string, days: number) => {
    const response = await apiClient.getGEXHistory(symbol, days)
    return response.data
  },

  // VIX
  vixCurrent: async () => {
    const response = await apiClient.getVIXCurrent()
    return response.data
  },
  vixHedgeSignal: async () => {
    const response = await apiClient.getVIXHedgeSignal()
    return response.data
  },
  vixSignalHistory: async () => {
    try {
      const response = await api.get('/api/vix/signal-history')
      return response.data
    } catch {
      return { success: false, data: [] }
    }
  },

  // Psychology
  psychologyRegime: async (symbol: string) => {
    const response = await apiClient.getPsychologyCurrentRegime(symbol)
    return response.data
  },

  // ARES Bot
  aresStatus: async () => {
    const response = await apiClient.getARESPageStatus()
    return response.data
  },
  aresPerformance: async () => {
    const response = await apiClient.getARESPerformance()
    return response.data
  },
  aresPositions: async () => {
    const response = await apiClient.getARESPositions()
    return response.data
  },
  aresMarketData: async () => {
    const response = await apiClient.getARESMarketData()
    return response.data
  },
  aresDecisions: async (limit: number) => {
    const response = await apiClient.getARESDecisions(limit)
    return response.data
  },
  aresEquityCurve: async (days: number) => {
    try {
      const response = await api.get(`/api/ares/equity-curve?days=${days}`)
      return response.data
    } catch {
      return { success: false, data: { equity_curve: [] } }
    }
  },
  aresTradierStatus: async () => {
    try {
      const response = await api.get('/api/ares/tradier-status')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  aresConfig: async () => {
    try {
      const response = await api.get('/api/ares/config')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },

  // ATHENA Bot
  athenaStatus: async () => {
    const response = await apiClient.getATHENAStatus()
    return response.data
  },
  athenaPositions: async () => {
    const response = await apiClient.getATHENAPositions()
    return response.data
  },
  athenaSignals: async (limit: number) => {
    const response = await apiClient.getATHENASignals(limit)
    return response.data
  },
  athenaPerformance: async (days: number) => {
    const response = await apiClient.getATHENAPerformance(days)
    return response.data
  },
  athenaOracleAdvice: async () => {
    try {
      const response = await api.get('/api/athena/oracle-advice')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  athenaMLSignal: async () => {
    try {
      const response = await api.get('/api/athena/ml-signal')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  athenaLogs: async (level?: string, limit?: number) => {
    try {
      const params = new URLSearchParams()
      if (level) params.append('level', level)
      params.append('limit', String(limit || 50))
      const response = await api.get(`/api/athena/logs?${params}`)
      return response.data
    } catch {
      return { success: false, data: [] }
    }
  },

  // PHOENIX Trader
  traderStatus: async () => {
    const response = await apiClient.getTraderStatus()
    return response.data
  },
  traderPerformance: async () => {
    const response = await apiClient.getTraderPerformance()
    return response.data
  },
  traderPositions: async () => {
    const response = await apiClient.getOpenPositions()
    return response.data
  },

  // Scanner
  scannerHistory: async (limit: number) => {
    const response = await apiClient.getScannerHistory(limit)
    return response.data
  },

  // Oracle
  oracleStatus: async () => {
    const response = await apiClient.getOracleStatus()
    return response.data
  },
  oracleLogs: async () => {
    const response = await apiClient.getOracleLogs()
    return response.data
  },
  oraclePredictions: async (params: { days: number; limit: number }) => {
    const response = await apiClient.getOraclePredictions(params)
    return response.data
  },

  // ML System
  mlStatus: async () => {
    const response = await apiClient.getMLStatus()
    return response.data
  },
  mlFeatureImportance: async () => {
    const response = await apiClient.getMLFeatureImportance()
    return response.data
  },

  // Decision Logs
  decisionLogs: async (params: any) => {
    const response = await apiClient.getDecisionLogs(params)
    return response.data
  },
  decisionSummary: async (params: any) => {
    const response = await apiClient.getDecisionSummary(params)
    return response.data
  },

  // Wheel Bots
  wheelCycles: async () => {
    const response = await apiClient.getWheelCycles()
    return response.data
  },
  spxStatus: async () => {
    const response = await apiClient.getSPXStatus()
    return response.data
  },
  spxPerformance: async () => {
    const response = await apiClient.getSPXPerformance()
    return response.data
  },

  // Alerts
  alerts: async () => {
    const response = await apiClient.getAlerts()
    return response.data
  },
  alertHistory: async (limit?: number) => {
    try {
      const response = await api.get(`/api/alerts/history?limit=${limit || 100}`)
      return response.data
    } catch {
      return { success: false, data: [] }
    }
  },

  // Database
  databaseStats: async () => {
    const response = await apiClient.getDatabaseStats()
    return response.data
  },
  tableFreshness: async () => {
    const response = await apiClient.getTableFreshness()
    return response.data
  },
  systemHealth: async () => {
    try {
      const response = await api.get('/api/health')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  systemLogs: async (limit?: number) => {
    try {
      const response = await api.get(`/api/logs/system?limit=${limit || 50}`)
      return response.data
    } catch {
      return { success: false, data: [] }
    }
  },

  // Logs Summary
  logsSummary: async (days?: number) => {
    try {
      const response = await api.get(`/api/logs/summary?days=${days || 30}`)
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  mlLogs: async (limit?: number) => {
    try {
      const response = await api.get(`/api/logs/ml?limit=${limit || 50}`)
      return response.data
    } catch {
      return { success: false, data: { logs: [] } }
    }
  },
  autonomousLogs: async (limit?: number) => {
    try {
      const response = await api.get(`/api/logs/autonomous?limit=${limit || 50}`)
      return response.data
    } catch {
      return { success: false, data: { logs: [] } }
    }
  },

  // ML Extended
  mlDataQuality: async () => {
    try {
      const response = await api.get('/api/ml/data-quality')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  mlStrategy: async () => {
    try {
      const response = await api.get('/api/ml/strategy')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },

  // Zero DTE Backtest
  zeroDTEResults: async () => {
    const response = await apiClient.getZeroDTEResults()
    return response.data
  },
  zeroDTEStrategies: async () => {
    const response = await apiClient.getZeroDTEStrategies()
    return response.data
  },

  // Volatility
  volSurfaceAnalysis: async (symbol: string) => {
    const response = await apiClient.getVolSurfaceAnalysis(symbol)
    return response.data
  },
}

// =============================================================================
// SWR CONFIG - Global caching settings
// =============================================================================

export const swrConfig: SWRConfiguration = {
  revalidateOnFocus: false,
  revalidateOnReconnect: true,
  dedupingInterval: 60000,
  errorRetryCount: 3,
  errorRetryInterval: 5000,
  keepPreviousData: true,
}

// =============================================================================
// DASHBOARD HOOKS
// =============================================================================

export function useMarketCommentary(options?: SWRConfiguration) {
  return useSWR('market-commentary', fetchers.marketCommentary, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,
    ...options,
  })
}

export function useDailyTradingPlan(options?: SWRConfiguration) {
  return useSWR('daily-trading-plan', fetchers.dailyTradingPlan, {
    ...swrConfig,
    refreshInterval: 30 * 60 * 1000,
    ...options,
  })
}

export function useIntelligenceFeed(options?: SWRConfiguration) {
  return useSWR('intelligence-feed', fetchers.intelligenceFeed, {
    ...swrConfig,
    refreshInterval: 2 * 60 * 1000, // 2 minutes - matches backend cache
    ...options,
  })
}

// =============================================================================
// GEX & GAMMA HOOKS
// =============================================================================

export function useGEX(symbol: string = 'SPY', options?: SWRConfiguration) {
  return useSWR(
    symbol ? `gex-${symbol}` : null,
    () => fetchers.gex(symbol),
    { ...swrConfig, refreshInterval: 2 * 60 * 1000, ...options }
  )
}

export function useGEXLevels(symbol: string = 'SPY', options?: SWRConfiguration) {
  return useSWR(
    symbol ? `gex-levels-${symbol}` : null,
    () => fetchers.gexLevels(symbol),
    { ...swrConfig, refreshInterval: 2 * 60 * 1000, ...options }
  )
}

export function useGammaExpiration(symbol: string = 'SPY', options?: SWRConfiguration) {
  return useSWR(
    symbol ? `gamma-expiration-${symbol}` : null,
    () => fetchers.gammaExpiration(symbol),
    { ...swrConfig, refreshInterval: 5 * 60 * 1000, ...options }
  )
}

export function useGammaIntelligence(symbol: string = 'SPY', options?: SWRConfiguration) {
  return useSWR(
    symbol ? `gamma-intelligence-${symbol}` : null,
    () => fetchers.gammaIntelligence(symbol),
    { ...swrConfig, refreshInterval: 2 * 60 * 1000, ...options }
  )
}

export function useGammaProbabilities(symbol: string = 'SPY', options?: SWRConfiguration) {
  return useSWR(
    symbol ? `gamma-probabilities-${symbol}` : null,
    () => fetchers.gammaProbabilities(symbol),
    { ...swrConfig, refreshInterval: 5 * 60 * 1000, ...options }
  )
}

export function useGEXHistory(symbol: string = 'SPY', days: number = 90, options?: SWRConfiguration) {
  return useSWR(
    `gex-history-${symbol}-${days}`,
    () => fetchers.gexHistory(symbol, days),
    { ...swrConfig, refreshInterval: 10 * 60 * 1000, ...options }
  )
}

// =============================================================================
// VIX HOOKS
// =============================================================================

export function useVIX(options?: SWRConfiguration) {
  return useSWR('vix-current', fetchers.vixCurrent, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useVIXHedgeSignal(options?: SWRConfiguration) {
  return useSWR('vix-hedge-signal', fetchers.vixHedgeSignal, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useVIXSignalHistory(options?: SWRConfiguration) {
  return useSWR('vix-signal-history', fetchers.vixSignalHistory, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,
    ...options,
  })
}

// =============================================================================
// PSYCHOLOGY HOOKS
// =============================================================================

export function usePsychologyRegime(symbol: string = 'SPY', options?: SWRConfiguration) {
  return useSWR(
    symbol ? `psychology-regime-${symbol}` : null,
    () => fetchers.psychologyRegime(symbol),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

// =============================================================================
// ARES BOT HOOKS
// =============================================================================

export function useARESStatus(options?: SWRConfiguration) {
  return useSWR('ares-status', fetchers.aresStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useARESPerformance(options?: SWRConfiguration) {
  return useSWR('ares-performance', fetchers.aresPerformance, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useARESPositions(options?: SWRConfiguration) {
  return useSWR('ares-positions', fetchers.aresPositions, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useARESMarketData(options?: SWRConfiguration) {
  return useSWR('ares-market-data', fetchers.aresMarketData, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useARESDecisions(limit: number = 50, options?: SWRConfiguration) {
  return useSWR(
    `ares-decisions-${limit}`,
    () => fetchers.aresDecisions(limit),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useARESEquityCurve(days: number = 30, options?: SWRConfiguration) {
  return useSWR(
    `ares-equity-curve-${days}`,
    () => fetchers.aresEquityCurve(days),
    { ...swrConfig, refreshInterval: 5 * 60 * 1000, ...options }
  )
}

export function useARESTradierStatus(options?: SWRConfiguration) {
  return useSWR('ares-tradier-status', fetchers.aresTradierStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useARESConfig(options?: SWRConfiguration) {
  return useSWR('ares-config', fetchers.aresConfig, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,
    ...options,
  })
}

// =============================================================================
// ATHENA BOT HOOKS
// =============================================================================

export function useATHENAStatus(options?: SWRConfiguration) {
  return useSWR('athena-status', fetchers.athenaStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useATHENAPositions(options?: SWRConfiguration) {
  return useSWR('athena-positions', fetchers.athenaPositions, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useATHENASignals(limit: number = 50, options?: SWRConfiguration) {
  return useSWR(
    `athena-signals-${limit}`,
    () => fetchers.athenaSignals(limit),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useATHENAPerformance(days: number = 30, options?: SWRConfiguration) {
  return useSWR(
    `athena-performance-${days}`,
    () => fetchers.athenaPerformance(days),
    { ...swrConfig, refreshInterval: 5 * 60 * 1000, ...options }
  )
}

export function useATHENAOracleAdvice(options?: SWRConfiguration) {
  return useSWR('athena-oracle-advice', fetchers.athenaOracleAdvice, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useATHENAMLSignal(options?: SWRConfiguration) {
  return useSWR('athena-ml-signal', fetchers.athenaMLSignal, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useATHENALogs(level?: string, limit: number = 50, options?: SWRConfiguration) {
  return useSWR(
    `athena-logs-${level || 'all'}-${limit}`,
    () => fetchers.athenaLogs(level, limit),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

// =============================================================================
// PHOENIX TRADER HOOKS
// =============================================================================

export function useTraderStatus(options?: SWRConfiguration) {
  return useSWR('trader-status', fetchers.traderStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useTraderPerformance(options?: SWRConfiguration) {
  return useSWR('trader-performance', fetchers.traderPerformance, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useTraderPositions(options?: SWRConfiguration) {
  return useSWR('trader-positions', fetchers.traderPositions, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

// =============================================================================
// SCANNER HOOKS
// =============================================================================

export function useScannerHistory(limit: number = 10, options?: SWRConfiguration) {
  return useSWR(
    `scanner-history-${limit}`,
    () => fetchers.scannerHistory(limit),
    { ...swrConfig, refreshInterval: 5 * 60 * 1000, ...options }
  )
}

// =============================================================================
// ORACLE HOOKS
// =============================================================================

export function useOracleStatus(options?: SWRConfiguration) {
  return useSWR('oracle-status', fetchers.oracleStatus, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useOracleLogs(options?: SWRConfiguration) {
  return useSWR('oracle-logs', fetchers.oracleLogs, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useOraclePredictions(days: number = 30, limit: number = 100, options?: SWRConfiguration) {
  return useSWR(
    `oracle-predictions-${days}-${limit}`,
    () => fetchers.oraclePredictions({ days, limit }),
    { ...swrConfig, refreshInterval: 5 * 60 * 1000, ...options }
  )
}

// =============================================================================
// ML SYSTEM HOOKS
// =============================================================================

export function useMLStatus(options?: SWRConfiguration) {
  return useSWR('ml-status', fetchers.mlStatus, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,
    ...options,
  })
}

export function useMLFeatureImportance(options?: SWRConfiguration) {
  return useSWR('ml-feature-importance', fetchers.mlFeatureImportance, {
    ...swrConfig,
    refreshInterval: 10 * 60 * 1000,
    ...options,
  })
}

// =============================================================================
// DECISION LOGS HOOKS
// =============================================================================

export function useDecisionLogs(params?: any, options?: SWRConfiguration) {
  const key = params ? `decision-logs-${JSON.stringify(params)}` : 'decision-logs'
  return useSWR(
    key,
    () => fetchers.decisionLogs(params || {}),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useDecisionSummary(params?: any, options?: SWRConfiguration) {
  const key = params ? `decision-summary-${JSON.stringify(params)}` : 'decision-summary'
  return useSWR(
    key,
    () => fetchers.decisionSummary(params || {}),
    { ...swrConfig, refreshInterval: 5 * 60 * 1000, ...options }
  )
}

// =============================================================================
// WHEEL BOTS HOOKS
// =============================================================================

export function useWheelCycles(options?: SWRConfiguration) {
  return useSWR('wheel-cycles', fetchers.wheelCycles, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useSPXStatus(options?: SWRConfiguration) {
  return useSWR('spx-status', fetchers.spxStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useSPXPerformance(options?: SWRConfiguration) {
  return useSWR('spx-performance', fetchers.spxPerformance, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

// =============================================================================
// ALERTS HOOKS
// =============================================================================

export function useAlerts(options?: SWRConfiguration) {
  return useSWR('alerts', fetchers.alerts, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useAlertHistory(limit: number = 100, options?: SWRConfiguration) {
  return useSWR(
    `alert-history-${limit}`,
    () => fetchers.alertHistory(limit),
    { ...swrConfig, refreshInterval: 5 * 60 * 1000, ...options }
  )
}

// =============================================================================
// DATABASE HOOKS
// =============================================================================

export function useDatabaseStats(options?: SWRConfiguration) {
  return useSWR('database-stats', fetchers.databaseStats, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,
    ...options,
  })
}

export function useTableFreshness(options?: SWRConfiguration) {
  return useSWR('table-freshness', fetchers.tableFreshness, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,
    ...options,
  })
}

export function useSystemHealth(options?: SWRConfiguration) {
  return useSWR('system-health', fetchers.systemHealth, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useSystemLogs(limit: number = 50, options?: SWRConfiguration) {
  return useSWR(
    `system-logs-${limit}`,
    () => fetchers.systemLogs(limit),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

// =============================================================================
// LOGS SUMMARY HOOKS
// =============================================================================

export function useLogsSummary(days: number = 30, options?: SWRConfiguration) {
  return useSWR(
    `logs-summary-${days}`,
    () => fetchers.logsSummary(days),
    { ...swrConfig, refreshInterval: 5 * 60 * 1000, ...options }
  )
}

export function useMLLogs(limit: number = 50, options?: SWRConfiguration) {
  return useSWR(
    `ml-logs-${limit}`,
    () => fetchers.mlLogs(limit),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useAutonomousLogs(limit: number = 50, options?: SWRConfiguration) {
  return useSWR(
    `autonomous-logs-${limit}`,
    () => fetchers.autonomousLogs(limit),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

// =============================================================================
// ML EXTENDED HOOKS
// =============================================================================

export function useMLDataQuality(options?: SWRConfiguration) {
  return useSWR('ml-data-quality', fetchers.mlDataQuality, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,
    ...options,
  })
}

export function useMLStrategy(options?: SWRConfiguration) {
  return useSWR('ml-strategy', fetchers.mlStrategy, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,
    ...options,
  })
}

// =============================================================================
// ZERO DTE BACKTEST HOOKS
// =============================================================================

export function useZeroDTEResults(options?: SWRConfiguration) {
  return useSWR('zero-dte-results', fetchers.zeroDTEResults, {
    ...swrConfig,
    refreshInterval: 10 * 60 * 1000,
    ...options,
  })
}

export function useZeroDTEStrategies(options?: SWRConfiguration) {
  return useSWR('zero-dte-strategies', fetchers.zeroDTEStrategies, {
    ...swrConfig,
    refreshInterval: 10 * 60 * 1000,
    ...options,
  })
}

// =============================================================================
// VOLATILITY HOOKS
// =============================================================================

export function useVolSurfaceAnalysis(symbol: string = 'SPY', options?: SWRConfiguration) {
  return useSWR(
    `vol-surface-${symbol}`,
    () => fetchers.volSurfaceAnalysis(symbol),
    { ...swrConfig, refreshInterval: 5 * 60 * 1000, ...options }
  )
}

// =============================================================================
// PREFETCH - Warm the cache on app load
// =============================================================================

export const prefetchMarketData = {
  // Individual prefetchers
  commentary: () => preload('market-commentary', fetchers.marketCommentary),
  dailyPlan: () => preload('daily-trading-plan', fetchers.dailyTradingPlan),
  gex: (symbol: string = 'SPY') => preload(`gex-${symbol}`, () => fetchers.gex(symbol)),
  gammaExpiration: (symbol: string = 'SPY') =>
    preload(`gamma-expiration-${symbol}`, () => fetchers.gammaExpiration(symbol)),
  gammaIntelligence: (symbol: string = 'SPY') =>
    preload(`gamma-intelligence-${symbol}`, () => fetchers.gammaIntelligence(symbol)),
  vix: () => preload('vix-current', fetchers.vixCurrent),
  aresStatus: () => preload('ares-status', fetchers.aresStatus),
  athenaStatus: () => preload('athena-status', fetchers.athenaStatus),
  traderStatus: () => preload('trader-status', fetchers.traderStatus),

  // Prefetch all common data at once
  all: (symbol: string = 'SPY') => {
    // Dashboard
    prefetchMarketData.commentary()
    prefetchMarketData.dailyPlan()
    prefetchMarketData.gammaExpiration(symbol)

    // Core market data
    prefetchMarketData.gex(symbol)
    prefetchMarketData.gammaIntelligence(symbol)
    prefetchMarketData.vix()

    // Bot statuses
    prefetchMarketData.aresStatus()
    prefetchMarketData.athenaStatus()
    prefetchMarketData.traderStatus()
  },
}
