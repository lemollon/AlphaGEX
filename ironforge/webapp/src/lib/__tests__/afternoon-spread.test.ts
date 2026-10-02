import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
  getAfternoonSpreadPaperMode,
  isInTriggerWindow,
  referencePutStrike,
  referenceCallStrike,
  downTriggerFires,
  upTriggerFires,
  downTriggerCallVertical,
  upTriggerPutVertical,
  entryCredit,
  callVerticalIntrinsic,
  putVerticalIntrinsic,
  settlementPnl,
  tagGate,
  summarizeAfternoonSpreadLedger,
  TRIGGER_WINDOW_START_HHMM,
  TRIGGER_WINDOW_END_HHMM,
  FLAME_VIX_GATE_CEILING,
  type AfternoonSpreadLedgerRow,
} from '../afternoon-spread'

describe('getAfternoonSpreadPaperMode', () => {
  const ORIGINAL = process.env.AFTERNOON_SPREAD_PAPER

  afterEach(() => {
    if (ORIGINAL === undefined) delete process.env.AFTERNOON_SPREAD_PAPER
    else process.env.AFTERNOON_SPREAD_PAPER = ORIGINAL
  })

  it('unset defaults to off', () => {
    delete process.env.AFTERNOON_SPREAD_PAPER
    expect(getAfternoonSpreadPaperMode()).toBe(false)
  })

  it('"on" (any case, trimmed) enables it', () => {
    process.env.AFTERNOON_SPREAD_PAPER = 'on'
    expect(getAfternoonSpreadPaperMode()).toBe(true)
    process.env.AFTERNOON_SPREAD_PAPER = ' ON '
    expect(getAfternoonSpreadPaperMode()).toBe(true)
  })

  it('fails CLOSED on anything else', () => {
    for (const v of ['off', '', 'true', '1', 'live', 'armed', 'yes']) {
      process.env.AFTERNOON_SPREAD_PAPER = v
      expect(getAfternoonSpreadPaperMode(), `"${v}" must resolve to off`).toBe(false)
    }
  })
})

describe('isInTriggerWindow', () => {
  it('is inclusive of both ends of 13:10-14:45 CT', () => {
    expect(isInTriggerWindow(TRIGGER_WINDOW_START_HHMM)).toBe(true)
    expect(isInTriggerWindow(TRIGGER_WINDOW_END_HHMM)).toBe(true)
    expect(isInTriggerWindow(1309)).toBe(false)
    expect(isInTriggerWindow(1446)).toBe(false)
    expect(isInTriggerWindow(1330)).toBe(true)
  })
})

describe('reference strikes', () => {
  it('P = round(spot - 1) — FLAME EBB $1 OTM put strike', () => {
    expect(referencePutStrike(583.4)).toBe(582)
    expect(referencePutStrike(583.6)).toBe(583)
    expect(referencePutStrike(600)).toBe(599)
  })

  it('C = ceil(spot + 1) — FLINT rule call strike', () => {
    expect(referenceCallStrike(583.05)).toBe(585)
    expect(referenceCallStrike(583)).toBe(584)
    expect(referenceCallStrike(600)).toBe(601)
  })
})

describe('trigger math', () => {
  it('down trigger fires at or inside $0.50 of P', () => {
    const p = 582
    expect(downTriggerFires(582.5, p)).toBe(true) // exactly at buffer
    expect(downTriggerFires(582.51, p)).toBe(false)
    expect(downTriggerFires(582, p)).toBe(true)
    expect(downTriggerFires(581, p)).toBe(true) // through the strike
  })

  it('up trigger fires at or inside $0.50 of C', () => {
    const c = 585
    expect(upTriggerFires(584.5, c)).toBe(true) // exactly at buffer
    expect(upTriggerFires(584.49, c)).toBe(false)
    expect(upTriggerFires(585, c)).toBe(true)
    expect(upTriggerFires(586, c)).toBe(true) // through the strike
  })

  it('respects a custom buffer', () => {
    expect(downTriggerFires(100, 99, 2)).toBe(true)
    expect(downTriggerFires(102, 99, 2)).toBe(false)
  })
})

describe('vertical strike rules', () => {
  it('down trigger sells a $1-wide CALL vertical: short=ceil(spot)+1, long=short+1', () => {
    expect(downTriggerCallVertical(582.4)).toEqual({ short: 584, long: 585 })
    expect(downTriggerCallVertical(582)).toEqual({ short: 583, long: 584 })
  })

  it('up trigger sells a $1-wide PUT vertical: short=floor(spot)-1, long=short-1', () => {
    expect(upTriggerPutVertical(585.6)).toEqual({ short: 584, long: 583 })
    expect(upTriggerPutVertical(586)).toEqual({ short: 585, long: 584 })
  })
})

describe('entryCredit', () => {
  it('short bid minus long ask, when positive', () => {
    expect(entryCredit(0.35, 0.10)).toBe(0.25)
  })

  it('returns null (never a floored zero) on non-positive credit', () => {
    expect(entryCredit(0.10, 0.10)).toBeNull()
    expect(entryCredit(0.10, 0.35)).toBeNull()
    expect(entryCredit(0, 0)).toBeNull()
  })
})

describe('settlement intrinsic', () => {
  it('call vertical: 0 below short, width above long, linear between', () => {
    expect(callVerticalIntrinsic(583, 584, 585)).toBe(0)
    expect(callVerticalIntrinsic(584, 584, 585)).toBe(0)
    expect(callVerticalIntrinsic(584.5, 584, 585)).toBe(0.5)
    expect(callVerticalIntrinsic(585, 584, 585)).toBe(1)
    expect(callVerticalIntrinsic(590, 584, 585)).toBe(1) // clamped to width
  })

  it('put vertical: 0 above short, width below long, linear between', () => {
    expect(putVerticalIntrinsic(585, 584, 583)).toBe(0)
    expect(putVerticalIntrinsic(584, 584, 583)).toBe(0)
    expect(putVerticalIntrinsic(583.5, 584, 583)).toBe(0.5)
    expect(putVerticalIntrinsic(583, 584, 583)).toBe(1)
    expect(putVerticalIntrinsic(575, 584, 583)).toBe(1) // clamped to width
  })
})

describe('settlementPnl', () => {
  it('(credit - intrinsic) x 100 x contracts, minus $1.40/contract commission', () => {
    // Full credit kept (expired worthless): 0.30 credit, 0 intrinsic.
    expect(settlementPnl(0.30, 0, 1)).toBe(0.30 * 100 - 1.40)
    // Max loss: 0.30 credit, 1.00 intrinsic (full width).
    expect(settlementPnl(0.30, 1, 1)).toBeCloseTo((0.30 - 1) * 100 - 1.40, 5)
  })

  it('scales with contracts', () => {
    expect(settlementPnl(0.30, 0, 3)).toBeCloseTo((0.30 * 100 - 1.40) * 3, 5)
  })
})

describe('tagGate', () => {
  it('gate_pass when ratio <= ceiling (FLAME would have traded)', () => {
    expect(tagGate(0.80)).toBe('gate_pass')
    expect(tagGate(0.50)).toBe('gate_pass')
  })

  it('gate_skip when ratio > ceiling (elevated — where 98% of the edge sits)', () => {
    expect(tagGate(0.81)).toBe('gate_skip')
    expect(tagGate(1.20)).toBe('gate_skip')
  })

  it('gate_skip when ratio is unreadable (null) — never a guess', () => {
    expect(tagGate(null)).toBe('gate_skip')
  })

  it('default ceiling is FLAME_VIX_GATE_CEILING (0.80)', () => {
    expect(FLAME_VIX_GATE_CEILING).toBe(0.80)
    expect(tagGate(0.80)).toBe('gate_pass')
    expect(tagGate(0.8000001)).toBe('gate_skip')
  })
})

describe('summarizeAfternoonSpreadLedger', () => {
  const rows: AfternoonSpreadLedgerRow[] = [
    { trade_date: '2026-09-01', side: 'down_call', gate_tag: 'gate_skip', status: 'settled', realized_pnl: 28.6 },
    { trade_date: '2026-09-02', side: 'up_put', gate_tag: 'gate_pass', status: 'settled', realized_pnl: -1.4 },
    { trade_date: '2026-09-03', side: 'down_call', gate_tag: 'gate_skip', status: 'skipped', realized_pnl: null },
    { trade_date: '2026-09-04', side: 'up_put', gate_tag: 'gate_skip', status: 'tracked', realized_pnl: null },
  ]

  it('buckets by side and by gate tag, summing only settled realized_pnl', () => {
    const totals = summarizeAfternoonSpreadLedger(rows)
    expect(totals.by_side.down_call).toEqual({ rows: 2, settled: 1, skipped: 1, net_pnl: 28.6 })
    expect(totals.by_side.up_put).toEqual({ rows: 2, settled: 1, skipped: 0, net_pnl: -1.4 })
    expect(totals.by_gate.gate_skip).toEqual({ rows: 3, settled: 1, skipped: 1, net_pnl: 28.6 })
    expect(totals.by_gate.gate_pass).toEqual({ rows: 1, settled: 1, skipped: 0, net_pnl: -1.4 })
  })

  it('empty ledger produces empty buckets', () => {
    expect(summarizeAfternoonSpreadLedger([])).toEqual({ by_side: {}, by_gate: {} })
  })
})
