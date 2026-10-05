import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { generateKeyPairSync, sign as cryptoSign } from 'crypto'
import {
  verifyGoogleIdToken,
  deriveUsernameBase,
  isGoogleOAuthConfigured,
  buildAuthorizeUrl,
  resetGoogleJwksCacheForTests,
  type GoogleIdClaims,
} from '@/lib/auth/google-oauth'

const CLIENT_ID = 'test-client-id.apps.googleusercontent.com'
const KID = 'test-kid-1'

function b64url(buf: Buffer): string {
  return buf.toString('base64url')
}

// One RSA keypair for the whole suite — generating is slow, and every test either
// signs with it or expects a real RS256 signature to verify against its public half.
const { publicKey, privateKey } = generateKeyPairSync('rsa', { modulusLength: 2048 })
const publicJwk = publicKey.export({ format: 'jwk' }) as { n: string; e: string }

function signToken(payload: Record<string, unknown>, opts: { kid?: string; alg?: string } = {}): string {
  const header = { alg: opts.alg ?? 'RS256', kid: opts.kid ?? KID, typ: 'JWT' }
  const headerB64 = b64url(Buffer.from(JSON.stringify(header)))
  const payloadB64 = b64url(Buffer.from(JSON.stringify(payload)))
  const signingInput = Buffer.from(`${headerB64}.${payloadB64}`)
  const signature = cryptoSign('RSA-SHA256', signingInput, privateKey)
  return `${headerB64}.${payloadB64}.${b64url(signature)}`
}

function validPayload(overrides: Record<string, unknown> = {}) {
  const now = Math.floor(Date.now() / 1000)
  return {
    iss: 'https://accounts.google.com',
    aud: CLIENT_ID,
    sub: '1234567890',
    email: 'Dana.Reyes@Gmail.com',
    email_verified: true,
    given_name: 'Dana',
    family_name: 'Reyes',
    iat: now - 10,
    exp: now + 3600,
    ...overrides,
  }
}

describe('google-oauth: verifyGoogleIdToken', () => {
  const savedEnv = { ...process.env }
  const savedFetch = global.fetch

  beforeEach(() => {
    process.env.GOOGLE_CLIENT_ID = CLIENT_ID
    process.env.GOOGLE_CLIENT_SECRET = 'test-secret'
    resetGoogleJwksCacheForTests()
    global.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ keys: [{ kid: KID, kty: 'RSA', n: publicJwk.n, e: publicJwk.e, alg: 'RS256', use: 'sig' }] }), {
        status: 200,
      }),
    ) as unknown as typeof fetch
  })
  afterEach(() => {
    process.env = { ...savedEnv }
    global.fetch = savedFetch
    resetGoogleJwksCacheForTests()
  })

  it('accepts a correctly signed token with valid claims', async () => {
    const token = signToken(validPayload())
    const claims = await verifyGoogleIdToken(token)
    expect(claims).not.toBeNull()
    expect(claims!.sub).toBe('1234567890')
    expect(claims!.email).toBe('Dana.Reyes@Gmail.com')
    expect(claims!.emailVerified).toBe(true)
    expect(claims!.givenName).toBe('Dana')
  })

  it('rejects a token whose signature does not match (tampered payload)', async () => {
    const token = signToken(validPayload())
    const [header, payload, sig] = token.split('.')
    const forgedPayload = Buffer.from(JSON.stringify(validPayload({ email: 'attacker@gmail.com' }))).toString(
      'base64url',
    )
    expect(await verifyGoogleIdToken(`${header}.${forgedPayload}.${sig}`)).toBeNull()
  })

  it('rejects a token signed by a key not in the JWKS (wrong kid)', async () => {
    const token = signToken(validPayload(), { kid: 'some-other-kid' })
    expect(await verifyGoogleIdToken(token)).toBeNull()
  })

  it('rejects an algorithm other than RS256', async () => {
    const token = signToken(validPayload(), { alg: 'HS256' })
    expect(await verifyGoogleIdToken(token)).toBeNull()
  })

  it('rejects the wrong audience', async () => {
    const token = signToken(validPayload({ aud: 'someone-elses-client-id' }))
    expect(await verifyGoogleIdToken(token)).toBeNull()
  })

  it('rejects an untrusted issuer', async () => {
    const token = signToken(validPayload({ iss: 'https://evil.example.com' }))
    expect(await verifyGoogleIdToken(token)).toBeNull()
  })

  it('rejects an expired token', async () => {
    const now = Math.floor(Date.now() / 1000)
    const token = signToken(validPayload({ exp: now - 10 }))
    expect(await verifyGoogleIdToken(token)).toBeNull()
  })

  it('surfaces email_verified so the caller can reject an unverified Google email', async () => {
    const token = signToken(validPayload({ email_verified: false }))
    const claims = await verifyGoogleIdToken(token)
    expect(claims).not.toBeNull()
    expect(claims!.emailVerified).toBe(false)
  })

  it('rejects malformed tokens without throwing', async () => {
    for (const bad of ['', 'not-a-jwt', 'a.b', 'a.b.c.d']) {
      expect(await verifyGoogleIdToken(bad)).toBeNull()
    }
  })
})

describe('google-oauth: config + helpers', () => {
  const savedEnv = { ...process.env }
  afterEach(() => {
    process.env = { ...savedEnv }
  })

  it('isGoogleOAuthConfigured requires BOTH client id and secret', () => {
    delete process.env.GOOGLE_CLIENT_ID
    delete process.env.GOOGLE_CLIENT_SECRET
    expect(isGoogleOAuthConfigured()).toBe(false)
    process.env.GOOGLE_CLIENT_ID = 'id-only'
    expect(isGoogleOAuthConfigured()).toBe(false)
    process.env.GOOGLE_CLIENT_SECRET = 'secret-too'
    expect(isGoogleOAuthConfigured()).toBe(true)
  })

  it('buildAuthorizeUrl carries state, PKCE challenge, and S256 method', () => {
    process.env.GOOGLE_CLIENT_ID = CLIENT_ID
    const url = new URL(
      buildAuthorizeUrl({ state: 'xyz', codeChallenge: 'chal123', redirectUri: 'https://ironforge.trade/api/auth/google/callback' }),
    )
    expect(url.searchParams.get('state')).toBe('xyz')
    expect(url.searchParams.get('code_challenge')).toBe('chal123')
    expect(url.searchParams.get('code_challenge_method')).toBe('S256')
    expect(url.searchParams.get('redirect_uri')).toBe('https://ironforge.trade/api/auth/google/callback')
    expect(url.searchParams.get('response_type')).toBe('code')
  })

  it('deriveUsernameBase sanitizes to the app username charset and starts with a letter', () => {
    const claims: GoogleIdClaims = {
      sub: '1',
      email: '7weird.chars+tag@gmail.com',
      emailVerified: true,
      givenName: "O'Brien-7!",
      familyName: null,
      picture: null,
    }
    const base = deriveUsernameBase(claims)
    expect(/^[a-z][a-z0-9_]*$/.test(base)).toBe(true)
    expect(base.length).toBeGreaterThanOrEqual(3)
  })
})
