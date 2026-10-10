/**
 * Advanced/technical-trader backtest envelope — OPT-IN, additive only.
 *
 * The default customer-facing Live page (`lib/live/state.ts`, `today_result`)
 * is deliberately jargon-free. This module exists ONLY for the "Advanced"
 * disclosure a technical trader can expand: it compares today's realized
 * PER-LOT result against the strategy's validated historical range and says
 * whether today fell inside or outside it. Strictly descriptive/backward-
 * looking — this must never be read or worded as a forward projection or a
 * promise about tomorrow.
 *
 * SOURCE OF THE ANCHOR NUMBERS: `ebb_loss_envelope.py` (`envelope()` /
 * `BOT_TRANCHE`) via `assignment_frontier_55.py`, in ironforge-data. This is
 * the SAME validated per-lot P&L series the production risk monitor
 * (`ebb_daily_monitor.py`) already uses for its BOOK HEALTH verdict — the
 * best-day side was mirrored by hand from that script's worst-day
 * methodology (`yearly_best = pnl.groupby(year).max()`), not re-derived.
 * Measured 2026-09-01.
 *
 * 🚨 STALENESS WARNING — mirrors the tone of `botStructure()` in scanner.ts
 * and the `BOT_TRANCHE` comments in ebb_loss_envelope.py: these numbers are
 * tied to ONE specific structure per bot (FLAME: PM 13:05 CT clock, $2 wing,
 * otm 1.0; SPARK: AM 10:05 CT clock, $5 wing, otm 2.0). If `botStructure()`
 * or `BOT_TRANCHE` ever changes either bot's wing/otm, this anchor is stale
 * and must be re-measured against the new structure before it is trusted.
 */

import { formatDollarPnl } from '@/lib/format'

export type BacktestTier =
  | 'beyond_worst_ever'
  | 'beyond_worst_avg'
  | 'within_range'
  | 'beyond_best_avg'
  | 'beyond_best_ever'

export interface BacktestAnchor {
  bot: 'flame' | 'spark'
  n: number
  sampleStart: string
  sampleEnd: string
  meanPerLot: number
  worstDay: number
  worstDayAvg: number
  bestDay: number
  bestDayAvg: number
  lossRate: number
}

export interface BacktestComparison {
  tier: BacktestTier
  label: string
  perLot: number
  anchor: BacktestAnchor
}

export const BACKTEST_ANCHORS: Record<'flame' | 'spark', BacktestAnchor> = {
  flame: {
    bot: 'flame',
    n: 944,
    sampleStart: '2022-11-02',
    sampleEnd: '2026-08-28',
    meanPerLot: 9.79,
    worstDay: -186.70,
    worstDayAvg: -182.30,
    bestDay: 92.30,
    bestDayAvg: 82.50,
    lossRate: 0.154,
  },
  spark: {
    bot: 'spark',
    n: 943,
    sampleStart: '2022-11-02',
    sampleEnd: '2026-08-28',
    meanPerLot: 10.86,
    worstDay: -484.70,
    worstDayAvg: -438.50,
    bestDay: 167.30,
    bestDayAvg: 140.10,
    lossRate: 0.157,
  },
}

/** Matches the style of formatDollarPnl/formatCurrency in lib/format.ts. */
function money(x: number): string {
  return formatDollarPnl(x)
}

/**
 * Compares one day's TOTAL realized P&L against the bot's validated per-lot
 * envelope. Mirrors the per-lot tiering in `ebb_loss_envelope.py`'s
 * `_check_bot` (`per_lot = float(pnl) / ct`, `beyond_ever` / `beyond_avg`).
 *
 * `totalRealizedPnl` MUST be the TOTAL across contracts — dividing by
 * `contracts` here is what makes the comparison correct. Comparing a
 * multi-lot total directly against a per-lot threshold would flag every
 * multi-contract trade as a false "outside the envelope" alarm.
 *
 * Returns null when `contracts <= 0` (no per-lot figure is computable).
 */
export function compareToBacktestAnchor(
  totalRealizedPnl: number,
  contracts: number,
  anchor: BacktestAnchor,
): BacktestComparison | null {
  if (contracts <= 0) return null

  const perLot = totalRealizedPnl / contracts

  if (perLot < anchor.worstDay) {
    return {
      tier: 'beyond_worst_ever',
      label: `Outside the backtested envelope — worse than any of the ${anchor.n} validated sessions since ${anchor.sampleStart} (worst ever ${money(anchor.worstDay)}/lot).`,
      perLot,
      anchor,
    }
  }
  if (perLot < anchor.worstDayAvg) {
    return {
      tier: 'beyond_worst_avg',
      label: `Past the typical worst-day average (${money(anchor.worstDayAvg)}/lot) but inside the all-time worst (${money(anchor.worstDay)}/lot).`,
      perLot,
      anchor,
    }
  }
  if (perLot > anchor.bestDay) {
    return {
      tier: 'beyond_best_ever',
      label: `Outside the backtested envelope — better than any of the ${anchor.n} validated sessions since ${anchor.sampleStart} (best ever ${money(anchor.bestDay)}/lot).`,
      perLot,
      anchor,
    }
  }
  if (perLot > anchor.bestDayAvg) {
    return {
      tier: 'beyond_best_avg',
      label: `Past the typical best-day average (${money(anchor.bestDayAvg)}/lot) — an unusually strong day.`,
      perLot,
      anchor,
    }
  }
  return {
    tier: 'within_range',
    label: `Within the expected per-lot range for this strategy (${money(anchor.worstDayAvg)} to ${money(anchor.bestDayAvg)}/lot on a typical day).`,
    perLot,
    anchor,
  }
}
