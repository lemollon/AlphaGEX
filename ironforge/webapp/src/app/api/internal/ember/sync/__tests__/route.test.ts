import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/ember-trades', () => ({
  upsertEmberTrade: vi.fn(async () => {}),
  upsertEmberStatus: vi.fn(async () => {}),
}))

import { upsertEmberTrade, upsertEmberStatus } from '@/lib/ember-trades'
import { POST } from '../route'

function req(body: unknown, secret?: string): NextRequest {
  const headers: Record<string, string> = { 'content-type': 'application/json' }
  if (secret !== undefined) headers['x-ember-sync-secret'] = secret
  return new NextRequest('http://localhost/api/internal/ember/sync', {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  process.env.EMBER_SYNC_SECRET = 'test-secret'
})
afterEach(() => {
  delete process.env.EMBER_SYNC_SECRET
})

describe('POST /api/internal/ember/sync — auth', () => {
  it('503s when EMBER_SYNC_SECRET is not configured — never accepts an unauthenticated write', async () => {
    delete process.env.EMBER_SYNC_SECRET
    const res = await POST(req({ trades: [] }, 'anything'))
    expect(res.status).toBe(503)
    expect(upsertEmberTrade).not.toHaveBeenCalled()
  })

  it('401s with a missing secret header', async () => {
    const res = await POST(req({ trades: [] }))
    expect(res.status).toBe(401)
    expect(upsertEmberTrade).not.toHaveBeenCalled()
  })

  it('401s with a wrong secret', async () => {
    const res = await POST(req({ trades: [] }, 'wrong'))
    expect(res.status).toBe(401)
    expect(upsertEmberTrade).not.toHaveBeenCalled()
  })

  it('accepts the correct secret', async () => {
    const res = await POST(req({ trades: [] }, 'test-secret'))
    expect(res.status).toBe(200)
  })
})

describe('POST /api/internal/ember/sync — trade upserts', () => {
  it('upserts every valid trade and reports the count', async () => {
    const res = await POST(
      req(
        {
          trades: [
            { source_ref: 'SPY|2026-10-05', symbol: 'SPY', status: 'open', qty: 10 },
            { source_ref: 'QQQ|2026-10-05', symbol: 'QQQ', status: 'closed', pnl: 5.6 },
          ],
        },
        'test-secret',
      ),
    )
    const body = await res.json()
    expect(res.status).toBe(200)
    expect(body.ok).toBe(true)
    expect(body.upserted).toBe(2)
    expect(body.skipped).toEqual([])
    expect(upsertEmberTrade).toHaveBeenCalledTimes(2)
  })

  it('skips a malformed row without failing the rest of the batch', async () => {
    const res = await POST(
      req(
        {
          trades: [
            { source_ref: '', symbol: 'SPY', status: 'open' }, // missing source_ref
            { source_ref: 'QQQ|2026-10-05', symbol: 'QQQ', status: 'closed' },
          ],
        },
        'test-secret',
      ),
    )
    const body = await res.json()
    expect(body.ok).toBe(true)
    expect(body.upserted).toBe(1)
    expect(body.skipped).toEqual([{ index: 0, reason: 'missing source_ref' }])
    expect(upsertEmberTrade).toHaveBeenCalledTimes(1)
  })

  it('syncs the status heartbeat when present', async () => {
    const res = await POST(
      req(
        {
          trades: [],
          status: { state: 'ok', last_heartbeat: '2026-10-05T19:58:00Z', open_positions: [] },
        },
        'test-secret',
      ),
    )
    const body = await res.json()
    expect(body.statusSynced).toBe(true)
    expect(upsertEmberStatus).toHaveBeenCalledWith({
      state: 'ok',
      lastHeartbeat: '2026-10-05T19:58:00Z',
      openPositions: [],
    })
  })

  it('rejects an unparseable body', async () => {
    const r = new NextRequest('http://localhost/api/internal/ember/sync', {
      method: 'POST',
      headers: { 'x-ember-sync-secret': 'test-secret', 'content-type': 'application/json' },
      body: 'not json',
    })
    const res = await POST(r)
    expect(res.status).toBe(400)
  })
})
