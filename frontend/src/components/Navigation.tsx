'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Activity, Menu, X } from 'lucide-react'
import { useState } from 'react'
import BuildVersion from './BuildVersion'
import { CrossButton, DedicationModal, StewardshipTagline } from './StewardshipBanner'

// Global top nav — exactly two links (design handoff §1).
// "Crypto Perps" stays active across the whole AGAPE derivatives area:
// the hub itself plus the legacy /agape-perps and /agape-{coin}-perp
// routes, which now redirect into it.
const navItems: { href: string; label: string; isActive: (pathname: string) => boolean }[] = [
  {
    href: '/valor',
    label: 'VALOR Futures',
    isActive: (pathname) => pathname === '/valor' || pathname.startsWith('/valor/'),
  },
  {
    href: '/perpetuals-crypto',
    label: 'Crypto Perps',
    isActive: (pathname) =>
      pathname === '/perpetuals-crypto' ||
      pathname === '/agape-perps' ||
      /^\/agape-[a-z0-9]+-perp$/.test(pathname),
  },
]

export default function Navigation() {
  const pathname = usePathname()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [dedicationModalOpen, setDedicationModalOpen] = useState(false)

  // Mobile drawer list — same two items as the top bar.
  const renderItems = (mobile = false) => (
    <div className="space-y-1">
      {navItems.map((item) => {
        const active = item.isActive(pathname)
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={() => mobile && setMobileMenuOpen(false)}
            className={
              'block rounded-lg text-sm px-3 py-2.5 transition-colors ' +
              (active
                ? 'text-[#f3f4f6] font-semibold bg-[#1a1f2e]'
                : 'text-[#9ca3af] font-medium hover:text-[#f3f4f6] hover:bg-[#1a1f2e]')
            }
          >
            {item.label}
          </Link>
        )
      })}
    </div>
  )

  // Desktop top-bar link row — full-height, 2px yellow underline when active.
  const renderTopBarItems = () => (
    <nav className="hidden lg:flex items-stretch h-full gap-1">
      {navItems.map((item) => {
        const active = item.isActive(pathname)
        return (
          <Link
            key={item.href}
            href={item.href}
            className={
              'flex items-center h-full px-[14px] text-[14px] border-b-2 transition-colors ' +
              (active
                ? 'text-[#f3f4f6] font-semibold border-[#eab308]'
                : 'text-[#9ca3af] font-medium border-transparent hover:text-[#f3f4f6]')
            }
          >
            {item.label}
          </Link>
        )
      })}
    </nav>
  )

  return (
    <>
      <nav className="fixed top-0 left-0 right-0 z-50 bg-[#0c1019] border-b border-[#1c2233] h-16">
        <div className="flex items-center justify-between h-full px-4">
          <div className="flex items-center space-x-4">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="lg:hidden p-2 rounded-lg text-[#9ca3af] hover:text-[#f3f4f6] hover:bg-[#1a1f2e]"
              aria-label="Toggle mobile menu"
            >
              {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>

            <Link href="/valor" className="flex items-center space-x-2">
              <Activity className="w-8 h-8 text-primary" />
              <div className="flex flex-col">
                <span className="text-xl font-bold text-text-primary leading-tight">AlphaGEX</span>
                <StewardshipTagline />
              </div>
            </Link>

            <CrossButton onClick={() => setDedicationModalOpen(true)} />
          </div>

          {renderTopBarItems()}
        </div>
      </nav>

      <DedicationModal
        isOpen={dedicationModalOpen}
        onClose={() => setDedicationModalOpen(false)}
      />

      {mobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      <aside
        className={
          'lg:hidden fixed top-16 left-0 bottom-0 z-50 bg-[#0c1019] border-r border-[#1c2233] ' +
          'transition-transform duration-300 ease-in-out w-64 overflow-y-auto ' +
          (mobileMenuOpen ? 'translate-x-0' : '-translate-x-full')
        }
      >
        <div className="p-4">
          {renderItems(true)}
          <div className="mt-6 pt-4 border-t border-[#1c2233]">
            <BuildVersion />
          </div>
        </div>
      </aside>
    </>
  )
}
