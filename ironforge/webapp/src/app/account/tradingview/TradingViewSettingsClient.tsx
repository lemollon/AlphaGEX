'use client'

import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import CustomerShell from '@/components/customer/CustomerShell'
import TradingViewPerkCard from '@/components/customer/TradingViewPerkCard'
import type { LiveSummary } from '@/lib/live/types'

/**
 * /account/tradingview — settings home for the TradingView indicator perk.
 * Same shell/membership wiring as the other /account pages.
 */
export default function TradingViewSettingsClient() {
  const { data: summary } = useSWR<LiveSummary>('/api/live/summary', fetcher)
  return (
    <CustomerShell membership={summary?.membership ?? null} maxWidthClass="max-w-2xl">
      <h1 className="text-xl font-bold text-white">TradingView</h1>
      <p className="mt-1 text-sm text-gray-400">
        Your indicator access, tied to the TradingView username below.
      </p>
      <div className="mt-5">
        <TradingViewPerkCard />
      </div>
    </CustomerShell>
  )
}
