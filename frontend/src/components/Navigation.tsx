'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  Activity,
  Bitcoin,
  ChevronLeft,
  ChevronRight,
  Menu,
  Pin,
  PinOff,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { useSidebar } from '@/contexts/SidebarContext'
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
  const { isPinned, setIsPinned, isHovered, setIsHovered, isExpanded } = useSidebar()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [dedicationModalOpen, setDedicationModalOpen] = useState(false)

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
            title={!mobile && !isExpanded ? item.label : undefined}
            className={
              'flex items-center rounded-lg font-medium transition-all text-sm ' +
              (mobile || isExpanded ? 'px-3 py-2.5 space-x-3 ' : 'px-3 py-2.5 justify-center ') +
              (active
                ? 'bg-primary text-white shadow-lg'
                : 'text-text-secondary hover:text-text-primary hover:bg-background-hover')
            }
          >
            <Icon className="w-5 h-5 flex-shrink-0" />
            {(mobile || isExpanded) && <span className="truncate">{item.label}</span>}
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

          <div className="hidden sm:flex items-center gap-2 text-sm text-text-secondary">
            <span>VALOR</span>
            <span>•</span>
            <span>Crypto Perpetuals</span>
          </div>
        </div>
      </nav>

      <div className="fixed top-16 left-0 right-0 z-40">
        <StewardshipBanner />
      </div>

      <DedicationModal
        isOpen={dedicationModalOpen}
        onClose={() => setDedicationModalOpen(false)}
      />

      <aside
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className={
          'hidden lg:block fixed top-16 left-0 bottom-0 z-40 bg-background-card border-r border-gray-800 ' +
          'transition-all duration-300 ease-in-out overflow-hidden ' +
          (isExpanded ? 'w-64' : 'w-16')
        }
      >
        <div className="h-full flex flex-col">
          <div className="flex-1 overflow-y-auto overflow-x-hidden py-4 px-2">
            {renderItems()}
          </div>

          <div className="border-t border-gray-800 p-2">
            <button
              onClick={() => setIsPinned(!isPinned)}
              title={isPinned ? 'Unpin sidebar' : 'Pin sidebar open'}
              className={
                'w-full flex items-center rounded-lg text-text-secondary hover:text-text-primary ' +
                'hover:bg-background-hover transition-all ' +
                (isExpanded ? 'px-3 py-2 space-x-3' : 'px-3 py-2 justify-center')
              }
            >
              {isPinned
                ? <PinOff className="w-5 h-5 flex-shrink-0" />
                : <Pin className="w-5 h-5 flex-shrink-0" />}
              {isExpanded && <span className="text-sm">{isPinned ? 'Unpin Sidebar' : 'Pin Sidebar'}</span>}
            </button>

            {isExpanded && (
              <div className="mt-2 flex items-center justify-between">
                <BuildVersion />
                <button
                  onClick={() => setIsPinned(false)}
                  className="p-1 text-text-muted hover:text-text-primary"
                  aria-label="Collapse sidebar"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
              </div>
            )}

            {!isExpanded && (
              <button
                onClick={() => setIsPinned(true)}
                className="w-full mt-1 flex justify-center p-2 text-text-muted hover:text-text-primary"
                aria-label="Expand sidebar"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </aside>

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
