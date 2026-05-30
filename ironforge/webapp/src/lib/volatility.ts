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
  // ratios (e.g. -0.084), NOT percents — scale x100 at render if ever displayed
  fwd_spy_5_ratio?: number
  fwd_vix_5_ratio?: number
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

/** Per-signal evidence stats from backtest/vvix_vix_analysis/evidence.json.
 * Forward-return fields (fwd_*) are decimals/ratios, NOT pre-multiplied
 * percentages (e.g. -0.084 means -8.4%). */
export interface AdvisorEvidenceSignal {
  n?: number
  hit_rate?: number
  fwd_vix_5?: number
  fwd_spy_5?: number
  timing_median?: number
}

export interface AdvisorEvidence {
  signals: Record<string, AdvisorEvidenceSignal>
}

export interface AdvisorPayload {
  report: AdvisorReport
  evidence: AdvisorEvidence
  live_record: AdvisorLiveRecord
}

/** One row of /api/volatility/history `rows[]`. All fields may be null. */
export interface AdvisorHistoryRow {
  log_date: string
  vix: number | null
  vvix: number | null
  regime_label: string | null
  stance: string | null
  conviction: string | null
  predicted_dir: string | null
  horizon_days: number | null
  window_p75_days: number | null
  realized_vix_chg: number | null
  realized_spy_ret: number | null
  event_landed_day: number | null
  correct: boolean | null
  in_window: boolean | null
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

/* ------------------------------------------------------------------ */
/*  3B chart / table transforms (pure, unit-tested)                    */
/* ------------------------------------------------------------------ */

/** A single point on the VIX term-structure curve. */
export interface TermPoint {
  label: string
  vol: number
}

/**
 * Build the VIX term-structure curve points from advisor inputs, in
 * tenor order [9D, 30D, 3M, 6M]. Null/undefined/NaN tenors are dropped so
 * the recharts line never breaks on a missing node.
 */
export function termStructurePoints(inputs?: AdvisorInputs | null): TermPoint[] {
  if (!inputs) return []
  const raw: TermPoint[] = [
    { label: '9D', vol: inputs.vix9d as number },
    { label: '30D', vol: inputs.vix as number },
    { label: '3M', vol: inputs.vix3m as number },
    { label: '6M', vol: inputs.vix6m as number },
  ]
  return raw.filter(
    (p) => p.vol !== null && p.vol !== undefined && !Number.isNaN(p.vol),
  )
}

/**
 * Backwardation = front-month fear above 3-month, i.e. VIX > VIX3M.
 * Returns false when either tenor is missing.
 */
export function isBackwardation(inputs?: AdvisorInputs | null): boolean {
  if (!inputs) return false
  const { vix, vix3m } = inputs
  if (vix === null || vix === undefined || Number.isNaN(vix)) return false
  if (vix3m === null || vix3m === undefined || Number.isNaN(vix3m)) return false
  return vix > vix3m
}

/** A single point on the timing cumulative-probability area chart. */
export interface TimingPoint {
  day: number
  pct: number
}

/**
 * Convert a timing CDF (probabilities in [0,1], indexed by day-1) into
 * day/percent points for the area chart: day starts at 1, pct = cdf*100.
 * Empty/missing CDF → [].
 */
export function timingAreaData(cdf?: number[] | null): TimingPoint[] {
  if (!cdf || cdf.length === 0) return []
  return cdf.map((p, i) => ({
    day: i + 1,
    pct: (p ?? 0) * 100,
  }))
}

/** Ordered list of advisor signal keys (display order). */
export const SIGNAL_KEYS = [
  'backwardation',
  'ts_flattening',
  'exhaustion',
  'double_floor',
  'divergence',
] as const

export type SignalKey = (typeof SIGNAL_KEYS)[number]

/** Human-readable name for a signal key. Unknown → the raw key. */
export function signalDisplayName(key: string): string {
  switch (key) {
    case 'backwardation':
      return 'Backwardation'
    case 'ts_flattening':
      return 'TS flattening'
    case 'exhaustion':
      return 'Exhaustion'
    case 'double_floor':
      return 'Double floor'
    case 'divergence':
      return 'VVIX divergence'
    default:
      return key
  }
}

/**
 * Format a hit-rate ratio in [0,1] as a whole-percent string, e.g.
 * 0.6388 → '64%'. Null/undefined/NaN → '—'.
 */
export function hitRateText(x?: number | null): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—'
  return `${Math.round(x * 100)}%`
}

/** A formatted evidence-table row, one per signal key. */
export interface EvidenceRow {
  key: string
  name: string
  n: string
  hitRate: string
  fwdVix5: string
  fwdSpy5: string
  timing: string
}

/**
 * Build the evidence table rows in SIGNAL_KEYS order. fwd_* are ratios in
 * the source data, so they are scaled ×100 before fmtPct. Missing signals
 * render em-dashes rather than being dropped.
 */
export function evidenceRows(evidence?: AdvisorEvidence | null): EvidenceRow[] {
  const signals = evidence?.signals ?? {}
  return SIGNAL_KEYS.map((key) => {
    const s = signals[key] as AdvisorEvidenceSignal | undefined
    const n = s?.n
    const med = s?.timing_median
    return {
      key,
      name: signalDisplayName(key),
      n: n === null || n === undefined || Number.isNaN(n) ? '—' : String(n),
      hitRate: hitRateText(s?.hit_rate),
      fwdVix5: fmtPct(s?.fwd_vix_5 === null || s?.fwd_vix_5 === undefined ? null : s.fwd_vix_5 * 100),
      fwdSpy5: fmtPct(s?.fwd_spy_5 === null || s?.fwd_spy_5 === undefined ? null : s.fwd_spy_5 * 100),
      timing: med === null || med === undefined || Number.isNaN(med) ? '—' : `${med}d`,
    }
  })
}

/**
 * Map a live-record `correct` flag to a result mark.
 * true → '✓', false → '✗', null/undefined → 'pending'.
 */
export function resultMark(correct?: boolean | null): string {
  if (correct === true) return '✓'
  if (correct === false) return '✗'
  return 'pending'
}

/* ------------------------------------------------------------------ */
/*  Daily-brief one-liner (pure, unit-tested)                          */
/* ------------------------------------------------------------------ */

/** Brief-flavored regime label (sentence form, slightly different wording
 * than the dashboard `regimeLabel`). Unknown → '' so the caller can fall
 * back to a locally-derived label. */
function briefRegimeText(key?: string | null): string {
  switch (key) {
    case 'backwardation_stressed':
      return 'Backwardation (stressed)'
    case 'exhaustion':
      return 'Exhaustion'
    case 'floor_complacent':
      return 'Floor / complacent'
    case 'contango_flattening':
      return 'Contango, flattening'
    case 'contango_calm':
      return 'Contango (calm)'
    default:
      return ''
  }
}

/** Brief-flavored stance text. Unknown → ''. */
function briefStanceText(stance?: string | null): string {
  switch (stance) {
    case 'buy_the_bounce':
      return 'lean long / buy the bounce'
    case 'lean_calls':
      return 'lean calls'
    case 'lean_puts':
      return 'lean puts'
    case 'neutral':
      return 'neutral'
    default:
      return ''
  }
}

/**
 * Build the single daily-brief volatility-regime line from an advisor report,
 * e.g. "Exhaustion — lean long / buy the bounce, ~13 DTE over 3–8 trading days".
 *
 * Pure + total: returns null when the report is missing or has no usable
 * regime label, so the caller can fall back to a locally-derived label or
 * omit the line. Never throws.
 */
export function formatVolRegime(report?: Partial<AdvisorReport> | null): string | null {
  if (!report) return null
  const regime = briefRegimeText(report.regime_label)
  if (!regime) return null
  const stance = briefStanceText(report.recommendation?.stance)
  const timing = report.timing
  const dte = timing?.suggested_dte
  const dtePart =
    dte === null || dte === undefined || Number.isNaN(dte) ? '' : `, ~${dte} DTE`
  const p25 = timing?.p25_days
  const p75 = timing?.p75_days
  const hasRange =
    p25 !== null && p25 !== undefined && !Number.isNaN(p25) &&
    p75 !== null && p75 !== undefined && !Number.isNaN(p75)
  const rangePart = hasRange ? ` over ${p25}–${p75} trading days` : ''
  const stancePart = stance ? ` — ${stance}` : ''
  return `${regime}${stancePart}${dtePart}${rangePart}`
}

/**
 * Headline summarizing the live track record.
 *   n_scored>0 → '64% over 25 scored calls' (+ ' · 72% in-window' if present)
 *   else       → 'No scored calls yet — accruing daily.'
 */
export function liveHeadline(record?: AdvisorLiveRecord | null): string {
  if (!record || !record.n_scored || record.n_scored <= 0) {
    return 'No scored calls yet — accruing daily.'
  }
  const acc = record.overall_accuracy
  const accTxt =
    acc === null || acc === undefined || Number.isNaN(acc)
      ? '—'
      : `${Math.round(acc * 100)}%`
  let out = `${accTxt} over ${record.n_scored} scored call${record.n_scored === 1 ? '' : 's'}`
  const inw = record.in_window_rate
  if (inw !== null && inw !== undefined && !Number.isNaN(inw)) {
    out += ` · ${Math.round(inw * 100)}% in-window`
  }
  return out
}
