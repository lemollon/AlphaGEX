'use client'

/**
 * ChartArea — ported verbatim from
 * spreadworks/frontend/src/components/ChartArea.jsx.
 *
 * Flex container that renders CandleChart (flex-[3]) and PayoffPanel
 * (220px fixed) side-by-side, computing a SHARED price range so strike
 * lines align perfectly across the divider.
 */
import { useMemo } from 'react'
import CandleChart from './CandleChart'
import PayoffPanel from './PayoffPanel'
import { computePriceRange, type Candle, type StrikeSet, type GexLevels } from '@/lib/price-scale'
import type { PnlPoint } from '@/lib/payoff-shape'

interface ChartAreaProps {
  candles: Candle[] | null | undefined
  spotPrice?: number | null
  strikes?: StrikeSet | null
  gexData?: GexLevels | null
  calcResult?: {
    pnl_curve?: PnlPoint[] | null
    max_profit?: number | null
    max_loss?: number | null
    lower_breakeven?: number | null
    upper_breakeven?: number | null
    // Commit G: when the IC has already closed, these carry the realized
    // outcome so the payoff panel can anchor a "Closed: +$X" badge at
    // the close_price instead of a live "Now: ..." badge at spot.
    closed_price?: number | null
    closed_realized_pnl?: number | null
    closed_realized_pct?: number | null
    is_open?: boolean
  } | null
  height?: number
  /** Symmetric range % around spot — 2.2 gives ±2.2% of spot as the base
   * range (matches SpreadWorks default). Floor'd against the natural
   * candle+strike range so the chart never crops real data. */
  rangePct?: number
  fetchError?: string | null
  candleSpacing?: number
}

export default function ChartArea({
  candles,
  spotPrice,
  gexData,
  strikes,
  calcResult,
  height = 500,
  rangePct = 2.2,
  fetchError,
  candleSpacing,
}: ChartAreaProps) {
  const { minPrice, maxPrice } = useMemo(() => {
    const base = computePriceRange(candles, strikes, gexData, 0.005)
    if (spotPrice && rangePct) {
      const rangeAmt = spotPrice * (rangePct / 100)
      const rMin = spotPrice - rangeAmt
      const rMax = spotPrice + rangeAmt
      return {
        minPrice: Math.min(base.minPrice, rMin),
        maxPrice: Math.max(base.maxPrice, rMax),
      }
    }
    return base
  }, [candles, strikes, gexData, spotPrice, rangePct])

  const breakevens = calcResult
    ? { lower: calcResult.lower_breakeven ?? null, upper: calcResult.upper_breakeven ?? null }
    : null

  return (
    <div className="flex flex-1 min-h-0 rounded-xl border border-forge-border bg-forge-card/80 overflow-hidden">
      <CandleChart
        candles={candles}
        minPrice={minPrice}
        maxPrice={maxPrice}
        height={height}
        strikes={strikes ?? null}
        spotPrice={spotPrice ?? null}
        fetchError={fetchError ?? null}
        candleSpacing={candleSpacing}
      />
      <PayoffPanel
        pnlCurve={calcResult?.pnl_curve ?? null}
        minPrice={minPrice}
        maxPrice={maxPrice}
        height={height}
        strikes={strikes ?? null}
        spotPrice={spotPrice ?? null}
        maxProfit={calcResult?.max_profit ?? null}
        maxLoss={calcResult?.max_loss ?? null}
        breakevens={breakevens}
        closedPrice={calcResult?.closed_price ?? null}
        closedRealizedPnl={calcResult?.closed_realized_pnl ?? null}
        closedRealizedPct={calcResult?.closed_realized_pct ?? null}
        isOpen={calcResult?.is_open ?? true}
      />
    </div>
  )
}
