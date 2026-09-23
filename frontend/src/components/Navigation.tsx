'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  Activity,
  Bitcoin,
  Menu,
  X,
} from 'lucide-react'
import { useState } from 'react'
import BuildVersion from './BuildVersion'
import { CrossButton, DedicationModal, StewardshipBanner, StewardshipTagline } from './StewardshipBanner'

const navItems = [
  { href: '/valor', label: 'VALOR Futures', icon: Activity },
  { href: '/perpetuals-crypto', label: 'Crypto Perpetuals', icon: Bitcoin },
  { href: '/agape-btc-perp', label: 'BTC Perpetual', icon: Bitcoin },
  { href: '/agape-eth-perp', label: 'ETH Perpetual', icon: Bitcoin },
  { href: '/agape-sol-perp', label: 'SOL Perpetual', icon: Bitcoin },
  { href: '/agape-avax-perp', label: 'AVAX Perpetual', icon: Bitcoin },
  { href: '/agape-xrp-perp', label: 'XRP Perpetual', icon: Bitcoin },
  { href: '/agape-doge-perp', label: 'DOGE Perpetual', icon: Bitcoin },
]

export default function Navigation() {
  const pathname = usePathname()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [dedicationModalOpen, setDedicationModalOpen] = useState(false)

  // Mobile drawer list (unchanged behavior — click-triggered overlay, not a hover rail)
  const renderItems = (mobile = false) => (
    <div className="space-y-1">
      {navItems.map((item) => {
        const Icon = item.icon
        const active = pathname === item.href
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={() => mobile && setMobileMenuOpen(false)}
            className={
              'flex items-center rounded-lg font-medium transition-all text-sm px-3 py-2.5 space-x-3 ' +
              (active
                ? 'bg-primary text-white shadow-lg'
                : 'text-text-secondary hover:text-text-primary hover:bg-background-hover')
            }
          >
            <Icon className="w-5 h-5 flex-shrink-0" />
            <span className="truncate">{item.label}</span>
          </Link>
        )
      })}
    </div>
  )

  // Desktop top-bar link row (replaces the old hover-expand left rail)
  const renderTopBarItems = () => (
    <div className="hidden lg:flex items-center gap-1 overflow-x-hidden">
      {navItems.map((item) => {
        const active = pathname === item.href
        return (
          <Link
            key={item.href}
            href={item.href}
            title={item.label}
            className={
              'whitespace-nowrap rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ' +
              (active
                ? 'bg-primary text-white shadow-lg'
                : 'text-text-secondary hover:text-text-primary hover:bg-background-hover')
            }
          >
            {item.label}
          </Link>
        )
      })}
    </div>
  )

  return (
    <>
      <nav className="fixed top-0 left-0 right-0 z-50 bg-background-card border-b border-gray-800 h-16">
        <div className="flex items-center justify-between h-full px-4">
          <div className="flex items-center space-x-4">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="lg:hidden p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-background-hover"
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

      <div className="fixed top-16 left-0 right-0 z-40">
        <StewardshipBanner />
      </div>

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
          'lg:hidden fixed top-16 left-0 bottom-0 z-50 bg-background-card border-r border-gray-800 ' +
          'transition-transform duration-300 ease-in-out w-64 overflow-y-auto ' +
          (mobileMenuOpen ? 'translate-x-0' : '-translate-x-full')
        }
      >
        <div className="p-4">
          {renderItems(true)}
          <div className="mt-6 pt-4 border-t border-gray-800">
            <BuildVersion />
          </div>
        </div>
      </aside>
    </>
  )
}
