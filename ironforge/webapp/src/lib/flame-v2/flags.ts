/**
 * FLAME v2 / SPARK v2 feature flags. Every flag is a per-bot, three-state
 * switch: 'off' | 'shadow' | 'live'. Default for every flag below is
 * 'shadow' per the build spec: compute + log the decision, change NOTHING
 * about orders. 'off' additionally skips the computation (useful to fully
 * silence a sleeve, e.g. if the ThetaData proxy is flaky and the log noise
 * isn't wanted). 'live' is the only mode that is allowed to change admission
 * or place an order — see each module's own file for exactly what 'live'
 * does and does NOT do yet (search for "LIVE MODE" comments).
 *
 * 🚨 Read before flipping anything to 'live' on a real account: PR description
 * "Go-live checklist" section has the full pre-arm sequence. These env vars
 * are Render dashboard settings — this module only reads them, it never sets
 * them, and nothing in this repo changes a Render env var for you.
 */

export type FlagMode = 'off' | 'shadow' | 'live'

function readMode(envVar: string, fallback: FlagMode = 'shadow'): FlagMode {
  const raw = (process.env[envVar] ?? '').trim().toLowerCase()
  if (raw === 'off' || raw === 'shadow' || raw === 'live') return raw
  return fallback
}

/** FLAME D2 regime brain — replaces the static "prior-SPY-up" admission rule
 *  for the (0.80, 0.925] relaxed VIX band with the monthly-refit depth-2 tree
 *  (PREREG_dynamic_relax_flame_spark.md D2, which PASSED both eras for FLAME). */
export function flameRegimeBrainMode(): FlagMode {
  return readMode('FLAME_V2_REGIME_BRAIN_MODE')
}

/** FLAME 14:05 ET SPY 0DTE CALL credit spread (RESULT_flame_product.md P3:
 *  FLAME D2 brain + call spread, the PASS/PICK combination). */
export function flameCallSpreadMode(): FlagMode {
  return readMode('FLAME_V2_CALL_SPREAD_MODE')
}

/** SPARK D1 trailing-60-winner for its own relaxed band (0.90, 0.975]
 *  (PREREG_dynamic_relax_flame_spark.md D1, which PASSED both eras for SPARK). */
export function sparkTrailingBandMode(): FlagMode {
  return readMode('SPARK_V2_TRAILING_BAND_MODE')
}

/** SPARK S1 signal-days filter (CALM or LONGG) applied to SPARK's existing
 *  core gate (<=0.90) admissions (PREREG_streak_versions_flame_spark.md S1). */
export function sparkSignalFilterMode(): FlagMode {
  return readMode('SPARK_V2_SIGNAL_FILTER_MODE')
}

export function isEnabled(mode: FlagMode): boolean {
  return mode !== 'off'
}

export function isLive(mode: FlagMode): boolean {
  return mode === 'live'
}
