import { describe, it, expect, vi, afterEach } from 'vitest'
import { GET } from '../route'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('GET /api/ember-fleet/status', () => {
  it('passes through the spreadworks-backend fleet status payload', async () => {
    const payload = { strategies: [{ strategy: 'xsp_flow', enabled: true }] }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 })
    )
    const res = await GET()
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith(
      'https://spreadworks-backend.onrender.com/api/spreadworks/ember/status',
      expect.objectContaining({ cache: 'no-store' })
    )
  })

  it('returns a 502 with the error message when the upstream call fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', { status: 503 }))
    const res = await GET()
    expect(res.status).toBe(502)
    const body = await res.json()
    expect(body.error).toContain('503')
  })
})
