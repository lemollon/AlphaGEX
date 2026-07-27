import Link from 'next/link'

import { CheckCircleIcon } from '../_home/icons'

/**
 * Hero — the only <h1> on the route.
 *
 * A server component with no data dependency, passed into the client island as
 * a slot so the headline and both CTAs are in the initial HTML. That keeps the
 * LCP element off the JavaScript critical path entirely and satisfies "hero and
 * CTAs render without waiting for the API".
 *
 * CTA styling note: the marketing idiom is `bg-amber-600`, which is 3.69:1
 * against white at 14px bold and fails WCAG AA for normal text. This route uses
 * `amber-700` / `emerald-700` (5.69:1 / 5.48:1) because the ledger is held to
 * the accessibility bar in its own requirements.
 */
export default function LedgerHero() {
  return (
    <div className="max-w-2xl">
      <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-amber-500">
        The Bot Ledger
      </p>

      <h1 className="mt-3 font-display text-[clamp(2.375rem,8vw,2.75rem)] leading-[1.05] tracking-tight text-white md:text-[clamp(3.375rem,4.5vw,4rem)]">
        Proven in <span className="text-amber-500">Practice.</span>
      </h1>

      <p className="mt-4 text-base leading-relaxed text-gray-300 md:text-[17px]">
        Every paper trade follows the same rules—and every result is recorded.
        <br className="hidden sm:block" />
        {' '}
        See how Spark and Flame perform, win or loss.
      </p>

      <div className="mt-7 flex flex-col gap-3 sm:flex-row">
        <Link
          href="/signup?source=bot_ledger&placement=hero"
          className="flex min-h-[44px] w-full items-center justify-center rounded-md bg-amber-700 px-7 py-3 text-sm font-bold text-white transition hover:bg-amber-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400 motion-reduce:transition-none sm:w-auto"
          data-ledger-cta="create_account"
        >
          Create Account
        </Link>

        <Link
          href="/signup?source=bot_ledger&placement=hero&plan=automate"
          className="flex min-h-[44px] w-full flex-col items-center justify-center rounded-md bg-emerald-700 px-7 py-2 text-center font-bold text-white transition hover:bg-emerald-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400 motion-reduce:transition-none sm:w-auto"
          data-ledger-cta="start_trial"
        >
          <span className="text-sm leading-tight">Start 5-Day Free Trial</span>
          <span className="text-[11px] font-medium leading-tight text-emerald-100">
            Forge Automate
          </span>
        </Link>
      </div>

      <ul className="mt-5 flex flex-wrap gap-x-8 gap-y-2 text-sm text-gray-300">
        <li className="flex items-center gap-2">
          <CheckCircleIcon className="h-4 w-4 shrink-0 text-amber-500" />
          No long-term commitment
        </li>
        <li className="flex items-center gap-2">
          <CheckCircleIcon className="h-4 w-4 shrink-0 text-amber-500" />
          Cancel anytime
        </li>
      </ul>
    </div>
  )
}
