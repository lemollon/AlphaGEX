export type BotKey = 'flame' | 'spark' | 'inferno' | 'portfolio'
export type BriefType = 'daily_eod' | 'fomc_eve' | 'post_event' | 'weekly_synth' | 'codex_monthly'
export type Mood = 'forged' | 'measured' | 'cooled' | 'burning'

export interface Factor { rank: number; title: string; detail: string }

export interface TradeOfDay {
  position_id: string
  strikes: { ps: number; pl: number; cs?: number | null; cl?: number | null }
  entry_credit: number
  exit_cost: number
  contracts: number
  pnl: number
  payoff_points: Array<{ spot: number; pnl: number }>
}

export interface MacroRibbon {
  spy_open: number; spy_close: number; spy_range_pct: number; em_pct: number
  vix: number; vix_change: number; regime: string; pin_risk: 'Low' | 'Medium' | 'High'
}

export interface SparklinePoint { date: string; cumulative_pnl: number }

export interface ParsedBrief {
  title: string
  summary: string
  wisdom: string | null
  risk_score: number
  bot_voice_signature: string
  factors: Factor[]
  trade_of_day?: TradeOfDay | null
}

export interface BriefRow {
  brief_id: string
  bot: BotKey
  brief_type: BriefType
  brief_date: string
  brief_time: string | Date
  title: string
  summary: string
  wisdom: string | null
  risk_score: number | null
  mood: Mood | null
  bot_voice_signature: string | null
  factors: Factor[] | null
  trade_of_day: TradeOfDay | null
  macro_ribbon: MacroRibbon | null
  sparkline_data: SparklinePoint[] | null
  prior_briefs_referenced: string[] | null
  codex_referenced: string | null
  model: string | null
  tokens_in: number | null
  tokens_out: number | null
  cost_usd: number | null
  generation_status: string
  is_active: boolean
}

export interface GatheredContext {
  bot: BotKey
  brief_type: BriefType
  brief_date: string
  today_positions: any[]
  today_trades: any[]
  daily_perf: any
  equity_curve_7d: SparklinePoint[]
  dashboard_state: any | null
  macro: MacroRibbon
  memory_recent: Array<{ brief_id: string; brief_date: string; summary: string; wisdom: string | null }>
  memory_codex: { brief_id: string; summary: string } | null
  upcoming_blackout: { title: string; halt_start_ts: string; halt_end_ts: string } | null
  active_blackout: { title: string; halt_end_ts: string } | null
}
