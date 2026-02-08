'use client'

import BotReportArchive from '@/components/trader/BotReportArchive'

export default function AresReportArchivePage() {
  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-6xl mx-auto">
        <BotReportArchive
          botName="FORTRESS"
          botDisplayName="FORTRESS"
          brandColor="amber"
          backLink="/fortress"
        />
      </div>
    </div>
  )
}
