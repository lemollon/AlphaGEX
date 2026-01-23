'use client'

import Navigation from '@/components/Navigation'
import BotReportArchive from '@/components/trader/BotReportArchive'

export default function ICARUSReportsArchivePage() {
  return (
    <div className="min-h-screen bg-bg-primary">
      <Navigation />

      <main className="pt-24 transition-all duration-300">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <BotReportArchive
            botName="ICARUS"
            botDisplayName="ICARUS"
            brandColor="orange"
            backLink="/icarus"
          />
        </div>
      </main>
    </div>
  )
}
