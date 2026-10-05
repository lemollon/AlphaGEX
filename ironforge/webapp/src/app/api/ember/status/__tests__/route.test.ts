import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/lib/ember-entitlement', () => ({ resolveEmberOwner: vi.fn() }))
vi.mock('@/lib/ember-trades', () => ({ getEmberStatus: vi.fn() }))

import { resolveEmberOwner } from '@/lib/ember-entitlement'
import { getEmberStatus } from '@/lib/ember-trades'
import { GET } from '../route'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('GET /api/ember/status', () => {
  it('403s when the signed-in customer does not own Ember', async () => {
    ;(resolveEmberOwner as any).mockResolvedValue(null)
    const res = await GET()
    expect(res.status).toBe(403)
    expect(getEmberStatus).not.toHaveBeenCalled()
  })

  it('returns the real status row for an entitled owner', async () => {
    ;(resolveEmberOwner as any).mockResolvedValue('cust-1')
    ;(getEmberStatus as any).mockResolvedValue({ state: 'ok', last_heartbeat: '2026-10-05T19:58:00Z', open_positions: [] })
    const res = await GET()
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.ok).toBe(true)
    expect(body.status.state).toBe('ok')
  })
})
