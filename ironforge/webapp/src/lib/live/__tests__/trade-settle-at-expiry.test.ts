import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getLiveTrade } from '../summary'

/**
 * Bug fix: the lifecycle line's "Target / Stop" and "Auto Close" nodes used
 * generic IC numbers for FLAME/SPARK, which are EBB settle-at-expiry bots —
 * PT off, stop not consulted, and the real close is 3:00 PM CT (not the
 * generic 2:45 PM EOD safety cutoff). See lib/db.ts isSettleAtExpiryBot.
 */

const CT_TODAY_STR = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })

let earlyClose = false
let positionRow: Record<string, unknown> = {}

vi.mock('@/lib/db', () => ({
  dbQuery: async (sql: string) => {
    if (sql.includes("status = 'open'") && sql.includes('position_id')) return [positionRow]
    if (sql.includes('_config')) return [{ stop_loss_pct: 200, profit_target_pct: 30 }]
    return []
  },
  botTable: (bot: string, suffix: string) => `${bot}_${suffix}`,
  sharedTable: (suffix: string) => suffix,
  num: (v: unknown) => (v == null || v === '' ? 0 : Number(v)),
  int: (v: unknown) => (v == null || v === '' ? 0 : parseInt(String(v), 10)),
  escapeSql: (v: string) => String(v).replace(/'/g, "''"),
  heartbeatName: (bot: string) => bot,
  dteMode: () => null,
  CT_TODAY: "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Chicago')::date",
  isSettleAtExpiryBot: (bot: string) => bot === 'flame' || bot === 'spark',
}))
vi.mock('@/lib/tradier', () => ({
  getProductionPauseState: async () => ({ paused: false }),
  getOwnerPauseState: async () => ({ ok: true, paused: new Set() }),
  getSandboxAccountBalances: async () => [],
  getFlameProductionBalance: async () => null,
  getQuoteDetail: async () => null,
  getIcMarkToMarket: async () => null,
  calculateIcUnrealizedPnl: () => null,
  isConfigured: () => false,
}))
vi.mock('@/lib/pt-tiers', () => ({
  isMarketOpen: () => true,
  DEFAULT_EOD_CUTOFF_MIN: 14 * 60 + 45,
  formatCTClock: () => '',
  getCurrentPTTier: () => ({ pct: 0.3 }),
  isSparkStrategyBot: (bot: string) => bot === 'spark',
}))
vi.mock('@/lib/market-calendar', () => ({
  isEarlyClose: () => earlyClose,
}))
vi.mock('../state', () => ({
  deriveCustomerState: () => null,
  getMarketSession: () => null,
}))
vi.mock('../riskProtection', () => ({ countProtectiveSkipDays: async () => 0 }))
vi.mock('../activityFeed', () => ({ buildActivityFeed: () => null }))
vi.mock('../winLossStreak', () => ({ RECENT_TRADES_LIMIT: 10, buildStreakSummary: () => null }))
vi.mock('../viewer', () => ({
  resolveAccountMode: () => 'sandbox',
  scopeFilter: () => '',
  LIVE_BOT_LABEL: {},
  paperDisclosure: () => null,
}))
vi.mock('../swing', () => ({
  deriveSwingMeta: () => ({ heldOvernight: false, dayNumber: 1 }),
}))
vi.mock('@/lib/spark-sizing', () => ({
  sparkRegimeBpCap: () => 0,
  isSparkV2SizingBot: () => false,
}))
vi.mock('../backtestAnchor', () => ({
  BACKTEST_ANCHORS: { spark: null, flame: null },
  compareToBacktestAnchor: () => null,
}))

/** The CT wall-clock the returned UTC instant actually represents. */
function ctClock(iso: string | null): string | null {
  if (!iso) return null
  return new Date(iso).toLocaleTimeString('en-US', {
    hour: 'numeric', minute: '2-digit', timeZone: 'America/Chicago',
  })
}

beforeEach(() => {
  earlyClose = false
  positionRow = {
    position_id: 'p1',
    ticker: 'SPY',
    expiration: CT_TODAY_STR,
    put_short_strike: 500,
    put_long_strike: 495,
    call_short_strike: 0,
    call_long_strike: 0,
    contracts: 2,
    total_credit: 1.5,
    spread_width: 5,
    open_time: new Date().toISOString(),
    gex_regime: null,
    collateral_required: 700,
  }
})

describe('getLiveTrade — settle-at-expiry bots (FLAME/SPARK)', () => {
  it('never reports a target or stop dollar figure for FLAME', async () => {
    const trade = await getLiveTrade('flame' as never, null, true)
    expect(trade.positions?.[0]?.target_dollars).toBeNull()
    expect(trade.positions?.[0]?.stop_dollars).toBeNull()
  })

  it('never reports a target or stop dollar figure for SPARK', async () => {
    const trade = await getLiveTrade('spark' as never, null, true)
    expect(trade.positions?.[0]?.target_dollars).toBeNull()
    expect(trade.positions?.[0]?.stop_dollars).toBeNull()
  })

  it('reports the real 3:00 PM CT close, not the generic 2:45 PM EOD cutoff', async () => {
    const trade = await getLiveTrade('flame' as never, null, true)
    expect(ctClock(trade.positions![0].auto_close_at)).toBe('3:00 PM')
  })

  it('reports noon CT on an early-close half-day', async () => {
    earlyClose = true
    const trade = await getLiveTrade('spark' as never, null, true)
    expect(ctClock(trade.positions![0].auto_close_at)).toBe('12:00 PM')
  })
})

// LiveBot is currently only 'spark' | 'flame' (both settle-at-expiry), so no real
// caller reaches this branch today — isSettleAtExpiryBot() is generic over any bot
// name, and this exercises that the OLD generic-IC behavior still holds for a
// hypothetical non-settle-at-expiry bot (the `as never` cast only bypasses the
// current LiveBot union, not the runtime logic under test).
describe('getLiveTrade — ordinary (non-settle-at-expiry) bots are unchanged', () => {
  it('still computes a real target/stop dollar figure', async () => {
    const trade = await getLiveTrade('inferno' as never, null, true)
    expect(trade.positions?.[0]?.target_dollars).not.toBeNull()
    expect(trade.positions?.[0]?.stop_dollars).not.toBeNull()
  })

  it('still uses the generic 2:45 PM EOD cutoff, unaffected by the early-close flag', async () => {
    earlyClose = true
    const trade = await getLiveTrade('inferno' as never, null, true)
    expect(ctClock(trade.positions![0].auto_close_at)).toBe('2:45 PM')
  })
})
