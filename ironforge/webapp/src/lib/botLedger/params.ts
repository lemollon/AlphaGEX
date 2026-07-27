/**
 * Bot Ledger — URL parameter handling.
 *
 * PURE, so the independence guarantee ("the period control never touches the
 * bot filter, and vice versa") is a unit test rather than a manual click-test.
 */

import {
  LEDGER_BOT_FILTERS,
  LEDGER_PERIODS,
  type LedgerBotFilter,
  type LedgerPeriod,
} from '@/lib/bot-ledger/constants'

export const DEFAULT_PERIOD: LedgerPeriod = '30d'
export const DEFAULT_BOT: LedgerBotFilter = 'all'

type RawParam = string | string[] | undefined

/** Next hands back an array when a param is repeated; take the first. */
function first(raw: RawParam): string | undefined {
  return Array.isArray(raw) ? raw[0] : raw
}

export function parsePeriod(raw: RawParam): LedgerPeriod {
  const v = first(raw)
  return (LEDGER_PERIODS as readonly string[]).includes(v ?? '')
    ? (v as LedgerPeriod)
    : DEFAULT_PERIOD
}

export function parseBotFilter(raw: RawParam): LedgerBotFilter {
  const v = first(raw)
  return (LEDGER_BOT_FILTERS as readonly string[]).includes(v ?? '')
    ? (v as LedgerBotFilter)
    : DEFAULT_BOT
}

/**
 * Transform a search string, touching ONLY the keys present in `patch`.
 *
 * This is what makes the two controls structurally independent: the period
 * control passes `{ period }` and the bot filter passes `{ bot }`, so neither
 * can clobber the other's parameter — and unrelated params (utm_*, ref) survive
 * untouched. Defaults are omitted so shared links stay clean.
 */
export function nextSearch(
  currentSearch: string,
  patch: { period?: LedgerPeriod; bot?: LedgerBotFilter },
): string {
  const sp = new URLSearchParams(currentSearch)

  if (patch.period !== undefined) {
    if (patch.period === DEFAULT_PERIOD) sp.delete('period')
    else sp.set('period', patch.period)
  }
  if (patch.bot !== undefined) {
    if (patch.bot === DEFAULT_BOT) sp.delete('bot')
    else sp.set('bot', patch.bot)
  }

  const s = sp.toString()
  return s ? `?${s}` : ''
}

export const PERIOD_LABEL: Record<LedgerPeriod, string> = {
  '7d': 'Last 7 days',
  '30d': 'Last 30 days',
}

export const PERIOD_CAPTION: Record<LedgerPeriod, string> = {
  '7d': 'LAST 7 DAYS',
  '30d': 'LAST 30 DAYS',
}

export const PERIOD_SPOKEN: Record<LedgerPeriod, string> = {
  '7d': 'last 7 days',
  '30d': 'last 30 days',
}

export const BOT_FILTER_LABEL: Record<LedgerBotFilter, string> = {
  all: 'All bots',
  spark: 'Spark',
  flame: 'Flame',
}
