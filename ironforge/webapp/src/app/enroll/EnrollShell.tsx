import Link from 'next/link'
import { Wordmark } from '@/components/Brand'

/**
 * The approved enrollment chrome (July 29 handoff, all ACCT/PLAN/LEGAL/BILL/AGENT/
 * BROKER/ACT screens): full-page split layout — dark left brand panel with the
 * IronForge lockup and a large headline, right content area, slim top nav.
 *
 * Deliberately NOT CustomerShell: enrollment is a funnel, not the product, and the
 * approved screens carry no sidebar. Also deliberately NO step counter anywhere —
 * "No visible step count" is a locked product decision; progress is conveyed by page
 * context and resumable state.
 *
 * At narrow widths the brand panel stacks above the form and drops to a compact
 * headline (§ responsive: "collapse nonessential marketing copy, keep the primary
 * CTA visible").
 */
export default function EnrollShell({
  headline,
  subline,
  topRight = 'save-exit',
  maxWidthClass = 'max-w-2xl',
  children,
}: {
  headline: string
  subline?: string
  /** 'login' before an account exists (ACCT-01); 'save-exit' once enrollment is resumable. */
  topRight?: 'save-exit' | 'login' | 'none'
  maxWidthClass?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex min-h-screen flex-col bg-forge-bg text-gray-200">
      <header className="border-b border-forge-border bg-black/40">
        <div className="flex h-12 items-center justify-between px-5">
          <Link href="/" className="text-sm text-gray-300 transition-colors hover:text-white">
            Home
          </Link>
          {topRight === 'login' ? (
            <span className="text-sm text-gray-400">
              Already have an account?{' '}
              <Link href="/login" className="font-semibold text-amber-500 hover:text-amber-400">
                Log in
              </Link>
            </span>
          ) : null}
          {topRight === 'save-exit' ? (
            // State is server-persisted after every step, so "Save & exit" is a plain
            // link — resuming later re-enters at the earliest incomplete gate.
            <Link href="/home" className="text-sm text-gray-300 transition-colors hover:text-white">
              Save &amp; exit
            </Link>
          ) : null}
        </div>
      </header>

      <div className="flex flex-1 flex-col lg:flex-row">
        {/* Brand panel */}
        <aside className="border-b border-forge-border bg-black/50 px-6 py-6 lg:w-[38%] lg:shrink-0 lg:border-b-0 lg:border-r lg:px-10 lg:py-12">
          <Wordmark />
          <div className="mt-4 lg:mt-[38vh]">
            <h1 className="max-w-md text-2xl font-bold leading-tight text-white lg:text-4xl">{headline}</h1>
            {subline ? <p className="mt-3 hidden max-w-md text-base text-gray-400 lg:block">{subline}</p> : null}
          </div>
        </aside>

        {/* Content */}
        <main className="flex flex-1 justify-center px-4 py-8 lg:px-10 lg:py-14">
          <div className={`w-full ${maxWidthClass}`}>{children}</div>
        </main>
      </div>
    </div>
  )
}
