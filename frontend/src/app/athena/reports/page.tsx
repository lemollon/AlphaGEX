'use client'

import { useSearchParams } from 'next/navigation'
import BotReportPage from '@/components/trader/BotReportPage'

export default function AthenaReportsPage() {
  const searchParams = useSearchParams()
  const date = searchParams.get('date')

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-6xl mx-auto">
        <BotReportPage
          botName="ATHENA"
          botDisplayName="ATHENA"
          brandColor="cyan"
          backLink="/athena"
          date={date}
        />
      </div>
    </div>
  )
}
