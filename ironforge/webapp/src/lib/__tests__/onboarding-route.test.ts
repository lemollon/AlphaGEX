import { describe, it, expect } from 'vitest'
import { nextRouteForOnboarding } from '@/lib/auth/onboarding-route'

describe('nextRouteForOnboarding (cutover 7/30: /enroll is the universal door)', () => {
  // The legacy /onboarding/* funnel is retired as a destination. /enroll is
  // ownership-aware server-side (resumes open enrollments, routes owners to /live,
  // community members to /community), so ONE answer is correct for every step —
  // this test locks the cutover in place so a future edit can't quietly resurrect
  // the legacy funnel as a login landing.
  it.each([
    'account_created',
    'email_verified',
    'legal_accepted',
    'risk_assessed',
    'brokerage_connected',
    'something_future',
  ])('%s → /enroll', (step) => {
    expect(nextRouteForOnboarding(step)).toBe('/enroll')
  })

  it('null/undefined → /enroll', () => {
    expect(nextRouteForOnboarding(undefined)).toBe('/enroll')
    expect(nextRouteForOnboarding(null)).toBe('/enroll')
  })
})
