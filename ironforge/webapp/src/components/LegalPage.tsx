import Link from 'next/link'
import { Wordmark } from '@/components/Brand'

/**
 * Shared chrome for the public legal/contact pages (/contact, /privacy, /terms).
 *
 * These render standalone (see Shell `isStandalone`) and are in the public
 * allowlist (see `lib/auth/access.ts`) so they are reachable without a session —
 * required so payment/brokerage partners (Stripe, SnapTrade) and end users can
 * read them before signing in.
 */
export default function LegalPage({
  title,
  updated,
  children,
}: {
  title: string
  updated: string
  children: React.ReactNode
}) {
  return (
    <div className="min-h-screen bg-forge-bg text-gray-200">
      <header className="border-b border-forge-border">
        <div className="max-w-3xl mx-auto px-5 h-16 flex items-center justify-between">
          <Link href="/" aria-label="IronForge home" className="flex items-center">
            <Wordmark />
          </Link>
          <nav className="flex items-center gap-5 text-sm text-gray-400">
            <Link href="/contact" className="hover:text-amber-500 transition-colors">Contact</Link>
            <Link href="/privacy" className="hover:text-amber-500 transition-colors">Privacy</Link>
            <Link href="/terms" className="hover:text-amber-500 transition-colors">Terms</Link>
          </nav>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-5 py-12">
        <h1 className="text-3xl font-semibold text-white">{title}</h1>
        <p className="mt-2 text-sm text-forge-muted">Last updated: {updated}</p>
        <div className="legal-prose mt-8 space-y-6 text-[15px] leading-relaxed text-gray-300">
          {children}
        </div>
      </main>

      <footer className="border-t border-forge-border">
        <div className="max-w-3xl mx-auto px-5 py-8 text-sm text-forge-muted flex flex-col sm:flex-row gap-2 sm:items-center sm:justify-between">
          <span>© {new Date().getFullYear()} IronForge Technologies LLC. All rights reserved.</span>
          <span>
            <a href="mailto:leron@ironforge.trade" className="hover:text-amber-500 transition-colors">leron@ironforge.trade</a>
          </span>
        </div>
      </footer>
    </div>
  )
}

/** Section heading used inside legal page bodies. */
export function LegalSection({ heading, children }: { heading: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold text-white">{heading}</h2>
      {children}
    </section>
  )
}
