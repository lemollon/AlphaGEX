import { describe, it, expect } from 'vitest'
import {
  evaluateAccountEligibility, maskAccountNumber, normalizeInstitutionSlug,
  MIN_OPTIONS_LEVEL, MIN_BUYING_POWER,
} from '../eligibility'

const OK = {
  externalRef: '6YB712345',
  accountType: 'margin',
  optionsLevel: MIN_OPTIONS_LEVEL,
  status: 'active',
  buyingPower: 5000,
  brokerBlocked: false,
}

describe('account eligibility (§3 BROKER-02)', () => {
  it('a fully qualified margin account is eligible (options verified by broker level)', () => {
    expect(evaluateAccountEligibility(OK)).toEqual({ eligible: true, optionsVerification: 'broker_level' })
  })

  it('FAILS CLOSED on empty facts — unknown is never assumed tradeable', () => {
    const v = evaluateAccountEligibility({})
    expect(v.eligible).toBe(false)
    expect(v.code).toBeTruthy()
  })

  it.each([
    ['unknown options level', { optionsLevel: null }, 'OPTIONS_APPROVAL'],
    ['too-low options level', { optionsLevel: MIN_OPTIONS_LEVEL - 1 }, 'OPTIONS_APPROVAL'],
    ['unknown account type', { accountType: null }, 'ACCOUNT_TYPE'],
    ['cash account', { accountType: 'cash' }, 'ACCOUNT_TYPE'],
    ['closed account', { status: 'closed' }, 'ACCOUNT_STATUS'],
    ['unknown buying power', { buyingPower: null }, 'BUYING_POWER'],
    ['insufficient buying power', { buyingPower: MIN_BUYING_POWER - 1 }, 'BUYING_POWER'],
    ['broker blocked', { brokerBlocked: true }, 'BROKER_LIMITATION'],
  ])('%s → ineligible (%s)', (_label, patch, code) => {
    const v = evaluateAccountEligibility({ ...OK, ...patch })
    expect(v.eligible).toBe(false)
    expect(v.code).toBe(code)
    expect(v.reason).toBeTruthy()
  })

  it('every reason is remediable-specific, never a bare refusal', () => {
    const cash = evaluateAccountEligibility({ ...OK, accountType: 'cash' })
    expect(cash.reason).toMatch(/margin account is required/i)
    const lvl = evaluateAccountEligibility({ ...OK, optionsLevel: 1 })
    expect(lvl.reason).toMatch(/level 3/i)
    expect(lvl.reason).toMatch(/broker/i)
  })

  it('a broker block beats everything — no customer action fixes it', () => {
    const v = evaluateAccountEligibility({ ...OK, brokerBlocked: true, optionsLevel: 0, buyingPower: 0 })
    expect(v.code).toBe('BROKER_LIMITATION')
  })

  it('durable problems are reported before the volatile one', () => {
    // Buying power moves minute to minute and is re-checked at activation (§4); a
    // customer should be told about approval level first.
    const v = evaluateAccountEligibility({ ...OK, optionsLevel: 1, buyingPower: 0 })
    expect(v.code).toBe('OPTIONS_APPROVAL')
  })

  it('IRA/Roth are tradeable with approval; cash never is', () => {
    expect(evaluateAccountEligibility({ ...OK, accountType: 'ira' }).eligible).toBe(true)
    expect(evaluateAccountEligibility({ ...OK, accountType: 'roth' }).eligible).toBe(true)
    expect(evaluateAccountEligibility({ ...OK, accountType: 'cash' }).eligible).toBe(false)
  })

  it('broker type strings normalize by substring — "Individual Margin"/"MARGIN" pass, cash never', () => {
    expect(evaluateAccountEligibility({ ...OK, accountType: 'Individual Margin' }).eligible).toBe(true)
    expect(evaluateAccountEligibility({ ...OK, accountType: 'MARGIN' }).eligible).toBe(true)
    expect(evaluateAccountEligibility({ ...OK, accountType: 'CASH' }).eligible).toBe(false)
  })
})

describe('SnapTrade slug-aware gates (7/30 tastytrade lane)', () => {
  it('tastytrade with NO options level passes on platform capability (mleg is GA there)', () => {
    const v = evaluateAccountEligibility({ ...OK, optionsLevel: null, brokerSlug: 'TASTYTRADE' })
    expect(v).toEqual({ eligible: true, optionsVerification: 'platform_capability' })
  })

  it('a REPORTED too-low level still refuses, even on an mleg-capable broker', () => {
    // Capability substitutes for an UNKNOWN level, never for a known-insufficient one.
    const v = evaluateAccountEligibility({ ...OK, optionsLevel: 1, brokerSlug: 'TASTYTRADE' })
    expect(v.code).toBe('OPTIONS_APPROVAL')
  })

  it('an unknown slug with no options level stays fail-closed', () => {
    const v = evaluateAccountEligibility({ ...OK, optionsLevel: null, brokerSlug: 'WEBULL' })
    expect(v.code).toBe('OPTIONS_APPROVAL')
  })

  it('Robinhood is honestly broker-limited — data-only, not "go fix your approval"', () => {
    const v = evaluateAccountEligibility({ ...OK, optionsLevel: null, brokerSlug: 'ROBINHOOD' })
    expect(v.code).toBe('BROKER_LIMITATION')
  })

  it('capability gate still requires type, status and buying power', () => {
    expect(evaluateAccountEligibility({ ...OK, optionsLevel: null, brokerSlug: 'TASTYTRADE', accountType: 'cash' }).code)
      .toBe('ACCOUNT_TYPE')
    expect(evaluateAccountEligibility({ ...OK, optionsLevel: null, brokerSlug: 'TASTYTRADE', buyingPower: null }).code)
      .toBe('BUYING_POWER')
  })

  it('normalizeInstitutionSlug maps display names onto slugs', () => {
    expect(normalizeInstitutionSlug('tastytrade')).toBe('TASTYTRADE')
    expect(normalizeInstitutionSlug('Robinhood')).toBe('ROBINHOOD')
    expect(normalizeInstitutionSlug(null)).toBe(null)
    expect(normalizeInstitutionSlug('')).toBe(null)
  })
})

describe('account masking (§3 BROKER-02, §8 no full numbers in logs/UI)', () => {
  it('shows only the last four', () => {
    expect(maskAccountNumber('6YB712345')).toBe('••••2345')
  })

  it('masks SHORT identifiers entirely rather than revealing them', () => {
    // A naive slice(-4) would print a 4-char account number in full.
    expect(maskAccountNumber('1234')).toBe('••••')
    expect(maskAccountNumber('12')).toBe('••••')
  })

  it('handles null/undefined without leaking "null" into the UI', () => {
    expect(maskAccountNumber(null)).toBe('••••')
    expect(maskAccountNumber(undefined)).toBe('••••')
  })

  it('never contains the full reference', () => {
    const ref = '6YB712345'
    expect(maskAccountNumber(ref)).not.toContain(ref)
    expect(maskAccountNumber(ref).length).toBeLessThan(ref.length + 4)
  })
})
