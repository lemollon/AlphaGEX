'use client'

import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import CustomerShell from '@/components/customer/CustomerShell'
import type { LiveSummary } from '@/lib/live/types'
import TradeApprovalsClient from '../trades/TradeApprovalsClient'

/**
 * /account/approvals — the real mount point for TradeApprovalsClient (dashboard
 * audit "Account/Trade Approvals: dead code — fully built but never mounted").
 *
 * The queue itself (TradeApprovalsClient) already fetched its own data and
 * self-guarded on 401; this page only adds the app chrome and heading every
 * other /account/* destination has, and is the real customer-gated destination
 * the trade-approval email's approveUrl now points at (see
 * app/api/brokerage/trades/route.ts).
 */
export default function ApprovalsPageClient() {
  const { data: summary } = useSWR<LiveSummary>('/api/live/summary', fetcher)

  return (
    <CustomerShell membership={summary?.membership ?? null}>
      <div className="mx-auto max-w-3xl">
        <h1 className="text-2xl font-bold text-white">Trade Approvals</h1>
        <p className="mt-1 text-sm text-gray-400">
          Trades that need your review before they are placed with your broker.
        </p>
        <div className="mt-6">
          <TradeApprovalsClient />
        </div>
      </div>
    </CustomerShell>
  )
}
