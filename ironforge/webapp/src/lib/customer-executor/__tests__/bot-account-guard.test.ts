import { describe, it, expect } from 'vitest'
import {
  checkBotTradedAccount,
  normalizeAccountNumber,
  accountLast4,
} from '../bot-account-guard'

const KNOWN = ['6YB71371', 'ABC-99999']

describe('normalizeAccountNumber / accountLast4', () => {
  it('strips formatting and uppercases', () => {
    expect(normalizeAccountNumber('6yb-71371')).toBe('6YB71371')
    expect(normalizeAccountNumber(' 6YB 71371 ')).toBe('6YB71371')
  })

  it('last4 mirrors the display-mask convention', () => {
    expect(accountLast4('6YB71371')).toBe('1371')
    expect(accountLast4('ABC-99999')).toBe('9999')
  })
})

describe('checkBotTradedAccount — full number available', () => {
  it('blocks a production account the bots already trade directly (6YB71371)', () => {
    const v = checkBotTradedAccount({
      decryptedAccountRef: '6YB71371',
      displayMask: '••••1371',
      brokerSlug: 'TRADIER',
      knownBotAccountNumbers: KNOWN,
    })
    expect(v).toEqual({ blocked: true, reason: 'full_number_match', matchedLast4: '1371' })
  })

  it('normalizes formatting differences before comparing (dashes, case, spaces)', () => {
    const v = checkBotTradedAccount({
      decryptedAccountRef: ' 6yb-71371 ',
      displayMask: null,
      brokerSlug: 'TRADIER',
      knownBotAccountNumbers: KNOWN,
    })
    expect(v.blocked).toBe(true)
  })

  it('a normal customer account is mirrored — no match, not blocked', () => {
    const v = checkBotTradedAccount({
      decryptedAccountRef: 'XYZ998877',
      displayMask: '••••8877',
      brokerSlug: 'TASTYTRADE',
      knownBotAccountNumbers: KNOWN,
    })
    expect(v).toEqual({ blocked: false })
  })

  it('a full number always wins over the mask/institution fallback, even on Tradier', () => {
    // Same last4 as a bot account, but the FULL number is genuinely different —
    // the full-number check is authoritative and must not fall through to a
    // last-4 false positive.
    const v = checkBotTradedAccount({
      decryptedAccountRef: 'ZZZ71371',
      displayMask: '••••1371',
      brokerSlug: 'TRADIER',
      knownBotAccountNumbers: KNOWN,
    })
    expect(v).toEqual({ blocked: false })
  })
})

describe('checkBotTradedAccount — masked last-4 fallback (full number unavailable)', () => {
  it('blocks on institution=Tradier + matching last-4, and reports which', () => {
    const v = checkBotTradedAccount({
      decryptedAccountRef: null,
      displayMask: '••••1371',
      brokerSlug: 'TRADIER',
      knownBotAccountNumbers: KNOWN,
    })
    expect(v).toEqual({ blocked: true, reason: 'masked_last4_match', matchedLast4: '1371' })
  })

  it('a non-matching last-4 on Tradier is not blocked', () => {
    const v = checkBotTradedAccount({
      decryptedAccountRef: null,
      displayMask: '••••0000',
      brokerSlug: 'TRADIER',
      knownBotAccountNumbers: KNOWN,
    })
    expect(v).toEqual({ blocked: false })
  })

  it('a matching last-4 on a DIFFERENT institution is not blocked (cannot be a Tradier account)', () => {
    const v = checkBotTradedAccount({
      decryptedAccountRef: null,
      displayMask: '••••1371',
      brokerSlug: 'SCHWAB',
      knownBotAccountNumbers: KNOWN,
    })
    expect(v).toEqual({ blocked: false })
  })

  it('empty knownBotAccountNumbers never blocks anything', () => {
    const v = checkBotTradedAccount({
      decryptedAccountRef: null,
      displayMask: '••••1371',
      brokerSlug: 'TRADIER',
      knownBotAccountNumbers: [],
    })
    expect(v).toEqual({ blocked: false })
  })
})

describe('checkBotTradedAccount — unverifiable, FAILS CLOSED', () => {
  it('no full number, no mask, no institution → unverifiable', () => {
    const v = checkBotTradedAccount({
      decryptedAccountRef: null,
      displayMask: null,
      brokerSlug: null,
      knownBotAccountNumbers: KNOWN,
    })
    expect(v).toEqual({ blocked: true, reason: 'unverifiable' })
  })

  it('Tradier institution but no usable mask → unverifiable, not silently allowed', () => {
    const v = checkBotTradedAccount({
      decryptedAccountRef: null,
      displayMask: null,
      brokerSlug: 'TRADIER',
      knownBotAccountNumbers: KNOWN,
    })
    expect(v).toEqual({ blocked: true, reason: 'unverifiable' })
  })

  it('mask present but institution unknown (null) → unverifiable, cannot rule out Tradier', () => {
    const v = checkBotTradedAccount({
      decryptedAccountRef: null,
      displayMask: '••••1371',
      brokerSlug: null,
      knownBotAccountNumbers: KNOWN,
    })
    expect(v).toEqual({ blocked: true, reason: 'unverifiable' })
  })

  it('empty-string decrypted ref counts as unavailable, not as a value to compare', () => {
    const v = checkBotTradedAccount({
      decryptedAccountRef: '',
      displayMask: null,
      brokerSlug: null,
      knownBotAccountNumbers: KNOWN,
    })
    expect(v).toEqual({ blocked: true, reason: 'unverifiable' })
  })
})
