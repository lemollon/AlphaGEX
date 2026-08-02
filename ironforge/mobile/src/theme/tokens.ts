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
  // Surfaces
  bg: '#0B0B0D',
  card: '#16161A',
  border: '#262629',
  muted: '#78716C',

  // Brand. The wordmark orange differs from the UI accent — Brand.tsx hardcodes
  // #FD5301 and calls it "the marketing accent"; #EE5A24 is amber-500, used for
  // interactive orange in the app chrome.
  wordmark: '#FD5301',
  accent: '#EE5A24',

  // Agent identity (customer-facing agents are SPARK and FLAME only).
  spark: '#3B82F6',
  flame: '#FF5500',

  // Semantic P&L
  pos: '#34D399',
  neg: '#F87171',
  warn: '#E0B23F',

  text: '#FFFFFF',
  textDim: '#A3A3A3',
} as const

/** Per-agent theming, mirroring live/components/accent.ts. */
export const agentColor: Record<string, string> = {
  spark: color.spark,
  spark2: '#60A5FA',
  flame: color.flame,
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

export const radius = { sm: 6, md: 10, lg: 14, pill: 999 } as const

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
