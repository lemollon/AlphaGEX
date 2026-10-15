import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/ember-entitlement', () => ({ resolveEmberOwner: vi.fn() }))
vi.mock('@/lib/ember-trades', () => ({ getEmberEquityCurve: vi.fn() }))

import { resolveEmberOwner } from '@/lib/ember-entitlement'
import { getEmberEquityCurve } from '@/lib/ember-trades'
import { GET } from '../route'

function req(url: string): NextRequest {
  return new NextRequest(new URL(url, 'http://localhost'))
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('GET /api/ember/equity-curve', () => {
  it('403s when the signed-in customer does not own Ember (and never queries the curve)', async () => {
    ;(resolveEmberOwner as any).mockResolvedValue(null)
    const res = await GET(req('/api/ember/equity-curve?period=day'))
    expect(res.status).toBe(403)
    const body = await res.json()
    expect(body.points).toEqual([])
    expect(getEmberEquityCurve).not.toHaveBeenCalled()
  })

  it('passes the requested period through to getEmberEquityCurve', async () => {
    ;(resolveEmberOwner as any).mockResolvedValue('cust-1')
    ;(getEmberEquityCurve as any).mockResolvedValue({ points: [{ timestamp: '2026-10-15T00:00:00Z', cumulative_pnl: 12.5 }], period_pnl: 12.5 })
    const res = await GET(req('/api/ember/equity-curve?period=month'))
    expect(res.status).toBe(200)
    expect(getEmberEquityCurve).toHaveBeenCalledWith('month')
    const body = await res.json()
    expect(body.ok).toBe(true)
    expect(body.period).toBe('month')
    expect(body.period_pnl).toBe(12.5)
  })

  it('falls back to "day" for a missing or invalid period param', async () => {
    ;(resolveEmberOwner as any).mockResolvedValue('cust-1')
    ;(getEmberEquityCurve as any).mockResolvedValue({ points: [], period_pnl: null })
    await GET(req('/api/ember/equity-curve?period=bogus'))
    expect(getEmberEquityCurve).toHaveBeenCalledWith('day')
  })

  it('500s cleanly on a DB failure, never a thrown error', async () => {
    ;(resolveEmberOwner as any).mockResolvedValue('cust-1')
    ;(getEmberEquityCurve as any).mockRejectedValue(new Error('db down'))
    const res = await GET(req('/api/ember/equity-curve?period=all'))
    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.ok).toBe(false)
  })
})
