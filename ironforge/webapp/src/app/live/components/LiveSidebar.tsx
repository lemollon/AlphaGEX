'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { Wordmark } from '@/components/Brand'
import { MobileNavDrawer } from '@/components/customer/CustomerShell'

/**
 * Left rail for the customer Live page — keeps the original IronForge
 * palette (charcoal, white, Forge Orange active state). Only the Spark page
 * content shifts to electric blue; the rail never does.
 */

interface NavItem {
  label: string
  href: string | null
  icon: JSX.Element
  active?: boolean
  disabled?: boolean
}

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5 shrink-0">
      <path d={d} />
    </svg>
  )
}

const ICONS = {
  home: 'M3 10.5 12 3l9 7.5V21a1 1 0 0 1-1 1h-5v-7h-6v7H4a1 1 0 0 1-1-1z',
  live: 'M3 12h4l3-8 4 16 3-8h4',
  performance: 'M4 20V10m6 10V4m6 16v-7m-13 7h15',
  community: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M15 3.13a4 4 0 0 1 0 7.75M11 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  membership: 'M12 2l2.4 4.86 5.36.78-3.88 3.78.92 5.34L12 14.24l-4.8 2.52.92-5.34L4.24 7.64l5.36-.78z',
  history: 'M12 8v4l3 3m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm7.4-3a7.4 7.4 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7.5 7.5 0 0 0-2-1.2L14.5 3h-5l-.4 2.6a7.5 7.5 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7.5 7.5 0 0 0 2 1.2l.4 2.6h5l.4-2.6a7.5 7.5 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.07-.4.1-.8.1-1.2z',
  help: 'M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3m.08 4h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
  logout: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4m7 14 5-5-5-5m5 5H9',
}

export default function LiveSidebar({ membership }: { membership: { plan: string; badge: string } | null }) {
  const router = useRouter()
  const [menuOpen, setMenuOpen] = useState(false)

  async function handleLogout() {
    try {
      await fetch('/api/auth/customer-logout', { method: 'POST' })
    } finally {
      router.push('/login')
    }
  }

  const mainItems: NavItem[] = [
    { label: 'Home', href: '/home', icon: <Icon d={ICONS.home} /> },
    { label: 'Live', href: '/live', icon: <Icon d={ICONS.live} />, active: true },
    { label: 'Performance', href: '/spark', icon: <Icon d={ICONS.performance} /> },
    { label: 'Community', href: '/community', icon: <Icon d={ICONS.community} /> },
  ]
  const secondaryItems: NavItem[] = [
    { label: 'My Membership', href: '/pricing', icon: <Icon d={ICONS.membership} /> },
    { label: 'Trade History', href: '/account/trades', icon: <Icon d={ICONS.history} /> },
    { label: 'Settings', href: null, icon: <Icon d={ICONS.settings} />, disabled: true },
    { label: 'Help', href: '/contact', icon: <Icon d={ICONS.help} /> },
  ]

  const renderItem = (item: NavItem) => {
    const baseClass = 'flex items-center gap-3 px-4 py-2.5 text-sm transition-colors'
    if (item.disabled || !item.href) {
      return (
        <div key={item.label} className={`${baseClass} cursor-not-allowed text-gray-600`}>
          {item.icon}
          <span>{item.label}</span>
          <span className="ml-auto rounded-full border border-forge-border px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-gray-600">Soon</span>
        </div>
      )
    }
    if (item.active) {
      return (
        <Link key={item.label} href={item.href}
          className={`${baseClass} border-l-2 border-amber-500 bg-amber-500/10 font-medium text-amber-500`}>
          {item.icon}
          <span>{item.label}</span>
        </Link>
      )
    }
    return (
      <Link key={item.label} href={item.href}
        className={`${baseClass} border-l-2 border-transparent text-gray-400 hover:text-white`}>
        {item.icon}
        <span>{item.label}</span>
      </Link>
    )
  }

  return (
    <>
      {/* Mobile top bar */}
      <div className="flex items-center justify-between border-b border-forge-border bg-forge-bg px-4 py-3 lg:hidden">
        <Link href="/"><Wordmark markClass="h-6 w-auto" textClass="text-lg" /></Link>
        <button onClick={() => setMenuOpen(true)} className="p-1 text-gray-300 transition-colors hover:text-white" aria-label="Open menu">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
            strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6">
            <path d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
      </div>
      <MobileNavDrawer open={menuOpen} onClose={() => setMenuOpen(false)}
        membership={membership} planVariant="active" />

      {/* Desktop rail */}
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-60 flex-col border-r border-forge-border bg-forge-bg lg:flex">
        <div className="px-4 py-5">
          <Link href="/"><Wordmark /></Link>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto pb-4">
          {mainItems.map(renderItem)}
          <div className="mx-4 my-3 border-t border-forge-border" />
          {secondaryItems.map(renderItem)}
          <div className="mx-4 my-3 border-t border-forge-border" />
          <button onClick={handleLogout}
            className="flex w-full items-center gap-3 border-l-2 border-transparent px-4 py-2.5 text-sm text-gray-400 transition-colors hover:text-white">
            <Icon d={ICONS.logout} />
            <span>Log Out</span>
          </button>
        </nav>
        <div className="p-4">
          <div className="rounded-xl border border-amber-900/40 bg-forge-card p-4">
            <div className="font-display text-base text-amber-500">
              {membership?.plan ?? 'Forge Automate'}
            </div>
            <div className="mt-2 inline-block rounded-full border border-spark/30 bg-spark/15 px-2.5 py-0.5 text-xs text-spark">
              {membership?.badge ?? 'Early Access'}
            </div>
          </div>
        </div>
      </aside>
    </>
  )
}
