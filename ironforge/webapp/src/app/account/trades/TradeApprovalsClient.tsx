'use client'

import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'

interface Approval {
  id: string
  bot: string | null
  symbol: string
  action: string
  units: string | null
  order_type: string
  status: string
  expires_at: string
  created_at: string
}

const STATUS_STYLES: Record<string, string> = {
  pending: 'text-amber-300',
  placed: 'text-green-400',
  failed: 'text-red-400',
  expired: 'text-gray-500',
  declined: 'text-gray-500',
}

export default function TradeApprovalsClient() {
  const [approvals, setApprovals] = useState<Approval[] | null>(null)
  const [unauthed, setUnauthed] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/brokerage/trades', { cache: 'no-store' })
      if (res.status === 401) { setUnauthed(true); return }
      const data = await res.json().catch(() => ({}))
      setApprovals(Array.isArray(data.approvals) ? data.approvals : [])
    } catch {
      setApprovals([])
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function act(id: string, verb: 'approve' | 'decline') {
    if (busyId) return
    setBusyId(id)
    try {
      await fetch(`/api/brokerage/trades/${id}/${verb}`, { method: 'POST' })
      await load()
    } finally {
      setBusyId(null)
    }
  }

  if (unauthed) {
    return (
      <div className="rounded-2xl border border-white/10 bg-forge-card/90 p-8 text-center">
        <p className="text-sm text-gray-400">Please sign in to view your trades.</p>
        <Link href="/login?next=/account/trades" className="mt-3 inline-block text-sm font-semibold text-amber-500 hover:text-amber-400">
          Sign in
        </Link>
      </div>
    )
  }

  if (approvals === null) {
    return <div className="rounded-2xl border border-white/10 bg-forge-card/90 p-8 text-center text-sm text-gray-500">Loading…</div>
  }

  if (approvals.length === 0) {
    return <div className="rounded-2xl border border-white/10 bg-forge-card/90 p-8 text-center text-sm text-gray-400">No trades to review right now.</div>
  }

  return (
    <ul className="space-y-3">
      {approvals.map((a) => {
        const pending = a.status === 'pending'
        return (
          <li key={a.id} className="rounded-xl border border-white/10 bg-forge-card/90 p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-white">
                  {a.action} {a.units} {a.symbol}
                </p>
                <p className="text-xs text-gray-500">
                  {a.order_type}{a.bot ? ` · ${a.bot}` : ''} ·{' '}
                  <span className={STATUS_STYLES[a.status] ?? 'text-gray-400'}>{a.status}</span>
                </p>
              </div>
              {pending && (
                <div className="flex gap-2">
                  <button
                    onClick={() => act(a.id, 'approve')}
                    disabled={busyId === a.id}
                    className="rounded-md bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-500 disabled:opacity-50"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => act(a.id, 'decline')}
                    disabled={busyId === a.id}
                    className="rounded-md border border-white/15 px-3 py-1.5 text-xs text-gray-300 hover:bg-white/5 disabled:opacity-50"
                  >
                    Decline
                  </button>
                </div>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}
