'use client'

import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import {
  regimeLabel,
  type AdvisorPayload,
  type AdvisorHistoryRow,
} from '@/lib/volatility'
import ActionCard from '@/components/vol/ActionCard'
import RecommendationCard from '@/components/vol/RecommendationCard'
import OutlookCard from '@/components/vol/OutlookCard'
import SignalsPanel from '@/components/vol/SignalsPanel'
import TermStructureCurve from '@/components/vol/TermStructureCurve'
import VixVvixChart from '@/components/vol/VixVvixChart'
import TimingChart from '@/components/vol/TimingChart'
import TriggerWatch from '@/components/vol/TriggerWatch'
import EvidenceTable from '@/components/vol/EvidenceTable'
import LiveTrackRecord from '@/components/vol/LiveTrackRecord'
import AlertsFeed from '@/components/vol/AlertsFeed'
import GexSummaryBanner from '@/components/gex/GexSummaryBanner'

const REFRESH = 60_000

function fmtNum(x?: number | null): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—'
  return String(x)
}

interface HistoryPayload {
  rows: AdvisorHistoryRow[]
}

export default function VolatilityPage() {
  const { data, error, isLoading } = useSWR<AdvisorPayload>('/api/volatility', fetcher, {
    refreshInterval: REFRESH,
  })
  const { data: historyData } = useSWR<HistoryPayload>(
    '/api/volatility/history',
    fetcher,
    { refreshInterval: REFRESH },
  )

  if (isLoading) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-8">
        <p className="text-sm text-forge-muted">Loading volatility regime…</p>
      </main>
    )
  }

  if (error || !data || (data as any).error) {
    const msg = (data as any)?.error || (error instanceof Error ? error.message : 'unavailable')
    return (
      <main className="mx-auto max-w-3xl px-4 py-8">
        <h1 className="text-lg font-semibold text-white">Volatility Regime</h1>
        <p className="mt-2 text-sm text-forge-muted">Advisor unavailable: {String(msg)}</p>
      </main>
    )
  }

  const report = data.report
  if (!report || report.ok === false) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-8">
        <h1 className="text-lg font-semibold text-white">Volatility Regime</h1>
        <p className="mt-2 text-sm text-forge-muted">
          Advisor returned no recommendation right now.
        </p>
      </main>
    )
  }

  const { inputs, recommendation, timing, signals, outlook } = report

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 md:px-6">
      {/* SPY GEX context strip — same banner the bot dashboards carry, links to GEX Profile. */}
      <div className="mb-4">
        <GexSummaryBanner symbol="SPY" />
      </div>

      {/* Header */}
      <header className="mb-4">
        <h1 className="text-lg font-semibold text-white">Volatility Regime</h1>
        <p className="mt-1 font-mono text-xs text-forge-muted">
          {regimeLabel(report.regime_label)} · VIX {fmtNum(inputs?.vix)} · VVIX{' '}
          {fmtNum(inputs?.vvix)}
          {report.as_of ? ` · ${report.as_of}` : ''}
        </p>
      </header>

      <div className="space-y-3">
        <ActionCard action={report.action} recommendation={recommendation} />

        <AlertsFeed />

        <OutlookCard summary={report.summary} outlook={outlook} />

        <RecommendationCard recommendation={recommendation} timing={timing} />

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <TermStructureCurve inputs={inputs} />
          <VixVvixChart series={report.series} />
        </div>

        {timing?.cdf && timing.cdf.length > 0 && (
          <TimingChart cdf={timing.cdf} p75={timing?.p75_days} />
        )}

        <TriggerWatch signals={signals} />

        <SignalsPanel signals={signals} />

        <EvidenceTable evidence={data.evidence} />

        <LiveTrackRecord record={data.live_record} rows={historyData?.rows} />
      </div>
    </main>
  )
}
