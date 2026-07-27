'use client'

import Image from 'next/image'

import type { LedgerPeriod } from '@/lib/bot-ledger/constants'
import type { BotSummary } from '@/lib/bot-ledger/types'
import {
  EM_DASH,
  longDate,
  profitFactor as fmtProfitFactor,
  relativeTime,
  sampleLine,
  sampleLineAccessible,
  signedPct,
  winRate as fmtWinRate,
} from '@/lib/botLedger/format'
import { PERIOD_CAPTION, PERIOD_SPOKEN } from '@/lib/botLedger/params'
import type { CardState } from '@/lib/botLedger/state'
import { BOT_ACCENT, CARD_MIN_H, CARD_SHELL, LABEL, signClass } from './cardStyles'

/** Em dash plus a spoken reason — a dash alone tells a screen reader nothing. */
function Unavailable({ reason }: { reason: string }) {
  return (
    <>
      <span aria-hidden="true">{EM_DASH}</span>
      <span className="sr-only">Not available — {reason}</span>
    </>
  )
}

function PaperBadge({ bot }: { bot: 'spark' | 'flame' }) {
  const cls =
    bot === 'spark'
      ? 'border-spark/50 bg-spark/10 text-spark'
      : 'border-amber-500/50 bg-amber-950/40 text-amber-400'
  return (
    <span
      className={`whitespace-nowrap rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${cls}`}
    >
      Paper Trading
    </span>
  )
}

export default function BotKpiCard({
  state,
  period,
  now,
}: {
  state: Extract<CardState, { kind: 'ready' | 'empty' | 'stale' }>
  period: LedgerPeriod
  /** Passed in (not read from the clock) so SSR and hydration agree. */
  now: number | null
}) {
  const s: BotSummary = state.summary
  const accent = BOT_ACCENT[s.bot]
  const isEmpty = s.closed_trades === 0
  const noTradesReason = `no closed paper trades in the ${PERIOD_SPOKEN[period]}`

  return (
    <article className={`${CARD_SHELL} ${CARD_MIN_H} ${accent.border}`}>
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-12 -top-12 h-40 w-40 rounded-full opacity-40 blur-3xl"
        style={{ background: accent.glow }}
      />

      <div className="relative flex flex-col gap-4 p-6">
        {/* 1-2. Identity + always-visible paper badge */}
        <div className="flex items-center gap-3">
          <Image
            src={s.mascot}
            alt=""
            aria-hidden="true"
            width={56}
            height={56}
            className="h-14 w-14 shrink-0 object-contain"
          />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-display text-3xl leading-none text-white">{s.name}</h3>
              <PaperBadge bot={s.bot} />
            </div>
            <p className="mt-1 text-sm text-gray-300">{s.tagline}</p>
          </div>
        </div>

        {/* Stale chip. The slot is reserved in every state so its appearance
            never pushes the layout. */}
        <p className="flex min-h-[18px] items-center text-[11px] text-gray-400">
          {state.kind === 'stale' && now !== null ? (
            <>
              Updated
              <time dateTime={state.generatedAt} className="ml-1">
                {relativeTime(state.generatedAt, now)}
              </time>
            </>
          ) : null}
        </p>

        {/* 3-4. Hero win rate — the dominant value on the card. */}
        <div className="text-center">
          <div className="flex min-h-[72px] items-end justify-center md:min-h-[88px]">
            {isEmpty ? (
              <p className="pb-2 text-base text-gray-300">No closed paper trades in this period.</p>
            ) : (
              <p className="font-display text-[clamp(3.25rem,12vw,4rem)] leading-[0.9] tracking-tight text-white md:text-[clamp(4rem,5.5vw,5rem)]">
                <span aria-hidden="true">{fmtWinRate(s.win_rate_pct)}</span>
                <span className="sr-only">
                  {s.name} win rate, {fmtWinRate(s.win_rate_pct)}, {PERIOD_SPOKEN[period]}
                </span>
              </p>
            )}
          </div>
          <p className={`mt-1.5 ${LABEL}`} aria-hidden="true">
            Win rate • {PERIOD_CAPTION[period]}
          </p>

          {/* 5. Sample line */}
          <p className="mt-3 text-sm">
            {isEmpty ? (
              <span className="text-gray-400">
                <Unavailable reason={noTradesReason} />
              </span>
            ) : (
              <>
                <span aria-hidden="true">
                  <span className="text-emerald-400">{s.wins} wins</span>
                  <span className="text-gray-500"> • </span>
                  <span className="text-red-400">{s.losses} losses</span>
                  {s.scratches > 0 ? (
                    <>
                      <span className="text-gray-500"> • </span>
                      <span className="text-gray-300">{s.scratches} scratch</span>
                    </>
                  ) : null}
                  <span className="text-gray-500"> • </span>
                  <span className="text-gray-300">{s.closed_trades} closed trades</span>
                </span>
                <span className="sr-only">
                  {sampleLineAccessible(s.wins, s.losses, s.scratches, s.closed_trades)}
                </span>
              </>
            )}
          </p>
        </div>

        {/* 6. Average return on buying power */}
        <div className="text-center">
          <p
            className={`font-display text-[clamp(1.75rem,7vw,2.25rem)] leading-none ${signClass(
              s.avg_return_on_bp_pct,
            )}`}
          >
            {s.avg_return_on_bp_pct === null ? (
              <Unavailable reason={noTradesReason} />
            ) : (
              <>
                <span aria-hidden="true">{signedPct(s.avg_return_on_bp_pct)}</span>
                <span className="sr-only">
                  Average return on buying power, {signedPct(s.avg_return_on_bp_pct)}
                </span>
              </>
            )}
          </p>
          <p className={`mt-1.5 ${LABEL}`} aria-hidden="true">
            Avg. return on buying power
          </p>
        </div>
      </div>

      {/* 7. Supporting metrics */}
      <dl className="relative mt-auto grid grid-cols-3 gap-px border-t border-white/10 bg-white/5">
        {[
          {
            label: 'Profit factor',
            node:
              s.profit_factor === null ? (
                <Unavailable reason={s.losses === 0 ? 'no losing trades in this period' : noTradesReason} />
              ) : (
                fmtProfitFactor(s.profit_factor)
              ),
            cls: 'text-gray-100',
          },
          {
            label: 'Avg. winner',
            node:
              s.avg_winner_pct === null ? (
                <Unavailable reason="no winning trades in this period" />
              ) : (
                `${signedPct(s.avg_winner_pct)} BP`
              ),
            cls: signClass(s.avg_winner_pct),
          },
          {
            label: 'Avg. loser',
            node:
              s.avg_loser_pct === null ? (
                <Unavailable reason="no losing trades in this period" />
              ) : (
                `${signedPct(s.avg_loser_pct)} BP`
              ),
            cls: signClass(s.avg_loser_pct),
          },
        ].map((cell) => (
          <div key={cell.label} className="bg-forge-card px-3 py-4 text-center">
            <dt className={LABEL}>{cell.label}</dt>
            <dd className={`mt-1 font-mono text-base tabular-nums ${cell.cls}`}>{cell.node}</dd>
          </div>
        ))}
      </dl>

      {/* 8. Lifetime footer — renders even when the window is empty. That is the
          whole point of the empty state: a quiet week must not erase the record. */}
      <div className="relative border-t border-white/10 px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-gray-300">
            <span className={`${LABEL} mr-2`}>Lifetime</span>
            {s.lifetime_win_rate_pct === null ? (
              <Unavailable reason="no closed paper trades yet" />
            ) : (
              <>
                <span className="font-mono tabular-nums text-gray-100">
                  {fmtWinRate(s.lifetime_win_rate_pct)}
                </span>
                {' win rate · '}
                <span className="font-mono tabular-nums text-gray-100">
                  {s.lifetime_closed_trades}
                </span>
                {' trades'}
              </>
            )}
          </p>

          {s.current_win_streak >= 2 ? (
            <span className="rounded-md border border-emerald-600/50 bg-emerald-950/40 px-2.5 py-1 text-xs font-semibold text-emerald-300">
              {s.current_win_streak} wins in a row
            </span>
          ) : null}
        </div>

        {/* Disclosure of the ledger start. Sits directly under the lifetime
            figure it qualifies, so the two can never be read apart. */}
        {s.inception_date ? (
          <p className="mt-1.5 text-[11px] text-gray-400">
            {s.name} ledger since{' '}
            <time dateTime={s.inception_date}>{longDate(s.inception_date)}</time>
          </p>
        ) : null}
      </div>
    </article>
  )
}
