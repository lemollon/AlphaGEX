'use client'

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import type { LedgerPeriod } from '@/lib/bot-ledger/constants'
import type { SummaryResponse } from '@/lib/bot-ledger/types'
import { track } from '@/lib/analytics'
import { nextSearch, PERIOD_SPOKEN } from '@/lib/botLedger/params'
import { deriveLedgerView } from '@/lib/botLedger/state'
import AssumptionsBasis from './AssumptionsBasis'
import BotKpiCard from './BotKpiCard'
import { BotCardError, BotCardSkeleton, LedgerFailed, LedgerSuppressed } from './BotCardStates'
import PeriodSelector from './PeriodSelector'
import { LedgerHttpError, useLedgerResource } from './useLedgerResource'

/**
 * The KPI half of the page.
 *
 * Owns `period` and NOTHING else. The trade log is a separate island with its
 * own state, so "the period control never touches the log, and the bot filter
 * never touches the cards" is structural rather than a rule to remember.
 *
 * `hero` is a slot: the hero is rendered on the server and passed through, so
 * it never enters the client bundle and the H1 is in the initial HTML.
 */
export default function LedgerPerformance({
  initialPeriod,
  initialBot,
  hero,
}: {
  initialPeriod: LedgerPeriod
  initialBot: 'all' | 'spark' | 'flame'
  hero: ReactNode
}) {
  const [period, setPeriod] = useState<LedgerPeriod>(initialPeriod)
  const [announcement, setAnnouncement] = useState('')
  // Clock is read after mount only — a server-rendered relative time would
  // disagree with the client's and trip a hydration mismatch.
  const [now, setNow] = useState<number | null>(null)

  const resource = useLedgerResource<SummaryResponse>(
    `/api/public/bot-ledger/summary?period=${period}`,
  )

  useEffect(() => {
    setNow(Date.now())
    const id = setInterval(() => setNow(Date.now()), 60_000)
    return () => clearInterval(id)
  }, [])

  // One view event per mount. The ref guard matters: React 18 StrictMode
  // double-mounts in development and would otherwise fire it twice.
  const viewed = useRef(false)
  useEffect(() => {
    if (viewed.current) return
    viewed.current = true
    track({ name: 'bot_ledger_view', props: { period: initialPeriod, bot: initialBot } })
  }, [initialPeriod, initialBot])

  // Announce completed updates, never the first load.
  const firstLoad = useRef(true)
  useEffect(() => {
    if (!resource.data || resource.isRefreshing) return
    if (firstLoad.current) {
      firstLoad.current = false
      return
    }
    const message = `Performance updated for the ${PERIOD_SPOKEN[period]}`
    setAnnouncement((prev) =>
      // VoiceOver will not re-announce byte-identical text, and toggling
      // 7d -> 30d -> 7d produces exactly that. Alternate a zero-width space.
      prev.replace(/​/g, '') === message ? `${message}​` : message,
    )
  }, [resource.data, resource.isRefreshing, period])

  // Surface a failure once per code, not once per SWR retry.
  const reportedErrors = useRef(new Set<string>())
  useEffect(() => {
    if (!resource.error) return
    const code = resource.error instanceof LedgerHttpError ? resource.error.code : 'network'
    if (reportedErrors.current.has(code)) return
    reportedErrors.current.add(code)
    track({ name: 'bot_ledger_error', props: { component: 'summary', error_code: code } })
  }, [resource.error])

  function changePeriod(next: LedgerPeriod) {
    if (next === period) return
    track({ name: 'bot_ledger_period_change', props: { from: period, to: next } })
    setPeriod(next)
    // replaceState notifies nothing: no re-render, no RSC round-trip, no scroll
    // jump. Only the `bot` key is left alone, structurally (see nextSearch).
    window.history.replaceState(
      null,
      '',
      `${window.location.pathname}${nextSearch(window.location.search, { period: next })}${window.location.hash}`,
    )
  }

  const view = useMemo(
    () =>
      deriveLedgerView({
        data: resource.data,
        error: resource.error,
        isRefreshing: resource.isRefreshing,
        now: now ?? 0,
      }),
    [resource.data, resource.error, resource.isRefreshing, now],
  )

  return (
    <section aria-labelledby="ledger-performance-heading">
      <h2 id="ledger-performance-heading" className="sr-only">
        Paper-trade performance
      </h2>

      <div className="flex flex-col gap-8 md:flex-row md:items-end md:justify-between">
        {hero}
        <div className="md:pb-1">
          <PeriodSelector period={period} onChange={changePeriod} />
        </div>
      </div>

      <div className="mt-8">
        <AssumptionsBasis />
      </div>

      <p role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {announcement}
      </p>

      <div
        className="mt-6 grid grid-cols-1 items-stretch gap-5 md:grid-cols-2"
        aria-busy={view.kind === 'cards' ? view.busy : undefined}
      >
        {view.kind === 'suppressed' ? <LedgerSuppressed /> : null}
        {view.kind === 'failed' ? <LedgerFailed onRetry={resource.retry} /> : null}
        {view.kind === 'cards'
          ? view.cards.map((card) => {
              if (card.kind === 'loading') return <BotCardSkeleton key={card.bot} bot={card.bot} />
              if (card.kind === 'error') {
                return <BotCardError key={card.bot} bot={card.bot} onRetry={resource.retry} />
              }
              return <BotKpiCard key={card.bot} state={card} period={period} now={now} />
            })
          : null}
      </div>

      {view.kind === 'cards' && view.cards.some((c) => c.kind === 'loading') ? (
        <p className="sr-only">Loading performance figures…</p>
      ) : null}
    </section>
  )
}
