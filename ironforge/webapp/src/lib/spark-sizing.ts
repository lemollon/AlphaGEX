/**
 * SPARK's regime-conditional position sizing.
 *
 * Positive-gamma days carry roughly a third of the per-contract variance for a similar
 * mean (sd 33.6 vs 91.1, Brown-Forsythe p=0.0002 over n=1315), so contracts bought there
 * cost far less drawdown. 50% BP on positive / 20% on negative beat a flat 20% by +59%
 * at a slightly LOWER max drawdown across the same 1,315 trades.
 *
 * These lived as two hand-copied pairs — one in scanner.ts (the paper path), one inline
 * in tradier.ts (the production path) — under comments instructing the next person to
 * keep them in sync manually. They set how much real money goes into a trade, so a
 * silent divergence between the two paths is about the worst drift this codebase could
 * carry. One definition now; both paths import it.
 *
 * Applies to SPARK. Raising either number is a real-money risk change.
 */

/** Positive net GEX. */
export const SPARK_BP_CAP_POS = 0.50

/**
 * Negative net GEX — and the FAIL-SAFE for an unknown regime.
 *
 * A failed GEX read is not positive gamma. Unknown always takes the low cap, never the
 * high one, so a Tradier chain outage cannot size a trade up.
 */
export const SPARK_BP_CAP_NEG = 0.20

/**
 * The cap for a regime reading. `posGamma` must be TRUE only when a non-negative net GEX
 * was actually read — pass false for null/unknown.
 */
export function sparkRegimeBpCap(posGamma: boolean): number {
  return posGamma ? SPARK_BP_CAP_POS : SPARK_BP_CAP_NEG
}

/** Bots on the v2 regime-sizing path. Mirrors isSparkV2Sizing() in scanner.ts. */
export function isSparkV2SizingBot(name: string): boolean {
  return name === 'spark'
}
