'use client'

/**
 * Market Pulse tab — 4-card grid of beginner-friendly risk signals for
 * SPARK 1DTE IC sellers (Commit S1). Fetches /api/spark/risk-signals
 * every 30 seconds; each card shows:
 *
 *   1. A colored border/dot indicating safety tier
 *   2. Plain-English headline
 *   3. Compact numeric context
 *   4. A short beginner paragraph explaining the profitability impact
 *
 * Does NOT make trading decisions — it's purely a heads-up display so
 * the operator knows whether today is juicy-premium territory or the
 * open IC is in a tight spot.
 */
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'

type SignalColor = 'green' | 'amber' | 'red' | 'grey'

interface Tile {
  key: string
  title: string
  color: SignalColor
  headline: string
  numbers: string
  beginner: string
  values: Record<string, unknown>
}

interface RiskSignalsResponse {
  generated_at: string
  spy_price: number | null
  vix: number | null
  has_open_position: boolean
  tiles: Tile[]
  note?: string
}

const REFRESH_MS = 30_000

const COLOR_CLASSES: Record<SignalColor, {
  border: string
  dot: string
  headline: string
  tileBg: string
}> = {
  green: {
    border: 'border-emerald-500/40',
    dot: 'bg-emerald-400',
    headline: 'text-emerald-300',
    tileBg: 'bg-emerald-500/5',
  },
  amber: {
    border: 'border-amber-500/40',
    dot: 'bg-amber-400',
    headline: 'text-amber-300',
    tileBg: 'bg-amber-500/5',
  },
  red: {
    border: 'border-red-500/40',
    dot: 'bg-red-400',
    headline: 'text-red-300',
    tileBg: 'bg-red-500/10',
  },
  grey: {
    border: 'border-forge-border',
    dot: 'bg-forge-muted',
    headline: 'text-gray-300',
    tileBg: 'bg-forge-card/40',
  },
}

function formatCT(ts: string | null | undefined): string {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleString('en-US', {
      timeZone: 'America/Chicago',
      month: 'short', day: 'numeric',
      hour: 'numeric', minute: '2-digit', second: '2-digit',
    }) + ' CT'
  } catch { return ts.slice(0, 19) }
}

export default function MarketPulseTab() {
  const { data, error, isLoading, mutate } = useSWR<RiskSignalsResponse>(
    '/api/spark/risk-signals',
    fetcher,
    { refreshInterval: REFRESH_MS },
  )

  if (isLoading) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-8 text-center">
        <p className="text-forge-muted text-sm animate-pulse">Loading risk signals…</p>
      </div>
    )
  }
  if (error) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4">
        <p className="text-red-400 text-sm">Risk signals load error: {error.message}</p>
      </div>
    )
  }
  if (!data) return null

  return (
    <div className="space-y-4">
      {/* Header strip with live market state + refresh */}
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-3 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-4 flex-wrap">
          <h3 className="text-sm font-medium text-gray-200">Market Pulse</h3>
          <span className="text-xs text-forge-muted">
            Beginner-friendly risk signals for SPARK 1DTE Iron Condor sellers.
          </span>
        </div>
        <div className="flex items-center gap-4 text-xs text-forge-muted flex-wrap">
          {data.spy_price != null && <span>SPY <span className="text-gray-200 font-mono">${data.spy_price.toFixed(2)}</span></span>}
          {data.vix != null && <span>VIX <span className="text-gray-200 font-mono">{data.vix.toFixed(2)}</span></span>}
          <span>{data.has_open_position ? 'IC OPEN' : 'No open IC'}</span>
          <span>Updated {formatCT(data.generated_at)}</span>
          <button
            onClick={() => mutate()}
            className="text-blue-300 hover:text-blue-200 underline underline-offset-2"
          >
            refresh
          </button>
        </div>
      </div>

      {/* What each card is — tiny primer for first-time viewers */}
      <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-3 text-xs leading-relaxed text-blue-200/90 space-y-1">
        <p><strong className="text-blue-300">How to read this:</strong> four signals tell you whether today is a good day to sell premium AND how close your current position is to trouble. Green means favorable for an IC seller. Amber means caution. Red means an open position is under stress.</p>
        <p className="text-blue-200/70">Nothing here auto-adjusts SPARK. These are informational only.</p>
      </div>

      {/* 4 cards */}
      {data.tiles.length === 0 ? (
        <div className="rounded-xl border border-forge-border bg-forge-card/80 p-6 text-center text-forge-muted text-sm">
          {data.note ?? 'No signals available.'}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {data.tiles.map((tile) => <TileCard key={tile.key} tile={tile} />)}
        </div>
      )}
    </div>
  )
}

function TileCard({ tile }: { tile: Tile }) {
  const c = COLOR_CLASSES[tile.color] ?? COLOR_CLASSES.grey
  return (
    <div className={`rounded-xl border ${c.border} ${c.tileBg} p-4 flex flex-col gap-3`}>
      <div className="flex items-center gap-2">
        <span className={`inline-block w-2.5 h-2.5 rounded-full ${c.dot}`} />
        <h4 className="text-[11px] uppercase tracking-wider text-forge-muted font-semibold">{tile.title}</h4>
      </div>
      <div>
        <p className={`text-base font-semibold ${c.headline}`}>{tile.headline}</p>
        {tile.numbers && (
          <p className="text-xs font-mono text-forge-muted mt-1">{tile.numbers}</p>
        )}
      </div>
      <p className="text-xs text-gray-300 leading-relaxed">{tile.beginner}</p>
    </div>
  )
}
