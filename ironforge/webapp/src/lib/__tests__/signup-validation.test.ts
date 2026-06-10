import { describe, it, expect } from 'vitest'
import {
  normalizeEmail,
  isValidEmail,
  normalizePhone,
  isValidPhone,
  checkPassword,
  validateSignup,
  type SignupPayload,
} from '@/lib/signup-validation'

function validPayload(): SignupPayload {
  return {
    firstName: 'Ada',
    lastName: 'Lovelace',
    email: 'Ada@Example.com',
    phone: '(555) 123-4567',
    state: 'CA',
    password: 'Forge!Strong9x',
    confirmPassword: 'Forge!Strong9x',
    referralCode: 'launch24',
    ageConfirmed: true,
    noAdviceAcknowledged: true,
    electronicCommConsent: true,
  }
}

describe('normalizeEmail', () => {
  it('trims and lowercases', () => {
    expect(normalizeEmail('  Ada@Example.COM ')).toBe('ada@example.com')
  })
})

describe('isValidEmail', () => {
  it('accepts a normal address', () => {
    expect(isValidEmail('ada@example.com')).toBe(true)
  })
  it('rejects a missing domain', () => {
    expect(isValidEmail('ada@')).toBe(false)
  })
  it('rejects whitespace-only', () => {
    expect(isValidEmail('   ')).toBe(false)
  })
})

describe('normalizePhone', () => {
  it('formats a 10-digit US number to E.164', () => {
    expect(normalizePhone('(555) 123-4567')).toBe('+15551234567')
  })
  it('keeps an existing 11-digit US number with country code', () => {
    expect(normalizePhone('1-555-123-4567')).toBe('+15551234567')
  })
})

describe('isValidPhone', () => {
  it('accepts a 10-digit US number', () => {
    expect(isValidPhone('(555) 123-4567')).toBe(true)
  })
  it('rejects too-few digits', () => {
    expect(isValidPhone('123')).toBe(false)
  })
})

describe('checkPassword', () => {
  it('passes when all five rules are met', () => {
    const r = checkPassword('Forge!Strong9x')
    expect(r.valid).toBe(true)
    expect(r.rules).toEqual({
      minLength: true,
      upper: true,
      lower: true,
      number: true,
      special: true,
    })
  })
  it('fails a short password and flags minLength false', () => {
    const r = checkPassword('Ab1!')
    expect(r.valid).toBe(false)
    expect(r.rules.minLength).toBe(false)
  })
  it('fails when missing a special character', () => {
    const r = checkPassword('ForgeStrong9xx')
    expect(r.valid).toBe(false)
    expect(r.rules.special).toBe(false)
  })
})

describe('validateSignup', () => {
  it('accepts a fully valid payload and returns normalized fields', () => {
    const r = validateSignup(validPayload())
    expect(r.ok).toBe(true)
    expect(r.errors).toEqual({})
    expect(r.normalized.email).toBe('ada@example.com')
    expect(r.normalized.phone).toBe('+15551234567')
    expect(r.normalized.referralCode).toBe('LAUNCH24')
  })

  it('requires first and last name', () => {
    const r = validateSignup({ ...validPayload(), firstName: '  ', lastName: '' })
    expect(r.ok).toBe(false)
    expect(r.errors.firstName).toBeTruthy()
    expect(r.errors.lastName).toBeTruthy()
  })

  it('rejects an invalid email', () => {
    const r = validateSignup({ ...validPayload(), email: 'nope' })
    expect(r.ok).toBe(false)
    expect(r.errors.email).toBeTruthy()
  })

  it('rejects an invalid phone', () => {
    const r = validateSignup({ ...validPayload(), phone: '12' })
    expect(r.ok).toBe(false)
    expect(r.errors.phone).toBeTruthy()
  })

  it('requires a state selection', () => {
    const r = validateSignup({ ...validPayload(), state: '' })
    expect(r.ok).toBe(false)
    expect(r.errors.state).toBeTruthy()
  })

  it('rejects a weak password', () => {
    const r = validateSignup({ ...validPayload(), password: 'weak', confirmPassword: 'weak' })
    expect(r.ok).toBe(false)
    expect(r.errors.password).toBeTruthy()
  })

  it('rejects mismatched confirm password', () => {
    const r = validateSignup({ ...validPayload(), confirmPassword: 'Different!9xZ' })
    expect(r.ok).toBe(false)
    expect(r.errors.confirmPassword).toBeTruthy()
  })

  it('treats referral code as optional', () => {
    const r = validateSignup({ ...validPayload(), referralCode: '' })
    expect(r.ok).toBe(true)
    expect(r.normalized.referralCode).toBe('')
  })

  it('requires the age checkbox', () => {
    const r = validateSignup({ ...validPayload(), ageConfirmed: false })
    expect(r.ok).toBe(false)
    expect(r.errors.ageConfirmed).toBeTruthy()
  })

  it('requires the no-advice checkbox', () => {
    const r = validateSignup({ ...validPayload(), noAdviceAcknowledged: false })
    expect(r.ok).toBe(false)
    expect(r.errors.noAdviceAcknowledged).toBeTruthy()
  })

  it('requires the electronic-communications checkbox', () => {
    const r = validateSignup({ ...validPayload(), electronicCommConsent: false })
    expect(r.ok).toBe(false)
    expect(r.errors.electronicCommConsent).toBeTruthy()
  })
})
