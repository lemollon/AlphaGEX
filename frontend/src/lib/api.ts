import axios, { AxiosError } from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

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

      console.warn(`API Error (retrying in ${retryDelay}ms):`, error.message)
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

    console.error('API Error:', {
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

  // Market Data
  getPriceHistory: (symbol: string, days: number = 90) => api.get(`/api/market/price-history/${symbol}`, { params: { days } }),

  // Gamma Intelligence
  getGammaIntelligence: (symbol: string, vix?: number) =>
    api.get(`/api/gamma/${symbol}/intelligence`, { params: { vix } }),
  getGammaHistory: (symbol: string, days?: number) =>
    api.get(`/api/gamma/${symbol}/history`, { params: { days } }),
  getGammaExpiration: (symbol: string) =>
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

  // Probability System
  getProbabilityOutcomes: (days?: number) => api.get('/api/probability/outcomes', { params: { days: days || 30 } }),
  getProbabilityWeights: () => api.get('/api/probability/weights'),
  getCalibrationHistory: (days?: number) => api.get('/api/probability/calibration-history', { params: { days: days || 90 } }),

  // Conversation History
  getConversations: (limit?: number) => api.get('/api/ai/conversations', { params: { limit: limit || 50 } }),
  getConversation: (id: number) => api.get(`/api/ai/conversation/${id}`),

  // Open Interest Trends
  getOITrends: (symbol?: string, days?: number) => api.get('/api/oi/trends', { params: { symbol: symbol || 'SPY', days: days || 90 } }),
  getUnusualOIActivity: (symbol?: string, days?: number) => api.get('/api/oi/unusual-activity', { params: { symbol: symbol || 'SPY', days: days || 14 } }),

  // Recommendations History
  getRecommendationsHistory: (days?: number) => api.get('/api/recommendations/history', { params: { days: days || 90 } }),
  getRecommendationPerformance: () => api.get('/api/recommendations/performance'),

  // GEX History
  getGEXHistory: (symbol?: string, days?: number) => api.get('/api/gex/history', { params: { symbol: symbol || 'SPY', days: days || 90 } }),
  getGEXRegimeChanges: (symbol?: string, days?: number) => api.get('/api/gex/regime-changes', { params: { symbol: symbol || 'SPY', days: days || 90 } }),

  // Push Notifications
  getPushSubscriptions: () => api.get('/api/notifications/subscriptions'),
  deletePushSubscription: (id: number) => api.delete(`/api/notifications/subscription/${id}`),

  // Database Administration
  getDatabaseStats: () => api.get('/api/database/stats'),
  testConnections: () => api.get('/api/test-connections'),

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
  runBacktests: (config?: { lookback_days?: number, strategies?: string[] }) =>
    api.post('/api/backtests/run', config || {}),

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
}

// WebSocket connection
export const createWebSocket = (symbol: string = 'SPY') => {
  const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000'
  return new WebSocket(`${WS_URL}/ws/market-data?symbol=${symbol}`)
}

export default apiClient
