'use client'

/**
 * BuilderTab — the SpreadWorks "builder chart" pieces composed into a single
 * view on /{bot} → IC Chart. Display-only: no strategy input, no trade
 * execution. Renders whatever IC is currently open for this bot in the
 * requested account_type scope (Paper or Live).
 *
 * Layout (matches SpreadWorks' ChartArea exactly):
 *   [ CandleChart                flex-[3]  ] [ PayoffPanel  220px ]
 *   shared price Y-axis via minPrice/maxPrice computed in ChartArea.
 *
 * Data:
 *   /api/{bot}/builder/snapshot?account_type=... → position/legs/payoff/metrics/mtm
 *   /api/{bot}/builder/candles?symbol=SPY&minutes=120
 *
 * Polling cadence:
 *   snapshot: 30s  (quotes + greeks + MTM)
 *   candles:  60s  (intraday bars)
 */
import { useState } from 'react'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import MetricsBar from './MetricsBar'
import ChartArea from './ChartArea'
import PayoffTable from './PayoffTable'
import LegBreakdown, { type BuilderLeg } from './LegBreakdown'
import type { Candle } from '@/lib/price-scale'

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
    status: string
    is_open: boolean
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
  closed?: {
    status: string
    close_price: number | null
    close_time: string | null
    close_reason: string | null
    realized_pnl: number | null
    realized_pnl_pct: number | null
  } | null
}

interface CandlesResponse {
  symbol: string
  interval?: string
  bars?: number
  minutes?: number
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
  // interval=5min × bars=80 → ~1 full RTH day of price action. Matches
  // SpreadWorks' density (they use 15min × 80 bars for multi-day context;
  // we use 5min because SPARK is 1DTE so intraday is the relevant window).
  // Backend forces session_filter='open' so pre/post market bars never
  // appear. When the market is closed the chart freezes at the last live
  // session's bars — no after-hours noise on the right edge.
  const { data: candlesData } = useSWR<CandlesResponse>(
    `/api/${bot}/builder/candles?symbol=SPY&interval=5min&bars=80`,
    fetcher,
    { refreshInterval: CANDLES_REFRESH_MS },
  )

  // View + pnl mode toggles (SpreadWorks parity). viewMode controls whether
  // the main area renders the candle+payoff chart ("graph") or the numeric
  // table ("table"). pnlMode only affects the table representation.
  const [viewMode, setViewMode] = useState<'graph' | 'table'>('graph')
  const [pnlMode, setPnlMode] = useState<'dollar' | 'percent'>('dollar')

  if (snapErr) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4">
        <p className="text-red-400 text-sm">IC Chart snapshot failed: {snapErr.message}</p>
      </div>
    )
  }

  if (!snap) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-8 text-center">
        <p className="text-forge-muted text-sm animate-pulse">Loading IC chart...</p>
      </div>
    )
  }

  if (!snap.position) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-8 text-center">
        <p className="text-gray-200 text-sm font-semibold mb-1">No IC history in this scope</p>
        <p className="text-forge-muted text-xs">
          IC Chart renders as soon as {bot.toUpperCase()} takes its first Iron Condor in the <span className="font-mono">{accountType}</span> scope.
          Switch the Paper/Live toggle above if you want to see a different scope.
        </p>
      </div>
    )
  }

  const p = snap.position
  const isOpen = p.is_open
  const closedMeta = snap.closed ?? null

  // Map IronForge snake_case strike keys to SpreadWorks-style long*/short*
  // keys used by the ported components (priceScale, CandleChart, PayoffPanel).
  const spreadworksStrikes = {
    longPutStrike: p.put_long_strike,
    longCallStrike: p.call_long_strike,
    shortPutStrike: p.put_short_strike,
    shortCallStrike: p.call_short_strike,
  }

  // Reshape the snapshot payoff into SpreadWorks' `calcResult` shape that
  // PayoffPanel expects via ChartArea. When the position is closed, pass
  // the close price + realized P&L through too so the "Now" badge on the
  // payoff panel becomes a "Closed: +$X" badge anchored at close_price's Y.
  const calcResult = snap.payoff
    ? {
        pnl_curve: snap.payoff.pnl_curve,
        max_profit: snap.payoff.max_profit,
        max_loss: snap.payoff.max_loss,
        lower_breakeven: snap.payoff.breakeven_low,
        upper_breakeven: snap.payoff.breakeven_high,
        closed_price: !isOpen && closedMeta ? closedMeta.close_price : null,
        closed_realized_pnl: !isOpen && closedMeta ? closedMeta.realized_pnl : null,
        closed_realized_pct: !isOpen && closedMeta ? closedMeta.realized_pnl_pct : null,
        is_open: isOpen,
      }
    : null

  const statusBadge = isOpen
    ? <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 uppercase tracking-wider">Open</span>
    : <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-gray-500/20 text-gray-300 border border-gray-500/30 uppercase tracking-wider">{(closedMeta?.status ?? 'Closed')}</span>

  return (
    <div className="space-y-4">
      {/* Position header */}
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-3">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-forge-muted uppercase tracking-wider mr-1">IC</span>
            <span className="font-mono text-gray-200">{p.ticker}</span>
            <span className="text-gray-500 font-mono">exp {p.expiration}</span>
            {statusBadge}
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
          {/* P&L: unrealized when open, realized when closed */}
          {isOpen && snap.mtm ? (
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
          ) : !isOpen && closedMeta ? (
            <>
              <div>
                <span className="text-forge-muted uppercase tracking-wider mr-1">Realized</span>
                <span className={`font-mono ${(closedMeta.realized_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {closedMeta.realized_pnl != null
                    ? `${closedMeta.realized_pnl >= 0 ? '+' : ''}$${closedMeta.realized_pnl.toFixed(2)}`
                    : '—'}
                  {closedMeta.realized_pnl_pct != null && (
                    <span className="text-xs text-forge-muted ml-1">
                      ({closedMeta.realized_pnl_pct.toFixed(1)}% of net credit)
                    </span>
                  )}
                </span>
              </div>
              {closedMeta.close_reason && (
                <div>
                  <span className="text-forge-muted uppercase tracking-wider mr-1">Reason</span>
                  <span className="font-mono text-gray-300">{closedMeta.close_reason}</span>
                </div>
              )}
              {closedMeta.close_time && (
                <div>
                  <span className="text-forge-muted uppercase tracking-wider mr-1">Closed</span>
                  <span className="font-mono text-gray-300">
                    {new Date(closedMeta.close_time).toLocaleString('en-US', {
                      month: 'short', day: 'numeric',
                      hour: 'numeric', minute: '2-digit',
                      timeZone: 'America/Chicago',
                    })} CT
                  </span>
                </div>
              )}
            </>
          ) : null}
          <div>
            <span className="text-forge-muted uppercase tracking-wider mr-1">Spot</span>
            <span className="font-mono text-white">{fmtMoney2(snap.spot_price)}</span>
          </div>
        </div>
      </div>

      {/* Metrics */}
      <MetricsBar metrics={snap.metrics ?? null} legs={snap.legs ?? []} />

      {/* View toggle strip (SpreadWorks parity).
          Graph / Table switches the main visualization area.
          P&L $ / P&L % only affects the Table view's unit. */}
      <div className="flex items-center gap-2 text-[11px] font-mono">
        <div className="inline-flex rounded-md border border-forge-border overflow-hidden">
          <button
            onClick={() => setViewMode('graph')}
            className={`px-3 py-1.5 transition-colors ${
              viewMode === 'graph'
                ? 'bg-blue-500/20 text-blue-300 font-semibold'
                : 'text-forge-muted hover:text-gray-200'
            }`}
          >
            Graph
          </button>
          <button
            onClick={() => setViewMode('table')}
            className={`px-3 py-1.5 border-l border-forge-border transition-colors ${
              viewMode === 'table'
                ? 'bg-blue-500/20 text-blue-300 font-semibold'
                : 'text-forge-muted hover:text-gray-200'
            }`}
          >
            Table
          </button>
        </div>
        <div className={`inline-flex rounded-md border border-forge-border overflow-hidden ${viewMode === 'graph' ? 'opacity-40' : ''}`}>
          <button
            onClick={() => setPnlMode('dollar')}
            disabled={viewMode === 'graph'}
            className={`px-3 py-1.5 transition-colors ${
              pnlMode === 'dollar'
                ? 'bg-blue-500/20 text-blue-300 font-semibold'
                : 'text-forge-muted hover:text-gray-200'
            } disabled:cursor-not-allowed`}
          >
            P&L $
          </button>
          <button
            onClick={() => setPnlMode('percent')}
            disabled={viewMode === 'graph'}
            className={`px-3 py-1.5 border-l border-forge-border transition-colors ${
              pnlMode === 'percent'
                ? 'bg-blue-500/20 text-blue-300 font-semibold'
                : 'text-forge-muted hover:text-gray-200'
            } disabled:cursor-not-allowed`}
          >
            P&L %
          </button>
        </div>
      </div>

      {/* Visualization area: Graph (candles + payoff) or Table (numeric P&L). */}
      {viewMode === 'graph' ? (
        <div className="flex flex-col" style={{ height: 500 }}>
          <ChartArea
            candles={candlesData?.candles}
            spotPrice={snap.spot_price}
            strikes={spreadworksStrikes}
            calcResult={calcResult}
            height={500}
            rangePct={2.2}
          />
        </div>
      ) : (
        <PayoffTable
          pnlCurve={snap.payoff?.pnl_curve}
          maxProfit={snap.payoff?.max_profit ?? snap.metrics?.max_profit ?? null}
          maxLoss={snap.payoff?.max_loss ?? snap.metrics?.max_loss ?? null}
          spotPrice={snap.spot_price}
          netCredit={p.entry_credit}
          contracts={p.contracts}
          pnlMode={pnlMode}
        />
      )}

      {/* Legs */}
      <LegBreakdown legs={snap.legs} expiration={p.expiration} isOpen={isOpen} />
    </div>
  )
}
