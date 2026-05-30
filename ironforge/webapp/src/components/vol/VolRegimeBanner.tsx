'use client'

import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import { botVolMessage, type VolAlert, type VolBot, type VolTone } from '@/lib/volAlerts'

const REFRESH = 60_000

interface AlertsPayload {
  alerts: VolAlert[]
}

/** Tone → forge-token color classes for the thin banner. */
const TONE_CLASS: Record<VolTone, string> = {
  warn: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
  bull: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  bear: 'border-red-500/40 bg-red-500/10 text-red-300',
  info: 'border-forge-border bg-forge-card/80 text-forge-muted',
}

const TONE_LABEL: Record<VolTone, string> = {
  warn: 'Vol Warning',
  bull: 'Vol Tailwind',
  bear: 'Vol Headwind',
  info: 'Vol Note',
}

/**
 * Thin, full-width volatility-regime banner tailored to the bot. Renders
 * nothing unless a relevant directional alert is active for this bot kind.
 * Links to /volatility for the full picture.
 */
export default function VolRegimeBanner({ bot }: { bot: VolBot }) {
  const { data } = useSWR<AlertsPayload>('/api/vol-alerts?status=active', fetcher, {
    refreshInterval: REFRESH,
  })

  const msg = botVolMessage(bot, data?.alerts)
  if (!msg) return null

  return (
    <a
      href="/volatility"
      className={`block rounded-lg border px-3 py-2 text-xs transition-opacity hover:opacity-90 ${TONE_CLASS[msg.tone]}`}
    >
      <span className="font-semibold uppercase tracking-wider">{TONE_LABEL[msg.tone]}</span>
      <span className="mx-2 opacity-40">·</span>
      <span>{msg.text}</span>
      <span className="ml-2 opacity-60 underline underline-offset-2">view regime →</span>
    </a>
  )
}
