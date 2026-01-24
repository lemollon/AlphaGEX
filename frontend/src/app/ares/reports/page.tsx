'use client'

import { useSearchParams } from 'next/navigation'
import BotReportPage from '@/components/trader/BotReportPage'

export default function AresReportsPage() {
  const searchParams = useSearchParams()
  const date = searchParams.get('date')

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-6xl mx-auto">
        <BotReportPage
          botName="ARES"
          botDisplayName="ARES"
          brandColor="amber"
          backLink="/ares"
          date={date}
        />
      </div>
    </div>
  )
}
