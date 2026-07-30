import type { Metadata } from 'next'
import TradingViewSettingsClient from './TradingViewSettingsClient'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'TradingView — IronForge',
  description: 'Your IronForge indicator access on TradingView.',
}

/** /account/tradingview — the TradingView indicator perk settings page. */
export default function TradingViewSettingsPage() {
  return <TradingViewSettingsClient />
}
