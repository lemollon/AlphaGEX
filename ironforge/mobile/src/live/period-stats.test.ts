import { describe, it, expect } from 'vitest'
import { formatPeriodValue, periodTone } from '@/live/period-stats'
import type { HomeData } from '@/api/types'

describe('formatPeriodValue', () => {
  it('shows a dash ONLY when the value could not be loaded', () => {
    expect(formatPeriodValue(null)).toBe('—')
    expect(formatPeriodValue(undefined)).toBe('—')
  })

  it('shows $0 — never a dash — when nothing closed in the window', () => {
    expect(formatPeriodValue(0)).toBe('$0')
  })

  it('rounds to whole dollars with no decimals', () => {
    expect(formatPeriodValue(36.4)).toBe('+$36')
    expect(formatPeriodValue(36.6)).toBe('+$37')
  })

  it('signs a gain with + and a loss with a real minus sign', () => {
    expect(formatPeriodValue(36)).toBe('+$36')
    expect(formatPeriodValue(-42)).toBe('−$42')
  })

  it('never signs zero', () => {
    expect(formatPeriodValue(0)).not.toMatch(/^[+−-]/)
  })
})

describe('periodTone', () => {
  it('is na only for missing data, not for zero', () => {
    expect(periodTone(null)).toBe('na')
    expect(periodTone(undefined)).toBe('na')
    expect(periodTone(0)).toBe('zero')
  })

  it('is pos/neg by sign after rounding', () => {
    expect(periodTone(0.4)).toBe('zero') // rounds to 0
    expect(periodTone(36)).toBe('pos')
    expect(periodTone(-42)).toBe('neg')
  })
})

/**
 * Type-level guard against the exact bug this fix closes: mobile's HomeData
 * hand-mirrors webapp/src/lib/live/home.ts's getHomeData() return shape (no
 * shared package between the two apps). If a future change nests, renames, or
 * drops a field on either side without updating the other, this fixture stops
 * satisfying HomeData and `npx tsc --noEmit` fails — the same check the mock
 * flat `week_income` shape would have failed against the route's real nested
 * `wealth.weekly_income`. Keep in sync with
 * webapp/src/lib/live/__tests__/home.test.ts's HOME_DATA_* key lists.
 */
const _homeDataContract = {
  wealth: {
    weekly_income: 36,
    monthly_income: 210,
    lifetime_income: 512.5,
    lifetime_return_pct: 5.13,
  },
  recent_trades: [],
  yesterday_trades: 2,
  as_of: '2026-09-04T00:00:00.000Z',
} satisfies HomeData

describe('HomeData contract', () => {
  it('the mobile type accepts the route\'s real nested wire shape', () => {
    expect(_homeDataContract.wealth.weekly_income).toBe(36)
  })
})
