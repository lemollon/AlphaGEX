/**
 * Light / Dark / System appearance (APP-appearance).
 *
 * Pure token math, deliberately kept out of ThemeContext.tsx: vitest.config.ts only
 * collects `src/**\/*.test.ts` (no renderer, see its own comment), so anything that
 * needs a unit test has to live in a plain .ts file. This is that file — palette
 * resolution and the dark<->light tone bridge are both pure functions with no React
 * or react-native import.
 *
 * DARK is pixel-identical to theme/tokens.ts's `color` — it is the brand default and
 * ships unchanged today. LIGHT is a new palette: near-white surfaces, near-black text,
 * the same wordmark (unchanged), the design's per-theme accent orange (binding 2026-10
 * decision, see tokens.ts), and darkened pos/neg/warn/spark/flame so text painted in
 * those colours still clears WCAG AA (4.5:1) on a white card. See the contrast numbers
 * inline below — computed with the standard WCAG relative-luminance formula against
 * #FFFFFF (and, for accentText, against --accent-soft, the worst-case tinted badge
 * background it also renders on).
 */
import { color as darkColor } from './tokens'

export type Scheme = 'light' | 'dark'
export type AppearancePreference = 'system' | 'light' | 'dark'

export interface ColorTokens {
  bg: string
  card: string
  surface: string
  surfaceRaised: string
  border: string
  muted: string
  textMuted: string
  wordmark: string
  accent: string
  /** Deeper/brighter accent for small text and text links — see tokens.ts and the
   *  per-theme contrast notes below. Fills/buttons/icons/chart-strokes/pills/
   *  progress-bars use `accent` itself, never this. */
  accentText: string
  spark: string
  flame: string
  ember: string
  pos: string
  positive: string
  neg: string
  negative: string
  warn: string
  warning: string
  text: string
  textDim: string
  tabBar: string
}

/** Brand default, unchanged. Every value here matches theme/tokens.ts's `color`. */
export const dark: ColorTokens = {
  bg: darkColor.bg,
  card: darkColor.card,
  surface: darkColor.card,
  surfaceRaised: '#1F1F24',
  border: darkColor.border,
  muted: darkColor.muted,
  textMuted: darkColor.textDim,
  wordmark: darkColor.wordmark,
  accent: darkColor.accent,
  accentText: darkColor.accentText,
  spark: darkColor.spark,
  flame: darkColor.flame,
  ember: darkColor.ember,
  pos: darkColor.pos,
  positive: darkColor.pos,
  neg: darkColor.neg,
  negative: darkColor.neg,
  warn: darkColor.warn,
  warning: darkColor.warn,
  text: darkColor.text,
  textDim: darkColor.textDim,
  tabBar: darkColor.card,
}

/**
 * Light palette. Contrast ratios below are vs #FFFFFF (the card surface text most of
 * these render on); all text-weight tokens clear 4.5:1, all decorative/border tokens
 * are exempt (WCAG 1.4.11 non-text).
 *   pos     #0A8548  4.71:1     neg   #D93025  4.77:1     warn  #9C6B14  4.64:1
 *   spark   #2563EB  5.17:1     flame #B33900  6.00:1     ember #B52FE0  4.72:1
 *   text    #111114 18.85:1     textDim/muted #6E6E78  5.04:1
 *   accentText #BB4B0A  5.09:1 vs white, 4.57:1 vs --accent-soft (the worst case
 *     tinted-badge background it also has to clear — see tokens.ts)
 *
 * bg/card/border updated 2026-10 to the 10.4 redesign's light surface tokens
 * (--bg-2/--bg/--line, handoff/ironforge-10.4-design-spec.md §1) — those three are
 * decorative, not text, so no contrast re-check was needed. spark/flame/pos/neg/warn
 * stay at their EXISTING contrast-tuned hexes rather than the design doc's raw light
 * tokens (#1f7ae0/#f0600d/#0f9f6e/#d23a2a/#b7791f) — those fail 4.5:1 on a white card
 * (4.27/3.29/3.38/—/3.64 measured), so adopting them verbatim would regress the WCAG
 * AA guarantee below. wordmark stays locked per the note above. `accent` ITSELF is
 * the design's exact light-mode hex (#F0600D, binding 2026-10 decision, see
 * tokens.ts) — it only clears ~3.29:1 against white and is not expected to; fills,
 * buttons, icons, chart strokes, pills and progress bars use it regardless, and
 * `accentText` (a flat 80%-value darkening of the same hue) is the token that
 * carries the AA guarantee for small text and text links. muted/textMuted collapse
 * onto the design's single --muted token, which happens to clear 4.5:1.
 */
export const light: ColorTokens = {
  bg: '#F6F6F7',
  card: '#FFFFFF',
  surface: '#FFFFFF',
  surfaceRaised: '#FFFFFF',
  border: '#E7E7EA',
  muted: '#6E6E78',
  textMuted: '#6E6E78',
  wordmark: '#FD5301',
  accent: '#F0600D',
  accentText: '#BB4B0A',
  spark: '#2563EB',
  flame: '#B33900',
  ember: '#B52FE0',
  pos: '#0A8548',
  positive: '#0A8548',
  neg: '#D93025',
  negative: '#D93025',
  warn: '#9C6B14',
  warning: '#9C6B14',
  text: '#111114',
  textDim: '#5B5B63',
  tabBar: '#FFFFFF',
}

export function getPalette(scheme: Scheme): ColorTokens {
  return scheme === 'light' ? light : dark
}

/**
 * Resolve an `AppearancePreference` + the OS's reported scheme into the scheme the
 * app should actually render. 'system' with an unknown/null OS scheme falls back to
 * 'dark' (brand default), never to 'light' — a device that can't report its scheme
 * must not silently look different from what shipped.
 */
export function resolveScheme(
  preference: AppearancePreference,
  systemScheme: Scheme | null | undefined,
): Scheme {
  if (preference === 'light' || preference === 'dark') return preference
  return systemScheme === 'light' ? 'light' : 'dark'
}

/**
 * Reverse lookup, DARK hex -> LIGHT hex, built once from the two palettes above.
 *
 * Some values in this codebase are produced by plain functions that run outside a
 * component (card-stats.ts, alerts/banner.ts) and always return a DARK-canonical hex
 * — that is what their existing tests assert (`color.pos`, `color.neg`, ...) and
 * changing their return type would mean touching every call site and test for no
 * reason. Instead the render layer — the one place that knows the active scheme —
 * calls `resolveTone()` on whatever hex it was handed. In dark scheme this is the
 * identity function; in light scheme it swaps the dark-canonical value for its light
 * equivalent. Any hex that is not a recognized dark-canonical token (e.g. an
 * already-resolved `theme.colors.x` value, or a one-off literal) passes through
 * unchanged, so this is safe to call on anything.
 *
 * NOTE: dark.accent, dark.accentText and dark.flame are all #FF7124 (the design's own
 * dark --accent and --flame share one hex, tokens.ts) — this map can only keep one
 * light-side winner per duplicated dark hex, and `flame` wins since it's declared last
 * in ColorTokens. Nothing in this codebase feeds `color.accent`/`color.accentText`
 * through resolveTone (they're read directly off the active `getPalette(scheme)`
 * result, never off a dark-canonical function return), so this is not exercised —
 * don't add a resolveTone(dark.accent, ...) test/call expecting light.accent back.
 */
const LIGHT_FOR_DARK_HEX: Record<string, string> = {}
for (const key of Object.keys(dark) as (keyof ColorTokens)[]) {
  LIGHT_FOR_DARK_HEX[dark[key]] = light[key]
}

export function resolveTone(hex: string, scheme: Scheme): string {
  if (scheme === 'dark') return hex
  return LIGHT_FOR_DARK_HEX[hex] ?? hex
}
