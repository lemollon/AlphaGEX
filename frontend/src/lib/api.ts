import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Create axios instance with defaults
export const api = axios.create({
  baseURL: API_URL,
  timeout: 600000, // 10 minutes for scanner (with rate limiting, 18 symbols can take 6+ minutes)
  headers: {
    'Content-Type': 'application/json',
  },
})

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.response?.data || error.message)
    return Promise.reject(error)
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

  // Gamma Intelligence
  getGammaIntelligence: (symbol: string, vix?: number) =>
    api.get(`/api/gamma/${symbol}/intelligence`, { params: { vix } }),
  getGammaHistory: (symbol: string, days?: number) =>
    api.get(`/api/gamma/${symbol}/history`, { params: { days } }),
  getGammaExpiration: (symbol: string) =>
    api.get(`/api/gamma/${symbol}/expiration`),

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
  getTraderTrades: (limit: number = 10) => api.get('/api/trader/trades', { params: { limit } }),
  getOpenPositions: () => api.get('/api/trader/positions'),
  getTradeLog: () => api.get('/api/trader/trade-log'),
  getStrategies: () => api.get('/api/trader/strategies'),
  compareStrategies: (symbol: string = 'SPY') => api.get('/api/strategies/compare', { params: { symbol } }),

  // Market Data
  getPriceHistory: (symbol: string, days: number = 90) =>
    api.get(`/api/market/price-history/${symbol}`, { params: { days } }),

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
}

// WebSocket connection
export const createWebSocket = (symbol: string = 'SPY') => {
  const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000'
  return new WebSocket(`${WS_URL}/ws/market-data?symbol=${symbol}`)
}

export default apiClient
