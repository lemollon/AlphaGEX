'use client'

import { useSearchParams } from 'next/navigation'
import BotReportPage from '@/components/trader/BotReportPage'

export default function AnchorReportsPage() {
  const searchParams = useSearchParams()
  const date = searchParams.get('date')

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-6xl mx-auto">
        <BotReportPage
          botName="ANCHOR"
          botDisplayName="ANCHOR"
          brandColor="blue"
          backLink="/anchor"
          date={date}
        />
      </div>
    </div>
  )
}
