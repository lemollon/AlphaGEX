/**
 * Volatility Regime Advisor — TypeScript types + pure display helpers.
 *
 * Mirrors the AlphaGEX backend payload from `/api/vix/regime-advisor`.
 * Helpers here are intentionally pure (no I/O, no React) so they can be
 * unit-tested under vitest's `node` environment without a DOM.
 */

export type Stance = 'lean_puts' | 'lean_calls' | 'neutral' | 'buy_the_bounce'

export interface AdvisorRecommendation {
  stance: Stance
  conviction: string
  rationale: string
}

export interface AdvisorOutlook {
  fwd_spy_5_pct?: number
  fwd_vix_5_pct?: number
  hit_rate?: number
  sample_n?: number
}

export interface AdvisorTiming {
  primary_signal?: string | null
  median_days?: number
  p25_days?: number
  p75_days?: number
  suggested_dte?: number
  cdf?: number[]
  structure_note?: string
}

export interface AdvisorSignal {
  active: boolean
  value: number
  confidence: string
  blurb: string
  hit_rate: number | null
}

export interface AdvisorInputs {
  vix?: number
  vvix?: number
  vix9d?: number
  vix3m?: number
  vix6m?: number
}

export interface AdvisorReport {
  ok?: boolean
  as_of?: string
  regime_label: string
  recommendation: AdvisorRecommendation
  outlook: AdvisorOutlook
  timing: AdvisorTiming
  signals: Record<string, AdvisorSignal>
  inputs: AdvisorInputs
}

export interface AdvisorLiveRecord {
  n_scored: number
  overall_accuracy: number | null
  in_window_rate: number | null
}

export interface AdvisorPayload {
  report: AdvisorReport
  evidence: { signals: Record<string, any> }
  live_record: AdvisorLiveRecord
}

/**
 * Human-readable label for a recommendation stance.
 * Unknown/missing → '—'.
 */
export function stanceLabel(stance?: Stance | string | null): string {
  switch (stance) {
    case 'buy_the_bounce':
      return 'Buy the bounce'
    case 'lean_calls':
      return 'Lean calls'
    case 'lean_puts':
      return 'Lean puts'
    case 'neutral':
      return 'Neutral'
    default:
      return '—'
  }
}

/**
 * Human-readable label for a regime key.
 * Unknown/missing → 'Unknown'.
 */
export function regimeLabel(key?: string | null): string {
  switch (key) {
    case 'backwardation_stressed':
      return 'Backwardation (stressed)'
    case 'exhaustion':
      return 'Exhaustion'
    case 'floor_complacent':
      return 'Floor (complacent)'
    case 'contango_flattening':
      return 'Contango (flattening)'
    case 'contango_calm':
      return 'Contango (calm)'
    case 'unknown':
    default:
      return 'Unknown'
  }
}

/**
 * Format a percentage with an explicit sign, e.g. 0.9 → '+0.9%', -1.2 → '-1.2%'.
 * null/undefined/NaN → '—'.
 */
export function fmtPct(x?: number | null): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—'
  const sign = x > 0 ? '+' : ''
  return `${sign}${x.toFixed(1)}%`
}

/**
 * Describe the expected timing window, e.g. '3–8 trading days (median 5)'.
 * If neither p25/p75 nor median is available → ''.
 */
export function windowText(timing?: AdvisorTiming | null): string {
  if (!timing) return ''
  const { p25_days, p75_days, median_days } = timing
  const hasRange = p25_days !== null && p25_days !== undefined && p75_days !== null && p75_days !== undefined
  const hasMedian = median_days !== null && median_days !== undefined
  if (hasRange && hasMedian) {
    return `${p25_days}–${p75_days} trading days (median ${median_days})`
  }
  if (hasRange) {
    return `${p25_days}–${p75_days} trading days`
  }
  if (hasMedian) {
    return `median ${median_days} trading days`
  }
  return ''
}

/**
 * Describe the suggested DTE, e.g. '~13 DTE'.
 * Missing → ''.
 */
export function dteText(timing?: AdvisorTiming | null): string {
  if (!timing) return ''
  const dte = timing.suggested_dte
  if (dte === null || dte === undefined || Number.isNaN(dte)) return ''
  return `~${dte} DTE`
}
