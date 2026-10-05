import { describe, it, expect } from 'vitest'
import { greetingForHour } from './greeting'

describe('greetingForHour', () => {
  it('is morning from midnight up to (not including) noon', () => {
    expect(greetingForHour(0)).toBe('Good morning')
    expect(greetingForHour(11)).toBe('Good morning')
  })

  it('is afternoon from noon up to (not including) 5pm', () => {
    expect(greetingForHour(12)).toBe('Good afternoon')
    expect(greetingForHour(16)).toBe('Good afternoon')
  })

  it('is evening from 5pm through the end of the day', () => {
    expect(greetingForHour(17)).toBe('Good evening')
    expect(greetingForHour(23)).toBe('Good evening')
  })
})
