import { describe, it, expect } from 'vitest'
import {
  stanceLabel,
  regimeLabel,
  fmtPct,
  windowText,
  dteText,
  termStructurePoints,
  isBackwardation,
  timingAreaData,
  signalDisplayName,
  hitRateText,
  evidenceRows,
  resultMark,
  liveHeadline,
  formatVolRegime,
  proximityPct,
  directionClass,
  actionAccentClass,
  sortedSignalEntries,
  triggerGroups,
  seriesForChart,
  regimeBannerText,
  type AdvisorTiming,
  type AdvisorReport,
  type AdvisorSignal,
} from './volatility'

/** Minimal signal factory for the per-signal helpers. */
function mkSignal(over: Partial<AdvisorSignal> = {}): AdvisorSignal {
  return {
    active: false,
    value: 0,
    confidence: 'high',
    blurb: '',
    hit_rate: null,
    ...over,
  }
}

describe('stanceLabel', () => {
  it('maps known stances', () => {
    expect(stanceLabel('buy_the_bounce')).toBe('Buy the bounce')
    expect(stanceLabel('lean_calls')).toBe('Lean calls')
    expect(stanceLabel('lean_puts')).toBe('Lean puts')
    expect(stanceLabel('neutral')).toBe('Neutral')
  })

  it('falls back to em-dash on unknown/missing', () => {
    expect(stanceLabel(undefined)).toBe('—')
    expect(stanceLabel(null)).toBe('—')
    expect(stanceLabel('something_else')).toBe('—')
    expect(stanceLabel('')).toBe('—')
  })
})

describe('regimeLabel', () => {
  it('maps known regime keys', () => {
    expect(regimeLabel('backwardation_stressed')).toBe('Backwardation (stressed)')
    expect(regimeLabel('exhaustion')).toBe('Exhaustion')
    expect(regimeLabel('floor_complacent')).toBe('Floor (complacent)')
    expect(regimeLabel('contango_flattening')).toBe('Contango (flattening)')
    expect(regimeLabel('contango_calm')).toBe('Contango (calm)')
  })

  it('falls back to Unknown on unknown/missing', () => {
    expect(regimeLabel('unknown')).toBe('Unknown')
    expect(regimeLabel(undefined)).toBe('Unknown')
    expect(regimeLabel(null)).toBe('Unknown')
    expect(regimeLabel('not_a_regime')).toBe('Unknown')
  })
})

describe('fmtPct', () => {
  it('formats positive with a leading +', () => {
    expect(fmtPct(0.9)).toBe('+0.9%')
    expect(fmtPct(12.34)).toBe('+12.3%')
  })

  it('formats negative with a leading -', () => {
    expect(fmtPct(-1.2)).toBe('-1.2%')
  })

  it('formats zero without a sign', () => {
    expect(fmtPct(0)).toBe('0.0%')
  })

  it('falls back to em-dash on null/undefined/NaN', () => {
    expect(fmtPct(null)).toBe('—')
    expect(fmtPct(undefined)).toBe('—')
    expect(fmtPct(NaN)).toBe('—')
  })
})

describe('windowText', () => {
  it('combines range and median', () => {
    const t: AdvisorTiming = { p25_days: 3, p75_days: 8, median_days: 5 }
    expect(windowText(t)).toBe('3–8 trading days (median 5)')
  })

  it('renders range only when median missing', () => {
    expect(windowText({ p25_days: 3, p75_days: 8 })).toBe('3–8 trading days')
  })

  it('renders median only when range missing', () => {
    expect(windowText({ median_days: 5 })).toBe('median 5 trading days')
  })

  it('returns empty string when nothing available', () => {
    expect(windowText({})).toBe('')
    expect(windowText(undefined)).toBe('')
    expect(windowText(null)).toBe('')
  })
})

describe('dteText', () => {
  it('formats suggested DTE', () => {
    expect(dteText({ suggested_dte: 13 })).toBe('~13 DTE')
    expect(dteText({ suggested_dte: 0 })).toBe('~0 DTE')
  })

  it('returns empty string when missing', () => {
    expect(dteText({})).toBe('')
    expect(dteText(undefined)).toBe('')
    expect(dteText(null)).toBe('')
    expect(dteText({ suggested_dte: NaN })).toBe('')
  })
})

describe('termStructurePoints', () => {
  it('builds tenor-ordered points', () => {
    const pts = termStructurePoints({ vix9d: 18, vix: 20, vix3m: 22, vix6m: 23 })
    expect(pts).toEqual([
      { label: '9D', vol: 18 },
      { label: '30D', vol: 20 },
      { label: '3M', vol: 22 },
      { label: '6M', vol: 23 },
    ])
  })

  it('drops missing tenors', () => {
    const pts = termStructurePoints({ vix: 20, vix3m: 22 })
    expect(pts).toEqual([
      { label: '30D', vol: 20 },
      { label: '3M', vol: 22 },
    ])
  })

  it('returns empty for null/undefined inputs', () => {
    expect(termStructurePoints(null)).toEqual([])
    expect(termStructurePoints(undefined)).toEqual([])
    expect(termStructurePoints({})).toEqual([])
  })
})

describe('isBackwardation', () => {
  it('true when VIX > VIX3M', () => {
    expect(isBackwardation({ vix: 25, vix3m: 22 })).toBe(true)
  })

  it('false when contango or equal', () => {
    expect(isBackwardation({ vix: 18, vix3m: 22 })).toBe(false)
    expect(isBackwardation({ vix: 20, vix3m: 20 })).toBe(false)
  })

  it('false when a tenor is missing', () => {
    expect(isBackwardation({ vix: 25 })).toBe(false)
    expect(isBackwardation({ vix3m: 22 })).toBe(false)
    expect(isBackwardation(null)).toBe(false)
    expect(isBackwardation(undefined)).toBe(false)
  })
})

describe('timingAreaData', () => {
  it('maps cdf to day/pct points starting at day 1', () => {
    expect(timingAreaData([0.5, 0.7, 1.0])).toEqual([
      { day: 1, pct: 50 },
      { day: 2, pct: 70 },
      { day: 3, pct: 100 },
    ])
  })

  it('returns empty for empty/missing cdf', () => {
    expect(timingAreaData([])).toEqual([])
    expect(timingAreaData(null)).toEqual([])
    expect(timingAreaData(undefined)).toEqual([])
  })
})

describe('signalDisplayName', () => {
  it('maps known signal keys', () => {
    expect(signalDisplayName('backwardation')).toBe('Backwardation')
    expect(signalDisplayName('ts_flattening')).toBe('TS flattening')
    expect(signalDisplayName('exhaustion')).toBe('Exhaustion')
    expect(signalDisplayName('double_floor')).toBe('Double floor')
    expect(signalDisplayName('divergence')).toBe('VVIX divergence')
  })

  it('falls back to the raw key on unknown', () => {
    expect(signalDisplayName('mystery')).toBe('mystery')
  })
})

describe('hitRateText', () => {
  it('rounds a ratio to whole percent', () => {
    expect(hitRateText(0.6388)).toBe('64%')
    expect(hitRateText(0)).toBe('0%')
    expect(hitRateText(1)).toBe('100%')
  })

  it('falls back to em-dash on null/undefined/NaN', () => {
    expect(hitRateText(null)).toBe('—')
    expect(hitRateText(undefined)).toBe('—')
    expect(hitRateText(NaN)).toBe('—')
  })
})

describe('evidenceRows', () => {
  it('builds all 5 rows in order, scaling fwd_* ratios to percent', () => {
    const rows = evidenceRows({
      signals: {
        backwardation: { n: 324, hit_rate: 0.6389, fwd_vix_5: -0.0842, fwd_spy_5: 0.0091, timing_median: 1 },
      },
    })
    expect(rows.map((r) => r.key)).toEqual([
      'backwardation',
      'ts_flattening',
      'exhaustion',
      'double_floor',
      'divergence',
    ])
    const bw = rows[0]
    expect(bw.name).toBe('Backwardation')
    expect(bw.n).toBe('324')
    expect(bw.hitRate).toBe('64%')
    expect(bw.fwdVix5).toBe('-8.4%')
    expect(bw.fwdSpy5).toBe('+0.9%')
    expect(bw.timing).toBe('1d')
  })

  it('renders em-dashes for missing signals', () => {
    const rows = evidenceRows({ signals: {} })
    const tf = rows[1]
    expect(tf.key).toBe('ts_flattening')
    expect(tf.n).toBe('—')
    expect(tf.hitRate).toBe('—')
    expect(tf.fwdVix5).toBe('—')
    expect(tf.fwdSpy5).toBe('—')
    expect(tf.timing).toBe('—')
  })

  it('handles null/undefined evidence', () => {
    expect(evidenceRows(null)).toHaveLength(5)
    expect(evidenceRows(undefined)).toHaveLength(5)
  })
})

describe('resultMark', () => {
  it('maps correctness to a mark', () => {
    expect(resultMark(true)).toBe('✓')
    expect(resultMark(false)).toBe('✗')
    expect(resultMark(null)).toBe('pending')
    expect(resultMark(undefined)).toBe('pending')
  })
})

describe('proximityPct', () => {
  it('scales proximity ratio to a clamped whole percent', () => {
    expect(proximityPct(mkSignal({ proximity: 0.42 }))).toBe(42)
    expect(proximityPct(mkSignal({ proximity: 0 }))).toBe(0)
    expect(proximityPct(mkSignal({ proximity: 1 }))).toBe(100)
  })

  it('clamps out-of-range proximity into [0,100]', () => {
    expect(proximityPct(mkSignal({ proximity: 1.5 }))).toBe(100)
    expect(proximityPct(mkSignal({ proximity: -0.2 }))).toBe(0)
  })

  it('active always reports 100 regardless of proximity', () => {
    expect(proximityPct(mkSignal({ active: true, proximity: 0.1 }))).toBe(100)
    expect(proximityPct(mkSignal({ active: true }))).toBe(100)
  })

  it('falls back to 0 on missing/NaN', () => {
    expect(proximityPct(mkSignal())).toBe(0)
    expect(proximityPct(mkSignal({ proximity: NaN }))).toBe(0)
    expect(proximityPct(null)).toBe(0)
    expect(proximityPct(undefined)).toBe(0)
  })
})

describe('directionClass', () => {
  it('maps direction to a tailwind color class', () => {
    expect(directionClass('bullish')).toBe('text-emerald-400')
    expect(directionClass('bearish')).toBe('text-red-400')
    expect(directionClass('neutral')).toBe('text-forge-muted')
  })

  it('falls back to muted on missing/unknown', () => {
    expect(directionClass(undefined)).toBe('text-forge-muted')
    expect(directionClass(null)).toBe('text-forge-muted')
    expect(directionClass('mystery')).toBe('text-forge-muted')
  })
})

describe('actionAccentClass', () => {
  it('maps bullish stances to emerald', () => {
    expect(actionAccentClass('buy_the_bounce')).toEqual({
      border: 'border-l-emerald-500',
      text: 'text-emerald-400',
    })
    expect(actionAccentClass('lean_calls')).toEqual({
      border: 'border-l-emerald-500',
      text: 'text-emerald-400',
    })
  })

  it('maps lean_puts to red', () => {
    expect(actionAccentClass('lean_puts')).toEqual({
      border: 'border-l-red-500',
      text: 'text-red-400',
    })
  })

  it('falls back to violet for neutral/unknown/missing', () => {
    const violet = { border: 'border-l-violet-500', text: 'text-violet-400' }
    expect(actionAccentClass('neutral')).toEqual(violet)
    expect(actionAccentClass(undefined)).toEqual(violet)
    expect(actionAccentClass(null)).toEqual(violet)
    expect(actionAccentClass('mystery')).toEqual(violet)
  })
})

describe('sortedSignalEntries', () => {
  it('sorts active first, then proximity descending', () => {
    const entries = sortedSignalEntries({
      armed_low: mkSignal({ proximity: 0.2 }),
      active_one: mkSignal({ active: true, proximity: 0.1 }),
      armed_high: mkSignal({ proximity: 0.8 }),
    })
    expect(entries.map((e) => e.key)).toEqual(['active_one', 'armed_high', 'armed_low'])
  })

  it('returns empty for missing signals', () => {
    expect(sortedSignalEntries(null)).toEqual([])
    expect(sortedSignalEntries(undefined)).toEqual([])
    expect(sortedSignalEntries({})).toEqual([])
  })
})

describe('triggerGroups', () => {
  it('splits by direction, omitting neutral, each proximity-sorted', () => {
    const groups = triggerGroups({
      backwardation: mkSignal({ direction: 'bullish', proximity: 0.3 }),
      exhaustion: mkSignal({ direction: 'bullish', active: true, proximity: 0.1 }),
      ts_flattening: mkSignal({ direction: 'bearish', proximity: 0.6 }),
      double_floor: mkSignal({ direction: 'neutral', proximity: 0.9 }),
    })
    expect(groups.bullish.map((e) => e.key)).toEqual(['exhaustion', 'backwardation'])
    expect(groups.bearish.map((e) => e.key)).toEqual(['ts_flattening'])
  })

  it('returns empty groups for missing signals', () => {
    expect(triggerGroups(null)).toEqual({ bullish: [], bearish: [] })
    expect(triggerGroups(undefined)).toEqual({ bullish: [], bearish: [] })
    expect(triggerGroups({})).toEqual({ bullish: [], bearish: [] })
  })
})

describe('seriesForChart', () => {
  it('projects to {d, vix_z, vvix_z}', () => {
    const pts = seriesForChart([
      { d: '2026-05-01', vix: 18, vvix: 95, vix_z: -0.5, vvix_z: 0.2, ratio: 5.2 },
      { d: '2026-05-02', vix: 20, vvix: 100, vix_z: 0.1, vvix_z: 0.4, ratio: 5.0 },
    ])
    expect(pts).toEqual([
      { d: '2026-05-01', vix_z: -0.5, vvix_z: 0.2 },
      { d: '2026-05-02', vix_z: 0.1, vvix_z: 0.4 },
    ])
  })

  it('drops rows with missing date or non-finite z-scores', () => {
    const pts = seriesForChart([
      { d: '2026-05-01', vix: 18, vvix: 95, vix_z: 0.5, vvix_z: 0.2, ratio: 5 },
      { d: '', vix: 18, vvix: 95, vix_z: 0.5, vvix_z: 0.2, ratio: 5 },
      { d: '2026-05-03', vix: 18, vvix: 95, vix_z: NaN, vvix_z: 0.2, ratio: 5 },
      { d: '2026-05-04', vix: 18, vvix: 95, vix_z: 0.5, vvix_z: NaN as any, ratio: 5 },
    ])
    expect(pts).toEqual([{ d: '2026-05-01', vix_z: 0.5, vvix_z: 0.2 }])
  })

  it('returns empty for missing/empty series', () => {
    expect(seriesForChart(null)).toEqual([])
    expect(seriesForChart(undefined)).toEqual([])
    expect(seriesForChart([])).toEqual([])
  })
})

describe('liveHeadline', () => {
  it('summarizes scored calls with in-window', () => {
    expect(
      liveHeadline({ n_scored: 25, overall_accuracy: 0.64, in_window_rate: 0.72 }),
    ).toBe('64% over 25 scored calls · 72% in-window')
  })

  it('omits in-window when null', () => {
    expect(
      liveHeadline({ n_scored: 1, overall_accuracy: 1, in_window_rate: null }),
    ).toBe('100% over 1 scored call')
  })

  it('accruing message when no scored calls', () => {
    expect(liveHeadline({ n_scored: 0, overall_accuracy: null, in_window_rate: null })).toBe(
      'No scored calls yet — accruing daily.',
    )
    expect(liveHeadline(null)).toBe('No scored calls yet — accruing daily.')
    expect(liveHeadline(undefined)).toBe('No scored calls yet — accruing daily.')
  })
})

describe('formatVolRegime', () => {
  it('builds the full sentence with stance, DTE, and range', () => {
    const report: Partial<AdvisorReport> = {
      regime_label: 'exhaustion',
      recommendation: { stance: 'buy_the_bounce', conviction: 'high', rationale: '' },
      timing: { suggested_dte: 13, p25_days: 3, p75_days: 8 },
    }
    expect(formatVolRegime(report)).toBe(
      'Exhaustion — lean long / buy the bounce, ~13 DTE over 3–8 trading days',
    )
  })

  it('maps each regime label to readable text', () => {
    const mk = (regime_label: string): Partial<AdvisorReport> => ({ regime_label })
    expect(formatVolRegime(mk('backwardation_stressed'))).toBe('Backwardation (stressed)')
    expect(formatVolRegime(mk('floor_complacent'))).toBe('Floor / complacent')
    expect(formatVolRegime(mk('contango_flattening'))).toBe('Contango, flattening')
    expect(formatVolRegime(mk('contango_calm'))).toBe('Contango (calm)')
  })

  it('maps each stance to readable text', () => {
    const mk = (stance: string): Partial<AdvisorReport> => ({
      regime_label: 'exhaustion',
      recommendation: { stance: stance as any, conviction: '', rationale: '' },
    })
    expect(formatVolRegime(mk('lean_calls'))).toBe('Exhaustion — lean calls')
    expect(formatVolRegime(mk('lean_puts'))).toBe('Exhaustion — lean puts')
    expect(formatVolRegime(mk('neutral'))).toBe('Exhaustion — neutral')
  })

  it('omits DTE and range parts when timing fields are missing', () => {
    expect(
      formatVolRegime({
        regime_label: 'contango_calm',
        recommendation: { stance: 'neutral', conviction: '', rationale: '' },
        timing: {},
      }),
    ).toBe('Contango (calm) — neutral')
  })

  it('omits the range when only one endpoint is present', () => {
    expect(
      formatVolRegime({
        regime_label: 'exhaustion',
        timing: { suggested_dte: 5, p25_days: 3 },
      }),
    ).toBe('Exhaustion, ~5 DTE')
  })

  it('returns null when the report or regime label is unusable', () => {
    expect(formatVolRegime(null)).toBeNull()
    expect(formatVolRegime(undefined)).toBeNull()
    expect(formatVolRegime({})).toBeNull()
    expect(formatVolRegime({ regime_label: 'not_a_regime' })).toBeNull()
  })
})

describe('regimeBannerText', () => {
  it('builds regime + contango term structure + action headline', () => {
    expect(
      regimeBannerText({
        regime_label: 'contango_calm',
        inputs: { vix: 20.26, vix3m: 21.65 },
        action: {
          headline: 'No directional trade — sell premium or sit out',
          do: '', dte_text: '', plain: '',
        },
      }),
    ).toBe('Contango (calm) — VIX 20.3 < VIX3M 21.6 · No directional trade — sell premium or sit out')
  })

  it('uses > when the front month is above VIX3M (backwardation)', () => {
    expect(
      regimeBannerText({
        regime_label: 'backwardation_stressed',
        inputs: { vix: 28.4, vix3m: 23.1 },
      }),
    ).toBe('Backwardation (stressed) — VIX 28.4 > VIX3M 23.1')
  })

  it('drops the term clause when VIX/VIX3M are missing, keeps the headline', () => {
    expect(
      regimeBannerText({
        regime_label: 'contango_calm',
        action: { headline: 'Sit out', do: '', dte_text: '', plain: '' },
      }),
    ).toBe('Contango (calm) · Sit out')
  })

  it('returns just the label when only the regime is present', () => {
    expect(regimeBannerText({ regime_label: 'contango_calm' })).toBe('Contango (calm)')
  })

  it('returns null for missing report or unrecognized regime', () => {
    expect(regimeBannerText(null)).toBeNull()
    expect(regimeBannerText(undefined)).toBeNull()
    expect(regimeBannerText({})).toBeNull()
    expect(regimeBannerText({ regime_label: 'not_a_regime' })).toBeNull()
  })
})
