'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Wordmark } from '@/components/Brand'
import { MenuIcon, CloseIcon } from './icons'

/* Sticky top navigation per the handoff spec: logo, Home, How It Works, Login,
 * Create Account on desktop; logo + solid Create Account + hamburger on mobile.
 * Operators additionally get an "Ops" item next to Home (invisible to everyone
 * else — same status probe as the AdminBadge, which reveals nothing without an
 * operator session). */
export default function HomeNav({ active = 'home' }: { active?: 'home' | 'how-it-works' }) {
  const [open, setOpen] = useState(false)
  const [isOperator, setIsOperator] = useState(false)
  const [isCustomer, setIsCustomer] = useState(false)

  useEffect(() => {
    fetch('/api/ops/impersonate?status=true')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setIsOperator(Boolean(d?.operator)))
      .catch(() => setIsOperator(false))
    // Logged-in customers get "Dashboard" instead of Login/Create Account.
    fetch('/api/auth/customer-me')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setIsCustomer(Boolean(d?.ok)))
      .catch(() => setIsCustomer(false))
  }, [])

  return (
    <header className="sticky top-0 z-50 border-b border-white/5 bg-black">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-5 md:px-8">
        <Link href="/" aria-label="IronForge home">
          <Wordmark markClass="h-8 w-auto" textClass="text-lg" />
        </Link>

        {/* Desktop links */}
        <nav className="hidden items-center gap-8 md:flex">
          <Link
            href="/"
            className={
              active === 'home'
                ? 'border-b-2 border-[#FD5301] pb-0.5 text-sm font-semibold text-white'
                : 'text-sm text-gray-300 transition-colors hover:text-white'
            }
          >
            Home
          </Link>
          {isOperator ? (
            <Link
              href="/spark"
              className="text-sm font-semibold text-[#FD5301] transition-colors hover:text-[#FF6A1F]"
            >
              Ops
            </Link>
          ) : null}
          <Link
            href="/how-it-works"
            className={
              active === 'how-it-works'
                ? 'border-b-2 border-[#FD5301] pb-0.5 text-sm font-semibold text-white'
                : 'text-sm text-gray-300 transition-colors hover:text-white'
            }
          >
            How It Works
          </Link>
          {isCustomer ? (
            <Link
              href="/home"
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
            href={isCustomer ? '/home' : '/signup'}
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
            <Link href="/" onClick={() => setOpen(false)} className="text-sm font-semibold text-white">
              Home
            </Link>
            {isOperator ? (
              <Link href="/spark" onClick={() => setOpen(false)} className="text-sm font-semibold text-[#FD5301]">
                Ops
              </Link>
            ) : null}
            <Link href="/how-it-works" onClick={() => setOpen(false)} className="text-sm text-gray-300">
              How It Works
            </Link>
            {isCustomer ? (
              <Link href="/home" onClick={() => setOpen(false)} className="text-sm text-gray-300">
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
