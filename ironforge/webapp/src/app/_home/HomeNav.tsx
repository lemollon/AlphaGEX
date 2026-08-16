'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Wordmark } from '@/components/Brand'
import { MenuIcon, CloseIcon } from './icons'

/* Sticky top navigation for the public homepage: logo, the customer-facing
 * pages, then Login / Create Account (or My Dashboard once signed in). Nothing
 * operator-facing is exposed to customers or visitors — including to an
 * operator. The masthead is a customer surface, so it links customer pages and
 * nothing else; the ops console is a separate deployment with its own nav. */

// Public marketing links — shown to everyone, signed in or not.
const NAV_LINKS: ReadonlyArray<{ href: string; label: string }> = [
  { href: '/', label: 'Home' },
  { href: '/how-it-works', label: 'How It Works' },
  { href: '/waitlist', label: 'Join the Waitlist' },
]

// Links that require a MEMBERSHIP — any live subscription, a strategy or Community
// itself. Community is a $10 product, so advertising it to someone who has bought
// nothing points at a door they cannot walk through. Discovery is unaffected: the
// homepage membership section is where Community is actually sold, and it links there.
const MEMBER_LINKS: ReadonlyArray<{ href: string; label: string }> = [
  { href: '/community', label: 'Community' },
]

// Links that require actually OWNING the product. Live is the strategy dashboard;
// there is nothing on it for someone who owns no strategy, so advertising it to a
// free account is a dead end dressed as a feature.
/**
 * EVERY page on the deployment, shown only when the whole service runs open
 * (IRONFORGE_PUBLIC_MODE). The masthead is normally a strict customer surface —
 * nothing operator-facing is exposed to visitors — and that rule still holds on
 * ironforge.trade, which never sets the flag.
 *
 * The exception exists because an open sandbox with a customer-only masthead is
 * unusable: every operator page returns 200 and there is nothing to click, so it
 * reads as locked when it is wide open. Same failure as the live viewer before
 * #2817 — open at the door, closed everywhere it matters.
 */
const CONSOLE_LINKS: ReadonlyArray<{ href: string; label: string }> = [
  { href: '/spark', label: 'SPARK' },
  { href: '/spark2', label: 'SPARK2' },
  { href: '/flame', label: 'FLAME' },
  { href: '/inferno', label: 'INFERNO' },
  { href: '/blaze', label: 'BLAZE' },
  { href: '/flare', label: 'FLARE' },
  { href: '/compare', label: 'Compare' },
  { href: '/accounts', label: 'Accounts' },
  { href: '/gex', label: 'GEX' },
  { href: '/volatility', label: 'Volatility' },
  { href: '/calendar', label: 'Calendar' },
  { href: '/briefings', label: 'Briefings' },
  { href: '/ember', label: 'EMBER' },
  { href: '/agents/spark', label: 'Agent: Spark' },
  { href: '/agents/flame', label: 'Agent: Flame' },
  { href: '/performance', label: 'Performance' },
  { href: '/community', label: 'Community' },
  { href: '/support', label: 'Support' },
]

const OWNER_LINKS: ReadonlyArray<{ href: string; label: string }> = [
  { href: '/live', label: 'My Agents' },
]

// `active` is retained for backward compatibility with existing callers
// (page.tsx passes "home"); the current page is now derived from the pathname.
export default function HomeNav(
  { active: _active, showAll = false }: { active?: string; showAll?: boolean } = {},
) {
  const [open, setOpen] = useState(false)
  // SIGNED IN — drives "My Dashboard" vs "Create Account".
  const [isCustomer, setIsCustomer] = useState(false)
  // OWNS A STRATEGY — a strictly stronger claim, and the only thing that may reveal Live.
  const [ownsStrategy, setOwnsStrategy] = useState(false)
  // Any live subscription — strategy or Community.
  const [hasMembership, setHasMembership] = useState(false)
  const pathname = usePathname()

  useEffect(() => {
    fetch('/api/auth/customer-me')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        setIsCustomer(Boolean(d?.ok))
        setOwnsStrategy(Boolean(d?.ownsStrategy))
        setHasMembership(Boolean(d?.hasMembership))
      })
      .catch(() => {
        setIsCustomer(false)
        setOwnsStrategy(false)
        setHasMembership(false)
      })
  }, [])

  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : pathname.startsWith(href)

  // Both default false, so the first paint and any failed lookup show the PUBLIC nav.
  // A signed-in visitor briefly seeing marketing links is harmless; the reverse is not.
  const visibleLinks = [
    ...NAV_LINKS,
    ...(hasMembership ? MEMBER_LINKS : []),
    ...(ownsStrategy ? OWNER_LINKS : []),
    ...(showAll ? CONSOLE_LINKS : []),
  ]

  return (
    <header className="sticky top-0 z-50 border-b border-white/5 bg-black">
      <div className={`mx-auto flex max-w-[1200px] items-center justify-between px-5 md:px-8 ${showAll ? 'min-h-16 py-2' : 'h-16'}`}>
        <Link href="/" aria-label="IronForge home">
          <Wordmark markClass="h-8 w-auto" textClass="text-lg" />
        </Link>

        {/* Desktop links */}
        <nav className={`hidden items-center md:flex ${showAll ? 'flex-wrap gap-x-4 gap-y-1 justify-end' : 'gap-8'}`}>
          {visibleLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={
                isActive(link.href)
                  ? 'border-b-2 border-amber-500 pb-0.5 text-sm font-semibold text-white'
                  : 'text-sm text-gray-300 transition-colors hover:text-white'
              }
            >
              {link.label}
            </Link>
          ))}
          {isCustomer ? (
            <Link
              href="/performance"
              className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-amber-400"
            >
              My Dashboard
            </Link>
          ) : (
            <>
              <Link href="/login" className="text-sm text-gray-300 transition-colors hover:text-white">
                Login
              </Link>
              <Link
                href="/signup"
                className="rounded-lg border border-amber-500 px-4 py-2 text-sm font-semibold text-amber-500 transition-colors hover:bg-amber-500 hover:text-white"
              >
                Create Account
              </Link>
            </>
          )}
        </nav>

        {/* Mobile: solid CTA + hamburger */}
        <div className="flex items-center gap-3 md:hidden">
          <Link
            href={isCustomer ? '/performance' : '/signup'}
            className="rounded-lg bg-amber-500 px-3.5 py-2 text-sm font-semibold text-white"
          >
            {isCustomer ? 'My Dashboard' : 'Create Account'}
          </Link>
          <button
            type="button"
            aria-label={open ? 'Close menu' : 'Open menu'}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
            className="text-white"
          >
            {open ? <CloseIcon className="h-6 w-6" /> : <MenuIcon className="h-6 w-6" />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {open ? (
        <nav className="border-t border-white/10 bg-black px-5 py-4 md:hidden">
          <div className="flex flex-col gap-4">
            {visibleLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setOpen(false)}
                className={
                  isActive(link.href)
                    ? 'text-sm font-semibold text-white'
                    : 'text-sm text-gray-300'
                }
              >
                {link.label}
              </Link>
            ))}
            {isCustomer ? (
              <Link href="/performance" onClick={() => setOpen(false)} className="text-sm text-gray-300">
                My Dashboard
              </Link>
            ) : (
              <Link href="/login" onClick={() => setOpen(false)} className="text-sm text-gray-300">
                Login
              </Link>
            )}
          </div>
        </nav>
      ) : null}
    </header>
  )
}
