'use client'

import type { LedgerBot } from '@/lib/bot-ledger/constants'
import { LEDGER_BOT_NAME } from '@/lib/bot-ledger/constants'
import { BOT_ACCENT, CARD_MIN_H, CARD_SHELL } from './cardStyles'

/**
 * Skeleton.
 *
 * Grey bars only, at the geometry of the real content. Deliberately NO digits,
 * no em dashes and no PAPER TRADING badge on a fake body — a placeholder that
 * looks like a value is a value as far as a reader is concerned.
 */
export function BotCardSkeleton({ bot }: { bot: LedgerBot }) {
  const accent = BOT_ACCENT[bot]
  const bar = 'animate-pulse rounded bg-white/5 motion-reduce:animate-none'
  return (
    <div className={`${CARD_SHELL} ${CARD_MIN_H} ${accent.border}`}>
      <div className="flex flex-col gap-4 p-6">
        <div className="flex items-center gap-3">
          <div className={`${bar} h-14 w-14 shrink-0 rounded-full`} />
          <div className="w-full space-y-2">
            <div className={`${bar} h-7 w-32`} />
            <div className={`${bar} h-4 w-44`} />
          </div>
        </div>
        <div className="min-h-[18px]" />
        <div className="flex flex-col items-center gap-3">
          <div className={`${bar} h-[72px] w-52 md:h-[88px]`} />
          <div className={`${bar} h-3 w-40`} />
          <div className={`${bar} h-4 w-56`} />
        </div>
        <div className="flex flex-col items-center gap-2">
          <div className={`${bar} h-9 w-32`} />
          <div className={`${bar} h-3 w-48`} />
        </div>
      </div>
      <div className="mt-auto grid grid-cols-3 gap-px border-t border-white/10 bg-white/5">
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex flex-col items-center gap-2 bg-forge-card px-3 py-4">
            <div className={`${bar} h-3 w-20`} />
            <div className={`${bar} h-5 w-16`} />
          </div>
        ))}
      </div>
      <div className="border-t border-white/10 px-5 py-4">
        <div className={`${bar} h-4 w-52`} />
      </div>
    </div>
  )
}

/**
 * Per-bot error panel. Keeps the bot's identity so the card still says what it
 * is, and offers a retry. The other bot's card is unaffected.
 */
export function BotCardError({ bot, onRetry }: { bot: LedgerBot; onRetry: () => void }) {
  const name = LEDGER_BOT_NAME[bot]
  const other = bot === 'spark' ? LEDGER_BOT_NAME.flame : LEDGER_BOT_NAME.spark
  return (
    <div
      className={`${CARD_SHELL} ${CARD_MIN_H} items-center justify-center border-red-900/50 bg-red-950/20 p-6 text-center`}
    >
      <h3 className="font-display text-2xl text-white">{name}</h3>
      <p className="mt-3 max-w-xs text-sm text-gray-300">
        We couldn&apos;t load {name}&apos;s figures just now. {other}&apos;s are unaffected.
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-5 min-h-[44px] rounded-md border border-white/15 px-5 text-sm font-semibold text-gray-200 transition hover:border-white/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400 motion-reduce:transition-none"
      >
        Retry
      </button>
    </div>
  )
}

/** Whole-request failure with nothing cached to fall back on. */
export function LedgerFailed({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      className={`${CARD_SHELL} ${CARD_MIN_H} col-span-full items-center justify-center border-white/10 p-8 text-center`}
    >
      <h3 className="font-display text-2xl text-white">Performance is temporarily unavailable</h3>
      <p className="mt-3 max-w-md text-sm text-gray-300">
        We couldn&apos;t load the ledger just now. Nothing has changed about the record — this is a
        display problem on our side.
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-5 min-h-[44px] rounded-md border border-white/15 px-5 text-sm font-semibold text-gray-200 transition hover:border-white/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400 motion-reduce:transition-none"
      >
        Retry
      </button>
    </div>
  )
}

/**
 * Reconciliation failure — BOTH cards suppressed.
 *
 * No retry: retrying cannot fix a reconciliation mismatch. Showing nothing is
 * correct here; showing a partial figure would be the failure mode this page
 * exists to rule out.
 */
export function LedgerSuppressed() {
  return (
    <div
      className={`${CARD_SHELL} ${CARD_MIN_H} col-span-full items-center justify-center border-white/10 p-8 text-center`}
    >
      <h3 className="font-display text-2xl text-white">Performance figures are being verified</h3>
      <p className="mt-3 max-w-md text-sm text-gray-300">
        We hold these numbers back until they reconcile against the trade log, so nothing partial is
        shown. The trade log below is unaffected. Please check back shortly.
      </p>
    </div>
  )
}
