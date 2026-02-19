'use client'

/**
 * useDashboardBatch — single HTTP call replaces ~50 individual API calls.
 *
 * Returns the raw batch response and a pre-built `fallback` object that can
 * be fed into <SWRConfig value={{ fallback }}>.  Every child useSWR hook
 * whose cache key appears in the fallback will receive pre-fetched data
 * without making its own HTTP request.
 */

import { useMemo } from 'react'
import useSWR from 'swr'
import { api } from '@/lib/api'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface BatchResponse {
  success: boolean
  data: Record<string, any>
  meta?: { sections_requested: string[]; elapsed_ms: number }
}

// ---------------------------------------------------------------------------
// Fetcher
// ---------------------------------------------------------------------------

const fetchBatch = async (
  sections: string[],
  equityCurveDays: number = 30,
): Promise<BatchResponse> => {
  const res = await api.post('/api/v1/dashboard/batch', {
    sections,
    equity_curve_days: equityCurveDays,
  })
  return res.data
}

// ---------------------------------------------------------------------------
// Fallback builder — maps batch response paths → SWR cache keys
// ---------------------------------------------------------------------------

function buildFallback(data: Record<string, any> | undefined): Record<string, any> {
  if (!data) return {}

  const f: Record<string, any> = {}

  // Bot statuses → named keys used by useMarketData hooks
  const statuses = data.bot_statuses
  if (statuses) {
    if (statuses.fortress) f['fortress-status'] = statuses.fortress
    if (statuses.solomon) f['solomon-status'] = statuses.solomon
    if (statuses.gideon) f['gideon-status'] = statuses.gideon
    if (statuses.anchor) f['anchor-status'] = statuses.anchor
    if (statuses.samson) f['samson-status'] = statuses.samson
    if (statuses.jubilee) f['jubilee-status'] = statuses.jubilee
    if (statuses.agape) f['agape-status'] = statuses.agape
    if (statuses.agape_btc) f['agape-btc-status'] = statuses.agape_btc
    if (statuses.agape_xrp) f['agape-xrp-status'] = statuses.agape_xrp
  }

  // Bot live PnL → named keys
  const pnl = data.bot_live_pnl
  if (pnl) {
    if (pnl.fortress) f['fortress-live-pnl'] = pnl.fortress
    if (pnl.solomon) f['solomon-live-pnl'] = pnl.solomon
    if (pnl.gideon) f['gideon-live-pnl'] = pnl.gideon
    if (pnl.anchor) f['anchor-live-pnl'] = pnl.anchor
    if (pnl.samson) f['samson-live-pnl'] = pnl.samson
  }

  // Market data → URL keys used by MarketConditionsBanner
  const market = data.market_data
  if (market) {
    if (market.gex_spy) f['/api/gex/SPY'] = market.gex_spy
    if (market.vix) f['/api/vix/current'] = market.vix
    if (market.prophet) f['/api/prophet/status'] = market.prophet
  }

  // Daily manna → named key from useDailyMannaWidget()
  if (data.daily_manna) {
    f['daily-manna-widget'] = data.daily_manna
  }

  // Bot positions → URL keys used by AllOpenPositionsTable
  const pos = data.bot_positions
  if (pos) {
    if (pos.fortress) f['/api/fortress/positions'] = pos.fortress
    if (pos.solomon) f['/api/solomon/positions'] = pos.solomon
    if (pos.gideon) f['/api/gideon/positions'] = pos.gideon
    if (pos.anchor) f['/api/anchor/positions'] = pos.anchor
    if (pos.samson) f['/api/samson/positions'] = pos.samson
  }

  // Bot reports → URL keys used by AllBotReportsSummary
  const reports = data.bot_reports
  if (reports) {
    if (reports.fortress) f['/api/trader/fortress/reports/today/summary'] = reports.fortress
    if (reports.solomon) f['/api/trader/solomon/reports/today/summary'] = reports.solomon
    if (reports.gideon) f['/api/trader/gideon/reports/today/summary'] = reports.gideon
    if (reports.anchor) f['/api/trader/anchor/reports/today/summary'] = reports.anchor
    if (reports.samson) f['/api/trader/samson/reports/today/summary'] = reports.samson
  }

  // Equity curves → URL keys used by MultiBotEquityCurveImpl
  const eq = data.bot_equity_curves
  if (eq) {
    const days = 30 // default used by MultiBotEquityCurve
    const mapping: Record<string, string> = {
      fortress: `/api/fortress/equity-curve?days=${days}`,
      solomon: `/api/solomon/equity-curve?days=${days}`,
      gideon: `/api/gideon/equity-curve?days=${days}`,
      anchor: `/api/anchor/equity-curve?days=${days}`,
      samson: `/api/samson/equity-curve?days=${days}`,
      jubilee: `/api/jubilee/ic/equity-curve?days=${days}`,
      valor: `/api/valor/paper-equity-curve?days=${days}`,
      agape: `/api/agape/equity-curve?days=${days}`,
      agape_spot: `/api/agape-spot/equity-curve?days=${days}`,
      agape_btc: `/api/agape-btc/equity-curve?days=${days}`,
      agape_xrp: `/api/agape-xrp/equity-curve?days=${days}`,
      agape_eth_perp: `/api/agape-eth-perp/equity-curve?days=${days}`,
      agape_btc_perp: `/api/agape-btc-perp/equity-curve?days=${days}`,
      agape_xrp_perp: `/api/agape-xrp-perp/equity-curve?days=${days}`,
      agape_doge_perp: `/api/agape-doge-perp/equity-curve?days=${days}`,
      agape_shib_perp: `/api/agape-shib-perp/equity-curve?days=${days}`,
    }
    for (const [bot, key] of Object.entries(mapping)) {
      if (eq[bot]) f[key] = eq[bot]
    }
  }

  // ML status → URL keys used by Phase 3 widgets
  const ml = data.ml_status
  if (ml) {
    if (ml.wisdom) f['/api/ml/wisdom/status'] = ml.wisdom
    if (ml.bot_ml) f['/api/ml/bot-status'] = ml.bot_ml
    if (ml.quant) f['/api/quant/status'] = ml.quant
    if (ml.alerts) f['/api/quant/alerts?limit=5&unacknowledged_only=true'] = ml.alerts
    if (ml.optimizer) f['/api/math-optimizer/status'] = ml.optimizer
    if (ml.optimizer_live) f['/api/math-optimizer/live-dashboard'] = ml.optimizer_live
  }

  // System → URL key used by SyncStatusWidget
  if (data.system) {
    f['/api/time'] = data.system
  }

  return f
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

const ALL_SECTIONS = [
  'bot_statuses',
  'bot_live_pnl',
  'bot_positions',
  'bot_equity_curves',
  'bot_reports',
  'market_data',
  'ml_status',
  'daily_manna',
  'system',
]

export function useDashboardBatch(equityCurveDays: number = 30) {
  const { data, error, isLoading } = useSWR<BatchResponse>(
    'dashboard-batch',
    () => fetchBatch(ALL_SECTIONS, equityCurveDays),
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      revalidateIfStale: false,
      // Don't auto-refresh the batch — individual hooks handle their own intervals
      refreshInterval: 0,
    },
  )

  const fallback = useMemo(() => buildFallback(data?.data), [data])

  return {
    data: data?.data,
    fallback,
    error,
    isLoading,
    meta: data?.meta,
  }
}
