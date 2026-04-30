'use client'

/**
 * LatestBriefCard — small card rendered below the Equity Curve showing the
 * most recent market-risk brief. Bot-aware so each bot dashboard reads its
 * own {bot}_market_briefs table.
 *
 * Controls:
 *   - "Regenerate" button → POST /api/{bot}/briefs/generate?type=intraday
 *     (costs ~$0.03 on Claude; wrapped in a confirm to avoid spam)
 */
import { useState } from 'react'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'

interface Brief {
  id: number
  brief_date: string
  brief_time: string
  brief_type: 'morning' | 'intraday' | 'eod_debrief'
  risk_score: number | null
  summary: string
  factors_json: {
    factors?: Array<{ title: string; detail: string }>
    watch_next_hour?: string | null
    raw?: string
  } | null
  spy_price: number | null
  vix: number | null
  vix3m: number | null
  term_structure: number | null
  model: string | null
}

const BRIEF_REFRESH_MS = 60_000

function riskScoreColor(score: number | null): string {
  if (score == null) return 'text-forge-muted border-forge-border'
  if (score <= 3) return 'text-emerald-400 border-emerald-500/40 bg-emerald-500/10'
  if (score <= 6) return 'text-amber-400 border-amber-500/40 bg-amber-500/10'
  return 'text-red-400 border-red-500/40 bg-red-500/10'
}

function formatCT(ts: string | null): string {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleString('en-US', {
      timeZone: 'America/Chicago',
      month: 'short', day: 'numeric',
      hour: 'numeric', minute: '2-digit',
    }) + ' CT'
  } catch { return ts.slice(0, 16) }
}

function briefTypeLabel(t: string): string {
  if (t === 'morning') return 'Morning Brief'
  if (t === 'intraday') return 'Intraday Brief'
  if (t === 'eod_debrief') return 'EOD Debrief'
  return t
}

/** Strip markdown emphasis so older briefs stored with `**bold**` render as
 * plain text. New briefs are stripped server-side, but historical rows in
 * the {bot}_market_briefs tables may still contain raw markdown — including
 * unbalanced patterns like `**Title*` that paired-only regex misses, so we
 * scrub all asterisks unconditionally. */
function stripMarkdown(s: string | null | undefined): string {
  if (!s) return ''
  return s
    .replace(/\*+/g, '')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^\s*-{3,}\s*$/gm, '')
    .replace(/\s+-{3,}\s*$/g, '')
    .trim()
}

export default function LatestBriefCard({ bot }: { bot: 'flame' | 'spark' | 'inferno' }) {
  const { data, error, isLoading, mutate } = useSWR<{ brief: Brief | null }>(
    `/api/${bot}/briefs/latest`,
    fetcher,
    { refreshInterval: BRIEF_REFRESH_MS },
  )
  const [generating, setGenerating] = useState(false)
  const [genError, setGenError] = useState<string | null>(null)

  const handleGenerate = async () => {
    if (!confirm('Generate a new intraday brief now? (~$0.03 Claude API call)')) return
    setGenerating(true)
    setGenError(null)
    try {
      const resp = await fetch(`/api/${bot}/briefs/generate?type=intraday`, { method: 'POST' })
      const json = await resp.json()
      if (!resp.ok) {
        setGenError(json.error || `HTTP ${resp.status}`)
      } else {
        // Force SWR to refetch /latest now
        await mutate()
      }
    } catch (e) {
      setGenError(e instanceof Error ? e.message : String(e))
    } finally {
      setGenerating(false)
    }
  }

  if (isLoading) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
        <p className="text-forge-muted text-sm animate-pulse">Loading latest brief...</p>
      </div>
    )
  }
  if (error) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4">
        <p className="text-red-400 text-sm">Brief load error: {error.message}</p>
      </div>
    )
  }

  const brief = data?.brief ?? null
  const factors = brief?.factors_json?.factors ?? []
  const watchNextHour = brief?.factors_json?.watch_next_hour ?? null

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 overflow-hidden">
      <div className="px-4 py-3 border-b border-forge-border/50 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap">
          <h3 className="text-sm font-medium text-gray-300">{bot.toUpperCase()} Market-Risk Brief</h3>
          {brief && (
            <>
              <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-mono border ${riskScoreColor(brief.risk_score)}`}>
                Risk: {brief.risk_score != null ? `${brief.risk_score}/10` : '—'}
              </span>
              <span className="text-[11px] text-forge-muted">
                {briefTypeLabel(brief.brief_type)} · {formatCT(brief.brief_time)}
              </span>
              {brief.model && (
                <span className="text-[10px] text-forge-muted/70 font-mono">{brief.model}</span>
              )}
            </>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="text-[11px] font-medium px-2.5 py-1 rounded-md border border-blue-500/40 bg-blue-500/10 text-blue-300 hover:bg-blue-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            title={`POST /api/${bot}/briefs/generate?type=intraday (calls Claude, ~$0.03)`}
          >
            {generating ? 'Generating…' : 'Regenerate'}
          </button>
        </div>
      </div>

      {genError && (
        <div className="px-4 py-2 bg-red-500/10 border-b border-red-500/30 text-red-300 text-xs">
          Generate failed: {genError}
        </div>
      )}

      {!brief ? (
        <div className="p-6 text-center">
          <p className="text-forge-muted text-sm mb-3">No briefs yet. Click "Regenerate" to create the first one.</p>
          <p className="text-[10px] text-forge-muted">
            Briefs cost ~$0.03 each on the Claude API. Auto-scheduling at 7:30 AM / hourly 9-2 / 3:15 PM CT will ship in Q2.
          </p>
        </div>
      ) : (
        <div className="p-4 space-y-4">
          {/* Summary */}
          <div>
            <p className="text-[10px] uppercase tracking-wider text-forge-muted mb-1">Summary</p>
            <p className="text-sm text-gray-200 leading-relaxed whitespace-pre-line">{stripMarkdown(brief.summary)}</p>
          </div>

          {/* Factors */}
          {factors.length > 0 && (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-forge-muted mb-2">Top Risk Factors</p>
              <ol className="space-y-2">
                {factors.map((f, i) => (
                  <li key={i} className="text-xs text-gray-300">
                    <span className="font-semibold text-gray-200">{i + 1}. {stripMarkdown(f.title)}</span>
                    {' — '}
                    <span className="text-gray-400">{stripMarkdown(f.detail)}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Watch next hour */}
          {watchNextHour && (
            <div className="rounded-md bg-amber-500/5 border border-amber-500/30 px-3 py-2">
              <p className="text-[10px] uppercase tracking-wider text-amber-400/80 mb-0.5">Watch Next Hour</p>
              <p className="text-xs text-amber-200">{stripMarkdown(watchNextHour)}</p>
            </div>
          )}

          {/* Market state footer */}
          <div className="flex gap-4 flex-wrap text-[10px] text-forge-muted border-t border-forge-border/50 pt-3">
            {brief.spy_price != null && <span>SPY ${brief.spy_price.toFixed(2)}</span>}
            {brief.vix != null && <span>VIX {brief.vix.toFixed(2)}</span>}
            {brief.vix3m != null && <span>VIX3M {brief.vix3m.toFixed(2)}</span>}
            {brief.term_structure != null && (
              <span>
                Term: {(brief.term_structure * 100).toFixed(2)}%
                {brief.term_structure > 0 ? ' contango' : brief.term_structure < 0 ? ' backwardation' : ''}
              </span>
            )}
            <span className="ml-auto">Brief #{brief.id}</span>
          </div>
        </div>
      )}
    </div>
  )
}
