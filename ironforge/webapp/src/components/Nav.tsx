'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

/* ── Inline SVG Icons ──────────────────────────────────────────── */

function AnvilIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M2 18h20v2H2v-2zm3-2h14l1-3H10l-1-3h8V7H9L7 4H4v6l-2 3v1h3v2zm0 0"
        fill="#F59E0B"
      />
      <path
        d="M4 4h3l2 3h8v3H9l1 3h10l-1 3H5"
        stroke="#D97706"
        strokeWidth="0.5"
        fill="none"
      />
    </svg>
  )
}

function FlameIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 16 16" fill="none" className="inline-block mr-1.5 align-[-2px]">
      <path
        d="M8 1C8 1 3 6.5 3 10a5 5 0 0 0 10 0C13 6.5 8 1 8 1zm0 12.5a2.5 2.5 0 0 1-2.5-2.5c0-1.5 2.5-4.5 2.5-4.5s2.5 3 2.5 4.5A2.5 2.5 0 0 1 8 13.5z"
        fill="#F59E0B"
      />
    </svg>
  )
}

function SparkIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 16 16" fill="none" className="inline-block mr-1.5 align-[-2px]">
      <path
        d="M9.5 1L4 9h4l-1.5 6L13 7H9l.5-6z"
        fill="#3B82F6"
      />
    </svg>
  )
}

function InfernoIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 16 16" fill="none" className="inline-block mr-1.5 align-[-2px]">
      <path
        d="M8 0l2 5h-1.5l2.5 4h-2l2 5H5l2-5H5l2.5-4H6L8 0z"
        fill="#EF4444"
      />
    </svg>
  )
}

const botIcons: Record<string, React.ReactNode> = {
  FLAME: <FlameIcon />,
  SPARK: <SparkIcon />,
  INFERNO: <InfernoIcon />,
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
]

export default function Nav() {
  const pathname = usePathname()

  return (
    <nav className="border-b border-amber-900/30 bg-forge-bg/95 backdrop-blur-sm">
      <div className="max-w-7xl mx-auto px-4 py-2 flex items-center gap-8">
        <div className="flex flex-col items-start">
          <Link href="/" className="text-xl font-bold flex items-center gap-1.5">
            <AnvilIcon size={22} />
            <span className="text-white glow-amber">Iron</span>
            <span className="text-amber-400 glow-amber">Forge</span>
          </Link>
          <p style={{
            color: '#F59E0B',
            fontStyle: 'italic',
            fontSize: '0.75rem',
            fontFamily: "Georgia, 'Times New Roman', serif",
            letterSpacing: '0.05em',
            textAlign: 'center',
            maxWidth: '400px',
            margin: '4px auto 0 auto',
            opacity: 0.85,
          }}>
            &ldquo;As iron sharpens iron, so one person sharpens another.&rdquo; &mdash; Proverbs 27:17
          </p>
        </div>
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
