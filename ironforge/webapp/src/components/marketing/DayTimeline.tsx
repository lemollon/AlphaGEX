'use client'

import { useEffect, useState } from 'react'
import MarketStatusBadge from './MarketStatusBadge'

const STEPS = [
  { time: '8:30 AM', title: 'Market opens', body: 'Conditions tracked in real time' },
  { time: '9:00 AM', title: 'Analyze', body: 'Opportunities checked against the rules' },
  { time: '10:00 AM', title: 'Execute', body: 'Trades placed only when every rule passes' },
  { time: 'All day', title: 'Monitor', body: 'Positions and risk watched continuously' },
  { time: '3:00 PM', title: 'Review', body: 'Results logged for tomorrow' },
]

/** Live 5-step daily routine — /how-it-works `#how-day`. Flat per design: no active-step highlight. */
export default function DayTimeline() {
  const [clock, setClock] = useState<string>('--:--')

  useEffect(() => {
    const tick = () => {
      const d = new Date()
      const ct = new Date(d.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
      setClock(`${ct.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })} CT`)
    }
    tick()
    const id = setInterval(tick, 30_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="wrap card tl-card" id="day">
      <div className="live-top">
        <span className="t num">{clock}</span>
        <MarketStatusBadge />
      </div>
      <div className="tl">
        {STEPS.map((s) => (
          <div key={s.title} className="tl-step">
            <span className="t">{s.time}</span>
            <b>{s.title}</b>
            <small>{s.body}</small>
          </div>
        ))}
      </div>
    </div>
  )
}
