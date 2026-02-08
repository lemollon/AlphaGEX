'use client'

import BotReportArchive from '@/components/trader/BotReportArchive'

export default function SolomonReportArchivePage() {
  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-6xl mx-auto">
        <BotReportArchive
          botName="SOLOMON"
          botDisplayName="SOLOMON"
          brandColor="cyan"
          backLink="/solomon"
        />
      </div>
    </div>
  )
}
