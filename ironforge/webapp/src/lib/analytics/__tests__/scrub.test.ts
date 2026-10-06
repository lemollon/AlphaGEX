import { describe, it, expect } from 'vitest'
import { scrubProps, looksLikePii } from '../scrub'

describe('looksLikePii', () => {
  it('flags an email address', () => {
    expect(looksLikePii('shairan2016@gmail.com')).toBe(true)
  })
  it('flags a phone number', () => {
    expect(looksLikePii('(713) 555-0199')).toBe(true)
  })
  it('flags a long digit run (card/account/ssn shape)', () => {
    expect(looksLikePii('4111 1111 1111 1111')).toBe(true)
    expect(looksLikePii('123-45-6789')).toBe(true)
  })
  it('does not flag an ordinary short value', () => {
    expect(looksLikePii('hero')).toBe(false)
    expect(looksLikePii('spark')).toBe(false)
    expect(looksLikePii('3')).toBe(false)
  })
})

describe('scrubProps', () => {
  it('drops props whose key names a sensitive field', () => {
    const out = scrubProps({
      cardNumber: '4111111111111111',
      accountId: 'acct_1',
      brokerToken: 'tok',
      email: 'a@b.com',
      phone: '7135550199',
      placement: 'hero',
    })
    expect(out).toEqual({ placement: 'hero' })
  })

  it('drops a string VALUE that looks like PII even under an innocuous key', () => {
    const out = scrubProps({ note: 'reach me at shairan2016@gmail.com', cta: 'create_account' })
    expect(out).toEqual({ cta: 'create_account' })
  })

  it('drops non-primitive values', () => {
    const out = scrubProps({ nested: { a: 1 }, list: [1, 2], ok: 'fine' })
    expect(out).toEqual({ ok: 'fine' })
  })

  it('returns null for an empty or fully-scrubbed object', () => {
    expect(scrubProps({})).toBeNull()
    expect(scrubProps({ email: 'a@b.com' })).toBeNull()
    expect(scrubProps(null)).toBeNull()
  })
})
