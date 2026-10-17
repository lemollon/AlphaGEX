import { describe, it, expect, vi, afterEach } from 'vitest'
import { GET } from '../route'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('GET /api/ember-fleet/pnl', () => {
  it('passes through the spreadworks-backend aggregate payload', async () => {
    const payload = {
      total_realized_pnl: 123.45,
      strategies_with_data: ['call_diag'],
      strategies_without_data: ['tv_book', 'spike'],
      by_strategy: {},
      trade_series: [],
    }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 })
    )
    const res = await GET()
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith(
      'https://spreadworks-backend.onrender.com/api/spreadworks/ember/pnl',
      expect.objectContaining({ cache: 'no-store' })
    )
  })

  it('returns a 502 with the error message when the upstream call fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', { status: 500 }))
    const res = await GET()
    expect(res.status).toBe(502)
    const body = await res.json()
    expect(body.error).toContain('500')
  })
})
