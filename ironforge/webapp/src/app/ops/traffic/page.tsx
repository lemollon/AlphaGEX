'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import useSWR, { mutate } from 'swr'
import { fetcher } from '@/lib/fetcher'

/**
 * Operator-only page-view dashboard. Gated by the operator session
 * server-side (/api/ops/traffic), same as /ops/customers.
 *
 * Every count on this page comes from page_views (day, path, rotating daily
 * visitor hash — no IP/UA/cookie is ever stored, see /api/track) plus
 * waitlist_submissions for the two waitlist series. Auto-refreshes every 15
 * minutes; the Refresh button re-fetches on demand.
 */

const KEY = '/api/ops/traffic?days=30'

interface DayCell {
  visitors: number
  views: number
}
interface PageSummary {
  path: string
  totalVisitors: number
  totalViews: number
  byDay: Record<string, DayCell>
}
interface TrafficResp {
  ok: boolean
  error?: string
  generatedAt: string
  tz: string
  days: string[]
  pages: PageSummary[]
  waitlistSubmissions: { total: number; byDay: Record<string, number> }
  firstSeen: string | null
  distinctVisitorsToday: number
  distinctVisitorsLast7Days: number
}

const card = 'rounded-xl border border-forge-border bg-forge-card/80 p-5'
const tileLabel = 'text-[11px] uppercase tracking-wide text-gray-500'
const tileValue = 'mt-1 text-2xl font-bold text-white'

function fmtDay(day: string): string {
  // 'YYYY-MM-DD' → 'MMM D', no timezone conversion needed — the string IS the
  // CT calendar date already (see lib/track.ts ctDateString).
  const [, m, d] = day.split('-')
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${months[Number(m) - 1]} ${Number(d)}`
}

function sum(values: number[]): number {
  return values.reduce((a, b) => a + b, 0)
}

/** Linear-scale polyline points for an inline SVG line chart. */
function polylinePoints(values: number[], width: number, height: number, pad = 3): string {
  const max = Math.max(1, ...values)
  const step = values.length > 1 ? (width - pad * 2) / (values.length - 1) : 0
  return values
    .map((v, i) => {
      const x = pad + i * step
      const y = height - pad - (v / max) * (height - pad * 2)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

/** Small per-row 30-day trend line. Purely decorative — the table cells carry the numbers. */
function Sparkline({ values, color }: { values: number[]; color: string }) {
  const w = 100
  const h = 28
  if (values.every((v) => v === 0)) {
    return <svg width={w} height={h} className="opacity-30" />
  }
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="overflow-visible">
      <polyline points={polylinePoints(values, w, h)} fill="none" stroke={color} strokeWidth={1.5} />
    </svg>
  )
}

/** The Waitlist panel's two-series trend: /waitlist page visitors vs waitlist submissions. */
function WaitlistTrend({ days, visitors, submissions }: { days: string[]; visitors: number[]; submissions: number[] }) {
  const w = 640
  const h = 140
  const visitorColor = '#f59e0b' // amber-500
  const submissionColor = '#34d399' // emerald-400
  return (
    <div>
      <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="overflow-visible">
        <polyline points={polylinePoints(visitors, w, h)} fill="none" stroke={visitorColor} strokeWidth={2} />
        <polyline
          points={polylinePoints(submissions, w, h)}
          fill="none"
          stroke={submissionColor}
          strokeWidth={2}
          strokeDasharray="5,4"
        />
      </svg>
      <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-gray-400">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4" style={{ backgroundColor: visitorColor }} />
          Waitlist page visitors
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 border-t-2 border-dashed" style={{ borderColor: submissionColor }} />
          Waitlist submissions
        </span>
        <span className="text-gray-600">
          {fmtDay(days[0])} – {fmtDay(days[days.length - 1])}
        </span>
      </div>
    </div>
  )
}

export default function OpsTrafficPage() {
  const { data, error, isLoading } = useSWR<TrafficResp>(KEY, fetcher, { refreshInterval: 900_000 })
  const [metric, setMetric] = useState<'visitors' | 'views'>('visitors')
  const [refreshing, setRefreshing] = useState(false)

  const unauthorized = data && data.ok === false

  const last14 = data ? data.days.slice(-14) : []
  const last7 = data ? data.days.slice(-7) : []

  const waitlistPage = useMemo(() => data?.pages.find((p) => p.path === '/waitlist') ?? null, [data])
  const waitlistVisitorsSeries = useMemo(
    () => (data && waitlistPage ? data.days.map((d) => waitlistPage.byDay[d]?.visitors ?? 0) : []),
    [data, waitlistPage],
  )
  const waitlistSubmissionsSeries = useMemo(
    () => (data ? data.days.map((d) => data.waitlistSubmissions.byDay[d] ?? 0) : []),
    [data],
  )
  const waitlistVisitorsLast7 = sum(last7.map((d) => waitlistPage?.byDay[d]?.visitors ?? 0))
  const waitlistSubmissionsLast7 = sum(last7.map((d) => data?.waitlistSubmissions.byDay[d] ?? 0))

  const updatedAt = data?.generatedAt
    ? new Date(data.generatedAt).toLocaleTimeString('en-US', {
        timeZone: 'America/Chicago',
        hour: 'numeric',
        minute: '2-digit',
      })
    : null

  const refresh = async () => {
    setRefreshing(true)
    await mutate(KEY)
    setRefreshing(false)
  }

  return (
    <div className="min-h-screen bg-forge-bg text-white">
      <div className="mx-auto max-w-[1200px] px-4 py-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">Traffic</h1>
            <p className="mt-1 text-sm text-gray-400">
              First-party, privacy-safe page views — no IP, user agent, or cookie is ever stored.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/ops/customers" className="text-sm font-semibold text-amber-400 underline hover:text-amber-300">
              Customers
            </Link>
            <span className="text-xs text-gray-500">{updatedAt ? `Updated ${updatedAt} CT` : ''}</span>
            <button
              type="button"
              onClick={refresh}
              disabled={refreshing || isLoading}
              className="rounded-md border border-forge-border bg-forge-card px-3 py-1.5 text-xs font-semibold text-gray-200 hover:border-amber-500 hover:text-amber-400 disabled:opacity-50"
            >
              {refreshing ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
        </div>

        {unauthorized ? (
          <div className="mt-6 rounded-xl border border-forge-border bg-forge-card/80 p-6 text-sm text-gray-300">
            {data?.error ?? 'Operator session required.'} Sign in with your operator link, then reload this page.
          </div>
        ) : error ? (
          <div className="mt-6 rounded-xl border border-red-900/40 bg-red-950/20 p-6 text-sm text-red-300">
            Failed to load traffic data.
          </div>
        ) : isLoading || !data ? (
          <div className="mt-6 text-sm text-gray-400">Loading…</div>
        ) : data.pages.length === 0 ? (
          <div className="mt-6 rounded-xl border border-forge-border bg-forge-card/80 p-6 text-sm text-gray-400">
            {data.firstSeen
              ? `Collecting since ${new Date(data.firstSeen).toLocaleDateString('en-US', { timeZone: 'America/Chicago' })} — no visits yet.`
              : 'Collecting since today — no visits yet.'}
          </div>
        ) : (
          <>
            {/* Summary tiles */}
            <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className={card}>
                <div className={tileLabel}>Visitors today</div>
                <div className={tileValue}>{data.distinctVisitorsToday.toLocaleString()}</div>
              </div>
              <div className={card}>
                <div className={tileLabel}>Visitors, last 7 days</div>
                <div className={tileValue}>{data.distinctVisitorsLast7Days.toLocaleString()}</div>
              </div>
              <div className={card}>
                <div className={tileLabel}>Waitlist page visitors, 7d</div>
                <div className={tileValue}>{waitlistVisitorsLast7.toLocaleString()}</div>
              </div>
              <div className={card}>
                <div className={tileLabel}>Waitlist submissions, 7d</div>
                <div className={tileValue}>{waitlistSubmissionsLast7.toLocaleString()}</div>
              </div>
            </div>

            {/* Waitlist panel, pinned at top */}
            <section className={`mt-4 ${card}`}>
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-bold uppercase tracking-wide text-amber-500">Waitlist</h2>
                <span className="text-xs text-gray-500">{data.waitlistSubmissions.total.toLocaleString()} submissions all-time</span>
              </div>
              <div className="mt-4">
                <WaitlistTrend days={data.days} visitors={waitlistVisitorsSeries} submissions={waitlistSubmissionsSeries} />
              </div>
            </section>

            {/* Page table */}
            <section className={`mt-4 ${card} overflow-x-auto`}>
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-bold uppercase tracking-wide text-amber-500">Pages (30-day)</h2>
                <div className="flex items-center gap-1 rounded-md border border-forge-border p-0.5 text-xs">
                  <button
                    type="button"
                    onClick={() => setMetric('visitors')}
                    className={`rounded px-2 py-1 font-semibold ${metric === 'visitors' ? 'bg-amber-500 text-black' : 'text-gray-400'}`}
                  >
                    Visitors
                  </button>
                  <button
                    type="button"
                    onClick={() => setMetric('views')}
                    className={`rounded px-2 py-1 font-semibold ${metric === 'views' ? 'bg-amber-500 text-black' : 'text-gray-400'}`}
                  >
                    Views
                  </button>
                </div>
              </div>

              <table className="mt-4 w-full min-w-[900px] border-collapse text-sm">
                <thead>
                  <tr className="border-b border-forge-border text-left text-[11px] uppercase tracking-wide text-gray-500">
                    <th className="py-2 pr-3">Path</th>
                    <th className="px-2 py-2 text-right">30d {metric === 'visitors' ? 'visitors' : 'views'}</th>
                    <th className="px-2 py-2">Trend</th>
                    {last14.map((day) => (
                      <th key={day} className="px-1.5 py-2 text-right font-normal">
                        {fmtDay(day)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.pages.map((p) => {
                    const series = data.days.map((d) => (metric === 'visitors' ? p.byDay[d]?.visitors ?? 0 : p.byDay[d]?.views ?? 0))
                    return (
                      <tr key={p.path} className="border-b border-forge-border/50">
                        <td className="max-w-[220px] truncate py-2 pr-3 font-mono text-xs text-gray-200" title={p.path}>
                          {p.path}
                        </td>
                        <td className="px-2 py-2 text-right font-semibold text-white">
                          {(metric === 'visitors' ? p.totalVisitors : p.totalViews).toLocaleString()}
                        </td>
                        <td className="px-2 py-2">
                          <Sparkline values={series} color="#f59e0b" />
                        </td>
                        {last14.map((day) => {
                          const cell = p.byDay[day] ?? { visitors: 0, views: 0 }
                          const shown = metric === 'visitors' ? cell.visitors : cell.views
                          const tooltip = metric === 'visitors' ? `${cell.views} views` : `${cell.visitors} visitors`
                          return (
                            <td key={day} className="px-1.5 py-2 text-right text-gray-300" title={tooltip}>
                              {shown > 0 ? shown.toLocaleString() : <span className="text-gray-700">·</span>}
                            </td>
                          )
                        })}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </section>
          </>
        )}
      </div>
    </div>
  )
}
