import { describe, it, expect } from 'vitest'
import {
  addBusinessDays,
  ctDateKey,
  defaultFirstSendDate,
  federalHolidays,
  firstSendAt,
  fromCtWallClock,
  isBusinessDay,
  isDateKey,
  isFederalHoliday,
  moveToBusinessDay,
  nextSendDate,
  weekdayOf,
} from '../schedule'

/** Chicago wall clock → ISO, for readable expectations. */
const ct = (k: string, h = 9, mi = 0) => fromCtWallClock(k, h, mi)

describe('federal holiday rules (computed, not tabled)', () => {
  it('2026: all eleven observed federal holidays', () => {
    const h = federalHolidays(2026)
    expect(Array.from(h.keys()).sort()).toEqual([
      '2026-01-01', // New Year's Day (Thu)
      '2026-01-19', // MLK (3rd Mon Jan)
      '2026-02-16', // Washington's Birthday (3rd Mon Feb)
      '2026-05-25', // Memorial Day (last Mon May)
      '2026-06-19', // Juneteenth (Fri)
      '2026-07-03', // Independence Day — Jul 4 is Saturday → observed Friday
      '2026-09-07', // Labor Day
      '2026-10-12', // Columbus Day (2nd Mon Oct)
      '2026-11-11', // Veterans Day (Wed)
      '2026-11-26', // Thanksgiving (4th Thu)
      '2026-12-25', // Christmas (Fri)
    ])
  })

  it('Sunday holidays observe Monday (Christmas 2022 → Dec 26), Saturday observe Friday (Christmas 2021 → Dec 24)', () => {
    expect(isFederalHoliday('2022-12-26')).toBe(true)
    expect(isFederalHoliday('2022-12-25')).toBe(false)
    expect(isFederalHoliday('2021-12-24')).toBe(true)
  })

  it("New Year's Day on a Saturday is observed on the prior year's Dec 31", () => {
    // 2028-01-01 is a Saturday.
    expect(weekdayOf('2028-01-01')).toBe(6)
    expect(isFederalHoliday('2027-12-31')).toBe(true)
    expect(federalHolidays(2027).has('2027-12-31')).toBe(true)
  })

  it('federal ≠ NYSE: Columbus Day and Veterans Day are closures here; Good Friday is not', () => {
    expect(isBusinessDay('2026-10-12')).toBe(false)
    expect(isBusinessDay('2026-11-11')).toBe(false)
    expect(isBusinessDay('2026-04-03')).toBe(true) // Good Friday 2026 — NYSE closed, federal open
  })

  it('weekends are never business days', () => {
    expect(isBusinessDay('2026-09-12')).toBe(false) // Sat
    expect(isBusinessDay('2026-09-13')).toBe(false) // Sun
    expect(isBusinessDay('2026-09-14')).toBe(true) // Mon
  })
})

describe('business-day arithmetic', () => {
  it('addBusinessDays counts strictly after the start date and skips weekends', () => {
    expect(addBusinessDays('2026-09-11', 1)).toBe('2026-09-14') // Fri → Mon
    expect(addBusinessDays('2026-09-11', 3)).toBe('2026-09-16')
  })

  it('addBusinessDays skips a federal holiday (Labor Day 2026-09-07)', () => {
    expect(addBusinessDays('2026-09-04', 1)).toBe('2026-09-08') // Fri → skip Mon holiday → Tue
    expect(addBusinessDays('2026-09-04', 3)).toBe('2026-09-10')
  })

  it('moveToBusinessDay leaves a business day alone and rolls a weekend/holiday forward', () => {
    expect(moveToBusinessDay('2026-09-08')).toBe('2026-09-08')
    expect(moveToBusinessDay('2026-09-12')).toBe('2026-09-14') // Sat → Mon
    expect(moveToBusinessDay('2026-09-07')).toBe('2026-09-08') // Labor Day → Tue
    expect(moveToBusinessDay('2026-07-03')).toBe('2026-07-06') // Observed Jul 4 (Fri) → Mon
  })

  it('isDateKey rejects malformed and impossible dates', () => {
    expect(isDateKey('2026-09-08')).toBe(true)
    expect(isDateKey('2026-9-8')).toBe(false)
    expect(isDateKey('2026-02-30')).toBe(false)
    expect(isDateKey(20260908)).toBe(false)
  })
})

describe('Chicago wall clock', () => {
  it('round-trips a CDT instant and a CST instant', () => {
    expect(ct('2026-09-08', 9).toISOString()).toBe('2026-09-08T14:00:00.000Z') // CDT = UTC-5
    expect(ct('2026-12-15', 9).toISOString()).toBe('2026-12-15T15:00:00.000Z') // CST = UTC-6
    expect(ctDateKey(new Date('2026-09-08T14:00:00Z'))).toBe('2026-09-08')
  })

  it('23:30 CT is still today in Chicago even though it is tomorrow in UTC', () => {
    const late = ct('2026-09-08', 23, 30)
    expect(late.toISOString()).toBe('2026-09-09T04:30:00.000Z')
    expect(ctDateKey(late)).toBe('2026-09-08')
  })
})

describe('nextSendDate — the kit cadence', () => {
  it('reproduces the kit rollout table exactly (Sep 8 → 11 → 16 → 21 → 24 → 29, 2026)', () => {
    const plan = ['2026-09-08', '2026-09-11', '2026-09-16', '2026-09-21', '2026-09-24', '2026-09-29']
    let at = ct(plan[0], 9)
    for (let i = 1; i < plan.length; i++) {
      at = nextSendDate(at, 3, { sendHour: 9 })
      expect(ctDateKey(at)).toBe(plan[i])
    }
  })

  it('returns the send hour on the due day, whatever time the previous send went out', () => {
    const at = nextSendDate(ct('2026-09-08', 16, 47), 3, { sendHour: 9 })
    expect(at.toISOString()).toBe(ct('2026-09-11', 9).toISOString())
  })

  it('defers across a holiday: a Thursday send before Labor Day lands the following Tuesday', () => {
    // Thu Sep 3 + 3 business days: Fri 4, (Mon 7 = Labor Day skipped), Tue 8, Wed 9.
    expect(ctDateKey(nextSendDate(ct('2026-09-03'), 3, { sendHour: 9 }))).toBe('2026-09-09')
  })

  it('restarts the count from the ACTUAL send, not the planned one', () => {
    // Planned: Wed Sep 16. Suppose the send actually happened Fri Sep 18 (an outage).
    // Next must be 3 business days after Sep 18 (= Wed Sep 23), NOT after Sep 16 (= Mon Sep 21).
    const actual = ct('2026-09-18', 11, 5)
    expect(ctDateKey(nextSendDate(actual, 3, { sendHour: 9 }))).toBe('2026-09-23')
    expect(ctDateKey(nextSendDate(ct('2026-09-16'), 3, { sendHour: 9 }))).toBe('2026-09-21')
  })

  it('a late-night send counts as its Chicago date', () => {
    // 23:30 CT Tue Sep 8 → still Sep 8 → due Fri Sep 11.
    expect(ctDateKey(nextSendDate(ct('2026-09-08', 23, 30), 3, { sendHour: 9 }))).toBe('2026-09-11')
  })

  it('honours the send-hour override', () => {
    const at = nextSendDate(ct('2026-09-08'), 3, { sendHour: 14 })
    expect(at.toISOString()).toBe(ct('2026-09-11', 14).toISOString())
  })
})

describe('backfill helpers', () => {
  it('firstSendAt uses the requested date when it is a business day and defers otherwise', () => {
    expect(firstSendAt('2026-09-09', { sendHour: 9 }).toISOString()).toBe(ct('2026-09-09', 9).toISOString())
    expect(firstSendAt('2026-09-12', { sendHour: 9 }).toISOString()).toBe(ct('2026-09-14', 9).toISOString())
    expect(firstSendAt('2026-09-07', { sendHour: 9 }).toISOString()).toBe(ct('2026-09-08', 9).toISOString())
  })

  it('defaultFirstSendDate is the next business day strictly after today (Chicago)', () => {
    expect(defaultFirstSendDate(ct('2026-09-08', 10))).toBe('2026-09-09')
    expect(defaultFirstSendDate(ct('2026-09-11', 10))).toBe('2026-09-14') // Fri → Mon
    expect(defaultFirstSendDate(ct('2026-09-04', 10))).toBe('2026-09-08') // Fri before Labor Day → Tue
    // 20:00 CT Sep 8 is 01:00 UTC Sep 9 — must still be "after Sep 8", i.e. Sep 9, not Sep 10.
    expect(defaultFirstSendDate(ct('2026-09-08', 20))).toBe('2026-09-09')
  })
})
