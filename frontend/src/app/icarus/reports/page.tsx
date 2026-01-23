'use client'

import { Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import Navigation from '@/components/Navigation'
import BotReportPage from '@/components/trader/BotReportPage'
import BotReportArchive from '@/components/trader/BotReportArchive'
import { Loader2 } from 'lucide-react'

function ReportsContent() {
  const searchParams = useSearchParams()
  const date = searchParams.get('date')
  const isArchive = searchParams.get('archive') === 'true'

  if (isArchive) {
    return (
      <BotReportArchive
        botName="ICARUS"
        botDisplayName="ICARUS"
        brandColor="orange"
        backLink="/icarus"
      />
    )
  }

  // Show main report page (today or specific date)
  return (
    <BotReportPage
      botName="ICARUS"
      botDisplayName="ICARUS"
      brandColor="orange"
      backLink="/icarus"
      date={date}
    />
  )
}

export default function ICARUSReportsPage() {
  return (
    <div className="min-h-screen bg-bg-primary">
      <Navigation />

      <main className="pt-24 transition-all duration-300">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <Suspense
            fallback={
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-8 h-8 text-orange-400 animate-spin" />
              </div>
            }
          >
            <ReportsContent />
          </Suspense>
        </div>
      </main>
    </div>
  )
}
