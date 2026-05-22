'use client'

import { type BuildParams } from '@/app/ember/page'

interface Props {
  params: BuildParams
  onChange: (p: BuildParams) => void
  onBuild: () => void
  loading: boolean
}

const FILL_OPTIONS: { value: BuildParams['fill']; label: string; desc: string }[] = [
  { value: 'ask_cross', label: 'Ask Cross', desc: 'Opens at ask + 1¢ (conservative)' },
  { value: 'mid', label: 'Mid', desc: 'Opens at bid/ask midpoint' },
  { value: 'mid_slip', label: 'Mid + Slip', desc: 'Mid with 10% slippage' },
]

export default function EmberBuildForm({ params, onChange, onBuild, loading }: Props) {
  function set<K extends keyof BuildParams>(k: K, v: BuildParams[K]) {
    onChange({ ...params, [k]: v })
  }

  // Entry minute options: every 30 min from 0 to 360 (09:30 to 15:30 ET)
  const entryOptions: { value: number; label: string }[] = []
  for (let m = 0; m <= 360; m += 30) {
    const totalMin = 9 * 60 + 30 + m
    const h = Math.floor(totalMin / 60)
    const min = totalMin % 60
    const ampm = h < 12 ? 'AM' : 'PM'
    const h12 = h > 12 ? h - 12 : h === 0 ? 12 : h
    entryOptions.push({
      value: m,
      label: `${h12}:${String(min).padStart(2, '0')} ${ampm} ET (+${m}min)`,
    })
  }

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-5">
      {/* Section header */}
      <div className="flex items-center gap-2 mb-4">
        {/* Gear glyph */}
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="text-amber-400">
          <circle cx="8" cy="8" r="2.5" stroke="currentColor" strokeWidth="1.4" />
          <path
            d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M2.93 2.93l1.06 1.06M12.01 12.01l1.06 1.06M2.93 13.07l1.06-1.06M12.01 3.99l1.06-1.06"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
          />
        </svg>
        <h2 className="text-sm font-semibold text-gray-300">Entry Configuration</h2>
        <span className="text-xs text-forge-muted ml-1">— changes require a new build</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {/* Start date */}
        <div className="lg:col-span-1">
          <label className="block text-xs text-forge-muted mb-1.5">Start Date</label>
          <input
            type="date"
            value={params.start}
            onChange={(e) => set('start', e.target.value)}
            className="w-full bg-forge-bg border border-forge-border rounded-lg px-2.5 py-2 text-sm text-gray-200 focus:outline-none focus:border-amber-500/60"
          />
        </div>

        {/* End date */}
        <div className="lg:col-span-1">
          <label className="block text-xs text-forge-muted mb-1.5">End Date</label>
          <input
            type="date"
            value={params.end}
            onChange={(e) => set('end', e.target.value)}
            className="w-full bg-forge-bg border border-forge-border rounded-lg px-2.5 py-2 text-sm text-gray-200 focus:outline-none focus:border-amber-500/60"
          />
        </div>

        {/* Entry time */}
        <div className="lg:col-span-1">
          <label className="block text-xs text-forge-muted mb-1.5">
            Entry Time ET
            <span className="ml-1 text-forge-muted/60">(minutes since 09:30)</span>
          </label>
          <select
            value={params.entry_minute}
            onChange={(e) => set('entry_minute', parseInt(e.target.value, 10))}
            className="w-full bg-forge-bg border border-forge-border rounded-lg px-2.5 py-2 text-sm text-gray-200 focus:outline-none focus:border-amber-500/60"
          >
            {entryOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        {/* Short delta */}
        <div className="lg:col-span-1">
          <label className="block text-xs text-forge-muted mb-1.5">
            Short Delta
            <span className="ml-1 text-forge-muted/60">(0.05–0.30)</span>
          </label>
          <input
            type="number"
            min={0.05}
            max={0.30}
            step={0.01}
            value={params.short_delta}
            onChange={(e) => set('short_delta', parseFloat(e.target.value))}
            className="w-full bg-forge-bg border border-forge-border rounded-lg px-2.5 py-2 text-sm text-gray-200 focus:outline-none focus:border-amber-500/60"
          />
        </div>

        {/* Wing width */}
        <div className="lg:col-span-1">
          <label className="block text-xs text-forge-muted mb-1.5">
            Wing Width $
            <span className="ml-1 text-forge-muted/60">(1–20)</span>
          </label>
          <input
            type="number"
            min={1}
            max={20}
            step={1}
            value={params.wing_width}
            onChange={(e) => set('wing_width', parseInt(e.target.value, 10))}
            className="w-full bg-forge-bg border border-forge-border rounded-lg px-2.5 py-2 text-sm text-gray-200 focus:outline-none focus:border-amber-500/60"
          />
        </div>

        {/* Fill model */}
        <div className="lg:col-span-1">
          <label className="block text-xs text-forge-muted mb-1.5">Fill Model</label>
          <select
            value={params.fill}
            onChange={(e) => set('fill', e.target.value as BuildParams['fill'])}
            className="w-full bg-forge-bg border border-forge-border rounded-lg px-2.5 py-2 text-sm text-gray-200 focus:outline-none focus:border-amber-500/60"
          >
            {FILL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value} title={o.desc}>
                {o.label}
              </option>
            ))}
          </select>
          <p className="text-[10px] text-forge-muted mt-1">
            {FILL_OPTIONS.find((o) => o.value === params.fill)?.desc}
          </p>
        </div>
      </div>

      {/* Build button */}
      <div className="flex items-center gap-4 mt-5 pt-4 border-t border-forge-border/50">
        <button
          onClick={onBuild}
          disabled={loading}
          className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold transition-all ${
            loading
              ? 'bg-amber-500/20 text-amber-400/60 cursor-not-allowed'
              : 'bg-amber-500/20 hover:bg-amber-500/30 text-amber-400 border border-amber-500/40 hover:border-amber-500/60'
          }`}
        >
          {loading ? (
            <>
              {/* Spinner glyph */}
              <svg
                width="14"
                height="14"
                viewBox="0 0 14 14"
                fill="none"
                className="animate-spin"
              >
                <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.5" strokeDasharray="26" strokeDashoffset="10" />
              </svg>
              Building...
            </>
          ) : (
            <>
              {/* Play glyph */}
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M3 2.5L11 7L3 11.5V2.5Z" fill="currentColor" />
              </svg>
              Build / Load
            </>
          )}
        </button>
        <p className="text-xs text-forge-muted">
          Cached builds return instantly &mdash; only rebuild if you change entry parameters.
        </p>
      </div>
    </div>
  )
}
