import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

// Mock iron-session so we control whether a session exists.
// NOTE: the factory creates the vi.fn() INLINE (no outer-variable reference) to
// avoid vitest's hoisting TDZ trap; control it via vi.mocked(getIronSession).
vi.mock('iron-session', () => ({ getIronSession: vi.fn() }))

import { getIronSession } from 'iron-session'
import { middleware, config } from '@/middleware'

beforeEach(() => {
  process.env.IRONFORGE_SESSION_SECRET = 'x'.repeat(32)
  process.env.IRONFORGE_SERVICE_TOKEN = 'svc-token'
  vi.mocked(getIronSession).mockReset()
})

function req(path: string, headers: Record<string, string> = {}) {
  return new NextRequest(`https://app.test${path}`, { headers })
}

describe('middleware gate', () => {
  it('401s a gated API route with no session', async () => {
    vi.mocked(getIronSession).mockResolvedValue({} as never)
    const res = await middleware(req('/api/spark/status'))
    expect(res.status).toBe(401)
  })

  it('redirects a gated page with no session to /login', async () => {
    vi.mocked(getIronSession).mockResolvedValue({} as never)
    const res = await middleware(req('/spark'))
    expect(res.status).toBe(307)
    expect(res.headers.get('location')).toContain('/login')
  })

  it('allows a gated route when a session exists', async () => {
    vi.mocked(getIronSession).mockResolvedValue({ userId: 1 } as never)
    const res = await middleware(req('/api/spark/status'))
    expect(res.status).toBe(200)
    expect(res.headers.get('location')).toBeNull()
  })

  it('allows the public /login path with no session', async () => {
    vi.mocked(getIronSession).mockResolvedValue({} as never)
    const res = await middleware(req('/login'))
    expect(res.status).toBe(200)
  })

  it('allows a request bearing a valid service token', async () => {
    vi.mocked(getIronSession).mockResolvedValue({} as never)
    const res = await middleware(req('/api/spark/status', { 'x-ironforge-service': 'svc-token' }))
    expect(res.status).toBe(200)
  })

  it('treats a thrown/invalid session as no session', async () => {
    vi.mocked(getIronSession).mockRejectedValue(new Error('bad cookie'))
    const res = await middleware(req('/api/spark/status'))
    expect(res.status).toBe(401)
  })
})

describe('matcher config (gate completeness)', () => {
  const matchers = config.matcher as string[]

  it('always gates every API route (no static-extension escape hatch)', () => {
    // Guards against the /api/ember/build.js bypass: an explicit /api matcher
    // must exist so no API path can be skipped by the asset-extension rule.
    expect(matchers).toContain('/api/:path*')
  })

  it('anchors the page asset-extension exclusion to the end of the path', () => {
    // Without the `$` anchor, any path merely CONTAINING ".js"/".css"/etc would
    // be skipped by middleware. The page matcher must end-anchor the extensions.
    const pageMatcher = matchers.find((m) => m.includes('_next/static'))
    expect(pageMatcher).toBeDefined()
    expect(pageMatcher).toContain('woff2?)$')
  })
})
