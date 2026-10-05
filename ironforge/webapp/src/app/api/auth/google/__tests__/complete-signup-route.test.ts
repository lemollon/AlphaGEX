import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: vi.fn(() => true),
  customerQuery: vi.fn(),
  customerExecute: vi.fn(async () => 1),
}))

vi.mock('@/lib/auth/google-oauth', () => ({
  deriveUsernameBase: () => 'dana',
}))

vi.mock('@/lib/auth/google-pending-signup-cookie', () => ({
  verifyGooglePendingSignupState: vi.fn(),
  GOOGLE_PENDING_SIGNUP_COOKIE: 'ironforge_google_pending_signup',
  googlePendingSignupCookieOptions: () => ({ httpOnly: true, path: '/' }),
}))

const mockSession: Record<string, unknown> & { save: ReturnType<typeof vi.fn> } = {
  save: vi.fn(async () => undefined),
}
vi.mock('@/lib/auth/customer-session-server', () => ({
  getCustomerSession: vi.fn(async () => mockSession),
}))

vi.mock('@/lib/auth/create-customer', () => ({
  createCustomerAccount: vi.fn(async () => ({ userId: 'new-user-uuid' })),
  writeAudit: vi.fn(async () => undefined),
  clientIpFromHeaders: () => null,
}))

import { customerQuery, customerExecute } from '@/lib/customers-db'
import { verifyGooglePendingSignupState } from '@/lib/auth/google-pending-signup-cookie'
import { createCustomerAccount } from '@/lib/auth/create-customer'
import { POST } from '../complete-signup/route'

function req(body: Record<string, unknown>, cookie = 'ironforge_google_pending_signup=signed-cookie-value') {
  return new NextRequest('https://ironforge.trade/api/auth/google/complete-signup', {
    method: 'POST',
    headers: { cookie, 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
}

const ALL_TRUE = { ageConfirmed: true, noAdviceAcknowledged: true, electronicCommConsent: true }
const PENDING = {
  sub: 'google-sub-1',
  email: 'dana.reyes@gmail.com',
  givenName: 'Dana',
  familyName: 'Reyes',
  next: '/enroll',
  exp: Date.now() + 600_000,
}

beforeEach(() => {
  vi.clearAllMocks()
  mockSession.customerId = undefined
  mockSession.email = undefined
  mockSession.emailVerified = undefined
  mockSession.onboardingStep = undefined
  ;(verifyGooglePendingSignupState as any).mockResolvedValue(PENDING)
})

describe('POST /api/auth/google/complete-signup', () => {
  it('rejects a missing/expired/tampered pending cookie before looking at the body at all', async () => {
    ;(verifyGooglePendingSignupState as any).mockResolvedValue(null)
    const res = await POST(req(ALL_TRUE))
    expect(res.status).toBe(400)
    const data = await res.json()
    expect(data.ok).toBe(false)
    expect(data.code).toBe('expired')
    expect(createCustomerAccount).not.toHaveBeenCalled()
  })

  it('refuses to create the account unless all 3 consents are literally true', async () => {
    ;(customerQuery as any).mockResolvedValue([])
    const res = await POST(req({ ageConfirmed: true, noAdviceAcknowledged: true, electronicCommConsent: false }))
    expect(res.status).toBe(400)
    expect(createCustomerAccount).not.toHaveBeenCalled()
  })

  it('never records consent=true from a non-boolean truthy value', async () => {
    ;(customerQuery as any).mockResolvedValue([])
    const res = await POST(req({ ageConfirmed: 1, noAdviceAcknowledged: 'true', electronicCommConsent: true }))
    expect(res.status).toBe(400)
    expect(createCustomerAccount).not.toHaveBeenCalled()
  })

  it('creates the account from the verified cookie identity + the 3 ticked consents', async () => {
    ;(customerQuery as any).mockResolvedValue([]) // no match by auth_user_id or email
    const res = await POST(req(ALL_TRUE))

    expect(createCustomerAccount).toHaveBeenCalledWith(
      expect.objectContaining({
        email: 'dana.reyes@gmail.com',
        authProvider: 'google',
        authUserId: 'google:google-sub-1',
        passwordHash: null,
        ageConfirmed: true,
        noAdviceAcknowledged: true,
        electronicCommConsent: true,
        emailVerified: true,
        source: 'google_signup',
      }),
    )
    expect(mockSession.customerId).toBe('new-user-uuid')
    const data = await res.json()
    expect(data.ok).toBe(true)
    expect(data.next).toBe('/enroll')
    // The pending cookie is single-use — cleared on success.
    expect(res.headers.get('set-cookie')).toContain('ironforge_google_pending_signup=;')
  })

  it('signs in without creating a second account if the identity was linked during the consent window', async () => {
    ;(customerQuery as any).mockImplementation(async (sql: string) =>
      /auth_user_id/i.test(sql)
        ? [{ id: 'existing-uuid', email: 'dana.reyes@gmail.com', onboarding_step: 'done', email_verified: true }]
        : [],
    )
    const res = await POST(req(ALL_TRUE))
    expect(createCustomerAccount).not.toHaveBeenCalled()
    expect(mockSession.customerId).toBe('existing-uuid')
    const data = await res.json()
    expect(data.ok).toBe(true)
  })

  it('links and signs in an existing, email-VERIFIED account instead of creating a duplicate', async () => {
    ;(customerQuery as any).mockImplementation(async (sql: string) => {
      if (/auth_user_id/i.test(sql)) return []
      if (/WHERE email/i.test(sql)) {
        return [{ id: 'existing-uuid', email: 'dana.reyes@gmail.com', onboarding_step: 'done', email_verified: true }]
      }
      return []
    })
    const res = await POST(req(ALL_TRUE))
    expect(createCustomerAccount).not.toHaveBeenCalled()
    expect(customerExecute).toHaveBeenCalledWith(
      expect.stringMatching(/UPDATE users SET auth_user_id/i),
      ['existing-uuid', 'google:google-sub-1'],
    )
    expect(mockSession.customerId).toBe('existing-uuid')
  })

  it('refuses to auto-link an existing account whose OWN email is unverified', async () => {
    ;(customerQuery as any).mockImplementation(async (sql: string) => {
      if (/auth_user_id/i.test(sql)) return []
      if (/WHERE email/i.test(sql)) {
        return [{ id: 'existing-uuid', email: 'dana.reyes@gmail.com', onboarding_step: 'account_created', email_verified: false }]
      }
      return []
    })
    const res = await POST(req(ALL_TRUE))
    expect(res.status).toBe(409)
    expect(createCustomerAccount).not.toHaveBeenCalled()
    expect(mockSession.customerId).toBeUndefined()
    const data = await res.json()
    expect(data.code).toBe('unverified_existing')
  })
})
