'use client'

import BotReportArchive from '@/components/trader/BotReportArchive'

export default function IcarusReportArchivePage() {
  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-6xl mx-auto">
        <BotReportArchive
          botName="ICARUS"
          botDisplayName="ICARUS"
          brandColor="orange"
          backLink="/icarus"
        />
      </div>
    </div>
  )
}
