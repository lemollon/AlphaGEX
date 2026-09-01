'use client'

import type { LiveSummary } from '@/lib/live/types'
import type { AccentTheme } from './accent'

/**
 * "Risky setups skipped this month" — reframes a no-trade day as the bot's
 * protection rules doing their job. Renders NOTHING when riskProtection is
 * null: that means the underlying query failed, and an honest empty card
 * beats a fabricated number on a real-money page. A count of exactly 0 is a
 * genuine value and DOES render — "0 skipped" is not the same as "unknown".
 */
export default function RiskProtectionCard({
  riskProtection,
  accent,
  botLabel,
}: {
  riskProtection: LiveSummary['risk_protection']
  accent: AccentTheme
  /** Customer-facing agent name, e.g. "Spark" — the copy must never hardcode it. */
  botLabel: string
}) {
  if (!riskProtection) return null
  const { skipped_count: count, period_label: periodLabel } = riskProtection

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <h3 className={`text-xs font-semibold uppercase tracking-widest ${accent.text}`}>
        Risk Protection
      </h3>
      <div className="mt-3 flex items-center gap-4">
        <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full ${accent.chip}`}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6">
            <path d="M12 2 4 6v6c0 5 3.5 8.5 8 10 4.5-1.5 8-5 8-10V6z" />
            <path d="m9.5 12 2 2 4-4" />
          </svg>
        </div>
        <div>
          <p className="text-lg font-semibold text-white">
            {count} unstable setup{count === 1 ? '' : 's'} skipped {periodLabel}
          </p>
          <p className="mt-0.5 text-sm text-gray-400">
            Protecting your capital when conditions don&apos;t meet {botLabel}&apos;s protection standards.
          </p>
        </div>
      </div>
    </section>
  )
}
