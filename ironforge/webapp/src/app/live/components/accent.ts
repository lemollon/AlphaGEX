/**
 * Live-page accent theme. The whole Live surface takes the ACTIVE bot's identity
 * colour — blue for Spark, orange for Flame — not just the mascot. Semantic
 * colours (green gain / red loss, market-condition status) are NOT accents and
 * stay put; only brand chrome (headers, the trade icon, the "what's happening"
 * timeline, the equity line, the Pause button) switches here.
 *
 * Tailwind can't build class names dynamically, so every accent's classes are
 * spelled out as literals below.
 */

import type { LiveBot } from '@/lib/live/bots'
import { LIVE_BOT_ACCENT } from '@/lib/live/bots'
import { BOT_COLORS } from '@/lib/botColors'

export type Accent = 'spark' | 'flame'

export interface AccentTheme {
  /** section-header + small accent text ("LIVE TRADE", "Live") */
  text: string
  /** solid status dot / live-updates pip */
  dot: string
  /** icon chip: border + tinted fill + icon colour */
  chip: string
  /** timeline node once its step is done */
  stepDone: string
  /** timeline node for the current step (pulsing, ringed) */
  stepCurrent: string
  /** timeline connector line when active */
  line: string
  /** primary action button (Pause / Confirm) */
  button: string
  /** text input focus ring */
  focus: string
  /** recharts equity-line stroke (hex) */
  chartHex: string
  /** recharts area fill under the equity line */
  chartFill: string
}

export const ACCENT_THEME: Record<Accent, AccentTheme> = {
  spark: {
    text: 'text-spark',
    dot: 'bg-spark',
    chip: 'border-spark/40 bg-spark/10 text-spark',
    stepDone: 'bg-spark/80',
    stepCurrent: 'animate-pulse bg-spark ring-4 ring-spark/25',
    line: 'bg-spark/60',
    button: 'bg-spark hover:bg-spark-dark',
    focus: 'focus:border-spark',
    chartHex: BOT_COLORS.spark, // #3b82f6
    chartFill: 'rgba(59,130,246,0.2)',
  },
  flame: {
    text: 'text-flame',
    dot: 'bg-flame',
    chip: 'border-flame/40 bg-flame/10 text-flame',
    stepDone: 'bg-flame/80',
    stepCurrent: 'animate-pulse bg-flame ring-4 ring-flame/25',
    line: 'bg-flame/60',
    button: 'bg-flame hover:bg-flame-dark',
    focus: 'focus:border-flame',
    chartHex: BOT_COLORS.flame, // #FF5500
    chartFill: 'rgba(255,85,0,0.2)',
  },
}

export function accentFor(bot: LiveBot): AccentTheme {
  return ACCENT_THEME[LIVE_BOT_ACCENT[bot]]
}
