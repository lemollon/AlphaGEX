'use client'

import { useEffect, useState } from 'react'
import MarketStatusBadge from './MarketStatusBadge'
import { minutesSinceMidnightCT } from '@/lib/marketing/marketStatus'

const STEPS = [
  { start: 510, time: '8:30 AM', title: 'Market opens', body: 'Conditions tracked in real time' },
  { start: 540, time: '9:00 AM', title: 'Analyze', body: 'Opportunities checked against the rules' },
  { start: 600, time: '10:00 AM', title: 'Execute', body: 'Trades placed only when every rule passes' },
  { start: 630, time: 'All day', title: 'Monitor', body: 'Positions and risk watched continuously' },
  { start: 900, time: '3:00 PM', title: 'Review', body: 'Results logged for tomorrow' },
]

function currentStepIndex(minutes: number): number {
  let idx = -1
  STEPS.forEach((s, i) => {
    if (minutes >= s.start) idx = i
  })
  return idx
}

/** Live 5-step daily routine — /how-it-works `#how-day`. */
export default function DayTimeline() {
  const [clock, setClock] = useState<string>('--:--')
  const [nowIdx, setNowIdx] = useState<number>(-1)

  useEffect(() => {
    const tick = () => {
      const d = new Date()
      const ct = new Date(d.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
      setClock(ct.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }))
      setNowIdx(currentStepIndex(minutesSinceMidnightCT()))
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
        {STEPS.map((s, i) => (
          <div key={s.title} className={`tl-step${i === nowIdx ? ' now' : ''}${i < nowIdx ? ' done' : ''}`}>
            <span className="t">{s.time}</span>
            <b>{s.title}</b>
            <small>{s.body}</small>
          </div>
        ))}
      </div>
    </div>
  )
}
