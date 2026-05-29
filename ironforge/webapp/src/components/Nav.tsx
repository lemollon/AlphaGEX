'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import AuthControls from './AuthControls'

const botIcons: Record<string, React.ReactNode> = {
  FLAME: <img src="/icon-flame.svg" alt="" className="h-4 w-4 inline-block mr-1.5 align-[-2px]" />,
  SPARK: <img src="/icon-spark.svg" alt="" className="h-4 w-4 inline-block mr-1.5 align-[-2px]" />,
  INFERNO: <img src="/icon-inferno.svg" alt="" className="h-4 w-4 inline-block mr-1.5 align-[-2px]" />,
  BLAZE: <img src="/icon-blaze.svg" alt="" className="h-4 w-4 inline-block mr-1.5 align-[-2px]" />,
  FLARE: <img src="/icon-flare.svg" alt="" className="h-4 w-4 inline-block mr-1.5 align-[-2px]" />,
}

const botGlow: Record<string, string> = {
  FLAME: 'glow-flame',
  SPARK: 'glow-spark',
  INFERNO: 'glow-inferno',
  BLAZE: 'glow-inferno',
  FLARE: 'glow-inferno',
}

/** Bots with trading accounts get a green dot; paper-only get nothing.
 *  SPARK is the only bot wired to a real Tradier production account (Iron Viper). */
const ACCOUNT_BOTS = new Set(['SPARK'])

type NavLink = { href: string; label: string; className?: string; external?: boolean }

// Primary row — always visible. Home, the five bots, GEX, Compare.
const primaryLinks: NavLink[] = [
  { href: '/', label: 'Home' },
  { href: '/spark', label: 'SPARK', className: 'text-blue-400 hover:text-blue-300' },
  { href: '/flame', label: 'FLAME', className: 'text-amber-400 hover:text-amber-300' },
  { href: '/inferno', label: 'INFERNO', className: 'text-red-400 hover:text-red-300' },
  { href: '/blaze', label: 'BLAZE', className: 'text-orange-400 hover:text-orange-300' },
  { href: '/flare', label: 'FLARE', className: 'text-fuchsia-400 hover:text-fuchsia-300' },
  { href: '/gex', label: 'GEX Profile', className: 'text-cyan-400 hover:text-cyan-300' },
  { href: '/compare', label: 'Compare' },
]

// Secondary — folded into a "More ▾" dropdown to declutter the row.
const moreLinks: NavLink[] = [
  { href: '/calendar', label: 'Calendar', className: 'text-gray-300 hover:text-gray-100' },
  { href: '/briefings', label: 'Briefings', className: 'text-gray-300 hover:text-gray-100' },
  { href: '/accounts', label: 'Accounts', className: 'text-gray-300 hover:text-gray-100' },
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
  const icon = botIcons[link.label]
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

  return (
    <nav className="border-b border-amber-900/30 bg-forge-bg/95 backdrop-blur-sm">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-8">
        {/* Logo + subtitle underneath, left-aligned */}
        <div className="flex flex-col items-start shrink-0">
          <Link href="/" className="text-xl font-bold flex items-center gap-1.5">
            <img src="/ironforge-logo.svg" alt="" className="h-8 w-8 inline-block" />
            <span className="text-white">Iron</span>
            <span className="text-amber-400">Forge</span>
          </Link>
          <span
            style={{
              color: '#FCD34D',
              fontSize: '0.75rem',
              fontFamily: "Georgia, 'Times New Roman', serif",
              fontStyle: 'italic',
              letterSpacing: '0.06em',
              lineHeight: 1,
              marginTop: '-1px',
              paddingLeft: '1.15rem',
              textShadow: '0 1px 3px rgba(0,0,0,0.8), 0 0 8px rgba(251,191,36,0.5)',
            }}
          >
            &ldquo;As iron sharpens iron, so one person sharpens another.&rdquo; &mdash; Proverbs 27:17
          </span>
        </div>

        {/* Primary links + More dropdown */}
        <div className="flex gap-6 items-center">
          {primaryLinks.map((link) => (
            <NavLinkItem key={link.href} link={link} pathname={pathname} />
          ))}

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
    </nav>
  )
}
