import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: vi.fn(() => true),
  customerQuery: vi.fn(),
  customerExecute: vi.fn(async () => 1),
}))

vi.mock('@/lib/auth/google-oauth', () => ({
  isGoogleOAuthConfigured: vi.fn(() => true),
  exchangeCodeForToken: vi.fn(async () => ({ idToken: 'id-token', accessToken: null })),
  verifyGoogleIdToken: vi.fn(),
  googleRedirectUri: (origin: string) => `${origin}/api/auth/google/callback`,
  deriveUsernameBase: () => 'dana',
}))

vi.mock('@/lib/auth/google-oauth-cookie', () => ({
  verifyGoogleOAuthState: vi.fn(),
  GOOGLE_OAUTH_COOKIE: 'ironforge_google_oauth',
  googleOAuthCookieOptions: () => ({ httpOnly: true, path: '/api/auth/google' }),
}))

vi.mock('@/lib/auth/google-pending-signup-cookie', () => ({
  signGooglePendingSignupState: vi.fn(async () => 'pending-signup-cookie-value'),
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
import { verifyGoogleIdToken } from '@/lib/auth/google-oauth'
import { verifyGoogleOAuthState } from '@/lib/auth/google-oauth-cookie'
import { signGooglePendingSignupState } from '@/lib/auth/google-pending-signup-cookie'
import { createCustomerAccount } from '@/lib/auth/create-customer'
import { GET } from '../callback/route'

function req(qs: string, cookie = 'ironforge_google_oauth=signed-cookie-value') {
  return new NextRequest(`https://ironforge.trade/api/auth/google/callback${qs}`, {
    headers: { cookie },
  })
}

const SAVED_STATE = { state: 'csrf-state', verifier: 'pkce-verifier', next: '/enroll', exp: Date.now() + 600_000 }

function googleClaims(overrides: Record<string, unknown> = {}) {
  return {
    sub: 'google-sub-1',
    email: 'dana.reyes@gmail.com',
    emailVerified: true,
    givenName: 'Dana',
    familyName: 'Reyes',
    picture: null,
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockSession.customerId = undefined
  mockSession.email = undefined
  mockSession.emailVerified = undefined
  mockSession.onboardingStep = undefined
  ;(verifyGoogleOAuthState as any).mockResolvedValue(SAVED_STATE)
  ;(verifyGoogleIdToken as any).mockResolvedValue(googleClaims())
})

describe('GET /api/auth/google/callback', () => {
  it('rejects a state that does not match the signed cookie (CSRF/replay)', async () => {
    ;(verifyGoogleOAuthState as any).mockResolvedValue({ ...SAVED_STATE, state: 'different-state' })
    const res = await GET(req('?code=abc&state=csrf-state'))
    expect(res.status).toBe(307)
    expect(res.headers.get('location')).toContain('/login')
    expect(res.headers.get('location')).toContain('googleError=invalid_state')
    expect(createCustomerAccount).not.toHaveBeenCalled()
  })

  it('rejects when the signed cookie is missing or expired', async () => {
    ;(verifyGoogleOAuthState as any).mockResolvedValue(null)
    const res = await GET(req('?code=abc&state=csrf-state'))
    expect(res.headers.get('location')).toContain('googleError=invalid_state')
  })

  it('rejects an unverified Google email without creating or signing in', async () => {
    ;(verifyGoogleIdToken as any).mockResolvedValue(googleClaims({ emailVerified: false }))
    const res = await GET(req('?code=abc&state=csrf-state'))
    expect(res.headers.get('location')).toContain('googleError=email_unverified')
    expect(createCustomerAccount).not.toHaveBeenCalled()
    expect(mockSession.customerId).toBeUndefined()
  })

  it('creates a new customer immediately when the signup round trip already carries all 3 consents', async () => {
    ;(customerQuery as any).mockResolvedValue([]) // neither by auth_user_id nor by email
    ;(verifyGoogleOAuthState as any).mockResolvedValue({
      ...SAVED_STATE,
      consents: { ageConfirmed: true, noAdviceAcknowledged: true, electronicCommConsent: true },
    })
    const res = await GET(req('?code=abc&state=csrf-state'))

    expect(createCustomerAccount).toHaveBeenCalledWith(
      expect.objectContaining({
        email: 'dana.reyes@gmail.com',
        authProvider: 'google',
        authUserId: 'google:google-sub-1',
        passwordHash: null,
        phone: null,
        state: null,
        emailVerified: true,
        ageConfirmed: true,
        noAdviceAcknowledged: true,
        electronicCommConsent: true,
      }),
    )
    expect(mockSession.customerId).toBe('new-user-uuid')
    expect(res.headers.get('location')).toContain('/enroll')
    expect(signGooglePendingSignupState).not.toHaveBeenCalled()
  })

  it('never creates an account on an implied yes — routes a brand-new Google identity with NO consents to the consent page', async () => {
    // SAVED_STATE (default mock) carries no `consents` — the shape a /login-
    // initiated round trip produces, since /login's button sends none.
    ;(customerQuery as any).mockResolvedValue([])
    const res = await GET(req('?code=abc&state=csrf-state'))

    expect(createCustomerAccount).not.toHaveBeenCalled()
    expect(mockSession.customerId).toBeUndefined()
    expect(signGooglePendingSignupState).toHaveBeenCalledWith(
      expect.objectContaining({ sub: 'google-sub-1', email: 'dana.reyes@gmail.com', next: '/enroll' }),
    )
    expect(res.status).toBe(307)
    expect(res.headers.get('location')).toContain('/signup/google-consent')
    // The OAuth round-trip cookie is cleared either way — this is a new leg, not a retry.
    expect(res.headers.get('set-cookie')).toContain('ironforge_google_oauth=')
  })

  it('still refuses to create an account when consents are present but incomplete (defense in depth)', async () => {
    ;(customerQuery as any).mockResolvedValue([])
    ;(verifyGoogleOAuthState as any).mockResolvedValue({
      ...SAVED_STATE,
      consents: { ageConfirmed: true, noAdviceAcknowledged: true, electronicCommConsent: false },
    })
    const res = await GET(req('?code=abc&state=csrf-state'))

    expect(createCustomerAccount).not.toHaveBeenCalled()
    expect(res.headers.get('location')).toContain('/signup/google-consent')
  })

  it('signs in (no account creation) when the Google identity is already linked', async () => {
    ;(customerQuery as any).mockImplementation(async (sql: string) =>
      /auth_user_id/i.test(sql)
        ? [{ id: 'existing-uuid', email: 'dana.reyes@gmail.com', onboarding_step: 'done', email_verified: true }]
        : [],
    )
    const res = await GET(req('?code=abc&state=csrf-state'))
    expect(createCustomerAccount).not.toHaveBeenCalled()
    expect(mockSession.customerId).toBe('existing-uuid')
    expect(res.status).toBe(307)
  })

  it('links and signs in an existing, email-VERIFIED account with a matching email', async () => {
    ;(customerQuery as any).mockImplementation(async (sql: string) => {
      if (/auth_user_id/i.test(sql)) return []
      if (/WHERE email/i.test(sql)) {
        return [{ id: 'existing-uuid', email: 'dana.reyes@gmail.com', onboarding_step: 'done', email_verified: true }]
      }
      return []
    })
    const res = await GET(req('?code=abc&state=csrf-state'))
    expect(createCustomerAccount).not.toHaveBeenCalled()
    expect(customerExecute).toHaveBeenCalledWith(
      expect.stringMatching(/UPDATE users SET auth_user_id/i),
      ['existing-uuid', 'google:google-sub-1'],
    )
    expect(mockSession.customerId).toBe('existing-uuid')
    expect(res.headers.get('location')).toContain('/enroll')
  })

  it('refuses to auto-link an existing account whose OWN email is unverified', async () => {
    ;(customerQuery as any).mockImplementation(async (sql: string) => {
      if (/auth_user_id/i.test(sql)) return []
      if (/WHERE email/i.test(sql)) {
        return [{ id: 'existing-uuid', email: 'dana.reyes@gmail.com', onboarding_step: 'account_created', email_verified: false }]
      }
      return []
    })
    const res = await GET(req('?code=abc&state=csrf-state'))
    expect(createCustomerAccount).not.toHaveBeenCalled()
    expect(customerExecute).not.toHaveBeenCalledWith(expect.stringMatching(/UPDATE users SET auth_user_id/i), expect.anything())
    expect(mockSession.customerId).toBeUndefined()
    expect(res.headers.get('location')).toContain('googleError=unverified_existing')
  })

  it('redirects with an error and never signs in when Google reports denial', async () => {
    const res = await GET(req('?error=access_denied&state=csrf-state'))
    expect(res.headers.get('location')).toContain('googleError=denied')
    expect(mockSession.customerId).toBeUndefined()
  })

  it('redirects with an error when the code is missing', async () => {
    const res = await GET(req('?state=csrf-state'))
    expect(res.headers.get('location')).toContain('googleError=missing_code')
  })

  it('redirects with an error when the id_token fails verification', async () => {
    ;(verifyGoogleIdToken as any).mockResolvedValue(null)
    const res = await GET(req('?code=abc&state=csrf-state'))
    expect(res.headers.get('location')).toContain('googleError=invalid_token')
  })
})
