import { describe, it, expect, afterEach } from 'vitest'
import { createHash } from 'crypto'
import { generateCodeVerifier, codeChallengeS256, OAUTH_STATE_TTL_MS } from '../oauth-state'
import { buildAuthorizeUrl, tradierPkceEnabled } from '@/lib/tradier-oauth'

/**
 * PKCE + state, the pure halves. The one-time-use guarantee lives in a single SQL
 * UPDATE and is asserted by reading that statement rather than by mocking a database:
 * see oauth-state.ts consumeOAuthState.
 */

describe('PKCE (RFC 7636)', () => {
  it('verifier is 43-128 unreserved characters', () => {
    for (let i = 0; i < 20; i++) {
      const v = generateCodeVerifier()
      expect(v.length).toBeGreaterThanOrEqual(43)
      expect(v.length).toBeLessThanOrEqual(128)
      // base64url alphabet only — no padding, no + or /
      expect(v).toMatch(/^[A-Za-z0-9\-_]+$/)
    }
  })

  it('verifiers are unique — a reused one would defeat the point', () => {
    const seen = new Set(Array.from({ length: 200 }, () => generateCodeVerifier()))
    expect(seen.size).toBe(200)
  })

  it('challenge is BASE64URL(SHA256(ASCII(verifier))) exactly', () => {
    const v = 'dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'
    const expected = createHash('sha256').update(v, 'ascii').digest('base64url')
    expect(codeChallengeS256(v)).toBe(expected)
  })

  it('the challenge is one-way — it never reveals the verifier', () => {
    const v = generateCodeVerifier()
    const c = codeChallengeS256(v)
    expect(c).not.toBe(v)
    expect(c).not.toContain(v.slice(0, 20))
  })

  it('state TTL is 10 minutes (§3 BROKER-01), not the old 15', () => {
    expect(OAUTH_STATE_TTL_MS).toBe(10 * 60 * 1000)
  })
})

describe('authorize URL', () => {
  const ENV_KEYS = ['TRADIER_OAUTH_CLIENT_ID', 'TRADIER_OAUTH_PKCE'] as const
  afterEach(() => { for (const k of ENV_KEYS) delete process.env[k] })

  it('omits PKCE params entirely when no challenge is supplied', () => {
    process.env.TRADIER_OAUTH_CLIENT_ID = 'cid'
    const u = buildAuthorizeUrl('state123')
    expect(u).toContain('state=state123')
    // Sending a challenge a provider ignores, then a verifier it does not expect,
    // can break the exchange — so absent must mean fully absent.
    expect(u).not.toContain('code_challenge')
    expect(u).not.toContain('code_challenge_method')
  })

  it('sends S256 when a challenge IS supplied', () => {
    process.env.TRADIER_OAUTH_CLIENT_ID = 'cid'
    const u = buildAuthorizeUrl('state123', 'chal')
    expect(u).toContain('code_challenge=chal')
    expect(u).toContain('code_challenge_method=S256')
  })

  it('PKCE defaults OFF until confirmed with the provider', () => {
    delete process.env.TRADIER_OAUTH_PKCE
    expect(tradierPkceEnabled()).toBe(false)
    process.env.TRADIER_OAUTH_PKCE = 'true'
    expect(tradierPkceEnabled()).toBe(true)
  })
})
