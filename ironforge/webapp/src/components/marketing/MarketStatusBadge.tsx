'use client'

import { useEffect, useState } from 'react'
import { marketStatusLabel } from '@/lib/marketing/marketStatus'

/** "Checking" during SSR/hydration, then the live market-clock state, matching the design's wording
 * ("Market open" / "Pre-market" / "After hours" / "Market closed"). */
export default function MarketStatusBadge() {
  const [label, setLabel] = useState<string | null>(null)

  useEffect(() => {
    const tick = () => setLabel(marketStatusLabel())
    tick()
    const id = setInterval(tick, 30_000)
    return () => clearInterval(id)
  }, [])

  const open = label === 'Market open'
  return (
    <span className={`status${open ? ' on' : ''}`}>
      <i />
      <span>{label ?? 'Checking'}</span>
    </span>
  )
}
