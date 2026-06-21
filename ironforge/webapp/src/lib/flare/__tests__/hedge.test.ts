import { describe, it, expect } from 'vitest'
import { computeImbalance, decideHedge, sigMove } from '@/lib/flare/hedge'

const pos = (direction: 'call' | 'put', debit: number, contracts: number, setup_type?: string) =>
  ({ direction, debit, contracts, setup_type })

describe('computeImbalance', () => {
  it('nets put vs call max-loss and finds the heavy side', () => {
    // 10 put spreads @ debit 0.22 × 23 ≈ the 6/15 shape (one-sided)
    const im = computeImbalance([pos('put', 0.22, 23), pos('put', 0.22, 23)])
    expect(im.callRisk).toBe(0)
    expect(im.heavyDir).toBe('put')
    expect(im.netImbalance).toBe(im.putRisk)
  })

  it('a balanced book has low net imbalance even at high gross', () => {
    const im = computeImbalance([pos('put', 0.2, 20), pos('call', 0.2, 20)]) // 6/08 shape
    expect(im.netImbalance).toBe(0)
    expect(im.heavyDir).toBe('none')
  })

  it('excludes the hedge’s own positions', () => {
    const im = computeImbalance([pos('put', 0.5, 10), pos('call', 0.5, 30, 'imbalance_hedge')])
    expect(im.callRisk).toBe(0) // the hedge call spread is not counted as directional exposure
    expect(im.heavyDir).toBe('put')
  })
})

describe('decideHedge', () => {
  const sig = 8 // ~$8 1σ move

  it('does not hedge a balanced book', () => {
    const d = decideHedge({ imbalance: computeImbalance([pos('put', 0.2, 10), pos('call', 0.2, 10)]), sigMove: sig })
    expect(d.hedge).toBe(false)
  })

  it('does not hedge below the floor', () => {
    const d = decideHedge({ imbalance: { putRisk: 1500, callRisk: 0, netImbalance: 1500, heavyDir: 'put' }, sigMove: sig, floor: 2000 })
    expect(d.hedge).toBe(false)
  })

  it('hedges the EXCESS above the floor, buying the opposing side', () => {
    // 6/15: $5,073 put-heavy, floor 2000, coverage 0.75 → excess 3073, target ~2305
    const d = decideHedge({ imbalance: { putRisk: 5073, callRisk: 0, netImbalance: 5073, heavyDir: 'put' }, sigMove: sig, floor: 2000, coverage: 0.75 })
    expect(d.hedge).toBe(true)
    expect(d.hedgeSide).toBe('call') // put-heavy → buy calls (profit on the adverse up-move)
    expect(d.excess).toBe(3073)
    expect(d.targetOffset).toBe(2305)
    expect(d.contracts).toBeGreaterThan(0)
  })

  it('call-heavy book hedges with puts', () => {
    const d = decideHedge({ imbalance: { putRisk: 0, callRisk: 6000, netImbalance: 6000, heavyDir: 'call' }, sigMove: sig })
    expect(d.hedgeSide).toBe('put')
  })
})

describe('sigMove', () => {
  it('computes the VIX-implied 1-day move (~$8 at SPY 753 / VIX 16.3)', () => {
    const s = sigMove(753, 16.3)
    expect(s).toBeGreaterThan(6)
    expect(s).toBeLessThan(10)
  })
})
