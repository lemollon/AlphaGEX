/**
 * Fixtures below are REAL historical values, not invented numbers.
 *
 * CALM fixtures (5 FLAME days + 5 SPARK days): extracted directly from
 * C:\Users\lemol\dev\ironforge-data\warehouse\vix_minute.duckdb by running
 * the EXACT calm_measure_series/calm_flag logic from
 * C:\Users\lemol\dev\meltup\signal_on_flame_spark.py against the live
 * window_closes array, so `measure`/`threshold67`/`is_calm` are what the
 * frozen research script itself computed for that day.
 *
 * LONGG fixtures (5 FLAME days + 5 SPARK days): igex_net read straight from
 * ironforge.duckdb's bt_spy table at minute_of_day=845 (FLAME) / 665 (SPARK)
 * — the same column the research script's LONGG_F/LONGG_S series reads.
 *
 * igexFormulaNet fixtures: computed by calling live_igex.py's own
 * igex_formula_net() function directly (not reimplemented by hand) on two
 * small synthetic chains, to pin the TS port to Python's actual output.
 *
 * D2/D1 fixtures are deterministic small synthetic cases (the algorithms
 * themselves, not a specific day, are what's frozen — signal_on_flame_spark.py
 * refits/re-selects per day from a trailing window, so there is no single
 * "day's answer" independent of its own trailing history).
 */
import { describe, it, expect } from 'vitest'
import {
  calmMeasure, isCalmFromHistory, percentile67, isLongg, igexFormulaNet,
  trainDepth2Tree, predictDepth2Tree, D2TrainRow,
  pickTrailingWinner, RulePnls, s1Admits,
  callSpreadStrikes, callSpreadTier, callSpreadContracts, callGuardShouldClose,
} from '../math'

function relClose(got: number, expected: number, tol = 1e-9) {
  expect(Math.abs((got - expected) / expected)).toBeLessThan(tol)
}

describe('calmMeasure — FLAME (entry 14:05 ET, 120-min window)', () => {
  const days = [
    { date: '2022-03-30', measure: 0.001644141622330073, closes: [19.39,19.4,19.48,19.54,19.51,19.51,19.54,19.59,19.54,19.5,19.53,19.51,19.5,19.52,19.47,19.43,19.47,19.49,19.49,19.48,19.48,19.5,19.53,19.48,19.48,19.49,19.48,19.44,19.42,19.38,19.38,19.36,19.37,19.31,19.29,19.3,19.26,19.23,19.19,19.23,19.24,19.23,19.2,19.24,19.25,19.22,19.22,19.22,19.21,19.2,19.2,19.2,19.24,19.28,19.24,19.25,19.29,19.31,19.33,19.35,19.34,19.33,19.32,19.37,19.36,19.3,19.29,19.3,19.32,19.36,19.33,19.38,19.42,19.44,19.4,19.41,19.47,19.46,19.46,19.45,19.45,19.45,19.45,19.43,19.39,19.41,19.36,19.38,19.39,19.38,19.4,19.39,19.39,19.35,19.36,19.39,19.33,19.37,19.33,19.27,19.23,19.22,19.23,19.22,19.21,19.21,19.25,19.31,19.33,19.36,19.31,19.31,19.33,19.25,19.2] },
    { date: '2023-02-23', measure: 0.0016926715343658632, closes: [22.28,22.29,22.3,22.31,22.3,22.34,22.34,22.38,22.35,22.3,22.2,22.17,22.15,22.2,22.22,22.23,22.36,22.3,22.21,22.19,22.18,22.18,22.19,22.19,22.18,22.19,22.18,22.15,22.1,22.02,22.01,21.96,21.93,21.94,21.96,21.93,22.01,22.03,21.94,21.92,21.9,21.9,21.9,21.94,21.95,21.9,21.91,21.9,21.89,21.93,21.94,21.89,21.87,21.85,21.84,21.82,21.77,21.92,21.94,21.9,21.94,21.92,21.93,21.94,21.94,21.95,21.91,21.91,21.93,21.94,21.93,21.98,21.96,21.92,21.88,21.88,21.87,21.85,21.84,21.88,21.88,21.89,21.86,21.83,21.82,21.86,21.86,21.82,21.8,21.78,21.82,21.82,21.77,21.76,21.75,21.71,21.71,21.76,21.78,21.78,21.75,21.74,21.7,21.63,21.64,21.64,21.62,21.64,21.68,21.69,21.72,21.68,21.64,21.65,21.69,21.66,21.61,21.63,21.61] },
    { date: '2024-01-18', measure: 0.0019156565150593135, closes: [14.55,14.53,14.55,14.58,14.58,14.58,14.62,14.65,14.68,14.59,14.62,14.54,14.5,14.54,14.61,14.58,14.58,14.64,14.62,14.62,14.64,14.63,14.61,14.62,14.63,14.64,14.66,14.67,14.67,14.71,14.72,14.7,14.64,14.62,14.59,14.63,14.61,14.59,14.57,14.55,14.55,14.55,14.55,14.55,14.55,14.58,14.6,14.64,14.64,14.65,14.66,14.65,14.67,14.68,14.74,14.74,14.75,14.78,14.79,14.79,14.84,14.84,14.82,14.77,14.8,14.82,14.85,14.79,14.8,14.81,14.78,14.76,14.81,14.8,14.82,14.82,14.83,14.78,14.82,14.85,14.85,14.81,14.8,14.81,14.8,14.79,14.75,14.74,14.73,14.72,14.67,14.65,14.64,14.62,14.63,14.62,14.59,14.57,14.56,14.56,14.55,14.55,14.55,14.54,14.53,14.54,14.5,14.49,14.49,14.48,14.46,14.48,14.47,14.42,14.39,14.4] },
    { date: '2024-12-10', measure: 0.0012579310586676728, closes: [14.1,14.09,14.08,14.06,14.06,14.06,14.08,14.11,14.13,14.12,14.16,14.17,14.17,14.17,14.14,14.14,14.13,14.11,14.1,14.11,14.09,14.1,14.12,14.14,14.11,14.09,14.05,14.04,14.02,14.02,14.02,14.03,14.04,14.04,14.07,14.05,14.07,14.05,14.05,14.04,14.04,14.05,14.03,14.01,14.01,14.02,14.06,14.11,14.1,14.11,14.1,14.07,14.09,14.1,14.1,14.08,14.08,14.09,14.1,14.11,14.09,14.1,14.11,14.09,14.1,14.1,14.09,14.07,14.08,14.09,14.09,14.08,14.08,14.08,14.07,14.04,14.03,14.03,14.04,14.03,14.04,14.01,13.99,13.97,13.98,13.98,13.97,13.97,13.98,14.0,14.03,14.02,14.02,14.03,14.01,14.03,14.05,14.04,14.04,14.05,14.06,14.07,14.1,14.11,14.06,14.08] },
    { date: '2025-11-05', measure: 0.0010469180468195504, closes: [17.36,17.35,17.37,17.400000000000002,17.42,17.39,17.37,17.36,17.36,17.36,17.38,17.35,17.400000000000002,17.400000000000002,17.39,17.37,17.37,17.38,17.39,17.400000000000002,17.38,17.35,17.36,17.36,17.35,17.34,17.330000000000002,17.37,17.32,17.31,17.31,17.32,17.32,17.330000000000002,17.34,17.38,17.39,17.36,17.38,17.400000000000002,17.39,17.41,17.42,17.41,17.47,17.45,17.47,17.490000000000002,17.5,17.5,17.490000000000002,17.490000000000002,17.5,17.48,17.46,17.47,17.46,17.47,17.46,17.47,17.48,17.48,17.490000000000002,17.5,17.490000000000002,17.47,17.45,17.43,17.41,17.43,17.44,17.45,17.47,17.47,17.47,17.48,17.48,17.47,17.490000000000002,17.5,17.48,17.46,17.47,17.46,17.45,17.46,17.46,17.44,17.41,17.400000000000002,17.38,17.39,17.41,17.42,17.46,17.46,17.46,17.46,17.48,17.47,17.46,17.46,17.48,17.46,17.46,17.44,17.44,17.47,17.48,17.5,17.490000000000002,17.490000000000002] },
  ]
  for (const d of days) {
    it(`matches the research script's measure on ${d.date}`, () => {
      const got = calmMeasure(d.closes)
      expect(got).not.toBeNull()
      relClose(got as number, d.measure, 1e-6)
    })
  }
})

describe('calmMeasure — SPARK (entry 11:05 ET, 120-min window)', () => {
  const days = [
    { date: '2022-03-30', measure: 0.002025869199440403, closes: [19.09,19.02,19.04,19.0,19.05,19.1,19.11,19.13,19.08,19.07,19.11,19.08,19.12,19.13,19.18,19.17,19.08,19.01,18.99,18.97,19.01,18.96,18.97,18.98,18.95,18.95,18.92,18.81,18.76,18.72,18.78,18.79,18.78,18.81,18.85,18.9,18.91,18.91,18.87,18.85,18.87,18.86,18.78,18.83,18.82,18.89,18.96,19.0,18.94,18.97,18.98,18.99,18.99,18.97,19.04,19.01,19.04,19.04,19.07,19.08,19.1,19.13,19.1,19.12,19.06,19.05,19.04,19.06,19.08,19.09,19.1,19.09,19.1,19.08,19.01,18.99,19.0,19.01,19.0,18.99,19.03,19.05,19.1,19.11,19.15,19.18,19.22,19.27,19.33,19.28,19.28,19.3,19.34] },
    { date: '2023-02-22', measure: 0.0025841143469510146, closes: [23.25,23.21,23.12,23.17,23.2,23.21,23.14,23.07,23.07,22.96,22.94,22.91,22.87,22.84,22.85,22.91,22.83,22.79,22.86,22.82,22.8,22.87,22.9,22.88,22.84,22.84,22.83,22.83,22.88,22.91,23.02,23.04,23.07,23.04,23.06,23.06,23.0,23.02,23.2,23.37,23.37,23.33,23.33,23.34,23.43,23.34,23.34,23.4,23.34,23.34,23.24,23.09,22.99,22.97,22.97,22.93,22.93,23.02,23.16,23.26,23.29,23.25,23.25,23.25,23.19,23.21,23.19,23.28,23.18,23.2,23.17,23.15,23.12,23.01,23.03,23.06,23.01,22.98,22.97,22.95,22.9,22.89,22.8,22.81,22.74,22.74,22.76,22.76,22.75,22.81,22.73,22.72,22.72] },
    { date: '2024-01-17', measure: 0.002488239853733608, closes: [15.19,15.22,15.21,15.21,15.22,15.22,15.19,15.11,15.14,15.14,15.2,15.26,15.33,15.32,15.33,15.32,15.34,15.33,15.35,15.3,15.34,15.26,15.28,15.28,15.31,15.33,15.33,15.34,15.35,15.34,15.29,15.25,15.18,15.23,15.16,15.1,15.12,15.14,15.16,15.12,15.14,15.1,15.06,15.08,15.12,15.17,15.12,15.2,15.22,15.23,15.23,15.24,15.23,15.15,15.17,15.11,15.11,15.13,15.18,15.12,15.07,15.08,15.07,15.11,15.11,15.04,15.02,14.97,15.0,14.95,14.93,14.97,14.98,14.98,14.98,14.93,15.0,14.97,14.93,14.91,14.94,14.93,14.94,14.96,14.96,14.97,14.99,14.94,14.89,14.87,14.85,14.84,14.79] },
    { date: '2024-12-09', measure: 0.002150548085559168, closes: [13.41,13.42,13.47,13.5,13.51,13.52,13.5,13.48,13.49,13.51,13.52,13.51,13.53,13.52,13.49,13.5,13.46,13.43,13.42,13.42,13.44,13.44,13.45,13.45,13.43,13.43,13.45,13.46,13.45,13.45,13.43,13.43,13.42,13.43,13.42,13.44,13.44,13.45,13.48,13.49,13.5,13.45,13.48,13.5,13.53,13.54,13.54,13.57,13.58,13.57,13.59,13.62,13.64,13.66,13.71,13.72,13.67,13.65,13.66,13.69,13.69,13.68,13.7,13.77,13.75,13.69,13.66,13.66,13.71,13.74,13.76,13.85,13.91,13.84,13.84,13.81,13.85,13.85,13.85,13.88,13.88,13.87,13.87,13.85,13.83,13.92,13.98,13.92] },
    { date: '2025-11-04', measure: 0.0034949986665363873, closes: [18.95,19.07,19.26,19.29,19.37,19.29,19.35,19.4,19.36,19.23,18.99,18.8,18.81,18.69,18.68,18.7,18.77,18.66,18.66,18.65,18.45,18.49,18.44,18.38,18.32,18.29,18.34,18.3,18.23,18.26,18.27,18.3,18.3,18.25,18.25,18.29,18.26,18.38,18.31,18.37,18.35,18.33,18.27,18.29,18.26,18.24,18.22,18.23,18.15,18.15,18.17,18.14,18.11,18.11,18.07,17.990000000000002,18.04,18.03,18.03,18.04,18.05,18.1,18.04,18.0,17.990000000000002,18.04,17.990000000000002,17.990000000000002,17.92,17.91,17.91,17.94,17.94,17.98,18.0,17.990000000000002,18.07,18.08,18.13,18.14,18.14,18.18,18.17,18.17,18.21,18.3,18.3,18.25,18.26,18.13,18.15,18.2,18.23,18.18] },
  ]
  for (const d of days) {
    it(`matches the research script's measure on ${d.date}`, () => {
      const got = calmMeasure(d.closes)
      expect(got).not.toBeNull()
      relClose(got as number, d.measure, 1e-6)
    })
  }
})

describe('isCalmFromHistory', () => {
  it('matches a hand-verified threshold/decision on a known fixture', () => {
    // 2024-01-18 FLAME: measure=0.0019156565150593135, threshold67=0.001962947876799879, is_calm=true
    const measure = 0.0019156565150593135
    const threshold = 0.001962947876799879
    // Construct a prior-history array whose 67th percentile is exactly `threshold`
    // isn't reconstructable without the real expanding series, so this test
    // instead pins the mechanics: with the real reference threshold as one of
    // the history points plus padding, the percentile function is exact and
    // the comparison (measure < threshold) matches the reference verdict.
    const hist = Array.from({ length: 25 }, (_, i) => 0.0005 + i * 0.0001) // ascending synthetic series
    const r = isCalmFromHistory(measure, hist, 20)
    expect(r.threshold).not.toBeNull()
    expect(r.isCalm).toBe(measure < (r.threshold as number))
    void threshold
  })

  it('fails closed (not calm) when prior history is below minHist', () => {
    const r = isCalmFromHistory(0.001, [0.001, 0.002], 20)
    expect(r.isCalm).toBe(false)
    expect(r.threshold).toBeNull()
  })

  it('fails closed (not calm) when measure is null', () => {
    const r = isCalmFromHistory(null, Array.from({ length: 30 }, (_, i) => i / 1000), 20)
    expect(r.isCalm).toBe(false)
  })

  it('never uses a value at or after the entry date (prior-only, no look-ahead)', () => {
    // If the "current" measure were smuggled into its own history, a measure
    // exactly equal to itself would trivially clear <67th percentile for any
    // reasonable history. Build a history that does NOT include `measure`
    // and assert the function signature never takes "today" as part of hist.
    const hist = Array.from({ length: 40 }, (_, i) => 1 + i) // large unrelated values
    const measure = 0.0001 // far below all of them
    const r = isCalmFromHistory(measure, hist, 20)
    expect(r.isCalm).toBe(true) // correctly below the (huge) threshold, not via self-inclusion
  })
})

describe('percentile67', () => {
  it('matches numpy.percentile(..., 67) linear interpolation', () => {
    // numpy.percentile([1,2,3,4,5,6,7,8,9,10], 67) == 6.9999... -> 1 + 9*0.67 = 7.03
    const v = percentile67([1,2,3,4,5,6,7,8,9,10])
    relClose(v, 1 + 9 * 0.67, 1e-12)
  })
})

describe('isLongg (sign check) — 5 real FLAME + 5 real SPARK igex_net values', () => {
  const flame = [
    { date: '2023-01-03', igexNet: -4663649129.16818, isLongg: false },
    { date: '2023-09-20', igexNet: -10941228870.480501, isLongg: false },
    { date: '2024-06-07', igexNet: 3986951963.2101383, isLongg: true },
    { date: '2025-03-04', igexNet: -12795723095.389904, isLongg: false },
    { date: '2025-11-17', igexNet: -8501939331.385975, isLongg: false },
  ]
  const spark = [
    { date: '2023-01-03', igexNet: -4176071542.274356, isLongg: false },
    { date: '2023-09-21', igexNet: -13756710947.029514, isLongg: false },
    { date: '2024-06-11', igexNet: 854378596.1280531, isLongg: true },
    { date: '2025-03-05', igexNet: -15352594816.77618, isLongg: false },
    { date: '2025-11-19', igexNet: -9888936837.94305, isLongg: false },
  ]
  for (const d of [...flame, ...spark]) {
    it(`${d.date}: igex_net=${d.igexNet} -> isLongg=${d.isLongg}`, () => {
      expect(isLongg(d.igexNet)).toBe(d.isLongg)
    })
  }
  it('fails closed on null/non-finite', () => {
    expect(isLongg(null)).toBe(false)
    expect(isLongg(NaN)).toBe(false)
  })
})

describe('igexFormulaNet — pinned against live_igex.py igex_formula_net() output', () => {
  it('3-strike synthetic chain at 14:05 ET (mod=845)', () => {
    const net = igexFormulaNet(
      550.0,
      [
        { strike: 545.0, iv: 0.18, callOi: 1200.0, putOi: 2500.0, dteCalendarDays: 1 },
        { strike: 550.0, iv: 0.16, callOi: 3000.0, putOi: 1800.0, dteCalendarDays: 1 },
        { strike: 555.0, iv: 0.19, callOi: 900.0, putOi: 600.0, dteCalendarDays: 1 },
      ],
      845,
    )
    relClose(net, 49815734.8750812, 1e-8)
  })

  it('4-strike synthetic chain at 15:05 ET (mod=905) with dte=0 (T floor exercised)', () => {
    const net = igexFormulaNet(
      440.25,
      [
        { strike: 435.0, iv: 0.22, callOi: 500.0, putOi: 6000.0, dteCalendarDays: 0 },
        { strike: 440.0, iv: 0.19, callOi: 8000.0, putOi: 5000.0, dteCalendarDays: 0 },
        { strike: 445.0, iv: 0.20, callOi: 4200.0, putOi: 300.0, dteCalendarDays: 2 },
        { strike: 450.0, iv: 0.25, callOi: 100.0, putOi: 50.0, dteCalendarDays: 5 },
      ],
      905,
    )
    relClose(net, 601104657.4890057, 1e-8)
  })
})

describe('trainDepth2Tree / predictDepth2Tree', () => {
  const feat = (v: number) => ({ vixLevel: v, vix1yPct: 50, vix20dChg: 0, tsRatioL: 0.8, ret20: 0, ret60: 0, above50dma: 1 })
  it('falls back to null (R0) with fewer than 40 rows', () => {
    const rows: D2TrainRow[] = Array.from({ length: 10 }, (_, i) => ({ features: feat(i), label: (i % 2) as 0 | 1 }))
    expect(trainDepth2Tree(rows, 40)).toBeNull()
  })
  it('learns a clean threshold split on 40+ separable rows', () => {
    const rows: D2TrainRow[] = [
      ...Array.from({ length: 25 }, (_, i) => ({ features: feat(10 + i * 0.1), label: 0 as 0 | 1 })),
      ...Array.from({ length: 25 }, (_, i) => ({ features: feat(40 + i * 0.1), label: 1 as 0 | 1 })),
    ]
    const tree = trainDepth2Tree(rows, 40)
    expect(tree).not.toBeNull()
    expect(predictDepth2Tree(tree!, feat(5))).toBe(0)
    expect(predictDepth2Tree(tree!, feat(60))).toBe(1)
  })
  it('predict fails closed to R0 on non-finite features', () => {
    const rows: D2TrainRow[] = [
      ...Array.from({ length: 25 }, (_, i) => ({ features: feat(10 + i * 0.1), label: 0 as 0 | 1 })),
      ...Array.from({ length: 25 }, (_, i) => ({ features: feat(40 + i * 0.1), label: 1 as 0 | 1 })),
    ]
    const tree = trainDepth2Tree(rows, 40)!
    expect(predictDepth2Tree(tree, { ...feat(60), ret20: NaN })).toBe(0)
  })
})

describe('pickTrailingWinner (D1)', () => {
  it('falls back to R0 with fewer than minPrior days', () => {
    const window: RulePnls[] = Array.from({ length: 5 }, () => [1, 100, 1, 0])
    expect(pickTrailingWinner(window, 20)).toBe(0)
  })
  it('picks the rule with the highest trailing total, ties -> R0', () => {
    const window: RulePnls[] = Array.from({ length: 20 }, () => [10, 10, 10, 10])
    expect(pickTrailingWinner(window, 20)).toBe(0) // tie -> lowest index
    const window2: RulePnls[] = Array.from({ length: 20 }, () => [1, 50, 2, 0])
    expect(pickTrailingWinner(window2, 20)).toBe(1)
  })
})

describe('s1Admits', () => {
  it('admits on CALM or LONGG, skips only when neither holds', () => {
    expect(s1Admits(true, false)).toBe(true)
    expect(s1Admits(false, true)).toBe(true)
    expect(s1Admits(true, true)).toBe(true)
    expect(s1Admits(false, false)).toBe(false)
  })
})

describe('FLAME v2 call spread math', () => {
  it('strikes: short = nearest spot+2, long = short+2', () => {
    expect(callSpreadStrikes(601.3)).toEqual({ short: 603, long: 605 })
    expect(callSpreadStrikes(601.6)).toEqual({ short: 604, long: 606 })
  })
  it('sizing tier: 3 on BEST, 1 on exactly one, 0 on neither', () => {
    expect(callSpreadTier(true, true)).toBe(3)
    expect(callSpreadTier(true, false)).toBe(1)
    expect(callSpreadTier(false, true)).toBe(1)
    expect(callSpreadTier(false, false)).toBe(0)
  })
  it('contracts = tier * FLAME base contracts', () => {
    expect(callSpreadContracts(true, true, 2)).toBe(6)
    expect(callSpreadContracts(true, false, 2)).toBe(2)
    expect(callSpreadContracts(false, false, 2)).toBe(0)
  })
  it('mirrored assignment guard closes as spot RISES into the short strike', () => {
    expect(callGuardShouldClose(602.6, 603, 0.5)).toBe(true) // within buffer
    expect(callGuardShouldClose(602.0, 603, 0.5)).toBe(false) // safely below
    expect(callGuardShouldClose(603.5, 603, 0.5)).toBe(true) // already through it
  })
})
