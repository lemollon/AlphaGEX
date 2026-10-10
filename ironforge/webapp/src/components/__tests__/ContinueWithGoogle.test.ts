import { describe, it, expect } from 'vitest'

/**
 * Pure-logic mirror of ContinueWithGoogle's gating + href-building rules — the
 * same approach as ui-contracts.test.ts (this repo's vitest config runs
 * `environment: 'node'` with no JSX/React transform wired up, so these
 * assertions exercise the exact branching the component uses rather than a
 * rendered DOM tree).
 */

interface GoogleButtonConsents {
  ageConfirmed: boolean
  noAdviceAcknowledged: boolean
  electronicCommConsent: boolean
}

function isBlocked(requireConsents: boolean | undefined, consents: GoogleButtonConsents | undefined): boolean {
  const allConsented = Boolean(
    consents?.ageConfirmed && consents?.noAdviceAcknowledged && consents?.electronicCommConsent,
  )
  return Boolean(requireConsents) && !allConsented
}

function buildHref(next: string | undefined, consents: GoogleButtonConsents | undefined): string {
  const params = new URLSearchParams()
  if (next) params.set('next', next)
  if (consents) {
    params.set('ageConfirmed', consents.ageConfirmed ? '1' : '0')
    params.set('noAdvice', consents.noAdviceAcknowledged ? '1' : '0')
    params.set('commConsent', consents.electronicCommConsent ? '1' : '0')
  }
  const qs = params.toString()
  return `/api/auth/google/start${qs ? `?${qs}` : ''}`
}

describe('ContinueWithGoogle — /signup consent gating', () => {
  it('blocks the button when requireConsents is set and no boxes are checked', () => {
    expect(isBlocked(true, { ageConfirmed: false, noAdviceAcknowledged: false, electronicCommConsent: false })).toBe(true)
  })

  it('blocks the button until ALL 3 consents are true, not just some', () => {
    expect(isBlocked(true, { ageConfirmed: true, noAdviceAcknowledged: true, electronicCommConsent: false })).toBe(true)
    expect(isBlocked(true, { ageConfirmed: true, noAdviceAcknowledged: false, electronicCommConsent: true })).toBe(true)
  })

  it('unblocks only once all 3 are true', () => {
    expect(isBlocked(true, { ageConfirmed: true, noAdviceAcknowledged: true, electronicCommConsent: true })).toBe(false)
  })

  it('/login usage (requireConsents unset) is never blocked, even with no consents object', () => {
    expect(isBlocked(undefined, undefined)).toBe(false)
  })

  it('carries all 3 consent flags + next in the /start href once unblocked', () => {
    const href = buildHref('/enroll', { ageConfirmed: true, noAdviceAcknowledged: true, electronicCommConsent: true })
    expect(href).toContain('/api/auth/google/start')
    expect(href).toContain('ageConfirmed=1')
    expect(href).toContain('noAdvice=1')
    expect(href).toContain('commConsent=1')
    expect(href).toContain('next=%2Fenroll')
  })

  it('the /login href carries no consent flags at all', () => {
    const href = buildHref('/enroll', undefined)
    expect(href).not.toContain('ageConfirmed')
    expect(href).not.toContain('noAdvice')
    expect(href).not.toContain('commConsent')
  })
})
