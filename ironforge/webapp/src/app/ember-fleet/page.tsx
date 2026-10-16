'use client'

import { useEffect, useState } from 'react'

/* ------------------------------------------------------------------ */
/*  Types — mirrors spreadworks/backend/ember/pnl.py's aggregate_pnl()  */
/* ------------------------------------------------------------------ */

interface StrategyPnl {
  source: string | null
  available: boolean
  total_pnl: number | null
  trade_count: number
  trades: { strategy?: string; date: string | null; pnl: number | null }[]
  caveat: string
  path?: string
}

interface AggregatePnl {
  total_realized_pnl: number
  strategies_with_data: string[]
  strategies_without_data: string[]
  by_strategy: Record<string, StrategyPnl>
  trade_series: { strategy: string; date: string; pnl: number }[]
}

const STRATEGY_LABELS: Record<string, string> = {
  call_diag: 'Call Diag',
  night_shift: 'Night Shift',
  divhike: 'Divhike',
  xsp_flow: 'XSP Flow',
  astra3_live: 'ASTRA-3 Live',
  tv_book: 'TV Book',
  spike: 'Spike',
}

function fmtUsd(value: number | null): string {
  if (value === null || value === undefined) return '—'
  const sign = value < 0 ? '-' : ''
  return `${sign}$${Math.abs(value).toFixed(2)}`
}

function pnlColor(value: number | null): string {
  if (value === null || value === undefined) return 'text-gray-400'
  return value >= 0 ? 'text-green-400' : 'text-red-400'
}

/* ------------------------------------------------------------------ */
/*  Page                                                                */
/* ------------------------------------------------------------------ */

export default function EmberFleetPage() {
  const [pnl, setPnl] = useState<AggregatePnl | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch('/api/ember-fleet/pnl', { cache: 'no-store' })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data: AggregatePnl = await res.json()
        if (!cancelled) setPnl(data)
      } catch (err: unknown) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  const strategyRows = pnl
    ? Object.entries(pnl.by_strategy).map(([name, data]) => ({ name, ...data }))
    : []

  // Most recent trades first; this is every known closed trade across the
  // strategies that actually carry per-trade dates (see pnl.py's module
  // docstring) — not a cumulative fleet-wide equity curve.
  const recentTrades = pnl ? [...pnl.trade_series].reverse().slice(0, 50) : []

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-start gap-4">
        <div>
          <svg width="40" height="40" viewBox="0 0 40 40" fill="none" className="shrink-0">
            <rect width="40" height="40" rx="8" fill="rgba(255,85,0,0.12)" />
            <path
              d="M20 6C20 6 14 12 14 19C14 22.3 15.5 24.8 18 26C17 24 17.5 22 19 21C19 23 20 25 20 25C20 25 21 23 21 21C22.5 22 23 24 22 26C24.5 24.8 26 22.3 26 19C26 12 20 6 20 6Z"
              fill="#FF5500"
            />
          </svg>
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            <span className="text-amber-400">EMBER</span>
            <span className="text-gray-400 font-normal text-lg ml-3">
              Robinhood Fleet — Realized P&amp;L
            </span>
          </h1>
          <p className="text-sm text-forge-muted mt-1">
            7-strategy fleet on account 570892331 (call_diag, night_shift, divhike,
            xsp_flow, astra3_live, tv_book, spike). Not the backtester at /ember —
            different product, same letter.
          </p>
        </div>
      </div>

      <div className="fire-divider" />

      {loading && (
        <div className="h-24 bg-forge-border/30 rounded-xl animate-pulse" />
      )}

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <span className="font-semibold">Failed to load P&amp;L: </span>{error}
        </div>
      )}

      {pnl && (
        <>
          {/* Total realized P&L */}
          <div className="rounded-xl border border-forge-border bg-forge-card/60 p-5">
            <p className="text-xs uppercase tracking-wide text-forge-muted font-semibold mb-1">
              Total Realized P&amp;L (fleet-wide)
            </p>
            <p className={`text-4xl font-bold ${pnlColor(pnl.total_realized_pnl)}`}>
              {fmtUsd(pnl.total_realized_pnl)}
            </p>
            <p className="text-xs text-forge-muted mt-2">
              Covers {pnl.strategies_with_data.length} of 7 strategies
              {pnl.strategies_without_data.length > 0 && (
                <> — no ledger yet for {pnl.strategies_without_data.map((s) => STRATEGY_LABELS[s] ?? s).join(', ')}</>
              )}
              .
            </p>
          </div>

          {/* By-strategy breakdown */}
          <div className="rounded-xl border border-forge-border bg-forge-card/60 p-5 overflow-x-auto">
            <h2 className="text-sm font-semibold text-gray-300 mb-3">By Strategy</h2>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-forge-muted text-xs uppercase tracking-wide border-b border-forge-border">
                  <th className="py-2 pr-4">Strategy</th>
                  <th className="py-2 pr-4 text-right">Realized P&amp;L</th>
                  <th className="py-2 pr-4 text-right">Trades</th>
                  <th className="py-2 pr-4">Source</th>
                  <th className="py-2">Caveat</th>
                </tr>
              </thead>
              <tbody>
                {strategyRows.map((row) => (
                  <tr key={row.name} className="border-b border-forge-border/50 align-top">
                    <td className="py-2 pr-4 font-medium text-gray-200">
                      {STRATEGY_LABELS[row.name] ?? row.name}
                    </td>
                    <td className={`py-2 pr-4 text-right font-mono ${pnlColor(row.total_pnl)}`}>
                      {fmtUsd(row.total_pnl)}
                    </td>
                    <td className="py-2 pr-4 text-right font-mono text-gray-300">
                      {row.trade_count}
                    </td>
                    <td className="py-2 pr-4 text-gray-400">{row.source ?? 'none'}</td>
                    <td className="py-2 text-xs text-forge-muted max-w-md">{row.caveat}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Recent closed trades across the strategies with real dates */}
          <div className="rounded-xl border border-forge-border bg-forge-card/60 p-5 overflow-x-auto">
            <h2 className="text-sm font-semibold text-gray-300 mb-1">Recent Closed Trades</h2>
            <p className="text-xs text-forge-muted mb-3">
              Only call_diag, night_shift, divhike, and astra3_live carry per-trade dates
              today — xsp_flow, tv_book, and spike are not in this list (see By Strategy
              above).
            </p>
            {recentTrades.length === 0 ? (
              <p className="text-sm text-forge-muted">No dated closed trades yet.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-forge-muted text-xs uppercase tracking-wide border-b border-forge-border">
                    <th className="py-2 pr-4">Date</th>
                    <th className="py-2 pr-4">Strategy</th>
                    <th className="py-2 text-right">P&amp;L</th>
                  </tr>
                </thead>
                <tbody>
                  {recentTrades.map((t, i) => (
                    <tr key={`${t.strategy}-${t.date}-${i}`} className="border-b border-forge-border/50">
                      <td className="py-2 pr-4 text-gray-300 font-mono">{t.date}</td>
                      <td className="py-2 pr-4 text-gray-300">{STRATEGY_LABELS[t.strategy] ?? t.strategy}</td>
                      <td className={`py-2 text-right font-mono ${pnlColor(t.pnl)}`}>{fmtUsd(t.pnl)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  )
}
