'use client'

import { useState } from 'react'

type Scenario = 'climb' | 'dip' | 'chop'

/** Plot area, in viewBox units (0 0 560 290) — leaves room at left for y-axis
 * labels and below for the x-axis label, matching the design. */
const PLOT_LEFT = 44
const PLOT_RIGHT = 550
const PLOT_TOP = 20
const PLOT_BOTTOM = 250
const Y_MIN = 90
const Y_MAX = 150
const Y_TICKS = [150, 140, 130, 120, 110, 100, 90]
const X_POINTS = [44, 116, 189, 261, 333, 406, 478, 550]

/** Maps an account-value tick (90-150) to its SVG y-coordinate. */
function vy(value: number): number {
  return PLOT_BOTTOM - ((value - Y_MIN) / (Y_MAX - Y_MIN)) * (PLOT_BOTTOM - PLOT_TOP)
}

/** Illustrative-only value paths — made up to demonstrate the rule ("size only
 * climbs after a new high"), not real account data. Each is a sequence of
 * account-value ticks across 8 trading days; the step line is the running
 * high, floored to the nearest 10 — same rule the copy below describes. */
const SCENARIO_VALUES: Record<Scenario, number[]> = {
  climb: [100, 104, 103, 112, 110, 121, 119, 131],
  dip: [100, 108, 115, 95, 90, 98, 105, 112],
  chop: [100, 107, 101, 108, 103, 111, 105, 109],
}

const CHIPS: Array<{ id: Scenario; label: string }> = [
  { id: 'climb', label: 'Steady climb' },
  { id: 'dip', label: 'Down stretch' },
  { id: 'chop', label: 'Choppy weeks' },
]

function toPath(values: number[]): string {
  return values.map((v, i) => `${i === 0 ? 'M' : 'L'}${X_POINTS[i]},${vy(v).toFixed(1)}`).join(' ')
}

/** The Ladder chart — /how-it-works `#ladder`. */
export default function LadderChart() {
  const [scenario, setScenario] = useState<Scenario>('climb')
  const values = SCENARIO_VALUES[scenario]

  // Step line = running high so far, floored to the nearest 10 — "size only climbs after a new high."
  let runningHigh = values[0]
  const stepValues = values.map((v) => {
    runningHigh = Math.max(runningHigh, v)
    return Math.floor(runningHigh / 10) * 10
  })

  const valuePath = toPath(values)
  const stepPath = toPath(stepValues)
  const areaPath = `${valuePath} L${X_POINTS[X_POINTS.length - 1]},${PLOT_BOTTOM} L${X_POINTS[0]},${PLOT_BOTTOM} Z`

  return (
    <div className="card card-pad">
      <div className="chart-head">
        <span>How sizing responds</span>
        <div className="legend">
          <span>
            <i style={{ background: 'var(--spark)' }} />
            Account value
          </span>
          <span>
            <i style={{ background: 'var(--accent)' }} />
            Size step
          </span>
        </div>
      </div>
      <svg
        id="ladderSvg"
        viewBox="0 0 560 290"
        role="img"
        aria-label="Account value moves up and down while size steps only rise at new highs"
      >
        {Y_TICKS.map((t) => (
          <g key={t}>
            <line
              x1={PLOT_LEFT}
              x2={PLOT_RIGHT}
              y1={vy(t)}
              y2={vy(t)}
              stroke="var(--line)"
              strokeWidth={1}
            />
            <text x={PLOT_LEFT - 8} y={vy(t) + 4} textAnchor="end" className="ladder-axis-label">
              {t}
            </text>
          </g>
        ))}
        <path d={areaPath} fill="var(--spark)" fillOpacity={0.08} stroke="none" />
        <path d={stepPath} fill="none" stroke="var(--accent)" strokeWidth={2.5} strokeLinejoin="round" />
        <path d={valuePath} fill="none" stroke="var(--spark)" strokeWidth={2} strokeLinecap="round" />
        <text x={PLOT_LEFT} y={PLOT_BOTTOM + 22} className="ladder-axis-label">
          Trading days →
        </text>
      </svg>
      <div className="seg" role="group" aria-label="Scenario">
        {CHIPS.map((c) => (
          <button
            key={c.id}
            className="chip"
            aria-pressed={scenario === c.id}
            onClick={() => setScenario(c.id)}
            type="button"
          >
            {c.label}
          </button>
        ))}
      </div>
      <p className="fine">Illustration of the rule with made-up paths. Not trading results.</p>
    </div>
  )
}
