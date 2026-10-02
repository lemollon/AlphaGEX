/**
 * FLAME/SPARK v2 — pure, side-effect-free math. No DB, no network, no clock.
 * Every function here is a direct TypeScript port of the FROZEN research
 * scripts so the exact algorithm that was backtested is the one that runs
 * live:
 *   - CALM measure / percentile      <- C:\Users\lemol\dev\meltup\signal_on_flame_spark.py
 *   - igexFormulaNet (BS gamma GEX)  <- C:\Users\lemol\dev\meltup\live_igex.py (igex_formula_net)
 *   - depth-2 regime tree (D2)       <- signal_on_flame_spark.py run_d2 (sklearn DecisionTreeClassifier,
 *                                        max_depth=2, reproduced here as a tiny hand-rolled CART since this
 *                                        runs inside the Next.js process, not Python)
 *   - trailing-60-winner (D1)        <- signal_on_flame_spark.py run_d1
 *
 * See __tests__/math.test.ts for the frozen numeric fixtures (5 real days per
 * signal, pulled straight out of vix_minute.duckdb / ironforge.duckdb — see
 * that file's header for exactly how they were extracted).
 */

// ---------------------------------------------------------------------------
// CALM: std of 1-minute log(VIX close) changes over the 120 minutes before
// entry, below the prior-day 67th percentile of that same measure (prior-only
// expanding window over all days strictly before the entry date).
// ---------------------------------------------------------------------------

/** Sample standard deviation (ddof=1, matches numpy.std(..., ddof=1)). */
function stdSample(xs: number[]): number {
  const n = xs.length
  const mean = xs.reduce((a, b) => a + b, 0) / n
  const sumSq = xs.reduce((a, b) => a + (b - mean) * (b - mean), 0)
  return Math.sqrt(sumSq / (n - 1))
}

/**
 * `closes` must be the 1-minute VIX closes for the 120 minutes strictly
 * before the entry minute, in chronological order (matches
 * calm_measure_series: modq in [entry-120, entry-1]). Returns null if there
 * are fewer than 5 closes (matches the research script's `len(c) < 5` skip).
 */
export function calmMeasure(closes: number[]): number | null {
  if (closes.length < 5) return null
  const logrets: number[] = []
  for (let i = 1; i < closes.length; i++) logrets.push(Math.log(closes[i] / closes[i - 1]))
  if (logrets.length < 2) return null
  return stdSample(logrets)
}

/** numpy.percentile(hist, 67) — default linear interpolation. */
export function percentile67(hist: number[]): number {
  const sorted = [...hist].sort((a, b) => a - b)
  const n = sorted.length
  if (n === 0) return NaN
  if (n === 1) return sorted[0]
  const h = (n - 1) * 0.67
  const lo = Math.floor(h)
  const hi = Math.ceil(h)
  if (lo === hi) return sorted[lo]
  return sorted[lo] + (h - lo) * (sorted[hi] - sorted[lo])
}

export type CalmResult = { isCalm: boolean; threshold: number | null; measure: number | null }

/**
 * `priorMeasures` = this bot's own CALM measure on every session STRICTLY
 * before the entry date, oldest-first-or-any-order (only values matter, not
 * order) — i.e. look-ahead-safe by construction as long as the caller never
 * includes today. `minHist=20` matches calm_flag's floor.
 */
export function isCalmFromHistory(measure: number | null, priorMeasures: number[], minHist = 20): CalmResult {
  const hist = priorMeasures.filter((v) => Number.isFinite(v))
  if (measure === null || !Number.isFinite(measure) || hist.length < minHist) {
    return { isCalm: false, threshold: null, measure }
  }
  const thr = percentile67(hist)
  return { isCalm: measure < thr, threshold: thr, measure }
}

// ---------------------------------------------------------------------------
// LONGG: igex_net > 0 at the bot's own entry minute. The sign check itself is
// trivial; the hard part is computing igex_net live, which igexFormulaNet
// below does (exact port of live_igex.py's igex_formula_net / build_intraday_gex.py).
// ---------------------------------------------------------------------------

export function isLongg(igexNet: number | null): boolean {
  return igexNet !== null && Number.isFinite(igexNet) && igexNet > 0
}

const GEX_R_DEFAULT = 0.05
const GEX_T_FLOOR = 5.0 / (365.0 * 24.0 * 60.0) // 5 minutes, in years
const GEX_SESSION_OPEN_MIN = 570 // 09:30 ET minute-of-day
const GEX_SESSION_LEN_MIN = 390 // 09:30-16:00 ET

function normPdf(x: number): number {
  return Math.exp(-0.5 * x * x) / Math.sqrt(2.0 * Math.PI)
}

export type GexRow = {
  strike: number
  iv: number
  callOi: number
  putOi: number
  /** Calendar days to expiration, as of the as-of date (not yet minute-fractioned). */
  dteCalendarDays: number
}

/**
 * Exact port of live_igex.py's igex_formula_net / build_intraday_gex.py's
 * per-minute net GEX sum: dte 0..60, prior-session OI held fixed, r=0.05, no
 * dividend term, T floored at 5 minutes. `ivs` are floored at 1e-4 exactly as
 * the Python `np.maximum(ivs, 1e-4)` does.
 */
export function igexFormulaNet(
  spot: number,
  rows: GexRow[],
  modOfDay: number,
  r: number = GEX_R_DEFAULT,
  tFloor: number = GEX_T_FLOOR,
): number {
  const S = spot
  const frac = Math.min(Math.max((modOfDay - GEX_SESSION_OPEN_MIN) / GEX_SESSION_LEN_MIN, 0), 1)
  let net = 0
  for (const row of rows) {
    const K = row.strike
    const iv = Math.max(row.iv, 1e-4)
    const T = Math.max((row.dteCalendarDays - frac) / 365.0, tFloor)
    const sq = Math.sqrt(T)
    const d1 = (Math.log(S / K) + (r + 0.5 * iv * iv) * T) / (iv * sq)
    const gamma = normPdf(d1) / (S * iv * sq)
    const scale = 100.0 * S * S * 0.01
    net += gamma * row.callOi * scale - gamma * row.putOi * scale
  }
  return net
}

// ---------------------------------------------------------------------------
// D2 regime brain: depth-2 CART over 7 features, refit monthly on PRIOR
// band-eligible days only (>=40 else fall back to R0/rule 0 — today's live
// behavior), predicting R1-pnl > R0-pnl. Hand-rolled to match sklearn's
// DecisionTreeClassifier(max_depth=2, criterion='gini') on a binary target:
// best Gini-impurity split per node, same tie-break (first feature index,
// first threshold found) as sklearn's deterministic scan order.
// ---------------------------------------------------------------------------

export type D2Features = {
  vixLevel: number
  vix1yPct: number
  vix20dChg: number
  tsRatioL: number
  ret20: number
  ret60: number
  above50dma: number
}

export const D2_FEATURE_ORDER: (keyof D2Features)[] = [
  'vixLevel', 'vix1yPct', 'vix20dChg', 'tsRatioL', 'ret20', 'ret60', 'above50dma',
]

export type D2TrainRow = { features: D2Features; label: 0 | 1 }

type SplitNode = { featureIdx: number; threshold: number; left: TreeNode; right: TreeNode }
type LeafNode = { predict: 0 | 1 }
type TreeNode = SplitNode | LeafNode
export type D2Tree = TreeNode

function gini(labels: (0 | 1)[]): number {
  const n = labels.length
  if (n === 0) return 0
  const p1 = labels.filter((l) => l === 1).length / n
  const p0 = 1 - p1
  return 1 - p0 * p0 - p1 * p1
}

function majorityLabel(labels: (0 | 1)[]): 0 | 1 {
  const ones = labels.filter((l) => l === 1).length
  return ones * 2 > labels.length ? 1 : 0
}

/** Best (featureIdx, threshold) split minimizing weighted Gini, scanning
 *  features in D2_FEATURE_ORDER and candidate thresholds (midpoints between
 *  sorted-unique values) in ascending order — first-found tie-break, matching
 *  sklearn's deterministic best-first scan for a small dense dataset. */
function bestSplit(X: number[][], y: (0 | 1)[]): { featureIdx: number; threshold: number } | null {
  const n = X.length
  if (n < 2) return null
  const parentGini = gini(y)
  let best: { featureIdx: number; threshold: number; score: number } | null = null
  for (let f = 0; f < D2_FEATURE_ORDER.length; f++) {
    const vals = Array.from(new Set(X.map((row) => row[f]))).sort((a, b) => a - b)
    for (let i = 0; i < vals.length - 1; i++) {
      const thr = (vals[i] + vals[i + 1]) / 2
      const leftY: (0 | 1)[] = []
      const rightY: (0 | 1)[] = []
      for (let r = 0; r < n; r++) (X[r][f] <= thr ? leftY : rightY).push(y[r])
      if (leftY.length === 0 || rightY.length === 0) continue
      const weighted = (leftY.length / n) * gini(leftY) + (rightY.length / n) * gini(rightY)
      const gain = parentGini - weighted
      if (gain <= 1e-12) continue
      if (!best || weighted < best.score - 1e-15) {
        best = { featureIdx: f, threshold: thr, score: weighted }
      }
    }
  }
  return best ? { featureIdx: best.featureIdx, threshold: best.threshold } : null
}

function buildNode(X: number[][], y: (0 | 1)[], depth: number, maxDepth: number): TreeNode {
  if (depth >= maxDepth || new Set(y).size <= 1) return { predict: majorityLabel(y) }
  const split = bestSplit(X, y)
  if (!split) return { predict: majorityLabel(y) }
  const leftIdx: number[] = []
  const rightIdx: number[] = []
  X.forEach((row, i) => (row[split.featureIdx] <= split.threshold ? leftIdx : rightIdx).push(i))
  const left = buildNode(leftIdx.map((i) => X[i]), leftIdx.map((i) => y[i]), depth + 1, maxDepth)
  const right = buildNode(rightIdx.map((i) => X[i]), rightIdx.map((i) => y[i]), depth + 1, maxDepth)
  return { featureIdx: split.featureIdx, threshold: split.threshold, left, right }
}

function featuresToVec(f: D2Features): number[] {
  return D2_FEATURE_ORDER.map((k) => f[k])
}

/**
 * Trains a depth-2 CART. Returns null if fewer than `minSamples` rows have
 * fully-finite features, or the label has no variance — matching
 * signal_on_flame_spark.py's run_d2 fallback-to-R0 conditions exactly
 * (`prior_mask.sum() >= 40` and `len(np.unique(ytr[valid])) > 1`).
 */
export function trainDepth2Tree(rows: D2TrainRow[], minSamples = 40): D2Tree | null {
  const valid = rows.filter((r) => featuresToVec(r.features).every((v) => Number.isFinite(v)))
  if (valid.length < minSamples) return null
  const y = valid.map((r) => r.label)
  if (new Set(y).size <= 1) return null
  const X = valid.map((r) => featuresToVec(r.features))
  return buildNode(X, y, 0, 2)
}

/** Predicts 0 (R0, today's live rule) or 1 (R1, BEST) for one day's features.
 *  Any non-finite feature fails closed to 0 (R0 — unchanged behavior). */
export function predictDepth2Tree(tree: D2Tree, features: D2Features): 0 | 1 {
  const vec = featuresToVec(features)
  if (!vec.every((v) => Number.isFinite(v))) return 0
  let node: TreeNode = tree
  for (let i = 0; i < 10; i++) {
    if ('predict' in node) return node.predict
    node = vec[node.featureIdx] <= node.threshold ? node.left : node.right
  }
  return 0
}

// ---------------------------------------------------------------------------
// D1 trailing-winner (SPARK relaxed band): rule with the best total pnl over
// the PRIOR 60 band-eligible days (what each rule would have done that day).
// Ties -> R0 (lowest index wins, matches np.argmax's first-max tie-break).
// Rules: 0=R0 prior-SPY-up, 1=R1 BEST, 2=R2 both, 3=R3 skip.
// ---------------------------------------------------------------------------

export type RulePnls = [number, number, number, number] // [R0, R1, R2, R3] hypothetical pnl for one day

/** `priorRulePnls` = the trailing window (already trimmed to <=60, oldest-
 *  first-or-any-order — only the sum matters) of PRIOR band-eligible days'
 *  hypothetical [R0,R1,R2,R3] pnl. Needs >=20 prior days else falls back to R0. */
export function pickTrailingWinner(priorRulePnls: RulePnls[], minPrior = 20): 0 | 1 | 2 | 3 {
  if (priorRulePnls.length < minPrior) return 0
  const totals: [number, number, number, number] = [0, 0, 0, 0]
  for (const day of priorRulePnls) for (let r = 0; r < 4; r++) totals[r] += day[r]
  let bestIdx: 0 | 1 | 2 | 3 = 0
  let bestVal = totals[0]
  for (let r = 1; r < 4; r++) {
    if (totals[r] > bestVal) { bestVal = totals[r]; bestIdx = r as 0 | 1 | 2 | 3 }
  }
  return bestIdx
}

// ---------------------------------------------------------------------------
// S1 signal-days filter: keep the day only if CALM or LONGG holds.
// ---------------------------------------------------------------------------

export function s1Admits(isCalm: boolean, isLongg: boolean): boolean {
  return isCalm || isLongg
}

// ---------------------------------------------------------------------------
// FLAME v2 14:05 ET SPY 0DTE CALL credit spread — strike selection, sizing
// tier, and the mirrored assignment guard. All pure/deterministic; no I/O.
// ---------------------------------------------------------------------------

/** Short call = nearest strike to spot+2 (round-to-nearest-dollar, matching
 *  the put side's `Math.round(spot - otmAbs)` convention). Long = short+2. */
export function callSpreadStrikes(spot: number, otmAbs = 2, width = 2): { short: number; long: number } {
  const short = Math.round(spot + otmAbs)
  return { short, long: short + width }
}

/** Sizing tier per spec: 3 contracts if CALM AND LONGG, 1 if exactly one,
 *  0 if neither. Multiplies the host FLAME base-contract count for the day. */
export function callSpreadTier(isCalm: boolean, isLongg: boolean): 0 | 1 | 3 {
  if (isCalm && isLongg) return 3
  if (isCalm || isLongg) return 1
  return 0
}

export function callSpreadContracts(isCalm: boolean, isLongg: boolean, flameBaseContracts: number): number {
  return callSpreadTier(isCalm, isLongg) === 0 ? 0 : callSpreadTier(isCalm, isLongg) * Math.max(0, flameBaseContracts)
}

/** Mirrors FLAME's own put-side assignment guard for the call leg: close if
 *  spot has risen to within `buffer` of the short call strike (spot >=
 *  shortStrike - buffer), since a short call goes in-the-money as spot RISES
 *  (the put guard closes as spot FALLS toward its short strike). */
export function callGuardShouldClose(spot: number, shortStrike: number, buffer: number): boolean {
  return spot >= shortStrike - buffer
}
