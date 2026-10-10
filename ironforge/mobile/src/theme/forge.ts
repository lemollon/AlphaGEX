/**
 * IronForge 10.4 design tokens (handoff/ironforge-10.4-redesign.md,
 * handoff/ironforge-10.4-design-spec.md §1, CSS extracted to
 * handoff/ironforge-10.4-css/*.css).
 *
 * This module is the single named export for "the 10.4 design's colors/type/radii"
 * that the enrollment screens (/enroll/*) and the dashboard/home tab import from.
 * It does not fork a second theme system: color and type values are sourced from
 * theme/tokens.ts + theme/palette.ts (already updated to the 10.4 hexes — see the
 * comments there for the handful of light-mode colors kept at their pre-existing,
 * contrast-tuned values instead of the design doc's raw tokens). `forgeRadius` is
 * additive — the design's exact 12/8/999px scale, distinct from the legacy
 * `radius` export in tokens.ts where this task didn't need every call site moved.
 *
 * Design-doc token names (left) vs this app's names (right), for anyone cross-
 * referencing the CSS: --bg→card/surface, --bg-2→bg, --line→border, --fg→text,
 * --muted→muted/textMuted, --accent→accent (locked, see tokens.ts), --up→pos,
 * --down→neg, --warn→warn, --spark/--flame/--ember→spark/flame/ember.
 */
import { color as darkColor, radius as legacyRadius, type, font, space } from './tokens'
import { light as lightPalette, dark as darkPalette, type ColorTokens, type Scheme } from './palette'

export type ForgeColors = ColorTokens

/** Dark palette (brand default) — pixel-identical to theme/palette.ts's `dark`. */
export const forgeDark: ForgeColors = darkPalette

/** Light palette — pixel-identical to theme/palette.ts's `light`. */
export const forgeLight: ForgeColors = lightPalette

export function getForgeColors(scheme: Scheme): ForgeColors {
  return scheme === 'light' ? forgeLight : forgeDark
}

/**
 * Design-spec §1 "Radii / spacing / shape": cards 12px, inputs 8px, buttons/
 * chips/pills a full pill. Use this (not the legacy `radius` export) on any new
 * 10.4-restyled surface so the exact spec numbers are visible at the call site.
 */
export const forgeRadius = {
  card: 12,
  input: 8,
  pill: 999,
} as const

/** Card padding (§1: "Card padding 18px") and the section rhythm padding
 *  (§1: ".sec{padding-block:44px}") — the two spacing numbers the design calls
 *  out explicitly that don't already have a home in theme/tokens.ts's `space`. */
export const forgeSpacing = {
  cardPadding: 18,
  sectionBlock: 44,
} as const

/**
 * Type scale. The design's font stack (Geist / Geist Mono / Barlow Condensed) is
 * not loaded in the app — app/_layout.tsx loads Oswald (display) and Inter
 * (body), the pair every other screen already uses — so this re-exports the
 * existing `type`/`font` tokens rather than introducing a second, unloaded font
 * family. The size/line-height scale (hero 40/46, title 26/32, section 13/18 at
 * .14em tracking, body 15/21, label 12/16) already matches the spec's rhythm.
 */
export const forgeType = type
export const forgeFont = font
export const forgeSpace = space

/** Re-exported for call sites that want one import for "everything 10.4". */
export const forgeAccent = darkColor.accent
/** Deeper/brighter accent for small text and text links — see tokens.ts. */
export const forgeAccentText = darkColor.accentText
export { legacyRadius }
