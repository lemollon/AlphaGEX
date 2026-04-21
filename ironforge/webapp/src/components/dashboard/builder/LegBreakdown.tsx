'use client'

/**
 * LegBreakdown — ported from spreadworks/frontend/src/components/LegBreakdown.jsx.
 * Collapsible per-leg table showing Strike / Type / Mid / IV / Delta / Theta.
 * Long legs are tinted green; short legs red.
 *
 * Data: legs[] from /api/{bot}/builder/snapshot.
 */
import { useState } from 'react'

export interface BuilderLeg {
  role: 'long_put' | 'short_put' | 'short_call' | 'long_call'
  strike: number
  type: 'P' | 'C'
  occ_symbol: string
  bid: number | null
  ask: number | null
  mid: number | null
  last: number | null
  delta: number | null
  gamma: number | null
  theta: number | null
  vega: number | null
  mid_iv: number | null
}

interface LegBreakdownProps {
  legs: BuilderLeg[] | null | undefined
  expiration?: string | null
  /** When false (closed position), the legs carry no live Tradier data —
   * bid/ask/mid/last/greeks will be null. We show an "at entry" hint in
   * the header so the operator knows not to expect fresh quotes. */
  isOpen?: boolean
}

function fmtMoney(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return `$${v.toFixed(2)}`
}
function fmtPct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return `${(v * 100).toFixed(1)}%`
}
function fmtGreek(v: number | null | undefined, digits = 3): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return v.toFixed(digits)
}

function roleLabel(role: BuilderLeg['role']): string {
  switch (role) {
    case 'long_put': return 'Long Put'
    case 'short_put': return 'Short Put'
    case 'short_call': return 'Short Call'
    case 'long_call': return 'Long Call'
  }
}

function isLong(role: BuilderLeg['role']): boolean {
  return role === 'long_put' || role === 'long_call'
}

export default function LegBreakdown({ legs, expiration, isOpen = true }: LegBreakdownProps) {
  const [openSection, setOpenSection] = useState(true)

  if (!legs || legs.length === 0) return null

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 overflow-hidden">
      <button
        onClick={() => setOpenSection(!openSection)}
        className="w-full text-left px-4 py-2 text-[11px] font-semibold uppercase tracking-wider text-forge-muted hover:text-gray-200 flex items-center justify-between border-b border-forge-border/50"
      >
        <span>
          <span className="mr-2">{openSection ? '▾' : '▸'}</span>
          Legs ({legs.length})
          {expiration ? <span className="ml-2 text-gray-500 normal-case font-normal">exp {expiration}</span> : null}
          {!isOpen ? <span className="ml-2 text-amber-400/80 normal-case font-normal">(position closed — quotes/greeks not live)</span> : null}
        </span>
      </button>
      {openSection && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-forge-muted border-b border-forge-border/40">
                <th className="text-left py-2 px-3 font-normal">Leg</th>
                <th className="text-right py-2 px-3 font-normal">Strike</th>
                <th className="text-right py-2 px-3 font-normal">Bid</th>
                <th className="text-right py-2 px-3 font-normal">Ask</th>
                <th className="text-right py-2 px-3 font-normal">Mid</th>
                <th className="text-right py-2 px-3 font-normal">IV</th>
                <th className="text-right py-2 px-3 font-normal">Δ</th>
                <th className="text-right py-2 px-3 font-normal">Θ</th>
                <th className="text-right py-2 px-3 font-normal">ν</th>
              </tr>
            </thead>
            <tbody>
              {legs.map((l) => {
                const long = isLong(l.role)
                const rowTint = long ? 'bg-emerald-500/[0.04]' : 'bg-red-500/[0.04]'
                const labelClass = long ? 'text-emerald-400' : 'text-red-400'
                return (
                  <tr key={l.occ_symbol} className={`${rowTint} border-b border-forge-border/20`}>
                    <td className={`py-2 px-3 font-semibold ${labelClass}`}>{roleLabel(l.role)}</td>
                    <td className="py-2 px-3 text-right font-mono text-gray-200">${l.strike.toFixed(0)}</td>
                    <td className="py-2 px-3 text-right font-mono text-gray-300">{fmtMoney(l.bid)}</td>
                    <td className="py-2 px-3 text-right font-mono text-gray-300">{fmtMoney(l.ask)}</td>
                    <td className="py-2 px-3 text-right font-mono text-gray-200">{fmtMoney(l.mid)}</td>
                    <td className="py-2 px-3 text-right font-mono text-gray-300">{fmtPct(l.mid_iv)}</td>
                    <td className="py-2 px-3 text-right font-mono text-gray-300">{fmtGreek(l.delta)}</td>
                    <td className="py-2 px-3 text-right font-mono text-gray-300">{fmtGreek(l.theta)}</td>
                    <td className="py-2 px-3 text-right font-mono text-gray-300">{fmtGreek(l.vega)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
