import { describe, it, expect } from 'vitest'
import { isValidVerifyCode, sanitizeCodeInput } from './verify-code-validation'

describe('isValidVerifyCode', () => {
  it('accepts a 6-digit code', () => {
    expect(isValidVerifyCode('123456')).toBe(true)
  })
  it('accepts a zero-padded 6-digit code', () => {
    expect(isValidVerifyCode('000042')).toBe(true)
  })
  it('rejects fewer than 6 digits', () => {
    expect(isValidVerifyCode('12345')).toBe(false)
  })
  it('rejects more than 6 digits', () => {
    expect(isValidVerifyCode('1234567')).toBe(false)
  })
  it('rejects non-digit characters', () => {
    expect(isValidVerifyCode('12a456')).toBe(false)
  })
  it('rejects empty input', () => {
    expect(isValidVerifyCode('')).toBe(false)
  })
  it('trims surrounding whitespace before checking', () => {
    expect(isValidVerifyCode(' 123456 ')).toBe(true)
  })
})

describe('sanitizeCodeInput', () => {
  it('strips non-digit characters', () => {
    expect(sanitizeCodeInput('1a2b3c')).toBe('123')
  })
  it('caps at the given length', () => {
    expect(sanitizeCodeInput('1234567890', 6)).toBe('123456')
  })
  it('defaults to length 6', () => {
    expect(sanitizeCodeInput('1234567890')).toBe('123456')
  })
  it('passes through a clean 6-digit code unchanged', () => {
    expect(sanitizeCodeInput('048213')).toBe('048213')
  })
})
