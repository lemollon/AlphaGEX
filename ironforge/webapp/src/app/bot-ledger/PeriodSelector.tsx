'use client'

import type { LedgerPeriod } from '@/lib/bot-ledger/constants'
import { PERIOD_LABEL } from '@/lib/botLedger/params'

/**
 * Segmented 7d / 30d control.
 *
 * Built on native radio inputs inside a fieldset, which buys the entire
 * accessibility contract for free: one tab stop, arrow-key roving, a real
 * checked state exposed to assistive tech, and a genuine group label. No
 * keyboard JavaScript, no role="radio" to get subtly wrong.
 *
 * The inputs are `sr-only` rather than `hidden` — they must stay focusable.
 */
export default function PeriodSelector({
  period,
  onChange,
}: {
  period: LedgerPeriod
  onChange: (next: LedgerPeriod) => void
}) {
  return (
    <fieldset className="w-full md:w-auto">
      <legend className="mb-2 block text-[10px] font-semibold uppercase tracking-wider text-gray-400 md:sr-only">
        Performance period
      </legend>
      <div className="flex w-full rounded-lg border border-white/10 bg-forge-card p-1 md:inline-flex md:w-auto">
        {(['7d', '30d'] as const).map((value) => (
          <label key={value} className="relative flex-1 md:flex-none">
            <input
              type="radio"
              name="bot-ledger-period"
              value={value}
              checked={period === value}
              onChange={() => onChange(value)}
              className="peer sr-only"
            />
            <span className="flex min-h-[44px] cursor-pointer select-none items-center justify-center whitespace-nowrap rounded-md px-5 py-2.5 text-sm font-semibold text-gray-400 transition-colors hover:text-white peer-checked:bg-amber-700 peer-checked:text-white peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-amber-400 motion-reduce:transition-none">
              {PERIOD_LABEL[value]}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}
