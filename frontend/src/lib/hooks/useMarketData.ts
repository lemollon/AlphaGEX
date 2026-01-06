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
  liberationSetups: async () => {
    const response = await apiClient.getLiberationSetups()
    return response.data
  },
  falseFloors: async () => {
    const response = await apiClient.getFalseFloors()
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
  aresStrategyPresets: async () => {
    try {
      const response = await apiClient.getARESStrategyPresets()
      return response.data
    } catch {
      return { success: false, data: { presets: [], active_preset: 'moderate' } }
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
  athenaDecisions: async (limit?: number) => {
    try {
      const params = new URLSearchParams()
      params.append('limit', String(limit || 100))
      const response = await api.get(`/api/athena/decisions?${params}`)
      return response.data
    } catch (error) {
      console.error('Error fetching ATHENA decisions:', error)
      return { success: false, data: [], count: 0 }
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
  athenaLivePnL: async () => {
    try {
      const response = await api.get('/api/athena/live-pnl')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  athenaConfig: async () => {
    try {
      const response = await api.get('/api/athena/config')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },

  // ICARUS Bot - Aggressive Directional Spreads
  icarusStatus: async () => {
    try {
      const response = await api.get('/api/icarus/status')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  icarusPositions: async () => {
    try {
      const response = await api.get('/api/icarus/positions')
      return response.data
    } catch {
      return { success: false, data: { open_positions: [], closed_positions: [] } }
    }
  },
  icarusSignals: async (limit: number) => {
    try {
      const response = await api.get(`/api/icarus/signals?limit=${limit}`)
      return response.data
    } catch {
      return { success: false, data: [] }
    }
  },
  icarusPerformance: async (days: number) => {
    try {
      const response = await api.get(`/api/icarus/performance?days=${days}`)
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  icarusOracleAdvice: async () => {
    try {
      const response = await api.get('/api/icarus/oracle-advice')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  icarusLogs: async (level?: string, limit?: number) => {
    try {
      const params = new URLSearchParams()
      if (level) params.append('level', level)
      params.append('limit', String(limit || 50))
      const response = await api.get(`/api/icarus/logs?${params}`)
      return response.data
    } catch {
      return { success: false, data: [] }
    }
  },
  icarusLivePnL: async () => {
    try {
      const response = await api.get('/api/icarus/live-pnl')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  icarusConfig: async () => {
    try {
      const response = await api.get('/api/icarus/config')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  icarusScanActivity: async (limit?: number, date?: string) => {
    try {
      const params = new URLSearchParams()
      params.append('limit', String(limit || 50))
      if (date) params.append('date', date)
      // Use centralized scan activity endpoint (like ATHENA) for full data
      const response = await api.get(`/api/scans/activity/ICARUS?${params}`)
      return response.data
    } catch {
      return { success: false, data: { scans: [] } }
    }
  },

  aresLivePnL: async () => {
    try {
      const response = await api.get('/api/ares/live-pnl')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  aresLogs: async (level?: string, limit: number = 100) => {
    try {
      const response = await api.get('/api/ares/logs', { params: { level, limit } })
      return response.data
    } catch {
      return { success: false, data: [] }
    }
  },

  // Scan Activity - comprehensive logging for EVERY scan
  scanActivityAres: async (limit?: number, date?: string) => {
    try {
      const params = new URLSearchParams()
      params.append('limit', String(limit || 50))
      if (date) params.append('date', date)
      const response = await api.get(`/api/scans/activity/ARES?${params}`)
      return response.data
    } catch {
      return { success: false, data: { scans: [] } }
    }
  },
  scanActivityAthena: async (limit?: number, date?: string) => {
    try {
      const params = new URLSearchParams()
      params.append('limit', String(limit || 50))
      if (date) params.append('date', date)
      const response = await api.get(`/api/scans/activity/ATHENA?${params}`)
      return response.data
    } catch {
      return { success: false, data: { scans: [] } }
    }
  },
  scanActivityToday: async (bot?: string) => {
    try {
      const endpoint = bot ? `/api/scans/${bot.toLowerCase()}/today` : '/api/scans/today'
      const response = await api.get(endpoint)
      return response.data
    } catch {
      return { success: false, data: { scans: [] } }
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
  // NEW: Full transparency data
  oracleDataFlows: async (params?: { limit?: number; bot_name?: string }) => {
    const response = await apiClient.getOracleDataFlows(params)
    return response.data
  },
  oracleClaudeExchanges: async (params?: { limit?: number; bot_name?: string }) => {
    const response = await apiClient.getOracleClaudeExchanges(params)
    return response.data
  },
  oracleFullTransparency: async (bot_name?: string) => {
    const response = await apiClient.getOracleFullTransparency(bot_name)
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
  dataCollectionStatus: async () => {
    try {
      const response = await apiClient.getDataCollectionStatus()
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  watchdogStatus: async () => {
    try {
      const response = await apiClient.getWatchdogStatus()
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
  mlStrategyExplanation: async () => {
    try {
      const response = await api.get('/api/ml/strategy-explanation')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  mlDecisionLogs: async (limit: number = 50) => {
    try {
      const response = await api.get(`/api/ml/logs?limit=${limit}`)
      return response.data
    } catch {
      return { success: false, data: { logs: [] } }
    }
  },

  // PROMETHEUS ML System
  prometheusStatus: async () => {
    try {
      const response = await api.get('/api/prometheus/status')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  prometheusFeatureImportance: async () => {
    try {
      const response = await api.get('/api/prometheus/feature-importance')
      return response.data
    } catch {
      return { success: false, data: { features: [] } }
    }
  },
  prometheusLogs: async (limit: number = 100, logType?: string) => {
    try {
      const params = new URLSearchParams()
      params.append('limit', String(limit))
      if (logType) params.append('log_type', logType)
      const response = await api.get(`/api/prometheus/logs?${params}`)
      return response.data
    } catch {
      return { success: false, data: { logs: [] } }
    }
  },
  prometheusTrainingHistory: async (limit: number = 20) => {
    try {
      const response = await api.get(`/api/prometheus/training-history?limit=${limit}`)
      return response.data
    } catch {
      return { success: false, data: { history: [] } }
    }
  },
  prometheusPerformance: async (periodDays: number = 30) => {
    try {
      const response = await api.get(`/api/prometheus/performance?period_days=${periodDays}`)
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  prometheusHealth: async () => {
    try {
      const response = await api.get('/api/prometheus/health')
      return response.data
    } catch {
      return { status: 'error', prometheus_available: false }
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

  // Daily Manna - Economic news with faith-based devotionals
  dailyManna: async (forceRefresh: boolean = false) => {
    try {
      const response = await apiClient.getDailyManna(forceRefresh)
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  dailyMannaWidget: async () => {
    try {
      const response = await apiClient.getDailyMannaWidget()
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  dailyMannaComments: async (date?: string) => {
    try {
      const response = await apiClient.getDailyMannaComments(date)
      return response.data
    } catch {
      return { success: false, data: { comments: [] } }
    }
  },
  dailyMannaArchive: async (limit: number = 30) => {
    try {
      const response = await apiClient.getDailyMannaArchive(limit)
      return response.data
    } catch {
      return { success: false, data: { archive: [] } }
    }
  },

  // PEGASUS SPX Iron Condor Bot
  pegasusStatus: async () => {
    try {
      const response = await api.get('/api/pegasus/status')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  pegasusPositions: async () => {
    try {
      const response = await api.get('/api/pegasus/positions')
      return response.data
    } catch {
      return { success: false, data: { open_positions: [], closed_positions: [] } }
    }
  },
  pegasusEquityCurve: async (days: number = 30) => {
    try {
      const response = await api.get(`/api/pegasus/equity-curve?days=${days}`)
      return response.data
    } catch {
      return { success: false, data: { equity_curve: [] } }
    }
  },
  pegasusConfig: async () => {
    try {
      const response = await api.get('/api/pegasus/config')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  pegasusLivePnL: async () => {
    try {
      const response = await api.get('/api/pegasus/live-pnl')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  scanActivityPegasus: async (limit?: number, date?: string) => {
    try {
      const params = new URLSearchParams()
      params.append('limit', String(limit || 50))
      if (date) params.append('date', date)
      const response = await api.get(`/api/scans/activity/PEGASUS?${params}`)
      return response.data
    } catch {
      return { success: false, data: { scans: [] } }
    }
  },

  // TITAN Aggressive SPX Iron Condor Bot (Daily Trading)
  titanStatus: async () => {
    try {
      const response = await api.get('/api/titan/status')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  titanPositions: async () => {
    try {
      const response = await api.get('/api/titan/positions')
      return response.data
    } catch {
      return { success: false, data: { open_positions: [], closed_positions: [] } }
    }
  },
  titanEquityCurve: async (days: number = 30) => {
    try {
      const response = await api.get(`/api/titan/equity-curve?days=${days}`)
      return response.data
    } catch {
      return { success: false, data: { equity_curve: [] } }
    }
  },
  titanConfig: async () => {
    try {
      const response = await api.get('/api/titan/config')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  titanLivePnL: async () => {
    try {
      const response = await api.get('/api/titan/live-pnl')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  scanActivityTitan: async (limit?: number, date?: string) => {
    try {
      const params = new URLSearchParams()
      params.append('limit', String(limit || 50))
      if (date) params.append('date', date)
      const response = await api.get(`/api/scans/activity/TITAN?${params}`)
      return response.data
    } catch {
      return { success: false, data: { scans: [] } }
    }
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

export function useLiberationSetups(options?: SWRConfiguration) {
  return useSWR('liberation-setups', fetchers.liberationSetups, {
    ...swrConfig,
    refreshInterval: 2 * 60 * 1000,
    ...options,
  })
}

export function useFalseFloors(options?: SWRConfiguration) {
  return useSWR('false-floors', fetchers.falseFloors, {
    ...swrConfig,
    refreshInterval: 2 * 60 * 1000,
    ...options,
  })
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

export function useARESStrategyPresets(options?: SWRConfiguration) {
  return useSWR('ares-strategy-presets', fetchers.aresStrategyPresets, {
    ...swrConfig,
    refreshInterval: 60 * 1000, // Refresh every minute
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

export function useATHENADecisions(limit: number = 100, options?: SWRConfiguration) {
  return useSWR(
    `athena-decisions-${limit}`,
    () => fetchers.athenaDecisions(limit),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

export function useATHENALivePnL(options?: SWRConfiguration) {
  return useSWR(
    'athena-live-pnl',
    fetchers.athenaLivePnL,
    { ...swrConfig, refreshInterval: 10 * 1000, ...options }  // 10 second refresh for live data
  )
}

export function useATHENAConfig(options?: SWRConfiguration) {
  return useSWR('athena-config', fetchers.athenaConfig, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,  // 5 minute refresh for config
    ...options,
  })
}

export function useARESLivePnL(options?: SWRConfiguration) {
  return useSWR(
    'ares-live-pnl',
    fetchers.aresLivePnL,
    { ...swrConfig, refreshInterval: 10 * 1000, ...options }  // 10 second refresh for live data
  )
}

export function useARESLogs(level?: string, limit: number = 100, options?: SWRConfiguration) {
  return useSWR(
    `ares-logs-${level || 'all'}-${limit}`,
    () => fetchers.aresLogs(level, limit),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

// =============================================================================
// ICARUS BOT HOOKS - Aggressive Directional Spreads
// =============================================================================

export function useICARUSStatus(options?: SWRConfiguration) {
  return useSWR('icarus-status', fetchers.icarusStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useICARUSPositions(options?: SWRConfiguration) {
  return useSWR('icarus-positions', fetchers.icarusPositions, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useICARUSSignals(limit: number = 50, options?: SWRConfiguration) {
  return useSWR(
    `icarus-signals-${limit}`,
    () => fetchers.icarusSignals(limit),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useICARUSPerformance(days: number = 30, options?: SWRConfiguration) {
  return useSWR(
    `icarus-performance-${days}`,
    () => fetchers.icarusPerformance(days),
    { ...swrConfig, refreshInterval: 5 * 60 * 1000, ...options }
  )
}

export function useICARUSOracleAdvice(options?: SWRConfiguration) {
  return useSWR('icarus-oracle-advice', fetchers.icarusOracleAdvice, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useICARUSLogs(level?: string, limit: number = 50, options?: SWRConfiguration) {
  return useSWR(
    `icarus-logs-${level || 'all'}-${limit}`,
    () => fetchers.icarusLogs(level, limit),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

export function useICARUSLivePnL(options?: SWRConfiguration) {
  return useSWR(
    'icarus-live-pnl',
    fetchers.icarusLivePnL,
    { ...swrConfig, refreshInterval: 10 * 1000, ...options }  // 10 second refresh for live data
  )
}

export function useICARUSConfig(options?: SWRConfiguration) {
  return useSWR('icarus-config', fetchers.icarusConfig, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,  // 5 minute refresh for config
    ...options,
  })
}

export function useICARUSScanActivity(limit: number = 50, date?: string, options?: SWRConfiguration) {
  return useSWR(
    `icarus-scan-activity-${limit}-${date || 'all'}`,
    () => fetchers.icarusScanActivity(limit, date),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

// =============================================================================
// SCAN ACTIVITY HOOKS - Every scan with full reasoning
// =============================================================================

export function useScanActivityAres(limit: number = 50, date?: string, options?: SWRConfiguration) {
  return useSWR(
    `scan-activity-ares-${limit}-${date || 'all'}`,
    () => fetchers.scanActivityAres(limit, date),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

export function useScanActivityAthena(limit: number = 50, date?: string, options?: SWRConfiguration) {
  return useSWR(
    `scan-activity-athena-${limit}-${date || 'all'}`,
    () => fetchers.scanActivityAthena(limit, date),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

export function useScanActivityToday(bot?: string, options?: SWRConfiguration) {
  return useSWR(
    `scan-activity-today-${bot || 'all'}`,
    () => fetchers.scanActivityToday(bot),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

// =============================================================================
// PEGASUS SPX IRON CONDOR HOOKS
// =============================================================================

export function usePEGASUSStatus(options?: SWRConfiguration) {
  return useSWR('pegasus-status', fetchers.pegasusStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function usePEGASUSPositions(options?: SWRConfiguration) {
  return useSWR('pegasus-positions', fetchers.pegasusPositions, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function usePEGASUSEquityCurve(days: number = 30, options?: SWRConfiguration) {
  return useSWR(
    `pegasus-equity-curve-${days}`,
    () => fetchers.pegasusEquityCurve(days),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function usePEGASUSConfig(options?: SWRConfiguration) {
  return useSWR('pegasus-config', fetchers.pegasusConfig, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,
    ...options,
  })
}

export function usePEGASUSLivePnL(options?: SWRConfiguration) {
  return useSWR('pegasus-live-pnl', fetchers.pegasusLivePnL, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useScanActivityPegasus(limit: number = 50, date?: string, options?: SWRConfiguration) {
  return useSWR(
    `scan-activity-pegasus-${limit}-${date || 'all'}`,
    () => fetchers.scanActivityPegasus(limit, date),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

// =============================================================================
// TITAN AGGRESSIVE SPX IRON CONDOR HOOKS (Daily Trading)
// =============================================================================

export function useTITANStatus(options?: SWRConfiguration) {
  return useSWR('titan-status', fetchers.titanStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useTITANPositions(options?: SWRConfiguration) {
  return useSWR('titan-positions', fetchers.titanPositions, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useTITANEquityCurve(days: number = 30, options?: SWRConfiguration) {
  return useSWR(
    `titan-equity-curve-${days}`,
    () => fetchers.titanEquityCurve(days),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useTITANConfig(options?: SWRConfiguration) {
  return useSWR('titan-config', fetchers.titanConfig, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,
    ...options,
  })
}

export function useTITANLivePnL(options?: SWRConfiguration) {
  return useSWR('titan-live-pnl', fetchers.titanLivePnL, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useScanActivityTitan(limit: number = 50, date?: string, options?: SWRConfiguration) {
  return useSWR(
    `scan-activity-titan-${limit}-${date || 'all'}`,
    () => fetchers.scanActivityTitan(limit, date),
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
    refreshInterval: 30 * 1000,  // Refresh every 30 seconds for fresher heartbeats
    ...options,
  })
}

export function useOracleLogs(options?: SWRConfiguration) {
  return useSWR('oracle-logs', fetchers.oracleLogs, {
    ...swrConfig,
    refreshInterval: 15 * 1000,  // Refresh every 15 seconds for live logs
    ...options,
  })
}

export function useOraclePredictions(days: number = 30, limit: number = 100, options?: SWRConfiguration) {
  return useSWR(
    `oracle-predictions-${days}-${limit}`,
    () => fetchers.oraclePredictions({ days, limit }),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

// NEW: Full transparency hooks with auto-refresh
export function useOracleDataFlows(limit: number = 50, bot_name?: string, options?: SWRConfiguration) {
  return useSWR(
    `oracle-data-flows-${limit}-${bot_name || 'all'}`,
    () => fetchers.oracleDataFlows({ limit, bot_name }),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

export function useOracleClaudeExchanges(limit: number = 20, bot_name?: string, options?: SWRConfiguration) {
  return useSWR(
    `oracle-claude-exchanges-${limit}-${bot_name || 'all'}`,
    () => fetchers.oracleClaudeExchanges({ limit, bot_name }),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

export function useOracleFullTransparency(bot_name?: string, options?: SWRConfiguration) {
  return useSWR(
    `oracle-full-transparency-${bot_name || 'all'}`,
    () => fetchers.oracleFullTransparency(bot_name),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
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

export function useDataCollectionStatus(options?: SWRConfiguration) {
  return useSWR('data-collection-status', fetchers.dataCollectionStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useWatchdogStatus(options?: SWRConfiguration) {
  return useSWR('watchdog-status', fetchers.watchdogStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
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

export function useMLStrategyExplanation(options?: SWRConfiguration) {
  return useSWR('ml-strategy-explanation', fetchers.mlStrategyExplanation, {
    ...swrConfig,
    refreshInterval: 30 * 60 * 1000, // Static content - cache for 30 minutes
    ...options,
  })
}

export function useMLDecisionLogs(limit: number = 50, options?: SWRConfiguration) {
  return useSWR(
    `ml-decision-logs-${limit}`,
    () => fetchers.mlDecisionLogs(limit),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

// =============================================================================
// PROMETHEUS ML SYSTEM HOOKS
// =============================================================================

export function usePrometheusStatus(options?: SWRConfiguration) {
  return useSWR('prometheus-status', fetchers.prometheusStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function usePrometheusFeatureImportance(options?: SWRConfiguration) {
  return useSWR('prometheus-feature-importance', fetchers.prometheusFeatureImportance, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,
    ...options,
  })
}

export function usePrometheusLogs(limit: number = 100, logType?: string, options?: SWRConfiguration) {
  return useSWR(
    `prometheus-logs-${limit}-${logType || 'all'}`,
    () => fetchers.prometheusLogs(limit, logType),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

export function usePrometheusTrainingHistory(limit: number = 20, options?: SWRConfiguration) {
  return useSWR(
    `prometheus-training-history-${limit}`,
    () => fetchers.prometheusTrainingHistory(limit),
    { ...swrConfig, refreshInterval: 5 * 60 * 1000, ...options }
  )
}

export function usePrometheusPerformance(periodDays: number = 30, options?: SWRConfiguration) {
  return useSWR(
    `prometheus-performance-${periodDays}`,
    () => fetchers.prometheusPerformance(periodDays),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function usePrometheusHealth(options?: SWRConfiguration) {
  return useSWR('prometheus-health', fetchers.prometheusHealth, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
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
// DAILY MANNA HOOKS - Economic news with faith-based devotionals
// =============================================================================

export function useDailyManna(forceRefresh: boolean = false, options?: SWRConfiguration) {
  return useSWR(
    'daily-manna',
    () => fetchers.dailyManna(forceRefresh),
    {
      ...swrConfig,
      refreshInterval: 30 * 60 * 1000, // 30 minutes - content is cached per day
      ...options,
    }
  )
}

export function useDailyMannaWidget(options?: SWRConfiguration) {
  return useSWR('daily-manna-widget', fetchers.dailyMannaWidget, {
    ...swrConfig,
    refreshInterval: 10 * 60 * 1000, // 10 minutes
    ...options,
  })
}

export function useDailyMannaComments(date?: string, options?: SWRConfiguration) {
  return useSWR(
    date ? `daily-manna-comments-${date}` : 'daily-manna-comments',
    () => fetchers.dailyMannaComments(date),
    {
      ...swrConfig,
      refreshInterval: 60 * 1000, // 1 minute for live comments
      ...options,
    }
  )
}

export function useDailyMannaArchive(limit: number = 30, options?: SWRConfiguration) {
  return useSWR(
    `daily-manna-archive-${limit}`,
    () => fetchers.dailyMannaArchive(limit),
    {
      ...swrConfig,
      refreshInterval: 10 * 60 * 1000, // 10 minutes
      ...options,
    }
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
  dailyManna: () => preload('daily-manna', () => fetchers.dailyManna()),
  dailyMannaWidget: () => preload('daily-manna-widget', fetchers.dailyMannaWidget),

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
