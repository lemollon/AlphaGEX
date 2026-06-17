'use client'

import { useEffect, useRef, useState } from 'react'
import { type BuildStatus } from '@/app/ember/page'

/* ------------------------------------------------------------------ */
/*  Helpers                                                             */
/* ------------------------------------------------------------------ */

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

function secondsSince(isoString: string | null): number {
  if (!isoString) return 0
  const delta = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000)
  return Math.max(0, delta)
}

function formatAge(seconds: number): string {
  if (seconds < 2) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  const m = Math.floor(seconds / 60)
  return `${m}m ago`
}

/* ------------------------------------------------------------------ */
/*  Props                                                               */
/* ------------------------------------------------------------------ */

interface Props {
  status: BuildStatus
  onStop: () => void
  onRetry: () => void
  canceling?: boolean
}

/* ------------------------------------------------------------------ */
/*  Component                                                           */
/* ------------------------------------------------------------------ */

export default function EmberBuildProgress({ status, onStop, onRetry, canceling }: Props) {
  const [, setTick] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Tick every second to update elapsed + heartbeat displays
  useEffect(() => {
    timerRef.current = setInterval(() => setTick((t) => t + 1), 1000)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [])

  const st = status.status
  const isPending = st === 'pending'
  const isRunning = st === 'running'
  const isCanceling = canceling || st === 'canceled' && canceling
  const isActive = isPending || isRunning || isCanceling
  const isFailed = st === 'failed'
  const isCanceled = st === 'canceled'
  const isCompleted = st === 'completed'

  const progress = Math.max(0, Math.min(100, status.progress ?? 0))
  const elapsedSec = secondsSince(status.created_at)
  const ageSec = secondsSince(status.updated_at)

  // Stuck = active + no update for >45s
  const STUCK_THRESHOLD = 45
  const isStuck = isActive && !canceling && ageSec > STUCK_THRESHOLD

  /* -- derived display values -- */
  const phaseLabel: string = (() => {
    if (isCanceling) return 'Canceling...'
    if (isCanceled) return 'Build Canceled'
    if (isFailed) return 'Build Failed'
    if (isCompleted) return 'Build Complete'
    if (isPending) return 'Build Queued'
    return 'Building Universe...'
  })()

  const progressMessage = status.progress_message?.trim() || null
  const displayMessage: string = (() => {
    if (progressMessage) return progressMessage
    if (isCanceling) return 'Waiting for the worker to acknowledge cancellation...'
    if (isCanceled) return 'Build canceled — adjust parameters and rebuild.'
    if (isFailed) return status.error ?? 'An unknown error occurred.'
    if (isPending) return 'Waiting for an available worker...'
    return 'Processing...'
  })()

  /* -- bar appearance -- */
  const showIndeterminate = isActive && progress === 0
  const showDeterminate = !isFailed && !isCanceled && progress > 0

  /* -- border/bg per state -- */
  const cardClass = isFailed
    ? 'border-red-500/30 bg-red-500/8'
    : isCanceled
    ? 'border-amber-500/20 bg-forge-card/60'
    : 'border-amber-500/20 bg-forge-card/80'

  /* -- stop button -- */
  const showStopButton = (isPending || isRunning) && !canceling
  const stopButtonDisabled = canceling ?? false

  return (
    <>
      {/* Keyframe animations injected into <head> via a style tag */}
      <style>{`
        @keyframes ember-indeterminate {
          0%   { transform: translateX(-100%); }
          100% { transform: translateX(400%); }
        }
        @keyframes ember-shimmer {
          0%   { opacity: 0.5; }
          50%  { opacity: 1; }
          100% { opacity: 0.5; }
        }
        .ember-indeterminate-bar {
          animation: ember-indeterminate 1.6s cubic-bezier(0.4, 0, 0.2, 1) infinite;
          width: 40%;
          background: linear-gradient(90deg, transparent, #FF5500, #ff8a3d, #FF5500, transparent);
        }
        .ember-shimmer-overlay {
          animation: ember-shimmer 2s ease-in-out infinite;
        }
      `}</style>

      <div className={`rounded-xl border p-4 ${cardClass}`}>
        {/* ── Header row ── */}
        <div className="flex items-center gap-2 mb-3">
          {/* Status indicator glyph */}
          {isFailed ? (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="shrink-0 text-red-400">
              <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.4" />
              <path d="M5.5 5.5L10.5 10.5M10.5 5.5L5.5 10.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
          ) : isCanceled ? (
            /* Square (stopped) glyph */
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="shrink-0 text-amber-500/60">
              <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.4" />
              <rect x="5" y="5" width="6" height="6" rx="1" fill="currentColor" />
            </svg>
          ) : isActive ? (
            /* Animated pulse dot */
            <span className="w-2.5 h-2.5 rounded-full shrink-0 bg-amber-400 animate-pulse" />
          ) : (
            /* Static dot for completed */
            <span className="w-2.5 h-2.5 rounded-full shrink-0 bg-amber-400" />
          )}

          <span className={`text-sm font-medium ${
            isFailed ? 'text-red-400' : isCanceled ? 'text-amber-500/60' : 'text-amber-300'
          }`}>
            {phaseLabel}
          </span>

          {/* Elapsed timer — only while active */}
          {isActive && status.created_at && (
            <span className="text-xs text-forge-muted font-mono ml-auto">
              {formatElapsed(elapsedSec)}
            </span>
          )}

          {/* Build ID (right-aligned when no timer) */}
          {!isActive && (
            <span className="ml-auto text-xs text-forge-muted font-mono">{status.build_id}</span>
          )}

          {/* Stop button */}
          {showStopButton && (
            <button
              onClick={onStop}
              disabled={stopButtonDisabled}
              title="Cancel this build"
              className="ml-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium
                         border border-amber-500/30 text-amber-400/80 hover:text-amber-300 hover:border-amber-500/60
                         bg-amber-500/5 hover:bg-amber-500/15 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {/* Stop/square SVG glyph */}
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                <rect x="1" y="1" width="8" height="8" rx="1.5" fill="currentColor" />
              </svg>
              Stop
            </button>
          )}

          {/* Canceling feedback (replaces stop button) */}
          {canceling && (isPending || isRunning) && (
            <span className="ml-2 text-xs text-amber-500/70 font-medium">
              Canceling...
            </span>
          )}
        </div>

        {/* ── Phase message ── */}
        <div className="mb-3">
          <p className={`text-xs ${isFailed ? 'text-red-400/80' : isCanceled ? 'text-amber-500/50' : 'text-forge-muted'}`}>
            {displayMessage}
          </p>
        </div>

        {/* ── Progress bar ── */}
        {!isFailed && !isCanceled && (
          <div className="mb-3">
            <div className="flex justify-between text-xs text-forge-muted mb-1.5">
              <span>{showIndeterminate ? 'Initializing...' : `${progress}% complete`}</span>
              {progress > 0 && <span>{progress}%</span>}
            </div>
            <div className="h-2 bg-forge-bg rounded-full overflow-hidden relative">
              {showIndeterminate ? (
                /* Indeterminate animated shimmer bar */
                <div className="absolute inset-0 overflow-hidden rounded-full">
                  <div className="ember-indeterminate-bar h-full rounded-full absolute left-0 top-0" />
                </div>
              ) : showDeterminate ? (
                /* Determinate bar with shimmer overlay */
                <div
                  className="h-full rounded-full transition-all duration-500 relative overflow-hidden"
                  style={{
                    width: `${progress}%`,
                    background: 'linear-gradient(90deg, #b83c12, #FF5500, #ff8a3d)',
                  }}
                >
                  {/* Animated shimmer overlay — keeps bar looking alive */}
                  <div
                    className="ember-shimmer-overlay absolute inset-0 rounded-full"
                    style={{ background: 'linear-gradient(90deg, transparent 30%, rgba(255,255,255,0.18) 50%, transparent 70%)' }}
                  />
                </div>
              ) : (
                /* Completed — full green */
                <div className="h-full w-full rounded-full bg-emerald-500/70" />
              )}
            </div>
          </div>
        )}

        {/* Canceled bar — muted amber, full width */}
        {isCanceled && (
          <div className="mb-3">
            <div className="h-2 bg-forge-bg rounded-full overflow-hidden">
              <div className="h-full w-full rounded-full bg-amber-500/20" />
            </div>
          </div>
        )}

        {/* ── Stuck warning ── */}
        {isStuck && (
          <div className="flex items-center gap-2 mb-3 px-3 py-2 rounded-lg border border-amber-500/30 bg-amber-500/8">
            {/* Warning triangle glyph */}
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="shrink-0 text-amber-400">
              <path d="M7 1.5L13 12H1L7 1.5Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
              <path d="M7 6V8.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
              <circle cx="7" cy="10.5" r="0.65" fill="currentColor" />
            </svg>
            <span className="text-xs text-amber-400 flex-1">
              No progress for {ageSec}s — the build may be stuck.
            </span>
            <button
              onClick={onRetry}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium
                         border border-amber-500/40 text-amber-400 hover:bg-amber-500/15 transition-all"
            >
              {/* Refresh/retry glyph */}
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                <path d="M8.5 5A3.5 3.5 0 1 1 5 1.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                <path d="M5 1.5L6.5 3H3.5L5 1.5Z" fill="currentColor" />
              </svg>
              Retry
            </button>
          </div>
        )}

        {/* ── Heartbeat / last update ── */}
        {isActive && status.updated_at && (
          <div className="flex items-center gap-1.5 text-xs text-forge-muted/70 mb-2">
            {/* Heartbeat dot */}
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500/50 shrink-0" />
            <span>updated {formatAge(ageSec)}</span>
          </div>
        )}

        {/* ── Canceled message ── */}
        {isCanceled && (
          <div className="flex items-center gap-2 mt-2">
            <p className="text-xs text-amber-500/60">
              Build canceled — adjust parameters and rebuild.
            </p>
            <button
              onClick={onRetry}
              className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                         border border-amber-500/30 text-amber-400 hover:bg-amber-500/15 transition-all"
            >
              {/* Play glyph */}
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                <path d="M2 1.5L8.5 5L2 8.5V1.5Z" fill="currentColor" />
              </svg>
              Rebuild
            </button>
          </div>
        )}

        {/* ── Failed message + retry ── */}
        {isFailed && (
          <div className="flex items-start gap-2 mt-1">
            {status.error && (
              <p className="text-sm text-red-400 flex-1">{status.error}</p>
            )}
            <button
              onClick={onRetry}
              className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                         border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-all"
            >
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                <path d="M8.5 5A3.5 3.5 0 1 1 5 1.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                <path d="M5 1.5L6.5 3H3.5L5 1.5Z" fill="currentColor" />
              </svg>
              Retry
            </button>
          </div>
        )}

        {/* ── Footer metadata ── */}
        <div className="flex flex-wrap gap-4 text-xs text-forge-muted/60 mt-2">
          {status.n_days != null && (
            <span>{status.n_days} trading days</span>
          )}
          {status.created_at && (
            <span>Started {new Date(status.created_at).toLocaleTimeString()}</span>
          )}
          <span className="font-mono">{status.build_id}</span>
        </div>
      </div>
    </>
  )
}
