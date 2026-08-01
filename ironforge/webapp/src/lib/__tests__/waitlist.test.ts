import { describe, it, expect } from 'vitest'
import { validateWaitlist, normalizePhone, validateWaitlistClient, CAPITAL_RANGES } from '../waitlist'

const valid = {
  firstName: 'Logan', lastName: 'Pennington', email: 'Logan@Example.com',
  phone: '(281) 555-1212', city: 'Fulshear', state: 'tx',
  tradingCapitalRange: '25000_50000', communicationConsent: true,
}

describe('normalizePhone', () => {
  it('renders US numbers as E.164', () => {
    expect(normalizePhone('(281) 555-1212')).toBe('+12815551212')
    expect(normalizePhone('12815551212')).toBe('+12815551212')
  })
  it('returns empty for unresolvable input', () => {
    expect(normalizePhone('123')).toBe('')
    expect(normalizePhone('')).toBe('')
  })
})

describe('waitlist validation', () => {
  it('accepts and normalizes a valid submission', () => {
    const r = validateWaitlist(valid)
    expect(r.ok).toBe(true)
    if (r.ok) {
      expect(r.data.email).toBe('logan@example.com')
      expect(r.data.phone).toBe('+12815551212')
      expect(r.data.state).toBe('TX')
    }
  })
  it('requires consent = true', () => {
    const r = validateWaitlistClient({ ...valid, communicationConsent: false })
    expect(r.communicationConsent).toBeTruthy()
  })
  it('rejects a bad email and a bad phone with field messages', () => {
    const r = validateWaitlist({ ...valid, email: 'nope', phone: '123' })
    expect(r.ok).toBe(false)
    if (!r.ok) {
      expect(r.fieldErrors.email).toBeTruthy()
      expect(r.fieldErrors.phone).toBeTruthy()
    }
  })
  it('rejects an unknown capital range', () => {
    const r = validateWaitlist({ ...valid, tradingCapitalRange: 'infinity' })
    expect(r.ok).toBe(false)
  })
  it('the 5 approved ranges are the enum', () => {
    expect(CAPITAL_RANGES.map((r) => r.value)).toEqual(['under_5000', '5000_10000', '10000_25000', '25000_50000', '50000_plus'])
  })
})
