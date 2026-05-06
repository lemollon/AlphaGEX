import { describe, it, expect } from 'vitest'
import {
  computeFridayPriorAt0830CT,
  computeEventDayAt,
  computeNTradingDaysPriorAt0830CT,
  computeDayOfNewsHaltWindow,
} from '../halt-window'

describe('computeFridayPriorAt0830CT (legacy — kept for back-compat)', () => {
  it('returns previous Friday 08:30 CT for a Wednesday FOMC (DST)', () => {
    const result = computeFridayPriorAt0830CT('2025-06-18')
    expect(result.toISOString()).toBe('2025-06-13T13:30:00.000Z')
  })

  it('returns the Friday a week prior when event is itself a Friday', () => {
    const result = computeFridayPriorAt0830CT('2026-07-03')
    expect(result.toISOString()).toBe('2026-06-26T13:30:00.000Z')
  })
})

describe('computeEventDayAt', () => {
  it('returns event_date + event_time + offset for FOMC default (DST)', () => {
    // Jun 18 2025, 13:00 CDT, +60 min = 14:00 CDT = 19:00 UTC
    const result = computeEventDayAt('2025-06-18', '13:00', 60)
    expect(result.toISOString()).toBe('2025-06-18T19:00:00.000Z')
  })

  it('handles a 0-minute offset', () => {
    const result = computeEventDayAt('2025-06-18', '13:00', 0)
    expect(result.toISOString()).toBe('2025-06-18T18:00:00.000Z')
  })

  it('handles event in standard time (no DST)', () => {
    // Jan 28 2026, 13:00 CST, +60 min = 14:00 CST = 20:00 UTC
    const result = computeEventDayAt('2026-01-28', '13:00', 60)
    expect(result.toISOString()).toBe('2026-01-28T20:00:00.000Z')
  })
})

describe('computeNTradingDaysPriorAt0830CT (legacy — kept for back-compat)', () => {
  it('returns Mon 08:30 CT for a Wed FOMC (DST → CDT, UTC-5)', () => {
    const result = computeNTradingDaysPriorAt0830CT('2026-06-17', 2)
    expect(result.toISOString()).toBe('2026-06-15T13:30:00.000Z')
  })

  it('skips weekend: Mon event → Thu-prior 08:30 CT', () => {
    const result = computeNTradingDaysPriorAt0830CT('2026-01-05', 2)
    expect(result.toISOString()).toBe('2026-01-01T14:30:00.000Z')
  })
})

describe('computeDayOfNewsHaltWindow (active 2026-05-06+ policy)', () => {
  it('FOMC mid-day (13:00 CDT) → halt 00:00 CDT same day, resume 13:30 CDT', () => {
    const { haltStart, haltEnd } = computeDayOfNewsHaltWindow('2026-06-17', '13:00', 30)
    // 00:00 CDT (UTC-5) → 05:00 UTC
    expect(haltStart.toISOString()).toBe('2026-06-17T05:00:00.000Z')
    // 13:00 CDT + 30 min = 13:30 CDT → 18:30 UTC
    expect(haltEnd.toISOString()).toBe('2026-06-17T18:30:00.000Z')
  })

  it('CPI pre-market (07:30 CDT) → resume at 08:30 CDT market open', () => {
    const { haltStart, haltEnd } = computeDayOfNewsHaltWindow('2026-05-12', '07:30', 30)
    // 00:00 CDT → 05:00 UTC
    expect(haltStart.toISOString()).toBe('2026-05-12T05:00:00.000Z')
    // 08:30 CDT → 13:30 UTC
    expect(haltEnd.toISOString()).toBe('2026-05-12T13:30:00.000Z')
  })

  it('NFP pre-market (07:30 CDT) → resume at 08:30 CDT market open (resumeOffset ignored)', () => {
    const { haltEnd } = computeDayOfNewsHaltWindow('2026-05-08', '07:30', 60)
    // resumeOffset is ignored for pre-market — always resumes at market open
    expect(haltEnd.toISOString()).toBe('2026-05-08T13:30:00.000Z')
  })

  it('Standard time mid-day (13:00 CST) handled correctly (Jan FOMC)', () => {
    const { haltStart, haltEnd } = computeDayOfNewsHaltWindow('2026-01-28', '13:00', 30)
    // 00:00 CST (UTC-6) → 06:00 UTC
    expect(haltStart.toISOString()).toBe('2026-01-28T06:00:00.000Z')
    // 13:30 CST → 19:30 UTC
    expect(haltEnd.toISOString()).toBe('2026-01-28T19:30:00.000Z')
  })

  it('Edge: release exactly at 08:30 CT counts as mid-day (resume +30 min)', () => {
    const { haltEnd } = computeDayOfNewsHaltWindow('2026-06-17', '08:30', 30)
    // 09:00 CDT → 14:00 UTC
    expect(haltEnd.toISOString()).toBe('2026-06-17T14:00:00.000Z')
  })

  it('Edge: release at 08:29 CT is pre-market (resume at 08:30 CT)', () => {
    const { haltEnd } = computeDayOfNewsHaltWindow('2026-06-17', '08:29', 30)
    // 08:30 CDT → 13:30 UTC
    expect(haltEnd.toISOString()).toBe('2026-06-17T13:30:00.000Z')
  })

  it('Custom resume offset is honored for mid-day events', () => {
    const { haltEnd } = computeDayOfNewsHaltWindow('2026-06-17', '13:00', 60)
    // 14:00 CDT → 19:00 UTC
    expect(haltEnd.toISOString()).toBe('2026-06-17T19:00:00.000Z')
  })
})
