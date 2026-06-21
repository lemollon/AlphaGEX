'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'

interface HedgePlanResp {
  ok?: boolean
  flagged?: boolean
  summary?: string
  plan?: {
    hedge: boolean
    reason: string
    long_strike: number
    short_strike: number
    dte: number
    contracts: number
    est_debit: number
    est_max_payoff: number
    coverage_pct: number
    est_sameday_offset: number
  }
  inputs?: { tail?: number; tail_source?: string; regime?: string | null }
  arm?: { armed?: boolean }
  execution?: {
    status?: string
    tradier_order_id?: string | null
    preview_cost?: number | null
    error?: string | null
    expensive?: boolean | null
    est_total_debit?: number | null
    soft_cap?: number | null
  } | null
}

function ArmBadge({ armed }: { armed?: boolean }) {
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${armed ? 'border-emerald-600/50 text-emerald-300' : 'border-gray-600/50 text-gray-400'}`}>
      {armed ? 'HEDGING ON' : 'HEDGING OFF'}
    </span>
  )
}

function Stat({ label, v }: { label: string; v: string }) {
  return (
    <div className="rounded bg-black/30 p-2">
      <div className="text-white">{v}</div>
      <div className="text-forge-muted">{label}</div>
    </div>
  )
}

export default function HedgeCard() {
  const { data, mutate } = useSWR<HedgePlanResp>('/api/hedge/plan', fetcher, { refreshInterval: 60_000 })
  const [busy, setBusy] = useState<string | null>(null)

  const p = data?.plan
  if (!data?.ok || !p) return null
  const exec = data.execution
  const status = exec?.status

  async function act(action: 'confirm' | 'decline') {
    if (busy) return
    if (action === 'confirm' && !window.confirm('Place a REAL-MONEY hedge on the SPARK (Iron Viper) account now?')) return
    setBusy(action)
    try {
      await fetch(`/api/hedge/place?action=${action}`, { method: 'POST' })
      await mutate()
    } finally {
      setBusy(null)
    }
  }

  if (!p.hedge) {
    return (
      <div className="rounded-lg border border-emerald-700/40 bg-emerald-950/20 p-4">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-emerald-300">No hedge today</p>
          <ArmBadge armed={data.arm?.armed} />
        </div>
        <p className="mt-1 text-xs text-forge-muted">{p.reason}</p>
      </div>
    )
  }

  const placed = status === 'placed'
  const declined = status === 'declined'
  const pending = status === 'pending'

  return (
    <div className={`rounded-lg border p-4 ${placed ? 'border-green-600/50 bg-green-950/20' : 'border-amber-600/50 bg-amber-950/20'}`}>
      <div className="flex items-center justify-between">
        <p className={`text-sm font-semibold ${placed ? 'text-green-300' : 'text-amber-300'}`}>
          {placed ? 'Hedge placed' : declined ? 'Hedge dismissed' : 'Hedge recommended — confirm to place'}
        </p>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-forge-muted">{data.inputs?.regime ?? ''}</span>
          <ArmBadge armed={data.arm?.armed} />
        </div>
      </div>

      <p className="mt-1 text-sm text-white">{data.summary}</p>
      <p className="mt-2 text-xs text-forge-muted">{p.reason}</p>

      {exec?.expensive ? (
        <p className="mt-2 rounded border border-amber-500/50 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-300">
          ⚠ Expensive hedge — ${Number(exec.est_total_debit ?? 0).toFixed(0)} is{' '}
          {data.inputs?.tail ? Math.round((Number(exec.est_total_debit ?? 0) / data.inputs.tail) * 100) : '?'}% of the tail
          {exec.soft_cap != null ? ` (above the $${Number(exec.soft_cap).toFixed(0)} soft cap)` : ''}. Review before placing.
        </p>
      ) : null}

      <div className="mt-3 grid grid-cols-3 gap-2 text-center font-mono text-[11px]">
        <Stat label="Est. debit" v={`$${p.est_debit.toFixed(0)}`} />
        <Stat label="Max payoff" v={`$${p.est_max_payoff.toFixed(0)}`} />
        <Stat label="~Same-day" v={`$${p.est_sameday_offset.toFixed(0)}`} />
      </div>

      {placed ? (
        <p className="mt-3 text-[11px] text-green-400">Placed on SPARK{exec?.tradier_order_id ? ` · order ${exec.tradier_order_id}` : ''}.</p>
      ) : declined ? (
        <p className="mt-3 text-[11px] text-forge-muted">Dismissed for today.</p>
      ) : (
        // pending (or freshly recommended): ask the operator to confirm the real-money order.
        <div className="mt-3 flex gap-2">
          <button
            onClick={() => act('confirm')}
            disabled={busy != null || !data.arm?.armed}
            title={!data.arm?.armed ? 'Hedging is OFF (set HEDGE_AUTO_PLACE=true to enable)' : ''}
            className="flex-1 rounded-md bg-amber-600 px-3 py-2 text-xs font-semibold text-white hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy === 'confirm' ? 'Placing…' : 'Place hedge on SPARK (live)'}
          </button>
          <button
            onClick={() => act('decline')}
            disabled={busy != null}
            className="rounded-md border border-white/15 px-3 py-2 text-xs text-gray-300 hover:bg-white/5 disabled:opacity-50"
          >
            Dismiss
          </button>
        </div>
      )}

      <p className="mt-2 text-[10px] text-forge-muted">
        Real-money SPARK hedge requires your confirmation. Covers {Math.round((p.coverage_pct ?? 0) * 100)}% of the
        ${data.inputs?.tail} tail{data.inputs?.tail_source ? ` (${data.inputs.tail_source})` : ''}.
        {pending && exec?.preview_cost != null ? ` Preview cost $${Number(exec.preview_cost).toFixed(0)}.` : ''}
        {status === 'failed' && exec?.error ? ` Last error: ${exec.error.slice(0, 80)}` : ''}
      </p>
    </div>
  )
}
