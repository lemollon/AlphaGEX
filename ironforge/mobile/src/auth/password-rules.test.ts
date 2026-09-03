import { describe, it, expect } from 'vitest'
import { checkPassword } from './password-rules'

describe('checkPassword', () => {
  it('rejects a password that fails every rule', () => {
    const { valid, rules } = checkPassword('')
    expect(valid).toBe(false)
    expect(rules).toEqual({
      minLength: false,
      upper: false,
      lower: false,
      number: false,
      special: false,
    })
  })

  it('flags each rule independently', () => {
    // 12 chars, lower + number only — missing upper and special.
    expect(checkPassword('lowercase123').rules).toEqual({
      minLength: true,
      upper: false,
      lower: true,
      number: true,
      special: false,
    })
  })

  it('accepts a password that satisfies all five rules', () => {
    const { valid, rules } = checkPassword('Correct-Horse1')
    expect(valid).toBe(true)
    expect(rules).toEqual({
      minLength: true,
      upper: true,
      lower: true,
      number: true,
      special: true,
    })
  })

  it('is exactly at the 12-character boundary', () => {
    expect(checkPassword('Aa1!aaaaaaaa').rules.minLength).toBe(true) // 12 chars
    expect(checkPassword('Aa1!aaaaaaa').rules.minLength).toBe(false) // 11 chars
  })

  it('treats null/undefined input as an empty string rather than throwing', () => {
    expect(() => checkPassword(undefined as unknown as string)).not.toThrow()
    expect(checkPassword(null as unknown as string).valid).toBe(false)
  })
})
