import { describe, expect, it } from 'vitest'

import type { BotSummary, SummaryResponse } from '@/lib/bot-ledger/types'
import { deriveLedgerView, isAbortError, STALE_AFTER_MS } from '../state'

const NOW = Date.parse('2026-07-26T21:00:00Z')

function bot(over: Partial<BotSummary> = {}): BotSummary {
  return {
    bot: 'spark',
    name: 'Spark',
    tagline: 'Next-day SPY spreads',
    execution_mode: 'paper',
    mascot: '/home/spark-mascot-glow.png',
    closed_trades: 19,
    wins: 14,
    losses: 4,
    scratches: 1,
    win_rate_pct: '73.68',
    avg_return_on_bp_pct: '0.20',
    profit_factor: '1.15',
    avg_winner_pct: '1.80',
    avg_loser_pct: '-5.40',
    lifetime_closed_trades: 22,
    lifetime_wins: 17,
    lifetime_win_rate_pct: '77.27',
    current_win_streak: 4,
    inception_date: '2026-06-24',
    setups: { 'SPY 1DTE Iron Condor': 22 },
    ...over,
  }
}

function summary(over: Partial<SummaryResponse> = {}): SummaryResponse {
  return {
    snapshot_id: 'bl1_1784067600_a8f3c1d2',
    as_of: '2026-07-26T21:00:00Z',
    period: '30d',
    calculation_version: 1,
    net_basis: 'gross_of_commissions',
    data_freshness_seconds: 120,
    generated_at: '2026-07-26T21:00:00Z',
    reconciled: true,
    bots: [bot(), bot({ bot: 'flame', name: 'Flame' })],
    data_quality: {
      tz_date_divergences: 0,
      dedupe_dropped: 0,
      excluded_no_bp: 0,
      excluded_zero_legs: 0,
      excluded_invalid_contracts: 0,
      excluded_missing_close_time: 0,
      excluded_invalid_numeric: 0,
    },
    ...over,
  }
}

const base = { data: undefined, error: undefined, isRefreshing: false, now: NOW }

describe('deriveLedgerView precedence', () => {
  it('suppresses BOTH cards when the payload does not reconcile', () => {
    const view = deriveLedgerView({ ...base, data: summary({ reconciled: false }) })
    expect(view.kind).toBe('suppressed')
  })

  it('suppression beats a healthy bot AND a missing bot', () => {
    const view = deriveLedgerView({
      ...base,
      data: summary({ reconciled: false, bots: [bot()] }),
    })
    expect(view.kind).toBe('suppressed')
  })

  it('shows skeletons while the first request is in flight', () => {
    const view = deriveLedgerView(base)
    expect(view.kind).toBe('cards')
    if (view.kind !== 'cards') return
    expect(view.cards.map((c) => c.kind)).toEqual(['loading', 'loading'])
    expect(view.busy).toBe(false)
  })

  it('fails only when there is nothing cached to show', () => {
    const view = deriveLedgerView({ ...base, error: new Error('boom') })
    expect(view.kind).toBe('failed')
  })

  it('renders STALE, not failed, when a revalidation fails with data on screen', () => {
    const view = deriveLedgerView({ ...base, data: summary(), error: new Error('boom') })
    expect(view.kind).toBe('cards')
    if (view.kind !== 'cards') return
    expect(view.cards.every((c) => c.kind === 'stale')).toBe(true)
  })
})

describe('deriveLedgerView card states', () => {
  it('is ready for a fresh payload with trades', () => {
    const view = deriveLedgerView({ ...base, data: summary() })
    if (view.kind !== 'cards') throw new Error('expected cards')
    expect(view.cards.map((c) => c.kind)).toEqual(['ready', 'ready'])
  })

  it('is empty when the window has no trades, and keeps lifetime intact', () => {
    const view = deriveLedgerView({
      ...base,
      data: summary({ bots: [bot({ closed_trades: 0 }), bot({ bot: 'flame' })] }),
    })
    if (view.kind !== 'cards') throw new Error('expected cards')
    const first = view.cards[0]
    expect(first.kind).toBe('empty')
    if (first.kind !== 'empty') return
    // The whole point of the empty state: a quiet week must not erase the record.
    expect(first.summary.lifetime_closed_trades).toBe(22)
  })

  it('goes stale once the payload is older than the threshold', () => {
    const view = deriveLedgerView({ ...base, data: summary(), now: NOW + STALE_AFTER_MS + 1000 })
    if (view.kind !== 'cards') throw new Error('expected cards')
    expect(view.cards.every((c) => c.kind === 'stale')).toBe(true)
  })

  it('stays ready just inside the threshold', () => {
    const view = deriveLedgerView({ ...base, data: summary(), now: NOW + STALE_AFTER_MS - 1000 })
    if (view.kind !== 'cards') throw new Error('expected cards')
    expect(view.cards.every((c) => c.kind === 'ready')).toBe(true)
  })

  it('errors only the missing bot, leaving the other rendered', () => {
    const view = deriveLedgerView({ ...base, data: summary({ bots: [bot()] }) })
    if (view.kind !== 'cards') throw new Error('expected cards')
    expect(view.cards.map((c) => c.kind)).toEqual(['ready', 'error'])
  })
})

describe('busy flag', () => {
  it('is true only when refreshing with values already on screen', () => {
    const refreshing = deriveLedgerView({ ...base, data: summary(), isRefreshing: true })
    expect(refreshing.kind === 'cards' && refreshing.busy).toBe(true)

    const firstLoad = deriveLedgerView({ ...base, isRefreshing: true })
    expect(firstLoad.kind === 'cards' && firstLoad.busy).toBe(false)
  })
})

describe('isAbortError', () => {
  it('recognises a cancelled fetch so it is not treated as a failure', () => {
    expect(isAbortError({ name: 'AbortError' })).toBe(true)
    expect(isAbortError({ name: 'TimeoutError' })).toBe(true)
  })

  it('does not swallow real errors', () => {
    expect(isAbortError(new Error('boom'))).toBe(false)
    expect(isAbortError(null)).toBe(false)
    expect(isAbortError('AbortError')).toBe(false)
  })
})
