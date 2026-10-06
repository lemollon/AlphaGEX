import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/auth/server', () => ({ getSession: vi.fn() }))
vi.mock('@/lib/auth/access', () => ({ isPublicMode: vi.fn(() => false) }))
vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: vi.fn(() => true),
  customerQuery: vi.fn(async () => []),
}))

import { getSession } from '@/lib/auth/server'
import { isPublicMode } from '@/lib/auth/access'
import { customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'
import { GET } from '../summary/route'

function call(qs = '') {
  return GET(new NextRequest(`https://app.test/api/ops/analytics/summary${qs}`))
}

beforeEach(() => {
  vi.clearAllMocks()
  ;(isPublicMode as any).mockReturnValue(false)
  ;(getSession as any).mockResolvedValue({ userId: null })
  ;(isCustomersDbConfigured as any).mockReturnValue(true)
  ;(customerQuery as any).mockResolvedValue([])
})

describe('GET /api/ops/analytics/summary', () => {
  it('401 without an operator session', async () => {
    const res = await call()
    expect(res.status).toBe(401)
  })

  it('allows a public-mode deployment through with no session', async () => {
    ;(isPublicMode as any).mockReturnValue(true)
    const res = await call()
    expect(res.status).toBe(200)
  })

  it('shapes counts into day -> event -> count and the funnel in rail order', async () => {
    ;(getSession as any).mockResolvedValue({ userId: 'ops1' })
    ;(customerQuery as any)
      .mockResolvedValueOnce([
        { day: '2026-10-01', event: 'cta_click', c: 12 },
        { day: '2026-10-01', event: 'waitlist_open', c: 3 },
      ])
      .mockResolvedValueOnce([
        { step: 'legal', viewers: 50, completers: 40 },
        { step: 'account', viewers: 80, completers: 70 },
      ])

    const res = await call('?days=7')
    const json = await res.json()
    expect(res.status).toBe(200)
    expect(json.counts['2026-10-01']).toEqual({ cta_click: 12, waitlist_open: 3 })
    expect(json.enrollFunnel.map((f: any) => f.step)).toEqual([
      'account',
      'legal',
      'plan',
      'broker',
      'billing',
      'review',
      'done',
    ])
    expect(json.enrollFunnel[0]).toEqual({ step: 'account', viewers: 80, completers: 70 })
    expect(json.enrollFunnel[1]).toEqual({ step: 'legal', viewers: 50, completers: 40 })
    expect(json.enrollFunnel[2]).toEqual({ step: 'plan', viewers: 0, completers: 0 })
  })

  it('503 when the customers DB is not configured', async () => {
    ;(getSession as any).mockResolvedValue({ userId: 'ops1' })
    ;(isCustomersDbConfigured as any).mockReturnValue(false)
    const res = await call()
    expect(res.status).toBe(503)
  })

  it('clamps days to the 90-day max', async () => {
    ;(getSession as any).mockResolvedValue({ userId: 'ops1' })
    const res = await call('?days=9999')
    const json = await res.json()
    expect(json.days).toBe(90)
  })
})
