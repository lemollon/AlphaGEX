'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

/* ── Inline SVG Icons ──────────────────────────────────────────── */

function FlamingHammerIcon({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* Flames rising from hammer head */}
      <path
        d="M7 2c0 0 2 1.5 1.5 3.5S6 8 7 9.5c.7 1 2 1 2 1s-1-1.2-.5-2.5S10 6 9.5 4.5 7 2 7 2z"
        fill="#F59E0B"
        opacity="0.9"
      />
      <path
        d="M11 1c0 0 1.5 1.5 1 3s-2 2-1.5 3.5c.3.8 1.2 1.2 1.2 1.2s-.5-1 0-2.2 1-2 .5-3.2S11 1 11 1z"
        fill="#EF4444"
        opacity="0.8"
      />
      <path
        d="M14.5 2.5c0 0 1 1 .5 2.5s-1.5 1.5-1 3c.3.7 1 .8 1 .8s-.3-.8 0-1.8.5-1.5.2-2.7-.7-1.8-.7-1.8z"
        fill="#F59E0B"
        opacity="0.7"
      />
      {/* Hammer head */}
      <rect x="4" y="9" width="14" height="5" rx="1" fill="#D97706" />
      <rect x="4" y="9" width="14" height="2.5" rx="1" fill="#F59E0B" />
      {/* Hammer handle */}
      <rect x="10" y="14" width="3" height="8" rx="0.5" fill="#92400E" />
      <rect x="10.5" y="14" width="1" height="8" rx="0.3" fill="#A16207" opacity="0.5" />
    </svg>
  )
}

const botIcons: Record<string, React.ReactNode> = {
  FLAME: <img src="/icon-flame.svg" alt="" className="h-4 w-4 inline-block mr-1.5 align-[-2px]" />,
  SPARK: <img src="/icon-spark.svg" alt="" className="h-4 w-4 inline-block mr-1.5 align-[-2px]" />,
  INFERNO: <img src="/icon-inferno.svg" alt="" className="h-4 w-4 inline-block mr-1.5 align-[-2px]" />,
}

const botGlow: Record<string, string> = {
  FLAME: 'glow-flame',
  SPARK: 'glow-spark',
  INFERNO: 'glow-inferno',
}

const links = [
  { href: '/', label: 'Home' },
  { href: '/spark', label: 'SPARK', className: 'text-blue-400 hover:text-blue-300' },
  { href: '/flame', label: 'FLAME', className: 'text-amber-400 hover:text-amber-300' },
  { href: '/inferno', label: 'INFERNO', className: 'text-red-400 hover:text-red-300' },
  { href: '/compare', label: 'Compare' },
  { href: '/accounts', label: 'Accounts', className: 'text-gray-400 hover:text-gray-200' },
]

export default function Nav() {
  const pathname = usePathname()

  return (
    <nav className="border-b border-amber-900/30 bg-forge-bg/95 backdrop-blur-sm">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-8">
        {/* Logo + subtitle stacked */}
        <div className="flex flex-col items-start shrink-0">
          <Link href="/" className="text-xl font-bold flex items-center gap-1.5">
            <img src="/ironforge-logo.svg" alt="" className="h-8 w-8 inline-block" />
            <span className="text-white">Iron</span>
            <span className="text-amber-400">Forge</span>
          </Link>
          <span
            style={{
              color: '#FBBF24',
              fontSize: '0.5rem',
              fontFamily: "Georgia, 'Times New Roman', serif",
              fontStyle: 'italic',
              letterSpacing: '0.08em',
              lineHeight: 1,
              marginTop: '-1px',
              paddingLeft: '1.15rem',
              textShadow: '0 0 6px rgba(251,191,36,0.6), 0 0 14px rgba(245,158,11,0.4)',
            }}
          >
            &ldquo;As iron sharpens iron, so one person sharpens another.&rdquo; &mdash; Proverbs 27:17
          </span>
        </div>

        {/* Nav links */}
        <div className="flex gap-6">
          {links.map((link) => {
            const isActive = pathname === link.href
            const icon = botIcons[link.label]
            const glow = botGlow[link.label] || ''
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`text-sm font-medium transition-colors ${glow} ${
                  isActive
                    ? 'text-white underline underline-offset-4 decoration-amber-500'
                    : link.className || 'text-gray-400 hover:text-gray-200'
                }`}
              >
                {icon}{link.label}
              </Link>
            )
          })}
        </div>
      </div>
    </nav>
  )
}
