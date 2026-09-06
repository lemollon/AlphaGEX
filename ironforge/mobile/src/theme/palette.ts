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
 * the same wordmark/accent orange (unchanged by request), and darkened pos/neg/warn/
 * spark/flame so text painted in those colours still clears WCAG AA (4.5:1) on a white
 * card. See the contrast numbers inline below — computed with the standard WCAG
 * relative-luminance formula against #FFFFFF.
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
  spark: string
  flame: string
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
  spark: darkColor.spark,
  flame: darkColor.flame,
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
 *   spark   #2563EB  5.17:1     flame #B33900  6.00:1
 *   text    #111114 18.85:1     textDim/muted #5B5B63 6.73:1 / #6B6560 5.74:1
 */
export const light: ColorTokens = {
  bg: '#F7F7F8',
  card: '#FFFFFF',
  surface: '#FFFFFF',
  surfaceRaised: '#FFFFFF',
  border: '#E2E2E6',
  muted: '#6B6560',
  textMuted: '#5B5B63',
  wordmark: '#FD5301',
  accent: '#EE5A24',
  spark: '#2563EB',
  flame: '#B33900',
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
 */
const LIGHT_FOR_DARK_HEX: Record<string, string> = {}
for (const key of Object.keys(dark) as (keyof ColorTokens)[]) {
  LIGHT_FOR_DARK_HEX[dark[key]] = light[key]
}

export function resolveTone(hex: string, scheme: Scheme): string {
  if (scheme === 'dark') return hex
  return LIGHT_FOR_DARK_HEX[hex] ?? hex
}
