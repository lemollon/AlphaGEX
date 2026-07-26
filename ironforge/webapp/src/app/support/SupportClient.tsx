'use client'

import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import CustomerShell, { type PlanCardData } from '@/components/customer/CustomerShell'
import SparkyChat from '@/components/support/SparkyChat'

interface SummaryResp { membership?: PlanCardData | null }

/**
 * The dedicated Sparky page — the full-page half of the support experience. Same chat brain
 * as the widget (and the same on-device conversation), just roomier. Lives inside the shared
 * customer shell so the nav is consistent.
 */
export default function SupportClient() {
  const { data: summary } = useSWR<SummaryResp>('/api/live/summary', fetcher, { refreshInterval: 120_000 })
  const membership = summary?.membership ?? null

  return (
    <CustomerShell membership={membership} planVariant="active" maxWidthClass="max-w-[760px]">
      <div className="mb-4 flex items-center gap-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/support/sparky-anim.webp" alt="Sparky" width={56} height={56}
          className="h-14 w-14 rounded-full ring-1 ring-spark/40" />
        <div>
          <h1 className="text-xl font-bold text-white">Ask Sparky</h1>
          <p className="text-sm text-gray-400">Your IronForge support assistant — plans, billing, brokers, and how things work.</p>
        </div>
      </div>

      <div className="h-[calc(100dvh-190px)] min-h-[440px] overflow-hidden rounded-2xl border border-forge-border bg-forge-bg/60">
        <SparkyChat variant="page" />
      </div>
    </CustomerShell>
  )
}
