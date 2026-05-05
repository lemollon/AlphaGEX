import { describe, it, expect } from 'vitest'
import { buildSystemPrompt, buildUserPrompt } from '../voices'
import type { GatheredContext } from '../types'

describe('buildSystemPrompt', () => {
  it('includes the FLAME voice and the daily_eod intro', () => {
    const p = buildSystemPrompt('flame', 'daily_eod')
    expect(p).toContain('You are FLAME')
    expect(p).toContain('end-of-day debrief')
    expect(p).toContain('You MUST respond with a single JSON object')
  })

  it('uses the SPARK voice with weekly synth intro', () => {
    const p = buildSystemPrompt('spark', 'weekly_synth')
    expect(p).toContain('You are SPARK')
    expect(p).toContain('weekly synthesis')
  })

  it('uses the Master voice for portfolio briefs', () => {
    const p = buildSystemPrompt('portfolio', 'daily_eod')
    expect(p).toContain('Master of the Forge')
  })

  it('uses the codex monthly intro', () => {
    const p = buildSystemPrompt('inferno', 'codex_monthly')
    expect(p).toContain('You are INFERNO')
    expect(p).toContain('monthly codex')
  })
})

describe('buildUserPrompt', () => {
  it('serializes the context as JSON', () => {
    const ctx: GatheredContext = {
      bot: 'flame', brief_type: 'daily_eod', brief_date: '2026-05-04',
      today_positions: [], today_trades: [], daily_perf: { trades: 0 },
      equity_curve_7d: [], dashboard_state: null,
      macro: { spy_open: 587, spy_close: 588, spy_range_pct: 0.5, em_pct: 0.9, vix: 18, vix_change: -0.5, regime: 'Negative Gamma', pin_risk: 'Medium' },
      memory_recent: [], memory_codex: null,
      upcoming_blackout: null, active_blackout: null,
    }
    const p = buildUserPrompt(ctx)
    expect(p).toContain('"bot": "flame"')
    expect(p).toContain('"brief_date": "2026-05-04"')
    expect(p).toContain('"regime": "Negative Gamma"')
  })
})
