'use client'

import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import type { LiveViewerInfo } from '@/lib/live/types'

interface CustomerMe {
  ok: boolean
  customer?: { email?: string }
}

interface LiveHeaderProps {
  viewer?: LiveViewerInfo | null
  onSwitch?: (bot: 'spark' | 'spark2') => void
}

const ACCOUNT_LABELS: Record<string, string> = { spark: 'SPARK', spark2: 'SPARK2' }

export default function LiveHeader({ viewer, onSwitch }: LiveHeaderProps = {}) {
  // Public route: 401s cleanly when signed out — chip just falls back.
  const { data } = useSWR<CustomerMe>('/api/auth/customer-me', fetcher, {
    shouldRetryOnError: false,
  })
  const email = data?.customer?.email ?? null
  const name = email ? email.split('@')[0] : 'Trader'
  const initials = name.slice(0, 2).toUpperCase()

  return (
    <div className="flex items-center justify-between">
      <h1 className="font-display text-2xl tracking-wide text-white">Live</h1>
      <div className="flex items-center gap-4">
        {viewer && viewer.allowedBots.length > 1 && onSwitch ? (
          <div className="flex items-center overflow-hidden rounded-lg border border-forge-border text-xs font-semibold">
            {viewer.allowedBots.map((b) => (
              <button
                key={b}
                type="button"
                onClick={() => onSwitch(b as 'spark' | 'spark2')}
                className={
                  b === viewer.bot
                    ? 'bg-spark/20 px-3 py-1.5 text-spark'
                    : 'px-3 py-1.5 text-gray-400 transition-colors hover:text-white'
                }
              >
                {ACCOUNT_LABELS[b] ?? b.toUpperCase()}
              </button>
            ))}
          </div>
        ) : null}
        <div className="relative">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
            strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5 text-gray-400">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0" />
          </svg>
          <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-spark" />
        </div>
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-spark/20 text-xs font-semibold text-spark">
            {initials}
          </div>
          <span className="hidden text-sm text-gray-300 sm:block">{name}</span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 text-gray-500">
            <path d="m6 9 6 6 6-6" />
          </svg>
        </div>
      </div>
    </div>
  )
}
