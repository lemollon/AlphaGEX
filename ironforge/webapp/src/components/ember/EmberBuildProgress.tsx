'use client'

import { type BuildStatus } from '@/app/ember/page'

export default function EmberBuildProgress({ status }: { status: BuildStatus }) {
  const isPending = status.status === 'pending'
  const isRunning = status.status === 'running'
  const isFailed = status.status === 'failed'
  const progress = Math.max(0, Math.min(100, status.progress ?? 0))

  return (
    <div className={`rounded-xl border p-4 ${isFailed ? 'border-red-500/30 bg-red-500/8' : 'border-amber-500/20 bg-forge-card/80'}`}>
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        {isFailed ? (
          /* X glyph */
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="shrink-0 text-red-400">
            <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.4" />
            <path d="M5.5 5.5L10.5 10.5M10.5 5.5L5.5 10.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
          </svg>
        ) : (
          /* Pulse dot */
          <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${
            isRunning ? 'bg-amber-400 animate-pulse' : 'bg-gray-500'
          }`} />
        )}
        <span className={`text-sm font-medium ${isFailed ? 'text-red-400' : 'text-amber-300'}`}>
          {isFailed ? 'Build Failed'
            : isPending ? 'Build Queued'
            : 'Building Universe...'}
        </span>
        <span className="ml-auto text-xs text-forge-muted font-mono">{status.build_id}</span>
      </div>

      {/* Progress bar */}
      {!isFailed && (
        <div className="mb-3">
          <div className="flex justify-between text-xs text-forge-muted mb-1.5">
            <span>{status.progress_message ?? 'Processing...'}</span>
            <span>{progress}%</span>
          </div>
          <div className="h-2 bg-forge-bg rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${progress}%`,
                background: isRunning
                  ? 'linear-gradient(90deg, #d97706, #f59e0b, #fbbf24)'
                  : 'rgba(245,158,11,0.3)',
              }}
            />
          </div>
        </div>
      )}

      {/* Error message */}
      {isFailed && status.error && (
        <p className="text-sm text-red-400 mt-1">{status.error}</p>
      )}

      {/* Metadata */}
      {!isFailed && (
        <div className="flex flex-wrap gap-4 text-xs text-forge-muted mt-1">
          {status.n_days != null && (
            <span>{status.n_days} trading days</span>
          )}
          {status.created_at && (
            <span>Started {new Date(status.created_at).toLocaleTimeString()}</span>
          )}
        </div>
      )}
    </div>
  )
}
