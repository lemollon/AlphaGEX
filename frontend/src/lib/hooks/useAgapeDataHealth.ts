'use client'

// Powers the amber data-health bar on /perpetuals-crypto. See
// backend/api/routes/agape_perpetuals_data_health_routes.py.

import useSWR from 'swr'

const API = process.env.NEXT_PUBLIC_API_URL || ''

export type BotDataHealth = {
  bot_id: string
  label: string
  last_scan: string | null
  minutes_since_scan: number | null
  funding_regime: string | null
  funding_unknown: boolean
  stale: boolean
  healthy: boolean
}

export type DataHealth = {
  healthy: boolean
  bots: BotDataHealth[]
  unknown_count: number
  stale_count: number
  checked_at: string
}

const fetcher = (url: string) =>
  fetch(url).then(r => {
    if (!r.ok) throw new Error(`API error ${r.status}`)
    return r.json() as Promise<DataHealth>
  })

export function useAgapeDataHealth(refreshInterval = 30_000) {
  const { data, error, isLoading } = useSWR<DataHealth>(
    `${API}/api/agape-perpetuals/data-health`,
    fetcher,
    { refreshInterval, dedupingInterval: 10_000 },
  )
  return { health: data, isLoading, error: error as Error | undefined }
}
