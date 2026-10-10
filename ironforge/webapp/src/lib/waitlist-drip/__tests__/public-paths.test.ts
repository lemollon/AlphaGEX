import { describe, it, expect } from 'vitest'
import { isPublicPath } from '@/lib/auth/access'
import { servesPath } from '@/lib/surface'

/**
 * The unsubscribe/preferences pages and the Resend webhook must be reachable with no
 * session and must be served by the CUSTOMER deployment (the one holding the customers DB).
 * A login wall on an unsubscribe link is a CAN-SPAM problem; a 404 from the surface split
 * would be the same failure with a different status code.
 */
describe('waitlist drip public paths', () => {
  const token = 'AbCdEfGhIjKlMnOpQrStUv'
  const pages = [`/email/unsubscribe/${token}`, `/email/preferences/${token}`]

  it('preferences and unsubscribe pages are public', () => {
    for (const p of pages) expect(isPublicPath(p), p).toBe(true)
  })

  it('the Resend webhook is public (self-guarded by signature)', () => {
    expect(isPublicPath('/api/email/webhook/resend')).toBe(true)
  })

  it('the ops drip endpoint is NOT public', () => {
    expect(isPublicPath('/api/ops/waitlist/drip')).toBe(false)
  })

  it('the customer surface serves all of them; the operator surface serves the pages to nobody', () => {
    for (const p of [...pages, '/api/email/webhook/resend']) {
      expect(servesPath('customer', p), `customer serves ${p}`).toBe(true)
      expect(servesPath('both', p)).toBe(true)
    }
    for (const p of pages) expect(servesPath('operator', p), `operator must not serve ${p}`).toBe(false)
    // /api/ops/* is shared infrastructure on both deployments.
    expect(servesPath('customer', '/api/ops/waitlist/drip')).toBe(true)
  })
})
