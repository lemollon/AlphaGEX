import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'
import {
  ageBadgeClasses,
  calendarDaysBetween,
  ctDateString,
  describePositionAge,
  toDateString,
} from '../position-age'

/**
 * "5 DAYS PAST EXPIRY" IS IMPOSSIBLE TO MISREAD. `Exp: 2026-08-21` IS NOT.
 *
 * SPARK's 8/21, 8/24 and 8/25 positions sat `status = 'open'` for three trading days
 * while the log printed `SETTLED ... pnl=$35.00` once a minute. The page showed the
 * expiration date and left the reader to do the arithmetic. Leron caught it by eye
 * anyway; this gives the eye better data.
 *
 * The watchdog now repairs a stranded position on its own, so this badge is no longer
 * the primary defence — it is what makes the state legible while a repair is in
 * flight, or when the watchdog escalated instead of acting.
 */

/** A Date whose LOCAL fields are the CT wall clock — the getCTNow() convention. */
const ct = (iso: string) => {
  const [d, t = '12:00'] = iso.split('T')
  const [y, m, day] = d.split('-').map(Number)
  const [hh, mm] = t.split(':').map(Number)
  return new Date(y, m - 1, day, hh, mm)
}

describe('the critical case is verbose on purpose', () => {
  it('names the exact number of days for each position that actually stuck', () => {
    const now = ct('2026-08-26')
    expect(describePositionAge('2026-08-21', '2026-08-21', now).label).toBe('5 days past expiry')
    expect(describePositionAge('2026-08-24', '2026-08-24', now).label).toBe('2 days past expiry')
    expect(describePositionAge('2026-08-25', '2026-08-25', now).label).toBe('1 day past expiry')
  })

  it('marks every one of them critical', () => {
    const now = ct('2026-08-26')
    for (const exp of ['2026-08-21', '2026-08-24', '2026-08-25']) {
      expect(describePositionAge(exp, exp, now).tone).toBe('critical')
    }
  })

  it('says "1 day", never "1 days" — an abbreviation is what the eye skips', () => {
    const a = describePositionAge('2026-08-25', '2026-08-25', ct('2026-08-26'))
    expect(a.label).toBe('1 day past expiry')
    expect(a.label).not.toMatch(/1 days/)
    expect(a.label).not.toMatch(/1d\b/)
  })

  it('gives the critical badge a colour that cannot be scrolled past', () => {
    expect(ageBadgeClasses('critical')).toMatch(/red/)
    expect(ageBadgeClasses('critical')).toMatch(/font-semibold/)
    expect(ageBadgeClasses('today')).not.toMatch(/red/)
    expect(ageBadgeClasses('normal')).not.toMatch(/red/)
  })
})

describe('a healthy position is not dressed up as a problem', () => {
  it('expiry day is normal for a 0DTE — flagged, not alarming', () => {
    const a = describePositionAge('2026-08-26', '2026-08-26', ct('2026-08-26'))
    expect(a.tone).toBe('today')
    expect(a.label).toBe('expires today')
    expect(a.daysPastExpiry).toBe(0)
  })

  it('a swing hold with time left reads as ordinary', () => {
    const a = describePositionAge('2026-08-28', '2026-08-25', ct('2026-08-26'))
    expect(a.tone).toBe('normal')
    expect(a.label).toBe('expires in 2 days')
    expect(a.heldLabel).toBe('held 1 day')
  })

  it('a position opened today says so', () => {
    const a = describePositionAge('2026-08-26', '2026-08-26', ct('2026-08-26'))
    expect(a.heldDays).toBe(0)
    expect(a.heldLabel).toBe('opened today')
  })
})

describe('boundaries — the cases you otherwise notice once a year', () => {
  it('rolls over at CT midnight, not at the viewer local midnight', () => {
    // Same instant, both sides of the CT date line. 23:59 is still expiry day;
    // one minute later the position is past expiry and the badge must say so.
    expect(describePositionAge('2026-08-26', '2026-08-26', ct('2026-08-26T23:59')).tone).toBe('today')
    expect(describePositionAge('2026-08-26', '2026-08-26', ct('2026-08-27T00:01')).tone).toBe('critical')
  })

  it('counts across a month boundary', () => {
    expect(describePositionAge('2026-08-31', '2026-08-31', ct('2026-09-02')).label)
      .toBe('2 days past expiry')
  })

  it('counts across a DST change without drifting a day', () => {
    // US DST ends 2026-11-01. A naive ms/86400000 with local Dates can round wrong here.
    expect(describePositionAge('2026-10-30', '2026-10-30', ct('2026-11-03')).label)
      .toBe('4 days past expiry')
  })

  it('reads a pg DATE object the same way as a string', () => {
    // String(new Date('2026-08-24')).slice(0,10) is "Mon Aug 24" — the locale
    // rendering, which matches no date format anywhere in this codebase.
    expect(toDateString(new Date('2026-08-24T00:00:00Z'))).toBe('2026-08-24')
    expect(describePositionAge(new Date('2026-08-24T00:00:00Z'), '2026-08-24', ct('2026-08-26')).label)
      .toBe('2 days past expiry')
  })

  it('handles an ISO timestamp for open_time', () => {
    const a = describePositionAge('2026-08-28', '2026-08-25T15:05:06.686Z', ct('2026-08-26'))
    expect(a.heldDays).toBe(1)
  })

  it('degrades safely on junk rather than inventing a number', () => {
    const a = describePositionAge(null, null, ct('2026-08-26'))
    expect(a.tone).toBe('normal')
    expect(a.label).toBe('expiry unknown')
    expect(a.daysPastExpiry).toBe(0)
    expect(describePositionAge('not-a-date', '', ct('2026-08-26')).label).toBe('expiry unknown')
  })

  it('never reports negative held days from a clock skew', () => {
    expect(describePositionAge('2026-08-28', '2026-08-27', ct('2026-08-26')).heldDays).toBe(0)
  })
})

describe('the primitives', () => {
  it('ctDateString reads the local fields, which ARE the CT wall clock', () => {
    expect(ctDateString(ct('2026-08-26T09:30'))).toBe('2026-08-26')
    expect(ctDateString(ct('2026-01-05T00:00'))).toBe('2026-01-05')
  })

  it('calendarDaysBetween is signed and whole', () => {
    expect(calendarDaysBetween('2026-08-21', '2026-08-26')).toBe(5)
    expect(calendarDaysBetween('2026-08-26', '2026-08-26')).toBe(0)
    expect(calendarDaysBetween('2026-08-28', '2026-08-26')).toBe(-2)
  })
})

describe('it is actually rendered on the position card', () => {
  const SRC = readFileSync(join(__dirname, '..', '..', 'components', 'PositionTable.tsx'), 'utf8')

  it('shows the badge next to the expiration', () => {
    expect(SRC).toMatch(/Exp: \{pos\.expiration\}/)
    expect(SRC).toMatch(/ageBadgeClasses\(age\.tone\)/)
    expect(SRC).toMatch(/age\.tone === 'critical' \? `⚠ \$\{age\.label\}` : age\.label/)
  })

  it('shows how long it has been held in the footer', () => {
    expect(SRC).toMatch(/\{age\.heldLabel\}/)
  })

  it('computes CT now on the CLIENT, so SSR cannot cause a hydration mismatch', () => {
    expect(SRC).toMatch(/const \[ctNow, setCtNow\] = useState<Date \| null>\(null\)/)
    expect(SRC).toMatch(/const age = ctNow \? describePositionAge\(/)
  })

  it('re-ticks, so a page left open overnight rolls into the critical state', () => {
    // This is the exact scenario the badge exists for: the tab was already open when
    // the position went stale.
    expect(SRC).toMatch(/setInterval\(tick, 60_000\)/)
  })
})
