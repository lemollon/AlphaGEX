export interface StrikeGex {
  strike: number
  net_gamma: number
  call_gamma: number
  put_gamma: number
  call_volume: number
  put_volume: number
  total_volume: number
  call_iv: number | null
  put_iv: number | null
  call_oi: number
  put_oi: number
  is_magnet: boolean
  magnet_rank: number | null
  is_pin: boolean
  is_danger: boolean
  danger_type: string | null
}

export interface DiagnosticCard {
  id: string
  label: string
  metric_name: string
  metric_value: string
  description: string
  raw_value: number
}

export interface SkewMeasures {
  skew_ratio: number
  skew_ratio_description: string
  call_skew: number
  call_skew_description: string
  atm_call_iv: number | null
  atm_put_iv: number | null
  avg_otm_call_iv: number | null
  avg_otm_put_iv: number | null
}

export interface Positioning {
  regime_label: 'Bullish' | 'Neutral' | 'Bearish' | string
  pressure_score: number
  call_vs_put_pressure: number
  summary: string
}

export interface StructureBalance {
  balance: number
  label: string
  resist_gamma: number
  support_gamma: number
  horizon_days: number
  summary: string
}

export interface GexAnalysisData {
  symbol: string
  timestamp: string
  expiration: string
  header: {
    price: number
    gex_flip: number | null
    '30_day_vol': number | null
    call_structure: string
    gex_at_expiration: number
    net_gex: number
    rating: string
    gamma_form: string
    previous_regime: string | null
    regime_flipped: boolean
  }
  call_structure_details?: {
    structure: string
    description: string
    call_buying_pressure: number
    is_hedging: boolean
    is_overwrite: boolean
    is_speculation: boolean
  }
  flow_diagnostics: { cards: DiagnosticCard[]; note: string }
  skew_measures: SkewMeasures
  rating: { rating: string; confidence: string; bullish_score: number; bearish_score: number; net_score: number }
  positioning?: Positioning
  levels: {
    price: number
    upper_1sd: number | null
    lower_1sd: number | null
    gex_flip: number | null
    call_wall: number | null
    put_wall: number | null
    expected_move: number | null
  }
  gex_chart: { expiration: string; strikes: StrikeGex[]; total_net_gamma: number; gamma_regime: string }
  summary: {
    total_call_volume: number
    total_put_volume: number
    total_volume: number
    total_call_oi: number
    total_put_oi: number
    put_call_ratio: number
    net_gex: number
  }
}

export interface GexAllData {
  symbol: string
  timestamp: string
  spot_price: number
  gex_chart_all: {
    strikes: { strike: number; net_gamma: number }[]
    expirations_included: string[]
    expirations_failed: string[]
    total_net_gamma: number
  }
  structure_balance: StructureBalance
}
