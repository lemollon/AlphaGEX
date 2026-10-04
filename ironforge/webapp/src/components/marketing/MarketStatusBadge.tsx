'use client'

import { useEffect, useState } from 'react'
import { isMarketOpenNow } from '@/lib/marketing/marketStatus'

/** "Checking" during SSR/hydration, then "Market open" / "Market closed", live. */
export default function MarketStatusBadge() {
  const [open, setOpen] = useState<boolean | null>(null)

  useEffect(() => {
    const tick = () => setOpen(isMarketOpenNow())
    tick()
    const id = setInterval(tick, 30_000)
    return () => clearInterval(id)
  }, [])

  const label = open === null ? 'Checking' : open ? 'Market open' : 'Market closed'
  return (
    <span className={`status${open ? ' on' : ''}`}>
      <i />
      <span>{label}</span>
    </span>
  )
}
