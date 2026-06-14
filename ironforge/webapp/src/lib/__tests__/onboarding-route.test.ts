import { describe, it, expect } from 'vitest'
import { nextRouteForOnboarding } from '@/lib/auth/onboarding-route'

describe('nextRouteForOnboarding', () => {
  it('routes fresh / verified accounts to the legal step', () => {
    expect(nextRouteForOnboarding('account_created')).toBe('/onboarding/legal')
    expect(nextRouteForOnboarding('email_verified')).toBe('/onboarding/legal')
  })
  it('routes legal-accepted to the risk-assessment step', () => {
    expect(nextRouteForOnboarding('legal_accepted')).toBe('/onboarding/risk')
  })
  it('routes risk-assessed to the brokerage-connection step', () => {
    expect(nextRouteForOnboarding('risk_assessed')).toBe('/onboarding/brokerage')
  })
  it('routes brokerage-connected to the completion placeholder', () => {
    expect(nextRouteForOnboarding('brokerage_connected')).toBe('/onboarding/complete')
  })
  it('defaults unknown/null steps to the completion placeholder', () => {
    expect(nextRouteForOnboarding(undefined)).toBe('/onboarding/complete')
    expect(nextRouteForOnboarding(null)).toBe('/onboarding/complete')
    expect(nextRouteForOnboarding('something_future')).toBe('/onboarding/complete')
  })
})
