'use client'

import BotReportArchive from '@/components/trader/BotReportArchive'

export default function AthenaReportArchivePage() {
  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-6xl mx-auto">
        <BotReportArchive
          botName="ATHENA"
          botDisplayName="ATHENA"
          brandColor="cyan"
          backLink="/athena"
        />
      </div>
    </div>
  )
}
