import { describe, it, expect } from 'vitest'
import {
  validateWaitlist,
  normalizePhone,
  CAPITAL_RANGES,
  CONSENT_COPY,
  US_STATES,
  type WaitlistFields,
} from './validation'

const VALID: WaitlistFields = {
  firstName: 'Leron',
  lastName: 'Mollon',
  email: 'leron@example.com',
  phone: '(555) 123-4567',
  city: 'Madison',
  state: 'WI',
  tradingCapitalRange: 'under_5000',
  communicationConsent: true,
}

describe('validateWaitlist', () => {
  it('accepts a fully valid submission', () => {
    expect(validateWaitlist(VALID)).toEqual({})
  })

  it('requires first and last name', () => {
    const e = validateWaitlist({ ...VALID, firstName: '', lastName: '  ' })
    expect(e.firstName).toBeTruthy()
    expect(e.lastName).toBeTruthy()
  })

  it('rejects a name starting with a non-letter', () => {
    expect(validateWaitlist({ ...VALID, firstName: '1eron' }).firstName).toBeTruthy()
  })

  it('rejects a malformed email', () => {
    expect(validateWaitlist({ ...VALID, email: 'not-an-email' }).email).toBeTruthy()
  })

  it('rejects a phone number that is not 10 (or leading-1 11) digits', () => {
    expect(validateWaitlist({ ...VALID, phone: '555-1234' }).phone).toBeTruthy()
  })

  it('requires a city between 1 and 80 characters', () => {
    expect(validateWaitlist({ ...VALID, city: '' }).city).toBeTruthy()
    expect(validateWaitlist({ ...VALID, city: 'a'.repeat(81) }).city).toBeTruthy()
    expect(validateWaitlist({ ...VALID, city: 'a'.repeat(80) }).city).toBeUndefined()
  })

  it('requires a 2-character state', () => {
    expect(validateWaitlist({ ...VALID, state: '' }).state).toBeTruthy()
    expect(validateWaitlist({ ...VALID, state: 'WIS' }).state).toBeTruthy()
    expect(validateWaitlist({ ...VALID, state: 'W' }).state).toBeTruthy()
  })

  it('requires a recognized capital range', () => {
    expect(validateWaitlist({ ...VALID, tradingCapitalRange: '' }).tradingCapitalRange).toBeTruthy()
    expect(validateWaitlist({ ...VALID, tradingCapitalRange: 'yacht_money' }).tradingCapitalRange).toBeTruthy()
  })

  it('requires consent to be explicitly true, not just truthy', () => {
    expect(validateWaitlist({ ...VALID, communicationConsent: false }).communicationConsent).toBeTruthy()
    // @ts-expect-error — exercising a non-boolean truthy value the server would also reject
    expect(validateWaitlist({ ...VALID, communicationConsent: 1 }).communicationConsent).toBeTruthy()
  })
})

describe('normalizePhone (mirrors webapp/src/lib/waitlist.ts)', () => {
  it('accepts a bare 10-digit number', () => {
    expect(normalizePhone('5551234567')).toBe('+15551234567')
  })

  it('accepts a leading-1 11-digit number', () => {
    expect(normalizePhone('15551234567')).toBe('+15551234567')
  })

  it('strips formatting before counting digits', () => {
    expect(normalizePhone('(555) 123-4567')).toBe('+15551234567')
  })

  it('returns empty string for anything else', () => {
    expect(normalizePhone('123')).toBe('')
    expect(normalizePhone('25551234567')).toBe('') // 11 digits, not leading 1
    expect(normalizePhone('')).toBe('')
  })
})

describe('CAPITAL_RANGES', () => {
  it('has exactly the five approved ranges, in order', () => {
    expect(CAPITAL_RANGES.map((r) => r.value)).toEqual([
      'under_5000',
      '5000_10000',
      '10000_25000',
      '25000_50000',
      '50000_plus',
    ])
  })

  it('never labels a range as income', () => {
    for (const r of CAPITAL_RANGES) {
      expect(r.label.toLowerCase()).not.toContain('income')
    }
  })
})

describe('CONSENT_COPY', () => {
  it('matches the server copy verbatim', () => {
    expect(CONSENT_COPY).toBe(
      'I agree to receive IronForge launch updates and account-related communications by email and phone.',
    )
  })
})

describe('US_STATES', () => {
  it('includes DC and exactly 51 two-letter entries with no duplicates', () => {
    expect(US_STATES).toHaveLength(51)
    expect(new Set(US_STATES).size).toBe(51)
    expect(US_STATES.every((s) => /^[A-Z]{2}$/.test(s))).toBe(true)
    expect(US_STATES).toContain('DC')
    expect(US_STATES).toContain('WI')
  })
})
