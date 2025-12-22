import axios, { AxiosError } from 'axios'
import { logger } from '@/lib/logger'

// IMPORTANT: In production, NEXT_PUBLIC_API_URL must be set.
// No localhost fallback to prevent accidental local connections in production.
const API_URL = process.env.NEXT_PUBLIC_API_URL
if (!API_URL) {
  console.warn('[API] NEXT_PUBLIC_API_URL not set. API calls will fail in production.')
}

// ==================== API RESPONSE TYPES ====================

export interface APIResponse<T = any> {
  success: boolean
  data?: T
  message?: string
  error?: string
}

export interface GEXData {
  symbol: string
  net_gex: number
  call_gex: number
  put_gex: number
  flip_point: number
  spot_price: number
  timestamp: string
  data_source?: string
}

export interface TraderPerformance {
  starting_capital: number
  current_equity: number
  total_pnl: number
  total_return_pct: number
  win_rate: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  max_drawdown_pct: number
  sharpe_ratio: number
}

export interface Position {
  id: string
  symbol: string
  side: 'long' | 'short'
  quantity: number
  entry_price: number
  current_price: number
  unrealized_pnl: number
  entry_time: string
}

export interface Trade {
  id: string
  symbol: string
  side: string
  quantity: number
  entry_price: number
  exit_price: number
  pnl: number
  entry_time: string
  exit_time: string
  strategy: string
}

export interface WheelPhase {
  id: string
  name: string
  description: string
  next_if_otm?: string
  next_if_itm?: string
  cost_basis?: string
}

export interface BacktestResult {
  start_date: string
  end_date: string
  initial_capital: number
  final_equity: number
  total_return_pct: number
  total_trades: number
  win_rate: number
  max_drawdown_pct: number
  sharpe_ratio: number
}

// API error response structure
interface APIErrorResponse {
  detail?: string
  message?: string
  [key: string]: any
}

// Error type classification
interface EnhancedError extends Error {
  status?: number
  type: 'network' | 'server' | 'client' | 'timeout' | 'unknown'
  retryable: boolean
  originalError?: any
}

// Helper: Check if error is retryable
function isRetryableError(error: AxiosError<APIErrorResponse>): boolean {
  // Network errors (no response)
  if (!error.response) return true

  // Server errors (5xx)
  if (error.response.status >= 500) return true

  // Rate limiting (429)
  if (error.response.status === 429) return true

  // Timeout errors
  if (error.code === 'ECONNABORTED') return true

  return false
}

// Helper: Categorize error type
function categorizeError(error: AxiosError<APIErrorResponse>): EnhancedError['type'] {
  if (!error.response) return 'network'
  if (error.code === 'ECONNABORTED') return 'timeout'
  if (error.response.status >= 500) return 'server'
  if (error.response.status >= 400) return 'client'
  return 'unknown'
}

// Helper: Delay function for retries
const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

// Create axios instance with defaults
export const api = axios.create({
  baseURL: API_URL,
  timeout: 600000, // 10 minutes for scanner (with rate limiting, 18 symbols can take 6+ minutes)
  headers: {
    'Content-Type': 'application/json',
  },
})

// Response interceptor for enhanced error handling with retry logic
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<APIErrorResponse>) => {
    const config = error.config as any

    // Retry transient errors (network, 5xx, timeout)
    if (!config._retryCount && isRetryableError(error)) {
      config._retryCount = 1
      const retryDelay = 1000 // 1 second

      logger.warn(`API Error (retrying in ${retryDelay}ms):`, error.message)
      await delay(retryDelay)

      return api(config)
    }

    // Enhanced error info for final rejection
    const enhancedError: EnhancedError = {
      name: error.name,
      message: (error.response?.data as any)?.detail || error.message || 'Unknown error',
      status: error.response?.status,
      type: categorizeError(error),
      retryable: isRetryableError(error),
      originalError: error
    }

    logger.error('API Error:', {
      message: enhancedError.message,
      status: enhancedError.status,
      type: enhancedError.type,
      retryable: enhancedError.retryable
    })

    return Promise.reject(enhancedError)
  }
)

// API Methods
export const apiClient = {
  // Health & Status
  health: () => api.get('/health'),
  time: () => api.get('/api/time'),

  // GEX Data
  getGEX: (symbol: string) => api.get(`/api/gex/${symbol}`),
  getGEXLevels: (symbol: string) => api.get(`/api/gex/${symbol}/levels`),
  get0DTEGammaComparison: (symbol: string, forceRefresh: boolean = false) =>
    api.get(`/api/gex/compare/0dte/${symbol}`, { params: { force_refresh: forceRefresh } }),

  // Market Data
  getPriceHistory: (symbol: string, days: number = 90) => api.get(`/api/market/price-history/${symbol}`, { params: { days } }),

  // Gamma Intelligence
  getGammaIntelligence: (symbol: string, vix?: number) =>
    api.get(`/api/gamma/${symbol}/intelligence`, { params: { vix } }),
  getGammaHistory: (symbol: string, days?: number) =>
    api.get(`/api/gamma/${symbol}/history`, { params: { days } }),
  getGammaExpiration: (symbol: string) =>
    api.get(`/api/gamma/${symbol}/expiration-intel`),
  getGammaExpirationBasic: (symbol: string) =>
    api.get(`/api/gamma/${symbol}/expiration`),
  getGammaProbabilities: (symbol: string, vix?: number, accountSize?: number) =>
    api.get(`/api/gamma/${symbol}/probabilities`, { params: { vix, account_size: accountSize } }),
  getGammaExpirationWaterfall: (symbol: string) =>
    api.get(`/api/gamma/${symbol}/expiration-waterfall`),

  // AI Copilot
  analyzeMarket: (data: {
    symbol: string
    query: string
    market_data?: any
    gamma_intel?: any
  }) => api.post('/api/ai/analyze', data),

  // AI Copilot with Image Analysis
  analyzeWithImage: (data: {
    symbol: string
    query: string
    image_data: string  // Base64 encoded image or data URL
    market_data?: any
  }) => api.post('/api/ai/analyze-with-image', data),

  // GEXIS Chatbot - Session-based conversational AI
  gexisAnalyzeWithContext: (data: {
    query: string
    symbol?: string
    session_id: string
    market_data?: any
  }) => api.post('/api/ai/gexis/analyze-with-context', data),

  gexisCommand: (command: string) =>
    api.post('/api/ai/gexis/command', { command }),

  gexisAlerts: () => api.get('/api/ai/gexis/alerts'),

  gexisExportConversation: (sessionId: string, format: string = 'markdown') =>
    api.get(`/api/ai/gexis/export/${sessionId}`, { params: { format } }),

  // Autonomous Trader
  getTraderStatus: () => api.get('/api/trader/status'),
  getTraderLiveStatus: () => api.get('/api/trader/live-status'),
  getTraderPerformance: () => api.get('/api/trader/performance'),
  getTraderDiagnostics: () => api.get('/api/trader/diagnostics'),
  getTraderTrades: (limit: number = 10) => api.get('/api/trader/trades', { params: { limit } }),
  getOpenPositions: () => api.get('/api/trader/positions'),
  getClosedTrades: (limit: number = 50) => api.get('/api/trader/closed-trades', { params: { limit } }),
  getTradeLog: () => api.get('/api/trader/trade-log'),
  getEquityCurve: (days: number = 30) => api.get('/api/trader/equity-curve', { params: { days } }),
  getStrategies: () => api.get('/api/trader/strategies'),
  getStrategyConfigs: () => api.get('/api/trader/strategies/config'),
  toggleStrategy: (strategyId: string, enabled: boolean) =>
    api.post(`/api/trader/strategies/${strategyId}/toggle`, null, { params: { enabled } }),
  compareStrategies: (symbol: string = 'SPY') => api.get('/api/strategies/compare', { params: { symbol } }),
  executeTraderCycle: () => api.post('/api/trader/execute'),

  // Trader System Controls
  getSystemTraderStatus: () => api.get('/api/system/trader-status'),
  startTrader: () => api.post('/api/system/start-trader'),
  stopTrader: () => api.post('/api/system/stop-trader'),
  enableTraderAutostart: () => api.post('/api/system/enable-autostart'),
  disableTraderAutostart: () => api.post('/api/system/disable-autostart'),

  // Autonomous Trader - Advanced Features
  getAutonomousLogs: (params?: { limit?: number, log_type?: string, session_id?: string, symbol?: string }) =>
    api.get('/api/autonomous/logs', { params }),
  getLogSessions: (limit: number = 10) => api.get('/api/autonomous/logs/sessions', { params: { limit } }),
  getCompetitionLeaderboard: () => api.get('/api/autonomous/competition/leaderboard'),
  getStrategyPerformance: (strategyId: string) => api.get(`/api/autonomous/competition/strategy/${strategyId}`),
  getCompetitionSummary: () => api.get('/api/autonomous/competition/summary'),
  getAllPatternBacktests: (lookbackDays: number = 90, save: boolean = false) =>
    api.get('/api/autonomous/backtests/all-patterns', { params: { lookback_days: lookbackDays, save } }),
  runAndSaveBacktests: (lookbackDays: number = 90) =>
    api.post('/api/autonomous/backtests/run-and-save', {}, { params: { lookback_days: lookbackDays } }),
  getPatternBacktest: (patternName: string, lookbackDays: number = 90) =>
    api.get(`/api/autonomous/backtests/pattern/${patternName}`, { params: { lookback_days: lookbackDays } }),
  getLiberationAccuracy: (lookbackDays: number = 90) =>
    api.get('/api/autonomous/backtests/liberation-accuracy', { params: { lookback_days: lookbackDays } }),
  getFalseFloorEffectiveness: (lookbackDays: number = 90) =>
    api.get('/api/autonomous/backtests/false-floor-effectiveness', { params: { lookback_days: lookbackDays } }),
  getRiskStatus: () => api.get('/api/autonomous/risk/status'),
  getRiskMetrics: (days: number = 30) => api.get('/api/autonomous/risk/metrics', { params: { days } }),
  getMLModelStatus: () => api.get('/api/autonomous/ml/model-status'),
  trainMLModel: (lookbackDays: number = 180) =>
    api.post('/api/autonomous/ml/train', {}, { params: { lookback_days: lookbackDays } }),
  getRecentMLPredictions: (limit: number = 20) =>
    api.get('/api/autonomous/ml/predictions/recent', { params: { limit } }),
  initializeAutonomousSystem: () => api.post('/api/autonomous/initialize'),
  getAutonomousHealth: () => api.get('/api/autonomous/health'),

  // Decision Transparency Logs - What/Why/How for all bot decisions
  // NOTE: These endpoints are at /api/trader not /api/autonomous
  getDecisionLogs: (params?: {
    bot?: string,
    start_date?: string,
    end_date?: string,
    decision_type?: string,
    symbol?: string,
    limit?: number
  }) => api.get('/api/trader/logs/decisions', { params }),

  exportDecisionLogsCSV: (params?: {
    bot?: string,
    start_date?: string,
    end_date?: string,
    symbol?: string
  }) => api.get('/api/trader/logs/decisions/export', { params, responseType: 'blob' }),

  getDecisionSummary: (params?: { bot?: string, days?: number }) =>
    api.get('/api/trader/logs/summary', { params }),

  getRecentDecisions: (params?: { bot?: string, limit?: number }) =>
    api.get('/api/trader/logs/recent', { params }),

  getBotsStatus: () => api.get('/api/trader/bots/status'),

  // Reset bots to start fresh
  resetBotData: (params?: { bot?: string, confirm?: boolean }) =>
    api.post('/api/trader/bots/reset', null, { params }),

  // ARES - Aggressive Iron Condor Bot
  getARESStatus: () => api.get('/api/trader/bots/ares/status'),
  runARESCycle: () => api.post('/api/trader/bots/ares/run'),

  // ARES Page API endpoints
  getARESPageStatus: () => api.get('/api/ares/status'),
  getARESPerformance: () => api.get('/api/ares/performance'),
  getARESEquityCurve: (days: number = 30) => api.get('/api/ares/equity-curve', { params: { days } }),
  getARESPositions: () => api.get('/api/ares/positions'),
  getARESMarketData: () => api.get('/api/ares/market-data'),
  getARESTradierStatus: () => api.get('/api/ares/tradier-status'),
  getARESDecisions: (limit: number = 50) => api.get('/api/ares/decisions', { params: { limit } }),
  getARESConfig: () => api.get('/api/ares/config'),

  // ATHENA - Directional Spread Bot
  getATHENAStatus: () => api.get('/api/athena/status'),
  getATHENAPositions: (status?: string) => api.get('/api/athena/positions', { params: status ? { status_filter: status } : {} }),
  getATHENASignals: (limit: number = 50) => api.get('/api/athena/signals', { params: { limit } }),
  getATHENALogs: (level?: string, limit: number = 100) => api.get('/api/athena/logs', { params: { level, limit } }),
  getATHENAPerformance: (days: number = 30) => api.get('/api/athena/performance', { params: { days } }),
  getATHENAConfig: () => api.get('/api/athena/config'),
  updateATHENAConfig: (name: string, value: string) => api.post(`/api/athena/config/${name}`, null, { params: { value } }),
  runATHENACycle: () => api.post('/api/athena/run'),
  getATHENAOracleAdvice: () => api.get('/api/athena/oracle-advice'),
  getATHENAMLSignal: () => api.get('/api/athena/ml-signal'),

  // AI Intelligence Enhancements - 7 Advanced Features
  generatePreTradeChecklist: (data: {
    symbol: string,
    strike: number,
    option_type: string,
    contracts: number,
    cost_per_contract: number,
    pattern_type?: string,
    confidence?: number
  }) => api.post('/api/ai-intelligence/pre-trade-checklist', data),
  explainTrade: (tradeId: string) => api.get(`/api/ai-intelligence/trade-explainer/${tradeId}`),
  getDailyTradingPlan: () => api.get('/api/ai-intelligence/daily-trading-plan'),
  getPositionGuidance: (tradeId: string) => api.get(`/api/ai-intelligence/position-guidance/${tradeId}`),
  getMarketCommentary: () => api.get('/api/ai-intelligence/market-commentary'),
  getIntelligenceFeed: () => api.get('/api/ai-intelligence/intelligence-feed'),
  compareAvailableStrategies: () => api.get('/api/ai-intelligence/compare-strategies'),
  explainGreek: (data: {
    greek: string,
    value: number,
    strike: number,
    current_price: number,
    contracts: number,
    option_type: string,
    days_to_expiration?: number
  }) => api.post('/api/ai-intelligence/explain-greek', data),
  getAIIntelligenceHealth: () => api.get('/api/ai-intelligence/health'),

  // Multi-Symbol Scanner
  scanSymbols: (symbols: string[]) => api.post('/api/scanner/scan', { symbols }),
  getScannerHistory: (limit: number = 10) => api.get('/api/scanner/history', { params: { limit } }),
  getScanResults: (scanId: string) => api.get(`/api/scanner/results/${scanId}`),

  // Trade Setups
  generateSetups: (data: { symbols?: string[], account_size?: number, risk_pct?: number }) =>
    api.post('/api/setups/generate', data),
  saveSetup: (setup: any) => api.post('/api/setups/save', setup),
  getSetups: (limit: number = 20, status: string = 'active') =>
    api.get('/api/setups/list', { params: { limit, status } }),
  updateSetup: (setupId: number, data: any) => api.put(`/api/setups/${setupId}`, data),

  // Alerts
  createAlert: (data: { symbol: string, alert_type: string, condition: string, threshold: number, message?: string }) =>
    api.post('/api/alerts/create', data),
  getAlerts: (status: string = 'active') => api.get('/api/alerts/list', { params: { status } }),
  deleteAlert: (alertId: number) => api.delete(`/api/alerts/${alertId}`),
  checkAlerts: () => api.get('/api/alerts/check'),
  getAlertHistory: (limit: number = 50) => api.get('/api/alerts/history', { params: { limit } }),

  // Position Sizing
  calculatePositionSize: (data: {
    account_size: number,
    win_rate: number,
    avg_win: number,
    avg_loss: number,
    current_price: number,
    risk_per_trade_pct: number
  }) => api.post('/api/position-sizing/calculate', data),

  // Strategy Optimizer - Strike-Level Intelligence
  getStrikePerformance: (strategy?: string) => api.get('/api/optimizer/strikes', { params: { strategy } }),
  getDTEPerformance: (strategy?: string) => api.get('/api/optimizer/dte', { params: { strategy } }),
  getRegimePerformance: (strategy?: string) => api.get('/api/optimizer/regime-specific', { params: { strategy } }),
  getGreeksPerformance: (strategy?: string) => api.get('/api/optimizer/greeks', { params: { strategy } }),
  getBestCombinations: (strategy?: string) => api.get('/api/optimizer/best-combinations', { params: { strategy } }),
  getLiveStrikeRecommendations: (data: {
    spot_price: number,
    vix_current: number,
    pattern_type: string
  }) => api.post('/api/optimizer/live-recommendations', data),

  // PYTHIA - Predictive Yield Through Holistic Intelligence Analysis
  getProbabilityOutcomes: (days?: number) => api.get('/api/probability/outcomes', { params: { days: days || 30 } }),
  getProbabilityWeights: () => api.get('/api/probability/weights'),
  getCalibrationHistory: (days?: number) => api.get('/api/probability/calibration-history', { params: { days: days || 90 } }),

  // ML System - SPX Wheel ML Training & Predictions
  getMLStatus: () => api.get('/api/ml/status'),
  trainML: (minSamples: number = 30) => api.post('/api/ml/train', { min_samples: minSamples }),
  getMLPrediction: (data: {
    trade_date: string
    strike: number
    underlying_price: number
    dte: number
    premium: number
    iv: number
    iv_rank: number
    vix: number
    delta?: number
    vix_percentile?: number
    vix_term_structure?: number
    put_wall_distance_pct?: number
    call_wall_distance_pct?: number
    net_gex?: number
    spx_20d_return?: number
    spx_5d_return?: number
    spx_distance_from_high?: number
  }) => api.post('/api/ml/predict', data),
  recordMLEntry: (tradeId: string, data: any) =>
    api.post('/api/ml/record-entry', data, { params: { trade_id: tradeId } }),
  recordMLOutcome: (data: {
    trade_id: string
    outcome: 'WIN' | 'LOSS'
    pnl: number
    settlement_price: number
    max_drawdown?: number
  }) => api.post('/api/ml/record-outcome', data),
  getMLFeatureImportance: () => api.get('/api/ml/feature-importance'),
  getMLStrategyExplanation: () => api.get('/api/ml/strategy-explanation'),
  getMLDataQuality: () => api.get('/api/ml/data-quality'),
  getMLLogs: (limit: number = 100, actionFilter?: string) =>
    api.get('/api/ml/logs', { params: { limit, action_filter: actionFilter } }),
  getMLLogsSummary: () => api.get('/api/ml/logs/summary'),
  scoreAndLogTrade: (data: {
    strike: number
    underlying_price: number
    dte: number
    premium: number
    iv?: number
    iv_rank?: number
    vix?: number
    trade_id?: string
  }) => api.post('/api/ml/score-and-log', null, { params: data }),

  // Conversation History
  getConversations: (limit?: number) => api.get('/api/ai/conversations', { params: { limit: limit || 50 } }),
  getConversation: (id: number) => api.get(`/api/ai/conversation/${id}`),

  // Recommendations History
  getRecommendationsHistory: (days?: number) => api.get('/api/recommendations/history', { params: { days: days || 90 } }),
  getRecommendationPerformance: () => api.get('/api/recommendations/performance'),

  // GEX History
  getGEXHistory: (symbol?: string, days?: number) => api.get('/api/gex/history', { params: { symbol: symbol || 'SPY', days: days || 90 } }),
  getGEXRegimeChanges: (symbol?: string, days?: number) => api.get('/api/gex/regime-changes', { params: { symbol: symbol || 'SPY', days: days || 90 } }),

  // Push Notifications
  getPushSubscriptions: () => api.get('/api/notifications/subscriptions'),
  deletePushSubscription: (id: number) => api.delete(`/api/notifications/subscription/${id}`),

  // Database Administration & System Monitoring
  getDatabaseStats: () => api.get('/api/database/stats'),
  getTableFreshness: () => api.get('/api/database/table-freshness'),
  testConnections: () => api.get('/api/test-connections'),
  getSystemHealth: () => api.get('/api/system/health'),
  getSystemLogs: (limit?: number, logType?: string) =>
    api.get('/api/system/logs', { params: { limit: limit || 50, log_type: logType || 'all' } }),
  clearSystemLogs: (logType?: string) =>
    api.delete('/api/system/logs/clear', { params: { log_type: logType || 'all' } }),
  clearSystemCache: () => api.post('/api/system/cache/clear'),
  getDataCollectionStatus: () => api.get('/api/data-collection/status'),
  triggerDataCollection: () => api.post('/api/data-collection/trigger'),
  getWatchdogStatus: () => api.get('/api/watchdog/status'),
  restartThread: (threadName: string) => api.post(`/api/watchdog/restart-thread/${threadName}`),

  // VIX Hedge Manager
  getVIXHedgeSignal: (portfolioDelta?: number, portfolioValue?: number) =>
    api.get('/api/vix/hedge-signal', {
      params: { portfolio_delta: portfolioDelta, portfolio_value: portfolioValue }
    }),
  getVIXSignalHistory: (days?: number) =>
    api.get('/api/vix/signal-history', { params: { days: days || 30 } }),
  getVIXCurrent: () => api.get('/api/vix/current'),
  getVIXDebug: () => api.get('/api/vix/debug'),

  // Psychology Traps & Analysis
  getPsychologyCurrentRegime: (symbol: string = 'SPY') =>
    api.get('/api/psychology/current-regime', { params: { symbol } }),
  getPsychologyStatistics: () => api.get('/api/psychology/statistics'),
  getLiberationSetups: () => api.get('/api/psychology/liberation-setups'),
  getFalseFloors: () => api.get('/api/psychology/false-floors'),
  getPsychologyNotificationStats: () => api.get('/api/psychology/notifications/stats'),
  getPsychologyNotificationHistory: (limit: number = 20) =>
    api.get('/api/psychology/notifications/history', { params: { limit } }),
  getPsychologyPerformanceOverview: () => api.get('/api/psychology/performance/overview'),
  getPsychologyPerformancePatterns: () => api.get('/api/psychology/performance/patterns'),
  getPsychologyPerformanceSignals: () => api.get('/api/psychology/performance/signals'),

  // Backtesting & Smart Recommendations
  getSmartRecommendations: () => api.get('/api/backtests/smart-recommendations'),
  getBacktestResults: () => api.get('/api/backtests/results'),
  runBacktests: (config?: { lookback_days?: number, strategies?: string[], async_mode?: boolean }) =>
    api.post('/api/backtests/run', { async_mode: true, ...config }),
  exportBacktestResults: () => {
    // Direct download - returns CSV file
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    window.open(`${baseUrl}/api/backtests/export`, '_blank')
  },

  // Background Job Management (for async backtests)
  getBacktestJobStatus: (jobId: string) => api.get(`/api/backtests/job/${jobId}`),
  getRecentBacktestJobs: (limit?: number) => api.get('/api/backtests/jobs', { params: { limit: limit || 20 } }),
  runSPXBacktestAsync: (config?: {
    start_date?: string
    end_date?: string
    initial_capital?: number
    put_delta?: number
    dte_target?: number
    use_ml_scoring?: boolean
    async_mode?: boolean
  }) => api.post('/api/backtests/run-spx', { async_mode: true, ...config }),

  // SPX Institutional Trader
  getSPXStatus: () => api.get('/api/spx/status'),
  getSPXPerformance: () => api.get('/api/spx/performance'),
  checkSPXRiskLimits: (contracts: number, entryPrice: number, delta?: number) =>
    api.post('/api/spx/check-risk', {}, {
      params: { contracts, entry_price: entryPrice, delta: delta || 0.5 }
    }),
  getSPXTrades: (limit?: number) => api.get('/api/spx/trades', { params: { limit: limit || 20 } }),
  getSPXEquityCurve: (days?: number) => api.get('/api/spx/equity-curve', { params: { days: days || 30 } }),
  getSPXTradeLog: () => api.get('/api/spx/trade-log'),

  // Wheel Strategy
  getWheelPhases: () => api.get('/api/wheel/phases'),
  startWheelCycle: (data: {
    symbol: string
    strike: number
    expiration_date: string
    contracts: number
    premium: number
    underlying_price: number
    delta?: number
  }) => api.post('/api/wheel/start', data),
  getWheelCycles: (status?: string) => api.get('/api/wheel/cycles', { params: { status } }),
  updateWheelPhase: (cycleId: number, phase: string, data?: any) =>
    api.post(`/api/wheel/cycle/${cycleId}/phase`, { phase, ...data }),

  // SPX Wheel Backtest
  runSPXBacktest: (data: {
    start_date: string
    end_date?: string
    initial_capital?: number
    put_delta?: number
    dte_target?: number
    use_ml_scoring?: boolean
  }) => api.post('/api/spx-backtest/run', data),
  getSPXBacktestResults: () => api.get('/api/spx-backtest/results'),

  // 0DTE Iron Condor Backtest
  runZeroDTEBacktest: (config: {
    start_date?: string
    end_date?: string
    initial_capital?: number
    spread_width?: number
    sd_multiplier?: number
    risk_per_trade_pct?: number
    ticker?: string
    strategy?: string
  }) => api.post('/api/zero-dte/run', config),
  getZeroDTEJobStatus: (jobId: string) => api.get(`/api/zero-dte/job/${jobId}`),
  getZeroDTEResults: () => api.get('/api/zero-dte/results'),
  getZeroDTEStrategies: () => api.get('/api/zero-dte/strategies'),
  getZeroDTETiers: () => api.get('/api/zero-dte/tiers'),
  getZeroDTEStrategyTypes: () => api.get('/api/zero-dte/strategy-types'),
  getZeroDTEDataSources: () => api.get('/api/zero-dte/data-sources'),
  getZeroDTEStoredDataStatus: () => api.get('/api/zero-dte/stored-data-status'),
  backfillZeroDTEMarketData: (startDate: string = '2020-01-01') =>
    api.post(`/api/zero-dte/backfill-all?start_date=${startDate}`),
  storeZeroDTEMarketData: (ticker: string, days: number = 1825) =>
    api.post(`/api/zero-dte/store-market-data?ticker=${ticker}&days=${days}`),
  exportZeroDTETrades: (jobId: string) => api.get(`/api/zero-dte/export/trades/${jobId}`, { responseType: 'blob' }),
  exportZeroDTESummary: (jobId: string) => api.get(`/api/zero-dte/export/summary/${jobId}`, { responseType: 'blob' }),
  exportZeroDTEEquityCurve: (jobId: string) => api.get(`/api/zero-dte/export/equity-curve/${jobId}`, { responseType: 'blob' }),
  compareZeroDTEBacktests: (jobIds: string[]) => api.get(`/api/zero-dte/compare?job_ids=${jobIds.join(',')}`),

  // Oracle AI - Claude-powered prediction validation and analysis
  getOracleStatus: () => api.get('/api/zero-dte/oracle/status'),
  getOracleLogs: () => api.get('/api/zero-dte/oracle/logs'),
  clearOracleLogs: () => api.delete('/api/zero-dte/oracle/logs'),
  getOraclePredictions: (params?: { limit?: number, bot_name?: string, days?: number }) =>
    api.get('/api/logs/oracle', { params }),
  oracleAnalyze: (data: {
    spot_price: number
    vix: number
    gex_regime: string
    day_of_week?: number
    vix_1d_change?: number
    normalized_gex?: number
    gex_normalized?: number
    gex_call_wall?: number
    gex_put_wall?: number
    distance_to_call_wall?: number
    distance_to_put_wall?: number
    bot_name?: string
  }) => api.post('/api/zero-dte/oracle/analyze', data),
  oracleExplain: (data: {
    prediction: any
    market_context?: any
  }) => api.post('/api/zero-dte/oracle/explain', data),
  oracleAnalyzePatterns: (data: {
    backtest_trades: any[]
    focus_area?: string
  }) => api.post('/api/zero-dte/oracle/analyze-patterns', data),

  // Oracle Training & Bot Interactions
  getOracleTrainingStatus: () => api.get('/api/zero-dte/oracle/training-status'),
  triggerOracleTraining: (force: boolean = false) =>
    api.post(`/api/zero-dte/oracle/trigger-training?force=${force}`),
  getOracleBotInteractions: (params?: { days?: number, limit?: number, bot_name?: string }) => {
    const queryParams = new URLSearchParams()
    if (params?.days) queryParams.append('days', String(params.days))
    if (params?.limit) queryParams.append('limit', String(params.limit))
    if (params?.bot_name) queryParams.append('bot_name', params.bot_name)
    return api.get(`/api/zero-dte/oracle/bot-interactions?${queryParams.toString()}`)
  },
  getOraclePerformance: (days: number = 90) =>
    api.get(`/api/zero-dte/oracle/performance?days=${days}`),
  getOraclePredictionsFull: (params?: { days?: number, limit?: number, bot_name?: string, include_claude?: boolean }) => {
    const queryParams = new URLSearchParams()
    if (params?.days) queryParams.append('days', String(params.days))
    if (params?.limit) queryParams.append('limit', String(params.limit))
    if (params?.bot_name) queryParams.append('bot_name', params.bot_name)
    if (params?.include_claude !== undefined) queryParams.append('include_claude', String(params.include_claude))
    return api.get(`/api/zero-dte/oracle/predictions?${queryParams.toString()}`)
  },

  // Export Routes
  exportData: async (type: 'trades' | 'pnl-attribution' | 'decision-logs' | 'wheel-cycles' | 'full-audit', params?: {
    symbol?: string
    start_date?: string
    end_date?: string
  }) => {
    const queryParams = new URLSearchParams()
    if (params?.symbol) queryParams.append('symbol', params.symbol)
    if (params?.start_date) queryParams.append('start_date', params.start_date)
    if (params?.end_date) queryParams.append('end_date', params.end_date)

    const response = await api.get(`/api/export/${type}?${queryParams.toString()}`, {
      responseType: 'blob'
    })
    return response
  },

  // ============================================================================
  // NEW: Transparency & Analysis Endpoints
  // ============================================================================

  // Unified Portfolio - Combined SPY + SPX view with Greeks
  getUnifiedPortfolio: () => api.get('/api/trader/portfolio/unified'),

  // Regime Signals - Full 80+ columns of analysis data
  getRegimeCurrent: () => api.get('/api/regime/current'),
  getRegimeHistory: (days: number = 7) => api.get(`/api/regime/history?days=${days}`),
  getRegimeColumns: () => api.get('/api/regime/columns'),
  getRegimeRSI: (limit: number = 20) => api.get(`/api/regime/rsi-analysis?limit=${limit}`),
  getRegimeGammaWalls: (limit: number = 20) => api.get(`/api/regime/gamma-walls?limit=${limit}`),
  getRegimePsychologyTraps: (limit: number = 20) => api.get(`/api/regime/psychology-traps?limit=${limit}`),
  getRegimeMonthlyMagnets: (limit: number = 20) => api.get(`/api/regime/monthly-magnets?limit=${limit}`),
  getRegimeSignalAccuracy: (days: number = 30) => api.get(`/api/regime/signal-accuracy?days=${days}`),
  getRegimeVIX: (limit: number = 20) => api.get(`/api/regime/vix-analysis?limit=${limit}`),
  getRegimeTradeReasoning: (limit: number = 10) => api.get(`/api/regime/trade-reasoning?limit=${limit}`),

  // Volatility Surface - Skew, Term Structure, Trading Signals
  getVolSurfaceStatus: () => api.get('/api/volatility-surface/status'),
  getVolSurfaceAnalysis: (symbol: string = 'SPY') => api.get(`/api/volatility-surface/analyze/${symbol}`),
  getVolSurfaceSkew: (symbol: string = 'SPY') => api.get(`/api/volatility-surface/skew/${symbol}`),
  getVolSurfaceTermStructure: (symbol: string = 'SPY') => api.get(`/api/volatility-surface/term-structure/${symbol}`),
  getVolSurfaceTradingSignal: (symbol: string = 'SPY') => api.get(`/api/volatility-surface/trading-signal/${symbol}`),

  // Background Jobs - Long-running backtests
  getJobsList: (status?: string, limit: number = 20) =>
    api.get('/api/jobs/list', { params: { status, limit } }),
  getJobStatus: (jobId: string) => api.get(`/api/jobs/${jobId}/status`),
  getJobResult: (jobId: string) => api.get(`/api/jobs/${jobId}/result`),
  cancelJob: (jobId: string) => api.post(`/api/jobs/${jobId}/cancel`),
  startBacktestJob: (type: 'spx' | 'spy' | 'all', params?: any) =>
    api.post(`/api/jobs/backtest/${type}`, params || {}),
  startMLTrainingJob: (lookbackDays: number = 180) =>
    api.post('/api/jobs/ml/train', { lookback_days: lookbackDays }),

  // Psychology SSE Stream
  subscribeToPsychologyNotifications: (onMessage: (data: any) => void, onError?: (error: any) => void) => {
    if (!API_URL) {
      onError?.({ message: 'API_URL not configured' })
      return () => {}
    }

    const eventSource = new EventSource(`${API_URL}/api/psychology/notifications/stream`)

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        onMessage(data)
      } catch (e) {
        console.error('Failed to parse SSE message:', e)
      }
    }

    eventSource.onerror = (error) => {
      console.error('SSE connection error:', error)
      onError?.(error)
    }

    // Return cleanup function
    return () => {
      eventSource.close()
    }
  },

  // Bot Decision Logs
  getBotDecisions: (params: {
    bot?: string
    decision_type?: string
    session_id?: string
    start_date?: string
    end_date?: string
    outcome?: string
    search?: string
    limit?: number
    offset?: number
  }) => api.get('/api/logs/bot-decisions', { params }),

  getBotDecisionStats: (bot?: string, days: number = 30) =>
    api.get('/api/logs/bot-decisions/stats', { params: { bot, days } }),

  getBotDecisionDetail: (decisionId: string) =>
    api.get(`/api/logs/bot-decisions/decision/${decisionId}`),

  exportBotDecisions: (params: {
    bot?: string
    format?: 'csv' | 'json' | 'excel'
    days?: number
    include_claude?: boolean
  }) => api.get('/api/logs/bot-decisions/export', {
    params,
    responseType: params.format === 'json' ? 'json' : 'blob' as const
  }),

  // APOLLO - AI-Powered Live Options Scanner
  apolloScan: (symbols: string[], includeChains: boolean = true) =>
    api.post('/api/apollo/scan', { symbols, include_chains: includeChains }),
  getApolloScan: (scanId: string) => api.get(`/api/apollo/scan/${scanId}`),
  getApolloHistory: (limit: number = 20, symbol?: string) =>
    api.get('/api/apollo/history', { params: { limit, symbol } }),
  apolloFeedback: (data: {
    scan_id: string
    symbol: string
    actual_direction: string
    actual_magnitude: string
    actual_return_pct: number
    strategy_used?: string
    strategy_pnl?: number
    notes?: string
  }) => api.post('/api/apollo/feedback', data),
  getApolloPerformance: () => api.get('/api/apollo/performance'),
  getApolloLiveQuote: (symbol: string) => api.get(`/api/apollo/live-quote/${symbol}`),
  getApolloOptionsChain: (symbol: string, expiration?: string) =>
    api.get(`/api/apollo/options-chain/${symbol}`, { params: { expiration } }),
  getApolloFeatures: (symbol: string) => api.get(`/api/apollo/features/${symbol}`),
  triggerApolloTraining: () => api.post('/api/apollo/train'),

  // Daily Manna - Economic news with faith-based devotionals
  getDailyManna: (forceRefresh: boolean = false) =>
    api.get('/api/daily-manna/today', { params: { force_refresh: forceRefresh } }),
  getDailyMannaNews: () => api.get('/api/daily-manna/news'),
  getDailyMannaScriptures: () => api.get('/api/daily-manna/scriptures'),
  getDailyMannaDevotional: (forceRefresh: boolean = false) =>
    api.get('/api/daily-manna/devotional', { params: { force_refresh: forceRefresh } }),
  getDailyMannaWidget: () => api.get('/api/daily-manna/widget'),

  // Daily Manna Archive
  getDailyMannaArchive: (limit: number = 30) =>
    api.get('/api/daily-manna/archive', { params: { limit } }),
  getArchivedDevotional: (date: string) =>
    api.get(`/api/daily-manna/archive/${date}`),

  // Daily Manna Comments
  getDailyMannaComments: (date?: string, limit: number = 50) =>
    api.get('/api/daily-manna/comments', { params: { date, limit } }),
  addDailyMannaComment: (data: { user_name: string; comment: string; date?: string }) =>
    api.post('/api/daily-manna/comments', data),
  likeDailyMannaComment: (commentId: number) =>
    api.post(`/api/daily-manna/comments/${commentId}/like`),

  // Daily Manna Reflections
  getDailyMannaReflections: (userId: string = 'default_user', limit: number = 100) =>
    api.get('/api/daily-manna/reflections', { params: { user_id: userId, limit } }),
  getReflectionForDate: (date: string, userId: string = 'default_user') =>
    api.get(`/api/daily-manna/reflections/${date}`, { params: { user_id: userId } }),
  saveDailyMannaReflection: (data: {
    reflection: string
    date?: string
    user_id?: string
    favorite?: boolean
    prayer_answered?: boolean
  }) => api.post('/api/daily-manna/reflections', data),
  updateDailyMannaReflection: (reflectionId: string, data: {
    reflection?: string
    favorite?: boolean
    prayer_answered?: boolean
    user_id?: string
  }) => api.put(`/api/daily-manna/reflections/${reflectionId}`, data),

  // Daily Manna Prayer Tracker
  markPrayedToday: (userId: string = 'default_user') =>
    api.post('/api/daily-manna/prayer/today', { user_id: userId }),
  getPrayerStats: (userId: string = 'default_user') =>
    api.get('/api/daily-manna/prayer/stats', { params: { user_id: userId } }),

  // ARGUS - 0DTE Gamma Live (Real-time gamma visualization)
  getArgusGamma: (expiration?: string) =>
    api.get('/api/argus/gamma', { params: { expiration } }),
  getArgusHistory: (expiration?: string, minutes?: number) =>
    api.get('/api/argus/history', { params: { expiration, minutes } }),
  getArgusProbability: () => api.get('/api/argus/probability'),
  getArgusAlerts: (acknowledged?: boolean, priority?: string) =>
    api.get('/api/argus/alerts', { params: { acknowledged, priority } }),
  acknowledgeArgusAlert: (alertId: number) =>
    api.post(`/api/argus/alerts/${alertId}/acknowledge`),
  getArgusCommentary: (limit?: number) =>
    api.get('/api/argus/commentary', { params: { limit } }),
  generateArgusCommentary: () => api.post('/api/argus/commentary/generate'),
  getArgusBots: () => api.get('/api/argus/bots'),
  getArgusAccuracy: () => api.get('/api/argus/accuracy'),
  getArgusPatterns: () => api.get('/api/argus/patterns'),
  exportArgusData: (format: 'csv' | 'xlsx' = 'xlsx') =>
    api.get('/api/argus/export', { params: { format }, responseType: 'blob' }),
  getArgusReplay: (date: string, time?: string) =>
    api.get('/api/argus/replay', { params: { date, time } }),
  getArgusReplayDates: () => api.get('/api/argus/replay/dates'),
  getArgusExpirations: () => api.get('/api/argus/expirations'),
  getArgusContext: () => api.get('/api/argus/context'),
}

// WebSocket connection
export const createWebSocket = (symbol: string = 'SPY') => {
  const WS_URL = process.env.NEXT_PUBLIC_WS_URL
  if (!WS_URL) {
    console.warn('[WebSocket] NEXT_PUBLIC_WS_URL not set. WebSocket connections will fail.')
    throw new Error('WebSocket URL not configured')
  }
  return new WebSocket(`${WS_URL}/ws/market-data?symbol=${symbol}`)
}

export default apiClient
