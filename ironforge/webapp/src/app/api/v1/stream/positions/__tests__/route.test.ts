import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/live/summary', () => ({ getLiveTrade: vi.fn() }))
vi.mock('@/lib/live/viewer', async () => {
  const actual = await vi.importActual<typeof import('@/lib/live/viewer')>('@/lib/live/viewer')
  return { ...actual, resolveLiveViewer: vi.fn() }
})

import { getLiveTrade } from '@/lib/live/summary'
import { resolveLiveViewer } from '@/lib/live/viewer'
import { _resetStreamRegistryForTest, currentStreamCount } from '@/lib/live/stream-registry'
import { GET } from '../route'

type MockViewer = Awaited<ReturnType<typeof resolveLiveViewer>>

const CUSTOMER_VIEWER: MockViewer = {
  bot: 'spark',
  allowedBots: ['spark'],
  isOperator: false,
  person: 'Logan',
  persons: { spark: 'Logan' },
  paperBots: [],
  customerId: 'cust_1',
}

function req(qs = '') {
  return new NextRequest(`https://app.test/api/v1/stream/positions${qs}`)
}

/** Reads exactly one SSE frame off the response body, then releases the reader
 *  (triggering the stream's own `cancel()` cleanup) without waiting out any
 *  interval timer. */
async function readOneFrame(res: Response): Promise<{ text: string; cancel: () => Promise<void> }> {
  const reader = res.body!.getReader()
  const { value } = await reader.read()
  const text = new TextDecoder().decode(value)
  return { text, cancel: () => reader.cancel() }
}

beforeEach(() => {
  vi.clearAllMocks()
  _resetStreamRegistryForTest()
  ;(getLiveTrade as any).mockResolvedValue({ active: false, positions: [] })
})

afterEach(() => {
  _resetStreamRegistryForTest()
})

describe('GET /api/v1/stream/positions', () => {
  it('returns an empty-state SSE frame for a viewer with no mapped bot', async () => {
    ;(resolveLiveViewer as any).mockResolvedValue({
      bot: null,
      allowedBots: [],
      isOperator: false,
      person: null,
      persons: {},
      paperBots: [],
      customerId: null,
    } satisfies MockViewer)

    const res = await GET(req())
    expect(res.headers.get('Content-Type')).toContain('text/event-stream')
    const { text } = await readOneFrame(res)
    expect(text).toContain('event: positions')
    expect(text).toContain('"empty":true')
    expect(getLiveTrade).not.toHaveBeenCalled()
  })

  it('scopes to the viewer\'s own mapped bot — never a bot it does not own', async () => {
    ;(resolveLiveViewer as any).mockResolvedValue(CUSTOMER_VIEWER)
    ;(getLiveTrade as any).mockResolvedValue({ active: true, positions: [{ position_id: 'p1' }] })

    const res = await GET(req('?account=flame')) // not in allowedBots
    const { text, cancel } = await readOneFrame(res)
    expect(text).toContain('event: positions')
    // Scoped to zero bots rather than silently falling back to spark's data.
    expect(getLiveTrade).not.toHaveBeenCalled()
    await cancel()
  })

  it('pushes the same LiveTrade payload /api/live/trade serves, for ?account=<owned bot>', async () => {
    ;(resolveLiveViewer as any).mockResolvedValue(CUSTOMER_VIEWER)
    const trade = { active: true, unrealized_pnl: 42, positions: [{ position_id: 'p1' }] }
    ;(getLiveTrade as any).mockResolvedValue(trade)

    const res = await GET(req('?account=spark'))
    const { text, cancel } = await readOneFrame(res)
    expect(getLiveTrade).toHaveBeenCalledWith('spark', 'Logan', false)
    expect(text).toContain('"unrealized_pnl":42')
    await cancel()
  })

  it('wraps every allowed bot when no ?account is given (mobile multi-agent shape)', async () => {
    const multiViewer: MockViewer = {
      ...CUSTOMER_VIEWER,
      bot: 'spark',
      allowedBots: ['spark', 'flame'],
      persons: { spark: 'Logan', flame: null },
    }
    ;(resolveLiveViewer as any).mockResolvedValue(multiViewer)
    ;(getLiveTrade as any).mockResolvedValue({ active: false, positions: [] })

    const res = await GET(req())
    const { text, cancel } = await readOneFrame(res)
    expect(getLiveTrade).toHaveBeenCalledWith('spark', 'Logan', false)
    expect(getLiveTrade).toHaveBeenCalledWith('flame', null, false)
    expect(text).toContain('"agents"')
    await cancel()
  })

  it('releases its slot on cancel — a disconnected client does not pin the cap forever', async () => {
    ;(resolveLiveViewer as any).mockResolvedValue(CUSTOMER_VIEWER)

    const res = await GET(req('?account=spark'))
    const { cancel } = await readOneFrame(res)
    expect(currentStreamCount('cust_1')).toBe(1)
    await cancel()
    expect(currentStreamCount('cust_1')).toBe(0)
  })

  it('caps concurrent streams per viewer and 429s past the limit', async () => {
    ;(resolveLiveViewer as any).mockResolvedValue(CUSTOMER_VIEWER)

    const open1 = await readOneFrame(await GET(req('?account=spark')))
    const open2 = await readOneFrame(await GET(req('?account=spark')))
    const open3 = await readOneFrame(await GET(req('?account=spark')))
    expect(currentStreamCount('cust_1')).toBe(3)

    const blocked = await GET(req('?account=spark'))
    expect(blocked.status).toBe(429)

    // Freeing one slot immediately lets the next connection through.
    await open1.cancel()
    expect(currentStreamCount('cust_1')).toBe(2)
    const open4 = await readOneFrame(await GET(req('?account=spark')))
    expect(currentStreamCount('cust_1')).toBe(3)

    await open2.cancel()
    await open3.cancel()
    await open4.cancel()
    expect(currentStreamCount('cust_1')).toBe(0)
  })

  it('caps operators/anonymous viewers by bot+person instead of a missing customerId', async () => {
    const opViewer: MockViewer = {
      bot: 'spark',
      allowedBots: ['spark', 'flame'],
      isOperator: true,
      person: null,
      persons: { spark: null, flame: null },
      paperBots: ['flame'],
      customerId: null,
    }
    ;(resolveLiveViewer as any).mockResolvedValue(opViewer)

    const res = await GET(req('?account=spark'))
    const { cancel } = await readOneFrame(res)
    expect(currentStreamCount('operator:spark:')).toBe(1)
    await cancel()
    expect(currentStreamCount('operator:spark:')).toBe(0)
  })
})
