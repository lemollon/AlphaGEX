import { describe, it, expect } from 'vitest'
import {
  computeFridayPriorAt0830CT,
  computeEventDayAt,
  computeNTradingDaysPriorAt0830CT,
} from '../halt-window'

describe('computeFridayPriorAt0830CT', () => {
  it('returns previous Friday 08:30 CT for a Wednesday FOMC (DST)', () => {
    // Wed Jun 18 2025 → Fri Jun 13 2025 08:30 CDT = 13:30 UTC
    const result = computeFridayPriorAt0830CT('2025-06-18')
    expect(result.toISOString()).toBe('2025-06-13T13:30:00.000Z')
  })

  it('returns previous Friday for an event on a Monday (standard time)', () => {
    // Mon Jan 5 2026 → Fri Jan 2 2026 08:30 CST = 14:30 UTC
    const result = computeFridayPriorAt0830CT('2026-01-05')
    expect(result.toISOString()).toBe('2026-01-02T14:30:00.000Z')
  })

  it('returns the Friday a week prior when event is itself a Friday', () => {
    // Fri Jul 3 2026 → Fri Jun 26 2026 (strictly before)
    const result = computeFridayPriorAt0830CT('2026-07-03')
    expect(result.toISOString()).toBe('2026-06-26T13:30:00.000Z')
  })

  it('handles cross-year boundary (event on Mon Jan 4 2027)', () => {
    // Mon Jan 4 2027 → Fri Jan 1 2027 08:30 CST = 14:30 UTC
    const result = computeFridayPriorAt0830CT('2027-01-04')
    expect(result.toISOString()).toBe('2027-01-01T14:30:00.000Z')
  })

  it('handles event on a Saturday (custom event)', () => {
    // Sat Mar 7 2026 → Fri Mar 6 2026 08:30 CST = 14:30 UTC
    const result = computeFridayPriorAt0830CT('2026-03-07')
    expect(result.toISOString()).toBe('2026-03-06T14:30:00.000Z')
  })

  it('handles event on a Sunday (custom event)', () => {
    // Sun Mar 8 2026 → Fri Mar 6 2026 08:30 CST = 14:30 UTC
    const result = computeFridayPriorAt0830CT('2026-03-08')
    expect(result.toISOString()).toBe('2026-03-06T14:30:00.000Z')
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

describe('computeNTradingDaysPriorAt0830CT (n=2 — IronForge halt-start)', () => {
  it('returns Mon 08:30 CT for a Wed FOMC (DST → CDT, UTC-5)', () => {
    // Wed Jun 17 2026 → Mon Jun 15 2026 08:30 CDT = 13:30 UTC
    const result = computeNTradingDaysPriorAt0830CT('2026-06-17', 2)
    expect(result.toISOString()).toBe('2026-06-15T13:30:00.000Z')
  })

  it('returns Wed 08:30 CT for a Fri NFP', () => {
    // Fri May 8 2026 → Wed May 6 2026 08:30 CDT = 13:30 UTC
    const result = computeNTradingDaysPriorAt0830CT('2026-05-08', 2)
    expect(result.toISOString()).toBe('2026-05-06T13:30:00.000Z')
  })

  it('skips weekend: Tue CPI → Fri-prior 08:30 CT', () => {
    // Tue May 12 2026 → Fri May 8 2026 08:30 CDT = 13:30 UTC
    const result = computeNTradingDaysPriorAt0830CT('2026-05-12', 2)
    expect(result.toISOString()).toBe('2026-05-08T13:30:00.000Z')
  })

  it('skips weekend: Mon event → Thu-prior 08:30 CT', () => {
    // Mon Jan 5 2026 → Thu Jan 1 2026 08:30 CST = 14:30 UTC
    const result = computeNTradingDaysPriorAt0830CT('2026-01-05', 2)
    expect(result.toISOString()).toBe('2026-01-01T14:30:00.000Z')
  })

  it('handles standard time (no DST)', () => {
    // Wed Feb 11 2026 → Mon Feb 9 2026 08:30 CST = 14:30 UTC
    const result = computeNTradingDaysPriorAt0830CT('2026-02-11', 2)
    expect(result.toISOString()).toBe('2026-02-09T14:30:00.000Z')
  })
})
