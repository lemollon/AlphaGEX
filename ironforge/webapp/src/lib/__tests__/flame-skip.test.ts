/**
 * FLAME_SKIP_WEEKDAYS / FLAME_SKIP_SCOPE — pins the off-by-default behavior,
 * the customers-vs-all scope split, and the America/Chicago weekday
 * resolution (including the UTC-day-boundary edge case).
 */
import { describe, it, expect, afterEach } from 'vitest'
import {
  getFlameSkipWeekdays,
  getFlameSkipScope,
  weekdayAbbrevFromDow,
  centralWeekdayAbbrev,
  isWeekdayInSkipSet,
  isFlameSkipWeekday,
  shouldSkipAccountForWeekday,
  weekdaySkipLogTag,
} from '../flame-skip'

const ENV_KEYS = ['FLAME_SKIP_WEEKDAYS', 'FLAME_SKIP_SCOPE'] as const

afterEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
})

describe('getFlameSkipWeekdays — env parsing, off by default', () => {
  it('unset -> empty set (no skipping, byte-for-byte prior behavior)', () => {
    delete process.env.FLAME_SKIP_WEEKDAYS
    expect(getFlameSkipWeekdays().size).toBe(0)
  })
  it('empty string -> empty set', () => {
    process.env.FLAME_SKIP_WEEKDAYS = '   '
    expect(getFlameSkipWeekdays().size).toBe(0)
  })
  it('"wed,thu" -> {wed, thu}', () => {
    process.env.FLAME_SKIP_WEEKDAYS = 'wed,thu'
    expect(getFlameSkipWeekdays()).toEqual(new Set(['wed', 'thu']))
  })
  it('is case-insensitive and tolerates full names / spacing', () => {
    process.env.FLAME_SKIP_WEEKDAYS = ' Wednesday, THURSDAY '
    expect(getFlameSkipWeekdays()).toEqual(new Set(['wed', 'thu']))
  })
  it('drops unrecognized tokens rather than throwing', () => {
    process.env.FLAME_SKIP_WEEKDAYS = 'wed,bogus'
    expect(getFlameSkipWeekdays()).toEqual(new Set(['wed']))
  })
})

describe('getFlameSkipScope — defaults to customers', () => {
  it('unset -> customers', () => {
    delete process.env.FLAME_SKIP_SCOPE
    expect(getFlameSkipScope()).toBe('customers')
  })
  it('"all" -> all', () => {
    process.env.FLAME_SKIP_SCOPE = 'all'
    expect(getFlameSkipScope()).toBe('all')
  })
  it('any other value (typo) fails closed to customers', () => {
    process.env.FLAME_SKIP_SCOPE = 'ALL_ACCOUNTS'
    expect(getFlameSkipScope()).toBe('customers')
  })
})

describe('weekdayAbbrevFromDow — scanner.ts ct.getDay() convention', () => {
  it('maps 0..6 to sun..sat', () => {
    expect(['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'].map((_, i) => weekdayAbbrevFromDow(i)))
      .toEqual(['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'])
  })
})

describe('centralWeekdayAbbrev — real Date instant, America/Chicago', () => {
  it('a plain Wednesday noon UTC in January (CST, no DST ambiguity) reads as wed', () => {
    expect(centralWeekdayAbbrev(new Date('2026-01-07T18:00:00Z'))).toBe('wed')
  })
  it('TIMEZONE EDGE: UTC Thursday 01:00 is Wednesday 19:00 CT — must read as wed, not thu', () => {
    expect(centralWeekdayAbbrev(new Date('2026-01-08T01:00:00Z'))).toBe('wed')
  })
  it('a few hours later, same UTC calendar day, has rolled into CT Thursday', () => {
    // 2026-01-08T07:00:00Z = Thursday 01:00 CT
    expect(centralWeekdayAbbrev(new Date('2026-01-08T07:00:00Z'))).toBe('thu')
  })
})

describe('isFlameSkipWeekday / isWeekdayInSkipSet', () => {
  it('unset env -> never skips, any day', () => {
    delete process.env.FLAME_SKIP_WEEKDAYS
    expect(isFlameSkipWeekday(new Date('2026-01-07T18:00:00Z'))).toBe(false) // Wed
    expect(isFlameSkipWeekday(new Date('2026-01-08T18:00:00Z'))).toBe(false) // Thu
  })
  it('"wed,thu" skips Wednesday and Thursday', () => {
    process.env.FLAME_SKIP_WEEKDAYS = 'wed,thu'
    expect(isFlameSkipWeekday(new Date('2026-01-07T18:00:00Z'))).toBe(true) // Wed
    expect(isFlameSkipWeekday(new Date('2026-01-08T18:00:00Z'))).toBe(true) // Thu
  })
  it('Friday is unaffected by a wed,thu skip list', () => {
    process.env.FLAME_SKIP_WEEKDAYS = 'wed,thu'
    expect(isFlameSkipWeekday(new Date('2026-01-09T18:00:00Z'))).toBe(false) // Fri
  })
  it('honors the UTC-day-boundary edge through the full env-driven path', () => {
    process.env.FLAME_SKIP_WEEKDAYS = 'wed,thu'
    // UTC Thursday 01:00 = Wednesday 19:00 CT -> matches "wed", is a skip day
    expect(isFlameSkipWeekday(new Date('2026-01-08T01:00:00Z'))).toBe(true)
  })
  it('isWeekdayInSkipSet with an explicit empty set never skips even on a listed day', () => {
    expect(isWeekdayInSkipSet('wed', new Set())).toBe(false)
  })
})

describe('shouldSkipAccountForWeekday — scope split', () => {
  it('weekday not skipped -> no account is ever skipped, regardless of scope', () => {
    expect(shouldSkipAccountForWeekday('sandbox', false, 'customers')).toBe(false)
    expect(shouldSkipAccountForWeekday('production', false, 'all')).toBe(false)
  })
  it('scope=customers (default): sandbox is skipped, production is NOT', () => {
    expect(shouldSkipAccountForWeekday('sandbox', true, 'customers')).toBe(true)
    expect(shouldSkipAccountForWeekday(undefined, true, 'customers')).toBe(true) // undefined == sandbox
    expect(shouldSkipAccountForWeekday('production', true, 'customers')).toBe(false)
  })
  it('scope=all: production is ALSO skipped', () => {
    expect(shouldSkipAccountForWeekday('production', true, 'all')).toBe(true)
    expect(shouldSkipAccountForWeekday('sandbox', true, 'all')).toBe(true)
  })
  it('defaults scope from the environment when not passed explicitly', () => {
    delete process.env.FLAME_SKIP_SCOPE
    expect(shouldSkipAccountForWeekday('production', true)).toBe(false) // customers default
    process.env.FLAME_SKIP_SCOPE = 'all'
    expect(shouldSkipAccountForWeekday('production', true)).toBe(true)
  })
})

describe('weekdaySkipLogTag', () => {
  it('matches the exact spec format skip:weekday_skip(wed)', () => {
    expect(weekdaySkipLogTag('wed')).toBe('skip:weekday_skip(wed)')
    expect(weekdaySkipLogTag('thu')).toBe('skip:weekday_skip(thu)')
  })
})
