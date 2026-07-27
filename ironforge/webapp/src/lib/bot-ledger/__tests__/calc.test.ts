import { describe, expect, it } from 'vitest'

import { classifyOutcome, legCountOf, projectTrade, setupLabel, toPublicTrade } from '../calc'
import { publicIdFor } from '../public-id'
import type { RawLedgerRow } from '../types'

function row(over: Partial<RawLedgerRow> = {}): RawLedgerRow {
  return {
    id: 101,
    position_id: 'pos-101',
    ticker: 'SPY',
    contracts: 1,
    realized_pnl: '42.00',
    bp: '500.00',
    put_short_strike: '618.00',
    put_long_strike: '613.00',
    call_short_strike: '628.00',
    call_long_strike: '633.00',
    status: 'closed',
    close_time: '2026-07-25T19:50:00.000Z',
    et_date: '2026-07-25',
    ct_date: '2026-07-25',
    ...over,
  }
}

describe('legCountOf', () => {
  it('counts a full iron condor as 4 legs', () => {
    expect(legCountOf(row())).toBe(4)
  })

  it('counts the post-April FLAME put credit spread as 2 legs', () => {
    // Call strikes are written as 0 by scanner.ts tryOpenFlamePutSpread.
    expect(legCountOf(row({ call_short_strike: '0', call_long_strike: '0' }))).toBe(2)
  })

  it('returns 0 when no strike pair is populated', () => {
    expect(
      legCountOf(
        row({ put_short_strike: '0', put_long_strike: '0', call_short_strike: '0', call_long_strike: '0' }),
      ),
    ).toBe(0)
  })
})

describe('setupLabel', () => {
  it('describes structure without leaking strikes', () => {
    expect(setupLabel(4, '1DTE', 'SPY')).toBe('SPY 1DTE Iron Condor')
    expect(setupLabel(2, '2DTE', 'SPY')).toBe('SPY 2DTE Put Credit Spread')
  })
})

describe('classifyOutcome', () => {
  it('splits on the exact cent boundary', () => {
    expect(classifyOutcome(1)).toBe('WIN')
    expect(classifyOutcome(0)).toBe('SCRATCH')
    expect(classifyOutcome(-1)).toBe('LOSS')
  })
})

describe('projectTrade', () => {
  it('projects a one-contract trade onto the public basis', () => {
    const r = projectTrade(row(), 'spark', '1DTE')
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.trade.netCents).toBe(4200)
    expect(r.trade.bpCents).toBe(50_000)
    expect(r.trade.returnOnBpHpct).toBe(840) // 8.40%
    expect(r.trade.outcome).toBe('WIN')
    expect(r.trade.setup).toBe('SPY 1DTE Iron Condor')
  })

  it('normalises a multi-contract position to a single contract', () => {
    // 127 contracts, $5,334.00 total, $63,500.00 collateral.
    const r = projectTrade(row({ contracts: 127, realized_pnl: '5334.00', bp: '63500.00' }), 'flame', '2DTE')
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.trade.netCents).toBe(4200) // 533400 / 127
    expect(r.trade.bpCents).toBe(50_000)
    expect(r.trade.returnOnBpHpct).toBe(840)
  })

  it('rounds a non-divisible per-contract split half away from zero', () => {
    const r = projectTrade(row({ contracts: 3, realized_pnl: '10.00', bp: '1500.00' }), 'spark', '1DTE')
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.trade.netCents).toBe(333) // 1000 / 3 = 333.33 -> 333
  })

  it('classifies a losing trade with a signed return', () => {
    const r = projectTrade(row({ realized_pnl: '-26.00' }), 'spark', '1DTE')
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.trade.outcome).toBe('LOSS')
    expect(r.trade.returnOnBpHpct).toBe(-520)
  })

  it('flags a trade whose ET and CT dates disagree', () => {
    const r = projectTrade(row({ et_date: '2026-07-26', ct_date: '2026-07-25' }), 'spark', '1DTE')
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.trade.tzDivergent).toBe(true)
  })

  it('rejects rows that cannot produce an honest public figure', () => {
    const reject = (over: Partial<RawLedgerRow>) => {
      const r = projectTrade(row(over), 'spark', '1DTE')
      expect(r.ok).toBe(false)
      return r.ok ? null : r.reason
    }
    expect(reject({ contracts: 0 })).toBe('INVALID_CONTRACTS')
    expect(reject({ contracts: -2 })).toBe('INVALID_CONTRACTS')
    expect(reject({ close_time: null })).toBe('MISSING_CLOSE_TIME')
    expect(reject({ bp: '0.00' })).toBe('INVALID_BUYING_POWER')
    expect(reject({ realized_pnl: 'not-a-number' })).toBe('INVALID_NUMERIC')
    expect(
      reject({
        put_short_strike: '0',
        put_long_strike: '0',
        call_short_strike: '0',
        call_long_strike: '0',
      }),
    ).toBe('ZERO_LEGS')
  })
})

describe('publicIdFor', () => {
  it('is stable for the same row and distinct across rows and bots', () => {
    expect(publicIdFor('spark', 101)).toBe(publicIdFor('spark', 101))
    expect(publicIdFor('spark', 101)).not.toBe(publicIdFor('spark', 102))
    expect(publicIdFor('spark', 101)).not.toBe(publicIdFor('flame', 101))
    expect(publicIdFor('spark', 101)).toMatch(/^trd_[0-9a-f]{12}$/)
  })
})

describe('toPublicTrade', () => {
  it('emits only allowlisted fields, all decimals as strings', () => {
    const r = projectTrade(row(), 'spark', '1DTE')
    if (!r.ok) throw new Error('expected projection to succeed')
    const dto = toPublicTrade(r.trade)

    expect(Object.keys(dto).sort()).toEqual([
      'bot',
      'buying_power_used',
      'closed_date',
      'net_result',
      'public_id',
      'return_on_bp_pct',
      'setup',
      'outcome',
    ].sort())
    expect(dto.buying_power_used).toBe('500.00')
    expect(dto.net_result).toBe('42.00')
    expect(dto.return_on_bp_pct).toBe('8.40')
    expect(dto.outcome).toBe('win')
    expect(dto.closed_date).toBe('2026-07-25')
  })

  it('never leaks a strike, a timestamp, or a close reason', () => {
    const r = projectTrade(row(), 'spark', '1DTE')
    if (!r.ok) throw new Error('expected projection to succeed')
    const serialised = JSON.stringify(toPublicTrade(r.trade))
    for (const forbidden of ['618', '613', '628', '633', '19:50', 'close_reason', 'position_id']) {
      expect(serialised).not.toContain(forbidden)
    }
  })
})
