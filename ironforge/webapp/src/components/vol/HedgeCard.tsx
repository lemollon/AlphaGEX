'use client'

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
}

function Stat({ label, v }: { label: string; v: string }) {
  return (
    <div className="rounded bg-black/30 p-2">
      <div className="text-white">{v}</div>
      <div className="text-forge-muted">{label}</div>
    </div>
  )
}

/** Today's regime hedge recommendation (Phase 2, advisory). */
export default function HedgeCard() {
  const { data } = useSWR<HedgePlanResp>('/api/hedge/plan', fetcher, { refreshInterval: 60_000 })
  const p = data?.plan
  if (!data?.ok || !p) return null

  if (!p.hedge) {
    return (
      <div className="rounded-lg border border-emerald-700/40 bg-emerald-950/20 p-4">
        <p className="text-sm font-semibold text-emerald-300">No hedge today</p>
        <p className="mt-1 text-xs text-forge-muted">{p.reason}</p>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-amber-600/50 bg-amber-950/20 p-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-amber-300">Hedge today</p>
        <span className="font-mono text-[11px] text-forge-muted">{data.inputs?.regime ?? ''}</span>
      </div>
      <p className="mt-1 text-sm text-white">{data.summary}</p>
      <p className="mt-2 text-xs text-forge-muted">{p.reason}</p>
      <div className="mt-3 grid grid-cols-3 gap-2 text-center font-mono text-[11px]">
        <Stat label="Est. debit" v={`$${p.est_debit.toFixed(0)}`} />
        <Stat label="Max payoff" v={`$${p.est_max_payoff.toFixed(0)}`} />
        <Stat label="~Same-day" v={`$${p.est_sameday_offset.toFixed(0)}`} />
      </div>
      <p className="mt-2 text-[10px] text-forge-muted">
        Advisory only — covers {Math.round((p.coverage_pct ?? 0) * 100)}% of the ${data.inputs?.tail} tail
        {data.inputs?.tail_source ? ` (${data.inputs.tail_source})` : ''}.
      </p>
    </div>
  )
}
