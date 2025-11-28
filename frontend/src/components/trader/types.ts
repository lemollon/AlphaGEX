// Shared types for trader components

export interface TraderStatus {
  is_active: boolean
  mode: 'paper' | 'live'
  status?: string
  current_action?: string
  market_analysis?: string
  last_decision?: string
  last_check: string
  next_check_time?: string
  strategies_active: number
  total_trades_today: number
  uptime?: number
}

export interface Performance {
  total_pnl: number
  today_pnl: number
  win_rate: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  sharpe_ratio: number
  max_drawdown: number
  starting_capital: number
  current_value: number
  realized_pnl: number
  unrealized_pnl: number
  return_pct: number
}

export interface Trade {
  id: string
  timestamp: string
  symbol: string
  action: 'BUY' | 'SELL' | 'LONG_STRADDLE' | 'IRON_CONDOR' | 'BULL_PUT_SPREAD' | 'BEAR_CALL_SPREAD' | 'CASH_SECURED_PUT' | string
  type: 'CALL' | 'PUT' | 'straddle' | 'iron_condor' | 'bull_put_spread' | 'bear_call_spread' | 'csp' | string
  strike: number
  quantity: number
  price: number
  status: 'filled' | 'pending' | 'cancelled' | 'OPEN' | 'CLOSED'
  pnl?: number
  strategy?: string
  entry_bid?: number
  entry_ask?: number
  entry_spot_price?: number
  current_price?: number
  current_spot_price?: number
  trade_reasoning?: string
  expiration_date?: string
  entry_iv?: number
  entry_delta?: number
  current_iv?: number
  current_delta?: number
  theta?: number
  gamma?: number
  vega?: number
  gex_regime?: string
  entry_net_gex?: number
}

export interface MLModelStatus {
  is_trained: boolean
  accuracy: number
  training_samples: number
  feature_count: number
  last_trained: string | null
  feature_importance: Record<string, number>
}

export interface MLPrediction {
  prediction: 'bullish' | 'bearish' | 'neutral'
  predicted_direction: number
  symbol: string
  pattern: string
  timestamp: string
  confidence: number
  probability: number
}

export interface ClosedTrade {
  id: string
  entry_date: string
  entry_time: string
  exit_date: string
  exit_time: string
  symbol: string
  strategy: string
  strike: number
  option_type: string
  contracts: number
  entry_price: number
  exit_price: number
  pnl: number
  pnl_pct: number
  exit_reason: string
  hold_duration_minutes: number
  trade_reasoning?: string
}

export interface EquityCurvePoint {
  timestamp: number
  equity: number
  pnl: number
  date: string
}

export interface RiskStatus {
  daily_loss_limit: number
  current_daily_loss: number
  max_position_size: number
  current_exposure: number
  risk_score: number
  alerts: string[]
}

// Utility functions
export const formatCurrency = (value: number): string => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

export const formatPercent = (value: number): string => {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}
