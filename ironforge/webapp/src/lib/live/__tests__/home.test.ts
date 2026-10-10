import { describe, it, expect, vi, beforeEach } from 'vitest'

/**
 * Contract check for the mobile bug this fix closes: mobile/src/api/types.ts
 * declares HomeData by hand (no shared package between the two apps), and it
 * previously drifted from this exact shape — mobile expected flat
 * `week_income` while the route returns nested `wealth.weekly_income`, so
 * three of the four stats-card numbers rendered "—" forever. Keep this
 * literal key list and mobile/src/live/period-stats.test.ts's `satisfies`
 * fixture in sync by hand; either one failing means the other needs updating.
 */
const HOME_DATA_TOP_KEYS = ['wealth', 'recent_trades', 'yesterday_trades', 'as_of']
const HOME_DATA_WEALTH_KEYS = ['weekly_income', 'monthly_income', 'lifetime_income', 'lifetime_return_pct']

let weeklyRow = { weekly: 36, monthly: 210 }
let lifetimeRow = { total: 512.5 }
const calls: string[] = []

vi.mock('@/lib/db', () => ({
  dbQuery: async (sql: string) => {
    calls.push(sql)
    if (sql.includes('AS weekly')) return [weeklyRow]
    if (sql.includes('starting_capital')) return [{ starting_capital: 10000 }]
    if (sql.includes('AS total')) return [lifetimeRow]
    if (sql.includes('close_time, ticker')) return []
    if (sql.includes('AS cnt')) return [{ cnt: 2 }]
    return []
  },
  botTable: (bot: string, suffix: string) => `${bot}_${suffix}`,
  num: (v: unknown) => (v == null || v === '' ? 0 : Number(v)),
  int: (v: unknown) => (v == null || v === '' ? 0 : parseInt(String(v), 10)),
  escapeSql: (v: string) => String(v).replace(/'/g, "''"),
  dteMode: () => '1dte',
  CT_TODAY: "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Chicago')::date",
}))
vi.mock('@/lib/tradier', () => ({
  canReadProductionBalance: () => false,
  isFlameLiveArmed: () => false,
}))

const { getHomeData } = await import('../home')

beforeEach(() => {
  calls.length = 0
  weeklyRow = { weekly: 36, monthly: 210 }
  lifetimeRow = { total: 512.5 }
})

describe('getHomeData', () => {
  it('returns the exact wire shape mobile depends on (additive-only — never rename/un-nest)', async () => {
    const data = await getHomeData('spark', null, true)
    expect(Object.keys(data).sort()).toEqual(HOME_DATA_TOP_KEYS.sort())
    expect(Object.keys(data.wealth).sort()).toEqual(HOME_DATA_WEALTH_KEYS.sort())
  })

  it('computes lifetime_income from the same lifetime query that feeds lifetime_return_pct', async () => {
    const data = await getHomeData('spark', null, true)
    expect(data.wealth.lifetime_income).toBe(512.5)
    // 512.50 / 10,000 starting capital = 5.13% (rounded to 2dp).
    expect(data.wealth.lifetime_return_pct).toBe(5.13)
  })

  it('returns 0, not null, for weekly/monthly/lifetime when nothing has closed', async () => {
    weeklyRow = { weekly: 0, monthly: 0 }
    lifetimeRow = { total: 0 }
    const data = await getHomeData('spark', null, true)
    expect(data.wealth.weekly_income).toBe(0)
    expect(data.wealth.monthly_income).toBe(0)
    expect(data.wealth.lifetime_income).toBe(0)
    expect(data.wealth.weekly_income).not.toBeNull()
    expect(data.wealth.monthly_income).not.toBeNull()
  })

  it('uses a calendar boundary, not a rolling 7/30-day window', async () => {
    await getHomeData('spark', null, true)
    const incomeSql = calls.find((c) => c.includes('AS weekly'))!
    expect(incomeSql).not.toContain("interval '7 days'")
    expect(incomeSql).not.toContain("interval '30 days'")
    // Bound to a literal ISO timestamp computed by period-windows.ts.
    expect(incomeSql).toMatch(/close_time >= '\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z'/)
  })

  it('the lifetime query carries no time filter at all — lifetime never resets', async () => {
    await getHomeData('spark', null, true)
    const lifetimeSql = calls.find((c) => c.includes('AS total'))!
    expect(lifetimeSql).not.toContain('close_time >=')
    expect(lifetimeSql).not.toContain('interval')
  })

  it('scopes weekly/monthly with the same filter summary.ts uses for Today', async () => {
    // scopeFilter('spark', null, true) is the unscoped operator fleet view —
    // the same call summary.ts makes for todayRealizedRows. No account_type
    // divergence between "Today" and the three longer windows.
    await getHomeData('spark', null, true)
    const incomeSql = calls.find((c) => c.includes('AS weekly'))!
    expect(incomeSql).toContain("COALESCE(account_type, 'sandbox') = 'production'")
  })
})
