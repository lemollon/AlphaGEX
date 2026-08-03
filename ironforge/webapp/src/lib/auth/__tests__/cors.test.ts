import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
  isCorsEnabled,
  resolveAllowedOrigin,
  corsHeaders,
  preflightResponse,
} from '@/lib/auth/cors'

const DEV = 'http://localhost:8081'
const PREVIEW = 'http://127.0.0.1:8099'

describe('cors', () => {
  const saved = process.env.CORS_ALLOWED_ORIGINS

  beforeEach(() => {
    process.env.CORS_ALLOWED_ORIGINS = `${DEV},${PREVIEW}`
  })
  afterEach(() => {
    if (saved === undefined) delete process.env.CORS_ALLOWED_ORIGINS
    else process.env.CORS_ALLOWED_ORIGINS = saved
  })

  // The production state. If this ever stops being true, CORS has leaked into prod.
  describe('off by default', () => {
    it('is disabled when the env var is unset', () => {
      delete process.env.CORS_ALLOWED_ORIGINS
      expect(isCorsEnabled()).toBe(false)
      expect(resolveAllowedOrigin(DEV)).toBeNull()
      expect(preflightResponse('OPTIONS', DEV, '/api/live/summary')).toBeNull()
    })

    it('is disabled when the env var is empty or whitespace', () => {
      for (const v of ['', '   ', ',', ' , ']) {
        process.env.CORS_ALLOWED_ORIGINS = v
        expect(isCorsEnabled()).toBe(false)
        expect(resolveAllowedOrigin(DEV)).toBeNull()
      }
    })
  })

  describe('allowlist is exact-match only', () => {
    it('echoes an allowed origin verbatim', () => {
      expect(resolveAllowedOrigin(DEV)).toBe(DEV)
      expect(resolveAllowedOrigin(PREVIEW)).toBe(PREVIEW)
    })

    it('refuses anything not on the list', () => {
      for (const o of [
        'https://evil.example',
        'null',
        '*',
        'http://localhost:8082', // different port
        'https://localhost:8081', // different scheme
        'http://localhost:8081/', // trailing slash
      ]) {
        expect(resolveAllowedOrigin(o), o).toBeNull()
      }
    })

    // The classic bypass: a domain that CONTAINS an allowed one. Substring or
    // suffix matching would let evil-ironforge.trade through.
    it('is not fooled by prefix/suffix lookalikes', () => {
      process.env.CORS_ALLOWED_ORIGINS = 'https://ironforge.trade'
      for (const o of [
        'https://evil-ironforge.trade',
        'https://ironforge.trade.evil.com',
        'https://ironforge.trade@evil.com',
        'https://notironforge.trade',
      ]) {
        expect(resolveAllowedOrigin(o), o).toBeNull()
      }
      expect(resolveAllowedOrigin('https://ironforge.trade')).toBe('https://ironforge.trade')
    })

    it('refuses missing/empty origins', () => {
      expect(resolveAllowedOrigin(null)).toBeNull()
      expect(resolveAllowedOrigin(undefined)).toBeNull()
      expect(resolveAllowedOrigin('')).toBeNull()
    })
  })

  describe('headers', () => {
    // THE important assertion. With credentials allowed, a browser would attach the
    // ironforge_customer cookie to cross-origin requests and an allowed origin could
    // ride a signed-in customer's web session. Without it, only the mobile bearer
    // token works cross-origin — and that lives where another origin cannot read it.
    it('NEVER allows credentials', () => {
      const h = corsHeaders(DEV)
      expect(h['Access-Control-Allow-Credentials']).toBeUndefined()
      expect(Object.keys(h).join(',').toLowerCase()).not.toContain('credentials')
    })

    it('never emits a wildcard origin', () => {
      expect(corsHeaders(DEV)['Access-Control-Allow-Origin']).toBe(DEV)
      expect(Object.values(corsHeaders(DEV))).not.toContain('*')
    })

    it('varies on Origin so a cache cannot cross-serve', () => {
      expect(corsHeaders(DEV).Vary).toBe('Origin')
    })

    it('allows the Authorization header — the entire point', () => {
      expect(corsHeaders(DEV)['Access-Control-Allow-Headers']).toContain('Authorization')
    })
  })

  describe('preflight', () => {
    it('answers OPTIONS from an allowed origin with 204 + headers', () => {
      const r = preflightResponse('OPTIONS', DEV, '/api/live/summary')
      expect(r).not.toBeNull()
      expect(r!.status).toBe(204)
      expect(r!.headers.get('Access-Control-Allow-Origin')).toBe(DEV)
      expect(r!.headers.get('Access-Control-Allow-Credentials')).toBeNull()
    })

    it('ignores OPTIONS from a disallowed origin, so the gate still applies', () => {
      expect(preflightResponse('OPTIONS', 'https://evil.example', '/api/live/summary')).toBeNull()
    })

    it('ignores non-OPTIONS methods', () => {
      for (const m of ['GET', 'POST', 'DELETE']) {
        expect(preflightResponse(m, DEV, '/api/live/summary')).toBeNull()
      }
    })

    // Pages have no reason to be read cross-origin, and answering a preflight for
    // them would widen the surface for nothing.
    it('only applies to /api/*', () => {
      expect(preflightResponse('OPTIONS', DEV, '/live')).toBeNull()
      expect(preflightResponse('OPTIONS', DEV, '/')).toBeNull()
      expect(preflightResponse('OPTIONS', DEV, '/api/live/summary')).not.toBeNull()
    })
  })
})
