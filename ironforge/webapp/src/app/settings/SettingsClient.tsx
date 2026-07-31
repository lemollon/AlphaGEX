'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import CustomerShell from '@/components/customer/CustomerShell'
import type { LiveSummary } from '@/lib/live/types'

/**
 * Settings hub (UAT-013): ONE rail entry replaces the three account-management links
 * (Manage Membership / Brokerage Settings / Change Password) that cluttered primary
 * navigation. Each destination keeps its own page, permissions, and deep-linkable URL
 * — this page is the clearly-labeled directory the doc asks for. No agent controls
 * and no TradingView section (removed under UAT-016) live here by design.
 */
const SECTIONS = [
  {
    href: '/account/billing',
    title: 'Membership & Billing',
    blurb: 'Your plan, payment method, invoices, and strategy upgrades.',
    icon: 'M4 7h16v10H4zM4 10h16',
  },
  {
    href: '/account/brokerage',
    title: 'Brokerage Connections',
    blurb: 'Connected brokers, account eligibility, and reconnect actions.',
    icon: 'M4 20h16M6 20V9m4 11V9m4 11V9m4 11V9M3 9l9-5 9 5',
  },
  {
    href: '/change-password',
    title: 'Security',
    blurb: 'Change your password.',
    icon: 'M8 11V7a4 4 0 1 1 8 0v4M5 11h14v9H5z',
  },
] as const

export default function SettingsClient() {
  const { data: summary } = useSWR<LiveSummary>('/api/live/summary', fetcher)

  return (
    <CustomerShell membership={summary?.membership ?? null} maxWidthClass="max-w-[860px]">
      <h1 className="text-2xl font-bold text-white">Settings</h1>
      <p className="mt-1 text-sm text-gray-400">Account management — membership, brokerages, and security.</p>

      <div className="mt-5 space-y-3">
        {SECTIONS.map((s) => (
          <Link key={s.href} href={s.href}
            className="flex items-center gap-4 rounded-xl border border-forge-border bg-forge-card/80 p-5 transition hover:border-white/25">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
              className="h-6 w-6 shrink-0 text-amber-500" aria-hidden="true">
              <path d={s.icon} strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-white">{s.title}</span>
              <span className="mt-0.5 block text-xs text-gray-400">{s.blurb}</span>
            </span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
              className="ml-auto h-4 w-4 shrink-0 text-gray-600" aria-hidden="true">
              <path d="M9 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Link>
        ))}
      </div>
    </CustomerShell>
  )
}
