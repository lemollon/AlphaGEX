'use client'
import { useCallback, useEffect, useState } from 'react'
import type { GexAnalysisData, GexAllData } from '@/lib/gex/types'
import HeaderMetrics from '@/components/gex/HeaderMetrics'
import CallStructure from '@/components/gex/CallStructure'
import KeyGammaLevels from '@/components/gex/KeyGammaLevels'
import NetGexChart from '@/components/gex/NetGexChart'
import ExpectedMove from '@/components/gex/ExpectedMove'
import ReactionFramework from '@/components/gex/ReactionFramework'
import PositioningRegime from '@/components/gex/PositioningRegime'
import StructureBalanceCard from '@/components/gex/StructureBalance'
import FlowDiagnostics from '@/components/gex/FlowDiagnostics'
import SkewMeasures from '@/components/gex/SkewMeasures'

// Market hours gate (ET) — only auto-refresh while open.
function isMarketOpen(): boolean {
  const now = new Date()
  const day = now.getUTCDay()
  if (day === 0 || day === 6) return false
  const utcMin = now.getUTCHours() * 60 + now.getUTCMinutes()
  const month = now.getUTCMonth()
  const isDST = month >= 2 && month <= 9
  const etMin = utcMin - (isDST ? 4 : 5) * 60
  return etMin >= 570 && etMin < 975
}

export default function GexProfilePage() {
  const symbol = 'SPY'
  const [data, setData] = useState<GexAnalysisData | null>(null)
  const [allData, setAllData] = useState<GexAllData | null>(null)
  const [loading, setLoading] = useState(true)
  const [allLoading, setAllLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [updated, setUpdated] = useState<Date | null>(null)

  const fetchFast = useCallback(async () => {
    try {
      setError(null)
      const r = await fetch(`/api/gex/analysis?symbol=${symbol}`, { cache: 'no-store' })
      const j = await r.json()
      if (j?.success) {
        setData(j.data)
        setUpdated(new Date())
      } else {
        setError(j?.message || 'GEX data unavailable')
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchAll = useCallback(async () => {
    try {
      setAllLoading(true)
      const r = await fetch(`/api/gex/analysis-all?symbol=${symbol}`, { cache: 'no-store' })
      const j = await r.json()
      if (j?.success) setAllData(j.data)
    } catch {
      /* full board is best-effort */
    } finally {
      setAllLoading(false)
    }
  }, [])

  useEffect(() => { fetchFast() }, [fetchFast])
  useEffect(() => { fetchAll() }, [fetchAll])

  useEffect(() => {
    const id = setInterval(() => {
      if (isMarketOpen()) { fetchFast(); fetchAll() }
    }, 30000)
    return () => clearInterval(id)
  }, [fetchFast, fetchAll])

  const balanceLabel = allData?.structure_balance?.label || 'Balanced'

  return (
    <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">GEX Profile <span className="text-amber-400">{symbol}</span></h1>
          <p className="text-sm text-gray-500">0DTE gamma exposure — nearest expiration. Net gamma by strike, walls, flip, and ±1σ.</p>
        </div>
        <div className="text-xs text-gray-500 text-right">
          {updated && <div>Updated {updated.toLocaleTimeString()}</div>}
          {!isMarketOpen() && <div className="text-amber-300">Data as of last close</div>}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">{error}</div>
      )}

      {loading && !data ? (
        <div className="h-64 flex items-center justify-center text-gray-500">Loading GEX profile…</div>
      ) : data ? (
        <>
          <HeaderMetrics data={data} />
          <CallStructure data={data} />

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <ReactionFramework data={data} balanceLabel={balanceLabel} />
            <PositioningRegime positioning={data.positioning} />
            <div className="space-y-6">
              <KeyGammaLevels data={data} allData={allData || undefined} allLoading={allLoading && !allData} />
              <StructureBalanceCard sb={allData?.structure_balance} loading={allLoading && !allData} />
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <NetGexChart
              title={`${symbol} Net GEX — ${data.expiration} (0DTE)`}
              strikes={data.gex_chart.strikes}
              price={data.levels.price}
              flip={data.levels.gex_flip}
              upper1sd={data.levels.upper_1sd}
              lower1sd={data.levels.lower_1sd}
              windowPct={0.05}
              subtitle={
                <ExpectedMove
                  price={data.levels.price}
                  expectedMove={data.levels.expected_move}
                  upper1sd={data.levels.upper_1sd}
                  lower1sd={data.levels.lower_1sd}
                />
              }
              emptyMessage="Real-time data not available outside market hours (8:30am–3:00pm CT)."
            />
            <NetGexChart
              title={`${symbol} Net GEX — All Expirations`}
              strikes={allData?.gex_chart_all.strikes || []}
              price={allData?.spot_price ?? data.levels.price}
              flip={data.levels.gex_flip}
              windowPct={0.12}
              loading={allLoading && !allData}
              emptyMessage="Full-board aggregate unavailable."
            />
          </div>

          <FlowDiagnostics data={data} />
          <SkewMeasures data={data} />
        </>
      ) : null}
    </main>
  )
}
