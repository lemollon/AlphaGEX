import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/auth/google-oauth', () => ({
  isGoogleOAuthConfigured: vi.fn(() => true),
  buildAuthorizeUrl: vi.fn(() => 'https://accounts.google.com/o/oauth2/v2/auth?mock=1'),
  googleRedirectUri: (origin: string) => `${origin}/api/auth/google/callback`,
}))

vi.mock('@/lib/auth/google-oauth-cookie', () => ({
  signGoogleOAuthState: vi.fn(async () => 'signed-cookie-value'),
  GOOGLE_OAUTH_COOKIE: 'ironforge_google_oauth',
  googleOAuthCookieOptions: () => ({ httpOnly: true, path: '/api/auth/google' }),
}))

import { signGoogleOAuthState } from '@/lib/auth/google-oauth-cookie'
import { GET } from '../start/route'

function req(qs: string) {
  return new NextRequest(`https://ironforge.trade/api/auth/google/start${qs}`)
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('GET /api/auth/google/start', () => {
  it('leaves consents undefined when the caller (e.g. /login) sends none — no implied consent', async () => {
    await GET(req('?next=%2Fenroll'))
    expect(signGoogleOAuthState).toHaveBeenCalledWith(
      expect.objectContaining({ next: '/enroll', consents: undefined }),
    )
  })

  it('carries the 3 consent flags exactly as sent by /signup', async () => {
    await GET(req('?next=%2Fenroll&ageConfirmed=1&noAdvice=1&commConsent=1'))
    expect(signGoogleOAuthState).toHaveBeenCalledWith(
      expect.objectContaining({
        consents: { ageConfirmed: true, noAdviceAcknowledged: true, electronicCommConsent: true },
      }),
    )
  })

  it('never defaults a missing or malformed flag to true', async () => {
    // ageConfirmed sent as "1", but noAdvice/commConsent are garbage/missing.
    await GET(req('?ageConfirmed=1&noAdvice=yes'))
    expect(signGoogleOAuthState).toHaveBeenCalledWith(
      expect.objectContaining({
        consents: { ageConfirmed: true, noAdviceAcknowledged: false, electronicCommConsent: false },
      }),
    )
  })
})
