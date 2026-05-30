'use client'

import {
  actionAccentClass,
  type AdvisorAction,
  type AdvisorRecommendation,
} from '@/lib/volatility'

const LABEL = 'text-[10px] text-forge-muted uppercase tracking-wider'

/**
 * HERO card — the blunt "what to do" read. Rendered first, above everything
 * else, and styled heavier than the other cards: a solid card with a thick,
 * stance-colored left border so it visually leads the page.
 *
 * Returns null when the backend hasn't supplied an `action` block, so older
 * payloads degrade gracefully to the existing OutlookCard/Recommendation flow.
 */
export default function ActionCard({
  action,
  recommendation,
}: {
  action?: AdvisorAction
  recommendation?: AdvisorRecommendation
}) {
  if (!action) return null

  const accent = actionAccentClass(recommendation?.stance)

  return (
    <section
      className={`rounded-xl border border-forge-border border-l-4 ${accent.border} bg-forge-card p-5 shadow-lg`}
    >
      <div className={LABEL}>What to do</div>

      {action.headline && (
        <h2 className={`mt-1 text-xl font-bold leading-snug text-white sm:text-2xl`}>
          {action.headline}
        </h2>
      )}

      {(action.do || action.dte_text) && (
        <p className={`mt-3 font-mono text-base font-semibold ${accent.text}`}>
          {action.do}
          {action.do && action.dte_text ? ' · ' : ''}
          {action.dte_text && <span className="text-white/90">{action.dte_text}</span>}
        </p>
      )}

      {action.plain && (
        <p className="mt-3 max-w-prose text-sm leading-relaxed text-gray-200 sm:text-base">
          {action.plain}
        </p>
      )}

      {action.watch && (
        <div className="mt-4 border-t border-forge-border pt-3">
          <span className={`${LABEL} mr-2`}>Watch for</span>
          <span className="text-sm leading-relaxed text-white/80">{action.watch}</span>
        </div>
      )}

      <p className="mt-4 text-[10px] text-forge-muted">Educational, not financial advice.</p>
    </section>
  )
}
