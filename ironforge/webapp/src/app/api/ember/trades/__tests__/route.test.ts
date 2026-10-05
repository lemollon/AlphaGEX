import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/lib/ember-entitlement', () => ({ resolveEmberOwner: vi.fn() }))
vi.mock('@/lib/ember-trades', () => ({ getEmberTrades: vi.fn() }))

import { resolveEmberOwner } from '@/lib/ember-entitlement'
import { getEmberTrades } from '@/lib/ember-trades'
import { GET } from '../route'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('GET /api/ember/trades', () => {
  it('403s when the signed-in customer does not own Ember (and never queries trades)', async () => {
    ;(resolveEmberOwner as any).mockResolvedValue(null)
    const res = await GET()
    expect(res.status).toBe(403)
    const body = await res.json()
    expect(body.trades).toEqual([])
    expect(getEmberTrades).not.toHaveBeenCalled()
  })

  it('returns the real trade rows for an entitled owner', async () => {
    ;(resolveEmberOwner as any).mockResolvedValue('cust-1')
    ;(getEmberTrades as any).mockResolvedValue([{ id: 1, symbol: 'SPY' }])
    const res = await GET()
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.ok).toBe(true)
    expect(body.trades).toEqual([{ id: 1, symbol: 'SPY' }])
  })

  it('500s cleanly on a DB failure, never a thrown error', async () => {
    ;(resolveEmberOwner as any).mockResolvedValue('cust-1')
    ;(getEmberTrades as any).mockRejectedValue(new Error('db down'))
    const res = await GET()
    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.ok).toBe(false)
  })
})
