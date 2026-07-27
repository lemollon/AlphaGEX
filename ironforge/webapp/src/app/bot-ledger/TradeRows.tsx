'use client'

import type { PublicLedgerTrade } from '@/lib/bot-ledger/types'
import { marketDate, signedDollars, signedPct, wholeDollars } from '@/lib/botLedger/format'
import { BOT_ACCENT, LABEL } from './cardStyles'

/**
 * Desktop table and mobile cards.
 *
 * Both variants consume the SAME trades array through the SAME formatters, so
 * only the presentational shell is duplicated — the data and formatting cannot
 * drift between them.
 *
 * Bot identity and outcome are never conveyed by colour alone: the dot is
 * aria-hidden decoration beside the literal word.
 */

const OUTCOME_LABEL: Record<PublicLedgerTrade['outcome'], string> = {
  win: 'Win',
  loss: 'Loss',
  scratch: 'Scratch',
}

const OUTCOME_CLASS: Record<PublicLedgerTrade['outcome'], string> = {
  win: 'text-emerald-400',
  loss: 'text-red-400',
  scratch: 'text-gray-300',
}

function BotTag({ bot }: { bot: PublicLedgerTrade['bot'] }) {
  return (
    <span className="inline-flex items-center gap-1.5 font-semibold text-gray-100">
      <span
        aria-hidden="true"
        className="h-2 w-2 shrink-0 rounded-full"
        style={{ background: BOT_ACCENT[bot].cssVar }}
      />
      {bot.toUpperCase()}
    </span>
  )
}

function amountClass(v: string): string {
  const n = Number(v)
  if (!Number.isFinite(n) || Math.abs(n) < 0.005) return 'text-gray-300'
  return n > 0 ? 'text-emerald-400' : 'text-red-400'
}

const TH = `px-4 py-3 ${LABEL}`
const TD = 'whitespace-nowrap px-4 py-4 text-sm'

export function TradeTable({ trades, year }: { trades: PublicLedgerTrade[]; year: number }) {
  return (
    <div className="hidden overflow-hidden rounded-2xl border border-white/10 bg-forge-card md:block">
      <table className="w-full text-left">
        <caption className="sr-only">
          Recent closed paper trades. One contract per trade; results are shown against the buying
          power used, before commissions.
        </caption>
        <thead>
          <tr className="border-b border-white/10">
            <th scope="col" className={TH}>Closed</th>
            <th scope="col" className={TH}>Bot</th>
            <th scope="col" className={TH}>Setup</th>
            <th scope="col" className={`${TH} text-right`}>Buying power</th>
            <th scope="col" className={`${TH} text-right`}>Net result</th>
            <th scope="col" className={`${TH} text-right`}>Return on BP</th>
            <th scope="col" className={TH}>Outcome</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.public_id} className="border-b border-white/5 last:border-0">
              <td className={`${TD} text-gray-400`}>{marketDate(t.closed_date, year)}</td>
              <td className={TD}><BotTag bot={t.bot} /></td>
              <td className={`${TD} text-gray-300`}>{t.setup}</td>
              <td className={`${TD} text-right font-mono tabular-nums text-gray-100`}>
                {wholeDollars(t.buying_power_used)}
              </td>
              <td className={`${TD} text-right font-mono tabular-nums ${amountClass(t.net_result)}`}>
                {signedDollars(t.net_result)}
              </td>
              <td
                className={`${TD} text-right font-mono tabular-nums ${amountClass(t.return_on_bp_pct)}`}
              >
                {signedPct(t.return_on_bp_pct)}
              </td>
              <td className={`${TD} font-semibold ${OUTCOME_CLASS[t.outcome]}`}>
                {OUTCOME_LABEL[t.outcome]}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function TradeCards({ trades, year }: { trades: PublicLedgerTrade[]; year: number }) {
  return (
    <ul className="space-y-3 md:hidden">
      {trades.map((t) => (
        <li key={t.public_id} className="rounded-xl border border-white/10 bg-forge-card p-4">
          <div className="flex items-start justify-between gap-3 border-b border-white/5 pb-3">
            <span className="flex flex-col gap-0.5">
              <span className="font-mono text-sm tabular-nums text-gray-400">
                {marketDate(t.closed_date, year)}
              </span>
              <BotTag bot={t.bot} />
            </span>
            <span
              className={`rounded-full border border-white/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${OUTCOME_CLASS[t.outcome]}`}
            >
              {OUTCOME_LABEL[t.outcome]}
            </span>
          </div>

          {/* A definition list, so every value keeps a labelled relationship —
              not merely a visual one. */}
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3">
            <div className="col-span-2">
              <dt className={LABEL}>Setup</dt>
              <dd className="mt-0.5 text-sm text-gray-300">{t.setup}</dd>
            </div>
            <div>
              <dt className={LABEL}>Buying power</dt>
              <dd className="mt-0.5 font-mono text-sm tabular-nums text-gray-100">
                {wholeDollars(t.buying_power_used)}
              </dd>
            </div>
            <div>
              <dt className={LABEL}>Net result</dt>
              <dd className={`mt-0.5 font-mono text-sm tabular-nums ${amountClass(t.net_result)}`}>
                {signedDollars(t.net_result)}
              </dd>
            </div>
            <div>
              <dt className={LABEL}>Return on BP</dt>
              <dd
                className={`mt-0.5 font-mono text-sm tabular-nums ${amountClass(t.return_on_bp_pct)}`}
              >
                {signedPct(t.return_on_bp_pct)}
              </dd>
            </div>
          </dl>
        </li>
      ))}
    </ul>
  )
}
