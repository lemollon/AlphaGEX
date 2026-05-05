import { describe, it, expect } from 'vitest'
import { parseFinnhubFomcEvents } from '../finnhub'

describe('parseFinnhubFomcEvents — FOMC', () => {
  it('returns FOMC events from the US economic calendar', () => {
    const json = {
      economicCalendar: [
        { country: 'US', event: 'FOMC Meeting', impact: 'high', time: '2025-06-18 18:00:00', actual: null },
        { country: 'EU', event: 'ECB Rate Decision', impact: 'high', time: '2025-06-05 11:45:00', actual: null },
        { country: 'US', event: 'Federal Funds Target Rate', impact: 'high', time: '2025-07-30 18:00:00', actual: null },
      ],
    }
    const result = parseFinnhubFomcEvents(json)
    expect(result).toHaveLength(2)
    expect(result[0]).toMatchObject({ date: '2025-06-18', time: '13:00', title: 'FOMC Meeting', event_type: 'FOMC' })
    expect(result[1]).toMatchObject({ date: '2025-07-30', time: '13:00', title: 'Federal Funds Target Rate', event_type: 'FOMC' })
  })

  it('matches Fed Interest Rate variants case-insensitively', () => {
    const json = {
      economicCalendar: [
        { country: 'US', event: 'fed interest rate decision', impact: 'high', time: '2025-09-17 18:00:00' },
      ],
    }
    const r = parseFinnhubFomcEvents(json)
    expect(r).toHaveLength(1)
    expect(r[0].event_type).toBe('FOMC')
  })
})

describe('parseFinnhubFomcEvents — CPI/PPI/NFP', () => {
  it('matches CPI variants', () => {
    const json = {
      economicCalendar: [
        { country: 'US', event: 'CPI YoY', impact: 'high', time: '2026-06-12 12:30:00' },
        { country: 'US', event: 'Core CPI MoM', impact: 'high', time: '2026-06-12 12:30:00' },
        { country: 'US', event: 'Consumer Price Index', impact: 'high', time: '2026-07-15 12:30:00' },
      ],
    }
    const r = parseFinnhubFomcEvents(json)
    expect(r).toHaveLength(3)
    for (const e of r) expect(e.event_type).toBe('CPI')
  })

  it('matches PPI variants', () => {
    const json = {
      economicCalendar: [
        { country: 'US', event: 'PPI MoM', impact: 'high', time: '2026-06-13 12:30:00' },
        { country: 'US', event: 'Producer Price Index', impact: 'high', time: '2026-07-16 12:30:00' },
      ],
    }
    const r = parseFinnhubFomcEvents(json)
    expect(r).toHaveLength(2)
    for (const e of r) expect(e.event_type).toBe('PPI')
  })

  it('matches NFP variants', () => {
    const json = {
      economicCalendar: [
        { country: 'US', event: 'Nonfarm Payrolls', impact: 'high', time: '2026-06-05 12:30:00' },
        { country: 'US', event: 'Non-Farm Payrolls', impact: 'high', time: '2026-07-03 12:30:00' },
        { country: 'US', event: 'Employment Situation', impact: 'high', time: '2026-08-07 12:30:00' },
      ],
    }
    const r = parseFinnhubFomcEvents(json)
    expect(r).toHaveLength(3)
    for (const e of r) expect(e.event_type).toBe('NFP')
  })

  it('does not classify a CPI entry that says "FOMC" as CPI (FOMC takes precedence)', () => {
    const json = {
      economicCalendar: [
        { country: 'US', event: 'FOMC Statement on CPI', impact: 'high', time: '2026-06-12 18:00:00' },
      ],
    }
    const r = parseFinnhubFomcEvents(json)
    expect(r).toHaveLength(1)
    expect(r[0].event_type).toBe('FOMC')
  })

  it('avoids false positives on CPIA, NFPC etc. via word-boundary on bare acronyms', () => {
    const json = {
      economicCalendar: [
        { country: 'US', event: 'NFPC Index', impact: 'high', time: '2026-06-05 12:30:00' },
        { country: 'US', event: 'CPIA Score', impact: 'high', time: '2026-06-12 12:30:00' },
      ],
    }
    expect(parseFinnhubFomcEvents(json)).toHaveLength(0)
  })
})

describe('parseFinnhubFomcEvents — exclusions', () => {
  it('skips non-US events', () => {
    const json = {
      economicCalendar: [
        { country: 'JP', event: 'BOJ Rate Decision', impact: 'high', time: '2025-06-17 03:00:00' },
        { country: 'GB', event: 'CPI YoY', impact: 'high', time: '2026-06-18 06:00:00' },
      ],
    }
    expect(parseFinnhubFomcEvents(json)).toHaveLength(0)
  })

  it('skips low/medium impact events even if title matches', () => {
    const json = {
      economicCalendar: [
        { country: 'US', event: 'CPI YoY', impact: 'medium', time: '2026-06-12 12:30:00' },
      ],
    }
    expect(parseFinnhubFomcEvents(json)).toHaveLength(0)
  })

  it('excludes "FOMC Minutes" releases (summaries of prior meetings, not rate decisions)', () => {
    const json = {
      economicCalendar: [
        { country: 'US', event: 'FOMC Minutes', impact: 'high', time: '2026-05-20 19:00:00' },
        { country: 'US', event: 'FOMC Meeting', impact: 'high', time: '2026-06-17 18:00:00' },
      ],
    }
    const r = parseFinnhubFomcEvents(json)
    expect(r).toHaveLength(1)
    expect(r[0].title).toBe('FOMC Meeting')
  })

  it('excludes Powell speeches, projections, testimony, revisions even at high impact', () => {
    const json = {
      economicCalendar: [
        { country: 'US', event: 'FOMC Member Powell Speaks', impact: 'high', time: '2026-05-15 14:00:00' },
        { country: 'US', event: 'FOMC Economic Projections', impact: 'high', time: '2026-05-15 18:00:00' },
        { country: 'US', event: 'Fed Chair Testimony', impact: 'high', time: '2026-05-15 14:00:00' },
        { country: 'US', event: 'CPI YoY (Revised)', impact: 'high', time: '2026-06-12 12:30:00' },
      ],
    }
    expect(parseFinnhubFomcEvents(json)).toHaveLength(0)
  })

  it('returns empty array for missing / malformed payload', () => {
    expect(parseFinnhubFomcEvents({})).toEqual([])
    expect(parseFinnhubFomcEvents({ economicCalendar: null })).toEqual([])
    expect(parseFinnhubFomcEvents(null as any)).toEqual([])
  })
})

describe('parseFinnhubFomcEvents — time conversion', () => {
  it('converts Finnhub UTC time to CT date and HH:MM (DST)', () => {
    const json = {
      economicCalendar: [
        { country: 'US', event: 'FOMC Meeting', impact: 'high', time: '2025-06-18 18:00:00' },
      ],
    }
    expect(parseFinnhubFomcEvents(json)[0]).toMatchObject({ date: '2025-06-18', time: '13:00' })
  })

  it('converts Finnhub UTC time to CT date and HH:MM (standard time)', () => {
    const json = {
      economicCalendar: [
        { country: 'US', event: 'FOMC Meeting', impact: 'high', time: '2026-01-28 19:00:00' },
      ],
    }
    expect(parseFinnhubFomcEvents(json)[0]).toMatchObject({ date: '2026-01-28', time: '13:00' })
  })
})
