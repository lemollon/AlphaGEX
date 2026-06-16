'use client'

import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import { botVolMessage, type VolAlert, type VolBot, type VolTone } from '@/lib/volAlerts'
import { regimeBannerText, type AdvisorPayload } from '@/lib/volatility'

const REFRESH = 60_000

interface AlertsPayload {
  alerts: VolAlert[]
}

/** Tone → forge-token color classes for the thin banner. */
const TONE_CLASS: Record<VolTone, string> = {
  warn: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
  bull: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  bear: 'border-red-500/40 bg-red-500/10 text-red-300',
  info: 'border-sky-500/40 bg-sky-500/10 text-sky-200',
}

const TONE_LABEL: Record<VolTone, string> = {
  warn: 'Vol Warning',
  bull: 'Vol Tailwind',
  bear: 'Vol Headwind',
  info: 'Vol Note',
}

/**
 * Thin, full-width volatility-regime banner. ALWAYS renders the live regime
 * headline; when a `bot` is supplied, a directional alert relevant to that bot
 * kind takes priority over the headline. Omit `bot` on non-bot pages (GEX
 * Profile, Volatility) to show the bot-agnostic regime headline.
 * Links to /volatility for the full picture.
 */
export default function VolRegimeBanner({ bot }: { bot?: VolBot }) {
  const { data } = useSWR<AlertsPayload>('/api/vol-alerts?status=active', fetcher, {
    refreshInterval: REFRESH,
  })
  // Live regime feed — drives the always-on headline when no alert is firing.
  const { data: vol } = useSWR<AdvisorPayload>('/api/volatility', fetcher, {
    refreshInterval: REFRESH,
  })

  // ALWAYS render so the vol status is persistent on every page (sticky at the top, never
  // absent — it stays put when the regime changes). Priority:
  //   1. an active directional alert tailored to this bot (warn/bull/bear) — bot pages only, else
  //   2. the live regime headline (regime + term structure + stance), else
  //   3. a neutral "conditions normal" note (first-fetch / feed unavailable).
  const regimeText = regimeBannerText(vol?.report)
  const msg: { tone: VolTone; text: string } =
    (bot ? botVolMessage(bot, data?.alerts) : null)
    ?? (regimeText
      ? { tone: 'info', text: regimeText }
      : { tone: 'info', text: 'No active vol-regime alert — conditions normal.' })

  return (
    <a
      href="/volatility"
      className={`sticky top-0 z-30 block rounded-lg border px-3 py-2 text-xs backdrop-blur-sm transition-opacity hover:opacity-90 ${TONE_CLASS[msg.tone]}`}
    >
      <span className="font-semibold uppercase tracking-wider">{TONE_LABEL[msg.tone]}</span>
      <span className="mx-2 opacity-40">·</span>
      <span>{msg.text}</span>
      <span className="ml-2 opacity-60 underline underline-offset-2">view regime →</span>
    </a>
  )
}
