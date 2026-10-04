'use client'

import Link from 'next/link'
import { useState } from 'react'
import { usePathname } from 'next/navigation'
import MarketingThemeToggle from './MarketingThemeToggle'

const PRIMARY_LINKS = [
  { href: '/', label: 'Home' },
  { href: '/agents', label: 'Agents' },
  { href: '/how-it-works', label: 'How it works' },
]

/**
 * Sticky header shared by every 10.4 marketing page. The source design is a
 * single-page app with hash routing (`#home`, `#agents.compare`, ...); the
 * dev-handoff spec says production should use real routes instead
 * (`/agents#compare`), which is what this does.
 */
export default function MarketingNav() {
  const pathname = usePathname()
  const [open, setOpen] = useState(false)

  return (
    <header className="nav">
      <div className="wrap">
        <Link className="wordmark" href="/" aria-label="IronForge home">
          IRON<b>FORGE</b>
        </Link>
        <nav className="links" aria-label="Primary">
          {PRIMARY_LINKS.map((l) => (
            <Link key={l.href} href={l.href} aria-current={pathname === l.href ? 'page' : undefined}>
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="nav-r">
          <MarketingThemeToggle />
          <Link className="btn login" href="/login">
            Log in
          </Link>
          <Link className="btn wl" href="/waitlist">
            Join waitlist
          </Link>
          <Link className="btn btn-accent join" href="/signup?source=site&placement=nav">
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
        {PRIMARY_LINKS.map((l) => (
          <Link key={l.href} href={l.href} onClick={() => setOpen(false)}>
            {l.label}
          </Link>
        ))}
        <Link href="/pricing" onClick={() => setOpen(false)}>
          Pricing
        </Link>
        <Link href="/about" onClick={() => setOpen(false)}>
          About
        </Link>
        <Link href="/waitlist" onClick={() => setOpen(false)}>
          Join the waitlist
        </Link>
        <Link href="/login" onClick={() => setOpen(false)}>
          Log in
        </Link>
      </div>
    </header>
  )
}
