import { NextRequest } from 'next/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * Route-level tests with the database mocked.
 *
 * These exercise the real orchestrator, projection, KPI math, snapshot digest
 * and cursor signing — everything below the HTTP boundary — so the only thing
 * standing in for production is the row fixture.
 */

interface Row {
  id: number
  position_id: string
  ticker: string
  contracts: number
  realized_pnl: string
  bp: string
  put_short_strike: string
  put_long_strike: string
  call_short_strike: string
  call_long_strike: string
  status: string
  close_time: string
  et_date: string
  ct_date: string
}

function row(id: number, pnl: string, closeIso: string, over: Partial<Row> = {}): Row {
  return {
    id,
    position_id: `pos-${id}`,
    ticker: 'SPY',
    contracts: 1,
    realized_pnl: pnl,
    bp: '500.00',
    put_short_strike: '618.00',
    put_long_strike: '613.00',
    call_short_strike: '628.00',
    call_long_strike: '633.00',
    status: 'closed',
    close_time: closeIso,
    et_date: closeIso.slice(0, 10),
    ct_date: closeIso.slice(0, 10),
    ...over,
  }
}

// Close times are relative to "now" so they land inside both windows.
const DAY = 86_400_000
function isoDaysAgo(days: number): string {
  return new Date(Date.now() - days * DAY).toISOString()
}

const SPARK_ROWS = () => [
  row(1, '42.00', isoDaysAgo(1)),
  row(2, '-26.00', isoDaysAgo(2)),
  row(3, '39.00', isoDaysAgo(3)),
]
const FLAME_ROWS = () => [
  row(11, '94.00', isoDaysAgo(1), { call_short_strike: '0', call_long_strike: '0' }),
  row(12, '81.00', isoDaysAgo(4), { call_short_strike: '0', call_long_strike: '0' }),
]

function sumPnl(rows: Row[]): string {
  return rows.reduce((a, r) => a + Number(r.realized_pnl), 0).toFixed(2)
}

vi.mock('@/lib/db', () => ({
  botTable: (bot: string, suffix: string) => `${bot}_${suffix}`,
  dteMode: (bot: string) => (bot === 'flame' ? '2DTE' : '1DTE'),
  escapeSql: (s: string) => String(s).replace(/'/g, "''"),
  num: (v: unknown) => Number(v),
  int: (v: unknown) => parseInt(String(v), 10),
  dbQuery: vi.fn(async (sql: string) => {
    const isFlame = sql.includes('flame_positions')
    const rows = isFlame ? FLAME_ROWS() : SPARK_ROWS()
    if (sql.includes('WITH deduped')) {
      return [{ raw_count: rows.length, deduped_count: rows.length, pnl_total: sumPnl(rows) }]
    }
    return rows
  }),
}))

const { GET: summaryGET } = await import('../summary/route')
const { GET: tradesGET } = await import('../trades/route')

function req(url: string): NextRequest {
  return new NextRequest(new URL(url, 'http://localhost'))
}

beforeEach(() => {
  process.env.IRONFORGE_SESSION_SECRET = 'test-secret-for-bot-ledger-routes'
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('GET /api/public/bot-ledger/summary', () => {
  it('returns both bots with every decimal as a string', async () => {
    const res = await summaryGET(req('/api/public/bot-ledger/summary?period=30d'))
    expect(res.status).toBe(200)

    const body = await res.json()
    expect(body.bots).toHaveLength(2)
    expect(body.bots.map((b: { bot: string }) => b.bot)).toEqual(['spark', 'flame'])

    const spark = body.bots[0]
    expect(spark.closed_trades).toBe(3)
    expect(spark.wins).toBe(2)
    expect(spark.losses).toBe(1)
    expect(typeof spark.win_rate_pct).toBe('string')
    expect(typeof spark.avg_return_on_bp_pct).toBe('string')
    expect(typeof spark.profit_factor).toBe('string')
    expect(spark.win_rate_pct).toBe('66.67')
    // (42 + 39) / 26
    expect(spark.profit_factor).toBe('3.12')
  })

  it('marks the payload reconciled and states the net basis', async () => {
    const res = await summaryGET(req('/api/public/bot-ledger/summary?period=30d'))
    const body = await res.json()
    expect(body.reconciled).toBe(true)
    expect(body.net_basis).toBe('gross_of_commissions')
    expect(body.calculation_version).toBe(1)
  })

  it('caches successful responses', async () => {
    const res = await summaryGET(req('/api/public/bot-ledger/summary?period=7d'))
    expect(res.headers.get('Cache-Control')).toBe('public, max-age=300, stale-while-revalidate=600')
  })

  it('defaults to 30d and rejects an unsupported period without caching', async () => {
    const dflt = await summaryGET(req('/api/public/bot-ledger/summary'))
    expect((await dflt.json()).period).toBe('30d')

    const bad = await summaryGET(req('/api/public/bot-ledger/summary?period=90d'))
    expect(bad.status).toBe(400)
    expect((await bad.json()).error_code).toBe('INVALID_PERIOD')
    expect(bad.headers.get('Cache-Control')).toBe('no-store')
  })

  it('never exposes a proprietary field', async () => {
    const res = await summaryGET(req('/api/public/bot-ledger/summary?period=30d'))
    const raw = JSON.stringify(await res.json())
    for (const forbidden of [
      'position_id',
      'close_reason',
      'spread_width',
      'account_type',
      'person',
      'put_short_strike',
      'realized_pnl',
      'collateral_required',
    ]) {
      expect(raw).not.toContain(forbidden)
    }
  })
})

describe('GET /api/public/bot-ledger/trades', () => {
  it('returns the allowlisted DTO only', async () => {
    const res = await tradesGET(req('/api/public/bot-ledger/trades?bot=all'))
    expect(res.status).toBe(200)

    const body = await res.json()
    expect(body.items.length).toBe(5)
    expect(Object.keys(body.items[0]).sort()).toEqual([
      'bot',
      'buying_power_used',
      'closed_date',
      'net_result',
      'outcome',
      'public_id',
      'return_on_bp_pct',
      'setup',
    ])
  })

  it('sorts newest first across both bots', async () => {
    const res = await tradesGET(req('/api/public/bot-ledger/trades?bot=all'))
    const dates = (await res.json()).items.map((i: { closed_date: string }) => i.closed_date)
    expect([...dates]).toEqual([...dates].sort().reverse())
  })

  it('filters to a single bot', async () => {
    const res = await tradesGET(req('/api/public/bot-ledger/trades?bot=flame'))
    const body = await res.json()
    expect(body.filter.bot).toBe('flame')
    expect(body.items.every((i: { bot: string }) => i.bot === 'flame')).toBe(true)
    expect(body.total).toBe(2)
  })

  it('labels each FLAME row by its actual structure', async () => {
    const res = await tradesGET(req('/api/public/bot-ledger/trades?bot=flame'))
    const body = await res.json()
    expect(body.items[0].setup).toBe('SPY 2DTE Put Credit Spread')
  })

  it('shares a snapshot_id with the summary endpoint', async () => {
    const s = await (await summaryGET(req('/api/public/bot-ledger/summary?period=30d'))).json()
    const t = await (await tradesGET(req('/api/public/bot-ledger/trades?bot=all'))).json()
    expect(t.snapshot_id).toBe(s.snapshot_id)
    expect(t.as_of).toBe(s.as_of)
  })

  it('rejects an unsupported bot filter and a bad limit', async () => {
    const badBot = await tradesGET(req('/api/public/bot-ledger/trades?bot=inferno'))
    expect(badBot.status).toBe(400)
    expect((await badBot.json()).error_code).toBe('INVALID_BOT_FILTER')

    for (const limit of ['0', '101', 'abc', '-5']) {
      const res = await tradesGET(req(`/api/public/bot-ledger/trades?limit=${limit}`))
      expect(res.status).toBe(400)
      expect((await res.json()).error_code).toBe('INVALID_LIMIT')
    }
  })

  it('409s a stale snapshot and hands back the current one', async () => {
    const res = await tradesGET(
      req('/api/public/bot-ledger/trades?snapshot_id=bl1_1000000200_deadbeef'),
    )
    expect(res.status).toBe(409)
    const body = await res.json()
    expect(body.error_code).toBe('SNAPSHOT_EXPIRED')
    expect(body.current_snapshot_id).toMatch(/^bl1_\d+_[0-9a-f]{8}$/)
    expect(res.headers.get('Cache-Control')).toBe('no-store')
  })

  it('400s a malformed snapshot id', async () => {
    const res = await tradesGET(req('/api/public/bot-ledger/trades?snapshot_id=nonsense'))
    expect(res.status).toBe(400)
    expect((await res.json()).error_code).toBe('INVALID_SNAPSHOT')
  })

  it('400s a forged cursor', async () => {
    const res = await tradesGET(req('/api/public/bot-ledger/trades?cursor=bm9wZQ.ZmFrZQ'))
    expect(res.status).toBe(400)
    expect((await res.json()).error_code).toBe('INVALID_CURSOR')
  })

  it('paginates with an opaque cursor that round-trips', async () => {
    const first = await (await tradesGET(req('/api/public/bot-ledger/trades?bot=all&limit=2'))).json()
    expect(first.items).toHaveLength(2)
    expect(first.next_cursor).toBeTruthy()
    expect(first.previous_cursor).toBeNull()

    const second = await (
      await tradesGET(
        req(
          `/api/public/bot-ledger/trades?bot=all&limit=2&cursor=${encodeURIComponent(first.next_cursor)}`,
        ),
      )
    ).json()
    expect(second.items).toHaveLength(2)
    expect(second.previous_cursor).toBeTruthy()
    // No overlap between pages.
    const firstIds = first.items.map((i: { public_id: string }) => i.public_id)
    const secondIds = second.items.map((i: { public_id: string }) => i.public_id)
    expect(firstIds.some((id: string) => secondIds.includes(id))).toBe(false)
  })

  it('never exposes a proprietary field', async () => {
    const res = await tradesGET(req('/api/public/bot-ledger/trades?bot=all'))
    const raw = JSON.stringify(await res.json())
    for (const forbidden of ['618', '613', '628', '633', 'pos-1', 'close_reason', 'account_type']) {
      expect(raw).not.toContain(forbidden)
    }
  })
})
