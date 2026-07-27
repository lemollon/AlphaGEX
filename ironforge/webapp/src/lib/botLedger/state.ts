/**
 * Bot Ledger — the card state machine.
 *
 * PURE. One function decides every card state, so all of them are covered by a
 * table-driven test with no DOM.
 */

import { LEDGER_BOTS, type LedgerBot } from '@/lib/bot-ledger/constants'
import type { BotSummary, SummaryResponse } from '@/lib/bot-ledger/types'

/** A card is stale once its snapshot is older than this. */
export const STALE_AFTER_MS = 15 * 60_000

export type CardState =
  | { kind: 'loading'; bot: LedgerBot }
  | { kind: 'ready'; bot: LedgerBot; summary: BotSummary }
  | { kind: 'empty'; bot: LedgerBot; summary: BotSummary }
  | { kind: 'stale'; bot: LedgerBot; summary: BotSummary; generatedAt: string }
  | { kind: 'error'; bot: LedgerBot }

export type LedgerView =
  /** Reconciliation failed — suppress BOTH cards. Beats every other state. */
  | { kind: 'suppressed' }
  /** The request failed and there is nothing cached to fall back on. */
  | { kind: 'failed' }
  | { kind: 'cards'; cards: CardState[]; busy: boolean }

export interface DeriveInput {
  data: SummaryResponse | undefined
  error: Error | undefined
  isRefreshing: boolean
  now: number
  staleAfterMs?: number
}

export function deriveLedgerView(input: DeriveInput): LedgerView {
  const { data, error, isRefreshing, now } = input
  const staleAfter = input.staleAfterMs ?? STALE_AFTER_MS

  // Suppression is checked FIRST: if the aggregate does not reconcile, no card
  // may render, however healthy an individual bot looks.
  if (data && data.reconciled === false) return { kind: 'suppressed' }

  if (!data) {
    if (error) return { kind: 'failed' }
    return {
      kind: 'cards',
      cards: LEDGER_BOTS.map((bot) => ({ kind: 'loading', bot }) as CardState),
      busy: false,
    }
  }

  // Values on screen beat an error: a failed revalidation renders stale, never
  // an error panel, and never a blanked card.
  const generatedAt = data.generated_at
  const age = Date.parse(generatedAt)
  const isStale =
    error !== undefined || (Number.isFinite(age) && now - age > staleAfter)

  const cards: CardState[] = LEDGER_BOTS.map((bot) => {
    const summary = data.bots.find((b) => b.bot === bot)
    // A bot missing from the payload is the only reachable partial failure:
    // one card errors, the other still renders.
    if (!summary) return { kind: 'error', bot }
    if (isStale) return { kind: 'stale', bot, summary, generatedAt }
    if (summary.closed_trades === 0) return { kind: 'empty', bot, summary }
    return { kind: 'ready', bot, summary }
  })

  return { kind: 'cards', cards, busy: isRefreshing }
}

/** True when the card should render its KPI body rather than a placeholder. */
export function hasWindowData(state: CardState): boolean {
  return (
    (state.kind === 'ready' || state.kind === 'stale') &&
    state.summary.closed_trades > 0
  )
}

/** An aborted fetch is not a failure — it is us cancelling a superseded request. */
export function isAbortError(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false
  const name = (err as { name?: unknown }).name
  return name === 'AbortError' || name === 'TimeoutError'
}
