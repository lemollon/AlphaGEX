import { describe, it, expect } from 'vitest'
import { compareToBacktestAnchor, BACKTEST_ANCHORS } from '../backtestAnchor'

describe('compareToBacktestAnchor', () => {
  it('returns null when contracts <= 0 — no per-lot figure is computable', () => {
    expect(compareToBacktestAnchor(100, 0, BACKTEST_ANCHORS.spark)).toBeNull()
    expect(compareToBacktestAnchor(100, -1, BACKTEST_ANCHORS.spark)).toBeNull()
  })

  describe('SPARK', () => {
    const anchor = BACKTEST_ANCHORS.spark

    it('beyond_worst_ever — worse than the all-time worst day', () => {
      // -484.70/lot is the worst ever; one dollar past it must trip the top tier.
      const c = compareToBacktestAnchor(-500 * 1, 1, anchor)
      expect(c?.tier).toBe('beyond_worst_ever')
      expect(c?.perLot).toBe(-500)
      expect(c?.label).toMatch(/Outside the backtested envelope/)
      expect(c?.label).toMatch(/943/)
    })

    it('beyond_worst_avg — past the typical worst day but inside the all-time worst', () => {
      // -438.50/lot is the worst-day average; -460/lot is past it but better than -484.70.
      const c = compareToBacktestAnchor(-460 * 1, 1, anchor)
      expect(c?.tier).toBe('beyond_worst_avg')
      expect(c?.label).toMatch(/typical worst-day average/)
    })

    it('within_range — a typical day inside the worst/best-day averages', () => {
      const c = compareToBacktestAnchor(10.86 * 1, 1, anchor)
      expect(c?.tier).toBe('within_range')
      expect(c?.label).toMatch(/Within the expected per-lot range/)
    })

    it('beyond_best_avg — past the typical best day but inside the all-time best', () => {
      // 140.10/lot is the best-day average; 150/lot is past it but better-bound short of 167.30.
      const c = compareToBacktestAnchor(150 * 1, 1, anchor)
      expect(c?.tier).toBe('beyond_best_avg')
      expect(c?.label).toMatch(/typical best-day average/)
    })

    it('beyond_best_ever — better than the all-time best day', () => {
      const c = compareToBacktestAnchor(200 * 1, 1, anchor)
      expect(c?.tier).toBe('beyond_best_ever')
      expect(c?.label).toMatch(/Outside the backtested envelope/)
    })

    it('divides by contracts before comparing — a multi-lot total must not falsely trip the envelope', () => {
      // -484.70 total across 5 lots is only -96.94/lot: comfortably within range,
      // even though -484.70 alone is SPARK's all-time worst single-lot day.
      const c = compareToBacktestAnchor(-484.70, 5, anchor)
      expect(c?.tier).toBe('within_range')
      expect(c?.perLot).toBeCloseTo(-96.94, 2)
    })
  })

  describe('FLAME', () => {
    const anchor = BACKTEST_ANCHORS.flame

    it('beyond_worst_ever — worse than the all-time worst day', () => {
      const c = compareToBacktestAnchor(-200 * 1, 1, anchor)
      expect(c?.tier).toBe('beyond_worst_ever')
      expect(c?.label).toMatch(/944/)
    })

    it('beyond_worst_avg — past the typical worst day but inside the all-time worst', () => {
      // -182.30/lot is the worst-day average; -184/lot is past it but better than -186.70.
      const c = compareToBacktestAnchor(-184 * 1, 1, anchor)
      expect(c?.tier).toBe('beyond_worst_avg')
    })

    it('within_range — a typical day inside the worst/best-day averages', () => {
      const c = compareToBacktestAnchor(9.79 * 1, 1, anchor)
      expect(c?.tier).toBe('within_range')
    })

    it('beyond_best_avg — past the typical best day but inside the all-time best', () => {
      // 82.50/lot is the best-day average; 85/lot is past it but short of 92.30.
      const c = compareToBacktestAnchor(85 * 1, 1, anchor)
      expect(c?.tier).toBe('beyond_best_avg')
    })

    it('beyond_best_ever — better than the all-time best day', () => {
      const c = compareToBacktestAnchor(100 * 1, 1, anchor)
      expect(c?.tier).toBe('beyond_best_ever')
    })
  })
})
