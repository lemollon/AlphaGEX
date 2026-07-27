import type { LedgerBot } from '@/lib/bot-ledger/constants'

/**
 * Shared card geometry and type scale.
 *
 * CARD_MIN_H is used verbatim by the KPI card, the skeleton and the error
 * panel. That single shared value is what holds CLS at zero across every state
 * transition — if they drift, the page jumps when data lands.
 */
export const CARD_MIN_H = 'min-h-[520px]'

export const CARD_SHELL =
  'relative flex h-full flex-col overflow-hidden rounded-2xl border bg-forge-card'

/** Metric labels. gray-400 (7.15:1), not the gray-500 marketing idiom (3.76:1). */
export const LABEL = 'text-[10px] font-semibold uppercase tracking-wider text-gray-400'
export const VALUE = 'font-mono text-sm tabular-nums text-gray-100'

/**
 * Bot accent. Tailwind remaps blue/sky/orange to stone (gray), so identity
 * colour must come from the CSS variables in globals.css, never a colour class.
 */
export const BOT_ACCENT: Record<LedgerBot, { border: string; cssVar: string; glow: string }> = {
  spark: {
    border: 'border-spark/40',
    cssVar: 'var(--bot-spark)',
    glow: 'rgba(59, 130, 246, 0.4)',
  },
  flame: {
    border: 'border-amber-500/40',
    cssVar: 'var(--bot-flame)',
    glow: 'rgba(232, 83, 31, 0.4)',
  },
}

/** Positive / negative text colours (emerald and red survive the remap). */
export const POS_TEXT = 'text-emerald-400'
export const NEG_TEXT = 'text-red-400'

export function signClass(value: string | null | undefined): string {
  if (value === null || value === undefined) return 'text-gray-400'
  const n = Number(value)
  if (!Number.isFinite(n) || Math.abs(n) < 0.005) return 'text-gray-300'
  return n > 0 ? POS_TEXT : NEG_TEXT
}
