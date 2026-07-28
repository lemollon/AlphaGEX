import { describe, it, expect } from 'vitest'
import { errorEnvelope, statusFor, redactProviderError, newCorrelationId } from '../errors'

describe('error envelope (§6)', () => {
  it('uses the status codes the spec fixes', () => {
    expect(statusFor('STATE_CONFLICT')).toBe(409)     // stale state / version conflict
    expect(statusFor('PREVIEW_STALE')).toBe(409)
    expect(statusFor('VALIDATION_FAILED')).toBe(422)  // validation
    expect(statusFor('UNAUTHORIZED')).toBe(401)
    expect(statusFor('FORBIDDEN')).toBe(403)
    expect(statusFor('RATE_LIMITED')).toBe(429)
    expect(statusFor('PROVIDER_UNAVAILABLE')).toBe(503) // retryable provider outage
  })

  it('marks only transients retryable — a 422 is never worth retrying', () => {
    expect(errorEnvelope('PROVIDER_UNAVAILABLE', 'x').retryable).toBe(true)
    expect(errorEnvelope('RATE_LIMITED', 'x').retryable).toBe(true)
    expect(errorEnvelope('VALIDATION_FAILED', 'x').retryable).toBe(false)
    expect(errorEnvelope('BROKER_ACCOUNT_INELIGIBLE', 'x').retryable).toBe(false)
  })

  it('always carries a correlation id, and a fresh one each time (§11)', () => {
    const a = errorEnvelope('INTERNAL', 'x')
    const b = errorEnvelope('INTERNAL', 'x')
    expect(a.correlation_id).toBeTruthy()
    expect(a.correlation_id).not.toBe(b.correlation_id)
  })

  it('omits `field` rather than emitting it empty', () => {
    expect('field' in errorEnvelope('INTERNAL', 'x')).toBe(false)
    expect(errorEnvelope('VALIDATION_FAILED', 'x', { field: 'plan' }).field).toBe('plan')
  })

  it('NEVER puts the provider\'s raw text in the client envelope (§6)', () => {
    const raw = new Error('Stripe: No such customer: cus_LIVE_123 (request req_abc)')
    const env = redactProviderError('billing', raw, 'PROVIDER_UNAVAILABLE', 'Billing is temporarily unavailable.')
    const serialized = JSON.stringify(env)
    expect(serialized).not.toContain('cus_LIVE_123')
    expect(serialized).not.toContain('req_abc')
    expect(serialized).not.toContain('Stripe')
    expect(env.message).toBe('Billing is temporarily unavailable.')
    // The correlation id is what lets support find the logged original.
    expect(env.correlation_id).toBeTruthy()
  })

  it('correlation ids are opaque — no PII to leak on an error screen', () => {
    const id = newCorrelationId()
    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/)
  })
})
