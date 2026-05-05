import type { Mood } from './types'

export interface MoodInput {
  pnl_pct_of_target: number
  risk_score: number
  trade_count: number
}

export function classifyMood(input: MoodInput): Mood {
  if (input.risk_score >= 7) return 'burning'
  if (input.trade_count >= 3) return 'burning'
  if (input.pnl_pct_of_target >= 0.8 && input.risk_score <= 4) return 'forged'
  if (input.pnl_pct_of_target <= -0.5 && input.pnl_pct_of_target > -1.0) return 'cooled'
  return 'measured'
}
