import { describe, it, expect } from 'vitest'
import { validateSignup, isValidUsername, isValidEmail, isValidPhone, checkPassword, type SignupFields } from './signup-validation'

const VALID: SignupFields = {
  firstName: 'Leron',
  lastName: 'Mollon',
  username: 'leron_m',
  email: 'leron@example.com',
  phone: '(555) 123-4567',
  state: 'WI',
  password: 'Str0ng!Passw0rd',
  confirmPassword: 'Str0ng!Passw0rd',
  ageConfirmed: true,
  noAdviceAcknowledged: true,
  electronicCommConsent: true,
}

describe('validateSignup', () => {
  it('accepts a fully valid submission', () => {
    const r = validateSignup(VALID)
    expect(r.ok).toBe(true)
    expect(r.errors).toEqual({})
  })

  it('requires first and last name', () => {
    const r = validateSignup({ ...VALID, firstName: '', lastName: '  ' })
    expect(r.ok).toBe(false)
    expect(r.errors.firstName).toBeTruthy()
    expect(r.errors.lastName).toBeTruthy()
  })

  it('rejects a username that does not start with a letter', () => {
    const r = validateSignup({ ...VALID, username: '1leron' })
    expect(r.errors.username).toBeTruthy()
  })

  it('rejects a malformed email', () => {
    const r = validateSignup({ ...VALID, email: 'not-an-email' })
    expect(r.errors.email).toBeTruthy()
  })

  it('rejects a phone number that is not 10 (or leading-1 11) digits', () => {
    const r = validateSignup({ ...VALID, phone: '555-1234' })
    expect(r.errors.phone).toBeTruthy()
  })

  it('requires a state', () => {
    const r = validateSignup({ ...VALID, state: '' })
    expect(r.errors.state).toBeTruthy()
  })

  it('rejects a password under 12 characters or missing a class', () => {
    expect(validateSignup({ ...VALID, password: 'short1!', confirmPassword: 'short1!' }).errors.password).toBeTruthy()
    expect(validateSignup({ ...VALID, password: 'alllowercase123', confirmPassword: 'alllowercase123' }).errors.password).toBeTruthy()
  })

  it('rejects mismatched password confirmation', () => {
    const r = validateSignup({ ...VALID, confirmPassword: 'Different!123' })
    expect(r.errors.confirmPassword).toBeTruthy()
  })

  it('requires all three legal acknowledgements independently', () => {
    expect(validateSignup({ ...VALID, ageConfirmed: false }).errors.ageConfirmed).toBeTruthy()
    expect(validateSignup({ ...VALID, noAdviceAcknowledged: false }).errors.noAdviceAcknowledged).toBeTruthy()
    expect(validateSignup({ ...VALID, electronicCommConsent: false }).errors.electronicCommConsent).toBeTruthy()
  })
})

describe('field helpers (mirrors webapp/src/lib/signup-validation.ts)', () => {
  it('isValidUsername', () => {
    expect(isValidUsername('abc')).toBe(true)
    expect(isValidUsername('ab')).toBe(false)
    expect(isValidUsername('_ab')).toBe(false)
  })

  it('isValidEmail', () => {
    expect(isValidEmail('a@b.com')).toBe(true)
    expect(isValidEmail('a@b')).toBe(false)
  })

  it('isValidPhone accepts bare 10-digit and leading-1 11-digit', () => {
    expect(isValidPhone('5551234567')).toBe(true)
    expect(isValidPhone('15551234567')).toBe(true)
    expect(isValidPhone('123')).toBe(false)
  })

  it('checkPassword reports every rule independently', () => {
    const r = checkPassword('Str0ng!Passw0rd')
    expect(r.valid).toBe(true)
    expect(r.rules).toEqual({ minLength: true, upper: true, lower: true, number: true, special: true })
  })
})
