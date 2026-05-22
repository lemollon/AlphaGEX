'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import EmberBuildForm from '@/components/ember/EmberBuildForm'
import EmberBuildProgress from '@/components/ember/EmberBuildProgress'
import EmberExitControls from '@/components/ember/EmberExitControls'
import EmberResults from '@/components/ember/EmberResults'

/* ------------------------------------------------------------------ */
/*  Types                                                               */
/* ------------------------------------------------------------------ */

export interface BuildParams {
  start: string
  end: string
  entry_minute: number
  short_delta: number
  wing_width: number
  fill: 'ask_cross' | 'mid' | 'mid_slip'
}

export interface BuildStatus {
  build_id: string
  params: BuildParams | null
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  progress_message: string | null
  n_days: number | null
  error: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ExitParams {
  profit_target_pct: number
  stop_loss_mult: number
  time_stop_minute: number | null
  trail_activation_pct: number | null
  trail_giveback_pct: number | null
  min_hold_minutes: number
}

export interface SummaryStats {
  n: number
  win_rate: number
  ev_per_contract: number
  total_pnl: number
  sharpe: number | null
  max_drawdown: number | null
  avg_hold_min: number | null
  pct_eod: number | null
}

export interface EquityCurvePoint {
  date: string
  pnl: number
  cum_pnl: number
  is_oos: boolean
}

export interface TradeRow {
  trade_date: string
  entry_minute: number
  exit_minute: number | null
  exit_reason: string
  entry_credit: number
  exit_cost: number
  pnl: number
  max_favorable: number | null
  max_adverse: number | null
  is_oos: boolean
}

export interface PolicyResult {
  policy: string
  in_sample: SummaryStats
  oos: SummaryStats
  equity_curve?: EquityCurvePoint[]
  trades?: TradeRow[]
}

export interface EvaluateResult {
  chosen: PolicyResult
  baseline: PolicyResult
  grid: PolicyResult[]
}

/* ------------------------------------------------------------------ */
/*  Defaults                                                            */
/* ------------------------------------------------------------------ */

const DEFAULT_BUILD: BuildParams = {
  start: '2023-01-03',
  end: '2025-12-05',
  entry_minute: 30,
  short_delta: 0.16,
  wing_width: 5,
  fill: 'ask_cross',
}

const DEFAULT_EXIT: ExitParams = {
  profit_target_pct: 40,
  stop_loss_mult: 1.0,
  time_stop_minute: null,
  trail_activation_pct: null,
  trail_giveback_pct: null,
  min_hold_minutes: 5,
}

/* ------------------------------------------------------------------ */
/*  Page Component                                                      */
/* ------------------------------------------------------------------ */

export default function EmberPage() {
  // Build state
  const [buildParams, setBuildParams] = useState<BuildParams>(DEFAULT_BUILD)
  const [buildId, setBuildId] = useState<string | null>(null)
  const [buildStatus, setBuildStatus] = useState<BuildStatus | null>(null)
  const [buildLoading, setBuildLoading] = useState(false)
  const [buildError, setBuildError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Exit params state
  const [exitParams, setExitParams] = useState<ExitParams>(DEFAULT_EXIT)
  const [evalResult, setEvalResult] = useState<EvaluateResult | null>(null)
  const [evalLoading, setEvalLoading] = useState(false)
  const [evalError, setEvalError] = useState<string | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  /* ---- Poll build status ---- */
  const startPolling = useCallback((id: string) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/ember/build/${id}`)
        if (!res.ok) return
        const data: BuildStatus = await res.json()
        setBuildStatus(data)
        if (data.status === 'completed' || data.status === 'failed') {
          if (pollRef.current) clearInterval(pollRef.current)
          if (data.status === 'completed') {
            runEvaluate(id, exitParams)
          }
        }
      } catch {
        // silently retry
      }
    }, 1500)
  }, [exitParams]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])

  /* ---- Evaluate endpoint ---- */
  const runEvaluate = useCallback(async (id: string, ep: ExitParams) => {
    setEvalLoading(true)
    setEvalError(null)
    try {
      const res = await fetch('/api/ember/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ build_id: id, ...ep }),
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData?.error ?? `HTTP ${res.status}`)
      }
      const data: EvaluateResult = await res.json()
      setEvalResult(data)
    } catch (err: unknown) {
      setEvalError(err instanceof Error ? err.message : String(err))
    } finally {
      setEvalLoading(false)
    }
  }, [])

  /* ---- Debounced exit param change ---- */
  const handleExitChange = useCallback((ep: ExitParams) => {
    setExitParams(ep)
    if (!buildId || buildStatus?.status !== 'completed') return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      runEvaluate(buildId, ep)
    }, 300)
  }, [buildId, buildStatus?.status, runEvaluate])

  /* ---- Build / Load ---- */
  async function handleBuild() {
    setBuildLoading(true)
    setBuildError(null)
    setBuildStatus(null)
    setEvalResult(null)
    setBuildId(null)
    if (pollRef.current) clearInterval(pollRef.current)

    try {
      const res = await fetch('/api/ember/build', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildParams),
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData?.error ?? `HTTP ${res.status}`)
      }
      const data: { build_id: string; status: string; cached?: boolean; n_days?: number } = await res.json()
      setBuildId(data.build_id)

      if (data.status === 'completed' || data.cached) {
        // Fetch full status then evaluate
        const statusRes = await fetch(`/api/ember/build/${data.build_id}`)
        const statusData: BuildStatus = statusRes.ok ? await statusRes.json() : {
          build_id: data.build_id,
          params: buildParams,
          status: 'completed',
          progress: 100,
          progress_message: 'Cached result loaded',
          n_days: data.n_days ?? null,
          error: null,
          created_at: null,
          updated_at: null,
        }
        setBuildStatus(statusData)
        runEvaluate(data.build_id, exitParams)
      } else {
        // Set initial status and start polling
        setBuildStatus({
          build_id: data.build_id,
          params: buildParams,
          status: data.status as 'pending' | 'running',
          progress: 0,
          progress_message: 'Build enqueued...',
          n_days: null,
          error: null,
          created_at: null,
          updated_at: null,
        })
        startPolling(data.build_id)
      }
    } catch (err: unknown) {
      setBuildError(err instanceof Error ? err.message : String(err))
    } finally {
      setBuildLoading(false)
    }
  }

  const buildReady = buildStatus?.status === 'completed'

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-start gap-4">
        <div>
          {/* Custom SVG glyph — stylized flame with a bar chart inside */}
          <svg
            width="40"
            height="40"
            viewBox="0 0 40 40"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="shrink-0"
          >
            <rect width="40" height="40" rx="8" fill="rgba(217,119,6,0.12)" />
            {/* Flame silhouette */}
            <path
              d="M20 6C20 6 14 12 14 19C14 22.3 15.5 24.8 18 26C17 24 17.5 22 19 21C19 23 20 25 20 25C20 25 21 23 21 21C22.5 22 23 24 22 26C24.5 24.8 26 22.3 26 19C26 12 20 6 20 6Z"
              fill="url(#ember-grad)"
            />
            {/* Bar chart lines inside flame */}
            <rect x="17" y="19" width="2" height="5" rx="1" fill="rgba(0,0,0,0.4)" />
            <rect x="20" y="17" width="2" height="7" rx="1" fill="rgba(0,0,0,0.4)" />
            <defs>
              <linearGradient id="ember-grad" x1="20" y1="6" x2="20" y2="26" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stopColor="#fbbf24" />
                <stop offset="100%" stopColor="#d97706" />
              </linearGradient>
            </defs>
          </svg>
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            <span className="text-amber-400">EMBER</span>
            <span className="text-gray-400 font-normal text-lg ml-3">Intraday Iron Condor Exit Optimizer</span>
          </h1>
          <p className="text-sm text-forge-muted mt-1">
            Build a universe of 1DTE SPY IC days, then tune exit parameters instantly.
            Results split in-sample / OOS. Edge is typically negative — optimize for least-bad.
          </p>
        </div>
      </div>

      <div className="fire-divider" />

      {/* Entry config form */}
      <EmberBuildForm
        params={buildParams}
        onChange={setBuildParams}
        onBuild={handleBuild}
        loading={buildLoading}
      />

      {/* Build error */}
      {buildError && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <span className="font-semibold">Build failed: </span>{buildError}
        </div>
      )}

      {/* Build progress */}
      {buildStatus && !buildReady && (
        <EmberBuildProgress status={buildStatus} />
      )}

      {/* Build complete banner */}
      {buildReady && buildStatus && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/8 px-4 py-3 flex items-center gap-3">
          {/* Checkmark glyph */}
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" className="shrink-0">
            <circle cx="9" cy="9" r="8" stroke="#f59e0b" strokeWidth="1.5" />
            <path d="M5.5 9L7.5 11L12.5 7" stroke="#f59e0b" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className="text-sm text-amber-300">
            Build ready &mdash; {buildStatus.n_days ?? '?'} trading days loaded.
            Adjusting exit parameters below re-evaluates instantly.
          </span>
        </div>
      )}

      {/* Exit param controls */}
      <EmberExitControls
        params={exitParams}
        onChange={handleExitChange}
        disabled={!buildReady}
      />

      {/* Evaluate error */}
      {evalError && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <span className="font-semibold">Evaluate failed: </span>{evalError}
        </div>
      )}

      {/* Results */}
      {(evalLoading || evalResult) && (
        <EmberResults
          result={evalResult}
          loading={evalLoading}
        />
      )}
    </div>
  )
}
