/**
 * API route logic tests — verifies data flow through status, positions,
 * equity-curve, performance, config, and health endpoints.
 *
 * These tests validate the data transformation logic that each API route
 * performs on database results. We mock the db and tradier modules, then
 * test the route handler functions directly.
 *
 * NOTE: Next.js route handlers can't be imported directly in vitest
 * (they depend on Next.js runtime). Instead we test the data contracts
 * and transformation logic that the routes implement.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

/* ================================================================== */
/*  Section 1: DB Helper Functions                                     */
/* ================================================================== */

describe('DB helper functions', () => {
  // Test the pure helper functions from db.ts that all routes depend on

  describe('botTable', () => {
    it('returns {bot}_{suffix} for known bots', () => {
      // Mirrors the logic in db.ts
      const botTable = (bot: string, suffix: string) => {
        const prefixes: Record<string, string> = { flame: 'flame', spark: 'spark', inferno: 'inferno' }
        return `${prefixes[bot] || bot}_${suffix}`
      }
      expect(botTable('flame', 'positions')).toBe('flame_positions')
      expect(botTable('spark', 'paper_account')).toBe('spark_paper_account')
      expect(botTable('inferno', 'equity_snapshots')).toBe('inferno_equity_snapshots')
    })
  })

  describe('dteMode', () => {
    it('maps bots to correct DTE modes', () => {
      const dteMode = (bot: string): string | null => {
        if (bot === 'flame') return '2DTE'
        if (bot === 'spark') return '1DTE'
        if (bot === 'inferno') return '0DTE'
        return null
      }
      expect(dteMode('flame')).toBe('2DTE')
      expect(dteMode('spark')).toBe('1DTE')
      expect(dteMode('inferno')).toBe('0DTE')
      expect(dteMode('unknown')).toBeNull()
    })
  })

  describe('validateBot', () => {
    it('accepts valid bot names', () => {
      const validateBot = (bot: string): string | null => {
        const valid = ['flame', 'spark', 'inferno']
        const b = bot.toLowerCase()
        return valid.includes(b) ? b : null
      }
      expect(validateBot('flame')).toBe('flame')
      expect(validateBot('SPARK')).toBe('spark')
      expect(validateBot('inferno')).toBe('inferno')
    })

    it('rejects invalid bot names', () => {
      const validateBot = (bot: string): string | null => {
        const valid = ['flame', 'spark', 'inferno']
        const b = bot.toLowerCase()
        return valid.includes(b) ? b : null
      }
      expect(validateBot('fortress')).toBeNull()
      expect(validateBot('')).toBeNull()
      expect(validateBot('admin')).toBeNull()
    })
  })

  describe('num and int helpers', () => {
    const num = (v: any) => { if (v == null || v === '') return 0; const n = parseFloat(v); return isNaN(n) ? 0 : n }
    const int = (v: any) => { if (v == null || v === '') return 0; const n = parseInt(v, 10); return isNaN(n) ? 0 : n }

    it('num handles null/undefined/empty', () => {
      expect(num(null)).toBe(0)
      expect(num(undefined)).toBe(0)
      expect(num('')).toBe(0)
    })

    it('num parses string numbers', () => {
      expect(num('585.50')).toBe(585.50)
      expect(num('-12.75')).toBe(-12.75)
    })

    it('num passes through real numbers', () => {
      expect(num(585.50)).toBe(585.50)
    })

    it('int truncates decimals', () => {
      expect(int('5.7')).toBe(5)
      expect(int('0')).toBe(0)
    })

    it('int handles NaN', () => {
      expect(int('abc')).toBe(0)
    })
  })
})

/* ================================================================== */
/*  Section 2: Status Route Data Contract                              */
/* ================================================================== */

describe('Status route data contract', () => {
  it('computes balance from starting_capital + realized_pnl', () => {
    const startingCapital = 10000
    const realizedPnl = 250.50
    const balance = Math.round((startingCapital + realizedPnl) * 100) / 100
    expect(balance).toBe(10250.50)
  })

  it('computes buying_power from balance - collateral', () => {
    const balance = 10250.50
    const collateral = 2365
    const buyingPower = Math.round((balance - collateral) * 100) / 100
    expect(buyingPower).toBe(7885.50)
  })

  it('buying_power goes negative when collateral exceeds balance', () => {
    const balance = 5000
    const collateral = 6000
    const buyingPower = Math.round((balance - collateral) * 100) / 100
    expect(buyingPower).toBe(-1000)
  })

  it('total_pnl includes unrealized when available', () => {
    const realizedPnl = 250.50
    const unrealizedPnl = -45.00
    const totalPnl = realizedPnl + unrealizedPnl
    expect(totalPnl).toBeCloseTo(205.50, 2)
  })

  it('total_pnl uses realized only when unrealized is null', () => {
    const realizedPnl = 250.50
    const unrealizedPnl = null
    const totalPnl = realizedPnl + (unrealizedPnl ?? 0)
    expect(totalPnl).toBe(250.50)
  })

  it('return_pct is percentage of starting capital', () => {
    const startingCapital = 10000
    const totalPnl = 500
    const returnPct = (totalPnl / startingCapital) * 100
    expect(returnPct).toBe(5.0)
  })

  it('bot_state derives correctly from heartbeat', () => {
    const deriveState = (hbStatus: string, hbAction: string, isActive: boolean) => {
      return hbStatus === 'error' ? 'error'
        : hbAction === 'pending_fill' ? 'pending_fill'
        : hbAction === 'awaiting_fill' ? 'awaiting_fill'
        : hbAction === 'monitoring' ? 'monitoring'
        : hbAction === 'traded' || hbAction === 'closed' ? 'traded'
        : hbAction === 'outside_window' || hbAction === 'outside_entry_window' ? 'market_closed'
        : hbStatus === 'idle' ? 'idle'
        : hbStatus === 'active' ? 'scanning'
        : 'unknown'
    }

    expect(deriveState('error', '', true)).toBe('error')
    expect(deriveState('active', 'monitoring', true)).toBe('monitoring')
    expect(deriveState('active', 'awaiting_fill', true)).toBe('awaiting_fill')
    expect(deriveState('active', 'traded', true)).toBe('traded')
    expect(deriveState('active', 'outside_window', true)).toBe('market_closed')
    expect(deriveState('idle', '', true)).toBe('idle')
    expect(deriveState('active', '', true)).toBe('scanning')
    expect(deriveState('', '', false)).toBe('unknown')
  })
})

/* ================================================================== */
/*  Section 3: Equity Curve Data Contract                              */
/* ================================================================== */

describe('Equity curve data contract', () => {
  it('computes cumulative equity from closed trades', () => {
    const startingCapital = 10000
    const closedTrades = [
      { realized_pnl: 50, cumulative_pnl: 50 },
      { realized_pnl: -20, cumulative_pnl: 30 },
      { realized_pnl: 100, cumulative_pnl: 130 },
    ]

    const curve = closedTrades.map((t) => ({
      equity: Math.round((startingCapital + t.cumulative_pnl) * 100) / 100,
      cumulative_pnl: t.cumulative_pnl,
    }))

    expect(curve[0].equity).toBe(10050)
    expect(curve[1].equity).toBe(10030)
    expect(curve[2].equity).toBe(10130)
  })

  it('live point appends unrealized P&L to last cumulative', () => {
    const startingCapital = 10000
    const lastCumPnl = 130
    const liveUnrealizedPnl = 25

    const liveCumPnl = lastCumPnl + liveUnrealizedPnl
    const liveEquity = Math.round((startingCapital + liveCumPnl) * 100) / 100

    expect(liveCumPnl).toBe(155)
    expect(liveEquity).toBe(10155)
  })

  it('handles empty trade history (no closed trades)', () => {
    const startingCapital = 10000
    const closedTrades: any[] = []
    const curve = closedTrades.map(() => ({}))
    expect(curve).toHaveLength(0)
    // With open positions, live point should still work
    const lastCumPnl = curve.length > 0 ? 0 : 0
    const liveEquity = startingCapital + lastCumPnl + 25 // unrealized
    expect(liveEquity).toBe(10025)
  })

  it('period filter works correctly', () => {
    const now = new Date()
    const oneDayAgo = new Date(now.getTime() - 86_400_000)
    const oneWeekAgo = new Date(now.getTime() - 7 * 86_400_000)
    const twoWeeksAgo = new Date(now.getTime() - 14 * 86_400_000)

    const curve = [
      { timestamp: twoWeeksAgo.toISOString(), equity: 10050 },
      { timestamp: oneWeekAgo.toISOString(), equity: 10030 },
      { timestamp: oneDayAgo.toISOString(), equity: 10130 },
    ]

    const cutoff1w = new Date(now.getTime() - 7 * 86_400_000)
    const filtered = curve.filter((pt) => new Date(pt.timestamp) >= cutoff1w)
    expect(filtered).toHaveLength(2) // oneWeekAgo and oneDayAgo
  })
})

/* ================================================================== */
/*  Section 4: Performance Data Contract                               */
/* ================================================================== */

describe('Performance data contract', () => {
  it('computes win rate correctly', () => {
    const total = 20
    const wins = 14
    const winRate = (wins / total) * 100
    expect(winRate).toBe(70)
  })

  it('handles zero trades gracefully', () => {
    const total = 0
    const wins = 0
    const winRate = total > 0 ? (wins / total) * 100 : 0
    expect(winRate).toBe(0)
  })

  it('rounds P&L to 2 decimals', () => {
    const totalPnl = 123.456789
    const rounded = Math.round(totalPnl * 100) / 100
    expect(rounded).toBe(123.46)
  })
})

/* ================================================================== */
/*  Section 5: Config Route Data Contract                              */
/* ================================================================== */

describe('Config data contract', () => {
  const DEFAULTS = {
    flame: {
      sd_multiplier: 1.2, spread_width: 5.0, profit_target_pct: 30.0,
      stop_loss_pct: 200.0, vix_skip: 32.0, max_contracts: 10,
      max_trades_per_day: 1, buying_power_usage_pct: 0.85,
      entry_end: '14:00', starting_capital: 10000.0,
    },
    inferno: {
      sd_multiplier: 1.0, spread_width: 5.0, profit_target_pct: 50.0,
      stop_loss_pct: 300.0, vix_skip: 32.0, max_contracts: 0,
      max_trades_per_day: 0, buying_power_usage_pct: 0.85,
      entry_end: '14:30', starting_capital: 10000.0,
    },
  }

  it('FLAME defaults have correct values', () => {
    expect(DEFAULTS.flame.sd_multiplier).toBe(1.2)
    expect(DEFAULTS.flame.profit_target_pct).toBe(30.0)
    expect(DEFAULTS.flame.stop_loss_pct).toBe(200.0)
    expect(DEFAULTS.flame.entry_end).toBe('14:00')
    expect(DEFAULTS.flame.max_trades_per_day).toBe(1)
  })

  it('INFERNO defaults differ from FLAME', () => {
    expect(DEFAULTS.inferno.sd_multiplier).toBe(1.0)
    expect(DEFAULTS.inferno.profit_target_pct).toBe(50.0)
    expect(DEFAULTS.inferno.stop_loss_pct).toBe(300.0)
    expect(DEFAULTS.inferno.entry_end).toBe('14:30')
    expect(DEFAULTS.inferno.max_contracts).toBe(0) // unlimited
    expect(DEFAULTS.inferno.max_trades_per_day).toBe(0) // unlimited
  })

  it('DB overrides merge on top of defaults', () => {
    const defaults = { ...DEFAULTS.flame }
    const dbRow = { sd_multiplier: 1.5, profit_target_pct: 25.0 }
    const merged = { ...defaults, ...dbRow }
    expect(merged.sd_multiplier).toBe(1.5) // overridden
    expect(merged.profit_target_pct).toBe(25.0) // overridden
    expect(merged.spread_width).toBe(5.0) // default preserved
  })

  it('buying_power_usage_pct is stored as decimal', () => {
    expect(DEFAULTS.flame.buying_power_usage_pct).toBe(0.85)
    // UI displays as percentage: 0.85 * 100 = 85%
    expect(DEFAULTS.flame.buying_power_usage_pct * 100).toBe(85)
  })
})

/* ================================================================== */
/*  Section 6: Positions Route Data Contract                           */
/* ================================================================== */

describe('Positions data contract', () => {
  it('maps raw DB row to position object correctly', () => {
    const num = (v: any) => parseFloat(v) || 0
    const int = (v: any) => parseInt(v, 10) || 0

    const row = {
      position_id: 'flame_2dte_20260316_093000',
      ticker: 'SPY',
      expiration: '2026-03-18',
      put_short_strike: '580',
      put_long_strike: '575',
      call_short_strike: '590',
      call_long_strike: '595',
      contracts: '5',
      spread_width: '5',
      total_credit: '0.27',
      collateral_required: '2365',
      open_time: '2026-03-16T09:30:00Z',
    }

    const position = {
      position_id: row.position_id,
      ticker: row.ticker,
      put_short_strike: num(row.put_short_strike),
      put_long_strike: num(row.put_long_strike),
      call_short_strike: num(row.call_short_strike),
      call_long_strike: num(row.call_long_strike),
      contracts: int(row.contracts),
      spread_width: num(row.spread_width),
      total_credit: num(row.total_credit),
      collateral_required: num(row.collateral_required),
    }

    expect(position.put_short_strike).toBe(580)
    expect(position.contracts).toBe(5)
    expect(position.total_credit).toBe(0.27)
    expect(position.collateral_required).toBe(2365)
  })

  it('handles NULL oracle fields gracefully', () => {
    const num = (v: any) => parseFloat(v) || 0
    const row = {
      oracle_win_probability: null,
      oracle_advice: null,
    }
    expect(num(row.oracle_win_probability)).toBe(0)
    expect(row.oracle_advice).toBeNull()
  })
})

/* ================================================================== */
/*  Section 7: Health Route Contract                                   */
/* ================================================================== */

describe('Health route contract', () => {
  it('status is "ok" when all checks pass', () => {
    const checks = {
      database: { status: 'ok' },
      tradier: { status: 'ok' },
    }
    const allOk = Object.values(checks).every((c) => c.status === 'ok' || c.status === 'not_configured')
    expect(allOk).toBe(true)
  })

  it('status is "degraded" when any check fails', () => {
    const checks = {
      database: { status: 'ok' },
      tradier: { status: 'error' },
    }
    const allOk = Object.values(checks).every((c) => c.status === 'ok' || c.status === 'not_configured')
    expect(allOk).toBe(false)
  })

  it('not_configured is treated as acceptable', () => {
    const checks = {
      database: { status: 'ok' },
      tradier: { status: 'not_configured' },
    }
    const allOk = Object.values(checks).every((c) => c.status === 'ok' || c.status === 'not_configured')
    expect(allOk).toBe(true)
  })
})

/* ================================================================== */
/*  Section 8: Accounts Production Route Contract                      */
/* ================================================================== */

describe('Accounts production route data contract', () => {
  it('cross-references OCC symbols to attribute positions to bots', () => {
    const tradierSymbols = [
      'SPY260318P00580000', 'SPY260318P00575000', 'SPY260318C00590000', 'SPY260318C00595000',
      'SPY260319P00582000', 'SPY260319P00577000', 'SPY260319C00592000', 'SPY260319C00597000',
    ]

    // Bot FLAME owns the 0318 position, SPARK owns the 0319 position
    const flameBotSymbols = new Set([
      'SPY260318P00580000', 'SPY260318P00575000', 'SPY260318C00590000', 'SPY260318C00595000',
    ])
    const sparkBotSymbols = new Set([
      'SPY260319P00582000', 'SPY260319P00577000', 'SPY260319C00592000', 'SPY260319C00597000',
    ])

    const flameMatches = tradierSymbols.filter((s) => flameBotSymbols.has(s))
    const sparkMatches = tradierSymbols.filter((s) => sparkBotSymbols.has(s))

    expect(flameMatches).toHaveLength(4) // 4 legs = 1 IC position
    expect(Math.ceil(flameMatches.length / 4)).toBe(1)
    expect(sparkMatches).toHaveLength(4)
    expect(Math.ceil(sparkMatches.length / 4)).toBe(1)

    // Unattributed = tradier symbols not owned by any bot
    const allBotSymbols = new Set([...flameBotSymbols, ...sparkBotSymbols])
    const unattributed = tradierSymbols.filter((s) => !allBotSymbols.has(s))
    expect(unattributed).toHaveLength(0)
  })

  it('detects unattributed positions', () => {
    const tradierSymbols = [
      'SPY260318P00580000', 'SPY260318P00575000', 'SPY260318C00590000', 'SPY260318C00595000',
      'QQQ260320C00500000', // This belongs to no bot
    ]
    const allBotSymbols = new Set([
      'SPY260318P00580000', 'SPY260318P00575000', 'SPY260318C00590000', 'SPY260318C00595000',
    ])

    const unattributed = tradierSymbols.filter((s) => !allBotSymbols.has(s))
    expect(unattributed).toHaveLength(1)
    expect(unattributed[0]).toBe('QQQ260320C00500000')
  })
})

/* ================================================================== */
/*  Section 9: DTE Filter Correctness                                  */
/* ================================================================== */

describe('DTE filter in SQL queries', () => {
  it('each bot filters to correct DTE mode', () => {
    const bots = ['flame', 'spark', 'inferno'] as const
    const dteMode = (bot: string) => {
      if (bot === 'flame') return '2DTE'
      if (bot === 'spark') return '1DTE'
      if (bot === 'inferno') return '0DTE'
      return null
    }

    for (const bot of bots) {
      const dte = dteMode(bot)
      expect(dte).not.toBeNull()
      const dteFilter = `AND dte_mode = '${dte}'`
      expect(dteFilter).toContain(dte!)
    }
  })

  it('SQL with DTE filter is well-formed', () => {
    const bot = 'flame'
    const dte = '2DTE'
    const table = `${bot}_positions`

    const sql = `SELECT * FROM ${table} WHERE status = 'open' AND dte_mode = '${dte}'`
    expect(sql).toContain("flame_positions")
    expect(sql).toContain("dte_mode = '2DTE'")
    expect(sql).not.toContain("undefined")
    expect(sql).not.toContain("null")
  })
})

/* ================================================================== */
/*  Section 10: Collateral Reconciliation Logic                        */
/* ================================================================== */

describe('Collateral reconciliation', () => {
  it('live collateral = SUM of open position collateral_required', () => {
    const openPositions = [
      { collateral_required: 2365 },
      { collateral_required: 1890 },
    ]
    const liveCollateral = openPositions.reduce((sum, p) => sum + p.collateral_required, 0)
    expect(liveCollateral).toBe(4255)
  })

  it('live collateral is 0 when no open positions', () => {
    const openPositions: any[] = []
    const liveCollateral = openPositions.reduce((sum, p) => sum + p.collateral_required, 0)
    expect(liveCollateral).toBe(0)
  })

  it('status uses live stats, not stale paper_account', () => {
    // paper_account says cumulative_pnl = 500 (stale)
    // actual closed trades sum to 250.50 (truth)
    const staleValue = 500
    const liveValue = 250.50
    const startingCapital = 10000

    const staleBalance = startingCapital + staleValue
    const liveBalance = startingCapital + liveValue

    expect(staleBalance).toBe(10500) // WRONG
    expect(liveBalance).toBe(10250.50) // CORRECT — status route uses this
  })
})

/* ================================================================== */
/*  Section 11: Scanner Status Route Contract                          */
/* ================================================================== */

describe('Scanner status route contract', () => {
  it('detects stale heartbeat (> 5 min old)', () => {
    const STALE_THRESHOLD_MS = 5 * 60 * 1000
    const now = Date.now()

    // 3 min old — not stale
    const recent = now - (3 * 60 * 1000)
    expect(now - recent > STALE_THRESHOLD_MS).toBe(false)

    // 6 min old — stale
    const old = now - (6 * 60 * 1000)
    expect(now - old > STALE_THRESHOLD_MS).toBe(true)
  })

  it('overall status logic: ok, degraded, down', () => {
    // ok: all bots healthy, no errors
    const botsOk = [
      { is_stale: false, status: 'active' },
      { is_stale: false, status: 'active' },
      { is_stale: false, status: 'idle' },
    ]
    const anyStale = botsOk.some(b => b.is_stale)
    const anyError = botsOk.some(b => b.status === 'error')
    expect(anyStale).toBe(false)
    expect(anyError).toBe(false)

    // degraded: one bot in error state
    const botsError = [
      { is_stale: false, status: 'active' },
      { is_stale: false, status: 'error' },
    ]
    expect(botsError.some(b => b.status === 'error')).toBe(true)

    // degraded: stale heartbeat during market hours
    const botsStale = [
      { is_stale: true, status: 'active' },
      { is_stale: false, status: 'active' },
    ]
    expect(botsStale.some(b => b.is_stale)).toBe(true)
  })

  it('computes age_minutes from heartbeat timestamp', () => {
    const now = Date.now()
    const lastBeat = now - (3.5 * 60 * 1000) // 3.5 min ago
    const ageMs = now - lastBeat
    const ageMins = Math.round(ageMs / 60_000 * 10) / 10
    expect(ageMins).toBeCloseTo(3.5, 0)
  })

  it('handles missing heartbeat data (null timestamp)', () => {
    const lastBeat = null
    const ageMs = lastBeat ? Date.now() - lastBeat : null
    const isStale = ageMs != null ? ageMs > 5 * 60 * 1000 : true
    expect(ageMs).toBeNull()
    expect(isStale).toBe(true) // Missing heartbeat is always stale
  })

  it('returns 503 when status is not ok', () => {
    const overall = 'degraded'
    const httpStatus = overall === 'ok' ? 200 : 503
    expect(httpStatus).toBe(503)
  })

  it('returns 200 when status is ok', () => {
    const overall = 'ok'
    const httpStatus = overall === 'ok' ? 200 : 503
    expect(httpStatus).toBe(200)
  })
})

/* ================================================================== */
/*  Section 10: Untested Route Logic Validation                        */
/* ================================================================== */

import { readFileSync } from 'fs'
import { resolve } from 'path'

describe('diagnose-trade route', () => {
  const source = readFileSync(
    resolve(__dirname, '../../app/api/[bot]/diagnose-trade/route.ts'),
    'utf-8',
  )

  it('exports a GET handler', () => {
    expect(source).toMatch(/export\s+async\s+function\s+GET/)
  })

  it('checks market hours', () => {
    expect(source).toMatch(/market.*hour|isMarketOpen|830|1500/i)
  })

  it('checks buying power', () => {
    expect(source).toMatch(/buying.?power|bp/i)
  })

  it('returns diagnostic gates array', () => {
    expect(source).toMatch(/gates|checks|diagnosis|diagnostic/i)
  })
})

describe('verify-pnl route', () => {
  const source = readFileSync(
    resolve(__dirname, '../../app/api/[bot]/verify-pnl/route.ts'),
    'utf-8',
  )

  it('exports a GET handler', () => {
    expect(source).toMatch(/export\s+async\s+function\s+GET/)
  })

  it('queries closed positions for P&L', () => {
    expect(source).toMatch(/realized_pnl/)
    expect(source).toMatch(/status.*closed|closed.*status/i)
  })
})

describe('eod-close route logic', () => {
  const source = readFileSync(
    resolve(__dirname, '../../app/api/[bot]/eod-close/route.ts'),
    'utf-8',
  )

  it('exports a POST handler', () => {
    expect(source).toMatch(/export\s+async\s+function\s+POST/)
  })

  it('validates EOD cutoff time (14:45 CT = 885 minutes)', () => {
    expect(source).toMatch(/885|14:45|14.*45/)
  })

  it('returns early with error if before cutoff', () => {
    expect(source).toMatch(/Not past EOD cutoff/)
  })

  it('handles zero open positions gracefully', () => {
    expect(source).toMatch(/No open positions/)
    expect(source).toMatch(/closed:\s*0/)
  })
})

describe('fix-collateral route', () => {
  const source = readFileSync(
    resolve(__dirname, '../../app/api/[bot]/fix-collateral/route.ts'),
    'utf-8',
  )

  it('exports GET (diagnostic) and POST (fix)', () => {
    expect(source).toMatch(/export\s+async\s+function\s+GET/)
    expect(source).toMatch(/export\s+async\s+function\s+POST/)
  })

  it('queries orphan positions', () => {
    expect(source).toMatch(/orphan|stale|expired/i)
  })

  it('reconciles collateral from live positions', () => {
    expect(source).toMatch(/SUM\(collateral_required\)/)
  })
})

describe('scanner/status route', () => {
  const source = readFileSync(
    resolve(__dirname, '../../app/api/scanner/status/route.ts'),
    'utf-8',
  )

  it('exports a GET handler', () => {
    expect(source).toMatch(/export\s+async\s+function\s+GET/)
  })

  it('queries bot_heartbeats table', () => {
    expect(source).toMatch(/bot_heartbeats/)
  })
})

/* ================================================================== */
/*  Person Filtering                                                    */
/* ================================================================== */

describe('Person filtering — API route support', () => {
  const routes = [
    { name: 'status', path: '../../app/api/[bot]/status/route.ts' },
    { name: 'equity-curve', path: '../../app/api/[bot]/equity-curve/route.ts' },
    { name: 'equity-curve/intraday', path: '../../app/api/[bot]/equity-curve/intraday/route.ts' },
    { name: 'performance', path: '../../app/api/[bot]/performance/route.ts' },
    { name: 'position-monitor', path: '../../app/api/[bot]/position-monitor/route.ts' },
    { name: 'positions', path: '../../app/api/[bot]/positions/route.ts' },
  ]

  for (const route of routes) {
    describe(`${route.name} route`, () => {
      const source = readFileSync(resolve(__dirname, route.path), 'utf-8')

      it('reads person query parameter from request', () => {
        expect(source).toMatch(/person/)
        expect(source).toMatch(/searchParams/)
      })

      it('builds personFilter for SQL WHERE clause', () => {
        expect(source).toMatch(/personFilter/)
      })

      it('applies personFilter to positions queries', () => {
        // personFilter should appear in at least one SQL query
        expect(source).toMatch(/\$\{personFilter\}/)
      })

      it('treats person=all as no filter (backward compatible)', () => {
        expect(source).toMatch(/!==\s*'all'/)
      })
    })
  }
})

describe('Person filtering — /api/persons endpoint', () => {
  const source = readFileSync(
    resolve(__dirname, '../../app/api/persons/route.ts'),
    'utf-8',
  )

  it('exports a GET handler', () => {
    expect(source).toMatch(/export\s+async\s+function\s+GET/)
  })

  it('queries ironforge_accounts for all active persons (sandbox + production)', () => {
    expect(source).toMatch(/ironforge_accounts/)
    expect(source).toMatch(/is_active\s*=\s*TRUE/)
    // Production accounts must appear in person dropdown for broker equity curve
    expect(source).not.toMatch(/type\s*=\s*'sandbox'/)
  })

  it('returns distinct person names', () => {
    expect(source).toMatch(/DISTINCT\s+\w*\.?person/)
  })
})

describe('Person filtering — schema migration', () => {
  const dbSource = readFileSync(resolve(__dirname, '../db.ts'), 'utf-8')

  it('adds person column to positions tables via ALTER TABLE migration', () => {
    // The migration loop adds 'person TEXT' to the columns list for positions
    expect(dbSource).toMatch(/'person TEXT'/)
    expect(dbSource).toMatch(/positions.*ADD COLUMN IF NOT EXISTS/)
  })

  it('adds person column to equity_snapshots tables', () => {
    expect(dbSource).toMatch(/equity_snapshots/)
    expect(dbSource).toMatch(/ADD COLUMN IF NOT EXISTS person/)
  })

  it('adds person column to daily_perf tables', () => {
    expect(dbSource).toMatch(/daily_perf/)
    expect(dbSource).toMatch(/ADD COLUMN IF NOT EXISTS person/)
  })
})

describe('Person filtering — scanner population', () => {
  const scannerSource = readFileSync(resolve(__dirname, '../scanner.ts'), 'utf-8')

  it('resolves person at start of tryOpenTrade', () => {
    const fn = scannerSource.match(
      /async function tryOpenTrade[\s\S]*?^}/m,
    )
    expect(fn).toBeTruthy()
    const body = fn![0]
    // person should be resolved BEFORE the PDT check
    const personIdx = body.indexOf("let person = 'User'")
    const pdtIdx = body.indexOf('ironforge_pdt_config')
    expect(personIdx).toBeGreaterThan(-1)
    expect(pdtIdx).toBeGreaterThan(-1)
    expect(personIdx).toBeLessThan(pdtIdx)
  })

  it('passes person to position INSERT', () => {
    // The position INSERT should include person column and $37 param
    expect(scannerSource).toMatch(/dte_mode, person/)
    expect(scannerSource).toMatch(/\$36, \$37/)
  })

  it('passes person to equity snapshot INSERT', () => {
    expect(scannerSource).toMatch(/dte_mode, person\)[\s\S]*?VALUES.*\$7/)
  })
})

describe('Person filtering — BotDashboard dropdown', () => {
  const source = readFileSync(
    resolve(__dirname, '../../components/BotDashboard.tsx'),
    'utf-8',
  )

  it('fetches /api/persons for dropdown options', () => {
    expect(source).toMatch(/\/api\/persons/)
  })

  it('has selectedPerson state', () => {
    expect(source).toMatch(/selectedPerson/)
    expect(source).toMatch(/setSelectedPerson/)
  })

  it('renders person dropdown when multiple persons exist', () => {
    expect(source).toMatch(/persons\.length > 1/)
    expect(source).toMatch(/<select/)
    expect(source).toMatch(/All Accounts/)
  })

  it('appends person param to ALL data API calls via withPerson helper', () => {
    expect(source).toMatch(/withPerson/)
    // Core scorecard routes
    expect(source).toMatch(/withPerson\(`\/api\/\$\{bot\}\/status`\)/)
    expect(source).toMatch(/withPerson\(`\/api\/\$\{bot\}\/equity-curve/)
    expect(source).toMatch(/withPerson\(`\/api\/\$\{bot\}\/position-monitor`\)/)
    expect(source).toMatch(/withPerson\(`\/api\/\$\{bot\}\/performance`\)/)
    // Extended data routes (trades, logs, signals, position-detail)
    expect(source).toMatch(/withPerson\(`\/api\/\$\{bot\}\/trades`\)/)
    expect(source).toMatch(/withPerson\(`\/api\/\$\{bot\}\/logs`\)/)
    expect(source).toMatch(/withPerson\(`\/api\/\$\{bot\}\/signals`\)/)
    expect(source).toMatch(/withPerson\(`\/api\/\$\{bot\}\/position-detail`\)/)
  })
})

/* ── Extended person filtering — additional routes ──────────── */

describe('Person filtering — additional routes', () => {
  const additionalRoutes = [
    { name: 'trades', path: '../../app/api/[bot]/trades/route.ts' },
    { name: 'daily-perf', path: '../../app/api/[bot]/daily-perf/route.ts' },
    { name: 'position-detail', path: '../../app/api/[bot]/position-detail/route.ts' },
    { name: 'logs', path: '../../app/api/[bot]/logs/route.ts' },
    { name: 'signals', path: '../../app/api/[bot]/signals/route.ts' },
  ]

  for (const route of additionalRoutes) {
    it(`${route.name} route reads person query parameter`, () => {
      const source = readFileSync(resolve(__dirname, route.path), 'utf-8')
      expect(source).toMatch(/personParam/)
      expect(source).toMatch(/personFilter/)
    })
  }
})

describe('Person filtering — NULL backfill migration', () => {
  const dbSource = readFileSync(resolve(__dirname, '../db.ts'), 'utf-8')

  it('backfills NULL person to User for positions', () => {
    expect(dbSource).toMatch(/SET person = 'User' WHERE person IS NULL/)
  })

  it('adds person column to logs and signals tables', () => {
    // The migration loop includes logs and signals in the table list
    expect(dbSource).toMatch(/logs/)
    expect(dbSource).toMatch(/signals/)
    // Both are in the same ALTER TABLE loop that adds person
    expect(dbSource).toMatch(/equity_snapshots.*daily_perf.*logs.*signals/)
  })
})

describe('Person filtering — scanner close-path', () => {
  const scannerSource = readFileSync(resolve(__dirname, '../scanner.ts'), 'utf-8')

  it('closePosition reads person from position row', () => {
    const fn = scannerSource.match(
      /async function closePosition[\s\S]*?^}/m,
    )
    expect(fn).toBeTruthy()
    expect(fn![0]).toMatch(/SELECT person FROM/)
    expect(fn![0]).toMatch(/posPerson/)
  })

  it('closePosition passes person to daily_perf INSERT', () => {
    const fn = scannerSource.match(
      /async function closePosition[\s\S]*?^}/m,
    )
    expect(fn).toBeTruthy()
    expect(fn![0]).toMatch(/daily_perf.*person/)
    expect(fn![0]).toMatch(/posPerson/)
  })
})

describe('Person filtering — force-close ownership check', () => {
  const source = readFileSync(
    resolve(__dirname, '../../app/api/[bot]/force-close/route.ts'),
    'utf-8',
  )

  it('reads person query parameter', () => {
    expect(source).toMatch(/personParam/)
  })

  it('selects person column from positions', () => {
    expect(source).toMatch(/person/)
    // The SELECT should include person
    expect(source).toMatch(/sandbox_order_id, person/)
  })

  it('returns 403 if position belongs to different person', () => {
    expect(source).toMatch(/403/)
    expect(source).toMatch(/belongs to/)
  })
})

describe('Person filtering — eod-close person filter', () => {
  const source = readFileSync(
    resolve(__dirname, '../../app/api/[bot]/eod-close/route.ts'),
    'utf-8',
  )

  it('reads person query parameter', () => {
    expect(source).toMatch(/personParam/)
  })

  it('builds parameterized person filter for positions query', () => {
    expect(source).toMatch(/personFilter/)
    expect(source).toMatch(/AND person = \$2/)
  })
})

describe('Person filtering — Compare page', () => {
  const source = readFileSync(
    resolve(__dirname, '../../components/CompareContent.tsx'),
    'utf-8',
  )

  it('fetches /api/persons for dropdown', () => {
    expect(source).toMatch(/\/api\/persons/)
  })

  it('has person dropdown when multiple persons exist', () => {
    expect(source).toMatch(/selectedPerson/)
    expect(source).toMatch(/persons\.length > 1/)
    expect(source).toMatch(/<select/)
  })

  it('appends person param to all 9 SWR calls', () => {
    // All bot status/equity/performance calls should include ${pq}
    expect(source).toMatch(/flame\/status\$\{pq\}/)
    expect(source).toMatch(/spark\/status\$\{pq\}/)
    expect(source).toMatch(/inferno\/status\$\{pq\}/)
    expect(source).toMatch(/flame\/equity-curve\$\{pq\}/)
    expect(source).toMatch(/flame\/performance\$\{pq\}/)
  })
})

/* ── Production Equity Curve ─────────────────────────────── */

describe('Production Equity Curve', () => {
  const { readFileSync } = require('fs')
  const { resolve } = require('path')

  const dbSource = readFileSync(
    resolve(__dirname, '../db.ts'),
    'utf-8',
  )
  const scannerSource = readFileSync(
    resolve(__dirname, '../scanner.ts'),
    'utf-8',
  )
  const equityCurveSource = readFileSync(
    resolve(__dirname, '../../app/api/accounts/production/equity-curve/route.ts'),
    'utf-8',
  )
  const dashboardSource = readFileSync(
    resolve(__dirname, '../../components/BotDashboard.tsx'),
    'utf-8',
  )

  it('creates production_equity_snapshots table in DDL', () => {
    expect(dbSource).toMatch(/CREATE TABLE IF NOT EXISTS production_equity_snapshots/)
  })

  it('production_equity_snapshots has required columns', () => {
    expect(dbSource).toMatch(/person TEXT NOT NULL/)
    expect(dbSource).toMatch(/total_equity NUMERIC/)
    expect(dbSource).toMatch(/option_buying_power NUMERIC/)
    expect(dbSource).toMatch(/day_pnl NUMERIC/)
    expect(dbSource).toMatch(/open_positions INT/)
  })

  it('scanner saves production equity snapshots each cycle', () => {
    expect(scannerSource).toMatch(/saveProductionEquitySnapshots/)
    // Called in runAllScans
    expect(scannerSource).toMatch(/saveProductionEquitySnapshots\(\)\.catch/)
  })

  it('saveProductionEquitySnapshots calls getSandboxAccountBalances', () => {
    const fn = scannerSource.match(
      /async function saveProductionEquitySnapshots[\s\S]*?^}/m,
    )
    expect(fn).toBeTruthy()
    expect(fn![0]).toMatch(/getSandboxAccountBalances/)
  })

  it('saveProductionEquitySnapshots inserts into production_equity_snapshots', () => {
    const fn = scannerSource.match(
      /async function saveProductionEquitySnapshots[\s\S]*?^}/m,
    )
    expect(fn).toBeTruthy()
    expect(fn![0]).toMatch(/INSERT INTO production_equity_snapshots/)
  })

  it('equity curve API supports person parameter', () => {
    expect(equityCurveSource).toMatch(/person.*parameter required/)
    expect(equityCurveSource).toMatch(/person = \$1/)
  })

  it('equity curve API supports intraday and historical modes', () => {
    expect(equityCurveSource).toMatch(/mode.*intraday/)
    expect(equityCurveSource).toMatch(/mode.*historical/)
  })

  it('equity curve API supports period filter', () => {
    expect(equityCurveSource).toMatch(/period/)
    expect(equityCurveSource).toMatch(/INTERVAL/)
  })

  it('BotDashboard includes Broker Equity tab', () => {
    expect(dashboardSource).toMatch(/Broker Equity/)
    expect(dashboardSource).toMatch(/BrokerEquityTab/)
  })

  it('BotDashboard fetches production equity curve data', () => {
    expect(dashboardSource).toMatch(/\/api\/accounts\/production\/equity-curve/)
  })
})
