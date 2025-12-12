'use client'

import BotLogsPage from '@/components/logs/BotLogsPage'

export default function AtlasLogsPage() {
  return (
    <BotLogsPage
      botName="ATLAS"
      botColor="text-blue-400"
      botDescription="Mean-reversion bot - Trades reversals at key GEX levels with tight risk management"
    />
  )
}
