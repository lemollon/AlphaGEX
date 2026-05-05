import { describe, it, expect } from 'vitest'
import { classifyMood } from '../mood'

describe('classifyMood', () => {
  it('returns "forged" when P&L >= 80% of max profit and risk <= 4', () => {
    expect(classifyMood({ pnl_pct_of_target: 0.85, risk_score: 3, trade_count: 1 })).toBe('forged')
  })

  it('returns "burning" when risk_score >= 7 regardless of P&L', () => {
    expect(classifyMood({ pnl_pct_of_target: 0.5, risk_score: 8, trade_count: 1 })).toBe('burning')
  })

  it('returns "burning" when trade_count >= 3 (high activity)', () => {
    expect(classifyMood({ pnl_pct_of_target: 0.2, risk_score: 5, trade_count: 4 })).toBe('burning')
  })

  it('returns "cooled" when -100% < P&L <= -50% of target', () => {
    expect(classifyMood({ pnl_pct_of_target: -0.6, risk_score: 5, trade_count: 1 })).toBe('cooled')
  })

  it('returns "measured" for the default middle band', () => {
    expect(classifyMood({ pnl_pct_of_target: 0.3, risk_score: 5, trade_count: 1 })).toBe('measured')
    expect(classifyMood({ pnl_pct_of_target: -0.2, risk_score: 4, trade_count: 1 })).toBe('measured')
  })

  it('returns "measured" for zero-trade days', () => {
    expect(classifyMood({ pnl_pct_of_target: 0, risk_score: 0, trade_count: 0 })).toBe('measured')
  })
})
