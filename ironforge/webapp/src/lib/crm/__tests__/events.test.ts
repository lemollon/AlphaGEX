import { describe, it, expect } from 'vitest'
import { deliverCrmEvent, safeErrorSummary, __testing } from '../events'
import type { CrmEventType } from '../events'

const { violatingKey } = __testing

/**
 * These assert the AC-CRM-006 / AC-CRM-007 firewall: no payment, bank, Stripe secret, brokerage
 * token, password or credential may ever reach Attio. The firewall is the reason those criteria
 * can be signed off on evidence rather than on trust, so it is worth over-testing.
 */
describe('violatingKey — forbidden field detection', () => {
  it('passes a clean membership payload', () => {
    expect(
      violatingKey({
        membership_id: 'sub_123',
        plan: 'Forge Automate',
        membership_status: 'Active',
        start_date: '2026-09-01',
      }),
    ).toBeNull()
  })

  it('allows Stripe REFERENCE ids — they are explicitly in scope', () => {
    expect(
      violatingKey({ stripe_customer_id: 'cus_abc123', stripe_subscription_id: 'sub_abc123' }),
    ).toBeNull()
  })

  it.each([
    ['access_token', { access_token: 'abc' }],
    ['refresh_token', { refresh_token: 'abc' }],
    ['password', { password: 'hunter2' }],
    ['card_number', { card_number: '4242424242424242' }],
    ['cvv', { cvv: '123' }],
    ['bank_account', { bank_account: '000123456' }],
    ['api_key', { api_key: 'k-1' }],
    ['client_secret', { client_secret: 's' }],
    ['ssn', { ssn: '000-00-0000' }],
  ])('blocks %s', (_label, payload) => {
    expect(violatingKey(payload)).not.toBeNull()
  })

  it('finds a forbidden key nested inside an object', () => {
    const hit = violatingKey({ member: { detail: { oauth_token: 'x' } } })
    expect(hit).toBe('member.detail.oauth_token')
  })

  it('finds a forbidden key nested inside an array', () => {
    const hit = violatingKey({ connections: [{ ok: true }, { refresh_token: 'x' }] })
    expect(hit).toBe('connections[1].refresh_token')
  })

  it('blocks a secret-shaped VALUE even under an innocent key', () => {
    expect(violatingKey({ last_error_summary: 'Authorization: Bearer abcdef1234567890' })).not.toBeNull()
    expect(violatingKey({ note: 'key sk_live_abcdef123456 leaked' })).not.toBeNull()
    expect(violatingKey({ note: 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig' })).not.toBeNull()
  })

  it('tolerates null and undefined without throwing', () => {
    expect(violatingKey(null)).toBeNull()
    expect(violatingKey(undefined)).toBeNull()
    expect(violatingKey({ a: null, b: undefined })).toBeNull()
  })
})

describe('safeErrorSummary', () => {
  it('keeps a customer-safe provider message intact', () => {
    expect(safeErrorSummary('Account must be active before connection can complete.')).toBe(
      'Account must be active before connection can complete.',
    )
  })

  it('redacts a bearer token embedded in an error string', () => {
    expect(safeErrorSummary('failed: Bearer abcdef1234567890 rejected')).toContain('[redacted]')
    expect(safeErrorSummary('failed: Bearer abcdef1234567890 rejected')).not.toContain('abcdef1234567890')
  })

  it('redacts a live Stripe key', () => {
    const out = safeErrorSummary('charge failed with sk_live_51Hxxxxxxxxxxxx')
    expect(out).toContain('[redacted]')
    expect(out).not.toContain('sk_live_51Hxxxxxxxxxxxx')
  })

  it('truncates to the requested length', () => {
    expect(safeErrorSummary('x'.repeat(500)).length).toBe(300)
    expect(safeErrorSummary('x'.repeat(500), 100).length).toBe(100)
  })

  it('returns empty string for non-strings and blanks', () => {
    expect(safeErrorSummary(undefined)).toBe('')
    expect(safeErrorSummary(null)).toBe('')
    expect(safeErrorSummary({ a: 1 })).toBe('')
    expect(safeErrorSummary('   ')).toBe('')
  })
})

describe('deliverCrmEvent guards', () => {
  it('dead-letters an unmapped event type instead of retrying forever', async () => {
    const res = await deliverCrmEvent('crm.not_a_real_event' as CrmEventType, {})
    expect(res.ok).toBe(false)
    expect(res.retryable).toBe(false)
    expect(res.error).toContain('unmapped')
  })

  it('dead-letters a payload with no email — retrying cannot supply one', async () => {
    const res = await deliverCrmEvent('crm.waitlist_submitted', { firstName: 'Jordan' })
    expect(res.ok).toBe(false)
    expect(res.retryable).toBe(false)
  })

  it('dead-letters a membership event with no membershipId', async () => {
    const res = await deliverCrmEvent('crm.subscription_active', { email: 'a@b.com' })
    expect(res.ok).toBe(false)
    expect(res.retryable).toBe(false)
  })
})
