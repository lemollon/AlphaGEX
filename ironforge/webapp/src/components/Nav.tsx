'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const botIcons: Record<string, React.ReactNode> = {
  FLAME: <img src="/icon-flame.svg" alt="" className="h-4 w-4 inline-block mr-1.5 align-[-2px]" />,
  SPARK: <img src="/icon-spark.svg" alt="" className="h-4 w-4 inline-block mr-1.5 align-[-2px]" />,
  INFERNO: <img src="/inferno-icon.svg" alt="" className="h-4 w-4 inline-block mr-1.5 align-[-2px]" />,
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
              fontSize: '0.95rem',
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
