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
  // Public proof surface — reachable with no account, unlike /live and /performance.
  // Replaced /track-record on 2026-07-27; that URL now 308s here.
  { href: '/bot-ledger', label: 'Bot Ledger' },
  { href: '/pricing', label: 'Pricing' },
]

// App links that live BEHIND the login. Only rendered for signed-in customers;
// a logged-out visitor never sees them (the pages themselves also require a
// session — this just stops the public nav from advertising a locked door).
const APP_LINKS: ReadonlyArray<{ href: string; label: string }> = [
  { href: '/live', label: 'Live' },
  { href: '/community', label: 'Community' },
]

// `active` is retained for backward compatibility with existing callers
// (page.tsx passes "home"); the current page is now derived from the pathname.
export default function HomeNav({ active: _active }: { active?: string } = {}) {
  const [open, setOpen] = useState(false)
  const [isCustomer, setIsCustomer] = useState(false)
  const pathname = usePathname()

  useEffect(() => {
    // Logged-in customers get "My Dashboard" instead of Login/Create Account.
    fetch('/api/auth/customer-me')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setIsCustomer(Boolean(d?.ok)))
      .catch(() => setIsCustomer(false))
  }, [])

  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : pathname.startsWith(href)

  // The public marketing links, plus the behind-login app links only once signed in.
  const visibleLinks = isCustomer ? [...NAV_LINKS, ...APP_LINKS] : NAV_LINKS

  return (
    <header className="sticky top-0 z-50 border-b border-white/5 bg-black">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-5 md:px-8">
        <Link href="/" aria-label="IronForge home">
          <Wordmark markClass="h-8 w-auto" textClass="text-lg" />
        </Link>

        {/* Desktop links */}
        <nav className="hidden items-center gap-8 md:flex">
          {visibleLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={
                isActive(link.href)
                  ? 'border-b-2 border-[#FD5301] pb-0.5 text-sm font-semibold text-white'
                  : 'text-sm text-gray-300 transition-colors hover:text-white'
              }
            >
              {link.label}
            </Link>
          ))}
          {isCustomer ? (
            <Link
              href="/performance"
              className="rounded-lg bg-[#FD5301] px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-[#FF6A1F]"
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
                className="rounded-lg border border-[#FD5301] px-4 py-2 text-sm font-semibold text-[#FD5301] transition-colors hover:bg-[#FD5301] hover:text-white"
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
            className="rounded-lg bg-[#FD5301] px-3.5 py-2 text-sm font-semibold text-white"
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
