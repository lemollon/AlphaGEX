import { describe, it, expect } from 'vitest'
import { daysToMonthNumber } from '../milestones'

/**
 * getMilestones() does real DB I/O, so only the pure day->month math is unit
 * tested here. The boundary cases (day 29->1, day 30->2) are the ones a
 * straight `/30` off-by-one would get wrong.
 */
describe('daysToMonthNumber', () => {
  it('day 0 is month 1', () => {
    expect(daysToMonthNumber(0)).toBe(1)
  })

  it('day 29 is still month 1', () => {
    expect(daysToMonthNumber(29)).toBe(1)
  })

  it('day 30 rolls to month 2', () => {
    expect(daysToMonthNumber(30)).toBe(2)
  })

  it('day 59 is still month 2', () => {
    expect(daysToMonthNumber(59)).toBe(2)
  })

  it('day 60 rolls to month 3', () => {
    expect(daysToMonthNumber(60)).toBe(3)
  })
})
