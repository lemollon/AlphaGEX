'use client'

import { useState } from 'react'

type Scenario = 'climb' | 'dip' | 'chop'

/**
 * Illustrative-only paths (viewBox 0 0 560 290) — made up to demonstrate the
 * rule ("size only climbs after a new high"), not real account data.
 */
const SCENARIOS: Record<Scenario, { value: string; step: string }> = {
  climb: {
    value: 'M10 230 L90 200 L170 205 L250 160 L330 140 L410 110 L490 90 L550 70',
    step: 'M10 250 H170 V220 H330 V180 H490 V150 H550',
  },
  dip: {
    value: 'M10 200 L90 150 L170 120 L250 180 L330 230 L410 200 L490 170 L550 160',
    step: 'M10 240 H170 V180 H550',
  },
  chop: {
    value: 'M10 180 L90 140 L170 190 L250 150 L330 195 L410 145 L490 185 L550 150',
    step: 'M10 230 H250 V210 H550',
  },
}

const CHIPS: Array<{ id: Scenario; label: string }> = [
  { id: 'climb', label: 'Steady climb' },
  { id: 'dip', label: 'Down stretch' },
  { id: 'chop', label: 'Choppy weeks' },
]

/** The Ladder chart — /how-it-works `#ladder`. */
export default function LadderChart() {
  const [scenario, setScenario] = useState<Scenario>('climb')
  const paths = SCENARIOS[scenario]

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
        <path d={paths.step} fill="none" stroke="var(--accent)" strokeWidth={2.5} strokeLinejoin="round" />
        <path d={paths.value} fill="none" stroke="var(--spark)" strokeWidth={2} strokeLinecap="round" />
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
