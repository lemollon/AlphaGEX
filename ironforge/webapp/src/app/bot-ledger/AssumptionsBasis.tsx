import { ChevronRightIcon } from '../_home/icons'

/**
 * The paper-trade basis strip.
 *
 * Desktop: a pill strip. Mobile: a native <details> disclosure, which gives a
 * button role, expanded state, keyboard operation and exactly one tab stop with
 * zero JavaScript.
 *
 * The commission asterisk resolves via an sr-only pointer to #ledger-fee-note
 * rather than a jump link, because a link here would insert a focus stop into
 * the middle of the pinned tab order (CTAs -> period -> basis -> bot filter ->
 * pagination).
 */

const ITEMS: ReadonlyArray<{ text: string; footnote?: boolean }> = [
  { text: 'Paper-trade basis' },
  { text: '1 contract per trade' },
  { text: 'Results measured against buying power used' },
  { text: 'Before commissions', footnote: true },
  { text: 'No compounding' },
]

function FootnoteMark() {
  return (
    <>
      <span aria-hidden="true">*</span>
      <span className="sr-only">
        {' '}
        — see the commissions note in the disclosure at the foot of this page
      </span>
    </>
  )
}

export default function AssumptionsBasis() {
  return (
    <>
      {/* Desktop: separators are borders, not generated bullet characters —
          CSS content is announced by some screen readers as noise. */}
      <ul className="hidden flex-wrap items-center justify-center rounded-full border border-white/10 bg-forge-card/60 px-5 py-2.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-gray-400 md:flex">
        {ITEMS.map((item, i) => (
          <li
            key={item.text}
            className={i === ITEMS.length - 1 ? '' : 'mr-3 border-r border-white/10 pr-3'}
          >
            {item.text}
            {item.footnote ? <FootnoteMark /> : null}
          </li>
        ))}
      </ul>

      <details className="group rounded-xl border border-white/10 bg-forge-card/60 md:hidden">
        <summary className="flex min-h-[44px] cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400 [&::-webkit-details-marker]:hidden">
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-gray-200">Paper-trade basis</span>
            <span className="mt-0.5 block text-xs text-gray-400">
              1 contract • BP-based returns • before commissions
            </span>
          </span>
          <ChevronRightIcon className="h-4 w-4 shrink-0 rotate-90 text-gray-400 transition-transform group-open:-rotate-90 motion-reduce:transition-none" />
        </summary>
        <ul className="space-y-1.5 border-t border-white/10 px-4 pb-3 pt-3 text-xs leading-relaxed text-gray-400">
          {ITEMS.map((item) => (
            <li key={item.text}>
              {item.text}
              {item.footnote ? <FootnoteMark /> : null}
            </li>
          ))}
        </ul>
      </details>
    </>
  )
}
