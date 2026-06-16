/**
 * FLARE net-imbalance hedge — pure statistical core.
 *
 * Replaces the per-direction force-close guillotine. The risk isn't gross size,
 * it's DIRECTIONAL IMBALANCE: on FLARE's own tape the profitable days ran balanced
 * books (6/08 P20/C16 → +$1,067) and the loss day ran one-sided with no offset
 * (6/15 P10/C0, $5,073 put-side at risk → −$1,290). So we measure the unhedged
 * one-directional tail and, above a tolerance floor, buy an OPPOSING debit spread
 * to recover a target fraction of the excess on an adverse move.
 *
 * Pure + total: no I/O. The monitor passes open positions + a 1σ move; the executor
 * turns the returned target into a real opposing spread.
 */

export interface HedgePosition {
  direction: 'call' | 'put'
  debit: number // per-contract debit (dollars)
  contracts: number
  setup_type?: string
}

export interface Imbalance {
  /** Σ max-loss of put (bearish) directional positions, dollars. */
  putRisk: number
  /** Σ max-loss of call (bullish) directional positions, dollars. */
  callRisk: number
  /** |putRisk − callRisk| — the unhedged one-directional tail. */
  netImbalance: number
  heavyDir: 'put' | 'call' | 'none'
}

/** A debit spread's max loss = debit × 100 × contracts. */
function posMaxLoss(p: HedgePosition): number {
  return Math.max(0, p.debit) * 100 * (p.contracts || 0)
}

/**
 * Net directional imbalance from the open SIGNAL book. Excludes the hedge's own
 * positions (setup_type 'imbalance_hedge') so the hedge can't chase its own tail.
 */
export function computeImbalance(positions: HedgePosition[]): Imbalance {
  let putRisk = 0
  let callRisk = 0
  for (const p of positions) {
    if (p.setup_type === 'imbalance_hedge') continue
    if (p.direction === 'put') putRisk += posMaxLoss(p)
    else callRisk += posMaxLoss(p)
  }
  putRisk = Math.round(putRisk)
  callRisk = Math.round(callRisk)
  const netImbalance = Math.abs(putRisk - callRisk)
  const heavyDir = putRisk === callRisk ? 'none' : putRisk > callRisk ? 'put' : 'call'
  return { putRisk, callRisk, netImbalance, heavyDir }
}

/** Calibrated from FLARE's tape: floor ≈ 2× a good day's net; cover the excess aggressively. */
export const HEDGE_FLOOR = Number(process.env.FLARE_HEDGE_FLOOR) || 2000
export const HEDGE_COVERAGE = Number(process.env.FLARE_HEDGE_COVERAGE) || 0.75

export interface HedgeDecision {
  hedge: boolean
  reason: string
  heavyDir: 'put' | 'call' | 'none'
  /** The protective side to BUY (opposite the heavy side). */
  hedgeSide: 'call' | 'put' | null
  netImbalance: number
  /** netImbalance − floor (>0 only when hedging). */
  excess: number
  /** Target $ the hedge should recover on a 1σ adverse move (coverage × excess). */
  targetOffset: number
  /** Opposing-spread contracts to buy, sized so its 1σ-adverse gain ≈ targetOffset. */
  contracts: number
}

/**
 * Decide the hedge from the imbalance. Hedge only the EXCESS above the tolerance
 * floor (a balanced/light book is naturally self-hedged), opposing the heavy side.
 * Contracts are sized so an opposing ATM-ish debit spread recovers ~targetOffset on
 * a 1σ adverse move: gain/contract ≈ perSpreadDeltaPayoff (long spread delta × σ × 100).
 */
export function decideHedge(p: {
  imbalance: Imbalance
  sigMove: number // 1σ daily SPY move in dollars (VIX-implied)
  floor?: number
  coverage?: number
  perSpreadDeltaPayoff?: number // est. $ a 1-wide opposing spread gains per 1σ move/contract
}): HedgeDecision {
  const floor = p.floor ?? HEDGE_FLOOR
  const coverage = p.coverage ?? HEDGE_COVERAGE
  const { netImbalance, heavyDir } = p.imbalance

  const none = (reason: string): HedgeDecision => ({
    hedge: false, reason, heavyDir, hedgeSide: null, netImbalance, excess: 0, targetOffset: 0, contracts: 0,
  })

  if (heavyDir === 'none' || netImbalance <= floor) {
    return none(`balanced book — net imbalance $${netImbalance} ≤ floor $${floor}`)
  }

  const excess = Math.round(netImbalance - floor)
  const targetOffset = Math.round(coverage * excess)
  const hedgeSide: 'call' | 'put' = heavyDir === 'put' ? 'call' : 'put' // buy the side that profits on the adverse move

  // A 1-wide debit spread's net delta ≈ 0.15; its $ gain on a 1σ move/contract ≈
  // 0.15 × sigMove × 100, capped by the spread width. Caller may override.
  const perSpreadGain = p.perSpreadDeltaPayoff ?? Math.max(1, 0.15 * p.sigMove * 100)
  const contracts = Math.max(1, Math.round(targetOffset / perSpreadGain))

  return {
    hedge: true,
    reason: `${heavyDir}-heavy by $${netImbalance} (>${floor}); hedge ${hedgeSide} to recover ~$${targetOffset} on a 1σ move`,
    heavyDir, hedgeSide, netImbalance, excess, targetOffset, contracts,
  }
}

/** VIX-implied 1σ one-day SPY move in dollars. */
export function sigMove(spot: number, vix: number): number {
  if (!(spot > 0) || !(vix > 0)) return 0
  return Math.round(spot * (vix / 100) * Math.sqrt(1 / 252) * 100) / 100
}
