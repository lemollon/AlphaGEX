/**
 * EDGE-DECAY ALARM — CUSUM math against a hand-computed series, the alarm
 * threshold, an intact-edge sequence that never alarms, the pause/shadow/
 * resume state machine, "EBB never pauses," and EDGE_DECAY_MODE gating
 * (off/notify/enforce). See lib/edge-decay.ts's header for the spec this
 * implements (PREREG_edge_decay_alarm.md / RESULT_edge_decay_alarm.md).
 *
 * The pure math (cusumStep/isAlarmed) and the pure state machine
 * (applyClosedTrade) need no DB mock at all — that is the whole point of the
 * split (mirrors lib/flame-skip.ts). A second, smaller suite exercises the
 * DB-touching wrapper (recordEdgeDecayClose/isEdgeDecayPaused) against a tiny
 * in-memory fake of edge_decay_state/edge_decay_alarm_log, to pin the actual
 * wiring (persistence across calls, notify, and "off = zero DB access").
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const dbCalls: string[] = []
const pushCalls: Array<{ title: string; body: string; severity: string }> = []

// In-memory fake of edge_decay_state / edge_decay_alarm_log, keyed exactly the
// way edge-decay.ts's real SQL addresses them — good enough to exercise
// persistence across multiple recordEdgeDecayClose calls without a real DB.
let stateStore: Record<string, any> = {}
let logRows: Array<{ strategy: string; event_type: string }> = []

const mockQuery = vi.fn(async (sql: string, params: any[] = []) => {
  dbCalls.push(sql)
  if (sql.includes('FROM edge_decay_state')) {
    const strategy = params[0]
    return stateStore[strategy] ? [stateStore[strategy]] : []
  }
  if (sql.includes('INSERT INTO edge_decay_state')) {
    const [strategy, mu0, k, h] = params
    if (!stateStore[strategy]) {
      stateStore[strategy] = { strategy, status: 'active', cusum_value: 0, mu0, k, h, shadow_count: 0, shadow_sum: 0 }
    }
    return []
  }
  if (sql.includes('UPDATE edge_decay_state')) {
    const [strategy, status, cusumValue, mu0, k, h, shadowCount, shadowSum] = params
    stateStore[strategy] = { strategy, status, cusum_value: cusumValue, mu0, k, h, shadow_count: shadowCount, shadow_sum: shadowSum }
    return []
  }
  if (sql.includes('INSERT INTO edge_decay_alarm_log')) {
    logRows.push({ strategy: params[0], event_type: params[1] })
    return []
  }
  if (sql.includes('calldiag_positions')) return [] // rolling baseline: no history -> frozen anchor fallback
  return []
})
const mockDbExecute = vi.fn(async (sql: string) => { dbCalls.push(sql); return 0 })

vi.mock('../db', () => ({
  query: (...args: any[]) => mockQuery(...(args as [string, any[]?])),
  dbExecute: (...args: any[]) => mockDbExecute(...(args as [string])),
}))

vi.mock('../sms', () => ({
  sendOpsPush: vi.fn(async (args: { title: string; body: string; severity: string }) => {
    pushCalls.push(args)
    return { sent: true }
  }),
}))

import {
  cusumStep,
  isAlarmed,
  applyClosedTrade,
  initialEdgeDecayState,
  STRATEGY_PARAMS,
  getEdgeDecayMode,
  recordEdgeDecayClose,
  isEdgeDecayPaused,
  type EdgeDecayState,
} from '../edge-decay'

beforeEach(() => {
  dbCalls.length = 0
  pushCalls.length = 0
  stateStore = {}
  logRows = []
})
afterEach(() => {
  delete process.env.EDGE_DECAY_MODE
})

/* ------------------------------------------------------------------ */
/*  Mode gating                                                        */
/* ------------------------------------------------------------------ */

describe('getEdgeDecayMode', () => {
  it('unset -> off', () => {
    delete process.env.EDGE_DECAY_MODE
    expect(getEdgeDecayMode()).toBe('off')
  })
  it('garbage value -> off (fails safe)', () => {
    process.env.EDGE_DECAY_MODE = 'yolo'
    expect(getEdgeDecayMode()).toBe('off')
  })
  it('notify / enforce pass through, case-insensitively', () => {
    process.env.EDGE_DECAY_MODE = 'NOTIFY'
    expect(getEdgeDecayMode()).toBe('notify')
    process.env.EDGE_DECAY_MODE = 'Enforce'
    expect(getEdgeDecayMode()).toBe('enforce')
  })
})

/* ------------------------------------------------------------------ */
/*  Pure CUSUM math — hand-computed series                             */
/* ------------------------------------------------------------------ */

describe('cusumStep — hand-computed series', () => {
  // mu0=10, k=5. Series: 10 (on-target), -20 (bad trade), 10, 10.
  // S0 = 0
  // S1 = min(0, 0 + (10-10) + 5)  = min(0, 5)   = 0
  // S2 = min(0, 0 + (-20-10) + 5) = min(0, -25) = -25
  // S3 = min(0, -25 + (10-10) + 5) = min(0, -20) = -20
  // S4 = min(0, -20 + (10-10) + 5) = min(0, -15) = -15
  it('matches a hand-computed 4-trade series exactly', () => {
    const mu0 = 10
    const k = 5
    let s = 0
    s = cusumStep(s, 10, mu0, k); expect(s).toBeCloseTo(0, 6)
    s = cusumStep(s, -20, mu0, k); expect(s).toBeCloseTo(-25, 6)
    s = cusumStep(s, 10, mu0, k); expect(s).toBeCloseTo(-20, 6)
    s = cusumStep(s, 10, mu0, k); expect(s).toBeCloseTo(-15, 6)
  })

  it('a single trade exactly at mu0-k drives S down by exactly k... no: by (pnl-mu0)+k', () => {
    // pnl = mu0 -> delta = 0 + k = k (positive) -> clamped to 0 from S=0.
    expect(cusumStep(0, 10, 10, 5)).toBe(0)
    // pnl = mu0 - 2k -> delta = -2k + k = -k -> S drops by k.
    expect(cusumStep(0, 10 - 2 * 5, 10, 5)).toBe(-5)
  })

  it('never rises above 0 — Page\'s CUSUM is one-sided (decay direction only)', () => {
    // A huge positive trade cannot push S positive, only reset the floor to 0.
    expect(cusumStep(-100, 10_000, 10, 5)).toBe(0)
  })
})

describe('isAlarmed', () => {
  it('alarms exactly AT the threshold (S <= -h), not only past it', () => {
    expect(isAlarmed(-417.88, 417.88)).toBe(true)
    expect(isAlarmed(-417.87, 417.88)).toBe(false)
    expect(isAlarmed(0, 417.88)).toBe(false)
  })
})

describe('no alarm on an intact-edge sequence', () => {
  it('flint/ebb (k>0): feeding pnl == mu0 forever holds S at exactly 0, never alarms', () => {
    for (const strategy of ['flint', 'ebb'] as const) {
      const { mu0, k, h } = STRATEGY_PARAMS[strategy]
      expect(k).toBeGreaterThan(0)
      let s = 0
      for (let i = 0; i < 5000; i++) s = cusumStep(s, mu0, mu0, k)
      expect(s).toBe(0)
      expect(isAlarmed(s, h)).toBe(false)
    }
  })

  // CallDiag's frozen mu0 is itself slightly negative (RESULT file's "degenerate
  // baseline" finding), so k=mu0/2 is negative too — a deterministic pnl===mu0
  // feed drifts S down by exactly |k| per trade with no positive noise to ever
  // clamp it back to 0 (that only happens with real trade-to-trade variance,
  // per the RESULT file's bootstrap ARL of 491.5 trades). This is the documented
  // reason CallDiag re-baselines live off a rolling window rather than trusting
  // this frozen anchor — the invariant this asserts is only "does not alarm
  // WELL WITHIN its own calibrated ARL," not "never alarms."
  it('calldiag (k<0): a deterministic pnl==mu0 feed drifts but does not alarm within its calibrated ARL', () => {
    const { mu0, k, h } = STRATEGY_PARAMS.calldiag
    expect(k).toBeLessThan(0)
    let s = 0
    for (let i = 0; i < 491; i++) s = cusumStep(s, mu0, mu0, k) // RESULT file's calibrated ARL for CallDiag CUSUM
    expect(isAlarmed(s, h)).toBe(false)
  })

  it('feeding pnl consistently ABOVE mu0 never alarms', () => {
    const { mu0, k, h } = STRATEGY_PARAMS.flint
    let s = 0
    for (let i = 0; i < 1000; i++) s = cusumStep(s, mu0 + 5, mu0, k)
    expect(isAlarmed(s, h)).toBe(false)
  })

  it('feeding pnl calibrated to alarm at ~0.5/yr does eventually alarm on a sustained break to 0', () => {
    // Sanity check that the calibrated FLINT threshold is reachable at all —
    // a sustained collapse to mean 0 (RESULT file's detection-speed scenario)
    // must alarm well within the 262.7-trade calibrated ARL horizon.
    const { mu0, k, h } = STRATEGY_PARAMS.flint
    let s = 0
    let alarmedAtTrade = -1
    for (let i = 1; i <= 300; i++) {
      s = cusumStep(s, 0, mu0, k) // mean collapses to 0, matches RESULT file's severity (b)
      if (isAlarmed(s, h)) { alarmedAtTrade = i; break }
    }
    expect(alarmedAtTrade).toBeGreaterThan(0)
    expect(alarmedAtTrade).toBeLessThan(150) // well inside the calibrated 262.7-trade ARL
  })
})

/* ------------------------------------------------------------------ */
/*  Pure pause/shadow/resume state machine                             */
/* ------------------------------------------------------------------ */

function freshState(strategy: 'flint' | 'calldiag' | 'ebb'): EdgeDecayState {
  return initialEdgeDecayState(strategy)
}

describe('applyClosedTrade — pause/shadow/resume state machine', () => {
  it('a pausable strategy under enforce: alarm -> paused, shadow block progresses, 10-trade avg>0 -> resumed', () => {
    let state = freshState('flint')
    const opts = { mode: 'enforce' as const, pausable: true }

    // Force an alarm: one huge loss trade.
    let res = applyClosedTrade(state, -10_000, opts)
    state = res.state
    expect(res.action.type).toBe('alarm')
    expect(res.action.type === 'alarm' && res.action.enforced).toBe(true)
    expect(state.status).toBe('paused')
    expect(state.cusumValue).toBe(0)

    // Feed 9 shadow trades averaging positive but not yet a full block of 10.
    for (let i = 0; i < 9; i++) {
      res = applyClosedTrade(state, 5, opts)
      state = res.state
      expect(['paused', 'shadow']).toContain(state.status)
      expect(res.action.type).toBe('shadow_progress')
      void i
    }
    expect(state.shadowCount).toBe(9)

    // 10th shadow trade completes the block; average is positive -> resume.
    res = applyClosedTrade(state, 5, opts)
    state = res.state
    expect(res.action.type).toBe('resumed')
    expect(state.status).toBe('active')
    expect(state.shadowCount).toBe(0)
    expect(state.shadowSum).toBe(0)
    expect(state.cusumValue).toBe(0)
  })

  it('a failed 10-trade shadow block (avg <= 0) stays blocked and starts a fresh block', () => {
    let state = freshState('flint')
    const opts = { mode: 'enforce' as const, pausable: true }
    state = applyClosedTrade(state, -10_000, opts).state
    expect(state.status).toBe('paused')

    // 10 trades averaging negative.
    for (let i = 0; i < 9; i++) state = applyClosedTrade(state, -5, opts).state
    const res = applyClosedTrade(state, -5, opts)
    expect(res.action.type).toBe('shadow_block_failed')
    expect(res.state.status).toBe('shadow') // still blocked
    expect(res.state.shadowCount).toBe(0) // fresh block started
  })

  it('mode=notify never pauses, even for a pausable strategy — alarms and resets S only', () => {
    let state = freshState('flint')
    const opts = { mode: 'notify' as const, pausable: true }
    const res = applyClosedTrade(state, -10_000, opts)
    expect(res.action.type).toBe('alarm')
    expect(res.action.type === 'alarm' && res.action.enforced).toBe(false)
    expect(res.state.status).toBe('active') // never paused under notify
    expect(res.state.cusumValue).toBe(0)
  })

  it('EBB (pausable=false) never pauses even under enforce — notify-only, S resets', () => {
    let state = freshState('ebb')
    const opts = { mode: 'enforce' as const, pausable: false } // caller passes STRATEGY_PARAMS.ebb.pausable
    const res = applyClosedTrade(state, -10_000, opts)
    expect(res.action.type).toBe('alarm')
    expect(res.action.type === 'alarm' && res.action.enforced).toBe(false)
    expect(res.state.status).toBe('active')
    expect(STRATEGY_PARAMS.ebb.pausable).toBe(false)
  })

  it('an intact-edge trade while active just accumulates progress, no alarm', () => {
    const state = freshState('flint')
    const res = applyClosedTrade(state, state.mu0, { mode: 'enforce', pausable: true })
    expect(res.action.type).toBe('progress')
    expect(res.state.status).toBe('active')
  })
})

/* ------------------------------------------------------------------ */
/*  DB-touching wrapper — persistence, notify, "off = zero DB access"  */
/* ------------------------------------------------------------------ */

describe('recordEdgeDecayClose / isEdgeDecayPaused — wiring', () => {
  it('EDGE_DECAY_MODE unset: recordEdgeDecayClose and isEdgeDecayPaused touch NO database and never call sendOpsPush', async () => {
    delete process.env.EDGE_DECAY_MODE
    const action = await recordEdgeDecayClose('flint', -10_000)
    expect(action).toEqual({ type: 'none' })
    expect(await isEdgeDecayPaused('flint')).toBe(false)
    expect(dbCalls).toEqual([])
    expect(pushCalls).toEqual([])
  })

  it('mode=enforce: a real alarm persists paused status and calls sendOpsPush with the [edge-decay] ALARM tag', async () => {
    process.env.EDGE_DECAY_MODE = 'enforce'
    await recordEdgeDecayClose('flint', -10_000)
    expect(await isEdgeDecayPaused('flint')).toBe(true)
    expect(pushCalls.length).toBe(1)
    expect(pushCalls[0].title).toContain('[edge-decay] ALARM FLINT')
    expect(pushCalls[0].severity).toBe('critical')
  })

  it('mode=enforce: EBB alarms but isEdgeDecayPaused stays false — EBB never pauses', async () => {
    process.env.EDGE_DECAY_MODE = 'enforce'
    await recordEdgeDecayClose('ebb', -10_000)
    expect(await isEdgeDecayPaused('ebb')).toBe(false)
    expect(pushCalls.length).toBe(1) // still notified
    expect(pushCalls[0].title).toContain('[edge-decay] ALARM EBB')
  })

  it('mode=notify: FLINT alarms but is never paused', async () => {
    process.env.EDGE_DECAY_MODE = 'notify'
    await recordEdgeDecayClose('flint', -10_000)
    expect(await isEdgeDecayPaused('flint')).toBe(false)
    expect(pushCalls.length).toBe(1)
  })

  it('resume: a full 10-trade shadow block averaging >0 flips isEdgeDecayPaused back to false and notifies resume', async () => {
    process.env.EDGE_DECAY_MODE = 'enforce'
    await recordEdgeDecayClose('flint', -10_000) // alarm -> paused
    expect(await isEdgeDecayPaused('flint')).toBe(true)

    for (let i = 0; i < 10; i++) await recordEdgeDecayClose('flint', 5)

    expect(await isEdgeDecayPaused('flint')).toBe(false)
    const resumeLog = logRows.filter((r) => r.strategy === 'flint' && r.event_type === 'resume')
    expect(resumeLog.length).toBe(1)
    const resumePush = pushCalls.find((p) => p.title.includes('RESUME FLINT'))
    expect(resumePush).toBeDefined()
  })
})
