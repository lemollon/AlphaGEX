'use client'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import type { GexAnalysisData } from '@/lib/gex/types'

function fmt(n: number): string {
  const a = Math.abs(n)
  if (a >= 1e9) return `${(n / 1e9).toFixed(1)}B`
  if (a >= 1e6) return `${(n / 1e6).toFixed(1)}M`
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}K`
  return n.toFixed(0)
}
const ratingColor = (r: string) =>
  r === 'BULLISH' ? 'text-green-400' : r === 'BEARISH' ? 'text-red-400' : 'text-gray-300'
const gammaColor = (g: string) =>
  g === 'POSITIVE' ? 'text-green-400' : g === 'NEGATIVE' ? 'text-red-400' : 'text-gray-300'

/**
 * Compact SPY GEX context strip shown at the top of every bot dashboard.
 * Reads the same /api/gex/analysis proxy the GEX Profile page uses.
 */
export default function GexSummaryBanner({ symbol = 'SPY' }: { symbol?: string }) {
  const [data, setData] = useState<GexAnalysisData | null>(null)

  useEffect(() => {
    let alive = true
    fetch(`/api/gex/analysis?symbol=${symbol}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((j) => { if (alive && j?.success) setData(j.data) })
      .catch(() => {})
    return () => { alive = false }
  }, [symbol])

  if (!data) return null
  const h = data.header
  const cell = (label: string, value: string, cls = 'text-white') => (
    <div className="flex items-baseline gap-1.5">
      <span className="text-[10px] uppercase tracking-wide text-gray-500">{label}</span>
      <span className={`text-sm font-semibold ${cls}`}>{value}</span>
    </div>
  )

  return (
    <Link
      href="/gex"
      className="flex flex-wrap items-center gap-x-5 gap-y-1 rounded-xl border border-forge-border bg-forge-card/70 px-4 py-2 hover:border-cyan-500/40 transition-colors"
      title="Open GEX Profile"
    >
      <span className="text-[11px] font-semibold text-cyan-300">{symbol} GEX</span>
      {cell('Rating', h.rating, ratingColor(h.rating))}
      {cell('Gamma', h.gamma_form, gammaColor(h.gamma_form))}
      {cell('Price', h.price.toFixed(2))}
      {cell('Flip', h.gex_flip != null ? h.gex_flip.toFixed(2) : 'N/A', 'text-amber-300')}
      {cell('Net GEX', fmt((h.net_gex || 0) * 1e6))}
      <span className="ml-auto text-[10px] text-gray-500">GEX Profile →</span>
    </Link>
  )
}
