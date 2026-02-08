'use client'

import BotReportArchive from '@/components/trader/BotReportArchive'

export default function AnchorReportArchivePage() {
  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-6xl mx-auto">
        <BotReportArchive
          botName="ANCHOR"
          botDisplayName="ANCHOR"
          brandColor="blue"
          backLink="/anchor"
        />
      </div>
    </div>
  )
}
