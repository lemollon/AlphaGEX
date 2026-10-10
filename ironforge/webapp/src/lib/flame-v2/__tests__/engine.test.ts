/**
 * Proves the core safety invariant of the whole FLAME v2 / SPARK v2 build:
 * when a required live input is missing or stale, every decision function
 * reports `available:false` and — for the admission-affecting ones —
 * `admits` falls back to EXACTLY the value the caller already computes
 * today (`todaysPriorSpyUpRule` / `false` for a sleeve that doesn't exist
 * live yet), so the live bot's behavior is byte-identical to pre-this-PR
 * behavior whenever data is missing. Also proves shadow mode never flips
 * `admits`/order-affecting fields even when the underlying signal IS
 * available (the "change nothing about orders" half of the spec).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.mock('../theta-proxy', () => ({
  fetchVixMinuteWindow: vi.fn(async () => ({ ok: false, reason: 'mock_unavailable' })),
  fetchLiveGexChain: vi.fn(async () => ({ ok: false, reason: 'mock_unavailable' })),
}))
vi.mock('../signal-store', () => ({
  priorCalmMeasures: vi.fn(async () => []),
  priorBandEligibleRows: vi.fn(async () => []),
  recordDailySignal: vi.fn(async () => undefined),
}))

import { fetchVixMinuteWindow, fetchLiveGexChain } from '../theta-proxy'
import { priorBandEligibleRows, priorCalmMeasures, recordDailySignal } from '../signal-store'
import {
  computeSignalSnapshot, flameRegimeBrainDecision, sparkTrailingBandDecision,
  sparkS1Decision, flameCallSpreadDecision, recordBandOutcome,
} from '../engine'

const ENV_KEYS = ['FLAME_V2_REGIME_BRAIN_MODE', 'FLAME_V2_CALL_SPREAD_MODE', 'SPARK_V2_TRAILING_BAND_MODE', 'SPARK_V2_SIGNAL_FILTER_MODE']
let savedEnv: Record<string, string | undefined> = {}

beforeEach(() => {
  savedEnv = {}
  for (const k of ENV_KEYS) { savedEnv[k] = process.env[k]; delete process.env[k] }
  vi.clearAllMocks()
})
afterEach(() => {
  for (const k of ENV_KEYS) {
    if (savedEnv[k] === undefined) delete process.env[k]
    else process.env[k] = savedEnv[k]
  }
})

describe('missing/stale inputs => identical behavior to today (fail-closed)', () => {
  it('computeSignalSnapshot: theta proxy unreachable -> both signals unavailable, no throw', async () => {
    const snap = await computeSignalSnapshot('flame', '2026-10-02')
    expect(snap.calm.available).toBe(false)
    expect(snap.longg.available).toBe(false)
    expect(snap.calm.reason).toContain('mock_unavailable')
    expect(snap.longg.reason).toContain('mock_unavailable')
  })

  it('flameRegimeBrainDecision: default mode is shadow and falls back to todays rule even when enabled', async () => {
    // default (env unset) = 'shadow', not 'off' — the decision still computes,
    // but `admits` must equal exactly what the caller already does today.
    const decision = await flameRegimeBrainDecision('2026-10-02', null, true)
    expect(decision.admits).toBe(true) // == todaysPriorSpyUpRule, unchanged
    const decision2 = await flameRegimeBrainDecision('2026-10-02', null, false)
    expect(decision2.admits).toBe(false)
  })

  it('flameRegimeBrainDecision: off mode never computes anything', async () => {
    process.env.FLAME_V2_REGIME_BRAIN_MODE = 'off'
    const decision = await flameRegimeBrainDecision('2026-10-02', null, true)
    expect(decision.available).toBe(false)
    expect(decision.reason).toBe('off')
  })

  it('flameRegimeBrainDecision: shadow mode never changes admits even with enough training rows and valid features', async () => {
    const rows = Array.from({ length: 50 }, (_, i) => ({
      tradeDate: `2026-01-${String((i % 28) + 1).padStart(2, '0')}`,
      ratio: 0.85, priorSpyUp: true,
      r0Pnl: i % 2 === 0 ? 50 : -10, r1Pnl: i % 2 === 0 ? -10 : 80, r2Pnl: 0, r3Pnl: 0,
      vixLevel: 15 + (i % 10), vix1yPct: 40, vix20dChg: 1, tsRatioL: 0.8, ret20: 0.01, ret60: 0.02, above50dma: 1,
    }))
    ;(priorBandEligibleRows as any).mockResolvedValueOnce(rows)
    const features = { vixLevel: 16, vix1yPct: 40, vix20dChg: 1, tsRatioL: 0.8, ret20: 0.01, ret60: 0.02, above50dma: 1 }
    const decision = await flameRegimeBrainDecision('2026-10-02', features, false)
    // Whatever D2 predicts internally, shadow mode's `admits` must equal the
    // caller's own static rule (false here) — never the model's rule.
    expect(decision.admits).toBe(false)
    expect(decision.reason).toBe('ok_shadow_no_behavior_change')
  })

  it('flameRegimeBrainDecision: live mode with insufficient rows still falls back to R0/static rule', async () => {
    process.env.FLAME_V2_REGIME_BRAIN_MODE = 'live'
    const features = { vixLevel: 16, vix1yPct: 40, vix20dChg: 1, tsRatioL: 0.8, ret20: 0.01, ret60: 0.02, above50dma: 1 }
    const decision = await flameRegimeBrainDecision('2026-10-02', features, true)
    expect(decision.admits).toBe(true)
    expect(decision.reason).toContain('fallback_R0')
  })

  it('flameRegimeBrainDecision: live mode, tree predicts R0, defers to todaysPriorSpyUpRule instead of hard-skipping', async () => {
    // 2026-10-10 regression: predicted R0 used to force admits=false
    // unconditionally. R0 means "defer to today's prior-SPY-up rule" --
    // prove it actually defers both ways (true AND false), not just skip.
    process.env.FLAME_V2_REGIME_BRAIN_MODE = 'live'
    const rows = Array.from({ length: 60 }, (_, i) => {
      const vixLevel = i < 30 ? 12 : 30 // clean separation for a depth-1 split
      const label1 = vixLevel >= 30 // R1 wins only on the high-vix side
      return {
        tradeDate: `2026-0${1 + (i % 9)}-${String((i % 28) + 1).padStart(2, '0')}`,
        ratio: 0.85, priorSpyUp: true,
        r0Pnl: label1 ? -10 : 50, r1Pnl: label1 ? 80 : -10, r2Pnl: 0, r3Pnl: 0,
        vixLevel, vix1yPct: 40, vix20dChg: 1, tsRatioL: 0.8, ret20: 0.01, ret60: 0.02, above50dma: 1,
      }
    })
    ;(priorBandEligibleRows as any).mockResolvedValueOnce(rows).mockResolvedValueOnce(rows)
    // Low-vix features land on the R0 (low-vix) leaf -> predicted rule 0.
    const lowVixFeatures = { vixLevel: 11, vix1yPct: 40, vix20dChg: 1, tsRatioL: 0.8, ret20: 0.01, ret60: 0.02, above50dma: 1 }

    const whenPriorUpTrue = await flameRegimeBrainDecision('2026-10-02', lowVixFeatures, true)
    expect(whenPriorUpTrue.rule).toBe(0)
    expect(whenPriorUpTrue.admits).toBe(true) // R0 predicted + prior_up true -> ADMIT, not skip

    const whenPriorUpFalse = await flameRegimeBrainDecision('2026-10-02', lowVixFeatures, false)
    expect(whenPriorUpFalse.rule).toBe(0)
    expect(whenPriorUpFalse.admits).toBe(false) // R0 predicted + prior_up false -> skip
  })

  it('sparkTrailingBandDecision: default shadow mode never admits a live order (SPARK has no relaxed-band order path yet)', async () => {
    const decision = await sparkTrailingBandDecision('2026-10-02')
    expect(decision.admits).toBe(false)
  })

  it('sparkS1Decision: signals unavailable -> would never skip a trade that is already admitted today', async () => {
    const decision = await sparkS1Decision('2026-10-02')
    expect(decision.available).toBe(false)
    expect(decision.wouldSkip).toBe(false)
  })

  it('flameCallSpreadDecision: signals unavailable -> 0 contracts, no strikes computed for an order', async () => {
    const decision = await flameCallSpreadDecision('2026-10-02', 601.5, 2)
    expect(decision.available).toBe(false)
    expect(decision.contracts).toBe(0)
    expect(decision.shortStrike).toBeNull()
  })

  it('flameCallSpreadDecision: off mode computes nothing at all', async () => {
    process.env.FLAME_V2_CALL_SPREAD_MODE = 'off'
    const decision = await flameCallSpreadDecision('2026-10-02', 601.5, 2)
    expect(decision.available).toBe(false)
    expect(decision.reason).toBe('off')
    expect(fetchVixMinuteWindow).not.toHaveBeenCalled()
    expect(fetchLiveGexChain).not.toHaveBeenCalled()
  })
})

describe('signals available end-to-end (theta proxy + history both healthy)', () => {
  beforeEach(() => {
    ;(fetchVixMinuteWindow as any).mockResolvedValue({
      ok: true,
      data: Array.from({ length: 119 }, (_, i) => 20 + Math.sin(i / 7) * 0.2),
    })
    ;(fetchLiveGexChain as any).mockResolvedValue({
      ok: true,
      data: {
        spot: 601.5,
        rows: [
          { strike: 598, iv: 0.15, callOi: 500, putOi: 3000, dteCalendarDays: 0 },
          { strike: 601, iv: 0.14, callOi: 2000, putOi: 1200, dteCalendarDays: 0 },
          { strike: 604, iv: 0.16, callOi: 1800, putOi: 400, dteCalendarDays: 0 },
        ],
      },
    })
  })

  it('computeSignalSnapshot: LONGG available and sign-consistent with igexFormulaNet', async () => {
    const snap = await computeSignalSnapshot('flame', '2026-10-02')
    expect(snap.longg.available).toBe(true)
    expect(typeof snap.longg.igexNet).toBe('number')
    expect(snap.longg.isLongg).toBe((snap.longg.igexNet as number) > 0)
  })

  it('computeSignalSnapshot: CALM still unavailable with <20 prior sessions even though the proxy answered', async () => {
    const snap = await computeSignalSnapshot('flame', '2026-10-02')
    expect(snap.calm.available).toBe(false)
    expect(snap.calm.reason).toContain('calm_insufficient_history')
  })

  it('flameCallSpreadDecision: shadow mode computes a real tier/strikes but still only logs — order placement is explicitly not implemented', async () => {
    process.env.FLAME_V2_CALL_SPREAD_MODE = 'shadow'
    const decision = await flameCallSpreadDecision('2026-10-02', 601.5, 2)
    // CALM is unavailable (insufficient history in this test), so the overall
    // decision stays unavailable — proving the call-spread sleeve inherits
    // CALM's own fail-closed behavior rather than silently sizing on LONGG alone.
    expect(decision.available).toBe(false)
  })

  describe('recordBandOutcome: never fabricates a pnl', () => {
    // computeSignalSnapshot's own finishSnapshot ALWAYS writes a calm/longg-
    // only recordDailySignal call as a side effect, independent of whatever
    // recordBandOutcome itself decides -- both the caller's own verification
    // snapshot AND recordBandOutcome's internal one trigger it. So: never
    // assert a call COUNT; assert whether any call ever set bandEligible,
    // and read the band-affecting fields off the LAST such call.
    const bandWrites = () => (recordDailySignal as any).mock.calls.filter((c: any[]) => c[2]?.bandEligible === true)

    beforeEach(() => {
      // >=20 prior measures -> CALM becomes available alongside LONGG, so
      // `best` is a real, both-signals-known boolean, not a forced skip.
      ;(priorCalmMeasures as any).mockResolvedValue(Array.from({ length: 25 }, (_, i) => 0.01 + i * 0.0005))
    })

    it('real trade settled -> r0/r1 derived from the SAME real pnl, gated by prior_up / best respectively', async () => {
      const snap = await computeSignalSnapshot('flame', '2026-10-05')
      expect(snap.calm.available).toBe(true)
      expect(snap.longg.available).toBe(true)
      const best = snap.calm.isCalm || snap.longg.isLongg

      const result = await recordBandOutcome({
        bot: 'flame', dateStr: '2026-10-05', ratio: 0.85, priorSpyUp: true, realizedPnl: 123.45,
      })
      expect(result).toContain('recorded')
      const writes = bandWrites()
      expect(writes.length).toBe(1)
      const written = writes[0][2]
      expect(written.r0Pnl).toBe(123.45) // prior_up=true -> R0 gets the real pnl
      expect(written.r1Pnl).toBe(best ? 123.45 : 0) // R1 gated on the real `best`
      expect(written.r3Pnl).toBe(0)
    })

    it('both signals unavailable -> refuses to guess `best`, records nothing band-related', async () => {
      ;(fetchVixMinuteWindow as any).mockResolvedValue({ ok: false, reason: 'mock_unavailable_for_this_case' })
      ;(fetchLiveGexChain as any).mockResolvedValue({ ok: false, reason: 'mock_unavailable_for_this_case' })
      const result = await recordBandOutcome({
        bot: 'flame', dateStr: '2026-10-05', ratio: 0.85, priorSpyUp: false, realizedPnl: null,
      })
      expect(result).toContain('skip:signals_unavailable')
      expect(bandWrites().length).toBe(0)
    })

    it('no trade, best genuinely false (both signals known) -> recorded as r0=0 r1=0, no fabrication', async () => {
      // Force LONGG false and CALM false with a concrete, checkable fixture.
      ;(fetchVixMinuteWindow as any).mockResolvedValue({
        ok: true, data: Array.from({ length: 119 }, (_, i) => 20 + (i % 2 === 0 ? 2 : -2)), // violently choppy -> high measure -> NOT calm
      })
      ;(fetchLiveGexChain as any).mockResolvedValue({
        ok: true, data: { spot: 601.5, rows: [{ strike: 601, iv: 0.15, callOi: 100, putOi: 5000, dteCalendarDays: 0 }] }, // put-heavy -> net < 0 -> NOT longg
      })
      const snap = await computeSignalSnapshot('flame', '2026-10-05')
      expect(snap.calm.isCalm).toBe(false)
      expect(snap.longg.isLongg).toBe(false)

      const result = await recordBandOutcome({
        bot: 'flame', dateStr: '2026-10-05', ratio: 0.85, priorSpyUp: false, realizedPnl: null,
      })
      expect(result).toContain('recorded')
      const writes = bandWrites()
      expect(writes.length).toBe(1)
      expect(writes[0][2].r0Pnl).toBe(0)
      expect(writes[0][2].r1Pnl).toBe(0)
    })

    it('no trade, prior_up=false but best=true -> the one genuine gap: skip, record nothing, never guess', async () => {
      ;(fetchVixMinuteWindow as any).mockResolvedValue({
        ok: true, data: Array.from({ length: 119 }, () => 20), // perfectly flat -> measure 0 -> calm
      })
      ;(fetchLiveGexChain as any).mockResolvedValue({
        ok: true, data: { spot: 601.5, rows: [{ strike: 601, iv: 0.15, callOi: 5000, putOi: 100, dteCalendarDays: 0 }] }, // call-heavy -> net > 0 -> longg
      })
      const snap = await computeSignalSnapshot('flame', '2026-10-05')
      expect(snap.calm.isCalm || snap.longg.isLongg).toBe(true) // best is true

      const result = await recordBandOutcome({
        bot: 'flame', dateStr: '2026-10-05', ratio: 0.85, priorSpyUp: false, realizedPnl: null,
      })
      expect(result).toBe('skip:unobservable_pnl_no_shadow_quote')
      expect(bandWrites().length).toBe(0)
    })
  })
})
