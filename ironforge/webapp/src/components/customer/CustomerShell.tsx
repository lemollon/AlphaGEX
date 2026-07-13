'use client'

import Link from 'next/link'
import { useIsOperator } from '@/lib/useIsOperator'
import { usePathname, useRouter } from 'next/navigation'
import { useState } from 'react'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'

/**
 * Shared chrome for the customer Home + Community pages (per the approved
 * dashboard design): full-width top nav (logo, section links, bell, avatar)
 * plus a left rail (plan card, main nav, account nav). Below lg the rail is
 * replaced by a hamburger-triggered slide-out drawer (MobileNavDrawer, also
 * used by the /live page's mobile bar). The /live page keeps its own desktop
 * shell — do not couple the two.
 */

interface CustomerMe {
  ok: boolean
  customer?: { email?: string }
}

const NAV_MAIN = [
  { label: 'Home', href: '/home', icon: 'M3 10.5 12 3l9 7.5V21a1 1 0 0 1-1 1h-5v-7h-6v7H4a1 1 0 0 1-1-1z' },
  { label: 'Live', href: '/live', icon: 'M3 12h4l3-8 4 16 3-8h4' },
  { label: 'Performance', href: '/spark', icon: 'M4 20V10m6 10V4m6 16v-7m-13 7h15' },
  { label: 'Community', href: '/community', icon: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M15 3.13a4 4 0 0 1 0 7.75M11 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0' },
]

const NAV_SECONDARY = [
  { label: 'Manage Membership', href: '/pricing', icon: 'M12 2l2.4 4.86 5.36.78-3.88 3.78.92 5.34L12 14.24l-4.8 2.52.92-5.34L4.24 7.64l5.36-.78z' },
  { label: 'Brokerage Settings', href: '/onboarding/brokerage', icon: 'M3 21h18M3 10h18M5 6l7-3 7 3M5 10v11m4.5-11v11m5-11v11M19 10v11' },
  { label: 'Trade History', href: '/account/trades', icon: 'M12 8v4l3 3m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0' },
  { label: 'Pause Trading', href: '/live', icon: 'M10 15V9m4 6V9m7 3a9 9 0 1 1-18 0 9 9 0 0 1 18 0' },
]

function Icon({ d, className = 'h-5 w-5 shrink-0' }: { d: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d={d} />
    </svg>
  )
}

function LogoLockup() {
  return (
    <Link href="/home" className="flex items-center gap-2.5">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/forge-logo-mark.png" alt="IronForge" className="h-8 w-8 rounded-lg" />
      <span className="text-lg font-bold tracking-tight">
        <span className="text-white">IRON</span>
        <span className="text-amber-500">FORGE</span>
      </span>
    </Link>
  )
}

export interface PlanCardData {
  plan: string
  badge: string
  trial?: { label: string; day: number; total_days: number; ends_label: string } | null
}

function PlanCard({ membership, variant }: { membership: PlanCardData | null; variant: 'trial' | 'active' }) {
  const plan = membership?.plan ?? 'Forge Automate'
  const trial = membership?.trial ?? null
  const pct = trial ? Math.min(100, Math.max(0, Math.round((trial.day / trial.total_days) * 100))) : 0
  return (
    <div className="rounded-xl border border-amber-900/40 bg-forge-card p-3.5">
      <div className="flex items-start gap-2.5">
        <Icon className="mt-0.5 h-5 w-5 shrink-0 text-amber-500"
          d="M12 2l8 3v6c0 5.25-3.4 9.74-8 11-4.6-1.26-8-5.75-8-11V5z" />
        <div>
          <div className="font-display text-base leading-tight text-amber-500">{plan}</div>
          {variant === 'trial' && trial ? (
            <div className="text-xs text-gray-500">{trial.label}</div>
          ) : (
            <div className="flex items-center gap-1 text-xs text-emerald-500">
              <Icon className="h-3.5 w-3.5" d="M20 6 9 17l-5-5" />
              Active
            </div>
          )}
        </div>
      </div>
      {variant === 'trial' && trial && (
        <div className="mt-3">
          <div className="text-xs text-gray-200">Trial Day {trial.day} of {trial.total_days}</div>
          <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-forge-border">
            <div className="h-full rounded-full bg-amber-500" style={{ width: `${pct}%` }} />
          </div>
          <div className="mt-1.5 text-[11px] text-gray-500">{trial.ends_label}</div>
        </div>
      )}
    </div>
  )
}

/** Main + secondary nav items + logout, shared by the desktop rail and the mobile drawer. */
function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname()
  const router = useRouter()
  const isOperator = useIsOperator()

  async function handleLogout() {
    try {
      await fetch('/api/auth/customer-logout', { method: 'POST' })
    } finally {
      router.push('/login')
    }
  }

  const renderItem = (item: { label: string; href: string; icon: string }) => {
    const active = pathname === item.href
    return (
      <Link key={item.label} href={item.href} onClick={onNavigate}
        className={`flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
          active
            ? 'border-l-2 border-amber-500 bg-amber-500/10 font-medium text-amber-500'
            : 'border-l-2 border-transparent text-gray-400 hover:text-white'
        }`}>
        <Icon d={item.icon} />
        <span>{item.label}</span>
      </Link>
    )
  }

  return (
    <>
      {isOperator ? (
        <Link
          href="/spark"
          onClick={onNavigate}
          className="flex items-center gap-3 border-l-2 border-transparent px-4 py-2.5 text-sm font-semibold text-amber-500 transition-colors hover:text-amber-400"
        >
          <Icon d="M13 2 4 14h6l-1 8 9-12h-6l1-8z" />
          <span>Ops</span>
        </Link>
      ) : null}
      {NAV_MAIN.map(renderItem)}
      <div className="mx-4 my-3 border-t border-forge-border" />
      {NAV_SECONDARY.map(renderItem)}
      <div className="mx-4 my-3 border-t border-forge-border" />
      <button onClick={handleLogout}
        className="flex w-full items-center gap-3 border-l-2 border-transparent px-4 py-2.5 text-sm text-gray-400 transition-colors hover:text-white">
        <Icon d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4m7 14 5-5-5-5m5 5H9" />
        <span>Log Out</span>
      </button>
    </>
  )
}

/** Slide-out mobile navigation. Also used by the /live page's mobile top bar. */
export function MobileNavDrawer({
  open,
  onClose,
  membership,
  planVariant = 'trial',
}: {
  open: boolean
  onClose: () => void
  membership: PlanCardData | null
  planVariant?: 'trial' | 'active'
}) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} aria-hidden />
      <div className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col overflow-y-auto border-r border-forge-border bg-forge-bg">
        <div className="flex items-center justify-between px-4 py-4">
          <LogoLockup />
          <button onClick={onClose} className="p-1 text-gray-400 transition-colors hover:text-white" aria-label="Close menu">
            <Icon className="h-5 w-5" d="M18 6 6 18M6 6l12 12" />
          </button>
        </div>
        <div className="px-4 pb-4">
          <PlanCard membership={membership} variant={planVariant} />
        </div>
        <nav className="flex-1 space-y-0.5 pb-6">
          <NavItems onNavigate={onClose} />
        </nav>
      </div>
    </div>
  )
}

function TopNav({ onMenuClick }: { onMenuClick: () => void }) {
  const pathname = usePathname()
  const { data } = useSWR<CustomerMe>('/api/auth/customer-me', fetcher, { shouldRetryOnError: false })
  const email = data?.customer?.email ?? null
  const name = email ? email.split('@')[0] : 'Trader'
  const initials = name.slice(0, 2).toUpperCase()

  return (
    <header className="fixed inset-x-0 top-0 z-30 border-b border-forge-border bg-forge-bg">
      <div className="flex h-14 items-center gap-4 px-4 md:gap-8">
        <button onClick={onMenuClick}
          className="-ml-1 p-1 text-gray-300 transition-colors hover:text-white lg:hidden"
          aria-label="Open menu">
          <Icon className="h-6 w-6" d="M4 6h16M4 12h16M4 18h16" />
        </button>
        <LogoLockup />
        <nav className="hidden h-full items-center gap-6 md:flex">
          {NAV_MAIN.map((item) => {
            const active = pathname === item.href
            return (
              <Link key={item.href} href={item.href}
                className={`relative flex h-full items-center px-1 text-sm transition-colors ${
                  active ? 'font-medium text-white' : 'text-gray-400 hover:text-white'
                }`}>
                {item.label}
                {active && <span className="absolute inset-x-0 bottom-0 h-0.5 rounded-full bg-amber-500" />}
              </Link>
            )
          })}
        </nav>
        <div className="ml-auto flex items-center gap-4">
          <div className="relative">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
              strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5 text-gray-400">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
            <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-amber-500" />
          </div>
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-amber-500/20 text-xs font-semibold text-amber-500">
              {initials}
            </div>
            <span className="hidden text-sm capitalize text-gray-300 sm:block">{name}</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 text-gray-500">
              <path d="m6 9 6 6 6-6" />
            </svg>
          </div>
        </div>
      </div>
    </header>
  )
}

function Sidebar({ membership, planVariant }: { membership: PlanCardData | null; planVariant: 'trial' | 'active' }) {
  return (
    <aside className="fixed bottom-0 left-0 top-14 z-20 hidden w-60 flex-col border-r border-forge-border bg-forge-bg lg:flex">
      <div className="p-4">
        <PlanCard membership={membership} variant={planVariant} />
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto pb-4">
        <NavItems />
      </nav>
    </aside>
  )
}

export default function CustomerShell({
  membership,
  planVariant = 'trial',
  maxWidthClass = 'max-w-[1200px]',
  children,
}: {
  membership: PlanCardData | null
  planVariant?: 'trial' | 'active'
  maxWidthClass?: string
  children: React.ReactNode
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  return (
    <div className="min-h-screen bg-forge-bg">
      <TopNav onMenuClick={() => setMenuOpen(true)} />
      <Sidebar membership={membership} planVariant={planVariant} />
      <MobileNavDrawer open={menuOpen} onClose={() => setMenuOpen(false)}
        membership={membership} planVariant={planVariant} />
      <div className="pt-14 lg:pl-60">
        <div className={`mx-auto ${maxWidthClass} px-4 py-5`}>{children}</div>
      </div>
    </div>
  )
}
