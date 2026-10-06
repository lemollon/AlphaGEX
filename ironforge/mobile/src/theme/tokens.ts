/**
 * IronForge mobile design tokens (APP-002).
 *
 * Ported as RAW HEX from three files in the webapp, deliberately not from class names:
 *   - tailwind.config.ts  (forge.*, flame, spark, the amber remap)
 *   - src/app/globals.css (--bot-*, --pos/--neg/--warn)
 *   - src/lib/botColors.ts
 *
 * ⚠️ THE TRAP: the web Tailwind config remaps blue, sky, cyan, indigo, violet, purple,
 * fuchsia, pink, teal, lime AND orange to `stone` (gray). So on the web `text-blue-500`
 * renders GRAY. React Native has no such remap, so copying a value by reading a web
 * class name gives you the wrong colour — Spark would come out gray. Always resolve
 * through botColors.ts / accent.ts and copy the hex, never the class.
 */

export const color = {
  // Surfaces — snapped 2026-10 to the design CSS's exact dark :root values
  // (ironforge-10.4-css/ironforge-app.css --bg/--card/--line) rather than the
  // near-identical hand-picked hexes this used to carry. Pure surface colour,
  // not text — no AA re-check needed (WCAG 1.4.11 non-text contrast only).
  bg: '#0B0B0D',
  card: '#121215',
  border: '#24242A',
  muted: '#9A9AA5',

  // Brand. `wordmark` (#FD5301, Brand.tsx's web twin hardcodes the same hex) is a
  // separate, unused-in-render token kept for parity with the web palette; Brand.tsx's
  // actual "FORGE" text and the interactive orange throughout app chrome both read
  // `accent`. Previously #EE5A24 (amber-500), locked theme-invariant on the theory that
  // the design doc's own --accent (#f0600d light / #ff7124 dark) shouldn't be
  // relitigated. Leron lifted that lock 2026-10: `accent` now carries the design's
  // EXACT per-theme hex for fills/buttons/icons/chart-strokes/pills/progress-bars.
  // `accentText` is a second, deeper-value token for small text and text links —
  // in LIGHT mode --accent only clears ~2.95-3.29:1 against light surfaces (fails
  // WCAG AA 4.5:1), so light.accentText darkens it; in this DARK palette --accent
  // already clears 6-7:1 against every dark surface it renders on, so accentText
  // stays identical. See palette.ts for the per-theme split and contrast numbers.
  wordmark: '#FD5301',
  accent: '#FF7124',
  accentText: '#FF7124',

  // Agent identity. Spark/Flame updated to the 10.4 dark tokens (--spark/--flame).
  // Ember joins as the third customer-facing agent (10.4 §3: free, 1 per person,
  // $500–$2,000 capital) — its internal strategy name "REFLEX" is never shown here
  // or anywhere in the app; customers see only "Ember".
  spark: '#5AA6FF',
  flame: '#FF7124',
  ember: '#DD63FF',

  // Semantic P&L — 10.4 dark tokens (--up/--down/--warn).
  pos: '#2FCF93',
  neg: '#FF6B5A',
  warn: '#E0A630',

  text: '#F2F2F4',
  textDim: '#A3A3A3',
} as const

/** Per-agent theming, mirroring live/components/accent.ts. */
export const agentColor: Record<string, string> = {
  spark: color.spark,
  flame: color.flame,
  ember: color.ember,
}

export function agentAccent(bot: string): string {
  return agentColor[bot] ?? color.accent
}

/** Green for gains, red for losses — never the reverse, never agent colour. */
export function pnlColor(n: number | null | undefined): string {
  if (n == null) return color.textDim
  return n >= 0 ? color.pos : color.neg
}

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const

// 10.4 redesign (handoff/ironforge-10.4-design-spec.md §1 "Radii / spacing / shape"):
// cards 12px, inputs 8px, buttons/chips/pills full pill. sm/lg moved from 6/14 to
// match; md (10) is kept for the handful of one-off chrome elements (code-entry
// boxes, the small secondary "Try again" button) the spec doesn't name.
export const radius = { sm: 8, md: 10, lg: 12, pill: 999 } as const

export const font = {
  // Oswald is the display/condensed face (the wordmark and numerics);
  // Inter is body. Loaded in app/_layout.tsx.
  display: 'Oswald_600SemiBold',
  body: 'Inter_400Regular',
  bodyMedium: 'Inter_500Medium',
  bodyBold: 'Inter_700Bold',
} as const

export const type = {
  hero: { fontSize: 40, lineHeight: 46 },
  title: { fontSize: 26, lineHeight: 32 },
  section: { fontSize: 13, lineHeight: 18, letterSpacing: 1.1 },
  body: { fontSize: 15, lineHeight: 21 },
  label: { fontSize: 12, lineHeight: 16 },
} as const

/** Outcome badge colours — must match HistoryTrade.outcome_kind from the API. */
export const outcomeColor: Record<string, string> = {
  profit: color.pos,
  auto: color.spark,
  stop: color.neg,
  manual: color.textDim,
  expired: color.textDim,
  other: color.textDim,
}
