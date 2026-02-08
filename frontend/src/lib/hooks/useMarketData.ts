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

  // FORTRESS Bot
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
      const response = await api.get(`/api/fortress/equity-curve?days=${days}`)
      return response.data
    } catch {
      return { success: false, data: { equity_curve: [] } }
    }
  },
  aresIntradayEquity: async (date?: string) => {
    try {
      const params = date ? `?date=${date}` : ''
      const response = await api.get(`/api/fortress/equity-curve/intraday${params}`)
      return response.data
    } catch {
      return { success: false, data: { intraday_curve: [] } }
    }
  },
  aresTradierStatus: async () => {
    try {
      const response = await api.get('/api/fortress/tradier-status')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  aresConfig: async () => {
    try {
      const response = await api.get('/api/fortress/config')
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

  // SOLOMON Bot
  solomonStatus: async () => {
    const response = await apiClient.getATHENAStatus()
    return response.data
  },
  solomonPositions: async () => {
    const response = await apiClient.getATHENAPositions()
    return response.data
  },
  solomonSignals: async (limit: number) => {
    const response = await apiClient.getSolomonSignals(limit)
    return response.data
  },
  solomonPerformance: async (days: number) => {
    const response = await apiClient.getATHENAPerformance(days)
    return response.data
  },
  solomonOracleAdvice: async () => {
    try {
      const response = await api.get('/api/solomon/oracle-advice')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  solomonMLSignal: async () => {
    try {
      const response = await api.get('/api/solomon/ml-signal')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  solomonDecisions: async (limit?: number) => {
    try {
      const params = new URLSearchParams()
      params.append('limit', String(limit || 100))
      const response = await api.get(`/api/solomon/decisions?${params}`)
      return response.data
    } catch (error) {
      console.error('Error fetching SOLOMON decisions:', error)
      return { success: false, data: [], count: 0 }
    }
  },
  solomonLogs: async (level?: string, limit?: number) => {
    try {
      const params = new URLSearchParams()
      if (level) params.append('level', level)
      params.append('limit', String(limit || 50))
      const response = await api.get(`/api/solomon/logs?${params}`)
      return response.data
    } catch {
      return { success: false, data: [] }
    }
  },
  solomonLivePnL: async () => {
    try {
      const response = await api.get('/api/solomon/live-pnl')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  solomonConfig: async () => {
    try {
      const response = await api.get('/api/solomon/config')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  solomonEquityCurve: async (days: number = 30) => {
    try {
      const response = await api.get(`/api/solomon/equity-curve?days=${days}`)
      return response.data
    } catch {
      return { success: false, data: { equity_curve: [] } }
    }
  },
  solomonIntradayEquity: async (date?: string) => {
    try {
      const params = date ? `?date=${date}` : ''
      const response = await api.get(`/api/solomon/equity-curve/intraday${params}`)
      return response.data
    } catch {
      return { success: false, data: { intraday_curve: [] } }
    }
  },

  // GIDEON Bot - Aggressive Directional Spreads
  icarusStatus: async () => {
    try {
      const response = await api.get('/api/gideon/status')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  icarusPositions: async () => {
    try {
      const response = await api.get('/api/gideon/positions')
      return response.data
    } catch {
      // Return consistent shape - data should always be an array like success case
      return { success: false, data: [] }
    }
  },
  icarusSignals: async (limit: number) => {
    try {
      const response = await api.get(`/api/gideon/signals?limit=${limit}`)
      return response.data
    } catch {
      return { success: false, data: [] }
    }
  },
  icarusPerformance: async (days: number) => {
    try {
      const response = await api.get(`/api/gideon/performance?days=${days}`)
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  icarusOracleAdvice: async () => {
    try {
      const response = await api.get('/api/gideon/oracle-advice')
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
      const response = await api.get(`/api/gideon/logs?${params}`)
      return response.data
    } catch {
      return { success: false, data: [] }
    }
  },
  icarusLivePnL: async () => {
    try {
      const response = await api.get('/api/gideon/live-pnl')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  icarusConfig: async () => {
    try {
      const response = await api.get('/api/gideon/config')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  icarusEquityCurve: async (days: number = 30) => {
    try {
      const response = await api.get(`/api/gideon/equity-curve?days=${days}`)
      return response.data
    } catch {
      return { success: false, data: { equity_curve: [] } }
    }
  },
  icarusIntradayEquity: async (date?: string) => {
    try {
      const params = date ? `?date=${date}` : ''
      const response = await api.get(`/api/gideon/equity-curve/intraday${params}`)
      return response.data
    } catch {
      return { success: false, data: { intraday_curve: [] } }
    }
  },
  icarusScanActivity: async (limit?: number, date?: string) => {
    try {
      const params = new URLSearchParams()
      params.append('limit', String(limit || 50))
      if (date) params.append('date', date)
      // Use GIDEON-specific scan activity endpoint
      const response = await api.get(`/api/gideon/scan-activity?${params}`)
      return response.data
    } catch {
      return { success: false, data: { scans: [] } }
    }
  },

  aresLivePnL: async () => {
    try {
      const response = await api.get('/api/fortress/live-pnl')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  aresLogs: async (level?: string, limit: number = 100) => {
    try {
      const response = await api.get('/api/fortress/logs', { params: { level, limit } })
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
      const response = await api.get(`/api/scans/activity/FORTRESS?${params}`)
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
      const response = await api.get(`/api/scans/activity/SOLOMON?${params}`)
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

  // LAZARUS Trader
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

  // ANCHOR SPX Iron Condor Bot
  anchorStatus: async () => {
    try {
      const response = await api.get('/api/anchor/status')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  anchorPositions: async () => {
    try {
      const response = await api.get('/api/anchor/positions')
      return response.data
    } catch {
      return { success: false, data: { open_positions: [], closed_positions: [] } }
    }
  },
  anchorEquityCurve: async (days: number = 30) => {
    try {
      const response = await api.get(`/api/anchor/equity-curve?days=${days}`)
      return response.data
    } catch {
      return { success: false, data: { equity_curve: [] } }
    }
  },
  anchorIntradayEquity: async (date?: string) => {
    try {
      const params = date ? `?date=${date}` : ''
      const response = await api.get(`/api/anchor/equity-curve/intraday${params}`)
      return response.data
    } catch {
      return { success: false, data: { intraday_curve: [] } }
    }
  },
  anchorConfig: async () => {
    try {
      const response = await api.get('/api/anchor/config')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  anchorLivePnL: async () => {
    try {
      const response = await api.get('/api/anchor/live-pnl')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  scanActivityAnchor: async (limit?: number, date?: string) => {
    try {
      const params = new URLSearchParams()
      params.append('limit', String(limit || 50))
      if (date) params.append('date', date)
      const response = await api.get(`/api/scans/activity/ANCHOR?${params}`)
      return response.data
    } catch {
      return { success: false, data: { scans: [] } }
    }
  },

  // SAMSON Aggressive SPX Iron Condor Bot (Daily Trading)
  titanStatus: async () => {
    try {
      const response = await api.get('/api/samson/status')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  titanPositions: async () => {
    try {
      const response = await api.get('/api/samson/positions')
      return response.data
    } catch {
      return { success: false, data: { open_positions: [], closed_positions: [] } }
    }
  },
  titanEquityCurve: async (days: number = 30) => {
    try {
      const response = await api.get(`/api/samson/equity-curve?days=${days}`)
      return response.data
    } catch {
      return { success: false, data: { equity_curve: [] } }
    }
  },
  titanIntradayEquity: async (date?: string) => {
    try {
      const params = date ? `?date=${date}` : ''
      const response = await api.get(`/api/samson/equity-curve/intraday${params}`)
      return response.data
    } catch {
      return { success: false, data: { intraday_curve: [] } }
    }
  },
  titanConfig: async () => {
    try {
      const response = await api.get('/api/samson/config')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  titanLivePnL: async () => {
    try {
      const response = await api.get('/api/samson/live-pnl')
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
      const response = await api.get(`/api/scans/activity/SAMSON?${params}`)
      return response.data
    } catch {
      return { success: false, data: { scans: [] } }
    }
  },

  // VALOR MES Futures Scalping Bot
  // Note: Fetchers throw errors instead of returning fallback values
  // This allows SWR to properly handle retries and error states
  heraclesStatus: async () => {
    const response = await api.get('/api/valor/status')
    return response.data
  },
  heraclesPositions: async () => {
    const response = await api.get('/api/valor/positions')
    return response.data
  },
  heraclesClosedTrades: async (limit: number = 50) => {
    const response = await api.get(`/api/valor/closed-trades?limit=${limit}`)
    return response.data
  },
  heraclesEquityCurve: async (days: number = 30) => {
    const response = await api.get(`/api/valor/paper-equity-curve?days=${days}`)
    return response.data
  },
  heraclesIntradayEquity: async () => {
    const response = await api.get('/api/valor/equity-curve/intraday')
    return response.data
  },
  heraclesConfig: async () => {
    const response = await api.get('/api/valor/config')
    return response.data
  },
  heraclesPaperAccount: async () => {
    const response = await api.get('/api/valor/paper-account')
    return response.data
  },
  heraclesScanActivity: async (limit?: number, outcome?: string) => {
    const params = new URLSearchParams()
    params.append('limit', String(limit || 100))
    if (outcome) params.append('outcome', outcome)
    const response = await api.get(`/api/valor/scan-activity?${params}`)
    return response.data
  },
  heraclesMLTrainingData: async () => {
    const response = await api.get('/api/valor/ml-training-data')
    return response.data
  },
  heraclesMLTrainingDataStats: async () => {
    const response = await api.get('/api/valor/ml/training-data-stats')
    return response.data
  },
  heraclesSignals: async (limit: number = 50) => {
    const response = await api.get(`/api/valor/signals/recent?limit=${limit}`)
    return response.data
  },
  heraclesMLStatus: async () => {
    const response = await api.get('/api/valor/ml/status')
    return response.data
  },
  heraclesMLTrain: async (minSamples: number = 50) => {
    try {
      const response = await api.post(`/api/valor/ml/train?min_samples=${minSamples}`)
      return response.data
    } catch (error: any) {
      return { success: false, error: error?.message || 'Training failed' }
    }
  },
  heraclesMLFeatureImportance: async () => {
    const response = await api.get('/api/valor/ml/feature-importance')
    return response.data
  },
  heraclesMLApprovalStatus: async () => {
    const response = await api.get('/api/valor/ml/approval-status')
    return response.data
  },
  heraclesMLApprove: async () => {
    try {
      const response = await api.post('/api/valor/ml/approve')
      return response.data
    } catch (error: any) {
      return { success: false, error: error?.message || 'Approval failed' }
    }
  },
  heraclesMLRevoke: async () => {
    try {
      const response = await api.post('/api/valor/ml/revoke')
      return response.data
    } catch (error: any) {
      return { success: false, error: error?.message || 'Revoke failed' }
    }
  },
  heraclesMLReject: async () => {
    try {
      const response = await api.post('/api/valor/ml/reject')
      return response.data
    } catch (error: any) {
      return { success: false, error: error?.message || 'Reject failed' }
    }
  },
  heraclesABTestStatus: async () => {
    const response = await api.get('/api/valor/ab-test/status')
    return response.data
  },
  heraclesABTestEnable: async () => {
    try {
      const response = await api.post('/api/valor/ab-test/enable')
      return response.data
    } catch (error: any) {
      return { success: false, error: error?.message || 'Failed to enable A/B test' }
    }
  },
  heraclesABTestDisable: async () => {
    try {
      const response = await api.post('/api/valor/ab-test/disable')
      return response.data
    } catch (error: any) {
      return { success: false, error: error?.message || 'Failed to disable A/B test' }
    }
  },
  heraclesABTestResults: async () => {
    const response = await api.get('/api/valor/ab-test/results')
    return response.data
  },

  // JUBILEE Box Spread Synthetic Borrowing + IC Trading Bot
  prometheusStatus: async () => {
    try {
      const response = await api.get('/api/jubilee/status')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  prometheusICStatus: async () => {
    try {
      const response = await api.get('/api/jubilee/ic/status')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  prometheusPositions: async () => {
    try {
      const response = await api.get('/api/jubilee/positions')
      return response.data
    } catch {
      return { success: false, data: { positions: [] } }
    }
  },
  prometheusICPositions: async () => {
    try {
      const response = await api.get('/api/jubilee/ic/positions')
      return response.data
    } catch {
      return { success: false, data: { positions: [] } }
    }
  },
  prometheusLivePnL: async () => {
    try {
      const response = await api.get('/api/jubilee/combined/performance')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },
  prometheusReconciliation: async () => {
    try {
      const response = await api.get('/api/jubilee/reconciliation')
      return response.data
    } catch {
      return { success: false, data: null }
    }
  },

  // AGAPE ETH Micro Futures Bot
  agapeStatus: async () => {
    const response = await api.get('/api/agape/status')
    return response.data
  },
  agapePositions: async () => {
    const response = await api.get('/api/agape/positions')
    return response.data
  },
  agapeClosedTrades: async (limit: number = 50) => {
    const response = await api.get(`/api/agape/closed-trades?limit=${limit}`)
    return response.data
  },
  agapeEquityCurve: async (days: number = 30) => {
    const response = await api.get(`/api/agape/equity-curve?days=${days}`)
    return response.data
  },
  agapeIntradayEquity: async () => {
    const response = await api.get('/api/agape/equity-curve/intraday')
    return response.data
  },
  agapePerformance: async () => {
    const response = await api.get('/api/agape/performance')
    return response.data
  },
  agapeScanActivity: async (limit: number = 30) => {
    const response = await api.get(`/api/agape/scan-activity?limit=${limit}`)
    return response.data
  },
  agapeSnapshot: async () => {
    const response = await api.get('/api/agape/snapshot')
    return response.data
  },
  agapeGexMapping: async () => {
    const response = await api.get('/api/agape/gex-mapping')
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
// FORTRESS BOT HOOKS
// =============================================================================

export function useARESStatus(options?: SWRConfiguration) {
  return useSWR('fortress-status', fetchers.aresStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useARESPerformance(options?: SWRConfiguration) {
  return useSWR('fortress-performance', fetchers.aresPerformance, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useARESPositions(options?: SWRConfiguration) {
  return useSWR('fortress-positions', fetchers.aresPositions, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useARESMarketData(options?: SWRConfiguration) {
  return useSWR('fortress-market-data', fetchers.aresMarketData, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useARESDecisions(limit: number = 50, options?: SWRConfiguration) {
  return useSWR(
    `fortress-decisions-${limit}`,
    () => fetchers.aresDecisions(limit),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useARESEquityCurve(days: number = 30, options?: SWRConfiguration) {
  return useSWR(
    `fortress-equity-curve-${days}`,
    () => fetchers.aresEquityCurve(days),
    { ...swrConfig, refreshInterval: 5 * 60 * 1000, ...options }
  )
}

export function useARESIntradayEquity(date?: string, options?: SWRConfiguration) {
  return useSWR(
    `fortress-intraday-equity-${date || 'today'}`,
    () => fetchers.aresIntradayEquity(date),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useARESTradierStatus(options?: SWRConfiguration) {
  return useSWR('fortress-tradier-status', fetchers.aresTradierStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useFortressConfig(options?: SWRConfiguration) {
  return useSWR('fortress-config', fetchers.aresConfig, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,
    ...options,
  })
}

export function useARESStrategyPresets(options?: SWRConfiguration) {
  return useSWR('fortress-strategy-presets', fetchers.aresStrategyPresets, {
    ...swrConfig,
    refreshInterval: 60 * 1000, // Refresh every minute
    ...options,
  })
}

// =============================================================================
// SOLOMON BOT HOOKS
// =============================================================================

export function useATHENAStatus(options?: SWRConfiguration) {
  return useSWR('solomon-status', fetchers.solomonStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useATHENAPositions(options?: SWRConfiguration) {
  return useSWR('solomon-positions', fetchers.solomonPositions, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useSolomonSignals(limit: number = 50, options?: SWRConfiguration) {
  return useSWR(
    `solomon-signals-${limit}`,
    () => fetchers.solomonSignals(limit),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useATHENAPerformance(days: number = 30, options?: SWRConfiguration) {
  return useSWR(
    `solomon-performance-${days}`,
    () => fetchers.solomonPerformance(days),
    { ...swrConfig, refreshInterval: 5 * 60 * 1000, ...options }
  )
}

export function useATHENAOracleAdvice(options?: SWRConfiguration) {
  return useSWR('solomon-oracle-advice', fetchers.solomonOracleAdvice, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useATHENAMLSignal(options?: SWRConfiguration) {
  return useSWR('solomon-ml-signal', fetchers.solomonMLSignal, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useATHENALogs(level?: string, limit: number = 50, options?: SWRConfiguration) {
  return useSWR(
    `solomon-logs-${level || 'all'}-${limit}`,
    () => fetchers.solomonLogs(level, limit),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

export function useATHENADecisions(limit: number = 100, options?: SWRConfiguration) {
  return useSWR(
    `solomon-decisions-${limit}`,
    () => fetchers.solomonDecisions(limit),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

export function useATHENALivePnL(options?: SWRConfiguration) {
  return useSWR(
    'solomon-live-pnl',
    fetchers.solomonLivePnL,
    { ...swrConfig, refreshInterval: 10 * 1000, ...options }  // 10 second refresh for live data
  )
}

export function useSolomonConfig(options?: SWRConfiguration) {
  return useSWR('solomon-config', fetchers.solomonConfig, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,  // 5 minute refresh for config
    ...options,
  })
}

export function useATHENAEquityCurve(days: number = 30, options?: SWRConfiguration) {
  return useSWR(
    `solomon-equity-curve-${days}`,
    () => fetchers.solomonEquityCurve(days),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useATHENAIntradayEquity(date?: string, options?: SWRConfiguration) {
  return useSWR(
    `solomon-intraday-equity-${date || 'today'}`,
    () => fetchers.solomonIntradayEquity(date),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useARESLivePnL(options?: SWRConfiguration) {
  return useSWR(
    'fortress-live-pnl',
    fetchers.aresLivePnL,
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }  // 30 second refresh to match other bots
  )
}

export function useARESLogs(level?: string, limit: number = 100, options?: SWRConfiguration) {
  return useSWR(
    `fortress-logs-${level || 'all'}-${limit}`,
    () => fetchers.aresLogs(level, limit),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

// =============================================================================
// GIDEON BOT HOOKS - Aggressive Directional Spreads
// =============================================================================

export function useICARUSStatus(options?: SWRConfiguration) {
  return useSWR('gideon-status', fetchers.icarusStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useICARUSPositions(options?: SWRConfiguration) {
  return useSWR('gideon-positions', fetchers.icarusPositions, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useICARUSSignals(limit: number = 50, options?: SWRConfiguration) {
  return useSWR(
    `gideon-signals-${limit}`,
    () => fetchers.icarusSignals(limit),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useICARUSPerformance(days: number = 30, options?: SWRConfiguration) {
  return useSWR(
    `gideon-performance-${days}`,
    () => fetchers.icarusPerformance(days),
    { ...swrConfig, refreshInterval: 5 * 60 * 1000, ...options }
  )
}

export function useICARUSOracleAdvice(options?: SWRConfiguration) {
  return useSWR('gideon-oracle-advice', fetchers.icarusOracleAdvice, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useICARUSLogs(level?: string, limit: number = 50, options?: SWRConfiguration) {
  return useSWR(
    `gideon-logs-${level || 'all'}-${limit}`,
    () => fetchers.icarusLogs(level, limit),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

export function useICARUSLivePnL(options?: SWRConfiguration) {
  return useSWR(
    'gideon-live-pnl',
    fetchers.icarusLivePnL,
    { ...swrConfig, refreshInterval: 10 * 1000, ...options }  // 10 second refresh for live data
  )
}

export function useGideonConfig(options?: SWRConfiguration) {
  return useSWR('gideon-config', fetchers.icarusConfig, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,  // 5 minute refresh for config
    ...options,
  })
}

export function useICARUSEquityCurve(days: number = 30, options?: SWRConfiguration) {
  return useSWR(
    `gideon-equity-curve-${days}`,
    () => fetchers.icarusEquityCurve(days),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useICARUSIntradayEquity(date?: string, options?: SWRConfiguration) {
  return useSWR(
    `gideon-intraday-equity-${date || 'today'}`,
    () => fetchers.icarusIntradayEquity(date),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useICARUSScanActivity(limit: number = 50, date?: string, options?: SWRConfiguration) {
  return useSWR(
    `gideon-scan-activity-${limit}-${date || 'all'}`,
    () => fetchers.icarusScanActivity(limit, date),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

// =============================================================================
// SCAN ACTIVITY HOOKS - Every scan with full reasoning
// =============================================================================

export function useScanActivityAres(limit: number = 50, date?: string, options?: SWRConfiguration) {
  return useSWR(
    `scan-activity-fortress-${limit}-${date || 'all'}`,
    () => fetchers.scanActivityAres(limit, date),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

export function useScanActivityAthena(limit: number = 50, date?: string, options?: SWRConfiguration) {
  return useSWR(
    `scan-activity-solomon-${limit}-${date || 'all'}`,
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
// ANCHOR SPX IRON CONDOR HOOKS
// =============================================================================

export function useANCHORStatus(options?: SWRConfiguration) {
  return useSWR('anchor-status', fetchers.anchorStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useANCHORPositions(options?: SWRConfiguration) {
  return useSWR('anchor-positions', fetchers.anchorPositions, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useANCHOREquityCurve(days: number = 30, options?: SWRConfiguration) {
  return useSWR(
    `anchor-equity-curve-${days}`,
    () => fetchers.anchorEquityCurve(days),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useANCHORIntradayEquity(date?: string, options?: SWRConfiguration) {
  return useSWR(
    `anchor-intraday-equity-${date || 'today'}`,
    () => fetchers.anchorIntradayEquity(date),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useAnchorConfig(options?: SWRConfiguration) {
  return useSWR('anchor-config', fetchers.anchorConfig, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,
    ...options,
  })
}

export function useANCHORLivePnL(options?: SWRConfiguration) {
  return useSWR('anchor-live-pnl', fetchers.anchorLivePnL, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useScanActivityAnchor(limit: number = 50, date?: string, options?: SWRConfiguration) {
  return useSWR(
    `scan-activity-anchor-${limit}-${date || 'all'}`,
    () => fetchers.scanActivityAnchor(limit, date),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

// =============================================================================
// SAMSON AGGRESSIVE SPX IRON CONDOR HOOKS (Daily Trading)
// =============================================================================

export function useTITANStatus(options?: SWRConfiguration) {
  return useSWR('samson-status', fetchers.titanStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useTITANPositions(options?: SWRConfiguration) {
  return useSWR('samson-positions', fetchers.titanPositions, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useTITANEquityCurve(days: number = 30, options?: SWRConfiguration) {
  return useSWR(
    `samson-equity-curve-${days}`,
    () => fetchers.titanEquityCurve(days),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useTITANIntradayEquity(date?: string, options?: SWRConfiguration) {
  return useSWR(
    `samson-intraday-equity-${date || 'today'}`,
    () => fetchers.titanIntradayEquity(date),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useSamsonConfig(options?: SWRConfiguration) {
  return useSWR('samson-config', fetchers.titanConfig, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,
    ...options,
  })
}

export function useTITANLivePnL(options?: SWRConfiguration) {
  return useSWR('samson-live-pnl', fetchers.titanLivePnL, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useScanActivityTitan(limit: number = 50, date?: string, options?: SWRConfiguration) {
  return useSWR(
    `scan-activity-samson-${limit}-${date || 'all'}`,
    () => fetchers.scanActivityTitan(limit, date),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

// =============================================================================
// VALOR MES FUTURES SCALPING HOOKS
// =============================================================================

export function useHERACLESStatus(options?: SWRConfiguration) {
  return useSWR('valor-status', fetchers.heraclesStatus, {
    ...swrConfig,
    refreshInterval: 15 * 1000,  // 15 seconds for real-time position updates
    dedupingInterval: 5000,      // Allow refreshes within 5 seconds
    keepPreviousData: false,     // Don't show stale data - show loading state instead
    ...options,
  })
}

export function useHERACLESPositions(options?: SWRConfiguration) {
  return useSWR('valor-positions', fetchers.heraclesPositions, {
    ...swrConfig,
    dedupingInterval: 5000,
    keepPreviousData: false,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useHERACLESClosedTrades(limit: number = 50, options?: SWRConfiguration) {
  return useSWR(
    `valor-closed-trades-${limit}`,
    () => fetchers.heraclesClosedTrades(limit),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useHERACLESEquityCurve(days: number = 30, options?: SWRConfiguration) {
  return useSWR(
    `valor-equity-curve-${days}`,
    () => fetchers.heraclesEquityCurve(days),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useHERACLESIntradayEquity(options?: SWRConfiguration) {
  return useSWR('valor-intraday-equity', fetchers.heraclesIntradayEquity, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useValorConfig(options?: SWRConfiguration) {
  return useSWR('valor-config', fetchers.heraclesConfig, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,
    ...options,
  })
}

export function useHERACLESPaperAccount(options?: SWRConfiguration) {
  return useSWR('valor-paper-account', fetchers.heraclesPaperAccount, {
    ...swrConfig,
    refreshInterval: 15 * 1000,  // 15 seconds for real-time balance updates
    dedupingInterval: 5000,
    keepPreviousData: false,
    ...options,
  })
}

export function useHERACLESScanActivity(limit: number = 100, outcome?: string, options?: SWRConfiguration) {
  return useSWR(
    `valor-scan-activity-${limit}-${outcome || 'all'}`,
    () => fetchers.heraclesScanActivity(limit, outcome),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

export function useHERACLESMLTrainingData(options?: SWRConfiguration) {
  return useSWR('valor-ml-training-data', fetchers.heraclesMLTrainingData, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,  // Refresh every 5 minutes
    ...options,
  })
}

export function useHERACLESMLTrainingDataStats(options?: SWRConfiguration) {
  return useSWR('valor-ml-training-data-stats', fetchers.heraclesMLTrainingDataStats, {
    ...swrConfig,
    refreshInterval: 60 * 1000,  // Refresh every minute
    ...options,
  })
}

export function useHERACLESSignals(limit: number = 50, options?: SWRConfiguration) {
  return useSWR(
    `valor-signals-${limit}`,
    () => fetchers.heraclesSignals(limit),
    { ...swrConfig, refreshInterval: 30 * 1000, ...options }
  )
}

export function useHERACLESMLStatus(options?: SWRConfiguration) {
  return useSWR('valor-ml-status', fetchers.heraclesMLStatus, {
    ...swrConfig,
    refreshInterval: 60 * 1000,  // Refresh every minute
    ...options,
  })
}

export function useHERACLESMLFeatureImportance(options?: SWRConfiguration) {
  return useSWR('valor-ml-feature-importance', fetchers.heraclesMLFeatureImportance, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,  // Refresh every 5 minutes
    ...options,
  })
}

// Training function (not a hook - called imperatively)
export async function trainHERACLESML(minSamples: number = 50) {
  return fetchers.heraclesMLTrain(minSamples)
}

// ML Approval hooks and functions
export function useHERACLESMLApprovalStatus(options?: SWRConfiguration) {
  return useSWR('valor-ml-approval-status', fetchers.heraclesMLApprovalStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,  // Refresh every 30 seconds
    ...options,
  })
}

export async function approveHERACLESML() {
  return fetchers.heraclesMLApprove()
}

export async function revokeHERACLESML() {
  return fetchers.heraclesMLRevoke()
}

export async function rejectHERACLESML() {
  return fetchers.heraclesMLReject()
}

// A/B Test hooks and functions
export function useHERACLESABTestStatus(options?: SWRConfiguration) {
  return useSWR('valor-ab-test-status', fetchers.heraclesABTestStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useHERACLESABTestResults(options?: SWRConfiguration) {
  return useSWR('valor-ab-test-results', fetchers.heraclesABTestResults, {
    ...swrConfig,
    refreshInterval: 60 * 1000,  // Refresh every minute
    ...options,
  })
}

export async function enableHERACLESABTest() {
  return fetchers.heraclesABTestEnable()
}

export async function disableHERACLESABTest() {
  return fetchers.heraclesABTestDisable()
}

// =============================================================================
// JUBILEE BOX SPREAD + IC TRADING HOOKS
// =============================================================================

export function usePROMETHEUSStatus(options?: SWRConfiguration) {
  return useSWR('jubilee-status', fetchers.prometheusStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function usePROMETHEUSICStatus(options?: SWRConfiguration) {
  return useSWR('jubilee-ic-status', fetchers.prometheusICStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function usePROMETHEUSPositions(options?: SWRConfiguration) {
  return useSWR('jubilee-positions', fetchers.prometheusPositions, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function usePROMETHEUSICPositions(options?: SWRConfiguration) {
  return useSWR('jubilee-ic-positions', fetchers.prometheusICPositions, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function usePROMETHEUSLivePnL(options?: SWRConfiguration) {
  return useSWR('jubilee-live-pnl', fetchers.prometheusLivePnL, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function usePROMETHEUSReconciliation(options?: SWRConfiguration) {
  return useSWR('jubilee-reconciliation', fetchers.prometheusReconciliation, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

// =============================================================================
// AGAPE ETH MICRO FUTURES HOOKS
// =============================================================================

export function useAGAPEStatus(options?: SWRConfiguration) {
  return useSWR('agape-status', fetchers.agapeStatus, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useAGAPEPositions(options?: SWRConfiguration) {
  return useSWR('agape-positions', fetchers.agapePositions, {
    ...swrConfig,
    refreshInterval: 15 * 1000,
    ...options,
  })
}

export function useAGAPEClosedTrades(limit: number = 50, options?: SWRConfiguration) {
  return useSWR(
    `agape-closed-trades-${limit}`,
    () => fetchers.agapeClosedTrades(limit),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useAGAPEEquityCurve(days: number = 30, options?: SWRConfiguration) {
  return useSWR(
    `agape-equity-curve-${days}`,
    () => fetchers.agapeEquityCurve(days),
    { ...swrConfig, refreshInterval: 60 * 1000, ...options }
  )
}

export function useAGAPEIntradayEquity(options?: SWRConfiguration) {
  return useSWR('agape-intraday-equity', fetchers.agapeIntradayEquity, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useAGAPEPerformance(options?: SWRConfiguration) {
  return useSWR('agape-performance', fetchers.agapePerformance, {
    ...swrConfig,
    refreshInterval: 60 * 1000,
    ...options,
  })
}

export function useAGAPEScanActivity(limit: number = 30, options?: SWRConfiguration) {
  return useSWR(
    `agape-scan-activity-${limit}`,
    () => fetchers.agapeScanActivity(limit),
    { ...swrConfig, refreshInterval: 15 * 1000, ...options }
  )
}

export function useAGAPESnapshot(options?: SWRConfiguration) {
  return useSWR('agape-snapshot', fetchers.agapeSnapshot, {
    ...swrConfig,
    refreshInterval: 30 * 1000,
    ...options,
  })
}

export function useAGAPEGexMapping(options?: SWRConfiguration) {
  return useSWR('agape-gex-mapping', fetchers.agapeGexMapping, {
    ...swrConfig,
    refreshInterval: 5 * 60 * 1000,
    ...options,
  })
}

// =============================================================================
// LAZARUS TRADER HOOKS
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
// UNIFIED BOT METRICS HOOKS - Single Source of Truth
// These hooks provide consistent, authoritative data for all trading bots.
// Frontend should NEVER calculate stats locally - always use these hooks.
// =============================================================================

// Type definitions for unified metrics
export interface BotCapitalConfig {
  bot_name: string
  starting_capital: number
  capital_source: 'database' | 'tradier' | 'default'
  tradier_connected: boolean
  tradier_balance: number | null
  last_updated: string
}

export interface BotMetricsSummary {
  bot_name: string
  starting_capital: number
  current_equity: number
  capital_source: string
  total_realized_pnl: number
  total_unrealized_pnl: number
  total_pnl: number
  today_realized_pnl: number
  today_unrealized_pnl: number
  today_pnl: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number  // 0-100 percentage, NOT decimal
  open_positions: number
  closed_positions: number
  total_return_pct: number
  max_drawdown_pct: number
  high_water_mark: number
  calculated_at: string
}

export interface UnifiedEquityCurvePoint {
  date: string
  equity: number
  daily_pnl: number
  cumulative_pnl: number
  realized_pnl: number
  unrealized_pnl: number
  drawdown_pct: number
  trade_count: number
  return_pct: number
}

export interface UnifiedIntradayPoint {
  timestamp: string
  time: string
  equity: number
  cumulative_pnl: number
  realized_pnl: number
  unrealized_pnl: number
  open_positions: number
}

// Unified metrics fetchers
const unifiedMetricsFetchers = {
  summary: async (bot: string) => {
    const response = await api.get(`/api/metrics/${bot.toLowerCase()}/summary`)
    return response.data
  },
  capital: async (bot: string) => {
    const response = await api.get(`/api/metrics/${bot.toLowerCase()}/capital`)
    return response.data
  },
  equityCurve: async (bot: string, days: number = 90) => {
    const response = await api.get(`/api/metrics/${bot.toLowerCase()}/equity-curve?days=${days}`)
    return response.data
  },
  intradayEquity: async (bot: string, date?: string) => {
    const url = date
      ? `/api/metrics/${bot.toLowerCase()}/equity-curve/intraday?date=${date}`
      : `/api/metrics/${bot.toLowerCase()}/equity-curve/intraday`
    const response = await api.get(url)
    return response.data
  },
  reconcile: async (bot: string) => {
    const response = await api.get(`/api/metrics/${bot.toLowerCase()}/reconcile`)
    return response.data
  },
  allSummaries: async () => {
    const response = await api.get('/api/metrics/all/summary')
    return response.data
  },
  allCapital: async () => {
    const response = await api.get('/api/metrics/all/capital')
    return response.data
  },
  allReconcile: async () => {
    const response = await api.get('/api/metrics/all/reconcile')
    return response.data
  },
}

/**
 * Get unified metrics summary for a bot.
 * This is THE authoritative source for bot statistics.
 *
 * Data includes:
 * - starting_capital: Authoritative starting capital (from database/Tradier/default)
 * - current_equity: starting_capital + total_pnl
 * - win_rate: Percentage (0-100), NOT decimal
 * - All values come from database aggregates, never frontend calculations
 */
export function useUnifiedBotSummary(bot: string, options?: SWRConfiguration) {
  return useSWR<{ success: boolean; data: BotMetricsSummary }>(
    `unified-metrics-summary-${bot.toLowerCase()}`,
    () => unifiedMetricsFetchers.summary(bot),
    {
      ...swrConfig,
      refreshInterval: 30 * 1000, // 30 seconds
      ...options,
    }
  )
}

/**
 * Get capital configuration for a bot.
 * This is THE source of truth for starting capital.
 * Both historical and intraday charts use this same value.
 */
export function useUnifiedBotCapital(bot: string, options?: SWRConfiguration) {
  return useSWR<{ success: boolean; data: BotCapitalConfig }>(
    `unified-metrics-capital-${bot.toLowerCase()}`,
    () => unifiedMetricsFetchers.capital(bot),
    {
      ...swrConfig,
      refreshInterval: 60 * 1000, // 1 minute
      ...options,
    }
  )
}

/**
 * Get historical equity curve for a bot.
 * Uses the SAME starting capital as intraday endpoint.
 */
export function useUnifiedEquityCurve(bot: string, days: number = 90, options?: SWRConfiguration) {
  return useSWR(
    `unified-equity-curve-${bot.toLowerCase()}-${days}`,
    () => unifiedMetricsFetchers.equityCurve(bot, days),
    {
      ...swrConfig,
      refreshInterval: 60 * 1000, // 1 minute
      ...options,
    }
  )
}

/**
 * Get intraday equity curve for a bot.
 * Uses the SAME starting capital as historical endpoint.
 */
export function useUnifiedIntradayEquity(bot: string, date?: string, options?: SWRConfiguration) {
  return useSWR(
    `unified-intraday-equity-${bot.toLowerCase()}-${date || 'today'}`,
    () => unifiedMetricsFetchers.intradayEquity(bot, date),
    {
      ...swrConfig,
      refreshInterval: 60 * 1000, // 1 minute
      ...options,
    }
  )
}

/**
 * Check data consistency for a bot.
 * Returns list of any discrepancies found.
 */
export function useUnifiedReconcile(bot: string, options?: SWRConfiguration) {
  return useSWR(
    `unified-reconcile-${bot.toLowerCase()}`,
    () => unifiedMetricsFetchers.reconcile(bot),
    {
      ...swrConfig,
      refreshInterval: 5 * 60 * 1000, // 5 minutes
      ...options,
    }
  )
}

/**
 * Get metrics summaries for ALL bots at once.
 * Useful for dashboard overview.
 */
export function useAllBotsSummary(options?: SWRConfiguration) {
  return useSWR(
    'unified-all-bots-summary',
    unifiedMetricsFetchers.allSummaries,
    {
      ...swrConfig,
      refreshInterval: 30 * 1000, // 30 seconds
      ...options,
    }
  )
}

/**
 * Get capital configurations for ALL bots at once.
 * Useful for admin/config overview.
 */
export function useAllBotsCapital(options?: SWRConfiguration) {
  return useSWR(
    'unified-all-bots-capital',
    unifiedMetricsFetchers.allCapital,
    {
      ...swrConfig,
      refreshInterval: 60 * 1000, // 1 minute
      ...options,
    }
  )
}

/**
 * Run reconciliation check on ALL bots.
 * Returns summary of data consistency.
 */
export function useAllBotsReconcile(options?: SWRConfiguration) {
  return useSWR(
    'unified-all-bots-reconcile',
    unifiedMetricsFetchers.allReconcile,
    {
      ...swrConfig,
      refreshInterval: 5 * 60 * 1000, // 5 minutes
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
  aresStatus: () => preload('fortress-status', fetchers.aresStatus),
  solomonStatus: () => preload('solomon-status', fetchers.solomonStatus),
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
    prefetchMarketData.solomonStatus()
    prefetchMarketData.traderStatus()
  },
}
