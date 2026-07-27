'use client'

import { useEffect, useRef, useState } from 'react'

import {
  DEFAULT_TRADE_LIMIT,
  LEDGER_BOT_FILTERS,
  type LedgerBotFilter,
} from '@/lib/bot-ledger/constants'
import type { TradesResponse } from '@/lib/bot-ledger/types'
import { track } from '@/lib/analytics'
import { BOT_FILTER_LABEL, nextSearch } from '@/lib/botLedger/params'
import { LedgerHttpError, useLedgerResource } from './useLedgerResource'
import { TradeCards, TradeTable } from './TradeRows'
import { LABEL } from './cardStyles'

/**
 * The trade log.
 *
 * Owns `bot` and `cursor` and NOTHING else — changing the filter cannot touch
 * the KPI cards, because this island does not know they exist.
 */
export default function TradeLog({
  initialBot,
  year,
}: {
  initialBot: LedgerBotFilter
  year: number
}) {
  const [bot, setBot] = useState<LedgerBotFilter>(initialBot)
  const [cursor, setCursor] = useState<string | null>(null)
  const regionRef = useRef<HTMLDivElement | null>(null)

  const key =
    `/api/public/bot-ledger/trades?bot=${bot}&limit=${DEFAULT_TRADE_LIMIT}` +
    (cursor ? `&cursor=${encodeURIComponent(cursor)}` : '')

  const resource = useLedgerResource<TradesResponse>(key)

  const reportedErrors = useRef(new Set<string>())
  useEffect(() => {
    if (!resource.error) return
    const code = resource.error instanceof LedgerHttpError ? resource.error.code : 'network'
    // A stale snapshot is self-healing: drop the cursor and refetch page one.
    if (code === 'SNAPSHOT_EXPIRED' || code === 'INVALID_CURSOR') {
      if (cursor !== null) setCursor(null)
      return
    }
    if (reportedErrors.current.has(code)) return
    reportedErrors.current.add(code)
    track({ name: 'bot_ledger_error', props: { component: 'trade_log', error_code: code } })
  }, [resource.error, cursor])

  function changeBot(next: LedgerBotFilter) {
    if (next === bot) return
    track({ name: 'bot_ledger_bot_filter_change', props: { from: bot, to: next } })
    setBot(next)
    setCursor(null) // a new filter starts a new pagination run
    regionRef.current?.scrollIntoView({ block: 'nearest', behavior: 'auto' })
    window.history.replaceState(
      null,
      '',
      `${window.location.pathname}${nextSearch(window.location.search, { bot: next })}${window.location.hash}`,
    )
  }

  function page(direction: 'next' | 'prev') {
    const target =
      direction === 'next' ? resource.data?.next_cursor ?? null : resource.data?.previous_cursor ?? null
    track({
      name: 'bot_ledger_trade_log_page',
      props: { direction, page_size: DEFAULT_TRADE_LIMIT },
    })
    setCursor(target)
    regionRef.current?.scrollIntoView({ block: 'nearest', behavior: 'auto' })
  }

  const trades = resource.data?.items ?? []
  const filterName = bot === 'all' ? '' : ` ${BOT_FILTER_LABEL[bot]}`

  return (
    <section aria-labelledby="ledger-trades-heading" className="mt-16 md:mt-20" ref={regionRef}>
      <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 id="ledger-trades-heading" className="font-display text-3xl text-white md:text-4xl">
            Recent Paper Trades
          </h2>
          <p className="mt-2 max-w-xl text-sm text-gray-400">
            One contract per trade. Nominal results are shown alongside the buying power used.
          </p>
        </div>

        <div className="w-full md:w-56">
          <label htmlFor="ledger-bot-filter" className={`${LABEL} mb-1.5 block`}>
            Bot
          </label>
          <select
            id="ledger-bot-filter"
            aria-label="Filter trades by bot"
            value={bot}
            onChange={(e) => changeBot(e.target.value as LedgerBotFilter)}
            className="min-h-[44px] w-full rounded-lg border border-white/15 bg-forge-card px-3 text-sm text-gray-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400"
          >
            {LEDGER_BOT_FILTERS.map((value) => (
              <option key={value} value={value}>
                {BOT_FILTER_LABEL[value]}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="mt-6" aria-busy={resource.isRefreshing || undefined}>
        {resource.isLoading ? (
          <>
            <p className="sr-only">Loading recent paper trades…</p>
            <ul className="space-y-3" aria-hidden="true">
              {[0, 1, 2, 3, 4].map((i) => (
                <li
                  key={i}
                  className="h-16 animate-pulse rounded-xl border border-white/10 bg-forge-card/60 motion-reduce:animate-none"
                />
              ))}
            </ul>
          </>
        ) : null}

        {!resource.isLoading && resource.error ? (
          <div className="rounded-2xl border border-white/10 bg-forge-card p-8 text-center">
            <p className="text-sm text-gray-300">
              Recent paper trades are temporarily unavailable.
            </p>
            <button
              type="button"
              onClick={resource.retry}
              className="mt-4 min-h-[44px] rounded-md border border-white/15 px-5 text-sm font-semibold text-gray-200 transition hover:border-white/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400 motion-reduce:transition-none"
            >
              Retry
            </button>
          </div>
        ) : null}

        {!resource.isLoading && !resource.error && trades.length === 0 ? (
          <div className="rounded-2xl border border-white/10 bg-forge-card p-8 text-center">
            <p className="text-sm text-gray-300">No recent{filterName} paper trades.</p>
          </div>
        ) : null}

        {trades.length > 0 ? (
          <>
            <TradeTable trades={trades} year={year} />
            <TradeCards trades={trades} year={year} />
          </>
        ) : null}
      </div>

      {resource.data && (resource.data.next_cursor || resource.data.previous_cursor) ? (
        <div className="mt-5 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => page('prev')}
            disabled={!resource.data.previous_cursor}
            className="min-h-[44px] rounded-md border border-white/15 px-5 text-sm font-semibold text-gray-200 transition enabled:hover:border-white/30 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400 motion-reduce:transition-none"
          >
            Previous
          </button>
          <p className="text-xs text-gray-400">
            {resource.data.total} closed {resource.data.total === 1 ? 'trade' : 'trades'}
          </p>
          <button
            type="button"
            onClick={() => page('next')}
            disabled={!resource.data.next_cursor}
            className="min-h-[44px] rounded-md border border-white/15 px-5 text-sm font-semibold text-gray-200 transition enabled:hover:border-white/30 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400 motion-reduce:transition-none"
          >
            Next
          </button>
        </div>
      ) : null}
    </section>
  )
}
