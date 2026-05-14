'use client'

/**
 * BlazeDirectionalChart — replaces the IC payoff view on BLAZE's dashboard.
 *
 * BLAZE trades 1DTE vertical debit spreads at gamma walls / flip points. The
 * IC payoff diagram makes no sense for a 2-leg directional vertical. This
 * chart instead surfaces what BLAZE actually trades against:
 *
 *   - SPY 5m candles (Tradier intraday, RTH-only)
 *   - Call Wall / Put Wall / Flip Point overlay lines (alphagex-api)
 *   - ±1σ ribbon (spot × VIX × √(1/252))
 *   - BLAZE position strikes (long / short of any open position)
 *   - Top scorecard strip (Price / Net GEX / Flip / Walls / Rating)
 *   - Price Position in GEX Structure gradient bar
 *   - Market Interpretation card
 *
 * Phase 1 (this file): static walls/flip = current snapshot only. Phase 2
 * will add intraday GEX history so the lines move with the chart.
 *
 * Data sources (all SWR, see refresh cadences below):
 *   /api/blaze/builder/candles?symbol=SPY&interval=5min&bars=80  → 60s
 *   /api/blaze/gex-context                                        → 30s
 *   /api/blaze/positions                                          → 15s
 *   /api/blaze/trades?limit=10                                    → 60s
 */
import { useMemo } from 'react'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import CandleChart from './dashboard/builder/CandleChart'
import { computePriceRange, type Candle } from '@/lib/price-scale'

const CANDLES_REFRESH = 60_000
const GEX_REFRESH = 30_000
const POSITIONS_REFRESH = 15_000
const TRADES_REFRESH = 60_000

interface CandlesResponse {
  candles: Candle[]
  tradier_connected: boolean
  error?: string
}

interface GexContext {
  symbol: string
  spot_price: number
  vix: number
  vix_is_estimated: boolean
  net_gex: number
  call_gex: number
  put_gex: number
  call_wall: number
  put_wall: number
  flip_point: number
  max_pain: number
  regime: string
  mm_state: string
  rating: string
  timestamp: string | null
  error?: string
}

interface BlazePosition {
  position_id: string
  direction?: 'call' | 'put' | string | null
  long_strike?: number
  short_strike?: number
  debit?: number
  contracts: number
  setup_type?: string | null
  underlying_at_entry: number
}

interface BlazeTrade {
  position_id: string
  direction?: string | null
  long_strike?: number
  short_strike?: number
  debit?: number
  close_price: number
  realized_pnl: number
  close_reason: string
  close_time: string | null
  open_time: string | null
}

/* ---------------------------------------------------------------- */
/*  Helpers                                                         */
/* ---------------------------------------------------------------- */

function fmtBillions(v: number): string {
  if (!Number.isFinite(v)) return '—'
  const abs = Math.abs(v)
  if (abs >= 1e9) return `${(v / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `${(v / 1e6).toFixed(0)}M`
  return `${Math.round(v).toLocaleString()}`
}

function fmtDistance(spot: number, level: number): string {
  if (!spot || !level) return ''
  const pct = ((level - spot) / spot) * 100
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}% away`
}

function ratingColor(rating: string): string {
  if (rating.includes('BULLISH') && !rating.includes('CAUTIOUS')) return 'text-emerald-400'
  if (rating === 'CAUTIOUS_BULLISH') return 'text-emerald-300/80'
  if (rating === 'CAUTIOUS_BEARISH') return 'text-red-300/80'
  if (rating === 'BEARISH') return 'text-red-400'
  return 'text-gray-300'
}

function regimeColor(regime: string): string {
  if (regime.includes('POSITIVE')) return 'text-emerald-400'
  if (regime.includes('NEGATIVE')) return 'text-red-400'
  return 'text-gray-300'
}

/* ---------------------------------------------------------------- */
/*  Scorecard                                                        */
/* ---------------------------------------------------------------- */

function Scorecard({
  label,
  value,
  sub,
  color,
}: {
  label: string
  value: React.ReactNode
  sub?: React.ReactNode
  color?: string
}) {
  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 px-4 py-3">
      <p className="text-[10px] text-forge-muted uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-xl font-bold font-mono ${color ?? 'text-white'}`}>{value}</p>
      {sub != null && <p className="text-[10px] text-forge-muted mt-0.5">{sub}</p>}
    </div>
  )
}

/* ---------------------------------------------------------------- */
/*  Main component                                                  */
/* ---------------------------------------------------------------- */

export default function BlazeDirectionalChart() {
  const { data: candlesData, error: candlesErr } = useSWR<CandlesResponse>(
    `/api/blaze/builder/candles?symbol=SPY&interval=5min&bars=80`,
    fetcher,
    { refreshInterval: CANDLES_REFRESH },
  )

  const { data: gex, error: gexErr } = useSWR<GexContext>(
    `/api/blaze/gex-context`,
    fetcher,
    { refreshInterval: GEX_REFRESH },
  )

  const { data: posData } = useSWR<{ positions: BlazePosition[] }>(
    `/api/blaze/positions`,
    fetcher,
    { refreshInterval: POSITIONS_REFRESH },
  )

  const { data: tradesData } = useSWR<{ trades: BlazeTrade[] }>(
    `/api/blaze/trades?limit=10`,
    fetcher,
    { refreshInterval: TRADES_REFRESH },
  )

  const candles = candlesData?.candles ?? []
  const openPositions = posData?.positions ?? []
  const todaysTrades = useMemo(() => {
    if (!tradesData?.trades) return []
    const todayCt = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })
    return tradesData.trades.filter(t => {
      if (!t.close_time) return false
      try {
        const ct = new Date(t.close_time).toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })
        return ct === todayCt
      } catch { return false }
    })
  }, [tradesData])

  // Compose strike set from current open BLAZE position (max 1 at a time).
  // Phase 1: only the open position's strikes are drawn — closed trades show
  // up as the daily summary chip strip below.
  const openPos = openPositions[0]
  const strikes = openPos && openPos.direction && openPos.long_strike && openPos.short_strike
    ? {
        // Long = green (debit paid for the long leg)
        longPutStrike: openPos.direction === 'put' ? openPos.long_strike : null,
        longCallStrike: openPos.direction === 'call' ? openPos.long_strike : null,
        // Short = red (debit offset by short premium)
        shortPutStrike: openPos.direction === 'put' ? openPos.short_strike : null,
        shortCallStrike: openPos.direction === 'call' ? openPos.short_strike : null,
      }
    : null

  // ±1σ ribbon: spot × (VIX/100) × √(1/252). Mirrors gex-client.ts math.
  const sigmaPlus = gex && gex.spot_price && gex.vix
    ? gex.spot_price * (1 + (gex.vix / 100) * Math.sqrt(1 / 252))
    : null
  const sigmaMinus = gex && gex.spot_price && gex.vix
    ? gex.spot_price * (1 - (gex.vix / 100) * Math.sqrt(1 / 252))
    : null

  // Price range — incorporate candles + walls + flip + ±1σ + position strikes.
  // Then expand to ±0.8% around spot so the chart breathes.
  const { minPrice, maxPrice } = useMemo(() => {
    const gexForRange = gex
      ? { flip_point: gex.flip_point, call_wall: gex.call_wall, put_wall: gex.put_wall }
      : null
    const base = computePriceRange(candles, strikes, gexForRange, 0.005)
    if (sigmaPlus != null && sigmaPlus > base.maxPrice) base.maxPrice = sigmaPlus
    if (sigmaMinus != null && sigmaMinus < base.minPrice) base.minPrice = sigmaMinus
    if (gex?.spot_price) {
      const margin = gex.spot_price * 0.008
      base.minPrice = Math.min(base.minPrice, gex.spot_price - margin)
      base.maxPrice = Math.max(base.maxPrice, gex.spot_price + margin)
    }
    return base
  }, [candles, strikes, gex, sigmaPlus, sigmaMinus])

  const gexLines = useMemo(() => {
    if (!gex) return []
    const lines: Array<{ price: number; color: string; label: string; dash?: string; opacity?: number; side?: 'left' | 'right' }> = []
    if (gex.call_wall) lines.push({ price: gex.call_wall, color: '#22d3ee', label: `CALL WALL $${gex.call_wall.toFixed(0)}`, dash: '4,4' })
    if (gex.put_wall) lines.push({ price: gex.put_wall, color: '#c084fc', label: `PUT WALL $${gex.put_wall.toFixed(0)}`, dash: '4,4' })
    if (gex.flip_point) lines.push({ price: gex.flip_point, color: '#facc15', label: `FLIP $${gex.flip_point.toFixed(0)}`, dash: '8,3', opacity: 0.9 })
    if (sigmaPlus) lines.push({ price: sigmaPlus, color: '#9ca3af', label: `+1σ`, dash: '1,3', opacity: 0.55, side: 'right' })
    if (sigmaMinus) lines.push({ price: sigmaMinus, color: '#9ca3af', label: `−1σ`, dash: '1,3', opacity: 0.55, side: 'right' })
    return lines
  }, [gex, sigmaPlus, sigmaMinus])

  /* -------- Render: error/loading guards -------- */

  if (gexErr) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4">
        <p className="text-red-400 text-sm">GEX context unavailable: {gexErr.message}</p>
        <p className="text-red-300/70 text-xs mt-1">
          The alphagex-api endpoint is not reachable. Walls / flip / regime will be blank until it recovers.
        </p>
      </div>
    )
  }

  if (!gex) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-8 text-center">
        <p className="text-forge-muted text-sm animate-pulse">Loading directional chart…</p>
      </div>
    )
  }

  /* -------- Price-position-in-GEX-structure gradient bar -------- */
  const structPct = (() => {
    if (!gex.put_wall || !gex.call_wall || gex.call_wall <= gex.put_wall) return 50
    const raw = ((gex.spot_price - gex.put_wall) / (gex.call_wall - gex.put_wall)) * 100
    return Math.max(0, Math.min(100, raw))
  })()
  const flipPct = (() => {
    if (!gex.put_wall || !gex.call_wall || gex.call_wall <= gex.put_wall) return 50
    const raw = ((gex.flip_point - gex.put_wall) / (gex.call_wall - gex.put_wall)) * 100
    return Math.max(0, Math.min(100, raw))
  })()

  /* -------- Market interpretation rules -------- */
  const interp = (() => {
    const regimeText = gex.regime.includes('POSITIVE')
      ? 'Positive gamma regime — dealers are long gamma. Price tends to mean-revert. Counter-trend wall fades work; trend breaks are rare.'
      : gex.regime.includes('NEGATIVE')
        ? 'Negative gamma regime — dealers are short gamma. Price tends to trend. Wall breaks more likely than wall fades.'
        : 'Neutral gamma regime — no strong dealer-flow bias.'
    const flipText = gex.spot_price > gex.flip_point
      ? `Price above flip ($${gex.flip_point.toFixed(0)}) — positive gamma territory, upside stability.`
      : `Price below flip ($${gex.flip_point.toFixed(0)}) — negative gamma territory, downside acceleration risk.`
    return { regimeText, flipText }
  })()

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs">
          <span className="text-forge-muted">SPY Intraday 5m — Price + GEX walls</span>
          <span className="text-gray-500">·</span>
          <span className="text-forge-muted">
            Snapshot {gex.timestamp ? new Date(gex.timestamp).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/Chicago' }) : '—'} CT
          </span>
        </div>
        <span className={`text-[10px] uppercase tracking-wider font-semibold ${regimeColor(gex.regime)}`}>
          {gex.regime.replace(/_/g, ' ')}
        </span>
      </div>

      {/* Scorecard strip */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <Scorecard label="Price" value={`$${gex.spot_price.toFixed(2)}`} />
        <Scorecard
          label="Net GEX"
          value={`${gex.net_gex >= 0 ? '+' : ''}${fmtBillions(gex.net_gex)}`}
          color={gex.net_gex >= 0 ? 'text-emerald-400' : 'text-red-400'}
          sub={gex.regime.replace(/_/g, ' ')}
        />
        <Scorecard
          label="Flip Point"
          value={`$${gex.flip_point.toFixed(2)}`}
          color="text-yellow-400"
          sub={fmtDistance(gex.spot_price, gex.flip_point)}
        />
        <Scorecard
          label="Call Wall"
          value={`$${gex.call_wall.toFixed(2)}`}
          color="text-cyan-400"
          sub={fmtDistance(gex.spot_price, gex.call_wall)}
        />
        <Scorecard
          label="Put Wall"
          value={`$${gex.put_wall.toFixed(2)}`}
          color="text-fuchsia-400"
          sub={fmtDistance(gex.spot_price, gex.put_wall)}
        />
        <Scorecard
          label="Rating"
          value={gex.rating.replace(/_/g, ' ')}
          color={ratingColor(gex.rating)}
        />
      </div>

      {/* Chart */}
      <div className="rounded-xl border border-forge-border bg-forge-card/80 overflow-hidden">
        <CandleChart
          candles={candles}
          minPrice={minPrice}
          maxPrice={maxPrice}
          height={460}
          strikes={strikes}
          spotPrice={gex.spot_price}
          fetchError={candlesErr?.message ?? candlesData?.error ?? null}
          gexLines={gexLines}
        />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2 text-[10px] text-forge-muted border-t border-forge-border">
          <span className="inline-flex items-center gap-1">
            <span className="inline-block w-3 h-2 bg-cyan-400" /> Call Wall
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block w-3 h-2 bg-fuchsia-400" /> Put Wall
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block w-3 h-2 bg-yellow-400" /> Flip
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block w-3 h-2 bg-emerald-500" /> Long leg
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block w-3 h-2 bg-red-500" /> Short leg
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block w-3 h-2 bg-gray-400/60" /> ±1σ
          </span>
          <span className="ml-auto">
            {candlesData?.candles?.length ?? 0} bars · {new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })}
          </span>
        </div>
      </div>

      {/* Price position in GEX structure */}
      <div className="rounded-xl border border-forge-border bg-forge-card/80 px-4 py-3">
        <div className="flex items-center justify-between text-[10px] text-forge-muted uppercase tracking-wider mb-2">
          <span>Price Position in GEX Structure</span>
          <span className={gex.net_gex >= 0 ? 'text-emerald-400' : 'text-red-400'}>
            {gex.net_gex >= 0 ? 'POSITIVE GAMMA ZONE' : 'NEGATIVE GAMMA ZONE'}
          </span>
        </div>
        <div className="relative h-3 rounded-full overflow-hidden bg-forge-border">
          <div className="absolute inset-y-0 left-0 bg-gradient-to-r from-red-900/70 via-yellow-700/40 to-emerald-900/70" style={{ width: '100%' }} />
          <div className="absolute top-0 h-full w-0.5 bg-yellow-400" style={{ left: `${flipPct}%` }} />
          <div className="absolute top-0 h-full w-1 bg-blue-400 rounded shadow shadow-blue-400/50" style={{ left: `${structPct}%`, transform: 'translateX(-50%)' }} />
        </div>
        <div className="flex justify-between mt-1 text-[9px] font-mono text-forge-muted">
          <span className="text-fuchsia-400">Put Wall ${gex.put_wall.toFixed(0)} ({fmtDistance(gex.spot_price, gex.put_wall)})</span>
          <span className="text-yellow-400">Flip ${gex.flip_point.toFixed(0)}</span>
          <span className="text-cyan-400">({fmtDistance(gex.spot_price, gex.call_wall)}) Call Wall ${gex.call_wall.toFixed(0)}</span>
        </div>
      </div>

      {/* Market interpretation */}
      <div className="rounded-xl border border-forge-border bg-forge-card/80 px-4 py-3">
        <p className="text-xs text-forge-muted uppercase tracking-wider mb-2">Market Interpretation</p>
        <p className="text-sm text-gray-200 mb-1">{interp.regimeText}</p>
        <p className="text-sm text-gray-300/80">{interp.flipText}</p>
      </div>

      {/* Open position + today's trades */}
      {openPos && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 px-4 py-3">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-3">
              <span className="text-[10px] uppercase tracking-wider text-emerald-400">Open Position</span>
              <span className="font-mono text-gray-200">
                {openPos.long_strike}/{openPos.short_strike}{openPos.direction === 'call' ? 'C' : 'P'}
              </span>
              <span className="font-mono text-forge-muted">×{openPos.contracts}</span>
              <span className="font-mono text-red-300">DR ${openPos.debit?.toFixed(2)}</span>
              {openPos.setup_type && (
                <span className="text-[10px] uppercase tracking-wider text-gray-400">{openPos.setup_type.replace(/_/g, ' ')}</span>
              )}
            </div>
          </div>
        </div>
      )}

      {todaysTrades.length > 0 && (
        <div className="rounded-xl border border-forge-border bg-forge-card/80 px-4 py-3">
          <p className="text-[10px] text-forge-muted uppercase tracking-wider mb-2">
            Today&apos;s closed trades ({todaysTrades.length})
          </p>
          <div className="space-y-1.5 text-xs font-mono">
            {todaysTrades.map(t => {
              const win = t.realized_pnl >= 0
              const closeT = t.close_time
                ? new Date(t.close_time).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/Chicago' })
                : '—'
              return (
                <div key={t.position_id} className="flex items-center gap-3">
                  <span className="text-forge-muted w-12">{closeT}</span>
                  <span className="text-gray-200 w-20">
                    {t.long_strike}/{t.short_strike}{t.direction === 'call' ? 'C' : 'P'}
                  </span>
                  <span className="text-forge-muted w-20">DR ${t.debit?.toFixed(2)} → ${t.close_price.toFixed(2)}</span>
                  <span className={win ? 'text-emerald-400' : 'text-red-400'}>
                    {win ? '+' : ''}${t.realized_pnl.toFixed(2)}
                  </span>
                  <span className="text-[10px] uppercase tracking-wider text-forge-muted ml-auto">{t.close_reason}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
