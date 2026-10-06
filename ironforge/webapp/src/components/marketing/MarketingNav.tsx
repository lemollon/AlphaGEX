'use client'

import Link from 'next/link'
import { useState } from 'react'
import { usePathname } from 'next/navigation'
import MarketingThemeToggle from './MarketingThemeToggle'
import { useWaitlistModal } from './WaitlistModal'
import { useHomeScrollSpy } from './useHomeScrollSpy'
import { track } from '@/lib/analytics/track'

// On the home page, "Agents" and "How it works" scroll to the page's own
// #home-agents/#home-how sections instead of navigating away (ps-nav #40).
// From any other page they still link to the full dedicated pages — the
// home-page sections and the agent/step "Compare all / Learn more" links
// cover deep linking into those.
const PRIMARY_LINKS = [
  { href: '/', label: 'Home', homeAnchor: null },
  { href: '/agents', label: 'Agents', homeAnchor: 'home-agents' },
  { href: '/how-it-works', label: 'How it works', homeAnchor: 'home-how' },
]

/**
 * Sticky header shared by every 10.4 marketing page. The source design is a
 * single-page app with hash routing (`#home`, `#agents.compare`, ...); the
 * dev-handoff spec says production should use real routes instead
 * (`/agents#compare`), which is what this does.
 */
export default function MarketingNav() {
  const pathname = usePathname()
  const isHome = pathname === '/'
  const [open, setOpen] = useState(false)
  const { openWaitlist } = useWaitlistModal()
  const { activeId, lockAndSet } = useHomeScrollSpy(isHome)

  function homeAnchorClick(anchor: string) {
    return (e: React.MouseEvent) => {
      e.preventDefault()
      lockAndSet(anchor)
      document.getElementById(anchor)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      window.history.replaceState(null, '', `#${anchor}`)
    }
  }

  return (
    <header className="nav">
      <div className="wrap">
        <Link className="wordmark" href="/" aria-label="IronForge home">
          IRON<b>FORGE</b>
        </Link>
        <nav className="links" aria-label="Primary">
          {PRIMARY_LINKS.map((l) =>
            isHome && l.homeAnchor ? (
              <a
                key={l.href}
                href={`#${l.homeAnchor}`}
                aria-current={activeId === l.homeAnchor ? 'true' : undefined}
                onClick={homeAnchorClick(l.homeAnchor)}
              >
                {l.label}
              </a>
            ) : (
              <Link
                key={l.href}
                href={l.homeAnchor ? `/#${l.homeAnchor}` : l.href}
                aria-current={pathname === l.href ? 'page' : undefined}
              >
                {l.label}
              </Link>
            )
          )}
        </nav>
        <div className="nav-r">
          <MarketingThemeToggle />
          <Link className="btn login" href="/login">
            Log in
          </Link>
          <button
            type="button"
            className="btn wl"
            onClick={() => {
              track('cta_click', { cta: 'waitlist', placement: 'nav' })
              openWaitlist('nav')
            }}
          >
            Join waitlist
          </button>
          <Link
            className="btn btn-accent join"
            href="/signup?source=site&placement=nav"
            onClick={() => track('cta_click', { cta: 'create_account', placement: 'nav' })}
          >
            Create account
          </Link>
          <button
            className="icon-btn menu"
            type="button"
            aria-expanded={open}
            aria-controls="marketing-drawer"
            aria-label="Open menu"
            onClick={() => setOpen((v) => !v)}
          >
            <svg>
              <use href="#i-menu" />
            </svg>
          </button>
        </div>
      </div>
      <div className="wrap drawer" id="marketing-drawer" hidden={!open}>
        {PRIMARY_LINKS.map((l) =>
          isHome && l.homeAnchor ? (
            <a
              key={l.href}
              href={`#${l.homeAnchor}`}
              onClick={(e) => {
                setOpen(false)
                homeAnchorClick(l.homeAnchor!)(e)
              }}
            >
              {l.label}
            </a>
          ) : (
            <Link key={l.href} href={l.homeAnchor ? `/#${l.homeAnchor}` : l.href} onClick={() => setOpen(false)}>
              {l.label}
            </Link>
          )
        )}
        <Link href="/pricing" onClick={() => setOpen(false)}>
          Pricing
        </Link>
        <Link href="/about" onClick={() => setOpen(false)}>
          About
        </Link>
        <button
          type="button"
          onClick={() => {
            setOpen(false)
            track('cta_click', { cta: 'waitlist', placement: 'nav' })
            openWaitlist('nav')
          }}
        >
          Join the waitlist
        </button>
        <Link href="/login" onClick={() => setOpen(false)}>
          Log in
        </Link>
      </div>
    </header>
  )
}
