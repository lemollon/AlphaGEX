'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import type { VolAlert } from '@/lib/volAlerts'
import { BOT_COLORS } from '@/lib/botColors'
import AuthControls from './AuthControls'

/**
 * Unobtrusive bell + count of active volatility alerts, linking to /volatility.
 * Hidden entirely when the count is 0. Refreshes every 60s.
 */
function VolAlertBadge() {
  const { data } = useSWR<{ alerts: VolAlert[] }>(
    '/api/vol-alerts?status=active',
    fetcher,
    { refreshInterval: 60_000 },
  )
  const count = data?.alerts?.length ?? 0
  if (count <= 0) return null
  return (
    <Link
      href="/volatility"
      title={`${count} active volatility alert${count === 1 ? '' : 's'}`}
      className="relative inline-flex items-center text-violet-400 hover:text-violet-300 transition-colors"
    >
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path
          d="M8 2a3 3 0 0 0-3 3c0 3-1.2 4.2-2 5h10c-0.8-0.8-2-2-2-5a3 3 0 0 0-3-3Z"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinejoin="round"
        />
        <path d="M6.5 13a1.5 1.5 0 0 0 3 0" stroke="currentColor" strokeWidth="1.2" />
      </svg>
      <span className="ml-0.5 min-w-[16px] rounded-full bg-violet-500/25 px-1 text-[10px] font-semibold leading-4 text-violet-200 text-center">
        {count}
      </span>
    </Link>
  )
}

// Per-bot identity is shown as a single small colored dot (not mismatched icon
// art) — the one place a bot's color appears in the nav. Color from the SoT.
const BOT_DOT: Record<string, string> = {
  FLAME: BOT_COLORS.flame,
  SPARK: BOT_COLORS.spark,
  INFERNO: BOT_COLORS.inferno,
  BLAZE: BOT_COLORS.blaze,
  FLARE: BOT_COLORS.flare,
  KINDLE: '#fbbf24', // amber — KINDLE (1DTE IC, $500 live, SPARK strategy)
}

function botDot(label: string): React.ReactNode {
  const c = BOT_DOT[label]
  if (!c) return null
  return (
    <span
      className="inline-block w-1.5 h-1.5 rounded-full mr-2 align-[1px] shrink-0"
      style={{ background: c, boxShadow: `0 0 6px ${c}` }}
    />
  )
}

// Nav links carry no colored text glow — the dot is the only identity cue.
const botGlow: Record<string, string> = {}

/** Bots with trading accounts get a green dot; paper-only get nothing.
 *  SPARK is the only bot wired to a real Tradier production account (Iron Viper). */
const ACCOUNT_BOTS = new Set(['SPARK'])

type NavLink = { href: string; label: string; className?: string; external?: boolean }

// Primary row — always visible. Home, the five bots, GEX, Compare.
const primaryLinks: NavLink[] = [
  { href: '/', label: 'Home' },
  { href: '/spark', label: 'SPARK', className: 'text-gray-300 hover:text-white' },
  { href: '/live', label: 'SPARK V2', className: 'text-gray-300 hover:text-white' },
  { href: '/kindle', label: 'KINDLE', className: 'text-gray-300 hover:text-white' },
  { href: '/flame', label: 'FLAME', className: 'text-gray-300 hover:text-white' },
  { href: '/inferno', label: 'INFERNO', className: 'text-gray-300 hover:text-white' },
  { href: '/blaze', label: 'BLAZE', className: 'text-gray-300 hover:text-white' },
  { href: '/flare', label: 'FLARE', className: 'text-gray-300 hover:text-white' },
  { href: '/compare', label: 'Compare' },
]

// Secondary — folded into a "More ▾" dropdown to declutter the row.
const moreLinks: NavLink[] = [
  { href: '/gex', label: 'GEX Profile', className: 'text-gray-300 hover:text-gray-100' },
  { href: '/volatility', label: 'Volatility', className: 'text-gray-300 hover:text-gray-100' },
  { href: '/calendar', label: 'Calendar', className: 'text-gray-300 hover:text-gray-100' },
  { href: '/briefings', label: 'Briefings', className: 'text-gray-300 hover:text-gray-100' },
  { href: '/accounts', label: 'Accounts', className: 'text-gray-300 hover:text-gray-100' },
  { href: '/pricing', label: 'Pricing', className: 'text-amber-400 hover:text-amber-300' },
  { href: '/ember', label: 'EMBER', className: 'text-amber-400 hover:text-amber-300' },
]

function NavLinkItem({
  link,
  pathname,
  onClick,
  block,
}: {
  link: NavLink
  pathname: string
  onClick?: () => void
  block?: boolean
}) {
  const isActive = pathname === link.href
  const icon = botDot(link.label)
  const glow = botGlow[link.label] || ''
  const baseColor = link.className || 'text-gray-400 hover:text-gray-200'
  const activeColor = 'text-white underline underline-offset-4 decoration-amber-500'
  const className = `${block ? 'block px-4 py-2 ' : ''}text-sm font-medium whitespace-nowrap transition-colors ${glow} ${
    isActive ? activeColor : baseColor
  }`
  const content = (
    <>
      {icon}{link.label}
      {ACCOUNT_BOTS.has(link.label) && (
        <span
          className="inline-block w-1.5 h-1.5 rounded-full bg-green-400 ml-1 align-[1px]"
          title="Account Trading"
        />
      )}
    </>
  )
  if (link.external) {
    return (
      <a href={link.href} className={className} onClick={onClick}>
        {content}
      </a>
    )
  }
  return (
    <Link href={link.href} className={className} onClick={onClick}>
      {content}
    </Link>
  )
}

export default function Nav() {
  const pathname = usePathname()
  const [moreOpen, setMoreOpen] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const moreRef = useRef<HTMLDivElement>(null)

  // Close the More dropdown on outside click / Escape.
  useEffect(() => {
    if (!moreOpen) return
    const onClick = (e: MouseEvent) => {
      if (!moreRef.current?.contains(e.target as Node)) setMoreOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMoreOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [moreOpen])

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    setMobileOpen(false)
  }, [pathname])

  return (
    <nav className="relative z-[60] border-b border-amber-900/30 bg-forge-bg/95 backdrop-blur-sm">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-4">
        {/* Logo + subtitle underneath, left-aligned */}
        <div className="flex flex-col items-start shrink-0">
          <Link href="/" className="text-xl font-bold font-display flex items-center gap-1.5">
            <img src="/ironforge-mark.png" alt="" className="h-7 w-auto inline-block" />
            <span className="text-white">Iron</span>
            <span className="text-amber-400">Forge</span>
          </Link>
          {/* Proverbs verse — hidden on small screens to keep the bar compact */}
          <span
            className="hidden xl:block"
            style={{
              color: '#C7C1B6',
              fontSize: '0.75rem',
              fontFamily: "Georgia, 'Times New Roman', serif",
              fontStyle: 'italic',
              letterSpacing: '0.06em',
              lineHeight: 1,
              marginTop: '-1px',
              paddingLeft: '1.15rem',
              textShadow: 'none',
              maxWidth: '24rem',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            &ldquo;As iron sharpens iron, so one person sharpens another.&rdquo; &mdash;{' '}
            <span style={{ color: '#FF5500', fontStyle: 'normal', fontWeight: 600 }}>Proverbs 27:17</span>
          </span>
        </div>

        {/* Desktop links + auth — hidden below md, where the hamburger takes over */}
        <div className="hidden lg:flex flex-1 items-center gap-4">
          <div className="flex gap-4 items-center">
            {primaryLinks.map((link) => (
              <NavLinkItem key={link.href} link={link} pathname={pathname} />
            ))}

            <VolAlertBadge />

            <div ref={moreRef} className="relative">
              <button
                type="button"
                onClick={() => setMoreOpen((o) => !o)}
                aria-haspopup="menu"
                aria-expanded={moreOpen}
                className="text-sm font-medium text-gray-400 hover:text-gray-200 transition-colors flex items-center gap-1"
              >
                More
                <svg
                  width="10"
                  height="10"
                  viewBox="0 0 10 10"
                  aria-hidden="true"
                  className={`transition-transform ${moreOpen ? 'rotate-180' : ''}`}
                >
                  <path d="M2 4 L5 7 L8 4" stroke="currentColor" strokeWidth="1.2" fill="none" />
                </svg>
              </button>
              {moreOpen && (
                <div
                  role="menu"
                  className="absolute right-0 top-full mt-2 min-w-[180px] border border-amber-900/40 bg-forge-bg/95 backdrop-blur-sm py-2 shadow-2xl z-50"
                >
                  {moreLinks.map((link) => (
                    <NavLinkItem
                      key={link.href}
                      link={link}
                      pathname={pathname}
                      block
                      onClick={() => setMoreOpen(false)}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>

          <AuthControls />
        </div>

        {/* Mobile hamburger — only below md */}
        <button
          type="button"
          onClick={() => setMobileOpen((o) => !o)}
          aria-label="Toggle navigation menu"
          aria-expanded={mobileOpen}
          aria-controls="mobile-nav"
          className="lg:hidden ml-auto inline-flex items-center justify-center w-10 h-10 rounded-md text-gray-300 hover:text-white hover:bg-amber-900/20 transition-colors"
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            {mobileOpen ? (
              <path d="M6 6 L18 18 M18 6 L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            ) : (
              <path d="M4 7 H20 M4 12 H20 M4 17 H20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            )}
          </svg>
        </button>
      </div>

      {/* Mobile drawer — stacked links, only below md */}
      {mobileOpen && (
        <div
          id="mobile-nav"
          className="lg:hidden border-t border-amber-900/30 bg-forge-bg/98 backdrop-blur-sm px-2 py-2"
        >
          <div className="flex flex-col">
            {[...primaryLinks, ...moreLinks].map((link) => (
              <NavLinkItem
                key={link.href}
                link={link}
                pathname={pathname}
                block
                onClick={() => setMobileOpen(false)}
              />
            ))}
          </div>
          <div className="mt-2 pt-2 border-t border-amber-900/20 px-2 flex items-center justify-between">
            <VolAlertBadge />
            <AuthControls />
          </div>
        </div>
      )}
    </nav>
  )
}
