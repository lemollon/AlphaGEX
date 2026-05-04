import { describe, it, expect } from 'vitest'
import { parseFinnhubFomcEvents } from '../finnhub'

describe('parseFinnhubFomcEvents', () => {
  it('returns FOMC events from the US economic calendar', () => {
    const json = {
      economicCalendar: [
        { country: 'US', event: 'FOMC Meeting', impact: 'high', time: '2025-06-18 18:00:00', actual: null },
        { country: 'US', event: 'CPI YoY', impact: 'high', time: '2025-06-12 12:30:00', actual: null },
        { country: 'EU', event: 'ECB Rate Decision', impact: 'high', time: '2025-06-05 11:45:00', actual: null },
        { country: 'US', event: 'Federal Funds Target Rate', impact: 'high', time: '2025-07-30 18:00:00', actual: null },
      ],
    }
    const result = parseFinnhubFomcEvents(json)
    expect(result).toHaveLength(2)
    expect(result[0]).toMatchObject({ date: '2025-06-18', time: '13:00', title: 'FOMC Meeting' })
    expect(result[1]).toMatchObject({ date: '2025-07-30', time: '13:00', title: 'Federal Funds Target Rate' })
  })

  it('matches Fed Interest Rate variants case-insensitively', () => {
    const json = {
      economicCalendar: [
        { country: 'US', event: 'fed interest rate decision', impact: 'high', time: '2025-09-17 18:00:00' },
      ],
    }
    expect(parseFinnhubFomcEvents(json)).toHaveLength(1)
  })

  it('skips non-US events', () => {
    const json = {
      economicCalendar: [
        { country: 'JP', event: 'BOJ Rate Decision', impact: 'high', time: '2025-06-17 03:00:00' },
      ],
    }
    expect(parseFinnhubFomcEvents(json)).toHaveLength(0)
  })

  it('skips low/medium impact events even if title matches', () => {
    const json = {
      economicCalendar: [
        { country: 'US', event: 'FOMC Member Powell Speaks', impact: 'medium', time: '2025-06-15 14:00:00' },
      ],
    }
    expect(parseFinnhubFomcEvents(json)).toHaveLength(0)
  })

  it('returns empty array for missing / malformed payload', () => {
    expect(parseFinnhubFomcEvents({})).toEqual([])
    expect(parseFinnhubFomcEvents({ economicCalendar: null })).toEqual([])
    expect(parseFinnhubFomcEvents(null as any)).toEqual([])
  })

  it('converts Finnhub UTC time to CT date and HH:MM (DST)', () => {
    // 2025-06-18 18:00 UTC = 13:00 CDT (UTC-5)
    const json = {
      economicCalendar: [
        { country: 'US', event: 'FOMC Meeting', impact: 'high', time: '2025-06-18 18:00:00' },
      ],
    }
    const r = parseFinnhubFomcEvents(json)
    expect(r[0]).toMatchObject({ date: '2025-06-18', time: '13:00' })
  })

  it('converts Finnhub UTC time to CT date and HH:MM (standard time)', () => {
    // 2026-01-28 19:00 UTC = 13:00 CST (UTC-6)
    const json = {
      economicCalendar: [
        { country: 'US', event: 'FOMC Meeting', impact: 'high', time: '2026-01-28 19:00:00' },
      ],
    }
    const r = parseFinnhubFomcEvents(json)
    expect(r[0]).toMatchObject({ date: '2026-01-28', time: '13:00' })
  })
})
