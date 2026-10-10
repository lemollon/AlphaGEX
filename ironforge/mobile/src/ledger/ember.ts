/**
 * Ember's own closed trades (PR #3177, GET /api/ember/trades), adapted into the
 * same HistoryTrade shape the rest of the Ledger tab already renders — so the
 * day-grouped row layout, search and the trade sheet work identically whether
 * a row came from a {bot}_positions table or from Ember's REFLEX sync.
 *
 * Ember has no close_reason/outcome taxonomy of its own (reflex_sync.py never
 * writes one — see ember-trades.ts on web), so the outcome tag here is the one
 * honest signal available: the sign of pnl. This is NOT the same "Profit
 * target / Auto close / Stop loss" taxonomy FLAME/SPARK use (exit-reasons.ts)
 * — it is a strictly weaker, pnl-sign-only approximation, flagged as such in
 * the badge label rather than borrowing a label that implies a reason this
 * data doesn't carry.
 */
import type { EmberTradeRow, HistoryTrade, OutcomeKind } from '@/api/types'

const CT_ZONE = 'America/Chicago'

function ctDate(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: CT_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(d)
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '00'
  return `${get('year')}-${get('month')}-${get('day')}`
}

function ctTime(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return new Intl.DateTimeFormat('en-US', {
    timeZone: CT_ZONE,
    hour: 'numeric',
    minute: '2-digit',
  }).format(d)
}

function num(v: string | null): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function outcomeOf(pnl: number): { label: string; kind: OutcomeKind } {
  if (pnl > 0) return { label: 'Closed in profit', kind: 'profit' }
  if (pnl < 0) return { label: 'Closed at a loss', kind: 'stop' }
  return { label: 'Closed flat', kind: 'other' }
}

/** Only CLOSED rows — an open Ember position has no realized pnl/close time
 *  and belongs on Forge/the agent sheet, not the Ledger's closed-trade list. */
export function emberClosedTradesToHistory(rows: EmberTradeRow[]): HistoryTrade[] {
  return rows
    .filter((r) => r.status === 'closed' && r.closed_at)
    .map((r): HistoryTrade => {
      const pnl = Math.round(num(r.pnl) * 100) / 100
      const o = outcomeOf(pnl)
      return {
        id: `ember-${r.id}`,
        bot: 'ember',
        strategy: 'Ember',
        paper: false,
        underlying: r.symbol,
        close_date: ctDate(r.closed_at),
        opened_ct: ctTime(r.opened_at),
        closed_ct: ctTime(r.closed_at),
        contracts: Math.round(num(r.qty)) || 1,
        credit: null,
        pnl,
        pnl_pct: null,
        outcome: o.label,
        outcome_kind: o.kind,
      }
    })
}
