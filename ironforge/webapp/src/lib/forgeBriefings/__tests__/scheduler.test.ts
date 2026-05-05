import { describe, it, expect } from 'vitest'
import { decideTriggers } from '../scheduler'

describe('decideTriggers — daily EOD', () => {
  it('fires daily_eod for all 3 bots + portfolio at 15:30 CT on a weekday (DST)', () => {
    // 15:30 CDT = 20:30 UTC on a Mon
    const t = decideTriggers(new Date('2026-05-04T20:30:00Z'), [], [])
    const types = t.map(x => `${x.bot}:${x.brief_type}`)
    expect(types).toContain('flame:daily_eod')
    expect(types).toContain('spark:daily_eod')
    expect(types).toContain('inferno:daily_eod')
    expect(types).toContain('portfolio:daily_eod')
  })

  it('does NOT fire daily_eod at 15:29 CT', () => {
    const t = decideTriggers(new Date('2026-05-04T20:29:00Z'), [], [])
    expect(t.find(x => x.brief_type === 'daily_eod')).toBeUndefined()
  })

  it('does NOT fire on weekends', () => {
    // Saturday May 9 2026 15:30 CDT = 20:30 UTC
    const t = decideTriggers(new Date('2026-05-09T20:30:00Z'), [], [])
    expect(t.length).toBe(0)
  })

  it('fires within tolerance window 15:30-15:34', () => {
    const t1 = decideTriggers(new Date('2026-05-04T20:31:00Z'), [], [])
    const t2 = decideTriggers(new Date('2026-05-04T20:34:00Z'), [], [])
    const t3 = decideTriggers(new Date('2026-05-04T20:35:00Z'), [], [])
    expect(t1.find(x => x.brief_type === 'daily_eod')).toBeDefined()
    expect(t2.find(x => x.brief_type === 'daily_eod')).toBeDefined()
    expect(t3.find(x => x.brief_type === 'daily_eod')).toBeUndefined()
  })
})

describe('decideTriggers — weekly', () => {
  it('fires weekly_synth on Friday at 16:00 CT', () => {
    // Fri May 8 2026 16:00 CDT = 21:00 UTC
    const t = decideTriggers(new Date('2026-05-08T21:00:00Z'), [], [])
    const types = t.map(x => `${x.bot}:${x.brief_type}`)
    expect(types).toContain('flame:weekly_synth')
    expect(types).toContain('portfolio:weekly_synth')
  })

  it('does NOT fire weekly_synth on Thursday', () => {
    const t = decideTriggers(new Date('2026-05-07T21:00:00Z'), [], [])
    expect(t.find(x => x.brief_type === 'weekly_synth')).toBeUndefined()
  })
})

describe('decideTriggers — codex monthly', () => {
  it('fires codex_monthly on the last business day of the month at 17:00 CT', () => {
    // Fri May 29 2026 (last biz day of May; May 30=Sat, 31=Sun) 17:00 CDT = 22:00 UTC
    const t = decideTriggers(new Date('2026-05-29T22:00:00Z'), [], [])
    const types = t.map(x => `${x.bot}:${x.brief_type}`)
    expect(types).toContain('flame:codex_monthly')
    expect(types).toContain('portfolio:codex_monthly')
  })

  it('does NOT fire codex on the first day of the next month', () => {
    // Mon Jun 1 2026 17:00 CDT = 22:00 UTC
    const t = decideTriggers(new Date('2026-06-01T22:00:00Z'), [], [])
    expect(t.find(x => x.brief_type === 'codex_monthly')).toBeUndefined()
  })
})

describe('decideTriggers — fomc_eve', () => {
  it('fires fomc_eve on the Thursday before an upcoming Wed FOMC at 15:35 CT', () => {
    // Wed Jun 18 2025 FOMC; Thu before = Jun 12; 15:35 CDT = 20:35 UTC
    const upcoming = [{ event_date: '2025-06-18', halt_start_ts: '2025-06-13T13:30:00Z' }]
    const t = decideTriggers(new Date('2025-06-12T20:35:00Z'), upcoming, [])
    expect(t.find(x => x.brief_type === 'fomc_eve' && x.bot === 'flame')).toBeDefined()
  })
})

describe('decideTriggers — post_event', () => {
  it('fires post_event the day after a halt_end_ts at 09:00 CT', () => {
    // Wed Jun 18 2025 halt_end at 19:00 UTC. Next morning Thu Jun 19 09:00 CDT = 14:00 UTC.
    const recentlyEnded = [{ halt_end_ts: '2025-06-18T19:00:00Z', event_date: '2025-06-18' }]
    const t = decideTriggers(new Date('2025-06-19T14:00:00Z'), [], recentlyEnded)
    expect(t.find(x => x.brief_type === 'post_event' && x.bot === 'spark')).toBeDefined()
  })
})
