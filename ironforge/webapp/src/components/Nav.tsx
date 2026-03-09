'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

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
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-8">
        <Link href="/" className="text-xl font-bold flex items-center gap-1.5">
          <span className="text-amber-500">&#9632;</span>
          <span className="text-white">Iron</span>
          <span className="text-amber-400">Forge</span>
        </Link>
        <div className="flex gap-6">
          {links.map((link) => {
            const isActive = pathname === link.href
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`text-sm font-medium transition-colors ${
                  isActive
                    ? 'text-white underline underline-offset-4 decoration-amber-500'
                    : link.className || 'text-gray-400 hover:text-gray-200'
                }`}
              >
                {link.label}
              </Link>
            )
          })}
        </div>
      </div>
    </nav>
  )
}
