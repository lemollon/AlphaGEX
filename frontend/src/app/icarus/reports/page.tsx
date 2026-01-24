'use client'

import { useSearchParams } from 'next/navigation'
import BotReportPage from '@/components/trader/BotReportPage'

export default function IcarusReportsPage() {
  const searchParams = useSearchParams()
  const date = searchParams.get('date')

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-6xl mx-auto">
        <BotReportPage
          botName="ICARUS"
          botDisplayName="ICARUS"
          brandColor="orange"
          backLink="/icarus"
          date={date}
        />
      </div>
    </div>
  )
}
