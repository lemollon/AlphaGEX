'use client'

/**
 * BuilderTab — the four SpreadWorks "builder chart" pieces composed into a
 * single view on /{bot} → Builder. Display-only: no strategy input, no
 * trade execution. Renders whatever IC is currently open for this bot in
 * the requested account_type scope (Paper or Live).
 *
 * Data:
 *   /api/{bot}/builder/snapshot?account_type=... → position/legs/payoff/metrics/mtm
 *   /api/{bot}/builder/candles?symbol=SPY&minutes=120
 *
 * Polling cadence:
 *   snapshot: 30s (quotes + greeks)
 *   candles: 60s (intraday bars)
 */
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import MetricsBar from './MetricsBar'
import CandleWithPayoff, { type Candle } from './CandleWithPayoff'
import LegBreakdown, { type BuilderLeg } from './LegBreakdown'

const SNAPSHOT_REFRESH_MS = 30_000
const CANDLES_REFRESH_MS = 60_000

interface BuilderTabProps {
  bot: 'flame' | 'spark' | 'inferno'
  accountType: 'sandbox' | 'production'
}

interface SnapshotResponse {
  tradier_connected?: boolean
  position: {
    position_id: string
    ticker: string
    expiration: string
    put_long_strike: number
    put_short_strike: number
    call_short_strike: number
    call_long_strike: number
    contracts: number
    entry_credit: number
    spread_width: number
    open_time: string | null
    account_type: string
    person: string | null
  } | null
  spot_price?: number | null
  legs?: BuilderLeg[]
  payoff?: {
    pnl_curve: Array<{ price: number; pnl: number }>
    max_profit: number
    max_loss: number
    breakeven_low: number
    breakeven_high: number
    profit_zone: { low: number; high: number }
    pop_heuristic: number
  }
  metrics?: {
    net_credit: number | null
    max_profit: number | null
    max_loss: number | null
    breakeven_low: number | null
    breakeven_high: number | null
    pop_heuristic: number | null
    net_delta: number | null
    net_gamma: number | null
    net_theta: number | null
    net_vega: number | null
  }
  mtm?: {
    cost_to_close_last: number | null
    cost_to_close_mid: number | null
    unrealized_pnl: number | null
    unrealized_pnl_pct: number | null
  } | null
}

interface CandlesResponse {
  symbol: string
  minutes: number
  candles: Candle[]
  tradier_connected: boolean
  error?: string
}

function fmtMoney2(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return `$${v.toFixed(2)}`
}

export default function BuilderTab({ bot, accountType }: BuilderTabProps) {
  const { data: snap, error: snapErr } = useSWR<SnapshotResponse>(
    `/api/${bot}/builder/snapshot?account_type=${accountType}`,
    fetcher,
    { refreshInterval: SNAPSHOT_REFRESH_MS },
  )
  const { data: candlesData } = useSWR<CandlesResponse>(
    `/api/${bot}/builder/candles?symbol=SPY&minutes=120`,
    fetcher,
    { refreshInterval: CANDLES_REFRESH_MS },
  )

  if (snapErr) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4">
        <p className="text-red-400 text-sm">Builder snapshot failed: {snapErr.message}</p>
      </div>
    )
  }

  if (!snap) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-8 text-center">
        <p className="text-forge-muted text-sm animate-pulse">Loading builder...</p>
      </div>
    )
  }

  if (!snap.position) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-8 text-center">
        <p className="text-gray-200 text-sm font-semibold mb-1">No open IC for this scope</p>
        <p className="text-forge-muted text-xs">
          Builder renders when {bot.toUpperCase()} has an open Iron Condor in the <span className="font-mono">{accountType}</span> scope.
          Open a position (or switch the Paper/Live toggle above) to see the payoff diagram, candle chart with strike walls, leg breakdown, and metrics.
        </p>
      </div>
    )
  }

  const p = snap.position
  const strikes = {
    putLong: p.put_long_strike,
    putShort: p.put_short_strike,
    callShort: p.call_short_strike,
    callLong: p.call_long_strike,
  }
  const breakevens = snap.metrics
    ? { lower: snap.metrics.breakeven_low, upper: snap.metrics.breakeven_high }
    : null

  return (
    <div className="space-y-4">
      {/* Position header */}
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-3">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
          <div>
            <span className="text-forge-muted uppercase tracking-wider mr-1">IC</span>
            <span className="font-mono text-gray-200">{p.ticker}</span>
            <span className="text-gray-500 font-mono ml-2">exp {p.expiration}</span>
          </div>
          <div className="font-mono text-gray-200">
            <span className="text-emerald-400">{p.put_long_strike}P</span>
            <span className="text-forge-muted">/</span>
            <span className="text-red-400">{p.put_short_strike}P</span>
            <span className="text-forge-muted"> — </span>
            <span className="text-red-400">{p.call_short_strike}C</span>
            <span className="text-forge-muted">/</span>
            <span className="text-emerald-400">{p.call_long_strike}C</span>
          </div>
          <div>
            <span className="text-forge-muted uppercase tracking-wider mr-1">Contracts</span>
            <span className="font-mono text-white">{p.contracts}</span>
          </div>
          <div>
            <span className="text-forge-muted uppercase tracking-wider mr-1">Credit</span>
            <span className="font-mono text-white">{fmtMoney2(p.entry_credit)}</span>
          </div>
          {snap.mtm && (
            <div>
              <span className="text-forge-muted uppercase tracking-wider mr-1">Unrealized</span>
              <span className={`font-mono ${(snap.mtm.unrealized_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {snap.mtm.unrealized_pnl != null
                  ? `${snap.mtm.unrealized_pnl >= 0 ? '+' : ''}$${snap.mtm.unrealized_pnl.toFixed(2)}`
                  : '—'}
                {snap.mtm.unrealized_pnl_pct != null && (
                  <span className="text-xs text-forge-muted ml-1">
                    ({snap.mtm.unrealized_pnl_pct.toFixed(1)}% of credit)
                  </span>
                )}
              </span>
            </div>
          )}
          <div>
            <span className="text-forge-muted uppercase tracking-wider mr-1">Spot</span>
            <span className="font-mono text-white">{fmtMoney2(snap.spot_price)}</span>
          </div>
        </div>
      </div>

      {/* Metrics */}
      <MetricsBar metrics={snap.metrics ?? null} legs={snap.legs ?? []} />

      {/* Unified chart — candles (left) + sideways payoff (right) sharing the
          same price Y-axis, strike lines spanning both regions, BE ticks on
          the right edge, spot badge at the boundary, "Now: +$X (+X.X%)"
          floating P&L badge in the payoff region. Matches SpreadWorks. */}
      <div className="space-y-2">
        <div className="flex items-baseline justify-between">
          <h3 className="text-[10px] uppercase tracking-wider text-forge-muted">
            SPY · Strikes · Payoff
          </h3>
          <span className="text-[10px] text-forge-muted font-mono">
            {candlesData?.candles?.length ?? 0} bars
            {snap.metrics?.breakeven_low != null && snap.metrics?.breakeven_high != null && (
              <>  ·  BE ${snap.metrics.breakeven_low.toFixed(2)} — ${snap.metrics.breakeven_high.toFixed(2)}</>
            )}
          </span>
        </div>
        <CandleWithPayoff
          candles={candlesData?.candles}
          spotPrice={snap.spot_price}
          strikes={strikes}
          pnlCurve={snap.payoff?.pnl_curve}
          breakevens={breakevens}
          currentPnl={snap.mtm?.unrealized_pnl ?? null}
          currentPnlPct={snap.mtm?.unrealized_pnl_pct ?? null}
          height={440}
        />
      </div>

      {/* Legs */}
      <LegBreakdown legs={snap.legs} expiration={p.expiration} />
    </div>
  )
}
